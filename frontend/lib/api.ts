/**
 * 백엔드 클라이언트 (docs/06_REPO_API.md).
 *
 * 발주·장비 API 는 연결됐고, `/api/chat` SSE 는 에이전트 루프가 나오면 붙인다.
 *
 * ⚠️ EventSource 를 쓸 수 없다.
 *   - /api/chat 은 POST 이고 EventSource 는 GET 전용이다
 *   - EventSource 는 커스텀 헤더(X-Role · X-User)를 실을 수 없다
 *   → fetch + ReadableStream 으로 직접 파싱한다 (readSse 참조)
 */
import type { Role } from "./role";
import { ROLE_USER_ID } from "./role";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8003";

/**
 * 역할·신원 헤더. requested_by/decided_by 는 백엔드가 이 값에서 주입한다 (D23).
 * X-User 는 **ASCII 사용자 ID** — 한글 표시명을 넣으면 fetch 가 거부한다 (D36).
 */
export function authHeaders(role: Role): Record<string, string> {
  return { "X-Role": role, "X-User": ROLE_USER_ID[role] };
}

export async function apiFetch<T>(
  path: string,
  role: Role,
  init: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(role),
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return (await res.json()) as T;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: string
  ) {
    super(`API ${status}: ${body}`);
    this.name = "ApiError";
  }
}

/* -------------------------------------------------------------------------- */
/* SSE — 이벤트 4종 고정 (D14 · D22)                                          */

export type SseEventType = "token" | "tool_call" | "tool_result" | "block";

export interface SseEvent {
  event: SseEventType;
  data: unknown;
}

/**
 * `fetch` 응답 본문을 SSE 프레임 단위로 읽어 순서대로 넘긴다.
 *
 * block 이벤트는 token 스트림 "중간"에 끼어들 수 있어야 한다 (D22) —
 * 안전 경고가 위험 절차 서술보다 늦게 도착하면 안 되기 때문이다.
 * 그래서 버퍼링해서 마지막에 몰아 처리하지 말고 도착하는 즉시 콜백을 부른다.
 */
export async function readSse(
  res: Response,
  onEvent: (e: SseEvent) => void
): Promise<void> {
  if (!res.body) throw new Error("SSE 응답에 body 가 없습니다");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE 프레임 구분자는 빈 줄
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const parsed = parseFrame(frame);
      if (parsed) onEvent(parsed);
    }
  }
}

function parseFrame(frame: string): SseEvent | null {
  let event: string | null = null;
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!event || !dataLines.length) return null;
  const raw = dataLines.join("\n");
  return { event: event as SseEventType, data: safeJson(raw) };
}

