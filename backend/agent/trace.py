# -*- coding: utf-8 -*-
"""trace 영속화 (D21 · D41) — SSE 발행과 `traces` INSERT 를 **한 몸**으로 묶는다.

A5(09_RUNTIME §1): "모든 tool_call/tool_result/block 은 SSE 발행과 동시에 traces 에 저장".
그래서 이 모듈은 **저장 없이 발행하는 경로를 만들지 않는다** — 이벤트를 만드는 메서드가
곧 INSERT 지점이다. 에이전트 루프가 `backend.sse.*` 를 직접 부르면 그 이벤트는 저장되지
않으므로, 루프는 반드시 `TraceWriter` 를 거쳐야 한다 (이미 만들어진 이벤트는 `emit()`).

**token 메서드를 두지 않는 이유 (D41) — 버그가 아니라 설계다.**
`traces.event_type` 의 CHECK 는 `'tool_call' | 'tool_result' | 'block'` 3종만 허용한다
(docs/05_DB_SCHEMA §9). token 을 INSERT 하면 즉시 `IntegrityError` 로 튕긴다.
D41 원문: "**token 은 SSE 로만 발행하고 traces 에 저장하지 않음**(기존 CHECK 3종이 설계
의도대로였음) — 대화 전문을 DB 에 쌓는 일이고 D18(팀장은 대화를 안 읽는다)과도 어긋난다."
즉 A5 의 "모든 이벤트"는 3종을 뜻한다. token 은 `backend.sse.token()` 으로 직접 발행하고
여기 넣지 않는다. 저장 대상을 늘리려면 스키마 CHECK 부터 바꿔야 하고 그건 결정 변경이다.

**payload 는 SSE `data` 와 바이트 동일하다 (D30).** 평가가 SSE 스트림과 traces 두 소스를
대조해 "블록은 있고 페이지 숫자는 지어낸" 경우를 잡아내기 때문에, 직렬화가 갈리면 판정이
무너진다. `event_payload()` 가 `SseEvent.encode()` 와 같은 직렬화를 쓴다 —
`spikes/trace_persist.py` ② 가 실제 인코딩 프레임과 대조해 이 불변식을 지킨다.

**저장 실패가 사용자 스트림을 끊지 않는다.** INSERT 예외는 삼키고 `persist_errors` 를 올린다
(단 로그는 남긴다). 다만 `UNIQUE(session_id, seq)` 위반은 **조용히 넘기지 않고** seq 를
다시 읽어 1회 재시도한다 — 순번이 밀리면 순서 판정(scenario-smoke)·타임라인이 깨진다.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from backend import sse
from backend.db import connect
from backend.services.po import iso_utc

log = logging.getLogger(__name__)

#: `traces` CHECK 가 허용하는 event_type. token 이 없는 건 의도다 (D41).
PERSISTED_EVENTS: tuple[str, ...] = ("tool_call", "tool_result", "block")


def utc_now_z() -> str:
    """이벤트 표면에 실리는 시각 — 타임존을 명시한 ISO-8601 (D39)."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _db_ts() -> str:
    """DB 저장용 시각. SQLite `CURRENT_TIMESTAMP` 와 같은 **naive UTC** 표기 (D39).

    한 컬럼에 두 표기가 섞이지 않게 저장은 기존 컬럼들과 같은 모양으로 하고,
    'Z' 를 붙이는 경계는 전송 시점(`iso_utc`) 한 곳으로 유지한다.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def event_payload(event: sse.SseEvent) -> str:
    """SSE `data` 라인과 바이트 동일한 JSON (D30).

    `SseEvent.encode()` 의 직렬화와 인자가 같아야 한다 — 여기서 갈리면 평가의 두 소스
    대조가 무너진다. `sse.py` 는 MQ-312 소유라 이 함수가 따라가는 쪽이다.
    """
    return json.dumps(event.data, ensure_ascii=False)


class TraceWriter:
    """세션 하나의 trace 기록기. 이벤트 생성 + `traces` INSERT 를 한 번에 한다 (A5).

    사용:
        trace = TraceWriter(session_id)
        yield trace.tool_call("lookup_error_code", {"model": "iG5A", "code": "OHt"}).encode()
        ...
        yield trace.tool_result("lookup_error_code", "ok", "과열 · FAN-IG5-01", 0.4).encode()

    `token` 메서드는 없다 — 모듈 docstring 참조 (D41).
    """

    def __init__(self, session_id: str, db_path: Path | None = None) -> None:
        self.session_id = session_id
        self.db_path = db_path
        #: 저장에 실패한 이벤트 수. 스트림은 계속 흐르되 실패를 숨기지는 않는다
        self.persist_errors = 0
        #: 마지막으로 성공한 seq. None 이면 아직 DB 에서 MAX(seq) 를 안 읽었다는 뜻
        self._seq: int | None = None

    # ────────────────────────────────────────────── 이벤트 (생성 + 저장)

    def tool_call(self, tool: str, tool_input: dict, ts: str | None = None) -> sse.SseEvent:
        """도구 호출 **직전** 발행 (A1) — trace 패널이 '실행 중'을 먼저 보여줘야 한다."""
        return self._write(sse.tool_call(tool, tool_input, ts or utc_now_z()), tool)

    def tool_result(self, tool: str, status: str, summary: str, elapsed: float) -> sse.SseEvent:
        """도구 완료. `status` 는 D9 4종, 세분화는 도구가 `reason` 으로 (D46)."""
        return self._write(sse.tool_result(tool, status, summary, elapsed), tool)

    def block(self, block_type: str, data: dict) -> sse.SseEvent:
        """구조화 블록 — safety / po_card / citation (D22). `tool` 컬럼은 NULL."""
        return self._write(sse.block(block_type, data), None)

    def citation(
        self, manual: str, page: int, print_page: int, section: str | None = None
    ) -> sse.SseEvent:
        """인용 블록. `page` 는 물리 페이지 그대로, 오프셋 변환은 `sse` 쪽 1곳 (D26·D32)."""
        return self._write(sse.citation_block(manual, page, print_page, section), None)

    def emit(self, event: sse.SseEvent, tool: str | None = None) -> sse.SseEvent:
        """이미 만들어진 SSE 이벤트를 **저장하며** 발행한다.

        MQ-312 의 `sse.citation_for()` 처럼 이 클래스가 모르는 헬퍼가 만든 이벤트를
        A5 밖으로 새지 않게 받는 입구다. `token` 은 저장 대상이 아니므로 거부한다 (D41) —
        여기서 조용히 통과시키면 CHECK 위반이 런타임에 터지거나, 더 나쁘게는
        "저장 없이 발행"이 정상 경로처럼 굳는다.
        """
        if event.event not in PERSISTED_EVENTS:
            raise ValueError(
                f"traces 저장 대상이 아닙니다: {event.event!r} "
                f"(허용 {PERSISTED_EVENTS}). token 은 sse.token() 으로 직접 발행하세요 — D41"
            )
        return self._write(event, tool)

    # ────────────────────────────────────────────── 내부

    def _write(self, event: sse.SseEvent, tool: str | None) -> sse.SseEvent:
        self._persist(event.event, tool, event_payload(event))
        return event

    def _next_seq(self) -> int:
        """`MAX(seq)+1` 로 시작해 이어쓴다 — 같은 세션에 두 번째 턴이 붙어도 순번이 겹치지 않게."""
        if self._seq is None:
            with connect(self.db_path) as con:
                row = con.execute(
                    "SELECT MAX(seq) FROM traces WHERE session_id = ?", (self.session_id,)
                ).fetchone()
            self._seq = int(row[0] or 0)
        return self._seq + 1

    def _persist(self, event_type: str, tool: str | None, payload: str) -> None:
        for attempt in (1, 2):
            seq: int | None = None
            try:
                seq = self._next_seq()
                with connect(self.db_path) as con:
                    con.execute(
                        "INSERT INTO traces (session_id, seq, event_type, tool, payload, ts)"
                        " VALUES (?,?,?,?,?,?)",
                        (self.session_id, seq, event_type, tool, payload, _db_ts()),
                    )
                self._seq = seq
                return
            except sqlite3.IntegrityError as exc:
                # UNIQUE(session_id, seq) 충돌 — 삼키지 않는다 (D41).
                # 캐시한 seq 를 버리고 DB 에서 다시 읽어 1회만 재시도한다.
                self._seq = None
                log.error(
                    "traces seq 충돌 (session=%s seq=%s event=%s 시도=%d): %s",
                    self.session_id,
                    seq,
                    event_type,
                    attempt,
                    exc,
                )
            except sqlite3.Error as exc:
                # DB 잠금·파일 접근 실패 등. trace 저장 실패로 사용자 스트림이 끊기면 안 된다
                self.persist_errors += 1
                log.warning(
                    "traces INSERT 실패 (session=%s event=%s): %s", self.session_id, event_type, exc
                )
                return

        self.persist_errors += 1
        log.error(
            "traces INSERT 재시도 후에도 실패 (session=%s event=%s) — seq 순번을 확인하세요",
            self.session_id,
            event_type,
        )


def read_trace(session_id: str, db_path: Path | None = None) -> dict:
    """세션의 trace 전체 (D43 스키마) — `{session_id, count, events:[{seq,event,tool,data,ts}]}`.

    **없는 세션도 예외가 아니다** — `count: 0` 으로 돌려준다. 404 로 하면
    `services/po.trace_url` 이 항상 유효하다는 전제가 깨져 프론트 분기가 늘어난다 (D43).
    `data` 는 저장된 payload 를 그대로 되돌린 것이라 SSE 로 나갔던 `data` 와 동일하다 (D30).
    """
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT seq, event_type, tool, payload, ts FROM traces"
            " WHERE session_id = ? ORDER BY seq",
            (session_id,),
        ).fetchall()

    events = [
        {
            "seq": r["seq"],
            "event": r["event_type"],
            "tool": r["tool"],
            "data": json.loads(r["payload"]),
            "ts": iso_utc(r["ts"]),  # 전송은 타임존 명시 UTC (D39)
        }
        for r in rows
    ]
    return {"session_id": session_id, "count": len(events), "events": events}
