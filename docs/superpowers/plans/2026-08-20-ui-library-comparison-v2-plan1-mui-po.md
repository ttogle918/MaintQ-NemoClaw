# P40 v2 MUI 발주 상세 (Plan 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/v2/manager/po/[poId]` 라우트에 MUI 로 재구현한 발주 승인 큐(목록 + 발주 상세 + 실제 승인/반려)를 만든다 — 기존 v1(`/manager/po/[poId]`)은 한 글자도 건드리지 않는다.

**Architecture:** `app/v2/`(`(console)` 밖의 새 최상위 트리)에 MUI `ThemeProvider`+`AppRouterCacheProvider` 를 두는 자체 레이아웃을 만들고, 그 안에 v2 전용 오케스트레이션 훅(`lib/v2/useApprovalQueueV2.ts`)이 기존 `lib/api.ts`·`lib/mappers.tsx`·`lib/queueState.ts` 를 그대로 호출해 데이터를 가져온다. 화면은 `components/v2/` 아래 5개 MUI 컴포넌트로 재현한다.

**Tech Stack:** Next.js 14.2.5 App Router(기존) + `@mui/material` 9.x + `@emotion/react`/`@emotion/styled`/`@emotion/cache` + `@mui/material-nextjs`(App Router Emotion 캐시). Backend 는 기존 FastAPI(`:8003`) 그대로 — 새 엔드포인트 없음.

## Global Constraints

- 기존 v1 파일(`frontend/components/queue/*`·`frontend/components/screens/ApprovalQueueScreen.tsx`·`frontend/app/(console)/**`·`frontend/lib/api.ts`·`frontend/lib/mappers.tsx`·`frontend/lib/queueState.ts`·`frontend/lib/types.ts`)은 **읽기만 한다 — 절대 수정하지 않는다** (설계 spec §3-1)
- 데이터·매핑 로직(`lib/api.ts`·`lib/mappers.tsx`·`lib/queueState.ts`·`lib/types.ts`)은 **재사용만** 한다 — v2 전용 사본을 만들지 않는다
- 상태(`state`)·판정 어휘는 **직접 문자열 비교하지 않는다** — 반드시 `stateView()`/`kindView()`(`lib/queueState.ts`)를 거친다 (D87, `spikes/ui_honesty_contract.py` L2 가 자동 검사)
- MUI 는 **라이브러리 기본 테마 그대로** 쓴다 — `createTheme()` 에 색상 오버라이드를 넣지 않는다 (설계 spec §1)
- `<CssBaseline />` 을 쓰지 않는다 — `html`/`body` 전역 셀렉터로 리셋이 v1 화면까지 새 나간다
- 라우트는 `app/v2/manager/po/[poId]/page.tsx` 하나뿐이다 — `app/(console)/v2/...` 가 아니다(레이아웃 격리를 위한 정정, 설계 spec §2)
- 이 플랜은 **po 종류만** 다룬다. disposal·repair 상세는 후속 플랜(Plan 2)이 담당 — 큐 목록에는 섞여 뜨되 선택하면 "아직 없음" 안내로 처리한다

---

## File Structure

| 파일 | 상태 | 책임 |
|---|---|---|
| `frontend/package.json` | 수정 | MUI+Emotion 의존성 5개 추가 |
| `frontend/app/v2/layout.tsx` | 신설 | MUI Emotion 캐시 + 테마 프로바이더 (v2 서브트리 전용) |
| `frontend/app/v2/manager/po/[poId]/page.tsx` | 신설 | 라우트 페이지 — 훅 호출 + 레이아웃 조립 |
| `frontend/lib/v2/useApprovalQueueV2.ts` | 신설 | 데이터 페칭 + 승인/반려 오케스트레이션 (순수 로직, JSX 없음) |
| `frontend/components/v2/QueueListV2.tsx` | 신설 | 큐 목록 (MUI List) — 클릭 시 로컬 상태 전환 |
| `frontend/components/v2/EvidenceCardV2.tsx` | 신설 | 근거 요약 카드 |
| `frontend/components/v2/SupplierCompareV2.tsx` | 신설 | 공급사 비교 카드 2열 |
| `frontend/components/v2/DecisionBarV2.tsx` | 신설 | 승인/반려 바 + 반려 사유 입력 |
| `frontend/components/v2/PoDetailV2.tsx` | 신설 | 위 3개를 조립하는 발주 상세 컨테이너 |
| `spikes/ui_honesty_contract.py` | 수정 | `L2_GLOBS` 에 `app/v2/**/*.tsx`·`components/v2/*.tsx` 추가, `L2_FILES_FLOOR` 갱신 |
| `CLAUDE.md` | 수정 | 프론트 라우트 기준선 18→19, 회귀 건수 갱신 |

---

### Task 1: MUI 의존성 설치

**Files:**
- Modify: `frontend/package.json`

**Interfaces:**
- Produces: `@mui/material`·`@emotion/react`·`@emotion/styled`·`@emotion/cache`·`@mui/material-nextjs` 가 `node_modules` 에 설치된 상태 (이후 모든 태스크가 이 패키지들을 import 한다)

- [ ] **Step 1: 현재 상태 확인**

```bash
cd frontend && cat package.json
```

Expected: `dependencies` 에 `next`·`react`·`react-dom` 3개만 있어야 한다(이 플랜의 전제).

- [ ] **Step 2: 의존성 추가**

`frontend/package.json` 의 `"dependencies"` 블록을 다음으로 교체한다(버전은 2026-08-20 npm 레지스트리 실측값):

```json
  "dependencies": {
    "@emotion/cache": "^11.14.0",
    "@emotion/react": "^11.14.0",
    "@emotion/styled": "^11.14.1",
    "@mui/material": "^9.3.1",
    "@mui/material-nextjs": "^9.3.0",
    "next": "14.2.5",
    "react": "18.3.1",
    "react-dom": "18.3.1"
  },
```

- [ ] **Step 3: 설치**

```bash
cd frontend && npm install
```

Expected: `added N packages` 로 종료(에러 없음). `node_modules/@mui/material` 디렉터리가 생겼는지 확인:

```bash
ls frontend/node_modules/@mui/material/package.json && ls frontend/node_modules/@mui/material-nextjs/package.json
```

Expected: 둘 다 경로가 그대로 출력(존재 확인).

- [ ] **Step 4: 기존 앱이 여전히 빌드되는지 확인 (의존성 추가만으로 깨지지 않았는가)**

```bash
cd frontend && npx tsc --noEmit && npx next build
```

Expected: 에러 없이 종료, 기존 라우트 **18개** 그대로 출력(신규 라우트는 아직 없다 — v2 코드가 없으므로).

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "$(cat <<'EOF'
[M3] feat: P40 v2 Plan 1 Task 1 — MUI+Emotion 의존성 추가

