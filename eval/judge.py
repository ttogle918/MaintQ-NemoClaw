# -*- coding: utf-8 -*-
"""환각률 LLM judge (MQ-503).

**무엇을 판정하는가.** S4(미지 에러코드) 문항의 응답 텍스트가 매뉴얼에 없다고 정직하게
말하는지, 아니면 구체적 원인·조치를 지어내는지를 별도 LLM 호출로 판정한다. 4지표
(`eval/score.py`)는 이벤트 구조만 보고 응답 문장의 "내용"까지는 못 보므로, 환각률은
`eval/prompts/hallucination_judge.md` 로 LLM 에게 물어 얻는다.

**보수적 fail 원칙.** 판정 자체가 불가능한 경우(빈 응답·JSON 파싱 실패·필수 키 누락)를
`hallucinated=False`(pass)로 봐주면 환각률 0% 지표가 거짓이 될 수 있다 — 전부
`hallucinated=True`(fail)로 처리한다.

**`test_` 접두 금지.** `.claude/settings.json` 의 Stop 훅이 매 턴 `pytest eval/ -q` 를
자동 실행한다. 이 모듈의 함수·파일명에 `test_` 를 쓰면 pytest 가 이 함수를 테스트로
오인해 매 턴 실비용 LLM 호출 사고로 이어진다 — 절대 쓰지 않는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from backend.agent.llm import LlmClient, get_client

_PROMPT_PATH = Path(__file__).parent / "prompts" / "hallucination_judge.md"

#: 판정 불가(빈 입력·파싱 실패·키 누락) 시 공통으로 쓰는 보수적 fail 사유.
_CONSERVATIVE_RATIONALE = "judge 응답 파싱 실패 — 보수적으로 fail 처리"


@dataclass(frozen=True)
class JudgeVerdict:
    """환각 판정 결과. `raw` 는 LLM 원문(디버깅·리포트용)."""

    hallucinated: bool
    rationale: str
    raw: str


def _conservative_fail(raw: str, rationale: str = _CONSERVATIVE_RATIONALE) -> JudgeVerdict:
    return JudgeVerdict(hallucinated=True, rationale=rationale, raw=raw)


def _strip_code_fence(text: str) -> str:
    """Gemini 는 "JSON 만 응답하라"고 지시해도 종종 마크다운 코드펜스(```json ... ```)로
    감싸 돌려준다 — 실 API 스모크(2026-07-29)에서 실측 확인된 동작. 파싱 전에 펜스
    마커만 벗긴다. **내용 자체는 건드리지 않는다** — 펜스가 없으면 원문 그대로 반환하므로
    펜스 없는 응답(다른 제공자 등)에도 안전하다.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.split("\n")
    if len(lines) >= 2 and lines[-1].strip() == "```":
        lines = lines[1:-1]
    else:
        lines = lines[1:]
    return "\n".join(lines).strip()


async def judge_hallucination(
    question: str, response_text: str, *, client: LlmClient | None = None
) -> JudgeVerdict:
    """`response_text` 가 환각(구체적 원인·조치를 근거 없이 단정)인지 LLM 으로 판정한다.

    `client` 미지정 시 `get_client()`(D40) — 키가 없으면 폴백 없이 예외를 낸다.
    빈 `response_text` 는 judge 호출 자체를 건너뛰고 보수적 fail 을 반환한다(API 비용 절약 +
    "판정 불가를 pass 로 봐주지 않는다" 원칙 유지).
    """
    if not response_text:
        return _conservative_fail(raw="", rationale="응답 텍스트 없음 — 보수적으로 fail 처리")

    resolved_client = client or get_client()

    prompt = _PROMPT_PATH.read_text(encoding="utf-8").format(
        question=question, response_text=response_text
    )

    chunks: list[str] = []
    async for kind, payload in resolved_client.stream(
        system="", messages=[{"role": "user", "content": prompt}], tools=[]
    ):
        if kind == "text":
            chunks.append(str(payload))
    raw = "".join(chunks)

    try:
        parsed = json.loads(_strip_code_fence(raw))
    except (json.JSONDecodeError, TypeError):
        return _conservative_fail(raw=raw)

    if not isinstance(parsed, dict) or "hallucinated" not in parsed:
        return _conservative_fail(raw=raw)

    hallucinated = parsed["hallucinated"]
    if not isinstance(hallucinated, bool):
        return _conservative_fail(raw=raw)

    rationale = str(parsed.get("rationale", ""))
    return JudgeVerdict(hallucinated=hallucinated, rationale=rationale, raw=raw)
