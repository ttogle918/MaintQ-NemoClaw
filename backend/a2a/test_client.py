# -*- coding: utf-8 -*-
"""backend/a2a/client.py 테스트.

httpx.AsyncClient 는 실제 네트워크를 타지 않는다 — `_ScriptedAsyncClient` 로 대체해
호출 인자(url·headers·json)를 캡처하고 canned 응답/예외를 되돌려준다.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from backend.a2a.circuit import OPEN, registry
from backend.a2a.client import (
    A2ACircuitOpenError,
    A2AClientError,
    A2ATimeoutError,
    A2AUpstreamUnavailableError,
    call_skill,
)


@pytest.fixture(autouse=True)
def _reset_circuit():
    """차단기(P35)는 **프로세스 전역**이라 테스트 사이로 샌다.

    이 픽스처가 없으면 전송 실패를 다루는 테스트 3건이 차단기를 열어 버려,
    그 뒤 테스트들이 실제 매핑 대신 `A2ACircuitOpenError` 를 받는다
    (도입 당시 실제로 5건이 그렇게 깨졌다). 격리는 여기서 한 번만 한다.
    """
    registry().reset()
    yield
    registry().reset()


class _FakeResponse:
    def __init__(self, status_code: int, json_data: Any = None, text: str = "", json_error: bool = False):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self._json_error = json_error

    def json(self) -> Any:
        if self._json_error:
            raise ValueError("invalid json body")
        return self._json_data


class _ScriptedAsyncClient:
    """`httpx.AsyncClient(...)` 대역 — 생성자·post 호출 인자를 captured 에 기록한다."""

    def __init__(self, response: _FakeResponse | None = None, exc: Exception | None = None, captured: dict | None = None):
        self._response = response
        self._exc = exc
        self._captured = captured if captured is not None else {}

    def factory(self, **init_kwargs: Any) -> "_ScriptedAsyncClient":
        self._captured["init_kwargs"] = init_kwargs
        return self

    async def __aenter__(self) -> "_ScriptedAsyncClient":
        return self

    async def __aexit__(self, *exc_info: Any) -> bool:
        return False

    async def post(self, url: str, json: Any = None, headers: Any = None) -> _FakeResponse:
        self._captured.update(url=url, json=json, headers=headers)
        if self._exc is not None:
            raise self._exc
        assert self._response is not None
        return self._response


def _patch_client(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> dict:
    captured: dict = {}
    scripted = _ScriptedAsyncClient(captured=captured, **kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", scripted.factory)
    return captured


BASE_PAYLOAD = {"request_chain_id": "CHAIN-1", "amount": 1000}


@pytest.mark.asyncio
async def test_success_returns_parsed_json(monkeypatch: pytest.MonkeyPatch):
    captured = _patch_client(
        monkeypatch, response=_FakeResponse(200, json_data={"status": "completed"})
    )

    result = await call_skill(
        partner="finallq",
        skill_id="request-withdrawal",
        payload=BASE_PAYLOAD,
        request_chain_id="CHAIN-1",
        base_url="http://adapter.local",
    )

    assert result == {"status": "completed"}
    assert captured["url"] == "http://adapter.local/a2a/skills/request-withdrawal"
    assert captured["json"] == BASE_PAYLOAD
    assert captured["headers"]["X-Request-Chain-Id"] == "CHAIN-1"
    assert captured["headers"]["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_202_status_is_also_accepted(monkeypatch: pytest.MonkeyPatch):
    _patch_client(monkeypatch, response=_FakeResponse(202, json_data={"status": "input-required"}))
    result = await call_skill(
        partner="finallq",
        skill_id="request-withdrawal",
        payload=BASE_PAYLOAD,
        request_chain_id="CHAIN-1",
        base_url="http://adapter.local",
    )
    assert result == {"status": "input-required"}


@pytest.mark.asyncio
async def test_base_url_trailing_slash_is_stripped(monkeypatch: pytest.MonkeyPatch):
    captured = _patch_client(monkeypatch, response=_FakeResponse(200, json_data={}))
    await call_skill(
        partner="finallq",
        skill_id="request-withdrawal",
        payload=BASE_PAYLOAD,
        request_chain_id="CHAIN-1",
        base_url="http://adapter.local/",
    )
    assert captured["url"] == "http://adapter.local/a2a/skills/request-withdrawal"


@pytest.mark.asyncio
async def test_attaches_auth_header_when_partner_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FINALLQ_SERVICE_TOKEN", "tok-value")
    captured = _patch_client(monkeypatch, response=_FakeResponse(200, json_data={}))

    await call_skill(
        partner="finallq",
        skill_id="request-withdrawal",
        payload=BASE_PAYLOAD,
        request_chain_id="CHAIN-1",
        base_url="http://adapter.local",
    )

    assert captured["headers"]["Authorization"] == "Bearer tok-value"
    assert captured["headers"]["X-A2A-Partner-Id"] == "maintq-agent"


@pytest.mark.asyncio
async def test_missing_base_url_raises_value_error():
    with pytest.raises(ValueError, match="base_url"):
        await call_skill(
            partner="finallq",
            skill_id="request-withdrawal",
            payload=BASE_PAYLOAD,
            request_chain_id="CHAIN-1",
            base_url="",
        )


@pytest.mark.asyncio
async def test_missing_request_chain_id_raises_value_error():
    with pytest.raises(ValueError, match="request_chain_id"):
        await call_skill(
            partner="finallq",
            skill_id="request-withdrawal",
            payload=BASE_PAYLOAD,
            request_chain_id="",
            base_url="http://adapter.local",
        )


@pytest.mark.asyncio
async def test_chain_id_mismatch_between_header_and_body_raises():
    with pytest.raises(ValueError, match="mismatch"):
        await call_skill(
            partner="finallq",
            skill_id="request-withdrawal",
            payload={"request_chain_id": "CHAIN-BODY"},
            request_chain_id="CHAIN-HEADER",
            base_url="http://adapter.local",
        )


@pytest.mark.asyncio
async def test_timeout_exception_maps_to_a2a_timeout_error(monkeypatch: pytest.MonkeyPatch):
    _patch_client(monkeypatch, exc=httpx.TimeoutException("timed out"))
    with pytest.raises(A2ATimeoutError):
        await call_skill(
            partner="finallq",
            skill_id="request-withdrawal",
            payload=BASE_PAYLOAD,
            request_chain_id="CHAIN-1",
            base_url="http://adapter.local",
        )


@pytest.mark.asyncio
async def test_connect_error_maps_to_upstream_unavailable(monkeypatch: pytest.MonkeyPatch):
    _patch_client(monkeypatch, exc=httpx.ConnectError("refused"))
    with pytest.raises(A2AUpstreamUnavailableError):
        await call_skill(
            partner="finallq",
            skill_id="request-withdrawal",
            payload=BASE_PAYLOAD,
            request_chain_id="CHAIN-1",
            base_url="http://adapter.local",
        )


@pytest.mark.asyncio
async def test_other_transport_error_maps_to_upstream_unavailable(monkeypatch: pytest.MonkeyPatch):
    """TimeoutException·ConnectError 둘 다 아닌 httpx.HTTPError 계열(예: ReadError)도
    502 계열(A2AUpstreamUnavailableError)로 떨어져야 한다."""
    _patch_client(monkeypatch, exc=httpx.ReadError("connection reset"))
    with pytest.raises(A2AUpstreamUnavailableError):
        await call_skill(
            partner="finallq",
            skill_id="request-withdrawal",
            payload=BASE_PAYLOAD,
            request_chain_id="CHAIN-1",
            base_url="http://adapter.local",
        )


@pytest.mark.parametrize("status_code", [502, 503, 504])
@pytest.mark.asyncio
async def test_5xx_gateway_statuses_map_to_upstream_unavailable(
    monkeypatch: pytest.MonkeyPatch, status_code: int
):
    _patch_client(monkeypatch, response=_FakeResponse(status_code, text="adapter down"))
    with pytest.raises(A2AUpstreamUnavailableError) as excinfo:
        await call_skill(
            partner="finallq",
            skill_id="request-withdrawal",
            payload=BASE_PAYLOAD,
            request_chain_id="CHAIN-1",
            base_url="http://adapter.local",
        )
    assert excinfo.value.status_code == status_code


@pytest.mark.asyncio
async def test_other_status_codes_map_to_generic_client_error(monkeypatch: pytest.MonkeyPatch):
    _patch_client(monkeypatch, response=_FakeResponse(400, text="schema_validation_failed"))
    with pytest.raises(A2AClientError) as excinfo:
        await call_skill(
            partner="finallq",
            skill_id="request-withdrawal",
            payload=BASE_PAYLOAD,
            request_chain_id="CHAIN-1",
            base_url="http://adapter.local",
        )
    assert excinfo.value.status_code == 400
    assert not isinstance(excinfo.value, A2AUpstreamUnavailableError)


@pytest.mark.asyncio
async def test_forbidden_403_is_not_treated_as_upstream_unavailable(monkeypatch: pytest.MonkeyPatch):
    """FinAllQ 어댑터 리뷰에서 나온 교훈(403≠502)과 같은 취지 — 403을 502로 뭉개지 않는다."""
    _patch_client(monkeypatch, response=_FakeResponse(403, text="forbidden"))
    with pytest.raises(A2AClientError) as excinfo:
        await call_skill(
            partner="finallq",
            skill_id="request-withdrawal",
            payload=BASE_PAYLOAD,
            request_chain_id="CHAIN-1",
            base_url="http://adapter.local",
        )
    assert excinfo.value.status_code == 403
    assert not isinstance(excinfo.value, A2AUpstreamUnavailableError)


@pytest.mark.asyncio
async def test_200_with_invalid_json_body_raises_client_error(monkeypatch: pytest.MonkeyPatch):
    _patch_client(monkeypatch, response=_FakeResponse(200, json_error=True))
    with pytest.raises(A2AClientError):
        await call_skill(
            partner="finallq",
            skill_id="request-withdrawal",
            payload=BASE_PAYLOAD,
            request_chain_id="CHAIN-1",
            base_url="http://adapter.local",
        )


# --- 차단기 연동 (P35) --------------------------------------------------------


@pytest.mark.asyncio
async def test_circuit_opens_after_repeated_transport_failures(monkeypatch: pytest.MonkeyPatch):
    """연속 3회 도달 불가 → 4번째는 네트워크를 타지 않는다."""
    _patch_client(monkeypatch, exc=httpx.ConnectError("refused"))
    for _ in range(3):
        with pytest.raises(A2AUpstreamUnavailableError):
            await call_skill(
                partner="finallq",
                skill_id="request-withdrawal",
                payload=BASE_PAYLOAD,
                request_chain_id="CHAIN-1",
                base_url="http://adapter.local",
            )

    assert registry().snapshot("finallq")["state"] == OPEN

    captured = _patch_client(monkeypatch, exc=httpx.ConnectError("refused"))
    with pytest.raises(A2ACircuitOpenError) as excinfo:
        await call_skill(
            partner="finallq",
            skill_id="request-withdrawal",
            payload=BASE_PAYLOAD,
            request_chain_id="CHAIN-1",
            base_url="http://adapter.local",
        )
    assert excinfo.value.failure_count == 3
    assert excinfo.value.retry_after > 0
    # 핵심 단언: HTTP 를 **시도조차 하지 않았다** — 이게 타임아웃을 안 무는 이유다
    assert "post_kwargs" not in captured


@pytest.mark.asyncio
async def test_circuit_open_is_still_an_upstream_unavailable(monkeypatch: pytest.MonkeyPatch):
    """상속 관계 — 차단기를 모르는 기존 호출부도 안전하게 처리한다."""
    _patch_client(monkeypatch, exc=httpx.ConnectError("refused"))
    for _ in range(3):
        with pytest.raises(A2AUpstreamUnavailableError):
            await call_skill(
                partner="finallq",
                skill_id="request-withdrawal",
                payload=BASE_PAYLOAD,
                request_chain_id="CHAIN-1",
                base_url="http://adapter.local",
            )
    with pytest.raises(A2AUpstreamUnavailableError):
        await call_skill(
            partner="finallq",
            skill_id="request-withdrawal",
            payload=BASE_PAYLOAD,
            request_chain_id="CHAIN-1",
            base_url="http://adapter.local",
        )


@pytest.mark.asyncio
async def test_business_errors_do_not_open_the_circuit(monkeypatch: pytest.MonkeyPatch):
    """400 이 반복돼도 열지 않는다 — 상대는 살아 있고, 계약이 틀린 것이다.

    2026-08-24 assess-loan 계약 드리프트 때 실제로 400 이 반복됐는데,
    그때 같은 파트너의 request-withdrawal 은 정상 동작해야 했다.
    """
    _patch_client(monkeypatch, response=_FakeResponse(400, text="schema_validation_failed"))
    for _ in range(5):
        with pytest.raises(A2AClientError):
            await call_skill(
                partner="finallq",
                skill_id="assess-loan",
                payload=BASE_PAYLOAD,
                request_chain_id="CHAIN-1",
                base_url="http://adapter.local",
            )
    assert registry().snapshot("finallq")["state"] != OPEN

    # 같은 파트너의 다른 스킬은 계속 나간다
    _patch_client(monkeypatch, response=_FakeResponse(200, json_data={"status": "completed"}))
    res = await call_skill(
        partner="finallq",
        skill_id="request-withdrawal",
        payload=BASE_PAYLOAD,
        request_chain_id="CHAIN-1",
        base_url="http://adapter.local",
    )
    assert res == {"status": "completed"}


@pytest.mark.asyncio
async def test_one_partner_outage_does_not_block_the_other(monkeypatch: pytest.MonkeyPatch):
    """finallq 가 죽어도 insuq 약관 조회는 나간다 — 파트너 단위로 여는 이유."""
    _patch_client(monkeypatch, exc=httpx.ConnectError("refused"))
    for _ in range(3):
        with pytest.raises(A2AUpstreamUnavailableError):
            await call_skill(
                partner="finallq",
                skill_id="request-withdrawal",
                payload=BASE_PAYLOAD,
                request_chain_id="CHAIN-1",
                base_url="http://adapter.local",
            )

    _patch_client(monkeypatch, response=_FakeResponse(200, json_data={"status": "completed"}))
    res = await call_skill(
        partner="insuq",
        skill_id="lookup-clause",
        payload=BASE_PAYLOAD,
        request_chain_id="CHAIN-1",
        base_url="http://insuq-adapter.local",
    )
    assert res == {"status": "completed"}


@pytest.mark.asyncio
async def test_success_resets_the_failure_streak(monkeypatch: pytest.MonkeyPatch):
    """연속이 끊기면 다시 센다 — 누적이 아니라 연속이다."""
    _patch_client(monkeypatch, exc=httpx.ConnectError("refused"))
    for _ in range(2):
        with pytest.raises(A2AUpstreamUnavailableError):
            await call_skill(
                partner="finallq",
                skill_id="request-withdrawal",
                payload=BASE_PAYLOAD,
                request_chain_id="CHAIN-1",
                base_url="http://adapter.local",
            )

    _patch_client(monkeypatch, response=_FakeResponse(200, json_data={"status": "completed"}))
    await call_skill(
        partner="finallq",
        skill_id="request-withdrawal",
        payload=BASE_PAYLOAD,
        request_chain_id="CHAIN-1",
        base_url="http://adapter.local",
    )
    assert registry().snapshot("finallq")["failure_count"] == 0


@pytest.mark.asyncio
async def test_config_errors_do_not_touch_the_circuit():
    """base_url 누락은 우리 설정 문제다 — 상대 장애로 세면 안 된다."""
    with pytest.raises(ValueError):
        await call_skill(
            partner="finallq",
            skill_id="request-withdrawal",
            payload=BASE_PAYLOAD,
            request_chain_id="CHAIN-1",
            base_url="",
        )
    assert registry().snapshot("finallq")["failure_count"] == 0
