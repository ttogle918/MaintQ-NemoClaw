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
from backend.a2a.client import (
    A2AClientError,
    A2APolicyBlockedError,
    A2ATimeoutError,
    A2AUpstreamUnavailableError,
)


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


def test_insuq_base_url_defaults_to_localhost_8081(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    """InsuQ 가 lookup-clause 를 FastAPI 어댑터(:9102) → Spring backend(:8081) 로
    이관하면서 옛 어댑터를 삭제했다 (2026-08-30) — 기본값이 따라가야 한다."""
    monkeypatch.delenv("MAINTQ_A2A_INSUQ_BASE_URL", raising=False)
    captured: dict = {}

    async def _fake_call_skill(**kwargs: Any) -> dict:
        captured.update(kwargs)
        return {"status": "completed"}

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    client.post("/api/a2a/lookup-clause", json={"question": "질문"})

    assert captured["base_url"] == "http://localhost:8081"


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


def test_policy_blocked_maps_to_503(monkeypatch: pytest.MonkeyPatch, client: TestClient, db_path: str):
    """샌드박스 정책상 발신을 시도조차 안 했으면 503 `policy_blocked` 다 (D149)."""

    async def _fake_call_skill(**kwargs: Any):
        raise A2APolicyBlockedError("blocked")

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    resp = client.post("/api/a2a/lookup-clause", json={"question": "질문"})

    assert resp.status_code == 503
    assert resp.json()["detail"]["reason"] == "policy_blocked"
    rows = _traces(db_path)
    assert [r["event_type"] for r in rows] == ["tool_call", "tool_result"]
    result_payload = json.loads(rows[1]["payload"])
    assert result_payload["status"] == "policy_blocked"


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


def test_assess_loan_policy_blocked_maps_to_503(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, db_path: str
):
    async def _fake_call_skill(**kwargs: Any):
        raise A2APolicyBlockedError("blocked")

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    resp = client.post("/api/a2a/assess-loan", json=_LOAN_BODY)

    assert resp.status_code == 503
    assert resp.json()["detail"]["reason"] == "policy_blocked"
    result_payload = json.loads(_traces(db_path)[1]["payload"])
    assert result_payload["status"] == "policy_blocked"


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


def test_assess_used_equipment_loan_policy_blocked_maps_to_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_assets, db_path: str
) -> None:
    """`_dispatch` 헬퍼 경로(:70 부근)도 정책 차단을 먼저 잡는다 (D149)."""

    async def _fake_call_skill(**kwargs: Any):
        raise A2APolicyBlockedError("blocked")

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_call_skill)

    res = client.post(
        "/api/a2a/assess-used-equipment-loan",
        json={"asset_id": "AST-L3-CONV", "loan_amount": 5_000_000},
    )

    assert res.status_code == 503
    assert res.json()["detail"]["reason"] == "policy_blocked"
    rows = _traces(db_path)
    result_payload = json.loads(rows[1]["payload"])
    assert result_payload["status"] == "policy_blocked"


# ---- S12: request-settlement -------------------------------------------------


def _fake_settlement(lien_released: bool):
    async def _fake_call_skill(**kwargs: Any) -> dict:
        return {
            "status": "ok",
            "action": "repay",
            "lien_released": lien_released,
            "remaining_balance": 5_000_000,
        }

    return _fake_call_skill


def test_settlement_released_writes_lien_consent_ref(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_lien_decisions, fetch_asset
) -> None:
    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_settlement(True))

    res = client.post(
        "/api/a2a/request-settlement",
        json={
            "decision_id": "DEC-0001", "sale_amount": 8_000_000,
            "outstanding_loan": 3_000_000, "approved_by": "U-FIN-01",
        },
    )

    assert res.status_code == 200
    assert res.json()["maintq_lien_consent_updated"] is True
    ref = fetch_asset("AST-LIEN")["lien_consent_ref"]
    assert ref  # 비어 있지 않다
    assert ref.strip() == ref  # 공백만 있는 값도 아니다
    assert ref.startswith("A2A-SETTLE-")  # traces 로 되짚을 수 있는 형태다


def test_settlement_not_released_writes_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_lien_decisions, fetch_asset
) -> None:
    """음성 축 — `lien_released=false` 면 담보는 그대로 남는다."""
    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_settlement(False))

    res = client.post(
        "/api/a2a/request-settlement",
        json={
            "decision_id": "DEC-0001", "sale_amount": 1,
            "outstanding_loan": 999_999_999, "approved_by": "U",
        },
    )

    assert res.status_code == 200
    assert fetch_asset("AST-LIEN")["lien_consent_ref"] is None


def test_settlement_missing_key_writes_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_lien_decisions, fetch_asset
) -> None:
    """`lien_released` 키가 아예 없으면 아무것도 쓰지 않는다 — 조용한 해소 금지."""

    async def _no_key(**kwargs: Any) -> dict:
        return {"status": "ok", "action": "hold"}

    monkeypatch.setattr(a2a_router_module, "call_skill", _no_key)

    res = client.post(
        "/api/a2a/request-settlement",
        json={
            "decision_id": "DEC-0001", "sale_amount": 1,
            "outstanding_loan": 1, "approved_by": "U",
        },
    )

    assert res.status_code == 200
    assert "maintq_lien_consent_updated" not in res.json()
    assert fetch_asset("AST-LIEN")["lien_consent_ref"] is None


