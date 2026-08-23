"use client";

import { StateBadge, UrgencyBadge } from "@/components/ui/Badge";
import { Mono } from "@/components/ui/Mono";
import { sx } from "@/lib/sx";
import type { EvidenceEntry, QueueEntry, SupplierQuote } from "@/lib/types";
import { DecisionBar } from "./DecisionBar";
import { DocumentPreview } from "./DocumentPreview";
import { EvidenceCard } from "./EvidenceCard";
import { SupplierCompare } from "./SupplierCompare";
import { WithdrawalStatusPanel } from "./WithdrawalStatusPanel";

/**
 * 발주 상세. **`kind === "po"` 항목에만 렌더한다** — 처분 상세는 Stage 6(`DecisionDetail`).
 * 계약은 무변경이다: 여전히 `QueueEntry` + 근거 + 견적 + 승인/반려다.
 */
export function PoDetail({
  entry,
  evidence,
  quotes,
  documentsPreview,
  onApprove,
  onReject,
}: {
  entry: QueueEntry;
  evidence: EvidenceEntry[];
  quotes: SupplierQuote[];
  /** D118 — 백엔드가 조회 시점에 렌더한 문서 미리보기. 목업 모드(라이브 아님)에서는 없다 */
  documentsPreview?: { po_request: string; diagnosis: string | null } | null;
  /** 미지정이면 목업 모드 — 버튼이 아무것도 저장하지 않는다 */
  onApprove?: () => void;
  onReject?: (reason: string) => void;
}) {
  const recommended = quotes.find((q) => q.recommended) ?? quotes[0];

  return (
    <div style={sx("display:flex;flex-direction:column;padding:18px 20px")}>
      <div style={sx("display:flex;align-items:center;gap:9px;margin-bottom:14px")}>
        <span style={sx("font:700 17px 'Pretendard';color:var(--ink)")}>
          <Mono size={15}>#{entry.id}</Mono> {entry.title}
        </span>
        <UrgencyBadge urgency={entry.urgency} size={10} />
        <StateBadge kind={entry.kind} state={entry.state} size={10} />
        <div style={sx("flex:1")} />
        <span style={sx("font:11px 'JetBrains Mono',monospace;color:var(--dim2)")}>
          요청 · {entry.meta}
        </span>
      </div>

      <EvidenceCard entries={evidence} />
      <SupplierCompare quotes={quotes} />
      <WithdrawalStatusPanel poId={entry.id} />

      {documentsPreview && (
        <>
          <DocumentPreview
            title="설비 이상 진단 보고서"
            sub="미리보기 — 에러코드 정의·근거를 조회 시점에 렌더한 문안"
            text={documentsPreview.diagnosis}
          />
          <DocumentPreview
            title="정비 · 부품 발주 요청서"
            sub="미리보기 — 발주 데이터를 조회 시점에 렌더한 문안"
            text={documentsPreview.po_request}
          />
        </>
      )}

      <DecisionBar
        supplierName={recommended?.name ?? ""}
        onApprove={onApprove}
        onReject={onReject}
      />
    </div>
  );
}
