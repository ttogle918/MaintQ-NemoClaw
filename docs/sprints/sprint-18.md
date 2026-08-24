# Sprint 18 — 정비사 랜딩 화면 전환(챗봇 → 설비 대시보드)

**계획 작성일**: 2026-08-24 · **대상 스펙**:
`docs/superpowers/specs/2026-08-24-technician-landing-dashboard-design.md`(사용자 승인 완료,
107줄) + 스펙 작성 이후 대화에서 확정된 추가 사항(정렬 로직·이미지 재사용 방침·위치 표시
스코프 제외, 아래 각 태스크 명세에 반영) · **상태**: 계획만 — 코드 미착수

Sprint 17(재무부 승인+doc3)과 **독립**이다. 백엔드·DB·MCP 도구·API 신설이 전혀 없는
**프론트엔드 전용** 스프린트 — 라우팅 상수 1줄, 신규 컴포넌트 1개, 기존 화면 1개 확장이 전부다.

## 0. 선행 관계 그래프

```
Stage 1 (전체 3태스크 병렬 — 서로 다른 파일, 의존성 없음)
  MQ-1801 랜딩 라우팅 전환(role.ts)                        [독립]
  MQ-1802 챗 플로팅 버튼(ChatFab) 신설 + layout.tsx 삽입    [독립]
  MQ-1803 대시보드 카드: 정렬 + 이미지·인용문구·모델명       [독립]
```

세 태스크는 서로의 산출물을 참조하지 않는다(파일도, 함수 시그니처도 겹치지 않는다) — 계획
단계에서 발견한 유일한 함정은 "정렬 로직"과 "이미지 카드 확장"이 원래 사용자 대화에서는 별개
요구사항처럼 보였지만 **둘 다 같은 파일**(`equipment-status/page.tsx`)을 건드린다는 것이었다.
그래서 이 계획은 처음부터 **하나의 태스크(MQ-1803)로 합쳤다** — 두 태스크로 쪼개 병렬 실행하면
같은 파일에 대한 두 개의 diff가 충돌한다.

---

## 1. 스테이지 계획

### Stage 1 — 랜딩 전환 · 챗 FAB · 대시보드 카드 확장 (전체 병렬)

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1801 | 정비사 랜딩 라우팅을 `/technician/equipment-status`로 전환 | `frontend/lib/role.ts` | — |
| MQ-1802 | 챗 플로팅 버튼(ChatFab) 신설 + 콘솔 레이아웃 삽입 | `frontend/components/layout/ChatFab.tsx`(신규), `frontend/app/(console)/layout.tsx` | — |
| MQ-1803 | 대시보드 카드 — 우선순위 정렬 + 모델 이미지·인용문구·모델명 | `frontend/app/(console)/technician/equipment-status/page.tsx` | — |

### 스테이지 구성 근거

- **단일 스테이지인 이유**: 세 태스크가 건드리는 파일 집합이 완전히 분리된다 —
  `{lib/role.ts}` / `{components/layout/ChatFab.tsx, app/(console)/layout.tsx}` /
  `{app/(console)/technician/equipment-status/page.tsx}`. 세 집합 사이에 교집합이 없고, 어느
  태스크도 다른 태스크가 만드는 함수·상수를 import 하지 않는다(MQ-1802 의 `ChatFab` 은
  `ROLE_HOME.technician` 이 아니라 **리터럴 `"/technician"`** 을 쓴다 — 아래 MQ-1802 엣지
  케이스 참고. `ROLE_HOME.technician` 을 썼다면 MQ-1801 완료 후 그 값이 대시보드를 가리키게
  되어 챗봇으로 못 돌아가는 순환 참조가 생겼을 것이다). 독립적으로 검증 가능한 단위(정적
  검증 + 필요한 스위트)이자 병렬 실행이 안전한 단위라 두 스테이지로 나눌 근거가 없다.
- **이월 태스크 없음** — Sprint 17 은 완결됐고(`docs/sprints/sprint-17.md`, WIP 파일 없음),
  이 스프린트는 새 스펙에서 바로 시작한다.
- **사람 승인 대기 블로커 무관**: `error_codes` 사람 승인·`related_parts` 검수·
  `ANTHROPIC_API_KEY`·임베딩/벡터스토어 미결 — 넷 다 이 스프린트와 **완전히 무관**하다.
  진단 챗봇(`/technician`) 자체의 코드·URL·쿼리 파라미터는 한 글자도 안 바꾸고, 에이전트
  루프도 타지 않는다(순수 라우팅·정적 이미지 자산·클라이언트 정렬). 우회를 고민할 지점 자체가
  없었다.
- **라이브 서버 hang 블로커는 오늘 해소됨**(커밋 `46ef7e0`) — 각 태스크 DoD 에 "가능하면
  브라우저로 확인"을 권장으로 넣었다(필수 아님, `claude-in-chrome` 사용 가능 시).

---

## 2. 태스크별 상세 구현 명세

### MQ-1801 — 정비사 랜딩 라우팅을 `/technician/equipment-status`로 전환

- **복무 시나리오**: S1~S4 공용 — 정비사 콘솔의 진입 경로만 바뀌고, 각 시나리오의 도구
  오케스트레이션 로직은 한 글자도 안 바뀐다.
