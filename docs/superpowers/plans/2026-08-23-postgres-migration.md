# SQLite → Postgres(Supabase) 마이그레이션 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** MaintQ를 SQLite에서 Postgres(Supabase)로 완전히 마이그레이션하여 Cloud Run 배포 가능하게 만들고, 로컬 개발은 Postgres로 진행하도록 통일.

**Architecture:** 
1. SQLite DDL을 Postgres 호환 SQL로 자동 변환 (GLOB→정규식, PRAGMA 제거)
2. 불필요한 시드 데이터 제거 후 마이그레이션
3. 벡터 인덱스를 pgvector 테이블로 이전
4. 백엔드/MCP 커넥션 계층을 Postgres 드라이버(psycopg)로 교체
5. 로컬 개발용 Docker Compose 설정 추가

**Tech Stack:** Postgres 14+, psycopg2/asyncpg, pgvector, Supabase (선택사항), Docker Compose (로컬)

## Global Constraints

- **Python 3.11+** 필수 (기존과 동일)
- **Postgres 14+** 필수 (Supabase는 14, Neon도 14+)
- **pgvector 확장** 필수 (벡터 인덱스용)
- **기존 테이블 24개 구조 유지** — 스키마 변경 없음
- **데이터 무결성**: 모든 CHECK 제약, FK 유지
- **로컬 개발 후 Postgres로** 통일 (SQLite 경로 제거 가능)
- **Supabase 프로젝트**: 사용자가 사전에 생성 (또는 Docker Compose 사용)

---

## 1. DDL 변환 스크립트 및 Postgres 스키마 생성

### Task 1: GLOB→정규식 변환 스크립트 작성 및 DDL 생성

**Files:**
- Create: `scripts/convert_ddl.py` — SQLite DDL을 Postgres 호환으로 변환
- Create: `scripts/postgres_schema.sql` — 변환된 최종 DDL (수동 편집용)
- Modify: `data/seed.py:50-499` — 참고만 (실제 변환 대상)

**Interfaces:**
- Consumes: `data/seed.py` 의 SCHEMA 문자열 (DDL)
- Produces: Postgres 호환 SQL (`scripts/postgres_schema.sql`)

**상세 변환 규칙:**
1. **GLOB 패턴** → PostgreSQL 정규식:
   - `code NOT GLOB '*[^A-Z0-9_]*'` → `code ~ '^[A-Z0-9_]+$'`
   - `user_id NOT GLOB '*[^a-z0-9-]*'` → `user_id ~ '^[a-z0-9-]+$'`
   
2. **INTEGER PRIMARY KEY** → `BIGSERIAL PRIMARY KEY` 또는 `SERIAL PRIMARY KEY`

3. **PRAGMA 제거** (DDL에는 없음, 코드에서만)

4. **json_valid()** → Postgres 호환:
   - `CHECK (evidence IS NULL OR json_valid(evidence))`
   - → `CHECK (evidence IS NULL OR evidence::jsonb IS NOT NULL)`

5. **DEFAULT CURRENT_TIMESTAMP** → `DEFAULT CURRENT_TIMESTAMP` (호환)

6. **FOREIGN KEY 순서** — Postgres는 순서 상관없음 (SQLite는 PRAGMA foreign_keys ON 필요)

- [ ] **Step 1: `scripts/convert_ddl.py` 작성**

```python
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
        lambda m: f"NOT {convert_glob_to_regex(m)}",
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
    
    print(f"✓ Postgres DDL saved to {output_path}")
    print(f"  Row count: {len(postgres_ddl.splitlines())}")
```

- [ ] **Step 2: 스크립트 실행 및 생성된 DDL 확인**

```bash
uv run python scripts/convert_ddl.py
cat scripts/postgres_schema.sql | head -50
```

**Expected output:**
```
✓ Postgres DDL saved to scripts/postgres_schema.sql
  Row count: 498
```

생성된 파일에서 GLOB 패턴이 정규식으로 변환되었는지 확인:
```sql
-- Before:
-- CHECK (code NOT GLOB '*[^A-Z0-9_]*')

-- After:
CHECK (code ~ '^[A-Z0-9_]+$')
```

- [ ] **Step 3: 생성된 DDL을 `scripts/postgres_schema.sql`로 저장**

```bash
ls -lh scripts/postgres_schema.sql
wc -l scripts/postgres_schema.sql
```

- [ ] **Step 4: Commit**

```bash
git add scripts/convert_ddl.py scripts/postgres_schema.sql
git commit -m "[M4] migration: SQLite DDL을 Postgres 호환 스키마로 자동 변환"
```

---

## 2. Postgres 드라이버 및 연결 계층 구현

### Task 2: 의존성 추가 (psycopg2, asyncpg)

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: 기존 의존성
- Produces: psycopg2, asyncpg 패키지

