# -*- coding: utf-8 -*-
"""MQ-1903 — HV600 model enum 선등록 + DB CHECK 확장 + D155 형식 검증 계약
(D146·D155·D109 ⓒ, docs/sprints/sprint-19.md MQ-1903).

'enum 에 있다'와 '진단할 수 있다'는 다른 상태다(D146) — 이 스파이크는 그 경계를 고정한다:

  ① enum 코드 지점 10곳이 전부 `("iG5A", "S100", "IE5", "HV600")` 인가(AST 정적 검사,
     소스를 실행하지 않는다) + 레포 전역에 구(舊) 3종 튜플이 잔존하지 않는가
     (부재 검사 + 스캐너 생존 프로브를 함께 건다 — CLAUDE.md "부재 검사엔 liveness 앵커").
  ② DB CHECK — `equipment.model` 에 HV600 포함·IE5 는 여전히 미포함(D109 ⓒ 보존),
     `manual_chunks.model` 은 4종 전부 포함.
  ③ D155 형식(길이 2~5·대문자·`[A-Z0-9_-]`, 하이픈 포함) — 양성(5자·하이픈 코드)과
     음성(6자·소문자·공백) 을 **둘 다** 실측한다.
  ④ 기존 70행이 새 CHECK 하에서도 그대로 살아 있는가(격리 복제본, `model != 'HV600'`).
  ⑤ 승격 전 게이트(절대규칙 6) — HV600 은 enum 에는 있지만 `error_codes` 에 행이 없으니
     `lookup_error_code` 가 `not_found`(유사 코드 제안 없이, 키 집합 정확)를 내야 한다.
     같은 커넥션에서 iG5A 조회는 정상(ok) — "DB 가 전부 깨졌다"가 아니라는 앵커.
  ⑥ `rag_search_manual(model="HV600")` 은 `empty` 가 아니라 `error/index_not_built`(D50 논리).
  ⑦ `backend.manifest.print_page_offset("HV600") == 0`(manifest `hv600-iopm` primary).

DB 를 쓰는 검사(②~⑤)는 `data/pg_isolation.create_isolated_schema()` 격리 스키마에서만
돈다 — 공유 `public` 을 건드리지 않는다. 끝나면 `drop_isolated_schema()`.

실행:  DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" uv run python spikes/model_enum_contract.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402

from backend import manifest  # noqa: E402
from data import dbcompat, pg_isolation  # noqa: E402
from mcp_server import db as db_mod  # noqa: E402
from mcp_server.tools.lookup_error_code import lookup_error_code  # noqa: E402
from mcp_server.tools.rag_search_manual import rag_search_manual  # noqa: E402

EXPECTED = ("iG5A", "S100", "IE5", "HV600")
ENUM_NAMES = {"MODELS", "VALID_MODELS", "_VALID_MODELS"}

# docs/sprints/sprint-19.md MQ-1903 「변경 파일」 목록의 enum 10곳 그대로.
ENUM_FILES = [
    "backend/manifest.py",
    "backend/agent/prompts.py",
    "backend/services/po.py",
    "mcp_server/rag.py",
    "mcp_server/tools/lookup_error_code.py",
    "mcp_server/tools/create_po_draft.py",
    "mcp_server/tools/create_repair_record.py",
    "data/inventory.py",
    "data/chunk_manual.py",
    "data/repair_record.py",
]

SCAN_DIRS = ["backend", "mcp_server", "data", "spikes", "eval"]
# 구(舊) 3종 튜플 리터럴 — 따옴표 종류·공백 변주를 함께 잡는다.
STALE_PATTERN = re.compile(r"""\(\s*["']iG5A["']\s*,\s*["']S100["']\s*,\s*["']IE5["']\s*\)""")

results: list[tuple[str, bool, str]] = []
_pg_schemas: list[str] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


# ── ① enum 정적 검사 ─────────────────────────────────────────────────────────────


def _find_enum_tuple(path: Path) -> tuple | None:
    """모듈 최상위 Assign/AnnAssign 중 ENUM_NAMES 이름에 튜플 리터럴이 배정된 곳을 찾아
    `ast.literal_eval` 값을 돌려준다(소스를 import·실행하지 않는다). 없으면 None."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        else:
            continue
        for t in targets:
            if isinstance(t, ast.Name) and t.id in ENUM_NAMES and isinstance(value, ast.Tuple):
                try:
                    return ast.literal_eval(value)
                except (ValueError, SyntaxError):
                    return None
    return None


