# 세션 로그 — 2026-08-24 (재무부 승인+doc3 · 정비사 랜딩 대시보드)

**브랜치**: master · **범위**: Sprint 17(재무부 승인 게이트 + doc3 자금집행요청서, 4스테이지) →
Sprint 18(정비사 랜딩 화면 전환: 챗봇 → 설비 대시보드, 1스테이지) → 브라우저 QA 버그 수정 →
후속 UI 개선 4라운드(그리드·카드 레이아웃·컴포넌트 분리·사이드바 메뉴) → 배포 설계 문서 개정 →
`docker-compose.yml`에 backend 서비스 추가 → A2A 인증 스킴 교체(D120) → 계정 선택 화면 +
재무담당 전용 랜딩 → 빠른 정리 4건(D121 포함) → **3개 프로젝트(MaintQ·FinAllQ·InsuQ) 동시
기동 브라우저 QA로 실 버그 2건 발견·수정**.
같은 날짜의 다른 세션 로그(`2026-08-24.md` — Sprint 16 마무리/D117/D118/doc1·02, `2026-08-24_backend-hang-and-dashboard.md`,
`2026-08-24_finallq_conversion.md`)와는 별개 세션이다.

## 완료

- **Sprint 17 Stage 1** — D119 등재(재무부 승인 SoD 예외) + `po_drafts.state`에
  `finance_approved`/`finance_rejected` 추가 + 내부통제 판정(예산 한도·1일 누적 한도·FDS·SoD)
  — `data/expenditure_limits.py`(신규), `docs/05_DB_SCHEMA.md §8`
- **Sprint 17 Stage 2** — `POST /api/po/{id}/finance-approve`·`finance-reject` 엔드포인트,
  A2A(FinAllQ 출금 요청) 발신 시점을 finance-approve 이후로 이동 — `backend/routers/po.py`,
  `backend/services/po.py`, `backend/routers/test_po_a2a_trigger.py`(재작성)
  — `docs/06_REPO_API.md §2.2/§2.4`
- **Sprint 17 Stage 3** — 내부통제 계산 조립(예산/한도/FDS/SoD 실제 DB 값 결합) + doc3
  (자금집행요청서) 렌더 — `backend/services/po.py`(`get_po()` 의 `controls`/`a2a_info`/`payee`
  로컬 계산, D86), `backend/services/po_documents.py::render_fund_execution_document()`,
  `data/doc_review.py`
- **Sprint 17 Stage 4(마지막)** — 재무부 신원 전환 UX + 화면 반영 — `frontend/lib/role.ts`
  (`ManagerIdentity`·`MANAGER_IDENTITIES`), `ManagerIdentitySwitch.tsx`(신규),
  `frontend/lib/queueState.ts`(`approved` 상태 라벨·톤 변경 + `finance_approved`/`finance_rejected`
  추가 + `isApprovedState()`), `FinanceDecisionBar.tsx`(신규), `PoDetail.tsx`, `StatusLegend.tsx`
- **Sprint 17 브라우저 QA + 미결 2건 해소** — 실 uvicorn+next dev 로 로그인/전환/승인 흐름 검증,
  버그 2건 발견·수정(아래 트러블슈팅)
- **`docs/13_DEPLOYMENT.md` 전면 개정** — Postgres/pgvector 이미 완료(D116/D117) 전제로 갱신,
  배포 타깃 확정: GCP Cloud Run(backend) + Supabase(Postgres+pgvector) + Vercel/Netlify(frontend)
- **Sprint 18(1스테이지)** — 정비사 랜딩 화면을 챗봇에서 설비 하이라이트 대시보드로 전환
  (MQ-1801~1803) — `frontend/app/(console)/technician/equipment-status/page.tsx`(신규 랜딩),
  `frontend/lib/role.ts`(`ROLE_HOME.technician` 변경), `ChatFab.tsx`(신규, 진단 챗봇 진입 버튼)
