# MaintQ Frontend

Next.js (App Router + TypeScript) 진단 콘솔(화면 A) · 승인 큐(화면 B) UI.
아직 목업 데이터로 동작하며, 백엔드(FastAPI · SSE) 연동은 M2 에서 붙인다.

## 실행

```bash
npm install
npm run dev            # http://localhost:3000 → /technician 으로 리다이렉트
```

## 라우트

역할은 **라우트가 결정한다.** 클라이언트 상태 토글로 역할을 바꾸면 "정비사 approve → 403"
(완료 기준의 권한 위반 차단 100%)을 시연할 수 없기 때문이다. 각 라우트가 고정된 `X-Role` 을 보낸다.

| 라우트 | 화면 | X-Role |
|---|---|---|
| `/` | → `/technician` 리다이렉트 | — |
| `/technician` | 진단 콘솔 (화면 A) | `technician` |
| `/technician?scenario=s3` | 반복 고장 시나리오 — 데모 촬영용 | `technician` |
| `/manager` | 승인 큐 (화면 B) | `manager` |
| `/manager/po/[poId]` | 발주 상세 딥링크 (백로그 P3 알림의 착지점) | `manager` |

## 구조

```
frontend/
├── app/
│   ├── layout.tsx              # <html> · 폰트 (Pretendard · JetBrains Mono)
│   ├── globals.css             # 테마 토큰(dark/dgray/gray/light) + keyframes
│   ├── page.tsx                # → /technician
│   └── (console)/              # 라우트 그룹 — URL 에 안 나타남
│       ├── layout.tsx          # ThemeProvider + AppBar (라우트 이동에도 테마 유지)
│       ├── technician/page.tsx
│       └── manager/
│           ├── page.tsx
│           └── po/[poId]/page.tsx
│
├── components/
│   ├── ui/                     # 프리미티브
│   │   ├── Mono.tsx            #   코드·품번·에러코드 모노스페이스
│   │   ├── Badge.tsx           #   Badge · StateBadge(4상태) · UrgencyBadge
│   │   ├── CitationChip.tsx    #   인용 칩 — block(type: citation) 대응
│   │   ├── Button.tsx          #   Button(primary/outline/danger) · IconButton
│   │   └── Chip.tsx            #   SelectChip · Divider · Avatar · Logo
│   │
│   ├── layout/                 # 셸
│   │   ├── AppBar.tsx          #   상단 앱바
│   │   ├── RoleTabs.tsx        #   역할 전환 (Link — 상태 토글 아님)
│   │   ├── ThemeSwitch.tsx
│   │   ├── ConsoleFrame.tsx    #   ConsoleFrame · ConsoleHeader · ScreenStack · Spacer
│   │   └── Toast.tsx
│   │
│   ├── chat/                   # 화면 A 좌측 — SSE 이벤트 단위로 쪼갬
│   │   ├── ChatThread.tsx      #   ChatItem[] → 렌더 디스패치
│   │   ├── Bubble.tsx          #   UserBubble · AgentBubble
│   │   ├── SafetyBlock.tsx     #   block(type: safety) 전용
│   │   ├── CardShell.tsx       #   발주 카드/보류 블록 공통 껍데기
│   │   ├── PoDraftCard.tsx     #   block(type: po_card) — "확정" 버튼 없음
│   │   ├── PoHoldCard.tsx      #   S3 발주 보류 (발주 카드 아님)
│   │   ├── RepeatFaultBanner.tsx
│   │   ├── ChatComposer.tsx
│   │   └── VoiceBar.tsx
│   │
│   ├── trace/                  # 화면 A 우측 — 시그니처 화면
│   │   ├── TracePanel.tsx      #   탭 + 세션 헤더 + 스텝 목록
│   │   └── TraceStep.tsx       #   tool_call + tool_result 한 쌍
│   │
│   ├── queue/                  # 화면 B
│   │   ├── QueueList.tsx       #   큐 리스트 + 아이템 (딥링크)
│   │   ├── PoDetail.tsx        #   상세 조립
│   │   ├── EvidenceCard.tsx    #   근거 요약 카드 (evidence JSON 소스)
│   │   ├── SupplierCompare.tsx #   공급사 비교 카드
│   │   ├── DecisionBar.tsx     #   승인/반려
│   │   ├── EmptyQueue.tsx
│   │   └── StatusLegend.tsx
│   │
│   └── screens/                # 섹션 조립 (라우트가 이걸 렌더)
│       ├── DiagnosticConsole.tsx
│       └── ApprovalQueueScreen.tsx
│
└── lib/
    ├── sx.ts                   # 인라인 CSS 문자열 → React style 객체
    ├── theme.ts                # Theme 타입 · 배경 맵 · 라벨
    ├── theme-context.tsx       # ThemeProvider · useTheme
    ├── role.ts                 # Role · 라우트↔역할 매핑 · 목업 신원
    ├── citation.ts             # Citation · citationLabel (D26·D32)
    ├── types.ts                # 도메인 타입 (PoDraft · QueueEntry · TraceStep · ChatItem …)
    ├── api.ts                  # fetch 래퍼 · SSE 리더 · 엔드포인트 표
    └── mock/                   # 목업 데이터 — M2 에서 API 응답으로 대체
        ├── scenarios.tsx       #   S1 / S3 대화
        ├── trace.ts            #   실행 로그
        └── queue.tsx           #   승인 큐 · 근거 · 견적
```