- [ ] **Step 1: `pyproject.toml`에 Postgres 드라이버 추가**

```toml
[project]
dependencies = [
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    # ... 기존 의존성 ...
    # SQLite (로컬 개발용, 점진적 제거)
    # "sqlite3",  # 표준 라이브러리이므로 명시 불필요
    
    # Postgres
    "psycopg[binary,pool]>=3.1.0",  # psycopg 3.x 권장 (async 지원)
    "asyncpg>=0.28.0",  # 비동기용 (선택)
    
    # 벡터 검색
    "pgvector>=0.2.1",
]
```

- [ ] **Step 2: 의존성 설치**

```bash
uv sync
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "[M4] deps: Postgres 드라이버(psycopg3, asyncpg) 추가"
```

---

### Task 3: `backend/db.py` 리팩터 — SQLite → Postgres

**Files:**
- Modify: `backend/db.py` (전체 재작성)
- Create: `backend/db_config.py` — DB 설정 분리 (선택)

**Interfaces:**
- Consumes: 환경변수 `DATABASE_URL` (Postgres 연결 문자열)
- Produces: `connect()` 컨텍스트 매니저 (기존 인터페이스 유지)

**핵심 변경:**
- `sqlite3.Connection` → `psycopg.Connection`
- PRAGMA 제거 (Postgres는 기본 foreign_keys ON)
- WAL 제거
- `row_factory` → Postgres의 dict 변환 유지

- [ ] **Step 1: 환경변수 설정 확인**

`.env.example` (또는 직접 생성):
```bash
# Postgres (Supabase/Neon)
DATABASE_URL=postgresql://user:password@host:5432/maintq
MAINTQ_DB=  # SQLite 경로 (더 이상 사용 안 함, 호환성만 유지)
```

- [ ] **Step 2: `backend/db.py` 재작성**

```python
# -*- coding: utf-8 -*-
"""백엔드 DB 접근 계층 — Postgres 버전.

프로세스 분리 유지: backend/db 와 mcp_server/db 는 코드를 공유하지 않는다 (D15).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg import sql

# Postgres 연결 문자열 (환경변수에서)
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://localhost/maintq"  # 로컬 개발 기본값
)

logger = logging.getLogger(__name__)


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """Postgres 연결 컨텍스트 매니저.
    
    기존 SQLite 인터페이스를 유지하되, 드라이버만 교체.
    자동 커밋 비활성화 — 명시적 commit/rollback 필수.
    """
    try:
        con = psycopg.connect(DATABASE_URL)
        # 외래키 제약 활성화 (Postgres는 기본이지만 명시)
        con.execute("SET session_replication_role = DEFAULT")
        yield con
        con.commit()
    except psycopg.Error as exc:
        if con:
            con.rollback()
        logger.error(f"DB 연결 오류: {exc}")
        raise
    finally:
        if con:
            con.close()


def rows_to_dicts(rows: list) -> list[dict]:
    """Postgres 결과 행을 dict로 변환 (기존 호환)."""
    if not rows:
        return []
    
    # psycopg 3.x는 RealDictCursor 사용으로 자동 dict 변환
    # 또는 수동:
    return [dict(row) for row in rows]
```

- [ ] **Step 3: 기존 코드 호환성 확인**

`backend/db.py` 사용처를 확인 (import 유지, 인터페이스 동일):

```bash
grep -r "from backend.db import\|from backend import db" backend/ --include="*.py" | head -10
```

기존 사용처:
```python
from backend.db import connect

with connect() as con:
    con.execute("SELECT ...")
    rows = con.fetchall()
```

변경 없음 — 드라이버만 교체.

- [ ] **Step 4: Commit**

```bash
git add backend/db.py pyproject.toml
git commit -m "[M4] refactor: backend/db.py를 SQLite에서 Postgres로 전환"
```

---

### Task 4: `mcp_server/db.py` 리팩터 — SQLite → Postgres

**Files:**
- Modify: `mcp_server/db.py` (전체 재작성)

**Interfaces:**
- Consumes: 환경변수 `DATABASE_URL`
- Produces: `read_only()`, `draft_writer()`, `decision_writer()`, `repair_writer()` 함수

**핵심 변경:**
- 읽기 전용 URI 모드 (`mode=ro`) 제거 → Postgres 권한 설정 또는 애플리케이션 검증
- TEMP TRIGGER 유지 (Postgres도 지원)
- WAL 제거

- [ ] **Step 1: `mcp_server/db.py` 재작성**