이 프로젝트 최초로 next/react/react-dom 밖의 런타임 의존성이 늘어난다.
아직 어떤 코드도 이 패키지들을 쓰지 않는다 — 설치만 확인.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: v2 레이아웃 + 최소 페이지 (격리 증명)

**Files:**
- Create: `frontend/app/v2/layout.tsx`
- Create: `frontend/app/v2/manager/po/[poId]/page.tsx`

**Interfaces:**
- Consumes: `@mui/material-nextjs/v13-appRouter`(`AppRouterCacheProvider`), `@mui/material/styles`(`ThemeProvider`, `createTheme`)
- Produces: `/v2/manager/po/{poId}` 가 200 을 반환하고 MUI 로 렌더된 텍스트를 담는다. 이후 태스크가 `page.tsx` 를 계속 교체한다

- [ ] **Step 1: 레이아웃 작성**

`frontend/app/v2/layout.tsx`:

```tsx
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
    <AppRouterCacheProvider options={{ key: "mui-v2" }}>
      <ThemeProvider theme={theme}>{children}</ThemeProvider>
    </AppRouterCacheProvider>
  );
}
```

- [ ] **Step 2: 최소 페이지 작성**

`frontend/app/v2/manager/po/[poId]/page.tsx`:

```tsx
import Container from "@mui/material/Container";
import Typography from "@mui/material/Typography";

export default function PoDetailV2Page({ params }: { params: { poId: string } }) {
  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <Typography variant="h5">MaintQ v2 (MUI) — {params.poId}</Typography>
    </Container>
  );
}
```

- [ ] **Step 3: 타입 체크**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 에러 없음.

- [ ] **Step 4: dev 서버로 격리 확인**

백엔드는 필요 없다(이 태스크는 정적 텍스트만 렌더). 프론트 dev 서버만 띄운다:

```bash
cd frontend && npm run dev &
sleep 3
curl -s http://localhost:3003/v2/manager/po/PO-0117 | grep -o "MaintQ v2 (MUI) — PO-0117"
curl -s http://localhost:3003/v2/manager/po/PO-0117 | grep -c "설비보전 AI 콘솔"
```

Expected: 첫 줄은 `MaintQ v2 (MUI) — PO-0117` 출력(페이지가 렌더됐다). 둘째 줄은 `0`(v1 AppBar 문구인 "설비보전 AI 콘솔" 이 **전혀 없어야** 한다 — 격리 증명).

- [ ] **Step 5: v1 화면이 그대로인지 대조 확인**

```bash
curl -s http://localhost:3003/manager | grep -c "설비보전 AI 콘솔"
```

Expected: `1` 이상(v1 은 여전히 AppBar 를 보여준다 — v2 만 격리됐지 v1 이 망가진 게 아님을 확인).

dev 서버를 계속 띄워 둔다(다음 태스크에서 재사용). 서버가 실패했다면:

```bash
kill %1 2>/dev/null; cd frontend && npm run dev &
sleep 3
```

- [ ] **Step 6: 프로덕션 빌드도 확인**

```bash
cd frontend && npx next build
```

Expected: 성공, 라우트 목록에 `/v2/manager/po/[poId]` 가 새로 나타난다(**19개**로 증가). `next build` 는 dev 서버와 같은 포트를 쓰지 않으므로 병행 가능하다.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/v2
git commit -m "$(cat <<'EOF'
[M3] feat: P40 v2 Plan 1 Task 2 — MUI 레이아웃 격리 확인

app/v2/layout.tsx 가 AppRouterCacheProvider+ThemeProvider(기본 테마)로
MUI 를 이 서브트리에만 격리한다. app/(console)/v2 가 아니라 app/v2 인
이유는 설계 spec §2 정정 참조 — (console)/layout.tsx 의 v1 AppBar를
Next.js 레이아웃 중첩 규칙상 생략할 수 없기 때문이다.

curl 로 실측 확인: v2 페이지에 v1 AppBar 문구("설비보전 AI 콘솔") 0건,
v1 페이지(/manager)는 그대로 유지.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: 데이터 훅 + 최소 상세 렌더 (데이터 흐름 증명)

**Files:**
- Create: `frontend/lib/v2/useApprovalQueueV2.ts`
- Modify: `frontend/app/v2/manager/po/[poId]/page.tsx` (Task 2 의 최소 버전을 교체)

**Interfaces:**
- Consumes: `frontend/lib/api.ts` 의 `getApprovals`·`getPo`·`approvePo`·`rejectPo`·`ApiError`·`extractDetail`·`ApiApproval`·`ApiPo`. `frontend/lib/mappers.tsx` 의 `toQueueEntry`·`toPoQueueEntry`·`toEvidenceEntries`·`toQuotes`. `frontend/lib/types.ts` 의 `QueueEntry`·`EvidenceEntry`·`SupplierQuote`
- Produces: `useApprovalQueueV2(initialId: string): ApprovalQueueV2` — 아래 인터페이스. Task 4~6 이 이 반환값의 필드를 그대로 쓴다:
  ```ts
  interface ApprovalQueueV2 {
    loading: boolean;
    error: string | null;
    pending: QueueEntry[];
    recent: QueueEntry[];
    selected: QueueEntry | null;
    poDetail: ApiPo | null;
    evidence: EvidenceEntry[];
    quotes: SupplierQuote[];
    notice: string | null;
    selectEntry: (entry: QueueEntry) => void;
    approve: () => Promise<void>;
    reject: (reason: string) => Promise<void>;
    dismissNotice: () => void;
  }
  ```

- [ ] **Step 1: 훅 작성**

`frontend/lib/v2/useApprovalQueueV2.ts`:

