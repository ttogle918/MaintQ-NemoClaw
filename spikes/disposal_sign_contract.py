# -*- coding: utf-8 -*-
"""MQ-708 — **BLOCKING 우회 처분 0건 · 서명 없는 처분 확정 0건** 전수 회귀 (S9·S10).

사용자 요청 1번의 헤드라인을 **증명**하는 스위트다. `approvals_contract`(MQ-707)가
대표 케이스로 REST 계약을 잠갔다면, 여기서는 **시드 9자산 × 3모드 = 27조합 전수**로
"한 건도 새지 않는다"를 세고, 4층 방어가 **각각 독립으로** 작동하는지를 본다.

────────────────────────────────────────────────────────────────────────────────
★ 4층 — 그리고 **한 층이 다른 층을 가리지 않는다는 것까지** 확인한다
────────────────────────────────────────────────────────────────────────────────
  ① MCP 도구 스키마    `override`·`override_reason`·`reviewed_by` 키 부재 (D81)
  ② MCP 커넥션         `decision_writer` 로 `UPDATE decisions` → TEMP TRIGGER ABORT (D10)
  ③ REST 로직          `sign()` 이 `override_required` 409 (D84)
  ④ DB CHECK           직접 SQL UPDATE → CHECK 위반 (스키마는 우회할 수 없다)

⚠ **MQ-706 이 실제로 빠졌던 함정**: ② 를 `UPDATE … SET state='signed'` 로 검사하면
  트리거를 지워도 통과한다 — ④ 의 CHECK 가 대신 `IntegrityError` 를 내기 때문이다.
  그래서 이 스위트는
    · ② 를 **스키마가 허용하는 전이**(`state='pending'`)로 찌르고,
    · 예외 메시지에 **트리거 문구**가 있는지 대조하며,
    · **같은 SQL 이 일반 커넥션에서는 성공**하는 것까지 확인한다 (거부의 원인이 트리거임을 실증).
  ④ 도 같은 태도다 — 어느 CHECK 가 걸렸는지 **제약식 문구로** 확인하고,
  CHECK 를 벗긴 뮤턴트 테이블에서 **같은 SQL 이 통과**하는 것을 대조한다.
  `sqlite3.Error` 를 통째로 잡고 "예외가 났으니 막혔다"로 넘기지 않는다.

────────────────────────────────────────────────────────────────────────────────
★ 전수 매트릭스는 **3열로 분리한다** (sprint-7 MQ-708 §3열 분리)
────────────────────────────────────────────────────────────────────────────────
    [서명거부 N] [번들불가 M] [서명성공 K]     N + M + K == 27

`law_text_unavailable` 로 draft 조차 만들어지지 않은 조합은 **"우회 성공"이 아니라
"번들 불가"** 다. 두 실패를 한 칸에 뭉개면 게이트가 통과한 것처럼 보인다 —
"막혔다"의 근거가 *방어선*인지 *데이터 공백*인지 구분되지 않기 때문이다.

현재 실 시드에서는 처분 룰 5종이 인용하는 조문이 **전부 `FETCHED`** 이므로
**`M == 0` 이 정상**이다. `M > 0` 이면 그것은 회귀가 아니라 **관측 사실**이며,
⑥ 이 "인용 조문 수집 상태"와 대조해 원인을 지목한다.

★ **위양성 방지**: 비차단 21조합이 **override 없이 서명된다**(K)는 것을 함께 센다.
  전부 막는 검사는 방어선이 아니라 고장이다.

★ **실 DB 는 읽기만 한다.** 전부 임시 폴더의 사본에서 돌리고, 마지막에 실
  `data/maintq.db` 의 mtime·size·`decisions` 행 수 불변을 **계수되는 검사**로 확인한다.

실행:  uv run python spikes/disposal_sign_contract.py
"""

from __future__ import annotations

import inspect
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DB = ROOT / "data" / "maintq.db"
sys.path.insert(0, str(ROOT))
from data import dbcompat, pg_isolation  # noqa: E402


def _open(db):
    """`db` 는 SQLite 사본 Path 이거나 Postgres 격리 스키마/공유 DSN 문자열이다."""
    if dbcompat.USE_POSTGRES:
        return dbcompat.connect_dsn(db)
    return sqlite3.connect(db)

# 이 스위트는 사람 전용 REST + 도구 함수 직접 호출이다 — stdio 서버를 띄울 이유가 없다.
# (실 서버·실 MCP 관통은 `spikes/s10_smoke.py` 소관.)
os.environ["MAINTQ_MCP_AUTOSTART"] = "0"
# ① 이 보는 것은 **full 프로파일에서 등록된 스키마**다 (D69). core 면 도구 자체가 없다.
os.environ["MAINTQ_TOOLS_PROFILE"] = "full"

TECH = {"X-Role": "technician", "X-User": "tech-01"}
MGR = {"X-Role": "manager", "X-User": "mgr-01"}

# 처분일을 고정한다 — 오늘 날짜를 쓰면 `months_since_acquisition` 이 매일 달라져
# 매트릭스의 verdict 분포가 흔들린다 (`approvals_contract.PROBE_DATE` 와 같은 값).
PROBE_DATE = "2026-09-01"

MODES = ("SALE", "SCRAP", "TRANSFER")
OVERRIDE_REASON = "법무 검토 완료 — 회귀 테스트가 기록하는 예외 사유"

# D81 — 도구 스키마에 **있어서는 안 되는** 키. `reviewed_by` 까지 함께 본다(신원 위조 경로).
FORBIDDEN_TOOL_KEYS = {"override", "override_reason", "reviewed_by", "requested_by", "state"}

# 트리거 문구(mcp_server/db.py `_DECISION_GUARDS`). **문구까지 대조**해야 ④ 가 ② 를 가리지 않는다.
TRIGGER_MARK = "MCP 도구는 decisions 를"

# CHECK 제약식의 식별 문구(`data/seed.py §14`). 어느 CHECK 가 걸렸는지 메시지로 확인한다.
CHECK_SIGNED_ELEMENTS = "signed_at IS NOT NULL"
CHECK_BLOCKING_OVERRIDE = "verdict_at_signing IN"
CHECK_OVERRIDE_REASON = "override_reason IS NOT NULL"
# Postgres 는 `pg_get_constraintdef()` 가 `IN (...)` 를 `= ANY (ARRAY[...])` 로 재구성한다 —
# 원문 그대로인 나머지 두 마커와 달리 이것만 별도 형태가 필요하다.
CHECK_BLOCKING_OVERRIDE_PG = "verdict_at_signing = ANY"

MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    """번호는 자동 부여 — 손으로 박으면 검사를 끼워 넣을 때마다 뒤가 전부 밀린다."""
    mark = MARKS[len(results)] if len(results) < len(MARKS) else f"[{len(results) + 1}]"
    results.append((f"{mark} {name}", ok, detail))


# ── DB 헬퍼 ─────────────────────────────────────────────────────────────────────
def rows(db: Path, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
    """행 조회. **실 DB(`SOURCE_DB`)는 반드시 읽기 전용 URI 로 연다.**

    쓰기 가능 커넥션을 열었다 닫으면 SQLite 가 WAL 체크포인트를 수행해 **본 파일의 mtime·size 가
    바뀐다** — 이 스위트의 마지막 검사가 바로 그 불변을 단언하므로, 자기 행위로 자기 게이트를
    깨뜨리는 플래키 레드가 된다(reviewer 경고 1). 임시 사본은 쓰기 가능해도 무해하다.
    """
    if dbcompat.USE_POSTGRES:
        con = dbcompat.connect_dsn(db)
    else:
        uri = db.resolve() == SOURCE_DB.resolve()
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) if uri else _open(db)
    con.row_factory = sqlite3.Row
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def scalar(db: Path, sql: str, args: tuple = ()) -> object:
    r = rows(db, sql, args)
    return r[0][0] if r else None