- **Sprint 18 브라우저 QA** — 하이라이트 정렬 실측 검증(빨강>주황>파랑>정상 우선순위 동작 확인),
  썸네일 가독성 제약을 사용자가 현재 상태로 수용
- **후속 UI 개선 4라운드**(대화 요청 기반, `/sprint` 미경유):
  1. 4×3 그리드 + 페이지네이션(한 페이지 12개)
  2. 카드 레이아웃 재설계(품번명·명칭 → 큰 이미지 → 위치·설명(인용문구) → 배지) — 와이어프레임
     선검토 후 구현
  3. `EquipmentCard`를 `components/asset/EquipmentCard.tsx`로 분리(기존 `*Card.tsx` 컨벤션 준수)
  4. 3×3 그리드로 축소 + 오른쪽 사이드바 신설(빠른 메뉴 자리) → 실사용 라우트 조사 후
     "발주 신규 작성"·"자산 목록·처분 사전판정" 2개로 채움(`AskUserQuestion`으로 사용자 선택)
- **`docker-compose.yml`에 `backend` 서비스 추가** — "배포된 페이지로 테스트하니 느리다"는
  사용자 문제 제기에 대응, 원격 배포 대신 로컬에서 빠르게 띄워 테스트하기 위함. frontend는
  제외(요청대로) — Vercel/Netlify 배포 결정과 별개로 로컬은 `next dev`로 충분. 루트
  `Dockerfile`(백엔드+MCP subprocess 동봉, 기존 파일)을 그대로 재사용해 `backend` 서비스
  하나로 구성 — MCP("AI 엔진")를 별도 서비스로 분리하지 못한 이유는 아래 "다음 세션" 참고
- **A2A 파트너 인증 스킴 교체(D120)** — InsuQ·FinAllQ 레포를 직접 열어 실 계약을 대조한 결과,
  D93의 Basic(CLIENT_ID/SECRET) 스킴이 InsuQ의 실 인증 필터(Bearer+X-A2A-Partner-Id)와 안
  맞아 자격증명을 채워도 401이 나는 걸 확인 — `credentials.py`·`auth_header.py`를 Bearer+
  파트너ID로 재작성. lookup-clause는 이 수정과 별개로 InsuQ 미구현(501)이라 여전히 막힘
- **계정 선택 화면 + 재무담당 전용 랜딩** — "계정마다 볼 수 있는 페이지가 달랐으면"이라는
  요청에, 진짜 로그인(범위 밖) 대신 시뮬레이션 신원 선택 화면(`/`)을 신설. 재무담당은
  `/manager/finance`(신규)로 이동 — 기존 `ApprovalQueueScreen`을 `focus="finance"` prop으로
  재사용해 일반 승인 대기를 숨기고 재무 승인 대기를 기본으로 연다. 브라우저로 재무 승인
  버튼까지 눌러 실 A2A 왕복 확인(로컬 FinAllQ 어댑터 상대)
- **빠른 정리 4건** — Dockerfile "Northflank"→"GCP Cloud Run" 주석 정정 · `docker compose
  up -d --build` 실제 기동 검증(이전엔 문법만 확인했었음) · CLAUDE.md 공식 pytest 목록에
  `data/test_expenditure_limits.py`(16건) 반영 · **D121** 신설(`today_total` 자기 제외 SQL을
  정식 결정으로 등재). 회귀 수치 재동기화(spikes 1,052→1,075 · seed 37→41 · pytest 83→99 ·
  라우트 21→22)
- **3개 프로젝트(MaintQ·FinAllQ·InsuQ) 동시 기동 브라우저 QA** — 사용자 요청으로 실제
  진단→발주→팀장승인→재무승인→A2A 출금요청(S1→S5) 전체와 담보대출 심사(S8, MaintQ→FinAllQ→
  InsuQ 멀티홉) 전체를 채팅으로 끝까지 밟았다. 둘 다 실제로 성공했고, 그 과정에서 진짜 버그
  2건을 찾아 고쳤다(아래 트러블슈팅). "장비 선택" 드롭다운이 안 바뀌는 것처럼 보인다고
  1차 보고했으나 재확인 결과 **오진** — `<select>`의 `textContent`가 선택 여부와 무관하게
  모든 `<option>`을 나열하는 DOM 특성 때문에 텍스트 기반 점검 도구가 잘못 읽은 것이었다.
  줌 스크린샷으로 실제 화면은 정상 표시("INV-L1-01 · iG5A")임을 확인 후 정정 — 코드 변경 없음

