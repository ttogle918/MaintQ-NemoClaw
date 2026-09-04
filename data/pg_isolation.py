# -*- coding: utf-8 -*-
"""스파이크가 공유 Postgres 를 오염시키지 않고 격리된 사본에서 돌 수 있게 하는 헬퍼
(Sprint 16 MQ-1614).

SQLite 시절 스파이크들은 `shutil.copy2(SOURCE_DB, tmp)` 로 파일 전체를 복제해 격리를
얻고, MCP 서브프로세스 env 의 `MAINTQ_DB` 로 그 사본 경로를 주입했다. `backend/db.py`·
`mcp_server/db.py` 가 Postgres 전용으로 바뀌면서 `MAINTQ_DB` 는 더 이상 읽히지 않고
`DATABASE_URL` 하나로 고정된다 — 이 상태로 스파이크를 그냥 돌리면 서브프로세스가
`os.environ` 을 상속해 **공유 Postgres DB 에 테스트 픽스처를 그대로 써버린다.**

이 모듈은 그 격리를 Postgres 스키마 단위로 재현한다: 매 호출마다 새 스키마를 만들고
그 안에 스키마 DDL·D10 가드·현재 `public` 스키마의 시드 데이터를 복제한 뒤,
`search_path` 를 그 스키마로 고정한 DATABASE_URL 을 돌려준다. 스파이크는 그 DSN 을
MCP 서브프로세스의 `DATABASE_URL` 로 주입하면 된다(과거 `MAINTQ_DB` 자리를 대신한다).
스파이크가 SQLite 사본에 하던 추가 준비(임시 컬럼 추가, 검증용 행 삽입 등)는 돌아온
DSN 으로 커넥션을 열어 그대로 실행하면 된다 — `dbcompat.connect()` 로 열면 `?`
플레이스홀더 등 기존 코드 그대로 쓸 수 있다.
"""

from __future__ import annotations

import os
import random
import string
import time
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import psycopg

from data.dbcompat import CompatCursor, sqlite_row_factory

ROOT = Path(__file__).resolve().parent.parent
_SCHEMA_SQL = (ROOT / "scripts" / "postgres_schema.sql").read_text(encoding="utf-8")
_GUARDS_SQL = (ROOT / "scripts" / "postgres_guards.sql").read_text(encoding="utf-8")

BASE_DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# FK 의존 순서 — scripts/migrate_data.py 의 테이블 순서와 같다.
_CLONE_TABLES = [
    "users", "parts", "suppliers", "supplier_parts", "inventory", "part_alternatives",
    "assets", "equipment", "error_history", "rules", "law_refs", "partner_links",
    "part_lifecycle_mock", "residual_curve", "deadlines", "incidents",
    "ownership_checks", "risk_profile", "error_codes",
    "po_drafts", "decisions", "repair_records", "flags", "traces",
    # `manual_chunks`(§24, D117)는 오래 이 목록에서 빠져 있었다 — 테이블은 `_SCHEMA_SQL` 로
    # 만들어지므로 **에러 없이 조용히 0행**이 됐다. public 도 0행이던 동안은 차이가 없었지만,
    # 코퍼스를 임베딩한 뒤에는 격리 스파이크만 dense 결과가 비고 그게 "실패"가 아니라
    # "검색 결과 없음"으로 보인다(알아채기 어려운 종류). 미리 막는다.
    "manual_chunks",
]


