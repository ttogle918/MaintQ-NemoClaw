# -*- coding: utf-8 -*-
"""LLM 응답 카세트 회귀 — **네트워크를 절대 타지 않는다** (D104).

최우선 목적은 "기능이 되는가"가 아니라 **"캐시가 지표를 조용히 오염시키지 않는가"** 다.
"""

from __future__ import annotations

import json
import subprocess
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


def _cache_files(tmp_path):
    """카세트 파일만 센다 — Task 7 이 같은 디렉터리에 사이드카 통계 파일
    (`_stats.json`)을 함께 쓰기 시작해서, 기존 `glob("*.json")` 카운트가 그대로면
    사이드카까지 카세트로 세어 깨진다. 카세트 키는 sha256 hex(64자) 파일명이라
    `_stats.json` 과 이름으로 구분된다."""
    return [p for p in tmp_path.glob("*.json") if p.name != lc.STATS_NAME]


def test_miss_calls_inner_and_records(tmp_path):
    inner = _Fake(_DELTAS)
    c = lc.CachingClient(inner, provider="p", model="m", root=tmp_path)
    out = _drain(c, **_KW)
    assert inner.calls == 1
    assert c.last_hit is False and c.hits == 0 and c.misses == 1
    assert [k for k, _ in out] == ["text", "tool_use", "end"]
    assert len(_cache_files(tmp_path)) == 1


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
    [f] = _cache_files(tmp_path)
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
    [f] = _cache_files(tmp_path)
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
    [f] = _cache_files(tmp_path)
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
    [f] = _cache_files(tmp_path)
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

    assert len(_cache_files(tmp_path)) == 0


from backend.agent.trace import TraceWriter  # noqa: E402


def test_trace_replay_marks_events_when_cached(tmp_path, monkeypatch):
    """히트 세션은 replay 표식이 붙어 eval/score.has_replay() 가 분모에서 뺀다 (D55).

    이 한 줄이 빠지면 캐시 히트가 지표에 **조용히** 섞인다 — 이 테스트가 그것만 본다.

    ⚠ **DB 까지는 검증하지 않는다.** `tmp_path / "t.db"` 는 스키마가 없는 빈 sqlite 파일이라
    `trace.tool_call(...)` 의 `TraceWriter._persist` 는 `traces` 테이블이 없어 예외를 삼키고
    `persist_errors` 를 올린 뒤 조용히 리턴한다(모듈 설계상 저장 실패가 스트림을 끊지 않는다).
    이 테스트가 보는 것은 **메모리상 `event.data`** 뿐이다 — 실제로 DB 행이 쓰였는지는
    검증하지 않는다. `assert trace.persist_errors == 0` 을 넣으면 이 테스트 자체가 (스키마가
    없으므로) 항상 실패해 목적과 다른 이유로 깨진다.
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

    단순 `in` 검사(문자열이 파일 어딘가에 있다)는 배선이 **잘못된 위치**로 옮겨져도
    통과한다 — 예를 들어 `last_hit` 판정을 `stream = _safe_stream(...)` 직후(=
    루프가 시작되기도 전이라 항상 이전 델타의 값을 읽는 자리)로 옮겨도 문자열
    자체는 여전히 파일에 있으므로 그대로 PASS 해버린다. 그래서 **위치(순서)** 를
    비교한다: `last_hit` 판정은 델타 소비 루프(`async for ... in stream:`) **안쪽**
    에서, 그리고 스트림 실패 분기(`if kind == "_stream_error"`)보다 **먼저** 읽혀야
    한다 — 그래야 그 턴의 첫 델타 처리 시점에 표식이 붙는다.
    """
    src = (ROOT / "backend" / "agent" / "loop.py").read_text(encoding="utf-8")
    anchors = [a for a in ("async def run_turn(", "_safe_stream(") if a in src]
    assert len(anchors) == 2, f"loop.py 앵커 {anchors} — 파일이 바뀌었거나 못 읽었다"
    assert "last_hit" in src, "run_turn 에 캐시 히트 → trace.replay 배선이 없다"
    assert "trace.replay = True" in src

    i_loop = src.index("async for kind, value in stream:")
    i_last_hit = src.index('getattr(llm, "last_hit"')
    i_stream_error = src.index('if kind == "_stream_error"')
    assert i_loop < i_last_hit < i_stream_error, (
        "last_hit 판정이 델타 소비 루프 안쪽 · 스트림 실패 분기보다 앞에 있어야 한다 "
        f"(loop={i_loop}, last_hit={i_last_hit}, stream_error={i_stream_error})"
    )


