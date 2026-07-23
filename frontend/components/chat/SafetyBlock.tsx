import { CitationChip } from "@/components/ui/CitationChip";
import type { Citation } from "@/lib/citation";
import { sx } from "@/lib/sx";

/**
 * 안전 경고 — SSE `block` 이벤트 (type: safety) 전용 컴포넌트 (D22).
 *
 * 일반 말풍선과 확실히 구분돼야 하고(오렌지 좌측 굵은 테두리), 텍스트 스트림 중간에
 * 삽입되므로 위험 절차 서술보다 먼저/함께 도착한다.
 * 안전 문구는 매뉴얼 근거 없이 생성 금지 — citation 이 required 인 이유다.
 */
export function SafetyBlock({
  title,
  children,
  citation,
}: {
  title: string;
  children: React.ReactNode;
  citation: Citation;
}) {
  return (
    <div
      style={sx(
        "align-self:flex-start;max-width:88%;border:1px solid var(--saf-bd);border-left:4px solid var(--saf-bd);" +
          "border-radius:7px;background:var(--saf-bg);padding:11px 13px"
      )}
    >
      <div style={sx("display:flex;align-items:center;gap:7px;margin-bottom:6px")}>
        <span style={sx("font-size:13px")}>⚠</span>
        <span
          style={sx(
            "font:700 11px 'JetBrains Mono',monospace;letter-spacing:.06em;color:var(--orange-tx)"
          )}
        >
          {title}
        </span>
      </div>
      <div style={sx("font:13px/1.6 'Pretendard';color:var(--saf-tx)")}>{children}</div>
      <div style={sx("margin-top:8px")}>
        <CitationChip citation={citation} tone="safety" />
      </div>
    </div>
  );
}
