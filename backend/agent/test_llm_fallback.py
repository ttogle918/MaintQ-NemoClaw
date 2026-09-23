# -*- coding: utf-8 -*-
"""nvidia provider 추가 + 제공자 자동 폴백 — **네트워크를 절대 타지 않는다**.

2026-08-29 LLM 제공자 통일(A2A_Q 설계 `2026-08-29-llm-provider-unification-design.md`).
기본 경로를 NVIDIA NIM 무료 티어로 두고, 그 경로가 죽으면 유료 OpenAI 로 자동 전환한다.

검증하는 것은 **클라이언트 조립과 전환 경계**뿐이다 — 실제 생성 품질은 여기 대상이 아니다.
`EliceClient` 생성자는 `AsyncOpenAI` 객체만 만들고 네트워크를 타지 않으므로 가짜 키로 안전하다.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.agent import llm  # noqa: E402

FAKE_KEY = "test-key-not-real"

_LLM_ENV = (
    "MAINTQ_LLM_PROVIDER",
    "MAINTQ_LLM_MODEL",
    "MAINTQ_LLM_FALLBACK_PROVIDER",
    "MAINTQ_LLM_FALLBACK_MODEL",
    "NVIDIA_API_KEY",
    "OPENAI_API_KEY",
    "MAINTQ_LLM_CACHE",
    "MAINTQ_SANDBOX",
    "NVIDIA_BASE_URL",
)


def _clear_llm_env(monkeypatch):
    """`.env` 가 이미 로드돼 있어도 이 테스트가 그 값에 좌우되지 않게 비운다."""
    for name in _LLM_ENV:
        monkeypatch.delenv(name, raising=False)


# ── Task 4 — nvidia provider ────────────────────────────────────────────────


def test_nvidia_is_a_known_provider():
    assert "nvidia" in llm.PROVIDERS


def test_elice_provider_is_not_removed():
    """D115 자산 유지 — nvidia 를 더한다고 elice 를 빼지 않는다."""
    assert "elice" in llm.PROVIDERS


def test_nvidia_client_uses_nim_base_url(monkeypatch):
    """EliceClient 가 `/v1` 을 붙이므로 여기서는 호스트까지만 넣는다 (llm.py:422-424)."""
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("MAINTQ_LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("MAINTQ_LLM_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("NVIDIA_API_KEY", FAKE_KEY)

    client = llm.get_client()

    assert isinstance(client, llm.EliceClient)
    assert str(client._client.base_url).rstrip("/") == "https://integrate.api.nvidia.com/v1"


def test_nvidia_base_url_has_no_double_v1(monkeypatch):
    """`/v1` 을 상수에 박아 두면 EliceClient 가 한 번 더 붙여 `/v1/v1` 이 된다.

    위 검사는 `rstrip("/")` 뒤 동등비교라 이미 이 사고를 잡지만, 실패했을 때
    **무엇이 틀렸는지**가 드러나지 않는다 — 그래서 음성 축을 따로 세운다.
    """
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("MAINTQ_LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("MAINTQ_LLM_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("NVIDIA_API_KEY", FAKE_KEY)

    assert "/v1/v1" not in str(llm.get_client()._client.base_url)


def test_nvidia_without_key_fails_loudly(monkeypatch):
    """키가 없으면 가짜 응답으로 대체하지 않고 실패한다 (D40)."""
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("MAINTQ_LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("MAINTQ_LLM_MODEL", "openai/gpt-oss-120b")

    with pytest.raises(RuntimeError, match="NVIDIA_API_KEY"):
        llm.get_client()


# ── Task 5 — FallbackClient ─────────────────────────────────────────────────


class FakeStatusError(Exception):
    """HTTP 상태를 실은 대역 예외 — 실제 openai SDK 예외를 흉내만 낸다."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class FakeClient:
    """`LlmClient` 대역 — 델타를 흘리다 지정 지점에서 예외를 던진다."""

    def __init__(self, deltas=(), *, exc=None, raise_after=None):
        self._deltas = list(deltas)
        self._exc = exc
        self._raise_after = raise_after
        self.calls = 0

    def stream(self, *, system, messages, tools):
        self.calls += 1

        async def gen():
            for i, d in enumerate(self._deltas):
                if self._raise_after is not None and i == self._raise_after:
                    raise self._exc or RuntimeError("stream broke")
                yield d
            if self._exc is not None and self._raise_after is None:
                raise self._exc

        return gen()


async def _drain(client):
    out = []
    async for d in client.stream(system="s", messages=[], tools=[]):
        out.append(d)
    return out


def _fallback(primary, secondary):
    return llm.FallbackClient(
        primary, secondary, primary_label="nvidia", fallback_label="openai"
    )