function safeJson(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

/* -------------------------------------------------------------------------- */
/* 엔드포인트 (M2 에서 본문 연결)                                              */

/* -------------------------------------------------------------------------- */
/* 발주 · 장비 API                                                             */

/** 백엔드 `/api/po` 응답. 화면 B 가 필요한 걸 한 번에 준다. */
export interface ApiPo {
  po_id: string;
  part_no: string;
  part_name: string;
  qty: number;
  supplier_id: string;
  supplier_name: string;
  model: string | null;
  error_code: string | null;
  evidence: { symptoms?: string[]; basis?: ApiBasis[]; notes?: string } | null;
  unit_price: number;
  reason: string;
  urgency: "urgent" | "normal";
  state: "draft" | "pending" | "approved" | "rejected";
  requested_by: string | null;
  requested_by_name: string;
  decided_by: string | null;
  decided_by_name: string;
  decision_note: string | null;
  session_id: string | null;
  created_at: string;
  quotes?: { supplier_id: string; name: string; lead_days: number; unit_price: number; moq: number }[];
  inventory?: { qty: number; safety_stock: number; location: string } | null;
  trace_url?: string | null;
}

export interface ApiBasis {
  tool?: string;
  code?: string;
  manual_page?: number;
  [k: string]: unknown;
}

export const getPoQueue = (role: Role, state = "pending") =>
  apiFetch<{ items: ApiPo[] }>(`/api/po?state=${state}`, role).then((r) => r.items);

export const getPo = (role: Role, poId: string) => apiFetch<ApiPo>(`/api/po/${poId}`, role);

/** draft → pending. 정비사만 — 팀장이 부르면 403 (D38). */
export const submitPo = (poId: string) =>
  apiFetch<ApiPo>(`/api/po/${poId}/submit`, "technician", { method: "POST" });

/** pending → approved. 팀장만. */
export const approvePo = (poId: string, note?: string) =>
  apiFetch<ApiPo>(`/api/po/${poId}/approve`, "manager", {
    method: "POST",
    body: JSON.stringify({ note: note ?? null }),
  });

/** pending → rejected. 사유 필수 (D38) — 없으면 백엔드가 422. */
export const rejectPo = (poId: string, reason: string) =>
  apiFetch<ApiPo>(`/api/po/${poId}/reject`, "manager", {
    method: "POST",
    body: JSON.stringify({ reason }),
  });

/* -------------------------------------------------------------------------- */
/* trace 조회 (D43)                                                            */

/**
 * `GET /api/chat/{session_id}/trace` 의 이벤트 한 건.
 *
 * `data` 는 SSE 로 나갔던 `data` 와 **바이트 동일**하다 (D30) — 즉 이벤트 종류별 모양이
 * `backend/sse.py` 와 같다:
 *   tool_call    `{tool, input, ts}`
 *   tool_result  `{tool, status, summary, elapsed, pages?}` — pages 는 근거 페이지 목록 (D54)
 *   block        `{type, data}`
 * token 은 들어오지 않는다 — traces 에 저장하지 않기 때문이다 (D41).
 * 재생(`?replay=…`)이 남긴 이벤트는 `replay: true` 표식을 단다 (D55) — 화면은 무시해도
 * 되지만, 이 행이 합성 데이터라는 뜻이므로 실적·통계 용도로 세지 말 것.
 * 모양을 여기서 좁게 못 박지 않고 `unknown` 값으로 두는 이유는, 백엔드가 키를 추가해도
 * 매퍼(`lib/trace.ts`)만 고치면 되게 하기 위해서다.
 */
export interface ApiTraceEvent {
  seq: number;
  event: "tool_call" | "tool_result" | "block";
  tool: string | null;
  data: Record<string, unknown>;
  ts: string;
}

/** 없는 세션도 404 가 아니라 200 + `count: 0` 이다 (D43). 빈 세션은 에러가 아니다. */
export interface ApiTrace {
  session_id: string;
  count: number;
  events: ApiTraceEvent[];
}

export const getTrace = (role: Role, sessionId: string) =>
  apiFetch<ApiTrace>(`/api/chat/${encodeURIComponent(sessionId)}/trace`, role);

export const getEquipment = () =>
  apiFetch<{ items: { equipment_id: string; line_id: number; model: string; location: string }[] }>(
    "/api/equipment",
    "technician"
  ).then((r) => r.items);

/** 에러 발생 이력 기록 — 정비사의 명시적 액션만 (D29·A7). */
export const recordError = (equipmentId: string, code: string, actionTaken?: string) =>
  apiFetch<{ status: string; id: number; code: string; occurred_at: string }>(
    `/api/equipment/${equipmentId}/errors`,
    "technician",
    { method: "POST", body: JSON.stringify({ code, action_taken: actionTaken ?? null }) }
  );

export const endpoints = {
  chat: "/api/chat",
  trace: (sessionId: string) => `/api/chat/${sessionId}/trace`,
  poQueue: (state = "pending") => `/api/po?state=${state}`,
  po: (poId: string) => `/api/po/${poId}`,
  poSubmit: (poId: string) => `/api/po/${poId}/submit`,
  poApprove: (poId: string) => `/api/po/${poId}/approve`,
  poReject: (poId: string) => `/api/po/${poId}/reject`,
  equipment: "/api/equipment",
  equipmentHistory: (id: string) => `/api/equipment/${id}/history`,
  /** 에러 발생 이력 기록 — 정비사의 명시적 액션만 (D29) */
  equipmentErrors: (id: string) => `/api/equipment/${id}/errors`,
} as const;
