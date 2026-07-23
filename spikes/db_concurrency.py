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

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


# ── 헬퍼 ────────────────────────────────────────────────────────────────────


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
    with mdb.read_only() as con:
        before = con.execute("SELECT state FROM po_drafts WHERE po_id='PO-0117'").fetchone()[0]
    try:
        with mdb.draft_writer() as con:
            con.execute("UPDATE po_drafts SET state='approved' WHERE po_id='PO-0117'")
        blocked_update, msg_u = False, "UPDATE 가 통과했다"
    except sqlite3.Error as exc:
        blocked_update, msg_u = True, str(exc)
    with mdb.read_only() as con:
        after = con.execute("SELECT state FROM po_drafts WHERE po_id='PO-0117'").fetchone()[0]
    check(
        "⑩ draft_writer UPDATE 차단 트리거 유지 (D10)",
        blocked_update and before == after,
        f"{msg_u} / state {before}→{after}",
    )

    # ── ⑪ draft_writer DELETE 차단 트리거 유지 (D10)
    try:
        with mdb.draft_writer() as con:
            con.execute("DELETE FROM po_drafts WHERE po_id='PO-0117'")
        blocked_delete, msg_d = False, "DELETE 가 통과했다"
    except sqlite3.Error as exc:
        blocked_delete, msg_d = True, str(exc)
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


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("SQLite 동시성 검증 (MQ-313) — WAL + busy_timeout / 임시 DB 사본\n")
    if not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    source_stat = (SOURCE_DB.stat().st_mtime_ns, SOURCE_DB.stat().st_size)

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "concurrency.db"
        shutil.copy2(SOURCE_DB, db)

        # 두 모듈 모두 import 시점에 MAINTQ_DB 를 읽는다 — import 보다 먼저 세팅
        os.environ["MAINTQ_DB"] = str(db)
        sys.path.insert(0, str(ROOT))
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
