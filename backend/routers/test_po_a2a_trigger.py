# -*- coding: utf-8 -*-
"""backend/routers/po.py 의 A2A 트리거(S5, `POST /api/po/{po_id}/approve`) 테스트.

po.py 라우터 전체(submit/reject 등)가 아니라 **승인 직후 FinAllQ A2A
request-withdrawal 을 보내는 경로**만 다룬다 — 특히 두 가지 계약을 고정한다:
  1) 팀장이 아니면(403) A2A 호출까지 도달하지 못한다 (돈을 움직이는 호출이므로).
  2) A2A 전송 실패가 승인 자체를 되돌리지 않는다 (routers/po.py 의 명시적 설계).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.a2a.client as a2a_client
import backend.routers.po as po_router_module


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> TestClient:
    monkeypatch.setenv("MAINTQ_DB", str(db_path))
    app = FastAPI()
    app.include_router(po_router_module.router)
    return TestClient(app)


MANAGER = {"X-Role": "manager", "X-User": "mgr-01"}
TECHNICIAN = {"X-Role": "technician", "X-User": "tech-01"}


def test_manager_approve_triggers_a2a_dispatch(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, db_path: Path, link_finallq, seed_po
):
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


def test_a2a_failure_does_not_undo_approval(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, db_path: Path, link_finallq, seed_po
):
    link_finallq()
    seed_po(po_id="PO-001", state="pending")
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_BASE_URL", "http://finallq-adapter.local")

    async def _fake_call_skill(**kwargs: Any):
        raise a2a_client.A2AUpstreamUnavailableError("adapter down", status_code=502)

    monkeypatch.setattr(a2a_client, "call_skill", _fake_call_skill)

    resp = client.post("/api/po/PO-001/approve", headers=MANAGER)

    assert resp.status_code == 200
    assert resp.json()["state"] == "approved"

    # 상태가 정말로 DB에도 approved로 남았는지 별도 조회로 재확인한다.
    detail = client.get("/api/po/PO-001", headers=MANAGER)
    assert detail.json()["state"] == "approved"


def test_dispatch_is_noop_when_base_url_not_configured(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, link_finallq, seed_po
):
    link_finallq()
    seed_po(po_id="PO-001", state="pending")
    monkeypatch.delenv("MAINTQ_A2A_FINALLQ_BASE_URL", raising=False)

    called = False

    async def _fake_call_skill(**kwargs: Any) -> dict:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(a2a_client, "call_skill", _fake_call_skill)

    resp = client.post("/api/po/PO-001/approve", headers=MANAGER)

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
