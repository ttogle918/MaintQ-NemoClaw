#!/usr/bin/env bash
# 로컬 Postgres(maintq_postgres 컨테이너)의 public 스키마를 **통째로** Supabase 로 옮긴다 — D159.
#
# 왜 재시드가 아니라 덤프인가: seed.py 는 HV600 승격·안전 문구 승인·LLM 정규화(약 43분)를
# 복구하지 못한다(CLAUDE.md 「회귀 스위트」 H9). 데모 상태를 그대로 가져가려면 덤프뿐이다.
#
# 사용:
#   SUPABASE_DATABASE_URL='postgresql://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require' \
#   deploy/cloudrun/db_to_supabase.sh
#
# - 대상 public 에 테이블이 이미 있으면 멈춘다(덮어쓰기 금지 — 지우려면 사람이 직접).
# - 소유자·권한은 덤프에서 뺀다(--no-owner --no-privileges). 로컬 역할이 Supabase 에 없기 때문이다.
#   대신 scripts/postgres_guards.sql 을 다시 적용해 D10 트리거·D154 온보딩 역할 GRANT 를 복원한다.
# - spikes 격리 스키마(eval_*·a2a_test_* 등)는 -n public 으로 제외된다.
set -euo pipefail

cd "$(dirname "$0")/../.."
: "${SUPABASE_DATABASE_URL:?Supabase Session pooler 연결 문자열이 필요합니다}"
SRC_CONTAINER="${SRC_CONTAINER:-maintq_postgres}"
PG_IMAGE="${PG_IMAGE:-postgres:17}"

psql_remote() { docker run --rm -i "$PG_IMAGE" psql "$SUPABASE_DATABASE_URL" -v ON_ERROR_STOP=1 -X "$@"; }

existing="$(psql_remote -Atc "select count(*) from pg_tables where schemaname='public'")"
if [ "$existing" != "0" ]; then
  echo "✗ 대상 public 에 테이블이 이미 ${existing}개 있습니다 — 덮어쓰지 않습니다." >&2
  exit 1
fi

echo "▶ pgvector 확장 (public — 로컬 덤프가 public.vector 타입을 참조한다)"
psql_remote -c "create extension if not exists vector with schema public;"

echo "▶ 덤프 → 적재"
docker exec "$SRC_CONTAINER" pg_dump -U postgres -d maintq -n public --no-owner --no-privileges \
  | grep -v '^CREATE SCHEMA public;$' \
  | grep -v '^COMMENT ON SCHEMA public ' \
  | psql_remote -q

echo "▶ D10 가드·D154 온보딩 역할 재적용"
psql_remote -q < scripts/postgres_guards.sql

echo "▶ Supabase Data API 차단 — anon/authenticated 권한 회수"
# Supabase 는 public 을 REST(PostgREST)로 자동 노출하고, 기본 권한으로 새 테이블에 anon·authenticated
# GRANT 가 붙는다(이관 직후 실측 462건). MaintQ 는 REST 를 쓰지 않는다 — 백엔드는 postgres 로 직결한다.
# 회수하지 않으면 공개 anon 키만으로 po_drafts 등을 직접 읽고 쓸 수 있어 D10·D159 가 통째로 우회된다.
psql_remote -q <<'SQL'
-- pgvector 함수는 supabase_admin 소유라 「no privileges could be revoked」 WARNING 이 100여 줄 난다(무해)
set client_min_messages = error;
revoke all on all tables    in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke all on all functions in schema public from anon, authenticated;
alter default privileges in schema public revoke all on tables    from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke all on functions from anon, authenticated;
SQL

echo "▶ 검증"
psql_remote -Atc "select 'tables', count(*) from pg_tables where schemaname='public'
  union all select 'error_codes', count(*) from public.error_codes
  union all select 'manual_chunks', count(*) from public.manual_chunks
  union all select 'po_drafts', count(*) from public.po_drafts
  union all select 'guard_triggers', count(*) from pg_trigger where tgname like 'mcp_no_%'"
echo "  로컬 대조: docker exec $SRC_CONTAINER psql -U postgres -d maintq -Atc \"select count(*) from error_codes\""