def probe_sql(con: sqlite3.Connection, sql: str) -> tuple[bool, str]:
    """SAVEPOINT 안에서 SQL 을 실제로 시도하고 되돌린다. `(거부됐는가, 메시지)`.

    `sqlite3.IntegrityError` 만 "거부"로 센다 — 다른 예외(문법 오류 등)를 거부로 세면
    검사가 자기도 모르게 통과한다.
    """
    con.execute("SAVEPOINT probe")
    try:
        con.execute(sql)
        return False, "통과해버림"
    except sqlite3.IntegrityError as exc:
        return True, " ".join(str(exc).split())
    finally:
        con.execute("ROLLBACK TO probe")
        con.execute("RELEASE probe")


def _check_marker_hit(msg: str, marker: str, db=None, pg_marker: str | None = None) -> bool:
    """`msg` 에 CHECK 식별 문구가 있는가.

    SQLite 는 예외 메시지에 CHECK 절 **본문**을 그대로 담는다 — 부분 문자열 대조로 충분하다.
    Postgres 는 제약식 **이름**만 담는다(예: `violates check constraint "decisions_check2"`) —
    본문은 `pg_get_constraintdef()` 로 그 이름을 다시 조회해야 나온다. `pg_marker` 는 Postgres 가
    절을 재구성하며 문구를 바꾸는 경우(`IN (...)` → `= ANY (ARRAY[...])`)를 위한 대체 마커다.
    """
    if not dbcompat.USE_POSTGRES:
        return marker in msg
    m = re.search(r'violates check constraint "(\w+)"', msg)
    if not m:
        return False
    con = _open(db)
    try:
        rows_ = con.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s",
            (m.group(1),),
        ).fetchall()
    finally:
        con.close()
    if not rows_:
        return False
    defn = rows_[0][0]
    return marker in defn or bool(pg_marker and pg_marker in defn)


# ── 전수 매트릭스 ───────────────────────────────────────────────────────────────
class Cell:
    """매트릭스 한 칸. **어떤 경우에도 살아남는다** — 도구가 error 를 내도 행으로 남는다."""

    def __init__(self, asset: str, mode: str) -> None:
        self.asset, self.mode = asset, mode
        self.bucket = "미분류"  # 서명거부 | 번들불가 | 서명성공 | 미분류
        self.verdict: str | None = None
        self.decision_id: str | None = None
        self.hash_before: str | None = None
        self.hash_after: str | None = None
        self.note = ""
        self.failures: list[str] = []

    @property
    def label(self) -> str:
        return f"{self.asset}/{self.mode}"

    def fail(self, msg: str) -> None:
        self.failures.append(f"{self.label}: {msg}")


def build_matrix(client, db: Path, assets: list[str], blocking: tuple[str, ...]) -> list[Cell]:
    """9자산 × 3모드 전수. draft 생성 → (차단이면) 서명 거부 확인 → override 서명."""
    from mcp_server.tools.generate_disposal_document import (  # noqa: PLC0415
        generate_disposal_document,
    )

    cells: list[Cell] = []
    for asset in assets:
        for mode in MODES:
            cell = Cell(asset, mode)
            cells.append(cell)
            try:
                _run_cell(client, db, cell, generate_disposal_document, blocking)
            except Exception as exc:  # noqa: BLE001 — 표가 트레이스백으로 죽지 않게 한다
                cell.bucket = "미분류"
                cell.note = f"{type(exc).__name__}: {exc}"
                cell.fail(f"예외 {type(exc).__name__}: {exc}")
    return cells


def _run_cell(client, db: Path, cell: Cell, make_doc, blocking: tuple[str, ...]) -> None:
    res = make_doc(
        reason=f"{cell.label} 전수 회귀 (MQ-708)",
        asset_id=cell.asset,
        disposal_mode=cell.mode,
        disposal_date=PROBE_DATE,
    )

    # ── 번들 불가 — draft 가 아예 만들어지지 않은 조합. **우회 성공이 아니다.**
    if res.get("status") != "ok":
        reason = res.get("reason")
        if reason == "law_text_unavailable":
            cell.bucket = "번들불가"
            cell.note = "law_text_unavailable"
            return
        cell.note = f"도구 실패 {reason}: {str(res.get('message'))[:60]}"
        cell.fail(cell.note)
        return

    cell.decision_id = res["decision_id"]
    cell.verdict = res["verdict_at_signing"]

    # 도구 출력과 저장 행 **양쪽**에서 override=0 을 본다 (출력만 보면 저장이 다를 수 있다)
    row = rows(db, "SELECT * FROM decisions WHERE decision_id=?", (cell.decision_id,))[0]
    cell.hash_before = row["bundle_hash"]
    if res.get("override") is not False or row["override"] != 0 or row["state"] != "draft":
        cell.fail(
            f"draft 계약 위반 output.override={res.get('override')} "
            f"row.override={row['override']} state={row['state']}"
        )
    if row["override_reason"] is not None or row["signed_at"] is not None:
        cell.fail("draft 인데 override_reason/signed_at 이 채워져 있다")

    r = client.post(f"/api/decisions/{cell.decision_id}/submit", headers=TECH)
    if r.status_code != 200 or r.json().get("state") != "pending":
        cell.fail(f"submit {r.status_code} state={r.json().get('state')}")
        cell.note = f"submit {r.status_code}"
        return

    if cell.verdict in blocking:
        # ── 차단 판정: override 없는 서명은 **반드시** 409 여야 한다
        plain = client.post(f"/api/decisions/{cell.decision_id}/sign", json={}, headers=MGR)
        body = plain.json() if plain.headers.get("content-type", "").startswith("application/json") else {}
        if plain.status_code == 200:
            # 실제로 뚫렸다 — 이 한 줄이 "BLOCKING 우회 0건"의 반증이다
            cell.fail(f"우회 성공! sign(no override) → 200 state={body.get('state')}")
            cell.note = "우회 200"
            return
        if plain.status_code != 409 or body.get("reason") != "override_required":
            # 다른 층이 대신 잡았을 수도 있다 — **초록으로 넘기지 않는다** (층③ 이 죽은 상태)
            cell.fail(f"층③ 게이트 이상 → {plain.status_code}/{body.get('reason')}")
            cell.note = f"층③ 이상 {plain.status_code}"
            return
        cell.bucket = "서명거부"

        # 예외 적용 경로는 살아 있어야 한다 (D63 — 막는 게 아니라 기록한다)
        ovr = client.post(
            f"/api/decisions/{cell.decision_id}/sign",
            json={"override": True, "override_reason": OVERRIDE_REASON},
            headers=MGR,
        )
        after = rows(db, "SELECT * FROM decisions WHERE decision_id=?", (cell.decision_id,))[0]
        cell.hash_after = after["bundle_hash"]
        if ovr.status_code != 200 or after["state"] != "signed" or after["override"] != 1:
            cell.fail(
                f"override 서명 실패 {ovr.status_code} state={after['state']} "
                f"override={after['override']}"
            )
        if (after["override_reason"] or "").strip() != OVERRIDE_REASON:
            cell.fail(f"override_reason 미저장: {after['override_reason']!r}")
        cell.note = f"409 → override 서명 {ovr.status_code}"
        return

    # ── 비차단 판정: override 없이 서명돼야 한다 (전부 막는 검사는 방어선이 아니다)
    #
    #   ★ 예외를 잡아 **FAIL 행**으로 바꾼다. 층③(REST 게이트)이 죽어 차단 판정을 비차단으로
    #     흘리면 층④(DB CHECK)가 `IntegrityError` 를 던지는데, 그대로 두면 트레이스백으로 죽어
    #     **표가 통째로 사라진다** — 진단 정보가 가장 필요한 순간에. 어느 층이 잡았는지도
    #     detail 에 남긴다(층 독립성의 증거다).
    try:
        ok = client.post(f"/api/decisions/{cell.decision_id}/sign", json={}, headers=MGR)
    except Exception as exc:  # noqa: BLE001
        cell.fail(f"비차단 서명이 예외로 죽었다 — 하위 층이 대신 막았다: {type(exc).__name__}: {exc}")
        cell.note = f"예외 {type(exc).__name__}"
        return
    after = rows(db, "SELECT * FROM decisions WHERE decision_id=?", (cell.decision_id,))[0]
    cell.hash_after = after["bundle_hash"]
    if ok.status_code != 200 or after["state"] != "signed" or after["override"] != 0:
        cell.fail(
            f"비차단인데 서명 실패 {ok.status_code}/{ok.json().get('reason')} "
            f"state={after['state']}"
        )
        cell.note = f"sign {ok.status_code}/{ok.json().get('reason')}"
        return
    cell.bucket = "서명성공"
    cell.note = "override 없이 200"


