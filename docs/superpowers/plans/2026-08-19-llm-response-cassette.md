# LLM 응답 카세트 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 반복 실행 시 LLM 응답만 재생해 백엔드 검증(`/scenario-smoke`·curl·`/run-eval --replay`)을 빠르게 한다. 도구 실행·DB 쓰기·SSE 발행은 진짜로 돈다.

**Architecture:** `LlmClient` 프로토콜을 구현하는 데코레이터 `CachingClient(inner)` 하나를 `get_client()` 가 마지막에 감싼다. 캐시 히트는 **D55 재생 표식**을 달아 기존 `has_replay()` 기계장치가 지표 분모에서 자동 제외한다. 저장은 `data/cache/llm/<key>.json`(git 미추적).

**Tech Stack:** Python 3.11+ · 표준 라이브러리만(`hashlib`·`json`·`os`) · pytest(테스트는 `asyncio.run()` 으로 동기 실행 — `pytest-asyncio` 의존성을 추가하지 않는다)

**설계 근거:** [`docs/superpowers/specs/2026-08-19-llm-response-cassette-design.md`](../specs/2026-08-19-llm-response-cassette-design.md) (사용자 승인 완료)

## Global Constraints

- **기본 꺼짐.** `MAINTQ_LLM_CACHE` 가 정확히 `"on"`(대소문자 무시, 앞뒤 공백 제거) 일 때만 동작한다. 그 밖의 값·빈 값·미설정은 전부 꺼짐 (D40 태도 · D56 선례)
- **네트워크 코드 0.** `llm_cache.py` 는 HTTP 클라이언트를 임포트하지 않는다. 그 라이브러리 **이름을 주석·독스트링에도 적지 않는다** — 부분문자열 스캐너가 주석만 보고 FAIL 한 전례가 있다(`spikes/law_fetch_contract.py ⓓ-2` 가 `sha256` 으로 같은 함정을 기록)
- **캐시 디렉터리는 git 미추적.** `data/cache/` 를 `.gitignore` 에 넣는다. `data/external/store.py`(D103)를 재사용하지 않는다 — 그건 git 추적·append-only 외부 원본용이라 성격이 정반대다
- **시각은 UTC** (D39). 파일 계층이므로 `.isoformat()`(`+00:00`) 을 쓴다 — `...Z` 는 API 전송 규정이다
- **line-length 100** (`pyproject.toml [tool.ruff]`). 정적 게이트는 `uv run ruff check` 다. `ruff format` 은 돌리지 않는다(레포에 기존 드리프트가 있어 무관한 줄이 대량으로 섞인다)
- **커밋 메시지 꼬리**: 이 브랜치는 Sprint 13 작업과 섞여 있다. 카세트 커밋은 본문 마지막에 `카세트 / Task N` 을 넣어 `git log --grep=카세트` 로 갈라 읽을 수 있게 한다
- **D 번호**: 스펙은 `D105` 를 예약했다. 착수 시 `docs/10_DECISIONS.md` 의 실제 마지막 번호를 확인할 것 — 현재 `D103` 까지이고 `D104` 는 Sprint 13 Stage 2(MQ-1307)가 선점했다

---

## File Structure

| 파일 | 책임 | 상태 |
|---|---|---|
| `backend/agent/llm_cache.py` | 캐시 키 계산 · 델타 직렬화 · `CachingClient` 데코레이터 · 히트율 집계 | **신규** |
| `backend/agent/test_llm_cache.py` | 위 모듈의 회귀 7건 | **신규** |
| `backend/agent/llm.py` | `get_client()` 가 마지막에 `CachingClient` 로 감싼다 | 수정(≤10줄) |
| `backend/agent/loop.py` | 델타 루프 첫 회차에서 `last_hit` → `trace.replay = True` | 수정(3줄) |
| `.gitignore` | `data/cache/` 제외 | 수정(2줄) |
| `eval/run_eval.py` | `--replay` 플래그 → 캐시 켜고 실행 | 수정 |
| `docs/10_DECISIONS.md` | D105 등재 | 수정(1행) |
| `CLAUDE.md` | pytest 커맨드·건수 갱신 | 수정 |

