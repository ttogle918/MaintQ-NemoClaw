import type { ReactNode } from "react";
import type { Citation } from "./citation";

/* -------------------------------------------------------------------------- */
/* 발주 (docs/05_DB_SCHEMA §8)                                                */

export type PoState = "draft" | "pending" | "approved" | "rejected";
export type Urgency = "urgent" | "normal";

export interface PoDraft {
  poId: string;
  partName: string;
  partNo: string;
  qty: number;
  /** 안전재고 부족분을 포함한 수량인지 */
  qtyNote?: string;
  supplierName: string;
  leadDays: number;
  /** 도구 파라미터가 아니라 서버가 채운 스냅샷 (D31) */
  unitPrice: number;
  state: PoState;
}

/** S3 — 원인 확정 전 발주 보류 (발주 카드가 아니다) */
export interface PoHold {
  reason: ReactNode;
  checklist: { label: string; citation: Citation }[];
}

/* -------------------------------------------------------------------------- */
/* 수리 증빙 (S19, MQ-912) — 원 어휘 그대로(D85), 표시는 `mappers.repairStateView` */

/**
 * `repair_records.state`. `PoState` 와 어휘가 다르다(`signed` 는 처분과 같은 사건 —
 * 서명은 책임 귀속이 붙는 별개 사건이라 발주의 `approved` 와 같은 칸이 아니다).
 * 백엔드 `GET/POST /api/repairs/*`(`backend/routers/repairs.py`, MQ-909)는 이미 있다 —
 * 단 이 타입은 현재 어디서도 소비되지 않는다(`ApiRepair.state`는 `string`으로 원 어휘를
 * 그대로 받는다). 큐 상세 화면(`RepairDetail.tsx`, MQ-916, 다음 스프린트)이 붙을 때
 * 정식으로 연결하거나, 그때도 안 쓰이면 제거할 것.
 */
export type RepairState = "draft" | "pending" | "signed" | "rejected";

/* -------------------------------------------------------------------------- */
/* 승인 큐 (화면 B) — 통합 큐 `GET /api/approvals` (D85)                        */

/**
 * 승인 대상 종류. **`repair`는 Sprint 9(MQ-909)부터 실제로 채워진다**
 * (`backend/services/approvals.py:_repair_item()`) — 이전엔 계약만 있고 항상 0건이었다.
 */
export type ApprovalKind = "po" | "disposal" | "repair";

/**
 * 큐 한 줄. 발주서·처분서·(수리)를 **한 형태로** 담는다.
 *
 * ⛔ `state` 를 공통 어휘로 정규화하지 않는다 — 발주의 `approved` 와 처분의 `signed` 는
 *   다른 사건이다(백엔드 `services/approvals.py` 의 같은 주석). 그래서 타입이 `string` 이고,
 *   "무엇으로 보이게 할 것인가"는 `lib/queueState.stateView(kind, state)` 한 곳이 정한다.
 * ⛔ `urgency`·`verdict`·`requiresOverride` 의 `null` 을 기본값으로 메우지 않는다 —
 *   처분서에는 긴급도가, 발주서에는 판정이 **없다**. `"normal"`·`false` 로 채우면
 *   없는 사실이 생긴다 (D62·D87).
 */
export interface QueueEntry {
  kind: ApprovalKind;
  /** 종류 불문 식별자 — `PO-0117` · `DEC-0001` */
  id: string;
  title: string;
  /** "(대체품)" 같은 부가 표기 */
  note?: string;
  /** 처분서는 `null` — 배지를 만들지 않는다 */
  urgency: Urgency | null;
  /** **원 어휘 그대로.** po: draft|pending|approved|rejected · disposal: …|signed|… */
  state: string;
  meta: string;
  /**
   * 상세 화면 경로. **착지점이 아직 없으면 `null`** — `repair` 가 그렇다(Sprint 8).
   * 빈 문자열 대신 `null` 인 이유: `<Link href="">` 는 조용히 현재 페이지로 가서
   * "눌렀는데 아무 일도 안 난다"가 되고, 라우트가 없다는 사실이 화면에서 사라진다.
   */
  detailHref: string | null;
  /** 처분 판정(`BLOCKED` 등). 발주에는 없다 → `null` */
  verdict?: string | null;
  requiresOverride?: boolean | null;
}

