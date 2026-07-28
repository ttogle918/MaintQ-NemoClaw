# -*- coding: utf-8 -*-
"""MQ-311 — S4(미지 에러코드) 관통 스모크.

`run_turn` 을 **in-process 로** 돌린다 (HTTP 미경유 — SSE 프레이밍은 sp3 가 검증).
LLM 은 `ScriptedClient` 로 고정하고, MCP 는 **실제 stdio 서버**(`McpClient`)를 띄워
`lookup_error_code` 가 진짜로 DB 를 읽게 한다. 그래야 not_found / ok / error(D50) 가
픽스처 하드코딩이 아니라 **도구 로직에서** 나온다.

**이 스모크의 한계 (반드시 이해할 것).**
스크립트 응답을 쓰므로 이 테스트는 "LLM 이 미지 코드에 유사 코드를 추측하지 않았는가"를
보지 **않는다**. 그건 실제 환각률이고 LLM judge(다음 스프린트)가 볼 몫이다.
여기서 보는 건 오직 **"루프가 도구의 not_found 를 왜곡·보충 없이 사용자에게 흘리는가"**
— 도구 결과와 최종 응답·인용·발주 경로 사이의 배선이다. 스크립트가 도구를 부르지 않고
바로 답하면 이 스모크는 아무것도 검증하지 못하므로, ① 로 **도구 호출이 실제로 일어나
traces 에 남는지**를 먼저 못 박는다.

DB 격리 (D50 승인 게이트 대비):
  - 실 `data/maintq.db` 는 `error_codes` 0행이다 → 그 상태로는 lookup 이 `not_found` 가
    아니라 `error`(catalog_not_loaded) 다. 원본을 건드리지 않는다 — mtime 을 시작·끝에서
    비교한다.
  - 사본 두 개로 작업한다: **loaded**(정상 코드 iG5A/OHT 1건 INSERT) 와 **empty**(0행 유지).
    loaded 가 있어야 "정상은 ok / 미지는 not_found" 대비가 성립해 위양성이 사라지고,
    empty 가 D50(⑨)을 재현한다.
  - MCP stdio 자식에는 `env={"MAINTQ_DB": <사본>}` 을 명시 전달한다 (SDK 화이트리스트가
    MAINTQ_DB 를 안 넘기므로 — mcp_client_contract.py ⑨ 참조).

실행:  uv run python spikes/s4_smoke.py
"""

from __future__ import annotations

import asyncio
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SOURCE_DB = ROOT / "data" / "maintq.db"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


# ─────────────────────────────────────────────────────────────── 이벤트 헬퍼


def tool_calls(events, tool: str | None = None) -> list[dict]:
    out = [e.data for e in events if e.event == "tool_call"]
    return [d for d in out if tool is None or d.get("tool") == tool]


def tool_results(events) -> list[dict]:
    return [e.data for e in events if e.event == "tool_result"]


def citations(events) -> list[dict]:
    return [
        e.data["data"]
        for e in events
        if e.event == "block" and e.data.get("type") == "citation"
    ]


def token_text(events) -> str:
    return " ".join(str(e.data.get("text", "")) for e in events if e.event == "token")


# ─────────────────────────────────────────────────────────────── 드라이버


async def drive(client, db: Path, script, *, session: str, message: str = "에러코드 문의"):
    """run_turn 한 턴을 in-process 로 돌리고 SSE 이벤트 목록을 돌려준다."""
    from backend.agent.llm import ScriptedClient
    from backend.agent.loop import SessionStore, run_turn
    from backend.agent.trace import TraceWriter

    writer = TraceWriter(session, db_path=db)
    events = []
    async for ev in run_turn(
        session_id=session,
        message=message,
        equipment_id=None,  # 컨텍스트 미주입 — model 은 스크립트가 도구 입력으로 넘긴다.
        # 이렇게 두면 backend.db(실 DB) 를 여는 _model_for 경로 자체가 안 돌아 mtime 이 안전하다.
        user_id="tech-01",
        llm=ScriptedClient(script),
        client=client,  # 실제 McpClient (stdio)
        trace=writer,
        store=SessionStore(),
    ):
        events.append(ev)
    return events


def tu(name: str, **kw):
    from backend.agent.llm import ToolUse

    return ("tool_use", ToolUse(id="t1", name=name, input=kw))