def print_matrix(cells: list[Cell], counts: dict[str, int]) -> None:
    by_key = {(c.asset, c.mode): c for c in cells}
    assets = sorted({c.asset for c in cells})
    width = max(len(a) for a in assets)
    print("\n── 전수 매트릭스 (9자산 × 3모드 = 27조합) ─────────────────────────────")
    print(f"  {'자산':<{width}}  " + "  ".join(f"{m:<34}" for m in MODES))
    for asset in assets:
        cols = []
        for mode in MODES:
            c = by_key[(asset, mode)]
            cols.append(f"{c.verdict or '-':<19}{c.bucket:<8}{'FAIL' if c.failures else ''}")
        print(f"  {asset:<{width}}  " + "  ".join(f"{c:<34}" for c in cols))
    print(
        f"\n  [서명거부 {counts['서명거부']}] [번들불가 {counts['번들불가']}] "
        f"[서명성공 {counts['서명성공']}]  (미분류 {counts['미분류']})"
        f"  합계 {sum(counts.values())} / 대상 {len(cells)}조합\n"
    )


# ── 본체 ────────────────────────────────────────────────────────────────────────
def _db_catalog(db: Path) -> tuple[dict, dict]:
    """계층 1·2 를 **DB 사본**에서 한 번만 로드한다.

    ★ 제품 경로(`build_evidence_bundle`·`rebuild_bundle`)는 DB 사본으로 판정한다(W5 원천 일원화).
      검사 코드가 파일 사본(`load_laws()`)을 쓰면 **W5 가 없애려던 이원화를 테스트 쪽에 다시 들여온다** —
      두 사본이 어긋나는 순간 방어선과 무관한 이유로 레드가 나고 원인을 읽어 내기 어렵다.
      한 번만 로드해 주입하는 부수 효과로 조문 JSON 재파싱 수천 회도 사라진다.
    """
    from data.rules import engine  # noqa: PLC0415

    with _open(db) as con:
        con.row_factory = sqlite3.Row
        laws = engine.load_laws_from_db(con)
        return laws, engine.load_rules_from_db(con, laws)


def _find_verdict_combo(
    db: Path, verdict: str, catalog: tuple[dict, dict]
) -> tuple[tuple[str, str, str] | None, int]:
    """해당 verdict 를 실제로 내는 `(asset, mode, disposal_date)` 를 시드에서 찾는다.

    ⛔ 값을 하드코딩하지 않는다 — 시드 취득일이 바뀌면 조용히 엉뚱한 조합을 시험하게 된다.
    엔진을 직접 돌려 **실제로 그 verdict 가 나오는** 조합만 돌려준다.
    `(조합|None, 시도한 후보 수)` — 못 찾았을 때 몇 개를 봤는지 남겨야 진단이 된다.
    """
    from data.rules import engine  # noqa: PLC0415
    from data.seed import _shift_months  # noqa: PLC0415

    laws, rules = catalog
    tried = 0
    with _open(db) as con:
        con.row_factory = sqlite3.Row
        for row in con.execute("SELECT * FROM assets ORDER BY asset_id").fetchall():
            if not row["acquired_at"]:
                continue
            base = date.fromisoformat(row["acquired_at"])
            # 경계 구간(D62)은 자산이 아니라 **처분일**이 만든다 — 취득 후 개월수를 훑는다.
            for months in range(1, 61):
                when = str(_shift_months(base, months))
                for mode in MODES:
                    tried += 1
                    facts = engine.build_facts(row, disposal_mode=mode, disposal_date=when)
                    out = engine.check_disposal_blockers(facts, laws=laws, rules=rules)
                    if out["verdict"] == verdict:
                        return (row["asset_id"], mode, when), tried
    return None, tried


def _prove_blocking(client, db: Path, verdict: str, asset: str, mode: str, when: str) -> str:
    """차단 판정 1건을 도구 → submit → sign(무override) → sign(override) 로 관통시킨다.

    매트릭스 셀과 **같은 계약**을 본다: 무override 는 409 `override_required`,
    override 는 200 + `override=1` + 사유 저장. 한 줄 요약을 돌려준다(끝이 `OK` 면 통과).
    """
    from mcp_server.tools.generate_disposal_document import generate_disposal_document  # noqa: PLC0415

    res = generate_disposal_document(
        reason=f"{verdict} 커버리지 프로브 (MQ-708 후속)",
        asset_id=asset,
        disposal_mode=mode,
        disposal_date=when,
    )
    label = f"{verdict}({asset}/{mode}/{when})"
    if res.get("status") != "ok":
        return f"{label}: draft 실패 {res.get('reason')}"
    if res.get("verdict_at_signing") != verdict:
        return f"{label}: verdict 불일치 {res.get('verdict_at_signing')}"
    did = res["decision_id"]

    sub = client.post(f"/api/decisions/{did}/submit", headers=TECH)
    if sub.status_code != 200:
        return f"{label}: submit {sub.status_code}"

    # 예외는 문자열로 접는다 — 표가 죽지 않게 한다 (`_run_cell` 과 같은 이유).
    try:
        plain = client.post(f"/api/decisions/{did}/sign", json={}, headers=MGR)
    except Exception as exc:  # noqa: BLE001
        return f"{label}: sign 이 예외로 죽었다(하위 층이 대신 막음) {type(exc).__name__}"
    body = plain.json() if plain.headers.get("content-type", "").startswith("application/json") else {}
    if plain.status_code == 200:
        return f"{label}: ★우회 성공! sign(no override) → 200"
    if plain.status_code != 409 or body.get("reason") != "override_required":
        return f"{label}: 층③ 이상 {plain.status_code}/{body.get('reason')}"

    ovr = client.post(
        f"/api/decisions/{did}/sign",
        json={"override": True, "override_reason": OVERRIDE_REASON},
        headers=MGR,
    )
    after = rows(db, "SELECT * FROM decisions WHERE decision_id=?", (did,))[0]
    if ovr.status_code != 200 or after["state"] != "signed" or after["override"] != 1:
        return f"{label}: override 서명 실패 {ovr.status_code}/{after['state']}"
    return f"{label}: 409 → override 200 OK"


def _run_coverage_probes(
    client, db: Path, blocking: tuple[str, ...], blocked_cells: list, all_failures: list[str]
) -> tuple[tuple[str, ...], bool, set[str], list[str], list[str]]:
    """매트릭스가 못 덮은 차단 어휘를 별도 프로브로 채운다. 실패는 `all_failures` 에 밀어 넣는다.

    ⛔ **기대치를 `dec_svc.BLOCKING_VERDICTS` 에서 파생하지 않는다.** 그러면 그 튜플을 줄이는
      순간 증명할 대상도 같이 줄어 검사가 **공허하게 통과**한다. 실제로 그렇게 만들어 봤다 —
      `NON_BLOCKING_VERDICTS` 에 `HOLD` 를 넣자 "미커버 없음"이 되어 PASS 했다.
      테스트 오라클은 정의상 검증 대상에서 독립해야 한다.
    """
    from data.rules import engine as _engine  # noqa: PLC0415

    expected_blocking = tuple(v for v in _engine.VERDICTS if v not in ("CONDITIONAL", "CLEAR"))
    vocab_drift = tuple(blocking) != expected_blocking
    covered = {c.verdict for c in blocked_cells}
    uncovered = [v for v in expected_blocking if v not in covered]
    extra_proofs: list[str] = []

    if vocab_drift:
        extra_proofs.append(
            f"차단 어휘 드리프트: 제품={list(blocking)} ≠ 엔진 파생={list(expected_blocking)}"
        )
        all_failures.append(extra_proofs[-1])

    catalog = _db_catalog(db)  # 제품과 **같은 원천**(DB 사본)으로 조합을 고른다 — W5 재발 방지
    for verdict in uncovered:
        combo, tried = _find_verdict_combo(db, verdict, catalog)
        if combo is None:
            msg = f"{verdict}: 시드에서 도달 불가 — 커버리지 공백 (후보 {tried}종 시도)"
            extra_proofs.append(msg)
            all_failures.append(msg)
            continue
        asset, mode, when = combo
        outcome = _prove_blocking(client, db, verdict, asset, mode, when)
        extra_proofs.append(outcome)
        if not outcome.endswith("OK"):
            all_failures.append(outcome)
    return expected_blocking, vocab_drift, covered, uncovered, extra_proofs


