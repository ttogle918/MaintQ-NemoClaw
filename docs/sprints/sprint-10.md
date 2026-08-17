# Sprint 10 — 근거 번들/지출 분류 화면 + 수리 증빙 승인 큐 상세

**상태**: Stage 2 완료(2026-08-18). 다음은 `/stage 3`(MQ-1004).

## Stage 1 완료 (2026-08-18)

**커밋**: `1a5fd89` — `[M3] 근거 번들/지출 분류 화면 + 수리 증빙 승인 큐 상세 (P37·P38)`

#### MQ-1001 — 근거 번들 화면 + 지출 분류 독립 페이지
- 구현 파일: `frontend/components/asset/EvidenceBundlePanel.tsx`·`ExpenditureForm.tsx`(신규),
  `frontend/app/(console)/technician/asset/[assetId]/evidence/page.tsx`·
  `frontend/app/(console)/manager/expenditure/page.tsx`(신규), `DisposalPanel.tsx`·`ExpenditureCard.tsx`·
  `DecisionDetail.tsx`(export 추가만), `frontend/lib/decisionView.ts`(신규 함수), disposal page.tsx(링크 1개)
- 회귀: tsc 클린 · build 통과

#### MQ-1002 — 승인 큐 kind:"repair" 상세
- 구현 파일: `frontend/lib/queueState.ts`(`STATE_LABEL.repair` 채움 + `isPendingState`),
  `frontend/lib/mappers.tsx`(`repairStateView`를 `stateView` 위임으로 단순화, `REPAIR_STATE_LABEL` 삭제),
  `frontend/components/queue/RepairDetail.tsx`(신규), `ApprovalQueueScreen.tsx`(repair 분기 추가)
- 리뷰 1차 FAIL — 승인 큐 목록에서 repair 항목이 `detailHref` 없음으로 클릭 불가(전용 라우트 없음). 수정:
  `frontend/app/(console)/manager/repair/[repairId]/page.tsx` 신설 + `detailHref()`에 한 줄 추가 → 재검토 PASS
- 부수 수정: `frontend/lib/__checks__/ui_honesty.ts`의 L1-9 픽스처가 "repair/pending은 맵 밖"이라는 이제는
  깨진 가정을 갖고 있어 `repair/archived`로 교체(Sprint 8이 비워 뒀던 `STATE_LABEL.repair`를 이번에 채운 결과,
  옛 오라클이 낡은 것이지 새 코드의 결함이 아님)
- 회귀: tsc 클린 · build 통과 · `ui_honesty_contract.py` 200계약+16게이트/뮤턴트/메타 전부 PASS

**실측 라우트 수**: 16개(`npx next build` 출력 기준, `/`·`/_not-found` 포함) — 계획 문서의 "13개" 예상은
계획 작성 시점 기준선 오차(11→12)로 어긋났었다. MQ-1004가 정확한 수치로 문서를 갱신할 것.

**미해결(경미, 후속)**: `frontend/components/queue/QueueList.tsx:61-63`의 "repair는 착지점이 없다" 주석이
이제 낡았다 — 다음에 이 파일을 만질 때 갱신 권장(리뷰어 지적, 커밋 차단 아님).

## Stage 2 완료 (2026-08-18)

**커밋**: `213b62d` — `[M3] ui_honesty_contract.py L2 확장 — RepairDetail.tsx 편입 + D87 위반 해소 (MQ-1003)`

#### MQ-1003 — L2 확장 (RepairDetail 편입 + 하한 실측 갱신)
- 구현 파일: `spikes/ui_honesty_contract.py`(`L2_EXTRA`에 `RepairDetail.tsx` 등재, `L2_FILES_FLOOR` 26→32 실측
  갱신, 낡은 주석 정정)
- **Stage 1에서 미발견이던 실제 D87 위반 1건을 이 스테이지가 발견**: `RepairDetail.tsx`의 `HashVerified`가
  `--ok-tx` 색 토큰을 직접 사용 — `RepairDetail.tsx`가 이번에 처음 L2 스캔에 편입되며 드러났다(예상된 결과 —
  `InventoryDrawer.tsx`·`equipment-status` 목록 페이지에서 같은 세션에 두 번 반복된 패턴과 동일 유형). `--blue-tx`
  (정보 톤)로 교체해 해소 — 코드 파일 1줄 변경(`frontend/components/queue/RepairDetail.tsx`)
  이 태스크에 딸려 커밋됐다.
- 뮤턴트 양성 검증(상태 어휘 직접비교 임시 주입 → FAIL 확인 → 원복) 완료
- 회귀: `ui_honesty_contract.py` 206계약+16게이트/뮤턴트/메타 전부 PASS · tsc clean

