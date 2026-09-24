# -*- coding: utf-8 -*-
"""backend/services/po.py::dispatch_a2a_withdrawal_request 테스트 (S5 트리거).

FinAllQ A2A 어댑터로의 실제 HTTP 호출은 `backend.a2a.client.call_skill` 을 monkeypatch
해서 대체한다 — 여기서 검증하는 것은 "언제 부르는가/안 부르는가"와 "trace에 뭐가
남는가"이지, client.py 의 HTTP 계약(그건 backend/a2a/test_client.py 가 이미 본다)이 아니다.
"""

from __future__ import annotations

from typing import Any

import pytest

from data import dbcompat

import backend.a2a.client as a2a_client
from backend.services.po import dispatch_a2a_withdrawal_request


def _traces(db_path: str) -> list:
    con = dbcompat.connect_dsn(db_path)
    try:
        return con.execute("SELECT * FROM traces ORDER BY seq").fetchall()
    finally:
        con.close()


@pytest.mark.asyncio
async def test_skips_when_base_url_not_configured(monkeypatch: pytest.MonkeyPatch, db_path: str, link_finallq, seed_po):
    link_finallq()
    seed_po(state="approved")
    monkeypatch.delenv("MAINTQ_A2A_FINALLQ_BASE_URL", raising=False)

    called = False

    async def _fake_call_skill(**kwargs: Any) -> dict:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(a2a_client, "call_skill", _fake_call_skill)

    result = await dispatch_a2a_withdrawal_request("PO-001", base_url=None, db_path=db_path)

    assert result is None
    assert called is False
    assert _traces(db_path) == []


@pytest.mark.asyncio
async def test_skips_when_finallq_company_not_linked(monkeypatch: pytest.MonkeyPatch, db_path: str, seed_po):
    seed_po(state="approved")  # partner_links에 아무 행도 없다 = not linked

    called = False

    async def _fake_call_skill(**kwargs: Any) -> dict:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(a2a_client, "call_skill", _fake_call_skill)

    result = await dispatch_a2a_withdrawal_request("PO-001", base_url="http://finallq-adapter.local", db_path=db_path)

    assert result is None
    assert called is False


@pytest.mark.asyncio
async def test_skips_when_po_not_found(monkeypatch: pytest.MonkeyPatch, db_path: str, link_finallq):
    link_finallq()

    called = False

    async def _fake_call_skill(**kwargs: Any) -> dict:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(a2a_client, "call_skill", _fake_call_skill)

    result = await dispatch_a2a_withdrawal_request("PO-DOES-NOT-EXIST", base_url="http://finallq-adapter.local", db_path=db_path)

    assert result is None
    assert called is False


@pytest.mark.asyncio
async def test_happy_path_calls_skill_with_assembled_payload_and_records_trace(
    monkeypatch: pytest.MonkeyPatch, db_path: str, link_finallq, seed_po
):
    link_finallq(external_ref="CMP-MAINTQ-001")
    seed_po(po_id="PO-001", unit_price=20000, qty=2, session_id="sess-42", state="approved")

    captured: dict = {}

    async def _fake_call_skill(**kwargs: Any) -> dict:
        captured.update(kwargs)
        return {"status": "input-required", "req_id": "9"}

    monkeypatch.setattr(a2a_client, "call_skill", _fake_call_skill)

    result = await dispatch_a2a_withdrawal_request(
        "PO-001", base_url="http://finallq-adapter.local", db_path=db_path
    )

    assert result == {"status": "input-required", "req_id": "9"}
    assert captured["partner"] == "finallq"
    assert captured["skill_id"] == "request-withdrawal"
    assert captured["base_url"] == "http://finallq-adapter.local"
    assert captured["payload"]["amount"] == 40000
    assert captured["payload"]["po_id"] == "PO-001"
    assert captured["payload"]["requester"]["finallq_company_id"] == "CMP-MAINTQ-001"
    assert captured["request_chain_id"] == captured["payload"]["request_chain_id"]
    assert captured["request_chain_id"].startswith("CHAIN-PO-001-")

    rows = _traces(db_path)
    assert [r["event_type"] for r in rows] == ["tool_call", "tool_result"]
    assert rows[0]["session_id"] == "sess-42"
    assert rows[0]["request_chain_id"] == captured["request_chain_id"]


@pytest.mark.asyncio
async def test_call_skill_failure_is_recorded_as_error_trace_and_reraised(
    monkeypatch: pytest.MonkeyPatch, db_path: str, link_finallq, seed_po
):
    link_finallq()
    seed_po(po_id="PO-001", session_id="sess-42", state="approved")

    async def _fake_call_skill(**kwargs: Any):
        raise a2a_client.A2AUpstreamUnavailableError("adapter down", status_code=502)

    monkeypatch.setattr(a2a_client, "call_skill", _fake_call_skill)

    with pytest.raises(a2a_client.A2AUpstreamUnavailableError):
        await dispatch_a2a_withdrawal_request(
            "PO-001", base_url="http://finallq-adapter.local", db_path=db_path
        )

    rows = _traces(db_path)
    assert [r["event_type"] for r in rows] == ["tool_call", "tool_result"]
    import json

    result_payload = json.loads(rows[1]["payload"])
    assert result_payload["status"] == "error"


@pytest.mark.asyncio
async def test_policy_blocked_is_recorded_as_policy_blocked_trace_and_reraised(
    monkeypatch: pytest.MonkeyPatch, db_path: str, link_finallq, seed_po
):
    """샌드박스 정책 차단은 `circuit_open`·`error` 와 구분되는 status 로 남는다 (D149)."""
    link_finallq()
    seed_po(po_id="PO-001", session_id="sess-42", state="approved")

    async def _fake_call_skill(**kwargs: Any):
        raise a2a_client.A2APolicyBlockedError("blocked")

    monkeypatch.setattr(a2a_client, "call_skill", _fake_call_skill)

    with pytest.raises(a2a_client.A2APolicyBlockedError):
        await dispatch_a2a_withdrawal_request(
            "PO-001", base_url="http://finallq-adapter.local", db_path=db_path
        )

    rows = _traces(db_path)
    assert [r["event_type"] for r in rows] == ["tool_call", "tool_result"]
    import json

    result_payload = json.loads(rows[1]["payload"])
    assert result_payload["status"] == "policy_blocked"
