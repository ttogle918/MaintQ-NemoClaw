"""
룰 카탈로그 테스트.

완료 기준 "룰 커버리지 100% (정의된 룰 = 테스트된 룰)"를 강제한다.
새 룰을 추가하고 테스트를 안 쓰면 test_every_rule_is_covered 가 실패한다.

실행:  uv run python -m pytest data/rules/test_rules.py -q
"""

import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from engine import (  # noqa: E402
    RuleIntegrityError,
    check_disposal_blockers,
    evaluate_rule,
    load_laws,
    load_rules,
    normalize,
    text_hash,
)

COVERED = {
    "TAX-CREDIT-2Y",
    "LIEN-CONSENT",
    "INSURANCE-NOTIFY",
    "VAT-INVOICE",
    "SAFETY-INSPECTION",
}


@pytest.fixture(scope="module")
def laws():
    return load_laws()


@pytest.fixture(scope="module")
def rules(laws):
    return load_rules(laws)


# ------------------------------------------------ 무결성


def test_every_rule_is_covered(rules):
    """정의된 룰 = 테스트된 룰."""
    assert set(rules) == COVERED, f"미커버 룰: {set(rules) - COVERED}"


def test_every_rule_has_evidence(rules):
    """근거 없는 룰은 존재할 수 없다 (D61)."""
    for rule in rules.values():
        assert rule.law_refs or rule.contract_refs, f"{rule.rule_id}: 근거 없음"


def test_law_refs_all_resolvable(rules, laws):
    for rule in rules.values():
        for ref in rule.law_refs:
            assert ref in laws, f"{rule.rule_id} → {ref} 미등록"


