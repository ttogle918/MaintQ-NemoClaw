import { sx } from "@/lib/sx";

/** 화면 A/B 공통 콘솔 프레임 — 1020px 고정, 데스크톱 우선 (08_DESIGN_BRIEF). */
export function ConsoleFrame({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={sx(
        "width:1020px;max-width:100%;background:var(--surface);border:1px solid var(--line);" +
          "border-radius:8px;overflow:hidden;box-shadow:0 10px 40px rgba(0,0,0,.28)"
      )}
    >
      {children}
    </div>
  );
}

/** 콘솔 내부 상단 바 (장비 선택기 / 승인 대기 카운트가 들어가는 자리). */
export function ConsoleHeader({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={sx(
        "display:flex;align-items:center;gap:10px;padding:11px 16px;border-bottom:1px solid var(--line);background:var(--head)"
      )}
    >
      {children}
    </div>
  );
}

export function Spacer() {
  return <div style={sx("flex:1")} />;
}

/** 콘솔 + 하단 부속(범례 등)을 세로로 쌓는 화면 컨테이너. */
export function ScreenStack({ children }: { children: React.ReactNode }) {
  return (
    <div style={sx("display:flex;flex-direction:column;align-items:center;gap:18px")}>
      {children}
    </div>
  );
}
