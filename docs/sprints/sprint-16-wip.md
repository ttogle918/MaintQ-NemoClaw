# Sprint 16 WIP — MQ-1614 (Stage 5, 마지막 태스크)
**저장 시각**: 2026-08-23 (세션 진행 중 — 대규모 Postgres 마이그레이션 완성 작업, 3차 체크포인트)
**상태**: 32/33 스파이크(공식 목록 정정 반영) 실 Postgres 위에서 검증 완료. 남은 1개
(`bundle_integrity`)는 사용자 승인으로 이번 세션 스코프에서 명시적으로 skip.

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
- pytest 3파일 — **83/83 PASS**
- spikes **32/33 PASS**(공식 목록에 `a2a_partner_tools_contract` 반영 후):
  `a2a_identity_contract`(19) · `a2a_partner_tools_contract`(22) · `agent_loop_contract`(35) · `api_contract`(41) ·
  `approvals_contract`(26) · `asset_tools_contract`(49) · `citation_render` ·
  `db_concurrency`(7, 재설계) · `deadline_risk_contract`(18) · `disposal_api_contract`(26) ·
  `disposal_sign_contract`(26) · `eval_replay_guard` · `eval_score_contract` ·
  `external_store_contract` · `ie5_extract_contract` · `law_fetch_contract` ·
  `llm_provider_contract` · `lookup_contract`(14) · `mcp_client_contract`(15) ·
  `ownership_api_contract` · `prompt_rules` · `rag_contract` · `repair_flow_contract`(19) ·
  `rules_db_load`(25) · `s10_smoke`(17, DB 오염 발견·수정) · `s4_smoke`(10) ·
  `sp2_mcp_roundtrip`(20) · `sp3_sse_events` · `tools_profile_contract` ·
  `trace_persist`(17) · `ui_honesty_contract` · `write_tool_contract`(30)

## 남은 것 — 1개, 사용자 승인으로 이번 세션 skip

- **`bundle_integrity.py`** — 스코프가 다른 스파이크보다 훨씬 크다: 30개 검사,
  `sqlite3.connect()` 가 전역에 흩어져 있고 픽스처 DB 변형이 7종(`all_fetched`·
  `all_pending`·`contract_only`·`rule_drift`·`asset_modified`·`asset_gone`·
  `cita_pending`) — 각각 자기 격리 스키마가 필요해 기계적 패턴 적용이 아니라 사실상
  재작성 규모. 사용자에게 확인 후("데이터 SQL 은 이미 다 변환됐다는 전제 맞나" →
  맞음, 이 스파이크의 gap 은 앱 스키마/마이그레이션이 아니라 **이 테스트 파일 자체의
  픽스처 코드**가 아직 sqlite3 를 직접 쓴다는 것뿐) skip 승인받음. 다음 세션 착수 시:
  `data/pg_isolation.create_isolated_schema(..., clone_data=True)` 를 픽스처 변형 수만큼
  호출(또는 하나의 베이스 스키마 위에서 시나리오별로 UPDATE/DELETE 후 롤백하는 방식으로
  스키마 생성 오버헤드를 줄이는 대안도 검토), `REAL_DB = mcp_db.DB_PATH` 전제(Postgres 는
  None) 부터 걷어내야 한다.

## 참고 — 스코프 밖 발견 (이번 세션에서 조치 안 함, 별도 확인 필요)

`ls spikes/*.py` 가 **37개**를 반환한다. 그중 `a2a_partner_tools_contract.py`(22건)는
Sprint 16 Stage 4(MQ-1613, 다른 세션이 이 세션 착수 전 이미 커밋·push)가 만든 정식 스위트인데
CLAUDE.md 목록 반영이 누락돼 있었다 — 실행해 보니 Postgres 위에서도 무수정 22/22 PASS(구독
subprocess 는 `list_tools()` 등록만 확인, DB 쓰기가 없어 안전)이라 이번 세션에서 CLAUDE.md
공식 목록·건수에 반영 완료(32→33스위트). 나머지 4개는 여전히 미확인·미반영 상태로 남는다:
`a2a_e2e_integration_spike.py`·`a2a_outbound_contract.py`·`demo_recommendation_1_and_2.py`·
`test_elice_stream.py` — 이름으로 미루어 실험/데모 스크립트로 보이나 실측하지 않았다.

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
