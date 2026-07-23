# -*- coding: utf-8 -*-
"""SP2 — MCP 서버 ↔ 클라이언트 왕복 검증 (docs/09_RUNTIME.md §4).

검증 질문: 도구 등록·호출·status 반환 왕복이 되는가?
실제 stdio 로 서버 프로세스를 띄우고 붙는다 (in-process 호출 아님) — D15 의
"프로세스 분리"가 실제로 성립하는지를 봐야 하기 때문.

실행:  uv run python spikes/sp2_mcp_roundtrip.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp_server" / "server.py"

EXPECTED_TOOLS = {
    "search_inventory",
    "find_alternative_parts",
    "get_supplier_quotes",
    "get_error_history",
}

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def payload(result) -> dict:
    """CallToolResult → 도구가 반환한 dict."""
    if getattr(result, "structuredContent", None):
        return result.structuredContent
    return json.loads(result.content[0].text)


async def run() -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            check("① 서버 initialize", True, "stdio 핸드셰이크 성공")

            listed = await session.list_tools()
            names = {t.name for t in listed.tools}
            check(
                "② 도구 등록",
                EXPECTED_TOOLS <= names,
                f"{len(names)}종: {', '.join(sorted(names))}",
            )

            missing_desc = [t.name for t in listed.tools if not (t.description or "").strip()]
            check(
                "③ description 존재 (오케스트레이션의 절반)",
                not missing_desc,
                "전부 있음" if not missing_desc else f"누락: {missing_desc}",
            )

            # ── S1: 안전재고 미달 케이스
            r = payload(await session.call_tool("search_inventory", {"part_no": "FAN-IG5-01"}))
            item = r["items"][0] if r.get("items") else {}
            check(
                "④ search_inventory (S1 재고 미달)",
                r["status"] == "ok" and item.get("qty") == 1 and item.get("safety_stock") == 3,
                f"status={r['status']}, qty={item.get('qty')}, safety={item.get('safety_stock')}",
            )

            # ── D28: model 필터가 기종 교차 오염을 막는가
            wide = payload(await session.call_tool("search_inventory", {"part_name": "냉각팬"}))
            narrow = payload(
                await session.call_tool(
                    "search_inventory", {"part_name": "냉각팬", "model": "S100"}
                )
            )
            wide_n = len(wide.get("items", []))
            narrow_models = {m for i in narrow.get("items", []) for m in i["compatible_models"]}
            check(
                "⑤ D28 model 필터",
                wide_n > len(narrow.get("items", []))
                and narrow_models <= {"S100", "iG5A"}
                and all("S100" in i["compatible_models"] for i in narrow.get("items", [])),
                f"필터 없음 {wide_n}건 → S100 지정 {len(narrow.get('items', []))}건",
            )

            # ── S2: 재고 0 + 단종 → 대체품 분기
            s2 = payload(await session.call_tool("search_inventory", {"part_no": "PCB-S100-CTRL"}))
            it = s2["items"][0]
            check(
                "⑥ S2 분기 근거 (qty 0 + 단종)",
                it["qty"] == 0 and it["discontinued"] is True,
                f"qty={it['qty']}, discontinued={it['discontinued']}",
            )

            alts = payload(
                await session.call_tool("find_alternative_parts", {"part_no": "PCB-S100-CTRL"})
            )
            check(
                "⑦ 대체품 조회",
                alts["status"] == "ok" and any(a["compat_confirmed"] for a in alts["alternatives"]),
                f"status={alts['status']}, {len(alts['alternatives'])}건",
            )

            # ── S2 서브: 대체품 없음 → status empty
            empty = payload(
                await session.call_tool("find_alternative_parts", {"part_no": "PWR-S100-MOD"})
            )
            check(
                "⑧ D9 status:empty (예외 아님)",
                empty["status"] == "empty",
                f"status={empty['status']}",
            )

            # ── S1: 견적 비교 + MOQ
            q = payload(
                await session.call_tool("get_supplier_quotes", {"part_no": "FAN-IG5-01", "qty": 2})
            )
            sups = {s["supplier_id"]: s for s in q.get("suppliers", [])}
            check(
                "⑨ 견적 트레이드오프 + MOQ",
                q["status"] == "ok"
                and sups["SUP-A"]["lead_days"] == 3
                and sups["SUP-B"]["moq"] == 10,
                f"A사 {sups['SUP-A']['lead_days']}일/₩{sups['SUP-A']['unit_price']:,}, "
                f"B사 {sups['SUP-B']['lead_days']}일/MOQ {sups['SUP-B']['moq']}",
            )

            # ── S3: 반복 고장 판정
            h = payload(
                await session.call_tool(
                    "get_error_history", {"equipment_id": "INV-L3-01", "code": "OCt", "days": 30}
                )
            )
            check(
                "⑩ S3 repeated 판정 (D25 대소문자 무관)",
                h["status"] == "ok" and h["count"] == 3 and h["repeated"] is True,
                f"count={h['count']}, repeated={h['repeated']} (입력 'OCt' → 저장 'OCT')",
            )

            # ── 없는 부품 → not_found (환각 방지의 도구측 근거)
            nf = payload(await session.call_tool("search_inventory", {"part_no": "NO-SUCH-PART"}))
            check("⑪ not_found 반환", nf["status"] == "not_found", f"status={nf['status']}")

            # ── 잘못된 입력도 예외가 아니라 status:error (D9)
            noargs = payload(await session.call_tool("search_inventory", {}))
            check(
                "⑫ 인자 누락 → status:error",
                noargs["status"] == "error",
                f"status={noargs['status']}, msg={noargs.get('message', '')[:32]}",
            )

            # ── D6/D13: model 은 enum 강제. 미지원 기종은 조용히 통과하면 안 된다
            bad_model = payload(
                await session.call_tool("search_inventory", {"part_name": "냉각팬", "model": "iS7"})
            )
            check(
                "⑬ model enum 강제 (iS7 거부)",
                bad_model["status"] == "error" and "iG5A" in bad_model.get("message", ""),
                f"status={bad_model['status']}, msg={bad_model.get('message', '')[:36]}",
            )


def check_write_isolation() -> None:
    """절대 규칙 1 — MCP 도구는 po_drafts 에 draft INSERT만 가능 (D10).

    MCP 왕복이 아니라 DB 계층 직접 검증이다. 규율(코드 리뷰)만으로 지키지 않고
    커넥션 수준에서 막혀 있는지를 본다.
    """
    sys.path.insert(0, str(ROOT))
    from mcp_server.db import draft_writer, read_only  # noqa: PLC0415

    try:
        with read_only() as con:
            con.execute("UPDATE inventory SET qty = qty + 1 WHERE part_no='FAN-IG5-01'")
        check("⑭ 읽기 커넥션 쓰기 차단", False, "쓰기가 통과해버렸다")
    except Exception as e:  # noqa: BLE001
        check("⑭ 읽기 커넥션 쓰기 차단", "readonly" in str(e).lower(), f"{type(e).__name__}")

    try:
        with draft_writer() as con:
            con.execute("UPDATE po_drafts SET state='approved' WHERE po_id='PO-0117'")
        check("⑮ 도구의 po_drafts UPDATE 차단 (D10)", False, "UPDATE 가 통과해버렸다")
    except Exception as e:  # noqa: BLE001
        check("⑮ 도구의 po_drafts UPDATE 차단 (D10)", "D10" in str(e), str(e)[:44])


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("SP2 — MCP 서버 ↔ 클라이언트 왕복 (stdio, 프로세스 분리)\n")
    try:
        asyncio.run(run())
        check_write_isolation()
    except Exception as e:  # noqa: BLE001
        print(f"[중단] {type(e).__name__}: {e}")
        raise SystemExit(1) from e

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 46))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 46))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[SP2 실패] {len(failed)}건: {', '.join(failed)}")
    print(f"\nSP2 통과 ({len(results)}건) — 도구 등록·호출·status 왕복 확인")


if __name__ == "__main__":
    main()
