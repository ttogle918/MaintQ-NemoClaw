# -*- coding: utf-8 -*-
"""deadlines/risk_grade 계약 검증 — DDL 무결성 · `track_deadlines` 4상태 · `assess_risk_grade` ·
프로파일 게이트 양방향 · REST 오류 매핑 (MQ-1106, D101·D102, D73, D88, D9).

Sprint 11 이 신설한 4테이블(`deadlines`·`incidents`·`ownership_checks`·`risk_profile`)과
2도구(`track_deadlines`·`assess_risk_grade`)는 Stage 1~4 에서 각각 개별 DoD 로만 확인됐고
회귀로 고정된 적이 없었다 — 이 파일이 그 공백을 덮는다. `tools_profile_contract.py` 가
프로파일 게이트 **전체**를 보는 것과 달리, 이 스위트는 이 두 도구의 판정 로직·DDL·REST 를
전담한다.

## 검증 6갈래

  1. DDL 무결성 — `deadlines`(type enum 밖 거부) · `incidents`(FK 위반 거부) ·
     `ownership_checks`(either-or CHECK 양성+음성) · `risk_profile`(risk_grade enum 밖 거부)
  2. `track_deadlines` — `today` 주입으로 `IN_REVIEW_BAND`·`UPCOMING`·`OVERDUE`·제외 4상태 재현 +
     **기본 호출이 정확히 0건**임을 확인하는 케이스(MQ-1102 DoD 회귀 고정) + `window_days` 경계값
  3. `assess_risk_grade` — BLD-C `changed=true`(의도적 불일치 시드), BLD-A `changed=false`,
     미등록 building_id `not_found`
  4. 프로파일 게이트 양방향 — `core` 미등록 / `full` 등록 (D69·D88)
  5. REST 오류 매핑 — `core` 프로파일 실 서버로 200/4xx 확인(D73 고정)
  6. **liveness 앵커** — `mcp_server/tools/*.py` 어디에도 4테이블 INSERT 코드가 없음을
     확인하되, 스캔 대상 파일 수(양성 축)를 함께 assert 한다(CLAUDE.md 부재검사 규칙)

`today` 를 주입해 결정론적으로 상태를 재현한다 — 벽시계에 의존하지 않는다(단, 검증 항목 2 의
"기본 호출 0건"만은 의도적으로 실제 오늘 날짜로 돌려 MQ-1102 DoD 를 있는 그대로 고정한다).

임시 DB 사본에서 돈다. review_band 는 하드코딩하지 않고 `data.rules.engine` 에서 그대로
읽는다 — `data/deadlines.py` 가 참조하는 것과 같은 원천이라야 룰이 바뀌어도 이 스위트가
따라간다.

실행:  uv run python spikes/deadline_risk_contract.py
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp_server" / "server.py"
SOURCE_DB = ROOT / "data" / "maintq.db"

sys.path.insert(0, str(ROOT))

results: list[tuple[str, bool, str]] = []
MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def check(name: str, ok: bool, detail: str) -> None:
    mark = MARKS[len(results)] if len(results) < len(MARKS) else f"[{len(results) + 1}]"
    results.append((f"{mark} {name}", ok, detail))


def raw_connect(db: Path) -> sqlite3.Connection:
    """DDL 테스트·픽스처 조작 전용 — `mcp_server.db` 를 거치지 않는 평범한 rw 커넥션.

    `mcp_server.db.read_only()` 는 `mode=ro` 라 쓸 수 없고, `draft_writer()` 류는 특정
    테이블에만 TEMP TRIGGER 를 걸어 다른 테이블 조작에는 맞지 않는다. 이 스위트는 시드
    자산 행을 직접 UPDATE 해 `today` 주입 시나리오의 사실관계를 만든다.
    """
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=ON")
    con.row_factory = sqlite3.Row
    return con


# ── ① DDL 무결성 ────────────────────────────────────────────────────────────
def check_ddl(db: Path) -> None:
    con = raw_connect(db)
    try:
        asset_id = con.execute("SELECT asset_id FROM assets ORDER BY asset_id LIMIT 1").fetchone()[0]
    finally:
        con.close()

    # deadlines.type 이 enum(TAX-CREDIT-2Y|SAFETY-INSPECTION) 밖 → CHECK 거부
    con = raw_connect(db)
    try:
        con.execute(
            "INSERT INTO deadlines (asset_id, type, due_date) VALUES (?,?,?)",
            (asset_id, "BOGUS-TYPE", "2026-01-01"),
        )
        con.commit()
        deadlines_rejected = False
    except sqlite3.IntegrityError:
        con.rollback()
        deadlines_rejected = True
    finally:
        con.close()
    check(
        "DDL — deadlines.type 이 enum(TAX-CREDIT-2Y|SAFETY-INSPECTION) 밖이면 CHECK 거부",
        deadlines_rejected,
        f"asset={asset_id} type=BOGUS-TYPE → {'거부됨' if deadlines_rejected else '삽입됨(결함)'}",
    )

    # incidents.asset_id 가 존재하지 않는 자산 → FK 위반
    con = raw_connect(db)
    try:
        con.execute(
            "INSERT INTO incidents (asset_id, type, occurred_at) VALUES (?,?,?)",
            ("AST-DOES-NOT-EXIST", "COLLISION", "2026-01-01 00:00:00"),
        )
        con.commit()
        incidents_rejected = False
    except sqlite3.IntegrityError:
        con.rollback()
        incidents_rejected = True
    finally:
        con.close()
    check(
        "DDL — incidents.asset_id 가 존재하지 않는 자산이면 FK 거부",
        incidents_rejected,
        f"asset=AST-DOES-NOT-EXIST → {'거부됨' if incidents_rejected else '삽입됨(결함)'}",
    )

    # ownership_checks either-or CHECK — 양성(state=VERIFIED+evidence_ref) 성공,
    # 음성(state=VERIFIED 인데 limit_note 를 채움) 거부. 두 CHECK 를 함께 지킨다:
    #   evidence_ref IS NULL OR state='VERIFIED'  /  limit_note IS NULL OR state='UNVERIFIED'
    con = raw_connect(db)
    try:
        con.execute(
            "INSERT INTO ownership_checks (asset_id, category, check_item, state,"
            " evidence_ref, limit_note, checked_at) VALUES (?,?,?,?,?,?,?)",
            (asset_id, "법정 요건", "DDL 계약 검증(양성)", "VERIFIED", "EVID-DDL-1", None, "2026-01-01 00:00:00"),
        )
        con.commit()
        positive_ok = True
    except sqlite3.IntegrityError:
        con.rollback()
        positive_ok = False
    finally:
        con.close()

    con = raw_connect(db)
    try:
        con.execute(
            "INSERT INTO ownership_checks (asset_id, category, check_item, state,"
            " evidence_ref, limit_note, checked_at) VALUES (?,?,?,?,?,?,?)",
            (asset_id, "법정 요건", "DDL 계약 검증(음성)", "VERIFIED", None, "확인 불가", "2026-01-01 00:00:00"),
        )
        con.commit()
        negative_rejected = False
    except sqlite3.IntegrityError:
        con.rollback()
        negative_rejected = True
    finally:
        con.close()

    check(
        "DDL — ownership_checks either-or CHECK: state=VERIFIED+evidence_ref 성공 · "
        "state=VERIFIED+limit_note 거부",
        positive_ok and negative_rejected,
        f"양성(evidence_ref 채움)={'성공' if positive_ok else '실패(결함)'} · "
        f"음성(VERIFIED 인데 limit_note 채움)={'거부됨' if negative_rejected else '삽입됨(결함)'}",
    )

    # risk_profile.risk_grade 가 enum(LOW|MEDIUM|HIGH) 밖 → CHECK 거부
    con = raw_connect(db)
    try:
        con.execute(
            "INSERT INTO risk_profile (building_id, risk_grade) VALUES (?,?)",
            ("BLD-DDL-TEST", "CRITICAL"),
        )
        con.commit()
        risk_rejected = False
    except sqlite3.IntegrityError:
        con.rollback()
        risk_rejected = True
    finally:
        con.close()
    check(
        "DDL — risk_profile.risk_grade 가 enum(LOW|MEDIUM|HIGH) 밖이면 CHECK 거부",
        risk_rejected,
        f"building=BLD-DDL-TEST risk_grade=CRITICAL → {'거부됨' if risk_rejected else '삽입됨(결함)'}",
    )


# ── ② track_deadlines — today 주입 4상태 + 기본 호출 0건 + window_days 경계값 ──────
def check_track_deadlines(db: Path) -> None:
    import data.deadlines as deadlines_mod  # noqa: PLC0415
    from data.rules import engine  # noqa: PLC0415
    from data.seed import _shift_months  # noqa: PLC0415
    from mcp_server.db import read_only  # noqa: PLC0415

    # ── 기본 호출(asset_id=None, window_days=180, today=실제 오늘) → 정확히 0건
    #    (MQ-1102 DoD 를 회귀로 고정 — 9자산 전부가 취득 후 24개월을 이미 넘긴 시드 구조)
    with read_only() as con:
        base = deadlines_mod.track_deadlines(con)
    check(
        "track_deadlines 기본 호출(인자 없음, 실제 오늘 날짜) → 정확히 0건 (D62, MQ-1102 DoD 고정)",
        base.get("status") == "ok" and base.get("items") == [],
        f"status={base.get('status')} items={len(base.get('items', []))}건",
    )

    rules = engine.load_rules(engine.load_laws())
    lo, hi = rules["TAX-CREDIT-2Y"].boundary["review_band"]

    test_asset = "AST-L1-CONV"  # 시드 실재 자산(BLD-A) — 픽스처 조작 전용
    fixed_today = date(2026, 1, 1)

    def set_asset(**cols: object) -> None:
        con2 = raw_connect(db)
        try:
            sets = ", ".join(f"{k}=?" for k in cols)
            con2.execute(
                f"UPDATE assets SET {sets} WHERE asset_id=?",  # noqa: S608 — 컬럼명은 리터럴 딕셔너리 키
                (*cols.values(), test_asset),
            )
            con2.commit()
        finally:
            con2.close()

    def call(**kwargs: object) -> dict:
        with read_only() as con2:
            return deadlines_mod.track_deadlines(con2, asset_id=test_asset, **kwargs)

    # ── IN_REVIEW_BAND — months_since = review_band 정중앙
    mid = (lo + hi) // 2
    set_asset(tax_credit_applied=1, acquired_at=_shift_months(fixed_today, -mid))
    r = call(today=fixed_today, window_days=180)
    items = r.get("items", [])
    check(
        f"today 주입 — IN_REVIEW_BAND (months_since={mid}, review_band=[{lo},{hi}])",
        r.get("status") == "ok"
        and len(items) == 1
        and items[0]["state"] == "IN_REVIEW_BAND"
        and items[0]["type"] == "TAX-CREDIT-2Y",
        f"status={r.get('status')} items={items}",
    )

    # ── UPCOMING — months_since < lo, days_remaining <= window_days
    months_upcoming = max(lo - 2, 0)
    set_asset(acquired_at=_shift_months(fixed_today, -months_upcoming))
    r = call(today=fixed_today, window_days=180)
    items = r.get("items", [])
    check(
        f"today 주입 — UPCOMING (months_since={months_upcoming} < lo={lo}, window_days=180)",
        r.get("status") == "ok"
        and len(items) == 1
        and items[0]["state"] == "UPCOMING"
        and items[0]["type"] == "TAX-CREDIT-2Y",
        f"status={r.get('status')} items={items}",
    )

    # ── 제외 — months_since >= hi (사후관리 기간을 이미 넘겼다 — 정직한 제외, D62)
    months_excluded = hi + 4
    set_asset(acquired_at=_shift_months(fixed_today, -months_excluded))
    r = call(today=fixed_today, window_days=180)
    items = r.get("items", [])
    check(
        f"today 주입 — 제외 (months_since={months_excluded} >= hi={hi}, 항목이 없어야 함)",
        r.get("status") == "ok" and items == [],
        f"status={r.get('status')} items={len(items)}건",
    )

    # ── OVERDUE — 안전검사 경로, 만료됨. window_days 를 작게 둬도 항상 포함돼야 한다
    set_asset(
        tax_credit_applied=0,
        safety_inspection_target=1,
        inspection_valid_until=(fixed_today - timedelta(days=30)).isoformat(),
    )
    r = call(today=fixed_today, window_days=1)
    items = r.get("items", [])
    check(
        "today 주입 — OVERDUE (안전검사 만료, window_days=1 이어도 항상 포함)",
        r.get("status") == "ok"
        and len(items) == 1
        and items[0]["state"] == "OVERDUE"
        and items[0]["type"] == "SAFETY-INSPECTION",
        f"status={r.get('status')} items={items}",
    )

    # ── window_days 경계값 — days_remaining=50 고정, window_days=50(포함) vs 49(제외)
    set_asset(inspection_valid_until=(fixed_today + timedelta(days=50)).isoformat())
    r_in = call(today=fixed_today, window_days=50)
    r_out = call(today=fixed_today, window_days=49)
    items_in = r_in.get("items", [])
    items_out = r_out.get("items", [])
    check(
        "window_days 경계값 — days_remaining=50 일 때 window_days=50 은 포함(<=) · 49 는 제외",
        r_in.get("status") == "ok"
        and len(items_in) == 1
        and items_in[0]["state"] == "UPCOMING"
        and r_out.get("status") == "ok"
        and items_out == [],
        f"window_days=50→{len(items_in)}건 · window_days=49→{len(items_out)}건",
    )


# ── ③ assess_risk_grade ─────────────────────────────────────────────────────
def check_risk_grade(db: Path) -> None:
    import data.risk_grade as risk_grade_mod  # noqa: PLC0415
    from mcp_server.db import read_only  # noqa: PLC0415

    with read_only() as con:
        r_c = risk_grade_mod.risk_grade(con, building_id="BLD-C")
    check(
        "assess_risk_grade — BLD-C: changed=true (stored=LOW, 재계산=HIGH, 의도적 불일치 시드)",
        r_c.get("status") == "ok"
        and r_c.get("changed") is True
        and r_c.get("current_grade") == "HIGH"
        and r_c.get("stored_grade") == "LOW",
        f"status={r_c.get('status')} changed={r_c.get('changed')} "
        f"current={r_c.get('current_grade')} stored={r_c.get('stored_grade')}",
    )

    with read_only() as con:
        r_a = risk_grade_mod.risk_grade(con, building_id="BLD-A")
    check(
        "assess_risk_grade — BLD-A: changed=false (저장값과 재계산이 일치)",
        r_a.get("status") == "ok" and r_a.get("changed") is False,
        f"status={r_a.get('status')} changed={r_a.get('changed')} "
        f"current={r_a.get('current_grade')} stored={r_a.get('stored_grade')}",
    )

    with read_only() as con:
        r_x = risk_grade_mod.risk_grade(con, building_id="BLD-NOPE")
    check(
        "assess_risk_grade — 미등록 building_id → not_found/unknown_building",
        r_x.get("status") == "not_found" and r_x.get("reason") == "unknown_building",
        f"status={r_x.get('status')} reason={r_x.get('reason')}",
    )


# ── ④ 프로파일 게이트 양방향 ─────────────────────────────────────────────────────
async def _list_tool_names(profile: str, db: Path) -> set[str]:
    env = {k: v for k, v in os.environ.items() if v is not None}
    env["MAINTQ_TOOLS_PROFILE"] = profile
    env["MAINTQ_DB"] = str(db)
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            return {t.name for t in listed.tools}


def check_profile_gate(db: Path) -> None:
    full_names = asyncio.run(_list_tool_names("full", db))
    core_names = asyncio.run(_list_tool_names("core", db))
    target = {"track_deadlines", "assess_risk_grade"}
    check(
        "프로파일 게이트 — full 기동 시 track_deadlines·assess_risk_grade 둘 다 등록",
        target <= full_names,
        f"full 도구 {len(full_names)}종 · 포함={sorted(target & full_names)}",
    )
    check(
        "프로파일 게이트 — core 기동 시 두 도구 모두 미등록 (D88, 평가는 core 기준)",
        not (target & core_names),
        f"core 도구 {len(core_names)}종 · 누출={sorted(target & core_names) or '없음'}",
    )


# ── ⑤ REST 오류 매핑 (core 프로파일, D73) ────────────────────────────────────────
def check_rest(db: Path) -> None:
    os.environ["MAINTQ_TOOLS_PROFILE"] = "core"
    os.environ["MAINTQ_MCP_AUTOSTART"] = "0"  # 판정은 MCP 프로세스와 무관하다 (D73)

    from fastapi.testclient import TestClient  # noqa: PLC0415

    from backend.main import app  # noqa: PLC0415

    with TestClient(app) as client:
        r1 = client.get("/api/deadlines", params={"asset_id": "AST-L1-CONV"})
        r2 = client.get("/api/deadlines", params={"asset_id": "AST-NOPE"})
        r3 = client.get("/api/deadlines", params={"window_days": -1})
        r4 = client.get("/api/buildings/BLD-A/risk-grade")
        r5 = client.get("/api/assets/AST-L1-CONV/risk-grade")
        r6 = client.get("/api/buildings/BLD-NOPE/risk-grade")

    check(
        "REST(core) — GET /api/deadlines: 정상 자산 200 · 없는 자산 404 · window_days=-1 422",
        r1.status_code == 200 and r2.status_code == 404 and r3.status_code == 422,
        f"{r1.status_code}/{r2.status_code}/{r3.status_code} (asset_id 정상/없음, window_days=-1)",
    )
    check(
        "REST(core) — GET .../risk-grade: building 200 · asset 200 · 없는 building 404 (D73)",
        r4.status_code == 200 and r5.status_code == 200 and r6.status_code == 404,
        f"{r4.status_code}/{r5.status_code}/{r6.status_code} (BLD-A/AST-L1-CONV/BLD-NOPE)",
    )


# ── ⑥ liveness 앵커 — 쓰기 부재 검사는 반드시 양성 축(스캔 파일 수)과 함께 ──────────
def check_liveness_anchor() -> None:
    tools_dir = ROOT / "mcp_server" / "tools"
    files = sorted(tools_dir.glob("*.py"))
    needles = ("INSERT INTO deadlines", "INSERT INTO incidents", "INSERT INTO ownership_checks", "INSERT INTO risk_profile")
    bad = []
    for f in files:
        src = f.read_text(encoding="utf-8")
        hits = [n for n in needles if n in src]
        if hits:
            bad.append(f"{f.name}:{hits}")
    check(
        "liveness 앵커 — mcp_server/tools/*.py 전 파일에 deadlines·incidents·ownership_checks·"
        "risk_profile INSERT 코드 부재 (양성 축: 스캔 파일 수 > 0)",
        not bad and len(files) > 0,
        f"스캔 {len(files)}개 파일 · 위반={bad or '없음'}",
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print(
        "deadlines/risk_grade 계약 검증 — DDL 무결성 · track_deadlines 4상태 · "
        "assess_risk_grade · 프로파일 게이트 · REST 매핑 (MQ-1106)\n"
    )
    if not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "deadline_risk.db"
        shutil.copy2(SOURCE_DB, db)

        # backend·mcp_server 둘 다 이 경로를 **import 시점에** 읽는다 — 실 DB 를 건드리지 않는다
        os.environ["MAINTQ_DB"] = str(db)

        check_ddl(db)
        check_track_deadlines(db)
        check_risk_grade(db)
        check_profile_gate(db)
        check_rest(db)
        check_liveness_anchor()

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 40))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 40))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건:\n  - " + "\n  - ".join(failed))
    print(
        f"\n통과 ({len(results)}건) — DDL 무결성 · track_deadlines 4상태·경계값 · "
        "assess_risk_grade · 프로파일 게이트 양방향 · REST 매핑 · liveness 앵커"
    )


if __name__ == "__main__":
    main()