```ts
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  approvePo,
  extractDetail,
  getApprovals,
  getPo,
  rejectPo,
  type ApiApproval,
  type ApiPo,
} from "@/lib/api";
import { toEvidenceEntries, toPoQueueEntry, toQueueEntry, toQuotes } from "@/lib/mappers";
import type { EvidenceEntry, QueueEntry, SupplierQuote } from "@/lib/types";

export interface ApprovalQueueV2 {
  loading: boolean;
  error: string | null;
  pending: QueueEntry[];
  recent: QueueEntry[];
  selected: QueueEntry | null;
  poDetail: ApiPo | null;
  evidence: EvidenceEntry[];
  quotes: SupplierQuote[];
  notice: string | null;
  selectEntry: (entry: QueueEntry) => void;
  approve: () => Promise<void>;
  reject: (reason: string) => Promise<void>;
  dismissNotice: () => void;
}

function describeError(e: unknown): string {
  return e instanceof ApiError
    ? `${e.status} — ${extractDetail(e.body)}`
    : `백엔드에 연결하지 못했습니다 — ${String(e)}`;
}

/**
 * v2 전용 큐 오케스트레이션 (설계 spec §3-1).
 *
 * `components/screens/ApprovalQueueScreen.tsx` 의 `load()`/`decide()` 와 같은 API 호출·
 * 매퍼를 쓰되 독립 구현이다 — v1 파일을 건드리지 않기 위한 의도적 중복(대안 기각 이유는
 * spec §3-1 표). 목업 폴백이 없다 — v2 는 실 API 전용이라 백엔드가 없으면 에러를 그대로
 * 보여준다(v1 의 "mock 모드"보다 단순하고, 이 화면의 목적(실동작 비교)에 더 맞다).
 *
 * **Plan 1 범위**: po 종류만 상세를 채운다. disposal·repair 항목은 큐 목록에는 섞여
 * 뜨지만 선택해도 `poDetail` 이 `null` 로 남는다 — 페이지가 "아직 없음" 안내로 처리한다
 * (Plan 2 가 DecisionDetailV2·RepairDetailV2 를 추가하면 이 훅도 함께 확장한다).
 */
export function useApprovalQueueV2(initialId: string): ApprovalQueueV2 {
  const [selectedId, setSelectedId] = useState(initialId);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<QueueEntry[]>([]);
  const [recent, setRecent] = useState<QueueEntry[]>([]);
  const [selected, setSelected] = useState<QueueEntry | null>(null);
  const [poDetail, setPoDetail] = useState<ApiPo | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // 종결 어휘가 종류마다 다르다(D85) — po 는 approved, disposal 은 signed. Plan 1 은
      // po·rejected 만 필요하지만 큐 목록에는 다른 종류도 섞여 보여야 하므로 approved 만
      // 추가로 모은다(전 종류 종결 상태를 다 모으는 것은 Plan 2 범위).
      const [p, approved, rejected] = await Promise.all([
        getApprovals("manager", "pending"),
        getApprovals("manager", "approved"),
        getApprovals("manager", "rejected"),
      ]);
      const done = [...approved, ...rejected].slice(0, 4);
      setPending(p.map(toQueueEntry));
      setRecent(done.map(toQueueEntry));

      const all: ApiApproval[] = [...p, ...done];
      const found = all.find((i) => i.id === selectedId);

      if (found) {
        setSelected(toQueueEntry(found));
        setPoDetail(found.kind === "po" ? await getPo("manager", found.id) : null);
      } else {
        // 큐 4목록 밖의 발주(예: draft) 딥링크 — /api/po 로 직접 확인 (v1 load() 와 같은 순서)
        const direct = await getPo("manager", selectedId);
        setSelected(toPoQueueEntry(direct));
        setPoDetail(direct);
      }
      setError(null);
    } catch (e) {
      setSelected(null);
      setPoDetail(null);
      setError(describeError(e));
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    void load();
  }, [load]);

  function selectEntry(entry: QueueEntry) {
    setSelectedId(entry.id);
  }

  async function approve() {
    if (!poDetail) return;
    try {
      const updated = await approvePo(poDetail.po_id);
      setNotice(`${updated.po_id} 승인 완료 — ${updated.state}`);
      await load();
    } catch (e) {
      setNotice(describeError(e));
    }
  }

  async function reject(reason: string) {
    if (!poDetail) return;
    try {
      const updated = await rejectPo(poDetail.po_id, reason);
      setNotice(`${updated.po_id} 반려 완료 — ${updated.state}`);
      await load();
    } catch (e) {
      setNotice(describeError(e));
    }
  }

  return {
    loading,
    error,
    pending,
    recent,
    selected,
    poDetail,
    evidence: poDetail ? toEvidenceEntries(poDetail) : [],
    quotes: poDetail ? toQuotes(poDetail) : [],
    notice,
    selectEntry,
    approve,
    reject,
    dismissNotice: () => setNotice(null),
  };
}
```

- [ ] **Step 2: 페이지를 훅 연결 버전으로 교체 (최소 렌더)**

`frontend/app/v2/manager/po/[poId]/page.tsx` 전체 교체:

```tsx
"use client";

import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import Container from "@mui/material/Container";
import Typography from "@mui/material/Typography";
import { useApprovalQueueV2 } from "@/lib/v2/useApprovalQueueV2";
import { stateView } from "@/lib/queueState";

export default function PoDetailV2Page({ params }: { params: { poId: string } }) {
  const q = useApprovalQueueV2(params.poId);

  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <Typography variant="h5" sx={{ mb: 2 }}>
        MaintQ v2 (MUI) — 승인 큐
      </Typography>

      {q.error && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {q.error}
        </Alert>
      )}

      {q.loading ? (
        <Typography color="text.secondary">불러오는 중…</Typography>
      ) : q.selected ? (
        <>
          <Typography variant="h6">
            #{q.selected.id} {q.selected.title}
          </Typography>
          <Chip
            label={(() => {
              const s = stateView(q.selected.kind, q.selected.state);
              return s.known ? s.text : `${s.text}`;
            })()}
            sx={{ mt: 1 }}
          />
        </>
      ) : (
        <Typography color="text.secondary">표시할 항목이 없습니다.</Typography>
      )}
    </Container>
  );
}
```

- [ ] **Step 3: 타입 체크**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 에러 없음.

- [ ] **Step 4: 백엔드 기동 (데이터 흐름을 실제로 보려면 필요)**

```bash
uv run uvicorn backend.main:app --port 8003 &
sleep 3
curl -s http://localhost:8003/health
```

Expected: 헬스체크 200 응답(백엔드 정상 기동).

- [ ] **Step 5: 실제 발주로 데이터 흐름 확인**

프론트 dev 서버가 Task 2 부터 계속 떠 있어야 한다(꺼졌다면 `cd frontend && npm run dev &`).

```bash
curl -s http://localhost:3003/v2/manager/po/PO-0117 | grep -oE "#PO-0117[^<]*"
curl -s http://localhost:3003/v2/manager/po/PO-0117 | grep -c "MuiChip-root"
```

Expected: 첫 줄에 `PO-0117` 관련 제목 텍스트가 보인다(정확한 문구는 시드 데이터에 따라 다를 수 있음 — 핵심은 `PO-0117` 문자열이 실제 발주 제목과 함께 나오는 것, 즉 하드코딩이 아니라 백엔드 응답에서 왔다는 증거). 둘째 줄은 `1` 이상(MUI Chip 이 실제로 렌더됨).

- [ ] **Step 6: 없는 발주로 에러 처리 확인**

