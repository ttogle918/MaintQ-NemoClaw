"use client";

import { StateBadge, UrgencyBadge } from "@/components/ui/Badge";
import { Mono } from "@/components/ui/Mono";
import { sx } from "@/lib/sx";
import type { EvidenceEntry, QueueEntry, SupplierQuote } from "@/lib/types";
import { DecisionBar } from "./DecisionBar";
import { EvidenceCard } from "./EvidenceCard";
import { SupplierCompare } from "./SupplierCompare";

export function PoDetail({
  entry,
  evidence,
  quotes,
  onApprove,
  onReject,
}: {
  entry: QueueEntry;
  evidence: EvidenceEntry[];
  quotes: SupplierQuote[];
  /** 미지정이면 목업 모드 — 버튼이 아무것도 저장하지 않는다 */
  onApprove?: () => void;
  onReject?: (reason: string) => void;
}) {
  const recommended = quotes.find((q) => q.recommended) ?? quotes[0];

  return (
    <div style={sx("display:flex;flex-direction:column;padding:18px 20px")}>
      <div style={sx("display:flex;align-items:center;gap:9px;margin-bottom:14px")}>
        <span style={sx("font:700 17px 'Pretendard';color:var(--ink)")}>
          <Mono size={15}>#{entry.poId}</Mono> {entry.title}
        </span>
        <UrgencyBadge urgency={entry.urgency} size={10} />
        <StateBadge state={entry.state} size={10} />
        <div style={sx("flex:1")} />
        <span style={sx("font:11px 'JetBrains Mono',monospace;color:var(--dim2)")}>
          요청 · {entry.meta}
        </span>
      </div>

      <EvidenceCard entries={evidence} />
      <SupplierCompare quotes={quotes} />
      <DecisionBar
        supplierName={recommended?.name ?? ""}
        onApprove={onApprove}
        onReject={onReject}
      />
    </div>
  );
}
