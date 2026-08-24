"use client";

import { AppBar } from "@/components/layout/AppBar";
import { ChatFab } from "@/components/layout/ChatFab";
import { PENDING_COUNT } from "@/lib/mock/queue";
import { sx } from "@/lib/sx";
import { ThemeProvider, useTheme } from "@/lib/theme-context";

/**
 * 콘솔 셸 — /technician 과 /manager 가 공유한다.
 * 라우트 그룹 `(console)` 은 URL 에 나타나지 않는다.
 *
 * 레이아웃은 라우트 이동 시 리마운트되지 않으므로 선택한 테마가 그대로 유지된다.
 */
export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <Shell>{children}</Shell>
    </ThemeProvider>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const { theme } = useTheme();

  return (
    <div
      className="app-root"
      data-theme={theme}
      style={sx("min-height:100vh;background:var(--page);transition:background .2s")}
    >
      <AppBar pendingCount={PENDING_COUNT} />
      <ChatFab />
      <div style={sx("padding:26px 24px 60px")}>{children}</div>
    </div>
  );
}
