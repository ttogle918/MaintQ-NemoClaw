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

import psycopg

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://localhost/maintq"
)

logger = logging.getLogger(__name__)


def _configure(con: psycopg.Connection) -> psycopg.Connection:
    """기본 설정 (외래키 등)."""
    con.execute("SET session_replication_role = DEFAULT")
    return con


@contextmanager
def read_only() -> Iterator[psycopg.Connection]:
    """읽기 전용 커넥션 (검증용).

    Postgres는 URI mode=ro가 없으므로:
    - 옵션 1: 읽기 전용 사용자로 연결 (운영 권장)
    - 옵션 2: 애플리케이션에서 SELECT만 실행하도록 강제 (검증용)

    현재는 옵션 2 구현 (로컬/테스트용).
    프로덕션은 읽기 전용 역할 사용.
    """
    con = None
    try:
        con = psycopg.connect(DATABASE_URL)
        yield _configure(con)
    except psycopg.Error as exc:
        logger.error(f"읽기 연결 오류: {exc}")
        raise
    finally:
        if con:
            con.close()


# ── 쓰기 커넥션의 세션 잠금 (D10) ───────────────────────────────
# Postgres TEMP TRIGGER는 기존 문법과 동일하게 작동한다.

_PO_GUARDS = """
CREATE TEMP TRIGGER mcp_no_po_update
BEFORE UPDATE ON po_drafts
FOR EACH ROW EXECUTE FUNCTION raise('abort', 'MCP 도구는 po_drafts 를 수정할 수 없습니다 (D10)');

CREATE TEMP TRIGGER mcp_no_po_delete
BEFORE DELETE ON po_drafts
FOR EACH ROW EXECUTE FUNCTION raise('abort', 'MCP 도구는 po_drafts 를 삭제할 수 없습니다 (D10)');
"""

_DECISION_GUARDS = """
CREATE TEMP TRIGGER mcp_no_decision_update
BEFORE UPDATE ON decisions
FOR EACH ROW EXECUTE FUNCTION raise('abort', 'MCP 도구는 decisions 를 수정할 수 없습니다 (D10)');

CREATE TEMP TRIGGER mcp_no_decision_delete
BEFORE DELETE ON decisions
FOR EACH ROW EXECUTE FUNCTION raise('abort', 'MCP 도구는 decisions 를 삭제할 수 없습니다 (D10)');
"""

_REPAIR_GUARDS = """
CREATE TEMP TRIGGER mcp_no_repair_update
BEFORE UPDATE ON repair_records
FOR EACH ROW EXECUTE FUNCTION raise('abort', 'MCP 도구는 repair_records 를 수정할 수 없습니다 (D10·D98)');

CREATE TEMP TRIGGER mcp_no_repair_delete
BEFORE DELETE ON repair_records
FOR EACH ROW EXECUTE FUNCTION raise('abort', 'MCP 도구는 repair_records 를 삭제할 수 없습니다 (D10·D98)');
"""


@contextmanager
def _guarded_writer(guards: str) -> Iterator[psycopg.Connection]:
    """INSERT 전용 쓰기 커넥션 (TEMP TRIGGER 활용)."""
    con = None
    try:
        con = psycopg.connect(DATABASE_URL)
        _configure(con)
        # TEMP TRIGGER 생성 (기존 로직 유지)
        con.execute(guards)
        yield con
        con.commit()
    except psycopg.Error as exc:
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
    with _guarded_writer(_PO_GUARDS) as con:
        yield con


@contextmanager
def decision_writer() -> Iterator[psycopg.Connection]:
    """`decisions` 에 draft 한 건을 INSERT 하기 위한 커넥션."""
    with _guarded_writer(_DECISION_GUARDS) as con:
        yield con


@contextmanager
def repair_writer() -> Iterator[psycopg.Connection]:
    """`repair_records` 에 draft 한 건을 INSERT 하기 위한 커넥션."""
    with _guarded_writer(_REPAIR_GUARDS) as con:
        yield con


def rows_to_dicts(rows: list) -> list[dict]:
    """결과 행을 dict로 변환 (기존 호환)."""
    if not rows:
        return []
    return [dict(row) for row in rows]
