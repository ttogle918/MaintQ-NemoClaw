# -*- coding: utf-8 -*-
"""create_po_draft 계약 검증 — 유일한 쓰기 도구가 경계를 지키는가.

검증 대상: D10(draft INSERT만) · D23·D37(신원은 도구 스키마에 없음) ·
          D31(단가 스냅샷 / MOQ 거부) · D33(코드 FK) · D34(evidence)

실제 DB를 오염시키지 않도록 **임시 사본**을 만들고 MAINTQ_DB 로 주입한다.
error_codes 는 사람 승인 전이라 비어 있으므로, D33 FK 검증만은 사본에
검증용 코드 1건을 직접 넣어 확인한다 (원본 DB·추출 JSON 은 건드리지 않음).

실행:  uv run python spikes/write_tool_contract.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp_server" / "server.py"
SOURCE_DB = ROOT / "data" / "maintq.db"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def payload(result) -> dict:
    if getattr(result, "structuredContent", None):
        return result.structuredContent
    return json.loads(result.content[0].text)


def prepare_db(tmp: Path) -> Path:
    """실제 DB 사본 + D33 검증용 error_codes 1건."""
    db = tmp / "contract.db"
    shutil.copy2(SOURCE_DB, db)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute(
        "INSERT INTO error_codes (model, code, display_code, error_name, severity,"
        " causes, actions, related_parts, manual_page)"
        " VALUES ('iG5A','OHT','OHt','인버터 과열','warning','[]','[]',NULL,202)"
    )
    con.commit()
    con.close()
    return db


EVIDENCE = {
    "symptoms": ["냉각팬 소음 증가"],
    "basis": [{"tool": "lookup_error_code", "code": "OHT", "manual_page": 202}],
    "notes": "야간조 육안 확인",
}


async def run(db: Path) -> None:
    env = {**os.environ, "MAINTQ_DB": str(db)}
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env=env)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            listed = await session.list_tools()
            tool = next(t for t in listed.tools if t.name == "create_po_draft")
            props = set((tool.inputSchema or {}).get("properties", {}))

            # ── D23·D37: 신원·단가가 LLM 이 채울 수 있는 자리에 있으면 안 된다
            forbidden = {"requested_by", "decided_by", "session_id", "unit_price", "state"}
            check(
                "① 신원·단가·state 가 스키마에 없음 (D23·D31·D37)",
                not (props & forbidden),
                f"노출 파라미터: {sorted(props)}",
            )

            # ── 정상 발주 (MOQ 1 인 SUP-A)
            ok = payload(
                await session.call_tool(
                    "create_po_draft",
                    {
                        "part_no": "FAN-IG5-01",
                        "qty": 2,
                        "supplier_id": "SUP-A",
                        "reason": "iG5A OHt 과열 — 냉각팬 고장 유력 (매뉴얼 p.202)",
                        "urgency": "urgent",
                        "model": "iG5A",
                        "error_code": "OHt",
                        "evidence": EVIDENCE,
                    },
                )
            )
            check(
                "② 정상 발주 → draft 생성",
                ok["status"] == "ok" and ok["state"] == "draft",
                f"po_id={ok.get('po_id')}, state={ok.get('state')}",
            )
            check(
                "③ D31 단가 스냅샷 (입력 아님)",
                ok.get("unit_price") == 38000 and ok.get("total") == 76000,
                f"unit_price={ok.get('unit_price')}, total={ok.get('total')}",
            )
            po_id = ok["po_id"]

            # ── D31: MOQ 미달은 자동 상향이 아니라 거부
            moq = payload(
                await session.call_tool(
                    "create_po_draft",
                    {
                        "part_no": "FAN-IG5-01",
                        "qty": 2,
                        "supplier_id": "SUP-B",  # MOQ 10
                        "reason": "단가 저렴한 B사로",
                    },
                )
            )
            check(
                "④ D31 MOQ 미달 거부 (자동 상향 안 함)",
                moq["status"] == "error"
                and moq.get("reason") == "moq_not_met"
                and moq.get("moq") == 10,
                f"reason={moq.get('reason')}, moq={moq.get('moq')}",
            )

            # ── D33: 매뉴얼에 없는 코드는 거부
            bad = payload(
                await session.call_tool(
                    "create_po_draft",
                    {
                        "part_no": "FAN-IG5-01",
                        "qty": 1,
                        "supplier_id": "SUP-A",
                        "reason": "미지 코드로 발주 시도",
                        "model": "iG5A",
                        "error_code": "XY9",
                    },
                )
            )
            check(
                "⑤ D33 미지 코드 거부 (환각이 발주까지 못 감)",
                bad["status"] == "error" and bad.get("reason") == "unknown_error_code",
                f"reason={bad.get('reason')}",
            )

            # ── D33: model 만 주고 code 를 빼면 거부
            pair = payload(
                await session.call_tool(
                    "create_po_draft",
                    {
                        "part_no": "FAN-IG5-01",
                        "qty": 1,
                        "supplier_id": "SUP-A",
                        "reason": "짝 안 맞는 입력",
                        "model": "iG5A",
                    },
                )
            )
            check(
                "⑥ D33 model/code 짝 강제",
                pair["status"] == "error" and pair.get("reason") == "model_code_pair",
                f"reason={pair.get('reason')}",
            )

            # ── D5: reason 없이는 발주 못 만든다
            noreason = payload(
                await session.call_tool(
                    "create_po_draft",
                    {"part_no": "FAN-IG5-01", "qty": 1, "supplier_id": "SUP-A", "reason": "  "},
                )
            )
            check(
                "⑦ D5 reason 필수",
                noreason["status"] == "error" and noreason.get("reason") == "reason_required",
                f"reason={noreason.get('reason')}",
            )

            # ── 공급 안 하는 조합
            nq = payload(
                await session.call_tool(
                    "create_po_draft",
                    {
                        "part_no": "FAN-IG5-01",
                        "qty": 1,
                        "supplier_id": "SUP-D",
                        "reason": "공급 안 하는 조합",
                    },
                )
            )
            check(
                "⑧ 견적 없는 공급사 → not_found",
                nq["status"] == "not_found" and nq.get("reason") == "no_quote",
                f"status={nq['status']}, reason={nq.get('reason')}",
            )

            return po_id


def verify_row(db: Path, po_id: str) -> None:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM po_drafts WHERE po_id=?", (po_id,)).fetchone()

    check(
        "⑨ D10 state 는 draft 고정",
        r["state"] == "draft",
        f"state={r['state']}",
    )
    check(
        "⑩ D23 신원은 도구가 못 채움 (INSERT 시 NULL)",
        r["requested_by"] is None and r["session_id"] is None,
        f"requested_by={r['requested_by']}, session_id={r['session_id']}",
    )
    ev = json.loads(r["evidence"])
    check(
        "⑪ D34 evidence 저장",
        set(ev) == {"symptoms", "basis", "notes"} and ev["symptoms"],
        f"keys={sorted(ev)}",
    )
    check(
        "⑫ D25 코드는 대문자 canonical 저장 ('OHt'→'OHT')",
        r["error_code"] == "OHT" and r["model"] == "iG5A",
        f"model={r['model']}, error_code={r['error_code']}",
    )
    con.close()

    # ── D37: 백엔드가 신원을 stamp 한다
    sys.path.insert(0, str(ROOT))
    from backend.services.po import display_name, stamp_identity  # noqa: PLC0415

    ok1 = stamp_identity(po_id, "tech-01", "S1", db_path=db)
    ok2 = stamp_identity(po_id, "mgr-01", "S9", db_path=db)  # 재stamp 시도
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    r2 = con.execute("SELECT * FROM po_drafts WHERE po_id=?", (po_id,)).fetchone()
    con.close()
    check(
        "⑬ D37 백엔드 stamp (1회만, 덮어쓰기 불가)",
        ok1 and not ok2 and r2["requested_by"] == "tech-01" and r2["session_id"] == "S1",
        f"1차={ok1}, 2차={ok2}, requested_by={r2['requested_by']}",
    )
    check(
        "⑭ D36 표시명은 서버 매핑",
        display_name("tech-01") == "김OO",
        f"tech-01 → {display_name('tech-01')}",
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("create_po_draft 계약 검증 — 유일한 쓰기 도구 (임시 DB 사본)\n")
    if not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    with tempfile.TemporaryDirectory() as td:
        db = prepare_db(Path(td))
        po_id = asyncio.run(run(db))
        verify_row(db, po_id)

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 44))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 44))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(f"\n통과 ({len(results)}건) — 쓰기 도구가 D10·D23·D31·D33·D34·D37 경계를 지킨다")


if __name__ == "__main__":
    main()