# 미지 코드로 조회 → not_found 를 받은 뒤 "확인되지 않"으로 답하는 흐름을 그대로 재현한다.
# (스크립트가 도구를 안 부르고 바로 답하면 스모크가 공회전한다 — 주의 항목.)
SCRIPT_UNKNOWN = [
    [tu("lookup_error_code", model="iG5A", code="E999")],
    [
        (
            "text",
            "요청하신 코드 E999 는 iG5A 매뉴얼에서 확인되지 않는 코드입니다. "
            "정확한 코드를 다시 확인하시거나 제조사 A/S 센터에 문의해 주세요.",
        )
    ],
]

SCRIPT_KNOWN = [
    [tu("lookup_error_code", model="iG5A", code="OHt")],
    [("text", "iG5A 과열(OHt) 코드입니다.")],
]


# ─────────────────────────────────────────────────────────────── DB 사본


def make_loaded(td: Path) -> Path:
    """error_codes 에 정상 코드 1건(iG5A/OHT)을 넣은 사본."""
    db = td / "loaded.db"
    shutil.copy2(SOURCE_DB, db)
    con = sqlite3.connect(db)
    # OR REPLACE — iG5A 매핑 승인(2026-07-28) 후로는 복사한 실 DB 에 이미 (iG5A, OHT) 가
    # 있다. 아래 검사들이 이 고정 fixture 문구(causes·actions)를 그대로 기대하므로
    # 실 데이터와 무관하게 이 값이 이겨야 한다 — 순수 INSERT 면 UNIQUE 충돌로 죽는다.
    con.execute(
        "INSERT OR REPLACE INTO error_codes"
        " (model, code, display_code, error_name, severity,"
        "  causes, actions, related_parts, manual_page)"
        " VALUES ('iG5A','OHT','OHt','인버터 과열','warning',"
        "         '[\"냉각 불량\"]','[\"냉각팬 점검\"]','[\"FAN-IG5-01\"]',202)"
    )
    con.commit()
    con.close()
    return db


def make_empty(td: Path) -> Path:
    """error_codes 0행 사본 — D50 승인 게이트 상태 (⑨)."""
    db = td / "empty.db"
    shutil.copy2(SOURCE_DB, db)
    con = sqlite3.connect(db)
    # 실 DB 는 이제 65행(iG5A 매핑 승인, 2026-07-28)이지만, 이 테스트는 승인 전 D50
    # 게이트 상태를 재현해야 하므로 사본에서 명시적으로 비운다 — 실 DB 상태와 무관하게 결정적
    con.execute("DELETE FROM error_codes")
    con.commit()
    con.close()
    return db


# ─────────────────────────────────────────────────────────────── 검사


