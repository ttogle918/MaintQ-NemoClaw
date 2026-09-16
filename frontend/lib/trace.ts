import type { ApiTrace, ApiTraceEvent } from "./api";
import type { TraceSession, TraceStatus, TraceStepData } from "./types";

/**
 * `GET /api/chat/{id}/trace` 응답(D43) → `TraceSession` (화면 A/B 공용 타임라인).
 *
 * traces 는 **이벤트의 평평한 나열**이고 화면은 "호출 한 쌍 = 한 스텝"이라, 이 파일이
 * 하는 일은 대부분 짝짓기다.
 *
 * ## 페어링 규칙 — 같은 도구는 FIFO
 * traces 에 pair 키(call id)가 **없다**. 그래서 `tool_result` 가 오면 같은 `tool` 의
 * 미완료 `tool_call` 중 **가장 이른 것**과 짝짓는다.
 *
 * 이 규칙이 성립하는 근거는 **에이전트 루프의 순차 dispatch** 다 — `backend/agent/loop.py`
 * 는 `for tu in pending:` 을 돌며 `tool_call` 을 흘리고 `await client.call()` 이 **끝나야**
 * 다음 호출로 넘어간다(재생본 `chat.py` 도 동일). 즉 한 세션에서 call/result 는 항상
 * 인접 쌍이고, "가장 이른 미완료 호출"이 곧 "지금 끝난 그 호출"이다.
 * → 루프가 `asyncio.gather` 로 도구를 병렬 호출하도록 바뀌면 **이 매퍼가 조용히 잘못
 *   짝짓는다.** pair 키를 이벤트에 넣는 계약 변경이 선행돼야 하며, 여기서 추측으로
 *   맞추면 안 된다. (MCP 워커가 큐를 직렬 소비한다는 D42 는 이 불변식의 근거가 아니다 —
 *   워커가 직렬이어도 루프가 병렬로 호출하면 인접 쌍이 깨진다.)
 *
 * ## 상태 매핑 (D44 · D46)
 * `ok→ok` / `not_found`·`empty→warn` / `error→error` / 결과 없는 call→`pending` /
 * hold 합성 스텝→`held`.
 *
 * 타임아웃은 타입을 늘리지 않고 `error` + summary `✗ timeout ·` 접두인데, **그 접두를
 * 붙이는 주체는 백엔드다** (`loop.py`). `traces` 는 화면만의 것이 아니라 평가 판정
 * 소스이므로(D21·D30) 저장된 summary 자체가 자기설명적이어야 한다. 여기서 다시 붙이지
 * 않는다 — `tool_result` payload 는 `{tool,status,summary,elapsed,pages?}` 라(D54 로
 * pages 추가) 프론트가 볼 `reason` 자체가 없다 (06_REPO_API).
 *
 * 반대로 **표시할 때는** error 행의 선두 `✗ ` 를 지운다 — 붉은 점 글리프가 이미 `✗` 라
 * 화면에 같은 표지가 두 번 찍히기 때문이다(N-c). 이것은 렌더 단계의 중복 제거일 뿐,
 * traces 저장값·SSE payload 는 그대로다 — 저장값의 자기설명성(D44)은 백엔드 접두가
 * 계속 보장한다. 자세한 규칙은 `stepPatchFromResult` docstring 참조.
 */

/** 도구 status(D9 4종) → 스텝 상태. 계약 밖 값은 여기 없다 — `stepStatus()` 참조. */
const STATUS: Record<string, TraceStatus> = {
  ok: "ok",
  not_found: "warn",
  empty: "warn",
  error: "error",
};

/**
 * S3 발주 보류의 합성 스텝 (D35).
 * `create_po_draft` 는 **호출되지 않았다** — 원인 확정 전 발주를 막는 게 요점이라
 * 타임라인에서도 "호출 안 함"이 보여야 한다. 그래서 도구명에 취소선(`strikeTool`)을 준다.
 * 문구는 화면 A 목업(`lib/mock/trace.ts` TRACE_S3)과 **같은 표현**을 유지한다.
 * export 인 이유: SSE 리듀서(`lib/chatStream.ts`)도 같은 합성 스텝을 그려야 한다.
 */
export const HOLD_STEP: TraceStepData = {
  tool: "create_po_draft",
  input: "차단: 원인 확정 전 발주 금지",
  summary: "⏸ held · 발주 보류",
  status: "held",
  strikeTool: true,
};

/**
 * `tool_call` payload → pending 스텝. traces 재생(`toTraceSession`)과 SSE 실시간
 * (`lib/chatStream.ts`)이 **같은 이벤트를 같은 스텝으로** 그리기 위한 단일 매핑 지점.
 */
export function stepFromCall(tool: string, input: unknown): TraceStepData {
  return {
    tool,
    input: formatInput(input),
    summary: "○ pending",
    status: "pending",
  };
}