## 결정과 맥락

### D119 — 재무부 승인 SoD 예외
- **계기**: Sprint 17 설계(`docs/superpowers/specs/2026-08-24-finance-approval-doc3-design.md`)를
  구현하며 `finance-approve`/`finance-reject`가 department(소속)를 확인해야 하는데,
  D108이 "department는 권한이 아니다, `require()`는 role만 본다"고 못박아 둔 상태였다.
- **결정**: `require()` 자체는 그대로 role만 보고, 이 두 엔드포인트만 자기 함수 본문에서
  SoD(직무분리) 목적의 추가 `c.department == "finance"` 검사를 한다 — D108을 어기는 게 아니라
  명시적 예외로 등재.
- **대안과 기각 이유**: ① `require()`에 선택적 `department` 파라미터 추가 → 범용 함수의
  단순성을 다른 모든 호출부까지 흔든다. ② 전용 `role: "finance"` 신설 → `X-Role`이
  `technician`/`manager` 두 값으로 고정된 계약(D38)을 깨고 소속 문제를 권한 문제로
  과잉 격상시킨다.

### D120 — A2A 인증 스킴을 Basic에서 Bearer+X-A2A-Partner-Id로 교체
- **계기**: 사용자가 "SERVICE_TOKEN 이름으로 통일하고 싶다"고 요청 → 확인차 InsuQ·FinAllQ
  레포를 직접 열어보니, InsuQ의 실 인증 필터(`ServiceTokenFilter.java`)는 D93이 정한
  `MAINTQ_A2A_<PARTNER>_CLIENT_ID`/`_SECRET` → Basic 스킴이 아니라 `Authorization: Bearer
  <token>` + `X-A2A-Partner-Id` 자기신고 헤더만 검사하고 있었다. FinAllQ→InsuQ 2차 홉이
  이미 이 스킴으로 실 성공 중이었다.
- **결정**: `credentials.py`를 `<PARTNER>_SERVICE_TOKEN`(단일값) 읽기로, `auth_header.py`를
  Bearer+파트너ID(`maintq-agent`, InsuQ `CustomerSeeder.java` 시드값과 일치) 조립으로 교체.
- **대안과 기각 이유**: ① Basic 유지 + InsuQ에 지원 요청 → 상대가 이미 완성·시연한 걸
  재작업시키는 것. ② 두 스킴 동시 지원 → 실제 쓰이는 스킴은 하나뿐이라 죽은 분기만 생김.
- **부수 발견**: lookup-clause는 이 수정과 별개로 InsuQ가 스킬 자체를 미구현(501 고정
  반환)이라 여전히 막혀 있다 — "곧 될 예정"이라는 사용자 확인에 따라 이번 세션은 이 블로커를
  더 파지 않았다.

### D121 — `today_total` 자기 제외 SQL을 정식 결정으로 등재
- **계기**: 이전 세션(Sprint 17 Stage 3) 구현 당시 스펙 원문에 없던 `AND po_id != ?` 조건이
  코드에만 남아 있고 설계 문서엔 없었다.
- **결정**: 이미 `finance_approved`된 발주를 재조회할 때 자기 금액이 "오늘 누적"에 중복
  산입되는 걸 막는 의도된 보정이라고 정식 등재. 대안(스펙 원문 그대로/전이 시점 캐시)은
  각각 표시 버그·D86 위반이라 기각.

## 트러블슈팅

