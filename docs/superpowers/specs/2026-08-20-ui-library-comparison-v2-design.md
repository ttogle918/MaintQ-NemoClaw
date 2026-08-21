# UI 라이브러리 비교판 (P40) — MUI + animata.design v2 화면 — 설계

**작성일**: 2026-08-20 · **브레인스토밍 세션**: 같은 날 대화(P41 부서 분리 완료 직후) · **상태**: 사용자 승인 완료

## 0. 배경

백로그 `P40`(2026-08-20 신설)이 요청한 작업이다 — 요청 원문: *"v2 에 같은 화면 만들어서 기존 화면이랑 비교만 해보고 싶어"*, 참고 예시로 `https://animata.design/docs/widget/security-alert` 를 들었다.

착수 전 실측(P40 백로그 항목)이 이미 확인해 둔 제약: 지금 프론트 런타임 의존성은 `next`·`react`·`react-dom` **3개뿐**이고 스타일은 `frontend/app/globals.css` 한 파일로 손수 짠 것이다. 즉 이 작업은 "라이브러리 교체"가 아니라 **스타일 시스템 신규 도입**이다.

### 0-1. 브레인스토밍 중 정정된 것 — 애초 프레이밍은 3-way 비교였다

최초 질문("MUI+animata 를 한 화면에 같이 쓰나요, 별도로 만들어 비교하나요?")에 사용자가 "별도 2버전"을 골라 기존/MUI/animata **3-way 비교**로 설계를 진행했으나, 이후 라우팅 질문 중 사용자가 정정했다 — *"mui 버전 + animate 버전(쓸만한거 있으면 추가) 의미였어. 각각에 대해서 말한게 아니"*. 즉 실제 요구는 **MUI 를 기본 구조로 하고 animata 컴포넌트를 쓸만한 데 골라 얹은 v2 화면 하나**이지, 라이브러리별로 독립된 3개 화면이 아니다. 이 정정에 따라 이후 질문(스테이지 순서 등)도 다시 확인했다.

## 1. 범위

### 포함
- `/manager/po/[poId]` 가 렌더하는 `ApprovalQueueScreen` 의 동작을 **그대로 재현**: 큐 리스트(대기·최근) + 클릭 시 발주(po)·처분(disposal)·수리증빙(repair) 상세가 **인라인**으로 전환
- **실제 백엔드 API 연동** — 승인/반려 버튼이 실제 상태를 바꾼다(목업 아님)
- **라이브러리 기본 미관** — MUI Material Design 기본값, animata 기본 테마를 그대로 쓴다. 기존 MaintQ 색상 토큰(오렌지 `#E8590C`·딥블루 `#1C5D99`·Pretendard)에 맞추지 않는다
- 새 라우트 하나: `/v2/manager/po/[poId]`

### 제외 (명시)
- `/manager/decision/[decisionId]` 같은 **독립 서명 페이지**는 재현하지 않는다 — 그 페이지는 `ApprovalQueueScreen` 을 안 쓰는 별도 패턴(목업 폴백 없음, D65·D87 안전상 이유)이라 스코프 밖. po/disposal/repair 상세는 **큐 안 인라인 전환**으로만 본다
- 기존 v1 화면·컴포넌트·라우트는 **전부 무변경**
- MUI·animata 를 각각 독립 URL로 나눠 3-way 비교하는 구조는 **하지 않는다** (§0-1 정정)
- animata 의 구체적 컴포넌트 목록은 이 스펙에서 확정하지 않는다 — Cloudflare 가 `animata.design` 을 WebFetch 로 막아(이 세션에서 두 URL 모두 403 확인) 카탈로그를 못 봤다. **Stage 2 착수 시 claude-in-chrome(사용자 브라우저 세션)으로 확인 후 선정**한다

## 2. 라우팅

| | 값 |
|---|---|
| URL | `/v2/manager/po/[poId]` |
| 파일 위치 | `frontend/app/v2/manager/po/[poId]/page.tsx` |

Next.js 라우트 그룹 `(console)` 은 URL 세그먼트로 나타나지 않으므로, `(console)` 안에 둬도 URL 은 `/v2/manager/po/[poId]` 가 된다 — **그러나 계획(writing-plans) 단계에서 이 결정을 뒤집었다.**

