import { sx } from "@/lib/sx";

/** 발주 카드 / 발주 보류 블록이 공유하는 껍데기. */
export function CardShell({
  children,
  accent,
}: {
  children: React.ReactNode;
  /** 좌측 강조선 (발주 보류는 오렌지) */
  accent?: "orange";
}) {
  const left = accent === "orange" ? "border-left:4px solid var(--orange);" : "";
  return (
    <div
      style={sx(
        `align-self:flex-start;width:88%;border:1px solid var(--line2);${left}` +
          "border-radius:8px;background:var(--pocard);overflow:hidden"
      )}
    >
      {children}
    </div>
  );
}

export function CardHead({
  title,
  right,
}: {
  title: React.ReactNode;
  right?: React.ReactNode;
}) {
  return (
    <div
      style={sx(
        "display:flex;justify-content:space-between;align-items:center;padding:9px 13px;" +
          "border-bottom:1px solid var(--line);background:var(--pocard-head)"
      )}
    >
      <span
        style={sx(
          "display:flex;align-items:center;gap:7px;font:700 12.5px 'Pretendard';color:var(--ink)"
        )}
      >
        {title}
      </span>
      {right}
    </div>
  );
}

export function CardFoot({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={sx(
        "display:flex;gap:8px;align-items:center;padding:11px 13px;border-top:1px solid var(--line)"
      )}
    >
      {children}
    </div>
  );
}
