# -*- coding: utf-8 -*-
"""LLM 응답 카세트 회귀 — **네트워크를 절대 타지 않는다** (D105).

최우선 목적은 "기능이 되는가"가 아니라 **"캐시가 지표를 조용히 오염시키지 않는가"** 다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

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


def test_corrupted_utf8_bytes_is_treated_as_miss(tmp_path):
    """캐시 파일 바이트가 깨져 UTF-8 디코딩이 실패해도 예외가 새지 않고 미스로
    폴백해야 한다 — `UnicodeDecodeError` 는 `OSError` 의 하위 클래스가 아니다."""
    _drain(lc.CachingClient(_Fake(_DELTAS), provider="p", model="m", root=tmp_path), **_KW)
    [f] = list(tmp_path.glob("*.json"))
    f.write_bytes(b"\xff\xfe\x00invalid")

    inner = _Fake(_DELTAS)
    c = lc.CachingClient(inner, provider="p", model="m", root=tmp_path)
    out = _drain(c, **_KW)
    assert inner.calls == 1
    assert c.last_hit is False
    assert [k for k, _ in out] == ["text", "tool_use", "end"]


def test_interrupted_stream_is_not_cached(tmp_path):
    """도중에 끊긴 스트림은 캐시 파일로 남지 않아야 한다 — 잘린 응답이 다음 실행에서
    "정상"으로 재생되면 안 된다."""

    class _Interrupted:
        def stream(self, *, system, messages, tools):
            async def gen():
                yield ("text", "일부")
                raise RuntimeError("연결 끊김")

            return gen()

    c = lc.CachingClient(_Interrupted(), provider="p", model="m", root=tmp_path)

    async def go():
        out = []
        async for d in c.stream(**_KW):
            out.append(d)

    with pytest.raises(RuntimeError):
        asyncio.run(go())

    assert len(list(tmp_path.glob("*.json"))) == 0


from backend.agent.trace import TraceWriter  # noqa: E402


def test_trace_replay_marks_events_when_cached(tmp_path, monkeypatch):
    """히트 세션은 replay 표식이 붙어 eval/score.has_replay() 가 분모에서 뺀다 (D55).

    이 한 줄이 빠지면 캐시 히트가 지표에 **조용히** 섞인다 — 이 테스트가 그것만 본다.
    """
    trace = TraceWriter("sess-cache-test", db_path=tmp_path / "t.db")
    assert trace.replay is False

    _drain(lc.CachingClient(_Fake(_DELTAS), provider="p", model="m", root=tmp_path), **_KW)
    cached = lc.CachingClient(_Boom(), provider="p", model="m", root=tmp_path)
    _drain(cached, **_KW)

    # run_turn 이 하는 것과 같은 판정 — 히트면 켠다
    if getattr(cached, "last_hit", False):
        trace.replay = True

    assert trace.replay is True
    event = trace.tool_call("lookup_error_code", {"model": "iG5A"})
    assert event.data.get("replay") is True


def test_loop_wires_replay_marker():
    """`loop.py` 에 배선이 실제로 있는가 — 양성 축(앵커)을 함께 건다 (P30).

    부재 검사가 아니라 **존재 검사**이지만, 파일을 못 읽었을 때 조용히 통과하지 않도록
    앵커를 함께 본다.
    """
    src = (ROOT / "backend" / "agent" / "loop.py").read_text(encoding="utf-8")
    anchors = [a for a in ("async def run_turn(", "_safe_stream(") if a in src]
    assert len(anchors) == 2, f"loop.py 앵커 {anchors} — 파일이 바뀌었거나 못 읽었다"
    assert "last_hit" in src, "run_turn 에 캐시 히트 → trace.replay 배선이 없다"
    assert "trace.replay = True" in src
