# -*- coding: utf-8 -*-
"""MCP 도구용 DB 접근 계층 — 읽기 전용 / draft INSERT 전용을 분리한다 (D10).

절대 규칙: MCP 도구는 `po_drafts` 에 **draft INSERT만** 가능하다.
상태 전이(draft→pending→approved/rejected)는 backend/routers/po.py 의 사람 전용 API 만.
그래서 커넥션을 두 개로 나눈다 — 읽기용은 SQLite URI 의 `mode=ro` 로 물리적으로 막는다.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "maintq.db"

# 계약 테스트가 실제 DB를 오염시키지 않도록 경로를 갈아끼울 수 있게 한다
DB_PATH = Path(os.environ.get("MAINTQ_DB") or _DEFAULT_DB)


def _configure(con: sqlite3.Connection) -> sqlite3.Connection:
    # 기본 OFF — 안 켜면 po_drafts 의 (model, error_code) FK 검증이 조용히 사라진다 (D33)
    con.execute("PRAGMA foreign_keys=ON")
    con.row_factory = sqlite3.Row
    return con


@contextmanager
def read_only() -> Iterator[sqlite3.Connection]:
    """읽기 전용 커넥션. 쓰기를 시도하면 sqlite 가 거부한다."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"목업 DB가 없습니다: {DB_PATH} — data/seed.py 를 먼저 실행하세요")
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    try:
        yield _configure(con)
    finally:
        con.close()


@contextmanager
def draft_writer() -> Iterator[sqlite3.Connection]:
    """`po_drafts` 에 draft 한 건을 INSERT 하기 위한 커넥션.

    UPDATE/DELETE 를 막는 건 코드 규율만으로는 부족해서, 세션 수준 트리거로
    한 번 더 잠근다 — 도구 코드가 실수로 UPDATE 를 시도하면 즉시 예외가 난다.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"목업 DB가 없습니다: {DB_PATH} — data/seed.py 를 먼저 실행하세요")
    con = sqlite3.connect(DB_PATH)
    _configure(con)
    con.executescript(
        """
        CREATE TEMP TRIGGER IF NOT EXISTS mcp_no_po_update
        BEFORE UPDATE ON po_drafts
        BEGIN SELECT raise(ABORT, 'MCP 도구는 po_drafts 를 수정할 수 없습니다 (D10)'); END;

        CREATE TEMP TRIGGER IF NOT EXISTS mcp_no_po_delete
        BEFORE DELETE ON po_drafts
        BEGIN SELECT raise(ABORT, 'MCP 도구는 po_drafts 를 삭제할 수 없습니다 (D10)'); END;
        """
    )
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]