🔴 **정정 (계획 단계, 2026-08-20)** — 실측하니 `app/(console)/layout.tsx` 가 이미 `/manager`·`/technician` 전체를 감싸는 **기존 AppBar + 테마 컨텍스트**를 갖고 있었다. Next.js 는 하위 라우트가 상위 레이아웃을 생략할 방법이 없다 — `app/(console)/v2/…` 에 두면 D87 글롭은 자동으로 걸리지만 **v2 화면 위에 v1 AppBar 가 강제로 씌워져** "라이브러리 기본 미관 비교"라는 목적과 어긋난다.

**해결책**: `app/v2/…` (완전히 밖, `(console)` 형제 경로)로 두고, 대신 `spikes/ui_honesty_contract.py` 의 `L2_GLOBS` 에 **`"app/v2/**/*.tsx"` 를 새 글롭으로 추가**한다 — Sprint 10 이 `app/(console)/**` 를 세 번째 글롭으로 더한 것과 같은 방식(스파이크 상단 주석 선례). 결과는 동일(D87 자동 적용)하면서 레이아웃은 완전히 격리되고, URL 도 그대로다. 사용자 확인 완료.

## 3. 데이터·로직 재사용

### 3-1. 결정 — v2 전용 얇은 오케스트레이션 훅 신설 (대안 기각)

| | 채택: v2 전용 훅 신설 | 기각: 기존 화면에서 훅 추출·공유 |
|---|---|---|
| 방식 | `lib/api.ts`·`lib/mappers.tsx`·`lib/types.ts`·`lib/queueState.ts` 는 **그대로 재사용**. fetch+승인/반려 오케스트레이션만 v2 전용으로 새로 작성 | `ApprovalQueueScreen.tsx` 내부 로직을 훅으로 뽑아 v1·v2 가 공유 |
| 장점 | v1 파일을 한 글자도 안 건드린다 — "기존 화면 무변경"이 코드로 보증됨 | 오케스트레이션 로직 중복 0 |
| 단점 | 승인/반려 흐름이 개념적으로 중복(~100줄) — 백엔드 계약이 바뀌면 두 곳 손봐야 함 | 기존 화면 파일을 건드리는 리스크 — "안 바꾼다"는 전제와 정면 충돌 |

**채택 근거**: 데이터 계층(`api.ts`·`mappers.tsx`·`types.ts`)은 100% 공유되므로 실질 중복은 상태 관리 글루 코드뿐이다. v1 무변경을 코드로 보증하는 쪽이 안전 마진이 크다.

새 파일: `frontend/lib/v2/useApprovalQueueV2.ts` — `ApprovalQueueScreen.tsx` 의 `load()`/`decide()` 오케스트레이션과 같은 모양(같은 API 호출·같은 매퍼)이되 독립 구현.

### 3-2. 컴포넌트 구조

새 디렉터리 `frontend/components/v2/`(MUI 기반)에 기존 대응물을 재현한다:

```
QueueListV2        (MUI List/Table)         ↔ components/queue/QueueList.tsx
PoDetailV2          (MUI Card + Chip)        ↔ components/queue/PoDetail.tsx
DecisionDetailV2                             ↔ components/queue/DecisionDetail.tsx
RepairDetailV2                               ↔ components/queue/RepairDetail.tsx
EvidenceCardV2                               ↔ components/queue/EvidenceCard.tsx
SupplierCompareV2   (MUI Table)              ↔ components/queue/SupplierCompare.tsx
DecisionBarV2        (MUI Button)            ↔ components/queue/DecisionBar.tsx
```

배지·상태 표시는 MUI `Chip`/`Alert` 로 옮기되, **상태→표시 매핑은 `frontend/lib/queueState.ts`·`mappers.tsx` 를 그대로 호출**한다(D87 — 전역 total 맵 1곳 규약, 라이브러리를 바꿔도 매핑 계층은 재사용).

## 4. 스타일 격리 (3중 시스템 공존)

### 4-1. MUI (Stage 1)

신규 의존성: `@mui/material` · `@emotion/react` · `@emotion/styled` · `@mui/material-nextjs`(App Router 용 Emotion 캐시 프로바이더).

`frontend/app/v2/layout.tsx` 신설 — `AppRouterCacheProvider` + `ThemeProvider(createTheme())` 로 감싼다. 테마는 **MUI 기본값 그대로**(§1 라이브러리 기본 미관 결정). 이 레이아웃은 `v2` 서브트리에만 적용되므로 나머지 앱은 영향 없음.

