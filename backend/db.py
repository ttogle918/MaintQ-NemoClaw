# -*- coding: utf-8 -*-
"""백엔드 DB 접근.

`mcp_server/db.py` 와 코드를 공유하지 않는다 — 두 프로세스는 분리돼 있고(D15)
같은 SQLite 파일만 공유한다. 백엔드는 사람 쪽 코드라 `po_drafts` 상태 전이 권한이 있다
(D10 은 MCP 도구만 제약).
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "maintq.db"
DB_PATH = Path(os.environ.get("MAINTQ_DB") or _DEFAULT_DB)

# 백엔드(traces INSERT)와 MCP 서브프로세스(po_drafts INSERT)가 같은 파일에 동시에 쓴다.
# WAL 이 없으면 읽기와 쓰기가 서로를 막고, busy_timeout 이 없으면 잠김 즉시 예외다.
# 같은 두 줄이 mcp_server/db.py 에도 있다 — 공용 모듈로 빼지 않는다 (D15: 프로세스 분리 우선).
BUSY_TIMEOUT_MS = 5000

logger = logging.getLogger(__name__)


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(db_path or DB_PATH)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    try:
        # WAL 은 DB 파일에 영속되는 설정이라 커넥션마다 재설정해도 무해하다.
        con.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error as exc:  # 네트워크 FS 등에서 실패 가능 — 앱을 죽이지 않는다
        logger.warning("WAL 전환 실패, 기본 저널로 진행합니다: %s", exc)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
