# -*- coding: utf-8 -*-
"""대화 라우터 (SSE) — docs/06_REPO_API.md §2.1.

`POST /api/chat` 은 두 경로를 갖는다.

  기본            에이전트 루프 (`backend.agent.loop.run_turn`) — 실 LLM + MCP 도구
  `?replay=s1`    S1 해피패스 **고정 재생** — LLM·MCP 없이 SSE 규격만 흘린다

**replay 를 남겨 두는 이유는 두 가지다.**
  1. SP3 의 SSE 규격 회귀(이벤트 4종·A1 순서·block 중간 삽입)가 **API 키 없이** 상시로 돌아야 한다
  2. replay 도 `traces` 에 행을 남기므로 화면 B trace 페이지(MQ-309)를 API 키 없이 눈으로 확인할 수 있다

그래서 replay 는 "SSE 만 흘리는 지름길"이 아니라 **반드시 `TraceWriter` 를 거친다** (A5·D21).
`sse.*` 를 직접 부르는 이벤트는 traces 에 남지 않아, 그 경로가 하나라도 있으면
"발행=저장"이 코드가 아니라 관례가 된다. `token` 만 예외이고 그건 설계다 (D41).

**이 라우터가 하지 않는 것**
  - `po_drafts` 상태 전이 (A3) — draft→pending 은 `POST /api/po/{id}/submit` 뿐이다
  - MCP 세션 open/close (D42) — lifespan 이 소유한 `request.app.state.mcp` 를 주입만 한다
  - LLM 클라이언트 폴백 (D40) — 키가 없으면 스크립트로 떨어지지 않고 그렇다고 말한다
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend import sse
from backend.agent import prompts
from backend.agent.llm import get_client
from backend.agent.loop import run_turn
from backend.agent.trace import TraceWriter, read_trace
from backend.deps import Caller, caller

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])

# 재생 스트리밍의 체감을 만들기 위한 지연. 테스트에서는 0 에 가깝게 줄인다(`?delay=0.02`).
TOKEN_DELAY = 0.01
#: 도구 "실행"에 걸리는 시간의 재현. tool_call 이 **이 지연 앞에** 나가야 A1 이 성립한다.
TOOL_DELAY_FACTOR = 3

#: 지원하는 재생 시나리오. 오타(`?replay=S1`)를 조용히 실 LLM 경로로 흘리지 않는다 —
#: 키가 없으면 안내 토큰만 나와서 "왜 재생이 안 되지"를 한참 헤매게 된다.
REPLAYS = ("s1",)


class ChatRequest(BaseModel):
    session_id: str
    message: str
    equipment_id: str | None = None  # 미선택이면 에이전트가 모델 확인 질문 (S1 1단계)


# ─────────────────────────────────────────────────────────────────────────────
# S1 고정 재생 — SseEvent 를 yield 한다 (인코딩은 스트리밍 래퍼 한 곳에서)
# ─────────────────────────────────────────────────────────────────────────────


async def _replay_s1(trace: TraceWriter, delay: float) -> AsyncIterator[sse.SseEvent]:
    """S1 해피패스 재생 — `TraceWriter` 경유라 `traces` 에도 그대로 남는다 (A5).

    **인코딩하지 않는다.** `str` 을 yield 하면 traces 저장을 우회하는 지름길이 생기고,
    실제로 이 함수가 그랬다(MQ-308 이전). 이벤트 객체를 흘리고 프레임 직렬화는
    `_encode()` 한 곳에서 한다.

    안전 문구는 `prompts.SAFETY_BASELINE` 상수에서만 온다 — 재생본이라고 문장을 새로
    쓰면 승인된 문안과 데모 화면이 갈린다(safety-guardrail 규칙 1: 매뉴얼 근거 없는
    안전 문구 생성 금지).
    """
    model = "iG5A"

    async def tool(
        name: str, tool_input: dict, status: str, summary: str, elapsed: float
    ) -> AsyncIterator[sse.SseEvent]:
        # A1 — 호출 "직전" 에 tool_call 을 먼저 흘린다. 아래 sleep 이 도구 실행 시간이고,
        # tool_call 은 그 **앞에서 이미 클라이언트로 나가 있어야** trace 패널이 스피너를 띄운다.
        yield trace.tool_call(name, tool_input)
        await asyncio.sleep(delay * TOOL_DELAY_FACTOR)
        yield trace.tool_result(name, status, summary, elapsed)

    async for e in tool(
        "lookup_error_code",
        {"model": model, "code": "OHt"},
        "ok",
        "과열 · related: FAN-IG5-01",
        0.4,
    ):
        yield e

    async for e in tool(
        "rag_search_manual",
        {"model": model, "query": "OHt 점검 절차"},
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
        # token 은 traces 에 저장하지 않는다 (D41) — `TraceWriter.emit()` 이 거부하므로
        # `sse.token()` 을 직접 쓴다. 이건 우회가 아니라 명시된 설계다.
        yield sse.token(t)
        await asyncio.sleep(delay)

    # 인용은 텍스트가 아니라 block 으로 (D22·D32). **인쇄 페이지를 여기서 계산하지 않는다** —
    # `trace.citation` → `sse.citation_for` → `manifest.to_print_page` 가 유일한 변환 지점이다.
    yield trace.citation(model, 202)

    # ── ★ SP3 의 핵심: 위험 절차 서술이 흘러가기 "전"에 안전 경고가 도착해야 한다
    safety_page = prompts.SAFETY_BASELINE["pages"][model]  # type: ignore[index]
    yield trace.block(
        "safety",
        {
            "title": prompts.SAFETY_BASELINE["title"],
            "text": prompts.SAFETY_BASELINE["text"],
            # 중첩 인용도 {page, print_page, label} 형태여야 프론트가 같은 칩으로 렌더한다.
            # 근거 페이지는 안전 문구 자체의 출처(iG5A p.4)이지 그 턴의 조회 페이지가 아니다.
            "citation": sse.citation_payload(model, safety_page),
        },
    )

    # 경고 뒤에 이어지는 위험 절차 서술
    for t in ["커버를 열고 ", "냉각팬 커넥터를 ", "분리하십시오."]:
        yield sse.token(t)
        await asyncio.sleep(delay)

    async for e in tool(
        "search_inventory",
        {"model": model, "part_no": "FAN-IG5-01"},
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

    # 재생이라 `create_po_draft` 를 호출하지 않는다 — 쓰기 도구를 회귀가 돌 때마다 부르면
    # po_drafts 가 계속 늘어난다. 카드 모양(D35 variant)만 보여준다.
    yield trace.block(
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
    )


# ─────────────────────────────────────────────────────────────────────────────
# 에이전트 루프 배선
# ─────────────────────────────────────────────────────────────────────────────


async def _agent_stream(
    request: Request, req: ChatRequest, c: Caller, trace: TraceWriter
) -> AsyncIterator[sse.SseEvent]:
    """실 에이전트 턴. **여기서 MCP 세션도 LLM 폴백도 만들지 않는다.**

    - MCP: lifespan 이 소유한 `app.state.mcp` 를 그대로 주입 (D42). 제너레이터 안에서
      `stdio_client` 를 열면 클라이언트 조기 종료 시 cancel scope 가 다른 태스크에서
      닫히며 무관한 태스크까지 취소된다 — 실측된 결함이다.
    - LLM: `get_client()` 는 키가 없으면 **실패한다** (D40). 여기서 `ScriptedClient` 로
      떨어지면 데모에서 가짜 응답을 진짜로 착각한다. 대신 그 사실을 token 으로 말한다.
    """
    mcp = getattr(request.app.state, "mcp", None)
    # 09_RUNTIME §3 — 도구 서버가 없으면 공백을 지식으로 메우지 않는다.
    #
    # **`mcp is None` 만 보면 안 된다.** lifespan 은 기동에 실패해도 객체를 남긴다
    # (main.py — 승인 큐는 MCP 없이도 살아야 하므로 의도된 설계). 실제 다운 상태는
    # `ready == False` 다. 그대로 진입하면 모든 도구 호출이 `status:"error"` 로만 돌아오고
    # (기동 실패 경로에서는 도구 목록도 비어 있다), 도구 호출이 0건이라 citation·safety
    # 블록이 붙지 않은 채 LLM 이 근거 없는 진단을 스트리밍한다 (절대규칙 6 위반).
    #
    # 판정은 **`ready` 로만** 한다. `list_tools()` 가 비었는지로 대신하지 말 것 —
    # 워커가 도중에 죽는 경로에서는 `_ready=False` 만 내려가고 `_tools` 는 마지막 성공
    # 목록을 그대로 들고 있어서, 목록 검사로 바꾸면 죽은 세션을 조용히 통과시킨다.
    if mcp is None or not mcp.ready:
        detail = getattr(mcp, "start_error", None) if mcp is not None else None
        yield sse.token("도구 서버에 연결할 수 없습니다. 재시도하거나 관리자에게 문의하세요.")
        if detail:
            yield sse.token(f" ({detail})")
        return

    try:
        llm = get_client()
    except Exception as exc:  # noqa: BLE001 — 설정 부재는 500 이 아니라 안내다
        logger.warning("LLM 클라이언트 생성 실패: %s", exc)
        # SSE 는 이미 200 으로 시작한 편이 프론트에 친절하다 — 스트림을 여는 쪽에서
        # 500 을 던지면 EventSource/fetch 소비자가 "연결 실패"와 "설정 미비"를 구분 못 한다.
        yield sse.token(f"{exc}")
        yield sse.token(
            " (SSE 규격만 확인하려면 같은 요청에 ?replay=s1 을 붙이세요 — LLM 없이 재생합니다.)"
        )
        return

    async for ev in run_turn(
        session_id=req.session_id,
        message=req.message,
        equipment_id=req.equipment_id,
        user_id=c.user_id,  # D23·D36·D37 — 신원은 검증된 헤더에서만 온다
        llm=llm,
        client=mcp,
        trace=trace,
    ):
        yield ev


async def _encode(events: AsyncIterator[sse.SseEvent]) -> AsyncIterator[str]:
    """SSE 프레임 직렬화의 **유일한 지점**.

    이벤트 생산자는 전부 `SseEvent` 를 흘린다 — 중간에 `str` 을 섞을 수 있게 두면
    `TraceWriter` 를 우회한 이벤트가 조용히 스트림에 낀다.
    """
    try:
        async for ev in events:
            yield ev.encode()
    except asyncio.CancelledError:
        # 클라이언트 조기 종료. **삼키지 않는다** — 여기서 잡아먹으면 Starlette 이
        # 스트림 종료를 인지하지 못한다. MCP 세션은 이 태스크 소유가 아니므로(D42)
        # 취소가 워커로 새지 않는다.
        raise
    except Exception:
        logger.exception("SSE 스트림 중단 (session 스트림을 닫습니다)")
        yield sse.token("응답 생성에 실패했습니다. 다시 시도해 주세요.").encode()


@router.post("/chat")
async def chat(
    req: ChatRequest,
    request: Request,
    c: Caller = Depends(caller),
    replay: str | None = None,
    delay: float | None = None,
) -> StreamingResponse:
    """대화 턴 — SSE 이벤트 4종 (D14·D22).

    `c` 가 raw `Header` 가 아니라 `Depends(caller)` 인 것이 중요하다. 이 값은
    `run_turn` → `services.po.stamp_identity` 로 흘러 `po_drafts.requested_by` 에
    저장된다 (D37). 검증을 건너뛰면 **D36 위반 값(비 ASCII·미등록 역할)이 DB 에
    들어가는 경로**가 된다 — 헤더 검증은 `deps.caller` 한 곳에서만 한다.
    """
    if replay is not None and replay not in REPLAYS:
        raise HTTPException(400, f"replay 는 {REPLAYS} 중 하나여야 합니다: {replay!r}")

    # ── 진입 표식 (MQ-713b 조사) ────────────────────────────────────────────────
    # **왜 여기인가.** 2026-08-11·12 두 차례 평가에서 문항 10~11개 이후 10문항이
    # 전부 정확히 180초(클라이언트 읽기 타임아웃)로 죽었는데, 서버 로그에는 그 요청들의
    # 흔적이 **한 줄도** 없었다. 그래서 두 가지가 구분되지 않았다:
    #   ⓐ 요청이 서버에 도착했는데 응답이 안 나갔다  (서버 쪽 문제)
    #   ⓑ 요청이 애초에 나가지 못했다               (클라이언트·OS 소켓 문제)
    # 이 한 줄이 있으면 다음 재현에서 **로그에 찍혔는지 여부만으로** 갈린다.
    # WARNING 인 것도 의도다 — uvicorn 기본 설정에서 루트 로거에 핸들러가 없어
    # INFO 는 `logging.lastResort`(WARNING 하한)에 걸려 조용히 사라진다
    # (`loop.py:LLM_END_MARKER` 주석과 같은 이유).
    logger.warning("[CHAT_IN] session=%s replay=%s", req.session_id, replay or "-")

    d = TOKEN_DELAY if delay is None else delay
    # 재생이든 실 루프든 **같은 writer** 를 쓴다 — A5(발행=저장)에 예외 경로를 만들지 않는다.
    # 다만 재생은 `replay: true` 표식을 단다 (D55) — 재생이 traces 에 남기는 합성 행이
    # 실 도구 결과와 구분 불가능하면 실적 판정이 오염된다 (reviewer W-5).
    trace = TraceWriter(req.session_id, replay=replay is not None)

    events = (
        _replay_s1(trace, d) if replay == "s1" else _agent_stream(request, req, c, trace)
    )
    return StreamingResponse(
        _encode(events),
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
