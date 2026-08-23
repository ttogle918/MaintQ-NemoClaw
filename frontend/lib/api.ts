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
import type { ApprovalKind } from "./types";

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

/**
 * 오류 본문에서 사람이 읽을 문장을 꺼낸다.
 * 403(권한)·409(전이)·422(사유 누락)를 **구분해서** 보여 주기 위한 것 — 이게 D38 의 요점이다.
 * FastAPI 는 `{"detail": …}`, 처분 409 는 `{"reason": …, "detail": …}` 로 온다.
 */
export function extractDetail(body: string): string {
  try {
    const j = JSON.parse(body);
    if (typeof j?.detail === "string") return j.detail;
    if (j?.detail !== undefined) return JSON.stringify(j.detail);
    if (typeof j?.message === "string") return j.message;
    return JSON.stringify(j);
  } catch {
    return body.slice(0, 120);
  }
}

/**
 * 오류 본문을 객체로. **409 는 재료를 싣고 온다** — `reason`(`evidence_changed` ·
 * `override_required` · `law_text_unavailable` …) 과 `verdict`·`blockers`·`bundle_hash` 를
 * 읽어야 사용자에게 "무엇을 하면 풀리는지"를 말할 수 있다 (`backend/routers/decisions.py`).
 * 파싱 실패는 `null` — 지어내지 않는다.
 */
