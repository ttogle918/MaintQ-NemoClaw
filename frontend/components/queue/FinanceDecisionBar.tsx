"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { sx } from "@/lib/sx";
import { RejectPanel } from "./DecisionBar";

/**
 * 재무 승인/반려 — 재무부 전용. `POST /api/po/{id}/finance-approve` · `/finance-reject` 로 간다.
 *
 * `DecisionBar`(팀장 승인)와 구조는 같지만 사건이 다르다 — 팀장 승인은 발주서 **확정**이고
 * 이 컴포넌트는 그 다음 단계인 **출금 요청 전송**이다(D63 — 두 사건을 한 버튼으로 뭉개지 않는다).
 *
 * `canAct=false`(재무부 소속이 아닌 신원으로 보고 있는 경우)면 반려 패널로 전환하는 상태를
 * 아예 만들지 않고 안내문 하나만 렌더한다 — 권한이 없는데도 반려 사유 입력창이 뜨는 것
 * 자체가 오해를 부른다.
 */
export function FinanceDecisionBar({
  supplierName,
  canAct,
  onApprove,
  onReject,
}: {
  supplierName: string;
  /** false 면 승인/반려 버튼 대신 "재무부 소속만 처리 가능" 안내만 보여준다 */
  canAct: boolean;
  onApprove?: () => void;
  onReject?: (reason: string) => void;
}) {
  const [rejecting, setRejecting] = useState(false);

  if (!canAct) {
    return (
      <div
        style={sx(
          "display:flex;align-items:center;margin-top:auto;padding-top:14px;" +
            "border-top:1px solid var(--line)"
        )}
      >
        <span style={sx("font:11px/1.4 'Pretendard';color:var(--dim2)")}>
          재무 승인 대기 중 — 재무부 소속 담당자만 승인/반려할 수 있습니다.
          (상단 신원 전환에서 &quot;재무담당 · 최OO&quot; 선택)
        </span>
      </div>
    );
  }

  const disabled = !onApprove && !onReject;

  if (rejecting) {
    return (
      <RejectPanel
        label="반려 사유 (필수)"
        placeholder="예: 예산 부족 — 차기 분기 재검토 / 지출 항목 불명확 / 증빙 미비"
        hint="사유는 요청자에게 그대로 전달되고 발주 이력에 남습니다."
        confirmLabel="반려 확정"
        onCancel={() => setRejecting(false)}
        onConfirm={(reason) => {
          onReject?.(reason);
          setRejecting(false);
        }}
      />
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
            승인 시 {supplierName} 건에 대한 <b style={sx("color:var(--ink2)")}>출금 요청</b>이
            전송됩니다. 반려 시 요청자에게 사유가 전달됩니다.
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
        재무 승인 — 출금 요청 전송
      </Button>
    </div>
  );
}