## 배경

Sprint 9 §9-1 에서 규모 압축을 위해 **MQ-915**(근거 번들 화면+지출 분류 페이지, `docs/07_BACKLOG.md` P37)와
**MQ-916**(승인 큐 `kind:"repair"` 상세, P38) 두 화면 태스크가 컷됐다. 둘 다 **백엔드는 Sprint 9 에서 이미 완성**돼 있고
(`build_evidence_bundle`·`GET /api/assets/{id}/evidence-bundle`·`POST /api/expenditure/classify`·`GET/POST /api/repairs/*`),
남은 건 화면뿐이다 — **백로그 승격이 아니라 Sprint 9 에서 컷된 MVP 화면 B 잔여 작업**이다(`00_MVP_SCOPE.md` §9 화면 B).

PM 조사에서 원 브리핑과 실제 코드가 갈리는 지점 3건을 확인·정정했다:

1. **D83 5키 정정** — `facts·laws·rules·evaluated·judgment`(원 브리핑, 오기) → **`laws·rules·evaluated·contracts·facts`**
   (`verdict`는 5키 밖 별도 필드, 해시 대상 아님). `04_MCP_TOOLS.md §14`·D83 로 재확인.
2. **`queueState.ts` 의 `STATE_LABEL.repair` 가 여전히 `{}`** — Sprint 8 이 "어휘 미정"으로 비워 둔 채였다.
   `RepairDetail.tsx` 를 만들어도 승인 큐 **목록**(`StateBadge` 경유)의 repair 행은 이 맵을 안 채우면 계속 `⚠` 미지값으로
   뜬다. `mappers.repairStateView`(상세 전용, Sprint 9 산출물, 현재 미사용)와 이 맵이 **같은 어휘의 두 번째 맵**이 되는
   D87 위반이 이미 잠재해 있었다 — MQ-1002 가 이걸 먼저 고친다.
3. **`ui_honesty_contract.py` 의 `L2_GLOBS`/`L2_EXTRA`/`L2_FILES_FLOOR` 는 같은 날 다른 스레드(설비 하이라이트
   대시보드/재고 드로어)가 이미 손댔다** — 현재 실측 하한 **26**, 프론트 라우트 **11개**(이 스레드의 산출물 기준).
   Sprint 9 문서의 예상치가 아니라 **이 실측을 기준선으로** 잡는다.

## 1. 스테이지 계획

| TASK | 제목 | 범위 | 선행 |
|---|---|---|---|
| MQ-1001 | 근거 번들 화면 + 지출 분류 독립 페이지 (P37) | `frontend/` (asset 컴포넌트·evidence·manager/expenditure 라우트) | — |
| MQ-1002 | 승인 큐 `kind:"repair"` 상세 (P38) | `frontend/` (queue 컴포넌트·`ApprovalQueueScreen`·`queueState.ts`·`mappers.tsx`) | — |
| MQ-1003 | `ui_honesty_contract.py` L2 확장 — `RepairDetail.tsx` 편입 + 하한 실측 갱신 | `spikes/` | MQ-1001, MQ-1002 |
| MQ-1004 | 문서·개수 전파 | `docs/07_BACKLOG.md` · `CLAUDE.md` | MQ-1003 |

```
MQ-1001 ─┐
         ├─► MQ-1003 ─► MQ-1004
MQ-1002 ─┘
```

### 스테이지 구성 근거

- **Stage 1 (MQ-1001 ∥ MQ-1002)** — 파일 교집합 0. MQ-1001 은 `components/asset/*`·`app/…/evidence,manager/expenditure`·
  `decisionView.ts` 만, MQ-1002 는 `components/queue/*`·`components/screens/ApprovalQueueScreen.tsx`·`queueState.ts`·
  `mappers.tsx` 만 건드린다. `mappers.tsx`/`decisionView.ts` 둘 다 겹쳐 보이지만 MQ-1001 은 기존 export(`expenditureVerdictView`
  등)를 **읽기만** 하고 쓰기는 MQ-1002 전용(`repairStateView` 단순화)이라 충돌 없음.
- **Stage 2 (MQ-1003) 단독** — `RepairDetail.tsx` 는 `components/queue/*.tsx` 글롭이 `Decision*.tsx` 만 잡으므로 `L2_EXTRA`
  에 명시 등재가 필요하다. **자기 코드를 자기가 검증 대상에 넣지 않는다**(Sprint 9 §14 재발방지 규칙과 같은 이유) — 별도
  태스크로 분리. `L2_FILES_FLOOR` 도 Stage 1 산출물이 다 있어야 정확한 실측값을 넣을 수 있다.