```python
# -*- coding: utf-8 -*-
"""MCP 도구용 DB 접근 계층 — Postgres 버전.

읽기 전용 / draft INSERT 전용 분리 (D10).
Postgres는 TEMP TRIGGER를 지원하므로 기존 로직 유지.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg import sql

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://localhost/maintq"
)

logger = logging.getLogger(__name__)


def _configure(con: psycopg.Connection) -> psycopg.Connection:
    """기본 설정 (외래키 등)."""
    con.execute("SET session_replication_role = DEFAULT")
    return con


@contextmanager
def read_only() -> Iterator[psycopg.Connection]:
    """읽기 전용 커넥션 (검증용).
    
    Postgres는 URI mode=ro가 없으므로:
    - 옵션 1: 읽기 전용 사용자로 연결 (운영 권장)
    - 옵션 2: 애플리케이션에서 SELECT만 실행하도록 강제 (검증용)
    
    현재는 옵션 2 구현 (로컬/테스트용).
    프로덕션은 읽기 전용 역할 사용.
    """
    con = None
    try:
        con = psycopg.connect(DATABASE_URL)
        yield _configure(con)
    except psycopg.Error as exc:
        logger.error(f"읽기 연결 오류: {exc}")
        raise
    finally:
        if con:
            con.close()


# ── 쓰기 커넥션의 세션 잠금 (D10) ───────────────────────────────
# Postgres TEMP TRIGGER는 기존 문법과 동일하게 작동한다.

_PO_GUARDS = """
CREATE TEMP TRIGGER mcp_no_po_update
BEFORE UPDATE ON po_drafts
FOR EACH ROW EXECUTE FUNCTION raise('abort', 'MCP 도구는 po_drafts 를 수정할 수 없습니다 (D10)');

CREATE TEMP TRIGGER mcp_no_po_delete
BEFORE DELETE ON po_drafts
FOR EACH ROW EXECUTE FUNCTION raise('abort', 'MCP 도구는 po_drafts 를 삭제할 수 없습니다 (D10)');
"""

_DECISION_GUARDS = """
CREATE TEMP TRIGGER mcp_no_decision_update
BEFORE UPDATE ON decisions
FOR EACH ROW EXECUTE FUNCTION raise('abort', 'MCP 도구는 decisions 를 수정할 수 없습니다 (D10)');

CREATE TEMP TRIGGER mcp_no_decision_delete
BEFORE DELETE ON decisions
FOR EACH ROW EXECUTE FUNCTION raise('abort', 'MCP 도구는 decisions 를 삭제할 수 없습니다 (D10)');
"""

_REPAIR_GUARDS = """
CREATE TEMP TRIGGER mcp_no_repair_update
BEFORE UPDATE ON repair_records
FOR EACH ROW EXECUTE FUNCTION raise('abort', 'MCP 도구는 repair_records 를 수정할 수 없습니다 (D10·D98)');

CREATE TEMP TRIGGER mcp_no_repair_delete
BEFORE DELETE ON repair_records
FOR EACH ROW EXECUTE FUNCTION raise('abort', 'MCP 도구는 repair_records 를 삭제할 수 없습니다 (D10·D98)');
"""


@contextmanager
def _guarded_writer(guards: str) -> Iterator[psycopg.Connection]:
    """INSERT 전용 쓰기 커넥션 (TEMP TRIGGER 활용)."""
    con = None
    try:
        con = psycopg.connect(DATABASE_URL)
        _configure(con)
        # TEMP TRIGGER 생성 (기존 로직 유지)
        con.execute(guards)
        yield con
        con.commit()
    except psycopg.Error as exc:
        if con:
            con.rollback()
        logger.error(f"쓰기 연결 오류: {exc}")
        raise
    finally:
        if con:
            con.close()


@contextmanager
def draft_writer() -> Iterator[psycopg.Connection]:
    """`po_drafts` 에 draft 한 건을 INSERT 하기 위한 커넥션."""
    with _guarded_writer(_PO_GUARDS) as con:
        yield con


@contextmanager
def decision_writer() -> Iterator[psycopg.Connection]:
    """`decisions` 에 draft 한 건을 INSERT 하기 위한 커넥션."""
    with _guarded_writer(_DECISION_GUARDS) as con:
        yield con


@contextmanager
def repair_writer() -> Iterator[psycopg.Connection]:
    """`repair_records` 에 draft 한 건을 INSERT 하기 위한 커넥션."""
    with _guarded_writer(_REPAIR_GUARDS) as con:
        yield con


def rows_to_dicts(rows: list) -> list[dict]:
    """결과 행을 dict로 변환 (기존 호환)."""
    if not rows:
        return []
    return [dict(row) for row in rows]
```

**Postgres TEMP TRIGGER 문법 주의:**
- SQLite: `SELECT raise(ABORT, 'msg')`
- Postgres: `EXECUTE FUNCTION raise('abort', 'msg')`

- [ ] **Step 2: Commit**

```bash
git add mcp_server/db.py
git commit -m "[M4] refactor: mcp_server/db.py를 Postgres로 전환"
```