---

## Task 1: 캐시 모듈 — 키·직렬화·활성화 판정

순수 함수만 만든다. `CachingClient` 는 Task 2 다 — 이 셋이 먼저 서야 클라이언트가 기댈 바닥이 생긴다.

**Files:**
- Create: `backend/agent/llm_cache.py`
- Test: `backend/agent/test_llm_cache.py`

**Interfaces:**
- Consumes: `backend.agent.llm.LlmDelta`(`tuple[str, object]`) · `backend.agent.llm.ToolUse`(`id`·`name`·`input` 데이터클래스)
- Produces: `cache_enabled() -> bool` · `cache_key(*, provider: str, model: str, system: str, messages: list[dict], tools: list[dict]) -> str` · `encode_delta(delta: LlmDelta) -> dict` · `decode_delta(raw: dict) -> LlmDelta` · `CACHE_ROOT: Path` · `ENV_FLAG: str`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/agent/test_llm_cache.py` 신규:

```python
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
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run --with pytest python -m pytest backend/agent/test_llm_cache.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.agent.llm_cache'`

- [ ] **Step 3: 최소 구현**

`backend/agent/llm_cache.py` 신규:

```python
# -*- coding: utf-8 -*-
"""LLM 응답 카세트 — 개발 가속용 응답 캐시 (D105 · 설계 스펙 2026-08-19).

**기본 꺼짐.** `MAINTQ_LLM_CACHE=on` 일 때만 동작한다 — D40 이 *"테스트용 스크립트 응답으로
자동 대체하지 않는다(가짜 응답을 진짜로 착각하는 사고를 막기 위해)"* 라고 정한 태도를 따라
명시적 옵트인으로 둔다.

**이 모듈은 네트워크를 타지 않는다.** 실제 호출은 감싸인 `inner` 가 한다.

**캐시 히트는 D55 재생이다.** `CachingClient.last_hit` 을 `run_turn` 이 읽어
`trace.replay = True` 로 켜고, 그러면 `eval/score.py:has_replay()` 가 그 세션을 지표
분모에서 제외한다. **그 한 줄이 빠지면 히트가 지표에 조용히 섞인다** — 이 설계에서 가장
빠뜨리기 쉬운 지점이라 회귀가 따로 그것만 본다.

저장은 `data/cache/llm/<key>.json` 이고 **git 미추적**이다. 언제 지워도 된다.
`data/external/store.py`(D103)를 쓰지 않는다 — 그건 git 추적·append-only 외부 원본용이라
성격이 정반대다.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Final

from backend.agent.llm import LlmDelta, ToolUse

ENV_FLAG: Final[str] = "MAINTQ_LLM_CACHE"
CACHE_ROOT: Final[Path] = Path(__file__).resolve().parents[2] / "data" / "cache" / "llm"
SCHEMA: Final[str] = "maintq.llmcache.v1"


def cache_enabled() -> bool:
    """`MAINTQ_LLM_CACHE` 가 정확히 `on` 일 때만 True. 빈 값·미설정은 꺼짐(D56 선례)."""
    return (os.environ.get(ENV_FLAG) or "").strip().lower() == "on"


def cache_key(
    *,
    provider: str,
    model: str,
    system: str,
    messages: list[dict],
    tools: list[dict],
) -> str:
    """호출 입력 전체의 sha256.

    `provider`·`model` 을 넣는 이유: 모델을 바꾸면 **반드시 미스가 나야 한다.**
    안 그러면 flash 로 만든 응답을 flash-lite 결과로 착각한다.
    """
    blob = json.dumps(
        {
            "provider": provider,
            "model": model,
            "system": system,
            "messages": messages,
            "tools": tools,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def encode_delta(delta: LlmDelta) -> dict[str, Any]:
    """`("text"|"tool_use"|"end", payload)` → JSON 직렬화 가능 dict."""
    kind, payload = delta
    if kind == "tool_use" and isinstance(payload, ToolUse):
        return {"kind": kind, "id": payload.id, "name": payload.name, "input": payload.input}
    return {"kind": kind, "value": payload}


def decode_delta(raw: dict[str, Any]) -> LlmDelta:
    kind = raw.get("kind")
    if kind == "tool_use":
        return ("tool_use", ToolUse(id=raw["id"], name=raw["name"], input=raw.get("input") or {}))
    return (str(kind), raw.get("value"))
```

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run --with pytest python -m pytest backend/agent/test_llm_cache.py -q`
Expected: `5 passed`

- [ ] **Step 5: 린트**

Run: `uv run ruff check backend/agent/llm_cache.py backend/agent/test_llm_cache.py`
Expected: `All checks passed!`

- [ ] **Step 6: 커밋**

```bash
git add backend/agent/llm_cache.py backend/agent/test_llm_cache.py
git commit -F - <<'MSG'
[M2] feat: LLM 응답 카세트 — 키·델타 직렬화·활성화 판정