- **Stage 3 (MQ-1004) 단독** — 숫자는 러너 출력을 그대로 옮긴다(CLAUDE.md 규칙). MQ-1003 실행 결과가 나오기 전엔 못 적는다.

## 2. 태스크별 상세 구현 명세

### MQ-1001 — 근거 번들 화면 + 지출 분류 독립 페이지 (P37)

**복무 시나리오**: S10(근거 번들) · S1+(지출 분류)

**변경 파일**

1. `frontend/components/asset/DisposalPanel.tsx` — `const MODES = [...]` 에 `export` 추가만. 로직 변경 없음.
2. `frontend/components/asset/ExpenditureCard.tsx` — `function ExpenditureResult(...)` 에 `export` 추가만. 로직 변경
   없음. (지출 분류 결과 렌더는 카드와 독립 페이지가 **같은 컴포넌트를 재사용**해야 판정 문안·톤이 두 화면에서
   갈리지 않는다 — D87 "맵 1곳"과 같은 정신을 렌더 컴포넌트에도 적용.)
3. `frontend/components/queue/DecisionDetail.tsx` — `function HashFixedMark(...)` 에 `export` 추가만. 로직 변경 없음.
   (`contracts[].hash_fixed` 표기를 근거 번들 화면과 처분 상세가 동일 컴포넌트로 그린다.)
4. `frontend/lib/decisionView.ts` — 신규 함수 추가만(기존 export 무변경):

   ```ts
   // 근거 번들 조회 실패 어휘 (`04 §14`·`06 §2.5` 오류 매핑). SIGN_ERROR 와 reason 집합이
   // 다르므로(evidence_changed·override_required·cited_rule_missing 없음) 별도 맵을 둔다 —
   // 기존 맵에 억지로 끼워 넣으면 존재하지 않는 reason 코드에 대한 죽은 분기가 생긴다.
   export interface EvidenceBundleErrorLabel {
     title: string;
     recovery: "retry" | "none";
     known: boolean;
   }
   const EVIDENCE_BUNDLE_ERROR: Record<string, Omit<EvidenceBundleErrorLabel, "known">> = {
     law_text_unavailable: {
       title: "인용 조문 원문이 아직 수집되지 않아 근거 번들을 만들 수 없습니다 — 재시도로 풀리지 않습니다.",
       recovery: "none",
     },
     rule_catalog_not_loaded: {
       title: "룰 카탈로그가 적재되지 않았습니다 — 서버 준비 후 다시 시도하십시오.",
       recovery: "retry",
     },
   };
   export function evidenceBundleErrorView(reason: string | null | undefined): EvidenceBundleErrorLabel {
     if (!reason) return { title: "", recovery: "retry", known: false };
     const known = EVIDENCE_BUNDLE_ERROR[reason];
     if (!known) return { title: reason, recovery: "none", known: false };
     return { ...known, known: true };
   }
   ```

5. `frontend/components/asset/EvidenceBundlePanel.tsx` (신규) — props `{ assetId: string }`.
   - `ModeForm` 을 `DisposalPanel` 과 **동일한 패턴**으로 복제(3버튼 SALE/SCRAP/TRANSFER + 날짜 입력, 기본 선택·
     기본 날짜 없음, D62). `MODES` 는 `DisposalPanel` 에서 import.
   - 모드 선택 시 `getEvidenceBundle("technician", assetId, mode, date || undefined)` 호출.
   - 성공(`status:"ok"`) 렌더 순서:
     a. **판정 배너** — `verdictView(data.verdict)`/`verdictHeadline(data.verdict)` 재사용(신규 맵 안 만든다).
     b. **`hash_fixed` 의미 고지** — 고정 문구: *"`bundle_hash`는 이 화면의 5개 항목(laws·rules·evaluated·
        contracts·facts)만 고정합니다. 렌더된 문서나 증빙 패키지는 해시 대상이 아닙니다."* (`04 §14` 근거).
     c. `laws[]` — `law_ref_id`·`effective_from`·`text_hash`(Mono, 앞 16자 + 툴팁 전체).
     d. `rules[]` — `rule_id` v`rule_version`·`rule_hash`(같은 표기).
     e. `evaluated[]` — `rule_id` v`rule_version` · `verdict`(그대로 텍스트, **색·톤 매핑 없음** — 룰 단위
        TRIGGERED/CLEAR 는 자산 단위 판정 5종과 다른 어휘라 새 맵을 안 만들고 무채색으로만 찍는다) · `law_refs[]`.
     f. `contracts[]` — `contract_ref` · `HashFixedMark`(DecisionDetail 에서 import) · `note`.
     g. `facts` — key-value grid, `<details>`로 접되 기본 펼침(D62 — `DisposalPanel.FactsUsed`와 같은 문안).
     h. `not_considered[]`·`disclaimer`·`built_at`·`bundle_hash`(Mono, **전체 표시** — 서명 검증 대조값이라 축약 금지).
   - 실패:
     - 404(`unknown_asset`) → "자산을 찾을 수 없습니다".
     - 422(`invalid_input`) → `DisposalPanel.parse422` 와 같은 필드 오류 패턴(로직 복제 — `parse422` 비공개면
       인라인 재구현, 파일 커지는 게 싫으면 `parse422` export 추가도 가능하나 필수 아님).
     - 409(`law_text_unavailable`) → `evidenceBundleErrorView` 타이틀 + `missing_law_refs[]`·`missing_rules[]`(있으면).
     - 503(`rule_catalog_not_loaded`) → `evidenceBundleErrorView`("retry" 안내).
     - 그 밖 5xx(`asset_modified`·`asset_disappeared`·`rule_integrity`·`engine_error` 등, REST 층 500 뭉갬) →
       일반 오류 배너, `extractDetail` 그대로.
