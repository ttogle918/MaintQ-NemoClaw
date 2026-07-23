/**
 * 백엔드 연동 골격 (docs/06_REPO_API.md).
 *
 * 아직 backend/ 가 없어 실제 호출은 M2 에서 연결한다. 여기서는
 * "헤더를 어디서 채우는가" 와 "SSE 를 어떻게 읽는가" 만 한 곳에 고정해 둔다.
 *
 * ⚠️ EventSource 를 쓸 수 없다.
 *   - /api/chat 은 POST 이고 EventSource 는 GET 전용이다
 *   - EventSource 는 커스텀 헤더(X-Role · X-User)를 실을 수 없다
 *   → fetch + ReadableStream 으로 직접 파싱한다 (readSse 참조)
 */
import type { Role } from "./role";
import { ROLE_USER_ID } from "./role";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

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
