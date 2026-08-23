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

def convert_datetime(sql):
    """DATETIME → TIMESTAMP (Postgres에는 DATETIME 타입이 없다)."""
    return re.sub(r'\bDATETIME\b', 'TIMESTAMP', sql, flags=re.IGNORECASE)

def convert_boolean_default(sql):
    """BOOLEAN 컬럼의 정수 리터럴 DEFAULT(0/1) → FALSE/TRUE.

    Postgres는 BOOLEAN 컬럼의 DEFAULT 절에 정수 리터럴을 암묵 변환하지 않는다
    (SQLite는 BOOLEAN 을 별칭으로만 취급해 0/1 을 그대로 받아준다).
    같은 줄 안에서 BOOLEAN 이 DEFAULT 보다 먼저 나올 때만 치환한다.
    """
    def repl(m):
        between = m.group(1)
        value = m.group(2)
        replacement = 'TRUE' if value == '1' else 'FALSE'
        return f'BOOLEAN{between}DEFAULT {replacement}'

    return re.sub(
        r'BOOLEAN([^,\n]*?)DEFAULT (0|1)\b',
        repl,
        sql
    )

def convert_boolean_comparisons(sql):
    """BOOLEAN 컬럼을 `col = 0` / `col = 1` 로 비교하는 CHECK 식을 FALSE/TRUE 비교로 바꾼다.

    DEFAULT 절 밖(CHECK 제약 등)에서도 같은 컬럼이 정수 리터럴과 비교되면
    Postgres 는 `operator does not exist: boolean = integer` 로 거부한다.
    먼저 BOOLEAN 으로 선언된 컬럼명을 모두 모은 뒤, 그 이름이 나오는 모든
    `= 0` / `= 1` 비교를 치환한다 — 컬럼 하나만 하드코딩하지 않기 위해서다.
    """
    bool_cols = set(re.findall(r'(\w+)\s+BOOLEAN\b', sql))
    for col in bool_cols:
        sql = re.sub(rf'\b{re.escape(col)}\s*=\s*0\b', f'{col} = FALSE', sql)
        sql = re.sub(rf'\b{re.escape(col)}\s*=\s*1\b', f'{col} = TRUE', sql)
    return sql

def convert_is_literal(sql):
    """`col IS 'LITERAL'` → `col IS NOT DISTINCT FROM 'LITERAL'`.

    SQLite 의 IS 는 NULL-safe 비교이며 임의의 피연산자에 쓸 수 있다 — 한쪽이 NULL 이어도
    항상 TRUE/FALSE 를 돌려준다(NULL 을 절대 안 돌려준다). Postgres 의 IS 는 NULL/TRUE/
    FALSE/UNKNOWN 전용이라 문자열 리터럴에는 못 쓴다. `= 'LITERAL'` 로 바꾸면 얼핏 맞아
    보이지만 `NULL = 'LITERAL'` 은 NULL 을 반환하고, CHECK 제약은 NULL 을 "통과"로 취급한다
    — partner_links 의 `external_ref IS NULL OR link_state IS 'LINKED'` 처럼 NULL 을
    **차단**하려고 IS 를 쓴 CHECK 가 `=` 로 바뀌면 조용히 뚫린다(D96-ⓐ, 실사고 MQ-1614:
    `link_state=NULL, external_ref='X'` INSERT 가 거부돼야 하는데 통과해버렸다).
    `IS NOT DISTINCT FROM` 이 Postgres 의 진짜 null-safe 비교 연산자다 — SQLite `IS` 와
    항상 같은 TRUE/FALSE 를 돌려준다. `IS NULL`/`IS NOT NULL` 은 뒤에 따옴표가 없으므로
    이 정규식에 걸리지 않는다.
    """
    return re.sub(r"\bIS\s+'([^']*)'", r"IS NOT DISTINCT FROM '\1'", sql)

def convert_reserved_identifiers(sql):
    """Postgres 예약어와 충돌하는 컬럼명을 큰따옴표로 감싼다.

    `trigger` 는 law_refs.rules 스키마에서 컬럼명으로 쓰이는데 Postgres 예약어라
    큰따옴표 없이는 파서가 거부한다.
    """
    sql = re.sub(r'(?<![\w"])trigger(?![\w"])', '"trigger"', sql)
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

    # 5. DATETIME → TIMESTAMP
    result = convert_datetime(result)

    # 6. BOOLEAN DEFAULT 0/1 → FALSE/TRUE
    result = convert_boolean_default(result)

    # 6b. BOOLEAN 컬럼의 `col = 0/1` 비교 → FALSE/TRUE (DEFAULT 절 밖, 예: CHECK)
    result = convert_boolean_comparisons(result)

    # 7. `col IS 'literal'` → `col = 'literal'`
    result = convert_is_literal(result)

    # 8. 예약어 컬럼명 인용
    result = convert_reserved_identifiers(result)

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
