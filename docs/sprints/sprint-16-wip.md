# Sprint 16 WIP — MQ-1614 (Stage 5, 마지막 태스크)
**저장 시각**: 2026-08-23 (세션 진행 중 — 대규모 Postgres 마이그레이션 완성 작업, 4차 체크포인트)
**상태**: **33/33 스파이크 전부** + **새로 발견한 미반영 pytest 스위트(8파일·86건)까지 전부**
실 Postgres 위에서 검증 완료. 남은 과제 없음 — 아래 "4차 체크포인트" 절 참고.

## 4차 체크포인트 후속 — 미반영 pytest 스위트(8파일·86건) 수정 완료

발견 당시 46/86 FAIL 이었으나, 근본 원인 하나를 고치니 대부분 같이 풀렸다:

1. **`backend/a2a/payloads.py`·`backend/a2a/trace.py`** — `connect(Path(db_path) if
   db_path else None)` 패턴 제거, `connect(db_path)` 로 직결. Postgres DSN 문자열을
   `Path()` 로 감싸면 `backend/db.py::connect()` 의 `isinstance(db_path, str)` 검사를
   벗어나 조용히 실 `DATABASE_URL`(공유 public)로 샌다 — 이게 대부분의 실패 원인이었다.
2. **`backend/conftest.py`** — `db_path`/`seed_po`/`link_finallq` 픽스처가 여전히
   `sqlite3.connect()` 로 SQLite 파일을 만들던 것을 `data/pg_isolation.create_isolated_schema
   (label="a2a_test", clone_data=False)` + `data/dbcompat.connect_dsn()` 으로 교체 —
   `bundle_integrity` 포팅과 같은 패턴. 발췌 스키마(`_SCHEMA` 상수)도 통째로 걷어내고
   프로덕션 전체 스키마를 그대로 쓴다.
3. **`backend/a2a/test_trace.py`·`backend/routers/test_a2a.py`·
   `backend/services/test_po_a2a_dispatch.py`** — 파일 내부에 각자 만들어 둔 `_traces()`/
   `_rows()` 헬퍼가 `sqlite3.connect(db_path)` 직결이었던 것을 `dbcompat.connect_dsn()` 으로.
4. **`backend/routers/test_a2a.py`·`backend/routers/test_po_a2a_trigger.py`** —
   `client` 픽스처가 `monkeypatch.setenv("MAINTQ_DB", ...)` 로 세팅하고 있었다 — Postgres
   전용 `backend/db.py` 는 `MAINTQ_DB` 를 아예 안 읽는다(`s10_smoke.py` 실사고와 같은 패턴).
   `monkeypatch.setattr("backend.db.DB_PATH", db_path)` 전역 override 로 교체.
5. **무관한 별도 문제 하나 더 발견**: `backend/a2a/test_client.py` 등 async 테스트가
   `pytest-asyncio` 플러그인 미설치로 전부 실패하고 있었다(Postgres 와 무관, 원래
   `uv run --with pytest` 실행 커맨드에 플러그인이 안 딸려 있었다) — 실행 커맨드에
   `--with pytest-asyncio` 추가로 해소.

**결과**: `uv run --with pytest --with pytest-asyncio python -m pytest backend/a2a/test_auth_header.py
backend/a2a/test_client.py backend/a2a/test_credentials.py backend/a2a/test_payloads.py
backend/a2a/test_trace.py backend/routers/test_a2a.py backend/routers/test_po_a2a_trigger.py
backend/services/test_po_a2a_dispatch.py` → **86/86 PASS**. 격리 스키마 잔존 0개·
`error_codes` 70행 불변 확인. 기존 공식 pytest 3파일(83건)·spikes 33종·`bundle_integrity`·
2개 A2A 스파이크 전부 재확인 — 회귀 없음.

**CLAUDE.md 반영 필요**(다음 `/done` 또는 이번 세션 마무리 시): 공식 pytest 목록을
"3파일 83건"에서 "4파일군 169건"(기존 3파일 + 이 8파일)으로 갱신하고, 실행 커맨드에
`--with pytest-asyncio` 를 추가할 것 — async 테스트가 있는 한 계속 필요하다.

## 4차 체크포인트 (2026-08-23, 이어받은 세션) — 남은 1개 스파이크 포팅 완료

`bundle_integrity.py`(26건, 원본 25 + 신설 1)·`a2a_outbound_contract.py`(4건)·
`a2a_e2e_integration_spike.py`(2건) 를 tool-builder 에이전트가 `data/pg_isolation.py`·
`data/dbcompat.py` 기존 인프라로 포팅했다. 검증: 세 파일 각각 단독 재실행 PASS, 격리 스키마
잔존 0개, `error_codes` 70행 불변, `po_drafts.PO-0117`·`traces` 실 DB 불변, `ruff` clean —
전부 이 세션이 tool-builder 결과와 별개로 직접 재실행해 확인했다.

