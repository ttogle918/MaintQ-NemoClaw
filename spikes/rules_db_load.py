# -*- coding: utf-8 -*-
"""근거 계층 DB 로더 · build_facts 계약 검증 (MQ-601b · D60·D61·D62·D77).

검증 대상:
  ⓐ 파일 로더 == DB 로더 (LawRef·Rule dataclass 동치) — 정본은 파일, DB는 사본 (D60)
  ⓑ DB 사본이 무결성 게이트를 우회하지 못한다 — 근거 없는 룰·미등록 법령 참조 거부 (D61)
  ⓒ NULL 컬럼은 facts 키에서 빠진다 (D62)
  ⓓ 그 결과 판정이 INSUFFICIENT_FACTS 다 — **CLEAR 로 내려가지 않는다**

**임시 DB 만 만든다.** `data/maintq.db` 를 열지 않는다 — 스키마·적재 경로는 `data/seed.py`
의 것을 그대로 재사용해서(create_schema → seed_rule_catalog) 실 시드와 같은 경로를 밟는다.

실행:  uv run python spikes/rules_db_load.py
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.rules.engine import (  # noqa: E402
    RuleIntegrityError,
    build_facts,
    check_disposal_blockers,
    evaluate_rule,
    load_laws,
    load_laws_from_db,
    load_rules,
    load_rules_from_db,
)
from data.seed import create_schema, seed_rule_catalog  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def make_db(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys=ON")
    create_schema(con)
    seed_rule_catalog(con)  # ← load_rules 무결성 게이트를 경유하는 실 시드 경로
    con.commit()
    return con


# 스키마 CHECK 가 없는 **사본** — 실제 ERP 에서 떠 온 테이블에는 우리 CHECK 가 없다.
# 로더의 무결성 게이트가 스키마 제약에 업혀 있는지, 스스로 서는지를 가르는 픽스처다.
LOOSE_DDL = """
CREATE TABLE law_refs (
  law_ref_id TEXT PRIMARY KEY, law_name TEXT, article TEXT, title TEXT, text TEXT,
  fetch_status TEXT, effective_from DATE, effective_to DATE, source_url TEXT,
  text_hash TEXT, verification_note TEXT);
CREATE TABLE rules (
  rule_id TEXT, rule_version INTEGER, label TEXT, category TEXT, disposal_type TEXT,
  source_type TEXT, law_refs TEXT, contract_refs TEXT, interpretation TEXT,
  required_facts TEXT, trigger TEXT, boundary TEXT, message TEXT, resolve_options TEXT,
  confidence TEXT, requires_expert_review BOOLEAN, PRIMARY KEY (rule_id, rule_version));
