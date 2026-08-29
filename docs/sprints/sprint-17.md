# Sprint 17 — 재무부 승인 단계 신설 + doc3(자금집행요청서) 렌더

**계획 작성일**: 2026-08-24 · **대상 스펙**: `docs/superpowers/specs/2026-08-24-finance-approval-doc3-design.md`
(사용자 승인 완료) · **상태**: ✅ **완료 (2026-08-24)** — Stage 1~4 전건 착지 + 브라우저 QA
(`7b28aee` Stage 1 · `80804fb` Stage 2 · `def1d19` Stage 3 · `754baf4` Stage 4 · `f3ebd49` QA·미결 2건 해소).
산출: D119(재무부 승인 단계) · `data/expenditure_limits.py`(내부통제 4종 판정) ·
`POST /api/po/{po_id}/finance-approve|reject` · doc3(자금집행요청서) 렌더 · `/manager/finance`.
회귀: `api_contract` 41→52건 · pytest `data/test_expenditure_limits.py` 16건 신설

> ⚠ 이 스프린트 착수 직전, 사용자가 CLAUDE.md 회귀 기준선(spikes 33종 + seed + pytest)을
> 별도 터미널에서 갱신 중이다. 아래 DoD 는 **절대 건수를 못박지 않는다** — "회귀 스위트 전건
> PASS, 새 회귀 0건" 식으로만 적는다. 실행 시점에 실측 건수를 스스로 확인할 것.

## 0. 선행 관계 그래프

```
Stage 1 (기반, 4태스크 병렬)
  MQ-1701 문서 결정 등재(D119·S5+)         [독립]
  MQ-1702 DB 스키마 확장 + 시드            [독립]
  MQ-1703 내부통제 판정 로직 모듈          [독립]
  MQ-1704 상태 전이 규칙 확장(services/po.py) [독립]
        │
        ▼ (Stage 1 완료 후 순차 진입)
Stage 2 (REST + A2A 이동, 3태스크 병렬)
  MQ-1705 REST 엔드포인트 신설 + 06_REPO_API.md   [MQ-1702·1704 결과물 전제]
  MQ-1706 회귀: spikes/api_contract.py 확장        [MQ-1705 계약을 스펙으로 미리 알고 작성]
  MQ-1707 회귀: test_po_a2a_trigger.py 재작성       [MQ-1705 계약을 스펙으로 미리 알고 작성]
        │
        ▼
Stage 3 (문서 렌더, 3태스크 병렬)
  MQ-1708 get_po() 내부통제 계산 + A2A 이력 조회    [MQ-1702·1703 전제]
  MQ-1709 doc3 렌더 함수 + 검수 플래그              [MQ-1708 이 정하는 controls/a2a_info/payee 계약을 전제]
  MQ-1710 회귀: spikes/api_contract.py 재확장       [MQ-1708·1709 계약을 스펙으로 미리 알고 작성]
        │
        ▼
Stage 4 (화면, 4태스크 병렬)
  MQ-1711 재무부 신원 전환 UX(role.ts)              [독립]
  MQ-1712 API 클라이언트/타입 확장(api.ts 등)        [MQ-1705 계약 전제]
  MQ-1713 PoDetail 재무 액션 UI                     [MQ-1711·1712 계약을 스펙으로 미리 알고 작성]
  MQ-1714 승인 큐 화면 재무 대기열 wiring            [MQ-1711·1712·1713 계약을 스펙으로 미리 알고 작성]
```

각 화살표는 "그 스테이지가 끝난 뒤 다음 스테이지가 시작된다"는 뜻이지, 같은 스테이지 안에서
병렬로 도는 태스크가 서로의 완성된 코드를 읽어야 한다는 뜻이 아니다 — 병렬 태스크는 이 문서가
못박은 **인터페이스**만 보고 각자 작성한다(아래 태스크별 상세의 "인터페이스" 절이 그 계약이다).

---

## 1. 스테이지 계획

### Stage 1 — 기반: 결정 문서 · DB 스키마 · 판정 로직 · 상태전이 규칙

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1701 | D119 등재 + S5+ 시나리오 반영 | `docs/10_DECISIONS.md`, `docs/02_SCENARIOS.md`, `docs/00_MVP_SCOPE.md` | — |
| MQ-1702 | `po_drafts` 스키마 확장 + 시드 표본 + 자가검증 | `data/seed.py`, `docs/05_DB_SCHEMA.md` | — |
| MQ-1703 | 내부통제 판정 로직 모듈 | `data/expenditure_limits.py`(신규), `data/test_expenditure_limits.py`(신규) | — |
| MQ-1704 | `po_drafts` 상태 전이 규칙 확장 | `backend/services/po.py` | — |

### Stage 2 — REST 엔드포인트 신설 + A2A 트리거 이동

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1705 | `finance-approve`/`finance-reject` 엔드포인트 + A2A 이동 | `backend/routers/po.py`, `docs/06_REPO_API.md` | MQ-1702, MQ-1704 |
| MQ-1706 | 회귀: REST 계약(403/409/200) | `spikes/api_contract.py` | MQ-1705(계약 스펙만 필요, 코드 완성 불필요) |
| MQ-1707 | 회귀: A2A 트리거 이동 재검증 | `backend/routers/test_po_a2a_trigger.py` | MQ-1705(계약 스펙만 필요) |

### Stage 3 — 문서 렌더 (doc3)

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1708 | `get_po()` 내부통제 계산 + A2A 이력 조회 + doc3 게이트 | `backend/services/po.py` | MQ-1702, MQ-1703, Stage 2 완료 |
| MQ-1709 | doc3 렌더 함수 + 검수 플래그 | `backend/services/po_documents.py`, `data/doc_review.py` | MQ-1708(계약 스펙만 필요) |
| MQ-1710 | 회귀: doc3 렌더 계약 + 키집합 동기화 | `spikes/api_contract.py` | MQ-1708·1709(계약 스펙만 필요) |

### Stage 4 — 화면 반영

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1711 | 재무부 신원 전환 UX | `frontend/lib/role.ts`, `frontend/components/layout/ManagerIdentitySwitch.tsx`(신규), `frontend/components/layout/AppBar.tsx` | — |
| MQ-1712 | API 클라이언트/타입 확장 | `frontend/lib/api.ts`, `frontend/lib/types.ts`, `frontend/lib/queueState.ts` | Stage 2·3 REST 계약 |
| MQ-1713 | `PoDetail` 재무 액션 UI | `frontend/components/queue/FinanceDecisionBar.tsx`(신규), `frontend/components/queue/PoDetail.tsx` | MQ-1711·1712(계약 스펙만 필요) |
| MQ-1714 | 승인 큐 화면 재무 대기열 wiring | `frontend/components/screens/ApprovalQueueScreen.tsx`, `frontend/components/queue/QueueList.tsx` | MQ-1711·1712·1713(계약 스펙만 필요) |

### 스테이지 구성 근거

- **Stage 1**: 네 태스크가 건드리는 파일이 완전히 분리된다(문서 2+1종 / `data/seed.py`+스키마 문서 /
  신규 순수함수 모듈+그 테스트 / `backend/services/po.py`). `backend/services/po.py`는 이후
  Stage 2(라우터만 변경, 서비스 파일은 안 건드림)·Stage 3(같은 파일을 다시 건드림)에서도
  나오지만 스테이지가 순차이므로 충돌하지 않는다. D10 절대 규칙(설계 결정 먼저 등재)에 따라
  MQ-1701의 D119가 Stage 2의 department 체크 코드보다 먼저 커밋 이력에 있어야 하므로 최우선
  스테이지에 둔다. MQ-1702(스키마)·MQ-1704(전이 규칙)는 이후 모든 스테이지의 전제 조건이다.
- **Stage 2**: `backend/routers/po.py`(엔드포인트 신설) 하나와 회귀 두 파일
  (`spikes/api_contract.py`, `backend/routers/test_po_a2a_trigger.py`)이 서로 다른 파일이라
  병렬이다. 회귀 두 태스크는 라우터 코드가 완성되길 "기다리지" 않는다 — 이 문서가 못박은
  엔드포인트 계약(요청/응답/상태코드)만 보고 검증 코드를 쓸 수 있고, 스테이지 종료 시
  eval-runner 가 전체를 통합 실행해 어긋나면 그 자리에서 드러난다. 이 스테이지가 Stage 1과
  분리된 이유: `backend/services/decisions.py::now_utc_sql` 재사용·`ALLOWED_FROM` 확장 같은
  서비스 계층 변경이 먼저 안정돼야 라우터가 그 위에 얹을 수 있다.
- **Stage 3**: `backend/services/po.py`(다시 등장, Stage1·2가 이미 끝난 뒤라 충돌 없음)와
  `backend/services/po_documents.py`+`data/doc_review.py`, 그리고 회귀 파일이 셋 다 다른
  파일이라 병렬이다. `get_po()`가 만드는 `controls`/`a2a_info`/`payee` 세 값의 **정확한 모양**을
  이 문서가 못박아 두었으므로(MQ-1708 인터페이스 절), `render_fund_execution_document()`을
  작성하는 MQ-1709가 MQ-1708의 실제 코드를 읽지 않고도 호환되는 함수를 쓸 수 있다.
- **Stage 4**: 프론트 4태스크가 서로 다른 파일 집합을 갖도록 의도적으로 나눴다 —
  신원 전환(role.ts+신규 컴포넌트+AppBar) / API 계약(api.ts+types.ts+queueState.ts) /
  발주 상세 UI(신규 컴포넌트+PoDetail.tsx) / 큐 화면 wiring(ApprovalQueueScreen.tsx+
  QueueList.tsx). 넷 다 서로의 산출물을 참조하지만 **파일이 겹치지 않아** 병렬로 작성 가능하고,
  이 문서의 인터페이스 절이 각 태스크가 다른 태스크에 기대하는 함수 시그니처를 전부 명시한다.
- **이월 태스크 없음** — Sprint 16 은 완결됐고(`docs/sessions/2026-08-24_backend-hang-and-dashboard.md`),
  이 스프린트는 새 스펙에서 바로 시작한다.
- **블로커 우회**: `error_codes` 사람 승인 상태·`related_parts` 검수 상태·임베딩/벡터스토어
  미결은 이 스프린트와 **무관하다** — 발주 승인 워크플로우 확장이지 진단·RAG 경로가 아니다.
  `ANTHROPIC_API_KEY` 도 무관 — 전부 사람 전용 REST(D10 예외)와 화면이고 에이전트 루프를
  타지 않는다. 막히는 지점이 없어 스테이지 배치에 우회가 필요 없었다.

---

## 2. 태스크별 상세 구현 명세

### MQ-1701 — D119 등재 + S5+ 시나리오 반영

- **복무 시나리오**: S5+(신규, 아래 참고) — S1/S2 가 만드는 발주의 승인 후 흐름 확장
- **변경 파일**:
  - `docs/10_DECISIONS.md` (수정 — D119 신규 행 추가)
  - `docs/02_SCENARIOS.md` (수정 — "확장 시나리오" 표에 S5+ 행 추가)
  - `docs/00_MVP_SCOPE.md` (수정 — §3 발주서 초안+승인 워크플로우 절에 한 줄 추가)
