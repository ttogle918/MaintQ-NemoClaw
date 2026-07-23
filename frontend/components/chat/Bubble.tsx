import { CitationRow } from "@/components/ui/CitationChip";
import type { Citation } from "@/lib/citation";
import { sx } from "@/lib/sx";

export function UserBubble({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={sx(
        "align-self:flex-end;max-width:78%;background:var(--userbub);border:1px solid var(--userbub-line);" +
          "border-radius:9px 9px 3px 9px;padding:9px 13px;font:13px/1.5 'Pretendard';color:var(--ink)"
      )}
    >
      {children}
    </div>
  );
}

/**
 * 에이전트 말풍선. 본문은 SSE `token` 이벤트가 흘러들어오는 자리고,
 * 인용은 `block`(type: citation)으로 따로 도착한다 (D22).
 */
export function AgentBubble({
  children,
  citations = [],
}: {
  children: React.ReactNode;
  citations?: Citation[];
}) {
  return (
    <div
      style={sx(
        "align-self:flex-start;max-width:86%;background:var(--aibub);border:1px solid var(--line);" +
          "border-radius:9px 9px 9px 3px;padding:11px 13px;font:13px/1.62 'Pretendard';color:var(--ink2)"
      )}
    >
      {children}
      <CitationRow citations={citations} />
    </div>
  );
}