def test_fallback_client_satisfies_the_protocol():
    """래퍼가 LlmClient 자리에 그대로 들어가야 호출부가 안 바뀐다."""
    assert isinstance(_fallback(FakeClient(), FakeClient()), llm.LlmClient)


def test_primary_success_does_not_touch_fallback():
    primary = FakeClient([("text", "일차")])
    secondary = FakeClient([("text", "폴백")])

    assert asyncio.run(_drain(_fallback(primary, secondary))) == [("text", "일차")]
    assert primary.calls == 1
    assert secondary.calls == 0


def test_fallback_takes_over_before_first_delta():
    primary = FakeClient([], exc=FakeStatusError(401))
    secondary = FakeClient([("text", "폴백")])

    assert asyncio.run(_drain(_fallback(primary, secondary))) == [("text", "폴백")]
    assert secondary.calls == 1


def test_fallback_covers_unclassified_errors():
    """상태코드 없는 임의 예외도 폴백 대상이다 — 분류 실패로 사이트가 죽지 않게."""
    primary = FakeClient([], exc=RuntimeError("연결 실패"))
    secondary = FakeClient([("text", "폴백")])

    assert asyncio.run(_drain(_fallback(primary, secondary))) == [("text", "폴백")]


def test_no_fallback_after_first_delta():
    """이미 나간 델타 뒤에 다른 모델로 다시 쓰면 화면에 중복·모순 출력이 된다."""
    primary = FakeClient(
        [("text", "일"), ("text", "차")], raise_after=1, exc=FakeStatusError(500)
    )
    secondary = FakeClient([("text", "폴백")])

    with pytest.raises(FakeStatusError):
        asyncio.run(_drain(_fallback(primary, secondary)))
    assert secondary.calls == 0


def test_fallback_failure_propagates():
    """폴백까지 죽으면 예외를 그대로 올린다 — 빈 응답으로 삼키지 않는다 (D40 태도)."""
    primary = FakeClient([], exc=FakeStatusError(401))
    secondary = FakeClient([], exc=FakeStatusError(500))

    with pytest.raises(FakeStatusError):
        asyncio.run(_drain(_fallback(primary, secondary)))


def test_fallback_logs_provider_and_error_type_without_key(caplog):
    primary = FakeClient([], exc=FakeStatusError(401))
    secondary = FakeClient([("text", "폴백")])

    with caplog.at_level("WARNING", logger="backend.agent.llm"):
        asyncio.run(_drain(_fallback(primary, secondary)))

    assert "nvidia" in caplog.text and "openai" in caplog.text
    assert "FakeStatusError" in caplog.text
    # 예외 메시지·키가 새지 않는다 (D40) — 타입 이름만 남긴다
    assert FAKE_KEY not in caplog.text
    assert "status 401" not in caplog.text


def test_no_warning_when_primary_succeeds(caplog):
    """양성 축의 짝 — 성공 경로에서 경고가 나오면 로그가 무의미해진다."""
    with caplog.at_level("WARNING", logger="backend.agent.llm"):
        asyncio.run(_drain(_fallback(FakeClient([("text", "일차")]), FakeClient())))

    assert caplog.text == ""