def run(client, db: Path) -> None:
    import backend.services.decisions as dec_svc  # noqa: PLC0415
    import mcp_server.db as mcp_db  # noqa: PLC0415

    blocking = dec_svc.BLOCKING_VERDICTS
    assets = [r[0] for r in rows(db, "SELECT asset_id FROM assets ORDER BY asset_id")]

    cells = build_matrix(client, db, assets, blocking)
    counts = {k: 0 for k in ("서명거부", "번들불가", "서명성공", "미분류")}
    for c in cells:
        counts[c.bucket] += 1
    print_matrix(cells, counts)

    all_failures = [f for c in cells for f in c.failures]
    n, m, k = counts["서명거부"], counts["번들불가"], counts["서명성공"]

    # ① 3열 분리 항등식. "우회 성공"과 "번들 불가"를 한 칸에 뭉개지 않는다.
    check(
        "전수 매트릭스 3열 분리 — [서명거부 N][번들불가 M][서명성공 K] · N+M+K == 27",
        n + m + k == len(cells) == 27 and counts["미분류"] == 0,
        f"N={n} · M={m} · K={k} · 미분류={counts['미분류']} · 대상={len(cells)}조합"
        + (f" · 미분류 조합={[c.label for c in cells if c.bucket == '미분류']}" if counts["미분류"] else ""),
    )

    blocked_cells = [c for c in cells if c.verdict in blocking]

    # ── 커버리지 프로브를 **검사 ② 보다 먼저 실행한다** (reviewer 경고 2) ────────────
    #   ② 는 "BLOCKING 우회 0건" 이라는 **헤드라인 이름을 단 검사**다. 프로브를 나중에 돌리면
    #   프로브가 실제 우회(`★우회 성공! → 200`)를 발견해도 ② 는 이미 스냅샷한 `all_failures` 로
    #   `우회 성공 0건` 초록을 찍는다 — 헤드라인 카운터가 3종 중 2종만 세는 상태가 된다.
    #   실행을 앞으로 당겨 ② 가 프로브 결과까지 세게 한다. 검사 자체는 아래 ②-b 에 그대로 둔다.
    expected_blocking, vocab_drift, covered, uncovered, extra_proofs = _run_coverage_probes(
        client, db, blocking, blocked_cells, all_failures
    )

    # ② **BLOCKING 우회 0건** — 차단 판정 조합에서 override 없는 서명이 한 건도 200 이 아니다
    bypass = [f for f in all_failures if "우회 성공" in f]
    gate_off = [f for f in all_failures if "층③ 게이트 이상" in f]
    # 차단 조합인데 "서명거부"로 분류되지 못한 건 = 409 override_required 를 못 받은 건이다.
    # (예외로 죽은 경우까지 포함한다 — 다른 층이 대신 잡았어도 층③ 이 죽은 것은 사실이다.)
    unresolved = [c.label for c in blocked_cells if c.bucket != "서명거부"]
    check(
        "BLOCKING 우회 0건 — 차단 판정 조합 전부 override 없는 서명이 409 override_required",
        not bypass and not gate_off and not unresolved and len(blocked_cells) > 0,
        f"차단 조합 {len(blocked_cells)}건({sorted({c.verdict for c in blocked_cells})}) · "
        f"우회 성공 {len(bypass)}건 · 층③ 이상 {len(gate_off)}건 · "
        f"409 를 못 받은 조합 {len(unresolved)}건"
        + (f" {unresolved}" if unresolved else " (전부 0건)"),
    )

    # ②-b **BLOCKING_VERDICTS 3종이 전부 런타임으로 증명됐는가** ─────────────────
    #
    #   ★ 전수 매트릭스는 `PROBE_DATE` 한 날짜로 돌아 `BLOCKED`·`INSUFFICIENT_FACTS` 두 종만
    #     발화시킨다. **`HOLD` 는 27조합 어디에서도 나오지 않는다.**
    #     "BLOCKING 우회 0건" 이라고 말하면서 3종 중 2종만 실제로 막아 본 상태였다 —
    #     DB CHECK 가 화이트리스트라 구조적으로는 fail-closed 지만 **그건 코드를 읽은 결론**이지
    #     실행한 증거가 아니다. 이 프로젝트에서 반복된 실패가 정확히 그 간극이었다.
    #
    #   `HOLD` 는 `TAX-CREDIT-2Y` 의 경계 구간(`months_since_acquisition ∈ [22,26]`, D62)에서 나온다.
    #   즉 자산이 아니라 **처분일**이 결정한다 — 취득 후 22~26개월인 날짜를 골라 발화시킨다.
    #   이 검사는 `BLOCKING_VERDICTS` 를 순회하므로 **4번째 차단 어휘가 생기면 커버리지를 자동으로 요구**한다.
    #   실행은 위(② 앞)에서 이미 했다 — 여기서는 판정만 한다.
    #   ⚠ 남은 우회 여지 하나: `engine.VERDICTS` 에서 `HOLD` 를 지우면 제품 튜플과 이 기대치가
    #     **같이** 줄어 공허하게 통과한다. 그 경로는 스파이크가 아니라 제품 두 장치가 막는다 —
    #     `backend/services/decisions.py` 의 모듈 레벨 `assert` 와 `data/seed.py verify() ㉑`.
    #     ⛔ `assert` 는 `python -O` 에서 사라진다는 것을 알고 있을 것.
    check(
        "차단 어휘 3종이 **전부 런타임으로** 차단됐다 (매트릭스는 고정 처분일이라 HOLD 를 "
        "못 낸다 — 별도 프로브로 채운다. 기대치는 엔진에서 독립 파생)",
        not vocab_drift and all(p.endswith("OK") for p in extra_proofs),
        f"기대 차단 어휘 {list(expected_blocking)} · 매트릭스 커버 {sorted(covered)} · "
        f"미커버 {uncovered or '없음'}"
        + (f" → {'; '.join(extra_proofs)}" if extra_proofs else ""),
    )

    # ③ 예외 경로는 살아 있다 (D63 — 시스템은 막는 게 아니라 기록한다)
    ovr_fail = [f for f in all_failures if "override" in f and "우회 성공" not in f]
    signed_ovr = rows(
        db, "SELECT decision_id, override_reason FROM decisions WHERE state='signed' AND override=1"
    )
    # ②-b 의 커버리지 프로브도 override 서명을 1건씩 남긴다 — 기대치에 더한다.
    # ⛔ `>=` 로 느슨하게 풀지 않는다. **정확히 일치**해야 "override 서명은 차단 판정에서만 나온다"가
    #    성립한다 — 느슨하게 두면 비차단 조합이 override 로 서명되는 회귀를 못 잡는다.
    probe_signed = sum(1 for p in extra_proofs if p.endswith("OK"))
    expected_ovr = len(blocked_cells) + probe_signed
    check(
        "차단 조합 override 서명 → 200 · override=1 · 사유 저장 (D63 — 막지 않고 기록한다)",
        not ovr_fail
        and len(signed_ovr) == expected_ovr
        and all((r["override_reason"] or "").strip() for r in signed_ovr),
        f"override 서명 {len(signed_ovr)}건 / 기대 {expected_ovr}건"
        f"(차단 조합 {len(blocked_cells)} + 커버리지 프로브 {probe_signed}) · "
        f"실패={[f[:80] for f in ovr_fail] or '없음'}",
    )

    # ④ 위양성 방지 — 비차단 조합은 override 없이 서명된다. 전부 막는 검사는 고장이다.
    non_block_fail = [f for f in all_failures if "비차단" in f]
    check(
        "위양성 방지 — 비차단 조합은 override 없이 200 (전부 막는 검사가 아님)",
        not non_block_fail and k > 0,
        f"K={k}건 · 실패={non_block_fail or '없음'}",
    )

    # ⑤ draft 계약 — 27조합 전부 `override=0`·`state='draft'` 로 태어난다 (D81)
    draft_fail = [f for f in all_failures if "draft" in f]
    check(
        "모든 조합의 draft 가 override=0 · state='draft' 로 생성 (D81 — 도구는 예외를 만들 수 없다)",
        not draft_fail,
        f"위반={draft_fail or '없음'} · 생성된 decisions {scalar(db, 'SELECT count(*) FROM decisions')}건",
    )

    # D63 — 차단 판정이 draft 생성을 막지 않는다. **막으면 기록만 사라진다.**
    blocked_drafts = [c for c in blocked_cells if c.decision_id]
    check(
        "D63 — 차단 판정 조합도 draft 가 전부 생성된다 (시스템은 막지 않고 기록한다)",
        len(blocked_drafts) == len(blocked_cells) and len(blocked_cells) > 0,
        f"차단 조합 {len(blocked_cells)}건 중 draft 생성 {len(blocked_drafts)}건 "
        f"({[c.label for c in blocked_cells]})",
    )

    # 서명은 **근거를 바꾸지 않는다** — bundle_hash 가 draft 시점과 같아야 서명이 가리키는
    # 근거가 확정된다. 바뀌면 "서명한 것"과 "저장된 것"이 갈린다.
    hash_moved = [
        c.label for c in cells if c.decision_id and c.hash_after and c.hash_after != c.hash_before
    ]
    check(
        "서명 전후 bundle_hash 불변 — 서명이 근거를 갈아치우지 않는다 (D84)",
        not hash_moved and any(c.hash_after for c in cells),
        f"해시 변동 {len(hash_moved)}건{hash_moved if hash_moved else ''} · "
        f"대조한 조합 {sum(1 for c in cells if c.hash_after)}건",
    )

    # 도구가 `draft_writer`(po_drafts 전용 트리거)로 `decisions` 를 쓰면 **잠금 없이 쓰는 것**이
    # 된다 — 층② 가 조용히 사라지는 경로다. 소스에서 커넥션 선택을 못 박는다.
    import mcp_server.tools.generate_disposal_document as doc_mod  # noqa: PLC0415

    doc_src = inspect.getsource(doc_mod)
    uses_decision_writer = "with decision_writer()" in doc_src
    uses_draft_writer = "with draft_writer(" in doc_src
    check(
        "층② 전제 — 도구가 decision_writer 로 쓴다 (draft_writer 재사용 = 잠금 없는 쓰기)",
        uses_decision_writer and not uses_draft_writer,
        f"with decision_writer()={uses_decision_writer} · with draft_writer(={uses_draft_writer}",
    )

    # ⑥ **번들불가 M 의 원인 지목** — 인용 조문 수집 상태와 대조한다.
    #    M>0 은 회귀가 아니라 관측이다. 다만 "왜 M 이 그 값인지"를 말하지 못하면
    #    번들불가가 방어선 실패를 가릴 수 있다.
    #    ⚠ **단방향으로만 단언한다** (reviewer 경고 3): `미수집 0건 ⇒ M==0` 은 옳지만
    #      역방향(`미수집 있음 ⇒ M>0`)은 **틀리다.** `law_text_unavailable` 은
    #      *4버킷에 실린 findings 의 `law_refs`* 만 게이트하므로(MQ-705 §laws[] 범위),
    #      아무 룰도 발화시키지 않는 조문이 미수집이면 M==0 이 정상이다.
    #      역방향까지 요구하면 조문 하나만 더 인용돼도 **방어선과 무관한 레드**가 난다.
    #    ⚠ `cited` 는 rule_id 별 **최신 버전만** 본다 — `rules` 는 append-only(D60)라
    #      전 행을 훑으면 로드되지도 않는 구버전의 `law_refs` 까지 섞인다.
    cited = {
        rid
        for r in rows(
            db,
            "SELECT r.law_refs FROM rules r JOIN "
            "(SELECT rule_id, MAX(rule_version) v FROM rules GROUP BY rule_id) m "
            "ON r.rule_id=m.rule_id AND r.rule_version=m.v",
        )
        for rid in json.loads(r["law_refs"] or "[]")
    }
    unfetched = sorted(
        r["law_ref_id"]
        for r in rows(db, "SELECT law_ref_id, fetch_status, text_hash FROM law_refs")
        if r["law_ref_id"] in cited and (r["fetch_status"] != "FETCHED" or not r["text_hash"])
    )
    check(
        "번들불가 M 이 인용 조문 수집 상태와 정합 (미수집 0건 ⇒ M==0 · 단방향)",
        bool(unfetched) or m == 0,
        f"M={m} · 최신 버전 룰이 인용한 조문 {len(cited)}건 중 미수집={unfetched or '없음'}"
        + (" — 미수집이 있으면 M>0 을 요구하지 않는다(발화하지 않는 룰의 조문일 수 있다)" if unfetched else ""),
    )

    # ── 층 ① MCP 도구 스키마 ────────────────────────────────────────────────────
    # 두 겹으로 본다: **FastMCP inputSchema**(서버 래퍼) + **도구 함수 시그니처**(도구 파일).
    # 한쪽만 보면 다른 파일에 파라미터를 추가하는 뮤턴트를 놓친다.
    import asyncio  # noqa: PLC0415

    from mcp_server.server import mcp as fastmcp  # noqa: PLC0415
    from mcp_server.tools.generate_disposal_document import (  # noqa: PLC0415
        generate_disposal_document,
    )

    listed = asyncio.run(fastmcp.list_tools())
    doc_tool = next((t for t in listed if t.name == "generate_disposal_document"), None)
    schema_props = set((doc_tool.inputSchema.get("properties") or {})) if doc_tool else set()
    sig_params = set(inspect.signature(generate_disposal_document).parameters)
    leaked = sorted((schema_props | sig_params) & FORBIDDEN_TOOL_KEYS)
    check(
        "층① 도구 스키마·함수 시그니처 어디에도 override/override_reason/reviewed_by 없음 (D81)",
        doc_tool is not None and not leaked,
        f"도구 등록={doc_tool is not None} · 스키마 키={sorted(schema_props)} · "
        f"시그니처={sorted(sig_params)} · 금지 키 노출={leaked or '없음'}",
    )

    # ── 층 ② MCP 커넥션 (TEMP TRIGGER) ──────────────────────────────────────────
    # ⚠ **스키마가 허용하는 전이**로 찌른다. `state='signed'` 로 찌르면 트리거를 지워도
    #   층④ CHECK 가 대신 거부해 검사가 위양성으로 통과한다 (MQ-706 실측 함정).
    probe_id = _make_probe_draft(db, "AST-L3-CONV", "SALE")
    if probe_id is None:
        check(
            "층②③④ 프로브 draft 생성 (AST-L3-CONV/SALE)",
            False,
            "프로브 draft 를 만들지 못해 층②③④ 검사를 실행하지 못했다 — 통과가 아니라 미실행이다",
        )
        return
    saved_path = mcp_db.DB_PATH
    mcp_db.DB_PATH = db
    trigger_msgs: dict[str, tuple[bool, str]] = {}
    try:
        with mcp_db.decision_writer() as con:
            trigger_msgs["UPDATE(state='pending')"] = probe_sql(
                con, f"UPDATE decisions SET state='pending' WHERE decision_id='{probe_id}'"
            )
            trigger_msgs["DELETE"] = probe_sql(
                con, f"DELETE FROM decisions WHERE decision_id='{probe_id}'"
            )
    finally:
        mcp_db.DB_PATH = saved_path

    check(
        "층② decision_writer 의 UPDATE·DELETE 가 TRIGGER 로 ABORT — **문구까지 대조** (D10)",
        all(ok for ok, _ in trigger_msgs.values())
        and all(TRIGGER_MARK in msg for _, msg in trigger_msgs.values()),
        " · ".join(
            f"{k}: {'거부' if ok else '통과'}({msg[:52]})" for k, (ok, msg) in trigger_msgs.items()
        ),
    )

    # 층② 의 **대조군** — 같은 UPDATE 가 트리거 없는 커넥션에서는 성공한다.
    # 이게 없으면 "스키마가 막은 것"과 "트리거가 막은 것"을 구분하지 못한다.
    plain = _open(db)
    try:
        plain_ok, plain_msg = probe_sql(
            plain, f"UPDATE decisions SET state='pending' WHERE decision_id='{probe_id}'"
        )
    finally:
        plain.close()
    check(
        "층② 대조군 — 같은 UPDATE 가 일반 커넥션에서는 **성공** (거부 원인이 트리거임을 실증)",
        not plain_ok,
        f"일반 커넥션: {'거부됨(' + plain_msg[:60] + ')' if plain_ok else '통과 — 트리거가 유일한 차단자'}",
    )

    # 층② 양성 대조 — 커넥션이 통째로 잠긴 게 아니다. INSERT 는 통과해야 한다(D63 draft 생성).
    check(
        "층② INSERT 는 통과 — 커넥션이 통째로 막힌 게 아니라 UPDATE/DELETE 만 잠겼다",
        scalar(db, "SELECT count(*) FROM decisions WHERE decision_id=?", (probe_id,)) == 1,
        f"{probe_id} 존재 · decisions 총 {scalar(db, 'SELECT count(*) FROM decisions')}행",
    )

    # ── 층 ③ REST 로직 ──────────────────────────────────────────────────────────
    # draft 상태에서 sign → 409(권한 아님) · 없는 id → 404 · 403 양방향
    r_draft = client.post(f"/api/decisions/{probe_id}/sign", json={}, headers=MGR)
    r_404 = client.post("/api/decisions/DEC-NOPE/sign", json={}, headers=MGR)
    r_tech_sign = client.post(f"/api/decisions/{probe_id}/sign", json={}, headers=TECH)
    r_mgr_submit = client.post(f"/api/decisions/{probe_id}/submit", headers=MGR)
    check(
        "층③ draft 서명 → 409 invalid_transition · 없는 id → 404 · 403 양방향 (D38)",
        r_draft.status_code == 409
        and r_draft.json().get("reason") == "invalid_transition"
        and r_404.status_code == 404
        and r_tech_sign.status_code == 403
        and r_mgr_submit.status_code == 403,
        f"draft sign={r_draft.status_code}({r_draft.json().get('reason')}) · 404={r_404.status_code}"
        f" · technician sign={r_tech_sign.status_code} · manager submit={r_mgr_submit.status_code}",
    )

    # 재서명 — 이미 signed 인 건은 409. "서명 없는 확정"의 반대편(이중 확정) 차단.
    # ⛔ `next(...)` 를 기본값 없이 쓰지 않는다 — K==0 이면 `StopIteration` 이 `run()` 밖으로
    #    나가 **결과표가 통째로 사라진다**(reviewer 경고 4). 진단이 가장 필요한 순간에.
    already = next((c for c in cells if c.bucket == "서명성공"), None)
    if already is None:
        check(
            "층③ 재서명·서명 후 반려 → 409 (이중 확정 차단)",
            False,
            "서명성공 조합이 0건이라 재서명 프로브를 돌릴 수 없다 — 매트릭스가 전부 막혔다는 뜻이다",
        )
        return
    r_again = client.post(f"/api/decisions/{already.decision_id}/sign", json={}, headers=MGR)
    r_reject_signed = client.post(
        f"/api/decisions/{already.decision_id}/reject", json={"reason": "x"}, headers=MGR
    )
    check(
        "층③ 서명된 건 재서명·반려 → 409 (확정 이후 상태를 되돌리지 않는다)",
        r_again.status_code == 409 and r_reject_signed.status_code == 409,
        f"재서명={r_again.status_code}({r_again.json().get('reason')}) · "
        f"반려={r_reject_signed.status_code}({r_reject_signed.json().get('reason')})",
    )

    # override=true 인데 사유 공백 → 422 (DB CHECK 는 2차 방어선, D63)
    pending_id = _make_probe_draft(db, "AST-L3-CONV", "SCRAP")
    if pending_id is None:
        check("층③ 422·층 독립성 프로브 draft 생성", False, "프로브 draft 생성 실패 — 미실행")
        return
    client.post(f"/api/decisions/{pending_id}/submit", headers=TECH)
    r_blank = client.post(
        f"/api/decisions/{pending_id}/sign",
        json={"override": True, "override_reason": "   "},
        headers=MGR,
    )
    r_missing = client.post(
        f"/api/decisions/{pending_id}/sign", json={"override": True}, headers=MGR
    )
    check(
        "층③ override=true + 사유 공백/누락 → 422 (409 가 아니다 — D38 이 나눈 코드)",
        r_blank.status_code == 422 and r_missing.status_code == 422,
        f"공백={r_blank.status_code} · 누락={r_missing.status_code} · "
        f"행 상태={scalar(db, 'SELECT state FROM decisions WHERE decision_id=?', (pending_id,))}",
    )

    # ── 층 ③ 을 무력화하면 층 ④ 가 잡는가 (층 독립성) ────────────────────────────
    #    `BLOCKING_VERDICTS` 를 비워 ④ 게이트를 죽인 상태로 서명한다 = 뮤턴트 ⓐ 의 in-process 판.
    #    이때 REST 는 통과하지만 **DB CHECK 가 IntegrityError 로 막아야** 한다.
    saved_blocking = dec_svc.BLOCKING_VERDICTS
    dec_svc.BLOCKING_VERDICTS = ()
    try:
        caught: Exception | None = None
        try:
            dec_svc.sign(pending_id, reviewed_by="mgr-01")
        except sqlite3.IntegrityError as exc:
            caught = exc
        except Exception as exc:  # noqa: BLE001 — 다른 예외면 층④ 가 잡은 게 아니다
            caught = exc
    finally:
        dec_svc.BLOCKING_VERDICTS = saved_blocking
    state_after = scalar(db, "SELECT state FROM decisions WHERE decision_id=?", (pending_id,))
    check(
        "**층 독립성** — 층③ 게이트를 죽여도 층④ CHECK 가 BLOCKED 서명을 막는다",
        isinstance(caught, sqlite3.IntegrityError)
        and _check_marker_hit(
            " ".join(str(caught).split()), CHECK_BLOCKING_OVERRIDE, db, CHECK_BLOCKING_OVERRIDE_PG
        )
        and state_after == "pending",
        f"예외={type(caught).__name__ if caught else '없음(뚫림!)'} · "
        f"메시지={' '.join(str(caught).split())[:70] if caught else '-'} · 서명 후 상태={state_after}",
    )

    # ── 순서 잠금 (D84) — 근거가 바뀐 건은 **override 로도** 뚫리지 않는다 ─────────
    #    근거 변경 + BLOCKED 를 동시에 만든 뒤 override=true 로 밀어 본다.
    #    `override_required` 가 나오면 "사람이 본 것과 다른 근거에 서명"이 성립해 버린다.
    order_id = _make_probe_draft(db, "AST-L3-LIFT", "SCRAP")  # 원래 CLEAR
    if order_id is None:
        check("순서 잠금 프로브 draft 생성", False, "프로브 draft 생성 실패 — 미실행")
        return
    client.post(f"/api/decisions/{order_id}/submit", headers=TECH)
    con_mut = _open(db)
    try:
        con_mut.execute(
            "UPDATE assets SET has_lien=1, lien_creditor='스파이크은행', lien_consent_ref=NULL"
            " WHERE asset_id='AST-L3-LIFT'"
        )
        con_mut.commit()
    finally:
        con_mut.close()
    r_ec = client.post(f"/api/decisions/{order_id}/sign", json={}, headers=MGR)
    r_ec_ovr = client.post(
        f"/api/decisions/{order_id}/sign",
        json={"override": True, "override_reason": "근거가 바뀐 건을 밀어 본다"},
        headers=MGR,
    )
    check(
        "순서 잠금 (D84) — 근거 변경 + BLOCKED 는 override=true 로도 409 evidence_changed",
        r_ec.status_code == 409
        and r_ec.json().get("reason") == "evidence_changed"
        and r_ec_ovr.status_code == 409
        and r_ec_ovr.json().get("reason") == "evidence_changed"
        and scalar(db, "SELECT state FROM decisions WHERE decision_id=?", (order_id,)) == "pending",
        f"override 없음={r_ec.status_code}/{r_ec.json().get('reason')} · "
        f"override=true={r_ec_ovr.status_code}/{r_ec_ovr.json().get('reason')}",
    )

    # ── 층 ④ DB CHECK — 직접 SQL 로 뚫기 3건 ────────────────────────────────────
    #    각 CHECK 를 **제약식 문구로 식별**한다. "예외가 났다"만으로는 어느 층이 잡았는지 모른다.
    con = _open(db)
    con.execute("PRAGMA foreign_keys=ON")
    try:
        probes = {
            "ⓐ 서명 요소 없이 signed": (
                f"UPDATE decisions SET state='signed' WHERE decision_id='{probe_id}'",
                CHECK_SIGNED_ELEMENTS,
                None,
            ),
            "ⓑ BLOCKED 를 override=0 으로 signed": (
                "UPDATE decisions SET state='signed', signed_at='2026-08-10 00:00:00',"
                f" reviewed_by='mgr-01' WHERE decision_id='{probe_id}'",
                CHECK_BLOCKING_OVERRIDE,
                CHECK_BLOCKING_OVERRIDE_PG,
            ),
            "ⓒ 사유 없는 override": (
                f"UPDATE decisions SET override=1, override_reason='  ' WHERE decision_id='{probe_id}'",
                CHECK_OVERRIDE_REASON,
                None,
            ),
        }
        outcome = {
            label: (*probe_sql(con, sql), mark, pg_mark)
            for label, (sql, mark, pg_mark) in probes.items()
        }
        stripped, mutant_passed = _mutant_table(con, probe_id, [sql for sql, _, _ in probes.values()])
    finally:
        con.close()

    check(
        "층④ 직접 SQL 3건 전부 CHECK 거부 — **어느 CHECK 인지 제약식 문구로 확인**",
        all(
            ok and _check_marker_hit(msg, mark, db, pg_mark)
            for ok, msg, mark, pg_mark in outcome.values()
        ),
        # ⚠ 문구를 보여 준다 — "거부됐다"만 찍으면 **다른 CHECK 가 대신 잡은 경우**를 못 읽는다
        #   (뮤턴트 ⓑ 실측: 서명 3요소 CHECK 를 지워도 BLOCKING CHECK 가 대신 거부했다)
        " · ".join(
            f"{lbl}: {'거부' if ok else '통과'}/"
            + (
                "문구일치"
                if _check_marker_hit(msg, mark, db, pg_mark)
                else f"문구불일치[{msg.replace('CHECK constraint failed: ', '')[:56]}]"
            )
            for lbl, (ok, msg, mark, pg_mark) in outcome.items()
        ),
    )

    check(
        "층④ 대조군 — CHECK 를 벗긴 뮤턴트 테이블에서는 **같은 SQL 3건이 전부 통과**",
        stripped and mutant_passed == 3,
        f"CHECK 제거 확인={stripped} · 뮤턴트에서 통과한 SQL={mutant_passed}/3",
    )

    # ── 불변식 쿼리 — "서명 없는 확정 0건" 을 **전 행에 대해** 센다 ────────────────
    signed_n = scalar(db, "SELECT count(*) FROM decisions WHERE state='signed'")
    bad_sign = rows(
        db,
        "SELECT decision_id FROM decisions WHERE state='signed' AND ("
        " signed_at IS NULL OR reviewed_by IS NULL"
        " OR reviewed_by NOT IN (SELECT user_id FROM users)"
        " OR length(trim(bundle_hash)) = 0)",
    )
    check(
        "불변식 — state='signed' 전 행에 signed_at·reviewed_by(users FK)·bundle_hash 존재 (D41)",
        not bad_sign and signed_n > 0,
        f"signed {signed_n}행 · 위반 {len(bad_sign)}행"
        + (f" {[r[0] for r in bad_sign]}" if bad_sign else ""),
    )

    bad_bypass = rows(
        db,
        "SELECT decision_id, verdict_at_signing FROM decisions WHERE state='signed'"
        " AND verdict_at_signing NOT IN ('CONDITIONAL','CLEAR') AND override <> 1",
    )
    bad_reason = rows(
        db,
        "SELECT decision_id FROM decisions WHERE override = 1 AND ("
        " override_reason IS NULL OR length(trim(override_reason)) = 0)",
    )
    check(
        "불변식 — 차단 판정 서명은 전부 override=1 이고 사유가 비어 있지 않다 (BLOCKING 우회 0건)",
        not bad_bypass and not bad_reason,
        f"우회 서명 {len(bad_bypass)}행 · 사유 없는 override {len(bad_reason)}행 · "
        f"override 서명 {scalar(db, 'SELECT count(*) FROM decisions WHERE override=1')}행",
    )

    # 불변식이 **공허하게 참**이 아님을 못 박는다 — 서명이 0건이면 위 두 검사는 그냥 통과한다.
    pending_n = scalar(db, "SELECT count(*) FROM decisions WHERE state='pending'")
    check(
        "불변식 비공허성 — 27조합 중 서명 완료가 실제로 존재하고 차단·비차단 양쪽이 섞여 있다",
        signed_n >= n + k and n > 0 and k > 0,
        f"signed {signed_n}행 (차단 override 서명 {n} + 비차단 서명 {k} 이상) · "
        f"pending {pending_n}행",
    )

    # ── 캐치올 — 어떤 셀 실패도 최소 한 검사에 걸린다는 것을 보증한다 ────────────
    #   위 검사들은 실패를 **문자열 부분일치**(`"우회 성공" in f`, `"override" in f` …)로 분류한다.
    #   `cell.fail(...)` 문구를 하나 고치면 그 실패가 **어느 검사에도 안 걸리는** 상태가 될 수 있고,
    #   그러면 셀은 실패했는데 스위트는 초록이 된다. 이 한 줄이 그 구멍을 영구히 막는다.
    check(
        "캐치올 — 셀·프로브 실패 0건 (분류 문구가 바뀌어도 실패가 새지 않는다)",
        not all_failures,
        f"누적 실패 {len(all_failures)}건"
        + (f": {[f[:70] for f in all_failures[:3]]}" if all_failures else ""),
    )


