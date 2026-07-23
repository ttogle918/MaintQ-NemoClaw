import { Mono } from "@/components/ui/Mono";
import type { ApiPo } from "./api";
import type { Citation } from "./citation";
import type { EvidenceEntry, QueueEntry, SupplierQuote } from "./types";

/**
 * 백엔드 응답 → 화면 B 컴포넌트 props.
 *
 * 매핑을 한 곳에 모아 두는 이유: 컴포넌트가 API 모양을 직접 알면
 * 계약이 바뀔 때마다 UI 전체를 훑어야 한다.
 */

export function toQueueEntry(po: ApiPo): QueueEntry {
  return {
    poId: po.po_id,
    title: `${po.part_name} ×${po.qty}`,
    urgency: po.urgency,
    state: po.state,
    meta: [po.requested_by_name, relativeTime(po.created_at)].filter(Boolean).join(" · "),
  };
}

export function toQuotes(po: ApiPo): SupplierQuote[] {
  const quotes = po.quotes ?? [];
  return quotes.map((q) => ({
    supplierId: q.supplier_id,
    name: q.name,
    leadDays: q.lead_days,
    unitPrice: q.unit_price,
    moq: q.moq,
    // 이 발주가 고른 공급사를 강조한다. 자동 추천 로직 자체는 백로그 P2
    recommended: q.supplier_id === po.supplier_id,
    note: quoteNote(q, po.qty),
  }));
}

function quoteNote(
  q: { lead_days: number; moq: number },
  qty: number
): string {
  // MOQ 미달이면 발주가 거부된다 (D31) — 고르기 전에 알려야 한다
  if (q.moq > qty) return `MOQ ${q.moq} — 수량 ${qty}로는 발주 불가 (D31)`;
  return q.lead_days <= 3 ? "최단 납기" : `리드타임 ${q.lead_days}일`;
}

/**
 * 근거 요약 카드 행 (D34).
 * symptoms → SYMPTOMS, basis 의 manual_page → DIAGNOSIS 인용, notes → NOTES.
 * 값이 없는 행은 아예 만들지 않는다 — 빈 행이 늘어지면 "3초 안에 읽는" 목적이 깨진다.
 */
export function toEvidenceEntries(po: ApiPo): EvidenceEntry[] {
  const rows: EvidenceEntry[] = [];

  if (po.model && po.error_code) {
    rows.push({
      label: "ERROR",
      value: (
        <>
          {po.model} · <Mono>{po.error_code}</Mono>
        </>
      ),
    });
  }

  const symptoms = po.evidence?.symptoms ?? [];
  if (symptoms.length) {
    rows.push({ label: "SYMPTOMS", value: symptoms.join(" · ") });
  }

  rows.push({ label: "DIAGNOSIS", value: po.reason, citation: firstCitation(po) });

  if (po.inventory) {
    const short = po.inventory.safety_stock - po.inventory.qty;
    rows.push({
      label: "INVENTORY",
      value: (
        <>
          재고 {po.inventory.qty} / 안전재고 {po.inventory.safety_stock}
          {short > 0 && <b> — 부족분 {short}</b>} · {po.inventory.location}
        </>
      ),
    });
  }

  if (po.evidence?.notes) {
    rows.push({ label: "NOTES", value: po.evidence.notes });
  }

  if (po.session_id) {
    rows.push({
      label: "TRACE",
      value: "에이전트 실행 로그 전체 보기 →",
      href: `/manager/trace/${po.session_id}`,
    });
  }

  if (po.decision_note) {
    rows.push({
      label: po.state === "rejected" ? "반려 사유" : "승인 코멘트",
      value: `${po.decision_note}${po.decided_by_name ? ` (${po.decided_by_name})` : ""}`,
    });
  }

  return rows;
}

/** basis 안의 manual_page 를 인용 칩으로. 오프셋은 백엔드가 이미 적용해 보낸다 (D32). */
function firstCitation(po: ApiPo): Citation | undefined {
  const page = po.evidence?.basis?.find((b) => typeof b.manual_page === "number")?.manual_page;
  if (typeof page !== "number") return undefined;
  return { manual: `${po.model ?? ""} 매뉴얼`.trim(), page, printPage: page };
}

function relativeTime(iso: string): string {
  const then = new Date(iso.replace(" ", "T")).getTime();
  if (Number.isNaN(then)) return "";
  const min = Math.floor((Date.now() - then) / 60000);
  if (min < 1) return "방금";
  if (min < 60) return `${min}분 전`;
  if (min < 60 * 24) return `${Math.floor(min / 60)}시간 전`;
  return `${Math.floor(min / 1440)}일 전`;
}
