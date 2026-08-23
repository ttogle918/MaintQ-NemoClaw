# -*- coding: utf-8 -*-
"""백엔드 DB 접근 계층 — Postgres 버전.

프로세스 분리 유지: backend/db 와 mcp_server/db 는 코드를 공유하지 않는다 (D15).
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg import sql

from data.dbcompat import CompatCursor, sqlite_row_factory

# Postgres 연결 문자열 (환경변수에서)
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://localhost/maintq"  # 로컬 개발 기본값
)

# SQLite 호환 스텁 (Postgres는 이것들을 사용하지 않지만 기존 코드 호환성을 위해 유지)
BUSY_TIMEOUT_MS = 5000  # SQLite 타임아웃 설정
DB_PATH = Path(os.environ.get("MAINTQ_DB", "data/maintq.db"))  # SQLite 경로 (호환용)

logger = logging.getLogger(__name__)


@contextmanager
def connect(db_path: Path | str | None = None) -> Iterator[psycopg.Connection]:
    """Postgres 연결 컨텍스트 매니저.

    기존 SQLite 인터페이스를 유지하되, 드라이버만 교체.
    자동 커밋 비활성화 — 명시적 commit/rollback 필수.

    Args:
        db_path: SQLite 경로면 Postgres 에서는 무시한다(DATABASE_URL 이 우선).
                 **Postgres DSN 문자열**이면 이게 최우선이다 — `backend/agent/trace.py`
                 의 `TraceWriter(db_path=...)`처럼 호출부가 이미 명시적으로 대상을
                 지정하는 자리이므로, 굳이 `backend.db.DB_PATH` 전역까지 갈아끼우게
                 하지 않아도 격리 스키마(data/pg_isolation.py)로 곧장 간다.
                 명시 인자가 없으면 `backend.db.DB_PATH`(회귀가 전역으로 갈아끼운 경우)
                 → `DATABASE_URL` 순으로 본다. `DB_PATH` 를 **호출 시점에** 읽는 이유는
                 backend/services/disposal.py·ownership.py 의 기존 관행과 같다: 모듈
                 임포트 시점 값으로 고정하면 회귀가 갈아끼워도 반영되지 않는다.
    """
    con = None
    try:
        target = DATABASE_URL
        if isinstance(DB_PATH, str) and DB_PATH.startswith("postgresql://"):
            target = DB_PATH
        if isinstance(db_path, str) and db_path.startswith("postgresql://"):
            target = db_path
        # row_factory: backend/services/* 다수가 sqlite3.Row 관행(row["col"]) 을 그대로 쓴다 —
        # psycopg 기본 tuple_row 로는 그 접근이 깨진다 (Sprint 16 MQ-1614 에서 발견).
        con = psycopg.connect(target, row_factory=sqlite_row_factory, cursor_factory=CompatCursor)
        # 외래키 제약 활성화 (Postgres는 기본이지만 명시)
        con.execute("SET session_replication_role = DEFAULT")
        yield con
        con.commit()
    except (psycopg.Error, sqlite3.Error) as exc:
        if con:
            con.rollback()
        logger.error(f"DB 연결 오류: {exc}")
        raise
    finally:
        if con:
            con.close()


def rows_to_dicts(rows: list) -> list[dict]:
    """Postgres 결과 행을 dict로 변환 (기존 호환)."""
    if not rows:
        return []

    # psycopg 3.x는 RealDictCursor 사용으로 자동 dict 변환
    # 또는 수동:
    return [dict(row) for row in rows]