/**
 * `tool_result` payload → 스텝에 덮어쓸 패치 (`stepFromCall` 과 대칭인 단일 매핑 지점).
 *
 * **N-c — 표시용 `✗ ` 접두 제거**: status 가 `error` 인 행의 summary 선두 `✗` 를 지운다.
 * 붉은 점 글리프가 이미 `✗` 라(09_RUNTIME §3, `TraceStep` GLYPH) 화면에 같은 표지가
 * 두 번 찍히기 때문이다. 이 제거는 **렌더 직전 표시값에만** 적용된다 — traces 저장값과
 * SSE payload 는 백엔드가 붙인 접두 그대로이며(D21·D30 판정 소스 무변경), 저장된
 * summary 의 자기설명성(D44)도 그대로다. 접두 제거 외의 요약 재작성은 하지 않는다 —
 * 문장을 만들면 도구가 주지 않은 정보가 사실처럼 보인다.
 */
export function stepPatchFromResult(data: Record<string, unknown>): {
  summary: string;
  status: TraceStatus;
} {
  const status = stepStatus(data.status);
  let summary = formatSummary(data);
  if (status === "error" && summary.startsWith("✗")) {
    // "✗ timeout · …" → "timeout · …". summary 가 "✗" 한 글자면 strip 후 비므로
    // status 문자열로 폴백한다 — 빈 줄보다 "무슨 일이 있었는지"가 낫다.
    const stripped = summary.slice(1).trimStart();
    summary = stripped || (typeof data.status === "string" ? data.status : "error");
  }
  return { summary, status };
}

/**
 * 이 타임라인이 **어느 범위**의 이벤트로 만들어졌는지. 호출 수 라벨이 여기서 갈린다.
 *
 * `toTraceSession()` 은 받은 이벤트 묶음의 `tool_call` 을 셀 뿐이라 같은 코드가 호출자에
 * 따라 **다른 뜻의 숫자**를 낸다 — 정비사 콘솔(`lib/chatStream.ts`)은 턴마다 이벤트를
 * 비우므로 `4 → 1 → 0` 으로 리셋되는 것이 정상이고, 매니저 트레이스 화면
 * (`manager/trace/[sessionId]`)은 세션 전체를 받으므로 누적값이다.
 *
 * ⚠️ **이 모호함이 실제로 오독을 낳았다.** 2026-08-31 촬영에서 호출 수가 `1 → 0 → 1` 로
 * 리셋되는 것을 보고 *"세션 상태가 매 턴 초기화된다"* 는 가설이 서서 다른 세션에 조사가
 * 위임됐다. 진짜 원인은 이력 절삭이었고 이 값은 **정상 동작**이었다 — 값이 틀린 게 아니라
 * **같은 이름이 두 뜻**이었다. 그래서 범위를 추론하지 않고 **호출자가 선언**하게 한다.
 * 기본값을 두지 않는 이유도 같다: 기본이 있으면 두 뜻 중 하나가 조용히 선택되고,
 * 그 순간 이 결함이 그대로 돌아온다.
 */
export type TraceScope = "turn" | "session";

/**
 * `scope` 는 호출자가 **넘긴 이벤트의 범위**다 — 한 턴만 넘겼으면 `"turn"`,
 * 세션 전체면 `"session"`. 화면 문구가 이 값으로만 갈린다(`callsLabel`).
 */
export function toTraceSession(trace: ApiTrace, scope: TraceScope): TraceSession {
  const steps: TraceStepData[] = [];
  /** tool → 아직 결과가 안 붙은 스텝의 인덱스 큐 (가장 이른 것이 앞) */
  const waiting = new Map<string, number[]>();
  let calls = 0;
  let elapsed = 0;
  let held = false;
  /** `replay === true`(boolean 만, D55) 인 이벤트 수 — truthy 로 넓히지 않는다 */
  let replayEvents = 0;

  for (const ev of trace.events) {
    if (ev.data.replay === true) replayEvents += 1;

    if (ev.event === "tool_call") {
      const tool = toolName(ev);
      calls += 1;
      steps.push(stepFromCall(tool, ev.data.input));
      pushWaiting(waiting, tool, steps.length - 1);
      continue;
    }

    if (ev.event === "tool_result") {
      const tool = toolName(ev);
      const patch = stepPatchFromResult(ev.data);
      const idx = shiftWaiting(waiting, tool);
      // 재생 행의 elapsed 는 합성값이다 — 실측인 양 합산하지 않는다 (N-b · D55)
      if (ev.data.replay !== true) elapsed += numberOr(ev.data.elapsed, 0);

      if (idx === undefined) {
        // 짝이 없는 결과 — 이전 턴의 호출이거나 tool_call 저장이 실패한 경우(persist_errors).
        // 조용히 버리면 타임라인에서 실행 자체가 사라지므로 스텝으로 남기되 입력을 지어내지 않는다.
        steps.push({ tool, input: "in: (호출 이벤트 없음)", ...patch });
        continue;
      }
      steps[idx] = { ...steps[idx], ...patch };
      continue;
    }

    if (ev.event === "block" && isHoldCard(ev.data)) held = true;
  }

  // 합성 스텝은 항상 마지막 — 실제 호출 뒤에 "그래서 발주는 막았다"가 오는 순서다.
  // hold 가 여러 턴에 걸쳐 여러 번 와도 1행만 둔다: 같은 문구 반복은 정보가 아니라 잡음이다.
  if (held) steps.push(HOLD_STEP);

  // N-b — elapsed 의 두 의미 분리: 전 이벤트가 재생이면 남는 실측 elapsed 가 0 인데
  // "0.0s" 는 "즉시 끝났다"로 읽히므로 시간 자체를 표기하지 않는다. 혼재면 실 행의
  // 실측만 합산해 기존 형식을 유지하고, 재생 여부는 배지(TracePanel)가 구분한다.
  const allReplay = trace.events.length > 0 && replayEvents === trace.events.length;
  const session: TraceSession = {
    label: `SESSION #${trace.session_id}`,
    meta: allReplay
      ? `${callsLabel(scope, calls)} · 재생`
      : `${elapsed.toFixed(1)}s · ${callsLabel(scope, calls)}`,
    // 오렌지는 안전·긴급 전용이다 — held(발주 보류)일 때만 쓴다
    accent: held ? "orange" : "blue",
    steps,
  };
  if (replayEvents > 0) session.replay = true;
  return session;
}

