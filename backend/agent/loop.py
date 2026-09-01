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
import time
from collections.abc import AsyncIterator

from backend import sse
from backend.agent import prompts
from backend.agent.llm import LlmClient, ToolUse
from backend.agent.mcp_client import TOOL_TIMEOUT_SEC, McpClient, summarize_result
from backend.agent.trace import TraceWriter
from backend.db import connect
from backend.services import po as po_svc

logger = logging.getLogger(__name__)

# 09_RUNTIME §2 — 상한. TOOL_TIMEOUT_SEC(기본 10초, mcp_client 소유)는 도구별로 재정의하지
# 않는 게 원칙이지만, search_insurance_clause 하나만 예외를 둔다 — InsuQ RAG 파이프라인 실측
# 응답 시간이 ~11.3초(2026-08-24 리허설, curl 직결 확인)라 기본 10초로는 구조적으로 항상
# 타임아웃난다. 다른 18종 도구는 기본값 그대로 — 이 사전은 "예외 목록"이지 새 기본값이 아니다.
_TOOL_TIMEOUT_OVERRIDES: dict[str, float] = {
    "search_insurance_clause": 25.0,
}
MAX_TOOL_CALLS_PER_TURN = 8
MAX_LLM_CALLS_PER_TURN = 10
MAX_LLM_CALLS_PER_SESSION = 50
HISTORY_LIMIT = 20

#: A2A 상관관계 키(`request_chain_id`)를 SSE `tool_result` 에 실어 나르는 도구 (MQ-1604, D113).
#: 그 외 도구는 `payload` 에 이 키가 있어도(있을 리 없지만) 무시된다.
_A2A_CHAIN_TOOLS = ("search_insurance_clause", "assess_equipment_loan")

#: 이력에서 **잘라낼** 경로만 나열한다 (D76 — 화이트리스트가 아니라 블랙리스트).
#: 키는 payload 루트부터의 경로, 값은 `"drop"`(통째 제거) 또는 int(문자 상한).
#:
#: 여기 없는 필드는 **전부 원형 그대로** 간다 — 새 도구가 새 필드를 돌려줘도
#: 자동으로 보존된다. 빠뜨렸을 때의 대가가 "환각"이 아니라 "토큰 조금 더"다.
HISTORY_DROP: dict[tuple[str, ...], object] = {
    # rag 청크 본문 — 최대 900자 × top_k. 절차 원문은 안전 블록·인용이 코드로 실어 나르므로
    # (D22·D32) LLM 이력에는 어느 페이지의 어느 절인지만 있으면 된다.
    ("chunks", "text"): 400,
}

#: 리스트 원소 상한. 초과분은 "…외 N건 생략" 표식을 남긴다 — 조용히 줄이지 않는다.
#: 5 였다가 10 으로 올렸다: 견적이 A사·B사 2건인데 이력에 A사만 남으면 사용자가
#: "B사로" 라고 말하는 **다음 턴**(A2)에 SUP-B 의 단가·MOQ 가 없어 발주가 틀어진다.
HISTORY_MAX_ITEMS = 10

#: 문장 종결 판정 — 안전 블록을 문장 **앞에** 끼워 넣으려면 문장 단위로 끊어야 한다
_SENTENCE_ENDINGS = ("다.", "요.", ".", "!", "?", "\n")