- **인터페이스**: 문서 편집만, 코드 인터페이스 없음
- **핵심 로직**:
  1. `docs/10_DECISIONS.md` 마지막 행(D118, 141번째 줄 부근) 바로 뒤에 **5열 표 형식**으로
     D119 를 추가한다. 최근 행(D115~D118)의 실제 열 구성을 그대로 따를 것 —
     `| D119 | **결정문** | 대안 나열 | 대안별 기각 사유 | 근거/구현 메모 |`
     (헤더 줄 `| # | 결정 | 대안 | 채택 이유 |` 은 4열로 보이지만 D115~D118 실제 행은 모두
     5열이다 — 헤더가 낡았을 뿐이니 헤더를 고치지 말고 **기존 행의 실제 패턴**을 따른다).
     결정문 초안(스펙 §4 문구 기반, 정확히 옮기지 말고 이 스프린트가 실제로 구현한 대로 조정):
     > **재무부 승인 단계 신설과 함께, `finance-approve`/`finance-reject` 두 엔드포인트에 한해
     > `c.department == "finance"` 체크를 추가한다 — D108("department 는 권한이 아니다,
     > `require()` 는 role 만 본다")을 어기는 게 아니라 명시적으로 등재하는 예외다.
     > `require()` 자체(다른 모든 라우트가 쓰는 공용 함수)는 여전히 department 를 보지 않는다 —
     > 오직 이 두 엔드포인트가 자기 함수 본문에서 SoD(직무분리) 목적으로 추가 검사를 한다.**
     대안: ① `require()` 자체에 선택적 `department` 파라미터를 추가해 범용화 / ② 재무 승인 전용
     새 역할(`role: "finance"`)을 만들어 `require()`로 통일. 기각 사유: **①은** `require()`가
     "role 만 본다"는 D108 의 단순성을 다른 모든 호출부까지 흔든다 — 두 엔드포인트만의 예외를
     범용 함수에 넣으면 그 함수를 읽는 사람 전부가 department 분기를 신경 써야 한다. **②는**
     `X-Role` 이 `technician|manager` 두 값으로 고정된 계약(D38 완료 기준 "권한 위반 403 차단
     100%"가 이 이분법을 전제)을 깨고, `users.role` 스키마도 다시 손대야 한다 — 소속(department)
     문제를 권한(role) 문제로 격상시키는 과잉 설계.
     근거/구현 메모: `backend/routers/po.py::finance_approve`/`finance_reject`(MQ-1705),
     `docs/superpowers/specs/2026-08-24-finance-approval-doc3-design.md §4`.
  2. `docs/02_SCENARIOS.md`의 "확장 시나리오" 표(S1+·S9·S10·S18·S29 가 있는 표, 파일 끝부분)에
     새 행을 추가한다:
     ```
     | **S5+** 재무 승인 | approve(팀장) → **finance-approve/finance-reject(재무담당, D119)**
       → (승인 시) dispatch_a2a_withdrawal_request(S5, FinAllQ) | 재무부 소속(department=
       'finance') manager 전용. `approved` 는 이제 "재무 승인 대기"를 겸한다 — 별도
       `finance_pending` 상태를 만들지 않았다(스키마 단순화) |
     ```
     표 아래 각주(현재 "~~S17~~ ... 는 v2 로 제외" 각주가 있는 자리) 근처에 한 줄 덧붙여도 좋다:
     "S5(FinAllQ 출금 요청) 자체는 A2A_Q 저장소가 정의한 시나리오이고, S5+ 는 그 앞에 MaintQ
     내부 재무 승인 단계를 끼워 넣은 확장이다 — 기존 S1+/S9/S10/S18/S29 표기 관례와 같다."
  3. `docs/00_MVP_SCOPE.md`§3(발주서 초안+승인 워크플로우) 절, "MOQ 미달 수량은..." 단락과
     "→ 근거: D10..." 사이 또는 그 아래에 짧은 단락 추가:
     > **Sprint 17 확장 (D119)**: `approved` 뒤에 재무부 승인 단계(`finance_approve`/
     > `finance_reject`)가 붙는다 — 팀장 승인만으로는 자금이 나가지 않고, 재무부 소속
     > 매니저의 별도 승인이 있어야 FinAllQ 출금 요청(S5)이 전송된다. 상세는 `docs/02_SCENARIOS.md`
     > S5+, `docs/06_REPO_API.md §2.2`.
- **엣지 케이스**: 없음(순수 문서 작업)
- **지켜야 할 결정**: D108(department 는 권한이 아니다 — D119 는 이를 어기지 않고 명시적
  예외를 등재하는 것임을 문구로 분명히 할 것) · D10(도구가 아니라 사람 전용 REST 확장임을
  명시)
- **DoD**: `docs/10_DECISIONS.md`에 D119 행이 존재하고 D115~D118 과 같은 5열 형식을 따른다.
  `docs/02_SCENARIOS.md`에 S5+ 행이 존재한다. `docs/00_MVP_SCOPE.md §3`에 확장 언급이 있다.
  세 파일 모두 마크다운 표가 깨지지 않는다(열 개수 일치).

---

### MQ-1702 — `po_drafts` 스키마 확장 + 시드 표본 + 자가검증

- **복무 시나리오**: S5+
- **변경 파일**: `data/seed.py` (수정), `docs/05_DB_SCHEMA.md` (수정, §8)
- **인터페이스**:
  - `po_drafts` DDL(현재 `data/seed.py` 약 206~232번째 줄)에 컬럼 4종 추가:
    ```sql
    decided_at            DATETIME,                 -- 팀장 결정 시각 (기존 gap — approve/reject 도 지금까지 없었다)
    finance_decided_by    TEXT REFERENCES users,     -- 재무 담당 사용자 ID
    finance_decision_note TEXT,                      -- 재무 승인 코멘트 / 반려 사유
    finance_decided_at    DATETIME,                  -- 재무 결정 시각
    ```
    `CHECK (state IN ('draft','pending','approved','rejected'))` →
    `CHECK (state IN ('draft','pending','approved','rejected','finance_approved','finance_rejected'))`
  - `seed_po_drafts(con, with_codes)` 함수: 튜플 스키마에 4개 필드 추가(끝에 이어붙임) —
    `(po_id, part_no, qty, supplier_id, model, code, evidence, unit_price, reason, urgency,
    state, requested_by, decided_by, decision_note, session_id, decided_at, finance_decided_by,
    finance_decision_note, finance_decided_at)` — 19개 컬럼. `INSERT INTO po_drafts (...)`문의
    컬럼 목록·플레이스홀더(`?` 19개)도 함께 갱신.
    ⚠ `with_codes=False`일 때 `model`·`error_code`를 비우는 기존 로직
    (`rows = [r[:4] + (None, None) + r[6:] for r in rows]`)은 튜플 길이가 늘어나도 그대로
    동작한다(슬라이스 기반이라 뒤쪽 필드 개수와 무관) — 수정 불필요, 그대로 둘 것.
- **핵심 로직**:
  1. 기존 5개 샘플 행(PO-0117~PO-0113) 중 `state='approved'`인 **PO-0114**와
     `state='rejected'`인 **PO-0113**에 `decided_at` 값을 채운다(그동안 컬럼이 없어 비어
     있던 gap). 예: PO-0114 `decided_at='2026-08-05 03:20:00'`, PO-0113
     `decided_at='2026-08-04 07:10:00'` (다른 샘플의 타임스탬프 스타일과 맞춘 임의 값 —
     `created_at DEFAULT CURRENT_TIMESTAMP`보다 늦은 시각이면 된다, 정밀值 불필요).
     나머지 3행(draft·pending 상태)은 `decided_at=None`.
  2. **PO-0114 는 `approved` 상태 그대로 유지한다** — 새 상태 머신에서 이 상태는 자동으로
     "재무 승인 대기"를 겸하므로 별도 수정 없이 그대로 좋은 회귀 픽스처가 된다.
  3. 신규 샘플 3행 추가:
     - **PO-0118** — `state='finance_approved'`. 저액(예: 단가 15,000원 × 수량 2 = 30,000원,
       예산 한도 5,000,000원 이내가 확실하도록) 부품으로, `decided_by='mgr-01'`,
       `decided_at`(임의), `finance_decided_by='mgr-02'`, `finance_decision_note='승인 —
       예산·한도 이내'`, `finance_decided_at`(decided_at 보다 늦은 시각). doc3 "승인" 내러티브
       샘플.
     - **PO-0119** — `state='finance_rejected'`. **의도적으로 예산 한도(5,000,000원)를
       초과하는 금액**(예: 단가 3,000,000원 × 수량 2 = 6,000,000원)으로 만들어, Stage 3 에서
       `budget_check()`가 실제로 `ok=False`를 내는 표본이 되게 한다. `finance_decided_by=
       'mgr-02'`, `finance_decision_note='예산 한도 초과 — 반려'`.
     - **PO-0120** — `state='approved'` (재무 결정 전, `finance_decided_by=None` 등 전부 NULL).
       Stage 2 회귀(MQ-1706·1707)가 `finance-approve`/`finance-reject` **성공 경로**를 각각
       독립적으로 검증할 여분 픽스처로 쓴다 — PO-0114 하나만 있으면 먼저 approve 를 소비하는
       테스트가 reject 테스트의 전제 상태를 깨버린다.
     part_no/supplier_id 는 기존 시드에 이미 있는 값(`FAN-IG5-01`·`SUP-A` 등)을 재사용해
     FK 를 항상 만족시킬 것. `model`/`error_code`는 기존 관례대로 `with_codes` 분기를 그대로
     타게 두면 된다(굳이 셋 다 코드 있는 발주로 만들 필요 없음 — 최소 하나는 코드 없는 S2류로
     둬도 무방, 다만 필수는 아님).
  4. `verify(con, with_codes, db_path)` 함수(약 2270번째 줄~)에 새 자가검증 항목을 추가한다.
     **번호는 파일에 이미 있는 마지막 원문자 번호(현재 ㊱ 근방으로 알려져 있으나 실행 시점에
     실제로 확인할 것 — CLAUDE.md 자체가 이 숫자는 자주 낡는다고 경고한다) 바로 다음 것을
     쓴다.** 함수 상단 독스트링의 번호 안내문에도 이번에 추가한 범위를 이어붙일 것(D 결정을
     인용하는 관례 없음 — 이번엔 인용 대상 D 없음, 생략 가능).
     - **check A** — `state` CHECK 가 `finance_approved`/`finance_rejected` 를 허용하고
       임의 문자열은 거부하는지. `SAVEPOINT`로 감싸고(기존 `fk_probe` 패턴,
       2382번째 줄 부근 참고) `UPDATE po_drafts SET state='bogus_state' WHERE po_id='PO-0117'`
       시도 → 반드시 예외 → `ROLLBACK TO SAVEPOINT`. 성공 케이스는 이미 3.의 INSERT 가 통과한
       것으로 증명된다(별도 assert 불필요, `SELECT count(*) FROM po_drafts WHERE state IN
       ('finance_approved','finance_rejected')` == 2 확인 정도면 충분).
     - **check B** — `decided_at`이 `approved`/`rejected`/`finance_approved`/`finance_rejected`
       인 모든 행에서 NULL 이 아님: `SELECT count(*) FROM po_drafts WHERE state IN (...) AND
       decided_at IS NULL` == 0.
     - **check C** — PO-0118/PO-0119 두 표본이 `finance_decided_by='mgr-02'`이고
       `finance_decision_note`·`finance_decided_at`이 모두 NOT NULL.
     - **check D** — `finance_decided_by`의 FK 무결성 probe: 존재하지 않는 유령 ID로
       `finance_decided_by`를 채운 INSERT 시도 → 거부 확인 (`fk_probe`와 같은 SAVEPOINT 패턴,
       새 SAVEPOINT 이름 사용할 것 — 기존 `fk_probe`와 겹치지 않게 예: `fk_probe_finance`).
- **엣지 케이스**:
  - `with_codes=False`로 재시드하면 PO-0118/0119 의 `model`/`error_code`도 기존 관례대로
    비워지는지 확인(슬라이스 로직이 뒤쪽 4개 신규 필드를 안 건드리므로 자동으로 맞다).
  - 마크다운 표 형식이 아니라 SQL DDL 이므로 `docs/05_DB_SCHEMA.md §8`의 코드 블록도 반드시
    같은 컬럼·CHECK 로 동기화할 것(문서가 실제 DDL 과 다르면 다음 세션이 또 낡은 문서로
    혼란을 겪는다 — CLAUDE.md 가 반복 경고하는 패턴).
- **지켜야 할 결정**: D33(model/error_code 짝 규칙, 손대지 않음) · D38(반려 사유 필수 —
  PO-0119 의 `finance_decision_note`가 비어 있으면 안 됨, 나중 스테이지의 반려 로직과 일관)
- **DoD**:
  `uv run python data/seed.py --with-error-codes` 재시드 성공, 자가검증 전건 PASS(새로 추가한
  check A~D 포함, 기존 항목 회귀 없음). `SELECT count(*) FROM error_codes`가 여전히 기대한
  건수(재시드 직후 실측할 것, 하드코딩 금지). `docs/05_DB_SCHEMA.md §8`의 DDL 코드 블록이
  `data/seed.py`와 컬럼·CHECK 문자 그대로 일치.

---

### MQ-1703 — 내부통제 판정 로직 모듈

- **복무 시나리오**: S5+
- **변경 파일**: `data/expenditure_limits.py` (신규), `data/test_expenditure_limits.py` (신규)
- **인터페이스**:
  ```python
  BUDGET_LIMIT: int = 5_000_000
  DAILY_LIMIT: int = 15_000_000
  FDS_WARNING_RATIO: float = 0.5

  def budget_check(amount: int) -> tuple[bool, str]: ...
  def daily_limit_check(amount: int, today_total_before: int) -> tuple[bool, str]: ...
  def fds_verdict(amount: int) -> tuple[str, str]: ...
  def sod_check(requested_by: str, decided_by: str, finance_decided_by: str) -> tuple[bool, str]: ...
  ```
  네 함수 모두 스펙 §5 에 이미 완전한 구현이 주어져 있다 — **그대로 옮겨 쓴다** (아래 핵심
  로직 절에 재수록, 글자 하나 바꾸지 말 것).
- **핵심 로직**:
  ```python
  # -*- coding: utf-8 -*-
  """자금집행 내부통제 판정 — 전부 목업 상수/규칙이다. 실제 재무 정책이 아니다."""

  BUDGET_LIMIT = 5_000_000       # 건당 예산 한도 (원) — 목업 상수
  DAILY_LIMIT = 15_000_000       # 부서 1일 누적 한도 (원) — 목업 상수
  FDS_WARNING_RATIO = 0.5        # 예산한도 대비 이 비율 초과 시 "주의" — 목업 규칙


  def budget_check(amount: int) -> tuple[bool, str]:
      ok = amount <= BUDGET_LIMIT
      return ok, f"{amount:,}원 / 한도 {BUDGET_LIMIT:,}원 ({'이내' if ok else '초과'})"


  def daily_limit_check(amount: int, today_total_before: int) -> tuple[bool, str]:
      total = today_total_before + amount
      ok = total <= DAILY_LIMIT
      return ok, f"금일 누적 {total:,}원 / 한도 {DAILY_LIMIT:,}원 ({'이내' if ok else '초과'})"


  def fds_verdict(amount: int) -> tuple[str, str]:
      ratio = amount / BUDGET_LIMIT
      verdict = "주의" if ratio > FDS_WARNING_RATIO else "정상"
      return verdict, f"예산한도 대비 {ratio:.0%} — 목업 규칙(FDS_WARNING_RATIO={FDS_WARNING_RATIO})"


  def sod_check(requested_by: str, decided_by: str, finance_decided_by: str) -> tuple[bool, str]:
      ids = {requested_by, decided_by, finance_decided_by}
      ok = len(ids) == 3
      return ok, f"요청자·팀장·재무 3인 {'전원 상이' if ok else '중복 있음'} ({sorted(ids)})"
  ```
  모듈 docstring 은 반드시 "전부 목업 상수/규칙이다. 실제 재무 정책이 아니다" 문구를 유지할
  것 — D74(`residual_curve` 목업 공식)·D92(`partner_links` 목업 전제)와 같은 정직 고지 패턴.
- **엣지 케이스**:
  - `sod_check`에 `finance_decided_by=None`을 넘기면 `{requested_by, decided_by, None}`이
    조건상 3개 원소일 수 있어 `ok=True`가 **잘못** 나올 수 있다 — 이 함수 자체는 이 경우를
    방어하지 않는다(스펙이 준 순수함수 그대로). **호출부(MQ-1708)가 `finance_decided_by`가
    None 이면 이 함수를 아예 부르지 않고 별도 미확정 문구를 쓰도록 책임진다** — 이 모듈
    자체에는 방어 로직을 넣지 않는다(스펙 §5 원문 유지가 우선, 방어는 호출부 책임).
  - `fds_verdict`의 비율이 정확히 0.5일 때 `ratio > FDS_WARNING_RATIO`는 `False`이므로
    "정상"이다 — 경계값 테스트로 반드시 확인.
- **지켜야 할 결정**: 없음(신규 순수함수 모듈, 기존 결정과 충돌 없음) — 단 목업임을 코드
  주석에 명시하는 것은 D74/D92 선례를 지키는 것
- **DoD**:
  `uv run --with pytest python -m pytest data/test_expenditure_limits.py -q` 전건 PASS.
  테스트는 최소 다음을 포함: budget_check 경계(정확히 5,000,000원 → ok, +1원 → not ok),
  daily_limit_check 경계, fds_verdict 정확히 0.5 비율 → "정상" / 0.5 초과 → "주의",
  sod_check 3인 상이 → ok / 2인 중복(예: requested_by==decided_by) → not ok.
  ⚠ 이 신규 테스트 파일은 CLAUDE.md "회귀 스위트" 절의 pytest 커맨드 목록(현재 "3파일 합산")에
  아직 반영돼 있지 않다 — 이 태스크의 DoD 에는 포함하지 않지만, `/done` 세션 마무리 시점에
  CLAUDE.md 갱신이 필요함을 커밋 메시지나 세션 로그에 남길 것.

---

### MQ-1704 — `po_drafts` 상태 전이 규칙 확장

- **복무 시나리오**: S5+
- **변경 파일**: `backend/services/po.py` (수정)
- **인터페이스**:
  ```python
  ALLOWED_FROM: dict[str, str] = {
      "pending": "draft",
      "approved": "pending",
      "rejected": "pending",
      "finance_approved": "approved",
      "finance_rejected": "approved",
  }

  def _finance_transition(
      po_id: str,
      target: str,                  # "finance_approved" | "finance_rejected"
      finance_decided_by: str,
      note: str | None,
      db_path: Path | None = None,
  ) -> dict: ...                    # get_po() 와 같은 셰이프, 실패 시 KeyError/TransitionError
  ```
  기존 `transition(po_id, target, decided_by=None, note=None, db_path=None) -> dict`의
  시그니처는 **변경하지 않는다** — 내부 구현만 `decided_at` 컬럼을 함께 쓰도록 확장.
- **핵심 로직**:
  1. `ALLOWED_FROM`에 `"finance_approved": "approved"`, `"finance_rejected": "approved"`
     두 항목 추가(위 그대로).
  2. 기존 `transition()`의 else 분기(현재 "`target == "pending"` 이 아니면" 분기, 387~390번째
     줄 부근)를 다음처럼 바꾼다 — `decided_at`을 함께 찍는다:
     ```python
     from backend.services.decisions import now_utc_sql

     def transition(po_id, target, decided_by=None, note=None, db_path=None) -> dict:
         with connect(db_path) as con:
             r = con.execute("SELECT state FROM po_drafts WHERE po_id = ?", (po_id,)).fetchone()
             if r is None:
                 raise KeyError(po_id)
             if r["state"] != ALLOWED_FROM[target]:
                 raise TransitionError(po_id, r["state"], target)
             if target == "pending":
                 con.execute("UPDATE po_drafts SET state = ? WHERE po_id = ?", (target, po_id))
             else:
                 con.execute(
                     "UPDATE po_drafts SET state = ?, decided_by = ?, decision_note = ?,"
                     " decided_at = ? WHERE po_id = ?",
                     (target, decided_by, note, now_utc_sql(), po_id),
                 )
         return get_po(po_id, db_path) or {}
     ```
     `from backend.services.decisions import now_utc_sql`는 파일 상단 import 블록에 추가
     (이미 `backend/services/repairs.py`가 같은 방식으로 재사용하는 선례가 있다 — 순환
     임포트 없음, `decisions.py`는 `po.py`를 import 하지 않는다. 구현 전 `python -c "from
     backend.services import po"`로 순환 임포트 없음을 재확인할 것).
  3. 새 함수 `_finance_transition()`을 `transition()` 바로 아래에 추가한다 —
     `decided_by`/`decision_note` 대신 `finance_decided_by`/`finance_decision_note`/
     `finance_decided_at` 3컬럼을 쓴다(스펙 §3 — 3자 서명 각각 독립 기록):
     ```python
     def _finance_transition(
         po_id: str,
         target: str,
         finance_decided_by: str,
         note: str | None,
         db_path: Path | None = None,
     ) -> dict:
         """재무 승인 전이. 팀장 전용 `decided_by`/`decision_note`와 별도 컬럼 3종을 쓴다."""
         with connect(db_path) as con:
             r = con.execute("SELECT state FROM po_drafts WHERE po_id = ?", (po_id,)).fetchone()
             if r is None:
                 raise KeyError(po_id)
             if r["state"] != ALLOWED_FROM[target]:
                 raise TransitionError(po_id, r["state"], target)
             con.execute(
                 "UPDATE po_drafts SET state = ?, finance_decided_by = ?,"
                 " finance_decision_note = ?, finance_decided_at = ? WHERE po_id = ?",
                 (target, finance_decided_by, note, now_utc_sql(), po_id),
             )
         return get_po(po_id, db_path) or {}
     ```
  4. 파일 상단 모듈 docstring(1~14번째 줄, ASCII 상태 다이어그램 포함)을 갱신해
     `approved` 뒤 재무 승인 두 갈래를 반영한다.
  5. `dispatch_a2a_withdrawal_request()`의 독스트링(현재 "S5: approved 상태의 발주서를..."
     로 시작)에서 "approved" 를 "finance_approved" 로 바꾼다 — **함수 본문은 건드리지
     않는다**, 어디서 호출되는지(라우터의 어느 엔드포인트)는 Stage 2(MQ-1705)의 몫이고
     이 함수 자체는 이번 스프린트에서 로직이 바뀌지 않는다.
- **엣지 케이스**:
  - `TransitionError`의 메시지 조립(`f"... ('{ALLOWED_FROM[target]}' 에서만 가능)"`)이
    새 target 값(`finance_approved`/`finance_rejected`)에서도 KeyError 없이 동작하는지 —
    `ALLOWED_FROM`에 두 값이 이미 있으므로 자동으로 안전하다.
  - `_finance_transition()`을 `finance_rejected` 상태의 발주에 다시 호출하면(이미 종결)
    `ALLOWED_FROM["finance_approved"] == "approved"`인데 현재 상태가 `finance_rejected`라
    `TransitionError`로 정상 거부된다 — 별도 코드 불필요, 자연히 막힌다.
- **지켜야 할 결정**: D10(MCP 도구는 여전히 draft INSERT 만 — 이 태스크는 MCP 도구를
  전혀 건드리지 않는다) · D38(403/409 구분 — 이 파일은 서비스 계층이라 HTTP 매핑은
  Stage 2 라우터가 함, 여기선 `TransitionError`/`KeyError` 예외만 던진다)
- **DoD**: 순환 임포트 없음(`python -c "from backend.services import po"` 성공).
  기존 `transition()` 호출부(라우터의 submit/approve/reject)가 그대로 동작(회귀 없음) —
  Stage 2 진입 전에 `uv run --with pytest --with pytest-asyncio python -m pytest
  backend/routers/test_po_a2a_trigger.py -q`(개조 전 원본)가 여전히 통과하는지로 확인
  가능(단, 이 파일 자체는 Stage 2·MQ-1707 이 재작성하므로 이 시점엔 원본 그대로 통과해야
  한다는 뜻).

---

### MQ-1705 — `finance-approve`/`finance-reject` 엔드포인트 + A2A 이동

- **복무 시나리오**: S5+
- **변경 파일**: `backend/routers/po.py` (수정), `docs/06_REPO_API.md` (수정, §2.2·§2.4)
- **인터페이스**:
  ```
  POST /api/po/{po_id}/finance-approve   # approved → finance_approved (재무부 manager 전용)
       body: { note?: string | null }     (기존 ApproveBody 재사용)
       → 200 get_po() 셰이프
       → 403 role≠manager · 403 department≠finance · 404 없음 · 409 상태 순서 위반

  POST /api/po/{po_id}/finance-reject    # approved → finance_rejected (재무부 manager 전용)
       body: { reason: string }           (기존 RejectBody 재사용, min_length=1 → 422)
       → 200 get_po() 셰이프
       → 403 role≠manager · 403 department≠finance · 404 없음 · 409 상태 순서 위반 · 422 사유 공백
  ```
- **핵심 로직**:
  1. 기존 `approve()`(현재 156~174번째 줄)에서 `dispatch_a2a_withdrawal_request` 호출
     블록(`try: await svc.dispatch_a2a_withdrawal_request(po_id) except Exception: ...`)을
     **제거**하고, `async def approve(...)` → `def approve(...)`(동기)로 되돌린다.
     독스트링에서 "승인 완료 직후 FinAllQ에 출금 요청..." 문단을 제거하고 대신:
     "FinAllQ 출금 요청 전송은 더 이상 여기서 하지 않는다 — 재무 승인(finance-approve)
     시점으로 이동했다(D119). 팀장 승인은 재무 승인 대기 상태로 넘기는 것뿐이다." 로 교체.
  2. 새 헬퍼(기존 `_transition()`과 이름이 겹치지 않게 `_finance_transition_http`로 명명 —
     스펙 §4 원문은 서비스 함수와 같은 이름을 썼으나 같은 파일 안에서 이름이 충돌하므로
     이 프로젝트에선 라우터 쪽 이름을 분리한다):
     ```python
     def _finance_transition_http(
         po_id: str, target: str, finance_decided_by: str, note: str | None
     ) -> dict:
         try:
             return svc._finance_transition(po_id, target, finance_decided_by, note)
         except KeyError as e:
             raise HTTPException(404, f"발주서를 찾을 수 없습니다: {po_id}") from e
         except svc.TransitionError as e:
             raise HTTPException(409, str(e)) from e
     ```
  3. 신규 엔드포인트:
     ```python
     @router.post("/{po_id}/finance-approve")
     async def finance_approve(
         po_id: str, body: ApproveBody | None = None, c: Caller = Depends(caller)
     ) -> dict:
         """approved → finance_approved. 재무부 소속 manager 전용 (SoD, D119).
         승인 직후 FinAllQ에 출금 요청(A2A request-withdrawal, S5)을 보낸다 — approve()가
         갖던 자리에서 이동해 왔다. 전송 실패는 승인 자체를 되돌리지 않는다."""
         require(c, "manager", "자금집행 승인")
         if c.department != "finance":
             raise HTTPException(403, "자금집행 승인은 재무부 소속만 수행할 수 있습니다 (D119)")
         result = _finance_transition_http(
             po_id, "finance_approved", c.user_id, body.note if body else None
         )
         try:
             await svc.dispatch_a2a_withdrawal_request(po_id)
         except Exception:
             logger.exception("A2A request-withdrawal 전송 실패: po_id=%s", po_id)
         return result


     @router.post("/{po_id}/finance-reject")
     def finance_reject(po_id: str, body: RejectBody, c: Caller = Depends(caller)) -> dict:
         """approved → finance_rejected. 사유 필수 (D38). 재무부 소속 manager 전용 (D119)."""
         require(c, "manager", "자금집행 반려")
         if c.department != "finance":
             raise HTTPException(403, "자금집행 반려는 재무부 소속만 수행할 수 있습니다 (D119)")
         return _finance_transition_http(po_id, "finance_rejected", c.user_id, body.reason)
     ```
     **역할 체크(`require`)가 소속 체크보다 먼저** — technician 이 호출하면 role 에러
     메시지(403)가 나오고, department 미배정 manager 가 호출하면 소속 에러 메시지(403)가
     나온다. 순서를 바꾸면 technician 호출 시 엉뚱하게 "재무부만" 메시지가 나가 D38 이
     구분해 둔 403 사유가 흐려진다.
  4. `docs/06_REPO_API.md §2.2` 엔드포인트 블록에 두 줄 추가(기존 `POST /api/po/{po_id}/reject`
     줄 아래):
     ```
     POST /api/po/{po_id}/finance-approve # approved → finance_approved (재무부 manager 전용, D119)
                                          #   승인 직후 FinAllQ 출금 요청(S5) 전송 — approve() 자리에서 이동
     POST /api/po/{po_id}/finance-reject  # approved → finance_rejected (재무부 manager 전용, body: {reason})
     ```
  5. `docs/06_REPO_API.md §2.4` 상태 전이 다이어그램의 `[발주 po_drafts]` 블록을 스펙 §2 의
     다이어그램(`finance_pending` 은 개념적 표기일 뿐 실제 DB 값이 아님을 각주로 명시)으로
     교체한다.
- **엣지 케이스**:
  - `finance_approve`에서 `_finance_transition_http`가 404/409 를 던지면 그 아래
    `dispatch_a2a_withdrawal_request` 호출부에 **도달하지 않는다**(예외가 함수를 빠져나감) —
    실패한 전이에서 A2A 를 잘못 트리거하지 않는다는 뜻. 이 순서를 바꾸지 말 것.
  - `finance_reject`는 async 로 만들 필요가 없다(A2A 호출이 없으므로) — 동기 함수 유지.
- **지켜야 할 결정**: D119(이번에 등재, MQ-1701 선행 필수) · D38(403/409/422 구분 유지) ·
  D10(사람 전용 REST, MCP 도구 아님 — 이 태스크는 `mcp_server/` 를 전혀 건드리지 않는다)
- **DoD**: 손으로 `uvicorn backend.main:app`을 띄우고 `curl`로 세 가지(technician 403,
  mgr-01(department=maintenance) 403, mgr-02(department=finance) 200) 확인 가능한 상태.
  `docs/06_REPO_API.md`의 §2.2·§2.4 표/다이어그램이 실제 코드와 문자 그대로 일치. 정식 검증은
  MQ-1706·MQ-1707 회귀로 한다(이 태스크 자체는 그 회귀가 통과하는 것으로 완료를 확인).

---

### MQ-1706 — 회귀: REST 계약(403/409/200)

- **복무 시나리오**: S5+
- **변경 파일**: `spikes/api_contract.py` (수정)
- **인터페이스**: 없음(회귀 스크립트, 신규 함수 노출 안 함) — MQ-1705 가 정의한 엔드포인트
  계약을 그대로 검증 대상으로 삼는다.
- **핵심 로직**:
  1. 새 헤더 상수 추가(기존 `TECH`/`MGR` 옆, 35~36번째 줄 부근):
     ```python
     MGR_FIN = {"X-Role": "manager", "X-User": "mgr-02"}
     ```
  2. `PO_LIST_ITEM_KEYS`(44~51번째 줄) 갱신 — **실행 시점에 먼저 `set(get_po 응답 키)`를
     실측해 프리셋과 대조할 것**(이 문서 작성 시점 실측으로는 이미 `alternatives`·
     `error_code_def`·`documents_preview` 가 `PO_DETAIL_KEYS`에 없는 드리프트가 발견됐다 —
     사용자가 별도 터미널에서 회귀 기준선을 갱신 중이라 이 드리프트가 이미 해소돼 있을 수도
     있다. **옛 스냅샷을 기준으로 삼지 말고, 실행 시점 실제 응답과 대조해 프리셋을 그
     실측값에 맞춘 뒤, 이번 스프린트가 추가하는 4개 컬럼만 그 위에 더할 것**):
     `decided_at`, `finance_decided_by`, `finance_decision_note`, `finance_decided_at`
     네 키를 `PO_LIST_ITEM_KEYS`에 추가(`PO_DETAIL_KEYS`는 `PO_LIST_ITEM_KEYS`를 상속하므로
     자동 반영).
  3. 기존 승인/반려 체크 블록(130~171번째 줄 부근, ④~⑪) 뒤에 새 체크를 추가한다 —
     번호는 파일의 마지막 체크 번호(원문자) 다음부터 이어서 매길 것(실행 시점 실측):
     - technician(`TECH`) 이 `POST /api/po/PO-0114/finance-approve` 호출 → **403**
       (role 사유 메시지에 "자금집행 승인" 문자열 포함하는지도 확인).
     - mgr-01(`MGR`, department=maintenance) 이 `POST /api/po/PO-0114/finance-approve`
       호출 → **403** (소속 사유 메시지에 "재무부" 문자열 포함 확인) — role 은 통과했지만
       department 가 다른 경우를 role 실패와 구분해서 검증.
     - mgr-02(`MGR_FIN`) 이 `POST /api/po/PO-0117/finance-approve` 호출(PO-0117 은 시드상
       `pending` 상태) → **409**(`ALLOWED_FROM["finance_approved"] == "approved"`인데
       현재 `pending`).
     - mgr-02 가 `POST /api/po/PO-0114/finance-approve` 호출(PO-0114 는 `approved`) →
       **200**, 응답 `state == "finance_approved"`, `finance_decided_by == "mgr-02"`,
       `finance_decided_at` not null.
     - mgr-02 가 `POST /api/po/PO-0120/finance-reject` 호출(PO-0120, `approved`, MQ-1702 가
       마련한 예비 픽스처) body `{"reason": "일일 한도 초과"}` → **200**, `state ==
       "finance_rejected"`, `finance_decision_note == "일일 한도 초과"`.
     - mgr-02 가 `POST /api/po/PO-0114/finance-reject`(방금 finance_approved 로 이미 종결된
       건) 재호출 → **409**(이미 종결 상태에서 다시 반려 시도).
  4. `docs/06_REPO_API.md`와의 "403 vs 409" 서술이 이번 department 403 도 포괄하는지 텍스트
     확인만(코드 수정 아님).
- **엣지 케이스**: PO-0114 는 이 태스크의 4번째 체크에서 `finance_approved`로 소비되므로,
  그 뒤 순서의 체크(5번째: 이미 종결 상태에서 반려 재시도)는 **반드시 4번째 체크 다음에**
  실행돼야 한다(같은 스크립트 안 순서 보장 — `run()` 함수 내 순차 실행이므로 자연히 보장됨,
  단 체크 순서를 뒤섞지 말 것).
- **지켜야 할 결정**: D38(403 vs 409 구분이 이 스프린트로 흐려지지 않는지 — department 403
  도 "권한 위반 차단" 지표에 포함되는 것이 맞다, 상태 순서 위반과 섞이지 않아야 함)
- **DoD**: `uv run python spikes/api_contract.py` 전건 PASS(새로 추가한 체크 포함, 기존 체크
  회귀 없음). 실행 전 `data/seed.py --with-error-codes` 재시드 필수(PO-0118~0120 픽스처
  반영 위해).

---

### MQ-1707 — 회귀: A2A 트리거 이동 재검증

- **복무 시나리오**: S5+
- **변경 파일**: `backend/routers/test_po_a2a_trigger.py` (수정 — 사실상 재작성)
- **인터페이스**: 없음(pytest 파일)
- **핵심 로직**:
  1. **중요한 선행 사실**: 이 파일이 쓰는 `db_path`/`seed_po`/`link_finallq` 픽스처는
     `backend/conftest.py`에 있고, **격리 스키마를 `clone_data=False`로 만들어 `users`
     테이블이 비어 있다.** `seed_po()`는 `decided_by` 사용자 하나만
     `INSERT OR IGNORE INTO users (user_id, display_name, role) VALUES (...)`로 넣고
     **`department` 컬럼은 채우지 않는다**(NULL로 남음). 재무 승인자(`mgr-02`,
     `department='finance'`) 는 이 스키마에 **존재하지 않으므로**, finance-approve 성공
     경로를 테스트하려면 이 파일 안에서 **직접** `users` 행을 만들어야 한다. `conftest.py`는
     이 스프린트에서 건드리지 않는다(다른 A2A 테스트 파일들이 공유하는 인프라라 변경 범위를
     최소화 — 이 파일 로컬 헬퍼로 충분).
  2. 파일 상단에 로컬 헬퍼 추가:
     ```python
     from data import dbcompat

     def _seed_finance_manager(db_path: str, user_id: str = "mgr-02") -> None:
         con = dbcompat.connect_dsn(db_path)
         try:
             con.execute(
                 "INSERT INTO users (user_id, display_name, role, department)"
                 " VALUES (?, ?, 'manager', 'finance')",
                 (user_id, user_id),
             )
             con.commit()
         finally:
             con.close()
     ```
     새 헤더 상수 `MANAGER_FINANCE = {"X-Role": "manager", "X-User": "mgr-02"}` 추가.
  3. 기존 5개 테스트를 다음처럼 재편한다(테스트 함수명·내용 변경 — 파일 헤더 독스트링도
     "승인 직후" → "재무 승인 직후"로 갱신):
     - `test_manager_approve_triggers_a2a_dispatch` → **`test_manager_approve_does_not_trigger_a2a_dispatch`**
       로 개명. `seed_po(po_id="PO-001", state="pending", ...)`, `MANAGER`로
       `/api/po/PO-001/approve` 호출 → `200` + `state=="approved"` 확인은 유지하되,
       **`captured`(call_skill 인자)가 비어 있어야 함**(`assert not captured`)으로 단언
       반전.
     - **신규** `test_finance_approve_triggers_a2a_dispatch`: `seed_po(po_id="PO-001",
       state="approved", unit_price=10000, qty=3)` + `_seed_finance_manager(db_path)` +
       `link_finallq(...)` + `MAINTQ_A2A_FINALLQ_BASE_URL` env 설정 →
       `MANAGER_FINANCE`로 `/api/po/PO-001/finance-approve` 호출 → `200` +
       `state=="finance_approved"` + `captured["skill_id"]=="request-withdrawal"` +
       `captured["payload"]["amount"]==30000`(기존 happy-path 검증 이관).
     - `test_technician_cannot_approve_and_a2a_is_never_called` — **그대로 유지**(approve
       경로, technician 403, A2A 호출 안 됨 — 이 계약은 안 바뀜). 추가로 같은 파일에
       `test_technician_cannot_finance_approve_and_a2a_is_never_called` 신규 — 위와 같은
       구조로 `/finance-approve`에 technician 헤더 → 403, `called is False`.
     - `test_a2a_failure_does_not_undo_approval` → **`test_a2a_failure_does_not_undo_finance_approval`**
       로 이관: `seed_po(state="approved")` + `_seed_finance_manager` + `link_finallq` →
       `MANAGER_FINANCE`로 `/finance-approve` 호출, `call_skill`이
       `A2AUpstreamUnavailableError` 던지도록 monkeypatch → 응답은 여전히 `200` +
       `state=="finance_approved"`(전송 실패가 승인을 되돌리지 않음, 기존 계약 그대로
       이관). 기존 `approve()` 대상 버전은 이제 A2A 자체가 안 얽히므로 이 테스트는 완전히
       finance-approve 로 옮긴다(approve() 용 버전은 필요 없음 — A2A 가 안 걸리니 "실패해도
       되돌리지 않는다"는 명제 자체가 approve() 에는 더 이상 성립할 일이 없다).
     - `test_dispatch_is_noop_when_base_url_not_configured` → **`finance-approve`**
       대상으로 이관(같은 이유).
     - `test_reject_does_not_trigger_a2a` — **그대로 유지**(reject 경로는 원래도 A2A 와
       무관, 안 바뀜). 추가로 `test_finance_reject_does_not_trigger_a2a` 신규(같은 구조,
       `/finance-reject` 대상, `_seed_finance_manager` 필요).
  4. 모든 신규/이관 테스트에서 `finance-approve`/`finance-reject` 호출 전에 반드시
     `_seed_finance_manager(db_path)`를 호출할 것 — 빠뜨리면 `caller()`가
     `department=None`을 주입해 항상 403(department 사유)이 나고, 테스트가 의도와 다른
     이유로 "우연히" 통과하거나 실패해 원인 파악이 어려워진다.
- **엣지 케이스**: `seed_po()`가 `decided_by="mgr-01"` 사용자를 이미 만들어 두므로,
  `_seed_finance_manager`가 같은 `user_id`(`mgr-02`)로 두 번 불리지 않도록 각 테스트 함수
  안에서 한 번만 호출할 것(`INSERT`이지 `INSERT OR IGNORE`가 아니므로 중복 호출 시 PK
  충돌 — 필요하면 `INSERT OR IGNORE`로 바꿔도 무방, 두 방식 다 허용).
- **지켜야 할 결정**: D119(department 게이트) · 기존 파일 독스트링이 명시한 두 계약
  ("팀장 아니면 403", "A2A 실패가 승인을 되돌리지 않는다")은 **대상만 finance-approve로
  옮겨 계속 성립해야 한다** — 계약 자체를 없애는 게 아니라 이관하는 것.
- **DoD**: `uv run --with pytest --with pytest-asyncio python -m pytest
  backend/routers/test_po_a2a_trigger.py -q` 전건 PASS. `backend/services/test_po_a2a_dispatch.py`
  (함수 레벨 테스트, 이 태스크에서 변경하지 않음)도 함께 재실행해 회귀 없음 확인.

---

### MQ-1708 — `get_po()` 내부통제 계산 + A2A 이력 조회 + doc3 게이트

- **복무 시나리오**: S5+
- **변경 파일**: `backend/services/po.py` (수정)
- **인터페이스**: `get_po()`의 반환 딕셔너리 **최상위 키 집합은 늘리지 않는다** — 내부
  통제 판정값(`controls`)과 A2A 이력(`a2a_info`)·공급사 계좌(`payee`)는 `get_po()` 안의
  **지역 변수**로만 존재하고, `po_documents.render_fund_execution_document()` 호출 인자로만
  전달한 뒤 버린다(D86 정신 — 저장·별도 API 노출 없이 조회 시점에만 조립).
  ```python
  # get_po() 내부, documents_preview 조립 지점에 추가
  _FUND_EXECUTION_STATES = ("approved", "finance_approved", "finance_rejected")

  # controls 모양 (Stage 3 계약 — MQ-1709 가 그대로 소비):
  controls = {
      "budget": (bool, str),        # expenditure_limits.budget_check() 그대로
      "daily_limit": (bool, str),   # expenditure_limits.daily_limit_check() 그대로
      "fds": (str, str),            # expenditure_limits.fds_verdict() 그대로 ("정상"|"주의", 설명)
      "sod": (bool | None, str),    # finance_decided_by 가 None 이면 (None, "확인 전 — ...")
  }
  # a2a_info 모양: a2a_history.list_a2a_history(...)["items"][0] 그대로, 없으면 None
  # payee 모양: {"account_number": str | None, "bank_code": str | None} | None
  ```
- **핵심 로직**:
  1. `_PO_SELECT`(77~86번째 줄)에 재무 승인자 표시명 LEFT JOIN 추가 —
     ```sql
     SELECT p.*, pt.name AS part_name, s.name AS supplier_name,
            ru.display_name AS requested_by_name, ru.department AS requested_by_department,
            du.display_name AS decided_by_name,
            fu.display_name AS finance_decided_by_name
     FROM po_drafts p
     JOIN parts pt ON pt.part_no = p.part_no
     JOIN suppliers s ON s.supplier_id = p.supplier_id
     LEFT JOIN users ru ON ru.user_id = p.requested_by
     LEFT JOIN users du ON du.user_id = p.decided_by
     LEFT JOIN users fu ON fu.user_id = p.finance_decided_by
     ```
     `_row_to_po()`에 `d["finance_decided_by_name"] = d.get("finance_decided_by_name") or
     d.get("finance_decided_by") or ""` 한 줄 추가(기존 `decided_by_name` 처리와 같은 패턴).
     ⚠ 이 변경으로 `list_pos()`·`get_po()` 응답에 `finance_decided_by_name`이라는 **새
     최상위 키 하나**가 실제로 추가된다(이건 `documents_preview` 안이 아니라 평평한 필드다,
     기존 `decided_by_name`과 대칭이므로 자연스러운 계약 확장) — MQ-1710 이 `PO_LIST_ITEM_KEYS`
     에 이 키를 추가해야 한다는 뜻, MQ-1708 자신의 DoD 범위는 아님(다음 스테이지 몫).
  2. `get_po()`의 `documents_preview` 조립 지점(현재 358~365번째 줄) 바로 앞에 내부통제·
     A2A·수취인 계산 블록을 추가:
     ```python
     fund_execution = None
     if po["state"] in _FUND_EXECUTION_STATES:
         from data import expenditure_limits as limits
         from backend.services import a2a_history

         amount = po["unit_price"] * po["qty"]
         today_total = con.execute(
             "SELECT COALESCE(SUM(unit_price * qty), 0) FROM po_drafts"
             " WHERE state = 'finance_approved' AND po_id != ?"
             " AND DATE(finance_decided_at) = CURRENT_DATE",
             (po_id,),
         ).fetchone()[0]
         controls = {
             "budget": limits.budget_check(amount),
             "daily_limit": limits.daily_limit_check(amount, today_total),
             "fds": limits.fds_verdict(amount),
             "sod": (
                 limits.sod_check(po["requested_by"], po["decided_by"], po["finance_decided_by"])
                 if po.get("finance_decided_by")
                 else (None, "확인 전 — 재무 승인자가 아직 지정되지 않았습니다")
             ),
         }
         a2a_result = a2a_history.list_a2a_history(
             po_id=po_id, skill="request-withdrawal", limit=1, db_path=db_path
         )
         a2a_info = a2a_result["items"][0] if a2a_result["items"] else None
         payee_row = con.execute(
             "SELECT account_number, bank_code FROM suppliers WHERE supplier_id = ?",
             (po["supplier_id"],),
         ).fetchone()
         payee = dict(payee_row) if payee_row else None
         fund_execution = po_documents.render_fund_execution_document(po, controls, a2a_info, payee)

     po["documents_preview"] = {
         "po_request": po_documents.render_po_request_document(po),
         "diagnosis": po_documents.render_diagnosis_document(po) if po["error_code_def"] else None,
         "fund_execution": fund_execution,
     }
     ```
     ⚠ **`today_total` 쿼리는 반드시 `AND po_id != ?`로 자기 자신을 제외한다** — 그렇지 않으면
     이미 `finance_approved`로 확정된 발주를 다시 조회할 때(예: 승인 직후 화면 재조회) 자기
     금액이 "오늘 누적"에 중복 산입돼 한도 판정이 왜곡된다. 스펙 §5 원문 SQL 에는 이 조건이
     없었으나, 이 자기중복 버그를 막기 위해 이 프로젝트에서 추가한 것 — 반드시 포함할 것.
  3. `import`는 함수 지역 임포트로 유지한다(기존 `dispatch_a2a_withdrawal_request`가
     `backend.a2a.*`를 지역 임포트하는 것과 같은 관례 — 모듈 순환 임포트 회피).
- **엣지 케이스**:
  - `po["finance_decided_by"]`가 `None`(state가 `approved`, 아직 재무 결정 전)이면
    `sod`는 `(None, "확인 전 — ...")` — `limits.sod_check()`를 아예 호출하지 않는다(호출부
    책임, MQ-1703 엣지 케이스 절 참고).
  - `today_total`이 `finance_approved` 상태의 다른 발주만 집계하므로, `state="approved"`
    (아직 재무 미결) 조회 시점에는 그 발주 자신은 애초에 그 SUM 에 안 잡힌다(자기 상태가
    아직 `finance_approved`가 아니므로) — `po_id != ?` 배제는 주로 "이미 승인된 건을 다시
    조회하는 시점"의 자기중복을 막기 위한 것.
  - `a2a_history.list_a2a_history()`는 자체적으로 새 커넥션을 연다(`backend.db.connect()`) —
    `get_po()`가 이미 연 `con`과는 별도 커넥션이다. 트랜잭션 격리상 문제 없음(읽기 전용
    조회이고 같은 트랜잭션에 있을 필요가 없다) — 다만 `db_path`를 반드시 함께 넘겨 격리
    스키마(회귀 테스트 환경)에서도 같은 스키마를 보게 할 것.
- **지켜야 할 결정**: D86(저장하지 않고 조회 시점 렌더 — `controls`/`a2a_info`/`payee`를
  DB 에 쓰지 않는다) · D62(모르는 값은 `확인되지 않음`으로 — `finance_decided_by`가
  None 일 때 SOD 를 지어내지 않는다) · D114(A2A 이력은 `a2a_history.list_a2a_history()`
  한 곳을 재사용 — SQL 을 이 파일에 복제하지 않는다, W2/W5 드리프트 재발 방지)
- **DoD**: `python -c "from backend.services import po"` 순환 임포트 없이 성공.
  MQ-1709 완료 후(같은 스테이지, 병렬이지만 통합은 스테이지 종료 시) `GET /api/po/PO-0118`
  (finance_approved 표본)과 `GET /api/po/PO-0114`(approved, 재무 결정 전 표본) 응답의
  `documents_preview.fund_execution`이 각각 non-null/문서 텍스트를 담고 있는지 수동 확인
  가능한 상태. 정식 검증은 MQ-1710.

---

### MQ-1709 — doc3 렌더 함수 + 검수 플래그

- **복무 시나리오**: S5+
- **변경 파일**: `backend/services/po_documents.py` (수정), `data/doc_review.py` (수정)
- **인터페이스**:
  ```python
  # backend/services/po_documents.py
  def render_fund_execution_document(
      po: dict,
      controls: dict[str, tuple],   # MQ-1708 이 정의한 모양 그대로
      a2a_info: dict | None,        # MQ-1708 이 정의한 모양 그대로
      payee: dict | None,           # {"account_number": str|None, "bank_code": str|None} | None
  ) -> str: ...

  # data/doc_review.py — 기존 PO_REQUEST_TEMPLATE_REVIEWED / DIAGNOSIS_TEMPLATE_REVIEWED 와 같은 패턴
  FUND_EXECUTION_TEMPLATE_REVIEWED: bool = False
  FUND_EXECUTION_TEMPLATE_REVIEWED_AT: str | None = None
  def fund_execution_template_review_notice() -> str: ...
  ```
- **핵심 로직**:
  1. `data/doc_review.py`에 기존 `PO_REQUEST_TEMPLATE_REVIEWED`/`DIAGNOSIS_TEMPLATE_REVIEWED`
     블록(35~42번째 줄) 바로 아래에 같은 패턴으로 추가:
     ```python
     # ── 자금집행요청서 (03, D118·D119) — data/templates/03_자금집행요청서.docx 문구를
     #    옮긴 렌더 문안. 아직 사람이 검수하지 않았다 — 승인 전까지는 아래를 False 로 둔다.
     FUND_EXECUTION_TEMPLATE_REVIEWED = False
     FUND_EXECUTION_TEMPLATE_REVIEWED_AT: str | None = None

     def fund_execution_template_review_notice() -> str:
         return _notice(FUND_EXECUTION_TEMPLATE_REVIEWED, FUND_EXECUTION_TEMPLATE_REVIEWED_AT)
     ```
  2. `po_documents.py`에 기존 `_DOC_STATUS_LABEL`/`_APPROVAL_RESULT_LABEL`(37~49번째 줄)에
     신규 상태 2종 추가(doc1·doc2 렌더가 `finance_approved`/`finance_rejected` 발주를 그릴
     때도 원문 상태 문자열 대신 한글 라벨이 나오게):
     ```python
     _DOC_STATUS_LABEL = {
         "draft": "초안 (미제출)", "pending": "결재 대기", "approved": "승인 완료",
         "rejected": "반려",
         "finance_approved": "재무 승인 완료", "finance_rejected": "재무 반려",
     }
     _APPROVAL_RESULT_LABEL = {
         "draft": "미제출", "pending": "결재 대기 중", "approved": "승인",
         "rejected": "반려",
         "finance_approved": "재무 승인", "finance_rejected": "재무 반려",
     }
     ```
     `render_po_request_document()`의 `approver_signed_at` 계산(현재 123번째 줄
     `po["state"] in ("approved", "rejected")`)도 4-상태로 확장:
     `po["state"] in ("approved", "rejected", "finance_approved", "finance_rejected")`
     (같은 로직을 쓰는 `render_diagnosis_document()`의 `manager_signed_at`, 현재 222번째
     줄도 동일하게 확장).
  3. `render_fund_execution_document()` 신규 함수 — 기존 두 렌더 함수와 같은 문체(`_val`·
     `_won`·`_UNKNOWN` 헬퍼 재사용). 스펙 §0 이 실측한 플레이스홀더 전체를 채운다:
     ```python
     _FUND_TYPE = "부품 구매대금"       # 고정 — S1/S2 발주 전용 문서라 항상 이 값 (담보/대출 아님)
     _FUNDING_METHOD = "계좌이체"        # 고정 — A2A request-withdrawal 전제
     _MFA_STATUS_TEXT = "미구현 (MaintQ 에 MFA 시스템 없음)"  # D118 이 이미 이 문구를 확정

     def _mask_account(acct: str | None) -> str:
         if not acct:
             return _UNKNOWN
         return acct[-4:].rjust(len(acct), "*") if len(acct) > 4 else acct

     def _fund_a2a_lines(a2a_info: dict | None) -> tuple[str, str, str]:
         """(A2A_DELEGATED, A2A_TARGET, REQUEST_CHAIN_ID) 3필드."""
         if a2a_info is None:
             return "아니오 (아직 전송되지 않음)", _UNKNOWN, _UNKNOWN
         delegated = "예" if a2a_info.get("status") == "ok" else "예 (전송 실패 또는 처리 중)"
         return delegated, "FinAllQ", a2a_info["request_chain_id"]

     def render_fund_execution_document(
         po: dict, controls: dict, a2a_info: dict | None, payee: dict | None
     ) -> str:
         qty, unit_price = po["qty"], po["unit_price"]
         subtotal = unit_price * qty
         vat = round(subtotal * 0.1)
         total = subtotal + vat

         budget_ok, budget_evidence = controls["budget"]
         daily_ok, daily_evidence = controls["daily_limit"]
         fds_verdict, fds_evidence = controls["fds"]
         sod_ok, sod_evidence = controls["sod"]

         delegated, target, chain_id = _fund_a2a_lines(a2a_info)
         payee_bank = _val(payee.get("bank_code")) if payee else _UNKNOWN
         payee_account = _mask_account(payee.get("account_number")) if payee else _UNKNOWN

         doc_status = _DOC_STATUS_LABEL.get(po["state"], po["state"])
         approval_result = _APPROVAL_RESULT_LABEL.get(po["state"], po["state"])
         diagnosis_doc_no = f"DIAG-{po['po_id']}" if po.get("error_code_def") else _UNKNOWN

         return f"""[자금집행 요청서 — {doc_status}]
     요청번호: FUND-{po["po_id"]}
     요청일시: {_val(po.get("decided_at"))}
     연계 발주요청서: {po["po_id"]}
     연계 진단서: {diagnosis_doc_no}
     기안 부서/기안자: {_val(po.get("requested_by_department"))} / {_val(po.get("requested_by_name"))}
     결재선(Chain ID): {chain_id}
     자금 종류: {_FUND_TYPE}

     1. 집행 목적 및 금액
          · 목적: {po["reason"]}
          · 금액: {_won(total)}원 ({amount_to_korean(total)})
          · 집행 예정일: {_UNKNOWN} (시스템이 별도로 기록하지 않음)
          · 집행 방법: {_FUNDING_METHOD}

     2. 수취인
          · 수취인명(공급사): {po["supplier_name"]}
          · 사업자번호: {_UNKNOWN} (suppliers 테이블에 없음)
          · 은행: {payee_bank}
          · 계좌(마스킹): {payee_account}

     3. 담보 · 대출 (해당 시)
          · 해당 없음 — 본 문서는 일반 부품 발주(S1/S2) 전용이며 담보·대출 취급 대상이 아니다

     4. 내부통제 확인
          · 예산 한도: {budget_evidence} — {"통과" if budget_ok else "초과"}
          · 1일 누적 한도: {daily_evidence} — {"통과" if daily_ok else "초과"}
          · FDS 판정: {fds_verdict} — {fds_evidence}
          · 직무분리(SoD): {sod_evidence if sod_ok is None else ("통과" if sod_ok else "위반")} — {sod_evidence}

     5. 서명
          · 기안(정비사): {_val(po.get("requested_by_name"))} / {_val(po.get("created_at"))}
          · 승인(정비팀장): {_val(po.get("decided_by_name"))} / {_val(po.get("decided_at"))}
          · 재무 승인(재무담당): {_val(po.get("finance_decided_by_name"))} / {_val(po.get("finance_decided_at"))}
          · 승인 결과: {approval_result}
          · 재무 의견 / 반려 사유: {_val(po.get("finance_decision_note"))}

     6. A2A 위임 전송
          · 위임 여부: {delegated}
          · 대상 시스템: {target}
          · MFA 상태: {_MFA_STATUS_TEXT}

     ※ {_UNKNOWN}으로 적힌 항목은 「해당 없음」이 아니라 시스템에서 확인되지 않았다는 뜻입니다.
     문서 상태: {doc_status} | 생성 시스템: MaintQ
     ※ {_doc_review.fund_execution_template_review_notice()}"""
     ```
     (들여쓰기·정확한 필드 순서는 스펙 §0 플레이스홀더 나열 순서를 참고해 자유롭게 다듬어도
     좋다 — 위 텍스트는 값 누락 없는 최소 골격이다. `data.doc_review`는 파일 상단에 이미
     `import data.doc_review as _doc_review`로 들어와 있으므로 재사용.)
- **엣지 케이스**:
  - `controls["sod"]`가 `(None, "확인 전 — ...")`일 때 4번 절의 표현이 `"통과"/"위반"` 대신
    `sod_evidence` 그대로 나오도록 위 f-string 의 조건식이 이미 처리한다 —
    `"통과" if sod_ok else "위반"`을 `sod_ok is None`일 때는 안 타도록 먼저 분기.
  - `payee`가 `None`(공급사 행이 어쩌다 없는 극단 상황 — FK 상 사실상 불가능하지만 방어)이면
    은행/계좌 모두 `_UNKNOWN`.
- **지켜야 할 결정**: D86(문안은 코드 상수, 저장 안 함, 조회 시점 렌더) · D118(담보/대출
  섹션은 "해당 없음" 고정, MFA_STATUS 는 "미구현" 고정 — 이 두 문구를 정확히 지킬 것) ·
  D62(모르는 값은 `확인되지 않음`)
- **DoD**: `python -c "from backend.services import po_documents"` 성공. MQ-1708 과 통합
  후(스테이지 종료 시) PO-0118(finance_approved)·PO-0119(finance_rejected, 예산 초과
  표본)·PO-0114(approved, 재무 결정 전) 세 표본의 `render_fund_execution_document()` 출력을
  직접 눈으로 확인해 값 누락(엉뚱한 `None`이 그대로 노출되는 등)이 없는지 확인. 정식 회귀는
  MQ-1710.

---

### MQ-1710 — 회귀: doc3 렌더 계약 + 키집합 동기화

- **복무 시나리오**: S5+
- **변경 파일**: `spikes/api_contract.py` (수정, MQ-1706 완료 이후 이어서 확장)
- **인터페이스**: 없음(회귀 스크립트)
- **핵심 로직**:
  1. `PO_LIST_ITEM_KEYS`에 `finance_decided_by_name` 키 추가(MQ-1708 이 만든 새 평평한
     필드, "엣지 케이스" 아님 — 실제 계약 확장이므로 반드시 반영).
  2. 새 체크 블록(MQ-1706 이 추가한 체크들 뒤, 번호는 실행 시점 마지막 번호 다음부터):
     - `GET /api/po/PO-0118`(finance_approved 표본) → `documents_preview.fund_execution`
       이 `None`이 아니고, 그 텍스트 안에 `"자금집행 요청서"` 문자열과 `"승인"` 계열
       문구가 있는지(정확 문자열은 MQ-1709 최종 구현에 맞춰 유연하게 — 핵심은 **null 이
       아님**과 **budget_check 결과가 "통과"로 나옴**의 확인).
     - `GET /api/po/PO-0119`(finance_rejected, 예산 초과 표본) → `fund_execution` 텍스트
       안에 예산 한도 초과를 나타내는 문구("초과")가 있는지(MQ-1702 가 의도적으로 예산
       초과 금액으로 만든 표본이므로 여기서 `budget_check` 의 `ok=False`가 실제로 드러나야
       한다 — 드러나지 않으면 Stage 3 로직이 잘못된 것).
     - `GET /api/po/PO-0117`(pending, 진단 있음 표본) → `documents_preview.fund_execution`
       이 **`None`**(아직 팀장 승인 전이라 자금집행요청서 자체가 성립하지 않음).
     - `GET /api/po/PO-0116`(pending, model/error_code 없는 S2 표본, 진단서도 이미
       `None`인 기존 표본) → 마찬가지로 `fund_execution`이 `None`.
     - `GET /api/po/PO-0114`(approved, 재무 결정 전) → `fund_execution`은 non-null 이되
       텍스트 안에 재무 승인자 서명란이 미확정 표현(`확인되지 않음` 또는 SOD 관련 "확인
       전" 문구)을 담고 있는지.
  3. 위 체크를 실행하기 전, 이미 MQ-1706 의 체크 순서에서 PO-0114/PO-0120 이 상태를
     소비했다면(finance_approved/finance_rejected 로 전이됨) 이 태스크의 체크가 **그
     이후 상태**를 대상으로 검증하도록 순서를 맞출 것 — 즉 이 태스크의 체크들은
     MQ-1706 이 추가한 체크 블록 **뒤**에 이어 붙인다(같은 파일의 `run()` 순서 안).
- **엣지 케이스**: `PO-0114`가 MQ-1706 의 체크에서 이미 `finance_approved`로 바뀌어
  있으므로, 이 태스크의 "PO-0114 → 재무 승인자 미확정" 체크는 **성립하지 않는다** —
  대신 PO-0120(MQ-1706 의 finance-reject 체크로 `finance_rejected`가 됨) 이나, 만약
  둘 다 소비됐다면 재무 결정 전 `approved` 표본이 스크립트 안에 하나도 안 남는 문제가
  생긴다. **이를 피하려면**: 이 태스크는 MQ-1706 의 체크 순서를 그대로 따라가되,
  "재무 결정 전 approved 표본"에 대한 doc3 non-null 검증은 **PO-0114/PO-0120 을 소비하기
  전 시점**(즉 MQ-1706 체크 블록 안, 4번째 체크 직전)에 끼워 넣어야 한다 — 이 조율은
  `spikes/api_contract.py`가 이미 한 파일에서 두 태스크가 순차로 이어붙이는 구조이므로,
  구현 시점에 **MQ-1706 의 4번째 체크(PO-0114 finance-approve 성공) 바로 앞**에 "PO-0114
  현재 상태에서 `fund_execution` non-null + SOD 미확정 문구" 체크를 삽입하도록 조정한다.
  (이 문서가 정한 대로 두 태스크가 정말 순서대로 이어붙기 전에, 최종 구현 시점에 스크립트
  전체를 한 번 검토해 표본 소비 순서와 검증 순서가 어긋나지 않는지 사람이 확인할 것 —
  자동 병렬 작성 특성상 두 태스크 사이의 이런 "표본 소비 순서" 조율은 이 문서로 최대한
  명시했지만, 최종 조립은 리뷰 단계에서 한 번 더 점검이 필요하다.)
- **지켜야 할 결정**: D62(모르는 값 `확인되지 않음`) · D86(저장 없이 조회 시점 렌더)
- **DoD**: `uv run python spikes/api_contract.py` 전건 PASS. 실행 전 재시드 필수.

---

### MQ-1711 — 재무부 신원 전환 UX

- **복무 시나리오**: S5+
- **변경 파일**: `frontend/lib/role.ts` (수정), `frontend/components/layout/ManagerIdentitySwitch.tsx`
  (신규), `frontend/components/layout/AppBar.tsx` (수정)
- **인터페이스**:
  ```typescript
  // frontend/lib/role.ts 추가분
  export interface ManagerIdentity {
    userId: string;
    displayName: string;
    department: "maintenance" | "finance";
    label: string;
  }

  export const MANAGER_IDENTITIES: ManagerIdentity[] = [
    { userId: "mgr-01", displayName: "박OO", department: "maintenance", label: "정비팀장 · 박OO" },
    { userId: "mgr-02", displayName: "최OO", department: "finance", label: "재무담당 · 최OO" },
  ];

  export function getManagerIdentity(): ManagerIdentity;   // 기본값 MANAGER_IDENTITIES[0]
  export function setManagerIdentity(userId: string): void;
  ```
  ```typescript
  // frontend/components/layout/ManagerIdentitySwitch.tsx
  export function ManagerIdentitySwitch(): JSX.Element | null;  // props 없음
  ```
- **핵심 로직**:
  1. `role.ts`에 위 인터페이스를 그대로 추가. localStorage 키
     `"maintq_manager_identity"` 사용, `typeof window === "undefined"` 가드 필수(SSR 안전).
     ```typescript
     const MANAGER_IDENTITY_KEY = "maintq_manager_identity";

     export function getManagerIdentity(): ManagerIdentity {
       if (typeof window === "undefined") return MANAGER_IDENTITIES[0];
       const stored = window.localStorage.getItem(MANAGER_IDENTITY_KEY);
       return MANAGER_IDENTITIES.find((m) => m.userId === stored) ?? MANAGER_IDENTITIES[0];
     }

     export function setManagerIdentity(userId: string): void {
       if (typeof window === "undefined") return;
       window.localStorage.setItem(MANAGER_IDENTITY_KEY, userId);
     }
     ```
     기존 `ROLE_USER_ID.manager`(현재 `"mgr-01"` 고정)는 **그대로 둔다** — 기본값·폴백으로
     계속 쓰이므로 삭제하지 말 것(다른 코드가 이미 참조 중일 수 있음, 실행 시점에
     `grep -rn "ROLE_USER_ID" frontend/`로 참조처를 먼저 확인).
     `role.ts`는 React 를 import 하지 않는 순수 함수 모듈 원칙을 유지할 것(L1 게이트 — 기존
     `lib/*.ts` 관례).
  2. `ManagerIdentitySwitch.tsx` 신규 — `"use client"`, `usePathname()`으로 현재 라우트가
     manager 인지 확인(`roleFromPath`), technician 라우트에서는 `return null`. manager
     라우트에서는 `MANAGER_IDENTITIES`를 순회하는 작은 세그먼트 버튼(기존 `RoleTabs.tsx`와
     비슷한 시각 스타일 — `sx()` 유틸 재사용, 같은 톤의 `--sw`/`--sw-line` 변수 사용). 클릭 시
     `setManagerIdentity(m.userId)` 호출 후 로컬 `useState`로 강제 리렌더(또는
     `window.location.reload()` 없이 상태만 바꿔도 다음 API 호출부터 반영되므로 새로고침
     불필요 — 단 화면에 그려진 값들은 컴포넌트가 다시 데이터를 fetch 해야 갱신되므로, 이
     컴포넌트 자체는 시각적 "현재 선택됨" 표시만 책임지고 나머지 화면 갱신은 MQ-1714 가
     담당).
  3. `AppBar.tsx`에 `<ManagerIdentitySwitch />`를 `<RoleTabs .../>` 옆에 배치(`<div
     style={sx("width:1px;...")} />` 구분선 뒤 등 기존 레이아웃 관례를 따를 것).
- **엣지 케이스**:
  - `localStorage`에 유효하지 않은 값이 남아 있으면(예: 예전 버전 잔여) `find()`가
    `undefined`를 반환하고 `?? MANAGER_IDENTITIES[0]`로 안전하게 폴백한다.
  - `MANAGER_IDENTITIES[0]`이 항상 `mgr-01`(department: maintenance)이어야 기존 회귀
    (프론트 라우트 개수·기존 데모 스크립트)가 그대로 통과한다 — 배열 순서를 바꾸지 말 것.
- **지켜야 할 결정**: D52(시뮬레이션 신원 태도 유지 — 실제 인증 아님, 로그인 시스템을
  새로 만들지 않는다) · D36(X-User 는 ASCII — `mgr-01`/`mgr-02` 둘 다 이미 ASCII)
- **DoD**: `npx tsc --noEmit` 통과. `npx next build` 성공(라우트 개수 불변 — 새 페이지
  라우트를 추가하지 않았으므로). 수동 확인: `/manager` 진입 후 스위치로 재무담당 선택 →
  `localStorage.getItem("maintq_manager_identity")`가 `"mgr-02"`로 바뀜. `/technician`
  라우트에서는 스위치 컴포넌트가 렌더되지 않음(DOM 에 없음).

---

### MQ-1712 — API 클라이언트/타입 확장

- **복무 시나리오**: S5+
- **변경 파일**: `frontend/lib/api.ts` (수정), `frontend/lib/types.ts` (수정),
  `frontend/lib/queueState.ts` (수정), `frontend/lib/__checks__/ui_honesty.ts` (수정 —
  tool-builder 현실성 평가에서 발견, 아래 7-b)
- **인터페이스**:
  ```typescript
  // types.ts
  export type PoState =
    | "draft" | "pending" | "approved" | "rejected"
    | "finance_approved" | "finance_rejected";

  // api.ts
  export interface ApiPo {
    // ... 기존 필드 전부 유지 ...
    state: "draft" | "pending" | "approved" | "rejected" | "finance_approved" | "finance_rejected";
    finance_decided_by: string | null;
    finance_decided_by_name: string;
    finance_decision_note: string | null;
    decided_at: string | null;
    finance_decided_at: string | null;
    documents_preview?: { po_request: string; diagnosis: string | null; fund_execution: string | null } | null;
  }

  export const financeApprovePo: (poId: string, note?: string) => Promise<ApiPo>;
  export const financeRejectPo: (poId: string, reason: string) => Promise<ApiPo>;

  // endpoints 객체에 추가
  poFinanceApprove: (poId: string) => string;  // `/api/po/${poId}/finance-approve`
  poFinanceReject: (poId: string) => string;   // `/api/po/${poId}/finance-reject`

  // queueState.ts
  export function isApprovedState(state: string): boolean;  // state === "approved"
  ```
- **핵심 로직**:
  1. `api.ts`의 `authHeaders(role)`(22~24번째 줄)를 신원-인지형으로 바꾼다:
     ```typescript
     import { getManagerIdentity, ROLE_USER_ID, type Role } from "./role";

     export function authHeaders(role: Role): Record<string, string> {
       const userId = role === "manager" ? getManagerIdentity().userId : ROLE_USER_ID.technician;
       return { "X-Role": role, "X-User": userId };
     }
     ```
     (MQ-1711 이 `role.ts`에 `getManagerIdentity`를 export 해 둔 것을 가져다 쓴다 — 파일이
     다르므로 병렬 작성 가능, import 만 맞으면 됨.)
  2. `ApiPo` 인터페이스(155~183번째 줄)에 `state` 유니온 확장 + 신규 필드 5개(위 인터페이스
     절 그대로) 추가. `documents_preview`의 서브타입에 `fund_execution: string | null` 추가.
  3. 신규 클라이언트 함수(기존 `approvePo`/`rejectPo` 바로 아래, 208~220번째 줄 부근) —
     `"manager"` 역할로 고정 호출(기존 두 함수와 같은 패턴, `authHeaders`가 내부적으로
     `getManagerIdentity()`를 참조하므로 실제 어느 재무 담당인지는 자동으로 반영됨):
     ```typescript
     export const financeApprovePo = (poId: string, note?: string) =>
       apiFetch<ApiPo>(`/api/po/${poId}/finance-approve`, "manager", {
         method: "POST",
         body: JSON.stringify({ note: note ?? null }),
       });

     export const financeRejectPo = (poId: string, reason: string) =>
       apiFetch<ApiPo>(`/api/po/${poId}/finance-reject`, "manager", {
         method: "POST",
         body: JSON.stringify({ reason }),
       });
     ```
  4. `endpoints` 객체(993번째 줄 부근)에 `poFinanceApprove`/`poFinanceReject` 두 항목
     추가(기존 `poApprove`/`poReject`와 같은 패턴).
  5. `types.ts`의 `PoState`(7번째 줄) 유니온에 `"finance_approved" | "finance_rejected"` 추가.
  6. `queueState.ts`의 `STATE_LABEL.po`(40~45번째 줄)에 두 항목 추가:
     ```typescript
     po: {
       draft: { text: "draft", tone: "neutral" },
       pending: { text: "◔ pending", tone: "info" },
       approved: { text: "◔ 재무승인대기", tone: "info" },   // 라벨 텍스트만 교체 — tone 은 그대로 info
       finance_approved: { text: "✓ finance_approved", tone: "ok" },
       finance_rejected: { text: "✕ finance_rejected", tone: "danger" },
       rejected: { text: "✕ rejected", tone: "danger" },
     },
     ```
     ⚠ **`approved` 항목의 텍스트를 바꾸는 것은 기존 계약을 건드리는 것**이다 — 처분·수리
     등 다른 곳에서 `stateView("po","approved")`를 다른 의미로 참조하는 곳이 있는지 실행 전
     `grep -rn 'stateView(' frontend/`로 확인할 것. 바꾸는 근거: 새 상태 머신에서 `approved`
     는 이제 "재무 승인 대기"를 겸하므로(스펙 §2), 기존 "✓ approved"(승인 완료로 오인되는
     문구)를 그대로 두면 사용자가 이미 확정된 것으로 착각한다 — D87("모르는 값을 초록으로
     떨어뜨리지 않는다")의 취지를 확장 적용. 만약 리뷰 단계에서 문구 변경이 과하다고 판단되면
     `text: "◔ approved"`로 최소화해도 무방(톤은 `info` 유지, `ok`로 바꾸지 않는 것이 핵심 —
     완전히 확정된 것처럼 초록으로 보이면 안 된다).
  7. `isApprovedState(state: string): boolean { return state === "approved"; }` 를
     `isDraftState`/`isPendingState` 바로 아래(76~85번째 줄 부근)에 같은 패턴으로 추가.
  7-b. **`frontend/lib/__checks__/ui_honesty.ts:326`의 하드코딩된 대조군(control probe)을
     함께 교체한다** — 이 파일은 `spikes/ui_honesty_contract.py:77`이 `node`로 컴파일·실행하는
     공식 회귀(L1 15건 중 1건)다. 현재 코드:
     ```ts
     const known = stateView("po", "approved");
     check("stateView — 맵 밖 (kind,state) 5종이 tone='ok' 로 떨어지지 않는다 (known=false + 원문)",
       bad.length === 0 && known.tone === "ok" && known.known, ...);
     ```
     위 6번에서 `po.approved`의 `tone`을 `"ok"`→`"info"`로 바꾸면(본안·축소 대안 둘 다 `tone`은
     `"info"`로 바뀐다 — 위 ⚠ 참고) 이 대조군이 `known.tone === "ok"`에서 즉시 깨진다. 대조군을
     `stateView("po", "finance_approved")`(이번에 신설하는 `{ tone: "ok" }` 항목 — 새 상태
     머신에서 실제로 "확정 완료"를 뜻하는 값)로 교체할 것:
     ```ts
     const known = stateView("po", "finance_approved");
     ```
     이 한 줄만 바꾸면 되고, `check()` 호출의 나머지 인자는 그대로 둔다.
- **엣지 케이스**:
  - `detailHref()`(96~105번째 줄)는 `kind === "po"`일 때 이미 `/manager/po/${id}`를
    반환하므로 상태와 무관 — 수정 불필요.
  - `getPoQueue(role, state="pending")`(199~200번째 줄)의 기본값은 그대로 둔다 — 이 함수는
    발주 전용 목록 조회이고 이번 기능과 무관.
- **지켜야 할 결정**: D87(모르는 값을 초록으로 떨어뜨리지 않는다 — `approved`를 `ok` 톤으로
  바꾸지 말 것) · D36(X-User ASCII — `mgr-02`도 이미 ASCII, 변경 없음)
- **DoD**: `npx tsc --noEmit` 통과(신규 필드·유니온 확장이 기존 소비처와 충돌 없는지 타입
  체커가 확인). `grep -rn 'stateView(' frontend/`로 `approved` 라벨 변경의 영향 범위를
  실행 시점에 재확인하고 문제 있으면 위 엣지케이스 대안으로 축소. **`uv run python
  spikes/ui_honesty_contract.py` 전건 PASS 필수**(7-b 를 빠뜨리면 L1 대조군 1건이 FAIL한다 —
  tool-builder 현실성 평가가 미리 잡아 둔 함정, `npx tsc --noEmit`만으로는 안 드러난다).

---

### MQ-1713 — `PoDetail` 재무 액션 UI

- **복무 시나리오**: S5+
- **변경 파일**: `frontend/components/queue/FinanceDecisionBar.tsx` (신규),
  `frontend/components/queue/PoDetail.tsx` (수정)
- **인터페이스**:
  ```typescript
  // FinanceDecisionBar.tsx
  export function FinanceDecisionBar(props: {
    supplierName: string;
    /** false 면 승인/반려 버튼 대신 "재무부 소속만 처리 가능" 안내만 보여준다 */
    canAct: boolean;
    onApprove?: () => void;
    onReject?: (reason: string) => void;
  }): JSX.Element;

  // PoDetail.tsx — 기존 props 에 추가
  {
    // ... 기존 props 유지 ...
    isFinanceApprover?: boolean;         // MQ-1714 가 getManagerIdentity() 로 계산해 넘김
    onFinanceApprove?: () => void;
    onFinanceReject?: (reason: string) => void;
  }
  ```
- **핵심 로직**:
  1. `FinanceDecisionBar.tsx`는 기존 `DecisionBar.tsx`(`components/queue/DecisionBar.tsx`)
     구조를 그대로 복제하되 다음을 바꾼다: 승인 버튼 문구 "승인 — 발주서 확정" →
     "재무 승인 — 출금 요청 전송", 반려 사유 placeholder/hint 를 자금집행 맥락으로 조정.
     **`canAct=false`일 때는 반려 패널로 전환하는 상태(`rejecting`)를 아예 안 만들고**,
     승인/반려 버튼 대신 안내문 하나만 렌더:
     ```tsx
     if (!canAct) {
       return (
         <div style={sx("...margin-top:auto;padding-top:14px;border-top:1px solid var(--line)")}>
           <span style={sx("font:11px/1.4 'Pretendard';color:var(--dim2)")}>
             재무 승인 대기 중 — 재무부 소속 담당자만 승인/반려할 수 있습니다.
             (상단 신원 전환에서 "재무담당 · 최OO" 선택)
           </span>
         </div>
       );
     }
     ```
     `canAct=true`이고 `onApprove`/`onReject`가 모두 없으면(목업 모드) 기존 `DecisionBar`의
     `disabled` 문구("목업 데이터 — ... 저장되지 않습니다")와 같은 패턴을 재사용.
  2. `PoDetail.tsx`의 렌더 로직(현재 `<DecisionBar .../>` 한 줄, 69~73번째 줄)을 상태
     분기로 바꾼다:
     ```tsx
     import { isApprovedState, isPendingState } from "@/lib/queueState";
     // ...
     {isPendingState(entry.state) && (
       <DecisionBar supplierName={recommended?.name ?? ""} onApprove={onApprove} onReject={onReject} />
     )}
     {isApprovedState(entry.state) && (
       <FinanceDecisionBar
         supplierName={recommended?.name ?? ""}
         canAct={isFinanceApprover ?? false}
         onApprove={onFinanceApprove}
         onReject={onFinanceReject}
       />
     )}
     ```
     `state`가 `draft`/`rejected`/`finance_approved`/`finance_rejected`일 때는 두 액션바
     모두 렌더하지 않는다(종결 상태 — 액션 없음, 기존 배지(`StateBadge`)로 이미 상태가
     표시됨).
     ⚠ `entry.state === "approved"` 를 직접 문자열 비교하지 말고 반드시
     `isApprovedState()`를 쓸 것(D87 — MQ-1712 가 이 헬퍼를 정의해 뒀다).
  3. `documents_preview` 블록(현재 54~67번째 줄)에 세 번째 `<DocumentPreview>` 추가:
     ```tsx
     {documentsPreview && (
       <>
         <DocumentPreview title="설비 이상 진단 보고서" ... text={documentsPreview.diagnosis} />
         <DocumentPreview title="정비 · 부품 발주 요청서" ... text={documentsPreview.po_request} />
         <DocumentPreview
           title="자금집행 요청서"
           sub="미리보기 — 재무 승인 대기/완료 발주만 표시(팀장 승인 전에는 해당 없음)"
           text={documentsPreview.fund_execution}
         />
       </>
     )}
     ```
     `DocumentPreview` 컴포넌트 자체는 `text === null`일 때 이미 "해당 없음" 문구를 그리므로
     **`DocumentPreview.tsx`는 수정하지 않는다**.
- **엣지 케이스**:
  - `recommended`(quotes 배열의 추천 견적)가 없을 수 있는 기존 로직(`quotes.find(...) ??
    quotes[0]`)은 그대로 재사용 — `FinanceDecisionBar`에도 같은 `supplierName` prop 전달.
  - `PoDetail.tsx`는 `"use client"` 컴포넌트이고 `components/queue/*.tsx`이므로
    `spikes/ui_honesty_contract.py`의 L2 자동 글롭 대상이 아닐 수 있다(기존 `RepairDetail.tsx`
    가 `L2_EXTRA`에 수동 등재된 선례 참고) — 이 태스크는 그 글롭 설정 자체를 건드리지
    않는다(스코프 밖), 다만 `isApprovedState()`/`isPendingState()`를 쓰는 것 자체가 D87
    실천이므로 스캔 대상이 아니어도 올바르게 작성된다.
- **지켜야 할 결정**: D87(상태 문자열 직접 비교 금지 — 헬퍼 함수 경유) · D18(승인은 채팅
  밖 전용 화면 — 이 컴포넌트가 그 화면의 일부) · D38(반려 사유 필수 — `RejectPanel` 재사용
  구조를 유지하면 자동으로 지켜짐)
- **DoD**: `npx tsc --noEmit` 통과. 수동 확인: `state="approved"`인 목업 데이터로 렌더 시
  `canAct=false`면 안내문만, `canAct=true`면 승인/반려 버튼이 보임. `state="pending"`에서는
  기존 `DecisionBar`가 그대로 보임(회귀 없음).

---

### MQ-1714 — 승인 큐 화면 재무 대기열 wiring

- **복무 시나리오**: S5+
- **변경 파일**: `frontend/components/screens/ApprovalQueueScreen.tsx` (수정),
  `frontend/components/queue/QueueList.tsx` (수정)
- **인터페이스**:
  ```typescript
  // QueueList.tsx — 기존 props 에 선택적 3번째 버킷 추가
  {
    pending: QueueEntry[];
    /** 신규 — 비어 있으면 섹션 자체를 렌더하지 않는다 */
    financePending?: QueueEntry[];
    recent: QueueEntry[];
    selectedId: string;
  }
  ```
- **핵심 로직**:
  1. `QueueList.tsx`에 `financePending` prop 추가, 기본값 `[]`. `pending` 섹션과 `recent`
     섹션 사이에 새 섹션 삽입(기존 `SectionLabel`/`QueueItem` 재사용):
     ```tsx
     {financePending.length > 0 && (
       <>
         <div style={sx("height:1px;background:var(--line);margin:14px 12px 0")} />
         <SectionLabel>재무 승인 대기 · {financePending.length}</SectionLabel>
         <div style={sx("padding:0 12px;display:flex;flex-direction:column;gap:8px")}>
           {financePending.map((e) => (
             <QueueItem key={`${e.kind}:${e.id}`} entry={e} selected={e.id === selectedId} />
           ))}
         </div>
       </>
     )}
     ```
  2. `ApprovalQueueScreen.tsx`의 `load()`(68~130번째 줄)에 새 조회 추가 — 기존
     `Promise.all([...])`(73~78번째 줄)에 항목 하나 추가:
     ```typescript
     const [p, financeApproved, approved, signed, rejected] = await Promise.all([
       getApprovals("manager", "pending"),
       getApprovals("manager", "approved", "po"),   // 신규 — 재무 승인 대기 (po kind 로 한정)
       getApprovals("manager", "approved"),
       getApprovals("manager", "signed"),
       getApprovals("manager", "rejected"),
     ]);
     const done = [...approved, ...signed, ...rejected].slice(0, 4);
     setPending(p);
     setFinancePending(financeApproved);   // 신규 state
     setRecent(done);
     ```
     ⚠ `approved`(기존, "최근 처리" 4건 슬라이스용)와 `financeApproved`(신규, "재무 승인
     대기" 섹션 전용, kind="po" 로 좁힘)는 **같은 데이터를 두 번 조회하는 것처럼 보이지만
     역할이 다르다** — 하나는 "최근 처리 완료" 목록(4건 제한, po/disposal/repair 섞임),
     하나는 "지금 재무가 처리해야 할 것"(제한 없음, po 전용). 합치지 말 것 — 합치면
     재무 승인 대기 건수가 4건 넘을 때 잘려 나간다.
     `useState<ApiApproval[]>([])`로 `financePending` state 신규 선언(다른 state 옆).
  3. `chosen.kind === "po"`인 `<PoDetail>` 렌더 지점(193~201번째 줄)에 새 prop 3개 전달:
     ```tsx
     import { getManagerIdentity } from "@/lib/role";
     import { financeApprovePo, financeRejectPo } from "@/lib/api";
     // ...
     <PoDetail
       entry={chosen}
       evidence={...}
       quotes={...}
       documentsPreview={...}
       onApprove={live ? () => void decide("approve") : undefined}
       onReject={live ? (reason) => void decide("reject", reason) : undefined}
       isFinanceApprover={getManagerIdentity().department === "finance"}
       onFinanceApprove={live ? () => void decideFinance("approve") : undefined}
       onFinanceReject={live ? (reason) => void decideFinance("reject", reason) : undefined}
     />
     ```
  4. `decide()`(136~151번째 줄) 바로 아래 새 함수 `decideFinance()` 추가(같은 패턴):
     ```typescript
     async function decideFinance(action: "approve" | "reject", reason?: string) {
       if (!detail) return;
       try {
         const updated =
           action === "approve"
             ? await financeApprovePo(detail.po_id)
             : await financeRejectPo(detail.po_id, reason ?? "");
         setNotice(
           `${updated.po_id} 재무 ${action === "approve" ? "승인" : "반려"} 완료 — ${updated.state}`
         );
         await load();
       } catch (e) {
         setNotice(e instanceof ApiError ? `${e.status} — ${extractDetail(e.body)}` : String(e));
       }
     }
     ```
  5. `<QueueList>` 호출부(188~192번째 줄)에 `financePending={live ?
     financePending.map(toQueueEntry) : []}` 전달(목업 모드에서는 빈 배열 — 재무 대기열의
     목업 데이터를 새로 만들지 않는다, 스코프 최소화).
  6. 헤더의 `팀장 {ROLE_USER_NAME.manager}`(180~182번째 줄)를 현재 선택된 신원 기준으로
     바꾼다:
     ```tsx
     import { getManagerIdentity } from "@/lib/role";
     // ...
     <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>
       {getManagerIdentity().label}
     </span>
     ```
     (기존 `ROLE_USER_NAME` import 가 이 용도로만 쓰였다면 제거해도 되고, 다른 곳에서 쓰이면
     그대로 둘 것 — 실행 시점에 `grep -n ROLE_USER_NAME` 로 확인.)
- **엣지 케이스**:
  - `getManagerIdentity()`는 클라이언트 전용(localStorage) 함수라 이 컴포넌트가
    `"use client"`(파일 최상단에 이미 있음, 1번째 줄)임을 재확인할 것 — 서버 컴포넌트에서
    호출하면 안전 가드가 `MANAGER_IDENTITIES[0]`으로 조용히 폴백하긴 하지만, 클라이언트
    선택값을 반영 못 하는 버그가 된다.
  - `financePending`에 뜬 항목을 클릭해 선택했는데 그게 `chosen`이 되는 경로(`selectedId`
    prop, 딥링크)는 기존 `load()`의 `found` 탐색 로직(83번째 줄, `[...p, ...done].find(...)`)
    이 `financePending`을 포함하지 않아 못 찾을 수 있다 — `found` 계산 시
    `[...p, ...financePending, ...done]`으로 배열을 확장할 것(83번째 줄 수정 필요).
- **지켜야 할 결정**: D18(승인 큐는 채팅 밖 전용 화면) · D85(통합 큐는 읽기 전용 조립기,
  `/api/po` 응답 형태를 이 화면이 직접 바꾸지 않는다 — `getApprovals` 재사용을 유지)
- **DoD**: `npx tsc --noEmit` · `npx next build` 통과(라우트 개수 불변). 수동 확인: 재무담당
  신원으로 전환 후 `/manager` 진입 시 "재무 승인 대기" 섹션에 `approved` 상태 po 항목이
  보이고, 클릭하면 `FinanceDecisionBar`의 액션 버튼이 활성 상태로 나옴. 정비팀장 신원에서는
  같은 항목이 `canAct=false` 안내문으로 보임.

---

## 3. 회귀 스위트 갱신 메모 (DoD 가 아니라 후속 조치 안내)

이 스프린트가 끝나면 다음이 CLAUDE.md "회귀 스위트" 절에 반영돼야 한다(별도 `/done` 세션
마무리 태스크로 남긴다 — 이 스프린트 태스크 목록에는 넣지 않음, PM 판단):

- pytest 파일 목록에 `data/test_expenditure_limits.py` 추가(3파일군 → 4파일군, 실측 건수로
  갱신).
- `spikes/api_contract.py` 건수 증가(정확한 델타는 MQ-1706·MQ-1710 완료 후 실측).
- seed.py 자가검증 항목 수 증가(MQ-1702 완료 후 실측).
- `docs/00_MVP_SCOPE.md`·`docs/07_BACKLOG.md`에 이번 확장이 "완료"로 반영될지 여부는
  사용자 승인 후 다음 세션에서 판단.

---

## 현실성 평가

**평가일**: 2026-08-24 · **평가자**: tool-builder(현실성 평가 단계) · **방법**: 문서 전문 통독
(1,381줄) + 14개 태스크가 인용한 실제 코드 줄번호·시그니처·픽스처 동작을 `Read`/`Grep`/`Bash`
(`uv run python -c "from backend.services import po"` 포함)로 직접 대조. 코드는 작성하지 않았다.

### 실측 대조 결과 (과제 5개 항목)

1. **MQ-1704** — `backend/services/decisions.py`에 `now_utc_sql` 함수 실재 확인.
   `backend/services/repairs.py:27`이 `from backend.services.decisions import now_utc_sql`로
   동일하게 재사용 중임을 확인(선례 주장 사실). 순환 임포트: `uv run python -c "from
   backend.services import po"` → 성공(`psycopg` 없는 순정 `python`으로는 `backend/db.py`가
   즉시 `ModuleNotFoundError`를 내므로 **반드시 `uv run`으로 검증해야 한다** — 이 함정은
   플랜에 언급이 없었으나 치명적이지 않음, 실행 커맨드 관례상 이미 `uv run`을 쓰므로 실제
   실행에는 영향 없음). `decisions.py`가 `po.py`를 import 하지 않음도 확인 — 순환 없음.
2. **MQ-1707** — `backend/conftest.py`를 직접 읽어 확인: `db_path` 픽스처는
   `create_isolated_schema(label="a2a_test", clone_data=False)`로 **빈 스키마**를 만들고,
   `seed_po()`는 `INSERT OR IGNORE INTO users (user_id, display_name, role) VALUES (?, ?,
   'manager')`로 `department` 컬럼을 **아예 채우지 않는다**(NULL로 남음) — 플랜(585~593줄)의
   주장과 완전히 일치. `data/pg_isolation.py:81`의 오늘 세션 수정(`search_path`에 `public`
   추가, pgvector 타입 참조용)은 `clone_data=False` 경로에도 그대로 적용되므로(같은
   `con.execute(f'SET search_path TO "{schema}", public')` 한 줄이 `clone_data` 분기 이전에
   실행됨) MQ-1707이 전제하는 격리 스키마 생성에 영향 없음.
3. **MQ-1708** — `backend/services/a2a_history.py:19`의 `list_a2a_history(*, skill=None,
   po_id=None, building_id=None, chain_id=None, limit=50, db_path=None) -> dict` 시그니처가
   플랜의 호출부(`a2a_history.list_a2a_history(po_id=po_id, skill="request-withdrawal",
   limit=1, db_path=db_path)`)와 키워드 인자 전부 일치. 반환 모양
   `{"count": int, "items": [{"request_chain_id", "skill", "status", ...}]}`도 플랜의
   `a2a_info["request_chain_id"]`·`a2a_info.get("status")` 사용과 일치 — 가정한 함수명·모양이
   실재하며 막히는 지점 없음.
4. **MQ-1702** — `data/seed.py` 실측: `CREATE TABLE po_drafts (` **206번째 줄**, `CHECK
   (state IN (...))` **224번째 줄**, `seed_po_drafts()` **1973번째 줄**(튜플 주석이 플랜이
   인용한 15필드 순서와 문자 그대로 일치, `with_codes=False` 슬라이싱 로직도 플랜 설명대로
   길이 무관하게 동작), `verify()` **2270번째 줄**, `SAVEPOINT fk_probe` **2382번째 줄** — 플랜이
   인용한 "약 206~232"·"2270번째 줄~"·"2382번째 줄 부근"이 전부 실제 줄번호와 일치하거나
   1~2줄 이내로 근접. `verify()`의 마지막 검사 원문자는 실측 결과 **㊱**(37번째 검사, 파일
   전체 `check()` 호출 37건과 일치 — CLAUDE.md의 "seed 37건"과도 부합) — 플랜이 "㊱ 근방으로
   알려져 있으나 실행 시점에 재확인"이라 적어 둔 것과 정확히 맞아떨어진다.
5. **오늘 세션 수정 2건과의 충돌 여부** — ⓐ `data/pg_isolation.py:81`(search_path에 `public`
   추가)은 위 2번 항목대로 MQ-1707이 의존하는 픽스처 생성 경로에 이미 자연스럽게 포함돼
   있어 충돌 없음. ⓑ `spikes/api_contract.py`의 `PO_DETAIL_KEYS`는 실측 결과 이미
   `alternatives`·`error_code_def`·`documents_preview`를 포함하고 있음(44~55번째 줄 직접
   확인) — 플랜이 경고한 드리프트가 **이미 오늘 세션에서 해소**돼 있는 상태였다. MQ-1706의
   지시("옛 스냅샷을 기준으로 삼지 말고 실행 시점 실제 응답과 대조")는 이 상태에서도 여전히
   유효하고 안전한 절차이므로 플랜 수정 불필요.

### 추가로 발견한 문제 (플랜에 없던 것)

**🔴 MQ-1712 — `ui_honesty_contract`의 하드코딩된 대조군(control probe)이 깨진다.**
`frontend/lib/queueState.ts`의 현재 `STATE_LABEL.po.approved`는 `{ text: "✓ approved", tone:
"ok" }`이다(38~59번째 줄 실측). `frontend/lib/__checks__/ui_honesty.ts:326`은 바로 이 값을
"알려진 정상값(대조군)"으로 하드코딩해 쓰고 있다:
```ts
const known = stateView("po", "approved");
check("stateView — 맵 밖 (kind,state) 5종이 tone='ok' 로 떨어지지 않는다 (known=false + 원문)",
  bad.length === 0 && known.tone === "ok" && known.known, ...);
```
이 파일은 `spikes/ui_honesty_contract.py:77`이 `node`로 컴파일·실행하는 **공식 회귀**(L1
순수함수 15건 중 1건, CLAUDE.md 기준선 "L1 15건"의 일부)다. MQ-1712는
`approved: { text: "◔ 재무승인대기", tone: "info" }`로 바꾸는 것을 본안으로 제시하고,
안전한 대안으로 제시한 것도 `text: "◔ approved"` 뿐(`tone`은 여전히 `"info"`로 유지, "`ok`로
바꾸지 않는 것이 핵심"이라고 스스로 명시)이다 — 즉 **본안이든 대안이든 `tone`이 `"ok"`에서
`"info"`로 바뀌는 것은 플랜의 의도 자체이며, 이 변경은 어느 쪽이든 위 대조군 단언을
깨뜨린다.** MQ-1712의 DoD는 `npx tsc --noEmit`과 `grep -rn 'stateView(' frontend/`뿐이라 이
파일이 실제로 컴파일·실행되는 `ui_honesty_contract` 스파이크를 돌리기 전까지는 드러나지
않는다(그 grep을 실제로 돌리면 `frontend/lib/__checks__/ui_honesty.ts:326`이 결과에
잡히지만, 플랜 본문은 이 특정 줄을 "다른 소비처" 취급만 하고 있어 실행자가 놓치기 쉽다).
14개 태스크 중 어느 것도 "변경 파일"에 `frontend/lib/__checks__/ui_honesty.ts`를 올려 두지
않았다.

**영향 범위**: `/stage`가 회귀를 자동 실행하면 Stage 4 종료 시점에 `ui_honesty_contract`가
FAIL로 잡히긴 한다 — 회귀 자체가 이 결함을 놓치는 것은 아니다. 문제는 **계획 문서가 이걸
예상하지 못해**, MQ-1712를 병렬로 작성하는 시점에 "그냥 tone을 바꾸면 된다"고 오인하게 만들고,
디버깅 시간을 스테이지 종료 후로 미룬다는 점이다.

**제안**: MQ-1712의 "핵심 로직" 6번 항목(`STATE_LABEL.po` 갱신) 바로 다음에 항목을 하나
추가한다 — `frontend/lib/__checks__/ui_honesty.ts:326`의 대조군을
`stateView("po", "finance_approved")`(플랜이 이번에 신설하는 `{ text: "✓
finance_approved", tone: "ok" }` 항목 — 새 상태 머신에서 실제로 "확정 완료"를 뜻하는 값이라
대조군으로 적합)로 교체한다. MQ-1712의 "변경 파일" 목록에
`frontend/lib/__checks__/ui_honesty.ts`를 추가할 것.

**🟡 MQ-1701/D119 — D108이 이미 명시적으로 기각했던 대안을 다시 채택한다(절차는 준수).**
`docs/10_DECISIONS.md` D108 본문을 직접 대조한 결과, D108은 "department를 승인 판정에
넣는" 안(대안 ⓑ, "대상 제한")을 **이미 검토 후 명시적으로 기각**했고, 그 이유를 "승인
판정에 department가 들어가는 순간 '부서는 권한이 아니다'가 깨진다"고 적어 뒀다. 그리고
"나중에 실제로 부서별 승인 제한이 필요해지면 **role을 늘리는 방식**(`finance_manager`)으로
가고 그때도 판정에 들어가는 것은 여전히 role이다"라고 미래 경로까지 **이미 못박아
뒀다**(D108 결정문 마지막 문단). Sprint 17의 D119는 정확히 그 미래 시나리오("부서별 승인
제한이 필요해졌다")를 맞았는데, D108이 지정해 둔 경로(role 확장)가 아니라 D108이 기각했던
경로(department 직접 체크)를 선택한다. MQ-1701은 이를 인지하고 있고(대안 ②로 role 확장을
명시적으로 검토·기각), 기각 사유도 나름대로 타당하다(`X-Role` 이분법이 D38 완료 기준의
전제라는 점) — **절차상 CLAUDE.md의 "설계와 다른 결정을 하려면 D 문서에 먼저 등재"** 요구는
MQ-1701이 정확히 충족한다. 다만 이건 "새 영역을 여는" 통상적 결정이 아니라 **이전 결정이
스스로 예견하고 미리 거부해 둔 경로를 다시 여는 것**이라, PM 판단만으로 넘기기보다
Stage 1 착수 직전에 사용자에게 "D108이 이 정확한 시나리오에 대해 이미 다른 답을 정해
뒀었다"는 사실을 한 번 더 짚고 진행 승인을 받는 편이 안전하다. 계획 자체를 막을 사유는
아니다(사용자가 이미 스펙 브레인스토밍 단계에서 "재무부 승인 단계 신설"을 명시적으로
결정했고, `docs/superpowers/specs/2026-08-24-finance-approval-doc3-design.md §4`도 같은
논리를 담고 있어 사용자 의도와 일치할 가능성이 높다) — 다만 이 대조가 이번 평가에서 처음
드러난 것이라 명시적으로 기록해 둔다.

**🟢 MQ-1713 — `FinanceDecisionBar.tsx`도 `ui_honesty_contract`의 L2 자동 스캔 밖(경미,
선택 사항).** `spikes/ui_honesty_contract.py`의 `L2_GLOBS`는 `components/queue/Decision*.tsx`
패턴만 잡는다 — 신설되는 `FinanceDecisionBar.tsx`는 이 접두어와 안 맞아 자동 스캔에
안 잡힌다(플랜이 이미 인지한 `PoDetail.tsx`의 동일한 사각지대와 같은 종류). 과거
`RepairDetail.tsx`·`WithdrawalStatusPanel.tsx`는 이 사각지대를 `L2_EXTRA`에 수동 등재해
해소한 선례가 있다. 코드 자체는 `isApprovedState()`/`canAct` prop 패턴을 올바르게 쓰므로
기능적 결함은 아니고, 회귀를 깨뜨리지도 않는다 — 다만 D87 감시망에서 빠진다는 점을
알아 두고 후속 태스크(또는 이번 스테이지 리뷰)에서 `L2_EXTRA`에 추가할지 판단할 것을 권고.

### 그 외 태스크 (실측 이상 없음)

MQ-1703(스펙 코드 그대로 옮기는 신규 순수함수 모듈, 충돌 대상 없음)·MQ-1705(`_transition()`
헬퍼·403/409 매핑이 `backend/routers/po.py:139-146`의 기존 패턴과 정확히 같은 모양임을
확인)·MQ-1706·MQ-1709(`_DOC_STATUS_LABEL`@37·`approver_signed_at`@123·
`manager_signed_at`@222·`data/doc_review.py`@35-42 전부 실측과 일치)·MQ-1710·MQ-1711(`role.ts`
전문 확인, `ROLE_USER_ID.manager` 폴백 유지 지시 정확)·MQ-1714(`getApprovals(role, state?,
kind?)` 시그니처 확인, `load()`/`decide()`/`found` 계산의 줄번호 전부 실측과 일치)는 인용된
파일 경로·함수 시그니처·줄번호가 실제 코드베이스와 대조해 어긋나는 지점이 없었다. 블로커
체크리스트(`error_codes` 미승인·`related_parts` 미검수·`ANTHROPIC_API_KEY`·임베딩/벡터스토어
미결)는 이 스프린트가 진단·RAG·에이전트 루프 경로를 전혀 건드리지 않으므로 PM의 "무관"
결론이 실측과 일치한다.

| 스테이지 | TASK | 리스크 | 제안 |
|---|---|---|---|
| 1 | MQ-1701 | 🟡 중 — D119가 D108 ⓔ가 이미 명시적으로 기각한 대안("department가 승인 판정에 들어간다")을 다시 채택. D108은 이 정확한 미래 시나리오에 대해 "role 확장"을 답으로 못박아 뒀다 | 절차(D 문서 선등재)는 이미 충족됨. Stage 1 착수 전 사용자에게 "D108이 이 시나리오를 이미 다르게 정해 뒀다"는 사실을 한 번 더 확인받을 것을 권고(계획을 막을 사유는 아님) |
| 1 | MQ-1702 | 🟢 낮음 — 모든 줄번호·슬라이싱 로직·CHECK 위치 실측 일치 | 그대로 진행 |
| 1 | MQ-1703 | 🟢 낮음 — 신규 순수함수, 충돌 없음 | 그대로 진행 |
| 1 | MQ-1704 | 🟢 낮음 — `now_utc_sql` 선례·순환 임포트 없음을 `uv run`으로 직접 검증 완료 | 그대로 진행 |
| 2 | MQ-1705 | 🟢 낮음 — `_transition()` 패턴·D38 403/409 순서 로직이 기존 코드와 정확히 일치 | 그대로 진행 |
| 2 | MQ-1706 | 🟢 낮음 — 상수 위치·`PO_LIST_ITEM_KEYS` 실측 일치, 오늘 세션이 이미 드리프트 해소 | 그대로 진행. `run()`과 `run_print_page_checks()`가 원문자 번호를 독립적으로 재사용한다는 점만 실행 시점에 재확인(플랜이 이미 지시한 절차로 충분) |
| 2 | MQ-1707 | 🟢 낮음 — `conftest.py` 픽스처 동작(clone_data=False·department 미충전) 실측 일치 | 그대로 진행 |
| 3 | MQ-1708 | 🟢 낮음 — `_PO_SELECT`·`_row_to_po`·`list_a2a_history` 시그니처·`suppliers.account_number/bank_code` 전부 실측 일치 | 그대로 진행 |
| 3 | MQ-1709 | 🟢 낮음 — 모든 헬퍼·줄번호 참조가 실제 코드와 일치 | 그대로 진행 |
| 3 | MQ-1710 | 🟢 낮음 — MQ-1706과의 순서 조율 지시가 구체적이고 실행 가능 | 그대로 진행 |
| 4 | MQ-1711 | 🟢 낮음 — `role.ts` 실측 일치 | 그대로 진행 |
| 4 | MQ-1712 | 🔴 높음 — `STATE_LABEL.po.approved.tone`을 "ok"→"info"로 바꾸면 `frontend/lib/__checks__/ui_honesty.ts:326`의 하드코딩된 대조군 단언이 깨진다(공식 회귀 `ui_honesty_contract` L1 15건 중 1건). 본안·대안 둘 다 이 문제를 못 피한다 | **태스크 명세 수정 필요**: `ui_honesty.ts:326`의 대조군을 `stateView("po","finance_approved")`(플랜이 신설하는 tone:"ok" 상태)로 교체하는 항목을 MQ-1712에 추가하고 "변경 파일"에 이 파일을 등재할 것 |
| 4 | MQ-1713 | 🟢 낮음(선택 사항 1건) — `PoDetail.tsx`/`FinanceDecisionBar.tsx` 줄번호·L2 스캔 대상 여부 실측 일치 | `FinanceDecisionBar.tsx`도 `L2_EXTRA` 미등재 상태(D87 감시망 밖) — 기능 결함 아님, 후속 판단 사항으로 기록 |
| 4 | MQ-1714 | 🟢 낮음 — `getApprovals` 시그니처·`load()`/`decide()`/`found` 로직 실측 일치 | 그대로 진행 |

### 평가 결론
- 계획 수정 필요: **Y**(소규모) — MQ-1712에 `ui_honesty.ts:326` 대조군 교체 항목 1개 추가가
  필수(추가하지 않으면 Stage 4 종료 시점에 `ui_honesty_contract` 회귀가 확실히 FAIL한다).
  그 외 13개 태스크는 코드베이스 실측과 대조해 수정 없이 그대로 착수 가능 — 인용된 줄번호·
  함수 시그니처·픽스처 동작이 이례적으로 정확했다(대부분 실제 줄번호와 완전히 일치하거나
  1~2줄 이내). MQ-1701/D119는 코드 수정이 필요한 결함은 아니지만 D108과의 관계가 "새 영역
  확장"이 아니라 "이전에 명시적으로 기각된 대안의 재채택"이라는 점을 사용자가 인지하고
  진행하는지 Stage 1 착수 전에 한 번 확인받을 것을 권고한다.

---

## 3. 계획 확정

**확정일**: 2026-08-24 · **확정자**: 사용자(본인 확인)

- **MQ-1712 수정 반영 완료** — 위 🔴 발견에 따라 "변경 파일"에
  `frontend/lib/__checks__/ui_honesty.ts` 추가, "핵심 로직" 7-b(`ui_honesty.ts:326`의 대조군을
  `stateView("po","approved")` → `stateView("po","finance_approved")`로 교체) 신설, DoD에
  `spikes/ui_honesty_contract.py` 전건 PASS 조건 추가. 이걸로 🔴 항목 해소.
- **MQ-1701/D119 범위 재확인 완료** — 사용자에게 "department가 승인 판정에 들어가는 것"을
  D119(finance-approve/finance-reject 2종, department=='finance' 체크)로 한정할지, 기존
  일반 `approve()`/`reject()`(팀장 승인)까지 확장할지 물었다. **답: D119 그대로(추가 확장
  없음)** — 계획 수정 불필요, MQ-1701~1714 어느 것도 변경하지 않는다. D108과의 관계(이전에
  기각된 경로의 재채택)는 위 평가가 기록한 그대로 사용자 승인하에 진행한다.
- **🟢 MQ-1713(`FinanceDecisionBar.tsx`의 `ui_honesty_contract` L2 사각지대)** — 경미·선택
  사항으로 남겨 둔다. 이번 스프린트 DoD에 넣지 않음(기능 결함 아니고 회귀도 안 깨짐) — Stage 4
  리뷰 시점에 `L2_EXTRA` 등재 여부를 판단한다.

계획 수정 완료. **14개 태스크(MQ-1701~1714) 전부 착수 가능한 상태다.**

실행: `/stage 1`

---

### Stage 1 완료 (2026-08-24)
**커밋**: `7b28aee` — `[M4] feat: Sprint 17 Stage 1 — 재무부 승인 D119 등재 + DB 스키마 + 내부통제 판정 + 상태전이`
(선행 인프라 수정 `12df5f5`가 별도 커밋으로 먼저 들어감 — Sprint 17 태스크는 아니지만
Stage 1 회귀가 이 수정에 의존해 같은 세션에서 함께 처리)

#### MQ-1701 — D119 등재 + S5+ 시나리오 반영
- `docs/10_DECISIONS.md`(D119 신규 행) · `docs/02_SCENARIOS.md`(S5+ 행+각주) ·
  `docs/00_MVP_SCOPE.md`(§3 확장 단락)
- D115~D118과 같은 5열 표 형식 실측 검증(pipe count 대조) 중 D119 초안 문장의 리터럴
  `technician|manager`가 표를 깨뜨리던 실제 버그 1건 발견·수정

#### MQ-1702 — `po_drafts` 스키마 확장 + 시드 표본 + 자가검증
- `data/seed.py`(DDL 4컬럼+CHECK 확장, 시드 표본 PO-0118/0119/0120, 자가검증 ㊲~㊵) ·
  `docs/05_DB_SCHEMA.md §8` · `scripts/postgres_schema.sql`(스코프 밖이지만 필수 —
  Postgres 타겟 재시드가 이 파일을 직접 읽어서, 안 고치면 즉시 실패)
- 회귀: 재시드 41/41, `error_codes` 70건

#### MQ-1703 — 내부통제 판정 로직 모듈
- `data/expenditure_limits.py`(신규, 스펙 원문 그대로) · `data/test_expenditure_limits.py`
  (신규)
- 회귀: pytest 16/16

#### MQ-1704 — `po_drafts` 상태 전이 규칙 확장
- `backend/services/po.py`(`ALLOWED_FROM` 확장·`transition()` 수정·`_finance_transition()`
  신규)
- 스펙이 지시한 `now_utc_sql` 상단 import는 실측으로 순환 임포트
  (`po→decisions→disposal→po`)가 재현돼 함수 내부 지연 import로 회피 — 공개 계약(시그니처·
  `ALLOWED_FROM` 값)은 스펙과 동일
- 회귀: `test_po_a2a_trigger.py`+`test_po_a2a_dispatch.py` 10/10(원본 그대로 무변화 확인)

#### 회귀 게이트 정리 (스테이지 내 즉시 해소, 별도 태스크 아님)
- `spikes/api_contract.py`의 `PO_LIST_ITEM_KEYS`에 MQ-1702 신규 컬럼 4개 추가 —
  원래 Stage 2(MQ-1706) 몫이었으나 스테이지 경계마다 회귀를 깨끗하게 유지하려고 앞당김
- `backend/db.py`의 ruff F401(미사용 import, Sprint 16부터의 기존 부채) 제거

**eval-runner 종합**(2차 재확인 기준): seed 41/41(error_codes 70) · sp2_mcp_roundtrip
20/20 · write_tool_contract 30/30 · api_contract 41/41 · sp3_sse_events 22/22 ·
test_expenditure_limits 16/16 · test_po_a2a_trigger+test_po_a2a_dispatch 10/10 ·
ruff clean. 1차 실행 중 `sp2_mcp_roundtrip`가 WinError 10014(소켓 고갈)로 1회
실패했으나 단독 재실행으로 해소(코드 결함 아님).

**reviewer 게이트**: PASS(블로커 없음). 비블로커 관찰 2건 — ① `data/test_expenditure_limits.py`가
CLAUDE.md 공식 pytest 목록에 아직 미반영(`/done` 시 갱신 필요) ② `docs/00_MVP_SCOPE.md`의
`docs/06_REPO_API.md §2.2` 인용이 현재는 정상 선행 참조이나 Stage 2 완료 시 §2.2 실제
갱신 여부 확인 필요. **Stage 2 진입 조건 재확인**(reviewer가 명시적으로 짚음): 현재
`approve()`가 여전히 A2A 출금 요청을 즉시 트리거한다 — Stage 2(MQ-1705)가 이 호출을
`finance_approve()`로 반드시 옮겨야 하며, 이는 sprint-17.md에 이미 계획된 작업이다.

---

### Stage 2 완료 (2026-08-24)
**커밋**: `80804fb` — `[M4] feat: Sprint 17 Stage 2 — finance-approve/reject 엔드포인트 + A2A 발신 시점 이동`
(선행 문서 정비 `76dc766`가 별도 커밋으로 먼저 들어감 — Sprint 17 태스크는 아니지만 같은
세션에서 `docs/13_DEPLOYMENT.md`를 Postgres/pgvector 전제로 갱신)

#### MQ-1705 — `finance-approve`/`finance-reject` 엔드포인트 + A2A 이동
- `backend/routers/po.py`(`approve()` 동기 복귀+A2A 제거, `_finance_transition_http()`
  신규, `finance_approve`/`finance_reject` 신규) · `docs/06_REPO_API.md`(§2.2·§2.4)
- Stage 1 게이트가 예고한 핵심 항목(A2A 발신 이동)을 curl 6케이스(403 role·403 department·
  200 승인·200 반려·409 상태순서·422 사유공백)로 직접 검증

#### MQ-1706 — 회귀: REST 계약(403/409/200)
- `spikes/api_contract.py`에 신규 체크 6건(㊲~㊷) 추가, 41→47건
- 실행 중 명세가 가정한 픽스처(PO-0117)가 앞선 체크에서 이미 소비돼 있던 걸 발견 — PO-0115로
  교체해 해소(실측 기반 수정)

#### MQ-1707 — 회귀: A2A 트리거 이동 재검증
- `backend/routers/test_po_a2a_trigger.py` 전면 재작성(8개 함수) — `_seed_finance_manager()`
  로컬 헬퍼로 격리 스키마에 없는 `mgr-02`/finance 픽스처 보강
- 회귀: `test_po_a2a_trigger.py`+`test_po_a2a_dispatch.py` 13/13

**eval-runner 종합**: seed 41/41(error_codes 70) · sp2_mcp_roundtrip 20/20 ·
write_tool_contract 30/30 · api_contract 47/47 · sp3_sse_events 22/22 ·
test_expenditure_limits 16/16 · test_po_a2a_trigger+test_po_a2a_dispatch 13/13 ·
ruff clean. 인프라 노이즈(Windows Docker Desktop의 Postgres 포트포워딩 간헐적
`ConnectionTimeout`, 2명의 tool-builder가 독립적으로 겪음)가 관측됐으나 재시도로 코드와
무관함을 확인 — 최종 eval-runner 실행은 재시도 없이 1회차 클린.

**reviewer 게이트**: PASS(블로커 없음). Stage 1이 예고한 3가지 핵심 확인 항목
(`approve()`의 A2A 호출 제거 · `_finance_transition`의 컬럼 분리 · role→department 체크
순서) 전부 코드로 재확인 완료. 비블로커 관찰 1건 — `finance_reject`의 pydantic 검증(422)이
`require()`의 role 체크(403)보다 먼저 실행되는 기존 관성은 `reject()` 선례와 동일, 이번
스테이지가 새로 만든 문제 아님.

---

### Stage 3 완료 (2026-08-24)
**커밋**: `def1d19` — `[M4] feat: Sprint 17 Stage 3 — 내부통제 계산 조립 + doc3(자금집행요청서) 렌더`

#### MQ-1708 — `get_po()` 내부통제 계산 + A2A 이력 조회 + doc3 게이트
- `backend/services/po.py`(`_PO_SELECT`에 `finance_decided_by_name` LEFT JOIN,
  `controls`/`a2a_info`/`payee` 계산 블록 신규)
- MQ-1709와 병렬 완료 직후 통합 테스트까지 자체 수행(PO-0118·PO-0114 두 표본 렌더 확인)

#### MQ-1709 — doc3 렌더 함수 + 검수 플래그
- `backend/services/po_documents.py`(`render_fund_execution_document()` 신규, 상태
  라벨·서명 시각 4-상태 확장) · `data/doc_review.py`(검수 플래그 신규)
- 담보/대출 "해당 없음", MFA_STATUS "미구현" 고정 문구(D118) 그대로 반영 확인

#### MQ-1710 — 회귀: doc3 렌더 계약 + 키집합 동기화
- `spikes/api_contract.py`에 신규 5건, 47→52건
- 스펙이 가정한 체크 배치(PO-0117/PO-0116 검증을 파일 뒤쪽에 이어 붙임)가 실제 실행
  순서와 안 맞는 것을 발견 — 두 표본이 그 위치 전에 이미 approve/reject로 소비돼 있어,
  MQ-1706의 PO-0117→PO-0115 치환과 같은 원칙으로 소비 전 시점에 재배치해 해소

#### 회귀에서 발견해 커밋 전 직접 고친 버그 1건 (별도 태스크 아님)
- `sod_check()` 호출 가드가 `finance_decided_by`만 확인해 `requested_by`가 NULL인 정상
  상태(D23·D37)에서 `TypeError`로 죽던 버그를 `backend/routers/test_po_a2a_trigger.py`
  4건 FAIL로 발견 — 가드를 신원 3종 전부 있을 때만 호출하도록 넓혀 해소.
  `data/expenditure_limits.py::sod_check` 함수 자체는 스펙 원문 그대로 무변경(방어는
  호출부 책임이라는 설계 유지)

**eval-runner 종합**(2차 재확인 기준): seed 41/41(error_codes 70) · sp2_mcp_roundtrip
20/20 · write_tool_contract 30/30 · api_contract 52/52 · sp3_sse_events 22/22 ·
test_expenditure_limits 16/16 · test_po_a2a_trigger+test_po_a2a_dispatch 13/13 ·
ruff clean · 순환 임포트 없음(`po`·`po_documents` 둘 다). 1차 회귀에서 위 버그로 인한
FAIL 4건이 있었으나 수정 후 재실행에서 재시도 없이 1회차 클린.

**reviewer 게이트**: PASS(블로커 없음). `sod_check` 가드 수정이 D62를 지키는지, 함수
자체는 무변경인지, `spikes/api_contract.py`의 체크 재배치가 실제로 소비 전 시점에서
실행되는지(파일을 직접 읽고 라인 순서 확인) 전부 검증 완료. 비블로커 관찰 2건 — ①
`today_total` 쿼리의 `po_id != ?` 자기중복 방지 조건이 설계 스펙 원문에 없던 것이라
`docs/10_DECISIONS.md`에 D 번호로 정식 등재하거나 스펙 문서 갱신 권장 ②
`render_fund_execution_document()`의 담보/대출 섹션 문구가 스펙의 "해당 없음" 단문보다
부가 설명이 붙어 있음(값을 지어낸 건 아니라 D62 위반 아님).

---

### Stage 4 완료 (2026-08-24) — Sprint 17 마지막 스테이지

**커밋**: `754baf4` — `[M4] feat: Sprint 17 Stage 4 — 재무부 신원 전환 UX + 화면 반영 (마지막 스테이지)`

#### MQ-1711 — 재무부 신원 전환 UX
- `frontend/lib/role.ts`(`ManagerIdentity`·`MANAGER_IDENTITIES`·localStorage 기반
  `getManagerIdentity`/`setManagerIdentity`) · `ManagerIdentitySwitch.tsx`(신규) ·
  `AppBar.tsx`
- 병렬 진행 중 MQ-1712가 같은 파일에 선제로 같은 코드를 써놓은 걸 스스로 발견해 중복 선언
  정리(다른 태스크와의 파일 충돌을 tool-builder가 직접 해소한 사례)

#### MQ-1712 — API 클라이언트/타입 확장
- `frontend/lib/api.ts`·`types.ts`·`queueState.ts`(`po.approved` tone `ok`→`info`) ·
  `frontend/lib/__checks__/ui_honesty.ts`(공식 회귀 대조군을 `finance_approved`로 이동,
  tool-builder 현실성 평가가 사전에 잡아 둔 필수 항목)
- 회귀: `ui_honesty_contract.py` 291/291(CLAUDE.md 기준선과 일치)

#### MQ-1713 — `PoDetail` 재무 액션 UI
- `FinanceDecisionBar.tsx`(신규) · `PoDetail.tsx`
- 명세는 "DecisionBar 구조 복제"였으나 기존 `RejectPanel`을 재사용하는 쪽으로 판단(D38 취지에
  더 맞음, 중복 코드 없음)

#### MQ-1714 — 승인 큐 화면 재무 대기열 wiring
- `ApprovalQueueScreen.tsx`(재무 대기열 조회 분리, `decideFinance()`, 딥링크 `found` 확장) ·
  `QueueList.tsx`("재무 승인 대기" 섹션)
- `next build` 클린(21라우트, 신규 라우트 없음) — MQ-1711/1712/1713과 통합 그린까지 자체 확인

#### 커밋 전 직접 반영한 비블로커 정정 2건 (reviewer 관찰, 별도 태스크 아님)
- `StatusLegend.tsx` — `approved` 범례가 여전히 "발주 확정"(구 의미)이던 것을 "팀장 승인 —
  재무 승인 대기 (D119)"로, `finance_approved`/`finance_rejected` 범례 신규 추가
- `ApprovalQueueScreen.tsx`의 "최근 처리"(`done`) 목록에서 이제 비종결인 `approved` po를
  제외 — `financePending` 섹션이 이미 그 항목을 보여주므로 중복이자 오해 소지 제거

**eval-runner 종합**: seed 41/41(error_codes 70) · sp2_mcp_roundtrip 20/20 ·
write_tool_contract 30/30 · api_contract 52/52(변동 없음, 프론트 전용 스테이지) ·
sp3_sse_events 22/22 · test_expenditure_limits 16/16 · test_po_a2a_trigger+dispatch
13/13(1차 WinError 10014 소켓 고갈, 단독 재실행으로 해소) · ruff clean · `tsc --noEmit`
clean · `next build` 21라우트 · `ui_honesty_contract.py` 291/291.

**reviewer 게이트**: PASS(블로커 없음). D87(`approved` tone 전환이 실제로 초록 누수 없이
됐는지)·L1 순수성(`role.ts`)·`MANAGER_IDENTITIES[0]` 순서·재무 대기열 조회 분리·
`decideFinance()`의 REST 계약 일치 전부 코드로 직접 확인. 비블로커 관찰 2건은 위에서
바로 반영, 1건(SSR 하이드레이션 잠재 경고, 기존 패턴과 동일 — 이번 스테이지 고유 결함
아님)은 정보성으로만 기록.

---

## Sprint 17 완료

**Stage 1~4 전부 완료.** doc3(자금집행요청서) 렌더 + 재무부 승인 단계(D119)가 실제로 동작한다
— DB 스키마 확장부터 내부통제 판정·REST 엔드포인트·문서 렌더·화면 반영까지 전 층이 연결됨.
14개 태스크(MQ-1701~1714) 전부 완료, 회귀 스위트 전건 그린. 커밋 순서:
`12df5f5`(선행 인프라 픽스) → `7b28aee`+`adca285`(Stage 1) → `76dc766`(배포 문서 갱신,
Sprint 17 태스크는 아님) → `80804fb`+`26fa15b`(Stage 2) → `def1d19`+`366e637`(Stage 3) →
`754baf4`(Stage 4).

**다음 세션 확인 사항**:
- `data/test_expenditure_limits.py`(16건)를 CLAUDE.md 공식 pytest 목록에 반영(현재 "3파일군
  +4파일군"에 미포함)
- `docs/10_DECISIONS.md`에 D120 후보로 `today_total` 자기중복 배제 조건 정식 등재 검토
  (Stage 3 reviewer 관찰)
- ~~`.env.example`의 `INSUQ_SERVICE_TOKEN`/`FINALLQ_SERVICE_TOKEN` 커밋 여부~~ — **해소**.
  사용자 확인: 본인이 직접 추가한 값, FinAllQ·InsuQ와의 A2A 통신에 실사용 중. 커밋 `3755feb`
- ~~`docs/sessions/2026-08-24_spikes_test.md`~~ — **해소**. 사용자 확인: 본인이 만든 파일,
  spikes 실행 결과 전건 PASS 원문 기록. 그대로 둔다(git 미추적 유지)

### 브라우저 QA 완료 (2026-08-24, claude-in-chrome) — 커밋 `fc8375c`

사용자 요청으로 스프린트 종료 직후 진행. 로컬에 격리된 백엔드(:8897)+프론트(:3000,
`MAINTQ_CORS_ORIGINS` 기본 허용 범위 3000~3005 안에서 골라야 CORS 안 막힘 — 처음
3010으로 띄웠다가 "백엔드에 연결하지 못함" 목업 폴백을 만나 재확인) 조합으로 확인.

**정상 동작 확인**: 승인 큐에 "재무 승인 대기" 섹션(PO-0120·PO-0114) 정확히 노출·배지
tone 정직(`info`, 초록 아님)·PO-0117 상세의 "자금집행 요청서 — 해당 없음"·PO-0119
렌더의 "예산 한도 ... 초과" 표기·`StatusLegend` 6종 라벨 전부 육안 확인.

**실제 버그 2건 발견·수정**(자동 회귀가 못 잡는 영역 — 반응성·hydration은 정적 타입
체크·순수함수 회귀 대상이 아니다):
1. 신원 전환 버튼을 눌러도 승인 큐 화면이 재렌더하지 않아 재무 승인 버튼이 새로고침
   전까지 안 뜸(형제 컴포넌트 간 상태 미공유) — 커스텀 이벤트로 해소
2. `getManagerIdentity()`를 렌더 중 직접 호출하는 두 지점에서 SSR/hydration mismatch
   (React가 전체 트리를 클라이언트 재렌더로 강등, 콘솔 에러 다수) — SSR-안전 기본값 +
   마운트 후 동기화로 해소

수정 후 재검증: 양방향 전환 새로고침 없이 즉시 반영·`/technician`에 스위치 미노출·
콘솔 에러 0건·`tsc`/`next build`(21라우트)/`ui_honesty_contract`(291/291) 전부 클린.
