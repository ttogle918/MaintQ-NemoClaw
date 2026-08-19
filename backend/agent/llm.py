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

import json
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
                messages=anthropic_messages(messages),  # D76 — role:"tool" 변환
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


# ────────────────────────────────────────────── Gemini (D56)

#: Gemini 함수 선언 스키마가 받는 키만 남긴다. MCP 의 inputSchema(JSON Schema)에는
#: `title`·`additionalProperties`·`$schema` 같은 키가 섞여 오는데 Gemini 쪽 검증이
#: 거부할 수 있다 — 없어도 의미가 줄지 않는 표시용 키라 버리는 쪽이 안전하다.
_GEMINI_SCHEMA_KEYS = ("type", "description", "enum", "properties", "required", "items")


def gemini_schema(schema: dict) -> dict:
    """JSON Schema → Gemini 가 받는 부분집합으로 재귀 정리."""
    out: dict = {}
    for key in _GEMINI_SCHEMA_KEYS:
        if key not in schema:
            continue
        value = schema[key]
        if key == "properties" and isinstance(value, dict):
            out[key] = {name: gemini_schema(p) for name, p in value.items()}
        elif key == "items" and isinstance(value, dict):
            out[key] = gemini_schema(value)
        else:
            out[key] = value
    return out


def gemini_declarations(tools: list[dict]) -> list[dict]:
    """MCP 도구 목록(`{name, description, input_schema}` — Anthropic 형식과 동일)을
    Gemini `function_declarations` 로 변환한다. 변환은 **여기(클라이언트 쪽)** 이다 —
    루프·MCP 클라이언트가 제공자별 형식을 알게 하지 않는다 (D40·D56).

    파라미터 없는 도구는 `parameters` 를 아예 뺀다 — 빈 object 스키마를 넘기면
    SDK 검증이 판본에 따라 거부한다.
    """
    decls: list[dict] = []
    for t in tools:
        d: dict = {"name": t["name"], "description": t.get("description", "")}
        params = gemini_schema(t.get("input_schema") or {})
        if params.get("properties"):
            d["parameters"] = params
        decls.append(d)
    return decls


def gemini_contents(messages: list[dict]) -> list[dict]:
    """루프 이력을 Gemini `contents` 로.

    역할 3종을 받는다 (D76):
      `user`/`assistant` — `{"content": str}`. Gemini 의 상대 역할명은 `model` 이다
      `tool`             — `{"name": str, "content": dict}` → **`functionResponse` 파트**

    도구 결과를 평문으로 넣지 않는 이유는 D76 에 있다 — 프로즈로 뭉개면 값이 사라지고
    모델이 "사용자가 그렇게 말했다"고 읽는다.
    """
    out: list[dict] = []
    for m in messages:
        role = m.get("role")
        if role == "tool":
            payload = m.get("content")
            # Gemini 의 functionResponse.response 는 **객체**여야 한다. 도구가 스칼라를
            # 돌려주는 일은 없지만(04_MCP_TOOLS 는 전부 dict) 방어적으로 감싼다.
            resp = payload if isinstance(payload, dict) else {"result": payload}
            out.append(
                {
                    "role": "user",
                    "parts": [
                        {"functionResponse": {"name": m.get("name", ""), "response": resp}}
                    ],
                }
            )
        else:
            out.append(
                {
                    "role": "model" if role == "assistant" else "user",
                    "parts": [{"text": str(m.get("content", ""))}],
                }
            )
    return out


def anthropic_messages(messages: list[dict]) -> list[dict]:
    """루프 이력을 Anthropic `messages` 로 (D76).

    ⚠️ **네이티브 `tool_result` 블록을 쓰지 않는다.** Anthropic 의 `tool_result` 는 직전
    assistant 메시지의 `tool_use` 와 `tool_use_id` 로 짝지어야 하는데, 루프가 assistant
    `tool_use` 블록을 이력에 남기지 않는다(sprint-3 C-5 가 지적한 그 구조). 짝 없이
    `tool_result` 를 보내면 400 이다.

    그래서 **구조는 보존하되 JSON 텍스트로** 넘긴다 — 프로즈 요약보다는 낫고, 네이티브
    프로토콜보다는 못하다. 완전 해소는 루프가 `tool_use` 를 기록하도록 바꿔야 하며
    별도 결정 대상이다. 현재 기본 제공자는 gemini 라 실경로가 아니다(D56).
    """
    out: list[dict] = []
    for m in messages:
        if m.get("role") == "tool":
            body = json.dumps(m.get("content"), ensure_ascii=False, sort_keys=True)
            out.append(
                {"role": "user", "content": f"[도구 결과 {m.get('name', '')}]\n{body}"}
            )
        else:
            out.append({"role": m["role"], "content": str(m.get("content", ""))})
    return out


