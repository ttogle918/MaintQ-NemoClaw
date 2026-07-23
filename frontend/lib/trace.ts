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
 * 않는다 — `tool_result` payload 는 `{tool,status,summary,elapsed}` 4필드뿐이라
 * 프론트가 볼 `reason` 자체가 없다 (06_REPO_API).
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
 */
const HOLD_STEP: TraceStepData = {
  tool: "create_po_draft",
  input: "차단: 원인 확정 전 발주 금지",
  summary: "⏸ held · 발주 보류",
  status: "held",
  strikeTool: true,
};

export function toTraceSession(trace: ApiTrace): TraceSession {
  const steps: TraceStepData[] = [];
  /** tool → 아직 결과가 안 붙은 스텝의 인덱스 큐 (가장 이른 것이 앞) */
  const waiting = new Map<string, number[]>();
  let calls = 0;
  let elapsed = 0;
  let held = false;

  for (const ev of trace.events) {
    if (ev.event === "tool_call") {
      const tool = toolName(ev);
      calls += 1;
      steps.push({
        tool,
        input: formatInput(ev.data.input),
        summary: "○ pending",
        status: "pending",
      });
      pushWaiting(waiting, tool, steps.length - 1);
      continue;
    }

    if (ev.event === "tool_result") {
      const tool = toolName(ev);
      const status = stepStatus(ev.data.status);
      const summary = formatSummary(ev.data);
      const idx = shiftWaiting(waiting, tool);
      elapsed += numberOr(ev.data.elapsed, 0);

      if (idx === undefined) {
        // 짝이 없는 결과 — 이전 턴의 호출이거나 tool_call 저장이 실패한 경우(persist_errors).
        // 조용히 버리면 타임라인에서 실행 자체가 사라지므로 스텝으로 남기되 입력을 지어내지 않는다.
        steps.push({ tool, input: "in: (호출 이벤트 없음)", summary, status });
        continue;
      }
      steps[idx] = { ...steps[idx], summary, status };
      continue;
    }

    if (ev.event === "block" && isHoldCard(ev.data)) held = true;
  }

  // 합성 스텝은 항상 마지막 — 실제 호출 뒤에 "그래서 발주는 막았다"가 오는 순서다.
  // hold 가 여러 턴에 걸쳐 여러 번 와도 1행만 둔다: 같은 문구 반복은 정보가 아니라 잡음이다.
  if (held) steps.push(HOLD_STEP);

  return {
    label: `SESSION #${trace.session_id}`,
    meta: `${elapsed.toFixed(1)}s · ${calls} calls`,
    // 오렌지는 안전·긴급 전용이다 — held(발주 보류)일 때만 쓴다
    accent: held ? "orange" : "blue",
    steps,
  };
}

/* -------------------------------------------------------------------------- */
/* 내부                                                                        */

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

/** `block(po_card, variant:"hold")` 인지 (D35 · D45). */
function isHoldCard(data: Record<string, unknown>): boolean {
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
