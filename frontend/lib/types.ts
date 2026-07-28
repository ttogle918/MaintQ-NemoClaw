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
/* 승인 큐 (화면 B)                                                            */

export interface QueueEntry {
  poId: string;
  title: string;
  /** "(대체품)" 같은 부가 표기 */
  note?: string;
  urgency: Urgency;
  state: PoState;
  meta: string;
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
 * `repeat_banner` 는 block 이 아니라 get_error_history 의 tool_result 에서 파생되는 UI 요소다.
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