## 스타일링 방식

프로토타입이 전부 인라인 스타일 + CSS 변수로 작성돼 있어, `lib/sx.ts` 의
`sx("padding:9px;color:var(--ink)")` 헬퍼로 CSS 문자열을 React style 객체로 변환한다.
테마 색상은 `.app-root[data-theme]` 셀렉터(globals.css)에서 CSS 변수로 스위칭.

## 설계 계약 (docs/)

UI 를 고칠 때 깨면 안 되는 것들:

- **인용 페이지** — 저장·검증은 PDF 물리 페이지, 표시는 인쇄 페이지 우선 + PDF 병기 (D26·D32).
  변환은 백엔드 렌더 1곳에서만 하고 프론트는 `citationLabel()` 로 표시만 한다
- **안전 경고** — 말풍선 텍스트에 섞지 않고 `SafetyBlock` 전용 컴포넌트로, 매뉴얼 근거 필수 (D22)
- **발주 카드에 "확정" 버튼 금지** — 정비사는 승인 *요청*만, 확정은 화면 B (D10·D18)
- **S3 는 발주 카드가 아니라 발주 보류 블록** (02_SCENARIOS S3)
- **오렌지는 안전·긴급 전용** — 장식으로 새면 경고가 무감각해진다

## 백엔드 연동 TODO (M2, docs/06_REPO_API.md)

- `ChatComposer` 전송 → `POST /api/chat` → `readSse()` 로 이벤트 4종 수신
  - ⚠️ **`EventSource` 를 쓸 수 없다** — `/api/chat` 은 POST 이고 EventSource 는 GET 전용이며
    커스텀 헤더(`X-Role`·`X-User`)를 실을 수 없다. `fetch` + `ReadableStream` 으로 파싱한다
  - `block` 이벤트는 도착 즉시 `ChatItem[]` 에 push — token 사이에 끼어들어야 한다 (D22)
- `TracePanel` ← `tool_call`·`tool_result` 실시간 렌더 (현재는 `lib/mock/trace.ts`)
- 발주 카드 "팀장 승인 요청" → `POST /api/po/{id}/submit`
- `DecisionBar` → `POST /api/po/{id}/approve` · `/reject`
- 헤더 라인/장비 선택기 ← `GET /api/equipment`
- 이력 기록 액션 → `POST /api/equipment/{id}/errors` (D29) — **아직 UI 자리가 없다**
