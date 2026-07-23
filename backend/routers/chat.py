# -*- coding: utf-8 -*-
"""대화 라우터 (SSE) — docs/06_REPO_API.md §2.1.

SP3 단계라 에이전트 루프 대신 **S1 시나리오를 고정 재생**한다.
검증 대상은 스트리밍 규격 자체다:
  - 이벤트 4종이 구분 수신되는가 (D14·D22)
  - tool_call 이 도구 호출 "직전"에 오는가 (A1)
  - block 이 token 스트림 **중간**에 삽입되는가 (D22) ← SP3 의 핵심 질문

`GET /chat/{session_id}/trace` (MQ-307) 는 이 재생 경로와 독립이다 — `traces` 테이블만
읽으며, 재생이 traces 에 쓰도록 배선하는 건 MQ-308 의 몫이다.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend import sse
from backend.agent.trace import read_trace
from backend.deps import Caller, caller

router = APIRouter(prefix="/api", tags=["chat"])

# 스트리밍 체감을 만들기 위한 지연. 테스트에서는 0 으로 줄인다.
TOKEN_DELAY = 0.01
TOOL_DELAY = 0.03


class ChatRequest(BaseModel):
    session_id: str
    message: str
    equipment_id: str | None = None  # 미선택이면 에이전트가 모델 확인 질문 (S1 1단계)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _replay_s1(delay: float) -> AsyncIterator[str]:
    """S1 해피패스 재생. M2 에서 에이전트 루프 출력으로 교체된다."""

    async def tool(name: str, tool_input: dict, status: str, summary: str, elapsed: float):
        # A1 — 호출 "직전" 에 tool_call 을 먼저 흘린다
        yield sse.tool_call(name, tool_input, _now()).encode()
        await asyncio.sleep(delay * 3)
        yield sse.tool_result(name, status, summary, elapsed).encode()

    async for e in tool(
        "lookup_error_code",
        {"model": "iG5A", "code": "OHt"},
        "ok",
        "과열 · related: FAN-IG5-01",
        0.4,
    ):
        yield e

    async for e in tool(
        "rag_search_manual",
        {"model": "iG5A", "query": "OHt 점검 절차"},
        "ok",
        "p.202 인용 2건",
        1.2,
    ):
        yield e

    # ── 진단 서술 시작
    for t in [
        "OHt",
        " — ",
        "인버터 과열",
        "입니다. ",
        "유력 원인은 ",
        "냉각팬 고장·주위 온도 초과.",
    ]:
        yield sse.token(t).encode()
        await asyncio.sleep(delay)

    # 인용은 텍스트가 아니라 block 으로 (D22·D32)
    yield sse.citation_block("iG5A 매뉴얼", page=202, print_page=202).encode()

    # ── ★ SP3 의 핵심: 위험 절차 서술이 흘러가기 "전"에 안전 경고가 도착해야 한다
    yield sse.block(
        "safety",
        {
            "title": "SAFETY · 감전 위험",
            "text": "커버 개방 전 전원 차단 후 10분 이상 대기, 테스터로 직류 전압 방전 확인.",
            "citation": {"page": 4, "print_page": 4, "label": "iG5A 매뉴얼 p.4"},
        },
    ).encode()

    # 경고 뒤에 이어지는 위험 절차 서술
    for t in ["커버를 열고 ", "냉각팬 커넥터를 ", "분리하십시오."]:
        yield sse.token(t).encode()
        await asyncio.sleep(delay)

    async for e in tool(
        "search_inventory",
        {"model": "iG5A", "part_no": "FAN-IG5-01"},
        "ok",
        "재고 1 < 안전재고 3 → 부족분 2",
        0.2,
    ):
        yield e

    async for e in tool(
        "get_supplier_quotes",
        {"part_no": "FAN-IG5-01", "qty": 2},
        "ok",
        "A사 3일 vs B사 14일(MOQ 10)",
        0.3,
    ):
        yield e

    yield sse.block(
        "po_card",
        {
            "variant": "draft",  # D35 — 보류는 variant:"hold"
            "po_id": "PO-0117",
            "part_no": "FAN-IG5-01",
            "part_name": "냉각팬",
            "qty": 2,
            "supplier_name": "A사",
            "lead_days": 3,
            "unit_price": 38000,
            "state": "draft",
        },
    ).encode()


@router.post("/chat")
async def chat(
    req: ChatRequest,
    x_role: str = Header(default="technician"),
    # ASCII 사용자 ID. 표시명(김OO)은 서버가 매핑한다 — HTTP 헤더 값은 ASCII 만 (D36)
    x_user: str = Header(default="tech-01"),
    delay: float | None = None,
) -> StreamingResponse:
    d = TOKEN_DELAY if delay is None else delay
    return StreamingResponse(
        _replay_s1(d),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/chat/{session_id}/trace")
def get_trace(session_id: str, c: Caller = Depends(caller)) -> dict:
    """세션 trace 전체 조회 (D21·D43) — 화면 B '실행 로그 보기' · SSE 끊김 폴백.

    **응답 스키마를 여기서 다시 만들지 않는다.** D43(`{session_id, count, events:[...]}`)의
    단일 구현체는 `backend.agent.trace.read_trace` 이고 이 핸들러는 그 반환을 그대로 흘린다 —
    같은 스키마를 두 곳에서 조립하면 화면 B(MQ-309)와 평가 판정이 서로 다른 모양을 보게 된다.
    `ts` 의 `...Z` 표기(D39)도 `read_trace` 가 `iso_utc` 로 붙인다.

    **없는 세션은 404 가 아니라 200 + `count:0`** (D43). 아직 도구를 한 번도 부르지 않은
    세션은 정상 상태이고, `services/po.trace_url` 이 항상 유효해야 프론트 분기가 늘지 않는다.

    **역할 제한 없음** (D43) — `Depends(caller)` 는 헤더 검증(D36 ASCII·역할 enum)만 한다.
    팀장의 링크이자 정비사의 SSE 폴백 경로라 어느 한쪽으로 좁히면 다른 쪽이 막힌다.

    read_trace 는 동기 SQLite 호출이라 `def` 로 둔다 — `async def` 로 두면 이벤트 루프를
    막아 같은 워커의 SSE 스트림이 함께 멈춘다.
    """
    return read_trace(session_id)
