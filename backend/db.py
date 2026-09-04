# -*- coding: utf-8 -*-
"""백엔드 DB 접근 계층 — Postgres 버전.

프로세스 분리 유지: backend/db 와 mcp_server/db 는 코드를 공유하지 않는다 (D15).
"""

from __future__ import annotations

import atexit
import logging
import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

from data.dbcompat import CompatCursor, sqlite_row_factory

# Postgres 연결 문자열 (환경변수에서)
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://localhost/maintq"  # 로컬 개발 기본값
)

# SQLite 호환 스텁 (Postgres는 이것들을 사용하지 않지만 기존 코드 호환성을 위해 유지)
BUSY_TIMEOUT_MS = 5000  # SQLite 타임아웃 설정
DB_PATH = Path(os.environ.get("MAINTQ_DB", "data/maintq.db"))  # SQLite 경로 (호환용)

logger = logging.getLogger(__name__)

# ── 커넥션 풀 (D127) ─────────────────────────────────────────────────────────
#
# **왜 필요한가 (실측).** 풀이 없을 때 커넥션 1개를 여는 데 **~16ms** 가 든다(TCP+인증
# 핸드셰이크). 그런데 핫 쿼리 자체는 **0.03~0.8ms** 다 — 즉 응답 시간의 대부분이 접속
# 비용이고, `GET /api/po/{id}` 는 커넥션을 2개, 상태 전이는 3개 연다.
#
# 🔴 **지연만의 문제가 아니다.** 2026-09-04 세션에서 회귀를 병렬로 돌리다 Windows 의
#    TIME_WAIT 소켓이 **933개**까지 쌓여 Docker 포트 프록시가 죽고 호스트에서 DB 접속이
#    통째로 끊겼다(컨테이너 재시작으로 복구). 매 쿼리마다 새 TCP 를 여는 구조가 부하에서
#    환경을 멈춰 세운 것이다 — 풀링은 성능 최적화이기 이전에 **안정성 조치**다.
#
# ⚠ **격리 DSN 은 절대 풀링하지 않는다.** 스파이크는 실행마다 새 격리 스키마 DSN 을 만든다
#   (`data/pg_isolation.py`). 그걸 풀에 넣으면 스키마 수만큼 풀이 쌓여 커넥션을 고갈시키고,
#   `drop_isolated_schema()` 뒤에도 죽은 커넥션이 풀에 남는다. 그래서 **기본 대상
#   (`DATABASE_URL`)일 때만** 풀을 태우고, 인자나 `DB_PATH` 전역으로 대상이 바뀌면
#   기존처럼 직접 접속한다. 회귀 1,186건의 격리 전제를 건드리지 않는 유일한 방법이다.

#: 풀 크기. 데모·단일 인스턴스 전제(09_RUNTIME)라 작게 잡는다.
POOL_MIN_SIZE = int(os.environ.get("MAINTQ_DB_POOL_MIN") or 1)
POOL_MAX_SIZE = int(os.environ.get("MAINTQ_DB_POOL_MAX") or 10)
#: 풀에서 커넥션을 얻지 못할 때 포기하는 시간(초). 무한 대기는 hang 으로 보인다.
POOL_TIMEOUT_SEC = float(os.environ.get("MAINTQ_DB_POOL_TIMEOUT") or 10)
#: 탈출구 — `MAINTQ_DB_POOL=0` 이면 풀을 쓰지 않는다(장애 격리용).
POOL_ENABLED = (os.environ.get("MAINTQ_DB_POOL") or "1") not in ("0", "false", "False")

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def _connect_kwargs() -> dict:
    """`psycopg.connect()` 에 넘길 공통 인자. 풀·직접 접속이 **같은 값**을 써야 한다 —
    갈리면 풀을 켰을 때만 행 접근 방식이 달라진다."""
    return {"row_factory": sqlite_row_factory, "cursor_factory": CompatCursor}