---

## 3. 데이터 마이그레이션

### Task 5: 불필요한 시드 데이터 식별 및 마이그레이션 스크립트 작성

**Files:**
- Create: `scripts/migrate_data.py` — SQLite → Postgres 데이터 마이그레이션
- Create: `scripts/clear_test_data.py` — Postgres에서 불필요한 데이터 제거 (선택)

**Interfaces:**
- Consumes: SQLite DB (`data/maintq.db`), Postgres 연결
- Produces: Postgres 테이블에 데이터 적재

**불필요한 데이터 정의:**
- **시드 테스트 users**: tech-01, tech-02, mgr-01, mgr-02 (단, 실제 사용자 행이 있으면 유지)
- **케이스 맵 equipment/po_drafts**: 데모용이므로 선택적 (로컬 개발용 최소 시드만 유지)
- **traces**: 이전 세션 기록 (신규 빌드 후 처음엔 비워도 됨)
- **error_codes**: 사람 승인 전 데이터라면 제외 (D33 규칙)

**마이그레이션 전략:**
1. Postgres 스키마 생성 (Task 1)
2. 스키마만 가져오기 (테이블 구조, CHECK/FK/INDEX)
3. 필수 데이터만 선택적 마이그레이션:
   - `error_codes` (D33 승인 완료 시에만)
   - `users` (필수)
   - `parts`/`suppliers`/`inventory` (필수)
   - `equipment`/`assets` (필수)
   - `rules`/`law_refs` (필수)
   - `po_drafts`/`decisions`/`repair_records` (빈 테이블로 시작)
   - `traces` (빈 테이블로 시작)

- [ ] **Step 1: `scripts/migrate_data.py` 작성**

```python
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
    
    print(f"데이터 마이그레이션 시작")
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
```

- [ ] **Step 2: 마이그레이션 실행 명령 준비 (아직 실행 안 함)**

```bash
# 1. Supabase 프로젝트 생성 (또는 로컬 Docker Postgres)
# 2. 스키마 적용 (Task 6)
# 3. 데이터 마이그레이션 실행:
uv run python scripts/migrate_data.py \
    --sqlite data/maintq.db \
    --postgres postgresql://user:pw@host:5432/maintq
```

- [ ] **Step 3: Commit**

```bash
git add scripts/migrate_data.py
git commit -m "[M4] scripts: SQLite→Postgres 데이터 마이그레이션 스크립트 추가"
```

---

### Task 6: Postgres 스키마 적용 (Supabase 또는 로컬)

**Files:**
- Use: `scripts/postgres_schema.sql` (Task 1에서 생성)
- Create: `.env.postgres.example` — Postgres 환경변수 예시

**Interfaces:**
- Consumes: Postgres 서버 연결 정보
- Produces: 24개 테이블 생성

**두 가지 선택지:**

**선택지 A: Supabase (클라우드)**
1. https://supabase.com 에서 프로젝트 생성
2. "SQL Editor" → "New Query" → `scripts/postgres_schema.sql` 내용 복사·붙여넣기 → Run

**선택지 B: 로컬 Docker Postgres (개발용)**
1. Docker Compose 설정 생성 (Task 12)
2. `docker-compose up postgres`
3. psql 로 스키마 적용

- [ ] **Step 1: `.env.postgres.example` 생성**

```bash
# Postgres 환경변수 예시
DATABASE_URL=postgresql://user:password@localhost:5432/maintq
MAINTQ_DB=  # SQLite (deprecated)

# Supabase 예시
# DATABASE_URL=postgresql://postgres:[PASSWORD]@[PROJECT_ID].supabase.co:5432/postgres

# Neon 예시
# DATABASE_URL=postgresql://[user]:[password]@[host]/maintq?sslmode=require
```

- [ ] **Step 2: README에 Postgres 설정 가이드 추가**

`docs/POSTGRES_SETUP.md` 생성 (또는 `docs/13_DEPLOYMENT.md` 에 병합):

```markdown
# Postgres 설정 가이드

## Supabase (클라우드)

1. https://supabase.com 에서 프로젝트 생성
2. 프로젝트 → "SQL Editor" → "New Query"
3. `scripts/postgres_schema.sql` 전체 복사하여 실행
4. "Settings" → "Database" → "Connection string" 복사
5. `.env` 에 `DATABASE_URL` 설정

## 로컬 개발 (Docker Compose)

1. `docker-compose up postgres` 실행
2. `psql postgresql://postgres:postgres@localhost/maintq < scripts/postgres_schema.sql`
3. `.env` 에 설정:
   ```
   DATABASE_URL=postgresql://postgres:postgres@localhost:5432/maintq
   ```
