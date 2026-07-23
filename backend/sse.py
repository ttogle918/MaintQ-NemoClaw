# -*- coding: utf-8 -*-
"""SSE 이벤트 발행 (D14 · D22) — 이벤트는 4종으로 고정한다.

  token        LLM 응답 토큰
  tool_call    도구 호출 **직전** 발행 (A1) — trace 패널이 "실행 중"을 보여줘야 함
  tool_result  도구 완료
  block        구조화 블록 — safety / po_card / citation (D22)

block 이 필요한 이유: 안전 경고는 **스트리밍 중간 삽입**이 돼야 한다.
마지막에 몰아 보내면 위험 절차 서술이 먼저 흘러가고 경고가 뒤늦게 도착한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

EventType = Literal["token", "tool_call", "tool_result", "block"]
BlockType = Literal["safety", "po_card", "citation"]

EVENT_TYPES: tuple[EventType, ...] = ("token", "tool_call", "tool_result", "block")


@dataclass(frozen=True)
class SseEvent:
    event: EventType
    data: dict

    def encode(self) -> str:
        """SSE 프레임. data 는 한 줄 JSON — 개행이 프레임을 깨지 않게."""
        body = json.dumps(self.data, ensure_ascii=False)
        return f"event: {self.event}\ndata: {body}\n\n"


def token(text: str) -> SseEvent:
    return SseEvent("token", {"text": text})


def tool_call(tool: str, tool_input: dict, ts: str) -> SseEvent:
    return SseEvent("tool_call", {"tool": tool, "input": tool_input, "ts": ts})


def tool_result(tool: str, status: str, summary: str, elapsed: float) -> SseEvent:
    return SseEvent(
        "tool_result",
        {"tool": tool, "status": status, "summary": summary, "elapsed": elapsed},
    )


def block(block_type: BlockType, data: dict) -> SseEvent:
    return SseEvent("block", {"type": block_type, "data": data})


def citation_block(manual: str, page: int, print_page: int, section: str | None = None) -> SseEvent:
    """인용 블록 (D32).

    `page` 는 PDF 물리 페이지 — 저장·평가 검증의 단일 기준이라 절대 변환하지 않는다 (D26).
    `print_page` 는 manifest.print_page_offset 을 적용한 값이고, 오프셋 변환은
    **여기 한 곳에서만** 한다. 평가 코드는 계속 `page` 만 본다.
    """
    label = f"{manual} p.{print_page}"
    if print_page != page:
        label += f" (PDF p.{page})"
    if section:
        label += f" · {section}"
    return block("citation", {"page": page, "print_page": print_page, "label": label})