CachingClient 가 기댈 순수 함수 3종을 먼저 세운다. 네트워크 코드 0.

- cache_enabled(): MAINTQ_LLM_CACHE 가 정확히 "on" 일 때만 True.
  빈 값·미설정·"1"·"true" 는 전부 꺼짐 — D40 이 정한 "가짜 응답을 진짜로
  착각하는 사고를 막는다" 태도를 따라 명시적 옵트인으로 둔다
- cache_key(): provider·model 을 키에 포함한다. 모델을 바꾸면 반드시 미스가
  나야 flash 응답을 flash-lite 결과로 착각하지 않는다
- encode/decode_delta(): LlmDelta 3종(text·tool_use·end) 왕복. ToolUse 는
  데이터클래스라 id·name·input 을 펼쳐 담는다

회귀 5건 전부 통과. 캐시 디렉터리는 아직 만들지 않는다(Task 2).

카세트 / Task 1

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```

---

## Task 2: `CachingClient` 데코레이터 + `.gitignore`

**Files:**
- Modify: `backend/agent/llm_cache.py` (클래스 추가)
- Modify: `backend/agent/test_llm_cache.py` (테스트 추가)
- Modify: `.gitignore`

**Interfaces:**
- Consumes: Task 1 의 `cache_key`·`encode_delta`·`decode_delta`·`CACHE_ROOT`·`SCHEMA`
- Produces: `CachingClient(inner: LlmClient, *, provider: str, model: str, root: Path | None = None)` — 속성 `last_hit: bool` · `hits: int` · `misses: int`, 메서드 `stream(*, system, messages, tools) -> AsyncIterator[LlmDelta]` · `stats_line() -> str`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/agent/test_llm_cache.py` 끝에 추가:

```python
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
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run --with pytest python -m pytest backend/agent/test_llm_cache.py -q`
Expected: FAIL — `AttributeError: module 'backend.agent.llm_cache' has no attribute 'CachingClient'`

- [ ] **Step 3: 구현**

`backend/agent/llm_cache.py` 끝에 추가:

