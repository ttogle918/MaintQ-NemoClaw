# -*- coding: utf-8 -*-
"""SQLite 동시성 검증 (MQ-313) — WAL + busy_timeout 이 실제로 잠금을 막는가.

배경: MCP 서브프로세스(`draft_writer` → po_drafts INSERT)와 백엔드(traces INSERT)가
같은 SQLite 파일에 동시에 쓴다. WAL·busy_timeout 이 없으면 `database is locked` 가
랜덤하게 터진다.

같이 지켜야 하는 경계:
  - D15: 두 모듈은 코드를 공유하지 않는다. 같은 두 줄을 각자 갖는다 (공용 모듈로 빼지 않음)
  - D10: WAL 로 바꿔도 `read_only()` 는 여전히 쓰기를 거부하고, draft_writer 의
         po_drafts UPDATE/DELETE 차단 트리거는 그대로 살아 있어야 한다

이 스파이크는 검증 목적상 두 모듈을 한 프로세스에서 import 하지만(런타임에는 분리),
DB 는 반드시 **임시 사본**만 건드린다 — `data/maintq.db` 는 읽기만 하고 mtime 을 확인한다.

실행:  uv run python spikes/db_concurrency.py
"""

from __future__ import annotations

import ast
import inspect
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DB = ROOT / "data" / "maintq.db"
sys.path.insert(0, str(ROOT))
from data import dbcompat, pg_isolation  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


# ── 헬퍼 ────────────────────────────────────────────────────────────────────


def _pg_scalar(dsn: str, sql: str) -> object:
    con = dbcompat.connect_dsn(dsn)
    try:
        return con.execute(sql).fetchall()[0][0]
    finally:
        con.close()


def journal_mode(db: Path) -> str:
    """파일에 영속된 저널 모드를 별도 커넥션으로 읽는다."""
    con = sqlite3.connect(db)
    try:
        return con.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        con.close()


