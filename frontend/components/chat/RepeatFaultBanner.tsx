import { sx } from "@/lib/sx";

/**
 * 반복 고장 감지 배너 (S3).
 * block 이벤트가 아니라 `get_error_history` 의 tool_result(repeated=true)에서 파생되는 UI 요소다.
 */
export function RepeatFaultBanner({
  badge,
  children,
}: {
  badge: string;
  children: React.ReactNode;
}) {
  return (
    <div
      style={sx(
        "align-self:flex-start;max-width:88%;display:flex;align-items:center;gap:9px;" +
          "border:1px solid var(--line2);border-radius:7px;background:var(--raise);padding:9px 12px"
      )}
    >
      <span
        style={sx(
          "width:22px;height:22px;flex-shrink:0;border-radius:5px;background:var(--cite-bg);" +
            "border:1px solid var(--cite-bd);display:flex;align-items:center;justify-content:center;" +
            "font:700 11px 'JetBrains Mono';color:var(--blue-tx)"
        )}
      >
        {badge}
      </span>
      <span style={sx("font:12px/1.5 'Pretendard';color:var(--ink2)")}>{children}</span>
    </div>
  );
}
