# -*- coding: utf-8 -*-
"""search_insurance_clause 테스트 — httpx.post 를 monkeypatch 로 모킹한다.

D15·D93: 이 파일도 도구 파일과 마찬가지로 A2A 자격증명·파트너 대장을 직접 참조하지 않는다.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from mcp_server.tools.search_insurance_clause import search_insurance_clause


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


def test_blank_question_returns_question_required():
    result = search_insurance_clause(question="   ")
    assert result == {
        "status": "error",
        "reason": "question_required",
        "message": "question 이 비어 있습니다.",
    }


def test_success_completed_maps_to_ok(monkeypatch: pytest.MonkeyPatch):
    captured = _patch_post(
        monkeypatch,
        response=_FakeResponse(
            200,
            json_data={
                "status": "completed",
                "verdict": "COVERED",
                "answer": "화재로 인한 인버터 손해는 보장됩니다.",
                "evidence": ["제3조 화재손해"],
                "request_chain_id": "CHAIN-CLAUSE-1",
            },
        ),
    )

    result = search_insurance_clause(question="화재로 인한 인버터 손해가 보장되나요?")

    assert result["status"] == "ok"
    assert result["skill_status"] == "completed"
    assert result["verdict"] == "COVERED"
    assert result["answer"] == "화재로 인한 인버터 손해는 보장됩니다."
    assert result["evidence"] == ["제3조 화재손해"]
    assert result["request_chain_id"] == "CHAIN-CLAUSE-1"
    assert captured["url"].endswith("/api/a2a/lookup-clause")
    assert captured["json"] == {"question": "화재로 인한 인버터 손해가 보장되나요?"}


@pytest.mark.parametrize("skill_status", ["input-required", "rejected"])
def test_non_completed_skill_status_maps_to_no_answer(monkeypatch: pytest.MonkeyPatch, skill_status: str):
    _patch_post(monkeypatch, response=_FakeResponse(200, json_data={"status": skill_status}))

    result = search_insurance_clause(question="보장되나요?")

    assert result["status"] == "error"
    assert result["reason"] == "no_answer"
    assert result["skill_status"] == skill_status


def test_unexpected_skill_status_maps_to_unexpected_status(monkeypatch: pytest.MonkeyPatch):
    _patch_post(monkeypatch, response=_FakeResponse(200, json_data={"status": "weird"}))

    result = search_insurance_clause(question="보장되나요?")

    assert result["status"] == "error"
    assert result["reason"] == "unexpected_status"
    assert result["skill_status"] == "weird"


def test_502_maps_to_upstream_unavailable(monkeypatch: pytest.MonkeyPatch):
    _patch_post(monkeypatch, response=_FakeResponse(502, text="adapter down"))

    result = search_insurance_clause(question="보장되나요?")

    assert result == {
        "status": "error",
        "reason": "upstream_unavailable",
        "message": "InsuQ A2A 어댑터에 연결할 수 없습니다 (HTTP 502).",
    }


@pytest.mark.parametrize("status_code", [503, 504])
def test_other_5xx_gateway_statuses_map_to_upstream_unavailable(monkeypatch: pytest.MonkeyPatch, status_code: int):
    _patch_post(monkeypatch, response=_FakeResponse(status_code, text="adapter down"))

    result = search_insurance_clause(question="보장되나요?")

    assert result["status"] == "error"
    assert result["reason"] == "upstream_unavailable"


def test_timeout_maps_to_timeout(monkeypatch: pytest.MonkeyPatch):
    _patch_post(monkeypatch, exc=httpx.TimeoutException("timed out"))

    result = search_insurance_clause(question="보장되나요?")

    assert result["status"] == "error"
    assert result["reason"] == "timeout"


def test_connection_refused_maps_to_backend_unreachable(monkeypatch: pytest.MonkeyPatch):
    _patch_post(monkeypatch, exc=httpx.ConnectError("refused"))

    result = search_insurance_clause(question="보장되나요?")

    assert result["status"] == "error"
    assert result["reason"] == "backend_unreachable"


def test_other_status_code_maps_to_a2a_error(monkeypatch: pytest.MonkeyPatch):
    _patch_post(monkeypatch, response=_FakeResponse(400, json_data={"detail": "schema_validation_failed"}))

    result = search_insurance_clause(question="보장되나요?")

    assert result["status"] == "error"
    assert result["reason"] == "a2a_error"
    assert result["message"] == "schema_validation_failed"


def test_200_with_invalid_json_body_maps_to_invalid_response(monkeypatch: pytest.MonkeyPatch):
    _patch_post(monkeypatch, response=_FakeResponse(200, json_data=None))

    result = search_insurance_clause(question="보장되나요?")

    assert result["status"] == "error"
    assert result["reason"] == "invalid_response"


def test_base_url_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MAINTQ_BACKEND_BASE_URL", "http://example.local:9000/")
    captured = _patch_post(monkeypatch, response=_FakeResponse(200, json_data={"status": "completed"}))

    search_insurance_clause(question="보장되나요?")

    assert captured["url"] == "http://example.local:9000/api/a2a/lookup-clause"
