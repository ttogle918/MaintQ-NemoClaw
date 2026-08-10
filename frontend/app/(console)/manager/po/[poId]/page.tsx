import { ApprovalQueueScreen } from "@/components/screens/ApprovalQueueScreen";

/**
 * /manager/po/{poId} — 발주 상세 딥링크.
 * 승인 요청 알림(백로그 P3)의 착지점이자, 큐에서 발주 항목을 고를 때의 URL 이다.
 *
 * 라우트 파라미터 이름은 `poId` 그대로다 — **이 라우트는 발주 도메인 전용**이고,
 * 처분서는 `/manager/decision/{id}` 라는 자기 라우트를 갖는다 (Stage 6).
 * 화면 쪽 prop 만 종류 중립(`selectedId`)이다.
 */
export default function PoDetailPage({ params }: { params: { poId: string } }) {
  return <ApprovalQueueScreen selectedId={params.poId} />;
}