def _make_probe_draft(db: Path, asset: str, mode: str) -> str | None:
    """층②·③·④ 프로브용 draft 를 도구로 하나 더 만든다 (BLOCKED 자산 — D63 재확인).

    실패하면 **예외를 던지지 않고 None** 을 돌려준다 — 여기서 죽으면 이미 끝난 매트릭스
    판정이 결과표에 찍히지 못하고 사라진다 ("표는 어떤 경우에도 살아남는다").
    """
    import mcp_server.db as mcp_db  # noqa: PLC0415
    from mcp_server.tools.generate_disposal_document import (  # noqa: PLC0415
        generate_disposal_document,
    )

    saved = mcp_db.DB_PATH
    mcp_db.DB_PATH = db
    try:
        res = generate_disposal_document(
            reason=f"{asset}/{mode} 층별 프로브 (MQ-708)",
            asset_id=asset,
            disposal_mode=mode,
            disposal_date=PROBE_DATE,
        )
    finally:
        mcp_db.DB_PATH = saved
    if res.get("status") != "ok":
        return None
    return res["decision_id"]


def _mutant_table(con, probe_id: str, sqls: list[str]) -> tuple[bool, int]:
    """CHECK 3종을 벗긴 사본 테이블에서 같은 SQL 이 통과하는지 본다 (`approvals_contract ㉑` 패턴)."""
    if dbcompat.USE_POSTGRES:
        return _mutant_table_pg(con, probe_id, sqls)

    # ⚠ 저장된 DDL 에는 주석이 남는다 — 먼저 지우지 않으면 `,\s*CHECK` 가 주석 줄을 못 건너뛰어
    #   뮤턴트가 조용히 **원본과 같아지고** "뮤턴트에서도 거부됨" = 위양성 FAIL 이 난다 (실측 선례).
    ddl = con.execute("SELECT sql FROM sqlite_master WHERE name='decisions'").fetchone()[0]
    mutant = re.sub(r"--[^\n]*", "", ddl)
    mutant = mutant.replace("CREATE TABLE decisions", "CREATE TABLE decisions_mutant", 1)
    for pattern in (
        r",\s*CHECK \(override = 0 OR \(override_reason IS NOT NULL"
        r" AND length\(trim\(override_reason\)\) > 0\)\)",
        r",\s*CHECK \(state <> 'signed' OR \(signed_at.*?length\(trim\(bundle_hash\)\) > 0\)\)",
        r",\s*CHECK \(state <> 'signed' OR override = 1\s*OR verdict_at_signing IN \([^)]*\)\)",
    ):
        mutant = re.sub(pattern, "", mutant, flags=re.S)
    stripped = not any(
        mark in mutant
        for mark in (CHECK_SIGNED_ELEMENTS, CHECK_BLOCKING_OVERRIDE, CHECK_OVERRIDE_REASON)
    )

    con.execute("SAVEPOINT mutant")
    passed = 0
    try:
        con.execute(mutant)
        con.execute(
            "INSERT INTO decisions_mutant SELECT * FROM decisions WHERE decision_id = ?",
            (probe_id,),
        )
        for sql in sqls:
            try:
                con.execute(sql.replace("decisions ", "decisions_mutant ", 1))
                passed += 1
            except sqlite3.IntegrityError:
                pass
    finally:
        con.execute("ROLLBACK TO mutant")
        con.execute("RELEASE mutant")
    return stripped, passed


