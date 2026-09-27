/**
 * SSE 스트림 리듀서 — 이벤트 4종(D14·D22) → 화면 A 렌더 단위(`ChatItem[]` + `TraceSession`).
 *
 * **React 를 import 하지 않는다.** `reduceChatEvent` 는 순수 함수(입력 state·event → 새 state)
 * 이고, `runChatTurn` 은 fetch 러너일 뿐이다. 훅·전역 상태·DOM 은 MQ-405 소유다.
 *
 * ## 화면 A(실시간) == 화면 B(재생) — trace 는 `toTraceSession` 재사용
 * 화면 B(`GET .../trace` → `toTraceSession`)와 **같은 스텝**을 그려야 감사 화면의 신뢰가
 * 선다(sprint-4 "매핑 로직을 리듀서에 복제하는 대안은 기각"). 그래서 이 리듀서는 FIFO
 * 페어링·replay 감지(D55)·N-b meta·`HOLD_STEP` 합성을 **다시 구현하지 않고**, 도착한
 * `tool_call`/`tool_result`/`block` 이벤트를 `ApiTraceEvent[]` 로 누적한 뒤 매 이벤트마다
 * `toTraceSession(...)` 으로 통째로 다시 그린다. `stepFromCall`·`stepPatchFromResult`·
 * `isHoldCard`·`HOLD_STEP`(MQ-401 export)은 그 함수 **안에서** 호출된다 — 매핑 지점이 하나다.
 * (token 은 traces 에 없으므로 누적하지 않는다, D41.)
 *
 * ## 인용/라벨 (D32)
 * SSE 인용 payload `{page, print_page, label}` → `{page, printPage, label}` 스네이크 변환만
 * 한다. 라벨은 백엔드가 조립한 것을 **그대로 passthrough** — 프론트에서 재조립하지 않는다.
 *
 * ## `?replay=s1` 기대 이벤트 시퀀스 (chat.py `_replay_s1`) — Stage 3 육안 채점표
 * 모든 tool_call/tool_result/block 은 `replay: true` 표식을 단다(TraceWriter._write, D55) →
 * `trace.replay === true`, meta `이번 턴 4회 · 재생`(실측 elapsed 합산 제외). token 은 표식 없음.
 *
 *   1. tool_call  lookup_error_code {model:iG5A, code:OHt}
 *   2. tool_result lookup_error_code ok "과열 · related: FAN-IG5-01"
 *        → equipmentId 가 있으면 error_log 액션 push(code 는 ①의 input.code 에서), null 이면 스킵
 *   3. tool_call  rag_search_manual {model:iG5A, query:"OHt 점검 절차"}
 *   4. tool_result rag_search_manual ok "p.202 인용 2건"
 *   5. token ×6  "OHt — 인버터 과열입니다. 유력 원인은 냉각팬 고장·주위 온도 초과."  → agent 버블 #1
 *   6. block citation (iG5A p.202)  → 버블 #1 의 citations 에 부착("iG5A 매뉴얼 p.202")
 *   7. block safety  {title, text:"…", citation: iG5A p.4}  → safety 아이템
 *   8. token ×3  "커버를 열고 냉각팬 커넥터를 분리하십시오."  → agent 버블 #2 (안전 블록 **뒤**, D22)
 *   9. tool_call/tool_result search_inventory ok
 *  10. tool_call/tool_result get_supplier_quotes ok
 *  11. block po_card variant:"draft" (PO-0117)  → po_draft 카드
 *
 * 기대 최종 items: [error_log?, agent#1(cite 202), safety, agent#2, po_draft]
 * 기대 trace: 이번 턴 4회 · 재생 + `재생 데이터` 배지(TracePanel), 각 스텝 pending→ok.
 *
 * ## repeat_banner 는 hold payload 의 `repeated` 로 산출한다 (MQ-405 정정)
 * hold payload(`backend/agent/loop.py _hold_block`)는 `repeated:{count, window_days}` 를
 * 담는다(D45). `repeated.count > 0` 이면 hold 카드(po_hold) **앞에** `repeat_banner` 를
 * push 한다 — 배너 소스는 이 구조화 payload 이지, summary 파싱 같은 우회가 아니다.
 * 개별 발생 날짜는 payload 에 없으므로 지어내지 않는다: mock 은 "07-01·07-11·07-19"까지
 * 상세하지만 라이브는 payload 가 주는 `count`·`window_days` 만 쓴다. `repeated` 가 없거나
 * count 0 이면 배너 없이 hold 카드만 뜬다 (D35·D45).
 *
 * ## 지켜야 할 결정
 * D14·D22(이벤트 4종·같은 채널 순서 보존) · D35·D45(hold payload) · D29·A7(자동 기록 금지,
 * 버튼만 표시) · D32(라벨 재조립 금지) · D55(replay 표식 읽기 전용) · D9(status 4종은
 * `stepPatchFromResult` 재사용으로 자동 준수).
 */
