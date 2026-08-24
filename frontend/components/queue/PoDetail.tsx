"use client";

import { StateBadge, UrgencyBadge } from "@/components/ui/Badge";
import { Mono } from "@/components/ui/Mono";
import { sx } from "@/lib/sx";
import { isApprovedState, isPendingState } from "@/lib/queueState";
import type { EvidenceEntry, QueueEntry, SupplierQuote } from "@/lib/types";
import { DecisionBar } from "./DecisionBar";
import { DocumentPreview } from "./DocumentPreview";
import { EvidenceCard } from "./EvidenceCard";
import { FinanceDecisionBar } from "./FinanceDecisionBar";
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
  isFinanceApprover,
  onFinanceApprove,
  onFinanceReject,
}: {
  entry: QueueEntry;
  evidence: EvidenceEntry[];
  quotes: SupplierQuote[];
  /** D118 — 백엔드가 조회 시점에 렌더한 문서 미리보기. 목업 모드(라이브 아님)에서는 없다 */
  documentsPreview?: {
    po_request: string;
    diagnosis: string | null;
    fund_execution: string | null;
  } | null;
  /** 미지정이면 목업 모드 — 버튼이 아무것도 저장하지 않는다 */
  onApprove?: () => void;
  onReject?: (reason: string) => void;
  /** MQ-1714 가 `getManagerIdentity().department === "finance"` 로 계산해 넘긴다 */
  isFinanceApprover?: boolean;
  onFinanceApprove?: () => void;
  onFinanceReject?: (reason: string) => void;
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
          <DocumentPreview
            title="자금집행 요청서"
            sub="미리보기 — 재무 승인 대기/완료 발주만 표시(팀장 승인 전에는 해당 없음)"
            text={documentsPreview.fund_execution}
          />
        </>
      )}

      {isPendingState(entry.state) && (
        <DecisionBar
          supplierName={recommended?.name ?? ""}
          onApprove={onApprove}
          onReject={onReject}
        />
      )}
      {isApprovedState(entry.state) && (
        <FinanceDecisionBar
          supplierName={recommended?.name ?? ""}
          canAct={isFinanceApprover ?? false}
          onApprove={onFinanceApprove}
          onReject={onFinanceReject}
        />
      )}
    </div>
  );
}
