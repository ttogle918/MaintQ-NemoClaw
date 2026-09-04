# -*- coding: utf-8 -*-
"""sqlite3 DB-API 표면을 유지한 채 `DATABASE_URL` 이 있으면 Postgres(psycopg)로 라우팅하는
얇은 호환 계층 (Sprint 16 MQ-1614 — Postgres 마이그레이션 완성).

배경: `backend/db.py`·`mcp_server/db.py` 는 이미 Postgres 전용으로 전환됐지만, 그 아래
`data/`·`backend/services/`·`mcp_server/tools/`·`spikes/` 45개 파일은 각자 `sqlite3.connect()`
를 직접 부르거나 `sqlite3.Row`/`sqlite3.IntegrityError`/`?` 플레이스홀더/`PRAGMA` 를 쓴다.
파일마다 손으로 다 고치는 대신, 이 모듈의 `connect()` 하나로 연결 지점만 모으고
나머지(플레이스홀더 변환·행 접근·예외 타입·PRAGMA)는 이 계층이 흡수한다 — 호출부 코드는
대부분 그대로 둔다.

`DATABASE_URL` 이 비어 있으면 이 모듈은 진짜 `sqlite3` 를 그대로 돌려준다 — 동작이 하나도
바뀌지 않는다. 설정돼 있을 때만 아래 psycopg 기반 어댑터가 개입한다.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import sqlite3
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from typing import TYPE_CHECKING, TypeAlias

import psycopg

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_POSTGRES = bool(DATABASE_URL)


# ── 타입 별칭 (D129) ─────────────────────────────────────────────────────────
#
# Postgres 전환(D116) 이후에도 코드 전반의 시그니처가 `sqlite3.Connection` /
# `sqlite3.Row` 로 남아 있었다. **런타임에 그런 객체는 오지 않는다** — 실제로 오는 것은
# `psycopg.Connection`(대개) 또는 이 모듈의 `PgConnection`(dbcompat 경유)이고, 행은
# 이 모듈의 `Row` 다.
#
# 힌트가 틀리면 없느니만 못하다. 이 레포는 SQLite/Postgres 혼동으로 이미 여러 번 사고를
# 냈고(`backend/db.py` 의 `Path` 래핑 · `disposal.py` 의 조용한 SQLite 폴백 ·
# `MAINTQ_DB` 를 읽지 않는 서브프로세스), 그때마다 "이게 무슨 커넥션인지"가 쟁점이었다.
#
# ⚠ **예외 타입은 바꾸지 않는다.** `sqlite3.Error`·`sqlite3.IntegrityError` 로 잡는
#   코드는 정상이다 — `_map_exception()` 이 psycopg 예외를 **의도적으로** 그 타입들로
#   되던지기 때문이다(호출부를 그대로 두기 위한 설계). 여기서 손대는 것은 **타입 힌트뿐**이다.
#
# ⚠ **이 이름은 타입 힌트 전용이다 — `isinstance()` 에 쓰면 안 된다.**
#   `sqlite3.Connection` 은 힌트로도 쓰이고 `data/seed.py:create_schema()` 처럼 **런타임
#   분기**로도 쓰였다. 그 둘을 구분하지 않고 일괄 치환했다가 사고가 났다(2026-09-04):
#   런타임 값이 `object` 라 `isinstance(con, DbConnection)` 이 **항상 True** 가 되고,
#   Postgres 타겟에서 SQLite DDL 을 실행해 `NOT GLOB` 문법 오류로 죽었다.
#   **조용히 틀린 분기를 타는 것**이 최악이라, 아래 메타클래스로 그 오용을 **즉시 예외**로
#   바꾼다. 런타임에 커넥션 종류를 봐야 하면 `sqlite3.Connection`/`psycopg.Connection` 을
#   직접 쓸 것.
class _HintOnlyMeta(type):
    def __instancecheck__(cls, obj):  # noqa: D105
        raise TypeError(
            f"{cls.__name__} 은 타입 힌트 전용입니다 — isinstance() 로 쓸 수 없습니다. "
            "런타임 분기가 필요하면 sqlite3.Connection / psycopg.Connection 을 직접 쓰십시오 "
            "(data/seed.py:create_schema 참고)."
        )


if TYPE_CHECKING:
    #: 이 프로젝트에서 "DB 커넥션"으로 통용되는 타입.
    DbConnection: TypeAlias = "psycopg.Connection | PgConnection"
else:
    class DbConnection(metaclass=_HintOnlyMeta):
        """타입 힌트 전용 자리표시자 (런타임 의미 없음)."""

#: 조회 결과 한 행. `row["col"]` 접근을 지원한다(`sqlite_row_factory` 가 만든다).
DbRow: TypeAlias = "Row"


# ────────────────────────────────────────────────────────── 행 접근 (sqlite3.Row 대체)


class Row(tuple):
    """`sqlite3.Row` 대체 — 인덱스·컬럼명 양쪽 접근 + 튜플과의 등가비교(seed.py verify()
    가 `row == (1, 3)` 형태로 비교하는 코드가 많다 — tuple 서브클래스라 그대로 성립한다)."""

    def __new__(cls, values, cols):
        obj = super().__new__(cls, values)
        obj._cols = cols
        return obj

    def __getitem__(self, key):
        if isinstance(key, str):
            return tuple.__getitem__(self, self._cols[key])
        return tuple.__getitem__(self, key)

    def keys(self):
        return list(self._cols.keys())


def _normalize_value(v):
    """SQLite 는 DATE/TIMESTAMP 를 그냥 TEXT 로 저장·반환한다 — 앱 코드 전반이
    `date.fromisoformat(row["acquired_at"])`, `.strftime(...)` 비교처럼 **문자열**이라고
    가정한다. psycopg 는 같은 컬럼을 진짜 `date`/`datetime` 객체로 돌려주므로, SQLite 가
    저장하던 것과 같은 문자열 형태('YYYY-MM-DD' / 'YYYY-MM-DD HH:MM:SS')로 되돌린다.
    """
    if isinstance(v, _dt.datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, _dt.date):
        return v.isoformat()
    return v


def sqlite_row_factory(cursor):
    """psycopg 의 row_factory 프로토콜(커서 → 행 생성 콜러블)에 맞춘 `Row` 팩토리.

    `backend/db.py`·`mcp_server/db.py` 가 이걸 `psycopg.connect(..., row_factory=...)` 에
    바로 물려서 `row["col"]`(sqlite3.Row 관행에 기대는 backend/services/*, mcp_server/tools/*
    다수)와 `row[0]` 양쪽이 psycopg 커넥션에서도 그대로 통하게 한다.
    """
    cols = {d.name: i for i, d in enumerate(cursor.description)} if cursor.description else {}

    def make_row(values):
        return Row([_normalize_value(v) for v in values], cols)

    return make_row


# ────────────────────────────────────────────────────────── SQL 텍스트 변환

_DATETIME_NOW_PARAM = re.compile(r"datetime\('now',\s*\?\)")
_DATETIME_NOW_LITERAL = re.compile(r"datetime\('now',\s*'([^']+)'\)")
_DATETIME_NOW_PAREN = re.compile(r"datetime\('now'\)")
_INSERT_OR_IGNORE = re.compile(r"INSERT OR IGNORE INTO", re.IGNORECASE)
_INSERT_OR_REPLACE = re.compile(r"INSERT OR REPLACE INTO\s+(\w+)", re.IGNORECASE)

# INSERT OR REPLACE 를 쓰는 테이블의 PK — ON CONFLICT 타깃 지정에 필요하다.
# 새 테이블에 이 패턴을 쓰게 되면 여기 추가해야 한다(안 하면 NotImplementedError).
_UPSERT_PK = {
    "error_codes": ("model", "code"),
}

# scripts/postgres_schema.sql 기준 BOOLEAN 컬럼 전체 — 이름이 테이블 간에 겹치지 않아
# 테이블 문맥 없이도 SQL 텍스트에서 안전하게 치환할 수 있다(seed.py verify() 등이
# `compat_confirmed=1` 처럼 정수 리터럴로 비교하는 WHERE/CHECK 절 다수를 이걸로 커버한다).
_BOOLEAN_COLUMN_NAMES = (
    "active",
    "tax_credit_applied",
    "has_lien",
    "insured",
    "safety_inspection_target",
    "parts_eol_flag",
    "discontinued",
    "compat_confirmed",
    "resolved",
    "requires_expert_review",
    "override",
)
_BOOL_COMPARE = re.compile(
    r"\b(" + "|".join(_BOOLEAN_COLUMN_NAMES) + r")\s*(=|<>|!=)\s*(0|1)\b"
)


def _bool_compare_sub(m: re.Match) -> str:
    return f"{m.group(1)}{m.group(2)}{'TRUE' if m.group(3) == '1' else 'FALSE'}"


_JSON_ARRAY_LENGTH = re.compile(r"json_array_length\(([^)]+)\)", re.IGNORECASE)

_INSERT_LITERAL_VALUES = re.compile(
    r"^\s*INSERT INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES\s*\((.*)\)\s*;?\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _split_sql_values(text: str) -> list[str]:
    """콤마로 구분된 SQL 리터럴 값을 따옴표 안 콤마는 건드리지 않고 나눈다."""
    parts, buf, in_str = [], [], False
    for ch in text:
        if ch == "'":
            in_str = not in_str
            buf.append(ch)
        elif ch == "," and not in_str:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf).strip())
    return parts


def _cast_insert_literal_bools(sql: str) -> str:
    """파라미터 바인딩이 아니라 `VALUES ('a','b',1)` 처럼 리터럴을 f-string 으로 박아 넣는
    INSERT(예: seed.py verify() 의 SAVEPOINT 프로브들)의 boolean 컬럼 위치 0/1 을 캐스팅한다.
    `_cast_bool_params` 는 바인딩 파라미터만 다루므로 이 경로를 못 본다."""
    m = _INSERT_LITERAL_VALUES.match(sql)
    if not m:
        return sql
    table, cols_text, values_text = m.group(1), m.group(2), m.group(3)
    cols = [c.strip() for c in cols_text.split(",")]
    values = _split_sql_values(values_text)
    if len(values) != len(cols):
        return sql
    changed = False
    for i, c in enumerate(cols):
        if c in _BOOLEAN_COLUMN_NAMES and values[i] in ("0", "1"):
            values[i] = "TRUE" if values[i] == "1" else "FALSE"
            changed = True
    if not changed:
        return sql
    return f"INSERT INTO {table} ({cols_text}) VALUES ({', '.join(values)})"


def translate_sql(sql: str) -> str:
    """SQLite 전용 구문을 Postgres 호환으로 바꾼다. SQLite 타겟이면 그대로 돌려준다."""
    if not USE_POSTGRES:
        return sql

    # datetime('now', ?) / datetime('now','-30 day') / datetime('now')
    sql = _DATETIME_NOW_PARAM.sub("(NOW() + (?)::interval)", sql)
    sql = _DATETIME_NOW_LITERAL.sub(lambda m: f"(NOW() + INTERVAL '{m.group(1)}')", sql)
    sql = _DATETIME_NOW_PAREN.sub("NOW()", sql)
    sql = _BOOL_COMPARE.sub(_bool_compare_sub, sql)
    sql = _cast_insert_literal_bools(sql)
    # SQLite json_array_length(text_col) → Postgres 는 json/jsonb 타입 인자가 필요하다.
    sql = _JSON_ARRAY_LENGTH.sub(r"json_array_length((\1)::json)", sql)

    if _INSERT_OR_IGNORE.search(sql):
        sql = _INSERT_OR_IGNORE.sub("INSERT INTO", sql).rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

    m = _INSERT_OR_REPLACE.search(sql)
    if m:
        table = m.group(1)
        if table not in _UPSERT_PK:
            raise NotImplementedError(
                f"INSERT OR REPLACE INTO {table}: dbcompat._UPSERT_PK 에 PK 매핑이 없습니다."
            )
        pk = _UPSERT_PK[table]
        cols_match = re.search(
            rf"INSERT OR REPLACE INTO\s+{table}\s*\(([^)]+)\)", sql, re.IGNORECASE
        )
        if not cols_match:
            raise NotImplementedError(
                f"INSERT OR REPLACE INTO {table}: 컬럼 목록을 SQL 에서 파싱하지 못했습니다"
                " (VALUES 절 형태만 지원)."
            )
        cols = [c.strip() for c in cols_match.group(1).split(",")]
        update_cols = [c for c in cols if c not in pk]
        set_clause = ", ".join(f"{c}=EXCLUDED.{c}" for c in update_cols)
        sql = _INSERT_OR_REPLACE.sub(r"INSERT INTO \1", sql)
        sql = sql.rstrip().rstrip(";") + f" ON CONFLICT ({', '.join(pk)}) DO UPDATE SET {set_clause}"

    # 마지막에 일괄 치환 — 위 단계에서 새로 심은 `?` 도 여기서 함께 바뀐다.
    return sql.replace("?", "%s")


# ────────────────────────────────────────────────────────── PRAGMA 대체 (Postgres 전용)

_PRAGMA_TABLE_INFO = re.compile(r"^\s*PRAGMA\s+table_info\((\w+)\)\s*$", re.IGNORECASE)
_PRAGMA_FK_LIST = re.compile(r"^\s*PRAGMA\s+foreign_key_list\((\w+)\)\s*$", re.IGNORECASE)
_PRAGMA_ANY = re.compile(r"^\s*PRAGMA\b", re.IGNORECASE)


def _pragma_table_info_rows(raw_cursor, table: str) -> list[tuple]:
    """sqlite3 `PRAGMA table_info(t)` 와 같은 모양의 (cid, name, type, notnull, dflt_value, pk)."""
    raw_cursor.execute(
        "SELECT ordinal_position, column_name, data_type, is_nullable, column_default"
        " FROM information_schema.columns"
        " WHERE table_schema = current_schema() AND table_name = %s ORDER BY ordinal_position",
        (table,),
    )
    cols = raw_cursor.fetchall()
    raw_cursor.execute(
        "SELECT kcu.column_name FROM information_schema.table_constraints tc"
        " JOIN information_schema.key_column_usage kcu"
        "   ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema"
        " WHERE tc.table_schema = current_schema() AND tc.table_name = %s"
        " AND tc.constraint_type = 'PRIMARY KEY'",
        (table,),
    )
    pk_cols = {r[0] for r in raw_cursor.fetchall()}
    rows = []
    for pos, name, dtype, nullable, default in cols:
        rows.append((pos - 1, name, dtype, 0 if nullable == "YES" else 1, default, 1 if name in pk_cols else 0))
    return rows


def _pragma_fk_list_rows(raw_cursor, table: str) -> list[tuple]:
    """sqlite3 `PRAGMA foreign_key_list(t)` 와 같은 모양의
    (id, seq, table, from, to, on_update, on_delete, match)."""
    raw_cursor.execute(
        "SELECT kcu.column_name, ccu.table_name, ccu.column_name"
        " FROM information_schema.table_constraints tc"
        " JOIN information_schema.key_column_usage kcu"
        "   ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema"
        " JOIN information_schema.constraint_column_usage ccu"
        "   ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema"
        " WHERE tc.table_schema = current_schema() AND tc.constraint_type = 'FOREIGN KEY'"
        " AND tc.table_name = %s",
        (table,),
    )
    rows = []
    for i, (from_col, ref_table, ref_col) in enumerate(raw_cursor.fetchall()):
        rows.append((i, 0, ref_table, from_col, ref_col, "NO ACTION", "NO ACTION", "NONE"))
    return rows


def _pragma_override(sql: str, raw_cursor):
    """PRAGMA 문을 가로채 Postgres 대체 결과(행 리스트)를 돌려준다. 해당 없으면 None."""
    if not USE_POSTGRES:
        return None
    m = _PRAGMA_TABLE_INFO.match(sql)
    if m:
        return _pragma_table_info_rows(raw_cursor, m.group(1))
    m = _PRAGMA_FK_LIST.match(sql)
    if m:
        return _pragma_fk_list_rows(raw_cursor, m.group(1))
    if _PRAGMA_ANY.match(sql):
        # foreign_keys=ON, busy_timeout=... 등 — Postgres 에서는 개념이 없거나 항상 적용된다.
        return []
    return None


# ────────────────────────────────────────────────────────── INSERT 의 boolean 컬럼 자동 캐스팅
#
# SQLite 는 BOOLEAN 을 그냥 INTEGER(0/1)로 저장하므로 시드 데이터·기존 코드가 전부 0/1 정수를
# 넘긴다. psycopg 파라미터 바인딩은 그 정수를 boolean 컬럼에 암묵 변환하지 않는다
# ("column is of type boolean but expression is of type smallint"). INSERT 문에서
# 대상 테이블·컬럼을 파싱해 boolean 컬럼 위치의 0/1 만 Python bool 로 바꿔준다.

_INSERT_WITH_COLS = re.compile(r"INSERT INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES", re.IGNORECASE)
_INSERT_NO_COLS = re.compile(r"INSERT INTO\s+(\w+)\s+VALUES", re.IGNORECASE)

_bool_cols_cache: dict[str, set] = {}
_all_cols_cache: dict[str, list] = {}


def _cache_key(raw_cursor, table: str) -> tuple:
    # `information_schema.columns` 는 스키마 무관하게 이름이 같은 테이블을 전부 매칭한다
    # (예: 스파이크가 만든 격리 스키마마다 "parts" 가 하나씩 더 있다) — table_schema 를
    # 안 걸면 여러 스키마의 컬럼 목록이 섞여 순서·개수가 어긋난다(Sprint 16 MQ-1614 로 발견:
    # 정리 안 된 격리 스키마가 남아 있으면 완전히 무관한 이후의 seed.py 실행까지 깨졌다).
    # search_path 가 가리키는 현재 스키마로만 한정하고, 캐시 키에도 그 스키마를 넣는다.
    schema = raw_cursor.execute("SELECT current_schema()").fetchone()[0]
    return (schema, table)


def _boolean_columns(raw_cursor, table: str) -> set:
    key = _cache_key(raw_cursor, table)
    if key not in _bool_cols_cache:
        raw_cursor.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = current_schema() AND table_name = %s AND data_type = 'boolean'",
            (table,),
        )
        _bool_cols_cache[key] = {r[0] for r in raw_cursor.fetchall()}
    return _bool_cols_cache[key]


def _all_columns_in_order(raw_cursor, table: str) -> list:
    key = _cache_key(raw_cursor, table)
    if key not in _all_cols_cache:
        raw_cursor.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = current_schema() AND table_name = %s ORDER BY ordinal_position",
            (table,),
        )
        _all_cols_cache[key] = [r[0] for r in raw_cursor.fetchall()]
    return _all_cols_cache[key]


def _insert_target(sql: str, raw_cursor):
    """INSERT 문에서 (table, 컬럼 순서 목록) 을 알아낸다. 컬럼 목록이 없는 `VALUES (...)`
    형태(예: `INSERT INTO suppliers VALUES (?,?,?,?,?)`)는 information_schema 순서로 채운다.
    반환하는 컬럼 목록은 **파라미터 전체**(1:1)에 대응한다."""
    m = _INSERT_WITH_COLS.search(sql)
    if m:
        return m.group(1), [c.strip() for c in m.group(2).split(",")], True
    m = _INSERT_NO_COLS.search(sql)
    if m:
        table = m.group(1)
        return table, _all_columns_in_order(raw_cursor, table), True
    return None, None, True


_UPDATE_SET = re.compile(r"^\s*UPDATE\s+(\w+)\s+SET\s+(.*?)(?:\s+WHERE\b|$)", re.IGNORECASE | re.DOTALL)
_ASSIGN_PARAM = re.compile(r"^\s*(\w+)\s*=\s*%s\s*$")


def _split_top_level(text: str, sep: str = ",") -> list[str]:
    """괄호 깊이를 추적하며 콤마로 나눈다(함수 호출 인자의 콤마는 건드리지 않는다)."""
    parts, depth, buf = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


def _update_target(sql: str):
    """UPDATE ... SET 절에서, **파라미터로 바인딩되는 컬럼만** 등장 순서대로 뽑는다
    (리터럴 대입은 파라미터를 소비하지 않으므로 건너뛴다). SET 절이 WHERE 절보다 먼저
    나오므로, 이 목록은 params 튜플의 **앞쪽 N개**(WHERE 절 파라미터는 그 뒤)와 대응한다."""
    m = _UPDATE_SET.search(sql)
    if not m:
        return None, None, False
    table = m.group(1)
    cols = []
    for assignment in _split_top_level(m.group(2)):
        am = _ASSIGN_PARAM.match(assignment)
        if am:
            cols.append(am.group(1))
    return table, cols, False


def _cast_bool_params(sql: str, params, raw_cursor):
    if not USE_POSTGRES or params is None:
        return params
    if re.match(r"\s*INSERT\b", sql, re.IGNORECASE):
        table, cols, full = _insert_target(sql, raw_cursor)
    elif re.match(r"\s*UPDATE\b", sql, re.IGNORECASE):
        table, cols, full = _update_target(sql)
    else:
        return params
    if not table or not cols:
        return params
    bool_cols = _boolean_columns(raw_cursor, table)
    if not bool_cols:
        return params
    bool_idx = {i for i, c in enumerate(cols) if c in bool_cols}
    if not bool_idx:
        return params

    def _cast_row(row):
        if full and len(row) != len(cols):
            return row  # INSERT 인데 컬럼 수가 안 맞으면(예상 밖 형태) 손대지 않는다
        row = list(row)
        for i in bool_idx:
            if i < len(row) and row[i] is not None and not isinstance(row[i], bool):
                row[i] = bool(row[i])
        return tuple(row)

    if isinstance(params, (list, tuple)) and params and isinstance(params[0], (list, tuple)):
        return [_cast_row(r) for r in params]
    return _cast_row(params)


# ────────────────────────────────────────────────────────── 예외 매핑

def _map_exception(exc: psycopg.Error) -> Exception:
    if isinstance(exc, psycopg.errors.IntegrityError):
        return sqlite3.IntegrityError(str(exc))
    if isinstance(exc, psycopg.errors.RaiseException):
        # PL/pgSQL 트리거의 `RAISE EXCEPTION` (scripts/postgres_guards.sql 의 D10 가드 등).
        # SQLite 시절 트리거의 `RAISE(ABORT, 'msg')` 는 Python sqlite3 에서 IntegrityError
        # 로 올라왔다 — 호출부의 `except sqlite3.IntegrityError` 가 그대로 잡게 하려면
        # 여기서도 같은 클래스로 매핑해야 한다(DatabaseError 로 두면 안 잡혀서 그대로 죽는다).
        return sqlite3.IntegrityError(str(exc))
    if isinstance(exc, psycopg.errors.OperationalError):
        return sqlite3.OperationalError(str(exc))
    return sqlite3.DatabaseError(str(exc))


# ────────────────────────────────────────────────────────── 실패한 statement 의 자동 격리
#
# SQLite 는 한 statement 가 실패해도(CHECK/FK 위반 등) 커넥션이 멀쩡해서 바로 다음 statement를
# 실행할 수 있다. Postgres 는 트랜잭션 안에서 statement 하나가 실패하면 그 트랜잭션 전체가
# "aborted" 상태가 되고, 명시적 ROLLBACK(또는 SAVEPOINT 로 되돌리기) 전까지 **아무 명령도**
# 받지 않는다. 이 코드베이스(특히 seed.py verify())는 "잘못된 INSERT 를 시도해 거부되는지
# 본다"는 SAVEPOINT 없는 프로브를 여럿 쓰므로, 여기서 매 statement 를 자동으로 SAVEPOINT 로
# 감싸 SQLite 와 같은 "실패해도 다음 statement 는 정상 진행" 성질을 흉내낸다.
# SAVEPOINT/RELEASE/ROLLBACK/COMMIT/BEGIN 자체는 감싸지 않는다 — 호출부가 이미 자기
# SAVEPOINT 를 관리하는 곳(FK 프로브 등)과 이름이 꼬이면 안 되기 때문이다.

_TXN_CONTROL_RE = re.compile(r"^\s*(SAVEPOINT|RELEASE|ROLLBACK|COMMIT|BEGIN)\b", re.IGNORECASE)
_AUTO_SAVEPOINT = "__dbcompat_auto"


def _is_txn_control(sql) -> bool:
    return isinstance(sql, str) and bool(_TXN_CONTROL_RE.match(sql))


class _AutoSavepoint:
    """`with _AutoSavepoint(raw_exec):` — 안에서 실패하면 이 statement 만 되돌리고,
    매핑된 예외로 다시 던진다. `raw_exec(sql)` 은 번역·재귀 없이 SAVEPOINT 문 자체를
    실행하는 최소 콜러블이어야 한다(그래야 SAVEPOINT 문이 다시 이 클래스를 거치지 않는다)."""

    def __init__(self, raw_exec, active: bool):
        self._raw_exec = raw_exec
        self._active = active

    def __enter__(self):
        if self._active:
            self._raw_exec(f"SAVEPOINT {_AUTO_SAVEPOINT}")
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self._active:
            return False
        if exc_type is None:
            self._raw_exec(f"RELEASE SAVEPOINT {_AUTO_SAVEPOINT}")
        else:
            self._raw_exec(f"ROLLBACK TO SAVEPOINT {_AUTO_SAVEPOINT}")
            self._raw_exec(f"RELEASE SAVEPOINT {_AUTO_SAVEPOINT}")
        return False  # 원래 예외는 그대로 전파(호출부가 매핑해 다시 던진다)


# ────────────────────────────────────────────────────────── 커넥션/커서 어댑터


class _PgCursor:
    def __init__(self, raw_cursor):
        self._cur = raw_cursor
        self._override_rows: list[tuple] | None = None

    @property
    def description(self):
        return self._cur.description

    @property
    def lastrowid(self):
        return None  # Postgres 경로는 BIGSERIAL 이라 시드 코드가 이 값에 의존하지 않는다.

    @property
    def rowcount(self):
        return self._cur.rowcount

    def execute(self, sql, params=None):
        override = _pragma_override(sql, self._cur)
        if override is not None:
            self._override_rows = override
            return self
        self._override_rows = None
        sql2 = translate_sql(sql)
        # 빈 시퀀스는 "파라미터 없음"과 같다 — sqlite3 는 이걸 그냥 무시하지만, psycopg 는
        # params 가 None 이 아니면 `%s`/리터럴 `%` 문자를 해석하려 들어서 LIKE 패턴('%목업%'
        # 같은) 문자열이 있는 무파라미터 쿼리가 깨진다. None 으로 정규화해 그 파싱 자체를 끈다.
        if params is not None and len(params) == 0:
            params = None
        # SAVEPOINT/RELEASE 부기는 self._cur 가 아니라 **별도 커서**로 실행해야 한다 —
        # 같은 커서에 실행하면 그 커서의 "마지막 결과셋"이 RELEASE 결과(행 없음)로 덮여
        # 그 다음 fetchone()/fetchall() 이 "the last operation didn't produce records" 로 죽는다.
        guard = _AutoSavepoint(
            lambda s: self._cur.connection.execute(s), USE_POSTGRES and not _is_txn_control(sql)
        )
        try:
            with guard:
                if params is None:
                    self._cur.execute(sql2)
                else:
                    if USE_POSTGRES:
                        params = _cast_bool_params(sql2, params, self._cur)
                    self._cur.execute(sql2, params)
        except psycopg.Error as exc:
            raise _map_exception(exc) from exc
        return self

    def executemany(self, sql, rows):
        self._override_rows = None
        sql2 = translate_sql(sql)
        rows = list(rows)
        if USE_POSTGRES:
            rows = _cast_bool_params(sql2, rows, self._cur)
        guard = _AutoSavepoint(lambda s: self._cur.connection.execute(s), USE_POSTGRES)
        try:
            with guard:
                self._cur.executemany(sql2, rows)
        except psycopg.Error as exc:
            raise _map_exception(exc) from exc
        return self

    def fetchone(self):
        # 커넥션에 row_factory=sqlite_row_factory 가 걸려 있으므로 psycopg 가 이미 Row 를 반환한다.
        if self._override_rows is not None:
            return self._override_rows[0] if self._override_rows else None
        return self._cur.fetchone()

    def fetchall(self):
        if self._override_rows is not None:
            return self._override_rows
        return self._cur.fetchall()

    def fetchmany(self, size=None):
        if self._override_rows is not None:
            return self._override_rows[:size] if size else self._override_rows
        return self._cur.fetchmany(size) if size is not None else self._cur.fetchmany()

    def __iter__(self):
        return iter(self.fetchall())


class PgConnection:
    """`sqlite3.Connection` 최소 API 표면(execute/executemany/cursor/commit/rollback/close
    /row_factory)만 흉내낸다 — 이 계층을 거치는 코드는 sqlite3 를 직접 쓰던 시절 그대로 동작한다."""

    def __init__(self, dsn: str):
        self._con = psycopg.connect(dsn, row_factory=sqlite_row_factory)
        self.row_factory = None  # API 호환용 자리 — 실제로는 항상 Row 를 반환하므로 무시된다.

    def cursor(self) -> _PgCursor:
        return _PgCursor(self._con.cursor())

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def executemany(self, sql, rows):
        cur = self.cursor()
        cur.executemany(sql, rows)
        return cur

    def executescript(self, sql: str):
        """SQLite 의 `executescript` — 세미콜론으로 구분된 여러 DDL 문을 한 번에 돌린다.
        psycopg 는 파라미터 없는 다중 statement 실행을 그대로 지원한다."""
        with self._con.cursor() as cur:
            cur.execute(sql)
        return self

    def commit(self):
        self._con.commit()

    def rollback(self):
        self._con.rollback()

    def close(self):
        self._con.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()


class _RawBypass:
    """`_pragma_override`/`_cast_bool_params` 등 introspection 헬퍼가 `CompatCursor` 안에서
    자기 자신의 `execute()` 를 다시 부르면(무한 재귀·중첩 auto-SAVEPOINT 이름 충돌) 안 되므로,
    psycopg.Cursor 원형 메서드로 곧장 내려가는 얇은 우회로."""

    def __init__(self, cur: "CompatCursor"):
        self._cur = cur

    def execute(self, sql, params=None):
        if params is None:
            psycopg.Cursor.execute(self._cur, sql)
        else:
            psycopg.Cursor.execute(self._cur, sql, params)
        return self

    def fetchall(self):
        return psycopg.Cursor.fetchall(self._cur)

    def fetchone(self):
        return psycopg.Cursor.fetchone(self._cur)


class CompatCursor(psycopg.Cursor):
    """`backend/db.py`·`mcp_server/db.py` 가 연 **진짜 psycopg 커넥션**에 물리는 커서.

    이 파일들의 `connect()`/`read_only()`/`draft_writer()` 등은 sqlite3 대체 껍데기(`PgConnection`)
    를 쓰지 않고 psycopg 를 직접 부르지만, 그 아래(`backend/services/*`·`mcp_server/tools/*`)의
    호출부는 여전히 `?` 플레이스홀더·`sqlite3.IntegrityError`·0/1 boolean 리터럴을 그대로 쓴다.
    `cursor_factory=CompatCursor` 로 물리면 그 코드도 손대지 않고 통과한다 — `_PgCursor`(위)와
    같은 변환을 psycopg 자체 Cursor 서브클래스로 구현한 것뿐, 로직은 하나의 원천
    (`translate_sql`·`_cast_bool_params`·`_map_exception`)을 공유한다.
    """

    @property
    def lastrowid(self):
        """sqlite3.Cursor.lastrowid 대체. BIGSERIAL 이 방금 채번한 값은 세션 안에서
        `lastval()` 로 그대로 읽힌다 — INSERT 직후 호출하는 기존 관행과 호환된다
        (backend/routers/equipment.py 등). 시퀀스를 아직 하나도 안 썼으면(예: PK 가
        BIGSERIAL 이 아닌 테이블에 INSERT) sqlite3 처럼 None 을 돌려준다."""
        try:
            return psycopg.Cursor.execute(self, "SELECT lastval()").fetchone()[0]
        except psycopg.Error:
            return None

    def execute(self, query, params=None, **kwargs):
        self._compat_override_rows = None
        raw = _RawBypass(self)
        is_control = False
        if isinstance(query, str):
            is_control = _is_txn_control(query)
            override = _pragma_override(query, raw)
            if override is not None:
                self._compat_override_rows = override
                return self
            query = translate_sql(query)
            if params is not None and len(params) == 0:
                params = None  # 빈 시퀀스 → None (LIKE '%...%' 등 리터럴 % 파싱 오작동 방지)
            if params is not None:
                params = _cast_bool_params(query, params, raw)
        # self(=CompatCursor) 대신 별도 커서로 부기한다 — 같은 커서면 fetch 대상 결과셋이 덮인다.
        guard = _AutoSavepoint(lambda s: self.connection.execute(s), USE_POSTGRES and not is_control)
        try:
            with guard:
                return super().execute(query, params, **kwargs)
        except psycopg.Error as exc:
            raise _map_exception(exc) from exc

    def executemany(self, query, params_seq, **kwargs):
        self._compat_override_rows = None
        params_seq = list(params_seq)
        raw = _RawBypass(self)
        if isinstance(query, str):
            query2 = translate_sql(query)
            params_seq = _cast_bool_params(query2, params_seq, raw)
        else:
            query2 = query
        guard = _AutoSavepoint(lambda s: self.connection.execute(s), USE_POSTGRES)
        try:
            with guard:
                return super().executemany(query2, params_seq, **kwargs)
        except psycopg.Error as exc:
            raise _map_exception(exc) from exc

    def fetchone(self):
        rows = getattr(self, "_compat_override_rows", None)
        if rows is not None:
            self._compat_override_rows = None
            return rows[0] if rows else None
        return super().fetchone()

    def fetchall(self):
        rows = getattr(self, "_compat_override_rows", None)
        if rows is not None:
            self._compat_override_rows = None
            return rows
        return super().fetchall()


def connect(db_path: str | Path | None = None, *, uri: bool = False, allow_sqlite: bool = False):
    """`sqlite3.connect()` 대체. `DATABASE_URL` 이 있으면 Postgres, 없으면 SQLite.

    🔴 **SQLite 로 떨어지려면 `allow_sqlite=True` 를 명시해야 한다 (D130).**
    예전에는 환경변수 유무만으로 조용히 갈렸다 — 같은 코드가 어떤 날은 Postgres 를,
    어떤 날은 `data/maintq.db` 를 보면서 **아무 말도 하지 않았다.** 그 사이 `backend/db.py`
    는 같은 상황에서 `localhost:5432`(무응답)로 가서 무한 대기했다. 즉 환경변수 하나가
    빠지면 두 모듈이 **서로 다른 DB** 를 보는데 어느 쪽도 알려주지 않았다.

    지금은 SQLite 를 쓰겠다는 **의도를 코드에 적어야** 한다. 픽스처 DB 를 만드는
    `data/seed.py`(`--db` 로 SQLite 파일을 지정하는 경로)와 스파이크가 그 대상이고,
    애플리케이션 런타임에는 해당 경로가 없다 — 이 프로젝트는 Postgres 전용이다(D116).
    """
    if USE_POSTGRES:
        return PgConnection(DATABASE_URL)
    if not allow_sqlite:
        raise RuntimeError(
            "DATABASE_URL 이 없습니다. 이 프로젝트는 Postgres 전용입니다 (D116·D130) — "
            "SQLite 로 조용히 폴백하지 않습니다. 셸에서 "
            "DATABASE_URL=\"$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)\" 를 실어 주십시오. "
            "픽스처용 SQLite 파일이 정말 필요하면 connect(..., allow_sqlite=True) 로 의도를 밝히십시오."
        )
    if uri:
        return sqlite3.connect(str(db_path), uri=True)
    return sqlite3.connect(db_path)


def connect_dsn(dsn: str) -> "PgConnection":
    """모듈 전역 `DATABASE_URL` 이 아니라 **명시적으로 지정한** Postgres DSN 에 연결한다.

    `data/pg_isolation.py` 로 만든 격리 스키마(스파이크 전용 사본)에 연결할 때 쓴다 —
    `connect()` 는 항상 전역 타겟(공유 DB)으로만 가므로 격리 스키마용으로는 못 쓴다.
    """
    return PgConnection(dsn)


def add_dsn_option(dsn: str, extra: str) -> str:
    """DSN 의 `options` 쿼리 파라미터에 `extra`(예: `-c default_transaction_read_only=on`)
    를 **더한다**(덮어쓰지 않는다).

    `psycopg.connect(dsn, options="...")` 처럼 별도 키워드 인자로 넘기면 conninfo
    문자열에 이미 있는 `options`(격리 스키마의 `search_path` 등, data/pg_isolation.py)를
    통째로 덮어써서 조용히 사라진다 — mcp_server/db.py 의 read_only() 에서 실사고로
    발견됐다(격리 스키마의 lookup 이 계속 public 을 읽고 있었다). 이 함수는 그 대신 DSN
    문자열 안에서 옵션을 합친다 — `backend/services/disposal.py` 의 읽기 전용 커넥션도
    같은 방식을 쓴다.
    """
    parts = urlsplit(dsn)
    q = dict(parse_qsl(parts.query))
    existing = q.get("options", "")
    q["options"] = f"{existing} {extra}".strip() if existing else extra
    query = urlencode(q, quote_via=quote)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