- **포팅 착수 전 발견한 실제 오염 사고**: `a2a_e2e_integration_spike.py`(미포팅 버전)가
  과거 실행에서 `backend.services.po.transition(..., db_path=Path(td)/"maintq_e2e.db")`
  호출 시 `db_path` 가 `Path` 객체라 `backend/db.py::connect()` 의 `isinstance(db_path, str)`
  분기를 타지 못하고 조용히 실 `DATABASE_URL`(공유 `public`)에 썼다 — `po_drafts.PO-0117` 이
  `approved` 로, `traces` 에 `session_id='S1'` 잔여 2행이 남아 있었다. `data/seed.py
  --with-error-codes` 재시드로 정리(37/37, 70행, PO-0117 `pending` 복구 확인).
- **`bundle_integrity` ⑫ 유일한 로직 변경**: SQLite 는 `foreign_keys` 기본 OFF 라 자산
  DELETE 가 그냥 됐지만, Postgres 는 `equipment.asset_id → assets.asset_id` FK 를 강제한다 —
  `DELETE FROM assets` 전에 `UPDATE equipment SET asset_id=NULL` 을 추가해 해소했다(검사
  의미는 동일, "판정 직후 DELETE → asset_disappeared" 그대로).
- **실제 gap 발견 — 같은 세션에서 바로 수정함(아래 "4차 체크포인트 후속" 절)** —
  `backend/a2a/payloads.py` 의 `get_finallq_company_id`·`build_request_withdrawal_payload`·
  `build_lookup_clause_payload`·`build_assess_loan_payload` 전부 `connect(Path(db_path) if
  db_path else None)` 패턴이었다. `db_path` 로 이미 유효한 Postgres DSN 문자열을 넘겨도
  `Path()` 로 감싸는 순간 `backend/db.py::connect()` 의 `isinstance(db_path, str)` 검사를
  벗어나 **조용히 실 DB로 되돌아간다** — 위 오염 사고의 근본 원인이 바로 이거다.
  `backend/services/po.py` 는 `db_path` 를 그대로 전달해 이 문제가 없다 — 두 모듈의 관례가
  어긋나 있었다. 포팅된 두 스파이크는 당시 `db_path` 를 아예 안 넘기고 `DB_PATH` 전역
  오버라이드에만 의존해 우회했지만, 근본 원인 자체는 뒤이어 `payloads.py`·`backend/a2a/
  trace.py`(같은 패턴)에서 `Path()` 래핑을 걷어내는 것으로 직접 해소했다.

## 새로 발견했던 미반영 pytest 스위트 — 같은 세션에서 수정 완료 (아래 "4차 체크포인트 후속" 참고)

CLAUDE.md 회귀 스위트 목록의 pytest 는 "3파일 합산 83건"(`data/rules/test_rules.py`·
`backend/agent/test_llm_cache.py`·`data/external/test_elice_docvision.py`)만 공식이었다.
그런데 커밋 `5895c2e`("A2A 코드 테스트 75건 추가")가 별도로 8개 파일을 신설해 놓았고
CLAUDE.md 에 전혀 반영이 안 돼 있었다: `backend/a2a/test_auth_header.py`·`test_client.py`·
`test_credentials.py`·`test_payloads.py`·`test_trace.py`·`backend/routers/test_a2a.py`·
`test_po_a2a_trigger.py`·`backend/services/test_po_a2a_dispatch.py`. 처음 발견 시점 실측은
86건 중 46건 FAIL 이었으나, 사용자가 "지금 바로 고치자"고 결정해 같은 세션에서 바로
포팅했다 — 결과·상세 원인은 아래 "4차 체크포인트 후속" 절 참고, 최종 **86/86 PASS**.

⚠ **재발 방지 필요는 여전히 남는다**: `a2a_partner_tools_contract`(spikes, MQ-1613) ·
이 pytest 8파일(MQ-?, 커밋 `5895c2e`) — "다른 세션이 테스트 파일을 만들어 놓고 CLAUDE.md
공식 목록에 아무도 등록 안 한" 패턴이 이번이 두 번째다. 신규 테스트 파일 커밋 시 CLAUDE.md
반영을 강제하는 체크리스트/훅을 D-결정으로 남기는 것을 고려할 것 — 아직 미결.

## 배경

