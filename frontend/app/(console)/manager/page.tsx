import { ApprovalQueueScreen } from "@/components/screens/ApprovalQueueScreen";

/**
 * /manager — 통합 승인 큐 (발주서·처분서, D85).
 * 이 라우트의 API 호출은 X-Role: manager 로 나간다.
 */
export default function ManagerPage() {
  return <ApprovalQueueScreen />;
}
