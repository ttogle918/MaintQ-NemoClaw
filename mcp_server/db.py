# -*- coding: utf-8 -*-
"""MCP 도구용 DB 접근 계층 — Postgres 버전.

읽기 전용 / draft INSERT 전용 분리 (D10).
Postgres는 TEMP TRIGGER를 지원하므로 기존 로직 유지.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

import sqlite3
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import psycopg

from data.dbcompat import CompatCursor, sqlite_row_factory

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://localhost/maintq"
)

# SQLite 시절의 "mcp_server.db.DB_PATH 를 갈아끼워 임시 사본에 물린다" 회귀 관행과의
# 호환 자리 (backend/db.py 의 같은 이름 스텁과 짝). 기본값 None = 미override.
# `data/pg_isolation.py` 로 만든 격리 스키마 DSN 문자열을 넣으면 그 커넥션들만 그리로 간다.
DB_PATH: str | None = None

logger = logging.getLogger(__name__)


def _target_url() -> str:
    """호출 시점의 DB_PATH override 를 반영한 접속 대상. `read_only()`/`_guarded_writer()`
    가 매 커넥션마다 다시 읽는다 — 모듈 임포트 시점 값으로 고정하면 회귀가 DB_PATH 를
    나중에 갈아끼워도 반영되지 않는다."""
    if isinstance(DB_PATH, str) and DB_PATH.startswith("postgresql://"):
        return DB_PATH
    return DATABASE_URL


def _readonly_url() -> str:
    """`_target_url()` 에 `default_transaction_read_only=on` 을 **더한다**(덮어쓰지 않는다).

    DSN 이 이미 `options=-c search_path=...` 를 갖고 있을 수 있다(격리 스키마,
    data/pg_isolation.py) — `psycopg.connect(dsn, options="...")` 처럼 별도 키워드
    인자로 넘기면 conninfo 문자열의 기존 `options` 를 통째로 덮어써서 search_path 가
    조용히 사라지고 커넥션이 격리 스키마 대신 public 을 본다(Sprint 16 MQ-1614 로 발견 —
    lookup_error_code 류가 격리 스키마의 픽스처가 아니라 실 데이터를 돌려줬다).
    그래서 옵션을 DSN 문자열 안에서 **합친다**.
    """
    url = _target_url()
    parts = urlsplit(url)
    q = dict(parse_qsl(parts.query))
    existing = q.get("options", "")
    extra = "-c default_transaction_read_only=on"
    q["options"] = f"{existing} {extra}".strip() if existing else extra
    query = urlencode(q, quote_via=quote)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _configure(con: psycopg.Connection) -> psycopg.Connection:
    """기본 설정 (외래키 등)."""
    con.execute("SET session_replication_role = DEFAULT")
    return con


@contextmanager
def read_only() -> Iterator[psycopg.Connection]:
    """읽기 전용 커넥션.

    SQLite 버전은 `file:...?mode=ro` URI 로 **물리적으로** 강제했다. Postgres 에는
    그 URI 트릭이 없지만, 세션의 기본 트랜잭션 모드를 read-only 로 고정하는 진짜
    서버측 강제가 있다 — 뒤에 오는 모든 INSERT/UPDATE/DELETE 는
    `psycopg.errors.ReadOnlySqlTransaction` 으로 거부된다(단순히 "SELECT 만 짜자"는
    애플리케이션 관행이 아니라 서버가 막는다). `SET TRANSACTION READ ONLY` 를 커넥션
    직후 statement 로 실행하는 방식은 SQL 표준상 "트랜잭션의 첫 statement여야 한다"는
    제약이 있어 `CompatCursor` 의 auto-SAVEPOINT 래핑(그 자체가 먼저 실행되는 statement)
    과 부딪혀 조용히 무시됐다(Sprint 16 MQ-1614 로 발견) — 그래서 접속 문자열의
    `options=-c default_transaction_read_only=on` 로 세션 시작 시점부터 고정한다.
    프로덕션은 여기에 더해 읽기 전용 역할(옵션 1)도 쓸 수 있다.
    """
    con = None
    try:
        con = psycopg.connect(
            _readonly_url(),
            row_factory=sqlite_row_factory,
            cursor_factory=CompatCursor,
        )
        yield _configure(con)
    except (psycopg.Error, sqlite3.Error) as exc:
        logger.error(f"읽기 연결 오류: {exc}")
        raise
    finally:
        if con:
            con.close()


# ── 쓰기 커넥션의 세션 잠금 (D10) ───────────────────────────────
# Postgres는 SQLite의 CREATE TEMP TRIGGER(세션 범위 트리거)를 지원하지 않는다 —
# 트리거는 테이블에 영구히 붙는 객체다. 대신 트리거 자체는 scripts/postgres_guards.sql 이
# 영구히 붙여두고, 이 커넥션이 "MCP 쓰기 도구 커넥션"인지는 세션 GUC 로 표시한다.
# read_only()·backend/db.py 커넥션은 이 GUC 를 절대 설정하지 않으므로 그쪽 UPDATE 는
# 영향받지 않는다.
# ⚠ SET LOCAL — 반드시 트랜잭션 범위여야 한다. Supabase 같은 PgBouncer 트랜잭션 풀링
# 환경에서는 커넥션(client 관점의 con.close())이 끝나도 물리적 백엔드가 즉시 다른
# 클라이언트에게 재사용될 수 있다 — 세션 범위 `SET`(LOCAL 없이)을 쓰면 이 GUC 가 그
# 다음 무관한 요청에 새어 들어가 D10 가드가 엉뚱하게 발동/미발동할 수 있다. `SET LOCAL`
# 은 COMMIT/ROLLBACK 시 자동 원복돼 풀링 모드와 무관하게 안전하다 — psycopg 커넥션은
# 기본이 autocommit=False 라 이 문장이 곧 트랜잭션의 첫 문장이 되고, 그 트랜잭션 안에서
# 실행되는 INSERT 까지 그대로 적용된 뒤 `con.commit()` 에서 정확히 사라진다.
_MCP_WRITE_GUARD_ON = "SET LOCAL maintq.mcp_write_guard = 'on'"


@contextmanager
def _guarded_writer() -> Iterator[psycopg.Connection]:
    """INSERT 전용 쓰기 커넥션 (scripts/postgres_guards.sql 의 영구 트리거 + 세션 GUC)."""
    con = None
    try:
        con = psycopg.connect(_target_url(), row_factory=sqlite_row_factory, cursor_factory=CompatCursor)
        _configure(con)
        con.execute(_MCP_WRITE_GUARD_ON)
        yield con
        con.commit()
    except (psycopg.Error, sqlite3.Error) as exc:
        if con:
            con.rollback()
        logger.error(f"쓰기 연결 오류: {exc}")
        raise
    finally:
        if con:
            con.close()


@contextmanager
def draft_writer() -> Iterator[psycopg.Connection]:
    """`po_drafts` 에 draft 한 건을 INSERT 하기 위한 커넥션."""
    with _guarded_writer() as con:
        yield con


@contextmanager
def decision_writer() -> Iterator[psycopg.Connection]:
    """`decisions` 에 draft 한 건을 INSERT 하기 위한 커넥션."""
    with _guarded_writer() as con:
        yield con


@contextmanager
def repair_writer() -> Iterator[psycopg.Connection]:
    """`repair_records` 에 draft 한 건을 INSERT 하기 위한 커넥션."""
    with _guarded_writer() as con:
        yield con


# ── 온보딩 스테이징 쓰기 커넥션 (D154) ───────────────────────────────
# 쓰기 도구 4번째 `stage_code_normalization` 전용. `_guarded_writer()` 와 같은
# 트랜잭션 규약(가드 GUC)에 전용 DB 역할(`SET LOCAL ROLE`)을 더한다 — GRANT 가 없는
# 모든 테이블(정본 error_codes·manual_chunks·po_drafts·users·onboarding_promotions 포함)은
# 권한 오류로 거부된다. 역할 자체는 scripts/postgres_guards.sql 이 스키마 적용 시 만든다.
_ONBOARDING_ROLE = "SET LOCAL ROLE maintq_onboarding"


@contextmanager
def onboarding_writer() -> Iterator[psycopg.Connection]:
    """스테이징 4테이블 INSERT 전용 (D154). `_guarded_writer()` 와 같은 트랜잭션 규약에
    `SET LOCAL ROLE` 을 더한다 — GRANT 가 없는 모든 테이블은 권한 오류로 거부된다."""
    with _guarded_writer() as con:
        con.execute(_ONBOARDING_ROLE)
        yield con


def rows_to_dicts(rows: list) -> list[dict]:
    """결과 행을 dict로 변환 (기존 호환)."""
    if not rows:
        return []
    return [dict(row) for row in rows]