### `sod_check()` TypeError — `requested_by`가 NULL일 때 크래시
- **원인**: `sorted({requested_by, decided_by, finance_decided_by})`가 `None`과 `str`을
  비교하려 해서 터진다. `requested_by`는 D23/D37상 정당하게 NULL일 수 있는 값(테스트
  픽스처만의 문제가 아님).
- **해결**: 순수 함수(`sod_check`) 자체는 손대지 않고, 호출부(`backend/services/po.py`)의
  가드를 `if po.get("finance_decided_by")` → `if po.get("requested_by") and po.get("decided_by")
  and po.get("finance_decided_by")` 로 확장.
- **커밋**: `def1d19`

### 순환 import — `now_utc_sql` 최상단 import
- **원인**: 설계 스펙 문구 그대로 `backend/services/po.py` 최상단에 `now_utc_sql`을
  import하면 `po → decisions → disposal → po` 순환이 발생(`decisions.py`·`disposal.py`가
  모두 `po.iso_utc`를 최상단에서 import).
- **해결**: 함수 내부(지연) import로 전환 — 스펙 문구와 다른 의도적 편차, reviewer가 안전성
  확인 후 승인.
- **커밋**: `80804fb`

### 재무부 신원 전환이 새로고침 없이 반영되지 않음
- **증상**: `ManagerIdentitySwitch`(AppBar)에서 신원을 바꿔도 `ApprovalQueueScreen`(페이지)의
  승인 버튼 노출 여부가 갱신되지 않음 — 새로고침해야만 반영.
- **원인**: 두 컴포넌트가 형제 관계라 React 상태를 공유하지 않고, `localStorage`만 바꿔서는
  페이지 쪽이 재렌더할 계기가 없음.
- **해결**: `frontend/lib/role.ts`에 `MANAGER_IDENTITY_CHANGE_EVENT` 커스텀 `window` 이벤트를
  추가, `setManagerIdentity()`가 디스패치, `ApprovalQueueScreen`이 `useEffect`로 구독해 강제
  재동기화.
- **커밋**: `fc8375c`

### SSR/hydration mismatch — `getManagerIdentity()` 를 렌더 바디에서 직접 호출
- **증상**: `localStorage`에 비기본 신원이 저장돼 있으면 `Warning: Text content did not match
  server-rendered HTML` + 전체 CSR 폴백.
- **원인**: `ManagerIdentitySwitch`·`ApprovalQueueScreen` 둘 다 render 시점에 `getManagerIdentity()`
  (localStorage 읽기)를 직접 호출 — 서버는 항상 기본값을 렌더하는데 클라이언트는 저장된 값을
  렌더해서 불일치.
- **해결**: `useState(MANAGER_IDENTITIES[0])`로 SSR-safe 기본값을 시딩하고, 실제 값은
  post-mount `useEffect`에서만 동기화.
- **커밋**: `fc8375c`

### `data/pg_isolation.py` — 격리 스키마에서 `vector` 타입을 못 찾음
- **원인**: `SET search_path TO "{schema}"`가 `public`을 제외 — pgvector 확장이 이미 전역
  등록돼 있어 `CREATE EXTENSION IF NOT EXISTS vector`가 조용히 no-op하지만, `vector` 타입
  자체는 `public`에만 존재해 격리 스키마에서 해석 불가.
- **해결**: `SET search_path TO "{schema}", public`으로 수정.
- **커밋**: `12df5f5` (이 세션의 첫 커밋, 이전 세션이 남긴 미완결 마이그레이션 이슈)

### `evidence.basis`가 문자열일 때 PO 카드·문서 렌더가 죽음 (브라우저 QA로 발견)
- **증상**: 채팅으로 진단→발주 흐름을 실제로 끝까지 밟다가 `create_po_draft`는 성공했는데
  채팅에 "응답 생성에 실패했습니다"가 붙었다. `GET /api/po/{id}`도 500.
