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

  // session_id 가 없는 발주(사람이 직접 올린 소모품 보충 등)는 TRACE 행을 **만들지 않는다**.
  // 없는 세션도 200 을 주므로(D43) 링크는 열리지만 `/manager/trace/null` 이라는 착지점은
  // 존재하지 않는 세션을 가리키는 죽은 링크다 — 애초에 만들지 않는 게 맞다.
  if (po.session_id) {
    rows.push({
      label: "TRACE",
      value: "에이전트 실행 로그 전체 보기 →",
      href: `/manager/trace/${encodeURIComponent(po.session_id)}`,
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

/**
 * basis 안의 `manual_page` 를 인용 칩으로.
 *
 * **`printPage` 는 백엔드가 준 값을 그대로 옮길 뿐, 여기서 계산하지 않는다 (D26·D32·D57).**
 * `evidence.basis[].manual_page` 는 PDF **물리** 페이지다 (D26 — 저장·검증의 단일 기준).
 * `print_page` 는 `GET /api/po/{id}` 가 응답 조립 시점에 계산해 붙인 값(D57,
 * `backend.services.po._attach_print_pages` → `manifest.to_print_page`) — 오프셋
 * 변환은 여전히 그 한 곳에서만 하고, 프론트는 옮겨 적기만 한다 (D32 불변).
 *
 * `model` 이 미확정(에러코드 승인 전 등)이거나 `manual_page` 가 없으면 백엔드가 `print_page`
 * 를 아예 안 보낸다 — 이때 `printPage` 를 `page` 로 채우면 offset 이 0 이 아닌 S100(16)에서
 * **물리 p.416 을 인쇄 p.416 인 양** 표시하게 된다(D32 가 막으려던 문제). 그래서 `printPage`
 * 는 **없으면 undefined 로 둔다** — `citationLabel()` 이 그 경우 `"{manual} PDF p.{page}"`
 * 로 정직하게 병기한다 (W-6 표시측 해소, Stage 1).
 */
function firstCitation(po: ApiPo): Citation | undefined {
  const basis = po.evidence?.basis?.find((b) => typeof b.manual_page === "number");
  if (!basis || typeof basis.manual_page !== "number") return undefined;
  return {
    manual: `${po.model ?? ""} 매뉴얼`.trim(),
    page: basis.manual_page,
    printPage: typeof basis.print_page === "number" ? basis.print_page : undefined,
  };
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