6. `frontend/app/(console)/technician/asset/[assetId]/evidence/page.tsx` (신규) — `value/page.tsx` 와 동일한
   fetch/loading/error 패턴(자산 조회 → `AssetHeader` → `EvidenceBundlePanel`). 하단에
   `<Link href="/manager/expenditure">지출 분류 페이지에서 별도로 확인 →</Link>` 1줄(발견 가능성 확보).
7. `frontend/app/(console)/technician/asset/[assetId]/disposal/page.tsx` (수정) — `AssetHeader`의 `right` 슬롯에
   "근거 번들 보기 →"(`/…/evidence`) 링크 1개 추가. **로직 추가 없음.**
8. `frontend/components/asset/ExpenditureForm.tsx` (신규) — props 없음(독립 페이지 전용, 자산 컨텍스트 없음).
   - 부품 검색 입력 → `getInventory("manager", { part_name: query })` → **`Promise<ApiInventory>`**(배열이
     아니라 `{status, items?, reason?, message?}` 봉투, `frontend/lib/api.ts:604-622`) — `res.items ?? []` 로
     언랩해서 선택 가능한 리스트로 렌더(각 행 `part_no`·`name`·`compatible_models`).
   - **검색 결과 0건은 `.then()` 이 아니라 `.catch()` 에서 잡는다** — `data/inventory.py:81-83` 이 매치 0건이면
     `{"status":"not_found","items":[]}` 을 내고 `backend/routers/inventory.py:31-37` 이 이걸 **HTTP 404** 로
     매핑하므로 `apiFetch` 가 `ApiError` 를 던진다. `InventoryDrawer.tsx:72-76` 의 `notFound` 분기는 이미
     도달 불가능한 죽은 코드이니 그 패턴을 베끼지 말 것 — 대신 `CriticalityDrawer.tsx:50-60` 의 `.catch`
     패턴(reason + `extractDetail` 조합)을 따른다.
   - **`part_class` 를 직접 고르는 UI는 만들지 않는다**(도구 설명이 "추측 금지" 명시). 사용자는 부품만 고른다
     → `selectedPartNo` state.
   - `repair_scope` select — `mappers.WORK_SCOPE_OPTIONS` 재사용(신규 옵션 목록 안 만든다).
   - `amount` — number input, `> 0` 아니면 제출 버튼 비활성 + 사유 문구(D62 — 0을 기본값으로 넣지 않는다).
   - 제출 → `postExpenditure("manager", { part_no: selectedPartNo, repair_scope, amount })`(★ `part_no` 를
     보낸다, `part_class` 가 아니다 — `backend/routers/maint_value.py:131-141` 에서 either-or 처리 실측 확인).
   - 결과 렌더는 `ExpenditureCard.tsx` 의 `ExpenditureResult` 그대로 재사용(중복 구현 금지).
9. `frontend/app/(console)/manager/expenditure/page.tsx` (신규) — 헤더 + `ExpenditureForm` 배치. 무저장 판정
   화면임을 명시하는 안내 문구 1줄(D71과 같은 태도).

**엣지 케이스**

| 상황 | 기대 |
|---|---|
| `evidence_bundle` 없는데 `status:"ok"`(계약 위반) | 5개 섹션을 만들지 않고 "계약 위반 신호" 배너 |
| `contracts: []` | "계약 근거가 인용되지 않았습니다" 한 줄. 섹션 자체를 숨기지 않는다(D65) |
| `getInventory` 검색 결과 0건 | **404 로 throw 됨**(`status:"not_found"`) → `.catch()` 에서 "일치하는 부품이 없습니다" — 부품 없음을 조용히 숨기지 않는다 |
| `amount` 비정수/음수 | 클라이언트에서 막고, 넘어가면 백엔드 422 → `extractDetail` 그대로 |
| 카드 vs 독립 페이지 판정 문안 불일치 | `ExpenditureResult` 공유로 구조적으로 발생 불가 — DoD 에서 확인 |