import { API_BASE, authHeaders, promptDemoTokenIfRequired, readSse } from "./api";
import type { ApiTraceEvent, SseEvent } from "./api";
import type { Citation } from "./citation";
import { toTraceSession } from "./trace";
import type { ChatItem, PoDraft, PoHold, PoState, TraceSession } from "./types";

/**
 * 리듀서 내부 기록. **소비자(화면)는 아래 `ChatStreamState` 의 items·trace·streaming·error
 * 4개만 읽는다.** `reduceChatEvent` 를 순수 함수(2-인자)로 유지하려면 턴 컨텍스트와 페어링
 * 상태가 상태에 실려 있어야 해서 둔 것이다 — 이벤트 사이에 살아남아야 하는 값만 담는다.
 */
interface ReducerCtx {
  /** 아이템 id 네임스페이스 (ASCII, D36) */
  readonly sessionId: string;
  /** 이 턴의 장비 id. null 이면 error_log 를 push 하지 않는다 (S1 모델 확인 흐름) */
  readonly equipmentId: string | null;
  /** 열린 agent 버블 id. tool_call·block 이 도착하면 닫힌다(null) */
  readonly openAgentId: string | null;
  /** 단조 증가 아이템 시퀀스 */
  readonly itemSeq: number;
  /** traces 대상 이벤트 누적(tool_call·tool_result·block) — `toTraceSession` 입력 */
  readonly traceEvents: ApiTraceEvent[];
  /** tool → 아직 결과가 안 붙은 호출 input 의 FIFO 큐 (error_log code 소스) */
  readonly pending: Record<string, unknown[]>;
  /** 이미 push 한 error_log 키(`equipmentId\0code`) — 중복 push 방지 */
  readonly logged: string[];
}

export interface ChatStreamState {
  items: ChatItem[];
  trace: TraceSession;
  streaming: boolean;
  error?: string;
  /** 리듀서 내부 — 화면은 읽지 않는다. 순수성 유지를 위해 상태에 산다. */
  readonly _ctx: ReducerCtx;
}

/* -------------------------------------------------------------------------- */
/* 초기 상태                                                                   */

export function initialState(sessionId: string): ChatStreamState {
  const _ctx: ReducerCtx = {
    sessionId,
    equipmentId: null,
    openAgentId: null,
    itemSeq: 0,
    traceEvents: [],
    pending: {},
    logged: [],
  };
  return { items: [], trace: rebuildTrace(_ctx), streaming: false, _ctx };
}

/* -------------------------------------------------------------------------- */
/* 순수 리듀서                                                                 */

export function reduceChatEvent(s: ChatStreamState, e: SseEvent): ChatStreamState {
  const data = e.data;
  // JSON 파싱 실패(readSse.safeJson 은 실패 시 원문 string 을 넘긴다) → 조용히 버리지 않는다.
  if (!isRecord(data)) {
    console.warn("chatStream: 파싱 불가/비객체 이벤트 무시", e.event, data);
    return s;
  }

  switch (e.event) {
    case "token":
      return onToken(s, data);
    case "tool_call":
      return onToolCall(s, data);
    case "tool_result":
      return onToolResult(s, data);
    case "block":
      return onBlock(s, data);
    default:
      console.warn("chatStream: 알 수 없는 이벤트 무시", e.event);
      return s;
  }
}

/** token → 열린 agent 버블에 이어붙임, 없으면 새 버블. **버퍼링하지 않는다**(D22 순서 보존). */
function onToken(s: ChatStreamState, data: Record<string, unknown>): ChatStreamState {
  const text = typeof data.text === "string" ? data.text : "";
  if (!text) return s;

  const openId = s._ctx.openAgentId;
  if (openId && s.items.some((it) => it.id === openId && it.kind === "agent")) {
    const items = s.items.map((it) =>
      it.id === openId && it.kind === "agent"
        ? { ...it, content: agentText(it.content) + text }
        : it
    );
    return { ...s, items };
  }

  const id = nextId(s._ctx);
  const item: ChatItem = { kind: "agent", id, content: text };
  return {
    ...s,
    items: [...s.items, item],
    _ctx: { ...s._ctx, openAgentId: id, itemSeq: s._ctx.itemSeq + 1 },
  };
}

