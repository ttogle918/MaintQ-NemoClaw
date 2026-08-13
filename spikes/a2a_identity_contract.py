# -*- coding: utf-8 -*-
"""A2A 신원 식별 **기반층** 계약 검증 (MQ-805) — 자리를 만들었다는 말이 사실인가.

검증 대상: D91(판정/식별자 분리) · D92(시드 전제) · D93(자격증명 위치·MCP 격리) ·
          D94(traces.request_chain_id · event_type 불변 · payload 바이트 동일) ·
          D95(policy_id 정본) · D96(DDL 정정 — null-safe `IS` · subject_ref NOT NULL · CHECK 2종) ·
          D30 · D62 · D15 · D76-2

핵심 질문 3개
  1. `partner_links` 의 DDL 이 *"식별자만 있고 승인은 없는 상태"* 를 **실제로** 막는가
     (SQLite 3값 논리 때문에 `=` 로 쓰면 가장 애매한 칸이 조용히 통과한다 — D96-ⓐ)
  2. `NULL`(모름)을 적을 자리가 살아 있는가 (D62·D78 — 막는 건 "모르는데 식별자는 있다"뿐)
  3. **컬럼만 만들고 쓰는 쪽이 없는 상태**를 "값이 비었다"가 아니라 **"쓰는 쪽이 없다"** 로
     말하는가 (D76-2 가 3차 평가까지 전부 NULL 이었던 전례의 재발 방지)

**⑪ 을 둘로 나눈 이유 — 성격이 다르다.**
  - **⑪-a 는 영구 검사**다. A2A 호출부가 생겨도 *"A2A 와 무관한 세션의 trace 에는
    `request_chain_id` 가 없다"* 는 참이어야 한다(무관한 이벤트로 값이 새는 것을 막는다).
  - **⑪-b 는 한시 검사**다. 지금 `request_chain_id` 를 **쓰는 코드가 0건**이라는 사실을
    검사 **이름 자체에** 적는다. ⚠⚠ **호출부가 생기는 스프린트의 DoD 는 ⑪-b 를 지우는 것이
    아니라 '쓰는 쪽이 계측한다'로 교체하는 것이다** — 지우고 넘어가면 D76-2 가 겪은
    *"저장했다고 믿었는데 안 한"* 상태가 그대로 재발한다.

**임시 DB 에서만 돈다** — 스키마는 `data/seed.py` 의 SCHEMA 를 그대로 써서 DDL 이 갈리면
여기서 먼저 깨지게 한다. `data/maintq.db` 는 읽지도 쓰지도 않는다(⑱ 검사).
자격증명 검사(⑯·⑰)는 `os.environ` 을 **직접 조작해 격리**하고 반드시 복원한다 —
개발자 OS env 에 `MAINTQ_A2A_*` 가 실제로 있으면 격리 없이는 머신마다 결과가 달라진다.
⛔ secret 원문은 assert 메시지·detail 어디에도 담지 않는다 (길이·상태만 비교한다).

실행:  uv run python spikes/a2a_identity_contract.py
"""

from __future__ import annotations

import ast
import contextlib
import json
import os
import re
import sqlite3
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL_DB = ROOT / "data" / "maintq.db"
ENV_EXAMPLE = ROOT / ".env.example"

#: ⑯·⑰ 전용 가짜 값. 실제 자격증명이 아니며 어떤 출력에도 원문을 싣지 않는다.
FAKE_ID = "cid-FAKE-NOT-A-REAL-CREDENTIAL"
FAKE_SECRET = "sec-FAKE-NOT-A-REAL-CREDENTIAL-0123456789"