def _configure(con: psycopg.Connection) -> None:
    """새 커넥션 1회 설정. **트랜잭션을 열어 둔 채 끝나면 안 된다.**

    psycopg 는 autocommit=False 가 기본이라 `execute()` 하나로 트랜잭션이 시작된다.
    풀의 `configure` 콜백이 그 상태(INTRANS)로 반환하면 psycopg_pool 이 그 커넥션을
    **폐기**하고, 폐기가 반복되면 풀이 비어 `PoolTimeout` 이 난다(실측으로 확인).
    그래서 `SET` 뒤에 반드시 커밋해 idle 로 되돌린다.

    `SET`(LOCAL 아님)은 세션 범위라 커밋해도 값이 유지된다 — 풀에서 재사용되는 동안
    계속 적용된다.
    """
    con.execute("SET session_replication_role = DEFAULT")
    con.commit()


def _check(con: psycopg.Connection) -> None:
    """풀이 커넥션을 건네기 전 생존을 확인한다. 죽었으면 예외 → 풀이 폐기하고 새로 만든다.

    **왜 `ConnectionPool.check_connection` 을 쓰지 않는가.** 그 기본 구현은 빈 SQL
    (`conn.execute("")`)을 날리는데, 이 프로젝트의 `CompatCursor`(data/dbcompat.py)가
    모든 statement 를 auto-SAVEPOINT 로 감싸기 때문에 빈 쿼리에서 깨진다. 실측하면
    커넥션이 만들어질 때마다 폐기돼 풀이 끝내 비고 `PoolTimeout` 이 난다 —
    **접속 실패처럼 보이지만 원인은 체크 함수다.**

    그래서 같은 목적(왕복 1회로 생존 확인)을 dbcompat 과 호환되는 형태로 다시 쓴다.
    앞뒤 `rollback()` 이 핵심이다 — 앞은 이전 사용의 잔여 트랜잭션을, 뒤는 auto-SAVEPOINT
    가 연 트랜잭션을 정리해 커넥션을 idle 로 되돌린다(idle 이 아니면 풀이 폐기한다).

    체크 한 번(~1ms)이 재접속(~16ms)보다 싸고, 무엇보다 네트워크가 한 번 끊긴 뒤
    (2026-09-04 Docker 포트 프록시 사고) 죽은 커넥션이 조용히 건네지는 것을 막는다.
    """
    con.rollback()
    con.execute("SELECT 1").fetchone()
    con.rollback()


def get_pool() -> ConnectionPool:
    """기본 대상(`DATABASE_URL`)의 풀. **첫 사용 시점에 만든다.**

    ⛔ 모듈 임포트 시점에 만들지 않는다 — `backend/main.py` 의 D56 주석이 기록한 hang 과
    같은 계열의 사고가 난다(임포트 중에 접속을 시도하면 대상이 없을 때 조용히 멈춘다).
    """
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ConnectionPool(
                DATABASE_URL,
                min_size=POOL_MIN_SIZE,
                max_size=POOL_MAX_SIZE,
                timeout=POOL_TIMEOUT_SEC,
                kwargs=_connect_kwargs(),
                configure=_configure,
                check=_check,
                name="maintq-backend",
                open=True,
            )
            logger.info(
                "DB 커넥션 풀 생성 (min=%d max=%d timeout=%.1fs)",
                POOL_MIN_SIZE, POOL_MAX_SIZE, POOL_TIMEOUT_SEC,
            )
    return _pool


