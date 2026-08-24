import { ApprovalQueueScreen } from "@/components/screens/ApprovalQueueScreen";

/**
 * /manager/finance — 재무담당 전용 랜딩 (계정 선택 화면이 재무담당을 여기로 보낸다).
 *
 * `/manager`와 같은 화면·같은 데이터를 재사용하되(`ApprovalQueueScreen focus="finance"`)
 * 일반 승인 대기 섹션을 숨기고 재무 승인 대기를 기본으로 연다 — 재무담당이 여기 들어오면
 * 자기 일이 바로 보이게 하려는 UI 편의다. **진짜 권한 경계는 여전히 백엔드**다 — 이 라우트가
 * 접근을 막지 않아도 `finance-approve`/`finance-reject`는 department 가 아니면 403(D119).
 * 이 라우트의 API 호출도 X-Role: manager 로 나간다(role 은 여전히 manager, department 만 다름).
 */
export default function ManagerFinancePage() {
  return <ApprovalQueueScreen focus="finance" />;
}