#: ⑪-b 판정식 (sprint-8.md:649~660). 단순 grep 은 MQ-803 의 **DDL 주석**에 걸려 오탐한다.
#:
#: ⚠ 명세의 단일 정규식
#:     `(?is)(insert\s+into\s+traces|update\s+traces)(.{0,400}?)(?=;|insert\s+into|update\s+|$)`
#:   은 **문 종결자가 400자 안에 없으면 매치 자체가 실패**하고, 그러면 `hit` 이 항상 0이 되어
#:   검사가 **공허하게 통과**한다. 실측(2026-08-13): `backend/agent/trace.py` 의 상수 blob 에서
#:   위 정규식의 매치가 **0건**이었고(뒤에 `;`·두 번째 `insert into`·`update ` 가 없고 `$` 는
#:   400자 밖이다), 뮤턴트 ⓔ(INSERT 컬럼 목록에 `request_chain_id` 추가)가 **그대로 통과**했다.
#:   그래서 같은 의미를 **앵커 + 윈도우**로 쪼갠다 — 종결자가 있으면 거기서 자르고 없으면 400자까지
#:   본다. 명세 정규식이 잡는 것은 전부 잡는 **상위집합**이라 판정이 느슨해지지는 않는다.
#:
#: ⚠⚠ **더 나쁜 사실 (2026-08-13 교차 검증).** 명세 정규식의 생사는 **blob 을 어떻게 잇느냐에
#:   달려 있었다.** 같은 파일이라도 `ast.walk()` 순서로 `""` 조인하면 뮤턴트를 **잡고**,
#:   이 함수처럼 `lineno` 정렬로 `"\n"` 조인하면 **놓친다** — 앵커에서 종결자까지의 거리가
#:   창(400)에 **근접**해 있어, 조립 순서·조인 문자·로그 문구 한 줄이 결과를 뒤집는다.
#:   (구체 수치는 소스가 바뀌면 낡으므로 여기 적지 않는다. 재현하려면
#:    `sql_blob()` 로 blob 을 만들어 명세 정규식과 `ANCHOR` 를 각각 돌려 비교할 것.)
#:   즉 "정규식이 틀렸다"가 아니라
#:   **"판정식의 생사가 무관한 구현 세부에 좌우된다"** 는 것이 진짜 결함이다.
#:   그래서 아래 ⑪-b 는 `anchors > 0` 을 **판정에 포함**한다 — 앵커가 0이면 그건
#:   "쓰는 코드가 없다"가 아니라 **"판정식이 죽었다"** 이고, 둘을 구분하지 못하면
#:   이 검사는 언제든 조용히 공허해진다.
ANCHOR = re.compile(r"(?is)insert\s+into\s+traces|update\s+traces")
STMT_END = re.compile(r"(?is);|insert\s+into|update\s+")
STMT_WINDOW = 400


def writes_request_chain_id(blob: str) -> bool:
    """`INSERT INTO traces` / `UPDATE traces` **문 범위 안**에 `request_chain_id` 가 있는가."""
    for m in ANCHOR.finditer(blob):
        window = blob[m.end() : m.end() + STMT_WINDOW]
        end = STMT_END.search(window)
        if "request_chain_id" in (window[: end.start()] if end else window):
            return True
    return False

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


# ────────────────────────────────────────────────────────────── 공용 헬퍼


def make_db(td: Path) -> Path:
    """seed.py 의 실제 DDL 로 빈 DB 를 만든다 (시드 데이터는 필요 없다)."""
    sys.path.insert(0, str(ROOT / "data"))
    import seed  # noqa: PLC0415

    db = td / "a2a.db"
    con = sqlite3.connect(db)
    con.executescript(seed.SCHEMA)
    con.commit()
    con.close()
    return db


def table_ddl(db: Path, table: str) -> str:
    con = sqlite3.connect(db)
    try:
        row = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
    finally:
        con.close()
    return row[0] if row else ""


def table_info(db: Path, table: str) -> dict[str, sqlite3.Row]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        return {r["name"]: r for r in con.execute(f"PRAGMA table_info({table})")}
    finally:
        con.close()


def strip_sql_comments(ddl: str) -> str:
    """`--` 주석 제거 (문자열 리터럴 안의 `--` 는 남긴다).

    `sqlite_master.sql` 은 **작성한 원문 그대로** 주석까지 담고 있다 —
    ②·③ 이 주석 문구에 걸려 오탐하지 않도록 먼저 걷어낸다.
    """
    out: list[str] = []
    for line in ddl.splitlines():
        in_str = False
        cut: int | None = None
        for i, ch in enumerate(line):
            if ch == "'":
                in_str = not in_str
            elif not in_str and ch == "-" and line[i + 1 : i + 2] == "-":
                cut = i
                break
        out.append(line if cut is None else line[:cut])
    return "\n".join(out)


