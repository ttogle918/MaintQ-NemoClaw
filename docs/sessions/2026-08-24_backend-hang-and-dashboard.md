# 세션 로그 — 2026-08-24 (라이브 서버 hang 근본원인 해결 + 정비사 랜딩 대시보드 + doc3 설계)

**브랜치**: master (최종) — 작업은 `feat/technician-landing-dashboard`(대기 중)·
`fix/backend-dotenv-import-order`(머지 완료 후 삭제) 두 브랜치에서도 진행 · **범위**: 직전
세션(`2026-08-24.md`)이 "원인불명"으로 남기고 간 라이브 서버 hang 재조사·근본원인 해결,
정비사 콘솔 랜딩 화면을 챗봇에서 설비 대시보드로 전환, doc3(자금집행요청서)+재무부 승인
단계 설계 착수

## 완료

### 라이브 서버 hang 근본원인 확정·수정 — `46ef7e0`
- 재부팅 후에도 재현 확인(`/api/po`·`/api/assets` 전부 타임아웃, `/health`만 응답) —
  트러블슈팅 재개 대신 우선 보고만 하고 넘어갔다가, 사용자 요청으로 나중에 다시 착수
- `superpowers:systematic-debugging`으로 정식 조사: `uv run --with py-spy py-spy dump --pid`
  로 실행 중인 워커 스레드 스택을 떠서 `psycopg.connect()` 안의 `wait_conn`/`select()`
  에서 멈춰 있는 것을 직접 확인 — 쿼리나 락이 아니라 **TCP 연결 시도 자체**가 멈춰 있었다
- 최소 재현으로 원인 격리: `backend/main.py`가 `backend.routers.*`(→ `backend.deps`
  → `backend.db`)를 import한 **뒤에** `load_dotenv(override=False)`를 호출하고 있었다.
  `backend/db.py`의 `DATABASE_URL`은 모듈 import 시점에 `os.environ.get(...)`으로 **한 번만**
  평가되는 전역 상수라, `.env`가 아직 안 실린 상태에서 잘못된 기본값
  (`postgresql://localhost/maintq`, 포트 5432·자격증명 없음)으로 영구 고정됐다 — 셸에
  `DATABASE_URL`이 직접 export 안 돼 있으면 100% 재현되는 결정론적 버그였다
- `load_dotenv()`를 해당 import들보다 앞으로 이동해 수정(`# noqa: E402` 4곳, 의도적 순서라
  주석으로 명시). `.env` 미export 상태에서 `/health`·`/api/assets`·`/api/po` 전부 정상
  즉시 응답 확인
- `data/seed.py --with-error-codes`도 같은 근본원인 계열(다만 `load_dotenv()` 자체가
  아예 없음)이었음을 확인 — `DATABASE_URL`을 셸에 export하고 재실행하니 37/37 정상 통과.
  이쪽은 이번 세션에서 코드 수정은 하지 않음(§다음 세션 참고)
- 브랜치 `fix/backend-dotenv-import-order`(master에서 분기) → master로 로컬 머지·브랜치 삭제

### 정비사 랜딩 화면 전환 (챗봇 → 설비 대시보드) — `feat/technician-landing-dashboard`
- `superpowers:brainstorming` → 스펙(`docs/superpowers/specs/2026-08-24-technician-landing-
  dashboard-design.md`) → `superpowers:writing-plans`(`docs/superpowers/plans/2026-08-24-
  technician-landing-dashboard.md`) → `superpowers:subagent-driven-development`(4태스크,
  각 구현+리뷰) → 최종 전체 브랜치 리뷰(opus) → 수정 1라운드(재검토 통과) 순서로 완주
- 기존 `/technician/equipment-status` 화면(Sprint 10 산출물)을 랜딩으로 승격 —
  `ROLE_HOME.technician`을 `/technician`→`/technician/equipment-status`로 변경(`d780e08`)
- 대시보드 카드에 모델별 실 매뉴얼 도면 이미지+인용문구(iG5A·S100, IE5는 폴백 아이콘)·
  모델명 배지 추가(`0fd7dad`)
- 우측 하단 원형 챗 플로팅 버튼(`ChatFab.tsx`) 신설 — draft 발주 건수 배지, `/technician`
  으로 이동(`9d88d63`)
- 최종 리뷰(opus)가 실제 결함 1건 발견: `ChatFab`의 draft 건수 fetch가 `visible` 무관하게
  무조건 실행돼 **매니저 화면에서도 `X-Role: technician` API를 호출**하는 권한 경계 누출
  — `role.ts`가 스스로 명시한 "라우트별로 X-Role을 고정해야 권한 경계가 실제로 드러난다"는
  원칙 위반. `visible` 가드 추가로 수정, 배지 접근성 라벨(`aria-label`)·`frontend/README.md`
  redirect 표기 3곳 정정도 같은 커밋(`c95fd2a`)에 포함, 재검토 통과