# ────────────────────────────────────────────── LLM 종료 사유 계측 (MQ-713a ③)
#
# **왜 필요한가.** `llm.py` 는 스트림 끝에 `("end", finish_reason)` 델타를 흘리는데
# 이 루프가 그걸 **읽지 않고 버리고 있었다.** 그래서 `MAX_TOKENS` 로 잘린 응답과 모델이
# 스스로 끝낸 응답이 **구분되지 않았다** — 3차 평가에서 "에이전트가 되묻고 턴을 끝낸다"로
# 결론낸 실패들이 실제로는 잘림일 수도 있는데, 두 기전은 고칠 곳이 완전히 다르다
# (프롬프트 vs `max_output_tokens`). 측정 없이 다음 회차를 돌리면 같은 자리로 돌아온다.
#
# **왜 `traces` 행이 아닌가 (판단 근거).** 처음 설계는 `TraceWriter` 로 별도 trace 행을
# 남기는 것이었고, 실제로 그게 자연스럽다. 그런데 그 경로는 **막혀 있다**:
#   1. `traces.event_type` 의 CHECK 가 `tool_call|tool_result|block` 3종뿐이다
#      (`data/seed.py`, D41). 4번째 종류를 INSERT 하면 `IntegrityError` 로 튕긴다.
#   2. SQLite 는 CHECK 를 `ALTER TABLE` 로 못 바꾼다 — 테이블 재작성 마이그레이션이 필요하고,
#      평가는 **실 DB 사본**으로 도므로 사본도 옛 CHECK 를 그대로 물려받는다. 즉 "기록했다고
#      믿었는데 전부 거부되는" 최악의 실패가 조용히 난다.
#   3. `block` 타입을 하나 더 만드는 우회도 막혀 있다 — block 은 `safety|po_card|citation`
#      3종 고정이다 (D14·D22, 09_RUNTIME §3 각주가 `decision_card` 를 만들지 않은 이유).
#   4. 기존 이벤트 payload 에 얹는 것도 안 된다. `payload` 는 **SSE `data` 와 바이트 동일**이
#      계약이고(D30, `trace_persist ②`·`sp3 ⑬` 이 바이트로 대조한다), 무엇보다
#      **도구를 한 번도 안 부른 턴에는 trace 행 자체가 없다** — T08 처럼 잘림이 가장 의심되는
#      경우가 정확히 그 경우라 얹을 행이 존재하지 않는다.
# 그래서 스키마·계약을 건드리지 않고 **서버측 로그 한 줄**로 남긴다. `eval/run_eval.py` 가
# 이미 자식 서버의 stderr 를 회수하고 있어(`_shutdown_server`) 추가 채널을 만들지 않아도 된다.
# ⛔ SSE 이벤트는 4종 그대로다 — 프론트로 새 이벤트가 나가지 않는다.
#
# 로그 레벨을 WARNING 으로 고정한 것도 의도다. 정상 턴을 INFO 로 낮추면 uvicorn 기본
# 설정에서 루트 로거에 핸들러가 없어 `logging.lastResort`(WARNING 하한)에 걸려 **사라진다.**
# 그러면 "잘림 0건"과 "계측이 안 됐다"를 구분할 수 없게 되는데, 이번 계측의 목적이 바로
# 그 구분이다.
LLM_END_MARKER = "[LLM_END]"

#: 잘림으로 셀 종료 사유. Gemini 는 `FinishReason.MAX_TOKENS`, Anthropic 은 `max_tokens`,
#: OpenAI 계열은 `length` 를 쓴다 — `_normalize_finish_reason` 이 셋 다 여기로 정규화한다.
TRUNCATION_REASONS: frozenset[str] = frozenset({"MAX_TOKENS", "LENGTH"})


def normalize_finish_reason(raw: object) -> str:
    """제공자별 stop reason 표기를 대문자 토큰 하나로 정규화한다.

    `FinishReason.MAX_TOKENS`(enum repr) → `MAX_TOKENS`, `max_tokens` → `MAX_TOKENS`,
    `end_turn` → `END_TURN`. 값이 없으면 지어내지 않고 `UNKNOWN` 이다.
    """
    text = str(raw).strip() if raw is not None else ""
    if not text:
        return "UNKNOWN"
    text = text.rsplit(".", 1)[-1]  # enum repr 의 앞부분을 떨군다
    cleaned = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in text)
    return cleaned.upper() or "UNKNOWN"


def is_truncated(raw: object) -> bool:
    """이 종료 사유가 **출력 잘림**인가 (max_output_tokens / thinking 예산 소진)."""
    return normalize_finish_reason(raw) in TRUNCATION_REASONS


def format_llm_end(session_id: str, call_index: int, raw: object) -> str:
    """계측 한 줄. `eval/run_eval.py:parse_llm_end` 가 이 형식을 파싱한다 (양끝을 스파이크가 묶는다)."""
    reason = normalize_finish_reason(raw)
    return (
        f"{LLM_END_MARKER} session={session_id} call={call_index} "
        f"reason={reason} truncated={1 if reason in TRUNCATION_REASONS else 0}"
    )


def record_llm_end(session_id: str, call_index: int, raw: object) -> str:
    """종료 사유를 서버측에 기록하고 기록한 줄을 돌려준다(테스트가 같은 문자열을 본다)."""
    line = format_llm_end(session_id, call_index, raw)
    logger.warning("%s", line)
    return line


