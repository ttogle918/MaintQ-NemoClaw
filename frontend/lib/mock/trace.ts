import type { TraceSession } from "../types";

/** M2 에서 traces 테이블 / SSE tool_call·tool_result 로 대체된다 (D21). */
export const TRACE_S1: TraceSession = {
  label: "SESSION #S1 · 오케스트레이션",
  meta: "2.1s · 5 calls",
  accent: "blue",
  steps: [
    {
      tool: "lookup_error_code",
      input: 'in: {model:"iG5A", code:"OHt"}',
      summary: "✓ 0.4s · 과열 · related: FAN-IG5-01",
      status: "ok",
    },
    {
      tool: "rag_search_manual",
      input: 'in: {query:"OHt 점검 절차"}',
      summary: "✓ 1.2s · p.202 인용 2건",
      status: "ok",
    },
    {
      tool: "search_inventory",
      input: 'in: {model:"iG5A", part:"FAN-IG5-01"}',
      summary: "⚠ 분기 · 재고 1 < 안전재고 3 → 부족분 2 제안",
      status: "warn",
    },
    {
      tool: "get_supplier_quotes",
      input: 'in: {part:"FAN-IG5-01", qty:2}',
      summary: "✓ 0.3s · A사 3일 vs B사 14일(MOQ 10)",
      status: "ok",
    },
    {
      tool: "create_po_draft",
      input: "대기: 사용자 공급사 선택 필요",
      summary: "○ pending",
      status: "pending",
    },
  ],
};

export const TRACE_S3: TraceSession = {
  label: "SESSION #S3 · 이력 기반 판단 · 분기",
  meta: "1.9s · 3 calls",
  accent: "orange",
  steps: [
    {
      tool: "lookup_error_code",
      input: 'in: {model:"iG5A", code:"OCt"}',
      summary: "✓ 0.4s · 과전류 · related: 모터·케이블",
      status: "ok",
    },
    {
      tool: "get_error_history",
      input: 'in: {equipment_id:"INV-L3-01", days:30}',
      summary: "⚠ 분기 · count 3, repeated=true → 근본원인 모드",
      status: "warn",
    },
    {
      tool: "rag_search_manual",
      input: 'in: {query:"OCt 근본원인 점검 절차"}',
      summary: "✓ 1.1s · p.204 인용 3건 · ⚠ 안전 경고 삽입",
      status: "ok",
    },
    {
      tool: "create_po_draft",
      input: "차단: 원인 확정 전 발주 금지",
      summary: "⏸ held · 발주 보류",
      status: "held",
      strikeTool: true,
    },
  ],
};