/** tool_call → pending 스텝(trace) + input 을 FIFO 에 넣고, 열린 버블을 닫는다. */
function onToolCall(s: ChatStreamState, data: Record<string, unknown>): ChatStreamState {
  const tool = typeof data.tool === "string" ? data.tool : "(unknown)";
  const traceEvents = [
    ...s._ctx.traceEvents,
    { seq: s._ctx.traceEvents.length + 1, event: "tool_call", tool, data, ts: tstr(data.ts) } as ApiTraceEvent,
  ];
  const pending = {
    ...s._ctx.pending,
    [tool]: [...(s._ctx.pending[tool] ?? []), data.input],
  };
  const _ctx: ReducerCtx = { ...s._ctx, traceEvents, pending, openAgentId: null };
  return { ...s, trace: rebuildTrace(_ctx), _ctx };
}

/**
 * tool_result → trace 스텝 패치(toTraceSession 이 `stepPatchFromResult` 로 적용) + FIFO 로
 * 짝지어진 tool_call 소비. `lookup_error_code` 가 ok 면 error_log 액션을 push 한다 —
 * code 는 payload 에 없으므로 **짝지어진 tool_call 의 input.code** 에서 꺼낸다(A7).
 */
function onToolResult(s: ChatStreamState, data: Record<string, unknown>): ChatStreamState {
  const tool = typeof data.tool === "string" ? data.tool : "(unknown)";
  const traceEvents = [
    ...s._ctx.traceEvents,
    { seq: s._ctx.traceEvents.length + 1, event: "tool_result", tool, data, ts: tstr(data.ts) } as ApiTraceEvent,
  ];
  const queue = s._ctx.pending[tool] ?? [];
  const pairedInput = queue[0];
  const pending = { ...s._ctx.pending, [tool]: queue.slice(1) };

  let _ctx: ReducerCtx = { ...s._ctx, traceEvents, pending };
  let items = s.items;

  if (tool === "lookup_error_code" && data.status === "ok") {
    const code =
      isRecord(pairedInput) && typeof pairedInput.code === "string" ? pairedInput.code : null;
    const equipmentId = _ctx.equipmentId;
    if (equipmentId && code) {
      const key = `${equipmentId} ${code}`;
      // equipmentId 미선택이면 스킵, 같은 (equipmentId, code) 는 한 번만. push 는 버튼 표시일
      // 뿐 — 기록은 사용자가 누를 때 일어난다(D29·A7).
      if (!_ctx.logged.includes(key)) {
        const id = nextId(_ctx);
        items = [...items, { kind: "error_log", id, equipmentId, code }];
        _ctx = { ..._ctx, itemSeq: _ctx.itemSeq + 1, logged: [..._ctx.logged, key] };
      }
    }
  }

  // A2A 파트너 도구(D113·D114, MQ-1606) — 얇은 a2a_result 아이템만 push. 실제 구조화 내용은
  // 렌더 컴포넌트(MQ-1607)가 chainId 로 GET /api/a2a/history 를 따로 열어 채운다.
  const A2A_TOOLS = ["search_insurance_clause", "assess_equipment_loan"] as const;
  if ((A2A_TOOLS as readonly string[]).includes(tool)) {
    const chainId = typeof data.a2a_chain_id === "string" ? data.a2a_chain_id : null;
    const status = typeof data.status === "string" ? data.status : "error";
    const id = nextId(_ctx);
    items = [
      ...items,
      {
        kind: "a2a_result",
        id,
        skill: tool as "search_insurance_clause" | "assess_equipment_loan",
        chainId,
        status,
      },
    ];
    _ctx = { ..._ctx, itemSeq: _ctx.itemSeq + 1 };
  }

  return { ...s, items, trace: rebuildTrace(_ctx), _ctx };
}

/**
 * block → safety / citation / po_card. 셋 다 열린 버블을 닫는다(위험 서술이 안전 경고보다
 * 먼저 보이지 않게, D22). 3종 밖은 렌더하지 않고 warn. 모든 block 은 trace 에도 누적한다 —
 * hold 판별(`isHoldCard`)과 재생 이벤트 카운트가 화면 B 와 같아야 하기 때문이다.
 */