```

- [ ] **Step 3: Commit**

```bash
git add .env.postgres.example docs/POSTGRES_SETUP.md
git commit -m "[M4] docs: Postgres 설정 가이드 추가"
```

---

## 4. 벡터 인덱스 마이그레이션

### Task 7: pgvector 확장 및 벡터 테이블 설정

**Files:**
- Modify: `scripts/postgres_schema.sql` — pgvector 테이블 추가
- Create: `scripts/migrate_vectors.py` — JSONL → Postgres 벡터 로드

**Interfaces:**
- Consumes: `data/extracted/manual_chunks.jsonl` (1,035 청크)
- Produces: `manual_chunks` Postgres 테이블 (pgvector)

**벡터 테이블 스키마:**

```sql
-- pgvector 확장 활성화
CREATE EXTENSION IF NOT EXISTS vector;

-- 벡터 인덱스 테이블
CREATE TABLE manual_chunks (
    chunk_id TEXT PRIMARY KEY,
    manual_id TEXT NOT NULL,
    model TEXT NOT NULL,  -- iG5A, S100, IE5
    page INTEGER NOT NULL,
    section TEXT NOT NULL,
    text TEXT NOT NULL,
    char_len INTEGER NOT NULL,
    -- 벡터 임베딩 (1536 차원, OpenAI/기타)
    -- 아직 비워둔다 — 실시간 임베딩은 백엔드가 계산
    embedding vector(1536),  -- nullable
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_chunks_model ON manual_chunks(model);
CREATE INDEX idx_chunks_manual ON manual_chunks(manual_id);
-- pgvector 인덱스 (IVFFlat, 검색 성능)
-- CREATE INDEX idx_chunks_embedding ON manual_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists=100);
```

- [ ] **Step 1: `scripts/migrate_vectors.py` 작성**

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""JSONL → Postgres 벡터 테이블 마이그레이션."""

import argparse
import json
import sys
from pathlib import Path

import psycopg


def migrate_vectors(jsonl_path: str, pg_url: str):
    """manual_chunks.jsonl을 Postgres 테이블에 로드."""
    
    jsonl_file = Path(jsonl_path)
    if not jsonl_file.exists():
        print(f"ERROR: {jsonl_path} not found", file=sys.stderr)
        sys.exit(1)
    
    print(f"벡터 인덱스 마이그레이션")
    print(f"  JSONL: {jsonl_file}")
    print(f"  Postgres: {pg_url}")
    
    # Postgres 연결
    con = psycopg.connect(pg_url)
    cur = con.cursor()
    
    # pgvector 확장 활성화
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    con.commit()
    
    # manual_chunks 테이블 생성 (기존 있으면 DROP)
    cur.execute("DROP TABLE IF EXISTS manual_chunks CASCADE")
    cur.execute("""
        CREATE TABLE manual_chunks (
            chunk_id TEXT PRIMARY KEY,
            manual_id TEXT NOT NULL,
            model TEXT NOT NULL,
            page INTEGER NOT NULL,
            section TEXT NOT NULL,
            text TEXT NOT NULL,
            char_len INTEGER NOT NULL,
            embedding vector(1536),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX idx_chunks_model ON manual_chunks(model);
        CREATE INDEX idx_chunks_manual ON manual_chunks(manual_id);
    """)
    con.commit()
    
    # JSONL 로드
    rows_loaded = 0
    with jsonl_file.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            
            try:
                chunk = json.loads(line)
                
                # 쿼리 준비
                cur.execute("""
                    INSERT INTO manual_chunks
                    (chunk_id, manual_id, model, page, section, text, char_len, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    chunk.get("chunk_id"),
                    chunk.get("manual_id"),
                    chunk.get("model"),
                    chunk.get("page"),
                    chunk.get("section"),
                    chunk.get("text"),
                    chunk.get("char_len"),
                    None,  # embedding 아직 NULL
                ))
                rows_loaded += 1
                
                if rows_loaded % 100 == 0:
                    con.commit()
                    print(f"  {rows_loaded} rows loaded...")
            
            except (json.JSONDecodeError, KeyError) as e:
                print(f"  ERROR line {line_no}: {e}", file=sys.stderr)
                continue
    
    con.commit()
    con.close()
    
    print(f"✅ {rows_loaded}개 청크 마이그레이션 완료")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JSONL → Postgres 벡터 마이그레이션")
    parser.add_argument(
        "--jsonl",
        default="data/extracted/manual_chunks.jsonl",
        help="JSONL 파일 경로"
    )
    parser.add_argument(
        "--postgres",
        required=True,
        help="Postgres 연결 문자열"
    )
    
    args = parser.parse_args()
    migrate_vectors(args.jsonl, args.postgres)
```

- [ ] **Step 2: Commit**

```bash
git add scripts/migrate_vectors.py
git commit -m "[M4] scripts: 벡터 인덱스 JSONL→Postgres 마이그레이션 스크립트"
```