```python
class CachingClient:
    """`LlmClient` 데코레이터 — 응답만 재생하고 도구 실행은 그대로 둔다.

    `last_hit` 은 `stream()` **호출 시점에** 확정된다(조회가 동기라서). `run_turn` 은
    델타 루프 첫 회차에서 이 값을 읽어 `trace.replay` 를 켠다 — `_safe_stream` 이
    async generator 라 `stream()` 이 첫 델타를 당길 때 비로소 호출되기 때문이다.
    """

    def __init__(
        self,
        inner: Any,
        *,
        provider: str,
        model: str,
        root: Path | None = None,
    ) -> None:
        self._inner = inner
        self._provider = provider
        self._model = model
        self._root = Path(root) if root is not None else CACHE_ROOT
        self.last_hit: bool = False
        self.hits: int = 0
        self.misses: int = 0

    def _path(self, key: str) -> Path:
        return self._root / f"{key}.json"

    def stream(
        self, *, system: str, messages: list[dict], tools: list[dict]
    ):
        key = cache_key(
            provider=self._provider,
            model=self._model,
            system=system,
            messages=messages,
            tools=tools,
        )
        path = self._path(key)
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            deltas = [decode_delta(d) for d in record.get("deltas", [])]
            self.last_hit = True
            self.hits += 1

            async def replay():
                for d in deltas:
                    yield d

            return replay()

        self.last_hit = False
        self.misses += 1
        inner_stream = self._inner.stream(system=system, messages=messages, tools=tools)

        async def record_and_yield():
            captured: list[LlmDelta] = []
            async for delta in inner_stream:
                captured.append(delta)
                yield delta
            # 스트림이 끝까지 온 경우에만 기록한다 — 도중에 끊긴 응답을 캐시하면
            # 다음 실행이 잘린 답을 "정상"으로 재생한다.
            self._root.mkdir(parents=True, exist_ok=True)
            payload = {
                "_schema": SCHEMA,
                "provider": self._provider,
                "model": self._model,
                "deltas": [encode_delta(d) for d in captured],
            }
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

        return record_and_yield()

    def stats_line(self) -> str:
        """`캐시 히트 N/M (히트율 X%)`. 실익이 있는지 **재고 나서** 판단하기 위한 실측치다."""
        total = self.hits + self.misses
        rate = (self.hits / total * 100) if total else 0.0
        return f"캐시 히트 {self.hits}/{total} (히트율 {rate:.1f}%)"
```

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run --with pytest python -m pytest backend/agent/test_llm_cache.py -q`
Expected: `9 passed`

- [ ] **Step 5: `.gitignore` 에 캐시 디렉터리 추가**

`.gitignore` 끝에:

```gitignore
# LLM 응답 카세트 (D105) — 개발 보조물이라 추적하지 않는다. 언제 지워도 된다.
data/cache/
```

- [ ] **Step 6: 제외를 실측으로 확인한다**

Run: `git check-ignore -q data/cache/llm/abc123.json; echo "rc=$?"`
Expected: `rc=0` (제외됨)

- [ ] **Step 7: 커밋**

```bash
git add backend/agent/llm_cache.py backend/agent/test_llm_cache.py .gitignore
git commit -F - <<'MSG'
[M2] feat: CachingClient 데코레이터 + 캐시 디렉터리 git 제외

LlmClient 프로토콜을 구현하는 데코레이터. 캐시가 대신하는 것은 LLM 응답뿐이라
MCP 왕복·DB 쓰기·SSE 발행·trace 저장은 실제로 일어난다 — 그게 이 설계의 목적이다
("테스트하려는 건 LLM 결과가 아니라 backend 실행").

- 히트: 기록된 델타를 재생하고 inner 를 건드리지 않는다. 회귀가 폭파 스텁으로 증명
- 미스: inner 를 실행하며 델타를 포착해 기록. 스트림이 끝까지 온 경우에만 쓴다 —
  도중에 끊긴 응답을 캐시하면 다음 실행이 잘린 답을 "정상"으로 재생한다
- last_hit 은 stream() 호출 시점에 확정된다(조회가 동기). run_turn 이 델타 루프
  첫 회차에서 읽는 이유는 _safe_stream 이 async generator 라 stream() 이 첫 델타를
  당길 때 비로소 호출되기 때문이다 (Task 3)
- stats_line(): 캐시 히트 N/M (히트율 X%). 다중 호출 턴은 이력에 po_id·타임스탬프가
  섞여 미스가 날 수 있는데, 휘발성 필드를 지우고 해싱하면 다른 입력에 같은 응답을
  주는 더 나쁜 버그가 된다. 미리 풀지 않고 실측한 뒤 대응한다

data/cache/ 를 .gitignore 에 넣었다(git check-ignore rc=0 확인).
store.py(D103)를 재사용하지 않는다 — 그건 git 추적 append-only 외부 원본용이다.

회귀 9건 통과.