def _schema_dsn(schema: str) -> str:
    parts = urlsplit(BASE_DATABASE_URL)
    q = dict(parse_qsl(parts.query))
    q["options"] = f"-c search_path={schema},public"
    # libpq 는 query 안 공백을 `%20` 으로만 인식한다 — urlencode 기본값(`+`)은 그대로
    # "unrecognized configuration parameter" 로 거부당한다. quote_via=quote 로 강제한다.
    query = urlencode(q, quote_via=quote)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def create_isolated_schema(label: str = "spike", clone_data: bool = True) -> tuple[str, str]:
    """새 스키마를 만들고 스키마 DDL·가드를 적용한다.

    `clone_data=True`(기본)면 `public` 의 현재 데이터도 복제한다 — 대부분의 스파이크가
    쓰는 형태(기존 시드 데이터 위에서 시나리오를 재현). `clone_data=False` 는
    `data/seed.py` 의 `SCHEMA` 를 갓 적용한 **빈 DB** 가 필요한 스파이크용이다
    (trace_persist.py 처럼 스키마만 필요하거나, D50 "0행 카탈로그" 음성 테스트처럼
    특정 테이블이 확실히 0행이어야 하는 경우 — 복제하면 public 의 기존 행이 섞여 든다).

    반환: (schema_name, 그 스키마로 search_path 가 고정된 DATABASE_URL).
    호출부가 다 쓴 뒤에는 `drop_isolated_schema(schema_name)` 으로 정리해야 한다.
    """
    if not BASE_DATABASE_URL:
        raise RuntimeError("DATABASE_URL 미설정 — Postgres 격리 스키마는 Postgres 타겟에서만 쓴다")

    label = "".join(c if c.isalnum() else "_" for c in label)
    suffix = f"{int(time.time())}_{''.join(random.choices(string.ascii_lowercase, k=6))}"
    schema = f"{label}_{suffix}"[:63]  # Postgres identifier 63자 제한

    con = psycopg.connect(BASE_DATABASE_URL, row_factory=sqlite_row_factory, cursor_factory=CompatCursor)
    try:
        con.execute(f'CREATE SCHEMA "{schema}"')
        # `public` 을 반드시 포함한다 — pgvector(D117) 확장이 이미 `public` 에 설치돼 있어
        # `_SCHEMA_SQL` 의 `CREATE EXTENSION IF NOT EXISTS vector` 가 조용히 스킵되고,
        # `manual_chunks.embedding vector(2048)` 컬럼 DDL 이 이 스키마만으로는 `vector`
        # 타입을 찾지 못해 "type \"vector\" does not exist" 로 죽는다(실측: A2A pytest
        # 8파일군에서 fixture 단계 52건 ERROR).
        con.execute(f'SET search_path TO "{schema}", public')
        con.execute(_SCHEMA_SQL)
        con.execute(_GUARDS_SQL)
        if not clone_data:
            con.commit()
            return schema, _schema_dsn(schema)
        for table in _CLONE_TABLES:
            con.execute(f'INSERT INTO "{schema}".{table} SELECT * FROM public.{table}')
        # BIGSERIAL PK 인 테이블(traces·error_history·flags·deadlines·incidents·
        # ownership_checks)은 값을 그대로 복사해도 그 테이블의 시퀀스 카운터는 안 따라온다
        # — 새로 INSERT 하면 시퀀스가 1부터 다시 새 값을 내놓다가 방금 복사해 온 기존
        # id 와 충돌한다(UniqueViolation). 복제한 데이터의 현재 MAX 값으로 맞춰준다.
        for table in _CLONE_TABLES:
            cur = con.execute(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema=%s AND table_name=%s AND column_default LIKE 'nextval(%%'",
                (schema, table),
            )
            for (col,) in cur.fetchall():
                con.execute(
                    f'SELECT setval(pg_get_serial_sequence(%s, %s),'
                    f' COALESCE((SELECT MAX("{col}") FROM "{schema}".{table}), 0) + 1, false)',
                    (f"{schema}.{table}", col),
                )
        con.commit()
    except Exception:
        con.rollback()
        con.close()
        # 부분 생성된 스키마가 남지 않게 정리한다(별도 커넥션 — 위 커넥션은 이미 rollback됨).
        drop_isolated_schema(schema)
        raise
    else:
        con.close()

    return schema, _schema_dsn(schema)


def schema_from_dsn(dsn: str) -> str | None:
    """`create_isolated_schema()` 가 만든 DSN 에서 스키마 이름을 되돌린다(정리용)."""
    q = dict(parse_qsl(urlsplit(dsn).query))
    options = q.get("options", "")
    prefix = "-c search_path="
    if options.startswith(prefix):
        return options[len(prefix):].split(",", 1)[0]
    return None


def drop_isolated_schema(schema: str) -> None:
    if not BASE_DATABASE_URL or not schema:
        return
    con = psycopg.connect(BASE_DATABASE_URL)
    try:
        con.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        con.commit()
    finally:
        con.close()


def drop_schema_from_dsn(dsn: str) -> None:
    """`create_isolated_schema()` 가 돌려준 DSN 하나만 들고 있을 때(스키마 이름을 따로
    기억하지 않은 경우) 정리하는 편의 함수 — `mcp_db.DB_PATH = dsn` 처럼 DSN 자체를
    `db` 로 들고 다니는 스파이크들이 쓴다."""
    schema = schema_from_dsn(dsn)
    if schema:
        drop_isolated_schema(schema)