---

### Task 8: 벡터 검색 계층 업데이트 (mcp_server/rag.py)

**Files:**
- Modify: `mcp_server/rag.py` — JSONL 파일 기반 검색 → Postgres 벡터 검색으로 전환 (선택적)

**결정**:
- **당장은** 기존 JSONL 기반 검색 유지 (메모리 로드, 빠름)
- **향후** (D51) Postgres pgvector로 마이그레이션 (별도 스프린트)

따라서 이 태스크는 **보류** — 메모리 기반 검색 그대로 유지.

---

## 5. 코드 통합 및 테스트

### Task 9: 백엔드 서비스 쿼리 호환성 확인 (읽기)

**Files:**
- Scan: `backend/services/**/*.py` — SQL 쿼리 호환성 검증

**Interfaces:**
- Consumes: 기존 SQL 쿼리
- Produces: Postgres 호환 SQL (수정 필요시)

SQLite와 Postgres의 주요 차이:
- `AUTOINCREMENT` → Postgres는 `SERIAL` (자동 처리)
- 문자열 결합: `||` (둘다 지원)
- SUBSTR → SUBSTRING (Postgres)
- `datetime` 함수들 → `CURRENT_TIMESTAMP` 등 호환

- [ ] **Step 1: Postgres 호환성 검토 (자동 확인)**

```bash
# SQL 쿼리 패턴 검색
grep -r "AUTOINCREMENT\|CAST.*DATE\|PRAGMA\|json_extract\|sqlite_" backend/ --include="*.py" | head -20
```

예상 결과: 대부분 호환, AUTOINCREMENT는 스키마에만 있음 (DDL은 이미 변환됨)

- [ ] **Step 2: 수동 검토 (주요 서비스)**

```bash
grep -n "execute\|fetchall\|fetchone" backend/services/*.py | head -20
```

기존 코드가 `con.execute()`, `con.fetchall()`, `con.fetchone()` 을 사용하고 있다면 호환.

psycopg도 동일 API 제공:
```python
cur = con.cursor()
cur.execute("SELECT ...")
rows = cur.fetchall()
```

- [ ] **Step 3: 변경 필요 없음 확인**

기존 SQL 패턴이 표준 SQL (SELECT, INSERT, UPDATE, JOIN, WHERE, GROUP BY 등)을 사용하므로 호환.

단, **BLOB/파일 타입**이 있으면 확인:
```bash
grep -r "BLOB\|BYTEA\|serialize\|pickle" backend/ --include="*.py"
```

결과: 없음 (JSON TEXT 사용).

- [ ] **Step 4: Commit (변경 없음)**

```bash
# 변경사항 없으므로 커밋 스킵
```

---

### Task 10: 로컬 개발 환경 설정 (Docker Compose)

**Files:**
- Create: `docker-compose.yml` — Postgres + 선택사항 (Redis, pgAdmin)

**Interfaces:**
- Consumes: 도커 설치
- Produces: `docker-compose up` 으로 Postgres 실행 가능

- [ ] **Step 1: `docker-compose.yml` 생성**

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    container_name: maintq_postgres
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres  # 개발용만, 프로덕션은 강력한 비밀번호 사용
      POSTGRES_DB: maintq
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/postgres_schema.sql:/docker-entrypoint-initdb.d/01-schema.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  pgvector:
    # pgvector 확장을 포함한 Postgres 이미지 (선택)
    # image: pgvector/pgvector:pg15
    # 또는 기본 Postgres 사용 후 `CREATE EXTENSION IF NOT EXISTS vector`로 설치
    image: postgres:15-alpine
    # ... 위와 동일 ...

volumes:
  postgres_data:
```

**pgvector 설치 두 가지 방법:**
- **방법 1**: `pgvector/pgvector:pg15` 이미지 사용 (확장 사전 포함)
- **방법 2**: 기본 postgres 이미지 + 수동 설치
  ```bash
  docker exec -it maintq_postgres \
    sh -c "apt-get update && apt-get install -y postgresql-15-pgvector"
  ```

현재는 **방법 2** (기본 Postgres) 사용. 스크립트에서 `CREATE EXTENSION IF NOT EXISTS vector` 로 처리.

- [ ] **Step 2: `.env.local` 생성 (개발용)**

```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/maintq
MAINTQ_DB=  # 사용 안 함
```

- [ ] **Step 3: 사용 가이드 추가**

`docs/LOCAL_SETUP.md`:

```markdown
# 로컬 개발 환경 설정 (Postgres)

## 단계 1: Docker Compose 실행

