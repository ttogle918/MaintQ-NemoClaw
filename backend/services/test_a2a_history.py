# -*- coding: utf-8 -*-
"""backend/services/a2a_history.py (list_a2a_history) 테스트 (MQ-1602, D114).

`backend/a2a/trace.py::record_a2a_trace` 로 traces 에 tool_call/tool_result 쌍을 심어
`list_a2a_history` 가 그 쌍을 request_chain_id 로 정확히 묶어 돌려주는지 확인한다.
`backend/conftest.py::db_path` 픽스처(A2A 테스트 공용 최소 스키마)를 재사용한다.
"""

from __future__ import annotations


from data import dbcompat

from backend.a2a.trace import record_a2a_trace
from backend.services.a2a_history import list_a2a_history


def _seed(
    db_path: str,
    *,
    session_id: str = "sess-01",
    skill_id: str,
    request_payload: dict,
    response_payload: dict | None,
    request_chain_id: str,
    status: str = "ok",
) -> None:
    record_a2a_trace(
        session_id=session_id,
        skill_id=skill_id,
        request_payload=request_payload,
        response_payload=response_payload,
        request_chain_id=request_chain_id,
        status=status,
        db_path=db_path,
    )


# ---- (a) po_id 필터 -----------------------------------------------------------


def test_po_id_filter_matches_exactly(db_path: str):
    _seed(
        db_path,
        skill_id="request-withdrawal",
        request_payload={"po_id": "PO-777", "amount": 60000},
        response_payload={"status": "completed", "req_id": "3"},
        request_chain_id="CHAIN-PO-1",
    )
    _seed(
        db_path,
        skill_id="request-withdrawal",
        request_payload={"po_id": "PO-999", "amount": 10000},
        response_payload={"status": "completed", "req_id": "9"},
        request_chain_id="CHAIN-PO-2",
    )

    result = list_a2a_history(po_id="PO-777", db_path=db_path)

    assert result["count"] == 1
    item = result["items"][0]
    assert item["request_chain_id"] == "CHAIN-PO-1"
    assert item["skill"] == "request-withdrawal"
    assert item["request"] == {"po_id": "PO-777", "amount": 60000}
    assert item["response"] == {"status": "completed", "req_id": "3"}
    assert item["status"] == "ok"


# ---- (b) skill 필터 -------------------------------------------------------------


def test_skill_filter(db_path: str):
    _seed(
        db_path,
        skill_id="lookup-clause",
        request_payload={"question": "화재 특약 보장 범위는?"},
        response_payload={"status": "completed", "answer": "..."},
        request_chain_id="CHAIN-CLAUSE-1",
    )
    _seed(
        db_path,
        skill_id="assess-loan",
        request_payload={"loan_amount": 5000, "collateral_building_id": "BLD-001"},
        response_payload={"status": "completed"},
        request_chain_id="CHAIN-LOAN-1",
    )

    result = list_a2a_history(skill="lookup-clause", db_path=db_path)

    assert result["count"] == 1
    assert result["items"][0]["skill"] == "lookup-clause"
    assert result["items"][0]["request_chain_id"] == "CHAIN-CLAUSE-1"


# ---- (c) chain_id 정확 매칭 (접두어 매칭 아님) ------------------------------------


def test_chain_id_exact_match_not_prefix(db_path: str):
    _seed(
        db_path,
        skill_id="lookup-clause",
        request_payload={"question": "q1"},
        response_payload={"status": "completed"},
        request_chain_id="CHAIN-A",
    )
    _seed(
        db_path,
        skill_id="lookup-clause",
        request_payload={"question": "q2"},
        response_payload={"status": "completed"},
        request_chain_id="CHAIN-AB",
    )

    result = list_a2a_history(chain_id="CHAIN-A", db_path=db_path)

    assert result["count"] == 1
    assert result["items"][0]["request_chain_id"] == "CHAIN-A"


# ---- (d) tool_payload NULL 일 때 response: None ---------------------------------


