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
exec /app/.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
