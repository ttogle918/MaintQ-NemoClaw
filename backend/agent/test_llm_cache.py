# -*- coding: utf-8 -*-
"""LLM 응답 카세트 회귀 — **네트워크를 절대 타지 않는다** (D105).

최우선 목적은 "기능이 되는가"가 아니라 **"캐시가 지표를 조용히 오염시키지 않는가"** 다.
"""

from __future__ import annotations

import json
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


import asyncio  # noqa: E402


class _Boom:
    """네트워크가 호출되면 테스트를 깨뜨리는 스텁 — 히트 시 미접촉을 증명한다."""

    def stream(self, *, system, messages, tools):
        raise AssertionError("캐시가 있는데 inner 를 호출했다")


class _Fake:
    """고정 델타를 흘리는 스텁. 호출 횟수를 센다."""

    def __init__(self, deltas):
        self.deltas = deltas
        self.calls = 0

    def stream(self, *, system, messages, tools):
        self.calls += 1

        async def gen():
            for d in self.deltas:
                yield d

        return gen()


def _drain(client, **kw):
    async def go():
        return [d async for d in client.stream(**kw)]

    return asyncio.run(go())


_KW = dict(system="s", messages=[{"role": "user", "content": "q"}], tools=[])
_DELTAS = [("text", "답"), ("tool_use", ToolUse(id="t1", name="lookup_error_code",
                                                input={"model": "iG5A"})), ("end", "STOP")]


def test_miss_calls_inner_and_records(tmp_path):
    inner = _Fake(_DELTAS)
    c = lc.CachingClient(inner, provider="p", model="m", root=tmp_path)
    out = _drain(c, **_KW)
    assert inner.calls == 1
    assert c.last_hit is False and c.hits == 0 and c.misses == 1
    assert [k for k, _ in out] == ["text", "tool_use", "end"]
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_hit_does_not_touch_inner(tmp_path):
    _drain(lc.CachingClient(_Fake(_DELTAS), provider="p", model="m", root=tmp_path), **_KW)
    c = lc.CachingClient(_Boom(), provider="p", model="m", root=tmp_path)
    out = _drain(c, **_KW)
    assert c.last_hit is True and c.hits == 1 and c.misses == 0
    assert [k for k, _ in out] == ["text", "tool_use", "end"]
    assert out[1][1].name == "lookup_error_code"


def test_model_change_misses(tmp_path):
    _drain(lc.CachingClient(_Fake(_DELTAS), provider="p", model="m", root=tmp_path), **_KW)
    inner = _Fake(_DELTAS)
    c = lc.CachingClient(inner, provider="p", model="m-lite", root=tmp_path)
    _drain(c, **_KW)
    assert inner.calls == 1 and c.last_hit is False


def test_stats_line_reports_hit_rate(tmp_path):
    c = lc.CachingClient(_Fake(_DELTAS), provider="p", model="m", root=tmp_path)
    _drain(c, **_KW)
    line = c.stats_line()
    assert "0/1" in line and "0.0%" in line


def test_corrupted_schema_is_treated_as_miss(tmp_path):
    """`_schema` 가 다르면(구버전·다른 프로그램이 쓴 파일 등) 캐시가 있어도 미스로 취급한다
    (D62 — 모름을 통과로 바꾸지 않는다). 예외로 실행을 죽이지 않고 inner 로 폴백한다."""
    _drain(lc.CachingClient(_Fake(_DELTAS), provider="p", model="m", root=tmp_path), **_KW)
    [f] = list(tmp_path.glob("*.json"))
    record = json.loads(f.read_text(encoding="utf-8"))
    record["_schema"] = "bogus.v0"
    f.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

    inner = _Fake(_DELTAS)
    c = lc.CachingClient(inner, provider="p", model="m", root=tmp_path)
    out = _drain(c, **_KW)
    assert inner.calls == 1
    assert c.last_hit is False and c.hits == 0 and c.misses == 1
    assert [k for k, _ in out] == ["text", "tool_use", "end"]


def test_corrupted_deltas_not_a_list_is_treated_as_miss(tmp_path):
    _drain(lc.CachingClient(_Fake(_DELTAS), provider="p", model="m", root=tmp_path), **_KW)
    [f] = list(tmp_path.glob("*.json"))
    record = json.loads(f.read_text(encoding="utf-8"))
    record["deltas"] = "not-a-list"
    f.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

    inner = _Fake(_DELTAS)
    c = lc.CachingClient(inner, provider="p", model="m", root=tmp_path)
    out = _drain(c, **_KW)
    assert inner.calls == 1
    assert c.last_hit is False
    assert [k for k, _ in out] == ["text", "tool_use", "end"]


def test_corrupted_unknown_kind_is_treated_as_miss(tmp_path):
    """`decode_delta` 는 예상 밖 kind(예: None)에도 예외 없이 ("None", None) 을 돌려준다 —
    그 관용성이 손상된 캐시를 조용히 이상한 델타로 재생하지 않도록 로드 시점에서 kind
    화이트리스트({"text","tool_use","end"})를 검사한다."""
    _drain(lc.CachingClient(_Fake(_DELTAS), provider="p", model="m", root=tmp_path), **_KW)
    [f] = list(tmp_path.glob("*.json"))
    record = json.loads(f.read_text(encoding="utf-8"))
    record["deltas"][0]["kind"] = None
    f.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

    inner = _Fake(_DELTAS)
    c = lc.CachingClient(inner, provider="p", model="m", root=tmp_path)
    out = _drain(c, **_KW)
    assert inner.calls == 1
    assert c.last_hit is False
    assert [k for k, _ in out] == ["text", "tool_use", "end"]