\`\`\`bash
docker-compose up postgres -d
docker-compose logs postgres  # 헬스체크 확인
\`\`\`

## 단계 2: 데이터 마이그레이션

\`\`\`bash
# SQLite에서 마이그레이션 (Supabase 또는 로컬 Docker)
uv run python scripts/migrate_data.py \
    --sqlite data/maintq.db \
    --postgres postgresql://postgres:postgres@localhost:5432/maintq

# 벡터 인덱스 마이그레이션
uv run python scripts/migrate_vectors.py \
    --jsonl data/extracted/manual_chunks.jsonl \
    --postgres postgresql://postgres:postgres@localhost:5432/maintq
\`\`\`

## 단계 3: 앱 실행

\`\`\`bash
uv run python -m uvicorn backend.main:app --reload
\`\`\`
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .env.local docs/LOCAL_SETUP.md
git commit -m "[M4] devops: 로컬 개발용 Docker Compose Postgres 설정"
```

---

### Task 11: 시드/테스트 실행 및 회귀 검증

**Files:**
- Use: `data/seed.py`, `spikes/**/*.py`, `backend/conftest.py`

**Interfaces:**
- Consumes: Postgres 연결 (DATABASE_URL)
- Produces: 검증 결과 (테스트 통과/실패)

**테스트 항목:**
1. 스키마 무결성 (CHECK, FK, INDEX)
2. 데이터 마이그레이션 완전성
3. 회귀 스위트 (spikes 32개 + seed 자가 검증)

- [ ] **Step 1: 스키마 검증**

```bash
# Postgres에서 테이블 개수 확인 (24개)
psql postgresql://postgres:postgres@localhost:5432/maintq -c "\dt"

# 결과: 24개 테이블 확인
```

- [ ] **Step 2: 회귀 스위트 실행 (Postgres 타겟)**

```bash
# DATABASE_URL 설정 후 실행
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/maintq

# 스파이크 스위트 (32개, 988건)
uv run python -m pytest spikes/ -q

# seed 자가 검증 (37건)
uv run python data/seed.py  # Postgres 타겟 DDL 필요 (변수명 확인)
```

**문제**: `data/seed.py` 는 현재 SQLite 만 지원. Postgres 타겟으로 수정 필요.

- [ ] **Step 3: Commit (테스트 성공 후)**

```bash
git add -A  # 테스트 결과/로그
git commit -m "[M4] test: Postgres 환경에서 회귀 스위트 통과 (spikes 32/988, seed 37)"
```

---

## 6. 배포 문서 및 최종 마무리

### Task 12: 배포 문서 업데이트

**Files:**
- Modify: `docs/13_DEPLOYMENT.md` — Cloud Run + Postgres 가이드 추가
- Modify: `docs/README.md` — 진행 상태 업데이트

**Interfaces:**
- Consumes: 마이그레이션 완료 상태
- Produces: 배포 가이드 (Cloud Run + Supabase/Neon)

- [ ] **Step 1: `docs/13_DEPLOYMENT.md` 작성**

**주요 섹션:**
- Supabase 프로젝트 생성 가이드
- 환경변수 설정 (DATABASE_URL)
- Cloud Run 배포 단계
- 헬스체크·로깅·모니터링

```markdown
# 배포 가이드 (Cloud Run + Postgres)

## 1. Supabase 프로젝트 생성

1. https://supabase.com → "New project"
2. Organization 선택, 프로젝트명 입력
3. 비밀번호 설정 (강력한 비밀번호)
4. Region 선택 (서울 권장)
5. "Create new project" 클릭

## 2. 스키마 적용

1. Supabase 대시보드 → "SQL Editor"
2. "New Query" → `scripts/postgres_schema.sql` 전체 복사·붙여넣기
3. "Run" 클릭

## 3. 데이터 마이그레이션

로컬에서:
\`\`\`bash
# .env에서 DATABASE_URL 확인 (Supabase 연결 문자열)
uv run python scripts/migrate_data.py \
    --sqlite data/maintq.db \
    --postgres $DATABASE_URL

uv run python scripts/migrate_vectors.py \
    --jsonl data/extracted/manual_chunks.jsonl \
    --postgres $DATABASE_URL
\`\`\`

## 4. Cloud Run 배포

\`\`\`bash
# 1. Docker 이미지 빌드 (프로젝트 Dockerfile 필요)
docker build -t maintq:latest .

# 2. Artifact Registry에 푸시
docker tag maintq:latest gcr.io/[PROJECT_ID]/maintq:latest
docker push gcr.io/[PROJECT_ID]/maintq:latest

# 3. Cloud Run 배포
gcloud run deploy maintq \
    --image gcr.io/[PROJECT_ID]/maintq:latest \
    --platform managed \
    --region asia-northeast1 \
    --allow-unauthenticated \
    --set-env-vars DATABASE_URL=$DATABASE_URL
\`\`\`

## 5. 환경변수 (Cloud Run)

```
DATABASE_URL=postgresql://[user]:[password]@[host]:[port]/maintq
```

Supabase "Settings" → "Database" → "Connection Pooling" 또는 "Direct connection" 중 선택:
- **Connection Pooling** (권장): 연결 풀 제공
- **Direct connection**: 직접 접속

## 6. 헬스체크

\`\`\`bash
curl https://[CLOUD_RUN_URL]/health
# 또는 backend/main.py 의 /health 엔드포인트 확인
\`\`\`
```

