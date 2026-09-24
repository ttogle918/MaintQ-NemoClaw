#!/bin/sh
# MaintQ 샌드박스 엔트리포인트 (방식 B, D143)
#
# 샌드박스 정책상 쓰기는 /tmp 뿐이라 빌드 때 만든 DB 템플릿(/app/pgdata-template, 읽기 전용)을
# /tmp/pgdata 로 복사해 uid 1000 으로 띄운다. Postgres 는 샌드박스 안 loopback 에만 바인드한다 —
# 샌드박스 밖으로 나가는 DB 트래픽이 없으므로 network_policies 에 DB 항목이 필요 없다.
#
# ⚠ 샌드박스는 매번 빌드 시점 DB 스냅샷에서 시작한다. 샌드박스 안에서 만든 draft 는
#   샌드박스를 지우면 사라진다(데모 격리 — 공유 DB 를 오염시키지 않는다).
set -eu

PGBIN=/usr/lib/postgresql/17/bin
PGDATA=/tmp/pgdata

if [ ! -f "$PGDATA/PG_VERSION" ]; then
    cp -a /app/pgdata-template "$PGDATA"
    chmod 700 "$PGDATA"
fi

# dynamic_shared_memory_type=mmap — 기본값 posix 는 /dev/shm 을 쓰는데 파일시스템 정책에 없다.
"$PGBIN/pg_ctl" -D "$PGDATA" -l /tmp/postgres.log -w start \
    -o "-c listen_addresses=127.0.0.1 -c port=5432 -c unix_socket_directories=/tmp -c dynamic_shared_memory_type=mmap"

cd /app

# MCP streamable-http 입구 (D150) — NemoClaw/OpenClaw 가 붙는 자리.
# MAINTQ_MCP_TOKEN 이 없으면 http_entry 가 **기동을 거부**하므로(D150 가드 ⓐ) 여기서도
# 띄우지 않는다. 토큰 없이 조용히 열린 입구가 생기지 않게 하려는 것이다.
# 바깥으로 나가는 길은 `openshell service expose` 하나뿐이다 — loopback 에만 바인드한다.
if [ -n "${MAINTQ_MCP_TOKEN:-}" ]; then
    MAINTQ_MCP_HTTP_PORT="${MAINTQ_MCP_HTTP_PORT:-8765}" \
        /app/.venv/bin/python -m mcp_server.http_entry >/tmp/mcp_http.log 2>&1 &
    echo "MCP http 입구 기동 (port ${MAINTQ_MCP_HTTP_PORT:-8765})"
else
    echo "MAINTQ_MCP_TOKEN 없음 — MCP http 입구를 열지 않는다 (D150)"
fi

exec /app/.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
