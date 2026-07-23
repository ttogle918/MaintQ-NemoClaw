import { ApprovalQueueScreen } from "@/components/screens/ApprovalQueueScreen";

/**
 * /manager/po/{poId} — 발주 상세 딥링크.
 * 승인 요청 알림(백로그 P3)의 착지점이자, 큐에서 항목을 고를 때의 URL 이다.
 */
export default function PoDetailPage({ params }: { params: { poId: string } }) {
  return <ApprovalQueueScreen selectedPoId={params.poId} />;
}