**지켜야 할 결정**: D62 · D65 · D71 · D83(5키 정정) · D84 · D86 · D87 · CLAUDE.md 절대규칙 1(이 화면은 아무것도 쓰지 않는다)

**DoD**
- `cd frontend && npx tsc --noEmit` 통과.
- `npm run build` → 라우트 **13개**(실측 기준선 11 + `evidence` + `manager/expenditure`).
- `rg -n "hash_fixed" frontend/components/asset/EvidenceBundlePanel.tsx` → 존재.
- `rg -n "\"BLOCKED\"|\"HOLD\"|\"CLEAR\"|\"CONDITIONAL\"|\"INSUFFICIENT_FACTS\"" frontend/components/asset/EvidenceBundlePanel.tsx frontend/components/asset/ExpenditureForm.tsx` → **0건**.
- `rg -n "part_class" frontend/components/asset/ExpenditureForm.tsx` → 입력 UI로 등장하지 않음(선택 드롭다운 없음), `postExpenditure` 호출부의 `part_no:` 전달 코드만 존재.
- 수동: `/technician/asset/{id}/disposal` → "근거 번들 보기 →" → `/technician/asset/{id}/evidence` 정상 도달.
- 수동: `/manager/expenditure` 부품 검색 → 선택 → 판정 결과가 `value/page.tsx`의 `ExpenditureCard`와 동일 컴포넌트로 렌더됨(같은 함수 import로 코드 확인).

---

### MQ-1002 — 승인 큐 `kind:"repair"` 상세 (P38)

**복무 시나리오**: S19 (⚠ `docs/07_BACKLOG.md` P33 — 이 번호는 Q 시리즈 전사 지도의 S19(FinAllQ 기업 고객
온보딩)와 충돌 중이며 아직 사람 협의 대기다. 기능·계약(D·enum·DB)에는 영향 없음 — 번호는 문서에만 있다. 이
스프린트가 그 미결을 늘리는 것은 아니지만, 정정되면 이 문서의 표기도 따라 바뀐다.)

**선행 정정(반드시 먼저)**: `frontend/lib/queueState.ts`의 `STATE_LABEL.repair`가 현재 `{}`다. 채우지 않으면
큐 **목록**(`StateBadge` 경유)의 repair 행은 상세 화면이 생긴 뒤에도 `⚠` 미지값으로 뜬다 — `mappers.repairStateView`
(상세 전용)와 `STATE_LABEL.repair`(목록 배지 전용)가 같은 어휘의 두 번째 맵이 되는 D87 위반이 이미 잠재해 있다.

**변경 파일**

1. `frontend/lib/queueState.ts` (수정) — `STATE_LABEL.repair`를 `disposal`과 동일한 4엔트리로 채운다:
   ```ts
   repair: {
     draft: { text: "draft", tone: "neutral" },
     pending: { text: "◔ pending", tone: "info" },
     signed: { text: "✓ signed", tone: "ok" },
     rejected: { text: "✕ rejected", tone: "danger" },
   },
   ```
   같은 파일에 `isDraftState`(Sprint 9 산출물, 이번 세션 D87 수정에서 추가됨)와 같은 패턴으로:
   ```ts
   /** `state === "pending"` 직접 비교를 컴포넌트에 두지 않기 위한 총 술어 (D87, isDraftState 선례). */
   export function isPendingState(state: string): boolean {
     return state === "pending";
   }
   ```
2. `frontend/lib/mappers.tsx` (수정) — `REPAIR_STATE_LABEL` 로컬 맵을 **삭제**하고 `repairStateView`를
   `queueState.stateView`에 위임:
   ```ts
   export function repairStateView(state: string): QueueLabel {
     return stateView("repair", state);
   }
   ```
   (`stateView`를 이 파일의 import 목록에 추가.)
