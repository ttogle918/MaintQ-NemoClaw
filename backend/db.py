# -*- coding: utf-8 -*-
"""백엔드 DB 접근 계층 — Postgres 버전.

프로세스 분리 유지: backend/db 와 mcp_server/db 는 코드를 공유하지 않는다 (D15).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg import sql

# Postgres 연결 문자열 (환경변수에서)
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://localhost/maintq"  # 로컬 개발 기본값
)

logger = logging.getLogger(__name__)


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """Postgres 연결 컨텍스트 매니저.

    기존 SQLite 인터페이스를 유지하되, 드라이버만 교체.
    자동 커밋 비활성화 — 명시적 commit/rollback 필수.
    """
    con = None
    try:
        con = psycopg.connect(DATABASE_URL)
        # 외래키 제약 활성화 (Postgres는 기본이지만 명시)
        con.execute("SET session_replication_role = DEFAULT")
        yield con
        con.commit()
    except psycopg.Error as exc:
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