```bash
curl -s http://localhost:3003/v2/manager/po/PO-9999 | grep -o "백엔드에 연결하지 못했습니다\|404"
```

Expected: 에러 관련 텍스트가 보인다(정확한 문구는 `extractDetail` 이 백엔드 404 응답을 파싱한 결과 — "찾을 수 없습니다" 류 문구일 수 있다. 핵심은 **빈 화면이나 크래시가 아니라 에러가 명시적으로 보이는 것**).

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/v2 frontend/app/v2/manager/po/[poId]/page.tsx
git commit -m "$(cat <<'EOF'
[M3] feat: P40 v2 Plan 1 Task 3 — useApprovalQueueV2 훅 + 데이터 흐름 확인

lib/api.ts·lib/mappers.tsx 를 그대로 재사용해 실제 백엔드에서 발주를
읽어온다. 상태 표시는 stateView() 를 거쳐 D87 을 지킨다.

curl 로 실측: 존재하는 발주는 실제 제목이 렌더되고, 없는 발주는 크래시
대신 에러 메시지가 뜬다.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: QueueListV2 (큐 목록)

**Files:**
- Create: `frontend/components/v2/QueueListV2.tsx`
- Modify: `frontend/app/v2/manager/po/[poId]/page.tsx`

**Interfaces:**
- Consumes: `useApprovalQueueV2()` 의 `pending`·`recent`·`selected`·`selectEntry` (Task 3 산출). `lib/queueState.ts` 의 `kindView`·`stateView`
- Produces: `QueueListV2({ pending, recent, selectedId, onSelect })` — Task 5 이후에도 그대로 쓰인다

- [ ] **Step 1: 컴포넌트 작성**

`frontend/components/v2/QueueListV2.tsx`:

```tsx
"use client";

import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { kindView, stateView, type QueueTone } from "@/lib/queueState";
import type { QueueEntry } from "@/lib/types";

/**
 * 통합 승인 큐 목록 (MUI). `components/queue/QueueList.tsx` 와 달리 `<Link>` 네비게이션이
 * 아니라 **로컬 상태 전환**이다 — v2 는 라우트 하나 안에서 po/disposal/repair 상세를
 * 인라인으로 바꾼다 (설계 spec §1 "인라인 전환", v1 은 3개 별도 라우트로 이동한다).
 */
export function QueueListV2({
  pending,
  recent,
  selectedId,
  onSelect,
}: {
  pending: QueueEntry[];
  recent: QueueEntry[];
  selectedId: string | null;
  onSelect: (entry: QueueEntry) => void;
}) {
  return (
    <Stack sx={{ borderRight: "1px solid", borderColor: "divider", height: "100%" }}>
      <SectionLabel>승인 대기 · {pending.length}</SectionLabel>
      <List dense disablePadding>
        {pending.map((e) => (
          <QueueItemV2
            key={`${e.kind}:${e.id}`}
            entry={e}
            selected={e.id === selectedId}
            onSelect={onSelect}
          />
        ))}
      </List>
      <Divider sx={{ my: 1.5 }} />
      <SectionLabel>최근 처리</SectionLabel>
      <List dense disablePadding>
        {recent.map((e) => (
          <QueueItemV2 key={`${e.kind}:${e.id}`} entry={e} muted onSelect={onSelect} />
        ))}
      </List>
    </Stack>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <Typography
      variant="overline"
      color="text.secondary"
      sx={{ px: 1.5, pt: 1.5, pb: 1, display: "block" }}
    >
      {children}
    </Typography>
  );
}

function toneToChipColor(tone: QueueTone): "default" | "info" | "success" | "error" | "warning" {
  if (tone === "info") return "info";
  if (tone === "ok") return "success";
  if (tone === "danger") return "error";
  if (tone === "warn") return "warning";
  return "default";
}

function QueueItemV2({
  entry,
  selected = false,
  muted = false,
  onSelect,
}: {
  entry: QueueEntry;
  selected?: boolean;
  muted?: boolean;
  onSelect: (entry: QueueEntry) => void;
}) {
  const kind = kindView(entry.kind);
  const state = stateView(entry.kind, entry.state);

  return (
    <ListItemButton
      selected={selected}
      onClick={() => onSelect(entry)}
      sx={{ opacity: muted ? 0.72 : 1, flexDirection: "column", alignItems: "stretch", py: 1 }}
    >
      <Stack direction="row" spacing={0.5} sx={{ mb: 0.5 }}>
        <Chip
          size="small"
          variant="outlined"
          label={kind.known ? kind.text : `${kind.text}`}
        />
        <Chip
          size="small"
          variant={state.known ? "filled" : "outlined"}
          color={state.known ? toneToChipColor(state.tone) : "default"}
          label={state.known ? state.text : `${state.text}`}
        />
      </Stack>
      <Typography variant="body2" fontWeight={700} noWrap>
        #{entry.id} {entry.title}
      </Typography>
      {entry.meta && (
        <Typography variant="caption" color="text.secondary" fontFamily="monospace">
          {entry.meta}
        </Typography>
      )}
    </ListItemButton>
  );
}
```

- [ ] **Step 2: 페이지에 QueueListV2 연결**

`frontend/app/v2/manager/po/[poId]/page.tsx` 전체 교체:

```tsx
"use client";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Container from "@mui/material/Container";
import Typography from "@mui/material/Typography";
import { QueueListV2 } from "@/components/v2/QueueListV2";
import { useApprovalQueueV2 } from "@/lib/v2/useApprovalQueueV2";
import { stateView } from "@/lib/queueState";

export default function PoDetailV2Page({ params }: { params: { poId: string } }) {
  const q = useApprovalQueueV2(params.poId);

  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <Typography variant="h5" sx={{ mb: 2 }}>
        MaintQ v2 (MUI) — 승인 큐
      </Typography>

      {q.error && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {q.error}
        </Alert>
      )}

      {q.loading ? (
        <Typography color="text.secondary">불러오는 중…</Typography>
      ) : q.selected ? (
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: "280px 1fr",
            minHeight: 560,
            border: "1px solid",
            borderColor: "divider",
          }}
        >
          <QueueListV2
            pending={q.pending}
            recent={q.recent}
            selectedId={q.selected.id}
            onSelect={q.selectEntry}
          />
          <Box sx={{ p: 3 }}>
            <Typography variant="h6">
              #{q.selected.id} {q.selected.title}
            </Typography>
            <Chip
              label={(() => {
                const s = stateView(q.selected.kind, q.selected.state);
                return s.known ? s.text : `${s.text}`;
              })()}
              sx={{ mt: 1 }}
            />
          </Box>
        </Box>
      ) : (
        <Typography color="text.secondary">표시할 항목이 없습니다.</Typography>
      )}
    </Container>
  );
}
```