3. `frontend/components/queue/RepairDetail.tsx` (신규):
   ```ts
   export function RepairDetail({
     repairId,
     onUpdated,
   }: {
     repairId: string;
     onUpdated?: (updated: ApiRepair) => void;
   }) { ... }
   ```
   - 마운트 시 `getRepair("manager", repairId)` 호출(로딩/실패 처리는 `CriticalityDrawer` 패턴과 동일).
   - 헤더: `KindBadge kind="repair"` · `StateBadge kind="repair" state={repair.state}`(이제 `STATE_LABEL.repair`가
     채워져 정상 렌더) · `repair_id` Mono.
   - 요약: `EvidenceCard`(queue/EvidenceCard.tsx, 기존 컴포넌트 재사용)에 로컬 `repairSummary(repair): EvidenceEntry[]`
     함수로 만든 행 전달 — 부품/시리얼/수량, `work_type`, `repair_scope`, `part_class`(값 없으면 "미상", D97 태도),
     `expenditure_class` + `expenditure_reason`, `cost`, `downtime_hours`, `equipment_id`/`model`/`error_code`.
   - **서명 상태 표시**: `signed`면 `record_hash`(Mono, **앞 12자만**) + `hash_verified`(불리언 — `true`→"대조 일치",
     `false`→경고 톤 고정 텍스트, `undefined`면 "대조 결과 없음". boolean 분기이므로 D87의 "상태 어휘" 규칙 대상 아님).
   - **서명/반려 컨트롤** — `SignBar.tsx`를 재사용하지 않는다(그 컴포넌트는 `ApiDecision`/`signDecision`/`override`
     개념에 강결합). 이 파일 안에 작고 전용화된 컨트롤을 둔다:
     - `!isPendingState(repair.state)`면 컨트롤을 렌더하지 않고 `<NotSignable state={repair.state}/>` (직접
       `state === "pending"` 비교를 쓰지 않고 `queueState.isPendingState` 호출 — D87 L2 스캔의 `STATE_WORDS`에
       `pending`이 이미 있어 직접 비교는 걸린다).
     - `pending`이면: "서명" 버튼(`signRepair(repairId)`, 본문 없음) + "반려" 버튼(사유 textarea 필수 — `DecisionBar`가
       export하는 `RejectPanel` import, 신규 구현 불필요).
     - **`self_sign` 409**: `errorBody(e).reason === "self_sign"`이면 고정 문구 *"본인이 수행한 수리는 본인이
       서명할 수 없습니다."*(D4). reason이 2종(`invalid_transition`·`self_sign`)뿐이라 소규모 `if/else` 인라인으로
       충분 — `self_sign`은 `STATE_WORDS`에 없어 D87 L2 스캔에 걸리지 않는다.
     - `override`·`requires_override` 개념 없음 — 렌더하지 않는다.
   - `draft` 상태: "정비사가 아직 제출하지 않았습니다"만 표시, 컨트롤 없음.
   - `rejected`: 종착역, 재요청 버튼 **만들지 않는다**(P15는 백로그, 승격 금지).
4. `frontend/components/screens/ApprovalQueueScreen.tsx` (수정):
   - `load()`에 repair 상세 조회 분기 추가: `const [repair, setRepair] = useState<ApiRepair | null>(null);` →
     `target?.kind === "repair" ? await getRepair("manager", target.id) : null`.
   - 딥링크 미스매치 분기(`selectedId && !found`)에도 `getRepair` 직접조회 폴백 추가(현재 `getPo`만 있음 — `po`뿐
     아니라 `repair`도 큐 4목록 밖 상태(`draft`)로 존재할 수 있어 동일 위험).
   - 렌더 분기에 `chosen.kind === "repair" && live && repair ? <RepairDetail repairId={repair.repair_id}
     onUpdated={(u) => { setRepair(u); setNotice(...); void load(); }} /> : ...` 추가, `PendingImplementationDetail`은
     최종 폴백으로 유지.

**엣지 케이스**

| 상황 | 화면 |
|---|---|
| 목록에 12건(서명 11 + draft 1) 표시 | 정상 — `state` 필터로 좁힐 수 있게 `QueueList`는 기존 필터 그대로 |
| `verdict: null`, `requires_override: null`(큐 목록 항목) | 판정 칸 자체를 만들지 않는다(D62) — `PendingImplementationDetail`과 같은 태도 |
| `hash_verified: undefined`(미서명 레코드) | "대조 결과 없음" — `false`(불일치)와 구분 |
| 딥링크로 `draft` 상태 repair 직접 진입 | `getRepair` 폴백으로 헤더 렌더, 컨트롤은 "제출 전" 문구만 |

**지켜야 할 결정**: D85 · D87 · D62 · D38 · D4 · CLAUDE.md 규칙 1(사람 전용 API만 호출) · **P15 승격 금지**(재요청 버튼 없음)

