# -*- coding: utf-8 -*-
"""backend/a2a/trace.py 테스트.

traces 테이블에 tool_call/tool_result 쌍이 session_id·seq·request_chain_id 와 함께
불변 기록되는지, 그리고 비밀정보(Authorization 등)가 payload 에 섞이지 않는지를 고정한다.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from backend.a2a.trace import record_a2a_trace


def _rows(db_path: Path, session_id: str) -> list[sqlite3.Row]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM traces WHERE session_id = ? ORDER BY seq", (session_id,)
    ).fetchall()
    con.close()
    return rows


def test_records_tool_call_and_tool_result_pair(db_path: Path):
    record_a2a_trace(
        session_id="sess-01",
        skill_id="request-withdrawal",
        request_payload={"amount": 1000},
        response_payload={"status": "input-required"},
        request_chain_id="CHAIN-001",
        db_path=db_path,
    )

    rows = _rows(db_path, "sess-01")
    assert [r["event_type"] for r in rows] == ["tool_call", "tool_result"]
    assert [r["seq"] for r in rows] == [1, 2]
    assert all(r["tool"] == "a2a_request_withdrawal" for r in rows)
    assert all(r["request_chain_id"] == "CHAIN-001" for r in rows)


def test_tool_call_payload_contains_request_input(db_path: Path):
    record_a2a_trace(
        session_id="sess-01",
        skill_id="lookup-clause",
        request_payload={"question": "화재 특약 보장 범위는?"},
        response_payload={"answer": "..."},
        request_chain_id="CHAIN-002",
        db_path=db_path,
    )
    call_row = _rows(db_path, "sess-01")[0]
    payload = json.loads(call_row["payload"])
    assert payload["tool"] == "a2a_lookup_clause"
    assert payload["input"] == {"question": "화재 특약 보장 범위는?"}


def test_tool_result_records_status_in_summary(db_path: Path):
    record_a2a_trace(
        session_id="sess-01",
        skill_id="request-withdrawal",
        request_payload={},
        response_payload={"error": "timed out"},
        request_chain_id="CHAIN-003",
        status="timeout",
        db_path=db_path,
    )
    result_row = _rows(db_path, "sess-01")[1]
    payload = json.loads(result_row["payload"])
    assert payload["status"] == "timeout"
    assert "timeout" in payload["summary"]


def test_response_payload_none_leaves_tool_payload_null(db_path: Path):
    record_a2a_trace(
        session_id="sess-01",
        skill_id="request-withdrawal",
        request_payload={},
        response_payload=None,
        request_chain_id="CHAIN-004",
        status="error",
        db_path=db_path,
    )
    result_row = _rows(db_path, "sess-01")[1]
    assert result_row["tool_payload"] is None


def test_response_payload_stored_as_raw_json_in_tool_payload(db_path: Path):
    record_a2a_trace(
        session_id="sess-01",
        skill_id="request-withdrawal",
        request_payload={},
        response_payload={"status": "completed", "req_id": "3"},
        request_chain_id="CHAIN-005",
        db_path=db_path,
    )
    result_row = _rows(db_path, "sess-01")[1]
    assert json.loads(result_row["tool_payload"]) == {"status": "completed", "req_id": "3"}


def test_seq_increments_across_multiple_calls_in_same_session(db_path: Path):
    record_a2a_trace(
        session_id="sess-01",
        skill_id="lookup-clause",
        request_payload={},
        response_payload={},
        request_chain_id="CHAIN-006",
        db_path=db_path,
    )
    record_a2a_trace(
        session_id="sess-01",
        skill_id="request-withdrawal",
        request_payload={},
        response_payload={},
        request_chain_id="CHAIN-007",
        db_path=db_path,
    )
    rows = _rows(db_path, "sess-01")
    assert [r["seq"] for r in rows] == [1, 2, 3, 4]


def test_missing_session_id_falls_back_to_chain_suffix(db_path: Path):
    record_a2a_trace(
        session_id="",
        skill_id="lookup-clause",
        request_payload={},
        response_payload={},
        request_chain_id="CHAIN-abcdefgh",
        db_path=db_path,
    )
    rows = _rows(db_path, "a2a-sess-abcdefgh")
    assert len(rows) == 2


def test_never_embeds_authorization_header_in_payload(db_path: Path):
    """호출부가 실수로 헤더를 payload 에 섞어 넘겨도, 이 함수 자체는 별도 필드를 추가하지
    않는다는 계약 확인 — payload 는 호출부가 넘긴 request_payload 를 그대로 담는다."""
    request_payload = {"amount": 1000}  # Authorization은 client.py가 헤더로만 보내고 payload엔 안 넣는다
    record_a2a_trace(
        session_id="sess-01",
        skill_id="request-withdrawal",
        request_payload=request_payload,
        response_payload={},
        request_chain_id="CHAIN-008",
        db_path=db_path,
    )
    call_row = _rows(db_path, "sess-01")[0]
    payload = json.loads(call_row["payload"])
    assert "Authorization" not in json.dumps(payload)
