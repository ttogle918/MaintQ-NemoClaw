# -*- coding: utf-8 -*-
"""D158 사업장 평면도 REST 계약 — `GET /api/sites` · `GET /api/sites/{site_id}/floorplan`
(Sprint 19 MQ-1914).

이 계약이 지키는 것:
  1. **평면도에 모든 설비가 있다** — 위치 없는 설비가 생기면 화면에서 조용히 사라진다.
     기대 대수는 하드코딩하지 않고 `equipment` 실측에서 파생한다(설비가 늘면 같이 움직인다).
  2. **좌표가 구역 사각형 안, 구역이 사업장 안** — 점이 엉뚱한 구역 위에 찍히면 정비사가
     다른 설비를 누른다.
  3. **HV600 은 공조·유틸리티동에 있다**(D158) · **목업 사업장은 목업이라고 말한다**.
  4. **읽기 전용 · 역할 무관** — 두 역할이 같은 바이트를 받고, 쓰기 메서드는 없고(405),
     호출 전후 DB 행 수가 같다.
  5. **`equipment` 에 컬럼이 추가되지 않았다**(D158 ⓐ — A2A 페이로드 계약면 불변의 구조적 근거).
  6. **마이그레이션 DDL 블록이 멱등**이다 — 같은 스키마에 두 번 실행해도 두 번째가 무변화.

격리 스키마(`data/pg_isolation`, public 복제)에서 돈다 — 공유 DB 에 쓰지 않는다.

실행:  DATABASE_URL=... uv run python spikes/site_floorplan_contract.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402

from data import pg_isolation  # noqa: E402
from data.site_layout import (  # noqa: E402
    EQUIPMENT_LOCATIONS,
    HV600_EQUIPMENT,
    SITES,
    ZONES,
    location_inside_zone,
)

results: list[tuple[str, bool, str]] = []
MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

TECH = {"X-Role": "technician", "X-User": "tech-01"}
MGR = {"X-Role": "manager", "X-User": "mgr-01"}

EQUIPMENT_COLUMNS = {"equipment_id", "line_id", "model", "installed_at", "location", "asset_id"}
FLOORPLAN_KEYS = {"site", "zones", "equipment"}
SITE_KEYS = {"site_id", "name", "is_mock", "width", "height"}
ZONE_KEYS = {"zone_id", "name", "kind", "x", "y", "w", "h"}
EQ_KEYS = {"equipment_id", "model", "zone_id", "x", "y", "location", "asset_id", "asset_name"}
FINGERPRINT_TABLES = ("sites", "zones", "equipment_locations", "equipment", "assets", "traces")


def check(name: str, ok: bool, detail: str) -> None:
    mark = MARKS[len(results)] if len(results) < len(MARKS) else f"[{len(results) + 1}]"
    results.append((f"{mark} {name}", ok, detail))


def canon(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def counts(dsn: str) -> dict[str, int]:
    with psycopg.connect(dsn) as con:
        return {
            t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]  # noqa: S608
            for t in FINGERPRINT_TABLES
        }


def run(client, dsn: str) -> None:
    with psycopg.connect(dsn) as con:
        eq_rows = con.execute(
            "SELECT equipment_id, model, asset_id FROM equipment ORDER BY equipment_id"
        ).fetchall()
        asset_names = dict(con.execute("SELECT asset_id, name FROM assets").fetchall())
        eq_cols = {
            r[0]
            for r in con.execute(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = current_schema() AND table_name = 'equipment'"
            )
        }
    db_ids = [r[0] for r in eq_rows]
    before = counts(dsn)

    # ① 사업장 목록 형상 · 목업 표시
    r = client.get("/api/sites", headers=TECH)
    items = r.json().get("items", []) if r.status_code == 200 else []
    check(
        "GET /api/sites 형상 · 목업 사업장은 is_mock=true",
        r.status_code == 200
        and len(items) == len(SITES) >= 1
        and all(set(i) == SITE_KEYS for i in items)
        and all(i["is_mock"] is True for i in items)
        and all("목업" in i["name"] for i in items),
        f"{r.status_code} · {len(items)}곳 · {[(i.get('site_id'), i.get('name'), i.get('is_mock')) for i in items]}",
    )
    site_id = items[0]["site_id"] if items else SITES[0][0]

    # ② 평면도 형상
    r = client.get(f"/api/sites/{site_id}/floorplan", headers=TECH)
    fp = r.json() if r.status_code == 200 else {}
    zones = fp.get("zones", [])
    eqs = fp.get("equipment", [])
    check(
        "floorplan 형상 — site·zones·equipment 키 집합 고정",
        r.status_code == 200
        and set(fp) == FLOORPLAN_KEYS
        and set(fp["site"]) == SITE_KEYS
        and bool(zones) and all(set(z) == ZONE_KEYS for z in zones)
        and bool(eqs) and all(set(e) == EQ_KEYS for e in eqs),
        f"{r.status_code} · 키={sorted(fp)} · zones {len(zones)} · equipment {len(eqs)}",
    )

    # ③ 설비 전부가 평면도에 있다 — 기대값은 DB 실측(양성 축 len(db_ids) > 0 포함)
    fp_ids = sorted(e["equipment_id"] for e in eqs)
    check(
        "설비 전부 위치 있음 (floorplan 설비 == equipment 전체)",
        len(db_ids) > 0 and fp_ids == db_ids and len(db_ids) == len(EQUIPMENT_LOCATIONS),
        f"equipment {len(db_ids)}대 · 평면도 {len(fp_ids)}대 · 누락 {sorted(set(db_ids) - set(fp_ids)) or 0}",
    )

    # ④ HV600 2대 전부 공조·유틸리티동
    zone_by_id = {z["zone_id"]: z for z in zones}
    hv = [e for e in eqs if e["model"] == "HV600"]
    hv_zones = sorted({(zone_by_id[e["zone_id"]]["kind"], zone_by_id[e["zone_id"]]["name"]) for e in hv})
    check(
        "HV600 설비는 공조·유틸리티동(kind=utility)에만",
        len(hv) == len(HV600_EQUIPMENT) == 2
        and sorted(e["equipment_id"] for e in hv) == sorted(x[0] for x in HV600_EQUIPMENT)
        and hv_zones == [("utility", "공조·유틸리티동")],
        f"HV600 {len(hv)}대 {[e['equipment_id'] for e in hv]} · 구역 {hv_zones}",
    )

    # ⑤ 좌표가 구역 안 · 구역이 사업장 안 (스캔 수를 detail 에 함께 — 부재 검사 liveness)
    site = fp.get("site", {})
    outside = [
        e["equipment_id"]
        for e in eqs
        if not location_inside_zone(
            e["x"], e["y"],
            (e["zone_id"], site_id, "", "", *(zone_by_id[e["zone_id"]][k] for k in ("x", "y", "w", "h"))),
        )
    ]
    zone_out = [
        z["zone_id"]
        for z in zones
        if not (z["x"] + z["w"] <= site.get("width", 0) and z["y"] + z["h"] <= site.get("height", 0))
    ]
    check(
        "설비 좌표가 소속 구역 안 · 구역이 사업장 안",
        bool(eqs) and bool(zones) and not outside and not zone_out,
        f"설비 스캔 {len(eqs)} · 구역 밖 {outside or 0} · 구역 스캔 {len(zones)} · 사업장 밖 {zone_out or 0}",
    )

    # ⑥ asset_name 은 호스트 자산이 있을 때만 — null 을 지어낸 이름으로 메우지 않는다
    by_db = {r[0]: r for r in eq_rows}
    wrong = [
        e["equipment_id"]
        for e in eqs
        if e["asset_id"] != by_db[e["equipment_id"]][2]
        or e["asset_name"] != (asset_names.get(e["asset_id"]) if e["asset_id"] else None)
    ]
    n_null = sum(1 for e in eqs if e["asset_name"] is None)
    n_named = sum(1 for e in eqs if e["asset_name"] is not None)
    check(
        "asset_name = assets.name (asset_id NULL 이면 null)",
        not wrong and n_null >= 3 and n_named >= 1,
        f"불일치 {wrong or 0} · null {n_null}대(분전반+HV600 기대 ≥3) · 이름 있음 {n_named}대",
    )

    # ⑦ 404
    r = client.get("/api/sites/NO-SUCH-SITE/floorplan", headers=TECH)
    check("없는 사업장 → 404", r.status_code == 404, f"{r.status_code}")

    # ⑧ 역할 무관 — 두 역할이 같은 바이트
    t1 = client.get(f"/api/sites/{site_id}/floorplan", headers=TECH)
    m1 = client.get(f"/api/sites/{site_id}/floorplan", headers=MGR)
    ts, ms = client.get("/api/sites", headers=TECH), client.get("/api/sites", headers=MGR)
    check(
        "역할 무관 읽기 — technician == manager (바이트 동일, 403 없음)",
        t1.status_code == m1.status_code == ts.status_code == ms.status_code == 200
        and canon(t1.json()) == canon(m1.json())
        and canon(ts.json()) == canon(ms.json()),
        f"floorplan {t1.status_code}/{m1.status_code} · sites {ts.status_code}/{ms.status_code} · "
        f"본문 동일={canon(t1.json()) == canon(m1.json())}",
    )

    # ⑨ 쓰기 메서드 없음 + 무저장
    writes = {
        m: getattr(client, m)(f"/api/sites/{site_id}/floorplan", headers=MGR).status_code
        for m in ("post", "put", "delete")
    }
    writes["post /api/sites"] = client.post("/api/sites", headers=MGR).status_code
    after = counts(dsn)
    check(
        "쓰기 메서드 없음(405) · 호출 전후 행 수 동일",
        all(v == 405 for v in writes.values()) and before == after and before["sites"] > 0,
        f"{writes} · 전 {before} · 후 {after}",
    )

    # ⑩ equipment 에 D158 컬럼이 없다 (D158 ⓐ) — 양성 축: 컬럼을 실제로 읽었는가
    check(
        "equipment 컬럼 6개 그대로 (site_id·zone_id·좌표 추가 없음, D158 ⓐ)",
        eq_cols == EQUIPMENT_COLUMNS,
        f"스캔 {len(eq_cols)}개 · 초과 {sorted(eq_cols - EQUIPMENT_COLUMNS) or '없음'} · "
        f"누락 {sorted(EQUIPMENT_COLUMNS - eq_cols) or '없음'}",
    )

    # ⑪ 콘솔 드롭다운 원천(/api/equipment)에 HV600 이 나온다 — 평면도 클릭의 착지점
    lst = client.get("/api/equipment", headers=TECH).json()["items"]
    hv_list = sorted(i["equipment_id"] for i in lst if i["model"] == "HV600")
    check(
        "GET /api/equipment 에 HV600 2행 (진단 콘솔 설비 선택기)",
        hv_list == sorted(x[0] for x in HV600_EQUIPMENT) and len(lst) == len(db_ids),
        f"목록 {len(lst)}대 · HV600 {hv_list}",
    )

    # ⑫ DB 행이 데이터 정본(data/site_layout.py)과 일치 — 공유 DB 드리프트 감지
    with psycopg.connect(dsn) as con:
        db_sites = [tuple(r) for r in con.execute("SELECT * FROM sites ORDER BY 1")]
        db_zones = [tuple(r) for r in con.execute("SELECT * FROM zones ORDER BY 1")]
        db_locs = [tuple(r) for r in con.execute("SELECT * FROM equipment_locations ORDER BY 1")]
    check(
        "DB 사업장 계층 == data/site_layout.py 상수",
        db_sites == sorted(SITES) and db_zones == sorted(ZONES) and db_locs == sorted(EQUIPMENT_LOCATIONS),
        f"sites {len(db_sites)}/{len(SITES)} · zones {len(db_zones)}/{len(ZONES)} · "
        f"locations {len(db_locs)}/{len(EQUIPMENT_LOCATIONS)} · 일치 "
        f"{(db_sites == sorted(SITES), db_zones == sorted(ZONES), db_locs == sorted(EQUIPMENT_LOCATIONS))}",
    )


def check_migration_idempotent(dsn: str) -> None:
    """⑬ 마이그레이션 DDL 블록을 이미 테이블이 있는 스키마에 두 번 더 실행 — 오류 없이 무변화."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import migrate_d158_sites as mig  # noqa: PLC0415

    block = mig.ddl_block()
    n_stmts = sum(1 for s in block.split(";") if "CREATE" in s.upper())
    before = counts(dsn)
    err = None
    try:
        with psycopg.connect(dsn) as con:
            con.execute(block)
            con.execute(block)
            con.commit()
    except psycopg.Error as exc:
        err = f"{type(exc).__name__}: {exc}"
    after = counts(dsn)
    check(
        "마이그레이션 DDL 블록 2회 재실행 — 오류 없음 · 행 수 무변화",
        err is None and n_stmts == 5 and before == after,
        f"CREATE 문 {n_stmts}개 · 오류 {err or '없음'} · 행 수 {'동일' if before == after else f'{before}→{after}'}",
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    print("D158 사업장 평면도 계약 — 형상·전수 위치·구역 포함·HV600 공조동·역할 무관·읽기 전용 (격리 스키마)\n")

    schema, dsn = pg_isolation.create_isolated_schema("site_floorplan")
    try:
        import backend.db as bdb  # noqa: PLC0415

        bdb.DB_PATH = dsn  # TestClient 는 같은 프로세스 — read_only() 도 호출 시점에 이 값을 읽는다
        os.environ["MAINTQ_MCP_AUTOSTART"] = "0"  # 평면도는 MCP 와 무관하다
        from fastapi.testclient import TestClient  # noqa: PLC0415

        from backend.main import app  # noqa: PLC0415

        with TestClient(app) as client:
            run(client, dsn)
        check_migration_idempotent(dsn)
    finally:
        pg_isolation.drop_isolated_schema(schema)

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 40))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 40))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건:\n  - " + "\n  - ".join(failed))
    print(f"\n통과 ({len(results)}건) — 전수 위치·구역 포함·HV600 공조동·목업 표시·역할 무관·무저장·equipment 컬럼 불변·DDL 멱등")


if __name__ == "__main__":
    main()