def test_tool_payload_null_yields_response_none(db_path: str):
    _seed(
        db_path,
        skill_id="request-withdrawal",
        request_payload={"po_id": "PO-500"},
        response_payload=None,
        request_chain_id="CHAIN-NULL-1",
        status="timeout",
    )

    result = list_a2a_history(chain_id="CHAIN-NULL-1", db_path=db_path)

    assert result["count"] == 1
    item = result["items"][0]
    assert item["response"] is None
    assert item["status"] == "timeout"


# ---- (e) 필터 없을 때 3종 스킬이 섞여 나옴 ----------------------------------------


def test_no_filter_returns_all_three_skills(db_path: str):
    _seed(
        db_path,
        skill_id="request-withdrawal",
        request_payload={"po_id": "PO-1"},
        response_payload={"status": "completed"},
        request_chain_id="CHAIN-MIX-1",
    )
    _seed(
        db_path,
        skill_id="lookup-clause",
        request_payload={"question": "q"},
        response_payload={"status": "completed"},
        request_chain_id="CHAIN-MIX-2",
    )
    _seed(
        db_path,
        skill_id="assess-loan",
        request_payload={"collateral_building_id": "BLD-1"},
        response_payload={"status": "completed"},
        request_chain_id="CHAIN-MIX-3",
    )

    result = list_a2a_history(db_path=db_path)

    assert result["count"] == 3
    skills = {it["skill"] for it in result["items"]}
    assert skills == {"request-withdrawal", "lookup-clause", "assess-loan"}


# ---- (f) limit 적용 --------------------------------------------------------------


def test_limit_applied(db_path: str):
    for i in range(5):
        _seed(
            db_path,
            skill_id="lookup-clause",
            request_payload={"question": f"q{i}"},
            response_payload={"status": "completed"},
            request_chain_id=f"CHAIN-LIMIT-{i}",
        )

    result = list_a2a_history(limit=2, db_path=db_path)

    assert result["count"] == 2
    assert len(result["items"]) == 2


def test_limit_non_positive_returns_empty(db_path: str):
    _seed(
        db_path,
        skill_id="lookup-clause",
        request_payload={"question": "q"},
        response_payload={"status": "completed"},
        request_chain_id="CHAIN-ZERO-1",
    )

    result = list_a2a_history(limit=0, db_path=db_path)

    assert result == {"count": 0, "items": []}


# ---- 엣지 케이스: tool_call 만 있고 tool_result 없음 -------------------------------


def test_tool_call_only_no_result_yet(db_path: str):
    record_a2a_trace(
        session_id="sess-partial",
        skill_id="lookup-clause",
        request_payload={"question": "q"},
        response_payload={"status": "completed"},
        request_chain_id="CHAIN-PARTIAL",
        db_path=db_path,
    )
    # tool_result 행을 지워 tool_call 만 남긴다 (이론상 발생 안 하지만 방어적으로 확인)
    # ⚠ `db_path` 는 Postgres DSN 문자열이다(D116) — `sqlite3.connect()` 로는 못 연다.
    #   Postgres 전환 때 이 파일이 공식 8파일 목록 밖이라 아무도 안 돌려 남아 있었다
    #   (2026-08-30 발견).
    con = dbcompat.connect_dsn(db_path)
    con.execute("DELETE FROM traces WHERE event_type = 'tool_result'")
    con.commit()
    con.close()

    result = list_a2a_history(chain_id="CHAIN-PARTIAL", db_path=db_path)

    assert result["count"] == 1
    item = result["items"][0]
    assert item["status"] is None
    assert item["response"] is None


def test_building_id_filter(db_path: str):
    _seed(
        db_path,
        skill_id="assess-loan",
        request_payload={"collateral_building_id": "BLD-001", "loan_amount": 1000},
        response_payload={"status": "completed"},
        request_chain_id="CHAIN-BLD-1",
    )
    _seed(
        db_path,
        skill_id="assess-loan",
        request_payload={"collateral_building_id": "BLD-002", "loan_amount": 2000},
        response_payload={"status": "completed"},
        request_chain_id="CHAIN-BLD-2",
    )

    result = list_a2a_history(building_id="BLD-001", db_path=db_path)

    assert result["count"] == 1
    assert result["items"][0]["request_chain_id"] == "CHAIN-BLD-1"
