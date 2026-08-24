# -*- coding: utf-8 -*-
"""backend/routers/po.py 의 A2A 트리거(S5, `POST /api/po/{po_id}/finance-approve`) 테스트.

po.py 라우터 전체(submit/reject 등)가 아니라 **재무 승인 직후 FinAllQ A2A
request-withdrawal 을 보내는 경로**만 다룬다 — 특히 두 가지 계약을 고정한다:
  1) 재무부 소속 팀장이 아니면(403) A2A 호출까지 도달하지 못한다 (돈을 움직이는 호출이므로).
  2) A2A 전송 실패가 재무 승인 자체를 되돌리지 않는다 (routers/po.py 의 명시적 설계).

D119(SoD): 팀장 승인(`approve`)과 자금집행 승인(`finance-approve`)이 분리되면서 A2A
request-withdrawal 발송 시점도 `approve()` 에서 `finance-approve()` 로 이동했다. 이 파일도
그 이동을 그대로 반영한다.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.a2a.client as a2a_client
import backend.routers.po as po_router_module
from data import dbcompat


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, db_path: str) -> TestClient:
    monkeypatch.setattr("backend.db.DB_PATH", db_path)
    app = FastAPI()
    app.include_router(po_router_module.router)
    return TestClient(app)


def _seed_finance_manager(db_path: str, user_id: str = "mgr-02") -> None:
    """`users` 에 재무부 소속 팀장을 심는다.

    `seed_po()`(conftest.py)가 만드는 `decided_by` 사용자는 `department` 를 채우지 않는다
    — 격리 스키마는 `clone_data=False` 라 `users` 가 비어 있으므로, finance-approve/
    finance-reject 성공 경로를 테스트하려면 이 파일 안에서 직접 만들어야 한다(D119).
    """
    con = dbcompat.connect_dsn(db_path)
    try:
        con.execute(
            "INSERT INTO users (user_id, display_name, role, department)"
            " VALUES (?, ?, 'manager', 'finance')",
            (user_id, user_id),
        )
        con.commit()
    finally:
        con.close()


MANAGER = {"X-Role": "manager", "X-User": "mgr-01"}
MANAGER_FINANCE = {"X-Role": "manager", "X-User": "mgr-02"}
TECHNICIAN = {"X-Role": "technician", "X-User": "tech-01"}


def test_manager_approve_does_not_trigger_a2a_dispatch(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, db_path: str, link_finallq, seed_po
):
    """approve()는 더 이상 A2A를 부르지 않는다 — 발송 시점이 finance-approve로 이동했다(D119)."""
    link_finallq(external_ref="CMP-MAINTQ-001")
    seed_po(po_id="PO-001", state="pending", unit_price=10000, qty=3)
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_BASE_URL", "http://finallq-adapter.local")

    captured: dict = {}

    async def _fake_call_skill(**kwargs: Any) -> dict:
        captured.update(kwargs)
        return {"status": "input-required", "req_id": "1"}

    monkeypatch.setattr(a2a_client, "call_skill", _fake_call_skill)

    resp = client.post("/api/po/PO-001/approve", headers=MANAGER, json={"note": "승인합니다"})

    assert resp.status_code == 200
    assert resp.json()["state"] == "approved"
    assert not captured


def test_finance_approve_triggers_a2a_dispatch(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, db_path: str, link_finallq, seed_po
):
    link_finallq(external_ref="CMP-MAINTQ-001")
    seed_po(po_id="PO-001", state="approved", unit_price=10000, qty=3)
    _seed_finance_manager(db_path)
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_BASE_URL", "http://finallq-adapter.local")

    captured: dict = {}

    async def _fake_call_skill(**kwargs: Any) -> dict:
        captured.update(kwargs)
        return {"status": "input-required", "req_id": "1"}

    monkeypatch.setattr(a2a_client, "call_skill", _fake_call_skill)

    resp = client.post(
        "/api/po/PO-001/finance-approve", headers=MANAGER_FINANCE, json={"note": "승인합니다"}
    )

    assert resp.status_code == 200
    assert resp.json()["state"] == "finance_approved"
    assert captured["partner"] == "finallq"
    assert captured["skill_id"] == "request-withdrawal"
    assert captured["payload"]["amount"] == 30000


def test_technician_cannot_approve_and_a2a_is_never_called(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, link_finallq, seed_po
):
    link_finallq()
    seed_po(po_id="PO-001", state="pending")
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_BASE_URL", "http://finallq-adapter.local")

    called = False

    async def _fake_call_skill(**kwargs: Any) -> dict:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(a2a_client, "call_skill", _fake_call_skill)

    resp = client.post("/api/po/PO-001/approve", headers=TECHNICIAN)

    assert resp.status_code == 403
    assert called is False


def test_technician_cannot_finance_approve_and_a2a_is_never_called(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, link_finallq, seed_po
):
    link_finallq()
    seed_po(po_id="PO-001", state="approved")
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_BASE_URL", "http://finallq-adapter.local")

    called = False

    async def _fake_call_skill(**kwargs: Any) -> dict:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(a2a_client, "call_skill", _fake_call_skill)

    resp = client.post("/api/po/PO-001/finance-approve", headers=TECHNICIAN)

    assert resp.status_code == 403
    assert called is False


def test_a2a_failure_does_not_undo_finance_approval(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, db_path: str, link_finallq, seed_po
):
    link_finallq()
    seed_po(po_id="PO-001", state="approved")
    _seed_finance_manager(db_path)
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_BASE_URL", "http://finallq-adapter.local")

    async def _fake_call_skill(**kwargs: Any):
        raise a2a_client.A2AUpstreamUnavailableError("adapter down", status_code=502)

    monkeypatch.setattr(a2a_client, "call_skill", _fake_call_skill)

    resp = client.post("/api/po/PO-001/finance-approve", headers=MANAGER_FINANCE)

    assert resp.status_code == 200
    assert resp.json()["state"] == "finance_approved"

    # 상태가 정말로 DB에도 finance_approved로 남았는지 별도 조회로 재확인한다.
    detail = client.get("/api/po/PO-001", headers=MANAGER_FINANCE)
    assert detail.json()["state"] == "finance_approved"


def test_dispatch_is_noop_when_base_url_not_configured(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, db_path: str, link_finallq, seed_po
):
    link_finallq()
    seed_po(po_id="PO-001", state="approved")
    _seed_finance_manager(db_path)
    monkeypatch.delenv("MAINTQ_A2A_FINALLQ_BASE_URL", raising=False)

    called = False

    async def _fake_call_skill(**kwargs: Any) -> dict:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(a2a_client, "call_skill", _fake_call_skill)

    resp = client.post("/api/po/PO-001/finance-approve", headers=MANAGER_FINANCE)

    assert resp.status_code == 200
    assert called is False


def test_reject_does_not_trigger_a2a(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, link_finallq, seed_po
):
    """반려 경로는 A2A와 무관하다 — call_skill이 아예 호출되지 않아야 한다."""
    link_finallq()
    seed_po(po_id="PO-001", state="pending")
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_BASE_URL", "http://finallq-adapter.local")

    called = False

    async def _fake_call_skill(**kwargs: Any) -> dict:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(a2a_client, "call_skill", _fake_call_skill)

    resp = client.post("/api/po/PO-001/reject", headers=MANAGER, json={"reason": "예산 초과"})

    assert resp.status_code == 200
    assert called is False


def test_finance_reject_does_not_trigger_a2a(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, db_path: str, link_finallq, seed_po
):
    """자금집행 반려 경로도 A2A와 무관하다 — call_skill이 아예 호출되지 않아야 한다."""
    link_finallq()
    seed_po(po_id="PO-001", state="approved")
    _seed_finance_manager(db_path)
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_BASE_URL", "http://finallq-adapter.local")

    called = False

    async def _fake_call_skill(**kwargs: Any) -> dict:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(a2a_client, "call_skill", _fake_call_skill)

    resp = client.post(
        "/api/po/PO-001/finance-reject", headers=MANAGER_FINANCE, json={"reason": "예산 초과"}
    )

    assert resp.status_code == 200
    assert called is False