def check_clauses(ddl: str) -> list[str]:
    """DDL 의 `CHECK (...)` 본문만 괄호 균형을 맞춰 뽑는다."""
    body = strip_sql_comments(ddl)
    found: list[str] = []
    for m in re.finditer(r"(?i)\bCHECK\s*\(", body):
        start = m.end() - 1
        depth, in_str, j = 0, False, start
        while j < len(body):
            c = body[j]
            if c == "'":
                in_str = not in_str
            elif not in_str:
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                    if depth == 0:
                        break
            j += 1
        found.append(" ".join(body[start + 1 : j].split()))
    return found


def try_insert(db: Path, cols: tuple[str, ...], vals: tuple) -> tuple[bool, str]:
    """INSERT 성공 여부. 실패는 예외가 아니라 (False, 사유) 로 돌려준다."""
    con = sqlite3.connect(db)
    try:
        con.execute(
            f"INSERT INTO partner_links ({','.join(cols)})"
            f" VALUES ({','.join('?' * len(cols))})",
            vals,
        )
        con.commit()
        return True, "통과"
    except sqlite3.IntegrityError as exc:
        return False, str(exc)
    finally:
        con.close()


LINK_COLS = ("partner", "subject_type", "subject_ref", "link_state", "external_ref")


def data_line(frame: str) -> str:
    """SSE 프레임의 `data:` 본문 — payload 와 바이트 동일해야 한다 (D30)."""
    for line in frame.split("\n"):
        if line.startswith("data: "):
            return line[len("data: ") :]
    raise AssertionError(f"data 라인이 없는 프레임: {frame!r}")


def py_files(*rels: str) -> list[Path]:
    out: list[Path] = []
    for rel in rels:
        base = ROOT / rel
        if not base.exists():
            continue
        out += [p for p in sorted(base.rglob("*.py")) if "__pycache__" not in p.parts]
    return out


