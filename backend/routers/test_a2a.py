# -*- coding: utf-8 -*-
"""backend/routers/a2a.py (`POST /api/a2a/lookup-clause`) 테스트.

라우터만 올린 최소 FastAPI 앱을 쓴다 — `backend.main` 전체를 임포트하면 MCP
서브프로세스 lifespan 이 붙어 테스트가 무거워지고 네트워크 성격을 띤다.
`backend.routers.a2a.call_skill` (모듈 상단에서 바인딩된 이름)을 monkeypatch 해서
InsuQ 어댑터로의 실제 HTTP 호출을 대체한다.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from data import dbcompat

import backend.routers.a2a as a2a_router_module
from backend.a2a.client import A2AClientError, A2ATimeoutError, A2AUpstreamUnavailableError


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, db_path: str) -> TestClient:
    monkeypatch.setattr("backend.db.DB_PATH", db_path)
    app = FastAPI()
    app.include_router(a2a_router_module.router)
    return TestClient(app)


def _traces(db_path: str) -> list:
    con = dbcompat.connect_dsn(db_path)
    try:
        return con.execute("SELECT * FROM traces ORDER BY seq").fetchall()
    finally:
        con.close()


def test_success_returns_adapter_response(monkeypatch: pytest.MonkeyPatch, client: TestClient, db_path: str):
    captured: dict = {}

    async def _fake_call_skill(**kwargs: Any) -> dict:
        captured.update(kwargs)
        return {"status": "completed", "answer": "약관상 보장됩니다.", "evidence": ["제3조"]}

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    resp = client.post("/api/a2a/lookup-clause", json={"question": "화재보험 보장 범위는?"})

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "completed",
        "answer": "약관상 보장됩니다.",
        "evidence": ["제3조"],
        "request_chain_id": captured["request_chain_id"],
    }
    assert captured["partner"] == "insuq"
    assert captured["skill_id"] == "lookup-clause"
    assert captured["payload"]["question"] == "화재보험 보장 범위는?"

    rows = _traces(db_path)
    assert [r["event_type"] for r in rows] == ["tool_call", "tool_result"]
    result_payload = json.loads(rows[1]["payload"])
    assert result_payload["status"] == "ok"


def test_generates_chain_id_when_not_provided(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    captured: dict = {}

    async def _fake_call_skill(**kwargs: Any) -> dict:
        captured.update(kwargs)
        return {"status": "completed"}

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    client.post("/api/a2a/lookup-clause", json={"question": "질문"})

    assert captured["request_chain_id"].startswith("CHAIN-CLAUSE-")


def test_uses_provided_chain_id(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    captured: dict = {}

    async def _fake_call_skill(**kwargs: Any) -> dict:
        captured.update(kwargs)
        return {"status": "completed"}

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    client.post(
        "/api/a2a/lookup-clause",
        json={"question": "질문", "request_chain_id": "CHAIN-FIXED-1"},
    )

    assert captured["request_chain_id"] == "CHAIN-FIXED-1"


def test_base_url_defaults_to_localhost_9102(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    monkeypatch.delenv("MAINTQ_A2A_INSUQ_BASE_URL", raising=False)
    captured: dict = {}

    async def _fake_call_skill(**kwargs: Any) -> dict:
        captured.update(kwargs)
        return {"status": "completed"}

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    client.post("/api/a2a/lookup-clause", json={"question": "질문"})

    assert captured["base_url"] == "http://localhost:9102"


def test_base_url_reads_env_override(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    monkeypatch.setenv("MAINTQ_A2A_INSUQ_BASE_URL", "https://insuq.example.com")
    captured: dict = {}

    async def _fake_call_skill(**kwargs: Any) -> dict:
        captured.update(kwargs)
        return {"status": "completed"}

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    client.post("/api/a2a/lookup-clause", json={"question": "질문"})

    assert captured["base_url"] == "https://insuq.example.com"


def test_timeout_maps_to_504(monkeypatch: pytest.MonkeyPatch, client: TestClient, db_path: str):
    async def _fake_call_skill(**kwargs: Any):
        raise A2ATimeoutError("timed out")

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    resp = client.post("/api/a2a/lookup-clause", json={"question": "질문"})

    assert resp.status_code == 504
    result_payload = json.loads(_traces(db_path)[1]["payload"])
    assert result_payload["status"] == "timeout"


def test_upstream_unavailable_maps_to_502(monkeypatch: pytest.MonkeyPatch, client: TestClient, db_path: str):
    async def _fake_call_skill(**kwargs: Any):
        raise A2AUpstreamUnavailableError("adapter down", status_code=502)

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    resp = client.post("/api/a2a/lookup-clause", json={"question": "질문"})

    assert resp.status_code == 502
    result_payload = json.loads(_traces(db_path)[1]["payload"])
    assert result_payload["status"] == "unavailable"


def test_generic_client_error_uses_its_own_status_code(monkeypatch: pytest.MonkeyPatch, client: TestClient, db_path: str):
    async def _fake_call_skill(**kwargs: Any):
        raise A2AClientError("schema invalid", status_code=400, detail="bad request")

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    resp = client.post("/api/a2a/lookup-clause", json={"question": "질문"})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "bad request"
    result_payload = json.loads(_traces(db_path)[1]["payload"])
    assert result_payload["status"] == "error"


def test_generic_client_error_without_status_code_defaults_to_400(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    async def _fake_call_skill(**kwargs: Any):
        raise A2AClientError("unknown failure")

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    resp = client.post("/api/a2a/lookup-clause", json={"question": "질문"})

    assert resp.status_code == 400


def test_blank_question_is_rejected_by_validation(client: TestClient):
    resp = client.post("/api/a2a/lookup-clause", json={"question": ""})
    assert resp.status_code == 422


# ---- POST /api/a2a/assess-loan ------------------------------------------------


_LOAN_BODY = {"loan_amount": 50000000, "purpose": "설비 증설 자금", "collateral_building_id": "BLD-001"}


def test_assess_loan_success_returns_adapter_response(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, db_path: str
):
    captured: dict = {}

    async def _fake_call_skill(**kwargs: Any) -> dict:
        captured.update(kwargs)
        return {"status": "completed", "decision": "approved", "condition_note": None}

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    resp = client.post("/api/a2a/assess-loan", json=_LOAN_BODY)

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "completed",
        "decision": "approved",
        "condition_note": None,
        "request_chain_id": captured["request_chain_id"],
    }
    assert captured["partner"] == "finallq"
    assert captured["skill_id"] == "assess-loan"
    assert captured["payload"]["loan_amount"] == 50000000
    assert captured["payload"]["purpose"] == "설비 증설 자금"
    assert captured["payload"]["collateral_building_id"] == "BLD-001"

    rows = _traces(db_path)
    assert [r["event_type"] for r in rows] == ["tool_call", "tool_result"]
    result_payload = json.loads(rows[1]["payload"])
    assert result_payload["status"] == "ok"


def test_assess_loan_generates_chain_id_when_not_provided(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    captured: dict = {}

    async def _fake_call_skill(**kwargs: Any) -> dict:
        captured.update(kwargs)
        return {"status": "completed"}

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    client.post("/api/a2a/assess-loan", json=_LOAN_BODY)

    assert captured["request_chain_id"].startswith("CHAIN-LOAN-")


def test_assess_loan_uses_provided_chain_id(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    captured: dict = {}

    async def _fake_call_skill(**kwargs: Any) -> dict:
        captured.update(kwargs)
        return {"status": "completed"}

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    client.post("/api/a2a/assess-loan", json={**_LOAN_BODY, "request_chain_id": "CHAIN-FIXED-2"})

    assert captured["request_chain_id"] == "CHAIN-FIXED-2"


def test_assess_loan_base_url_defaults_to_localhost_9101(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    monkeypatch.delenv("MAINTQ_A2A_FINALLQ_BASE_URL", raising=False)
    captured: dict = {}

    async def _fake_call_skill(**kwargs: Any) -> dict:
        captured.update(kwargs)
        return {"status": "completed"}

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    client.post("/api/a2a/assess-loan", json=_LOAN_BODY)

    assert captured["base_url"] == "http://localhost:9101"


def test_assess_loan_base_url_reads_env_override(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_BASE_URL", "https://finallq.example.com")
    captured: dict = {}

    async def _fake_call_skill(**kwargs: Any) -> dict:
        captured.update(kwargs)
        return {"status": "completed"}

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    client.post("/api/a2a/assess-loan", json=_LOAN_BODY)

    assert captured["base_url"] == "https://finallq.example.com"


def test_assess_loan_timeout_maps_to_504(monkeypatch: pytest.MonkeyPatch, client: TestClient, db_path: str):
    async def _fake_call_skill(**kwargs: Any):
        raise A2ATimeoutError("timed out")

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    resp = client.post("/api/a2a/assess-loan", json=_LOAN_BODY)

    assert resp.status_code == 504
    result_payload = json.loads(_traces(db_path)[1]["payload"])
    assert result_payload["status"] == "timeout"


def test_assess_loan_upstream_unavailable_maps_to_502(monkeypatch: pytest.MonkeyPatch, client: TestClient, db_path: str):
    async def _fake_call_skill(**kwargs: Any):
        raise A2AUpstreamUnavailableError("adapter down", status_code=502)

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    resp = client.post("/api/a2a/assess-loan", json=_LOAN_BODY)

    assert resp.status_code == 502
    result_payload = json.loads(_traces(db_path)[1]["payload"])
    assert result_payload["status"] == "unavailable"


def test_assess_loan_generic_client_error_uses_its_own_status_code(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, db_path: str
):
    async def _fake_call_skill(**kwargs: Any):
        raise A2AClientError("schema invalid", status_code=400, detail="bad request")

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    resp = client.post("/api/a2a/assess-loan", json=_LOAN_BODY)

    assert resp.status_code == 400
    assert resp.json()["detail"] == "bad request"
    result_payload = json.loads(_traces(db_path)[1]["payload"])
    assert result_payload["status"] == "error"


def test_assess_loan_missing_required_field_rejected_by_validation(client: TestClient):
    resp = client.post(
        "/api/a2a/assess-loan",
        json={"loan_amount": 50000000, "purpose": "설비 증설 자금"},
    )
    assert resp.status_code == 422


def test_assess_loan_non_positive_amount_rejected_by_validation(client: TestClient):
    resp = client.post("/api/a2a/assess-loan", json={**_LOAN_BODY, "loan_amount": 0})
    assert resp.status_code == 422


# ---- S13: assess-used-equipment-loan ----------------------------------------


def test_assess_used_equipment_loan_endpoint_returns_partner_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_assets
) -> None:
    captured: dict[str, Any] = {}

    async def _fake_call_skill(**kwargs: Any) -> dict:
        captured.update(kwargs)
        return {"status": "ok", "decision": "conditional", "appraised_value": 4_000_000}

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    res = client.post(
        "/api/a2a/assess-used-equipment-loan",
        json={"asset_id": "AST-L3-CONV", "loan_amount": 5_000_000},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["decision"] == "conditional"
    assert body["request_chain_id"]  # 파트너가 echo 안 해도 채워진다
    assert captured["skill_id"] == "assess-used-equipment-loan"
    assert captured["partner"] == "finallq"
    # 빌더가 자산에서 파생한 값이 실제로 실려 나간다 (양성 축)
    assert captured["payload"]["collateral_building_id"] == "BLD-A"
    assert captured["payload"]["equipment_year"] == 2019


def test_assess_used_equipment_loan_unknown_asset_is_400(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_assets
) -> None:
    """빌더가 ValueError 를 던지면 500 이 아니라 400 으로 나간다 — 발신 자체를 안 한다."""

    async def _fake_call_skill(**kwargs: Any) -> dict:
        raise AssertionError("없는 자산인데 발신하면 안 된다")

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    res = client.post(
        "/api/a2a/assess-used-equipment-loan",
        json={"asset_id": "AST-NOPE", "loan_amount": 1},
    )

    assert res.status_code == 400
    assert "AST-NOPE" in res.json()["detail"]
