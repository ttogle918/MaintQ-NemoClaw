# -*- coding: utf-8 -*-
"""에이전트 루프 — 도구 오케스트레이션 (docs/09_RUNTIME.md §2).

이 루프가 지키는 것:
  A1   `tool_call` 은 도구 호출 **직전** 발행 — trace 패널이 "실행 중"을 보여줄 수 있어야 한다
  A2   `create_po_draft` 는 견적 제시 턴에서 자동 호출하지 않는다 (프롬프트 규칙 6)
  A4   안전 경고·발주 카드·인용은 `block` 으로, **스트리밍 중간 삽입**
  A5   모든 tool_call/tool_result/block 은 발행과 동시에 `traces` 저장 — `TraceWriter` 경유라 자동
  A6   MOQ 미달은 도구가 거부. 루프가 수량을 임의로 올리지 않는다
  A7   `error_history` 에 쓰지 않는다 (D29 — 이력 기록은 루프 밖 사용자 액션)
  A8   S3 보류는 `po_card` variant `hold` (D35·D45)
  D42  **MCP 세션을 열지 않는다.** 주입받은 `McpClient.call()` 만 쓴다

**안전 경고가 이 파일에서 가장 조심스러운 부분이다.** 문구는 상수(`SAFETY_BASELINE`)에서만
오고, 근거 페이지가 없으면 **안전 블록도 위험 절차 서술도 내보내지 않는다.**
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from backend import sse
from backend.agent import prompts
from backend.agent.llm import LlmClient, ToolUse
from backend.agent.mcp_client import TOOL_TIMEOUT_SEC, McpClient, summarize_result
from backend.agent.trace import TraceWriter
from backend.db import connect
from backend.services import po as po_svc

logger = logging.getLogger(__name__)

# 09_RUNTIME §2 — 상한. TOOL_TIMEOUT_SEC 는 mcp_client 소유라 재정의하지 않는다
MAX_TOOL_CALLS_PER_TURN = 8
MAX_LLM_CALLS_PER_TURN = 10
MAX_LLM_CALLS_PER_SESSION = 50
HISTORY_LIMIT = 20

#: 요약에서 탈락하면 안 되는 발주 식별 필드 (09_RUNTIME §2).
#: A2 에 따라 create_po_draft 가 **다음 턴**에 호출되므로 이 값이 유실되면 발주 입력이 부정확해진다.
PRESERVE_FIELDS = (
    "part_no",
    "supplier_id",
    "qty",
    "unit_price",
    "moq",
    "lead_days",
    "po_id",
)

#: 이력 요약에 보존할 중첩 원소 상한 — 전부 넣으면 컨텍스트를 잡아먹는다
_PRESERVE_MAX_ITEMS = 5

#: 문장 종결 판정 — 안전 블록을 문장 **앞에** 끼워 넣으려면 문장 단위로 끊어야 한다
_SENTENCE_ENDINGS = ("다.", "요.", ".", "!", "?", "\n")


class SessionStore:
    """프로세스 메모리 세션 저장소. 단일 사용자 데모 전제 (09_RUNTIME 스코프)."""

    def __init__(self) -> None:
        self._history: dict[str, list[dict]] = {}
        self._llm_calls: dict[str, int] = {}

    def history(self, session_id: str) -> list[dict]:
        return list(self._history.get(session_id, []))

    def append(self, session_id: str, msg: dict) -> None:
        h = self._history.setdefault(session_id, [])
        h.append(msg)
        if len(h) > HISTORY_LIMIT:  # 초과분은 앞에서 절삭
            del h[: len(h) - HISTORY_LIMIT]

    def llm_calls(self, session_id: str) -> int:
        return self._llm_calls.get(session_id, 0)

    def bump_llm(self, session_id: str) -> int:
        n = self._llm_calls.get(session_id, 0) + 1
        self._llm_calls[session_id] = n
        return n


STORE = SessionStore()


def _model_for(equipment_id: str | None) -> str | None:
    """매 턴 equipment 를 조회해 model 을 주입한다 (09_RUNTIME §2 컨텍스트 주입).

    없으면 None — 프롬프트가 "기종을 먼저 확인하는 질문"을 하게 한다. 추측해 채우지 않는다.
    """
    if not equipment_id:
        return None
    try:
        with connect() as con:
            r = con.execute(
                "SELECT model FROM equipment WHERE equipment_id = ?", (equipment_id,)
            ).fetchone()
        return r["model"] if r else None
    except Exception as e:  # noqa: BLE001 — 컨텍스트 주입 실패로 턴을 죽이지 않는다
        logger.warning("장비 컨텍스트 조회 실패 (%s): %s", equipment_id, e)
        return None


def _summarize_for_history(tool: str, payload: dict) -> str:
    """이력에는 요약본만 남긴다 (원문은 traces — D21).

    단 `PRESERVE_FIELDS` 는 요약 뒤에 붙여 유실을 막는다 (A2).
    """
    base = summarize_result(tool, payload)
    kept: list[str] = []

    for key in PRESERVE_FIELDS:
        if key in payload:
            kept.append(f"{key}={payload[key]}")

    # 중첩 리스트는 **전 원소**를 보존한다 (상한 _PRESERVE_MAX_ITEMS).
    # [0] 만 남기면 S1 의 핵심 장면에서 정확히 깨진다 — 견적이 A사·B사 2건인데
    # 이력에 A사만 남으면, 사용자가 "B사로" 라고 말하는 **다음 턴**(A2 그 자체)에
    # SUP-B 의 unit_price·moq·lead_days 가 없어 발주 입력이 부정확해진다.
    for seq_key in ("suppliers", "items", "alternatives"):
        seq = payload.get(seq_key)
        if not isinstance(seq, list):
            continue
        for elem in seq[:_PRESERVE_MAX_ITEMS]:
            if not isinstance(elem, dict):
                continue
            fields = [f"{k}={elem[k]}" for k in PRESERVE_FIELDS if k in elem]
            if fields:
                kept.append("(" + " ".join(fields) + ")")
        if len(seq) > _PRESERVE_MAX_ITEMS:
            kept.append(f"…외 {len(seq) - _PRESERVE_MAX_ITEMS}건")

    return f"{base} | {' '.join(kept)}" if kept else base


def _pages_from(tool: str, payload: dict) -> list[int]:
    """도구 결과에서 인용 가능한 물리 페이지를 뽑는다 (D30 판정의 소스와 동일)."""
    if tool == "lookup_error_code":
        p = payload.get("manual_page")
        return [p] if isinstance(p, int) else []
    if tool == "rag_search_manual":
        return [c["page"] for c in payload.get("chunks", []) if isinstance(c.get("page"), int)]
    return []


async def _safe_stream(llm: LlmClient, **kw) -> AsyncIterator[tuple[str, object]]:
    """LLM 스트림의 예외만 `("_stream_error", exc)` 델타로 바꿔 흘린다.

    호출부의 `try` 안에 소비 로직을 두면 **우리 코드의 버그까지 "LLM 실패"로 삼켜진다** —
    실제로 `SAFETY_BASELINE["title"]` KeyError 가 그렇게 위장돼 안전 블록이 조용히
    발행되지 않은 적이 있다. 예외의 출처를 여기서 분리한다.
    """
    try:
        async for delta in llm.stream(**kw):
            yield delta
    except AssertionError:
        raise  # 스크립트 소진 등 테스트 계약 위반은 그대로 드러낸다
    except Exception as e:  # noqa: BLE001
        logger.warning("LLM 스트림 실패: %s", e)
        yield ("_stream_error", e)


class _TurnState:
    """한 턴 동안의 누적 상태."""

    def __init__(self, model: str | None) -> None:
        self.model = model
        #: 장비 컨텍스트가 없을 때 LLM 이 도구에 넘긴 model 을 관측해 폴백으로 쓴다
        self.observed_model: str | None = None
        self.tool_calls = 0
        self.last_call: tuple[str, str] | None = None
        self.safety_sent = False
        self.citation_sent = False
        self.pages: list[int] = []  # 이 턴에 인용 가능한 페이지 (도구 결과 출처)
        self.sections: dict[int, str] = {}  # page -> 절 제목 (rag 결과에서)
        self.repeated: dict | None = None
        #: get_error_history 호출 시 쓴 조회 창. 도구 **출력**에는 window_days 가 없어서
        #: 입력에서 받아 둔다 (계약을 넓히지 않는다). 도구 입력은 traces 에도 남아 감사와 일치.
        self.repeat_window_days: int = 30
        self.po_created: dict | None = None
        self.results: dict[str, dict] = {}  # tool -> 마지막 payload

    def safety_model(self) -> str:
        return self.model or self.observed_model or ""

    def safety_page(self) -> int | None:
        """안전 문구의 **실제 근거 페이지** (SAFETY_BASELINE["pages"]).

        모델을 끝내 모르면 None — 그때는 안전 블록도 위험 서술도 내지 않는다.
        """
        pages = prompts.SAFETY_BASELINE.get("pages")
        model = self.safety_model()
        if not isinstance(pages, dict) or not model:
            return None
        page = pages.get(model)
        return page if isinstance(page, int) else None


async def run_turn(
    *,
    session_id: str,
    message: str,
    equipment_id: str | None,
    user_id: str,
    llm: LlmClient,
    client: McpClient,
    trace: TraceWriter,
    store: SessionStore | None = None,
) -> AsyncIterator[sse.SseEvent]:
    """한 턴을 실행하며 SSE 이벤트를 순서대로 흘린다.

    **MCP 세션을 열지 않는다** (D42) — `client` 를 주입받아 `call()` 만 한다.
    제너레이터 안에서 `stdio_client` 를 열면 소비자 취소 시 cancel scope 가 오염된다.
    """
    store = store or STORE

    if store.llm_calls(session_id) >= MAX_LLM_CALLS_PER_SESSION:
        yield sse.token("대화가 길어졌습니다. 새 세션을 시작해 주세요.")
        return

    st = _TurnState(_model_for(equipment_id))
    system = prompts.build_system_prompt(st.model, equipment_id=equipment_id)
    tools = await client.list_tools()

    store.append(session_id, {"role": "user", "content": message})
    messages = store.history(session_id)

    buf: list[str] = []  # 문장 버퍼 — 안전 블록을 문장 앞에 끼우려면 필요하다

    async def flush(force: bool = False) -> AsyncIterator[sse.SseEvent]:
        """버퍼를 문장 단위로 내보내되, 위험 서술이면 **안전 블록을 먼저** 낸다 (A4)."""
        text = "".join(buf)
        if not text or (not force and not text.endswith(_SENTENCE_ENDINGS)):
            return
        buf.clear()
        if prompts.needs_safety_block(text) and not st.safety_sent:
            safety_page = st.safety_page()
            # `st.pages` 는 "이 턴에 매뉴얼 근거를 실제로 조회했는가"의 **게이트**일 뿐이다.
            # 인용 페이지는 거기서 오지 않는다 — 아래 참조.
            if st.pages and safety_page is not None:
                st.safety_sent = True
                yield trace.block(
                    "safety",
                    {
                        "title": prompts.SAFETY_BASELINE["title"],
                        "text": prompts.SAFETY_BASELINE["text"],
                        # ★ 안전 문구의 근거는 SAFETY_BASELINE["pages"] 다 (iG5A 4 / S100 2).
                        # 그 턴의 lookup/rag 페이지(202·204 등)를 붙이면 **승인된 안전 문구를
                        # 엉뚱한 매뉴얼 면에 귀속**시키게 된다 — 정비사가 칩을 눌러 그 쪽을
                        # 펴면 방전 대기 문구가 없다. prompts.py 가 QUALIFIED_WORKER_NOTE 를
                        # 분리한 것과 같은 이유다.
                        "citation": sse.citation_payload(st.safety_model(), safety_page),
                    },
                )
            else:
                # 근거 없는 안전 문구를 만들지 않고, 위험 절차 서술도 흘리지 않는다
                yield sse.token("근거 문서를 확인하지 못해 작업 절차를 안내할 수 없습니다.")
                return
        yield sse.token(text)

    for _ in range(MAX_LLM_CALLS_PER_TURN):
        if store.bump_llm(session_id) > MAX_LLM_CALLS_PER_SESSION:
            yield sse.token("대화가 길어졌습니다. 새 세션을 시작해 주세요.")
            return

        pending: list[ToolUse] = []
        assistant_text: list[str] = []

        # LLM 스트림 예외만 잡는다. flush()·block 발행은 **이 밖에서** 처리한다 —
        # 안에 두면 우리 코드의 버그(KeyError 등)가 "LLM 실패"로 위장돼 조용히 우회된다.
        stream = _safe_stream(llm, system=system, messages=messages, tools=tools)
        failed = False
        async for kind, value in stream:
            if kind == "_stream_error":
                failed = True
                break
            if kind == "text":
                buf.append(str(value))
                assistant_text.append(str(value))
                async for ev in flush():
                    yield ev
            elif kind == "tool_use":
                pending.append(value)  # type: ignore[arg-type]

        if failed:
            # 09_RUNTIME §3 — 부분 스트림을 이어 붙이지 않는다
            yield sse.token("응답 생성에 실패했습니다. 다시 시도해 주세요.")
            return

        async for ev in flush(force=True):
            yield ev

        if assistant_text:
            store.append(session_id, {"role": "assistant", "content": "".join(assistant_text)})

        if not pending:
            break  # 도구 호출 없이 텍스트만 → 턴 종료 (09_RUNTIME 종료 조건)

        for tu in pending:
            if st.tool_calls >= MAX_TOOL_CALLS_PER_TURN:
                yield sse.token("확인할 항목이 남아 있어 추가 확인이 필요합니다.")
                pending = []
                break

            sig = (tu.name, json.dumps(tu.input, sort_keys=True, ensure_ascii=False))
            if sig == st.last_call:
                yield sse.token(
                    "같은 조회를 반복하고 있어 중단했습니다. 현재까지 확인된 정보로 답변합니다."
                )
                pending = []
                break
            st.last_call = sig
            st.tool_calls += 1

            # A1 — 호출 "직전" 에 tool_call 을 먼저 흘린다
            yield trace.tool_call(tu.name, tu.input)
            outcome = await client.call(tu.name, tu.input, timeout=TOOL_TIMEOUT_SEC)
            payload = outcome if isinstance(outcome, dict) else {"status": "error"}
            status = str(payload.get("status", "error"))

            summary = summarize_result(tu.name, payload)
            if payload.get("reason") == "timeout":
                summary = f"✗ timeout · {tu.name} 확인 실패"  # D44·D46 표시 규약
            yield trace.tool_result(
                tu.name, status, summary, float(payload.get("_elapsed", 0.0) or 0.0)
            )

            st.results[tu.name] = payload
            store.append(
                session_id,
                {
                    "role": "user",
                    "content": f"[도구 결과 {tu.name}] {_summarize_for_history(tu.name, payload)}",
                },
            )

            if tu.input.get("model") in ("iG5A", "S100"):
                st.observed_model = st.observed_model or tu.input["model"]
            if tu.name == "get_error_history" and isinstance(tu.input.get("days"), int):
                st.repeat_window_days = tu.input["days"]

            if status == "ok":
                for p in _pages_from(tu.name, payload):
                    if p not in st.pages:
                        st.pages.append(p)
                # 절 제목은 인용 라벨에 붙는다 — 안 모으면 항상 None 이 된다
                for c in payload.get("chunks", []) or []:
                    if isinstance(c.get("page"), int) and c.get("section"):
                        st.sections.setdefault(c["page"], c["section"])
                if tu.name == "get_error_history" and payload.get("repeated"):
                    st.repeated = payload
                if tu.name == "create_po_draft" and payload.get("po_id"):
                    st.po_created = payload

        messages = store.history(session_id)
        if not pending:
            break

    # ── 인용 블록: 코드가 도구 결과에서 만든다 (D30 — LLM 이 말한 페이지를 쓰지 않는다)
    if st.pages and st.model and not st.citation_sent:
        st.citation_sent = True
        yield trace.citation(st.model, st.pages[0], st.sections.get(st.pages[0]))

    # ── 발주 카드 (D45·D37)
    if st.po_created:
        async for ev in _emit_po_card(st, trace, user_id, session_id):
            yield ev
    elif st.repeated:
        yield _hold_block(st, trace)


async def _emit_po_card(
    st: _TurnState, trace: TraceWriter, user_id: str, session_id: str
) -> AsyncIterator[sse.SseEvent]:
    """draft 발주 카드 + 신원 stamp.

    `create_po_draft` 응답에는 `part_name`·`supplier_name`·`lead_days` 가 없다.
    **도구 계약을 넓히지 않고** `services.po.get_po()` 로 조립한다.
    """
    po_id = st.po_created["po_id"]
    if not po_svc.stamp_identity(po_id, requested_by=user_id, session_id=session_id):
        logger.warning("신원 stamp 실패 (이미 stamp 됐거나 draft 가 아님): %s", po_id)

    detail = po_svc.get_po(po_id)
    if detail is None:  # 경합 — 카드를 건너뛰고 번호만 알린다. 스트림을 죽이지 않는다
        yield sse.token(f"발주서 초안 {po_id} 를 생성했습니다.")
        return

    lead = next(
        (
            q["lead_days"]
            for q in detail.get("quotes", [])
            if q["supplier_id"] == detail["supplier_id"]
        ),
        None,
    )
    yield trace.block(
        "po_card",
        {
            "variant": "draft",  # D35
            "po_id": po_id,
            "part_no": detail["part_no"],
            "part_name": detail["part_name"],
            "qty": detail["qty"],
            "supplier_name": detail["supplier_name"],
            "lead_days": lead,
            "unit_price": detail["unit_price"],
            "state": detail["state"],
        },
    )


def _hold_block(st: _TurnState, trace: TraceWriter) -> sse.SseEvent:
    """S3 발주 보류 — 발주 카드가 아니다 (D35·A8). payload 는 D45 스키마 고정.

    checklist 의 citation 은 **rag 결과 page 에서만** 만든다 — 근거 없는 체크리스트 금지.
    """
    rag = st.results.get("rag_search_manual", {})
    chunks = rag.get("chunks", []) if rag.get("status") == "ok" else []
    model = st.safety_model()

    # label 은 **매뉴얼 절 제목 그대로** 쓴다. LLM 에게 점검 항목명을 만들게 하면
    # 근거 없는 점검 항목이 안전 블록 옆에 뜬다 — 이 프로젝트가 막으려는 바로 그 실패다.
    # 문항화는 사람 검수가 필요한 성격이라 백로그로 둔다.
    # dedup 은 **label 단위**다. 청크가 페이지 경계를 넘지 않으므로(MQ-305) 한 절이
    # p.204·p.205 에 걸치는 건 흔하다 — (label, page) 로 묶으면 둘 다 남아 label 이 중복되고,
    # 프론트 PoHoldCard 의 key={item.label} 이 충돌한다. 첫 페이지를 대표로 남긴다.
    checklist: list[dict] = []
    seen_labels: set[str] = set()
    for c in chunks:
        page = c.get("page")
        if not isinstance(page, int) or not model:
            continue  # model 을 모르면 계약 형태의 인용을 만들 수 없다 → 항목을 만들지 않는다
        label = c.get("section") or "관련 매뉴얼 절"
        if label in seen_labels:
            continue
        seen_labels.add(label)
        checklist.append(
            {
                "label": label,
                # 중첩 인용도 {page, print_page, label} 형태여야 프론트가 같은 칩으로 렌더한다
                "citation": sse.citation_payload(model, page, c.get("section")),
            }
        )
    return trace.block(
        "po_card",
        {
            "variant": "hold",  # D35 — 같은 슬롯, 다른 variant
            "reason": (
                "반복 고장은 부품 교체만으로 재발할 수 있어, 근본원인이 확정되기 전에는 "
                "발주서를 생성하지 않습니다."
            ),
            "checklist": checklist,
            "repeated": {
                "count": st.repeated.get("count") if st.repeated else 0,
                # 호출에 쓴 조회 창을 그대로 — 30 을 박으면 days=7 호출도 "30일"로 보고된다
                "window_days": st.repeat_window_days,
            },
        },
    )