- **변경 파일**: `frontend/lib/role.ts` (수정, 1줄)
- **인터페이스**: `ROLE_HOME: Record<Role, string>` 의 타입 시그니처는 무변경. 값만 교체:
  ```ts
  export const ROLE_HOME: Record<Role, string> = {
    technician: "/technician/equipment-status",  // 기존 "/technician"
    manager: "/manager",
  };
  ```
- **핵심 로직**: 정확히 그 1줄만 교체한다. `ROLE_LABEL`·`ROLE_ICON`·`ROLE_USER_ID`·
  `ROLE_USER_NAME`·`roleFromPath`·`MANAGER_IDENTITIES` 등 파일의 나머지 전부는 무변경.
- **엣지 케이스**:
  - `frontend/app/page.tsx`(`redirect(ROLE_HOME.technician)`)와
    `frontend/components/layout/RoleTabs.tsx`(`href={ROLE_HOME[role]}`)는 이미 `ROLE_HOME`을
    간접 참조하므로 **코드 변경 없이** 새 타깃을 따라간다(grep으로 `ROLE_HOME` 참조 지점이
    이 둘뿐임을 확인 완료 — `frontend/lib/role.ts`·`app/page.tsx`·`RoleTabs.tsx` 3곳).
  - `/technician`(챗봇 전체화면, `?scenario=`·`?replay=`·`?prefill=`·`?equipment=` 쿼리 포함)
    라우트 파일 자체는 건드리지 않는다 — `docs/demo_script.md`·`frontend/README.md`가 이
    경로를 리터럴로 참조하므로 깨지면 안 된다(스펙 §2 에서 이미 grep 확인 완료, 이 태스크는
    재확인 불필요).
  - `frontend/README.md`가 `/` → `/technician` 리다이렉트를 표로 문서화하고 있다면(tool-builder
    현실성 평가에서 발견, grep으로 실행 시점에 확인할 것) 그 행을
    `/` → `/technician/equipment-status`로 함께 갱신한다 — 코드는 맞는데 README만 낡는
    CLAUDE.md가 반복 경고하는 패턴을 이 태스크 안에서 미리 막는다.
  - `roleFromPath()`는 `pathname.startsWith("/manager")` 여부만 보므로
    `/technician/equipment-status`에서도 그대로 `"technician"`을 반환한다 — 수정 불필요.
- **지켜야 할 결정**: 없음(순수 프론트 라우팅 상수 변경, 신규 D 결정 불필요 — 코드·DB·API
  계약을 건드리지 않는다).
- **DoD**:
  - `frontend/lib/role.ts` 의 `ROLE_HOME.technician`이 `"/technician/equipment-status"`.
  - `cd frontend && npx tsc --noEmit` 통과.
  - `cd frontend && npx next build` 통과, 라우트 수 **21개 그대로**(새 페이지 파일 없음).
  - `frontend/README.md`에 `/` 리다이렉트 대상을 표로 적어 둔 곳이 있으면 갱신됐는지 확인
    (위 엣지 케이스 참고).
  - 권장(필수 아님): `claude-in-chrome`으로 `/` 접속 시 `/technician/equipment-status`로
    리다이렉트되는지, AppBar "정비사" 탭 클릭 시 같은 경로로 이동하는지 확인.

### MQ-1802 — 챗 플로팅 버튼(ChatFab) 신설 + 콘솔 레이아웃 삽입

- **복무 시나리오**: S1~S4 공용(챗봇 진입 도구) — 직접적인 시나리오 로직은 없음.
- **변경 파일**:
  - `frontend/components/layout/ChatFab.tsx` (신규)
  - `frontend/app/(console)/layout.tsx` (수정 — `Shell` 안에 `<ChatFab />` 렌더 1줄 추가 +
    import 1줄)
- **인터페이스**:
  ```ts
  export function ChatFab(): React.ReactNode
  ```
  props 없음 — 컴포넌트 내부에서 `usePathname()`(가시성 판단)과 `getPoQueue("technician",
  "draft")`(배지 카운트)를 자체 호출한다. `layout.tsx`의 `Shell`은 이 컴포넌트를 무조건
  렌더한다(가시성 조건은 `ChatFab` 내부에 있다 — `Shell`은 `pathname`을 알 필요가 없다).