async def run_all(td: Path) -> None:
    from backend.agent.mcp_client import McpClient
    from backend.agent.trace import read_trace

    db_loaded = make_loaded(td)
    db_empty = make_empty(td)

    # ── loaded DB (error_codes 적재됨) — 정상 흐름 검사 ①~⑧ ────────────────
    client = McpClient(env={"MAINTQ_DB": str(db_loaded)})
    started = await client.start()
    if not started:
        check("MCP 서버 기동", False, client.start_error or "start() 실패")
        return

    try:
        ev = await drive(client, db_loaded, SCRIPT_UNKNOWN, session="S4")

        calls = tool_calls(ev, "lookup_error_code")
        res = tool_results(ev)
        lookup_res = [r for r in res if r.get("tool") == "lookup_error_code"]

        # ① 미지 코드에 lookup 이 실제로 호출됐다 (스모크가 공회전이 아님을 보증 — 주의)
        check(
            "① 미지 코드 lookup 이 실제 1회 호출",
            len(calls) == 1 and len(tool_calls(ev)) == 1,
            f"lookup {len(calls)}회 · 전체 tool_call {len(tool_calls(ev))}건",
        )

        # ② 도구가 not_found 를 돌려줬다 (loaded DB 라 catalog_not_loaded 가 아님)
        check(
            "② lookup 결과 status == not_found",
            bool(lookup_res) and lookup_res[0]["status"] == "not_found",
            f"status={lookup_res[0]['status'] if lookup_res else None}",
        )

        # ③ 응답이 not_found 를 왜곡 없이 전달한다
        txt = token_text(ev)
        check(
            "③ 최종 응답에 '확인되지 않' 포함",
            "확인되지 않" in txt,
            txt[:60],
        )

        # ④ S4 는 인용이 없는 게 정답 (근거 페이지가 없으므로)
        check(
            "④ citation 블록 0건",
            len(citations(ev)) == 0,
            f"citation {len(citations(ev))}건",
        )

        # ⑤ 미지 코드가 발주로 흐르지 않는다
        check(
            "⑤ create_po_draft 미호출",
            len(tool_calls(ev, "create_po_draft")) == 0,
            f"create_po_draft {len(tool_calls(ev, 'create_po_draft'))}회",
        )

        # ⑥ 도구 호출이 A5 대로 traces 에 영속화됐다
        tr = read_trace("S4", db_loaded)
        types = {e["event"] for e in tr["events"]}
        check(
            "⑥ traces 에 tool_call·tool_result 행 존재 (A5)",
            {"tool_call", "tool_result"} <= types and tr["count"] >= 2,
            f"count={tr['count']}, types={sorted(types)}",
        )

        # ⑦ not_found 뒤 재조회하지 않는다 — traces 의 lookup tool_call 이 정확히 1건
        lookup_call_rows = [
            e
            for e in tr["events"]
            if e["event"] == "tool_call" and e["data"].get("tool") == "lookup_error_code"
        ]
        check(
            "⑦ 재조회 없음 — traces 의 lookup tool_call 정확히 1건",
            len(lookup_call_rows) == 1,
            f"lookup tool_call {len(lookup_call_rows)}건",
        )

        # ⑧ 정상 코드는 ok — 위양성 방지 대비군
        ev_ok = await drive(client, db_loaded, SCRIPT_KNOWN, session="OK")
        ok_res = [r for r in tool_results(ev_ok) if r.get("tool") == "lookup_error_code"]
        check(
            "⑧ 정상 코드 OHt 조회는 status == ok",
            bool(ok_res) and ok_res[0]["status"] == "ok",
            f"status={ok_res[0]['status'] if ok_res else None}",
        )
    finally:
        await client.stop()

    # ── empty DB (error_codes 0행) — D50 재현 검사 ⑨ ──────────────────────
    client2 = McpClient(env={"MAINTQ_DB": str(db_empty)})
    started2 = await client2.start()
    if not started2:
        check("⑨ D50 (empty DB 기동)", False, client2.start_error or "start() 실패")
        return
    try:
        ev_d50 = await drive(client2, db_empty, SCRIPT_UNKNOWN, session="D50")
        d50_res = [
            r for r in tool_results(ev_d50) if r.get("tool") == "lookup_error_code"
        ]
        status = d50_res[0]["status"] if d50_res else None
        summary = d50_res[0]["summary"] if d50_res else ""
        # 만약 0행을 not_found 로 줬다면 S4 스모크가 위양성으로 통과한다.
        # D50 대로 error(catalog_not_loaded) 여야 하고, 스모크는 이걸 fail 로 걸러야 한다.
        s4_would_falsely_pass = status == "not_found"
        check(
            "⑨ D50 — 0행 DB 는 not_found 가 아니라 error(catalog_not_loaded)",
            status == "error" and "적재" in summary and not s4_would_falsely_pass,
            f"status={status}, summary={summary[:40]!r}",
        )
    finally:
        await client2.stop()


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("MQ-311 — S4 관통 스모크 (run_turn in-process · ScriptedClient · 실 MCP)\n")
    if not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 없음 — data/seed.py 를 먼저 실행하세요")

    # DB 안전 게이트: 실 DB 는 절대 안 바뀐다 (DoD).
    before = (SOURCE_DB.stat().st_mtime, SOURCE_DB.stat().st_size)
    print(f"data/maintq.db mtime(before) = {before[0]:.6f}, size={before[1]}\n")

    with tempfile.TemporaryDirectory() as td:
        asyncio.run(run_all(Path(td)))

    after = (SOURCE_DB.stat().st_mtime, SOURCE_DB.stat().st_size)
    print(f"\ndata/maintq.db mtime(after)  = {after[0]:.6f}, size={after[1]}")
    check(
        "DB 안전 · data/maintq.db mtime·size 불변",
        after == before,
        f"변경={after != before}",
    )

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 46))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 46))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    core = len(results) - 1  # DB 안전 게이트 1건 제외
    print(f"\n통과 (S4判定 {core}건 + DB 안전 게이트 1건) — 루프가 not_found 를 왜곡 없이 흘림")


if __name__ == "__main__":
    main()
