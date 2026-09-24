# MaintQ Frontend

Next.js (App Router + TypeScript) 로 변환한 진단 콘솔(화면 A) · 승인 큐(화면 B) UI.
디자인 프로토타입(`MaintQ-*.dc.html`)을 1:1 로 옮긴 것으로, 아직 목업 UI 상태이며
백엔드(FastAPI · SSE)와의 연동은 TODO 로 남겨두었다.

## 실행

```bash
npm install
npm run dev            # http://localhost:3000
```

## 구조

```
frontend/
├── app/
│   ├── layout.tsx        # <html>·폰트 로드 (Pretendard · JetBrains Mono)
│   ├── globals.css       # 테마 토큰(dark/dgray/gray/light) + keyframes
│   └── page.tsx          # AppShell 마운트
├── components/
│   ├── AppShell.tsx      # 상단 앱바 · 역할 전환(정비사↔팀장) · 테마 전환 · 토스트
│   ├── ScreenA.tsx       # 진단 콘솔 (채팅 + 실행 trace, S1/S3 시나리오, 음성 입력)
│   └── ScreenB.tsx       # 승인 큐 (대기 목록 · 상세 · 공급사 비교 · 빈 상태)
└── lib/
    ├── sx.ts             # 인라인 CSS 문자열 → React style 객체 파서
    └── theme.ts          # Theme 타입 · 페이지 배경 맵 · 테마 라벨
```

## 스타일링 방식

프로토타입이 전부 인라인 스타일 + CSS 변수로 작성돼 있어, 마크업을 그대로 옮기기 위해
`lib/sx.ts` 의 `sx("padding:9px;color:var(--ink)")` 헬퍼로 CSS 문자열을 React style 객체로
변환한다. 테마 색상은 `.app-root[data-theme]` 셀렉터(globals.css)에서 CSS 변수로 스위칭.

## 컴포넌트 props

| 컴포넌트 | prop | 설명 |
|---|---|---|
| `ScreenA` | `theme` | 활성 테마 |
| | `onRequestApproval` | "팀장 승인 요청" 클릭 콜백 (draft→pending, `POST /api/po/{id}/submit` 연결 지점) |
| | `scenario` | `"s1"`(정상 파이프라인) \| `"s3"`(반복 고장) — 기본 `s1` |
| `ScreenB` | `theme` | 활성 테마 |
| | `view` | `"queue"` \| `"empty"` — 기본 `queue` |

## 백엔드 연동 TODO (docs/06_REPO_API.md 기준)

- `ScreenA` 채팅 → `POST /api/chat` SSE 구독 (token / tool_call / tool_result / block 4종)
- 실행 trace 패널 ← `tool_call`·`tool_result` 이벤트 실시간 렌더 (현재는 목업 스텝)
- 발주 카드 "팀장 승인 요청" → `POST /api/po/{id}/submit` (`X-Role: technician`)
- `ScreenB` 승인/반려 → `POST /api/po/{id}/approve` · `/reject` (`X-Role: manager`)
- 헤더 라인/장비 선택기 ← `GET /api/equipment`
```
