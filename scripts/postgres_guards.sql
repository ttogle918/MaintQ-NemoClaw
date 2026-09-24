-- D10 가드 — MCP 쓰기 도구 3종은 po_drafts / decisions / repair_records 에
-- draft INSERT 만 할 수 있다. UPDATE/DELETE 는 사람 전용 API(backend/routers/*)만.
--
-- SQLite 버전은 커넥션마다 CREATE TEMP TRIGGER 로 세션 범위 트리거를 만들어 이를 강제했다.
-- Postgres 는 세션(TEMP) 트리거가 없다 — 트리거는 테이블에 영구히 붙는 객체다.
-- 그래서 여기서는 트리거를 테이블에 영구히 붙이되, 세션 GUC(maintq.mcp_write_guard)로
-- "이 커넥션이 MCP 쓰기 도구 커넥션인가"를 판별한다. mcp_server/db.py 의
-- draft_writer()/decision_writer()/repair_writer() 만 이 GUC 를 'on' 으로 설정하고,
-- backend/db.py 커넥션(사람 API)은 절대 설정하지 않으므로 기존 UPDATE 경로는 그대로 동작한다.
--
-- 이 파일은 scripts/postgres_schema.sql 적용 뒤 한 번 실행한다(스키마 자체가 아니라
-- MCP 프로세스 분리 규약(D15)에 속하는 부속물이라 convert_ddl.py 생성 대상에서 분리했다).

CREATE OR REPLACE FUNCTION mcp_block_write() RETURNS trigger AS $$
BEGIN
    IF current_setting('maintq.mcp_write_guard', true) = 'on' THEN
        RAISE EXCEPTION 'MCP 도구는 % 를 수정/삭제할 수 없습니다 (D10, op=%)', TG_ARGV[0], TG_OP;
    END IF;
    -- 가드가 꺼져 있으면(backend/db.py 의 사람 API 커넥션) 정상 진행시켜야 한다.
    -- BEFORE 트리거가 NULL 을 반환하면 그 행의 연산 자체가 조용히 취소되므로,
    -- UPDATE 는 NEW 를, DELETE 는 OLD 를 그대로 돌려줘야 한다 — 여기서 NULL 을
    -- 반환하면 가드가 꺼져 있어도 모든 UPDATE/DELETE 가 0행으로 조용히 무력화된다.
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS mcp_no_po_write ON po_drafts;
CREATE TRIGGER mcp_no_po_write
    BEFORE UPDATE OR DELETE ON po_drafts
    FOR EACH ROW EXECUTE FUNCTION mcp_block_write('po_drafts');

DROP TRIGGER IF EXISTS mcp_no_decision_write ON decisions;
CREATE TRIGGER mcp_no_decision_write
    BEFORE UPDATE OR DELETE ON decisions
    FOR EACH ROW EXECUTE FUNCTION mcp_block_write('decisions');

DROP TRIGGER IF EXISTS mcp_no_repair_write ON repair_records;
CREATE TRIGGER mcp_no_repair_write
    BEFORE UPDATE OR DELETE ON repair_records
    FOR EACH ROW EXECUTE FUNCTION mcp_block_write('repair_records');

-- ─────────────────────────────────────────────────────────────────────────
-- 온보딩 전용 DB 역할 (D154, Sprint 19 MQ-1905) — 쓰기 도구 4번째 `stage_code_normalization`
-- 전용. 스테이징 4테이블(onboarding_batches/onboarding_code_rows/onboarding_normalizations/
-- onboarding_safety_candidates)에만 INSERT/SELECT 를 GRANT 받는다 — 그 밖은 GRANT 자체가
-- 없어 기본 거부(정본 error_codes·manual_chunks·po_drafts·users·onboarding_promotions 는
-- 이 역할로 손댈 수 없다). 역할 자체는 클러스터 전역이라 여러 격리 스키마가 동시에
-- 이 파일을 실행할 수 있다(스파이크 병렬) — CREATE ROLE 경합을 duplicate_object 예외로
-- 삼킨다(IF NOT EXISTS 로 먼저 보는 것은 check-then-act 라 원자적이지 않다).
DO $$ BEGIN
  BEGIN
    CREATE ROLE maintq_onboarding NOLOGIN;
  EXCEPTION WHEN duplicate_object THEN
    NULL;
  END;
  EXECUTE format('GRANT maintq_onboarding TO %I', current_user);          -- 비-superuser 접속자도 SET ROLE 가능
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO maintq_onboarding', current_schema());
END $$;

GRANT SELECT, INSERT ON onboarding_batches, onboarding_code_rows,
                       onboarding_normalizations, onboarding_safety_candidates TO maintq_onboarding;
GRANT USAGE ON SEQUENCE onboarding_batches_batch_id_seq, onboarding_code_rows_row_id_seq,
                        onboarding_normalizations_norm_id_seq, onboarding_safety_candidates_cand_id_seq TO maintq_onboarding;

-- 스테이징 4테이블에도 기존 D10 트리거(mcp_block_write)를 UPDATE/DELETE 로 건다
-- (역할 거부 위의 이중 잠금 — 역할 GRANT 를 실수로 넓혀도 이 트리거가 막는다).
DROP TRIGGER IF EXISTS mcp_no_onb_batches_write ON onboarding_batches;
CREATE TRIGGER mcp_no_onb_batches_write
    BEFORE UPDATE OR DELETE ON onboarding_batches
    FOR EACH ROW EXECUTE FUNCTION mcp_block_write('onboarding_batches');

DROP TRIGGER IF EXISTS mcp_no_onb_rows_write ON onboarding_code_rows;
CREATE TRIGGER mcp_no_onb_rows_write
    BEFORE UPDATE OR DELETE ON onboarding_code_rows
    FOR EACH ROW EXECUTE FUNCTION mcp_block_write('onboarding_code_rows');

DROP TRIGGER IF EXISTS mcp_no_onb_norms_write ON onboarding_normalizations;
CREATE TRIGGER mcp_no_onb_norms_write
    BEFORE UPDATE OR DELETE ON onboarding_normalizations
    FOR EACH ROW EXECUTE FUNCTION mcp_block_write('onboarding_normalizations');

DROP TRIGGER IF EXISTS mcp_no_onb_safety_write ON onboarding_safety_candidates;
CREATE TRIGGER mcp_no_onb_safety_write
    BEFORE UPDATE OR DELETE ON onboarding_safety_candidates
    FOR EACH ROW EXECUTE FUNCTION mcp_block_write('onboarding_safety_candidates');
