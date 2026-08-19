# -*- coding: utf-8 -*-
"""LLM 응답 카세트 — 개발 가속용 응답 캐시 (D105 · 설계 스펙 2026-08-19).

**기본 꺼짐.** `MAINTQ_LLM_CACHE=on` 일 때만 동작한다 — D40 이 *"테스트용 스크립트 응답으로
자동 대체하지 않는다(가짜 응답을 진짜로 착각하는 사고를 막기 위해)"* 라고 정한 태도를 따라
명시적 옵트인으로 둔다.

**이 모듈은 네트워크를 타지 않는다.** 실제 호출은 감싸인 `inner` 가 한다.

⚠ **캐시 히트는 D55 재생이다.** `CachingClient.last_hit` 을 `run_turn` 이 읽어
`trace.replay = True` 로 켜고, 그러면 `eval/score.py:has_replay()` 가 그 세션을 지표
분모에서 제외한다. **그 한 줄이 빠지면 히트가 지표에 조용히 섞인다** — 이 설계에서 가장
빠뜨리기 쉬운 지점이라 회귀가 따로 그것만 본다.

저장은 `data/cache/llm/<key>.json` 이고 **git 미추적**이다. 언제 지워도 된다.
⛔ `data/external/store.py`(D103)를 쓰지 않는다 — 그건 git 추적·append-only 외부 원본용이라
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


#: `decode_delta` 가 받아도 되는 kind 화이트리스트. 이 밖은 캐시 파일 손상으로 본다.
_KNOWN_KINDS = frozenset({"text", "tool_use", "end"})


def _load_cached_deltas(path: Path) -> list[LlmDelta] | None:
    """캐시 파일을 로드·검증한다. 손상됐으면 `None`(미스로 취급)을 돌려준다.

    `decode_delta` 는 예상 밖 `kind`(예: `None`)에도 예외 없이 `("None", None)` 을
    돌려준다 — 그 관용성이 손상된 캐시 파일을 조용히 이상한 델타로 재생하지 않도록,
    로드 시점에서 `_schema`·`deltas` 형태·`kind` 화이트리스트를 검사한다(D62 — 모름을
    통과로 바꾸지 않는다). 캐시는 개발 보조물이라 손상됐다고 예외를 던져 실행을 죽이지
    않는다 — 캐시가 없는 것처럼 미스로 폴백한다.
    """
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        # UnicodeDecodeError 는 OSError 의 하위 클래스가 아니다(ValueError 계열) —
        # 파일 바이트가 깨져 UTF-8 디코딩이 실패하는 경우도 명시적으로 잡아야
        # 손상 캐시가 예외로 새지 않고 미스로 폴백한다.
        return None
    if not isinstance(record, dict) or record.get("_schema") != SCHEMA:
        return None
    raw_deltas = record.get("deltas")
    if not isinstance(raw_deltas, list):
        return None
    for raw in raw_deltas:
        if not isinstance(raw, dict) or raw.get("kind") not in _KNOWN_KINDS:
            return None
    try:
        return [decode_delta(raw) for raw in raw_deltas]
    except (KeyError, TypeError):
        return None


class CachingClient:
    """`LlmClient` 데코레이터 — 응답만 재생하고 도구 실행은 그대로 둔다.

    ⚠ `last_hit` 은 `stream()` **호출 시점에** 확정된다(조회가 동기라서). `run_turn` 은
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
            deltas = _load_cached_deltas(path)
            if deltas is not None:
                self.last_hit = True
                self.hits += 1

                async def replay():
                    for d in deltas:
                        yield d

                return replay()
            # 손상된 캐시 파일 — 미스로 취급하고 아래 inner 호출 경로로 진행한다.

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
