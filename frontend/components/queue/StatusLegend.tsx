import { StateBadge } from "@/components/ui/Badge";
import { sx } from "@/lib/sx";
import type { PoState } from "@/lib/types";

const LEGEND: { state: PoState; desc: string }[] = [
  { state: "draft", desc: "정비사 작성 중" },
  { state: "pending", desc: "승인 대기" },
  { state: "approved", desc: "팀장 승인 — 재무 승인 대기 (D119)" },
  { state: "finance_approved", desc: "재무 승인 완료 — 발주 확정" },
  { state: "finance_rejected", desc: "재무 반려" },
  { state: "rejected", desc: "반려" },
];

/**
 * 상태 전이 다이어그램(06_REPO_API §2.4)의 UI 대응 범례.
 * **발주 어휘 전용**이다 — 처분(`signed`)은 다른 전이이고, 그 범례는 Stage 6 이 붙인다.
 */
export function StatusLegend() {
  return (
    <div
      style={sx(
        "width:1020px;max-width:100%;display:flex;align-items:center;gap:18px;flex-wrap:wrap;" +
          "font:11px 'Pretendard';color:var(--dim2)"
      )}
    >
      <span style={sx("font-weight:600;color:var(--dim)")}>승인 워크플로우 상태</span>
      {LEGEND.map(({ state, desc }) => (
        <span key={state} style={sx("display:inline-flex;align-items:center;gap:5px")}>
          <StateBadge kind="po" state={state} />
          {desc}
        </span>
      ))}
    </div>
  );
}
