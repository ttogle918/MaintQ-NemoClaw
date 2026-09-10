# -*- coding: utf-8 -*-
"""assess_used_equipment_loan 테스트 (S13) — `httpx.post` 를 monkeypatch 로 모킹한다.

형제 `test_assess_equipment_loan.py` 와 같은 골격이지만 **한 축이 다르다**:
503(차단기)을 502·504 와 분리해 `circuit_open` 으로 돌려주는지 단언한다. D139 가
«상대가 죽었다»와 «우리가 스스로 막았다»를 갈라 놓았는데, 도구 층에서 다시 뭉개면
에이전트가 사용자에게 같은 말을 하게 된다.

D15·D93: 이 파일도 도구 파일과 마찬가지로 A2A 자격증명·파트너 대장을 참조하지 않는다.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from mcp_server.tools.assess_used_equipment_loan import assess_used_equipment_loan


class _FakeResponse:
    def __init__(self, status_code: int, json_data: Any = None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self) -> Any:
        if self._json_data is None:
            raise ValueError("no json body")
        return self._json_data


def _patch_post(
    monkeypatch: pytest.MonkeyPatch,
    *,
    response: _FakeResponse | None = None,
    exc: Exception | None = None,
) -> dict:
    captured: dict = {}

    def fake_post(url: str, json: Any = None, timeout: float | None = None) -> _FakeResponse:
        captured.update(url=url, json=json, timeout=timeout)
        if exc is not None:
            raise exc
        assert response is not None
        return response

    monkeypatch.setattr(httpx, "post", fake_post)
    return captured


_OK_BODY = {
    "status": "completed",
    "appraised_value": 24000000.0,
    "decision": "approved",
    "collateral_check": {
        "coverage_amount": 500000000.0,
        "insured_value": 500000000.0,
        "effective_recovery": 24000000.0,
        "sufficient": True,
    },
    "request_chain_id": "CHAIN-UELOAN-ff296e3a",
}


def test_success_passes_partner_fields_through(monkeypatch: pytest.MonkeyPatch):
    """상대가 준 값을 그대로 올린다 — 여기서 문장을 만들면 도구가 주지 않은 정보가 섞인다."""
    _patch_post(monkeypatch, response=_FakeResponse(200, json_data=_OK_BODY))

    out = assess_used_equipment_loan(asset_id="AST-L4-CONV", loan_amount=3_000_000)

    assert out["status"] == "ok"
    assert out["skill_status"] == "completed"
    assert out["appraised_value"] == 24000000.0
    assert out["decision"] == "approved"
    # 비례보상 3필드가 S13 을 S8 과 구별짓는 것이다 — 통째로 보존한다
    assert out["collateral_check"]["sufficient"] is True
    assert out["collateral_check"]["effective_recovery"] == 24000000.0


def test_request_is_asset_based_and_carries_no_cost(monkeypatch: pytest.MonkeyPatch):
    """자산 기반 호출이다 — 원가·건물·연식은 **백엔드 빌더**가 파생한다 (D138).

    도구가 원가를 실어 보내면 모델이 그 값을 지어낼 자리가 생긴다. 부재 검사이므로
    양성 축(URL·필수 2필드)을 함께 단언한다.
    """
    captured = _patch_post(monkeypatch, response=_FakeResponse(200, json_data=_OK_BODY))

    assess_used_equipment_loan(asset_id="AST-L4-CONV", loan_amount=3_000_000)

    assert captured["url"].endswith("/api/a2a/assess-used-equipment-loan")
    assert captured["json"]["asset_id"] == "AST-L4-CONV"
    assert captured["json"]["loan_amount"] == 3_000_000
    for absent in ("original_cost", "collateral_building_id", "equipment_year", "inspection_data"):
        assert absent not in captured["json"]


def test_circuit_open_is_not_upstream_unavailable(monkeypatch: pytest.MonkeyPatch):
    """503 은 «우리가 스스로 막았다»다 — 502 와 같은 이유로 뭉개지 않는다 (D136·D139).

    사용자에게 할 말이 다르다: *"상대가 응답하지 않습니다"* 와
    *"연속 실패로 잠시 차단된 상태입니다"* 는 같은 안내가 아니다.
    """
    _patch_post(monkeypatch, response=_FakeResponse(503, text="차단기가 열려 있습니다 (연속 실패 3회)"))

    out = assess_used_equipment_loan(asset_id="AST-L4-CONV", loan_amount=3_000_000)

    assert out["status"] == "error"
    assert out["reason"] == "circuit_open"
    assert out["reason"] != "upstream_unavailable"


@pytest.mark.parametrize(
    "status_code,reason",
    [(502, "upstream_unavailable"), (504, "upstream_timeout")],
)
def test_gateway_statuses_keep_their_own_reason(
    monkeypatch: pytest.MonkeyPatch, status_code: int, reason: str
):
    """502·504 는 서로도 구분한다 — 상대가 죽은 것과 시간이 다한 것은 다른 사건이다."""
    _patch_post(monkeypatch, response=_FakeResponse(status_code, text="upstream"))

    out = assess_used_equipment_loan(asset_id="AST-L4-CONV", loan_amount=3_000_000)

    assert out["status"] == "error"
    assert out["reason"] == reason


def test_400_carries_backend_detail(monkeypatch: pytest.MonkeyPatch):
    """없는 자산·조립 단계 차단은 400 이다. 백엔드가 준 사유를 그대로 올린다."""
    _patch_post(
        monkeypatch,
        response=_FakeResponse(400, json_data={"detail": "알 수 없는 asset_id: AST-NOPE"}),
    )

    out = assess_used_equipment_loan(asset_id="AST-NOPE", loan_amount=3_000_000)

    assert out["status"] == "error"
    assert out["reason"] == "a2a_error"
    assert "AST-NOPE" in out["message"]


@pytest.mark.parametrize(
    "asset_id,loan_amount",
    [("", 3_000_000), ("   ", 3_000_000), ("AST-L4-CONV", 0), ("AST-L4-CONV", -1), ("AST-L4-CONV", True)],
)
def test_invalid_input_is_rejected_before_the_network(
    monkeypatch: pytest.MonkeyPatch, asset_id: str, loan_amount: Any
):
    """인자가 틀리면 네트워크를 타지 않는다 — 상대에게 빈 값을 보내지 않는다.

    ⚠ `True` 는 파이썬에서 `isinstance(True, int)` 라 금액으로 새기 쉽다. 명시적으로 막는다.
    """
    captured = _patch_post(monkeypatch, response=_FakeResponse(200, json_data=_OK_BODY))

    out = assess_used_equipment_loan(asset_id=asset_id, loan_amount=loan_amount)

    assert out["status"] == "error"
    assert out["reason"] == "invalid_input"
    # 양성 축 — 호출 자체가 없었음을 캡처 부재로 확인한다(정상 경로에서는 url 이 찍힌다)
    assert "url" not in captured


def test_backend_unreachable_is_distinct_from_partner_failure(monkeypatch: pytest.MonkeyPatch):
    """백엔드 프로세스에 못 닿은 것과 A2A 파트너 실패는 다른 사건이다."""
    _patch_post(monkeypatch, exc=httpx.ConnectError("refused"))

    out = assess_used_equipment_loan(asset_id="AST-L4-CONV", loan_amount=3_000_000)

    assert out["status"] == "error"
    assert out["reason"] == "backend_unreachable"


def test_client_timeout_is_reported_as_timeout(monkeypatch: pytest.MonkeyPatch):
    """도구 자신의 타임아웃 — 상대의 504 와 구분한다 (D139 와 같은 경계)."""
    _patch_post(monkeypatch, exc=httpx.TimeoutException("timed out"))

    out = assess_used_equipment_loan(asset_id="AST-L4-CONV", loan_amount=3_000_000)

    assert out["status"] == "error"
    assert out["reason"] == "timeout"


def test_description_forbids_calling_it_an_approval():
    """`decision:"approved"` 는 **담보 조건 판정**이지 여신 승인이 아니다.

    상대 백엔드의 `Loan.status` 는 `UNDER_REVIEW` 로 남고 실제 결재는 사람이 한다.
    모델이 *"대출이 승인됐습니다"* 라고 말하면 화면·장부가 그 말을 배신한다 —
    도구 설명이 그 경계를 먼저 못박는다.
    """
    from mcp_server.tools.assess_used_equipment_loan import DESCRIPTION

    assert "여신 승인" in DESCRIPTION
    assert "담보" in DESCRIPTION
    # 양성 축 — 설명이 비어 있거나 짧아서 통과한 것이 아니다
    assert len(DESCRIPTION) > 120
