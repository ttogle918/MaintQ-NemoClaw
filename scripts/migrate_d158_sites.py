#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""D158 사업장→구역→설비 위치 + HV600 설비 2행 — 공유 DB 멱등 마이그레이션 (Sprint 19 MQ-1914).

⛔ **왜 재시드가 아닌가 (H9).** `data/seed.py` 는 `DROP SCHEMA public CASCADE` 로 시작한다 —
공유 DB 에 쌓인 되돌릴 수 없는 사람 작업(HV600 승격 8건 · 안전 문구 SC-14 승인 · LLM 정규화
261행)을 지운다. 그래서 공유 DB 에는 이 스크립트만 쓴다.

하는 일 (한 트랜잭션):
  1. `scripts/postgres_schema.sql` 의 `-- BEGIN D158` ~ `-- END D158` 블록을 그대로 실행
     (`CREATE TABLE IF NOT EXISTS` — DDL 정본이 한 곳이다)
  2. `data/site_layout.py` 상수를 `INSERT … ON CONFLICT DO NOTHING` 으로 적재
     (sites → zones → equipment(HV600 2행) → equipment_locations, FK 순서)

⛔ 기존 행을 UPDATE·DELETE 하지 않는다. 이미 있는 행이 상수와 **다르면** 고치지 않고
   `[드리프트]` 로 보고만 한다(사람 판단 — 자동 교정은 누가 무엇을 바꿨는지 지운다).
두 번째 실행은 모든 INSERT 가 0행이어야 한다 — 그게 멱등의 증거다(출력의 `inserted` 열).

실행:
    DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" \
        uv run python scripts/migrate_d158_sites.py
    ... --dry-run    # 트랜잭션을 끝에서 ROLLBACK (무엇이 들어갈지만 본다)
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import re  # noqa: E402

import psycopg  # noqa: E402

from data.site_layout import (  # noqa: E402
    EQUIPMENT_LOCATIONS,
    HV600_EQUIPMENT,
    SITES,
    ZONES,
)

SCHEMA_SQL = ROOT / "scripts" / "postgres_schema.sql"
BEGIN, END = "-- BEGIN D158 site layout", "-- END D158 site layout"

TABLES = ("sites", "zones", "equipment", "equipment_locations")


def ddl_block() -> str:
    text = SCHEMA_SQL.read_text(encoding="utf-8")
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise SystemExit(f"[중단] {SCHEMA_SQL.name} 에 D158 표식이 정확히 1쌍이어야 합니다")
    block = text.split(BEGIN, 1)[1].split(END, 1)[0]
    # 공유 DB 에서 도는 DDL 이다 — **CREATE … IF NOT EXISTS 만** 허용하는 화이트리스트로 막는다.
    # 주석 줄을 먼저 걷어낸 뒤 판정한다(예전 판정은 주석으로 시작하는 문장을 통째로 건너뛰어
    # `-- 메모\nDELETE …` 가 통과했다 — 2026-09-25 Stage 5 리뷰 지적)
    code = "\n".join(line for line in block.splitlines() if not line.strip().startswith("--"))
    stmts = [s.strip() for s in code.split(";") if s.strip()]
    allowed = re.compile(r"^CREATE\s+(TABLE|INDEX|UNIQUE\s+INDEX)\s+IF\s+NOT\s+EXISTS\b", re.IGNORECASE)
    bad = [s.splitlines()[0] for s in stmts if not allowed.match(s)]
    if bad or not stmts:
        raise SystemExit(f"[중단] D158 블록에 허용되지 않은 문장: {bad or '(블록 비어 있음)'}")
    return code


def counts(con: psycopg.Connection) -> dict[str, int | None]:
    out: dict[str, int | None] = {}
    for t in TABLES:
        exists = con.execute("SELECT to_regclass(%s)", (f"public.{t}",)).fetchone()[0]
        out[t] = con.execute(f"SELECT count(*) FROM public.{t}").fetchone()[0] if exists else None  # noqa: S608
    return out


def invariants(con: psycopg.Connection) -> dict[str, object]:
    """이 마이그레이션이 **건드리면 안 되는** 것들 — 전후 동일해야 한다."""
    q = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    blob = "\n".join(
        "|".join("" if v is None else str(v) for v in r)
        for r in con.execute(
            "SELECT equipment_id, line_id, model, installed_at, location, asset_id FROM public.equipment"
            " WHERE equipment_id NOT IN (%s) ORDER BY equipment_id"
            % ",".join(f"'{e[0]}'" for e in HV600_EQUIPMENT)
        )
    )
    return {
        "기존 설비 지문(HV600 2행 제외)": hashlib.sha256(blob.encode()).hexdigest()[:16],
        "onboarding_promotions": q("SELECT count(*) FROM public.onboarding_promotions"),
        "안전 문구 approved": q(
            "SELECT count(*) FROM public.onboarding_safety_candidates WHERE state='approved'"
        ),
        "onboarding_normalizations": q("SELECT count(*) FROM public.onboarding_normalizations"),
        "error_codes": q("SELECT count(*) FROM public.error_codes"),
        "error_history": q("SELECT count(*) FROM public.error_history"),
        "inventory": q("SELECT count(*) FROM public.inventory"),
        "assets": q("SELECT count(*) FROM public.assets"),
    }


