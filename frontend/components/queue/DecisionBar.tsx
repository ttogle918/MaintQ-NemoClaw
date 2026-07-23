"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { sx } from "@/lib/sx";

/**
 * 승인/반려 — 팀장 전용. `POST /api/po/{id}/approve` · `/reject` 로 간다.
 * 정비사 라우트에는 이 컴포넌트가 아예 없고, 백엔드도 X-Role 로 403 을 낸다 (이중 방어).
 *
 * 반려는 **사유가 필수**다 (D38) — 사유 없이 반려하면 요청자가 뭘 고쳐야 할지 모른다.
 * 백엔드도 422 로 막지만, 거기까지 가기 전에 UI 에서 받는다.
 */
export function DecisionBar({
  supplierName,
  onApprove,
  onReject,
}: {
  supplierName: string;
  onApprove?: () => void;
  onReject?: (reason: string) => void;
}) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const disabled = !onApprove && !onReject;

  if (rejecting) {
    return (
      <div
        style={sx(
          "display:flex;flex-direction:column;gap:9px;margin-top:auto;padding-top:14px;" +
            "border-top:1px solid var(--line)"
        )}
      >
        <label
          style={sx("font:600 11px 'JetBrains Mono',monospace;color:var(--orange-tx)")}
        >
          반려 사유 (필수)
        </label>
        <textarea
          autoFocus
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="예: 예산 초과 — 차기 분기 재검토 / 재고 있음 / 사양 불일치"
          style={sx(
            "width:100%;min-height:62px;resize:vertical;border:1px solid var(--line2);" +
              "border-radius:7px;background:var(--field);color:var(--ink);padding:9px 11px;" +
              "font:12.5px/1.5 'Pretendard'"
          )}
        />
        <div style={sx("display:flex;gap:8px;align-items:center")}>
          <span style={sx("font:11px 'Pretendard';color:var(--dim2);flex:1")}>
            사유는 요청자에게 그대로 전달되고 발주 이력에 남습니다.
          </span>
          <Button
            variant="outline"
            onClick={() => {
              setRejecting(false);
              setReason("");
            }}
          >
            취소
          </Button>
          <Button
            variant="danger"
            size="lg"
            style="border-radius:7px"
            onClick={() => {
              if (!reason.trim()) return;
              onReject?.(reason.trim());
              setRejecting(false);
              setReason("");
            }}
          >
            반려 확정
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div
      style={sx(
        "display:flex;gap:10px;align-items:center;margin-top:auto;padding-top:14px;border-top:1px solid var(--line)"
      )}
    >
      <span style={sx("font:11px/1.4 'Pretendard';color:var(--dim2);flex:1")}>
        {disabled ? (
          "목업 데이터 — 승인·반려가 저장되지 않습니다"
        ) : (
          <>
            승인 시 {supplierName} 발주서가 <b style={sx("color:var(--ink2)")}>확정</b>됩니다. 반려
            시 요청자에게 사유가 전달됩니다.
          </>
        )}
      </span>
      <Button
        variant="danger"
        size="lg"
        style="border-radius:7px"
        onClick={() => setRejecting(true)}
      >
        반려 (사유 입력)
      </Button>
      <Button size="lg" style="border-radius:7px" onClick={onApprove}>
        승인 — 발주서 확정
      </Button>
    </div>
  );
}