- [ ] **Step 3: 타입 체크**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 에러 없음.

- [ ] **Step 4: 목록 렌더 확인**

프론트·백엔드 dev 서버가 둘 다 떠 있어야 한다(Task 2·3 에서 시작한 것 재사용, 꺼졌으면 다시 기동).

```bash
curl -s http://localhost:3003/v2/manager/po/PO-0117 | grep -c "승인 대기"
curl -s http://localhost:3003/v2/manager/po/PO-0117 | grep -c "최근 처리"
```

Expected: 둘 다 `1` 이상(섹션 라벨이 렌더됨 = 목록이 그려짐).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/v2/QueueListV2.tsx "frontend/app/v2/manager/po/[poId]/page.tsx"
git commit -m "$(cat <<'EOF'
[M3] feat: P40 v2 Plan 1 Task 4 — QueueListV2 (MUI List)

v1 QueueList 와 달리 <Link> 네비게이션이 아니라 로컬 상태 전환이다 —
v2 는 라우트 하나 안에서 인라인으로 상세를 바꾼다(설계 spec §1).
kindView()·stateView() 를 그대로 호출해 D87 을 지킨다.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: 발주 상세 3종 (EvidenceCardV2 · SupplierCompareV2 · DecisionBarV2 → PoDetailV2)

**Files:**
- Create: `frontend/components/v2/EvidenceCardV2.tsx`
- Create: `frontend/components/v2/SupplierCompareV2.tsx`
- Create: `frontend/components/v2/DecisionBarV2.tsx`
- Create: `frontend/components/v2/PoDetailV2.tsx`
- Modify: `frontend/app/v2/manager/po/[poId]/page.tsx`

**Interfaces:**
- Consumes: `lib/citation.ts` 의 `citationLabel`. `lib/types.ts` 의 `EvidenceEntry`·`SupplierQuote`·`QueueEntry`. `lib/queueState.ts` 의 `stateView`
- Produces: `PoDetailV2({ entry, evidence, quotes, onApprove, onReject })` — Task 6 이 `onApprove`/`onReject` 를 훅의 `approve`/`reject` 에 연결한다

이 셋(EvidenceCardV2·SupplierCompareV2·DecisionBarV2)은 전부 `PoDetailV2` 하나의 자식이고 서로 독립적으로 검토될 이유가 없어(Task Right-Sizing) 한 태스크로 묶는다.

- [ ] **Step 1: EvidenceCardV2 작성**

`frontend/components/v2/EvidenceCardV2.tsx`:

```tsx
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Link from "next/link";
import { citationLabel } from "@/lib/citation";
import type { EvidenceEntry } from "@/lib/types";

const DEFAULT_TITLE = "근거 요약 · 대화 전체를 읽지 않아도 판단 가능";

/** `components/queue/EvidenceCard.tsx` 의 MUI 재현. 값·인용 조립 로직은 손대지 않는다 —
 * `toEvidenceEntries()`(lib/mappers.tsx)가 이미 만든 EvidenceEntry[] 를 그대로 렌더만 한다. */
export function EvidenceCardV2({
  entries,
  title = DEFAULT_TITLE,
}: {
  entries: EvidenceEntry[];
  title?: string;
}) {
  return (
    <Card variant="outlined" sx={{ mb: 2 }}>
      <CardContent>
        <Typography variant="overline" color="text.secondary" sx={{ display: "block", mb: 1.5 }}>
          {title}
        </Typography>
        <Stack spacing={1.25}>
          {entries.map((e) => (
            <Stack key={e.label} direction="row" spacing={1.5} alignItems="baseline">
              <Typography
                variant="caption"
                sx={{
                  width: 82,
                  flexShrink: 0,
                  fontFamily: "monospace",
                  fontWeight: 700,
                  color: "text.secondary",
                }}
              >
                {e.label}
              </Typography>
              <Typography variant="body2">
                {e.href ? (
                  <Link href={e.href} style={{ color: "inherit" }}>
                    {e.value}
                  </Link>
                ) : (
                  e.value
                )}
                {e.citation && (
                  <Chip
                    size="small"
                    variant="outlined"
                    label={citationLabel(e.citation)}
                    sx={{ ml: 1, fontFamily: "monospace" }}
                  />
                )}
              </Typography>
            </Stack>
          ))}
        </Stack>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: SupplierCompareV2 작성**

`frontend/components/v2/SupplierCompareV2.tsx`:

```tsx
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Grid from "@mui/material/Grid";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { SupplierQuote } from "@/lib/types";

/** `components/queue/SupplierCompare.tsx` 의 MUI 재현. 추천 로직(P2)은 여기 없다 —
 * `q.recommended` 는 lib/mappers.tsx 의 toQuotes() 가 이미 정해서 넘긴다. */