function onBlock(s: ChatStreamState, data: Record<string, unknown>): ChatStreamState {
  const traceEvents = [
    ...s._ctx.traceEvents,
    { seq: s._ctx.traceEvents.length + 1, event: "block", tool: null, data, ts: tstr(data.ts) } as ApiTraceEvent,
  ];
  let _ctx: ReducerCtx = { ...s._ctx, traceEvents, openAgentId: null };
  let items = s.items;

  const type = data.type;
  const inner = isRecord(data.data) ? data.data : {};

  if (type === "safety") {
    const id = nextId(_ctx);
    items = [
      ...items,
      { kind: "safety", id, title: str(inner.title), body: str(inner.text), citation: toCitation(inner.citation) },
    ];
    _ctx = { ..._ctx, itemSeq: _ctx.itemSeq + 1 };
  } else if (type === "citation") {
    const citation = toCitation(inner);
    const idx = lastAgentIndex(items);
    if (idx >= 0) {
      items = items.map((it, i) =>
        i === idx && it.kind === "agent"
          ? { ...it, citations: [...(it.citations ?? []), citation] }
          : it
      );
    } else {
      // 앞에 agent 가 없으면 인용을 조용히 버리지 않고 빈 agent 를 만들어 부착한다.
      const id = nextId(_ctx);
      items = [...items, { kind: "agent", id, content: "", citations: [citation] }];
      _ctx = { ..._ctx, itemSeq: _ctx.itemSeq + 1 };
    }
  } else if (type === "po_card") {
    const variant = inner.variant;
    if (variant === "hold") {
      // hold 를 po_draft 로 렌더하지 않는다 (D35).
      // repeated.count>0 이면 hold 카드 앞에 repeat_banner 를 산출한다 (위 docstring, D45).
      // 개별 날짜는 payload 에 없으므로 지어내지 않는다 — count·window_days 만 쓴다.
      const repeated = isRecord(inner.repeated) ? inner.repeated : {};
      const count = num(repeated.count);
      if (count > 0) {
        const windowDays = num(repeated.window_days);
        const bid = nextId(_ctx);
        items = [
          ...items,
          {
            kind: "repeat_banner",
            id: bid,
            badge: `${count}×`,
            content: `반복 고장 감지 — 최근 ${windowDays}일 ${count}회`,
          },
        ];
        _ctx = { ..._ctx, itemSeq: _ctx.itemSeq + 1 };
      }
      const id = nextId(_ctx);
      items = [...items, { kind: "po_hold", id, hold: toHold(inner) }];
      _ctx = { ..._ctx, itemSeq: _ctx.itemSeq + 1 };
    } else if (variant === "draft") {
      const id = nextId(_ctx);
      items = [...items, { kind: "po_draft", id, po: toDraft(inner) }];
      _ctx = { ..._ctx, itemSeq: _ctx.itemSeq + 1 };
    } else {
      console.warn("chatStream: 알 수 없는 po_card variant 무시", variant);
    }
  } else {
    console.warn("chatStream: 알 수 없는 block type 무시", type);
  }

  return { ...s, items, trace: rebuildTrace(_ctx), _ctx };
}

/* -------------------------------------------------------------------------- */
/* fetch 러너                                                                  */

/**
 * `POST /api/chat`(+`?replay=s1`) → `readSse` → `reduceChatEvent` → `onState`.
 *
 * - `!res.ok` → `error:"API {status}"` 로 끝낸다(스트림은 열지 않는다).
 * - Abort → error 아님, `streaming:false` 만(사용자 이탈은 실패가 아니다).
 * - 네트워크/스트림 실패 → error + **기존 items 유지**(이미 그린 진단을 지우지 않는다).
 */
export async function runChatTurn(opts: {
  sessionId: string;
  message: string;
  equipmentId: string | null;
  replay?: "s1";
  signal?: AbortSignal;
  onState: (s: ChatStreamState) => void;
}): Promise<void> {
  const { sessionId, message, equipmentId, replay, signal, onState } = opts;

  let state = seedTurn(sessionId, message, equipmentId);
  onState(state);

  try {
    const url = `${API_BASE}/api/chat${replay ? `?replay=${replay}` : ""}`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders("technician") },
      body: JSON.stringify({ session_id: sessionId, message, equipment_id: equipmentId }),
      signal,
    });

    if (!res.ok) {
      promptDemoTokenIfRequired(res.status, await res.text()); // D159
      state = { ...state, streaming: false, error: `API ${res.status}` };
      onState(state);
      return;
    }

    await readSse(res, (e) => {
      state = reduceChatEvent(state, e);
      onState(state);
    });

    state = { ...state, streaming: false };
    onState(state);
  } catch (err) {
    if (isAbort(err)) {
      state = { ...state, streaming: false };
      onState(state);
      return;
    }
    state = {
      ...state,
      streaming: false,
      error: err instanceof Error ? err.message : "네트워크 오류로 응답을 받지 못했습니다",
    };
    onState(state);
  }
}