"""

# 근거 없는 룰 1행. 파일이었다면 load_rules 가 거부했을 값을 **DB 에 직접** 심는다
BAD_ROWS = {
    "no_evidence": ("BAD-NO-EVIDENCE", "[]", "[]", '{"all_of": []}'),
    "unknown_law": ("BAD-UNKNOWN-LAW", '["KR-NOT-REGISTERED-999"]', "[]", '{"all_of": []}'),
    # 근거는 계약 참조로 채우고(D61 통과) trigger 만 깨뜨린다 — JSON 파싱 게이트를 고립 검증
    "broken_json": ("BAD-JSON", "[]", '["여신거래기본약관"]', "{not json"),
}


def insert_bad_rule(con: sqlite3.Connection, kind: str, version: int = 1) -> None:
    rule_id, law_refs, contract_refs, trigger = BAD_ROWS[kind]
    con.execute(
        "INSERT INTO rules (rule_id, rule_version, label, category, disposal_type, source_type,"
        " law_refs, contract_refs, interpretation, required_facts, trigger, boundary, message,"
        " resolve_options, confidence, requires_expert_review)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            rule_id,
            version,
            "심어 넣은 결함 룰",
            "TAX",
            "BLOCKING",
            "LAW",
            law_refs,
            contract_refs,
            "",
            "[]",
            trigger,
            None,
            "",
            "[]",
            "LOW",
            0,
        ),
    )
    con.commit()


def raises_integrity(con: sqlite3.Connection) -> str | None:
    laws = load_laws_from_db(con)
    try:
        load_rules_from_db(con, laws)
    except RuleIntegrityError as exc:
        return str(exc)
    return None


def run(tmp: Path) -> None:
    # ── ⓐ 파일 == DB
    con = make_db(tmp / "catalog.db")
    file_laws, db_laws = load_laws(), load_laws_from_db(con)
    check(
        "① LawRef 파일 == DB (D60)",
        file_laws == db_laws and len(db_laws) > 0,
        f"파일 {len(file_laws)}건 / DB {len(db_laws)}건"
        + ("" if file_laws == db_laws else f" · 차이 {set(file_laws) ^ set(db_laws)}"),
    )

    file_rules, db_rules = load_rules(file_laws), load_rules_from_db(con, db_laws)
    diff = [r for r in file_rules if file_rules[r] != db_rules.get(r)]
    check(
        "② Rule 파일 == DB (dataclass 동치)",
        file_rules == db_rules and len(db_rules) == 5,
        f"파일 {len(file_rules)}종 / DB {len(db_rules)}종" + (f" · 불일치 {diff}" if diff else ""),
    )
    check(
        "③ rule_version 이 사본에도 실린다 (D60 복합 PK)",
        all(db_rules[r].rule_version == file_rules[r].rule_version for r in file_rules),
        str({r: db_rules[r].rule_version for r in sorted(db_rules)}),
    )
    con.close()

    # ── ⓑ 무결성 게이트 — DB 사본이 우회로가 되면 안 된다 (D61)
    for key, label in (
        ("no_evidence", "④ 근거 없는 룰 행 → RuleIntegrityError (D61)"),
        ("unknown_law", "⑤ 미등록 법령 참조 행 → RuleIntegrityError"),
    ):
        con = make_db(tmp / f"{key}.db")
        insert_bad_rule(con, key)
        msg = raises_integrity(con)
        check(label, msg is not None, msg or "로드가 통과해 버림 — DB 가 게이트를 우회한다")
        con.close()

    # 깨진 JSON — 스키마 CHECK 와 로더 게이트가 **각각** 막아야 한다
    # (둘 중 하나만 막으면 CHECK 없는 사본에서 샌다)
    con = make_db(tmp / "broken_schema.db")
    try:
        insert_bad_rule(con, "broken_json")
        schema_rejected, schema_detail = False, "CHECK 가 깨진 JSON 을 통과시켰다"
    except sqlite3.IntegrityError as exc:
        schema_rejected, schema_detail = True, str(exc)
    con.close()
    check("⑥ 깨진 JSON INSERT → 스키마 CHECK 거부", schema_rejected, schema_detail)

    con = sqlite3.connect(tmp / "loose.db")
    con.executescript(LOOSE_DDL)
    insert_bad_rule(con, "broken_json")
    msg = raises_integrity(con)
    check(
        "⑦ CHECK 없는 사본에서도 로더가 거부 (조용한 기본값 금지)",
        msg is not None,
        msg or "로드가 통과해 버림 — 게이트가 스키마 CHECK 에 업혀 있다",
    )
    con.close()

    # 개정본이 쌓여도 판정에는 최신 1행만 (D60)
    con = make_db(tmp / "versions.db")
    con.execute(
        "INSERT INTO rules SELECT rule_id, rule_version + 1, label, category, disposal_type,"
        " source_type, law_refs, contract_refs, '개정본', required_facts, trigger, boundary,"
        " message, resolve_options, confidence, requires_expert_review FROM rules"
        " WHERE rule_id='VAT-INVOICE'"
    )
    con.commit()
    laws = load_laws_from_db(con)
    rules = load_rules_from_db(con, laws)
    n_rows = con.execute("SELECT count(*) FROM rules WHERE rule_id='VAT-INVOICE'").fetchone()[0]
    check(
        "⑧ 개정본 공존 시 최신 rule_version 만 로드 (D60)",
        n_rows == 2 and len(rules) == 5 and rules["VAT-INVOICE"].interpretation == "개정본",
        f"VAT-INVOICE 행 {n_rows}개 → 로드 v{rules['VAT-INVOICE'].rule_version}",
    )

    # ── ⓒ NULL 컬럼은 facts 키에서 빠진다 (D62)
    con.execute(
        "INSERT INTO assets (asset_id, name, category, line_id, status)"
        " VALUES ('AST-NULL','사실 미상 자산','일반산업',9,'IN_USE')"
    )
    # 값이 있는 자산 — False/0 이 값으로 남는지 대조군. insured=1 (부보) 로 둔다 (D78)
    con.execute(
        "INSERT INTO assets (asset_id, name, category, line_id, status, tax_credit_applied,"
        " has_lien, lien_creditor, insured, policy_id, safety_inspection_target, acquired_at)"
        " VALUES ('AST-KNOWN','사실 확정 자산','일반산업',9,'IN_USE',0,0,'',1,'POL-1',0,'2020-02-10')"
    )
    con.commit()
    con.row_factory = sqlite3.Row
    null_row = con.execute("SELECT * FROM assets WHERE asset_id='AST-NULL'").fetchone()
    known_row = con.execute("SELECT * FROM assets WHERE asset_id='AST-KNOWN'").fetchone()

    facts = build_facts(null_row)
    missing_keys = [
        k
        for k in ("tax_credit_applied", "has_lien", "lien_consent_ref", "policy_id", "acquired_at")
        if k in facts
    ]
    check(
        "⑨ NULL 컬럼이 facts 키에서 빠진다 (D62)",
        not missing_keys,
        f"facts 키 {sorted(facts)}"
        + (f" · 새어 들어온 NULL {missing_keys}" if missing_keys else ""),
    )
    nones = [k for k, v in facts.items() if v is None]
    check("⑩ facts 에 None 값 키가 없다", not nones, f"None 값 키 {nones or 0}건")

    known = build_facts(known_row, disposal_date="2021-07-10")
    check(
        "⑪ False·0 은 값이므로 남는다",
        known["tax_credit_applied"] is False
        and known["has_lien"] is False
        and known["lien_creditor"] == "",
        f"tax_credit_applied={known['tax_credit_applied']!r}, has_lien={known['has_lien']!r},"
        f" lien_creditor={known['lien_creditor']!r}",
    )
    check(
        "⑫ 파생 필드는 원천이 둘 다 있을 때만 (months)",
        known["months_since_acquisition"] == 17
        and "months_since_acquisition" not in build_facts(known_row),
        f"disposal_date 有 → {known['months_since_acquisition']}개월 / 無 → 키 없음",
    )
    check(
        "⑬ vat_invoice_issued 는 채우고 거래 사실은 안 채운다 (D77)",
        known["vat_invoice_issued"] is False
        and known["disposal_mode"] == "SALE"
        and "sale_amount" not in known
        and "buyer_biz_no" not in known,
        "precheck = 거래 성립 전 → 미발행이 확정 사실 · 매각가액/매수인은 원천 없음",
    )
    check(
        "⑭ risk_* 는 키 자체가 없다 (F6 원천 부재)",
        not [
            k
            for k in (
                "risk_grade_before",
                "risk_grade_after",
                "risk_score_delta_pct",
                "risk_grade_changed",
            )
            if k in known
        ],
        "억지로 CLEAR 를 만들지 않는다",
    )

    # boundary 가 없는 키를 읽어도 예외를 내거나 잘못 HOLD 로 빠지지 않아야 한다
    insurance = load_rules(load_laws())["INSURANCE-NOTIFY"]
    try:
        f = evaluate_rule(insurance, known, load_laws())
        boundary_ok, boundary_detail = f.verdict == "TRIGGERED", f"verdict={f.verdict}"
    except Exception as exc:  # noqa: BLE001
        boundary_ok, boundary_detail = False, f"{type(exc).__name__}: {exc}"
    check(
        "⑮ risk_score_delta_pct 키 부재 → 경계 검사 건너뜀 (예외·오탐 HOLD 없음)",
        boundary_ok,
        boundary_detail,
    )

    # ── ⓓ 사실 부족은 CLEAR 가 아니다. D79 로 **자기 이름을 가진 최상위 verdict** 다
    verdicts = check_disposal_blockers(facts)
    insufficient = {f["rule_id"] for f in verdicts["insufficient"]}
    check(
        "⑯ 사실 전부 NULL → INSUFFICIENT_FACTS (≠ CLEAR, ≠ HOLD) [D79]",
        verdicts["verdict"] == "INSUFFICIENT_FACTS" and len(insufficient) >= 4,
        f"verdict={verdicts['verdict']} · insufficient={sorted(insufficient)}"
        f" · blockers={len(verdicts['blockers'])}",
    )
    check(
        "⑰ 반환 키가 asset_id 다 (D68 — equipment_id 아님)",
        "asset_id" in verdicts and "equipment_id" not in verdicts,
        f"asset_id={verdicts.get('asset_id')!r} · 키 {sorted(verdicts)[:4]}…",
    )

    # 확인된 미부보(insured=0) 는 "모름"(NULL)과 다르다 — D78 의 3상태가 DB→facts 를 통과하는지
    con.execute(
        "INSERT INTO assets (asset_id, name, category, line_id, status, tax_credit_applied,"
        " has_lien, lien_creditor, lien_consent_ref, insured, safety_inspection_target,"
        " acquired_at) VALUES ('AST-UNINSURED','미부보 자산','일반산업',9,'IN_USE',0,0,'','',0,0,"
        "'2023-02-17')"
    )
    con.commit()
    lift = con.execute("SELECT * FROM assets WHERE asset_id='AST-UNINSURED'").fetchone()
    sale = check_disposal_blockers(build_facts(lift, disposal_date="2028-02-17"))
    scrap = check_disposal_blockers(
        build_facts(lift, disposal_mode="SCRAP", disposal_date="2028-02-17")
    )
    check(
        "⑱ insured=0 은 '모름'이 아니라 '확인된 미부보' (D78)",
        build_facts(lift)["insured"] is False and scrap["verdict"] == "CLEAR",
        f"insured={build_facts(lift)['insured']!r} → SCRAP verdict={scrap['verdict']}",
    )
    check(
        "⑲ 같은 자산도 SALE 이면 CONDITIONAL (매각 = 최소 CONDITIONAL, D78 부수)",
        sale["verdict"] == "CONDITIONAL"
        and {p["rule_id"] for p in sale["preconditions"]} == {"VAT-INVOICE"},
        f"SALE={sale['verdict']} preconds={[p['rule_id'] for p in sale['preconditions']]}"
        f" / SCRAP={scrap['verdict']}",
    )
    con.close()


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("근거계층 DB 로더 · build_facts 계약 검증 — 임시 DB (실 DB 미사용)\n")
    real_db = ROOT / "data" / "maintq.db"
    before = real_db.stat().st_mtime_ns if real_db.exists() else None

    # Windows 는 sqlite 커넥션이 하나라도 열려 있으면 파일을 못 지운다 —
    # 정리 실패로 계약 검증 결과가 가려지지 않게 한다
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        run(Path(td))

    after = real_db.stat().st_mtime_ns if real_db.exists() else None
    check("⑳ 실 DB 불변 (mtime)", before == after, "data/maintq.db 를 열지도 않았다")

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 46))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 46))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(
        f"\n통과 ({len(results)}건) — D60(파일이 정본)·D61(사본도 게이트 통과)·"
        "D62(NULL 은 CLEAR 가 아니다)·D77 준수"
    )


if __name__ == "__main__":
    main()
