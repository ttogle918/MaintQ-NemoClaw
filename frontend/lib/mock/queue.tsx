import { Mono } from "@/components/ui/Mono";
import type { EvidenceEntry, QueueEntry, SupplierQuote } from "../types";

export const PENDING: QueueEntry[] = [
  {
    poId: "PO-0117",
    title: "냉각팬 ×2",
    urgency: "urgent",
    state: "pending",
    meta: "1번 라인 · 김OO · 10분 전",
  },
  {
    poId: "PO-0116",
    title: "제어보드",
    note: "(대체품)",
    urgency: "normal",
    state: "pending",
    meta: "1번 라인 · 이OO · 2시간 전",
  },
  {
    poId: "PO-0115",
    title: "퓨즈 ×10",
    urgency: "normal",
    state: "pending",
    meta: "2번 라인 · 김OO · 어제",
  },
];

export const RECENT: QueueEntry[] = [
  { poId: "PO-0114", title: "V벨트 ×1", urgency: "normal", state: "approved", meta: "" },
  {
    poId: "PO-0113",
    title: "인버터 ×1",
    note: "· 사유: 예산",
    urgency: "normal",
    state: "rejected",
    meta: "",
  },
];

export const PENDING_COUNT = PENDING.length;

/**
 * 근거 요약 카드 (D34).
 * SYMPTOMS·NOTES 는 po_drafts.evidence 의 symptoms / notes 에서 온다 —
 * "어떤 현상을 보고 고장으로 판단했는가" 가 승인 판단의 핵심이라 근거 카드에 노출한다.
 */
export const EVIDENCE_PO_0117: EvidenceEntry[] = [
  {
    label: "ERROR",
    value: (
      <>
        iG5A · <Mono>OHt</Mono> (과열) — 1번 라인 <Mono>INV-L1-01</Mono>
      </>
    ),
  },
  {
    label: "SYMPTOMS",
    value: <>냉각팬 소음 증가 · 3번 라인 2회 정지</>,
  },
  {
    label: "DIAGNOSIS",
    value: <>냉각팬 고장 유력</>,
    citation: { manual: "매뉴얼", page: 202, printPage: 202 },
  },
  {
    label: "INVENTORY",
    value: (
      <>
        재고 1 / 안전재고 3 — <b>부족분 2</b> · 자재창고 A-12
      </>
    ),
  },
  {
    label: "NOTES",
    value: <>야간조 정비사 육안 확인 — 팬 회전 불량</>,
  },
  {
    label: "TRACE",
    value: "에이전트 실행 로그 전체 보기 →",
    href: "/manager/trace/S1",
  },
];

export const QUOTES_PO_0117: SupplierQuote[] = [
  {
    supplierId: "SUP-A",
    name: "A사",
    leadDays: 3,
    unitPrice: 38000,
    recommended: true,
    note: "긴급도 高 → 최단 납기 우선",
  },
  {
    supplierId: "SUP-B",
    name: "B사",
    leadDays: 14,
    unitPrice: 29000,
    moq: 10,
    note: "단가 최저 · MOQ 10 — 수량 2 로는 발주 불가 (D31)",
  },
];
