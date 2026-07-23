import { sx } from "@/lib/sx";

export type BannerTone = "info" | "warn" | "error";

const TONE: Record<BannerTone, string> = {
  info: "border-color:var(--cite-bd);background:var(--cite-bg);color:var(--blue-tx)",
  warn: "border-color:var(--saf-cite-bd);background:var(--saf-cite-bg);color:var(--orange-tx)",
  error: "border-color:var(--saf-bd);background:var(--saf-bg);color:var(--orange-tx)",
};

/**
 * 상태 고지 — 특히 "지금 보이는 게 실데이터가 아니다"를 숨기지 않기 위한 것.
 * 백엔드가 꺼져 있어도 화면은 뜨지만, 그걸 조용히 넘기면 데모에서 오해를 만든다.
 */
export function StatusBanner({
  tone = "info",
  children,
}: {
  tone?: BannerTone;
  children: React.ReactNode;
}) {
  return (
    <div
      style={sx(
        "width:1020px;max-width:100%;display:flex;align-items:center;gap:8px;border:1px solid;" +
          `border-radius:7px;padding:9px 13px;font:12px/1.5 'Pretendard';${TONE[tone]}`
      )}
    >
      {children}
    </div>
  );
}
