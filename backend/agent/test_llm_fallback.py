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