class _CachedHitLlm:
    """`last_hit=True` 로 고정된 페이크 LLM — 카세트 히트를 흉내낸다.

    `ScriptedClient`(backend/agent/llm.py)와 동작은 같지만(턴별 고정 델타를 흘린다)
    `CachingClient` 가 히트일 때 노출하는 `last_hit` 속성을 함께 흉내낸다. 실제
    `CachingClient` 를 쓰지 않는 이유는 이 테스트가 `run_turn` **배선**만 보면 되기
    때문이다 — 카세트 파일 IO 는 `llm_cache.py` 쪽 단위 테스트가 이미 덮는다.
    """

    def __init__(self, script):
        self._script = [list(turn) for turn in script]
        self.calls = 0
        self.last_hit = True

    def stream(self, *, system, messages, tools):
        deltas = self._script[self.calls]
        self.calls += 1

        async def gen():
            for d in deltas:
                yield d

        return gen()


class _FakeMcp:
    """`run_turn` 이 쓰는 최소 표면(`list_tools`/`call`)만 흉내낸다 — 네트워크 없음."""

    def __init__(self, responses):
        self.responses = responses

    async def list_tools(self):
        return [{"name": n, "description": n, "inputSchema": {}} for n in self.responses]

    async def call(self, tool, args=None, *, timeout=None):
        return self.responses.get(tool, {"status": "error", "reason": "unknown_tool"})


def test_run_turn_marks_tool_call_replay_on_cache_hit(tmp_path):
    """e2e — 기존 두 테스트는 판정식을 **재현**만 할 뿐이라 `loop.py` 의 배선이 통째로
    빠져도 통과한다. 이 테스트는 실제 `run_turn` 을 한 턴 돌려, `last_hit=True` 인
    LLM 으로 나온 `tool_call` 이벤트에 `replay: true` 가 실제로 실리는지 확인한다
    (`spikes/agent_loop_contract.py` 의 `FakeMcp`/`drive()` 하네스 방식을 따른다).
    """
    from backend.agent.loop import SessionStore, run_turn

    script = [
        [("tool_use", ToolUse(id="t1", name="lookup_error_code", input={"model": "iG5A"}))],
        [("text", "확인했습니다.")],
    ]
    llm = _CachedHitLlm(script)
    mcp = _FakeMcp({"lookup_error_code": {"status": "ok", "code": "OHT"}})
    trace = TraceWriter("sess-cache-e2e", db_path=tmp_path / "t.db")

    async def go():
        events = []
        async for ev in run_turn(
            session_id="sess-cache-e2e",
            message="테스트",
            equipment_id="INV-L1-01",
            user_id="tech-01",
            llm=llm,
            client=mcp,
            trace=trace,
            store=SessionStore(),
        ):
            events.append(ev)
        return events

    events = asyncio.run(go())

    assert trace.replay is True, "히트 세션인데 trace.replay 가 켜지지 않았다"
    tool_calls = [e for e in events if e.event == "tool_call"]
    assert tool_calls, f"tool_call 이벤트가 없다 — events={[e.event for e in events]}"
    assert all(e.data.get("replay") is True for e in tool_calls), (
        f"tool_call 이벤트에 replay:true 가 안 실렸다 — {[e.data for e in tool_calls]}"
    )


def test_reset_stats_then_read_is_zero(tmp_path):
    """`reset_stats()` 는 파일이 없어도 무동작이어야 한다(예외 없음)."""
    lc.reset_stats(root=tmp_path)
    assert lc.read_stats(root=tmp_path) == {"hits": 0, "misses": 0}


def test_miss_bumps_sidecar_misses(tmp_path):
    c = lc.CachingClient(_Fake(_DELTAS), provider="p", model="m", root=tmp_path)
    _drain(c, **_KW)
    assert lc.read_stats(root=tmp_path) == {"hits": 0, "misses": 1}


def test_hit_after_miss_bumps_sidecar_hits(tmp_path):
    _drain(lc.CachingClient(_Fake(_DELTAS), provider="p", model="m", root=tmp_path), **_KW)
    _drain(lc.CachingClient(_Boom(), provider="p", model="m", root=tmp_path), **_KW)
    assert lc.read_stats(root=tmp_path) == {"hits": 1, "misses": 1}