def test_rule_without_evidence_is_rejected(tmp_path, monkeypatch):
    """근거를 지운 룰은 로드 단계에서 거부되어야 한다."""
    import engine

    bad_dir = tmp_path / "rules"
    bad_dir.mkdir()
    (bad_dir / "BAD.json").write_text(
        json.dumps(
            {
                "rule_id": "BAD",
                "label": "근거 없는 룰",
                "category": "TAX",
                "disposal_type": "BLOCKING",
                "source_type": "LAW",
                "law_refs": [],
                "interpretation": "",
                "trigger": {"all_of": []},
                "message": "",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(engine, "RULES_DIR", bad_dir)
    with pytest.raises(RuleIntegrityError):
        engine.load_rules(engine.load_laws())


def test_normalization_stabilizes_hash():
    """공백·전각 변형으로 해시가 흔들리면 개정 감지가 오작동한다."""
    a = "제24조（통합투자세액공제）  내국인이…"
    b = "제24조(통합투자세액공제) 내국인이…"
    assert text_hash(a) == text_hash(b)
    assert normalize("  a\n\n b ") == "a b"


# ------------------------------------------------ 룰별 동작


def test_tax_credit_blocks_within_window(rules, laws):
    f = evaluate_rule(
        rules["TAX-CREDIT-2Y"],
        {"tax_credit_applied": True, "acquired_at": "2025-03-01",
         "disposal_date": "2026-08-10", "months_since_acquisition": 17},
        laws,
    )
    assert f.verdict == "TRIGGERED"
    assert "KR-STTC-24" in f.law_refs
    assert f.citations, "근거 인용이 비어 있으면 안 된다"


def test_tax_credit_holds_on_boundary(rules, laws):
    """22~26개월 경계는 단정하지 않는다 (D62)."""
    f = evaluate_rule(
        rules["TAX-CREDIT-2Y"],
        {"tax_credit_applied": True, "acquired_at": "2024-09-01",
         "disposal_date": "2026-08-10", "months_since_acquisition": 23},
        laws,
    )
    assert f.verdict == "HOLD"


def test_tax_credit_clear_after_window(rules, laws):
    f = evaluate_rule(
        rules["TAX-CREDIT-2Y"],
        {"tax_credit_applied": True, "acquired_at": "2023-01-01",
         "disposal_date": "2026-08-10", "months_since_acquisition": 43},
        laws,
    )
    assert f.verdict == "CLEAR"


def test_lien_blocks_without_consent(rules, laws):
    f = evaluate_rule(
        rules["LIEN-CONSENT"],
        {"has_lien": True, "lien_creditor": "XX은행", "lien_consent_ref": None},
        laws,
    )
    assert f.verdict == "TRIGGERED"
    assert "여신거래기본약관" in f.citations, "계약 근거도 인용되어야 한다"


def test_lien_clears_with_consent(rules, laws):
    f = evaluate_rule(
        rules["LIEN-CONSENT"],
        {"has_lien": True, "lien_creditor": "XX은행", "lien_consent_ref": "DOC-8821"},
        laws,
    )
    assert f.verdict == "CLEAR"


def test_insurance_notify_holds_on_small_delta(rules, laws):
    """위험도 변화가 미미하면 '현저히'를 단정하지 않는다."""
    f = evaluate_rule(
        rules["INSURANCE-NOTIFY"],
        {"policy_id": "POL-01", "building_id": "BLD-1",
         "risk_grade_before": "C", "risk_grade_after": "C",
         "risk_score_delta_pct": 4},
        laws,
    )
    assert f.verdict == "HOLD"


def test_insurance_notify_triggers_on_insured_asset(rules, laws):
    f = evaluate_rule(
        rules["INSURANCE-NOTIFY"],
        {"policy_id": "POL-01", "building_id": "BLD-1",
         "risk_grade_before": "C", "risk_grade_after": "B",
         "risk_score_delta_pct": 35},
        laws,
    )
    assert f.verdict == "TRIGGERED"


def test_vat_invoice_only_for_sale(rules, laws):
    sale = evaluate_rule(
        rules["VAT-INVOICE"],
        {"disposal_mode": "SALE", "sale_amount": 42_000_000,
         "buyer_biz_no": "123-45-67890", "vat_invoice_issued": False},
        laws,
    )
    scrap = evaluate_rule(
        rules["VAT-INVOICE"],
        {"disposal_mode": "SCRAP", "sale_amount": 0,
         "buyer_biz_no": None, "vat_invoice_issued": False},
        laws,
    )
    assert sale.verdict == "TRIGGERED"
    assert scrap.verdict == "CLEAR", "폐기는 공급이 아니므로 세금계산서 대상이 아니다"


def test_safety_inspection_triggers_for_target_machine(rules, laws):
    f = evaluate_rule(
        rules["SAFETY-INSPECTION"],
        {"safety_inspection_target": True, "last_inspection_date": "2025-06-01",
         "inspection_valid_until": "2027-06-01", "disposal_mode": "SALE"},
        laws,
    )
    assert f.verdict == "TRIGGERED"
    assert f.disposal_type == "PRECONDITION", "안전검사는 차단이 아니라 선행조건"


def test_missing_facts_are_not_treated_as_clear(rules, laws):
    """사실을 모르는 것과 조건에 해당하지 않는 것은 다르다 (D62)."""
    f = evaluate_rule(rules["TAX-CREDIT-2Y"], {"tax_credit_applied": True}, laws)
    assert f.verdict == "INSUFFICIENT_FACTS"
    assert "acquired_at" in f.missing_facts


# ------------------------------------------------ 통합


def _full_facts(**over):
    facts = {
        "equipment_id": "INV-L3-01",
        "tax_credit_applied": True,
        "acquired_at": "2025-03-01",
        "disposal_date": "2026-08-10",
        "months_since_acquisition": 17,
        "has_lien": True,
        "lien_creditor": "XX은행",
        "lien_consent_ref": None,
        "policy_id": "POL-01",
        "building_id": "BLD-1",
        "risk_grade_before": "C",
        "risk_grade_after": "B",
        "risk_score_delta_pct": 30,
        "disposal_mode": "SALE",
        "sale_amount": 42_000_000,
        "buyer_biz_no": "123-45-67890",
        "vat_invoice_issued": False,
        "safety_inspection_target": True,
        "last_inspection_date": "2025-06-01",
        "inspection_valid_until": "2027-06-01",
    }
    facts.update(over)
    return facts


def test_blocked_when_any_blocker_triggers():
    result = check_disposal_blockers(_full_facts(), at=date(2026, 8, 4))
    assert result["verdict"] == "BLOCKED"
    ids = {b["rule_id"] for b in result["blockers"]}
    assert ids == {"TAX-CREDIT-2Y", "LIEN-CONSENT"}


def test_conditional_when_only_preconditions():
    result = check_disposal_blockers(
        _full_facts(months_since_acquisition=43, lien_consent_ref="DOC-8821"),
        at=date(2026, 8, 4),
    )
    assert result["verdict"] == "CONDITIONAL"
    assert {p["rule_id"] for p in result["preconditions"]} >= {"VAT-INVOICE", "SAFETY-INSPECTION"}


def test_every_finding_carries_citations():
    """근거 미인용 판정은 존재할 수 없다 (D61)."""
    result = check_disposal_blockers(_full_facts(), at=date(2026, 8, 4))
    for bucket in ("blockers", "preconditions", "holds"):
        for f in result[bucket]:
            assert f["citations"], f"{f['rule_id']}: 근거 인용 없음"


def test_result_declares_what_it_did_not_consider():
    """정직한 불확실성 — 고려하지 않은 것을 명시한다."""
    result = check_disposal_blockers(_full_facts(), at=date(2026, 8, 4))
    assert result["not_considered"]
    assert result["disclaimer"]