/** 사용자 말풍선을 얹고 streaming 을 켠 턴 시작 상태. */
function seedTurn(
  sessionId: string,
  message: string,
  equipmentId: string | null
): ChatStreamState {
  const base = initialState(sessionId);
  const id = nextId(base._ctx);
  const _ctx: ReducerCtx = { ...base._ctx, equipmentId, itemSeq: base._ctx.itemSeq + 1 };
  return {
    ...base,
    streaming: true,
    items: [{ kind: "user", id, content: message }],
    _ctx,
  };
}

/* -------------------------------------------------------------------------- */
/* 내부 헬퍼                                                                   */

/**
 * `"turn"` 인 이유: `traceEvents` 는 `startTurn()` 이 매 턴 `initialState` 로 비운다.
 * 세션 누적이 아니라 **이번 턴** 호출 수이므로 라벨도 그렇게 나가야 한다(`TraceScope`).
 */
function rebuildTrace(ctx: ReducerCtx): TraceSession {
  return toTraceSession(
    {
      session_id: ctx.sessionId,
      count: ctx.traceEvents.length,
      events: ctx.traceEvents,
    },
    "turn",
  );
}

function nextId(ctx: ReducerCtx): string {
  return `${ctx.sessionId}-${ctx.itemSeq}`;
}

function lastAgentIndex(items: ChatItem[]): number {
  for (let i = items.length - 1; i >= 0; i--) {
    if (items[i].kind === "agent") return i;
  }
  return -1;
}

/**
 * SSE 인용 payload `{page, print_page, label}` → `Citation`.
 * 스네이크 변환만 하고 **라벨은 재조립하지 않는다**(D32) — 백엔드가 조립한 label 을 passthrough.
 */
function toCitation(raw: unknown): Citation {
  const r = isRecord(raw) ? raw : {};
  const citation: Citation = { page: num(r.page) };
  if (typeof r.print_page === "number") citation.printPage = r.print_page;
  if (typeof r.label === "string") citation.label = r.label;
  return citation;
}

/** po_card draft → `PoDraft`. 누락 키는 지어내지 않고 `0`/`""` (카드가 안 깨지게). */
function toDraft(inner: Record<string, unknown>): PoDraft {
  return {
    poId: str(inner.po_id),
    partName: str(inner.part_name),
    partNo: str(inner.part_no),
    qty: num(inner.qty),
    supplierName: str(inner.supplier_name),
    leadDays: num(inner.lead_days),
    unitPrice: num(inner.unit_price),
    state: poState(inner.state),
  };
}

/** po_card hold(D45) → `PoHold`. 각 checklist citation 도 `toCitation` 을 거친다. */
function toHold(inner: Record<string, unknown>): PoHold {
  const rows = Array.isArray(inner.checklist) ? inner.checklist : [];
  return {
    reason: str(inner.reason),
    checklist: rows.map((row) => ({
      label: isRecord(row) ? str(row.label) : "",
      citation: toCitation(isRecord(row) ? row.citation : undefined),
    })),
  };
}

const PO_STATES: readonly PoState[] = ["draft", "pending", "approved", "rejected"];

function poState(v: unknown): PoState {
  return typeof v === "string" && (PO_STATES as readonly string[]).includes(v)
    ? (v as PoState)
    : "draft";
}

function agentText(content: unknown): string {
  return typeof content === "string" ? content : "";
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function str(v: unknown): string {
  return typeof v === "string" ? v : "";
}

function num(v: unknown): number {
  return typeof v === "number" && Number.isFinite(v) ? v : 0;
}

function tstr(v: unknown): string {
  return typeof v === "string" ? v : "";
}

function isAbort(err: unknown): boolean {
  return (
    (typeof DOMException !== "undefined" && err instanceof DOMException && err.name === "AbortError") ||
    (err instanceof Error && err.name === "AbortError")
  );
}
