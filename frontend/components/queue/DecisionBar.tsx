"use client";

import { Button } from "@/components/ui/Button";
import { sx } from "@/lib/sx";

/**
 * 승인/반려 — 팀장 전용. `POST /api/po/{id}/approve` · `/reject` 로 간다.
 * 정비사 라우트에는 이 컴포넌트가 아예 없고, 백엔드도 X-Role 로 403 을 낸다 (이중 방어).
 */
export function DecisionBar({
  supplierName,
  onApprove,
  onReject,
}: {
  supplierName: string;
  onApprove?: () => void;
  onReject?: () => void;
}) {
  return (
    <div
      style={sx(
        "display:flex;gap:10px;align-items:center;margin-top:auto;padding-top:14px;border-top:1px solid var(--line)"
      )}
    >
      <span style={sx("font:11px/1.4 'Pretendard';color:var(--dim2);flex:1")}>
        승인 시 {supplierName} 발주서가 <b style={sx("color:var(--ink2)")}>확정</b>됩니다. 반려 시
        요청자에게 사유가 전달됩니다.
      </span>
      <Button variant="danger" size="lg" onClick={onReject} style="border-radius:7px">
        반려 (사유 입력)
      </Button>
      <Button size="lg" onClick={onApprove} style="border-radius:7px">
        승인 — 발주서 확정
      </Button>
    </div>
  );
}
