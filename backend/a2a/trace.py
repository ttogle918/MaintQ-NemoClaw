# -*- coding: utf-8 -*-
"""MaintQ A2A 호출 추적(Trace) 기록 유틸리티.

A2A 호출부에서 나가는 요청(tool_call)과 들어오는 응답(tool_result)을
traces 테이블에 session_id, seq, request_chain_id와 함께 불변 기록한다.

⛔ Authorization 헤더 등 비밀정보는 tool_payload에 절대 포함하지 않는다.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.db import connect

logger = logging.getLogger(__name__)


def record_a2a_trace(
    session_id: str,
    skill_id: str,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any] | None,
    request_chain_id: str,
    status: str = "ok",
    db_path: Path | str | None = None,
) -> None:
    """traces 테이블에 A2A tool_call 및 tool_result 쌍을 저장한다."""
    if not session_id:
        session_id = f"a2a-sess-{request_chain_id[-8:]}"

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    call_payload_json = json.dumps(
        {
            "tool": f"a2a_{skill_id.replace('-', '_')}",
            "input": request_payload,
            "ts": now_iso,
        },
        ensure_ascii=False,
    )

    result_payload_json = json.dumps(
        {
            "tool": f"a2a_{skill_id.replace('-', '_')}",
            "status": status,
            "summary": f"A2A {skill_id} {status}",
            "elapsed": 0.1,
            "ts": now_iso,
        },
        ensure_ascii=False,
    )

    raw_response_json = (
        json.dumps(response_payload, ensure_ascii=False) if response_payload is not None else None
    )

    with connect(Path(db_path) if db_path else None) as con:
        # Get next seq
        r = con.execute("SELECT COALESCE(MAX(seq), 0) FROM traces WHERE session_id = ?", (session_id,)).fetchone()
        next_seq = (r[0] if r else 0) + 1

        # 1. tool_call insert
        con.execute(
            "INSERT INTO traces (session_id, seq, event_type, tool, payload, request_chain_id)"
            " VALUES (?, ?, 'tool_call', ?, ?, ?)",
            (session_id, next_seq, f"a2a_{skill_id.replace('-', '_')}", call_payload_json, request_chain_id),
        )

        # 2. tool_result insert
        con.execute(
            "INSERT INTO traces (session_id, seq, event_type, tool, payload, tool_payload, request_chain_id)"
            " VALUES (?, ?, 'tool_result', ?, ?, ?, ?)",
            (
                session_id,
                next_seq + 1,
                f"a2a_{skill_id.replace('-', '_')}",
                result_payload_json,
                raw_response_json,
                request_chain_id,
            ),
        )
