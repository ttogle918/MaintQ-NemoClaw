import { A2aHistoryScreen } from "@/components/screens/A2aHistoryScreen";

/**
 * `/manager/a2a` — 통합 A2A 이력 (request-withdrawal·lookup-clause·assess-loan, D114, MQ-1610).
 * 이 라우트의 API 호출은 X-Role: manager 로 나간다.
 */
export default function ManagerA2aPage() {
  return <A2aHistoryScreen />;
}