def _mutant_table_pg(con, probe_id: str, sqls: list[str]) -> tuple[bool, int]:
    """`decisions` 를 `LIKE ... INCLUDING ALL` 로 복제(제약 포함)한 뒤, 타깃 CHECK 3종만
    `pg_get_constraintdef()` 문구로 식별해 `ALTER TABLE ... DROP CONSTRAINT` 로 벗긴다.

    SQLite 판처럼 DDL 텍스트를 정규식으로 오려내지 않는 이유: Postgres 는 저장된 DDL 원문이
    없다(`pg_get_constraintdef()` 가 매번 정규화해 재구성한다 — `IN (...)` 이 `= ANY (ARRAY[...])`
    로 바뀌는 것도 그 재구성의 결과다). 텍스트 오려내기 대신 이름으로 제약을 지운다.
    """
    con.execute("SAVEPOINT mutant")
    passed = 0
    try:
        con.execute("DROP TABLE IF EXISTS decisions_mutant")
        con.execute("CREATE TABLE decisions_mutant (LIKE decisions INCLUDING ALL)")
        defs = con.execute(
            "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conrelid = 'decisions_mutant'::regclass AND contype = 'c'"
        ).fetchall()
        markers = (CHECK_SIGNED_ELEMENTS, CHECK_BLOCKING_OVERRIDE_PG, CHECK_OVERRIDE_REASON)
        to_drop = [name for name, d in defs if any(mark in d for mark in markers)]
        for name in to_drop:
            con.execute(f'ALTER TABLE decisions_mutant DROP CONSTRAINT "{name}"')
        remaining = con.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conrelid = 'decisions_mutant'::regclass AND contype = 'c'"
        ).fetchall()
        remaining_text = " ".join(d for (d,) in remaining)
        stripped = not any(mark in remaining_text for mark in markers)

        con.execute(
            "INSERT INTO decisions_mutant SELECT * FROM decisions WHERE decision_id = %s",
            (probe_id,),
        )
        for sql in sqls:
            try:
                con.execute(sql.replace("decisions ", "decisions_mutant ", 1))
                passed += 1
            except sqlite3.IntegrityError:
                pass
    finally:
        con.execute("ROLLBACK TO mutant")
        con.execute("RELEASE mutant")
    return stripped, passed


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("MQ-708 — BLOCKING 우회 0건 · 서명 없는 확정 0건 전수 회귀 (임시 DB 사본)\n")
    if not dbcompat.USE_POSTGRES and not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    if dbcompat.USE_POSTGRES:
        before = None
        before_rows = scalar(pg_isolation.BASE_DATABASE_URL, "SELECT count(*) FROM decisions")
    else:
        before = (SOURCE_DB.stat().st_mtime_ns, SOURCE_DB.stat().st_size)
        before_rows = scalar(SOURCE_DB, "SELECT count(*) FROM decisions")

    # 임시 폴더 정리 실패는 **경고로 끝난다** — Windows 는 핸들 해제가 비동기라,
    # 정리 실패가 예외로 터지면 이미 끝난 계약 검증 결과를 가린다 (rules_db_load 선례).
    schema = None
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        if dbcompat.USE_POSTGRES:
            import backend.db as backend_db  # noqa: PLC0415
            import mcp_server.db as mcp_db  # noqa: PLC0415

            schema, db = pg_isolation.create_isolated_schema("disposal_sign")
            # MCP autostart 가 꺼져 있어(위 os.environ) 도구가 서브프로세스 없이 이
            # 프로세스 안에서 직접 호출된다 — 두 db 모듈 전역을 둘 다 갈아끼워야 한다.
            backend_db.DB_PATH = db
            mcp_db.DB_PATH = db
            print(f"[격리] Postgres 격리 스키마 DATABASE_URL = {db}")
        else:
            db = Path(td) / "disposal_sign.db"
            shutil.copy2(SOURCE_DB, db)
            for side in ("-wal", "-shm"):
                src = SOURCE_DB.with_name(SOURCE_DB.name + side)
                if src.exists():
                    shutil.copy2(src, db.with_name(db.name + side))
            # backend.db 는 **import 시점**에 이 값을 읽는다 — backend import 전에 심는다
            print(f"[격리] MAINTQ_DB = {db}")
        print(f"[격리] 처분 예정일 고정 = {PROBE_DATE}\n")

        from fastapi.testclient import TestClient  # noqa: PLC0415

        from backend.main import app  # noqa: PLC0415

        try:
            with TestClient(app) as client:
                # ⛔ 예외가 여기를 뚫으면 **결과표가 통째로 사라진다** — 진단이 가장 필요한 순간에
                #    아무것도 안 남는다(reviewer 경고 4). FAIL 행으로 접고 표는 끝까지 그린다.
                try:
                    run(client, db)
                except Exception as exc:  # noqa: BLE001
                    check("run() 완주", False, f"{type(exc).__name__}: {exc}")
        finally:
            if schema:
                pg_isolation.drop_isolated_schema(schema)

    if dbcompat.USE_POSTGRES:
        after_rows = scalar(pg_isolation.BASE_DATABASE_URL, "SELECT count(*) FROM decisions")
        check(
            "실 DB 오염 0 — 공유 Postgres decisions 행 수 불변",
            before_rows == after_rows,
            f"decisions {before_rows} → {after_rows}행",
        )
    else:
        after = (SOURCE_DB.stat().st_mtime_ns, SOURCE_DB.stat().st_size)
        after_rows = scalar(SOURCE_DB, "SELECT count(*) FROM decisions")
        check(
            "실 DB 오염 0 — data/maintq.db mtime·size·decisions 행 수 불변",
            before == after and before_rows == after_rows,
            f"mtime·size {'불변' if before == after else f'{before} → {after}'} · "
            f"decisions {before_rows} → {after_rows}행",
        )

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 44))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 44))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(
        f"\n통과 ({len(results)}건) — 27조합 전수에서 BLOCKING 우회 0건 · 서명 없는 확정 0건,"
        " 4층이 각각 독립으로 막는다"
    )


if __name__ == "__main__":
    main()