카세트 / Task 2

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```

---

## Task 3: D55 재생 표식 배선 — 가장 빠뜨리기 쉬운 한 줄

**Files:**
- Modify: `backend/agent/loop.py` (델타 루프 첫 회차)
- Modify: `backend/agent/test_llm_cache.py` (테스트 추가)

**Interfaces:**
- Consumes: Task 2 의 `CachingClient.last_hit`
- Produces: 없음(배선). `run_turn` 이 히트 시 `trace.replay = True` 로 켠다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/agent/test_llm_cache.py` 끝에 추가:

```python
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
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run --with pytest python -m pytest backend/agent/test_llm_cache.py -q`
Expected: FAIL — `AssertionError: run_turn 에 캐시 히트 → trace.replay 배선이 없다`

- [ ] **Step 3: `loop.py` 에 배선을 넣는다**

`backend/agent/loop.py` 의 `stream = _safe_stream(...)`(현재 `:395`) 아래 델타 소비 루프
(`async for delta in stream:`) **본문 맨 앞**에 다음을 넣는다:

```python
            # 캐시 히트면 이 턴을 D55 재생으로 표식한다 — `eval/score.has_replay()` 가
            # 지표 분모에서 뺀다. 이 세 줄이 빠지면 캐시 히트가 지표에 **조용히** 섞인다.
            # `_safe_stream` 이 async generator 라 `llm.stream()` 은 첫 델타를 당길 때
            # 호출된다 — 그래서 루프 밖이 아니라 **첫 회차 안**에서 읽는다.
            if not trace.replay and getattr(llm, "last_hit", False):
                trace.replay = True
```

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run --with pytest python -m pytest backend/agent/test_llm_cache.py -q`
Expected: `11 passed`

- [ ] **Step 5: 기존 회귀가 안 깨졌는지 확인한다**

Run: `uv run python spikes/agent_loop_contract.py`
Expected: `통과 (35건)`

Run: `uv run python spikes/eval_replay_guard.py`
Expected: `통과 (16건)`

Run: `uv run python spikes/sp3_sse_events.py`
Expected: `통과 (22건)`

- [ ] **Step 6: 커밋**

```bash
git add backend/agent/loop.py backend/agent/test_llm_cache.py
git commit -F - <<'MSG'
[M2] feat: 캐시 히트를 D55 재생으로 표식 — 지표 오염 방지

이 설계에서 가장 빠뜨리기 쉬운 세 줄이다. 빠지면 캐시 히트가 지표에 조용히
섞이고 아무도 모른다.

run_turn 의 델타 루프 첫 회차에서 llm.last_hit 을 읽어 trace.replay 를 켠다.
루프 밖이 아니라 첫 회차 안인 이유: _safe_stream 이 async generator 라
llm.stream() 이 첫 델타를 당길 때 비로소 호출된다.

이렇게 하면 기존 기계장치가 그대로 값을 한다 — TraceWriter.replay 가 이벤트
payload 에 replay:true 를 주입하고(trace.py:162), eval/score.py:has_replay()
가 any() 로 세션 전체를 분모에서 뺀다. 부분 오염도 전체 배제라는 D55 규칙이
캐시에도 그대로 적용된다.

새 표식을 만들지 않은 이유: 의미상 캐시 히트는 재생이고, 캐시 끄는 걸 깜빡해도
지표가 조용히 오염되는 대신 "제외됨"으로 드러나며(지우는 방식은 깜빡하면 아무도
모른다), eval_replay_guard 16건이 이미 그 동치성을 지켜 새 회귀가 필요 없다.

회귀: 카세트 pytest 11건 · agent_loop_contract 35 · eval_replay_guard 16 ·
sp3_sse_events 22 전부 통과.

카세트 / Task 3

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```

---

## Task 4: `get_client()` 배선 — 켜야 감싼다

**Files:**
- Modify: `backend/agent/llm.py` (`get_client()` 끝)
- Modify: `backend/agent/test_llm_cache.py`

**Interfaces:**
- Consumes: Task 2 의 `CachingClient`, Task 1 의 `cache_enabled()`
- Produces: `get_client()` 가 `cache_enabled()` 일 때만 `CachingClient` 로 감싼 객체를 반환

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/agent/test_llm_cache.py` 끝에 추가:

```python
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
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run --with pytest python -m pytest backend/agent/test_llm_cache.py::test_get_client_wraps_only_when_enabled -q`
Expected: FAIL — `assert not isinstance(...)` 가 아니라 두 번째 단언에서 실패(`CachingClient` 로 감싸지 않음)

- [ ] **Step 3: `get_client()` 끝을 고친다**

`backend/agent/llm.py` 의 `get_client()` 마지막 두 줄

```python
    if provider == "gemini":
        return GeminiClient(model=model, api_key=api_key)
    return AnthropicClient(model=model, api_key=api_key)
```

을 다음으로 바꾼다:

```python
    inner = (
        GeminiClient(model=model, api_key=api_key)
        if provider == "gemini"
        else AnthropicClient(model=model, api_key=api_key)
    )
    # 카세트는 **명시적 옵트인**이다 (D105). 켜지 않으면 위 클라이언트가 그대로 나간다.
    from backend.agent.llm_cache import CachingClient, cache_enabled  # noqa: PLC0415

    if cache_enabled():
        return CachingClient(inner, provider=provider, model=model)
    return inner
```

> 지연 import 인 이유: `llm_cache` 가 `llm` 을 임포트하므로 모듈 최상단에 두면 순환이 된다.
> `_get_json` 이 `httpx` 를 지연 import 하는 것과 같은 형태다.

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run --with pytest python -m pytest backend/agent/test_llm_cache.py -q`
Expected: `12 passed`

- [ ] **Step 5: 기존 회귀 확인**

Run: `uv run python spikes/llm_provider_contract.py`
Expected: `통과 (14건)`

- [ ] **Step 6: 커밋**

```bash
git add backend/agent/llm.py backend/agent/test_llm_cache.py
git commit -F - <<'MSG'
[M2] feat: get_client() 가 카세트를 감싼다 (옵트인)

MAINTQ_LLM_CACHE=on 일 때만 CachingClient 로 감싼다. 켜지 않으면 기존
클라이언트가 그대로 나가 현재 동작이 한 톨도 바뀌지 않는다.

llm_cache 가 llm 을 임포트하므로 순환을 피해 지연 import 로 넣었다 —
_get_json 이 httpx 를 지연 import 하는 것과 같은 형태다.

회귀: 카세트 pytest 12건 · llm_provider_contract 14건 통과.

카세트 / Task 4

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```

---

## Task 5: `/run-eval --replay` 모드 + 히트율 인쇄

**Files:**
- Modify: `eval/run_eval.py`

**Interfaces:**
- Consumes: Task 1 의 `ENV_FLAG`
- Produces: `--replay` CLI 플래그

- [ ] **Step 1: 현재 CLI 구조를 읽는다**

Run: `grep -n "add_argument\|def main\|argparse" eval/run_eval.py | head -20`

읽고 나서 아래 Step 2 의 위치를 그 구조에 맞춘다. **다른 인자의 스타일(도움말 문구·기본값)을 그대로 따른다.**

- [ ] **Step 2: `--replay` 플래그를 넣는다**

`eval/run_eval.py` 의 argparse 정의부에 추가:

```python
    parser.add_argument(
        "--replay",
        action="store_true",
        help=(
            "LLM 응답 카세트를 켜고 실행한다 (D105). 채점·집계·배선을 고칠 때 빠르게 "
            "돌리기 위한 모드다. 캐시 히트 세션은 D55 표식이 붙어 지표 분모에서 "
            "제외되므로 이 모드의 수치를 실적으로 인용할 수 없다."
        ),
    )
```

그리고 실행 시작 지점(클라이언트를 만들기 **전**)에:

```python
    if args.replay:
        os.environ["MAINTQ_LLM_CACHE"] = "on"
        print(
            "[모드] 재생 — 카세트를 켰습니다. 캐시 히트 세션은 D55 표식이 붙어 "
            "지표 분모에서 제외됩니다. 이 실행의 수치를 실적으로 인용하지 마세요.",
            file=sys.stderr,
        )
