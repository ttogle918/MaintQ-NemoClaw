import { ApprovalQueueScreen } from "@/components/screens/ApprovalQueueScreen";

/**
 * /manager/decision/{decisionId} — 처분 상세 딥링크.
 *
 * ⚠ **Stage 5(MQ-709a)의 최소 스텁이다.** 화면은 `ApprovalQueueScreen` 의 큐 + 안내 패널만
 * 보여 주고, 처분 상세·서명 UI(`DecisionDetail`·`SignBar`)는 **Stage 6(MQ-709b)** 이 붙인다.
 *
 * 왜 스텁을 지금 두는가 — `queueState.detailHref()` 가 `disposal` 을 이 경로로 보내기
 * 때문이다. 라우트가 없으면 큐에서 처분서를 누르는 순간 **404** 가 뜬다. 그건
 * `frontend/README §설계 계약`·D87 이 막으려는 것과 같은 유형이다: 항목은 목록에 보이는데
 * 누르면 "그런 건 없다"가 되어 **사실을 감춘다**. 빈 링크(`href=""`)를 준 것과 다르지 않다.
 *
 * 🔴 **MQ-709b 인계**: 이 파일을 **통째로 교체**해라. `params.decisionId` 를 `getDecision()` 으로
 * 읽어 `DecisionDetail` 을 렌더하고, 서명은 `SignBar` 가 맡는다. 아래 위임은 그때 사라진다.
 */
export default function DecisionDetailPage({ params }: { params: { decisionId: string } }) {
  return <ApprovalQueueScreen selectedId={params.decisionId} />;
}
