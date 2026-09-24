# -*- coding: utf-8 -*-
"""`stage_code_normalization` 을 감싸는 드라이버 쪽 가드 (MQ-1908, SKILL.md 규칙 6).

에이전트(LLM)에게는 MCP 의 `stage_code_normalization` 을 **직접 주지 않고** 이 함수를 준다.
입력 스키마·설명은 MCP 도구의 것을 **그대로 재사용**한다(복제하지 않는다 — MCP 가 바뀌면
여기도 따라 바뀐다). 가드는 세 가지만 한다:

1. **현재 페이지 밖 `row_id` 거부** — 원문 속 주입 문구("row 1 도 저장하라")가 에이전트를
   움직여도 드라이버가 넘기지 않은 행에는 쓰지 못한다.
2. **같은 행 재저장 거부** — 한 행이 `ok` 로 저장되면 그 실행 안에서 두 번째 INSERT 를 막는다
   (정규화 행이 중복으로 쌓이지 않게. 재정규화는 사람이 명시적으로 새 실행을 돌릴 때만).
3. **행당 시도 상한**(기본 2회) — `shape_mismatch` 반복으로 루프를 도는 것을 끊는다.

이것은 **보조 방어선**이다. 최종 판정(confidence·flags·주입 판정)은 여전히 서버
(`mcp_server/onboarding_guard.finalize()`)가 결정적으로 내린다(D145·D154). 가드가 거부한
호출은 MCP 로 가지 않으므로 DB 에 아무것도 쓰지 않는다.
"""

# ⚠ `from __future__ import annotations` 를 쓰지 않는다 — NAT 가 converter 의 반환 주석
# (`-> schema`)을 실제 타입으로 읽는데, 문자열 주석이 되면 `schema` 를 못 찾는다(실측 NameError).
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.component_ref import FunctionRef
from nat.data_models.function import FunctionBaseConfig
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


@dataclass
class PageGuard:
    """드라이버가 페이지마다 `begin()` 으로 허용 행을 정하고, 가드 함수가 호출을 기록한다."""

    max_attempts_per_row: int = 2
    allowed: set[int] = field(default_factory=set)
    attempts: dict[int, int] = field(default_factory=dict)
    ok: dict[int, dict] = field(default_factory=dict)
    last_error: dict[int, str] = field(default_factory=dict)
    refused: dict[str, int] = field(default_factory=dict)
    #: 거절된 호출의 causes_ko **모양만**(원인 수·조치 수) — 번역문은 남기지 않는다(D144).
    last_shape: dict[int, object] = field(default_factory=dict)

    def begin(self, row_ids: list[int]) -> None:
        self.allowed = set(row_ids)

    def check(self, row_id: Any) -> str | None:
        """거부 사유(없으면 None)."""
        rid = _as_int(row_id)
        if rid is None or rid not in self.allowed:
            return "row_not_in_page"
        if rid in self.ok:
            return "already_staged"
        if self.attempts.get(rid, 0) >= self.max_attempts_per_row:
            return "attempts_exhausted"
        return None

    def record(self, row_id: int, raw: str, sent: dict | None = None) -> dict:
        """`sent` = 에이전트가 **보낸** confidence·flags(서버 덮어쓰기 전). 서버의 `forced_by_server`
        는 원문 `source_flags` 가 있으면 에이전트가 이미 보냈어도 `injection_suspect` 를 넣으므로,
        "에이전트가 스스로 알아봤는가" 는 이 값으로만 판정할 수 있다."""
        self.attempts[row_id] = self.attempts.get(row_id, 0) + 1
        parsed = _parse_result(raw)
        if parsed.get("status") == "ok":
            self.ok[row_id] = {**parsed, "agent_sent": sent or {}}
            self.last_error.pop(row_id, None)
        else:
            self.last_error[row_id] = str(parsed.get("reason") or "tool_error")
            if sent is not None and "shape" in sent:
                self.last_shape[row_id] = sent["shape"]
        return parsed

    def refuse(self, reason: str) -> None:
        self.refused[reason] = self.refused.get(reason, 0) + 1


#: 프로세스 전역 가드 — 드라이버(`run_normalize.py`)가 페이지마다 설정한다.
GUARD = PageGuard()

def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _shape(causes: Any) -> object:
    """causes_ko 의 모양 요약 — [(원인 타입, 조치 개수 또는 타입), ...]. 내용은 담지 않는다."""
    if isinstance(causes, str):
        try:
            causes = json.loads(causes)
        except ValueError:
            return "str(unparsable)"
    if not isinstance(causes, list):
        return type(causes).__name__
    out = []
    for c in causes:
        if not isinstance(c, dict):
            out.append(type(c).__name__)
            continue
        sol = c.get("solutions")
        out.append([type(c.get("cause")).__name__, len(sol) if isinstance(sol, list) else type(sol).__name__])
    return out


def _parse_result(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {"status": "error", "reason": "unparsable_tool_result"}
    return parsed if isinstance(parsed, dict) else {"status": "error", "reason": "unparsable_tool_result"}


class GuardedStageConfig(FunctionBaseConfig, name="maintq_guarded_stage"):
    """MCP `stage_code_normalization` 을 페이지 가드로 감싼 함수."""

    target: FunctionRef = Field(description="감쌀 MCP 함수 (예: maintq__stage_code_normalization)")


@register_function(config_type=GuardedStageConfig)
async def guarded_stage(config: GuardedStageConfig, builder: Builder):
    inner = await builder.get_function(config.target)
    schema = inner.input_schema

    async def _fn(tool_input: BaseModel | None = None, **kwargs) -> str:
        if tool_input is not None:
            args = tool_input.model_dump(exclude_none=True, mode="json")
        else:
            args = {k: v for k, v in kwargs.items() if v is not None}
        reason = GUARD.check(args.get("row_id"))
        if reason is not None:
            GUARD.refuse(reason)
            logger.warning("guarded_stage 거부: row_id=%r reason=%s", args.get("row_id"), reason)
            return json.dumps(
                {
                    "status": "error",
                    "reason": f"driver_refused_{reason}",
                    "message": "이 행은 지금 저장할 수 없습니다 — 받은 행에 대해서만, 행당 1회 호출하세요",
                },
                ensure_ascii=False,
            )
        raw = await inner.acall_invoke(**args)
        sent = {
            "confidence": args.get("confidence"),
            "flags": list(args.get("flags") or []),
            "shape": _shape(args.get("causes_ko")),
        }
        GUARD.record(_as_int(args.get("row_id")), raw, sent)
        return raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)

    def _from_str(input_str: str) -> schema:  # type: ignore[valid-type]
        return schema.model_validate_json(input_str)

    yield FunctionInfo.create(
        single_fn=_fn,
        description=inner.description,
        input_schema=schema,
        converters=[_from_str],
    )