- **핵심 로직**:
  1. `"use client"` 컴포넌트. `usePathname()`(next/navigation), `useEffect`/`useState`(React),
     `getPoQueue`(`@/lib/api`), `roleFromPath`(`@/lib/role`), `Link`(next/link), `sx`(`@/lib/sx`)
     를 import.
  2. **Hooks는 항상 호출**하고 가시성 판단은 **hooks 이후**에 조건부 `return null`로 처리한다
     (React hooks 규칙 — 조건부 이전에 return 하지 않는다):
     ```tsx
     export function ChatFab() {
       const pathname = usePathname();
       const [draftCount, setDraftCount] = useState<number | null>(null);

       useEffect(() => {
         let alive = true;
         getPoQueue("technician", "draft")
           .then((items) => { if (alive) setDraftCount(items.length); })
           .catch(() => { if (alive) setDraftCount(null); });
         return () => { alive = false; };
       }, []); // Shell 마운트 시 1회만 — pathname 을 deps 에 넣지 않는다(스펙 §4-3 "폴링 없음")

       if (roleFromPath(pathname) !== "technician" || pathname === "/technician") return null;

       return (
         <Link
           href="/technician"
           aria-label="진단 챗봇 열기"
           style={sx(
             "position:fixed;right:24px;bottom:24px;z-index:30;width:56px;height:56px;" +
               "border-radius:50%;background:var(--blue);color:#fff;display:flex;" +
               "align-items:center;justify-content:center;box-shadow:0 4px 14px rgba(0,0,0,.25);" +
               "text-decoration:none;font-size:24px"
           )}
         >
           💬
           {draftCount !== null && draftCount > 0 && (
             <span
               style={sx(
                 "position:absolute;top:-4px;right:-4px;min-width:18px;height:18px;padding:0 4px;" +
                   "border-radius:9px;background:var(--orange);color:#fff;display:flex;" +
                   "align-items:center;justify-content:center;font:700 10px 'JetBrains Mono',monospace"
               )}
             >
               {draftCount}
             </span>
           )}
         </Link>
       );
     }
     ```
  3. `layout.tsx`의 `Shell` 함수 리턴 JSX 안, `<AppBar .../>`와 콘텐츠 `<div>` 사이 또는
     콘텐츠 `<div>` 뒤(형제 요소)에 `<ChatFab />`를 추가한다. `position:fixed`라 DOM 위치는
     렌더 결과에 영향 없음 — 어느 쪽에 둬도 무방하나 코드 가독성상 `AppBar` 뒤가 자연스럽다.