```

- [ ] **Step 3: 두 모드가 실제로 갈리는지 확인한다**

Run: `uv run python eval/run_eval.py --help`
Expected: 도움말에 `--replay` 와 위 설명이 보인다

Run: `uv run python -c "import os; print(os.environ.get('MAINTQ_LLM_CACHE'))"`
Expected: `None` — 기본은 꺼짐이고 `--replay` 없이는 환경이 오염되지 않는다

- [ ] **Step 4: 커밋**

```bash
git add eval/run_eval.py
git commit -F - <<'MSG'
[M4] feat: /run-eval --replay 모드 — 채점 로직 고칠 때 빠르게

두 모드로 가른다:
- 기본: 캐시 off, 지표 인정. 지표를 잴 때
- --replay: 캐시 on, D55 표식이 붙어 분모에서 제외. 채점·집계·배선 고칠 때

--replay 는 실행 시작에 경고를 stderr 로 찍는다. 수치가 실적으로 인용되는
사고를 막기 위해서다 — 집계가 이미 분모에서 빼므로 애초에 수치가 나오지도
않지만, 사람이 그 사실을 모르고 표를 읽는 것을 막는다.

카세트 / Task 5

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```

---

## Task 6: D105 등재 + 기준선 갱신 + 실측

**Files:**
- Modify: `docs/10_DECISIONS.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: 현재 마지막 D 번호를 확인한다**

Run: `grep -oE "^\| D[0-9]+" docs/10_DECISIONS.md | tail -3`
Expected: `| D103` (Sprint 13 Stage 2 가 끝났다면 `| D104`)

번호가 다르면 **실제 다음 번호를 쓴다.** 아래 본문의 `D105` 를 그 번호로 바꾼다.

- [ ] **Step 2: D105 를 등재한다**

`docs/10_DECISIONS.md` 표 끝에 1행 추가. 기존 행의 4셀 형식(`| D | 결정 | 대안 | 근거 |`)을 그대로 따른다.

- **결정**: LLM 응답 캐시(카세트)는 **기본 꺼짐**(`MAINTQ_LLM_CACHE=on` 옵트인)이고, **캐시 히트는 D55 재생으로 표식**해 지표 분모에서 제외한다. 저장은 `data/cache/llm/`(git 미추적).
- **대안**: ⓐ 캐시 없음(현행) / ⓑ 평가 실행 전 캐시 삭제 / ⓒ 캐시 전용 새 표식 신설
- **근거**: ⓑ 는 **깜빡하면 조용히 오염**되고 다른 용도의 캐시까지 지운다 — 실패가 침묵하는 설계다. ⓒ 는 `eval_replay_guard` 16건과 `has_replay()` 를 중복시키고 *"재생과 캐시가 무엇이 다른가"* 를 계속 설명해야 한다. D55 가 이미 *"부분 오염도 전체 배제"* 를 정해 뒀으므로 재사용이 자연스럽다. ⓐ 는 실 통증(스모크·평가·curl 이 매번 실 호출)을 방치한다. **캐시 히트는 가짜 응답이 아니라 기록된 실제 응답**이다 — 그래도 표식하는 이유는 *"언제 만들어진 응답인지"* 가 지표의 전제이기 때문이다(그 사이 모델·프롬프트가 바뀌었을 수 있다). `store.py`(D103)를 재사용하지 않는다 — 그건 git 추적·append-only 외부 원본용이라 성격이 정반대다.

- [ ] **Step 3: 실측 — 이 스펙의 성공 판정**

Run (1회차, 캐시 채우기):
```bash
MAINTQ_LLM_CACHE=on bash -c 'time uv run python -m eval.run_eval --replay' 2>&1 | tail -5
```

Run (2회차, 캐시 사용):
```bash
MAINTQ_LLM_CACHE=on bash -c 'time uv run python -m eval.run_eval --replay' 2>&1 | tail -5
```

**두 실행의 초 단위 시간과 `stats_line()` 의 히트율을 기록한다.** 체감이 아니라 실측을 적는다.