def close_pool() -> None:
    """풀을 닫는다. FastAPI lifespan 종료와 인터프리터 종료 양쪽에서 부른다."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


atexit.register(close_pool)


@contextmanager
def connect(db_path: str | None = None) -> Iterator[psycopg.Connection]:
    """Postgres 연결 컨텍스트 매니저.

    기존 SQLite 인터페이스를 유지하되, 드라이버만 교체.
    자동 커밋 비활성화 — 명시적 commit/rollback 필수.

    Args:
        db_path: SQLite 경로면 Postgres 에서는 무시한다(DATABASE_URL 이 우선).
                 **Postgres DSN 문자열**이면 이게 최우선이다 — `backend/agent/trace.py`
                 의 `TraceWriter(db_path=...)`처럼 호출부가 이미 명시적으로 대상을
                 지정하는 자리이므로, 굳이 `backend.db.DB_PATH` 전역까지 갈아끼우게
                 하지 않아도 격리 스키마(data/pg_isolation.py)로 곧장 간다.
                 명시 인자가 없으면 `backend.db.DB_PATH`(회귀가 전역으로 갈아끼운 경우)
                 → `DATABASE_URL` 순으로 본다. `DB_PATH` 를 **호출 시점에** 읽는 이유는
                 backend/services/disposal.py·ownership.py 의 기존 관행과 같다: 모듈
                 임포트 시점 값으로 고정하면 회귀가 갈아끼워도 반영되지 않는다.
    """
    # 🔴 인자로 준 대상이 **무시되는 상황을 조용히 넘기지 않는다** (2026-08-29).
    #   아래 분기는 DSN 문자열만 존중한다 — `Path` 나 SQLite 경로 문자열을 넘기면
    #   조용히 무시되고 `DATABASE_URL`(공유 DB)로 간다. 호출부는 격리했다고 믿는데
    #   실제로는 실 데이터를 만지는 상태가 되고, 그게 Sprint 16 에서 두 번(payloads.py·
    #   trace.py 의 `Path()` 래핑), 2026-08-29 에 한 번 더(test_llm_cache.py) 사고를 냈다.
    #   ⚠ **`DB_PATH` 전역은 여기서 막지 않는다** — 스파이크 8곳이 그 전역을 갈아끼우고
    #     전부 DSN 을 넣지만, 전역까지 조이면 회귀 전체가 이 한 줄에 인질이 된다.
    #     인자 경로만 막아도 이 버그 클래스의 실제 발생 지점은 전부 덮인다.
    if db_path is not None and not (
        isinstance(db_path, str) and db_path.startswith("postgresql://")
    ):
        raise TypeError(
            f"connect(db_path=...) 는 Postgres DSN 문자열이어야 합니다: {db_path!r}. "
            "격리가 필요하면 data.pg_isolation.create_isolated_schema() 가 돌려주는 DSN 을 "
            "쓰십시오 — DSN 이 아닌 값은 무시되고 공유 DB 로 연결됩니다."
        )
    target = DATABASE_URL
    if isinstance(DB_PATH, str) and DB_PATH.startswith("postgresql://"):
        target = DB_PATH
    if isinstance(db_path, str):
        target = db_path

    # 기본 대상일 때만 풀을 태운다 (D127) — 격리 DSN 은 위 주석대로 직접 접속한다.
    if POOL_ENABLED and target == DATABASE_URL:
        try:
            # psycopg_pool 의 `connection()` 도 정상 종료 시 commit, 예외 시 rollback 한다
            # — 아래 직접 접속 경로와 의미가 같다. 다른 점은 `close()` 대신 **풀로 반납**
            # 한다는 것뿐이라, 호출부에서 보이는 계약은 바뀌지 않는다.
            with get_pool().connection() as con:
                yield con
            return
        except (psycopg.Error, sqlite3.Error) as exc:
            logger.error(f"DB 연결 오류: {exc}")
            raise

    con = None
    try:
        # row_factory: backend/services/* 다수가 sqlite3.Row 관행(row["col"]) 을 그대로 쓴다 —
        # psycopg 기본 tuple_row 로는 그 접근이 깨진다 (Sprint 16 MQ-1614 에서 발견).
        con = psycopg.connect(target, **_connect_kwargs())
        # 외래키 제약 활성화 (Postgres는 기본이지만 명시)
        _configure(con)
        yield con
        con.commit()
    except (psycopg.Error, sqlite3.Error) as exc:
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