def insert(con: psycopg.Connection, sql: str, rows: list[tuple]) -> int:
    n = 0
    for r in rows:
        n += con.execute(sql, r).rowcount
    return n


def drift(con: psycopg.Connection) -> list[str]:
    """이미 있던 행이 상수와 다른가 — 고치지 않고 보고만 한다."""
    out: list[str] = []
    checks = [
        ("sites", "SELECT site_id, name, is_mock, width, height FROM public.sites WHERE site_id=%s", SITES),
        ("zones", "SELECT zone_id, site_id, name, kind, x, y, w, h FROM public.zones WHERE zone_id=%s", ZONES),
        (
            "equipment",
            "SELECT equipment_id, line_id, model, installed_at::text, location, asset_id"
            " FROM public.equipment WHERE equipment_id=%s",
            HV600_EQUIPMENT,
        ),
        (
            "equipment_locations",
            "SELECT equipment_id, zone_id, x, y FROM public.equipment_locations WHERE equipment_id=%s",
            EQUIPMENT_LOCATIONS,
        ),
    ]
    for table, sql, rows in checks:
        for expected in rows:
            got = con.execute(sql, (expected[0],)).fetchone()
            if got is not None and tuple(got) != tuple(expected):
                out.append(f"{table}:{expected[0]} DB={tuple(got)} 상수={tuple(expected)}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="D158 사업장 계층 멱등 마이그레이션 (공유 DB)")
    ap.add_argument("--dry-run", action="store_true", help="끝에서 ROLLBACK")
    args = ap.parse_args()

    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn.startswith("postgresql://"):
        raise SystemExit("[중단] DATABASE_URL(Postgres DSN)이 필요합니다 — .env 에서 실어 실행하세요")

    block = ddl_block()
    with psycopg.connect(dsn) as con:
        con.execute("SET search_path TO public")
        before = counts(con)
        inv_before = invariants(con)

        con.execute(block)
        ins = {
            "sites": insert(
                con,
                "INSERT INTO sites (site_id, name, is_mock, width, height) VALUES (%s,%s,%s,%s,%s)"
                " ON CONFLICT (site_id) DO NOTHING",
                SITES,
            ),
            "zones": insert(
                con,
                "INSERT INTO zones (zone_id, site_id, name, kind, x, y, w, h)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (zone_id) DO NOTHING",
                ZONES,
            ),
            "equipment": insert(
                con,
                "INSERT INTO equipment (equipment_id, line_id, model, installed_at, location, asset_id)"
                " VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (equipment_id) DO NOTHING",
                HV600_EQUIPMENT,
            ),
            "equipment_locations": insert(
                con,
                "INSERT INTO equipment_locations (equipment_id, zone_id, x, y) VALUES (%s,%s,%s,%s)"
                " ON CONFLICT (equipment_id) DO NOTHING",
                EQUIPMENT_LOCATIONS,
            ),
        }
        after = counts(con)
        inv_after = invariants(con)
        drifts = drift(con)

        if inv_before != inv_after:
            con.rollback()
            raise SystemExit(f"[중단·롤백] 불변 항목이 바뀌었다: {inv_before} → {inv_after}")
        if args.dry_run:
            con.rollback()
        else:
            con.commit()

    print(f"[D158 마이그레이션] {'DRY-RUN (롤백)' if args.dry_run else '커밋'} — {dsn.split('@')[-1]}")
    print(f"  {'table':<22}{'before':>8}{'inserted':>10}{'after':>8}")
    for t in TABLES:
        b = "없음" if before[t] is None else before[t]
        print(f"  {t:<22}{b!s:>8}{ins[t]:>10}{after[t]!s:>8}")
    print("  불변 항목(전후 동일):")
    for k, v in inv_after.items():
        print(f"    {k}: {v}")
    if drifts:
        print(f"  [드리프트] {len(drifts)}건 — 고치지 않았다(사람 판단):")
        for d in drifts:
            print(f"    {d}")
    else:
        print("  드리프트 0건 — 기존 행이 data/site_layout.py 상수와 일치")
    print(f"  멱등 판정: 이번 실행 INSERT 합계 {sum(ins.values())}행")


if __name__ == "__main__":
    main()
