# -*- coding: utf-8 -*-
"""MCP 클라이언트(lifespan 워커) 계약 검증 — MQ-302 / D42·D46·D9·D15.

이 스파이크가 존재하는 이유는 두 가지 **실측 결함**이다:

  1. async generator 안에서 stdio 세션을 열면 소비자 취소 시
     `RuntimeError: Attempted to exit cancel scope in a different task` 가 나고
     무관한 후속 태스크까지 취소된다 → ⑧ 취소 안전성
  2. `StdioServerParameters(env=None)` 이면 SDK 화이트리스트만 상속돼 `MAINTQ_DB` 가
     자식에 전달되지 않는다 → 테스트가 **실 DB 에 draft 를 쓴다** → ⑨ env 격리

⑨ 는 `data/maintq.db` 의 mtime + po_drafts row count 를 전후 비교해 "조용히 통과하면서
실데이터를 오염시키는" 실패를 잡는다.

도구 목록은 **부분집합 비교**다 — MQ-304·314 가 도구를 더 붙이므로 완전 일치로 두면
남의 태스크가 이 스파이크를 깨뜨린다.

실행:  uv run python spikes/mcp_client_contract.py
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.agent.mcp_client import McpClient, summarize_result  # noqa: E402

SOURCE_DB = ROOT / "data" / "maintq.db"

# MQ-304(lookup_error_code)·MQ-314(rag_search_manual)가 도구를 추가한다.
# 완전 일치로 하면 이 스파이크가 남의 스테이지에 의존하게 된다.
EXPECTED_TOOLS = {
    "search_inventory",
    "find_alternative_parts",
    "get_supplier_quotes",
    "get_error_history",
    "create_po_draft",
}

results: list[tuple[str, bool, str]] = []
loop_errors: list[str] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def po_count(db: Path) -> int:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute("SELECT COUNT(*) FROM po_drafts").fetchone()[0]
    finally:
        con.close()


# ─────────────────────────────────────────────────────────────────────────────


async def run_session(db: Path) -> None:
    """세션 1개를 lifespan 처럼 열고 계약을 훑는다."""
    asyncio.get_running_loop().set_exception_handler(
        lambda _loop, ctx: loop_errors.append(str(ctx.get("message") or ctx.get("exception")))
    )

    client = McpClient()
    ok = await client.start()
    check("① start() → 세션 준비 (lifespan 소유)", ok and client.ready, f"ready={client.ready}")
    if not ok:
        return

    try:
        tools = await client.list_tools()
        names = {t["name"] for t in tools}
        check(
            "② 도구 목록 (부분집합 비교)",
            EXPECTED_TOOLS <= names,
            f"{len(names)}종 · 누락 {sorted(EXPECTED_TOOLS - names) or '없음'}",
        )

        # ── D9: 정상 호출
        inv = await client.call("search_inventory", {"part_no": "FAN-IG5-01"})
        item = (inv.get("items") or [{}])[0]
        check(
            "③ call() 정상 왕복",
            inv.get("status") == "ok" and item.get("part_no") == "FAN-IG5-01",
            f"status={inv.get('status')}, qty={item.get('qty')}",
        )

        # ── D9: 실패는 예외가 아니라 status
        bad = await client.call("search_inventory", {})
        check(
            "④ D9 인자 누락 → 예외 아닌 status:error",
            bad.get("status") == "error",
            f"status={bad.get('status')}, msg={(bad.get('message') or '')[:32]}",
        )

        # ── D46: 타임아웃은 status:error + reason:timeout (status 5종으로 늘리지 않음)
        to = await client.call("search_inventory", {"part_no": "FAN-IG5-01"}, timeout=0.001)
        check(
            "⑤ D46 타임아웃 → status:error + reason:timeout",
            to.get("status") == "error" and to.get("reason") == "timeout",
            f"status={to.get('status')}, reason={to.get('reason')}",
        )

        # ── 타임아웃이 세션을 죽이면 그 턴 이후가 통째로 무너진다
        after = await client.call("get_supplier_quotes", {"part_no": "FAN-IG5-01", "qty": 2})
        check(
            "⑥ 타임아웃 후에도 세션 생존",
            after.get("status") == "ok" and len(after.get("suppliers") or []) >= 2,
            f"status={after.get('status')}, 공급사 {len(after.get('suppliers') or [])}곳",
        )

        # ── 워커 큐 직렬 소비 (MQ-309 FIFO 페어링의 전제)
        batch = await asyncio.gather(
            *[client.call("search_inventory", {"part_no": "FAN-IG5-01"}) for _ in range(5)]
        )
        check(
            "⑦ 동시 호출 5건 직렬 소비",
            all(r.get("status") == "ok" for r in batch),
            f"ok {sum(r.get('status') == 'ok' for r in batch)}/5",
        )

        # ── ⑧ 취소 안전성 (이 태스크의 존재 이유)
        cancelled_task = asyncio.create_task(
            client.call("get_error_history", {"equipment_id": "INV-L3-01", "code": "OCt"})
        )
        await asyncio.sleep(0)  # 큐에 들어가고 워커가 집어들 틈을 준다
        cancelled_task.cancel()
        try:
            await cancelled_task
        except asyncio.CancelledError:
            pass

        # StreamingResponse 조기 종료와 같은 패턴 — 제너레이터를 소비 중에 닫는다
        async def streaming_turn():
            yield "start"
            r = await client.call("search_inventory", {"part_no": "FAN-IG5-01"})
            yield r.get("status")

        gen = streaming_turn()
        await gen.__anext__()
        await gen.aclose()

        revived = await client.call("search_inventory", {"part_no": "PCB-S100-CTRL"})
        scope_errs = [e for e in loop_errors if "cancel scope" in e.lower()]
        check(
            "⑧ 취소 안전성 (취소 직후 재호출 · cancel scope 예외 없음)",
            revived.get("status") == "ok" and not scope_errs,
            f"재호출 status={revived.get('status')}, cancel scope 예외 {len(scope_errs)}건",
        )

        # ── ⑨ 준비: 임시 DB 에 draft 를 쓴다 (검증은 verify_env_isolation)
        po = await client.call(
            "create_po_draft",
            {
                "part_no": "FAN-IG5-01",
                "qty": 2,
                "supplier_id": "SUP-A",
                "reason": "MQ-302 env 격리 검증 — 임시 DB 에만 써야 한다",
            },
        )
        check(
            "⑨-a create_po_draft 왕복 (쓰기 도구)",
            po.get("status") == "ok" and po.get("state") == "draft",
            f"status={po.get('status')}, po_id={po.get('po_id')}",
        )

        # ── 한 줄 요약 (SSE tool_result.summary)
        summaries = {
            "search_inventory": summarize_result("search_inventory", inv),
            "get_supplier_quotes": summarize_result("get_supplier_quotes", after),
            "create_po_draft": summarize_result("create_po_draft", po),
            "timeout": summarize_result("search_inventory", to),
        }
        check(
            "⑩ summarize_result 한 줄 요약",
            all(s and "\n" not in s for s in summaries.values())
            and "FAN-IG5-01" in summaries["search_inventory"]
            and "초과" in summaries["timeout"],
            " / ".join(f"{k}: {v}" for k, v in summaries.items())[:120],
        )
    finally:
        await client.stop()

    # ── 종료 후에도 예외가 아니라 status
    dead = await client.call("search_inventory", {"part_no": "FAN-IG5-01"})
    check(
        "⑪ stop() 후 호출 → status:error + reason:unavailable",
        dead.get("status") == "error" and dead.get("reason") == "unavailable" and not client.ready,
        f"status={dead.get('status')}, reason={dead.get('reason')}",
    )


async def run_startup_failure() -> None:
    """서버가 없어도 백엔드는 떠야 한다 — 09_RUNTIME §3 (MCP 서버 다운)."""
    client = McpClient(server_script=ROOT / "mcp_server" / "__no_such_server__.py")
    ok = await client.start()
    r = await client.call("search_inventory", {"part_no": "FAN-IG5-01"})
    check(
        "⑫ 기동 실패해도 예외 없이 status:error (앱은 산다)",
        ok is False and not client.ready and r.get("status") == "error",
        f"start={ok}, reason={r.get('reason')}",
    )
    await client.stop()


def verify_env_isolation(db: Path, before_rows: int, before_mtime: float) -> None:
    """D42 — `env={**os.environ}` 명시 상속이 실제로 자식에 닿았는가.

    닿지 않으면 자식은 기본 DB 를 열고, **임시 DB 는 그대로인데 실 DB 에 행이 는다.**
    """
    check(
        "⑨-b env 격리 · 임시 DB 에만 행 증가",
        po_count(db) == before_rows + 1,
        f"임시 DB {before_rows} → {po_count(db)}",
    )
    real_rows = po_count(SOURCE_DB)
    real_mtime = SOURCE_DB.stat().st_mtime
    check(
        "⑨-c 실 DB(data/maintq.db) mtime·row count 불변",
        real_rows == REAL_BEFORE[0] and real_mtime == REAL_BEFORE[1],
        f"rows {REAL_BEFORE[0]}→{real_rows}, mtime 변경={real_mtime != REAL_BEFORE[1]}",
    )
    check(
        "⑬ D15 프로세스 분리 (mcp_server 를 import 하지 않음)",
        "mcp_server" not in sys.modules,
        "sys.modules 에 없음" if "mcp_server" not in sys.modules else "import 됨 — D15 위반",
    )
    _ = before_mtime


REAL_BEFORE: tuple[int, float] = (0, 0.0)


def main() -> None:
    global REAL_BEFORE
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("MQ-302 — MCP 클라이언트(lifespan 워커) 계약 (D42·D46·D9·D15)\n")
    if not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    REAL_BEFORE = (po_count(SOURCE_DB), SOURCE_DB.stat().st_mtime)

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "client.db"
        shutil.copy2(SOURCE_DB, db)
        before_rows = po_count(db)

        # os.environ 경유로 준다 — SDK 화이트리스트 우회가 실제로 되는지 보는 게 목적이라
        # 생성자 override 가 아니라 이 경로여야 한다.
        prev = os.environ.get("MAINTQ_DB")
        os.environ["MAINTQ_DB"] = str(db)
        try:
            asyncio.run(run_session(db))
            asyncio.run(run_startup_failure())
        finally:
            if prev is None:
                os.environ.pop("MAINTQ_DB", None)
            else:
                os.environ["MAINTQ_DB"] = prev

        verify_env_isolation(db, before_rows, REAL_BEFORE[1])

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 46))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 46))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(f"\n통과 ({len(results)}건) — 워커 소유·shield 취소 안전·env 격리 확인")


if __name__ == "__main__":
    main()
