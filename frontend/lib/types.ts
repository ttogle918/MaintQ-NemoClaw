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

export type TraceStatus = "ok" | "warn" | "pending" | "held";

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