### 4-2. animata (Stage 2)

신규 의존성: `tailwindcss` · `postcss` · `autoprefixer` · `framer-motion`.

`tailwind.config.js` 의 `content` 를 `app/v2/**/*.{ts,tsx}` (+ `components/v2/**/*.{ts,tsx}`)로 좁혀 유틸리티 클래스 생성이 나머지 앱 파일을 스캔하지 않게 한다.

🔴 **리스크 — Tailwind `@tailwind base`(preflight) 전역 유출.** Tailwind 의 리셋 CSS 는 스코프 개념이 없어, 잘못 임포트하면 버튼·폼 기본 스타일이 앱 전체에서 깨질 수 있다. 대응:
- Tailwind 스타일시트는 **`v2/layout.tsx` 에서만 임포트**한다(전역 `app/globals.css`·루트 `layout.tsx` 에는 손대지 않는다)
- Next.js 는 non-root 레이아웃에서 임포트한 CSS 를 그 라우트 번들에 스코프하지만, **실측으로 확인이 필요하다** — Stage 2 착수 시 v1 화면(`/manager`·`/technician` 등) 스크린샷을 Stage 1 완료 시점과 대조해 리셋 유출이 없는지 확인한다. 유출되면 Tailwind 를 CSS Modules 처럼 클래스 프리픽스로 격리하거나 `important` 스코프 셀렉터(`important: '#v2-root'`) 로 우회한다

## 5. 스테이지 계획

| Stage | 내용 |
|---|---|
| **1** | MUI 설치·격리(`v2/layout.tsx`) + `useApprovalQueueV2` 훅 + `QueueListV2`·`PoDetailV2`·`DecisionDetailV2`·`RepairDetailV2` 등 전 구성요소를 MUI 컴포넌트로 + 실 API 연동. reviewer 게이트 통과까지 |
| **2** | Tailwind·framer-motion 설치·격리 + claude-in-chrome 으로 animata.design 카탈로그 확인 + 적합한 지점 선정·교체(예: 애니메이션 트랜지션, 배너/알림 스타일 등 — 확정은 착수 시) + v1 화면 스타일 유출 없음 실측 확인 + 회귀 |

## 6. 회귀·검증 영향

| 항목 | 영향 |
|---|---|
| `spikes/ui_honesty_contract.py` | `L2_GLOBS` 에 `"app/v2/**/*.tsx"` **와** `"components/v2/*.tsx"` **2개를 새 글롭으로 추가**해야 걸린다(자동 아님 — §2 정정 참조). 추가하면 새 컴포넌트마다 L2 검사 6건씩 늘어난다. D87 준수 필수(상태→표시는 매핑 계층만 경유) |
| 프론트 라우트 기준선 | 18 → **19** (`CLAUDE.md` 갱신 대상) |
| `tsc --noEmit` · `next build` | 클린 유지 필수 — MUI·Tailwind 최초 도입이라 설정 이슈 가능성 있음, Stage 별로 확인 |
| 기존 v1 파일 | 무변경이지만 Tailwind preflight 격리는 §4-2 대로 **실측 확인** 필요 |
| `package.json` | 이 프로젝트 최초로 런타임 의존성이 `next/react/react-dom` 밖으로 늘어난다 |

## 7. 알려진 리스크 (숨기지 않고 적는다)

- **같은 DB 를 공유한다** — v2 의 승인/반려 버튼은 실제 백엔드를 호출하므로 v1 화면과 **같은 개발 DB 의 같은 레코드**를 건드린다. v2 로 테스트 승인하면 v1 화면에서도 그 상태로 보인다. 자동 회귀는 임시 DB 사본을 쓰므로 영향 없음 — **수동 데모 테스트에서만 해당**하는 캐비어트
- **animata 컴포넌트 미확정** — §1 제외 항목 참조. Stage 2 착수 시 확정
- **소비자가 없다** — 이 화면은 비교·평가 목적이고 v1 을 대체할 계획이 없다. Stage 2 완료 후에도 아무 프로덕션 경로가 이 라우트를 링크하지 않는다(직접 URL 접근만 가능). 백로그 P40 에 이미 명시된 성격이라 새로 숨기는 사실은 아니다
