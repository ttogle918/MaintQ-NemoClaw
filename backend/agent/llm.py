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
import logging
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

logger = logging.getLogger(__name__)


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


# ────────────────────────────────────────────── Elice (D115)
#
# InsuQ 자매 프로젝트(ai-engine/insuq_ai/generation/llm.py)의 elice provider를
# 이식했다 — "모델 교체가 아니라 경로 교체"다. Elice ML API(mlapi.run)가 같은
# gemini 계열 모델을 OpenAI 호환 게이트웨이로 재판매한다. GEMINI_API_KEY/
# GOOGLE_API_KEY가 둘 다 무효해 실 LLM 검증이 막혔을 때 우회 경로로 추가했다.


def elice_tools(tools: list[dict]) -> list[dict]:
    """MCP 도구 목록(`{name, description, input_schema}`)을 OpenAI tool-calling
    스키마로 변환한다. Gemini와 달리 스키마를 축약하지 않는다 — OpenAI 호환
    레이어는 JSON Schema 를 그대로 받는다(InsuQ ai-engine 실측 확인)."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
            },
        }
        for t in tools
    ]


def elice_messages(messages: list[dict]) -> list[dict]:
    """루프 이력 → OpenAI `messages`.

    ⚠️ **네이티브 `tool` 역할(assistant `tool_calls` + `tool` 페어)을 쓰지 않는다.**
    처음엔 합성 assistant(`tool_calls`)로 id를 짝지어 봤는데, Elice가 재판매하는
    Gemini는 이전 턴에 실제 tool_calls가 있었다면 그 원본의 `thought_signature`
    확장 필드(구글 전용, `extra_content.google`)를 요구한다 — 루프가 assistant
    `tool_use` 블록 자체를 이력에 남기지 않아(D76, `anthropic_messages`와 같은
    사정) 합성 tool_calls로는 이 요구를 못 채운다(실측: `400 Function call is
    missing a thought_signature`). `anthropic_messages`와 같은 이유로 같은
    해법을 쓴다 — 구조는 보존하되 JSON 텍스트로 user 메시지에 담는다.
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


def elice_chunk_delta(chunk: object) -> tuple[str | None, list[dict], str | None]:
    """스트림 chunk 하나 → (텍스트 델타, tool_call 조각 목록, finish_reason).

    duck-typing만 쓴다 — SDK 없이 가짜 chunk로 검증 가능해야 한다(gemini_chunk_deltas
    와 같은 이유). OpenAI 호환 스트리밍은 tool_call 의 `arguments`가 여러 청크에
    걸쳐 조각으로 온다 — 조각 자체는 여기서 그대로 반환하고, 누적은
    `elice_finalize_tool_calls`가 한다(단일 chunk 처리와 누적 상태를 분리해
    둘 다 순수 함수로 테스트 가능하게 한다).
    """
    choices = getattr(chunk, "choices", None) or []
    if not choices:
        return None, [], None
    choice = choices[0]
    finish = getattr(choice, "finish_reason", None)
    delta = getattr(choice, "delta", None)
    text = getattr(delta, "content", None) if delta is not None else None
    frags: list[dict] = []
    for tc in (getattr(delta, "tool_calls", None) or []) if delta is not None else []:
        fn = getattr(tc, "function", None)
        frags.append(
            {
                "index": getattr(tc, "index", 0),
                "id": getattr(tc, "id", None),
                "name": getattr(fn, "name", None) if fn is not None else None,
                "arguments": getattr(fn, "arguments", None) if fn is not None else None,
            }
        )
    return text, frags, finish


def elice_finalize_tool_calls(acc: dict[int, dict]) -> list[ToolUse]:
    """누적된 tool_call 조각(index → {id, name, args}) → `ToolUse` 목록, index 오름차순.

    `args` JSON 파싱 실패는 예외를 던지지 않고 빈 dict로 대체한다 — 도구 호출
    자체는 진행시키고, 인자 누락은 이후 도구단(D9)이 흡수한다."""
    out: list[ToolUse] = []
    for idx in sorted(acc):
        data = acc[idx]
        try:
            parsed = json.loads(data["args"]) if data["args"] else {}
        except json.JSONDecodeError:
            parsed = {}
        out.append(ToolUse(id=data["id"] or f"call_{idx}", name=data["name"] or "", input=parsed))
    return out


def _fixup_max_completion_tokens(kwargs: dict, max_tokens: int) -> dict:
    out = {k: v for k, v in kwargs.items() if k != "max_tokens"}
    out["max_completion_tokens"] = max_tokens
    return out