/* -------------------------------------------------------------------------- */
/* 내부 (isHoldCard 만 예외 — chatStream 공용이라 export)                       */

/**
 * 호출 수 한 줄. **숫자만으로는 턴/누적을 구분할 수 없으므로** 라벨에 범위를 적는다
 * (위 `TraceScope`). 표기는 화면이 아니라 여기서 만든다 — 두 화면이 같은 규칙을 쓰게.
 */
function callsLabel(scope: TraceScope, calls: number): string {
  return scope === "turn" ? `이번 턴 ${calls}회` : `누적 ${calls}회`;
}

/** `tool` 컬럼이 비어 있으면 payload 의 `tool` 을 쓴다. 둘 다 없으면 지어내지 않는다. */
function toolName(ev: ApiTraceEvent): string {
  if (ev.tool) return ev.tool;
  const fromData = ev.data.tool;
  return typeof fromData === "string" && fromData ? fromData : "(unknown)";
}

function pushWaiting(waiting: Map<string, number[]>, tool: string, index: number): void {
  const queue = waiting.get(tool);
  if (queue) queue.push(index);
  else waiting.set(tool, [index]);
}

function shiftWaiting(waiting: Map<string, number[]>, tool: string): number | undefined {
  return waiting.get(tool)?.shift();
}

/**
 * D9 status 4종 밖의 값은 `warn` 으로 둔다.
 * `error` 로 단정하면 성공한 호출을 장애로 보고할 수 있고, `ok` 로 두면 실패를 숨긴다.
 * "판단하지 않았다"에 가장 가까운 쪽이 warn 이다.
 */
function stepStatus(raw: unknown): TraceStatus {
  return (typeof raw === "string" && STATUS[raw]) || "warn";
}

/**
 * 요약 한 줄. **도구가 준 문자열을 그대로 쓴다** — 여기서 문장을 만들면 도구가 주지 않은
 * 정보가 사용자에게 사실처럼 보인다. `✗ timeout ·` 접두도 붙이지 않는다(위 docstring).
 * summary 가 비면 status 를 쓴다 — 빈 줄보다 "무슨 일이 있었는지"가 낫다.
 */
function formatSummary(data: Record<string, unknown>): string {
  const raw = typeof data.summary === "string" ? data.summary.trim() : "";
  return raw || (typeof data.status === "string" ? data.status : "결과 없음");
}

function numberOr(v: unknown, fallback: number): number {
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
}

/**
 * `block(po_card, variant:"hold")` 인지 (D35 · D45).
 * export 인 이유: SSE 리듀서(`lib/chatStream.ts`)가 같은 판별로 `HOLD_STEP` 을 합성한다.
 */
export function isHoldCard(data: Record<string, unknown>): boolean {
  if (data.type !== "po_card") return false;
  const inner = data.data;
  return isRecord(inner) && inner.variant === "hold";
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** 값 하나의 표기 길이 상한. rag `query` 가 한 줄을 다 먹는 걸 막는다. */
const MAX_VALUE_LEN = 44;

/** `in: {model:"iG5A", code:"OHt"}` — 목업 타임라인과 같은 표기. */
function formatInput(input: unknown): string {
  if (!isRecord(input)) return "in: {}";
  const body = Object.entries(input)
    .map(([k, v]) => `${k}:${formatValue(v)}`)
    .join(", ");
  return `in: {${body}}`;
}

function formatValue(v: unknown): string {
  if (typeof v === "string") return `"${truncate(v)}"`;
  if (v === null || v === undefined) return "null";
  if (Array.isArray(v)) return `[${v.map(formatValue).join(",")}]`;
  if (isRecord(v)) return "{…}";
  return String(v);
}

function truncate(s: string): string {
  return s.length <= MAX_VALUE_LEN ? s : `${s.slice(0, MAX_VALUE_LEN - 1)}…`;
}