def test_settlement_never_signs_the_decision(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_lien_decisions, fetch_decision
) -> None:
    """🔴 `lien_released=true` 여도 결정은 draft 그대로다 — 서명은 사람이 한다."""
    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_settlement(True))

    client.post(
        "/api/a2a/request-settlement",
        json={
            "decision_id": "DEC-0001", "sale_amount": 8_000_000,
            "outstanding_loan": 3_000_000, "approved_by": "U-FIN-01",
        },
    )

    d = fetch_decision("DEC-0001")
    assert d["state"] == "draft"
    assert d["signed_at"] is None
    assert d["reviewed_by"] is None


def test_upstream_failure_leaves_state_unchanged(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_lien_decisions, fetch_asset
) -> None:
    """상대가 죽어도 MaintQ 상태는 안 바뀐다."""

    async def _boom(**kwargs: Any) -> dict:
        raise A2AUpstreamUnavailableError("down")

    monkeypatch.setattr(a2a_router_module, "call_skill", _boom)

    res = client.post(
        "/api/a2a/request-settlement",
        json={
            "decision_id": "DEC-0001", "sale_amount": 1,
            "outstanding_loan": 1, "approved_by": "U",
        },
    )

    assert res.status_code == 502
    assert fetch_asset("AST-LIEN")["lien_consent_ref"] is None


def test_settlement_on_asset_without_lien_is_400(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_lien_decisions
) -> None:
    async def _fake(**kwargs: Any) -> dict:
        raise AssertionError("담보 없는 자산인데 발신하면 안 된다")

    monkeypatch.setattr(a2a_router_module, "call_skill", _fake)

    res = client.post(
        "/api/a2a/request-settlement",
        json={
            "decision_id": "DEC-NOLIEN", "sale_amount": 1,
            "outstanding_loan": 1, "approved_by": "U",
        },
    )

    assert res.status_code == 400
    assert "담보" in res.json()["detail"]


# ---- S11: notify-asset-change ------------------------------------------------


def _fake_notify(captured: dict):
    async def _fake_call_skill(**kwargs: Any) -> dict:
        captured.update(kwargs)
        return {
            "status": "completed",
            "receipt_no": "RCP-2026-0811",
            "premium_adjustment": -120000,
            "evidence": ["화재보험 보통약관 제12조 ②, p.34"],
        }

    return _fake_call_skill


def test_notify_asset_change_dispatches_to_insuq(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_signed_disposals
) -> None:
    captured: dict = {}
    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_notify(captured))

    res = client.post("/api/a2a/notify-asset-change", json={"decision_id": "DEC-SIGNED"})

    assert res.status_code == 200
    assert res.json()["receipt_no"] == "RCP-2026-0811"
    # InsuQ 로 가야 한다 — 파트너를 잘못 넣으면 FinAllQ 토큰이 실린다
    assert captured["partner"] == "insuq"
    assert captured["skill_id"] == "notify-asset-change"
    assert captured["payload"]["change_type"] == "REMOVE"


def test_notify_asset_change_sends_idempotency_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_signed_disposals
) -> None:
    """S11 은 멱등키를 실어 보낸다 (D141) — 통지 재전송이 증권을 두 번 고치면 안 된다."""
    captured: dict = {}
    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_notify(captured))

    res = client.post("/api/a2a/notify-asset-change", json={"decision_id": "DEC-SIGNED"})

    assert res.status_code == 200
    assert captured["idempotency_key"] == "DEC-SIGNED:REMOVE"


def test_notify_asset_change_unsigned_is_400_and_never_dispatched(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_signed_disposals
) -> None:
    """조립에서 막힌 요청은 **나가지 않는다** — 빈 값을 실어 보내 상대가 400 을 내게 하지 않는다."""
    captured: dict = {}
    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_notify(captured))

    res = client.post("/api/a2a/notify-asset-change", json={"decision_id": "DEC-DRAFT"})

    assert res.status_code == 400
    assert "서명 전" in res.json()["detail"]
    assert captured == {}  # 발신 자체가 없었다


def test_notify_asset_change_uninsured_is_400(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_signed_disposals
) -> None:
    captured: dict = {}
    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_notify(captured))

    res = client.post("/api/a2a/notify-asset-change", json={"decision_id": "DEC-UNINSURED"})

    assert res.status_code == 400
    assert captured == {}


def test_notify_asset_change_does_not_mutate_maintq_state(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_signed_disposals, fetch_asset
) -> None:
    """S12 와 달리 통지는 되받지 않는다 — 보험료 조정이 와도 자산 장부를 건드리지 않는다."""
    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_notify({}))
    before = fetch_asset("AST-INSURED")

    res = client.post("/api/a2a/notify-asset-change", json={"decision_id": "DEC-SIGNED"})

    assert res.status_code == 200
    assert fetch_asset("AST-INSURED") == before


def test_notify_asset_change_uses_provided_chain_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seed_signed_disposals
) -> None:
    captured: dict = {}
    monkeypatch.setattr(a2a_router_module, "call_skill", _fake_notify(captured))

    client.post(
        "/api/a2a/notify-asset-change",
        json={"decision_id": "DEC-SIGNED", "request_chain_id": "CHAIN-S11-FIXED"},
    )

    assert captured["request_chain_id"] == "CHAIN-S11-FIXED"
    assert captured["payload"]["request_chain_id"] == "CHAIN-S11-FIXED"
