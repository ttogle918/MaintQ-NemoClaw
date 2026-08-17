import { ApprovalQueueScreen } from "@/components/screens/ApprovalQueueScreen";

/**
 * /manager/repair/{repairId} — 수리 증빙 상세 딥링크.
 * 승인 큐에서 수리 항목을 고를 때의 URL 이다 (MQ-1002 후속 — Sprint 10).
 *
 * 라우트 파라미터 이름은 `repairId` 그대로다 — **이 라우트는 수리 도메인 전용**이고,
 * 발주는 `/manager/po/{id}`, 처분은 `/manager/decision/{id}` 라는 자기 라우트를 갖는다.
 * 화면 쪽 prop 만 종류 중립(`selectedId`)이다 (`po/[poId]/page.tsx`와 같은 패턴, D87).
 */
export default function RepairDetailPage({ params }: { params: { repairId: string } }) {
  return <ApprovalQueueScreen selectedId={params.repairId} />;
}