- 검증: `tsc --noEmit` 클린, `next build` 21라우트, `ui_honesty_contract.py` 291/291
  (기존 기준선과 정확히 일치, 회귀 없음)
- **브랜치는 머지하지 않고 대기 중** — 사용자가 "그대로 유지 (나중에 처리)" 선택

### doc3(자금집행요청서) + 재무부 승인 단계 설계 — `fd40637`
- D118이 "내부통제 판정 로직이 DB에 없어서" 미뤄뒀던 doc3에 착수 결정
- `data/templates/03_자금집행요청서.docx` 플레이스홀더 실측 추출(zipfile+regex, D118과
  같은 방법) — 3단계 서명(정비사→팀장→**재무담당자**, 신규)·내부통제 4항목
  (`BUDGET_CHECK`·`DAILY_LIMIT_CHECK`·`FDS_VERDICT`·`SOD_CHECK`)·담보/대출 섹션(조건부)·
  `MFA_STATUS`·`A2A_DELEGATED`/`A2A_TARGET`를 확인
- 설계 확정(스펙 문서 커밋): `po_drafts` 상태 전이에 `finance_approved`/`finance_rejected`
  추가(`approved` 뒤), 신규 REST `POST /api/po/{id}/finance-approve`·`finance-reject`
  (`department='finance'`인 manager 전용, D108 명시적 예외로 D119 후보 등재 필요), 예산/
  일일한도/FDS/SoD 판정 로직(전부 "목업 전제" 코드·문서 양쪽 명시, D74·D92 선례),
  기존 `approve()`에 있던 A2A `request-withdrawal` 전송을 재무 승인 이후로 이동
- 명시적 스코프 제외: 담보/대출 섹션(S8 대출 흐름과 연결은 별도 과제, N/A 고정) ·
  `MFA_STATUS`(MaintQ에 MFA 없음, 이 필드만 "미구현" 정직 고지 — 문서 전체 무효화는 아님,
  D62 판단)
- **구현은 착수하지 않음** — 규모가 이번 세션 대시보드 작업보다 크다고 판단해 `/sprint`
  로 스테이지 분리 진행을 권고, 사용자가 다음 세션에 이어받기로 함

## 의논 내용과 결정 맥락

- **hang 원인 재조사 여부**: 사용자가 세션 시작 시 "여전히 hang하면 트러블슈팅 재개하지
  말고 바로 보고"라고 명시해서 1차 재현 확인 후 즉시 멈추고 보고했다. 이후 사용자가
  본작업(대시보드) 완료 뒤 "(a) 라이브 서버 hang 조사부터"를 명시적으로 요청해 재착수 —
  최초 지시와 나중 지시가 다른 시점의 다른 결정이라는 걸 구분해서 따랐다
- **"동시 세션 접근" 이론 폐기**: 직전 세션(`2026-08-24.md`)과 크로스세션 대화 기록
  (`2026-08-24_finallq_conversion.md`)은 hang을 FinAllQ 세션과의 동시 Postgres 접근
  경합으로 잠정 결론 내렸었다. 이번 조사로 **완전히 결정론적인 코드 버그**(import 순서)
  였음이 드러나 그 이론은 폐기됐다 — 동시 접근이 실제로 있었다면 별개의 우연이었을
  가능성이 높다(재현이 매번 100%였고 셸의 `DATABASE_URL` export 여부와 정확히 상관관계가
  있었다)
- **대시보드 vs 완전 신규 화면**: 기존 `/technician/equipment-status`가 사용자가 원한
  그림(카드형 목록+이상탐지 배지)과 이미 매우 가까워서, 완전 신규 화면 대신 확장하는
  쪽으로 결정 — 백엔드·API 변경 0건으로 끝났다
- **카드 이미지 — 자체 아이콘 vs 실 도면**: 처음엔 인용 의무(라이선스 고지) 부담을 피하려
  목록 카드엔 자체 제작 아이콘을 제안했으나, 사용자가 실 도면+작은 인용문구를 선택 —
  `EquipmentHotspotDiagram.tsx`가 이미 확립한 라이선스 표기 패턴을 그대로 재사용했다
- **챗 FAB 배지 의미**: "미읽음 메시지" 개념은 백엔드에 아예 없다(D41 — SSE 대화 미저장)는
  걸 먼저 밝히고, 실측 가능한 값(draft 상태 발주 수)으로 대체 — D62 원칙을 UI 설계
  단계에서부터 적용한 사례