def function_body(fn) -> str:
    """docstring 을 뺀 함수 본문 소스. 설명문의 단어가 정적 검사에 걸리지 않게 한다."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    node = tree.body[0]
    body = node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return "\n".join(ast.unparse(n) for n in body)


def module_imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    return names


def insert_draft(con: sqlite3.Connection, po_id: str) -> None:
    con.execute(
        "INSERT INTO po_drafts (po_id, part_no, qty, supplier_id, unit_price, reason)"
        " VALUES (?, 'FAN-IG5-01', 1, 'SUP-A', 38000, 'MQ-313 동시성 검증')",
        (po_id,),
    )


def hold_write_lock(db: Path, bdb, hold_s: float, seq: int, started, errors: list) -> None:
    """백엔드 쪽 쓰기 트랜잭션을 hold_s 초 동안 열어 둔다 (traces INSERT)."""
    try:
        with bdb.connect(db) as con:
            con.execute(
                "INSERT INTO traces (session_id, seq, event_type, payload)"
                " VALUES ('MQ-313', ?, 'tool_call', '{}')",
                (seq,),
            )
            started.set()  # 이 시점에 쓰기 잠금 보유
            time.sleep(hold_s)
    except Exception as exc:  # noqa: BLE001 — 스파이크는 실패를 결과로 보고한다
        errors.append(exc)
        started.set()


# ── 검증 ────────────────────────────────────────────────────────────────────


def run(db: Path) -> None:
    import backend.db as bdb  # noqa: PLC0415
    import mcp_server.db as mdb  # noqa: PLC0415

    # 안전장치: 두 모듈이 실 DB 를 보고 있으면 즉시 중단한다
    if mdb.DB_PATH != db:
        raise SystemExit(f"[중단] mcp_server.db.DB_PATH 가 임시 사본이 아님: {mdb.DB_PATH}")

    # ── ① WAL 전환 (백엔드 쓰기 커넥션)
    with bdb.connect(db) as con:
        mode_backend = con.execute("PRAGMA journal_mode").fetchone()[0]
    check(
        "① backend.connect → journal_mode=wal",
        mode_backend == "wal" and journal_mode(db) == "wal",
        f"커넥션={mode_backend}, 파일={journal_mode(db)}",
    )

    # ── ② WAL 전환 (MCP 쓰기 커넥션)
    with mdb.draft_writer() as con:
        mode_mcp = con.execute("PRAGMA journal_mode").fetchone()[0]
    check(
        "② draft_writer → journal_mode=wal",
        mode_mcp == "wal",
        f"커넥션={mode_mcp}",
    )

    # ── ③ busy_timeout 이 양쪽 모듈 3개 커넥션 모두에 걸렸는가
    with bdb.connect(db) as con:
        bt_backend = con.execute("PRAGMA busy_timeout").fetchone()[0]
    with mdb.draft_writer() as con:
        bt_writer = con.execute("PRAGMA busy_timeout").fetchone()[0]
    with mdb.read_only() as con:
        bt_ro = con.execute("PRAGMA busy_timeout").fetchone()[0]
    check(
        "③ busy_timeout=5000 (backend / draft_writer / read_only)",
        bt_backend == bt_writer == bt_ro == 5000,
        f"backend={bt_backend}, writer={bt_writer}, read_only={bt_ro}",
    )

    # ── ④ 쓰기 트랜잭션이 열린 상태에서 다른 커넥션의 INSERT 가 성공하는가 (핵심)
    started, errors = threading.Event(), []
    hold = 0.6
    t = threading.Thread(
        target=hold_write_lock, args=(db, bdb, hold, 1, started, errors), daemon=True
    )
    t.start()
    started.wait(3)
    t0 = time.perf_counter()
    locked_msg = ""
    try:
        with mdb.draft_writer() as con:
            insert_draft(con, "PO-9001")
        ok_concurrent = True
    except sqlite3.OperationalError as exc:
        ok_concurrent, locked_msg = False, str(exc)
    waited = time.perf_counter() - t0
    t.join(5)
    check(
        "④ 백엔드 쓰기 트랜잭션 중 MCP INSERT 성공 (locked 없음)",
        ok_concurrent and not errors and waited >= hold * 0.4,
        f"대기 {waited:.2f}s (잠금 보유 {hold}s){' / ' + locked_msg if locked_msg else ''}",
    )

    # ── ⑤ 대조군: busy_timeout 이 없으면 같은 시나리오가 실제로 깨진다
    started2, errors2 = threading.Event(), []
    t2 = threading.Thread(
        target=hold_write_lock, args=(db, bdb, hold, 2, started2, errors2), daemon=True
    )
    t2.start()
    started2.wait(3)
    raw = sqlite3.connect(db)
    raw.execute("PRAGMA busy_timeout=0")
    try:
        insert_draft(raw, "PO-9002")
        raw.commit()
        naive_locked = False
        detail = "잠기지 않음 — 이 대조군은 무의미해졌다"
    except sqlite3.OperationalError as exc:
        naive_locked = "locked" in str(exc)
        detail = str(exc)
    finally:
        raw.close()
    t2.join(5)
    check(
        "⑤ 대조군: busy_timeout=0 이면 database is locked (수정이 실제로 일한다)",
        naive_locked,
        detail,
    )

    # ── ⑥ read_only() 가 WAL DB 에서도 열린다
    try:
        with mdb.read_only() as con:
            n = con.execute("SELECT count(*) FROM po_drafts").fetchone()[0]
        ok_ro_open, ro_detail = True, f"po_drafts {n}행 조회"
    except Exception as exc:  # noqa: BLE001
        ok_ro_open, ro_detail = False, f"{type(exc).__name__}: {exc}"
    check("⑥ read_only() 가 WAL DB 에서 열린다", ok_ro_open, ro_detail)

    # ── ⑦ D10 회귀: WAL 이후에도 read_only() 쓰기는 거부
    refused = []
    with mdb.read_only() as con:
        for sql in (
            "INSERT INTO po_drafts (po_id, part_no, qty, supplier_id, unit_price, reason)"
            " VALUES ('PO-9999','FAN-IG5-01',1,'SUP-A',1,'x')",
            "UPDATE po_drafts SET state='approved' WHERE po_id='PO-0117'",
        ):
            try:
                con.execute(sql)
                refused.append(False)
            except sqlite3.OperationalError as exc:
                refused.append("readonly" in str(exc))
    check(
        "⑦ D10 회귀: read_only() 는 WAL 이후에도 쓰기 거부",
        all(refused) and len(refused) == 2,
        f"INSERT/UPDATE 거부={refused}",
    )

    # ── ⑧ read_only() 는 journal_mode 를 건드리지 않는다 (mode=ro 에서는 실패하는 PRAGMA)
    src_ro = function_body(mdb.read_only)  # docstring 제외한 실제 코드
    check(
        "⑧ read_only() 본문에 journal_mode/_enable_wal 없음 (분기 유지)",
        "journal_mode" not in src_ro and "_enable_wal" not in src_ro,
        "read_only 는 _configure(busy_timeout)만 사용",
    )

    # ── ⑨ WAL 전환 실패해도 예외를 던지지 않는다 (mode=ro 커넥션으로 실패 경로 재현)
    plain = Path(db).with_name("delete_mode.db")
    con = sqlite3.connect(plain)
    con.execute("CREATE TABLE t(a)")
    con.commit()
    con.close()
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    mdb.logger.addHandler(handler)
    ro = sqlite3.connect(f"file:{plain.as_posix()}?mode=ro", uri=True)
    try:
        mdb._enable_wal(ro)  # noqa: SLF001 — 실패 경로를 직접 재현한다
        survived = True
    except Exception as exc:  # noqa: BLE001
        survived, records = False, [exc]  # type: ignore[list-item]
    finally:
        ro.close()
        mdb.logger.removeHandler(handler)
    check(
        "⑨ WAL 전환 실패해도 예외 없이 warning 후 진행",
        survived and any(r.levelno == logging.WARNING for r in records),
        f"예외없음={survived}, warning={len(records)}건",
    )

    # ── ⑩ draft_writer UPDATE 차단 트리거 유지 (D10)
    #
    # ★ 예외가 났다는 것만으로 통과시키지 않는다 — **트리거 문구까지 대조**한다.
    #   MQ-706 이 `decisions` 쪽에서 정확히 이 함정에 빠졌다: `sqlite3.Error` 를 통째로 잡으면
    #   트리거를 지워도 **다른 층(CHECK 제약)이 대신 IntegrityError 를 내면서 PASS** 한다.
    #   `po_drafts` 에는 아직 상태 CHECK 가 없어 지금은 마스킹되지 않지만, 나중에 하나만
    #   추가되면 이 검사는 조용히 방어선이 아니게 된다 (reviewer W-8).
    _TRIGGER_MARK = "MCP 도구는 po_drafts 를"
    with mdb.read_only() as con:
        before = con.execute("SELECT state FROM po_drafts WHERE po_id='PO-0117'").fetchone()[0]
    try:
        with mdb.draft_writer() as con:
            con.execute("UPDATE po_drafts SET state='approved' WHERE po_id='PO-0117'")
        blocked_update, msg_u = False, "UPDATE 가 통과했다"
    except sqlite3.Error as exc:
        blocked_update, msg_u = _TRIGGER_MARK in str(exc), str(exc)
    with mdb.read_only() as con:
        after = con.execute("SELECT state FROM po_drafts WHERE po_id='PO-0117'").fetchone()[0]
    check(
        "⑩ draft_writer UPDATE 차단 트리거 유지 (D10 · 트리거 문구까지 대조)",
        blocked_update and before == after,
        f"{msg_u} / state {before}→{after}",
    )

    # ── ⑪ draft_writer DELETE 차단 트리거 유지 (D10)
    try:
        with mdb.draft_writer() as con:
            con.execute("DELETE FROM po_drafts WHERE po_id='PO-0117'")
        blocked_delete, msg_d = False, "DELETE 가 통과했다"
    except sqlite3.Error as exc:
        blocked_delete, msg_d = _TRIGGER_MARK in str(exc), str(exc)  # ⑩ 과 같은 이유
    with mdb.read_only() as con:
        alive = con.execute("SELECT count(*) FROM po_drafts WHERE po_id='PO-0117'").fetchone()[0]
    check(
        "⑪ draft_writer DELETE 차단 트리거 유지 (D10)",
        blocked_delete and alive == 1,
        f"{msg_d} / 잔존={alive}",
    )

    # ── ⑫ D15: 두 모듈이 서로(또는 공용 모듈)를 import 하지 않는다
    b_imports = module_imports(ROOT / "backend" / "db.py")
    m_imports = module_imports(ROOT / "mcp_server" / "db.py")
    check(
        "⑫ D15: backend/db.py ↔ mcp_server/db.py 코드 비공유",
        not any(i.startswith("mcp_server") for i in b_imports)
        and not any(i.startswith("backend") for i in m_imports),
        f"backend={sorted(b_imports)} / mcp={sorted(m_imports)}",
    )


def hold_write_lock_pg(bdb, hold_s: float, seq: int, started, errors: list) -> None:
    """`hold_write_lock` 의 Postgres 판 — `db` 인자가 없다(전역 DATABASE_URL/DB_PATH 를 본다)."""
    try:
        with bdb.connect() as con:
            con.execute(
                "INSERT INTO traces (session_id, seq, event_type, payload)"
                " VALUES ('MQ-313', %s, 'tool_call', '{}')",
                (seq,),
            )
            started.set()
            time.sleep(hold_s)
    except Exception as exc:  # noqa: BLE001
        errors.append(exc)
        started.set()


def run_pg(dsn: str) -> None:
    """Postgres 판 — WAL·busy_timeout 은 SQLite 전용 개념이라 이식 대상이 아니다.

    Postgres 는 MVCC 로 읽기/쓰기를 별도 스냅샷으로 다룬다 — SQLite 의 "파일 전체 쓰기 잠금"
    문제(MQ-313 이 잡으려던 것) 자체가 구조적으로 없다. `mcp_server/db.py`·`backend/db.py`
    의 Postgres 버전에는 `_enable_wal`·`journal_mode`·`busy_timeout` PRAGMA 코드가 아예 없다
    (Sprint 16 MQ-1614 로 전면 교체됨) — 원본 ①②③⑤⑥⑧⑨(WAL 전환·busy_timeout 값·
    `_enable_wal` 실패 경로)는 검증 대상이 사라진 것이지 이식을 빠뜨린 게 아니다.

    이식하는 것: D10 트리거(⑦·⑩·⑪)·D15 경계(⑫)는 DB 엔진과 무관한 계약이라 그대로 검증한다.
    "동시 쓰기가 서로를 막지 않는다"(원본 ④)는 주장은 MVCC 식으로 다시 실측한다(④' 로 대체).
    """
    import backend.db as bdb  # noqa: PLC0415
    import mcp_server.db as mdb  # noqa: PLC0415

    if mdb.DB_PATH != dsn:
        raise SystemExit(f"[중단] mcp_server.db.DB_PATH 가 격리 스키마가 아님: {mdb.DB_PATH}")

    check(
        "①②③⑤⑥⑧⑨ WAL/busy_timeout — 대상 없음 (Postgres 는 MVCC, 파일 잠금 개념이 없다)",
        True,
        "backend/db.py·mcp_server/db.py 의 Postgres 버전에 journal_mode/_enable_wal 코드 자체가 없다",
    )

    # ── ④' MVCC 대조 — 한 커넥션이 traces 에 쓰기 트랜잭션을 열어 둔 동안, 별도 커넥션의
    #    po_drafts INSERT 가 **대기 없이** 성공한다 (SQLite 는 파일 잠금 때문에 대기가
    #    필요했다 — busy_timeout 이 그 대기를 흡수했다. Postgres 는 애초에 대기할 이유가 없다)
    started, errors = threading.Event(), []
    hold = 0.6
    t = threading.Thread(
        target=hold_write_lock_pg, args=(bdb, hold, 1, started, errors), daemon=True
    )
    t.start()
    started.wait(3)
    t0 = time.perf_counter()
    try:
        with mdb.draft_writer() as con:
            insert_draft(con, "PO-9001")
        ok_concurrent, err_msg = True, ""
    except Exception as exc:  # noqa: BLE001
        ok_concurrent, err_msg = False, str(exc)
    waited = time.perf_counter() - t0
    t.join(5)
    check(
        "④' MVCC — traces 쓰기 트랜잭션이 열린 동안 po_drafts INSERT 가 대기 없이 성공",
        ok_concurrent and not errors and waited < hold * 0.5,
        f"대기 {waited:.2f}s (다른 트랜잭션 보유 {hold}s){' / ' + err_msg if err_msg else ''}"
        f"{' / errors=' + str(errors) if errors else ''}",
    )

    # ── ⑦ D10 회귀: read_only() 는 여전히 쓰기를 거부한다
    refused = []
    with mdb.read_only() as con:
        for sql in (
            "INSERT INTO po_drafts (po_id, part_no, qty, supplier_id, unit_price, reason)"
            " VALUES ('PO-9999','FAN-IG5-01',1,'SUP-A',1,'x')",
            "UPDATE po_drafts SET state='approved' WHERE po_id='PO-0117'",
        ):
            try:
                con.execute(sql)
                refused.append(False)
            except sqlite3.Error as exc:
                refused.append("read" in str(exc).lower())
    check(
        "⑦ D10 회귀: read_only() 는 쓰기 거부 (물리적 강제 — default_transaction_read_only)",
        all(refused) and len(refused) == 2,
        f"INSERT/UPDATE 거부={refused}",
    )

    # ── ⑩ draft_writer UPDATE 차단 트리거 유지 (D10 — 문구까지 대조)
    _TRIGGER_MARK = "MCP 도구는 po_drafts 를"
    with mdb.read_only() as con:
        before = con.execute("SELECT state FROM po_drafts WHERE po_id='PO-0117'").fetchone()[0]
    try:
        with mdb.draft_writer() as con:
            con.execute("UPDATE po_drafts SET state='approved' WHERE po_id='PO-0117'")
        blocked_update, msg_u = False, "UPDATE 가 통과했다"
    except sqlite3.Error as exc:
        blocked_update, msg_u = _TRIGGER_MARK in str(exc), str(exc)
    with mdb.read_only() as con:
        after = con.execute("SELECT state FROM po_drafts WHERE po_id='PO-0117'").fetchone()[0]
    check(
        "⑩ draft_writer UPDATE 차단 트리거 유지 (D10 · 트리거 문구까지 대조)",
        blocked_update and before == after,
        f"{msg_u} / state {before}→{after}",
    )

    # ── ⑪ draft_writer DELETE 차단 트리거 유지 (D10)
    try:
        with mdb.draft_writer() as con:
            con.execute("DELETE FROM po_drafts WHERE po_id='PO-0117'")
        blocked_delete, msg_d = False, "DELETE 가 통과했다"
    except sqlite3.Error as exc:
        blocked_delete, msg_d = _TRIGGER_MARK in str(exc), str(exc)
    with mdb.read_only() as con:
        alive = con.execute("SELECT count(*) FROM po_drafts WHERE po_id='PO-0117'").fetchone()[0]
    check(
        "⑪ draft_writer DELETE 차단 트리거 유지 (D10)",
        blocked_delete and alive == 1,
        f"{msg_d} / 잔존={alive}",
    )

    # ── ⑫ D15: 두 모듈이 서로(또는 공용 모듈)를 import 하지 않는다
    b_imports = module_imports(ROOT / "backend" / "db.py")
    m_imports = module_imports(ROOT / "mcp_server" / "db.py")
    check(
        "⑫ D15: backend/db.py ↔ mcp_server/db.py 코드 비공유",
        not any(i.startswith("mcp_server") for i in b_imports)
        and not any(i.startswith("backend") for i in m_imports),
        f"backend={sorted(b_imports)} / mcp={sorted(m_imports)}",
    )


    # ── ⑭⑮⑯ D126: locked_row() 가 실제로 행을 잠그는가 (두 번째 읽기가 대기하는가)
    #
    # **이 축이 없어서 이중 승인 사고가 안 잡혔다** (docs/14_CONCURRENCY.md).
    # 기존 ④' 는 서로 **다른 테이블**에 대한 INSERT 끼리만 봤다 — 같은 행을 두고 다투는
    # 경우를 세우는 검사가 34스위트 어디에도 없었다.
    #
    # ⚠ **두 스레드를 경쟁시켜 "둘 다 성공하는가"를 보는 방식은 쓰지 않는다.** 실제로
    #   그렇게 짰다가 뮤턴트(`FOR UPDATE` 제거)를 **놓치는 것을 실측했다** — SELECT→UPDATE
    #   간격이 짧아 잠금이 없어도 두 스레드가 우연히 어긋나면 그냥 통과한다. 경쟁 검사는
    #   실패를 **가끔** 잡으므로 회귀 가드로 쓸 수 없다.
    #   대신 잠금의 **정의**를 직접 측정한다: 한 트랜잭션이 행을 잡고 있는 동안 두 번째
    #   `locked_row()` 가 **대기하는가**. 잠그면 대기하고, 안 잠그면 즉시 돌아온다 —
    #   타이밍 운이 개입하지 않는다.
    for mark, table, pk in (
        ("⑭", "po_drafts", "po_id"),
        ("⑮", "decisions", "decision_id"),
        ("⑯", "repair_records", "repair_id"),
    ):
        ok, detail = _lock_blocks_second_reader(bdb, table, pk)
        check(f"{mark} D126: {table} locked_row() 가 두 번째 읽기를 대기시킨다", ok, detail)


def _lock_blocks_second_reader(bdb, table: str, pk: str):
    """`txn.locked_row()` 가 행을 실제로 잠그는지 **대기 시간으로** 판정한다.

    T1 이 행을 잡고 `HOLD` 초 버티는 동안 T2 가 같은 행에 `locked_row()` 를 건다.
    - 잠긴다  → T2 는 T1 의 COMMIT 까지 막힌다 (대기 ≈ HOLD)
    - 안 잠긴다 → T2 는 즉시 돌아온다 (대기 ≈ 0)

    판정에 **양성 축**을 함께 건다(CLAUDE.md 부재검사 규칙) — T1 이 실제로 잠금을
    잡았고 T2 가 행을 받아왔음을 함께 확인한다. 그러지 않으면 "T2 가 예외로 죽어서
    빨리 끝난 것"과 "잠금이 없어서 빨리 끝난 것"을 구분하지 못한다.
    """
    from data import txn  # noqa: PLC0415

    HOLD = 0.8
    row_id = _pick_existing_id(bdb, table, pk)
    if row_id is None:
        return False, f"{table} 에 대상 행이 없다 (픽스처 부재 — 검사 무효)"

    holding, release, held_ok = threading.Event(), threading.Event(), []

    def hold_lock() -> None:
        try:
            with bdb.connect() as con:
                r = txn.locked_row(con, table, pk, row_id)
                held_ok.append(r is not None)
                holding.set()
                release.wait(HOLD)      # 트랜잭션을 연 채로 버틴다
        except Exception as exc:        # noqa: BLE001
            held_ok.append(f"T1 실패: {type(exc).__name__}: {exc}")
            holding.set()

    t = threading.Thread(target=hold_lock, daemon=True)
    t.start()
    if not holding.wait(5):
        return False, "T1 이 잠금을 잡지 못했다 (검사 무효)"

    t0 = time.perf_counter()
    try:
        with bdb.connect() as con:
            second = txn.locked_row(con, table, pk, row_id)
        got_row, err = second is not None, ""
    except Exception as exc:            # noqa: BLE001
        got_row, err = False, f"{type(exc).__name__}: {exc}"
    waited = time.perf_counter() - t0
    release.set()
    t.join(5)

    blocked = waited >= HOLD * 0.4
    t1_ok = held_ok == [True]
    return (
        blocked and t1_ok and got_row,
        f"두 번째 읽기 대기 {waited:.2f}s (보유 {HOLD}s · 기준 ≥{HOLD * 0.4:.2f}s) · "
        f"T1={held_ok} · T2 행수신={got_row}{' / ' + err if err else ''}",
    )


def _pick_existing_id(bdb, table: str, pk: str):
    """격리 스키마에 이미 복제돼 있는 행 하나. 새로 INSERT 하지 않는다 —
    테이블마다 NOT NULL·CHECK 가 달라 픽스처가 검사보다 커진다."""
    with bdb.connect() as con:
        r = con.execute(f"SELECT {pk} AS v FROM {table} LIMIT 1").fetchone()
    return r["v"] if r else None


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("동시성 검증 (MQ-313) — WAL+busy_timeout(SQLite) / MVCC(Postgres)\n")

    if dbcompat.USE_POSTGRES:
        import backend.db as bdb  # noqa: PLC0415
        import mcp_server.db as mdb  # noqa: PLC0415

        before_rows = _pg_scalar(pg_isolation.BASE_DATABASE_URL, "SELECT count(*) FROM po_drafts")
        schema, dsn = pg_isolation.create_isolated_schema("db_concurrency")
        bdb.DB_PATH = dsn
        mdb.DB_PATH = dsn
        try:
            run_pg(dsn)
        finally:
            pg_isolation.drop_isolated_schema(schema)
        after_rows = _pg_scalar(pg_isolation.BASE_DATABASE_URL, "SELECT count(*) FROM po_drafts")
        check(
            "⑬ 공유 Postgres po_drafts 행 수 불변 (격리 스키마만 썼다는 증거)",
            before_rows == after_rows,
            f"{before_rows} → {after_rows}행",
        )
    else:
        if not SOURCE_DB.exists():
            raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

        source_stat = (SOURCE_DB.stat().st_mtime_ns, SOURCE_DB.stat().st_size)

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "concurrency.db"
            shutil.copy2(SOURCE_DB, db)

            # 두 모듈 모두 import 시점에 MAINTQ_DB 를 읽는다 — import 보다 먼저 세팅
            os.environ["MAINTQ_DB"] = str(db)
            run(db)

        check(
            "⑬ 원본 data/maintq.db 불변",
            (SOURCE_DB.stat().st_mtime_ns, SOURCE_DB.stat().st_size) == source_stat,
            f"mtime/size 동일 ({source_stat[1]} bytes)",
        )

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 52))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 52))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(f"\n통과 ({len(results)}건) — 동시 쓰기가 잠기지 않고 D10·D15 경계는 그대로다")


if __name__ == "__main__":
    main()