def test_get_client_wraps_only_when_both_fallback_vars_set(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("MAINTQ_LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("MAINTQ_LLM_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("NVIDIA_API_KEY", FAKE_KEY)

    # 폴백 미설정 → 기존 동작
    assert not isinstance(llm.get_client(), llm.FallbackClient)

    # 하나만 설정 → 여전히 기존 동작 (절반만 켜지 않는다)
    monkeypatch.setenv("MAINTQ_LLM_FALLBACK_PROVIDER", "openai")
    assert not isinstance(llm.get_client(), llm.FallbackClient)

    # 둘 다 설정 → 폴백
    monkeypatch.setenv("MAINTQ_LLM_FALLBACK_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    assert isinstance(llm.get_client(), llm.FallbackClient)


def test_fallback_client_uses_its_own_model_not_the_primary(monkeypatch):
    """폴백은 자기 모델로 만들어져야 한다 — primary 모델을 물려받으면 안 된다.

    `_build_single_client` 가 모델을 인자로 받는 이유가 이것이다(전역 env 를
    잠시 바꿔 끼우는 방식은 쓰지 않는다).
    """
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("MAINTQ_LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("MAINTQ_LLM_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("NVIDIA_API_KEY", FAKE_KEY)
    monkeypatch.setenv("MAINTQ_LLM_FALLBACK_PROVIDER", "openai")
    monkeypatch.setenv("MAINTQ_LLM_FALLBACK_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)

    client = llm.get_client()

    assert client._primary._model == "openai/gpt-oss-120b"
    assert client._fallback._model == "gpt-4.1-mini"
    # 환경변수를 되돌려 놓았는가 (전역 상태를 남기지 않는다)
    import os as _os

    assert _os.environ["MAINTQ_LLM_MODEL"] == "openai/gpt-oss-120b"


# ── D143 — OpenShell 샌드박스 모드 ───────────────────────────────────────────


def _sandbox_env(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("MAINTQ_SANDBOX", "openshell")
    monkeypatch.setenv("MAINTQ_LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("MAINTQ_LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b")


def test_sandbox_routes_nvidia_to_inference_local_without_key(monkeypatch):
    """키 없이 기동하고 inference.local 로 보낸다 — 키는 게이트웨이에만 있다."""
    _sandbox_env(monkeypatch)
    client = llm.get_client()

    assert isinstance(client, llm.SandboxNoFallbackClient)
    inner = client._primary
    assert str(inner._client.base_url).rstrip("/") == "https://inference.local/v1"
    assert inner._client.api_key == llm.SANDBOX_PLACEHOLDER_KEY


def test_sandbox_refuses_to_start_when_key_is_inside(monkeypatch):
    _sandbox_env(monkeypatch)
    monkeypatch.setenv("NVIDIA_API_KEY", FAKE_KEY)

    with pytest.raises(RuntimeError, match="게이트웨이에만") as ei:
        llm.get_client()
    assert FAKE_KEY not in str(ei.value)


def test_sandbox_rejects_non_nvidia_provider(monkeypatch):
    _sandbox_env(monkeypatch)
    monkeypatch.setenv("MAINTQ_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)

    with pytest.raises(RuntimeError, match="샌드박스 정책상"):
        llm.get_client()


def test_sandbox_value_typo_is_rejected(monkeypatch):
    """오타가 조용히 "샌드박스 아님" 이 되지 않는다."""
    _sandbox_env(monkeypatch)
    monkeypatch.setenv("MAINTQ_SANDBOX", "openshel")

    with pytest.raises(RuntimeError, match="MAINTQ_SANDBOX"):
        llm.get_client()


def test_sandbox_does_not_build_fallback_even_when_configured(monkeypatch, caplog):
    _sandbox_env(monkeypatch)
    monkeypatch.setenv("MAINTQ_LLM_FALLBACK_PROVIDER", "openai")
    monkeypatch.setenv("MAINTQ_LLM_FALLBACK_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)

    with caplog.at_level("WARNING", logger="backend.agent.llm"):
        client = llm.get_client()

    assert isinstance(client, llm.SandboxNoFallbackClient)
    assert not isinstance(client._primary, llm.FallbackClient)
    assert "샌드박스 정책상 폴백 불가" in caplog.text


def _no_fallback(primary, fb="openai"):
    return llm.SandboxNoFallbackClient(primary, primary_label="nvidia", fallback_label=fb)


def test_sandbox_primary_failure_is_explicit_not_silent():
    with pytest.raises(llm.SandboxFallbackBlocked) as ei:
        asyncio.run(_drain(_no_fallback(FakeClient([], exc=FakeStatusError(403)))))

    msg = str(ei.value)
    assert "샌드박스 정책상 폴백(openai) 불가" in msg
    assert "FakeStatusError 403" in msg
    assert "status 403" not in msg  # 예외 본문은 싣지 않는다 (D40·D131)
    assert llm.stream_failure_message(ei.value) == msg


def test_sandbox_primary_success_passes_through():
    """양성 축 — 래퍼가 항상 실패로 망가져도 위 테스트는 통과하므로 짝을 둔다."""
    out = asyncio.run(_drain(_no_fallback(FakeClient([("text", "정상"), ("end", "stop")]))))
    assert out == [("text", "정상"), ("end", "stop")]


def test_sandbox_failure_after_first_delta_keeps_original_error():
    primary = FakeClient([("text", "a"), ("text", "b")], exc=FakeStatusError(500), raise_after=1)
    with pytest.raises(FakeStatusError):
        asyncio.run(_drain(_no_fallback(primary)))


def test_generic_failure_message_is_unchanged():
    assert llm.stream_failure_message(RuntimeError("x")) == "응답 생성에 실패했습니다. 다시 시도해 주세요."
    assert llm.stream_failure_message(None) == "응답 생성에 실패했습니다. 다시 시도해 주세요."


def test_nvidia_base_url_override_outside_sandbox(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("MAINTQ_LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("MAINTQ_LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b")
    monkeypatch.setenv("NVIDIA_API_KEY", FAKE_KEY)
    monkeypatch.setenv("NVIDIA_BASE_URL", "https://example.invalid")

    client = llm.get_client()
    assert str(client._client.base_url).rstrip("/") == "https://example.invalid/v1"
