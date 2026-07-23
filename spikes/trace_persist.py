# -*- coding: utf-8 -*-
"""trace 영속화 계약 검증 (MQ-301) — A5 가 코드로 강제되는가.

검증 대상: D21(traces 영속화) · D41(UNIQUE(session_id,seq) · token 저장 제외 ·
          users 이관) · D30(payload == SSE data) · D39(UTC) · D43(read_trace 스키마)

핵심 질문 3개
  1. 이벤트를 만들면 **반드시** traces 에 남는가 (저장 없이 발행하는 경로가 없는가)
  2. seq 가 이어지고, 충돌하면 조용히 넘어가지 않는가
  3. 저장이 실패해도 사용자 스트림(이벤트 반환)은 끊기지 않는가

**임시 DB 에서만 돈다** — 스키마는 data/seed.py 의 SCHEMA 를 그대로 써서
DDL 이 갈리면 여기서 먼저 깨지게 한다. data/maintq.db 는 읽지도 쓰지도 않는다(⑫ 검사).

실행:  uv run python spikes/trace_persist.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL_DB = ROOT / "data" / "maintq.db"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def rows(db: Path, sql: str, *args) -> list[tuple]:
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def data_line(frame: str) -> str:
    """SSE 프레임에서 `data:` 라인의 본문만 — payload 와 바이트 동일해야 한다 (D30)."""
    for line in frame.split("\n"):
        if line.startswith("data: "):
            return line[len("data: ") :]
    raise AssertionError(f"data 라인이 없는 프레임: {frame!r}")


def make_db(td: Path) -> Path:
    """seed.py 의 실제 DDL 로 빈 DB 를 만든다 (시드 데이터는 필요 없다)."""
    sys.path.insert(0, str(ROOT / "data"))
    import seed  # noqa: PLC0415

    db = td / "trace.db"
    con = sqlite3.connect(db)
    con.executescript(seed.SCHEMA)
    con.commit()
    con.close()
    return db


def run(db: Path) -> None:
    from backend.agent.trace import TraceWriter, read_trace  # noqa: PLC0415

    # ── ① 이벤트 생성과 저장이 한 몸인가 (A5)
    w = TraceWriter("S-TRACE", db_path=db)
    ev = w.tool_call("lookup_error_code", {"model": "iG5A", "code": "OHt"})
    saved = rows(db, "SELECT seq, event_type, tool, payload FROM traces WHERE session_id='S-TRACE'")
    check(
        "① tool_call 발행 = traces INSERT (A5)",
        ev.event == "tool_call"
        and len(saved) == 1
        and saved[0][:3] == (1, "tool_call", "lookup_error_code"),
        f"이벤트={ev.event}, 저장={len(saved)}행 {saved[0][:3] if saved else None}",
    )

    # ── ② payload 는 SSE data 와 바이트 동일 (D30 — 평가가 두 소스를 대조한다)
    check(
        "② payload == SSE data (바이트 동일, D30)",
        saved[0][3] == data_line(ev.encode()),
        f"payload={saved[0][3][:52]}...",
    )

    # ── ③ seq 이어쓰기: 같은 세션에 새 TraceWriter 가 붙어도 MAX(seq)+1
    w.tool_result("lookup_error_code", "ok", "과열 · FAN-IG5-01", 0.4)
    w2 = TraceWriter("S-TRACE", db_path=db)  # 다음 턴 — 새 인스턴스
    w2.tool_call("search_inventory", {"part_no": "FAN-IG5-01"})
    w2.tool_result("search_inventory", "ok", "재고 1 < 안전재고 3", 0.2)
    seqs = [
        r[0] for r in rows(db, "SELECT seq FROM traces WHERE session_id='S-TRACE' ORDER BY seq")
    ]
    check(
        "③ seq 는 MAX(seq)+1 로 이어쓴다 (턴이 바뀌어도)",
        seqs == [1, 2, 3, 4],
        f"seq={seqs}",
    )

    # ── ④ token 메서드는 존재하지 않는다 (D41 — 버그가 아니라 설계)
    from backend import sse  # noqa: PLC0415

    has_token = hasattr(w, "token")
    try:
        w.emit(sse.token("안녕"))
        rejected = False
    except ValueError:
        rejected = True
    check(
        "④ TraceWriter 에 token 메서드 없음 + emit(token) 거부 (D41)",
        not has_token and rejected,
        f"hasattr(token)={has_token}, emit(token) 거부={rejected}",
    )

    # ── ⑤ 스키마가 token 을 애초에 못 받는다 (CHECK 3종)
    con = sqlite3.connect(db)
    try:
        con.execute(
            "INSERT INTO traces (session_id, seq, event_type, payload)"
            " VALUES ('S-TRACE', 99, 'token', '{}')"
        )
        check("⑤ traces 에 token 직접 INSERT → CHECK 거부", False, "INSERT 가 통과해버림")
    except sqlite3.IntegrityError as exc:
        check("⑤ traces 에 token 직접 INSERT → CHECK 거부", True, str(exc))
    finally:
        con.rollback()
        con.close()

    # ── ⑥ UNIQUE(session_id, seq) 가 실제로 걸려 있는가 (D41)
    con = sqlite3.connect(db)
    try:
        con.execute(
            "INSERT INTO traces (session_id, seq, event_type, payload)"
            " VALUES ('S-TRACE', 1, 'block', '{}')"
        )
        check("⑥ 같은 (session_id, seq) 중복 INSERT → 거부 (D41)", False, "중복이 통과해버림")
    except sqlite3.IntegrityError as exc:
        check("⑥ 같은 (session_id, seq) 중복 INSERT → 거부 (D41)", True, str(exc))
    finally:
        con.rollback()
        con.close()

    # ── ⑦ seq 충돌을 삼키지 않고 재시도해 이어쓴다
    #     writer 가 쓸 차례인 seq 5 를 외부(다른 프로세스 흉내)가 먼저 차지한 상황
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO traces (session_id, seq, event_type, tool, payload)"
        " VALUES ('S-TRACE', 5, 'block', NULL, '{\"from\":\"other\"}')"
    )
    con.commit()
    con.close()
    ev5 = w2.block("safety", {"title": "SAFETY", "text": "10분 이상 대기"})
    after = [
        r[0] for r in rows(db, "SELECT seq FROM traces WHERE session_id='S-TRACE' ORDER BY seq")
    ]
    check(
        "⑦ seq 충돌 → 1회 재시도로 이어씀 (persist_errors 0)",
        after == [1, 2, 3, 4, 5, 6] and w2.persist_errors == 0 and ev5.event == "block",
        f"seq={after}, persist_errors={w2.persist_errors}",
    )

    # ── ⑧ 저장 실패해도 이벤트는 정상 반환 (스트림을 끊지 않는다)
    broken = TraceWriter("S-BROKEN", db_path=db.parent / "no-such-dir" / "x.db")
    ev_b = broken.tool_call("lookup_error_code", {"model": "S100", "code": "OCT"})
    check(
        "⑧ DB 쓰기 실패 → 이벤트는 정상, persist_errors 증가",
        ev_b.event == "tool_call"
        and ev_b.data["tool"] == "lookup_error_code"
        and broken.persist_errors == 1,
        f"event={ev_b.event}, persist_errors={broken.persist_errors}",
    )

    # ── ⑨ read_trace 는 D43 스키마 그대로
    tr = read_trace("S-TRACE", db_path=db)
    keys = set(tr["events"][0]) if tr["events"] else set()
    check(
        "⑨ read_trace = D43 스키마 {session_id,count,events[{seq,event,tool,data,ts}]}",
        set(tr) == {"session_id", "count", "events"}
        and keys == {"seq", "event", "tool", "data", "ts"}
        and tr["count"] == 6
        and [e["seq"] for e in tr["events"]] == [1, 2, 3, 4, 5, 6],
        f"count={tr['count']}, event keys={sorted(keys)}",
    )
    check(
        "⑩ 저장된 data 가 SSE data 와 같은 객체로 복원 (D30)",
        tr["events"][0]["data"] == json.loads(data_line(ev.encode())),
        f"data={tr['events'][0]['data']}",
    )

    # ── ⑪ 없는 세션은 오류가 아니라 count 0 (D43)
    empty = read_trace("NO-SUCH-SESSION", db_path=db)
    check(
        "⑪ 없는 세션 → count 0 (404 아님, D43)",
        empty == {"session_id": "NO-SUCH-SESSION", "count": 0, "events": []},
        str(empty),
    )

    # ── ⑫ 시각은 UTC Z (D39), block 의 tool 컬럼은 NULL
    block_ev = [e for e in tr["events"] if e["event"] == "block"][-1]
    check(
        "⑫ ts 는 UTC 'Z' 표기 · block 의 tool 은 NULL (D39)",
        ev.data["ts"].endswith("Z")
        and block_ev["ts"].endswith("Z")
        and "T" in block_ev["ts"]
        and block_ev["tool"] is None,
        f"event ts={ev.data['ts']}, row ts={block_ev['ts']}, tool={block_ev['tool']}",
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("trace 영속화 계약 검증 — A5·D41 (임시 DB 전용)\n")
    before = REAL_DB.stat().st_mtime_ns if REAL_DB.exists() else None

    with tempfile.TemporaryDirectory() as td:
        db = make_db(Path(td))
        # backend.db 는 import 시점에 MAINTQ_DB 를 읽는다 — import 전에 심는다
        os.environ["MAINTQ_DB"] = str(db)
        sys.path.insert(0, str(ROOT))
        run(db)

    # ── ⑬ 실 DB 불변 (스파이크가 data/maintq.db 를 건드리면 안 된다)
    after = REAL_DB.stat().st_mtime_ns if REAL_DB.exists() else None
    check("⑬ data/maintq.db 불변 (mtime)", before == after, f"{before} == {after}")

    # ── ⑭ 표시명 하드코딩 제거 회귀 (D41 — users 이관)
    src = (ROOT / "backend" / "services" / "po.py").read_text(encoding="utf-8")
    check(
        "⑭ po.py 에 하드코딩 USER_NAMES 없음 · users 조회 (D41)",
        "USER_NAMES" not in src and "FROM users" in src,
        f"USER_NAMES={'USER_NAMES' in src}, users 조회={'FROM users' in src}",
    )

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 40))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail[:70]}")
    print("─" * (width + 40))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(
        f"\n통과 ({len(results)}건) — 발행=저장이 한 몸, seq 충돌은 재시도, 실패해도 스트림은 산다"
    )


if __name__ == "__main__":
    main()