**DoD**
- `cd frontend && npx tsc --noEmit` 통과.
- `npm run build` → 라우트 수 **MQ-1001 완료 후 값과 동일하게 유지**(큐 안이므로 신규 라우트 없음).
- `rg -n "\"pending\"|\"signed\"|\"draft\"|\"rejected\"" frontend/components/queue/RepairDetail.tsx` → 술어 함수(`isPendingState` 등) 호출부를 제외한 직접 `state === "..."` 리터럴 비교 **0건**.
- 수동: 팀장 승인 큐에서 repair 항목 선택 → 상세 렌더 → 서명(또는 반려) → 목록 배지가 `◔ pending` → `✓ signed`(또는 `✕ rejected`)로 정상 갱신(이전엔 `⚠` 미지값이었는지 함께 확인).
- `rg -n "REPAIR_STATE_LABEL" frontend/lib/mappers.tsx` → **0건**(로컬 맵 삭제 확인).

---

### MQ-1003 — `ui_honesty_contract.py` L2 확장 (RepairDetail 편입 + 하한 갱신)

**복무 시나리오**: 인프라 (D87 방어선)

**변경 파일**: `spikes/ui_honesty_contract.py`만.

**핵심 로직**
1. `L2_EXTRA = ("components/queue/SignBar.tsx", "components/queue/RepairDetail.tsx")`.
2. `L2_FILES_FLOOR`를 **실제로 스위트를 실행해 나온 값**으로 올린다. 산술 예상치(검증용, 실행 후 대조):
   기존 26 + `app/(console)/**/*.tsx` 신규 2개 + `components/asset/*.tsx` 신규 2개 + `L2_EXTRA` 신규 1개 = **31**.
   ⚠ 지어내지 말고 `len(l2_targets())` 실측으로 확정한다.
3. 상단 주석에 "MQ-1003 — Sprint 10, `RepairDetail.tsx` 편입 + 하한 31(실측 확정)" 한 줄 추가.

**지켜야 할 결정**: D87 · CLAUDE.md 부재검사 규칙(양성 축 필수) · Sprint 9 §14 재발방지(자기 코드 자기 검증 금지)

**DoD**
- `uv run python spikes/ui_honesty_contract.py` 전건 통과, 출력 "L2 스캔 대상 N개 (하한 …)"의 N이 새 하한과 일치.
- `rg -n "RepairDetail" spikes/ui_honesty_contract.py` → `L2_EXTRA` 등재 확인.
- MQ-1001/1002가 심은 코드에 D87 위반이 있으면 이 실행에서 FAIL로 잡혀야 한다 — 고의로 `state === "pending"`류
  리터럴을 임시로 넣어 FAIL 1회 확인(뮤턴트 검증과 같은 취지, 원본 파일에는 남기지 않는다).

---

### MQ-1004 — 문서·개수 전파

**복무 시나리오**: 인프라

**변경 파일**: `docs/07_BACKLOG.md` · `CLAUDE.md`

**핵심 로직**
1. `docs/07_BACKLOG.md` P37·P38 행의 `🟡 Sprint 10 이월` → `✅ 완료 (Sprint 10)`로 갱신, 산출물을 실제 생성된
   파일명으로 채운다.
2. `CLAUDE.md`의 "실측 기준선" 표: 프론트 라우트 `11개` → `13개`, `ui_honesty_contract` 건수를 MQ-1003 실행
   결과로 갱신, spikes 총 건수를 그만큼 조정.

**엣지 케이스**: 숫자는 러너 출력을 그대로 옮긴다(기억으로 적지 않는다).

**DoD**
- `rg -n "라우트 11개" docs/ CLAUDE.md` → **0건**.
- `rg -n "Sprint 10 이월" docs/07_BACKLOG.md` → **0건**(P37·P38 모두 완료로 바뀜).

---

## 3. 검토가 필요할 수 있는 지점 (구현 착수 전 재확인 권고)

- `ExpenditureForm.tsx`가 `part_no`만 보내는 경로는 프론트 최초 소비다(`ExpenditureCard`는 항상 `part_class`를
  직접 넘겨 왔음). **tool-builder 현실성 평가에서 실측 확정** — `data/maint_value.py:459-463`이 `part_no`는
  있는데 `part_class`가 비어 있으면 `reason="part_class_not_set"`을 내고, `backend/routers/maint_value.py`의
  `_REASON_HTTP`(:60-64)에 이 reason이 없어 **HTTP 500**으로 떨어진다(422/503/409 아님). 형제 reason
  `unknown_part`(→404)·`part_class_invalid`(→500)도 같은 경로에서 날 수 있다. **코드 변경은 불필요** —
  `ExpenditureForm`이 `ExpenditureCard.tsx:47-56`와 같은 범용 reason+message catch를 쓰면 이미 처리된다(스펙
  정정만 필요했던 항목, 처리 로직 자체는 원래 설계대로 맞았다).
