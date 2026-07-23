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

from backend import manifest

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


def citation_data(manual: str, page: int, print_page: int, section: str | None = None) -> dict:
    """인용 payload `{page, print_page, label}` — **인용 형태의 단일 출처** (D32·D45).

    citation 블록만 인용을 담는 게 아니다. 안전 블록의 근거, 발주 보류 체크리스트의
    항목도 **같은 형태**여야 프론트가 하나의 `CitationChip` 으로 렌더한다.
    `{page}` 만 담아 보내면 라벨이 `undefined p.204` 로 뜨고, S100 은 물리 페이지를
    인쇄 페이지인 양 표시해 D32 가 막으려던 문제가 그대로 재발한다.
    """
    label = f"{manual} p.{print_page}"
    if print_page != page:
        label += f" (PDF p.{page})"
    if section:
        label += f" · {section}"
    return {"page": page, "print_page": print_page, "label": label}


def citation_payload(model: str, page: int, section: str | None = None) -> dict:
    """model + PDF 물리 페이지 → 인용 payload. **중첩 인용은 전부 이걸 거친다.**

    오프셋 변환은 여전히 `manifest.to_print_page` 한 곳이다 (D32).
    """
    return citation_data(
        manifest.manual_label(model),
        page=page,
        print_page=manifest.to_print_page(model, page),
        section=section,
    )


def citation_block(manual: str, page: int, print_page: int, section: str | None = None) -> SseEvent:
    """인용 블록 (D32).

    `page` 는 PDF 물리 페이지 — 저장·평가 검증의 단일 기준이라 절대 변환하지 않는다 (D26).
    `print_page` 는 manifest.print_page_offset 을 적용한 값이고, 오프셋 변환은
    **여기 한 곳에서만** 한다. 평가 코드는 계속 `page` 만 본다.
    """
    return block("citation", citation_data(manual, page, print_page, section))


def citation_for(model: str, page: int, section: str | None = None) -> SseEvent:
    """model + PDF 물리 페이지로 인용 블록을 만든다 — **오프셋 변환의 유일한 지점** (D32).

    호출자(에이전트 루프·라우터)는 도구 결과의 물리 페이지를 그대로 넘기면 된다.
    manifest 조회와 인쇄 페이지 환산은 전부 여기 안에서 끝난다. 다른 곳에서
    `print_page` 를 직접 계산하면 D32 의 "변환은 1곳"이 깨진다.

    payload 의 `page` 는 **항상 PDF 물리 원본**이다 (D26) — 인용률 판정이 이 값을
    traces 의 lookup/rag 결과와 대조한다. `print_page` 는 표시용이고, 1 미만이 되는
    구간(표지·안전지침)에서는 환산하지 않고 물리 페이지를 그대로 쓴다 (D49).

    `model` 이 enum 밖이면 ValueError (D6 · D13). manifest 가 없거나 모델이
    목록에 없으면 offset 0 폴백 — `backend.manifest` 가 경고를 남긴다.
    """
    return citation_block(
        manifest.manual_label(model),
        page=page,
        print_page=manifest.to_print_page(model, page),
        section=section,
    )