/** 근거 요약 카드 한 행 */
export interface EvidenceEntry {
  label: string;
  value: ReactNode;
  citation?: Citation;
  /** 지정 시 값 대신 링크로 렌더 */
  href?: string;
}

export interface SupplierQuote {
  supplierId: string;
  name: string;
  leadDays: number;
  unitPrice: number;
  moq?: number;
  /** 추천 강조 테두리 — 추천 로직 자체는 백로그 P2 */
  recommended?: boolean;
  note: string;
}

/* -------------------------------------------------------------------------- */
/* 실행 trace (docs/09_RUNTIME §1)                                            */

/**
 * 스텝 상태 5종 (D44).
 *
 * `error` 는 **장애 전용**이다 — MCP 연결 실패·도구 예외·타임아웃 (09_RUNTIME §3).
 * `warn` 은 분기(not_found · empty)를 뜻하며 장애가 아니다. 둘을 한 색으로 뭉개면
 * "매뉴얼에 없는 코드"와 "도구 서버가 죽었다"를 화면에서 구분할 수 없다.
 * 타임아웃은 타입을 늘리지 않고 `error` + summary `✗ timeout ·` 접두로 표기한다 (D46).
 */
export type TraceStatus = "ok" | "warn" | "pending" | "held" | "error";

export interface TraceStepData {
  /** 도구명 — 모노스페이스로 렌더 */
  tool: string;
  /** "in: {model:\"iG5A\", code:\"OHt\"}" */
  input: string;
  summary: string;
  status: TraceStatus;
  /** 차단된 호출은 도구명에 취소선 */
  strikeTool?: boolean;
}

export interface TraceSession {
  label: string;
  meta: string;
  accent: "blue" | "orange";
  steps: TraceStepData[];
  /**
   * 재생(`?replay=…`) 이벤트가 1건 이상 섞인 세션 (D55).
   * 표식은 백엔드 `TraceWriter(replay=True)` 가 payload 에 심은 `replay: true` 를
   * **읽기만** 한 결과다 — 프론트가 부여·수정하지 않는다. mock 데이터는 이 필드가
   * 없으므로(undefined) 배지가 뜨지 않는다.
   */
  replay?: boolean;
}

/* -------------------------------------------------------------------------- */
/* 채팅 (SSE 이벤트 → 렌더 단위)                                               */

/**
 * SSE block 이벤트는 3종이다 — safety / po_card / citation (D22).
 * `po_draft` 와 `po_hold` 는 둘 다 **po_card 로 도착**하며 variant 로 갈린다.
 * `repeat_banner` 는 block 이 아니라, hold payload 의 `repeated:{count, window_days}`(D45)로
 * 리듀서(`lib/chatStream`)가 산출한다 — `repeated.count > 0` 이면 hold 카드 앞에 배너를 얹는다.
 * mock 은 개별 발생 날짜까지 상세하지만, 라이브는 payload 가 주는 `count`·`window_days` 만 쓴다
 * (날짜를 지어내지 않는다, MQ-405).
 */
export type ChatItem =
  | { kind: "user"; id: string; content: ReactNode }
  | { kind: "agent"; id: string; content: ReactNode; citations?: Citation[] }
  | { kind: "safety"; id: string; title: string; body: ReactNode; citation: Citation }
  | { kind: "repeat_banner"; id: string; badge: string; content: ReactNode }
  | { kind: "po_draft"; id: string; po: PoDraft }
  | { kind: "po_hold"; id: string; hold: PoHold }
  /** block 이 아니라 사용자 액션 — POST /api/equipment/{id}/errors (D29·A7) */
  | { kind: "error_log"; id: string; equipmentId: string; code: string; recordedAt?: string };
