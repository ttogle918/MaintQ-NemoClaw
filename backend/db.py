# -*- coding: utf-8 -*-
"""백엔드 DB 접근.

`mcp_server/db.py` 와 코드를 공유하지 않는다 — 두 프로세스는 분리돼 있고(D15)
같은 SQLite 파일만 공유한다. 백엔드는 사람 쪽 코드라 `po_drafts` 상태 전이 권한이 있다
(D10 은 MCP 도구만 제약).
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "maintq.db"
DB_PATH = Path(os.environ.get("MAINTQ_DB") or _DEFAULT_DB)


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(db_path or DB_PATH)
    con.execute("PRAGMA foreign_keys=ON")
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
