# -*- coding: utf-8 -*-
"""MCP 클라이언트 — lifespan 이 소유하는 단일 워커 태스크 (D42).

## 왜 워커 태스크인가

MCP stdio 세션을 **async generator 안에서 열면 깨진다.** 실측 결과, 소비자가 스트림을
조기 종료하면 `RuntimeError: Attempted to exit cancel scope in a different task` 가 나고
실패한 cancel scope 가 **무관한 후속 태스크까지 취소**한다. `StreamingResponse` +
클라이언트 조기 종료가 정확히 그 패턴이다.

그래서 세션의 **enter / call / exit 가 전부 한 태스크(`_worker`) 안**에 있다.
스트리밍 제너레이터는 세션을 열지 않고 큐에 요청만 넣는다:

    fut = loop.create_future()
    queue.put_nowait((tool, args, fut, timeout))
    await asyncio.wait_for(asyncio.shield(fut), timeout)

`shield` 가 필수인 이유: 제너레이터가 취소돼도 **워커에서 진행 중인 호출은 끊기면 안 된다.**
fut 이 취소되면 워커가 결과를 넣을 자리가 사라지고, 최악의 경우 쓰기 도구
(`create_po_draft`)가 절반만 진행된 상태로 남는다.

성능도 같은 결론이다 — 세션 spawn 0.9~1.2s vs 도구 호출 0.01s. 턴당 8콜이면 +8초.

## env 명시 상속

`StdioServerParameters(env=None)` 이면 SDK 가 `get_default_environment()` 화이트리스트만
자식에게 넘긴다. 그 목록에 `MAINTQ_DB` 는 **없다.** 명시하지 않으면 임시 DB 를 지정한
테스트가 조용히 `data/maintq.db` 에 draft 를 쓴다 — 통과하면서 실데이터를 오염시키는
종류의 실패다. 그래서 `env={**os.environ}` 를 항상 명시한다.

## D15 — 프로세스 분리

이 모듈은 `mcp_server` 를 **import 하지 않는다.** 서버는 파일 경로로만 알고 stdio 로만
말한다. 코드 공유가 시작되면 "MCP 서버만 교체" 구조가 무너진다.

## 실패는 예외가 아니라 status (D9 · D46)

`call()` 은 예외를 던지지 않는다. 타임아웃·연결 실패·프로토콜 오류를 전부
`{"status": "error", "reason": ...}` 로 되돌린다. status 4종은 유지하고 세분화는
`reason` 이 담당한다 (D46 — 타임아웃은 `status:"error"` + `reason:"timeout"`).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError

logger = logging.getLogger(__name__)

# 09_RUNTIME §2 — 개별 도구 타임아웃. 루프 상한(8/10/50)은 agent/loop.py 소유.
TOOL_TIMEOUT_SEC = 10.0
# 세션 spawn 실측 0.9~1.2s. 콜드 스타트·CI 를 감안해 넉넉히 잡되 무한 대기는 하지 않는다.
STARTUP_TIMEOUT_SEC = 30.0
SHUTDOWN_TIMEOUT_SEC = 5.0

_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SERVER_SCRIPT = _ROOT / "mcp_server" / "server.py"

_SENTINEL = object()


# ─────────────────────────────────────────────────────────────────────────────
# 결과 정규화
# ─────────────────────────────────────────────────────────────────────────────


def _error(reason: str, message: str) -> dict:
    """D9 — 도구 실패는 예외가 아니라 status 필드로 돌아온다."""
    return {"status": "error", "reason": reason, "message": message}


def _payload(result: Any) -> dict:
    """`CallToolResult` → 도구가 반환한 dict.

    FastMCP 는 dict 반환을 `structuredContent` 에 그대로 싣는다. 구형 서버·에러 응답을
    대비해 content 텍스트 JSON 폴백을 둔다.
    """
    if getattr(result, "isError", False):
        text = _first_text(result) or "도구가 오류를 반환했습니다"
        return _error("tool_error", text)

    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    text = _first_text(result)
    if text:
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if isinstance(data, dict):
            return data

    return _error("malformed_result", "도구 응답을 dict 로 해석하지 못했습니다")


def _first_text(result: Any) -> str | None:
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            return str(text)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 한 줄 요약 — SSE tool_result 의 summary (D14·D22)
# ─────────────────────────────────────────────────────────────────────────────


def _won(v: Any) -> str:
    return f"₩{int(v):,}" if isinstance(v, (int, float)) else "-"


def summarize_result(tool: str, result: dict) -> str:
    """도구 결과를 trace 패널 한 줄로 요약한다.

    화면에 그대로 뜨는 문자열이라 **결과에 있는 값만** 쓴다 — 여기서 문장을 지어내면
    도구가 주지 않은 정보가 사용자에게 사실처럼 보인다 (환각률 0% 지표는 UI 문구에도 적용).
    `✗ timeout ·` 접두는 **백엔드가 소유한다** — `loop.py` 가 이 함수의 반환값 앞에
    붙인다 (D44·D46). 프론트가 붙이는 게 아니다: `traces` 는 평가 판정 소스이고(D21·D30)
    `GET /trace` 소비자가 화면만이 아니므로, 저장된 summary 자체가 자기설명적이어야 한다.
    이 함수는 접두 없는 본문만 만든다 — `loop.py` 와 중복해 붙이지 않기 위해서다.
    """
    if not isinstance(result, dict):
        return "알 수 없는 응답"

    status = result.get("status")

    if status == "error":
        reason = result.get("reason") or "unknown"
        if reason == "timeout":
            return f"응답 시간 초과 ({TOOL_TIMEOUT_SEC:g}초)"
        message = (result.get("message") or "").strip()
        return message.splitlines()[0][:120] if message else f"오류 ({reason})"

    if status == "not_found":
        if tool == "lookup_error_code":
            return "매뉴얼에서 확인되지 않는 코드 (추측 금지 — S4)"
        return "조회 결과 없음"

    if status == "empty":
        return "결과 0건"

    if tool == "lookup_error_code":
        parts = [f"{result.get('code', '?')} {result.get('error_name', '')}".strip()]
        if result.get("severity"):
            parts.append(f"({result['severity']})")
        related = result.get("related_parts") or []
        if related:
            parts.append(f"· 관련부품 {len(related)}건")
        if result.get("manual_page"):
            parts.append(f"· p.{result['manual_page']}")
        return " ".join(parts)

    if tool == "rag_search_manual":
        chunks = result.get("chunks") or []
        pages = ", ".join(f"p.{c.get('page')}" for c in chunks[:3] if c.get("page"))
        return f"{len(chunks)}개 청크" + (f" ({pages})" if pages else "")

    if tool == "get_error_history":
        count = result.get("count", len(result.get("events") or []))
        return f"{count}건" + (" · 반복 감지" if result.get("repeated") else "")

    if tool == "search_inventory":
        items = result.get("items") or []
        if not items:
            return "0건"
        head = items[0]
        note = " · 단종" if head.get("discontinued") else ""
        qty, safety = head.get("qty"), head.get("safety_stock")
        if isinstance(qty, int) and isinstance(safety, int) and qty < safety:
            note += " · 안전재고 미달"
        more = f" 외 {len(items) - 1}건" if len(items) > 1 else ""
        return f"{head.get('part_no', '?')} 재고 {qty}/안전 {safety}{note}{more}"

    if tool == "find_alternative_parts":
        alts = result.get("alternatives") or []
        confirmed = sum(1 for a in alts if a.get("compat_confirmed"))
        return f"대체품 {len(alts)}건 (호환 확인 {confirmed}건)"

    if tool == "get_supplier_quotes":
        sups = result.get("suppliers") or []
        if not sups:
            return "견적 0건"
        fastest = min(
            (s.get("lead_days") for s in sups if s.get("lead_days") is not None), default=None
        )
        cheapest = min(
            (s.get("unit_price") for s in sups if s.get("unit_price") is not None), default=None
        )
        bits = [f"공급사 {len(sups)}곳"]
        if fastest is not None:
            bits.append(f"최단 {fastest}일")
        if cheapest is not None:
            bits.append(f"최저 {_won(cheapest)}")
        return " · ".join(bits)

    if tool == "create_po_draft":
        return f"{result.get('po_id', '?')} {result.get('state', 'draft')} · {_won(result.get('total'))}"

    # ── 확장 9종 (D69 `full` 프로파일에서만 호출된다) — `generate_disposal_document`·
    #    `create_repair_record` 처럼 아래 분기가 없는 도구는 `status or "ok"` 로 떨어진다
    #    (기존 §15 와 같은 처지 — 새 회귀는 아니다) ───────────────────────────
    # ⚠ D76 이후 이 문자열은 화면·traces 뿐 아니라 **LLM 입력**에도 실린다
    #   (`loop.py` 가 `_summary` 로 trimmed dict 안에 넣는다). 그래서 더더욱
    #   **결과에 있는 값만** 쓴다 — 여기서 판정을 요약하다 어휘를 바꾸면
    #   ("HOLD" → "문제 없음") 규칙 12 가 막으려는 오독을 코드가 먼저 저지른다.

    if tool == "check_disposal_blockers":
        verdict = result.get("verdict") or "?"
        blockers = result.get("blockers") or []
        bits = [str(verdict)]
        if blockers:
            ids = ", ".join(str(b.get("rule_id")) for b in blockers if b.get("rule_id"))
            bits.append(f"차단 {len(blockers)}건" + (f" ({ids})" if ids else ""))
        for key, label in (("holds", "경계"), ("insufficient", "사실부족")):
            items = result.get(key) or []
            if items:
                bits.append(f"{label} {len(items)}건")
        preconds = result.get("preconditions") or []
        if preconds:
            bits.append(f"선결 {len(preconds)}건")
        return " · ".join(bits)

    if tool == "verify_ownership":
        verdict = result.get("verdict") or "?"
        v, u = len(result.get("verified") or []), len(result.get("unverified") or [])
        return f"{verdict} · 확인 {v} / 미확인 {u}"

    if tool == "classify_part_criticality":
        return str(result.get("part_class") or "?")

    if tool == "get_maintenance_metrics":
        bits = []
        mtbf = result.get("mtbf_days")
        if mtbf is not None:
            # 단위를 반드시 붙인다 — D70 은 이 값이 **달력 기준**임을 계약으로 못 박았고,
            # 요약에서 기준이 사라지면 가동시간 MTBF 로 읽힌다.
            bits.append(f"MTBF {mtbf}일(달력)")
        planned = result.get("planned_ratio")
        if planned is not None:
            bits.append(f"예방보전 {round(planned * 100)}%")
        if result.get("repeat_failure"):
            bits.append("반복 고장")
        if not bits:
            bits.append(f"수리 이력 {result.get('n_repairs_signed', 0)}건")
        return " · ".join(bits)

    if tool == "classify_expenditure":
        verdict = result.get("verdict") or "?"
        if result.get("requires_expert_review"):
            return f"{verdict} · 전문가 확인 필요"
        return f"{verdict} · {result.get('basis') or '-'}"

    if tool == "assess_repair_value":
        verdict = result.get("verdict") or "?"
        ratio = result.get("recovery_ratio")
        # `recovery_ratio` 는 금액이 아니라 **수리비 대비 배수**다 (도구 자신도
        # "수리비의 N배"라고 쓴다). D76 이후 이 문자열은 trace·화면뿐 아니라
        # `_summary` 로 **LLM 입력에도** 실리므로, "회수비 1.06" 처럼 금액으로 읽힐
        # 여지가 있는 표기를 쓰지 않는다 — 단위를 잃은 숫자가 환각의 씨앗이다.
        # 추정치임도 요약에서 밝힌다 (D65·규칙 13). 값이 없으면 지어내지 않는다.
        return f"{verdict} · 회수비율 {ratio}배 (추정)" if ratio is not None else str(verdict)

    if tool == "build_evidence_bundle":
        digest = str(result.get("bundle_hash") or "")
        short = digest[:18] + "…" if len(digest) > 18 else digest or "-"
        bundle = result.get("evidence_bundle") or {}
        return (
            f"번들 해시 {short} · 조문 {len(bundle.get('laws') or [])}건 "
            f"· 룰 {len(bundle.get('rules') or [])}건"
        )

    return str(status or "ok")


# ─────────────────────────────────────────────────────────────────────────────
# 클라이언트
# ─────────────────────────────────────────────────────────────────────────────


class McpClient:
    """MCP stdio 세션 1개를 워커 태스크로 소유한다 (D42).

    수명은 `backend/main.py` 의 lifespan 이 관리하고, 라우터는 `request.app.state.mcp`
    로 접근한다. 워커가 큐를 **직렬 소비**하므로 tool_call ↔ tool_result 페어링이
    FIFO 로 성립한다 (화면 B trace 매퍼의 전제 — MQ-309).
    """

    def __init__(
        self,
        *,
        server_script: str | Path | None = None,
        python: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float = TOOL_TIMEOUT_SEC,
    ) -> None:
        self._server_script = Path(
            server_script or os.environ.get("MAINTQ_MCP_SERVER") or DEFAULT_SERVER_SCRIPT
        )
        self._python = python or os.environ.get("MAINTQ_MCP_PYTHON") or sys.executable
        self._env_overrides = dict(env or {})
        self._timeout = timeout

        self._queue: asyncio.Queue[Any] | None = None
        self._task: asyncio.Task | None = None
        self._started: asyncio.Event | None = None
        self._ready = False
        self._tools: list[dict] = []
        self.start_error: str | None = None

    # ── 상태 ────────────────────────────────────────────────────────────────

    @property
    def ready(self) -> bool:
        """세션이 살아 있고 도구 호출을 받을 수 있는가."""
        return self._ready

    # ── 수명 ────────────────────────────────────────────────────────────────

    async def start(self) -> bool:
        """워커를 띄우고 세션 초기화까지 기다린다.

        **실패해도 예외를 던지지 않는다** — MCP 서버가 없다고 백엔드가 못 뜨면
        승인 큐(사람 API)까지 같이 죽는다. 09_RUNTIME §3 대로 `ready=False` 로 두고,
        `call()` 이 `status:"error"` 를 돌려주면 에이전트가 "연결할 수 없다"고 말한다.
        """
        if self._task is not None:
            return self._ready

        self._queue = asyncio.Queue()
        self._started = asyncio.Event()
        self.start_error = None
        self._task = asyncio.create_task(self._worker(), name="mcp-worker")

        try:
            # py3.11+ 에서 asyncio.TimeoutError 는 내장 TimeoutError 의 별칭이다.
            await asyncio.wait_for(self._started.wait(), STARTUP_TIMEOUT_SEC)
        except TimeoutError:
            self.start_error = f"MCP 서버 기동 시간 초과 ({STARTUP_TIMEOUT_SEC:g}초)"
            logger.error("MCP 클라이언트 기동 실패 — %s", self.start_error)
            await self.stop()
            return False

        if not self._ready:
            logger.error("MCP 클라이언트 기동 실패 — %s", self.start_error)
        return self._ready

    async def stop(self) -> None:
        """워커를 종료한다. 세션 exit 은 워커 태스크 안에서 일어난다."""
        task, self._task = self._task, None
        if task is None:
            return

        self._ready = False
        if self._queue is not None:
            self._queue.put_nowait(_SENTINEL)

        try:
            await asyncio.wait_for(asyncio.shield(task), SHUTDOWN_TIMEOUT_SEC)
        except TimeoutError:
            # 자식 프로세스가 안 죽으면 태스크째 취소한다. 세션 cancel scope 가
            # 워커 태스크 소유이므로 여기서 취소해도 다른 태스크로 새지 않는다.
            task.cancel()
            with contextlib.suppress(BaseException):
                await task
        except asyncio.CancelledError:
            task.cancel()
            raise

        self._queue = None
        self._tools = []

    # ── 호출 ────────────────────────────────────────────────────────────────

    async def list_tools(self) -> list[dict]:
        """등록된 도구 목록 `[{name, description, input_schema}]` (세션 초기화 시 캐시)."""
        return list(self._tools)

    async def call(
        self, tool: str, args: dict | None = None, *, timeout: float | None = None
    ) -> dict:
        """도구를 호출하고 결과 dict 를 돌려준다. **예외를 던지지 않는다** (D9).

        호출자가 취소되어도 워커의 진행 중 호출은 `shield` 로 보호된다 (D42).
        """
        limit = self._timeout if timeout is None else timeout

        if not self._ready or self._queue is None:
            return _error(
                "unavailable",
                self.start_error or "MCP 서버에 연결되어 있지 않습니다",
            )

        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        # 호출자가 취소돼 아무도 결과를 안 읽어도 "Future exception was never retrieved"
        # 경고가 나지 않도록, 워커는 예외 대신 항상 dict 를 set_result 한다.
        self._queue.put_nowait((tool, dict(args or {}), fut, limit))

        try:
            return await asyncio.wait_for(asyncio.shield(fut), limit)
        except TimeoutError:
            # D46 — status 4종은 유지하고 세분화는 reason 이 담당한다.
            logger.warning("MCP 도구 타임아웃: %s (%.1fs)", tool, limit)
            return _error("timeout", f"{tool} 응답이 {limit:g}초 안에 오지 않았습니다")

    # ── 워커 (세션 enter/call/exit 이 전부 이 태스크 안) ──────────────────────

    def _child_env(self) -> dict[str, str]:
        """D42 — `env=None` 이면 SDK 화이트리스트만 상속돼 `MAINTQ_DB` 가 안 넘어간다."""
        env = {k: v for k, v in os.environ.items() if v is not None}
        env.update(self._env_overrides)
        return env

    async def _worker(self) -> None:
        assert self._started is not None
        try:
            params = StdioServerParameters(
                command=self._python,
                args=[str(self._server_script)],
                env=self._child_env(),
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    self._tools = [
                        {
                            "name": t.name,
                            "description": t.description or "",
                            "input_schema": t.inputSchema or {},
                        }
                        for t in listed.tools
                    ]
                    self._ready = True
                    self._started.set()
                    logger.info("MCP 세션 준비 — 도구 %d종", len(self._tools))
                    await self._serve(session)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self.start_error = f"{type(exc).__name__}: {exc}"
            logger.error("MCP 워커 종료 — %s", self.start_error)
        finally:
            self._ready = False
            self._started.set()
            self._drain()

    async def _serve(self, session: ClientSession) -> None:
        assert self._queue is not None
        while True:
            item = await self._queue.get()
            if item is _SENTINEL:
                return
            await self._dispatch(session, item)

    async def _dispatch(self, session: ClientSession, item: tuple) -> None:
        tool, args, fut, limit = item
        try:
            # SDK 의 요청 단위 타임아웃. 워커 자신의 태스크 안에서 anyio cancel scope 로
            # 처리되므로(=같은 컨텍스트) 세션이 살아남는다. 이게 없으면 도구 하나가
            # 멈출 때 워커가 영구히 막혀 이후 모든 호출이 타임아웃된다.
            raw = await session.call_tool(tool, args, read_timeout_seconds=timedelta(seconds=limit))
            result = _payload(raw)
        except McpError as exc:
            code = getattr(getattr(exc, "error", None), "code", None)
            if code == 408:
                result = _error("timeout", f"{tool} 응답이 {limit:g}초 안에 오지 않았습니다")
            else:
                result = _error("tool_error", str(exc))
        except asyncio.CancelledError:
            if not fut.done():
                fut.set_result(_error("unavailable", "MCP 세션이 종료되었습니다"))
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("MCP 호출 실패: %s — %s", tool, exc)
            result = _error("tool_error", f"{type(exc).__name__}: {exc}")

        if not fut.done():
            fut.set_result(result)

    def _drain(self) -> None:
        """세션이 죽었을 때 대기 중인 호출을 status:error 로 회수한다."""
        if self._queue is None:
            return
        while True:
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            if item is _SENTINEL:
                continue
            fut = item[2]
            if not fut.done():
                fut.set_result(
                    _error("unavailable", self.start_error or "MCP 세션이 종료되었습니다")
                )
