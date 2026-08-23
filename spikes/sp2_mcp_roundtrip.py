# -*- coding: utf-8 -*-
"""SP2 — MCP 서버 ↔ 클라이언트 왕복 검증 (docs/09_RUNTIME.md §4).

검증 질문: 도구 등록·호출·status 반환 왕복이 되는가?
실제 stdio 로 서버 프로세스를 띄우고 붙는다 (in-process 호출 아님) — D15 의
"프로세스 분리"가 실제로 성립하는지를 봐야 하기 때문.

## DB 격리 (MQ-704)

이 스위트는 원래 실 `data/maintq.db` 를 자식 서버와 공유했다. 같은 파일을 WAL 로 쓰는
다른 스위트(`s4_smoke`·`mcp_client_contract`)와 **연속 실행**하면, Windows 는 앞 스위트의
자식 프로세스 핸들 해제가 비동기라 writer 락 경합으로 `busy_timeout` 이 만료된다.
그래서 진입 시 DB 를 임시 디렉터리로 복사하고 `MAINTQ_DB` 로 그 사본을 가리킨다.

  - 자식 stdio 서버에는 **`env={**os.environ}` 를 명시 전달**한다 — SDK 기본값(`env=None`)은
    화이트리스트만 상속해 `MAINTQ_DB` 를 넘기지 않는다 (`backend/agent/mcp_client.py` §env 명시 상속).
  - `check_write_isolation` 이 import 하는 `mcp_server.db` 는 **import 시점에** `MAINTQ_DB` 를
    읽는다(`db.py:21`) → 환경변수를 심은 뒤에 import 해야 한다.
  - 실 DB 는 mtime·size 를 전후 비교한다. 이건 검사 19건에 들어가지 않는 **격리 게이트**다 —
    깨지면 계약 결과와 무관하게 중단시킨다.

실행:  uv run python spikes/sp2_mcp_roundtrip.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp_server" / "server.py"
SOURCE_DB = ROOT / "data" / "maintq.db"

EXPECTED_TOOLS = {
    "rag_search_manual",
    "lookup_error_code",
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


def copy_db(src: Path, dst: Path) -> Path:
    """DB 를 사본으로 뜬다. WAL 사이드카가 있으면 함께 가져온다.

    원본에 `wal_checkpoint` 를 걸지 않는다 — 그 순간 실 DB 의 mtime 이 변해
    "원본을 건드리지 않았다"는 게이트가 자기 손으로 깨진다.
    """
    shutil.copy2(src, dst)
    for suffix in ("-wal", "-shm"):
        side = src.with_name(src.name + suffix)
        if side.exists():
            shutil.copy2(side, dst.with_name(dst.name + suffix))
    return dst


async def run() -> None:
    # env 명시 — 기본값(None)이면 SDK 화이트리스트만 상속돼 MAINTQ_DB 가 자식에 안 닿는다.
    # 그러면 자식은 실 DB 를 열고, 이 스위트는 "격리된 척" 통과한다.
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env={**os.environ})

    # `stdio_client` 는 컨텍스트 종료 시 stdin 을 닫고 `process.wait()` 로 자식 종료를
    # **기다린다**(SDK stdio/__init__.py:205). sleep 으로 대체하지 않는다.
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

            # ── ⑤-b part_name 은 띄어쓰기에 흔들리지 않아야 한다
            #
            # 실측 배경(2026-08-05 평가): LLM 은 부품명을 자연스럽게 띄어 쓴다
            # ("냉각 팬", "전원 모듈"). 시드의 name 은 붙여쓰기라 LIKE 가 통째로 빗나가
            # not_found 가 났고, T04·T15 가 "부품을 찾을 수 없습니다"로 끝났다.
            # S2 진입(에러코드 없이 부품명만 말하는 경로)은 이름 조회가 **유일한 경로**라
            # 여기서 막히면 분기 자체가 성립하지 않는다.
            spaced = payload(
                await session.call_tool(
                    "search_inventory", {"part_name": "냉각 팬", "model": "iG5A"}
                )
            )
            tight = payload(
                await session.call_tool(
                    "search_inventory", {"part_name": "냉각팬", "model": "iG5A"}
                )
            )
            spaced_nos = [i["part_no"] for i in spaced.get("items", [])]
            check(
                "⑤-b part_name 공백 무관 매칭",
                spaced.get("status") == "ok"
                and spaced_nos == [i["part_no"] for i in tight.get("items", [])],
                f"'냉각 팬' → {spaced.get('status')} {spaced_nos}",
            )

            # 반대 방향 — 시드 이름에 공백이 있어도 붙여 쓴 질의로 찾혀야 한다
            pwr = payload(
                await session.call_tool(
                    "search_inventory", {"part_name": "전원 모듈", "model": "S100"}
                )
            )
            check(
                "⑤-c part_name 공백 무관 매칭 (전원모듈)",
                pwr.get("status") == "ok"
                and any(i["part_no"] == "PWR-S100-MOD" for i in pwr.get("items", [])),
                f"'전원 모듈' → {pwr.get('status')} "
                f"{[i['part_no'] for i in pwr.get('items', [])]}",
            )

            # ── ⑤-d line_id 에 라인 이름이 오면 예외가 아니라 status:error (D9)
            #
            # 실측(2026-08-05): LLM 이 line_id 에 "2번 가공라인"·"L1" 을 넣었고, 시그니처가
            # int 라 MCP 스키마 검증이 예외를 던져 원문 오류가 그대로 샜다. 에이전트는
            # 조치할 수 없고 턴당 도구 상한(8회)만 축난다. 추정해서 2 를 뽑지도 않는다 —
            # 라인을 잘못 짚으면 남의 설비 이력으로 repeated 를 판정하게 된다.
            bad_line = payload(
                await session.call_tool("get_error_history", {"line_id": "2번 가공라인"})
            )
            check(
                "⑤-d line_id 라인 이름 → status:error (예외 아님)",
                bad_line.get("status") == "error"
                and bad_line.get("reason") == "invalid_line_id",
                f"status={bad_line.get('status')}, reason={bad_line.get('reason')}",
            )

            # 숫자 문자열은 받아준다 — 값이 명확해 추정이 아니다
            num_line = payload(
                await session.call_tool("get_error_history", {"line_id": "3", "code": "OCT"})
            )
            check(
                "⑤-e line_id 숫자 문자열은 정상 조회",
                num_line.get("status") == "ok" and num_line.get("count", 0) >= 3,
                f"status={num_line.get('status')}, count={num_line.get('count')}",
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
    from mcp_server import db as mcp_db  # noqa: PLC0415
    from mcp_server.db import draft_writer, read_only  # noqa: PLC0415

    # 격리 증명 — 이 커넥션들이 실 DB 가 아니라 사본을 여는지 눈으로 확인한다
    print(f"[격리] mcp_server.db.DB_PATH = {mcp_db.DB_PATH}")

    try:
        with read_only() as con:
            con.execute("UPDATE inventory SET qty = qty + 1 WHERE part_no='FAN-IG5-01'")
        check("⑭ 읽기 커넥션 쓰기 차단", False, "쓰기가 통과해버렸다")
    except Exception as e:  # noqa: BLE001
        # SQLite 는 "attempt to write a readonly database", Postgres 는
        # "read-only transaction" — 문구는 다르지만 둘 다 물리적 강제가 막았다는 신호다.
        msg = str(e).lower()
        check(
            "⑭ 읽기 커넥션 쓰기 차단",
            "readonly" in msg or "read-only" in msg,
            f"{type(e).__name__}",
        )

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
    if not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    before = (SOURCE_DB.stat().st_mtime_ns, SOURCE_DB.stat().st_size)
    print(f"[격리] 실 DB(before) mtime_ns={before[0]} size={before[1]}")

    # Windows 는 sqlite 커넥션이 하나라도 열려 있으면 파일을 못 지운다 —
    # 정리 실패로 계약 검증 결과가 가려지지 않게 한다 (rules_db_load.py 선례)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = copy_db(SOURCE_DB, Path(td) / "sp2.db")
        prev = os.environ.get("MAINTQ_DB")
        os.environ["MAINTQ_DB"] = str(db)
        print(f"[격리] MAINTQ_DB = {db}\n")
        try:
            asyncio.run(run())
            check_write_isolation()
        except Exception as e:  # noqa: BLE001
            print(f"[중단] {type(e).__name__}: {e}")
            raise SystemExit(1) from e
        finally:
            if prev is None:
                os.environ.pop("MAINTQ_DB", None)
            else:
                os.environ["MAINTQ_DB"] = prev

    after = (SOURCE_DB.stat().st_mtime_ns, SOURCE_DB.stat().st_size)
    print(f"[격리] 실 DB(after)  mtime_ns={after[0]} size={after[1]}\n")

    # 격리를 **계수되는 검사**로 둔다 (MQ-704 판단 요청 1).
    # 비계수 게이트로 두면 러너 출력에 격리 생존 여부가 안 나타나 매 회귀마다 확인이 안 된다.
    # `s4_smoke`("DB 안전 …")·`mcp_client_contract` ⑨-c 와 같은 형태 — sp2 만 예외일 이유가 없다.
    # 이 검사가 없던 시절 sp2 는 `env=None` 탓에 **실 DB 를 읽으면서 통과**하고 있었다.
    check(
        "⑳ 격리 · 실 data/maintq.db mtime·size 불변",
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
        raise SystemExit(f"\n[SP2 실패] {len(failed)}건: {', '.join(failed)}")

    print(f"\nSP2 통과 ({len(results)}건) — 도구 등록·호출·status 왕복 확인")


if __name__ == "__main__":
    main()