def check_enum_points() -> None:
    per_file: dict[str, tuple | None] = {}
    matched = 0
    for rel in ENUM_FILES:
        value = _find_enum_tuple(ROOT / rel)
        per_file[rel] = value
        if value == EXPECTED:
            matched += 1
    check(
        "① enum 코드 10곳 전수 = ('iG5A','S100','IE5','HV600')",
        matched == len(ENUM_FILES) == 10,
        f"일치={matched}/10, 상세={ {k: v for k, v in per_file.items() if v != EXPECTED} or '전부 일치'}",
    )

    # 레포 전역 구(舊) 3종 튜플 잔존 0건 — 부재 검사에는 양성 축(스캐너 생존 프로브)을 함께 건다.
    self_path = Path(__file__).resolve()
    stale_hits: list[str] = []
    scanned = 0
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            if p.resolve() == self_path:
                # 이 스파이크 자신은 제외한다 — 아래 오라클 프로브가 구(舊) 튜플 리터럴을
                # **의도적으로** 문자열로 담고 있어(스캐너가 살아 있는지 증명하는 용도),
                # 스캔 대상에 포함하면 스캐너 자신이 자기 오라클을 "잔존"으로 오탐한다.
                continue
            scanned += 1
            text = p.read_text(encoding="utf-8", errors="ignore")
            if STALE_PATTERN.search(text):
                stale_hits.append(str(p.relative_to(ROOT)))
    probe_hit = bool(STALE_PATTERN.search('("iG5A", "S100", "IE5")'))
    check(
        "①-b 레포 전역 구(舊) 3종 튜플 잔존 0건 (스캐너 생존 프로브 포함)",
        not stale_hits and scanned > 0 and probe_hit,
        f"잔존={stale_hits or '없음'}, 스캔 파일수={scanned}, 프로브매칭={probe_hit}",
    )


# ── ② DB CHECK ──────────────────────────────────────────────────────────────────


def _constraintdefs(con, table: str) -> list[str]:
    rows = con.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
        f" WHERE conrelid = '{table}'::regclass AND contype = 'c'"
    ).fetchall()
    return [r[0] for r in rows]


def check_db_constraints(dsn: str) -> None:
    con = dbcompat.connect_dsn(dsn)
    try:
        equipment_defs = [d for d in _constraintdefs(con, "equipment") if "model" in d]
        check(
            "② equipment.model CHECK 에 HV600 포함·IE5 미포함 (D109 ⓒ 보존)",
            bool(equipment_defs)
            and any("HV600" in d for d in equipment_defs)
            and not any("IE5" in d for d in equipment_defs),
            f"equipment.model CHECK={equipment_defs}",
        )

        chunk_defs = [d for d in _constraintdefs(con, "manual_chunks") if "model" in d]
        joined = " ".join(chunk_defs)
        check(
            "②-b manual_chunks.model CHECK 4종(iG5A·S100·IE5·HV600) 전부 포함",
            bool(chunk_defs) and all(m in joined for m in EXPECTED),
            f"manual_chunks.model CHECK={chunk_defs}",
        )
    finally:
        con.close()


# ── ③ D155 형식 ──────────────────────────────────────────────────────────────────

_ROW_TEMPLATE = ("HV600", None, None, "임시 검증행", "warning", "[]", "[]", None, 1, None, None)