- **엣지 케이스**:
  - `getPoQueue` 실패(네트워크 오류 등) → `draftCount`를 `null`로 유지 → 배지 숨김. **에러를
    숫자 0으로 위장하지 않는다**(스펙 §4-3, D87 — tool-builder 현실성 평가에서 인용 번호
    오귀속 발견해 정정: 원래 D62로 적었으나 D62는 처분 판정 `HOLD`/`INSUFFICIENT_FACTS`
    구분이라 배지·카운트와 무관하다).
  - `draftCount === 0` → 배지를 그리지 않는다(조건식이 `draftCount > 0`이므로 자동 충족).
  - 매니저 화면(`/manager/*`)에서는 `roleFromPath(pathname) !== "technician"`이라 렌더가
    `null` — 그러나 `useEffect`는 hooks 규칙상 여전히 실행되어 **fetch는 항상 1회 일어난다.**
    이건 의도적이다 — `Shell`이 `/technician`·`/manager` 공유 레이아웃이고 라우트 이동 시
    리마운트되지 않으므로, 매니저로 세션을 시작해도 세션당 추가 API 호출은 **1회뿐**이다
    (폴링 없음 요건과 충돌하지 않는다). 이 사실을 컴포넌트 상단 주석으로 남길 것.
  - `/technician`(챗봇 페이지, 쿼리 파라미터 무관 — `usePathname()`은 쿼리스트링을 포함하지
    않는다) → 렌더 `null`.
  - **`Link href` 는 반드시 리터럴 문자열 `"/technician"`이어야 한다** — `ROLE_HOME.technician`
    을 쓰면 MQ-1801 이후 그 값이 `/technician/equipment-status`를 가리키므로 챗봇으로 돌아가는
    버튼이 대시보드로 돌아가는 버튼이 되어버린다(스펙 §4-2 "클릭 시 `/technician`으로 `Link`
    이동"을 문자 그대로 지킬 것).
- **지켜야 할 결정**: **D87**(배지에는 실측값만 — draft 발주 수는 `/api/po?state=draft`의
  실제 길이, 위 엣지케이스 정정 참고) · **D41**(SSE 대화는 저장하지 않으므로 "안 읽음 메시지"
  개념 자체가 없다 — 그래서 배지가 "안 읽음"이 아니라 "정비사의 다음 조치를 기다리는 draft
  발주 수"로 정직하게 재정의된 값임을 코드 주석에 남길 것).
- **DoD**:
  - `cd frontend && npx tsc --noEmit` 통과.
  - `cd frontend && npx next build` 통과, 라우트 수 21개 그대로(신규 페이지 파일 아님).
  - `ChatFab.tsx` 자신은 `spikes/ui_honesty_contract.py`의 `L2_GLOBS`
    (`components/asset/*.tsx` · `components/queue/Decision*.tsx` · `app/(console)/**/*.tsx`)
    어디에도 해당하지 않는다(`components/layout/`는 스캔 대상이 아님, 기존
    `components/chat/A2aResultCard.tsx`와 같은 의도적 사각지대).
  - ⚠️ **그러나 이 태스크가 함께 수정하는 `frontend/app/(console)/layout.tsx`는
    `app/(console)/**/*.tsx` 글롭에 실제로 걸린다**(tool-builder 현실성 평가에서 발견 —
    `ChatFab.tsx`만 스캔 밖이라고 안심하면 안 됨). `DATABASE_URL=...
    uv run python spikes/ui_honesty_contract.py` **전건 PASS 필수** — `<ChatFab />` 삽입
    한 줄이 L2 규칙(상태 문자열 직접 비교 등) 위반을 새로 만들지 않는지 이 스위트로 반드시
    확인할 것.
  - 권장(필수 아님): `claude-in-chrome`으로 `/technician/equipment-status`·설비 상세·
    `/technician/asset` 등 정비사 화면에서 우하단 버튼이 뜨고, 클릭 시 `/technician`으로
    이동하는지, `/manager`·`/technician`(챗봇 페이지) 자체에서는 버튼이 안 뜨는지 확인.

### MQ-1803 — 대시보드 카드: 우선순위 정렬 + 모델 이미지·인용문구·모델명

- **복무 시나리오**: S1~S4 공용 진입점. 특히 정렬 로직은 S3(반복 고장·이상 신호를 가진 설비를
  먼저 보여줌)의 취지와 가장 맞닿아 있다 — "출근하자마자 오늘 할 일 순서대로" 보고 싶다는
  사용자 의도를 반영한다.
- **변경 파일**: `frontend/app/(console)/technician/equipment-status/page.tsx` (수정) —
  정렬 로직과 카드 확장을 **하나의 태스크로 합친다**(같은 파일을 두 태스크가 병렬로 건드리면
  충돌하므로).
- **인터페이스**: 외부에 노출되는 컴포넌트 시그니처는 무변경
  (`export default function EquipmentStatusListPage()`,
  `EquipmentRow({ asset, status }: { asset: ApiAsset; status: ApiHotspotStatus | undefined })`).
  파일 내부에 순수 함수 3개를 신설(다른 파일로 빼지 않는다 — 이 화면 전용 로직이라 굳이
  `lib/`에 새 공유 모듈을 만들 필요가 없고, `lib/*.ts` 신설은 `ui_honesty_contract`의 L1
  게이트 대상 목록에 새로 편입될지 여부를 판단해야 하는 불필요한 부담을 만든다):
  ```ts
  function countHotspotColors(
    status: ApiHotspotStatus | undefined
  ): { red: number; orange: number; blue: number };

  function rankAsset(
    asset: ApiAsset,
    status: ApiHotspotStatus | undefined
  ): { tier: number; tierCount: number; totalCount: number };

  function compareAssets(
    a: ApiAsset,
    b: ApiAsset,
    statusByAsset: Map<string, ApiHotspotStatus>
  ): number;
  ```
  `import { useMemo } from "react"`를 기존 `useEffect, useState` import 줄에 추가한다.
- **핵심 로직**:
  1. **`countHotspotColors`**: 기존 `EquipmentRow` 내부에 있던
     `for (const p of parts) { ... }` 카운팅 루프를 이 함수로 추출한다. `EquipmentRow`는 이
     함수를 호출해 `counts`를 얻도록 리팩터(렌더 로직은 그대로, 카운팅만 공유).
  2. **`rankAsset`** — 정렬 우선순위 등급을 계산한다:
     ```ts
     function rankAsset(asset, status) {
       if (status?.status !== "ok") return { tier: 4, tierCount: 0, totalCount: 0 };
       const c = countHotspotColors(status);
       const total = c.red + c.orange + c.blue;
       if (c.red > 0) return { tier: 0, tierCount: c.red, totalCount: total };
       if (c.orange > 0) return { tier: 1, tierCount: c.orange, totalCount: total };
       if (c.blue > 0) return { tier: 2, tierCount: c.blue, totalCount: total };
       return { tier: 3, tierCount: 0, totalCount: 0 }; // 정상
     }
     ```
     tier 낮을수록 먼저 노출: **0=🔴 있음 → 1=🟠만 있음 → 2=🔵만 있음 → 3=정상 → 4=상태
     미상/로딩 중/조회 실패**.
  3. **`compareAssets`** — tier 오름차순 → (tier 0~2 한정) `tierCount` 내림차순 →
     (동차) `totalCount` 내림차순 → 최종 타이브레이크 `asset.asset_id.localeCompare()` 오름차순
     (항상 결정적 순서를 보장해 리렌더 시 깜빡임 방지):
     ```ts
     function compareAssets(a, b, statusByAsset) {
       const ra = rankAsset(a, statusByAsset.get(a.asset_id));
       const rb = rankAsset(b, statusByAsset.get(b.asset_id));
       if (ra.tier !== rb.tier) return ra.tier - rb.tier;
       if (ra.tier <= 2) {
         if (rb.tierCount !== ra.tierCount) return rb.tierCount - ra.tierCount;
         if (rb.totalCount !== ra.totalCount) return rb.totalCount - ra.totalCount;
       }
       return a.asset_id.localeCompare(b.asset_id);
     }
     ```
  4. `EquipmentStatusListPage`에서 `assets.map(...)` 직전에:
     ```ts
     const sortedAssets = useMemo(
       () => (assets ? [...assets].sort((a, b) => compareAssets(a, b, statusByAsset)) : []),
       [assets, statusByAsset]
     );
     ```
     렌더는 `assets.map(...)` 대신 `sortedAssets.map(...)`로 교체.
  5. **모델 이미지 + 인용문구** (`EquipmentRow` 좌측에 썸네일 블록 추가, `@/lib/hotspots`에서
     `MODEL_BASE_IMAGE`·`MODEL_CITATION` import — 신규 이미지 자산 제작 없음, 원본 PNG
     그대로 CSS로 축소):
     ```tsx
     const model = status?.model;
     const baseImage = model ? MODEL_BASE_IMAGE[model] : undefined;
     const citation = model ? MODEL_CITATION[model] : undefined;
     ```
     - `model === undefined`(로딩 중 또는 조회 실패) → 44×44px 스켈레톤 박스만
       (`background:var(--sw);border-radius:6px`), 이미지도 인용문구도 없음.
     - `model`은 있는데 `MODEL_BASE_IMAGE[model]`이 없음(IE5, D109 — 안전 문구·RAG 청킹과
       같은 이유로 이 하이라이트 좌표도 iG5A·S100만 커버) → 중립 아이콘(예: `⚙` 텍스트
       글리프, 44×44 flex 중앙정렬, `color:var(--dim2)`), 인용문구 없음. 현재 시드에
       `equipment.model='IE5'` 인스턴스가 없어(CHECK 제약 2종 유지) 실사용에서 도달하지
       않는 방어적 분기 — 코드 주석에 그렇게 남길 것.
     - `baseImage`가 있음(iG5A·S100) →
       ```tsx
       <div style={sx("display:flex;flex-direction:column;gap:2px;width:44px;flex-shrink:0")}>
         {/* eslint-disable-next-line @next/next/no-img-element -- 크롭된 정적 자산, 최적화 불필요 */}
         <img
           src={baseImage}
           alt={`${model} 도면`}
           style={sx("width:44px;height:44px;object-fit:cover;border-radius:6px;border:1px solid var(--line)")}
         />
         <span style={sx("font:8.5px 'Pretendard';color:var(--dim2);line-height:1.2")}>{citation}</span>
       </div>
       ```
       (`EquipmentHotspotDiagram.tsx`의 기존 `<img>` 태그 관례 그대로 재사용 — `next/image`
       미사용, eslint 억제 주석도 동일 패턴.)
  6. **모델명 텍스트**: 기존 "라인 X" `<span>` 옆에 `model`이 있을 때만 추가:
     ```tsx
     {status?.model && <Mono size={11}>{status.model}</Mono>}
     ```
     `model`이 없으면(로딩/실패) 아무것도 렌더하지 않는다 — 지어내지 않는다.
  7. **기존 유지(스펙 §3-3)**: 🔴🟠🔵 배지, 라인 위치, "확인 중…"/"상태 미상" 분기는 로직
     변경 없이 그대로 둔다. `EquipmentRow`의 리턴 JSX 구조에 위 5·6번 요소를 끼워 넣는 것
     뿐이다.
- **엣지 케이스**:
  - `status === undefined`인 동안(로딩 중)에는 모든 자산이 tier 4로 묶여 원래 fetch 순서를
    유지한다. `getAssets`→`Promise.all(getHotspotStatus...)` 뒤 `statusByAsset`를 한 번에
    통째로 `setState`하는 기존 구조(29~41번째 줄)상 "일부만 로드된" 중간 상태가 사실상
    존재하지 않는다 — 정렬이 깜빡일 소지가 낮다(기존 구조를 바꾸지 않으므로 이 전제도
    그대로 유지됨).
  - `status.status !== "ok"`(조회 실패)면 모델이 있어도(드묾) tier 4로 취급한다 — 정렬
    등급 판단은 하이라이트 상태(`status.status`) 기준이지 모델 정보 유무 기준이 아니다.
    다만 이미지·모델명 표시는 `model` 값 유무만으로 독립 판단하므로, "상태 미상"이어도
    모델 정보가 있으면 이미지는 뜰 수 있다(하이라이트 배지와 모델 이미지는 서로 다른
    정보이므로 별도 판단이 정직성 위반이 아니다).
  - `MODEL_BASE_IMAGE[model]`이 없는 경우(IE5) — 위 5번 분기, 실사용 미도달.
  - **"N번째 기계" 위치 세부 표시는 이번 스코프 밖**이다 — `ApiAsset`에는 `line_id`(숫자)만
    있고 "그 라인의 몇 번째 기계"인지 나타내는 필드가 없다(`frontend/lib/api.ts:432-446`
    확인 완료). 스펙의 "새 백엔드·API 신설 없음" 제약(§1)을 지키려면 이 필드를 새로 만들 수
    없으므로, 기존 `line_id`+`asset_id`+`asset.name`만으로 위치를 표시하고 세부 위치는
    **의도적으로** 다루지 않는다.
- **지켜야 할 결정**: **D87**(정직성 원칙의 연장 — 이미지·모델명은 실측 `status.model`이
  있을 때만 표시하고, 없으면 지어내지 않는다는 것이 이 태스크의 모든 조건부 렌더 분기가
  따르는 공통 원칙이다) · 스펙 §3-1(LS ELECTRIC 매뉴얼 도면 원본 라이선스 인용 의무 —
  이미지가 뜨는 카드에는 인용문구가 **항상** 함께 뜬다, 이미지만 있고 인용문구가 빠지는
  경로를 만들지 말 것).
- **DoD**:
  - `cd frontend && npx tsc --noEmit` 통과.
  - `cd frontend && npx next build` 통과, 라우트 수 21개 그대로.
  - `uv run python spikes/ui_honesty_contract.py` **PASS**(이 파일은 `L2_GLOBS`의
    `app/(console)/**/*.tsx`에 이미 편입돼 있다 — 수정 후 L2 6항목 재검증 필수, 신규 D87
    위반 없어야 한다. 특히 상태 문자열을 직접 비교하는 신규 코드를 넣지 않았는지 — 이 태스크는
    `status.status`를 `!== "ok"`로 비교하는 **기존** 패턴만 재사용하고 `state`/`decision` 류
    3항 비교를 새로 만들지 않으므로 해당 없을 가능성이 높지만, 실행해서 실측 확인할 것).
  - 권장(필수 아님): `claude-in-chrome`으로 `/technician/equipment-status` 접속 —
    🔴 있는 자산이 최상단, 그다음 🟠, 그다음 🔵, 정상/미상이 하단에 오는지. 카드마다 모델
    이미지·인용문구(작은 글자)·모델명이 보이는지. 새로고침 여러 번 해도 같은 등급 안 순서가
    안정적인지(최종 타이브레이크 `asset_id` 확인).

## 현실성 평가

평가 방법: 계획 문서의 모든 파일·심볼·시그니처 주장을 코드베이스에서 직접 읽어 대조했다
(`frontend/lib/role.ts`·`RoleTabs.tsx`·`app/page.tsx`·`equipment-status/page.tsx`·`lib/api.ts`·
`lib/hotspots.ts`·`EquipmentHotspotDiagram.tsx`·`app/(console)/layout.tsx`·
`spikes/ui_honesty_contract.py`·`docs/10_DECISIONS.md`·`docs/05_DB_SCHEMA.md`·
`frontend/README.md`·`docs/demo_script.md`). 코드는 작성하지 않았다.

| 스테이지 | TASK | 리스크 | 제안 |
|---------|------|--------|------|
| 1 | MQ-1801 | **없음(검증 완료)** — `ROLE_HOME` 참조 지점이 정확히 3곳(`role.ts`·`app/page.tsx`·`RoleTabs.tsx`)임을 grep으로 재확인. `roleFromPath`는 `/manager` 접두어만 보므로 무영향. 스파이크 중 `ROLE_HOME`·`"/technician"` 리다이렉트 타깃을 하드코딩 단언하는 곳 없음(grep 0건) — 회귀 블라스트 반경 0 | 그대로 진행 가능 |
| 1 | MQ-1801 | **경(문서 드리프트, 계획에 누락)** — `frontend/README.md`가 `/` → `/technician` 을 리터럴로 문서화한 라우트 표(10·20·21·33행)를 갖고 있는데, 이 값이 MQ-1801 이후 사실과 어긋나게 된다. 계획은 `docs/demo_script.md`·`README.md`가 "`/technician?scenario=` 리터럴 경로를 참조하므로 안 깨져야 한다"는 **반대 방향**만 확인했고, README 자신의 라우트 표가 낡는 문제는 다루지 않았다 | MQ-1801 DoD에 `frontend/README.md` 라우트 표 1줄(`/` 행) 갱신을 추가할 것(코드 영향 없는 사소한 수정이지만 CLAUDE.md가 반복 지적하는 "문서 낡음" 패턴을 이 스프린트가 그대로 재생산하지 않도록) |
| 1 | MQ-1802 | **없음(검증 완료)** — `components/layout/`는 `L2_GLOBS`(`components/asset/*.tsx`·`components/queue/Decision*.tsx`·`app/(console)/**/*.tsx`) 어디에도 없음을 실제 파이썬 glob 실행으로 재확인(스캔 대상 39개 목록에 `ChatFab.tsx` 미포함). `getPoQueue(role, state="pending")` 시그니처가 `getPoQueue("technician","draft")` 호출·`.then(items=>items.length)` 패턴과 정확히 일치(내부에서 `.items`를 이미 벗겨 배열을 resolve함, 이중 래핑 아님). `<img>` eslint-disable 주석 패턴이 `EquipmentHotspotDiagram.tsx`의 기존 선례와 문자 그대로 동일 | 그대로 진행 가능 |
| 1 | MQ-1802 | **경(검증 누락, DoD 보강 필요)** — `app/(console)/layout.tsx`는 `app/(console)/**/*.tsx` 글롭에 **실제로 걸린다**(직접 glob 실행으로 확인, `L2_FILES_FLOOR=42`에 이미 포함된 파일). MQ-1802가 이 파일을 수정하는데도 DoD는 "`ChatFab.tsx`는 L2_GLOBS 밖... 신규 회귀 스위트를 만들지 않는다"만 적어, 정작 **수정 대상인 layout.tsx가 이미 L2 스캔 대상**이라는 사실을 다루지 않는다. 실질 위험은 낮다 — 추가되는 코드가 `<ChatFab />` JSX 한 줄뿐이고 L2_RULES 6종(확인됨/VERIFIED 리터럴·`--green`/`--ok` 토큰·`state ===`·`STATE_WORDS` 어휘 비교·어휘 키 지역 맵)에 걸릴 토큰이 전혀 없음을 규칙 정규식 대조로 확인했다 | MQ-1802 DoD에 `uv run python spikes/ui_honesty_contract.py` **PASS**(스캔 파일 수 42 그대로, 신규 D87 위반 없음)를 명시적으로 추가할 것 — MQ-1803만 이 커맨드를 갖고 있고 layout.tsx를 건드리는 MQ-1802엔 없는 게 비대칭이다 |
| 1 | MQ-1803 | **없음(검증 완료)** — 현재 `EquipmentRow`의 카운팅 루프·`status.status !== "ok"` 분기·props 시그니처가 명세와 정확히 일치. `ApiHotspotStatus.model?: string` 존재 확인. `MODEL_BASE_IMAGE`/`MODEL_CITATION`이 `lib/hotspots.ts`에서 export됨을 확인. `STATE_WORDS`(L2 규칙 대상 어휘 목록)에 `"ok"`가 없고 `state ===` 정규식은 식별자 `state`만 잡아 `status.status !== "ok"` 는 매칭 대상이 아님을 직접 규칙 코드로 확인 — "기존 패턴 재사용, 신규 D87 위반 아님" 주장이 근거가 있다. `equipment.model` CHECK가 여전히 `'iG5A'\|'S100'` 2종(`docs/05_DB_SCHEMA.md:69`)임을 확인해 IE5 방어분기가 "실사용 미도달"이라는 주장도 사실 | 그대로 진행 가능 |
| 1 | 전체 | **없음** — 세 파일 집합(`{lib/role.ts}` / `{components/layout/ChatFab.tsx, app/(console)/layout.tsx}` / `{equipment-status/page.tsx}`)이 서로 겹치지 않음을 직접 대상 파일 3개를 모두 읽어 재확인. 심볼 의존 방향도 단방향(MQ-1802가 `roleFromPath`·`getPoQueue`를 소비하지만 역방향 없음)이라 병렬 실행 시 diff 충돌 가능성 없음 | 단일 스테이지 유지 |
| — | 인용 정확성 | **경(계획 문서 오류, 코드 영향 없음)** — MQ-1802의 "지켜야 할 결정"이 배지=실측값 원칙을 **D62**로 인용했으나, `docs/10_DECISIONS.md`의 실제 D62는 처분 판정의 `HOLD`/`INSUFFICIENT_FACTS` 별도 상태 구분(D50과 연결된 "0행을 not_found로 처리하면 안 된다"는 논지)이며 배지·카운트와 무관하다. 문서 전체에 "배지"라는 단어 자체가 D62 주변에 없음(grep 확인). 원칙 자체(지어내지 않는다)는 옳지만 인용 번호가 틀렸다 | MQ-1802 명세의 "D62" 표기를 **D87**(UI 정직성 규약 — 미확인 상태를 확인됨으로 위장 금지, 실측 확인)로 정정하거나 D-번호 없이 원칙만 서술할 것. 기능 구현에는 영향 없으나 향후 D62를 grep하는 사람이 오도됨 |
| — | 승인 대기 블로커 | **없음(검증 완료)** — 세 태스크 모두 기존 엔드포인트(`getAssets`·`getHotspotStatus`·`getPoQueue`)만 재사용하고 `lookup_error_code`·RAG·에이전트 루프·`related_parts`·임베딩 경로를 코드 레벨에서 전혀 참조하지 않음을 직접 확인(정렬·이미지·FAB은 순수 클라이언트 로직). `error_codes` 미승인·벡터스토어 미결과 무관하다는 PM 판단이 맞다 | 무관 판단 유지 |
| — | D-결정 충돌 | **없음** — D87(정직성, `model`/`draftCount`가 없을 때 렌더 안 함)·D62(오귀속, 위 항목 참고)·D41(SSE 미저장 → 배지를 "다음 조치 대기 draft 수"로 재정의) 모두 계획의 실제 조건부 렌더 분기와 부합. 새 계약(MCP 도구·API·DB) 변경이 없으므로 신규 D-결정 불필요하다는 판단도 맞다 | 신규 D-결정 불필요 판단 유지 |

### 평가 결론
- 계획 수정 필요: **Y (경미)**

세 태스크의 핵심 구현 명세(파일 경로·인터페이스·정렬 알고리즘·엣지케이스)는 전부 코드베이스
실측과 정확히 일치했고 기능적 블로커는 발견되지 않았다 — Stage 1 병렬 배치, 파일 비충돌,
사람 승인 무관 판단 전부 확정 가능한 수준이다. 다만 커밋 전에 반영하면 좋을 경미한 수정 2건이
있다:

1. MQ-1801 DoD에 `frontend/README.md` 라우트 표(`/` 행) 갱신 1줄 추가 — 안 하면 이 스프린트가
   끝나자마자 README가 낡은 문서가 된다(CLAUDE.md가 반복 경고하는 패턴).
2. MQ-1802 DoD에 `uv run python spikes/ui_honesty_contract.py` PASS(스캔 42개, 신규 위반 0) 확인
   항목을 명시적으로 추가 — 이 태스크가 수정하는 `app/(console)/layout.tsx`가 이미 L2 스캔
   대상임에도 계획에는 검증 커맨드가 빠져 있다(실질 위험은 낮다고 판단되지만 `/stage`의
   eval-runner가 이 스위트를 돌릴 근거를 계획 문서 안에 명시해 두는 편이 안전하다).
3. (선택) MQ-1802 명세의 "D62" 인용을 "D87"로 정정 — 기능에는 영향 없음.

이 세 건은 태스크 설계 자체를 바꾸는 게 아니라 각 TASK의 DoD 체크리스트에 문구를 추가/정정하는
수준이라, PM 재작업 없이 `/stage` 진행 중 tool-builder가 DoD를 따르면서 함께 처리해도 무방하다.

---

## 계획 확정

**확정일**: 2026-08-24

위 3건 전부 태스크 명세에 직접 반영 완료 — MQ-1801 DoD에 README 라우트 표 갱신 항목 추가,
MQ-1802 DoD에 `ui_honesty_contract.py` PASS 확인 항목(및 `layout.tsx`가 L2 스캔 대상이라는
경고) 추가, MQ-1802 "지켜야 할 결정"의 D62→D87 인용 정정. 계획 수정 완료.

**3개 태스크(MQ-1801~1803) 전부 착수 가능한 상태다.**

실행: `/stage 1`

---

### Stage 1 완료 (2026-08-24) — Sprint 18 유일·마지막 스테이지

**커밋**: `bf781e0` — `[M4] feat: Sprint 18 — 정비사 랜딩 화면 전환(챗봇→설비 대시보드) + doc3 계획 문서`
(커밋 제목의 "+ doc3 계획 문서"는 복붙 오기 — Sprint 17과 무관, 실제 변경분은 본문 그대로
정비사 랜딩 대시보드뿐. 로컬 단일 커밋이라 기능에 영향 없음)

#### MQ-1801 — 랜딩 라우팅 전환
- `frontend/lib/role.ts`(`ROLE_HOME.technician` 1줄) · `frontend/README.md`(라우트 표+주석
  2곳, 명세보다 범위를 넓혀 갱신 — reviewer가 "문서 드리프트를 능동적으로 막은 것"으로 확인)

#### MQ-1802 — ChatFab 신설
- `frontend/components/layout/ChatFab.tsx`(신규) · `app/(console)/layout.tsx`(삽입 2줄)
- 핵심 함정(`Link href`가 `ROLE_HOME.technician`을 참조하면 MQ-1801 이후 순환참조) 회피를
  reviewer가 코드로 직접 확인

#### MQ-1803 — 대시보드 카드 정렬+이미지
- `technician/equipment-status/page.tsx`에 `countHotspotColors`·`rankAsset`·`compareAssets`
  3개 순수함수, 정렬(🔴→🟠→🔵→정상→미상, 타이브레이크까지) + 카드 이미지(PNG 원본 재사용)+
  인용문구+모델명. `ui_honesty_contract` 291/291 자체 확인 후 통합

**eval-runner 종합**: seed 41/41(error_codes 70) · sp2_mcp_roundtrip 20/20(소켓 고갈 재시도
후 해소) · write_tool_contract 30/30 · api_contract 52/52(변동 없음) · sp3_sse_events
22/22(소켓 고갈 재시도 후 해소) · ruff clean · tsc clean · next build 21라우트(신규 없음) ·
ui_honesty_contract 291/291.

**reviewer 게이트**: PASS(블로커 없음). 5개 핵심 확인 항목(순환참조 회피·D87 3분기·정렬
알고리즘 명세 일치·hooks 규칙·README 갱신 범위) 전부 코드 직접 대조로 확인.

## Sprint 18 완료

**유일 스테이지 완료.** 정비사 콘솔 첫 화면이 챗봇에서 설비 하이라이트 대시보드로 바뀌고,
이상탐지 우선순위 정렬·모델 이미지 카드·챗 플로팅 버튼이 전부 연결됨. 백엔드·DB·API 신설
0건 — 순수 프론트 전용 스프린트가 계획대로 끝났다.

**다음**: 브라우저 QA(claude-in-chrome)로 실제 정렬 순서·카드 이미지·ChatFab 동작을
사용자에게 보여줄 것(설계 배경이 된 원 요청이라 시각 확인이 특히 중요).

### 브라우저 QA 완료 (2026-08-24, claude-in-chrome)

로컬 격리 백엔드(:8897)+프론트(:3000)로 확인. `/` → `/technician/equipment-status` 리다이렉트
정상, ChatFab 우하단 노출 정상.

**정렬 알고리즘 실측 검증** — 9개 자산 중 상위 5개 순서: `AST-L3-EXFAN`(🔴1🟠2, tier0·total3)
→ `AST-L3-LIFT`(🔴1🟠2, tier0·total3, `EXFAN`<`LIFT` 타이브레이크) → `AST-L1-CONV`(🔴1🟠1,
tier0·total2) → `AST-L2-CLNT`(🔴1🟠1, tier0·total2, `L1`<`L2` 타이브레이크) →
`AST-L3-CONV`(🔴1🟠1) — `compareAssets`가 설계한 tier→개수→asset_id 규칙과 실측이 정확히
일치.

**알려진 제약(사용자 확인·수용, 2026-08-24)**: `MODEL_BASE_IMAGE` 원본 PNG(부위별 클릭
다이어그램)를 44px 카드 썸네일로 축소하면 세부가 뭉개져 노이즈처럼 보인다 — 미리 우려했던
그대로 실측 확인됨. 사용자 결정: **지금은 그대로 배포, 나중에 실제 사용 피드백 보고 개선**
(작은 아이콘+색상 대체 / 신규 일러스트 제작 둘 다 후보로 남겨 둠, 이번 스프린트 스코프
아님). 코드 변경 없음 — 이대로 최종.