- **doc3 재무 승인 위치 — MaintQ 내부 vs FinAllQ 반영**: 기존 A2A request-withdrawal 응답에
  이미 `pending_action:"finance-approval"`이 있다는 걸 발견해 "FinAllQ 응답을 그대로
  반영"하는 안도 제시했으나, 사용자가 "MaintQ 내부에 새 단계 신설"을 선택 — FinAllQ 크로스팀
  조율 없이 이번 세션 스코프 안에서 완결 가능한 방향
- **doc3 담보/대출 섹션 스코프**: 템플릿에 이미 있는 필드라 포함할지 물었으나, S8
  assess-loan 흐름과 얽혀 범위가 커진다는 이유로 제외 결정 — 일반 부품 발주(S1/S2)만
  대상으로 좁혔다

## 트러블슈팅

### `backend.main:app`의 모든 DB 조회 엔드포인트가 무한 hang
- **증상**: `/health`는 즉시 응답하지만 `/api/po`·`/api/assets` 등은 몇 분을 기다려도
  응답 없음. `data/seed.py --with-error-codes`도 출력 없이 멈춤
- **원인**: `backend/main.py`가 `load_dotenv(override=False)`를 `backend.routers.*` import
  뒤에 호출 — `backend/db.py`의 `DATABASE_URL` 전역 상수가 `.env` 반영 전 시점에 잘못된
  기본값으로 고정됨. 그 기본값(`postgresql://localhost/maintq`, 포트 5432)에 대한
  `psycopg.connect()`가 Windows에서 빠른 실패(ECONNREFUSED) 대신 무한 대기
- **해결**: `load_dotenv()`를 관련 import들보다 앞으로 이동 (`backend/main.py`)
- **커밋**: `46ef7e0`
- **검증**: `py-spy dump --pid`로 워커 스레드가 `psycopg.connect`의 `select()`에 멈춘 것을
  직접 확인 → 최소 재현 스크립트 8종으로 변수 하나씩 격리(스레드 유무·asyncio 유무·MCP
  서브프로세스 유무·row_factory 유무·Depends 유무 — 전부 무관함을 증명) → import 순서만
  바꾼 재현에서 즉시 해소 확인 → 실제 파일 수정 후 `.env` 미export 상태로 최종 검증

## 검증 상태

- 프론트: `tsc --noEmit` 클린, `next build` 21라우트, `ui_honesty_contract.py` 291/291
  (`feat/technician-landing-dashboard` 브랜치, 회귀 없음)
- 백엔드 hang 수정: `ruff check backend/main.py` 클린, `.env` 미export 상태에서
  `/health`·`/api/assets`·`/api/po` 실측 200 확인 (master)
- **회귀 스위트 전체(seed.py + spikes 33종)는 이번 세션에서도 재실행하지 않음** — 사용자가
  "나중에 시간 날 때 백그라운드로 돌리겠다"고 함. hang이 해소됐으니 다음엔 정상 실행될
  가능성이 높지만 **미확인 상태**. CLAUDE.md의 291/291 등 기준선은 이번 세션 변경분과는
  다른 스위트(spikes)라 직접 검증되지 않았다

## 다음 세션

1. **회귀 스위트 전체 재실행** — `data/seed.py --with-error-codes` + `spikes/` 33종
   (hang이 해소됐으니 이번엔 완주 가능성 높음). CLAUDE.md 실측 기준선 갱신
2. **doc3 + 재무부 승인 구현** — `docs/superpowers/specs/2026-08-24-finance-approval-doc3-
   design.md` 대로. 규모가 커서 `/sprint`로 스테이지 분리 권장(예: Stage 1 DB·상태전이·
   판정로직, Stage 2 REST+A2A 이동, Stage 3 문서렌더, Stage 4 화면). 스펙의 "미결 항목"
   (재무부 로그인 전환 UX, D119 정식 등재, S# 시나리오 표기)을 스테이지 계획 전에 먼저 결정
3. **`feat/technician-landing-dashboard` 브랜치 처리** — 계속 대기 중, 머지 여부 사용자
   판단 필요
4. **`data/seed.py`에 `load_dotenv()` 추가 여부** — 이번 세션에서 코드는 안 고쳤다(문서/
   워크플로 갭으로 남겨둠). `backend/main.py`처럼 진입점에서 `.env`를 로드하게 할지,
   아니면 "셸에 `DATABASE_URL`을 미리 export하고 실행한다"는 관례를 CLAUDE.md 실행
   커맨드에 명시하는 선에서 끝낼지 결정 필요

## 사람 승인 대기

- `TODO_직접할일.md` 변화 없음 (이번 세션에서 항목 추가/제거 없음)