**히트율이 낮으면 그 사실을 그대로 적는다.** 다중 호출 턴은 이력에 `po_id`·타임스탬프가 섞여 미스가 날 수 있다(스펙 §6-1). 실익이 없으면 없다고 기록하고, 원인을 실측한 뒤 다음 작업으로 넘긴다 — 지금 추측으로 정규화하지 않는다.

- [ ] **Step 4: `CLAUDE.md` 기준선을 갱신한다**

pytest 커맨드가 바뀐다. 회귀 절의 pytest 항목을 다음으로:

```
uv run --with pytest python -m pytest data/rules/test_rules.py backend/agent/test_llm_cache.py -q
```

건수도 실측으로 갱신한다(현재 46 → 46 + 카세트 12 = **58** 예상. **러너 출력이 기준이다** — 예측과 다르면 실측을 적는다).

- [ ] **Step 5: 전수 회귀**

Run: 30스위트 전수 실행
Expected: **872건 · FAIL 0**. Windows 소켓 고갈로 스위트 1건이 실패하면 **단독 재실행해 확인**하고 그 사실을 보고에 적는다(CLAUDE.md 규칙)

- [ ] **Step 6: 커밋**

```bash
git add docs/10_DECISIONS.md CLAUDE.md
git commit -F - <<'MSG'
[M4] docs: D105 등재 + 기준선 갱신 + 카세트 실측

D105 — LLM 응답 캐시는 기본 꺼짐이고 히트는 D55 재생으로 표식해 지표 분모에서
제외한다. "평가 전 캐시 삭제"를 기각한 이유는 깜빡하면 조용히 오염되기 때문이다.
표식은 깜빡해도 집계가 잡는다 — 실패가 침묵하지 않는 쪽을 골랐다.

실측(이 스펙의 성공 판정):
- 1회차(캐시 채우기): <실측 초>
- 2회차(캐시 사용): <실측 초>
- 히트율: <실측>

pytest 커맨드가 2파일 합산으로 바뀌었다(46 → <실측>).
전수 회귀 30스위트 <실측>건 FAIL 0.

카세트 / Task 6

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
```

---

## Self-Review 결과

**1. 스펙 커버리지**

| 스펙 절 | 구현 태스크 |
|---|---|
| §2 구조(데코레이터 · 변경면 3곳) | Task 2(ⓐ) · Task 4(ⓑ) · Task 3(ⓒ) |
| §3 기본 꺼짐 | Task 1 `cache_enabled()` · Task 4 배선 |
| §4-1 키(provider·model 포함) | Task 1 |
| §4-2 값(델타 3종 직렬화) | Task 1 |
| §4-3 저장·git 미추적 | Task 2 Step 5~6 |
| §5 D55 표식 | **Task 3** |
| §5-3 `/run-eval` 두 모드 | Task 5 |
| §6 히트율 인쇄 | Task 2 `stats_line()` · Task 6 Step 3 실측 |
| §7 회귀 7건 | Task 1(3건) · Task 2(4건) · Task 3(2건) · Task 4(1건) = **12건**(스펙 7건보다 세분) |
| §8 D105 | Task 6 |

**갭 없음.**

**2. 플레이스홀더**: Task 6 Step 6 커밋 메시지의 `<실측 초>`·`<실측>` 은 **의도된 것**이다 — 실행해야 나오는 값이고, 그 자리를 비워 두는 것이 "체감이 아니라 실측을 적는다"는 요구를 강제한다. 그 밖의 플레이스홀더 없음.

**3. 타입 일관성**: `cache_key(*, provider, model, system, messages, tools)` · `encode_delta`/`decode_delta` · `CachingClient(inner, *, provider, model, root=None)` · `last_hit`/`hits`/`misses`/`stats_line()` — Task 1~4 에서 이름과 시그니처가 일치한다. `ENV_FLAG`·`CACHE_ROOT`·`SCHEMA` 도 Task 1 정의를 Task 2·4·5 가 그대로 참조한다.