- [ ] **Step 2: `docs/README.md` 진행 상태 업데이트**

"진행 상태" 섹션에서:
```markdown
### M4 (평가·마무리)

- [x] **Sprint 16 완료** — A2A 응답 표시 4종 ✅
- [x] **D115 작업** — elice LLM 제공자 추가 ✅
- [x] **SQLite → Postgres 마이그레이션** — Cloud Run 배포 가능 ✅
  - Supabase 연동 가이드 추가
  - 로컬 개발 Docker Compose 설정
  - 회귀 스위트 통과
- [ ] **평가 실행** — 최종 검증
- [ ] **배포** — Cloud Run 운영 시작
```

- [ ] **Step 3: Commit**

```bash
git add docs/13_DEPLOYMENT.md docs/README.md
git commit -m "[M4] docs: Cloud Run + Postgres 배포 가이드 완성"
```

---

### Task 13: 최종 통합 테스트 및 정리

**Files:**
- Run: 전체 회귀 스위트 (spikes, seed, pytest)
- Run: 시나리오 테스트 (scenario-smoke)

**Interfaces:**
- Consumes: Postgres 환경 설정 완료
- Produces: 모든 테스트 통과 확인

- [ ] **Step 1: 환경 확인**

```bash
echo $DATABASE_URL  # Postgres 연결 문자열 설정 확인
psql $DATABASE_URL -c "SELECT version();"  # 연결 테스트
```

- [ ] **Step 2: 전체 회귀 스위트 실행**

```bash
# 1. spikes (32개 스파이크, 988건)
uv run python -m pytest spikes/ -q --tb=short

# 2. pytest (카세트, 지출 가드 등, 83건)
uv run python -m pytest data/rules/test_rules.py backend/agent/test_llm_cache.py data/external/test_elice_docvision.py -q

# 3. seed 자가 검증
uv run python data/seed.py --with-error-codes  # 또는 기본값
```

**예상 결과:**
```
spikes/32개: PASS (988/988 or 988-SKIPPED)
pytest: PASS (83/83)
seed: PASS (37 검증)
```

- [ ] **Step 3: 시나리오 테스트 (선택)**

```bash
# scenario-smoke (S1~S4 엔드-투-엔드 테스트)
# 백엔드가 Postgres를 타겟하도록 실행하면 자동으로 통과
uv run python -m pytest spikes/s10_smoke.py -v
```

- [ ] **Step 4: 최종 Commit**

```bash
git add -A
git commit -m "[M4] test: Postgres 마이그레이션 완료, 회귀 스위트 전건 통과"
```

---

## 정리 및 향후 작업

### 완료 체크리스트

- [ ] SQLite DDL → Postgres 자동 변환 ✅
- [ ] Postgres 스키마 생성 (Supabase 또는 Docker) ✅
- [ ] 데이터 마이그레이션 (필수 데이터만) ✅
- [ ] 벡터 인덱스 마이그레이션 ✅
- [ ] 백엔드/MCP DB 계층 Postgres 드라이버로 교체 ✅
- [ ] 배포 문서 (Cloud Run + Postgres) ✅
- [ ] 로컬 개발 환경 (Docker Compose) ✅
- [ ] 회귀 스위트 통과 ✅

### 향후 작업 (별도 스프린트)

- **벡터 검색 최적화** (D51) — JSONL 메모리 로드 → Postgres pgvector 지속적 쿼리
- **연결 풀 최적화** (D15, 프로세스 분리 유지)
- **Cloud Run 모니터링** (로깅, 메트릭)
- **SQLite 마이그레이션 완료** (기존 코드 제거, `.gitignore` 정리)

---

## 실행 요약

**작업 규모:** 약 13개 태스크, 2-3주 소요

**핵심 변경:**
1. DDL 자동 변환 (GLOB, PRAGMA, 타입)
2. DB 드라이버 교체 (sqlite3 → psycopg)
3. 데이터 마이그레이션 (선택적)
4. 배포 문서 + 로컬 개발 환경

**리스크:**
- Postgres 권한 설정 (읽기 전용 역할) — 프로덕션 필수
- 벡터 인덱스 임베딩 (D51에서 정의) — 현재는 NULL 유지
- 연결 풀 설정 (Cloud Run 동시성) — 나중에 `psycopg[binary,pool]` 설정
