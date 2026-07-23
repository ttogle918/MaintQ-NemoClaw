"use client";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Mono } from "@/components/ui/Mono";
import { sx } from "@/lib/sx";
import type { PoDraft } from "@/lib/types";
import { CardShell, CardHead, CardFoot } from "./CardShell";

/**
 * 발주서 초안 카드 — SSE `block` 이벤트 (type: po_card) 전용 컴포넌트 (D22).
 *
 * ⚠️ "확정" 류 버튼을 절대 두지 않는다. 정비사가 할 수 있는 건 승인 **요청**뿐이고
 * 확정은 팀장 승인 큐에서만 일어난다 (D10 · D18).
 */
export function PoDraftCard({
  po,
  onRequestApproval,
}: {
  po: PoDraft;
  onRequestApproval?: (poId: string) => void;
}) {
  return (
    <CardShell>
      <CardHead
        title={
          <>
            발주서 초안 <Mono>#{po.poId}</Mono>
          </>
        }
        right={<Badge size={9.5}>DRAFT</Badge>}
      />

      <div
        style={sx(
          "display:grid;grid-template-columns:1fr 1fr;gap:9px 14px;padding:12px 13px;font:12px 'Pretendard'"
        )}
      >
        <Field label="품목">
          {po.partName} <Mono size={11}>{po.partNo}</Mono>
        </Field>
        <Field label="수량">
          {po.qty} EA{" "}
          {po.qtyNote && (
            <span style={sx("color:var(--orange-tx);font-size:11px")}>· {po.qtyNote}</span>
          )}
        </Field>
        <Field label="공급사">
          {po.supplierName} · 리드타임 {po.leadDays}일
        </Field>
        <Field label="단가">
          <Mono>₩{po.unitPrice.toLocaleString()}</Mono>
        </Field>
      </div>

      <CardFoot>
        <Button onClick={() => onRequestApproval?.(po.poId)}>팀장 승인 요청</Button>
        <Button variant="outline">수정</Button>
      </CardFoot>
    </CardShell>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <span style={sx("color:var(--dim2)")}>{label}</span>
      <br />
      <span style={sx("color:var(--ink)")}>{children}</span>
    </div>
  );
}