def gemini_chunk_deltas(chunk: object, next_id) -> list[LlmDelta]:
    """스트림 chunk 하나를 `LlmDelta` 목록으로 정규화한다.

    SDK 객체를 duck-typing 으로만 읽는다 — 계약 스파이크가 SDK 없이 가짜 chunk 로
    이 함수를 검증할 수 있어야 한다. Gemini 의 `function_call` 에는 id 가 없을 수
    있어 `next_id()` 로 합성한다 (루프는 id 를 쓰지 않지만 `ToolUse` 계약은 채운다).
    """
    deltas: list[LlmDelta] = []
    for cand in getattr(chunk, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in (getattr(content, "parts", None) or []) if content else []:
            text = getattr(part, "text", None)
            if text:
                deltas.append(("text", text))
            fc = getattr(part, "function_call", None)
            if fc is not None and getattr(fc, "name", None):
                deltas.append(
                    (
                        "tool_use",
                        ToolUse(
                            id=getattr(fc, "id", None) or next_id(),
                            name=fc.name,
                            input=dict(getattr(fc, "args", None) or {}),
                        ),
                    )
                )
    return deltas


class GeminiClient:
    """실제 Gemini 호출 (D56). `google-genai` SDK 스트리밍을 `LlmDelta` 로 정규화한다."""

    def __init__(self, model: str, api_key: str, max_tokens: int = 2048) -> None:
        from google import genai  # noqa: PLC0415 — 선택적 의존성

        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def stream(
        self, *, system: str, messages: list[dict], tools: list[dict]
    ) -> AsyncIterator[LlmDelta]:
        from google.genai import types  # noqa: PLC0415

        client, model, max_tokens = self._client, self._model, self._max_tokens
        config_kwargs: dict = {
            "system_instruction": system,
            "max_output_tokens": max_tokens,
        }
        # `tools` 가 빈 리스트면 config 에 `tools` 키 자체를 넣지 않는다 — 실 Gemini API 가
        # 빈 function_declarations 를 가진 Tool 객체를 받아들이는지 이 저장소에서 한 번도
        # 검증된 적이 없다(방어 코드, MQ-503). 기존 실 루프 경로(agent/loop.py)는 MCP 도구
        # 7종을 항상 채워 호출하므로 이 분기로 기존 동작은 달라지지 않는다.
        if tools:
            config_kwargs["tools"] = [
                types.Tool(function_declarations=gemini_declarations(tools))
            ]
        config = types.GenerateContentConfig(**config_kwargs)
        contents = gemini_contents(messages)

        async def gen() -> AsyncIterator[LlmDelta]:
            counter = iter(range(1, 1_000_000))

            def next_id() -> str:
                return f"fc-{next(counter)}"

            finish = None
            stream = await client.aio.models.generate_content_stream(
                model=model, contents=contents, config=config
            )
            async for chunk in stream:
                for delta in gemini_chunk_deltas(chunk, next_id):
                    yield delta
                for cand in getattr(chunk, "candidates", None) or []:
                    finish = getattr(cand, "finish_reason", None) or finish
            yield ("end", str(finish) if finish else "end_turn")

        return gen()


PROVIDERS = ("gemini", "anthropic")


def get_client() -> LlmClient:
    """환경변수로 실제 클라이언트를 만든다 (D56 — 제공자 분기, 기본 gemini).

    env 는 **OS 환경변수가 우선**이고 `.env` 는 빈 곳만 채운다 — 로드 지점은
    `backend/main.py` 의 `load_dotenv(override=False)` 한 곳이다 (D56).

    **키가 없으면 ScriptedClient 로 폴백하지 않고 실패한다 (D40).**
    스크립트는 테스트가 명시적으로 주입할 때만 쓰인다.
    """
    # `or` — .env 의 빈 키(`MAINTQ_LLM_PROVIDER=`)는 미설정과 같다 (D56, main.py CORS 와 동일 근거)
    provider = (os.environ.get("MAINTQ_LLM_PROVIDER") or "gemini").strip().lower()
    if provider not in PROVIDERS:
        raise RuntimeError(
            f"MAINTQ_LLM_PROVIDER 는 {PROVIDERS} 중 하나여야 합니다: {provider!r}"
        )

    model = os.environ.get("MAINTQ_LLM_MODEL", "").strip()
    if provider == "gemini":
        # SDK 관례상 두 이름이 통용된다 — GEMINI_API_KEY 를 우선하고 GOOGLE_API_KEY 도 인정
        api_key = (
            os.environ.get("GEMINI_API_KEY", "").strip()
            or os.environ.get("GOOGLE_API_KEY", "").strip()
        )
        key_label = "GEMINI_API_KEY(또는 GOOGLE_API_KEY)"
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        key_label = "ANTHROPIC_API_KEY"

    missing = [n for n, v in ((key_label, api_key), ("MAINTQ_LLM_MODEL", model)) if not v]
    if missing:
        raise RuntimeError(
            f"환경변수(또는 .env)에 {' · '.join(missing)} 이(가) 없습니다 "
            f"(provider={provider}). 테스트용 스크립트 응답으로 자동 대체하지 않습니다 "
            "(D40) — 가짜 응답을 진짜로 착각하는 사고를 막기 위해서입니다."
        )
    inner = (
        GeminiClient(model=model, api_key=api_key)
        if provider == "gemini"
        else AnthropicClient(model=model, api_key=api_key)
    )
    # 카세트는 **명시적 옵트인**이다 (D104). 켜지 않으면 위 클라이언트가 그대로 나간다.
    from backend.agent.llm_cache import CachingClient, cache_enabled  # noqa: PLC0415

    if cache_enabled():
        return CachingClient(inner, provider=provider, model=model)
    return inner