- `RepairDetail.tsx`의 서명/반려 소형 컨트롤은 `SignBar.tsx`를 재사용하지 않기로 했는데, 구현 중 코드량이
  예상보다 커지면 `DecisionBar.RejectPanel`뿐 아니라 `SignBar`의 실패-표시(`FailureBox`) 패턴도 함께 뜯어 재사용할
  가치가 있다 — 다만 `EXTRA_LISTS`(`resolve_options`·`missing_law_refs`·`missing_rules`)는 repair 실패 응답에
  없는 필드라 그대로 가져오면 안 된다.

## 4. 현실성 평가 (tool-builder, `/sprint` Step 2)

| 스테이지 | TASK | 리스크 | 처리 |
|---------|------|--------|------|
| Stage 1 | MQ-1001 | `getInventory` 반환 타입이 `ApiInventoryItem[]`이 아니라 `Promise<ApiInventory>`(봉투 객체) | 정정 완료 — 위 §2 항목8, 엣지케이스 표 |
| Stage 1 | MQ-1001 | 재고 검색 0건은 200/빈배열이 아니라 404(`ApiError`) — `InventoryDrawer.tsx`의 `notFound` 분기는 참고하면 안 되는 도달불가 코드 | 정정 완료 — `CriticalityDrawer.tsx` 의 `.catch` 패턴을 따르도록 명시 |
| Stage 1 | MQ-1001 | `part_class_not_set` reason의 실제 HTTP 코드가 "추정"으로만 적혀 있었음 | 정정 완료 — 500 확정, 형제 reason 2종 추가. 코드 변경은 불필요(범용 catch로 이미 처리됨) |
| Stage 1 | MQ-1001 vs MQ-1002 | 파일 교집합 | 실측 확인 — **교집합 0** |
| Stage 1 | 숨은 순서 의존성 | MQ-1002 가 `mappers.tsx` 에서 지우는 `REPAIR_STATE_LABEL`/`repairStateView` 를 MQ-1001 이 참조하는지 | 실측 확인 — **미참조, 교차 없음** |
| Stage 2 | MQ-1003 | `L2_EXTRA` 등재 필요성·하한 산술 | 실측 확인 — 계획대로 진행 가능 |
| Stage 1 | MQ-1002 | `RejectPanel`·`getRepair`/`signRepair`/`rejectRepair` 시그니처·`isDraftState` 선례 | 전부 실측 일치 |
| 인프라 | 게이트 체크리스트 | `error_codes`·`related_parts`·`ANTHROPIC_API_KEY`·임베딩 — 이번 스프린트는 순수 프론트+기존 완성 백엔드 재사용 | **해당 없음, 블로커 없음** |

### 평가 결론
계획 수정 필요: **Y (스펙 텍스트만, 코드/스테이지 구조 불변)** — 3건 전부 위 §2·§3 본문에 반영 완료.
Stage 1 병렬 안전성·Stage 2/3 순서·태스크 경계·DoD 는 실측으로 전부 확인되어 추가 수정 없음.

## 조사 시 참고한 파일

`docs/07_BACKLOG.md` · `docs/sprints/sprint-9.md` · `docs/10_DECISIONS.md`(D62·D65·D70·D74·D79·D83·D84·D85·D86·D87·D98·D100)
· `docs/04_MCP_TOOLS.md §14` · `docs/06_REPO_API.md §2.5-§2.8` · `frontend/lib/api.ts` · `frontend/lib/mappers.tsx` ·
`frontend/lib/decisionView.ts` · `frontend/lib/queueState.ts` · `frontend/components/asset/{CriticalityDrawer,
DisposalPanel,ExpenditureCard,MetricsAside,InventoryDrawer}.tsx` · `frontend/components/queue/{DecisionDetail,SignBar,
EvidenceCard}.tsx` · `frontend/components/screens/ApprovalQueueScreen.tsx` · `frontend/app/(console)/technician/
asset/[assetId]/{value,disposal}/page.tsx` · `spikes/ui_honesty_contract.py` · `backend/routers/maint_value.py`

---

## 5. Sprint 10 최종 실행 계획

| 스테이지 | 태스크 | 병렬 | 예상 결과물 |
|---------|--------|-----|-----------|
| Stage 1 | MQ-1001, MQ-1002 | ✅ | 근거 번들+지출 분류 화면 2개 신규 라우트, 승인 큐 repair 상세 컴포넌트 |
| Stage 2 | MQ-1003 | — | `ui_honesty_contract.py` L2 확장(`RepairDetail.tsx` 편입), 하한 실측 갱신 |
| Stage 3 | MQ-1004 | — | `docs/07_BACKLOG.md` P37·P38 완료 표기, `CLAUDE.md` 실측 기준선 갱신 |

실행: `/stage 1`