class SessionStore:
    """프로세스 메모리 세션 저장소. 단일 사용자 데모 전제 (09_RUNTIME 스코프)."""

    def __init__(self) -> None:
        self._history: dict[str, list[dict]] = {}
        self._llm_calls: dict[str, int] = {}

    def history(self, session_id: str) -> list[dict]:
        return list(self._history.get(session_id, []))

    #: 절삭 우선순위 — **먼저 버릴 것부터**. 사용자 메시지가 맨 뒤인 것이 핵심이다.
    #: 도구 결과는 재호출로 되살릴 수 있지만 **사용자가 한 말은 되살릴 방법이 없다**.
    _EVICT_ORDER: tuple[str, ...] = ("tool", "assistant", "user")

    def append(self, session_id: str, msg: dict) -> None:
        """이력에 한 건 추가하고, 상한을 넘으면 **역할을 보고** 골라 버린다.

        ⛔ 예전에는 `del h[: len(h) - HISTORY_LIMIT]` 로 **무조건 앞에서** 잘랐다.
        이력에는 셋이 쌓이는데(사용자 메시지 · 어시스턴트 응답 · 도구 결과 D76), 처분·발주
        흐름은 턴당 도구를 2~3개 부르므로 몇 턴 만에 상한을 넘고 **1턴의 사용자 메시지가
        가장 먼저 사라졌다** — 하필 사용자가 처음 말한 핵심 사실(자산 ID 등)이다.
        2026-08-31 촬영에서 "2턴에서 1턴의 자산 ID를 잊는" 증상으로 드러났다.

        ⚠️ **같은 계열 사고의 재발이다.** `HISTORY_MAX_ITEMS` 주석(위)이 기록한
        "견적 2건 중 A사만 남으면 다음 턴 발주가 틀어진다"와 같은 함정이 한 단계 위에서
        다시 났다. 상한을 키우는 건 답이 아니다 — 토큰·비용을 밀어올릴 뿐 순서가 그대로면
        같은 것이 또 사라진다. **무엇을 먼저 버리느냐**가 문제였다.

        절삭은 조용히 하지 않는다 — 사용자·어시스턴트 메시지를 버리게 되면 경고를 남긴다.
        """
        h = self._history.setdefault(session_id, [])
        h.append(msg)
        over = len(h) - HISTORY_LIMIT
        if over <= 0:
            return

        dropped: dict[str, int] = {}
        for role in self._EVICT_ORDER:
            i = 0
            while over > 0 and i < len(h):
                if h[i].get("role") == role:
                    del h[i]
                    over -= 1
                    dropped[role] = dropped.get(role, 0) + 1
                else:
                    i += 1
            if over <= 0:
                break

        # 도구 결과만 버렸으면 정상 운영이다(재호출로 되살릴 수 있다). 사용자·어시스턴트
        # 메시지까지 버렸다면 대화가 실제로 짧아진 것이므로 그 사실을 남긴다.
        if dropped.get("user") or dropped.get("assistant"):
            logger.warning(
                "대화 이력 절삭 — 세션 %s, 버린 것 %s (상한 %d). 사용자 메시지가 사라지면 "
                "에이전트가 앞서 받은 사실을 다시 묻게 된다.",
                session_id,
                dropped,
                HISTORY_LIMIT,
            )

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


def _history_payload(tool: str, payload: dict) -> dict:
    """이력에 넣을 도구 결과 — **구조를 보존한다** (D76).

    ~~화이트리스트(`PRESERVE_FIELDS`)~~ 를 버리고 **블랙리스트**로 뒤집었다.
    실패 방향이 바뀌는 게 요점이다:

      화이트리스트 — 넣을 걸 나열한다. 빠뜨리면 값이 사라지고 **에이전트가 지어낸다.**
                     2026-08-05 부품 특정 0/15 가 이 구조에서 났다
                     (`related_parts` 가 스칼라 루프에도 중첩 dict 루프에도 안 걸림).
      블랙리스트 — 뺄 걸 나열한다. 빠뜨려도 **토큰을 조금 더 쓸 뿐**이다.

    도구가 7종에서 16종으로 늘어도(Sprint 6) 샐 표면이 커지지 않는다.
    잘라내는 건 **부피가 큰 자연어 본문뿐**이고, 판단에 쓰이는 식별자·수치는 전부 남는다.
    """
    trimmed = _trim(payload, ())
    # `summary` 는 사람이 읽는 한 줄이라 LLM 에게는 중복이지만, 도구가 실패했을 때
    # (status != ok) 이유가 여기 담기는 경우가 있어 같이 넘긴다.
    trimmed.setdefault("_summary", summarize_result(tool, payload))
    return trimmed


