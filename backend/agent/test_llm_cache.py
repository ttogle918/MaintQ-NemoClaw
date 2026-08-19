# -*- coding: utf-8 -*-
"""LLM 응답 카세트 회귀 — **네트워크를 절대 타지 않는다** (D105).

최우선 목적은 "기능이 되는가"가 아니라 **"캐시가 지표를 조용히 오염시키지 않는가"** 다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.agent.llm import ToolUse  # noqa: E402
from backend.agent import llm_cache as lc  # noqa: E402


def test_cache_disabled_by_default(monkeypatch):
    """기본 꺼짐 — 설정하지 않으면 현재 동작이 그대로여야 한다 (D40 태도)."""
    monkeypatch.delenv(lc.ENV_FLAG, raising=False)
    assert lc.cache_enabled() is False


def test_cache_enabled_only_for_exact_on(monkeypatch):
    for value, expected in (("on", True), ("ON", True), ("  on  ", True),
                            ("", False), ("1", False), ("true", False), ("off", False)):
        monkeypatch.setenv(lc.ENV_FLAG, value)
        assert lc.cache_enabled() is expected, f"{value!r} → {expected}"


def test_key_includes_model_and_provider():
    """모델을 바꾸면 반드시 미스가 나야 한다 — flash 응답을 flash-lite 결과로 착각하지 않게."""
    base = dict(system="s", messages=[{"role": "user", "content": "q"}], tools=[])
    k1 = lc.cache_key(provider="gemini", model="gemini-2.5-flash", **base)
    k2 = lc.cache_key(provider="gemini", model="gemini-2.5-flash-lite", **base)
    k3 = lc.cache_key(provider="anthropic", model="gemini-2.5-flash", **base)
    assert k1 != k2 and k1 != k3 and k2 != k3
    assert lc.cache_key(provider="gemini", model="gemini-2.5-flash", **base) == k1


def test_key_is_order_stable_but_content_sensitive():
    a = lc.cache_key(provider="p", model="m", system="s",
                     messages=[{"role": "user", "content": "q"}], tools=[{"name": "t"}])
    b = lc.cache_key(provider="p", model="m", system="s",
                     messages=[{"content": "q", "role": "user"}], tools=[{"name": "t"}])
    c = lc.cache_key(provider="p", model="m", system="s",
                     messages=[{"role": "user", "content": "다름"}], tools=[{"name": "t"}])
    assert a == b, "키 순서만 다른 동일 입력은 같은 키여야 한다"
    assert a != c


def test_delta_roundtrip_all_three_kinds():
    """text · tool_use · end 3종 전부 왕복 동일 — ToolUse 필드가 보존돼야 한다."""
    deltas = [
        ("text", "안녕"),
        ("tool_use", ToolUse(id="tu_1", name="lookup_error_code",
                             input={"model": "iG5A", "code": "OCT"})),
        ("end", "STOP"),
    ]
    back = [lc.decode_delta(lc.encode_delta(d)) for d in deltas]
    assert back[0] == ("text", "안녕")
    assert back[2] == ("end", "STOP")
    kind, tu = back[1]
    assert kind == "tool_use"
    assert (tu.id, tu.name, tu.input) == ("tu_1", "lookup_error_code",
                                          {"model": "iG5A", "code": "OCT"})