MQ-1614(전수 회귀 + CLAUDE.md 기준선 갱신)를 시작하려 했으나, 다른 세션이 진행하던
SQLite→Postgres 마이그레이션이 "코드 전환만 끝나고 실제로 접속 가능한 Postgres가 없는"
상태였다. 사용자 승인을 받아 로컬 Postgres를 직접 띄우고 마이그레이션을 마저 완성하는
작업으로 범위가 크게 늘었다(원 계획 문서 자체가 "13개 태스크, 2-3주"로 추정했던 일).

## 완료 — 인프라

`docker-compose.yml`(pgvector/pgvector:pg15, 포트 5434) · `.env` DATABASE_URL ·
`scripts/convert_ddl.py`(DATETIME·BOOLEAN·`IS NOT DISTINCT FROM`·예약어) ·
`scripts/postgres_guards.sql`(D10 영구 트리거+세션 GUC) · `scripts/migrate_data.py`·
`migrate_vectors.py` · **`data/dbcompat.py`**(sqlite3 호환 계층 — Row/translate_sql/
`_cast_bool_params`(INSERT+UPDATE SET 절)/`_AutoSavepoint`/CompatCursor/`lastrowid`/
`connect_dsn`/`add_dsn_option`/**`_BOOL_COMPARE` 가 `=`·`<>`·`!=` 3종 다 처리**) ·
**`data/pg_isolation.py`**(스파이크별 격리 Postgres 스키마) ·
`backend/db.py`·`mcp_server/db.py`(DB_PATH override, `read_only()` 물리적 강제).

## 이번 세션(3차 체크포인트)에서 새로 고친 것

1. **`spikes/a2a_identity_contract.py`** — `run_schema()`(항상 순수 SQLite, DDL 원문
   텍스트 검증이 목적)와 `run_trace()`(Postgres 타겟이면 격리 스키마 DSN, `backend.db.connect()`
   실제 경로를 통과)를 분리. `table_ddl`/`table_info` 에 `pg_get_constraintdef()`/PRAGMA
   에뮬레이션 기반 Postgres 분기 추가. **19/19 PASS**.
2. **`data/dbcompat.py` 의 `_BOOL_COMPARE`** — `col = 0/1` 만 잡던 정규식을 `col <> 1`·
   `col != 1` 까지 확장(`operator does not exist: boolean <> integer`). 여러 스파이크의
   raw SQL(override 컬럼 등)에 공통으로 영향 — 시스템 차원 수정.
3. **`spikes/s10_smoke.py` — 실제 DB 오염 사고 발견 후 수정.** 이 스파이크는 실 uvicorn +
   실 MCP stdio 서브프로세스를 띄우는데, 자식에게 `MAINTQ_DB`(sqlite 시절 경로)만 넘기고
   있었다 — `backend/db.py`·`mcp_server/db.py` 는 Postgres 전용이라 `MAINTQ_DB` 를 아예
   읽지 않는다. 그 결과 자식이 **공유 `public` 스키마**를 그대로 열어 `DEC-0001`·`DEC-0002`
   를 `decisions` 테이블에 실제로 남겼다(최초 무수정 실행에서 실측 확인 —
   `docker exec ... psql -c "SELECT decision_id FROM decisions"` 로 직접 봤다). **`data/seed.py
   --with-error-codes` 재실행으로 정리**(37/37 PASS 재확인, `error_codes` 70행). 수정: 자식
   서브프로세스(uvicorn·MCP stdio) 둘 다 `DATABASE_URL` 을 격리 스키마 DSN 으로 직접 주입
   (`pg_isolation.create_isolated_schema`), `MAINTQ_DB` 대신. **17/17 PASS**, `public.decisions`
   0→0 실측 확인.
4. **`spikes/disposal_sign_contract.py`** — "mutant table" 기법(CHECK 3종을 벗긴 사본
   테이블에서 같은 SQL 이 통과하는지 대조)을 `_mutant_table_pg()` 로 재구현:
   `CREATE TABLE decisions_mutant (LIKE decisions INCLUDING ALL)` 로 제약까지 복제한 뒤
   `pg_get_constraintdef()` 문구로 대상 CHECK 만 이름을 찾아 `DROP CONSTRAINT`. Postgres 는
   `IN (...)` 를 `= ANY (ARRAY[...])` 로 재구성해 렌더링하므로 별도 마커
   (`CHECK_BLOCKING_OVERRIDE_PG`) 필요. 예외 메시지에는 제약 **이름**만 실리고 절 본문이
   없어, `_check_marker_hit()` 헬퍼가 이름을 다시 `pg_constraint` 로 조회해 판정한다.
   **26/26 PASS** (기존 24/27 → 마지막 2건 해소).
5. **`spikes/approvals_contract.py`** — 같은 `LIKE ... INCLUDING ALL` 기법으로 뮤턴트
   대조 재구현(기존엔 Postgres 에서 N/A 로 skip). **26/26 PASS**.
6. **`spikes/db_concurrency.py`** — WAL/busy_timeout(SQLite 전용, Postgres db.py 에는 그
   코드 자체가 없다)는 "대상 없음"으로 명시하고, D10 트리거(⑦⑩⑪)·D15 경계(⑫)는 그대로
   이식, "동시 쓰기가 안 막힌다"는 주장은 MVCC 식으로 재실측(④' — 다른 커넥션이 쓰기
   트랜잭션을 홀드하는 동안 즉시 INSERT 성공, 대기 0.02s). **7/7 PASS**.

## 완료 — 회귀 (실제 Postgres 위에서 검증됨)

- `data/seed.py --with-error-codes` — **37/37 PASS**, `error_codes` 70행
- pytest 3파일(공식 목록) — **83/83 PASS**
- spikes **33/33 PASS**(공식 목록 전체, 4차 체크포인트로 완결):
  `a2a_identity_contract`(19) · `a2a_partner_tools_contract`(22) · `agent_loop_contract`(35) · `api_contract`(41) ·
  `approvals_contract`(26) · `asset_tools_contract`(49) · `bundle_integrity`(26, 4차 체크포인트 포팅) ·
  `citation_render` ·
  `db_concurrency`(7, 재설계) · `deadline_risk_contract`(18) · `disposal_api_contract`(26) ·
  `disposal_sign_contract`(26) · `eval_replay_guard` · `eval_score_contract` ·
  `external_store_contract` · `ie5_extract_contract` · `law_fetch_contract` ·
  `llm_provider_contract` · `lookup_contract`(14) · `mcp_client_contract`(15) ·
  `ownership_api_contract` · `prompt_rules` · `rag_contract` · `repair_flow_contract`(19) ·
  `rules_db_load`(25) · `s10_smoke`(17, DB 오염 발견·수정) · `s4_smoke`(10) ·
  `sp2_mcp_roundtrip`(20) · `sp3_sse_events` · `tools_profile_contract` ·
  `trace_persist`(17) · `ui_honesty_contract`(291) · `write_tool_contract`(30)
- 공식 목록 밖(비공식) A2A 계약 스파이크 2개도 함께 포팅 완료 — `a2a_outbound_contract`(4/4)·
  `a2a_e2e_integration_spike`(2/2). 공식 33종에 포함할지는 CLAUDE.md 갱신 시 판단 필요(위
  "4차 체크포인트" 절 참고).

## 남은 것

`bundle_integrity.py`·`a2a_outbound_contract.py`·`a2a_e2e_integration_spike.py` 세 파일
전부 4차 체크포인트에서 포팅 완료 — spikes 관련해서는 더 이상 남은 것이 없다. 대신 새로
발견한 **미반영 pytest 스위트 1개**(8파일·86건, 46건 FAIL)가 다음 세션 과제로 남는다 —
위 "새로 발견 — 미반영 pytest 스위트" 절 참고.

## 참고 — 스코프 밖 발견 (이번 세션에서 조치 안 함, 별도 확인 필요)

`ls spikes/*.py` 가 **37개**를 반환한다. 그중 `a2a_partner_tools_contract.py`(22건)는
Sprint 16 Stage 4(MQ-1613, 다른 세션이 이 세션 착수 전 이미 커밋·push)가 만든 정식 스위트인데
CLAUDE.md 목록 반영이 누락돼 있었다 — 실행해 보니 Postgres 위에서도 무수정 22/22 PASS(구독
subprocess 는 `list_tools()` 등록만 확인, DB 쓰기가 없어 안전)이라 이번 세션에서 CLAUDE.md
공식 목록·건수에 반영 완료(32→33스위트).

**나머지 4개, 다음 세션에서 실측·정리 완료**:

- **`test_elice_stream.py`** — `.gitignore:31` 에 명시적으로 등재된 미추적 파일. 커밋된 적이
  없다(`git log --all` 무기록). 개인 실험/카세트 스크립트로 보이며 **의도적 제외** — 공식
  목록·CLAUDE.md 반영 대상 아님.
- **`demo_recommendation_1_and_2.py`** — PASS/FAIL 단언이 아예 없다(`grep PASS|FAIL` 무매치),
  콘솔 시각화 전용 "시연" 스크립트(파일 docstring이 스스로 그렇게 밝힌다). 회귀 스위트가 아니라
  데모 자료 — 공식 목록 반영 대상 아님.
- **`a2a_outbound_contract.py`(4건) · `a2a_e2e_integration_spike.py`(2건)** — **이건 진짜
  회귀 스위트다.** Sprint 16 D112 재개분(P34, `abbd87a`~`3a6c558`, Stage 1~3 시점)이 만든
  A2A 아웃바운드(FinAllQ 출금·InsuQ 약관조회) 계약 검증인데, `a2a_partner_tools_contract.py`
  와 같은 시기 작업임에도 공식 목록에 편입이 또 한 번 누락됐었다. **실행해보니 둘 다 현재
  Postgres 위에서 깨져 있다** — `bundle_integrity.py` 와 같은 결함 계열: 픽스처가
  `sqlite3.connect()` 로 직결한 파일 DB 사본을 가정하는데, 실제 코드 경로(`backend.a2a.*`
  → `backend/db.py`)는 이미 Postgres 전용이라 픽스처가 격리하지 못한 **공유 `public` 스키마의
  현재 상태**(예: `partner_links` 에 이미 LINKED 인 파트너가 있음)를 그대로 본다.
  `a2a_outbound_contract.py` 는 `test_partner_links_lookup()`(NOT_LINKED 기대 → 실제
  `CMP-MAINTQ-001` 반환)에서, `a2a_e2e_integration_spike.py` 는 `run_e2e_tests()`(a2a
  trace 2건 기대 → 0건)에서 각각 AssertionError. **공식 목록에 "통과 중"으로 올릴 수 없다** —
  `bundle_integrity` 포팅과 같은 방식(격리 스키마)으로 별도 포팅해야 한다. 스코프는
  `bundle_integrity` 보다 작다(각각 sqlite3 직결 4~5곳, 픽스처 변형 1~2종) — `bundle_integrity`
  포팅 작업에 함께 묶거나 그 직후 처리를 권장.

## 다음 세션에서 할 일

1. 전 32스파이크 최종 전수 재실행(Windows 소켓 고갈 재시도 감안) → 정확한 건수 확보,
   `CLAUDE.md` 실측 기준선 문단 갱신에 반영
2. `npx next build` (프론트 — 이번 세션에서 아직 안 건드림, Postgres 마이그레이션과
   무관하므로 변화 없을 것으로 예상되지만 실측 필요)
3. `docs/10_DECISIONS.md` 에 D-결정 추가 — Postgres 마이그레이션 자체에 대응하는
   결정이 아직 없다(D10 가드 재구현 방식, dbcompat 계층 존재, pg_isolation 스키마
   전략 등을 D 번호로 문서화)
4. `docs/sprints/sprint-16.md` 에 Stage 5 완료 기록
5. 커밋 — 다른 세션의 미완성 마이그레이션 커밋들(`fa9ae36`~`04219a0`) 위에 얹는
   대규모 후속 작업이라는 맥락을 커밋 메시지에 분명히 할 것. **`s10_smoke.py` 가 실제로
   공유 Postgres 를 오염시켰던 사고와 재발 방지책(자식 프로세스엔 `MAINTQ_DB` 가 아니라
   `DATABASE_URL` 격리 스키마 DSN)은 커밋 메시지나 D-결정에 남겨 재발을 막을 것**
6. `bundle_integrity.py` 포팅(위 "남은 것" 참고) — 별도 세션/스프린트로 분리 고려

## 실행 방법 메모

- Postgres 기동: `docker compose up -d postgres`
- 타겟 전환: `export DATABASE_URL="postgresql://postgres:postgres@localhost:5434/maintq"`
- 격리 스키마 잔여 확인(**매 스파이크 수정 후 확인 습관화**):
  `docker exec maintq_postgres psql -U postgres -d maintq -c "SELECT nspname FROM
  pg_namespace WHERE nspname NOT IN ('public','pg_catalog','information_schema','pg_toast')
  AND nspname NOT LIKE 'pg_%';"`
- 잔여 스키마 있으면: `docker exec maintq_postgres psql -U postgres -d maintq -c
  'DROP SCHEMA IF EXISTS "<이름>" CASCADE;'` 후 `data/seed.py --with-error-codes` 재실행
- **서브프로세스(uvicorn·MCP stdio) 를 띄우는 스파이크는 `MAINTQ_DB` 가 아니라
  `DATABASE_URL` 을 자식 env 에 격리 스키마 DSN 으로 주입해야 한다** — 안 그러면 조용히
  공유 `public` 스키마를 오염시킨다(`s10_smoke.py` 실사고, 위 3번 항목).
