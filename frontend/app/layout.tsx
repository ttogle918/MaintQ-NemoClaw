import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MaintQ · 설비보전 AI 콘솔",
  description: "설비 진단부터 부품 발주까지 — 제조 현장 AI 보전 에이전트",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // ⛔ 여기에 `<head>` 를 직접 쓰지 말 것. Netlify 는 모든 HTML 의 `<head>` 에 홍보 주석과 줄바꿈을
    // 끼워 넣는데(끄는 설정 없음), React 가 우리가 쓴 head 자식을 맞춰 보다 그 노드를 만나 하이드레이션에
    // 실패한다(#418·#423). 대부분은 클라이언트 재렌더로 복구되지만 가끔 #329 로 빠져 화면이 목업에
    // 멈췄다 — 배포판 직접 진입 시 약 1/7(2026-09-28 실측, 로컬에 같은 주석을 주입해 재현).
    // 폰트 링크는 `<body>` 맨 앞에 둔다: 내용보다 먼저 파싱되고, head 에는 React 가 맞출 우리 노드가 없다.
    <html lang="ko">
      <body>
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css"
        />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap"
          rel="stylesheet"
        />
        {children}
      </body>
    </html>
  );
}
