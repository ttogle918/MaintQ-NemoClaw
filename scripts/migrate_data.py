#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SQLite → Postgres 데이터 마이그레이션 스크립트.

사용:
    uv run python scripts/migrate_data.py \
        --sqlite data/maintq.db \
        --postgres postgresql://user:pw@host/maintq \
        --include-error-codes  # error_codes 포함 (D33 승인 필수)
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import psycopg


# 마이그레이션할 테이블 (순서 중요: FK 때문에)
TABLES_TO_MIGRATE = [
    "users",
    "parts",
    "suppliers",
    "supplier_parts",
    "inventory",
    "part_alternatives",
    "assets",
    "equipment",
    "error_history",
    "rules",
    "law_refs",
    "partner_links",
    "part_lifecycle_mock",
    "residual_curve",
    "deadlines",
    "incidents",
    "ownership_checks",
    "risk_profile",
]

# 선택적: error_codes (--include-error-codes 플래그)
OPTIONAL_TABLES = ["error_codes"]

# 빈 상태로 시작 (INSERT 가능하지만 시드는 넣지 않음)
EMPTY_TABLES = ["po_drafts", "decisions", "repair_records", "flags", "traces"]


def _boolean_columns(pg_con, table_name):
    """Postgres 쪽 대상 테이블에서 boolean 타입인 컬럼명 집합을 조회한다.

    SQLite 는 BOOLEAN 을 그냥 INTEGER(0/1)로 저장한다. psycopg 파라미터 바인딩은
    Python int → Postgres boolean 을 암묵 변환하지 않으므로("column is of type
    boolean but expression is of type smallint"), INSERT 전에 그 컬럼만 명시적으로
    Python bool 로 캐스팅해야 한다.
    """
    cur = pg_con.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = %s AND data_type = 'boolean'",
        (table_name,),
    )
    return {row[0] for row in cur.fetchall()}


def migrate_table(sqlite_con, pg_con, table_name):
    """SQLite의 한 테이블을 Postgres로 마이그레이션."""

    # 1. SQLite에서 스키마 조회
    cursor = sqlite_con.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]

    # 2. SQLite에서 데이터 조회
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()

    if not rows:
        print(f"  {table_name}: 0행 (스킵)")
        return

    # 2b. SQLite 의 0/1(int) → Postgres boolean 컬럼용 Python bool 로 변환
    bool_cols = _boolean_columns(pg_con, table_name)
    if bool_cols:
        bool_idx = [i for i, c in enumerate(columns) if c in bool_cols]
        converted = []
        for row in rows:
            row = list(row)
            for i in bool_idx:
                if row[i] is not None:
                    row[i] = bool(row[i])
            converted.append(tuple(row))
        rows = converted

    # 3. Postgres에 INSERT
    col_names = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    insert_sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"

    cursor = pg_con.cursor()
    cursor.executemany(insert_sql, rows)
    pg_con.commit()

    print(f"  {table_name}: {len(rows)}행 마이그레이션 완료")


def main():
    parser = argparse.ArgumentParser(description="SQLite → Postgres 마이그레이션")
    parser.add_argument("--sqlite", default="data/maintq.db", help="SQLite DB 경로")
    parser.add_argument("--postgres", required=True, help="Postgres 연결 문자열")
    parser.add_argument("--include-error-codes", action="store_true", help="error_codes 포함 (D33 승인 필수)")

    args = parser.parse_args()

    sqlite_path = Path(args.sqlite)
    if not sqlite_path.exists():
        print(f"ERROR: SQLite DB가 없습니다: {sqlite_path}", file=sys.stderr)
        sys.exit(1)

    print("📊 데이터 마이그레이션 시작")
    print(f"  SQLite: {sqlite_path}")
    print(f"  Postgres: {args.postgres}")

    # 연결
    sqlite_con = sqlite3.connect(sqlite_path)
    sqlite_con.execute("PRAGMA foreign_keys=ON")

    pg_con = psycopg.connect(args.postgres)

    try:
        # 1. 필수 테이블 마이그레이션
        print("\n✓ 필수 테이블 마이그레이션:")
        for table in TABLES_TO_MIGRATE:
            try:
                migrate_table(sqlite_con, pg_con, table)
            except psycopg.Error as e:
                print(f"  ERROR {table}: {e}", file=sys.stderr)
                pg_con.rollback()

        # 2. 선택적 테이블 (error_codes)
        if args.include_error_codes:
            print("\n✓ 선택적 테이블 (error_codes):")
            try:
                migrate_table(sqlite_con, pg_con, "error_codes")
            except psycopg.Error as e:
                print(f"  ERROR error_codes: {e}", file=sys.stderr)
                pg_con.rollback()
        else:
            print("\n⊘ error_codes: 스킵 (--include-error-codes 플래그 필요, D33 승인 후)")

        # 3. 빈 테이블 (스키마만 생성됨)
        print("\n✓ 빈 상태로 시작하는 테이블:")
        for table in EMPTY_TABLES:
            print(f"  {table}: 스키마 생성됨 (행 0)")

        pg_con.commit()
        print("\n✅ 마이그레이션 완료!")

    finally:
        sqlite_con.close()
        pg_con.close()


if __name__ == "__main__":
    main()
