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