- **원인**: `evidence`는 LLM이 `create_po_draft` 호출 시 자유 형식으로 채우는 값(D34, 스키마
  강제 없음)인데, LLM이 `basis`를 리스트가 아니라 통짜 문자열로 채웠다(실측 PO-0121). 렌더
  코드(`_attach_print_pages`·`_evidence_lines`)가 `basis`를 리스트-of-dict로 가정하고
  `for entry in basis: entry.get(...)`를 돌리다, 문자열을 순회하면 문자 하나하나가 `entry`가
  돼 `.get()` 호출에서 `AttributeError`.
- **해결**: 두 함수 모두 `entry`가 dict가 아니면 건너뛰도록 방어 추가 — 지어내지 않고, 죽지도
  않는다. 기존 seed 픽스처(PO-0117 등)는 전부 정상 형태(list-of-dict)라 이 버그가 회귀
  스위트에서 한 번도 안 걸렸다 — LLM 실사용 경로에서만 드러나는 종류였다.
- **회귀**: `backend/services/test_po.py`(5건)·`test_po_documents.py`(3건) 신규.
- **커밋**: `88bd22f`

### 백엔드를 기본 포트(8000) 밖에서 띄우면 A2A 확장 도구 2종이 조용히 404
- **증상**: 채팅에서 `assess_equipment_loan` 호출 시 "FinAllQ 사전판정을 지금은 확인할 수
  없습니다 — Not Found".
- **원인**: 앱 버그 아님 — QA 환경 설정 실수. `search_insurance_clause`·`assess_equipment_loan`
  MCP 도구는 외부 파트너를 직접 안 부르고 MaintQ 자기 백엔드 REST(`MAINTQ_BACKEND_BASE_URL`,
  기본값 `localhost:8000`)를 거친다(D15·D93) — 백엔드를 8901 같은 다른 포트로 띄우면서 이
  env를 안 맞추면 MCP 서버가 여전히 8000을 호출해 404가 난다. 이미 `.env.example`에
  문서화돼 있었지만 QA 중 놓쳤던 것.
- **해결**: `MAINTQ_BACKEND_BASE_URL`을 실제 포트로 맞춰서 재기동 → assess-loan(S8)이
  MaintQ→FinAllQ→InsuQ 멀티홉까지 4.7초 만에 `decision: approved` 실 성공.
- **교훈**: 시연 당일 포트를 바꿔야 하면 이 env도 같이 챙길 것 — 코드 수정 없음, 운영 메모.

## 검증 상태

- 회귀: Sprint 17 각 스테이지(seed·SP2·write_tool·`api_contract`(41→52건, 재무 전이/문서
  검사 추가)·SP3) 전부 통과, `tsc --noEmit`·`next build`·`ui_honesty_contract` 전부 통과
- Sprint 18: `tsc`·`next build`·`ui_honesty_contract`(268→274, `EquipmentCard.tsx` 신설로
  L2 6건 자연 증가) 전부 통과
- 브라우저 QA(claude-in-chrome, 격리 로컬 uvicorn:8897 + next dev:3000): 재무부 승인 흐름,
  정렬 우선순위(>>>정상), 사이드바 링크 왕복 — 모두 실사용 시나리오로 확인
- D-범위 표기 정합성(이 세션 `/done`에서 수행): `CLAUDE.md`·`README.md`·`docs/README.md`·
  `.claude/agents/reviewer.md` 4곳 모두 D1~D118 → **D1~D119**로 정정
- `docs/05_DB_SCHEMA.md §8`·`docs/06_REPO_API.md §2.2/§2.4`는 Sprint 17 스테이지 진행 중
  이미 갱신 확인됨 — `docs/04_MCP_TOOLS.md`는 D119가 MCP 도구 계약을 건드리지 않아 무변경 정상
- `docker compose up -d --build` **실제** 빌드+기동 검증 완료(임시 포트로 확인 후 8003 복귀,
  `/health`·DB 조회 엔드포인트까지 확인) — 이전엔 `config -q` 문법 검증만 했었음
