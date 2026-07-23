# -*- coding: utf-8 -*-
"""LLM 클라이언트 추상화 (D40).

**왜 인터페이스로 분리하는가.** 루프 정책(A1~A8·호출 상한·장애 모드)과 `traces` 영속화는
평가의 판정 소스다(D21·D30). 이게 `ANTHROPIC_API_KEY` 가용성과 과금에 묶이면 회귀가
상시로 돌지 못한다. 그래서 회귀·스모크는 `ScriptedClient`(고정 응답 시퀀스)로 구동한다.

**폴백을 막는 이유 (D40).** `get_client()` 는 키가 없을 때 조용히 `ScriptedClient` 로
떨어지지 않고 **실패한다.** 데모에서 스크립트 응답을 진짜 LLM 응답으로 착각하는 사고를
막기 위해서다. 스크립트 주입은 항상 **명시적**이어야 한다.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolUse:
    """LLM 이 요청한 도구 호출."""

    id: str
    name: str
    input: dict = field(default_factory=dict)


# 스트림 델타: ("text", str) | ("tool_use", ToolUse) | ("end", stop_reason)
LlmDelta = tuple[str, object]


@runtime_checkable
class LlmClient(Protocol):
    def stream(
        self, *, system: str, messages: list[dict], tools: list[dict]
    ) -> AsyncIterator[LlmDelta]: ...


class ScriptedClient:
    """테스트·스모크 전용 — 턴별 고정 델타 시퀀스를 그대로 흘린다 (D40).

    `script[i]` 가 i 번째 LLM 호출의 델타 목록이다. 호출이 스크립트를 넘어서면
    빈 응답 대신 **예외**를 낸다 — 스크립트가 짧아 조용히 턴이 끝나면
    "루프가 정상 종료했다"는 잘못된 통과가 생긴다.
    """

    def __init__(self, script: Sequence[Sequence[LlmDelta]]) -> None:
        self._script = [list(turn) for turn in script]
        self.calls = 0
        #: 루프가 매 호출에 넘긴 messages 스냅샷 — 이력 절삭·요약 검증용
        self.seen_messages: list[list[dict]] = []
        self.seen_systems: list[str] = []
        self.seen_tools: list[list[dict]] = []

    def stream(
        self, *, system: str, messages: list[dict], tools: list[dict]
    ) -> AsyncIterator[LlmDelta]:
        if self.calls >= len(self._script):
            raise AssertionError(
                f"ScriptedClient: {self.calls + 1}번째 LLM 호출인데 스크립트는 "
                f"{len(self._script)}턴뿐입니다 — 루프가 예상보다 많이 호출했습니다"
            )
        deltas = self._script[self.calls]
        self.calls += 1
        self.seen_systems.append(system)
        self.seen_messages.append([dict(m) for m in messages])
        self.seen_tools.append(list(tools))

        async def gen() -> AsyncIterator[LlmDelta]:
            for d in deltas:
                yield d

        return gen()


class AnthropicClient:
    """실제 Claude 호출. `anthropic` SDK 의 스트리밍을 `LlmDelta` 로 정규화한다."""

    def __init__(self, model: str, api_key: str, max_tokens: int = 2048) -> None:
        from anthropic import AsyncAnthropic  # noqa: PLC0415 — 선택적 의존성

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def stream(
        self, *, system: str, messages: list[dict], tools: list[dict]
    ) -> AsyncIterator[LlmDelta]:
        client, model, max_tokens = self._client, self._model, self._max_tokens

        async def gen() -> AsyncIterator[LlmDelta]:
            async with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                tools=tools,
            ) as stream:
                async for event in stream:
                    etype = getattr(event, "type", "")
                    if etype == "text":
                        yield ("text", event.text)
            final = await stream.get_final_message()
            for blk in final.content:
                if getattr(blk, "type", "") == "tool_use":
                    yield ("tool_use", ToolUse(id=blk.id, name=blk.name, input=blk.input or {}))
            yield ("end", final.stop_reason or "end_turn")

        return gen()


def get_client() -> LlmClient:
    """환경변수로 실제 클라이언트를 만든다.

    **키가 없으면 ScriptedClient 로 폴백하지 않고 실패한다 (D40).**
    스크립트는 테스트가 명시적으로 주입할 때만 쓰인다.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    model = os.environ.get("MAINTQ_LLM_MODEL", "").strip()
    missing = [n for n, v in (("ANTHROPIC_API_KEY", api_key), ("MAINTQ_LLM_MODEL", model)) if not v]
    if missing:
        raise RuntimeError(
            f".env 에 {' · '.join(missing)} 이(가) 없습니다. "
            "테스트용 스크립트 응답으로 자동 대체하지 않습니다 (D40) — "
            "가짜 응답을 진짜로 착각하는 사고를 막기 위해서입니다."
        )
    return AnthropicClient(model=model, api_key=api_key)
