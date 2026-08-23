#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SQLite DDL을 Postgres 호환으로 변환하는 스크립트."""

import re
import sys

def convert_glob_to_regex(match):
    """GLOB 패턴을 Postgres 정규식으로 변환.

    예시:
    - GLOB '*[^A-Z0-9_]*' → ~ '^[A-Z0-9_]+$'
    - GLOB '*[^a-z0-9-]*' → ~ '^[a-z0-9-]+$'
    """
    pattern = match.group(1)

    # 문제: SQLite GLOB은 와일드카드 문법이 다르다
    # '*[^X]*' = "X에 없는 문자를 포함" → 정규식은 '^[X]+$' (X만 포함)
    # 변환: [^A-Z0-9_] → [A-Z0-9_]만 허용

    if "*[^" in pattern and "]*" in pattern:
        # *[^...]*  형태 추출
        inner = re.search(r"\[\^([^\]]+)\]", pattern)
        if inner:
            chars = inner.group(1)
            return f"~ '^[{chars}]+$'"

    # 기본: 문자 그대로
    return f"GLOB '{pattern}'"

def convert_json_valid(sql):
    """json_valid() → Postgres 호환."""
    # json_valid(col) → (col::jsonb IS NOT NULL)
    sql = re.sub(
        r'json_valid\((\w+)\)',
        r'(\1::jsonb IS NOT NULL)',
        sql
    )
    return sql

def convert_integer_pk(sql):
    """INTEGER PRIMARY KEY → BIGSERIAL PRIMARY KEY."""
    # id INTEGER PRIMARY KEY → id BIGSERIAL PRIMARY KEY
    sql = re.sub(
        r'(\w+)\s+INTEGER\s+PRIMARY\s+KEY',
        r'\1 BIGSERIAL PRIMARY KEY',
        sql,
        flags=re.IGNORECASE
    )
    return sql

def convert_ddl(sqlite_ddl: str) -> str:
    """SQLite DDL 전체를 Postgres로 변환."""
    result = sqlite_ddl

    # 1. GLOB 패턴 변환
    result = re.sub(
        r"NOT GLOB '([^']+)'",
        lambda m: convert_glob_to_regex(m),
        result
    )

    # 2. json_valid 변환
    result = convert_json_valid(result)

    # 3. INTEGER PRIMARY KEY 변환
    result = convert_integer_pk(result)

    # 4. PRAGMA 제거 (DDL에는 없음)

    return result

if __name__ == "__main__":
    from pathlib import Path

    # data/seed.py에서 SCHEMA 추출
    seed_py = Path(__file__).parent.parent / "data" / "seed.py"
    content = seed_py.read_text(encoding="utf-8")

    # SCHEMA = """ ... """ 블록 추출
    match = re.search(r'SCHEMA = """(.*?)"""', content, re.DOTALL)
    if not match:
        print("ERROR: SCHEMA not found in data/seed.py", file=sys.stderr)
        sys.exit(1)

    sqlite_ddl = match.group(1)
    postgres_ddl = convert_ddl(sqlite_ddl)

    output_path = Path(__file__).parent / "postgres_schema.sql"
    output_path.write_text(postgres_ddl, encoding="utf-8")

    print(f"OK Postgres DDL saved to {output_path}")
    print(f"  Row count: {len(postgres_ddl.splitlines())}")
