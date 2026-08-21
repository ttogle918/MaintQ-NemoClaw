"use client";

import { AppRouterCacheProvider } from "@mui/material-nextjs/v13-appRouter";
import { ThemeProvider, createTheme } from "@mui/material/styles";

/**
 * v2 전용 레이아웃 — MUI 스타일 시스템을 이 서브트리에만 격리한다.
 *
 * `app/(console)/layout.tsx` 를 쓰지 않는다 — 그 레이아웃은 v1 AppBar·테마 컨텍스트를
 * 강제로 씌운다(Next.js 는 하위 라우트가 상위 레이아웃을 생략할 수 없다). v2 는
 * `(console)` 밖의 완전히 새 트리라서 이 문제가 없다 (설계 spec §2 정정, 계획 단계 실측).
 *
 * `<CssBaseline />` 을 일부러 안 쓴다 — 그건 `html`/`body` 전역 셀렉터로 리셋을
 * 주입해서 v1 화면까지 새 나간다. MUI 컴포넌트 자체 스타일(emotion 이 생성하는
 * 클래스)은 DOM 노드에 스코프되므로 안전하다.
 *
 * 테마는 라이브러리 기본값 그대로다(색상 오버라이드 없음) — 설계 spec §1 "라이브러리
 * 기본 미관" 결정.
 */
const theme = createTheme();

export default function V2Layout({ children }: { children: React.ReactNode }) {
  return (
    <AppRouterCacheProvider options={{ key: "mui-vtwo" }}>
      <ThemeProvider theme={theme}>{children}</ThemeProvider>
    </AppRouterCacheProvider>
  );
}