def sql_blob(path: Path) -> str:
    """파일의 **문자열 상수만** 소스 순서로 이어붙인다 (주석·docstring 제외).

    `#` 주석은 `ast` 가 애초에 버리고, module/class/function docstring 은 여기서 뺀다.
    → MQ-803 이 넣은 **DDL 주석**과 `trace.py` docstring 이 `request_chain_id` 를
      언급해도 ⑪-b 가 오탐하지 않는다.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    doc_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False) is not None:
                doc_ids.add(id(node.body[0].value))  # Expr(Constant) 의 Constant 노드
    consts = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in doc_ids
    ]
    consts.sort(key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0)))
    return "\n".join(n.value for n in consts)


@contextlib.contextmanager
def isolated_a2a_env() -> Iterator[None]:
    """`MAINTQ_A2A_*` 만 걷어내고 블록이 끝나면 **원상 복구**한다.

    개발자 머신에 실값이 설정돼 있어도 ⑯ 결과가 흔들리지 않게 하는 유일한 방법이다.
    """
    saved = {k: v for k, v in os.environ.items() if k.startswith("MAINTQ_A2A_")}
    for k in saved:
        del os.environ[k]
    try:
        yield
    finally:
        for k in [k for k in os.environ if k.startswith("MAINTQ_A2A_")]:
            del os.environ[k]
        os.environ.update(saved)


# ────────────────────────────────────────────────────────────── 검사


def run_schema(db: Path) -> None:
    """① ~ ⑨ — partner_links DDL 과 그 동작 (D91·D95·D96)."""
    ddl = table_ddl(db, "partner_links")
    info = table_info(db, "partner_links")

    # ── ① 스키마 드리프트
    pk = {name: r["pk"] for name, r in info.items() if r["pk"]}
    # ⚠ `linked_at` 의 **선언 타입**까지 본다 (D96-ⓓ · Stage 4 reviewer 권고).
    #    SQLite 는 `DATE`·`DATETIME` 둘 다 NUMERIC affinity 라 선언을 `DATE` 로 되돌려도
    #    값은 그대로 저장되고 seed ㉒-ⓓ(값 모양 검사)도 통과한다 —
    #    즉 **사람이 확정한 D96-ⓓ 를 잠그는 검사가 여기 말고는 없다.**
    # ⚠ `info` 의 값은 `sqlite3.Row` 라 `.get()` 이 없다 — 키 존재를 먼저 본다
    linked_at_type = info["linked_at"]["type"] if "linked_at" in info else ""
    check(
        "① partner_links 존재 · 컬럼 6종 · PK 3열 · subject_ref NOT NULL · linked_at DATETIME (D96-ⓑⓓ)",
        bool(ddl)
        and set(info) == set(LINK_COLS) | {"linked_at"}
        and pk == {"partner": 1, "subject_type": 2, "subject_ref": 3}
        and info["subject_ref"]["notnull"] == 1
        and linked_at_type.upper() == "DATETIME",
        f"컬럼={sorted(info)}, PK={pk},"
        f" subject_ref.notnull={info['subject_ref']['notnull'] if 'subject_ref' in info else None},"
        f" linked_at.type={linked_at_type!r}",
    )

    # ── ② 필수 CHECK 2종 존재 + partner·subject_type 엔 CHECK 없음 (D96-ⓒ)
    #    ⚠ 개수 상한을 잠그지 않는다 — 나중에 정당한 CHECK 가 추가될 수 있다.
    clauses = check_clauses(ddl)
    enum_c = [c for c in clauses if re.search(r"(?i)link_state\s+IN\s*\(", c)]
    pair_c = [c for c in clauses if "external_ref" in c and "link_state" in c]
    free_c = [c for c in clauses if re.search(r"(?i)\b(partner|subject_type)\b", c)]
    check(
        "② 필수 CHECK 2종 존재 · partner·subject_type 엔 CHECK 없음 (D96-ⓒ, 상한 미잠금)",
        len(enum_c) == 1 and len(pair_c) == 1 and not free_c,
        f"enum={len(enum_c)}, 결합={len(pair_c)}, partner/subject_type={len(free_c)}, 총 CHECK={len(clauses)}",
    )

    # ── ③ DDL 파싱 — 결합 CHECK 가 null-safe `IS` 인가 (D96-ⓐ)
    #    동작 검사(⑤)만 있으면 "왜 실패했는지" 를 알 수 없다. 검사 ㉑ 이 DDL 을 파싱한 선례.
    pair_txt = pair_c[0] if pair_c else ""
    check(
        "③ 결합 CHECK 가 null-safe `link_state IS 'LINKED'` (`=` 되돌림 차단, D96-ⓐ)",
        bool(re.search(r"(?i)link_state\s+IS\s+'LINKED'", pair_txt))
        and not re.search(r"(?i)link_state\s*=\s*'LINKED'", pair_txt),
        f"CHECK={pair_txt or '(없음)'}",
    )

    # ── ④ 음성 — 확인된 미연결인데 식별자가 있다 (D91 본래 목적)
    ok4, why4 = try_insert(
        db, LINK_COLS, ("finallq", "company", "neg4", "NOT_LINKED", "CMP-X")
    )
    check("④ ('NOT_LINKED','CMP-X') 거부 — 승인 없이 식별자 금지 (D91)", not ok4, why4)

    # ── ⑤ 음성 — **모르는데 식별자는 있다** (§3 결함 ①. ③의 동작 증명)
    ok5, why5 = try_insert(db, LINK_COLS, ("finallq", "company", "neg5", None, "CMP-X"))
    check(
        "⑤ (NULL,'CMP-X') 거부 — SQLite 3값 논리 구멍 (`=` 면 통과한다, D96-ⓐ)",
        not ok5,
        why5,
    )

    # ── ⑥ 음성 — enum 밖 (오타)
    ok6a, why6a = try_insert(db, LINK_COLS, ("finallq", "company", "neg6a", "linked", None))
    ok6b, why6b = try_insert(db, LINK_COLS, ("finallq", "company", "neg6b", "LINK", None))
    check(
        "⑥ 'linked'·'LINK' 거부 — link_state enum 2종 (오타 차단)",
        not ok6a and not ok6b,
        f"'linked'→{why6a[:34]} / 'LINK'→{why6b[:34]}",
    )

    # ── ⑦ 양성 — (NULL, NULL) = "모름". 이 자리가 사라지면 D62·D78 위반
    ok7, why7 = try_insert(db, LINK_COLS, ("finallq", "company", "pos7", None, None))
    check("⑦ (NULL, NULL) 통과 — '모름'을 적을 자리가 살아 있다 (D62·D78)", ok7, why7)

    # ── ⑧ 양성 — 과잉 차단 방지. 후자가 §A(InsuQ building 행)의 성립 조건이다 (D95)
    ok8a, why8a = try_insert(
        db, LINK_COLS, ("finallq", "company", "pos8a", "LINKED", "CMP-MAINTQ-001")
    )
    ok8b, why8b = try_insert(db, LINK_COLS, ("insuq", "building", "BLD-Z", "LINKED", None))
    check(
        "⑧ ('LINKED','CMP-X') 및 ('LINKED', NULL) 통과 — 후자가 §A InsuQ 행 (D95)",
        ok8a and ok8b,
        f"식별자 있음→{why8a[:30]} / 식별자 NULL→{why8b[:30]}",
    )

    # ── ⑨ PK — SQLite 는 비-INTEGER PK 의 NULL 을 허용하고 NULL 끼리 서로 다르다 (D96-ⓑ)
    ok9a, _ = try_insert(db, LINK_COLS, ("finallq", "company", "", "LINKED", "CMP-MAINTQ-001"))
    ok9b, why9b = try_insert(
        db, LINK_COLS, ("finallq", "company", "", "LINKED", "CMP-MAINTQ-001")
    )
    ok9c, why9c = try_insert(db, LINK_COLS, ("finallq", "company", None, None, None))
    check(
        "⑨ ('finallq','company','') 중복 거부 · subject_ref=NULL 거부 (D96-ⓑ)",
        ok9a and not ok9b and not ok9c,
        f"1회차={ok9a}, 중복→{why9b[:30]}, NULL→{why9c[:30]}",
    )


def run_trace(db: Path) -> None:
    """⑩ ~ ⑬ — traces 계측 자리 (D94 · D30 · D76-2)."""
    from backend.agent.trace import TraceWriter  # noqa: PLC0415

    info = table_info(db, "traces")

    # ── ⑩ 컬럼 존재 · nullable · 기본 NULL (D94-ⓐ)
    rc = info.get("request_chain_id")
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO traces (session_id, seq, event_type, payload)"
        " VALUES ('S-A2A-DEFAULT', 1, 'block', '{}')"
    )
    con.commit()
    default_null = con.execute(
        "SELECT request_chain_id FROM traces WHERE session_id='S-A2A-DEFAULT'"
    ).fetchone()[0]
    con.close()
    check(
        "⑩ traces.request_chain_id 존재 · nullable · 기본 NULL (D94-ⓐ)",
        rc is not None and rc["notnull"] == 0 and rc["dflt_value"] is None and default_null is None,
        f"notnull={rc['notnull'] if rc else None}, dflt={rc['dflt_value'] if rc else None}, 미지정 INSERT 후 값={default_null}",
    )

    # ── ⑪-a **행동** — 실제로 이벤트 3종을 발행해도 전 행 NULL (영구 검사)
    w = TraceWriter("S-A2A", db_path=db)
    ev_call = w.tool_call("lookup_error_code", {"model": "iG5A", "code": "OHt"})
    w.tool_result("lookup_error_code", "ok", "과열 · FAN-IG5-01", 0.4, tool_payload={"status": "ok"})
    w.block("safety", {"title": "SAFETY", "text": "10분 이상 대기"})
    con = sqlite3.connect(db)
    rc_rows = con.execute(
        "SELECT event_type, request_chain_id FROM traces WHERE session_id='S-A2A' ORDER BY seq"
    ).fetchall()
    # ⛔ `.fetchone()[0]` 로 바로 벗기지 않는다 (2026-08-13 실측).
    #    `TraceWriter` 가 쓰기에 실패하면 행이 **0개**가 되고, 그때 `[0]` 이 `TypeError` 를 던져
    #    **표가 인쇄되기 전에 프로세스가 죽는다** — 앞선 12건의 결과가 통째로 사라지고,
    #    진짜 원인(⑪-b 가 잡았어야 할 회귀)이 무관한 `TypeError` 로 둔갑한다.
    #    러너가 CLAUDE.md 의 "Windows 산발 실패"로 오진해 재시도만 반복하게 되는 경로다.
    #    없으면 `None` 을 그대로 넘겨 ⑬ 이 **FAIL 로 보고**하게 둔다.
    _row = con.execute(
        "SELECT payload FROM traces WHERE session_id='S-A2A' AND seq=1"
    ).fetchone()
    payload_row = _row[0] if _row else None
    con.close()
    check(
        "⑪-a TraceWriter 3종 발행 후 전 행 request_chain_id IS NULL (무관한 세션에 값이 새지 않는다)",
        len(rc_rows) == 3
        and [r[0] for r in rc_rows] == ["tool_call", "tool_result", "block"]
        and all(r[1] is None for r in rc_rows),
        f"{[(r[0], r[1]) for r in rc_rows]}",
    )

    # ── ⑪-b **정적** — 한시 검사. 이름에 사실을 적는다 (모듈 docstring 참조)
    hits: list[str] = []
    anchors = 0
    scanned = py_files("backend", "mcp_server")
    for p in scanned:
        blob = sql_blob(p)
        anchors += len(ANCHOR.findall(blob))
        if writes_request_chain_id(blob):
            hits.append(str(p.relative_to(ROOT)).replace("\\", "/"))
    # ⚠ 앵커 수를 함께 찍는다 — 0 이면 "쓰는 코드가 없다"가 아니라 **판정식이 죽은 것**이다
    #   (명세 정규식이 정확히 그렇게 공허 통과했다. 위 ANCHOR 주석 참조).
    check(
        "⑪-b request_chain_id 를 쓰는 코드 0건 (A2A 호출부 미착수 — 생기면 이 검사를 뒤집는다)",
        not hits and anchors > 0,
        f"{len(scanned)}개 파일 스캔(주석·docstring 제외), traces 쓰기문 {anchors}건, 히트={hits or '없음'}",
    )

    # ── ⑫ event_type CHECK 는 여전히 3종 (D94 가 a2a_call 신설을 기각한 근거)
    tddl = table_ddl(db, "traces")
    et = [c for c in check_clauses(tddl) if "event_type" in c]
    listed = re.findall(r"'([a-z_]+)'", et[0]) if et else []
    ok_a2a, why_a2a = True, ""
    con = sqlite3.connect(db)
    try:
        con.execute(
            "INSERT INTO traces (session_id, seq, event_type, payload)"
            " VALUES ('S-A2A-EV', 1, 'a2a_call', '{}')"
        )
    except sqlite3.IntegrityError as exc:
        ok_a2a, why_a2a = False, str(exc)
    finally:
        con.rollback()
        con.close()
    check(
        "⑫ traces.event_type CHECK 3종 유지 · 'a2a_call' INSERT 거부 (D94 ① 기각)",
        set(listed) == {"tool_call", "tool_result", "block"} and not ok_a2a,
        f"CHECK={listed}, a2a_call→{why_a2a[:40] or '통과해버림'}",
    )

    # ── ⑬ payload == SSE data 바이트 동일 · request_chain_id 가 그 안에 없다 (D30·D94-ⓔ)
    check(
        "⑬ payload == SSE data (바이트 동일) · payload 에 request_chain_id 없음 (D30)",
        payload_row == data_line(ev_call.encode())
        and "request_chain_id" not in payload_row
        and "request_chain_id" not in ev_call.encode(),
        f"payload={payload_row[:56]}...",
    )


def run_env() -> None:
    """⑭ ~ ⑰ — 자격증명 보관 위치와 격리 (D93 · D15)."""
    # ── ⑭ .env.example 4키 존재 · 값 전부 빈칸 · **수집 키 절 밖**
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    marker = next((i for i, ln in enumerate(lines) if "외부 데이터 원천" in ln), None)
    keys = [
        "MAINTQ_A2A_FINALLQ_CLIENT_ID",
        "MAINTQ_A2A_FINALLQ_CLIENT_SECRET",
        "MAINTQ_A2A_INSUQ_CLIENT_ID",
        "MAINTQ_A2A_INSUQ_CLIENT_SECRET",
    ]
    pos = {k: next((i for i, ln in enumerate(lines) if ln.strip() == f"{k}=") , None) for k in keys}
    missing = [k for k, v in pos.items() if v is None]
    nonempty = [k for k in keys if any(ln.startswith(f"{k}=") and ln.strip() != f"{k}=" for ln in lines)]
    check(
        "⑭ .env.example 에 A2A 4키 · 값 전부 빈칸 · 수집 키 절(외부 데이터 원천) **위** (D93 ③ 기각)",
        not missing
        and not nonempty
        and marker is not None
        and all(v < marker for v in pos.values() if v is not None),
        f"누락={missing or '없음'}, 실값={nonempty or '없음'}, 키줄={sorted(v for v in pos.values() if v is not None)}, 수집절={marker}",
    )

    # ── ⑮ MCP 격리 — 도구가 자격증명·파트너 대장을 보지 않는다 (D15·D93)
    #
    # ⚠ **평문 검색은 의도다** — ⑪-b 와 달리 주석·docstring 을 걷어내지 않는다.
    #   두 검사가 묻는 질문이 다르기 때문이다:
    #     ⑪-b = "코드가 X 를 **하는가**"  → 주석은 잡음이므로 반드시 제외해야 한다
    #     ⑮   = "mcp_server 가 이 이름들을 **아는가**" → D15 는 프로세스 분리이고,
    #            도구가 `partner_links` 를 docstring 에서라도 부를 이유가 없다.
    #            부르고 있다면 그 자체가 결합의 신호다.
    #   ⛔ 선의의 설명 주석도 FAIL 시킨다. 설명이 필요하면 **테이블명·env 이름을 적지 말고**
    #      `D15`·`D93` 만 인용할 것. 이 검사를 `ast` 로 바꾸면 방어선이 약해진다.
    banned = ("MAINTQ_A2A_", "backend.a2a", "partner_links")
    leaks: list[str] = []
    mcp_files = py_files("mcp_server")
    for p in mcp_files:
        text = p.read_text(encoding="utf-8")
        for token in banned:
            if token in text:
                leaks.append(f"{p.relative_to(ROOT)}:{token}".replace("\\", "/"))
    check(
        "⑮ mcp_server/** 에 MAINTQ_A2A_·backend.a2a·partner_links 0건 (D15·D93)",
        not leaks,
        f"{len(mcp_files)}개 파일 스캔, 히트={leaks or '없음'}",
    )

    from backend.a2a import credentials  # noqa: PLC0415

    # ── ⑯ load() 상태 4종. os.environ 을 직접 조작해 격리한다 (모듈 캐시가 있으면 성립 불가)
    with isolated_a2a_env():
        s_none = credentials.load("finallq").status
        os.environ["MAINTQ_A2A_FINALLQ_CLIENT_ID"] = FAKE_ID
        s_part = credentials.load("finallq").status
        os.environ["MAINTQ_A2A_FINALLQ_CLIENT_SECRET"] = FAKE_SECRET
        s_full = credentials.load("finallq").status
        cred = credentials.load("finallq")
        s_unknown = credentials.load("qmesh-nope").status
        report = credentials.status_report()

        # ⛔ secret 원문을 담지 않는다 — 길이·상태만 본다
        leaked = {
            "repr": FAKE_SECRET in repr(cred),
            "str": FAKE_SECRET in str(cred),
            "fstring": FAKE_SECRET in f"{cred}",
            "status_report": FAKE_SECRET in json.dumps(report, ensure_ascii=False),
        }
        asdict_leaks = FAKE_SECRET in json.dumps(asdict(cred), ensure_ascii=False)
        secret_len_ok = len(cred.client_secret) == len(FAKE_SECRET)

    check(
        "⑯ credentials.load() 상태 4종 (not_configured/incomplete/configured/unknown_partner) · 모듈 캐시 없음",
        (s_none, s_part, s_full, s_unknown)
        == ("not_configured", "incomplete", "configured", "unknown_partner")
        and report["insuq"] == "not_configured"
        and secret_len_ok,
        f"{s_none} → {s_part} → {s_full} / 미지={s_unknown}, secret_len 일치={secret_len_ok}",
    )

    # ── ⑰ secret 원문 부재 + **asdict/astuple 소비자 0건**
    #    repr/str 은 막혀 있으나 dataclasses.asdict 는 원문을 그대로 낸다 —
    #    호출부가 생기는 스프린트의 `JSONResponse(asdict(cred))` 사고를 앞단에서 막는다.
    consumers: list[str] = []
    for p in py_files("backend", "mcp_server"):
        text = p.read_text(encoding="utf-8")
        touches_cred = bool(re.search(r"\ba2a\b|PartnerCredential|credentials\.load", text))
        if touches_cred and re.search(r"\b(asdict|astuple)\s*\(", text):
            consumers.append(str(p.relative_to(ROOT)).replace("\\", "/"))
    check(
        "⑰ repr·str·f-string·status_report 에 secret 원문 없음 · asdict/astuple 소비자 0건",
        not any(leaked.values()) and not consumers,
        f"노출={[k for k, v in leaked.items() if v] or '없음'}, asdict 는 원문 노출={asdict_leaks}(소비자 {len(consumers)}건)",
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("A2A 신원 식별 기반층 계약 검증 — D91~D96 (임시 DB 전용)\n")
    before = REAL_DB.stat().st_mtime_ns if REAL_DB.exists() else None

    # ⛔ `ignore_cleanup_errors=True` 는 편의가 아니라 **보고 신뢰성**이다 (2026-08-13 실측).
    #    검사가 실패하는 방식에 따라 임시 DB 커넥션이 열린 채 남고, 그러면 Windows 에서
    #    `TemporaryDirectory.__exit__` 이 `PermissionError [WinError 32]` 를 던진다.
    #    표는 이 블록 **뒤에** 인쇄되므로, 그 예외가 **결과 표를 통째로 삼킨다** —
    #    진짜 회귀(⑪-b FAIL)가 "다른 프로세스가 파일을 사용 중" 이라는 무관한 메시지로 둔갑하고,
    #    CLAUDE.md 가 경고한 Windows 산발 실패로 오진돼 **재시도만 반복하게 된다.**
    #    임시 디렉터리 하나가 시스템 temp 에 남는 비용 < 실패 원인을 잃는 비용.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = make_db(Path(td))
        # backend.db 는 import 시점에 MAINTQ_DB 를 읽는다 — import 전에 심는다
        os.environ["MAINTQ_DB"] = str(db)
        sys.path.insert(0, str(ROOT))
        run_schema(db)
        run_trace(db)
        run_env()

    # ── ⑱ 실 DB 불변 (스파이크가 data/maintq.db 를 건드리면 안 된다)
    after = REAL_DB.stat().st_mtime_ns if REAL_DB.exists() else None
    check("⑱ data/maintq.db 불변 (mtime)", before == after, f"{before} == {after}")

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 40))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail[:70]}")
    print("─" * (width + 40))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(
        f"\n통과 ({len(results)}건) — 판정과 식별자는 분리돼 있고, '모름'을 적을 자리는 살아 있으며,\n"
        "request_chain_id 는 **쓰는 쪽이 아직 없다**(⑪-b — 호출부가 생기면 이 검사를 뒤집는다)"
    )


if __name__ == "__main__":
    main()