- A2A 8파일군 88/88(D120 반영, 기존 86+2) · pytest 공식 4파일 99/99(`data/test_expenditure_limits.py`
  16건 포함, 실측 8m46s) · `backend/services/test_po.py`·`test_po_documents.py` 신규 8/8 ·
  `api_contract` 52/52(재시드 후 재확인, PO 상태 변형 오염 없음) · ruff clean
- D-범위 표기 정합성: `CLAUDE.md`·`README.md`·`docs/README.md`·`.claude/agents/reviewer.md`
  4곳 모두 **D1~D121**로 정정(D120·D121 신설 반영)
- 회귀 수치 재동기화(CLAUDE.md 실측 기준선 문단): spikes 33스위트 1,052→**1,075**건 ·
  seed 37→**41**건 · pytest 83→**99**건(공식 4파일) · 프론트 라우트 21→**22**개
- **3개 프로젝트 동시 기동 브라우저 QA(claude-in-chrome)**: MaintQ(로컬 native, 격리 포트)
  + FinAllQ 어댑터(:9101, 이미 기동 중)·코어(:8082, docker)·프론트(:3002) + InsuQ 어댑터
  (:9102)·백엔드(:8081, docker)·ai-engine(:8000, docker)·프론트(:3001, docker) 전부 살아있는
  상태에서, 시나리오 1(진단→발주→팀장승인→재무승인→A2A 출금요청)과 시나리오 2(담보대출
  심사, MaintQ→FinAllQ→InsuQ 멀티홉) **둘 다 채팅으로 끝까지 실행해 성공 확인**. FinAllQ·
  InsuQ 자체의 직원(심사역)용 검토 화면은 발견하지 못함(로그인한 화면은 개인 소비자용
  대시보드였다) — 그쪽 팀 UI 영역이라 이번 세션에서 더 파지 않음
- QA 중 실 DB(로컬 docker postgres)를 두 번 건드렸다 — (a) `docker compose down` 후
  postgres 컨테이너 재기동을 깜빡해 백엔드가 전부 타임아웃(앱 버그 아님, 컨테이너 복구로
  해결) (b) 채팅으로 만든 PO-0121·승인 상태 변경이 남아 `api_contract` ㊶ 1건 실패 →
  `data/seed.py --with-error-codes` 재시드로 정리, 재실행 52/52 확인

## 다음 세션

1. `docs/13_DEPLOYMENT.md §6`의 나머지 open item(Cloud Run 레플리카 정책, Supabase pooling
   모드) 결정
2. 사이드바 빠른 메뉴 — 현재 2항목, 추가 요청 없으면 그대로 유지
3. (선택) `docs/07_BACKLOG.md` P14 — MCP를 stdio 자식 프로세스에서 네트워크 서비스로 바꿔
   compose에서 진짜 2서비스(backend/mcp)로 쪼갤지는 아직 백로그, 순전히 시연용 어필이라
   당장 급하지 않음(이번 세션에 사용자에게 설명·확인 완료)
4. lookup-clause — InsuQ가 "곧 구현할 예정"이라고 함(사용자 확인). InsuQ 쪽에서 501이 풀리면
   MaintQ 쪽 인증(D120)은 이미 맞는 스킴이라 바로 재검증 가능 — InsuQ 배포 소식 들어오면
   `spikes/lookup_contract.py` + 실 채팅으로 확인
5. FinAllQ·InsuQ 직원(심사역)용 검토 화면 위치 파악 — 시연 스토리를 "MaintQ 화면 → 상대방
   화면에도 뜨는 것 확인"까지 보여주고 싶다면 필요. 이번 세션엔 소비자용 화면만 찾았음
   (해당 팀에 직접 문의가 더 빠를 수 있음)
6. 실제 데모 리허설/큐시트 작성 — 기술적으로는 시나리오 1·2 둘 다 이번 세션에 E2E 성공
   확인됐으니, 다음은 발표용 순서·대사·화면 전환 타이밍을 정리하는 단계

## 사람 승인 대기

- `TODO_직접할일.md` 변화 없음(이 세션은 매뉴얼 다운로드·안전 문구 승인 등 해당 항목 없음)
