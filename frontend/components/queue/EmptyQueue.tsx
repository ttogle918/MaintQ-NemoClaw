import { sx } from "@/lib/sx";

export function EmptyQueue() {
  return (
    <div
      style={sx(
        "min-height:560px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;padding:40px"
      )}
    >
      <div
        style={sx(
          "width:66px;height:66px;border-radius:14px;border:2px solid var(--ok-bd);background:var(--ok-bg);" +
            "display:flex;align-items:center;justify-content:center;font-size:28px;color:var(--ok-tx)"
        )}
      >
        ✓
      </div>
      <div style={sx("font:700 17px 'Pretendard';color:var(--ink)")}>승인 대기 없음</div>
      <div
        style={sx(
          "font:13px/1.6 'Pretendard';color:var(--dim);text-align:center;max-width:340px"
        )}
      >
        모든 발주 요청이 처리되었습니다. 새 발주 요청이 오면 여기에 표시됩니다.
      </div>
      <div style={sx("display:flex;gap:8px;margin-top:4px")}>
        <span
          style={sx(
            "font:11px 'JetBrains Mono',monospace;color:var(--dim2);border:1px solid var(--line2);border-radius:14px;padding:5px 12px"
          )}
        >
          오늘 승인 4 · 반려 1
        </span>
      </div>
    </div>
  );
}