export function SupplierCompareV2({ quotes }: { quotes: SupplierQuote[] }) {
  return (
    <Stack sx={{ mb: 2 }}>
      <Typography variant="overline" color="text.secondary" sx={{ mb: 1 }}>
        공급사 비교 · 선택은 사람이
      </Typography>
      <Grid container spacing={1.5}>
        {quotes.map((q) => (
          <Grid size={6} key={q.supplierId}>
            <Card
              variant="outlined"
              sx={{
                borderColor: q.recommended ? "primary.main" : undefined,
                borderWidth: q.recommended ? 2 : 1,
                position: "relative",
              }}
            >
              {q.recommended && (
                <Chip
                  label="추천"
                  color="primary"
                  size="small"
                  sx={{ position: "absolute", top: -10, left: 12 }}
                />
              )}
              <CardContent>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  {q.name}
                </Typography>
                <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                  <Typography variant="body2" color="text.secondary">
                    리드타임
                  </Typography>
                  <Typography variant="body2" fontWeight={q.recommended ? 600 : 400}>
                    {q.leadDays}일
                  </Typography>
                </Stack>
                <Stack direction="row" justifyContent="space-between" sx={{ mb: 1 }}>
                  <Typography variant="body2" color="text.secondary">
                    단가
                  </Typography>
                  <Typography variant="body2" fontFamily="monospace">
                    ₩{q.unitPrice.toLocaleString()}
                  </Typography>
                </Stack>
                <Typography
                  variant="caption"
                  color={q.recommended ? "primary.main" : "text.secondary"}
                  sx={{ display: "block", pt: 1, borderTop: "1px solid", borderColor: "divider" }}
                >
                  {q.note}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Stack>
  );
}
```

`Grid` 는 `size={6}` 를 쓴다(`item xs={6}` 가 아니다) — 설치된 `@mui/material@9.x` 는 신 Grid API 다(2026-08-20 npm 레지스트리·타입 정의 실측 확인, `item` prop 이 제거됐다).

- [ ] **Step 3: DecisionBarV2 작성**

`frontend/components/v2/DecisionBarV2.tsx`:

```tsx
"use client";

import { useState } from "react";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

/** `components/queue/DecisionBar.tsx` 의 MUI 재현. v1 과 달리 목업 모드(disabled) 분기가
 * 없다 — v2 는 실 API 전용이라 항상 onApprove/onReject 가 있다(설계 spec §1). */
export function DecisionBarV2({
  supplierName,
  onApprove,
  onReject,
}: {
  supplierName: string;
  onApprove: () => void;
  onReject: (reason: string) => void;
}) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");

  if (rejecting) {
    return (
      <Stack spacing={1.5} sx={{ pt: 2, mt: "auto", borderTop: "1px solid", borderColor: "divider" }}>
        <Typography variant="caption" color="error" fontWeight={700}>
          반려 사유 (필수)
        </Typography>
        <TextField
          autoFocus
          multiline
          minRows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="예: 예산 초과 — 차기 분기 재검토 / 재고 있음 / 사양 불일치"
        />
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>
            사유는 요청자에게 그대로 전달되고 발주 이력에 남습니다.
          </Typography>
          <Button variant="outlined" onClick={() => setRejecting(false)}>
            취소
          </Button>
          <Button
            variant="contained"
            color="error"
            onClick={() => {
              // 공백만 입력한 경우도 사유가 아니다 (v1 DecisionBar 와 같은 규칙)
              if (!reason.trim()) return;
              onReject(reason.trim());
              setReason("");
              setRejecting(false);
            }}
          >
            반려 확정
          </Button>
        </Stack>
      </Stack>
    );
  }

  return (
    <Stack
      direction="row"
      spacing={1.5}
      alignItems="center"
      sx={{ pt: 2, mt: "auto", borderTop: "1px solid", borderColor: "divider" }}
    >
      <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>
        승인 시 {supplierName} 발주서가 확정됩니다. 반려 시 요청자에게 사유가 전달됩니다.
      </Typography>
      <Button variant="outlined" color="error" onClick={() => setRejecting(true)}>
        반려 (사유 입력)
      </Button>
      <Button variant="contained" onClick={onApprove}>
        승인 — 발주서 확정
      </Button>
    </Stack>
  );
}
```

- [ ] **Step 4: PoDetailV2 로 조립**

`frontend/components/v2/PoDetailV2.tsx`:

```tsx
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { stateView } from "@/lib/queueState";
import type { EvidenceEntry, QueueEntry, SupplierQuote } from "@/lib/types";
import { DecisionBarV2 } from "./DecisionBarV2";
import { EvidenceCardV2 } from "./EvidenceCardV2";
import { SupplierCompareV2 } from "./SupplierCompareV2";

/** `components/queue/PoDetail.tsx` 의 MUI 재현. `kind === "po"` 항목 전용(호출부가 보장). */
export function PoDetailV2({
  entry,
  evidence,
  quotes,
  onApprove,
  onReject,
}: {
  entry: QueueEntry;
  evidence: EvidenceEntry[];
  quotes: SupplierQuote[];
  onApprove: () => void;
  onReject: (reason: string) => void;
}) {
  const recommended = quotes.find((q) => q.recommended) ?? quotes[0];
  const state = stateView(entry.kind, entry.state);

  return (
    <Box sx={{ p: 3, display: "flex", flexDirection: "column", height: "100%" }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
        <Typography variant="h6" fontFamily="monospace">
          #{entry.id}
        </Typography>
        <Typography variant="h6">{entry.title}</Typography>
        {entry.urgency === "urgent" && <Chip label="▲ 긴급" color="warning" size="small" />}
        <Chip
          size="small"
          variant={state.known ? "filled" : "outlined"}
          label={state.known ? state.text : `${state.text}`}
        />
        <Box sx={{ flex: 1 }} />
        <Typography variant="caption" color="text.secondary" fontFamily="monospace">
          요청 · {entry.meta}
        </Typography>
      </Stack>

      <EvidenceCardV2 entries={evidence} />
      <SupplierCompareV2 quotes={quotes} />
      <DecisionBarV2
        supplierName={recommended?.name ?? ""}
        onApprove={onApprove}
        onReject={onReject}
      />
    </Box>
  );
}
```

- [ ] **Step 5: 페이지에서 PoDetailV2 로 교체 (승인/반려는 아직 콘솔 로그만 — Task 6 에서 실연결)**

`frontend/app/v2/manager/po/[poId]/page.tsx` 의 우측 패널 부분만 교체 — 전체 파일:

```tsx
"use client";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Typography from "@mui/material/Typography";
import { PoDetailV2 } from "@/components/v2/PoDetailV2";
import { QueueListV2 } from "@/components/v2/QueueListV2";
import { useApprovalQueueV2 } from "@/lib/v2/useApprovalQueueV2";

export default function PoDetailV2Page({ params }: { params: { poId: string } }) {
  const q = useApprovalQueueV2(params.poId);

  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <Typography variant="h5" sx={{ mb: 2 }}>
        MaintQ v2 (MUI) — 승인 큐
      </Typography>

      {q.error && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {q.error}
        </Alert>
      )}

      {q.loading ? (
        <Typography color="text.secondary">불러오는 중…</Typography>
      ) : q.selected ? (
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: "280px 1fr",
            minHeight: 560,
            border: "1px solid",
            borderColor: "divider",
          }}
        >
          <QueueListV2
            pending={q.pending}
            recent={q.recent}
            selectedId={q.selected.id}
            onSelect={q.selectEntry}
          />
          {q.selected.kind === "po" && q.poDetail ? (
            <PoDetailV2
              entry={q.selected}
              evidence={q.evidence}
              quotes={q.quotes}
              onApprove={() => console.log("approve — Task 6 에서 연결")}
              onReject={(reason) => console.log("reject", reason, "— Task 6 에서 연결")}
            />
          ) : (
            <Box sx={{ p: 3 }}>
              <Typography color="text.secondary">
                이 종류({q.selected.kind})의 v2 상세 화면은 아직 없습니다 — 다음 플랜에서
                붙습니다.
              </Typography>
            </Box>
          )}
        </Box>
      ) : (
        <Typography color="text.secondary">표시할 항목이 없습니다.</Typography>
      )}
    </Container>
  );
}
```

- [ ] **Step 6: 타입 체크**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 에러 없음. (Grid `size` prop 오류가 나면 §Step 2 의 경고대로 `item`/`xs` 를 쓰고 있지 않은지 확인)

- [ ] **Step 7: 렌더 확인**

```bash
curl -s http://localhost:3003/v2/manager/po/PO-0117 | grep -c "근거 요약"
curl -s http://localhost:3003/v2/manager/po/PO-0117 | grep -c "공급사 비교"
curl -s http://localhost:3003/v2/manager/po/PO-0117 | grep -c "승인 — 발주서 확정"
```

Expected: 셋 다 `1` 이상.

- [ ] **Step 8: Commit**

```bash
git add frontend/components/v2 "frontend/app/v2/manager/po/[poId]/page.tsx"
git commit -m "$(cat <<'EOF'
[M3] feat: P40 v2 Plan 1 Task 5 — 발주 상세 3종 MUI 재현