def test_stats_line_reads_sidecar_across_instances(tmp_path):
    """모듈 레벨 `stats_line()` 은 인스턴스가 갈려도(=다른 프로세스를 흉내) 사이드카에서
    누적치를 읽는다 — `CachingClient.stats_line()`(인스턴스 메서드)과는 다른 함수다."""
    _drain(lc.CachingClient(_Fake(_DELTAS), provider="p", model="m", root=tmp_path), **_KW)
    _drain(lc.CachingClient(_Boom(), provider="p", model="m", root=tmp_path), **_KW)
    line = lc.stats_line(root=tmp_path)
    assert "1/2" in line and "50.0%" in line


def test_sidecar_write_failure_does_not_break_streaming(tmp_path, monkeypatch):
    """사이드카 쓰기가 실패해도(예: 상위 경로가 디렉터리가 아님) 캐시 스트림 자체는
    정상 완주해야 한다 — 이건 계측이지 기능이 아니다."""
    blocker = tmp_path / "blocker"
    blocker.write_text("나는 파일이다 — 디렉터리가 아니다", encoding="utf-8")
    monkeypatch.setattr(lc, "stats_path", lambda root=None: blocker / lc.STATS_NAME)

    inner = _Fake(_DELTAS)
    c = lc.CachingClient(inner, provider="p", model="m", root=tmp_path)
    out = _drain(c, **_KW)
    assert inner.calls == 1
    assert [k for k, _ in out] == ["text", "tool_use", "end"]
    assert c.misses == 1  # 인스턴스 카운터는 사이드카 실패와 무관하게 정상 동작한다


def test_get_client_wraps_only_when_enabled(monkeypatch):
    """기본 꺼짐이면 감싸지 않는다 — 설정 안 하면 현재 동작 그대로."""
    from backend.agent import llm as llm_mod

    monkeypatch.setenv("MAINTQ_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("MAINTQ_LLM_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_API_KEY", "x" * 20)

    monkeypatch.delenv(lc.ENV_FLAG, raising=False)
    assert not isinstance(llm_mod.get_client(), lc.CachingClient)

    monkeypatch.setenv(lc.ENV_FLAG, "on")
    wrapped = llm_mod.get_client()
    assert isinstance(wrapped, lc.CachingClient)


def test_cache_dir_is_git_ignored():
    """`data/cache/`(카세트 저장 위치)가 git 추적에서 빠지는지 실측한다 (I2 · 스펙 §7-7).

    카세트 본문은 LLM 응답 원문이고 매뉴얼 인용문이 그대로 실릴 수 있다 — 되돌림을
    자동으로 잡을 회귀가 지금까지 pytest·spikes 어디에도 없었다.

    🔴 **양성 축을 함께 건다** (이 저장소 P30 규약) — `git check-ignore` 가 카세트 경로에
    대해 rc==0(제외됨)인 것 **그리고** 추적 대상 파일 하나에 대해 rc!=0(제외 안 됨)인
    것을 **둘 다** 확인한다. 부재(제외됨) 한쪽만 보면 `git` 이 없거나 rc 해석이 뒤집혀도
    조용히 통과한다 — 두 축을 함께 걸어야 "스캐너가 눈이 멀었다"와 "사실이 참이다"가
    구분된다.
    """
    ignored = subprocess.run(  # noqa: S603, S607 — 이 회귀 목적 자체가 로컬 git 검사다
        ["git", "check-ignore", "-q", "data/cache/llm/deadbeef.json"],
        cwd=ROOT,
        check=False,
    )
    tracked = subprocess.run(  # noqa: S603, S607
        ["git", "check-ignore", "-q", "backend/agent/llm_cache.py"],
        cwd=ROOT,
        check=False,
    )
    assert ignored.returncode == 0, (
        f"data/cache/ 가 git 추적에서 빠져야 한다 (rc={ignored.returncode})"
    )
    assert tracked.returncode != 0, (
        "양성 축 실패 — 추적 대상 파일도 rc!=0(제외됨)이면 이 검사가 아무것도 구분하지 "
        f"못한다는 뜻이다 (rc={tracked.returncode})"
    )