export function errorBody(e: unknown): Record<string, unknown> | null {
  if (!(e instanceof ApiError)) return null;
  try {
    const j = JSON.parse(e.body);
    return j && typeof j === "object" ? (j as Record<string, unknown>) : null;
  } catch {
    return null;
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
  /** 인쇄 페이지 (D57) — `model`·`manual_page` 둘 다 유효할 때만 백엔드가 붙인다. 없으면
   *  인쇄 페이지 미상 — 프론트가 계산해 채우지 않는다(D32, 오프셋 변환은 백엔드 1곳). */
  print_page?: number;
  [k: string]: unknown;
}

/**
 * 발주 **전용** 목록. 화면 B 의 큐는 이제 `getApprovals`(통합 큐, D85)를 쓴다 —
 * 이건 "발주만" 필요한 곳(정비사 화면·스크립트)을 위해 남긴다. `/api/po` 는 무변경이다.
 */
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

/** 부품의 공급사별 견적 — `/technician/po/new` 화면이 공급사를 고르기 전 조회 (D111). */
export interface ApiQuote {
  supplier_id: string;
  name: string;
  lead_days: number;
  unit_price: number;
  moq: number;
}

export const getPartQuotes = (role: Role, partNo: string) =>
  apiFetch<{ part_no: string; quotes: ApiQuote[] }>(
    `/api/po/quotes/${encodeURIComponent(partNo)}`,
    role
  );

/** POST /api/po · PATCH /api/po/{poId} 공용 바디 (D111, P39 축소판 — 발주서만). */
export interface CreatePoBody {
  part_no: string;
  qty: number;
  supplier_id: string;
  reason: string;
  urgency?: "urgent" | "normal";
}

/**
 * 화면에서 발주 초안을 직접 생성한다. 정비사만 — 팀장이 부르면 403.
 * 단가·MOQ 미달·미지 공급사 등 검증 실패는 404/422 로 ApiError 를 던진다
 * (`errorBody()` 로 status/reason/message 를 꺼내 보일 것 — `extractDetail()` 은
 * `.detail` 이 없으면 `.message` 로 자동 폴백한다).
 */
export const createPo = (body: CreatePoBody) =>
  apiFetch<ApiPo>("/api/po", "technician", {
    method: "POST",
    body: JSON.stringify(body),
  });

/** draft 상태 발주 초안을 수정한다. draft 아니면 409, 검증 실패는 422/404. */
export const updatePo = (poId: string, body: CreatePoBody) =>
  apiFetch<ApiPo>(`/api/po/${poId}`, "technician", {
    method: "PATCH",
    body: JSON.stringify(body),
  });

/* -------------------------------------------------------------------------- */
/* 통합 승인 큐 (D85) — `GET /api/approvals`                                    */

/**
 * 통합 큐 항목. **`/api/po` 는 한 글자도 바뀌지 않았다** — 처분서를 그 형태에 담으면
 * 응답 절반이 NULL 이 되고, `/api/po` 에 걸린 회귀 28건·403 지표가 흔들리기 때문에
 * 백엔드가 **읽기 전용 조립기**를 새 경로로 낸 것이다 (`backend/services/approvals.py`).
 *
 * ⚠ `kind`·`state` 를 유니온이 아니라 `string` 으로 받는 이유: 백엔드가 어휘를 늘리면
 *   **먼저 도착하는 쪽이 화면**이다. 유니온으로 좁혀 두면 모르는 값이 타입상 존재할 수
 *   없어서, "모르면 warn" 처리(D87)가 죽은 코드가 된다. 좁히기는 `lib/mappers` 가 한다.
 */
export interface ApiApproval {
  kind: string;
  id: string;
  title: string;
  /** 원 어휘 그대로 — po: approved / disposal: signed */
  state: string;
  /** 처분서에는 없다 → null */
  urgency: "urgent" | "normal" | null;
  requested_by: string | null;
  requested_by_name: string;
  created_at: string | null;
  /** API 경로다 (`/api/po/PO-0117`). 화면 경로는 `lib/queueState.detailHref` 가 만든다 */
  detail_path: string;
  /** kind==="disposal" 일 때만 값이 있다 */
  verdict: string | null;
  requires_override: boolean | null;
}

/**
 * 통합 큐 조회. `state` 는 **각 종류의 원 어휘**로 필터한다 —
 * 종결 상태가 종류마다 다르므로(`approved` vs `signed`) 한 번의 호출로는 다 못 모은다.
 * `kind` 에 `KINDS` 밖의 값을 넣으면 422 다 (오타를 0건으로 돌려주지 않는다).
 */
export const getApprovals = (role: Role, state?: string, kind?: ApprovalKind) => {
  const q = new URLSearchParams();
  if (state) q.set("state", state);
  if (kind) q.set("kind", kind);
  const qs = q.toString();
  return apiFetch<{ items: ApiApproval[]; kinds: string[] }>(
    `/api/approvals${qs ? `?${qs}` : ""}`,
    role
  ).then((r) => r.items);
};

/* -------------------------------------------------------------------------- */
/* 처분 결정 (S10) — 상세·제출·서명·반려                                        */

/**
 * `GET /api/decisions/{id}` 응답.
 *
 * `documents`·`evidence_bundle` 안쪽은 **여기서 좁히지 않는다** — D86 이 "저장하지 않고
 * 조립 시점 렌더"로 정한 구조라 항목이 늘어날 수 있고, 모양을 여기 박아 두면 백엔드가
 * 키를 하나 더할 때마다 이 파일이 바뀐다. 렌더 쪽(Stage 6)이 필요한 키만 좁혀 읽는다.
 */
export interface ApiDecision {
  decision_id: string;
  asset_id: string;
  asset_name?: string | null;
  asset_category?: string | null;
  /** draft | pending | signed | rejected — **`approved` 가 아니다** */
  state: string;
  disposal_mode: string | null;
  disposal_date: string | null;
  verdict_at_signing: string | null;
  /** 서명 시점 판정이 차단 어휘인가 = 우회 없이는 서명 불가인가 */
  requires_override: boolean;
  override: boolean;
  override_reason?: string | null;
  bundle_hash?: string | null;
  requested_by: string | null;
  requested_by_name: string;
  reviewed_by: string | null;
  reviewed_by_name: string;
  created_at: string | null;
  signed_at: string | null;
  evidence_bundle?: Record<string, unknown>;
  /** 승인서·진술보장서·증빙 패키지 + `missing_sections`·`hash_fixed` (D86) */
  documents?: Record<string, unknown>;
  [k: string]: unknown;
}

export const getDecisions = (role: Role, state?: string) =>
  apiFetch<{ items: ApiDecision[] }>(
    `/api/decisions${state ? `?state=${encodeURIComponent(state)}` : ""}`,
    role
  ).then((r) => r.items);

export const getDecision = (role: Role, id: string) =>
  apiFetch<ApiDecision>(`/api/decisions/${encodeURIComponent(id)}`, role);

/** draft → pending. **정비사만** — 팀장이 부르면 403 (403 은 양방향이다). */
export const submitDecision = (id: string) =>
  apiFetch<ApiDecision>(`/api/decisions/${encodeURIComponent(id)}/submit`, "technician", {
    method: "POST",
  });

/**
 * 서명 본문. `override` 는 **사람만** 넣을 수 있다 — 도구 스키마에는 이 키가 없다 (D81).
 * ⛔ `override_reason` 에 기본 문구를 채우지 말 것. 사유는 사람이 쓴 것만 사유다.
 */
export interface SignDecisionBody {
  override?: boolean;
  override_reason?: string | null;
  note?: string | null;
}

/**
 * pending → signed. **팀장만.**
 * 실패는 상태코드가 아니라 **409 본문의 `reason`** 으로 갈린다 —
 * `invalid_transition` · `law_text_unavailable` · `cited_rule_missing` ·
 * `evidence_changed` · `override_required`. `errorBody(e)` 로 읽는다.
 */
export const signDecision = (id: string, body: SignDecisionBody = {}) =>
  apiFetch<ApiDecision>(`/api/decisions/${encodeURIComponent(id)}/sign`, "manager", {
    method: "POST",
    body: JSON.stringify({
      override: body.override ?? false,
      override_reason: body.override_reason ?? null,
      note: body.note ?? null,
    }),
  });

/** pending → rejected. 사유 필수 (D38) — 공백이면 백엔드가 422. */
export const rejectDecision = (id: string, reason: string) =>
  apiFetch<ApiDecision>(`/api/decisions/${encodeURIComponent(id)}/reject`, "manager", {
    method: "POST",
    body: JSON.stringify({ reason }),
  });

/* -------------------------------------------------------------------------- */
/* 자산 · 처분 사전판정 · 실사 (S9 · S18)                                       */

export interface ApiAsset {
  asset_id: string;
  name: string;
  category: string | null;
  status: string | null;
  line_id: number | null;
  acquired_at: string | null;
  book_value: number | null;
  acquisition_cost: number | null;
  /** 위험등급 조회(`GET /api/assets/{id}/risk-grade`)가 이 값으로 건물을 해석한다. 없으면 null */
  building_id: string | null;
  equipment_count?: number;
  equipment?: Record<string, unknown>[];
  [k: string]: unknown;
}

export const getAssets = (role: Role, params?: { lineId?: number; status?: string }) => {
  const q = new URLSearchParams();
  if (params?.lineId !== undefined) q.set("line_id", String(params.lineId));
  if (params?.status) q.set("status", params.status);
  const qs = q.toString();
  return apiFetch<{ items: ApiAsset[] }>(`/api/assets${qs ? `?${qs}` : ""}`, role).then(
    (r) => r.items
  );
};

export const getAsset = (role: Role, assetId: string) =>
  apiFetch<ApiAsset>(`/api/assets/${encodeURIComponent(assetId)}`, role);

export interface ApiHotspotPart {
  part_no: string;
  color: "red" | "blue" | "orange" | null;
  basis: Record<string, unknown>;
}

export interface ApiHotspotStatus {
  status: string;
  equipment_id?: string;
  model?: string;
  parts?: ApiHotspotPart[];
  reason?: string;
  [k: string]: unknown;
}

export const getHotspotStatus = (role: Role, assetId: string) =>
  apiFetch<ApiHotspotStatus>(
    `/api/assets/${encodeURIComponent(assetId)}/hotspot-status`,
    role
  );

/**
 * 처분 사전판정 결과. **`CLEAR`·`CONDITIONAL` 만 200 이다** —
 * `BLOCKED`·`HOLD`·`INSUFFICIENT_FACTS` 는 409 로 오고, 본문은 200 과 **같은 형태 + `detail`**
 * 이다 (D71). 즉 차단이어도 `errorBody(e)` 로 이 형태를 그대로 렌더할 수 있다.
 *
 * ⛔ 409 를 "실패"로 뭉개 버리지 말 것 — 200 을 "진행 가능"으로 읽는 클라이언트를 위해
 *   일부러 갈라 놓은 것이고, 사용자가 볼 것은 blockers·resolve_options 다.
 */
export interface ApiPrecheck {
  asset_id: string;
  asset_name: string | null;
  disposal_mode: string;
  disposal_date: string | null;
  evaluated_at: string;
  generated_at: string;
  verdict: string;
  blockers: Record<string, unknown>[];
  preconditions: Record<string, unknown>[];
  holds: Record<string, unknown>[];
  insufficient: Record<string, unknown>[];
  checklist: Record<string, unknown>[];
  resolve_options: string[];
  missing_facts: string[];
  facts_used: Record<string, unknown>;
  not_considered: string[];
  /** 409 일 때만 붙는다 */
  detail?: string;
  [k: string]: unknown;
}

export const precheckDisposal = (
  role: Role,
  assetId: string,
  body: { disposal_mode: string; disposal_date?: string | null }
) =>
  apiFetch<ApiPrecheck>(
    `/api/assets/${encodeURIComponent(assetId)}/disposal/precheck`,
    role,
    {
      method: "POST",
      body: JSON.stringify({
        disposal_mode: body.disposal_mode,
        disposal_date: body.disposal_date ?? null,
      }),
    }
  );

/**
 * 중고 거래 실사 체크리스트 (S18 · `11 §6`). REST 응답 == MCP 도구 출력이다 —
 * 채팅으로 물었을 때와 화면으로 봤을 때 결과가 달라지지 않는다.
 *
 * `verdict` 는 `VERIFIED|PARTIAL|…` 이고 **`PARTIAL` 은 정상 결과다**(409 가 아니라 200).
 * `status:"not_found"` 는 404 로 오며 `reason`(`no_host_asset` 등)이 본문에 있다 —
 * "문제 없음"이 아니라 "실사 대상이 아니다"라는 판정이므로 `errorBody(e)` 로 읽어 보여준다.
 */
export interface ApiOwnership {
  status: "ok" | "not_found" | "error";
  asset_id?: string;
  verdict?: string;
  categories?: Record<string, unknown>[];
  verified?: string[];
  unverified?: string[];
  residual_risk?: unknown;
  mitigation?: unknown;
  not_considered?: string[];
  disclaimer?: unknown;
  reason?: string;
  [k: string]: unknown;
}

export const getOwnership = (role: Role, assetId: string) =>
  apiFetch<ApiOwnership>(`/api/assets/${encodeURIComponent(assetId)}/ownership`, role);

/* -------------------------------------------------------------------------- */
/* 법정 기한 · 위험등급 (S9 · S18, MQ-1102·MQ-1105) — `backend/routers/asset_monitoring.py`  */

/**
 * 이 두 경로 전부 **역할 게이트가 없다**(읽기 판정, `asset_monitoring.py` 상단 주석) —
 * `maintValue`·`ownership`·`disposal/precheck` 와 같은 이유로 403 이 안 난다.
 * 표시는 `lib/deadlines.ts`·`lib/riskGrade.ts` 를 거친다 — 여기서는 원 어휘를 좁히지 않는다.
 */

/** `GET /api/deadlines` 응답의 항목 하나. `type`·`state` 는 원 어휘 그대로(D9/D50). */
export interface ApiDeadlineItem {
  asset_id: string;
  /** "TAX-CREDIT-2Y" | "SAFETY-INSPECTION" — 원 어휘 그대로 */
  type: string;
  law_refs: string[];
  due_date: string;
  days_remaining: number;
  /** "UPCOMING" | "IN_REVIEW_BAND" | "OVERDUE" — 원 어휘 그대로 */
  state: string;
  message: string;
  resolve_options: string[];
  [k: string]: unknown;
}

/** `GET /api/deadlines` 응답. 0건도 `status:"ok"` 다 — 실패가 아니다(D62). */
export interface ApiDeadlines {
  status: string;
  evaluated_at?: string;
  window_days?: number;
  items?: ApiDeadlineItem[];
  not_considered?: string[];
  disclaimer?: string;
  /** status != "ok" 일 때만 */
  reason?: string;
  message?: string;
  [k: string]: unknown;
}

export const getDeadlines = (
  role: Role,
  params?: { assetId?: string; windowDays?: number }
) => {
  const q = new URLSearchParams();
  if (params?.assetId) q.set("asset_id", params.assetId);
  if (params?.windowDays !== undefined) q.set("window_days", String(params.windowDays));
  const qs = q.toString();
  return apiFetch<ApiDeadlines>(`/api/deadlines${qs ? `?${qs}` : ""}`, role);
};

/**
 * `GET /api/buildings/{id}/risk-grade`·`GET /api/assets/{id}/risk-grade` 공통 응답.
 * `current_grade` 는 3속성 중 하나라도 미확인이면 `null` 이다 — `LOW` 로 접지 않는다(D62,
 * `lib/riskGrade.ts` 참조).
 */
export interface ApiRiskGrade {
  status: string;
  building_id?: string;
  facts?: {
    fire_handling: string | null;
    hazmat_volume: string | null;
    power_capacity: string | null;
    product_type: string | null;
  };
  current_grade?: string | null;
  stored_grade?: string | null;
  stored_grade_updated_at?: string | null;
  changed?: boolean;
  grade_scale?: string[];
  rationale?: string;
  not_considered?: string[];
  disclaimer?: string;
  /** status != "ok" 일 때만 */
  reason?: string;
  message?: string;
  [k: string]: unknown;
}

export const getBuildingRiskGrade = (role: Role, buildingId: string) =>
  apiFetch<ApiRiskGrade>(
    `/api/buildings/${encodeURIComponent(buildingId)}/risk-grade`,
    role
  );

export const getAssetRiskGrade = (role: Role, assetId: string) =>
  apiFetch<ApiRiskGrade>(`/api/assets/${encodeURIComponent(assetId)}/risk-grade`, role);

/* -------------------------------------------------------------------------- */
/* 보전지표 · 수리가치 판단 (S1+, MQ-908) — `backend/routers/maint_value.py` 5경로  */

/**
 * 이 5경로 전부 **역할 게이트가 없다**(읽기 판정이라 403 이 안 난다, `maint_value.py` 상단
 * 주석). 값이 `null` 이거나 `mtbf_trend` 가 `"insufficient_data"` 여도 `status:"ok"` 로
 * 200 이다 — "데이터 부족"은 도구 실패가 아니다(D62). 표시는 `lib/maintValue.ts` 를 거친다.
 *
 * ⛔ 아래 응답 인터페이스는 **좁히지 않는다**(`[k: string]: unknown` 유지) — `04 §11~§13`
 *   본문이 `not_considered`·`estimates`·`assumptions` 처럼 계속 늘어나는 배열을 갖고, 여기서
 *   모양을 박아 두면 백엔드가 필드 하나만 늘려도 이 파일이 깨진다. 화면(Stage 6)이 필요한
 *   키만 좁혀 읽는다 (`toEvidenceEntries` 와 같은 태도).
 */

/** `GET /api/assets/{asset_id}/metrics` 응답 (`04 §11`). */
export interface ApiMetrics {
  status: string;
  asset_id?: string;
  window_months?: number;
  mtbf_days?: number | null;
  /** D70 — 가동시간이 아니라 달력 기준임을 계약 수준에서 고지 */
  mtbf_basis?: string | null;
  /** improving | stable | declining | insufficient_data */
  mtbf_trend?: string | null;
  mttr_hours?: number | null;
  availability?: number | null;
  planned_ratio?: number | null;
  n_repairs_signed?: number;
  n_repairs_unsigned?: number;
  cumulative_repair_cost?: number;
  acquisition_cost?: number | null;
  cumulative_repair_ratio?: number | null;
  repeat_failure?: boolean;
  excluded?: string[];
  not_considered?: string[];
  disclaimer?: string;
  /** status != "ok" 일 때만 */
  reason?: string;
  [k: string]: unknown;
}

export const getMetrics = (role: Role, assetId: string, windowMonths?: number) =>
  apiFetch<ApiMetrics>(
    `/api/assets/${encodeURIComponent(assetId)}/metrics${
      windowMonths !== undefined ? `?window_months=${windowMonths}` : ""
    }`,
    role
  );

/** `POST /api/equipment/{equipment_id}/repair-value` 본문. `repair_scope` 생략 시 서버 기본값(RESTORE). */
export interface RepairValueBody {
  failed_part: string;
  repair_cost: number;
  repair_scope?: string;
}

/** `assess_repair_value` 상당 응답 (`04 §13`). 3지 판단 — `verdict` 는 `HOLD` 를 포함해 전부 정상 결과다. */
export interface ApiRepairValue {
  status: string;
  asset_id?: string;
  equipment_id?: string;
  failed_part?: string;
  part_class?: string | null;
  repair_cost?: number;
  repair_scope?: string;
  evaluated_at?: string;
  book_value?: number | null;
  mtbf_trend?: string | null;
  repeat_failure?: boolean;
  cumulative_repair_ratio?: number | null;
  parts_eol_flag?: boolean;
  age_years?: number | null;
  age_bucket?: string | null;
  residual_ratio?: number | null;
  market_value_before?: number | null;
  market_value_after?: number | null;
  value_recovery?: number | null;
  recovery_ratio?: number | null;
  /** REPAIR_RECOMMENDED | REPLACE_RECOMMENDED | SELL_AS_IS | ROOT_CAUSE_FIRST | HOLD */
  verdict?: string;
  reasoning?: string;
  alternatives?: unknown[];
  /** 값이 있는 추정 필드의 이름만(D65) — 문장이 아니라 필드로 고지 */
  estimates?: string[];
  assumptions?: string[];
  not_considered?: string[];
  disclaimer?: string;
  reason?: string;
  [k: string]: unknown;
}

export const postRepairValue = (role: Role, equipmentId: string, body: RepairValueBody) =>
  apiFetch<ApiRepairValue>(`/api/equipment/${encodeURIComponent(equipmentId)}/repair-value`, role, {
    method: "POST",
    body: JSON.stringify({
      failed_part: body.failed_part,
      repair_cost: body.repair_cost,
      repair_scope: body.repair_scope ?? null,
    }),
  });

/** `classify_part_criticality` 상당 응답 (`04 §10`). `reviewed:false` — 사람 검수 전 초안이다. */
export interface ApiCriticality {
  status: string;
  part_no?: string;
  /** CONSUMABLE | CRITICAL */
  part_class?: string;
  basis?: string;
  name?: string;
  category?: string | null;
  discontinued?: boolean;
  reviewed?: boolean;
  note?: string;
  not_considered?: string[];
  disclaimer?: string;
  reason?: string;
  [k: string]: unknown;
}

export const getCriticality = (role: Role, partNo: string) =>
  apiFetch<ApiCriticality>(`/api/parts/${encodeURIComponent(partNo)}/criticality`, role);

export interface ApiInventoryItem {
  part_no: string;
  name: string;
  qty: number;
  safety_stock: number;
  location: string;
  compatible_models: string[];
  discontinued: boolean;
}

export interface ApiInventory {
  status: string;
  items?: ApiInventoryItem[];
  reason?: string;
  message?: string;
  [k: string]: unknown;
}

export const getInventory = (
  role: Role,
  params: { part_no?: string; part_name?: string; model?: string }
) => {
  const q = new URLSearchParams();
  if (params.part_no) q.set("part_no", params.part_no);
  if (params.part_name) q.set("part_name", params.part_name);
  if (params.model) q.set("model", params.model);
  const qs = q.toString();
  return apiFetch<ApiInventory>(`/api/inventory${qs ? `?${qs}` : ""}`, role);
};

/**
 * `POST /api/expenditure/classify` 본문. `part_no`·`part_class` 는 **either-or** —
 * 둘 다 주면 백엔드가 422 다. `asset_id` 는 이 REST 경로에 없다(취득원가 대비 중요도
 * 평가는 이 경로가 아니라 `assess_repair_value` 가 이미 해서 넘겨준다, `maint_value.py`).
 */
export interface ExpenditureBody {
  part_no?: string | null;
  part_class?: string | null;
  repair_scope: string;
  amount: number;
}

/** `classify_expenditure` 상당 응답 (`04 §12`). `verdict:"HOLD"` 는 실패가 아니라 판정이다. */
export interface ApiExpenditure {
  status: string;
  /** CAPITAL | REVENUE | HOLD */
  verdict?: string;
  asset_id?: string | null;
  part_class?: string;
  repair_scope?: string;
  amount?: number;
  basis?: string;
  law_refs?: string[];
  citations?: string[];
  reasoning?: string;
  requires_expert_review?: boolean;
  /** COMPLETE | LAW_TEXT_PENDING */
  evidence_completeness?: string;
  materiality?: Record<string, unknown>;
  evaluated_at?: string;
  not_considered?: string[];
  disclaimer?: string;
  reason?: string;
  [k: string]: unknown;
}

export const postExpenditure = (role: Role, body: ExpenditureBody) =>
  apiFetch<ApiExpenditure>("/api/expenditure/classify", role, {
    method: "POST",
    body: JSON.stringify({
      part_no: body.part_no ?? null,
      part_class: body.part_class ?? null,
      repair_scope: body.repair_scope,
      amount: body.amount,
    }),
  });

/**
 * `GET /api/assets/{asset_id}/evidence-bundle` 응답 — `build_evidence_bundle` 상당
 * 확장 응답(`04 §14`, `services/decisions.rebuild_bundle`). 5키 번들은 `evidence_bundle`
 * 안에 있다(D83) — 여기서 그 안쪽 모양을 좁히지 않는다(렌더 쪽이 필요한 키만 읽는다).
 * 409(`law_text_unavailable`·`cited_rule_missing` 상당)는 `reason`·`detail`·
 * `missing_law_refs`|`missing_rules` 로 온다 — `errorBody(e)` 로 읽는다.
 */
export interface ApiEvidenceBundle {
  status: string;
  asset_id?: string;
  evidence_bundle?: Record<string, unknown>;
  bundle_hash?: string;
  hash_spec?: string;
  verdict?: string;
  not_considered?: string[];
  built_at?: string;
  disclaimer?: string;
  reason?: string;
  detail?: string;
  missing_law_refs?: string[];
  missing_rules?: string[];
  [k: string]: unknown;
}

export const getEvidenceBundle = (role: Role, assetId: string, mode: string, date?: string) => {
  const q = new URLSearchParams({ disposal_mode: mode });
  if (date) q.set("disposal_date", date);
  return apiFetch<ApiEvidenceBundle>(
    `/api/assets/${encodeURIComponent(assetId)}/evidence-bundle?${q.toString()}`,
    role
  );
};

/* -------------------------------------------------------------------------- */
/* 수리 증빙 (S19, MQ-909) — backend/routers/repairs.py                        */

/**
 * `GET/POST /api/repairs/*` (`backend/routers/repairs.py`, MQ-909, Stage 5). `state` 는
 * `decisions` 와 같은 원 어휘 그대로(D85, draft|pending|signed|rejected) — 표시는
 * `mappers.repairStateView`. `sign`·`reject` 는 `verified_by`(팀장)를 채운다 — 반려자도
 * 이 컬럼을 공유한다(별도 `reviewed_by` 컬럼 없음, `backend/services/repairs.py` 참고).
 */
export interface ApiRepair {
  repair_id: string;
  /** draft | pending | signed | rejected — 원 어휘 그대로(D85). 표시는 `mappers.repairStateView` */
  state: string;
  equipment_id: string;
  work_type?: string;
  repair_scope?: string;
  part_class?: string | null;
  expenditure_class?: string | null;
  expenditure_reason?: string | null;
  cost?: number;
  downtime_hours?: number | null;
  parts?: { part_no: string; serial?: string | null; qty: number }[];
  model?: string | null;
  error_code?: string | null;
  note?: string | null;
  /** 서명 전에는 null (D84) */
  record_hash?: string | null;
  /** 저장된 record_hash 를 재계산해 대조한 결과(D84). 미서명이면 항상 false */
  hash_verified?: boolean;
  performed_by?: string | null;
  performed_by_name?: string;
  requested_by?: string | null;
  requested_by_name?: string;
  verified_by?: string | null;
  verified_by_name?: string;
  created_at?: string | null;
  signed_at?: string | null;
  next_step?: string;
  disclaimer?: string;
  [k: string]: unknown;
}

export const getRepairs = (role: Role, state?: string) =>
  apiFetch<{ items: ApiRepair[] }>(
    `/api/repairs${state ? `?state=${encodeURIComponent(state)}` : ""}`,
    role
  ).then((r) => r.items);

export const getRepair = (role: Role, repairId: string) =>
  apiFetch<ApiRepair>(`/api/repairs/${encodeURIComponent(repairId)}`, role);

/** draft → pending. **정비사만** — `submitPo`·`submitDecision` 과 같은 패턴. 본문 없음. */
export const submitRepair = (repairId: string) =>
  apiFetch<ApiRepair>(`/api/repairs/${encodeURIComponent(repairId)}/submit`, "technician", {
    method: "POST",
  });

/** pending → signed. **팀장만.** 본문 없음 — `override` 개념 자체가 없다(수리 증빙엔 D81 급 차단 없음). */
export const signRepair = (repairId: string) =>
  apiFetch<ApiRepair>(`/api/repairs/${encodeURIComponent(repairId)}/sign`, "manager", {
    method: "POST",
  });

/** pending → rejected. 사유 필수(D38) — 공백이면 백엔드가 422. */
export const rejectRepair = (repairId: string, reason: string) =>
  apiFetch<ApiRepair>(`/api/repairs/${encodeURIComponent(repairId)}/reject`, "manager", {
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

/* -------------------------------------------------------------------------- */
/* A2A 호출 감사 이력 (D114) — `backend/services/a2a_history.py`                */

/** `GET /api/a2a/history` 항목 하나 (D114). `request`/`response` 는 파트너 스킬마다 모양이
 * 달라 좁히지 않는다 — 소비자가 필요한 키만 골라 읽는다(`ApiMetrics` 와 같은 태도). */
export interface ApiA2aHistoryItem {
  request_chain_id: string;
  skill: string;
  session_id: string;
  status: string | null;
  request: Record<string, unknown> | null;
  response: Record<string, unknown> | null;
  ts: string;
}

export interface ApiA2aHistory {
  count: number;
  items: ApiA2aHistoryItem[];
}

export const getA2aHistory = (
  role: Role,
  params?: { skill?: string; poId?: string; buildingId?: string; chainId?: string; limit?: number }
) => {
  const q = new URLSearchParams();
  if (params?.skill) q.set("skill", params.skill);
  if (params?.poId) q.set("po_id", params.poId);
  if (params?.buildingId) q.set("building_id", params.buildingId);
  if (params?.chainId) q.set("chain_id", params.chainId);
  if (params?.limit !== undefined) q.set("limit", String(params.limit));
  const qs = q.toString();
  return apiFetch<ApiA2aHistory>(`/api/a2a/history${qs ? `?${qs}` : ""}`, role);
};

export const endpoints = {
  chat: "/api/chat",
  trace: (sessionId: string) => `/api/chat/${sessionId}/trace`,
  poQueue: (state = "pending") => `/api/po?state=${state}`,
  po: (poId: string) => `/api/po/${poId}`,
  poSubmit: (poId: string) => `/api/po/${poId}/submit`,
  poApprove: (poId: string) => `/api/po/${poId}/approve`,
  poReject: (poId: string) => `/api/po/${poId}/reject`,
  /** 통합 승인 큐 (D85) — 읽기 전용. 전이는 종류별 경로가 각자의 역할 게이트와 함께 한다 */
  approvals: "/api/approvals",
  decisions: "/api/decisions",
  decision: (id: string) => `/api/decisions/${id}`,
  decisionSubmit: (id: string) => `/api/decisions/${id}/submit`,
  decisionSign: (id: string) => `/api/decisions/${id}/sign`,
  decisionReject: (id: string) => `/api/decisions/${id}/reject`,
  assets: "/api/assets",
  asset: (assetId: string) => `/api/assets/${assetId}`,
  assetOwnership: (assetId: string) => `/api/assets/${assetId}/ownership`,
  disposalPrecheck: (assetId: string) => `/api/assets/${assetId}/disposal/precheck`,
  equipment: "/api/equipment",
  equipmentHistory: (id: string) => `/api/equipment/${id}/history`,
  /** 에러 발생 이력 기록 — 정비사의 명시적 액션만 (D29) */
  equipmentErrors: (id: string) => `/api/equipment/${id}/errors`,
  /** 법정 기한 · 위험등급 (MQ-1102·MQ-1105) */
  deadlines: "/api/deadlines",
  buildingRiskGrade: (buildingId: string) => `/api/buildings/${buildingId}/risk-grade`,
  assetRiskGrade: (assetId: string) => `/api/assets/${assetId}/risk-grade`,
  /** 보전지표 · 수리가치 판단 (MQ-908) */
  assetMetrics: (assetId: string) => `/api/assets/${assetId}/metrics`,
  equipmentRepairValue: (equipmentId: string) => `/api/equipment/${equipmentId}/repair-value`,
  partCriticality: (partNo: string) => `/api/parts/${partNo}/criticality`,
  expenditureClassify: "/api/expenditure/classify",
  assetEvidenceBundle: (assetId: string) => `/api/assets/${assetId}/evidence-bundle`,
  /** 수리 증빙 (MQ-909) — `backend/routers/repairs.py` */
  repairs: "/api/repairs",
  repair: (repairId: string) => `/api/repairs/${repairId}`,
  repairSubmit: (repairId: string) => `/api/repairs/${repairId}/submit`,
  repairSign: (repairId: string) => `/api/repairs/${repairId}/sign`,
  repairReject: (repairId: string) => `/api/repairs/${repairId}/reject`,
} as const;