def _trim(node: object, path: tuple[str, ...]) -> object:
    """`HISTORY_DROP` 경로만 잘라낸 사본. 그 외는 원형 그대로."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            here = (*path, k)
            rule = HISTORY_DROP.get(here)
            if rule is None:
                out[k] = _trim(v, here)
            elif rule == "drop":
                continue
            else:  # 길이 상한 — 자른 사실을 값 안에 남긴다 (조용히 줄이지 않는다)
                text = str(v)
                out[k] = text if len(text) <= rule else text[:rule] + f"…(총 {len(text)}자)"
        return out
    if isinstance(node, list):
        if len(node) > HISTORY_MAX_ITEMS:
            head = [_trim(x, path) for x in node[:HISTORY_MAX_ITEMS]]
            return [*head, f"…외 {len(node) - HISTORY_MAX_ITEMS}건 생략"]
        return [_trim(x, path) for x in node]
    return node


def _pages_from(tool: str, payload: dict) -> list[int]:
    """도구 결과에서 인용 가능한 물리 페이지를 뽑는다 (D30 판정의 소스와 동일)."""
    if tool == "lookup_error_code":
        p = payload.get("manual_page")
        return [p] if isinstance(p, int) else []
    if tool == "rag_search_manual":
        return [c["page"] for c in payload.get("chunks", []) if isinstance(c.get("page"), int)]
    return []


def _parts_from(tool: str, payload: dict) -> list[str]:
    """도구 결과가 특정한 부품 품번을 뽑는다 (D66 판정의 소스).

    `find_alternative_parts` 는 **`compat_confirmed` 인 것만** 싣는다 — 미확인 호환품은
    제안 자체가 금지(D20·규칙 4)라 "특정한 부품"이 아니다. 실어 두면 평가가 제안하면
    안 되는 부품을 정답으로 셀 수 있다.
    """
    if tool == "search_inventory":
        return [i["part_no"] for i in payload.get("items", []) if i.get("part_no")]
    if tool == "find_alternative_parts":
        return [
            a["part_no"]
            for a in payload.get("alternatives", [])
            if a.get("part_no") and a.get("compat_confirmed")
        ]
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
        #: 이 턴이 **부품 교체를 다루고 있는가** (MQ-713 후보 C).
        #: 안전 블록 트리거가 `DANGER_KEYWORDS` **응답 텍스트 매칭** 하나뿐이라,
        #: 모델이 같은 작업을 그 단어들 없이 서술하면 블록이 안 붙었다 —
        #: 4차 실측: `rag_search_manual` 을 부르고 교체를 안내했는데도 safety FAIL
        #: (T13 r2·r3 · T15 전 회차). 인버터 부품 교체는 함체 개방을 전제하므로
        #: (parts 카테고리 제어 8·전원 10·구동 8·냉각 7 — 소모품 3만 예외)
        #: 표현이 달라도 위험 작업이다.
        #: ⛔ 이 플래그는 **발행 조건을 넓히기만 한다.** 억제(근거 없을 때 서술 차단)
        #:    경로는 건드리지 않는다 — 넓히면 근거 없는 턴의 답변까지 잘려 나간다.
        self.replacement_ctx = False
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
    # 도구 목록을 **먼저** 받아 프롬프트에 넘긴다 (D69). 프롬프트가 `MAINTQ_TOOLS_PROFILE`
    # 을 따로 읽으면 등록(자식 프로세스)과 지시(백엔드)가 어긋날 수 있다 —
    # 실제 목록을 넘기면 "없는 도구의 사용법을 지시"하는 상태가 구조적으로 불가능해진다.
    tools = await client.list_tools()
    system = prompts.build_system_prompt(
        st.model, equipment_id=equipment_id, tool_names=[t["name"] for t in tools]
    )

    store.append(session_id, {"role": "user", "content": message})
    messages = store.history(session_id)

    buf: list[str] = []  # 문장 버퍼 — 안전 블록을 문장 앞에 끼우려면 필요하다

    async def flush(force: bool = False) -> AsyncIterator[sse.SseEvent]:
        """버퍼를 문장 단위로 내보내되, 위험 서술이면 **안전 블록을 먼저** 낸다 (A4)."""
        text = "".join(buf)
        if not text or (not force and not text.endswith(_SENTENCE_ENDINGS)):
            return
        buf.clear()
        # 트리거 2종 — **넓히기만 한다** (후보 C).
        #   ⓐ 기존: 응답 텍스트의 위험 작업 키워드 (safety-guardrail 규칙 2)
        #   ⓑ 신규: **근거가 이미 확보된** 부품 교체 맥락. `st.pages` 를 조건에 포함해
        #      두었으므로 이 갈래는 아래 `else`(억제) 분기에 **도달하지 않는다** —
        #      즉 근거 없는 턴의 답변이 새로 잘려 나가는 일이 없다.
        grounded_replacement = bool(st.pages) and st.replacement_ctx
        if (prompts.needs_safety_block(text) or grounded_replacement) and not st.safety_sent:
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
        #: `("end", stop_reason)` 델타. 이전에는 이 분기가 없어 **버려지고 있었다** —
        #: 잘린 응답과 스스로 끝낸 응답이 구분되지 않던 자리다 (MQ-713a ③).
        finish_raw: object | None = None
        saw_end = False
        async for kind, value in stream:
            # 캐시 히트면 이 턴을 D55 재생으로 표식한다 — `eval/score.has_replay()` 가
            # 지표 분모에서 뺀다. ⚠ 이 세 줄이 빠지면 캐시 히트가 지표에 **조용히** 섞인다.
            # `_safe_stream` 이 async generator 라 `llm.stream()` 은 첫 델타를 당길 때
            # 호출된다 — 그래서 루프 밖이 아니라 **첫 회차 안**에서 읽는다.
            if not trace.replay and getattr(llm, "last_hit", False):
                trace.replay = True
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
            elif kind == "end":
                finish_raw = value
                saw_end = True

        # 위 루프 안의 판정과 **같은 조건을 멱등하게 한 번 더** 건다. 카세트가 빈 델타
        # 목록으로 끝나면(정상 경로에서는 llm_cache.py 가 그런 카세트를 애초에 안 쓰지만,
        # 이미 존재하는 파일이나 향후 리팩터가 그 전제를 깰 수 있다) `async for` 루프가
        # 한 번도 안 돌아 안쪽 판정이 통째로 스킵된다 — 그 경우에도 히트라면 여기서 켠다.
        if not trace.replay and getattr(llm, "last_hit", False):
            trace.replay = True

        # 종료 사유 기록. 스트림 실패도 같은 줄로 남긴다 — 마커가 아예 없는 것과
        # "실패해서 끝났다"는 다른 사실이고, 뒤섞이면 잘림 집계의 분모가 흐려진다.
        # `end` 델타를 안 흘리는 클라이언트(`ScriptedClient` 기본)는 기록하지 않는다:
        # 없는 사유를 `UNKNOWN` 으로 지어내 분모를 부풀리지 않는다.
        if failed:
            record_llm_end(session_id, store.llm_calls(session_id), "stream_error")
        elif saw_end:
            record_llm_end(session_id, store.llm_calls(session_id), finish_raw)

        if failed:
            # 09_RUNTIME §3 — 부분 스트림을 이어 붙이지 않는다
            yield sse.token("응답 생성에 실패했습니다. 다시 시도해 주세요.")
            return

        async for ev in flush(force=True):
            yield ev

        if assistant_text:
            store.append(session_id, {"role": "assistant", "content": "".join(assistant_text)})

        if not pending:
            # 🔴 텍스트도 도구도 없이 끝났다면 그건 정상 종료가 아니라 **빈 응답**이다.
            #   추론 모델이 본문을 `reasoning` 에만 쏟고 `content` 를 비운 채
            #   `finish_reason=stop` 으로 끝내는 실패 모드가 실제로 있다
            #   (`elice_chunk_delta` 는 `delta.content` 만 읽는다). `TRUNCATION_REASONS`
            #   는 MAX_TOKENS/LENGTH 만 보므로 이 경우 경고조차 안 뜬다 —
            #   09_RUNTIME §3 "확인하지 못했다를 명시한다" 원칙대로 사실을 말한다.
            #   ⛔ 부분 스트림을 이어 붙이거나 재시도하지 않는다(스트림 실패와 같은 태도).
            if not assistant_text:
                logger.warning(
                    "빈 응답 — 세션 %s, LLM 호출 %d회차, 종료사유 %s. 텍스트·도구 호출이 "
                    "모두 없다(모델이 본문 대신 reasoning 에만 출력했을 수 있다).",
                    session_id,
                    store.llm_calls(session_id),
                    normalize_finish_reason(finish_raw) if saw_end else "NO_END_MARKER",
                )
                yield sse.token("응답을 받지 못했습니다. 다시 시도해 주세요.")
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
            # elapsed 는 **여기서 잰다** (소유권 한 곳). 도구 payload 에서 `_elapsed` 를
            # 꺼내 쓰던 이전 구현은 그 키를 넣는 생산자가 없어 **항상 0.0** 이었고,
            # trace 패널이 "0.0s · N calls" 라는 거짓을 표시했다. 계약(06_REPO_API)이
            # 필드로 명시한 값이 상시 거짓이면 감사 화면의 신뢰가 통째로 무너진다.
            t0 = time.perf_counter()
            outcome = await client.call(
                tu.name, tu.input, timeout=_TOOL_TIMEOUT_OVERRIDES.get(tu.name, TOOL_TIMEOUT_SEC)
            )
            elapsed = time.perf_counter() - t0
            payload = outcome if isinstance(outcome, dict) else {"status": "error"}
            status = str(payload.get("status", "error"))

            summary = summarize_result(tu.name, payload)
            if payload.get("reason") == "timeout":
                summary = f"✗ timeout · {tu.name} 확인 실패"  # D44·D46 표시 규약
            # D54 — 근거 페이지를 tool_result 에 싣는다. **항상** 넘긴다(근거 없는 도구는
            # 빈 리스트): 키가 있어야 평가가 strict 로 올라가 "블록은 있고 숫자는 지어낸"
            # citation 을 잡는다. 실패 결과의 페이지는 근거가 아니다 — ok 만 인정.
            pages = _pages_from(tu.name, payload) if status == "ok" else []
            # D66 — 특정된 부품 품번도 같은 방식으로 싣는다. 실패 결과는 부품을 특정한 게
            # 아니므로 ok 만 인정하는 것도 pages 와 같다.
            parts = _parts_from(tu.name, payload) if status == "ok" else []
            # D76-2 ⓑ — 도구 **원본** payload 는 `traces.tool_payload` 컬럼으로만 간다.
            # SSE tool_result 필드는 그대로다 (D76 ⓓ) — 프론트·score.py 무영향.
            # 컬럼만 있고 쓰는 쪽이 없어서 3차 평가가 "도구가 실제로 무엇을 반환했는지"를
            # 사후에 대조하지 못했다(`data/analysis/eval_gap_3rd.md`).
            # D113 — A2A 상관관계 키. 이 두 도구의 성공 응답에만 실린다(MQ-1602 가 성공
            # 분기에서 강제 주입). 빈 문자열은 "없음"과 같게 다룬다(MQ-1601 엣지케이스).
            a2a_chain_id = (
                payload.get("request_chain_id") if tu.name in _A2A_CHAIN_TOOLS else None
            )
            if isinstance(a2a_chain_id, str) and not a2a_chain_id:
                a2a_chain_id = None
            yield trace.tool_result(
                tu.name,
                status,
                summary,
                round(elapsed, 3),
                pages=pages,
                parts=parts,
                tool_payload=payload,
                a2a_chain_id=a2a_chain_id,
            )

            st.results[tu.name] = payload
            # D76 — 도구 결과는 `role:"tool"` 로 **구조를 보존해** 남긴다.
            # 프로즈로 뭉개면 LLM 이 값을 다시 파싱해야 하고, 화이트리스트가 빠뜨린 필드는
            # 아예 사라져 에이전트가 지어낸다. 제공자별 변환은 llm.py 어댑터가 맡는다.
            store.append(
                session_id,
                {
                    "role": "tool",
                    "name": tu.name,
                    "content": _history_payload(tu.name, payload),
                },
            )

            if tu.input.get("model") in prompts.MODELS:
                st.observed_model = st.observed_model or tu.input["model"]
            if tu.name == "get_error_history" and isinstance(tu.input.get("days"), int):
                st.repeat_window_days = tu.input["days"]

            if status == "ok":
                # 부품 조회가 성공한 턴 = 교체를 다루는 턴 (후보 C).
                if tu.name in ("search_inventory", "find_alternative_parts"):
                    st.replacement_ctx = True
                for p in pages:
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
