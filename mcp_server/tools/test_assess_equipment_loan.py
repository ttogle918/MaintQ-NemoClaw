# -*- coding: utf-8 -*-
"""assess_equipment_loan 테스트 — httpx.post 를 monkeypatch 로 모킹한다.

D15·D93: 이 파일도 도구 파일과 마찬가지로 A2A 자격증명·파트너 대장을 직접 참조하지 않는다.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from mcp_server.tools.assess_equipment_loan import assess_equipment_loan


class _FakeResponse:
    def __init__(self, status_code: int, json_data: Any = None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self) -> Any:
        if self._json_data is None:
            raise ValueError("no json body")
        return self._json_data


def _patch_post(monkeypatch: pytest.MonkeyPatch, *, response: _FakeResponse | None = None, exc: Exception | None = None):
    captured: dict = {}

    def fake_post(url: str, json: Any = None, timeout: float | None = None) -> _FakeResponse:
        captured.update(url=url, json=json, timeout=timeout)
        if exc is not None:
            raise exc
        assert response is not None
        return response

    monkeypatch.setattr(httpx, "post", fake_post)
    return captured


@pytest.mark.parametrize(
    "loan_amount,purpose,collateral_building_id",
    [
        (0, "설비교체", "BLD-1"),
        (-100, "설비교체", "BLD-1"),
        (1000, "   ", "BLD-1"),
        (1000, "설비교체", "  "),
    ],
)
def test_invalid_input_rejected(loan_amount, purpose, collateral_building_id):
    result = assess_equipment_loan(
        loan_amount=loan_amount, purpose=purpose, collateral_building_id=collateral_building_id
    )
    assert result["status"] == "error"
    assert result["reason"] == "invalid_input"


def test_success_completed_maps_to_ok(monkeypatch: pytest.MonkeyPatch):
    captured = _patch_post(
        monkeypatch,
        response=_FakeResponse(
            200,
            json_data={
                "status": "completed",
                "verdict": "APPROVED",
                "request_chain_id": "CHAIN-LOAN-1",
            },
        ),
    )

    result = assess_equipment_loan(
        loan_amount=50000000, purpose="설비교체", collateral_building_id="BLD-1"
    )

    assert result["status"] == "ok"
    assert result["skill_status"] == "completed"
    assert result["verdict"] == "APPROVED"
    assert result["request_chain_id"] == "CHAIN-LOAN-1"
    assert captured["url"].endswith("/api/a2a/assess-loan")
    assert captured["json"] == {
        "loan_amount": 50000000,
        "purpose": "설비교체",
        "collateral_building_id": "BLD-1",
    }


@pytest.mark.parametrize("skill_status", ["input-required", "rejected"])
def test_non_completed_skill_status_maps_to_no_answer(monkeypatch: pytest.MonkeyPatch, skill_status: str):
    _patch_post(monkeypatch, response=_FakeResponse(200, json_data={"status": skill_status}))

    result = assess_equipment_loan(
        loan_amount=1000, purpose="설비교체", collateral_building_id="BLD-1"
    )

    assert result["status"] == "error"
    assert result["reason"] == "no_answer"
    assert result["skill_status"] == skill_status


def test_unexpected_skill_status_maps_to_unexpected_status(monkeypatch: pytest.MonkeyPatch):
    _patch_post(monkeypatch, response=_FakeResponse(200, json_data={"status": "weird"}))

    result = assess_equipment_loan(
        loan_amount=1000, purpose="설비교체", collateral_building_id="BLD-1"
    )

    assert result["status"] == "error"
    assert result["reason"] == "unexpected_status"


def test_502_maps_to_upstream_unavailable_normal_path(monkeypatch: pytest.MonkeyPatch):
    """status.html 실측 — assess-loan 은 502/504 가 정상 경로다. 이걸 실패 취급하지 않고
    도구가 정직하게 status:error 를 반환하는지가 검증 대상이다."""
    _patch_post(monkeypatch, response=_FakeResponse(502, text="adapter down"))

    result = assess_equipment_loan(
        loan_amount=1000, purpose="설비교체", collateral_building_id="BLD-1"
    )

    assert result == {
        "status": "error",
        "reason": "upstream_unavailable",
        "message": "FinAllQ A2A 어댑터에 연결할 수 없습니다 (HTTP 502).",
    }


def test_circuit_open_is_not_upstream_unavailable(monkeypatch: pytest.MonkeyPatch):
    """503 은 «우리가 스스로 막았다»다 — 502 와 같은 이유로 뭉개지 않는다 (D136·D139).

    형제 `assess_used_equipment_loan` 이 이미 지키는 경계를 이쪽에도 옮긴다. 뭉개면
    에이전트가 «FinAllQ 가 죽었다»고 말하는데 실제로는 우리 차단기가 연 것이라,
    사용자에게 할 안내(잠시 후 재시도)가 통째로 달라진다.
    """
    _patch_post(monkeypatch, response=_FakeResponse(503, text="차단기가 열려 있습니다 (연속 실패 3회)"))

    result = assess_equipment_loan(
        loan_amount=1000, purpose="설비교체", collateral_building_id="BLD-1"
    )

    assert result["status"] == "error"
    assert result["reason"] == "circuit_open"
    assert result["reason"] != "upstream_unavailable"
    # 상대 장애가 아니라 우리 판단임이 사람 말에도 드러나야 한다
    assert "차단" in result["message"]


@pytest.mark.parametrize(
    ("status_code", "expected_reason"),
    [(502, "upstream_unavailable"), (504, "upstream_timeout")],
)
def test_gateway_statuses_keep_their_own_reason(
    monkeypatch: pytest.MonkeyPatch, status_code: int, expected_reason: str
):
    """502·504 는 서로도 구분한다 — 상대가 죽은 것과 시간이 다한 것은 다른 사건이다."""
    _patch_post(monkeypatch, response=_FakeResponse(status_code, text="adapter down"))

    result = assess_equipment_loan(
        loan_amount=1000, purpose="설비교체", collateral_building_id="BLD-1"
    )

    assert result["status"] == "error"
    assert result["reason"] == expected_reason


def test_timeout_maps_to_timeout(monkeypatch: pytest.MonkeyPatch):
    _patch_post(monkeypatch, exc=httpx.TimeoutException("timed out"))

    result = assess_equipment_loan(
        loan_amount=1000, purpose="설비교체", collateral_building_id="BLD-1"
    )

    assert result["status"] == "error"
    assert result["reason"] == "timeout"


def test_connection_refused_maps_to_backend_unreachable(monkeypatch: pytest.MonkeyPatch):
    _patch_post(monkeypatch, exc=httpx.ConnectError("refused"))

    result = assess_equipment_loan(
        loan_amount=1000, purpose="설비교체", collateral_building_id="BLD-1"
    )

    assert result["status"] == "error"
    assert result["reason"] == "backend_unreachable"


def test_other_status_code_maps_to_a2a_error(monkeypatch: pytest.MonkeyPatch):
    _patch_post(monkeypatch, response=_FakeResponse(400, json_data={"detail": "schema_validation_failed"}))

    result = assess_equipment_loan(
        loan_amount=1000, purpose="설비교체", collateral_building_id="BLD-1"
    )

    assert result["status"] == "error"
    assert result["reason"] == "a2a_error"
    assert result["message"] == "schema_validation_failed"


def test_200_with_invalid_json_body_maps_to_invalid_response(monkeypatch: pytest.MonkeyPatch):
    _patch_post(monkeypatch, response=_FakeResponse(200, json_data=None))

    result = assess_equipment_loan(
        loan_amount=1000, purpose="설비교체", collateral_building_id="BLD-1"
    )

    assert result["status"] == "error"
    assert result["reason"] == "invalid_response"


def test_base_url_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MAINTQ_BACKEND_BASE_URL", "http://example.local:9000/")
    captured = _patch_post(monkeypatch, response=_FakeResponse(200, json_data={"status": "completed"}))

    assess_equipment_loan(loan_amount=1000, purpose="설비교체", collateral_building_id="BLD-1")

    assert captured["url"] == "http://example.local:9000/api/a2a/assess-loan"
