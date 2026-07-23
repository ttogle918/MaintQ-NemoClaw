# -*- coding: utf-8 -*-
"""발주 관련 백엔드 서비스 — 신원 stamp 와 상태 전이.

**신원이 도구 파라미터가 아닌 이유 (D23·D37).**
MCP 도구 스키마에 `requested_by` 가 있으면 LLM 이 그 값을 채울 수 있다 = 위조 경로다.
그래서 도구는 신원 없이 INSERT 하고, 백엔드가 같은 요청 안에서 X-User 헤더 값으로 stamp 한다.
백엔드는 사람 쪽 코드라 UPDATE 권한이 있어도 되고(D10 은 MCP 도구만 제약), LLM 은
이 경로에 개입할 수 없다.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from mcp_server.db import DB_PATH

# 표시명 매핑 — 헤더·DB 에는 ASCII ID 만 오간다 (D36)
USER_NAMES: dict[str, str] = {
    "tech-01": "김OO",
    "tech-02": "이OO",
    "mgr-01": "박OO",
}


def display_name(user_id: str | None) -> str:
    return USER_NAMES.get(user_id or "", user_id or "")


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(db_path or DB_PATH)
    con.execute("PRAGMA foreign_keys=ON")
    con.row_factory = sqlite3.Row
    return con


def stamp_identity(
    po_id: str,
    requested_by: str,
    session_id: str | None = None,
    db_path: Path | None = None,
) -> bool:
    """도구가 만든 draft 에 신원·세션을 새긴다.

    draft 상태에서만, 그리고 아직 비어 있을 때만 채운다 —
    이미 stamp 된 발주의 요청자를 나중에 바꿀 수 있으면 감사 추적이 무너진다.
    """
    con = _connect(db_path)
    try:
        cur = con.execute(
            "UPDATE po_drafts SET requested_by = ?, session_id = ?"
            " WHERE po_id = ? AND state = 'draft' AND requested_by IS NULL",
            (requested_by, session_id, po_id),
        )
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()