EvidenceCardV2·SupplierCompareV2·DecisionBarV2 를 PoDetailV2 로 조립.
v1 컴포넌트(components/queue/*)와 같은 props 계약, MUI 프리미티브로만
재작성했다. 승인/반려 버튼은 아직 콘솔 로그만 찍는다 — 실 연결은 Task 6.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: 승인/반려 실연결 + D87 회귀 확장 + 전수 검증

**Files:**
- Modify: `frontend/app/v2/manager/po/[poId]/page.tsx`
- Modify: `spikes/ui_honesty_contract.py`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: `useApprovalQueueV2()` 의 `approve`·`reject`·`notice`·`dismissNotice` (Task 3 산출)

- [ ] **Step 1: 승인/반려를 훅에 실연결**

`frontend/app/v2/manager/po/[poId]/page.tsx` 전체 교체(Task 5 버전에서 콘솔 로그 대신 실제 훅 호출 + 알림 스낵바 추가):

```tsx
"use client";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Snackbar from "@mui/material/Snackbar";
import Typography from "@mui/material/Typography";
import { PoDetailV2 } from "@/components/v2/PoDetailV2";
import { QueueListV2 } from "@/components/v2/QueueListV2";
import { useApprovalQueueV2 } from "@/lib/v2/useApprovalQueueV2";

export default function PoDetailV2Page({ params }: { params: { poId: string } }) {
  const q = useApprovalQueueV2(params.poId);

  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <Typography variant="h5" sx={{ mb: 2 }}>
        MaintQ v2 (MUI) — 승인 큐
      </Typography>

      {q.error && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {q.error}
        </Alert>
      )}

      {q.loading ? (
        <Typography color="text.secondary">불러오는 중…</Typography>
      ) : q.selected ? (
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: "280px 1fr",
            minHeight: 560,
            border: "1px solid",
            borderColor: "divider",
          }}
        >
          <QueueListV2
            pending={q.pending}
            recent={q.recent}
            selectedId={q.selected.id}
            onSelect={q.selectEntry}
          />
          {q.selected.kind === "po" && q.poDetail ? (
            <PoDetailV2
              entry={q.selected}
              evidence={q.evidence}
              quotes={q.quotes}
              onApprove={() => void q.approve()}
              onReject={(reason) => void q.reject(reason)}
            />
          ) : (
            <Box sx={{ p: 3 }}>
              <Typography color="text.secondary">
                이 종류({q.selected.kind})의 v2 상세 화면은 아직 없습니다 — 다음 플랜에서
                붙습니다.
              </Typography>
            </Box>
          )}
        </Box>
      ) : (
        <Typography color="text.secondary">표시할 항목이 없습니다.</Typography>
      )}

      <Snackbar
        open={!!q.notice}
        autoHideDuration={4000}
        onClose={q.dismissNotice}
        message={q.notice}
      />
    </Container>
  );
}
```

- [ ] **Step 2: 타입 체크**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 에러 없음.

- [ ] **Step 3: 실제 승인 동작 확인 (실 DB 를 바꾼다 — 시드에서 pending 상태인 발주로)**

```bash
curl -s http://localhost:8003/api/po/PO-0117 -H "X-Role: manager" -H "X-User: mgr-01" | grep -o '"state":"[a-z]*"'
```

Expected: 지금 상태 확인(`pending` 이어야 다음 단계에서 의미가 있다). `pending` 이 아니면 `uv run python data/seed.py --with-error-codes` 로 재시드 후 재확인.

브라우저 없이 승인 동작 자체를 검증하려면 훅이 호출하는 것과 같은 API 를 직접 호출해 계약을 재확인한다(화면 클릭은 사람이 devtools 없이 curl 만으로 재현할 수 없으므로, 이 단계는 **훅이 부르는 백엔드 API 가 기대대로 동작하는지**를 확인하는 것이다 — 화면 자체의 클릭 확인은 아래 §수동 확인 체크리스트로 넘긴다):

```bash
curl -s -X POST http://localhost:8003/api/po/PO-0117/approve \
  -H "X-Role: manager" -H "X-User: mgr-01" -H "Content-Type: application/json" \
  -d '{"note": "Plan 1 Task 6 검증"}' | grep -o '"state":"[a-z]*"'
```

Expected: `"state":"approved"`.

**이 명령은 시드 DB 를 실제로 바꾼다.** 검증 후 재시드해 원복한다:

```bash
uv run python data/seed.py --with-error-codes
```

- [ ] **Step 4: `ui_honesty_contract.py` 글롭 확장**

`spikes/ui_honesty_contract.py` 에서:

```python
L2_GLOBS = ("components/asset/*.tsx", "components/queue/Decision*.tsx", "app/(console)/**/*.tsx")
L2_EXTRA = ("components/queue/SignBar.tsx", "components/queue/RepairDetail.tsx")
```

를 다음으로 교체:

```python
# P40 Plan 1(2026-08-20) — v2 는 app/(console) 밖의 새 트리라 기존 글롭이 못 잡는다.
# app/(console)/v2 대신 app/v2 로 간 이유(레이아웃 격리)는 설계 spec §2 정정 참조.
# 새 글롭 2개로 D87 감시를 그대로 유지한다 — Sprint 10 이 app/(console)/** 를 세 번째
# 글롭으로 더한 것과 같은 방식(윗 주석 "Sprint 10 이 …" 선례).
L2_GLOBS = (
    "components/asset/*.tsx",
    "components/queue/Decision*.tsx",
    "app/(console)/**/*.tsx",
    "app/v2/**/*.tsx",
    "components/v2/*.tsx",
)
L2_EXTRA = ("components/queue/SignBar.tsx", "components/queue/RepairDetail.tsx")
```

`L2_FILES_FLOOR = 36` 줄을 찾아 다음으로 교체(신규 7개 v2 파일 — `layout.tsx`·`page.tsx`·`QueueListV2.tsx`·`EvidenceCardV2.tsx`·`SupplierCompareV2.tsx`·`DecisionBarV2.tsx`·`PoDetailV2.tsx`):

```python
L2_FILES_FLOOR = 43
# P40 Plan 1(2026-08-20) — app/v2/layout.tsx·app/v2/manager/po/[poId]/page.tsx +
# components/v2/{QueueListV2,EvidenceCardV2,SupplierCompareV2,DecisionBarV2,PoDetailV2}.tsx
# 7개가 새 글롭에 편입돼 36 → 43. 실행 결과("L2 스캔 대상 N개")로 재확인할 것 — 암산 아님.
```

- [ ] **Step 5: 전수 회귀 실행**

```bash
uv run python spikes/ui_honesty_contract.py
```

Expected: `통과` 로 끝나고 "L2 스캔 대상 43개"(또는 그 이상)가 출력에 보인다. **FAIL 이 나면 코드를 고치지 말고 먼저 어느 L2 규칙에 걸렸는지 출력을 읽는다** — 이 플랜의 코드는 `stateView()`/`kindView()` 만 쓰도록 설계했으므로 통과해야 정상이다. 실패하면 Task 3~5 의 코드가 상태 어휘를 직접 비교하는 곳이 있는지 재검토한다.

```bash
uv run ruff check data backend mcp_server spikes
```

Expected: `All checks passed!` (Python 쪽은 이 플랜에서 건드리지 않았으므로 원래도 clean 이어야 한다)

```bash
cd frontend && npx tsc --noEmit && npx next build
```

Expected: 라우트 **19개** (v1 18개 + v2 1개), 에러 없음.

- [ ] **Step 6: dev 서버 정리**

```bash
kill %1 %2 2>/dev/null
```

(Task 2·3 에서 백그라운드로 띄운 프론트·백엔드 dev 서버를 종료. job 번호가 다르면 `jobs` 로 확인 후 개별 kill)

- [ ] **Step 7: CLAUDE.md 기준선 갱신**

`CLAUDE.md:125` (2026-08-20 기준 실측 줄 번호 — 태스크 실행 시점에 세션 중 다른 커밋이 끼어 줄 번호가 밀려 있을 수 있으니, 아래 **문자열로** 찾는다) 에서 다음 문구를 찾는다:

```
프론트 라우트 **18개**(`npx next build` — `find frontend/app -name page.tsx` 로 세면 **17개**다.
```

이 줄의 `**18개**` 를 `**19개**` 로, 문장 맨 끝(그 줄의 마지막 마침 지점, 다음 항목 나열 `,` 앞)에 아래 델타 설명을 이어붙인다. 정확히는 파이썬으로 치환한다:

```bash
uv run python - <<'PY'
import io
p = "CLAUDE.md"
s = io.open(p, encoding="utf-8").read()
old = "프론트 라우트 **18개**(`npx next build`"
new = "프론트 라우트 **19개**(`npx next build`"
assert old in s, "앵커 문자열을 못 찾았다 — CLAUDE.md 가 이 태스크 작성 이후 바뀌었을 수 있다. grep -n '라우트 \\*\\*18개\\*\\*' CLAUDE.md 로 재확인할 것"
s = s.replace(old, new, 1)
anchor = "> `ui_honesty_contract` 는 세 단계로 늘었다."
assert anchor in s
add = (
    "> **18→19**: P40 Plan 1(v2 MUI 발주 상세)이 `/v2/manager/po/[poId]` 를 추가했다.\n"
    "> `app/(console)` 밖의 새 트리라 기존 D87 글롭이 못 잡아 `ui_honesty_contract.py` 의\n"
    "> `L2_GLOBS` 를 확장했다(36→43파일). 상세는 `docs/superpowers/plans/\n"
    "> 2026-08-20-ui-library-comparison-v2-plan1-mui-po.md`.\n>\n"
)
s = s.replace(anchor, add + anchor, 1)
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("CLAUDE.md 갱신 완료")
PY
```

Expected: `CLAUDE.md 갱신 완료` 출력. 실패(`AssertionError`)하면 지시한 대로 `grep` 으로 현재 앵커 문자열을 재확인해 스크립트의 `old`/`anchor` 값을 그 실측값으로 바꿔 재실행한다.

- [ ] **Step 8: Commit**

```bash
git add "frontend/app/v2/manager/po/[poId]/page.tsx" spikes/ui_honesty_contract.py CLAUDE.md
git commit -m "$(cat <<'EOF'
[M3] feat: P40 v2 Plan 1 Task 6 — 승인/반려 실연결 + D87 회귀 확장

승인/반려 버튼을 useApprovalQueueV2 의 approve()/reject() 에 연결했다 —
실제 백엔드 상태를 바꾼다. curl 로 POST /api/po/{id}/approve 계약을
재확인하고 재시드로 원복.

ui_honesty_contract.py 의 L2_GLOBS 에 app/v2/**/*.tsx·components/v2/*.tsx
2개를 추가해 v2 도 D87(UI 정직성) 자동 감시 대상이 되게 했다(36→43파일).
전건 통과 확인.

CLAUDE.md 프론트 라우트 기준선 18→19.

Sprint: P40 Plan 1 (MUI 발주 상세)
검증: tsc clean · next build(19라우트) · ui_honesty_contract 통과(L2 43파일) · ruff clean

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## 수동 확인 체크리스트 (자동 검증이 못 잡는 것)

Plan 1 완료 후 브라우저로 직접 확인할 것 — `uv run uvicorn backend.main:app --port 8003` + `cd frontend && npm run dev` 를 띄운 채:

- [ ] `http://localhost:3003/v2/manager/po/PO-0117` 접속 — MUI 기본 테마(파란 프라이머리 색)로 렌더되는지, v1 AppBar 가 안 보이는지 눈으로 확인
- [ ] 큐 목록에서 다른 항목 클릭 — URL 이 안 바뀌면서(주소창 `/v2/manager/po/PO-0117` 그대로) 우측 상세가 바뀌는지 확인(인라인 전환)
- [ ] `disposal`·`repair` 종류 항목 클릭 — "아직 없음" 안내가 뜨는지(크래시 안 남)
- [ ] 반려 버튼 → 사유 입력창 → 빈 채로 "반려 확정" 클릭 시 아무 일도 안 일어나는지(빈 사유 방지)
- [ ] 승인 버튼 클릭 → 스낵바 알림 뜨고 목록이 갱신되는지
- [ ] `http://localhost:3003/manager` (v1) 을 같은 브라우저에서 열어 **레이아웃·색상이 기존과 완전히 같은지** — v2 작업이 v1 을 조금도 건드리지 않았다는 최종 시각 확인
- [ ] 브라우저 개발자 도구 Console 에러 없는지(hydration mismatch 등 MUI+SSR 관련 경고 확인)

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-20-ui-library-comparison-v2-plan1-mui-po.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