def _fixup_reasoning_effort_none(kwargs: dict, _max_tokens: int) -> dict:
    out = dict(kwargs)
    out["extra_body"] = {**out.get("extra_body", {}), "reasoning_effort": "none"}
    return out


#: 알려진 모델별 chat/completions 규격 이탈 — (오류 메시지에 전부 포함돼야 하는 부분
#: 문자열들, 보정 함수) 순서대로 시도한다. 새 모델에서 새 오류가 나오면 여기 한 줄만
#: 추가하면 된다 — `EliceClient.stream()` 본체는 안 건드린다.
_ELICE_QUIRK_FIXUPS: list[tuple[tuple[str, ...], object]] = [
    (("max_tokens", "max_completion_tokens"), _fixup_max_completion_tokens),
    (("reasoning_effort",), _fixup_reasoning_effort_none),
]


class EliceClient:
    """OpenAI 호환 스트리밍 클라이언트 — Elice 게이트웨이(mlapi.run, D115) 전용으로
    만들었지만 규격 자체가 OpenAI 호환이라 `base_url`만 바꾸면 다른 OpenAI 호환
    제공자(예: 실 OpenAI API — Elice/Gemini 특유의 도구 호출 문제인지 격리 진단할 때)
    에도 그대로 쓴다. 이름은 최초 용도를 남긴다."""

    def __init__(self, model: str, api_key: str, base_url: str, max_tokens: int = 2048) -> None:
        from openai import AsyncOpenAI  # noqa: PLC0415 — 선택적 의존성

        url = base_url.rstrip("/")
        if not url.endswith("/v1"):
            url = f"{url}/v1"
        self._client = AsyncOpenAI(base_url=url, api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def stream(
        self, *, system: str, messages: list[dict], tools: list[dict]
    ) -> AsyncIterator[LlmDelta]:
        client, model, max_tokens = self._client, self._model, self._max_tokens
        payload_messages = [{"role": "system", "content": system}, *elice_messages(messages)]
        kwargs: dict = {
            "model": model,
            "messages": payload_messages,
            "stream": True,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = elice_tools(tools)

        async def gen() -> AsyncIterator[LlmDelta]:
            acc: dict[int, dict] = {}
            finish: str | None = None
            active_kwargs = kwargs
            yielded_any = False
            for attempt in range(len(_ELICE_QUIRK_FIXUPS) + 1):
                try:
                    stream = await client.chat.completions.create(**active_kwargs)
                    async for chunk in stream:
                        text, frags, chunk_finish = elice_chunk_delta(chunk)
                        if chunk_finish:
                            finish = chunk_finish
                        if text:
                            yielded_any = True
                            yield ("text", text)
                        for frag in frags:
                            idx = frag["index"]
                            cur = acc.setdefault(
                                idx, {"id": frag["id"] or f"call_{idx}", "name": "", "args": ""}
                            )
                            if frag["id"]:
                                cur["id"] = frag["id"]
                            if frag["name"]:
                                cur["name"] = frag["name"]
                            if frag["arguments"]:
                                yielded_any = True
                                cur["args"] += frag["arguments"]
                    break
                except Exception as e:  # noqa: BLE001 — 예외 타입을 특정할 수 없어 메시지로만 판별
                    # 일부 최신 모델(reasoning 계열, 예: gpt-5.6-luna)은 표준 chat/completions
                    # 규격과 파라미터가 달라(`max_tokens`→`max_completion_tokens`,
                    # `reasoning_effort` 필요 등) 모델마다 다르고 목록을 미리 알 방법이 없다.
                    # Elice 게이트웨이는 상위 제공자 오류를 **원문 그대로**(유효한 JSON이 아닌
                    # "Upstream error (HTTP N): {원본 JSON}" 텍스트로) 돌려주고, 그것도
                    # `create()` 호출이 아니라 스트림 본문 순회(`async for`) 도중 나온다(HTTP 200
                    # 으로 연결을 먼저 연 뒤 본문에 실어 보낸다) — 그래서 정상적인 openai SDK
                    # 예외 타입으로 잡히지 않는다. `_ELICE_QUIRK_FIXUPS` 에 알려진 오류 메시지
                    # 패턴별 보정을 순서대로 등록해 두고, 매칭되는 것을 찾으면 그 보정을 적용해
                    # 재시도한다. **아직 아무 델타도 내보내지 않았을 때만** 재시도한다 — 이미
                    # 화면에 나간 부분 응답과 재시도 결과가 섞이면 안 된다.
                    if yielded_any:
                        raise
                    fixup = next(
                        (
                            f
                            for needles, f in _ELICE_QUIRK_FIXUPS
                            if all(n in str(e) for n in needles)
                        ),
                        None,
                    )
                    if fixup is None:
                        raise
                    active_kwargs = fixup(active_kwargs, max_tokens)
            for tool_use in elice_finalize_tool_calls(acc):
                yield ("tool_use", tool_use)
            yield ("end", finish or "end_turn")

        return gen()


class FallbackClient:
    """primary 스트림이 **열리기 전에** 실패하면 fallback 으로 넘긴다 (2026-08-29).

    ⛔ **첫 델타가 나간 뒤에는 폴백하지 않는다.** 이미 화면에 토큰이 흘러간 뒤 다른
    모델로 다시 쓰면 중복·모순 출력이 된다 — 그 시점부터는 예외를 그대로 전파해
    호출자가 지금까지 누적된 델타로 판단하게 둔다. `mcp_client` 의 "취소 직후 재호출"
    경계와 같은 종류의 판단이다.

    실패 **유형을 분류하지 않는다.** 크레딧 소진이 어떤 상태코드로 오는지 확정하지
    못했고, 분류에서 빠진 오류가 곧 "폴백이 안 되는 오류"가 된다 — 사이트가 죽지
    않는 쪽을 기본값으로 둔다. 대신 폴백까지 실패하면 예외를 그대로 올린다(D40 태도 —
    조용히 빈 응답을 내지 않는다).

    전환은 WARNING 으로 남긴다. 조용한 전환은 "왜 이번 달 청구서가 있지"가 된다 —
    Elice 장애 때 겪은 조용한 강등(생성 실패가 전부 거부 응답으로 둔갑)의 반복이다.
    로그에는 **예외 타입 이름만** 넣는다: 응답 본문에 키가 섞여 있을 수 있다 (D40).
    """

    def __init__(
        self,
        primary: LlmClient,
        fallback: LlmClient,
        *,
        primary_label: str,
        fallback_label: str,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._primary_label = primary_label
        self._fallback_label = fallback_label

    def stream(
        self, *, system: str, messages: list[dict], tools: list[dict]
    ) -> AsyncIterator[LlmDelta]:
        primary, fallback = self._primary, self._fallback
        primary_label, fallback_label = self._primary_label, self._fallback_label

        async def gen() -> AsyncIterator[LlmDelta]:
            yielded = False
            try:
                async for delta in primary.stream(
                    system=system, messages=messages, tools=tools
                ):
                    yielded = True
                    yield delta
            except Exception as exc:  # noqa: BLE001 — 어떤 실패든 폴백 대상이다
                if yielded:
                    raise  # 이미 나간 토큰이 있다 — 다시 쓰지 않는다
                logger.warning(
                    "LLM 제공자 폴백: %s → %s (원인 %s). 유료 경로로 전환됐다.",
                    primary_label,
                    fallback_label,
                    type(exc).__name__,
                )
                async for delta in fallback.stream(
                    system=system, messages=messages, tools=tools
                ):
                    yield delta

        return gen()


PROVIDERS = ("gemini", "anthropic", "elice", "openai", "nvidia")


def _build_single_client(provider: str, model: str) -> LlmClient:
    """제공자 하나에 대한 클라이언트를 만든다 (D56 — 제공자 분기).

    ⚠ **모델을 인자로 받는다.** 폴백 클라이언트는 primary 와 다른 모델로 만들어져야
    하는데, 여기서 `MAINTQ_LLM_MODEL` 을 직접 읽으면 폴백을 조립하는 쪽이 전역
    환경변수를 잠시 바꿔 끼우는 수밖에 없다 — 전역 상태 변경은 동시 호출에서
    엉키고, 예외 경로에서 원복이 새면 조용히 잘못된 모델로 과금된다.

    **키가 없으면 ScriptedClient 로 폴백하지 않고 실패한다 (D40).**
    스크립트는 테스트가 명시적으로 주입할 때만 쓰인다.
    """
    if provider not in PROVIDERS:
        raise RuntimeError(
            f"MAINTQ_LLM_PROVIDER 는 {PROVIDERS} 중 하나여야 합니다: {provider!r}"
        )

    base_url = ""
    if provider == "gemini":
        # SDK 관례상 두 이름이 통용된다 — GEMINI_API_KEY 를 우선하고 GOOGLE_API_KEY 도 인정
        api_key = (
            os.environ.get("GEMINI_API_KEY", "").strip()
            or os.environ.get("GOOGLE_API_KEY", "").strip()
        )
        key_label = "GEMINI_API_KEY(또는 GOOGLE_API_KEY)"
    elif provider == "elice":
        api_key = os.environ.get("ELICE_API_KEY", "").strip()
        key_label = "ELICE_API_KEY"
        base_url = os.environ.get("ELICE_LLM_URL", "").strip()
    elif provider == "openai":
        # 진단 전용 — Elice/Gemini 특유의 도구 호출 문제(빈 인자 tool_use)인지 격리하려고
        # 실 OpenAI API 를 직접 붙인다. EliceClient 를 그대로 재사용한다(둘 다 OpenAI 호환).
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        key_label = "OPENAI_API_KEY"
        base_url = "https://api.openai.com"
    elif provider == "nvidia":
        # NVIDIA NIM 무료 티어 — OpenAI 호환이라 EliceClient 를 그대로 재사용한다.
        # ⛔ base_url 에 `/v1` 을 붙이지 않는다: EliceClient 가 없으면 붙인다(L422-424).
        #    여기에 박으면 `/v1/v1` 이 된다.
        api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
        key_label = "NVIDIA_API_KEY"
        base_url = "https://integrate.api.nvidia.com"
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        key_label = "ANTHROPIC_API_KEY"

    required = [(key_label, api_key), ("MAINTQ_LLM_MODEL", model)]
    if provider == "elice":
        required.append(("ELICE_LLM_URL", base_url))
    missing = [n for n, v in required if not v]
    if missing:
        raise RuntimeError(
            f"환경변수(또는 .env)에 {' · '.join(missing)} 이(가) 없습니다 "
            f"(provider={provider}). 테스트용 스크립트 응답으로 자동 대체하지 않습니다 "
            "(D40) — 가짜 응답을 진짜로 착각하는 사고를 막기 위해서입니다."
        )
    if provider == "gemini":
        return GeminiClient(model=model, api_key=api_key)
    if provider in ("elice", "openai", "nvidia"):
        return EliceClient(model=model, api_key=api_key, base_url=base_url)
    return AnthropicClient(model=model, api_key=api_key)


def get_client() -> LlmClient:
    """환경변수로 실제 클라이언트를 만든다 (D56 — 제공자 분기, 기본 gemini).

    env 는 **OS 환경변수가 우선**이고 `.env` 는 빈 곳만 채운다 — 로드 지점은
    `backend/main.py` 의 `load_dotenv(override=False)` 한 곳이다 (D56).

    `MAINTQ_LLM_FALLBACK_PROVIDER` 와 `MAINTQ_LLM_FALLBACK_MODEL` 이 **둘 다** 있으면
    `FallbackClient` 로 감싼다 (2026-08-29). 하나만 있으면 켜지 않고 경고만 남긴다 —
    절반만 적용하면 "폴백이 켜진 줄 알았는데 아니었다"가 되고, 그건 폴백이 없는 것보다
    나쁘다. 비어 있으면 이 변경 이전과 완전히 같은 동작이다.
    """
    # `or` — .env 의 빈 키(`MAINTQ_LLM_PROVIDER=`)는 미설정과 같다 (D56, main.py CORS 와 동일 근거)
    provider = (os.environ.get("MAINTQ_LLM_PROVIDER") or "gemini").strip().lower()
    model = os.environ.get("MAINTQ_LLM_MODEL", "").strip()
    inner = _build_single_client(provider, model)

    fb_provider = (os.environ.get("MAINTQ_LLM_FALLBACK_PROVIDER") or "").strip().lower()
    fb_model = (os.environ.get("MAINTQ_LLM_FALLBACK_MODEL") or "").strip()
    if fb_provider and fb_model:
        inner = FallbackClient(
            inner,
            _build_single_client(fb_provider, fb_model),
            primary_label=provider,
            fallback_label=fb_provider,
        )
    elif fb_provider or fb_model:
        logger.warning(
            "MAINTQ_LLM_FALLBACK_PROVIDER 와 MAINTQ_LLM_FALLBACK_MODEL 은 함께 "
            "설정해야 한다 — 하나만 있어 폴백을 켜지 않았다."
        )

    # 카세트는 **명시적 옵트인**이다 (D104). 켜지 않으면 위 클라이언트가 그대로 나간다.
    # ⚠ 폴백보다 **바깥**에 둔다 — 캐시 히트는 제공자 선택 이전에 끝나야 한다.
    from backend.agent.llm_cache import CachingClient, cache_enabled  # noqa: PLC0415

    if cache_enabled():
        return CachingClient(inner, provider=provider, model=model)
    return inner