def _try_insert(con, code: str) -> tuple[bool, str, bool]:
    """(성공여부, 에러상세, CheckViolation여부)."""
    row = (_ROW_TEMPLATE[0], code, code, *_ROW_TEMPLATE[3:])
    try:
        con.execute("INSERT INTO error_codes VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
        return True, "", False
    except Exception as e:  # noqa: BLE001 — 원인 분류는 __cause__ 로 본다
        cause = e.__cause__
        return False, str(e), isinstance(cause, psycopg.errors.CheckViolation)


def check_d155_format(dsn: str) -> None:
    con = dbcompat.connect_dsn(dsn)
    try:
        positive_codes = ["CPF06", "ER-01"]  # 5자 · 하이픈 포함 — D155 양성 축
        negative_codes = ["ABCDEF", "er-01", "E R"]  # 6자 · 소문자 · 공백 — D155 음성 축

        pos = {c: _try_insert(con, c) for c in positive_codes}
        neg = {c: _try_insert(con, c) for c in negative_codes}

        check(
            "③ D155 형식 양성 — 5자·하이픈 코드 INSERT 성공",
            all(ok for ok, _, _ in pos.values()),
            f"positive={ {c: ok for c, (ok, _, _) in pos.items()} }",
        )
        check(
            "③-b D155 형식 음성 — 6자/소문자/공백 코드는 CheckViolation",
            all((not ok) and is_check for ok, _, is_check in neg.values()),
            f"negative(실패+CheckViolation 기대)="
            f"{ {c: (ok, is_check) for c, (ok, _, is_check) in neg.items()} }",
        )
    finally:
        con.close()


# ── ④ 기존 70행 유지 ──────────────────────────────────────────────────────────────


def check_existing_rows(dsn: str) -> None:
    con = dbcompat.connect_dsn(dsn)
    try:
        count = con.execute("SELECT count(*) FROM error_codes WHERE model != 'HV600'").fetchone()[0]
        check(
            "④ 기존 70행이 새 CHECK 하에서도 그대로 유지 (격리 복제본)",
            count == 70,
            f"count={count}",
        )
    finally:
        con.close()


# ── ⑤ 승격 전 게이트 ──────────────────────────────────────────────────────────────


def check_promotion_gate(dsn: str) -> None:
    db_mod.DB_PATH = dsn
    try:
        not_found = lookup_error_code(model="HV600", code="GF")
        keys_ok = set(not_found.keys()) == {"status", "model", "code", "message"}
        anchor = lookup_error_code(model="iG5A", code="OHt")

        con = dbcompat.connect_dsn(dsn)
        try:
            ig5a_codes = {
                r[0] for r in con.execute("SELECT code FROM error_codes WHERE model = 'iG5A'").fetchall()
            }
            hv600_rows = con.execute(
                "SELECT count(*) FROM error_codes WHERE model = 'HV600'"
            ).fetchone()[0]
        finally:
            con.close()

        message = str(not_found.get("message", ""))
        leaked = {c for c in ig5a_codes if c != "GF" and re.search(rf"\b{re.escape(c)}\b", message)}

        check(
            "⑤ 승격 전 게이트 — HV600 0행 상태에서 lookup not_found + 키 집합 정확 + 코드 토큰 누출 없음"
            " + iG5A 앵커 ok",
            hv600_rows == 0
            and not_found.get("status") == "not_found"
            and keys_ok
            and not leaked
            and anchor.get("status") == "ok",
            f"hv600_rows={hv600_rows}, not_found={not_found}, 키집합일치={keys_ok}, 누출={leaked or '없음'}, "
            f"anchor_status={anchor.get('status')}",
        )
    finally:
        db_mod.DB_PATH = None


# ── ⑥·⑦ DB 밖 계약 ────────────────────────────────────────────────────────────────


def check_rag_gate(dsn: str) -> None:
    """격리 스키마 **DROP 전**, `manual_chunks` 에 HV600 행이 아직 0건인 상태에서 돈다
    (2026-09-25 리뷰 반영). 예전에는 이 검사가 DROP **뒤**에 `db_mod.DB_PATH=None` 인 채로
    돌아 공유 `public` 스키마에 의존했다 — MQ-1909 가 HV600 을 승격하면 그 순간부터
    `manual_chunks` 에 HV600 행이 생겨 이 검사가 FAIL 로 뒤집힌다. 격리 스키마 안에서
    돌리고 "HV600 manual_chunks 0건"을 양성 축으로 함께 확인해야 지금 통과가
    "판정 로직이 맞아서"인지 "격리 스키마가 원래 비어서"인지 구분된다."""
    db_mod.DB_PATH = dsn
    try:
        con = dbcompat.connect_dsn(dsn)
        try:
            hv600_chunks = con.execute(
                "SELECT count(*) FROM manual_chunks WHERE model = 'HV600'"
            ).fetchone()[0]
        finally:
            con.close()

        result = rag_search_manual(model="HV600", query="점검 절차")
        check(
            "⑥ rag_search_manual(HV600) → error/index_not_built (격리 스키마 안, DROP 전 —"
            " HV600 manual_chunks 0건 양성 축 포함, empty 아님, D50 논리)",
            hv600_chunks == 0
            and result.get("status") == "error"
            and result.get("reason") == "index_not_built",
            f"HV600 manual_chunks={hv600_chunks} · "
            f"result={ {k: v for k, v in result.items() if k != 'message'} }",
        )
    finally:
        db_mod.DB_PATH = None


def check_manifest_offset() -> None:
    offset = manifest.print_page_offset("HV600")
    check(
        "⑦ backend.manifest.print_page_offset('HV600') == 0 (hv600-iopm primary)",
        offset == 0,
        f"offset={offset}",
    )


def main() -> None:
    check_enum_points()

    if not dbcompat.USE_POSTGRES:
        check(
            "② DB CHECK·③ D155 형식·④ 기존행·⑤ 승격 게이트·⑥ RAG 게이트",
            False,
            "DATABASE_URL 미설정 — Postgres 격리 스키마 검사는 Postgres 타겟에서만 가능",
        )
    else:
        schema, dsn = pg_isolation.create_isolated_schema("model_enum", clone_data=True)
        _pg_schemas.append(schema)
        try:
            check_db_constraints(dsn)
            # ⑤ 를 ③ 보다 먼저 — ③ 이 HV600 행(CPF06·ER-01)을 INSERT 하므로 그 뒤에 재면
            # 「승격 전(HV600 0행)」이 아니라 「행이 있는 기종의 미지 코드」만 증명한다(리뷰 지적)
            check_promotion_gate(dsn)
            check_d155_format(dsn)
            check_existing_rows(dsn)
            # ⑥ 도 격리 스키마 DROP **전**에 돈다 — 2026-09-25 리뷰 반영, check_rag_gate 참고.
            check_rag_gate(dsn)
        finally:
            db_mod.DB_PATH = None
            for s in _pg_schemas:
                pg_isolation.drop_isolated_schema(s)

    check_manifest_offset()

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 46))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 46))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(
        f"\n통과 ({len(results)}건) — enum 10곳 + DB CHECK 3곳(equipment·manual_chunks·D155 형식) "
        "+ 승격 전 게이트(D146·절대규칙 6) 준수."
    )


if __name__ == "__main__":
    main()
