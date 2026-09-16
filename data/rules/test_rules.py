"""
룰 카탈로그 테스트.

완료 기준 "룰 커버리지 100% (정의된 룰 = 테스트된 룰)"를 강제한다.
새 룰을 추가하고 테스트를 안 쓰면 test_every_rule_is_covered 가 실패한다.

실행:  uv run python -m pytest data/rules/test_rules.py -q
"""

import dataclasses
import itertools
import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from engine import (  # noqa: E402
    VERDICTS,
    RuleIntegrityError,
    build_facts,
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
        {
            "tax_credit_applied": True,
            "acquired_at": "2025-03-01",
            "disposal_date": "2026-08-10",
            "months_since_acquisition": 17,
        },
        laws,
    )
    assert f.verdict == "TRIGGERED"
    assert "KR-STTC-24" in f.law_refs
    assert f.citations, "근거 인용이 비어 있으면 안 된다"


def test_tax_credit_holds_on_boundary(rules, laws):
    """22~26개월 경계는 단정하지 않는다 (D62)."""
    f = evaluate_rule(
        rules["TAX-CREDIT-2Y"],
        {
            "tax_credit_applied": True,
            "acquired_at": "2024-09-01",
            "disposal_date": "2026-08-10",
            "months_since_acquisition": 23,
        },
        laws,
    )
    assert f.verdict == "HOLD"


def test_tax_credit_clear_after_window(rules, laws):
    f = evaluate_rule(
        rules["TAX-CREDIT-2Y"],
        {
            "tax_credit_applied": True,
            "acquired_at": "2023-01-01",
            "disposal_date": "2026-08-10",
            "months_since_acquisition": 43,
        },
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
        {
            "insured": True,
            "policy_id": "POL-01",
            "building_id": "BLD-1",
            "risk_grade_before": "C",
            "risk_grade_after": "C",
            "risk_score_delta_pct": 4,
        },
        laws,
    )
    assert f.verdict == "HOLD"


def test_insurance_notify_triggers_on_insured_asset(rules, laws):
    f = evaluate_rule(
        rules["INSURANCE-NOTIFY"],
        {
            "insured": True,
            "policy_id": "POL-01",
            "building_id": "BLD-1",
            "risk_grade_before": "C",
            "risk_grade_after": "B",
            "risk_score_delta_pct": 35,
        },
        laws,
    )
    assert f.verdict == "TRIGGERED"


def test_insurance_notify_clears_on_confirmed_uninsured(rules, laws):
    """D78 — '확인된 미부보'(insured=False)는 통지 대상이 아니다.

    v2 까지는 이 상태를 **표현할 방법 자체가 없었다** — `policy_id` 가 있으면 TRIGGERED,
    없으면 `required_facts` 누락으로 INSUFFICIENT_FACTS. 부보 여부를 별도 불리언으로
    분리하고서야 "해당 없음"을 말할 수 있게 됐다.
    """
    f = evaluate_rule(rules["INSURANCE-NOTIFY"], {"insured": False}, laws)
    assert f.verdict == "CLEAR"

    # 반대로 **모름**(키 부재)은 CLEAR 가 아니다 — 0 과 NULL 이 섞이면 D78 이 무의미해진다
    unknown = evaluate_rule(rules["INSURANCE-NOTIFY"], {}, laws)
    assert unknown.verdict == "INSUFFICIENT_FACTS"
    assert "insured" in unknown.missing_facts

    # policy_id 는 이제 증권 식별자일 뿐 — 있어도 판정을 바꾸지 않는다
    with_policy = evaluate_rule(
        rules["INSURANCE-NOTIFY"], {"insured": False, "policy_id": "POL-01"}, laws
    )
    assert with_policy.verdict == "CLEAR"


def test_vat_invoice_only_for_sale(rules, laws):
    sale = evaluate_rule(
        rules["VAT-INVOICE"],
        {
            "disposal_mode": "SALE",
            "sale_amount": 42_000_000,
            "buyer_biz_no": "123-45-67890",
            "vat_invoice_issued": False,
        },
        laws,
    )
    scrap = evaluate_rule(
        rules["VAT-INVOICE"],
        {
            "disposal_mode": "SCRAP",
            "sale_amount": 0,
            "buyer_biz_no": None,
            "vat_invoice_issued": False,
        },
        laws,
    )
    assert sale.verdict == "TRIGGERED"
    assert scrap.verdict == "CLEAR", "폐기는 공급이 아니므로 세금계산서 대상이 아니다"


def test_safety_inspection_triggers_for_target_machine(rules, laws):
    f = evaluate_rule(
        rules["SAFETY-INSPECTION"],
        {
            "safety_inspection_target": True,
            "last_inspection_date": "2025-06-01",
            "inspection_valid_until": "2027-06-01",
            "disposal_mode": "SALE",
        },
        laws,
    )
    assert f.verdict == "TRIGGERED"
    assert f.disposal_type == "PRECONDITION", "안전검사는 차단이 아니라 선행조건"


def test_missing_facts_are_not_treated_as_clear(rules, laws):
    """사실을 모르는 것과 조건에 해당하지 않는 것은 다르다 (D62)."""
    f = evaluate_rule(rules["TAX-CREDIT-2Y"], {"tax_credit_applied": True}, laws)
    assert f.verdict == "INSUFFICIENT_FACTS"
    assert "acquired_at" in f.missing_facts


def test_none_valued_key_is_not_caught_by_required_facts(rules, laws):
    """엔진의 누락 검사는 **값이 아니라 키 존재**를 본다 (N4).

    `05_DB_SCHEMA.md` 는 "NULL 이면 required_facts 검사에서 누락으로 잡힌다"고 쓰지만,
    그건 엔진의 성질이 아니라 **`build_facts` 가 키를 빼 주기 때문에** 성립한다.
    엔진에 직접 `None` 값 키를 넣으면 누락으로 잡히지 않는다 — 이 성질을 고정해 두지 않으면
    도구를 새로 만드는 사람이 `dict(row)` 를 그대로 넘겨 **"모른다"가 "CLEAR"로 바뀐다.**
    """
    raw = {"tax_credit_applied": None, "acquired_at": None, "disposal_date": None}
    f = evaluate_rule(rules["TAX-CREDIT-2Y"], raw, laws)
    assert f.verdict == "CLEAR", "지금 엔진은 None 값 키를 '값이 있다'로 본다 (계약 고정)"
    assert not f.missing_facts

    # 같은 원본 행을 build_facts 로 통과시키면 키가 빠져 INSUFFICIENT_FACTS 가 된다.
    # 즉 D62 를 지키는 것은 엔진이 아니라 build_facts 다.
    via_builder = evaluate_rule(rules["TAX-CREDIT-2Y"], build_facts(_asset_row(**raw)), laws)
    assert via_builder.verdict == "INSUFFICIENT_FACTS"
    assert "tax_credit_applied" in via_builder.missing_facts


# ------------------------------------------------ 발화 가능성 (D77)
#
# "어떤 사실 조합으로도 TRIGGERED 될 수 없는 룰"은 근거가 있어도 결함이다 (D77).
# D61(근거 있는가)이 못 잡는 구멍이라 로드 시점 검사가 아니라 회귀로 잡는다.
#
# ★ 탐색 공간을 `build_facts` 규약에 맞춘다 — **facts 에 None 값 키는 존재하지 않는다.**
#   그래서 `is_null` 조건은 오직 **키 부재**로만 만족된다. 이 규약을 빼고 `{f: None}` 을
#   허용하면 LIEN-CONSENT 같은 "선언과 트리거가 서로를 배제하는" 룰이 통과해 버린다.

_ABSENT = object()  # 그 키를 facts 에 넣지 않는다
_PRESENT = "<any-value>"  # 값이 있기만 하면 되는 자리


def _flip(value):
    """`eq` 조건을 빗나가게 하는 반대값."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    if isinstance(value, str):
        return value + "-OTHER"
    return _PRESENT


def _trigger_conds(trigger):
    return list(trigger.get("all_of", [])) + list(trigger.get("any_of", []))


def _candidate_space(rule):
    """룰이 실제로 읽는 필드별 후보값. 부재(_ABSENT)도 항상 후보다."""
    space: dict[str, list] = {}
    for cond in _trigger_conds(rule.trigger):
        field, op, value = cond["field"], cond["op"], cond.get("value")
        vals = space.setdefault(field, [])
        if op in ("eq", "ne"):
            vals += [value, _flip(value)]
        elif op in ("lt", "lte", "gt", "gte"):
            vals += [value - 1, value, value + 1]
        elif op == "is_not_null":
            vals.append(_PRESENT)
        # is_null 은 키 부재로만 만족된다 → 별도 후보 없음
    if rule.boundary:
        lo, hi = rule.boundary["review_band"]
        # 경계 **밖** 후보가 없으면 전 조합이 HOLD 로 빨려 들어가 발화가 불가능해진다
        space.setdefault(rule.boundary["field"], []).extend([lo - 1, hi + 1])
    for field in rule.required_facts:
        space.setdefault(field, []).append(_PRESENT)
    for field, vals in space.items():
        seen, uniq = set(), []
        for v in vals + [_ABSENT]:
            key = (type(v).__name__, repr(v))
            if key not in seen:
                seen.add(key)
                uniq.append(v)
        space[field] = uniq
    return space


def _facts_with_verdict(rule, laws, want):
    """`want` 판정을 만드는 사실 조합을 하나 찾는다. 없으면 None."""
    space = _candidate_space(rule)
    fields = sorted(space)
    for combo in itertools.product(*(space[f] for f in fields)):
        facts = {f: v for f, v in zip(fields, combo) if v is not _ABSENT}
        assert None not in facts.values(), "탐색 공간에 None 값이 섞이면 규약 위반이다"
        if evaluate_rule(rule, facts, laws).verdict == want:
            return facts
    return None


@pytest.mark.parametrize("rule_id", sorted(COVERED))
def test_every_rule_is_satisfiable(rules, laws, rule_id):
    """룰 5종 각각에 TRIGGERED 를 만드는 사실 조합이 존재해야 한다 (D77).

    실패 = required_facts 가 자기 트리거와 어긋나 논리적으로 발화 불가한 룰.
    """
    rule = rules[rule_id]
    facts = _facts_with_verdict(rule, laws, "TRIGGERED")
    assert facts is not None, (
        f"{rule_id}: 어떤 사실 조합으로도 TRIGGERED 되지 않는다 — "
        f"required_facts={rule.required_facts} 가 trigger 와 어긋난다 (D77)"
    )


@pytest.mark.parametrize("rule_id", sorted(COVERED))
def test_every_rule_is_clearable(rules, laws, rule_id):
    """룰 5종 각각에 **CLEAR 를 만드는** 사실 조합이 존재해야 한다 (D78).

    발화 가능성(D77)의 쌍둥이다. 발화만 되고 **해제될 수 없는 룰**은
    "이 조건에 해당하지 않는다"를 영원히 말하지 못하므로, 그 룰이 카탈로그에 있는 한
    어떤 자산도 `CLEAR` 를 받지 못한다 — 룰 하나가 시스템 전체의 판정을 고정시킨다.

    ★ `HOLD`·`INSUFFICIENT_FACTS` 는 해제로 치지 않는다. 그것들은 "아직 모른다"이지
      "해당 없음"이 아니다 (D62). 사실을 빼서 트리거를 피하는 건 해제가 아니라 회피다 —
      이걸 성공으로 세면 D78 이 잡으려는 결함(`policy_id` 가 있으면 TRIGGERED,
      없으면 INSUFFICIENT)이 그대로 통과한다.
    """
    rule = rules[rule_id]
    facts = _facts_with_verdict(rule, laws, "CLEAR")
    assert facts is not None, (
        f"{rule_id}: 어떤 사실 조합으로도 CLEAR 되지 않는다 — "
        f"'해당 없음'을 표현할 사실이 없다 (D78). required_facts={rule.required_facts}"
    )


def test_lien_empty_string_consent_does_not_trigger(rules, laws):
    """음성 케이스 — `''` 는 "확인된 해당 없음"이라 발화하지 않는다. **이게 의도다** (W2).

    표기 규약: `''` = 확인된 해당 없음 / 키 부재(NULL) = 모름.
    `is_null` 은 `a is None` 이므로 `''` 에는 걸리지 않는다.

    ⚠ 위험 지점: D77 로 `lien_consent_ref` 가 `required_facts` 에서 빠졌으므로,
      `has_lien=true` 인 자산에 동의서 필드를 **깜빡 잊어 `''` 로 채우면**
      BLOCKING 룰이 아무 소리 없이 미발화하고 INSUFFICIENT_FACTS 가드도 없다
      = "담보 있는 자산을 동의서 없이 처분 가능"이라는 최악의 오판.
      그래서 이 조합을 막는 책임은 룰이 아니라 **시드 불변식**(seed.py verify ⑱)에 있다.
      여기서는 엔진 동작을 고정해 두어, 나중에 누가 `is_null` 을 "빈 값도 포함"으로
      바꾸면(그래도 되는 것처럼 보인다) 이 테스트가 먼저 깨지게 한다.
    """
    empty = evaluate_rule(
        rules["LIEN-CONSENT"],
        {"has_lien": True, "lien_creditor": "XX은행", "lien_consent_ref": ""},
        laws,
    )
    assert empty.verdict == "CLEAR", "'' 는 값이다 — 발화하지 않는 게 규약이다"

    absent = evaluate_rule(
        rules["LIEN-CONSENT"], {"has_lien": True, "lien_creditor": "XX은행"}, laws
    )
    assert absent.verdict == "TRIGGERED", "키 부재(=동의서 없음)는 반드시 발화해야 한다"


# ------------------------------------------------ build_facts (D62)


def _asset_row(**over):
    row = {
        "asset_id": "AST-L3-CONV",
        "building_id": "BLD-C",
        "acquired_at": "2025-03-01",
        "status": "IN_USE",
        "tax_credit_applied": 1,
        "has_lien": 1,
        "lien_creditor": "한빛은행 여신부",
        "lien_consent_ref": None,
        "insured": 1,
        "policy_id": "SBP-2022-0003",  # BLD-C (InsuQ 발급)
        "safety_inspection_target": 0,
        "last_inspection_date": None,
        "inspection_valid_until": None,
    }
    row.update(over)
    return row


def test_build_facts_omits_null_columns():
    """NULL 컬럼은 키 자체가 없어야 한다 — 있으면 '모른다'가 'CLEAR'로 바뀐다 (D62)."""
    facts = build_facts(_asset_row(tax_credit_applied=None))
    assert "tax_credit_applied" not in facts
    assert "lien_consent_ref" not in facts
    assert "last_inspection_date" not in facts
    assert None not in facts.values(), f"None 값 키: {[k for k, v in facts.items() if v is None]}"


def test_build_facts_keeps_false_and_zero():
    """False·0 은 '모른다'가 아니라 값이다."""
    facts = build_facts(_asset_row(has_lien=0, safety_inspection_target=0))
    assert facts["has_lien"] is False
    assert facts["safety_inspection_target"] is False
    assert facts["vat_invoice_issued"] is False, (
        "precheck 는 거래 성립 전 — 미발행이 확정 사실 (D77)"
    )


def test_build_facts_months_needs_both_dates():
    """파생 필드는 원천이 둘 다 있을 때만 만든다."""
    assert "months_since_acquisition" not in build_facts(_asset_row())
    facts = build_facts(_asset_row(), disposal_date="2026-08-01")
    assert facts["months_since_acquisition"] == 17
    assert "months_since_acquisition" not in build_facts(
        _asset_row(acquired_at=None), disposal_date="2026-08-01"
    )


def test_build_facts_drops_unreadable_dates():
    """판독 불가한 날짜는 **원천 키째로** 뺀다 — 그러지 않으면 조용한 CLEAR 가 난다.

    `TAX-CREDIT-2Y.required_facts` 는 `acquired_at`·`disposal_date` 인데 트리거는 파생인
    `months_since_acquisition` 을 읽는다. 원천만 남기고 파생을 건너뛰면 필수 사실 검사는
    통과하고 `lt`(`a is not None and a < b`)가 False 를 내 **"사실은 충분한데 조건 미해당"**
    이 된다 — 세액공제 추징 대상 자산이 아무 표시 없이 통과하는 경로다.
    """
    facts = build_facts(_asset_row(acquired_at="2025/03/01"), disposal_date="2026-08-01")
    assert "acquired_at" not in facts
    assert "months_since_acquisition" not in facts

    laws_ = load_laws()
    f = evaluate_rule(load_rules(laws_)["TAX-CREDIT-2Y"], facts, laws_)
    assert f.verdict == "INSUFFICIENT_FACTS", "조용한 CLEAR 가 나오면 안 된다"
    assert "acquired_at" in f.missing_facts, "범인이 missing_facts 에 찍혀야 고칠 수 있다"

    # disposal_date 쪽이 깨진 경우도 같다
    bad_target = build_facts(_asset_row(), disposal_date="언젠가")
    assert "disposal_date" not in bad_target
    assert "months_since_acquisition" not in bad_target


def test_build_facts_derivation_is_structurally_guaranteed():
    """원천 2개가 facts 에 있으면 파생도 **반드시** 있다 (검사가 아니라 구조로 보장)."""
    for acquired, disposal in (
        ("2025-03-01", "2026-08-01"),
        ("2025/03/01", "2026-08-01"),
        ("2025-03-01", "언젠가"),
        (None, "2026-08-01"),
    ):
        facts = build_facts(_asset_row(acquired_at=acquired), disposal_date=disposal)
        if {"acquired_at", "disposal_date"} <= facts.keys():
            assert "months_since_acquisition" in facts


def test_build_facts_omits_risk_profile_fields():
    """F6 원천이 없는 사실은 지어내지 않는다 → INSURANCE-NOTIFY 는 경계 검사를 건너뛴다."""
    facts = build_facts(_asset_row())
    for f in (
        "risk_grade_before",
        "risk_grade_after",
        "risk_score_delta_pct",
        "risk_grade_changed",
    ):
        assert f not in facts


# ------------------------------------------------ 통합


def _full_facts(**over):
    facts = {
        "asset_id": "AST-L3-CONV",
        "tax_credit_applied": True,
        "acquired_at": "2025-03-01",
        "disposal_date": "2026-08-10",
        "months_since_acquisition": 17,
        "has_lien": True,
        "lien_creditor": "XX은행",
        "lien_consent_ref": None,
        "insured": True,
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


# ------------------------------------------------ verdict 어휘 5종 (D79)


def test_insufficient_facts_is_its_own_verdict():
    """`HOLD` 와 `INSUFFICIENT_FACTS` 를 합치지 않는다 (D79).

    해소 경로가 정반대다 — HOLD 는 *전문가 검토*, INSUFFICIENT_FACTS 는 *데이터 입력*.
    HTTP 는 둘 다 409 지만(D71) 사용자가 할 행동이 다르므로 본문에서 구분해야 한다.
    """
    # 담보 blocker 가 남아 있으면 BLOCKED 가 이긴다 (우선순위 확인)
    with_blocker = _full_facts()
    del with_blocker["tax_credit_applied"]
    assert check_disposal_blockers(with_blocker, at=date(2026, 8, 4))["verdict"] == "BLOCKED"

    # 사실 부족만 남기면 그 자체가 최상위 verdict 다 — HOLD 로 흡수되지 않는다
    only_missing = _full_facts(has_lien=False, months_since_acquisition=43)
    del only_missing["tax_credit_applied"]
    result = check_disposal_blockers(only_missing, at=date(2026, 8, 4))
    assert result["verdict"] == "INSUFFICIENT_FACTS"
    assert {f["rule_id"] for f in result["insufficient"]} == {"TAX-CREDIT-2Y"}
    assert not result["holds"], "경계에 걸린 룰이 없는데 HOLD 로 분류되면 안 된다"


def test_verdict_vocabulary_is_five(rules, laws):
    """엔진이 내는 최상위 verdict 는 이 5종뿐이다 (D79 · D71 매핑의 전제)."""
    assert VERDICTS == ("BLOCKED", "HOLD", "INSUFFICIENT_FACTS", "CONDITIONAL", "CLEAR")

    # 경계(HOLD)가 사실 부족(INSUFFICIENT)보다 우선한다 — 발화한 쪽이 더 구체적이다
    facts = _full_facts(has_lien=False, months_since_acquisition=23)
    del facts["safety_inspection_target"]
    result = check_disposal_blockers(facts, at=date(2026, 8, 4))
    assert result["verdict"] == "HOLD"
    assert result["holds"] and result["insufficient"], "둘 다 있는 상태에서 HOLD 가 이겨야 한다"


def test_sale_is_at_least_conditional_but_scrap_can_be_clear():
    """**도메인 사실**: 매각 precheck 은 정의상 최소 CONDITIONAL 이다 (D78 부수 확정).

    `VAT-INVOICE` 는 `disposal_mode='SALE' ∧ vat_invoice_issued=false` 로 발화하는데,
    precheck 은 거래 성립 전이라 `vat_invoice_issued` 는 **항상 false** 다(D77).
    → 사업용 고정자산 매각은 세금계산서 발급이 언제나 남아 있으므로 `CLEAR` 가 아니다.
    `CLEAR` 는 `SCRAP`·`TRANSFER` 에서만 나올 수 있는 값이며, 이건 결함이 아니라 옳은 판정이다.

    같은 자산(`AST-L3-LIFT` 상당: 법정 조건 전부 무해당·확인된 미부보)으로 양쪽을 고정한다.
    """
    lift = _asset_row(
        asset_id="AST-L3-LIFT",
        tax_credit_applied=0,
        has_lien=0,
        lien_creditor="",
        lien_consent_ref="",
        insured=0,
        policy_id=None,
        safety_inspection_target=0,
        acquired_at="2023-02-17",
    )
    sale = check_disposal_blockers(build_facts(lift, disposal_date="2028-02-17"))
    scrap = check_disposal_blockers(
        build_facts(lift, disposal_mode="SCRAP", disposal_date="2028-02-17")
    )
    assert sale["verdict"] == "CONDITIONAL"
    assert {p["rule_id"] for p in sale["preconditions"]} == {"VAT-INVOICE"}
    assert scrap["verdict"] == "CLEAR"
    assert not scrap["preconditions"] and not scrap["insufficient"]


# ------------------------------------------------ 주입점 (D82)
#
# 왜 여는가: `build_evidence_bundle` 이 **인용 집합은 파일 로더 판정에서, `text_hash` 는 DB
# 사본에서** 가져온다 — "판정이 본 조문"과 "해시로 고정된 조문"이 다른 사본이다(W5).
# 서명 산출물이라 파급이 가장 크다. 주입점은 소비자가 **하나의 카탈로그 객체**로 둘을
# 만들 수 있게 하고, `facts_used` 반환은 소비자가 사실을 재조립하지 않게 한다.


_ONLY_LIEN = dict(months_since_acquisition=43)  # TAX-CREDIT-2Y 는 CLEAR → blocker 는 담보 1건뿐


def test_injection_point_is_backward_compatible():
    """주입하지 않으면 **현행 그대로**, 주입하면 그 카탈로그가 판정을 지배한다 (D82).

    기존 호출자 3곳(MCP 도구·REST 서비스·`test_rules`)이 한 줄도 바뀌지 않는 것이 전제다.
    """
    facts = _full_facts(**_ONLY_LIEN)
    laws, rules = load_laws(), load_rules(load_laws())

    default = check_disposal_blockers(facts, at=date(2026, 8, 4))
    injected = check_disposal_blockers(facts, at=date(2026, 8, 4), laws=laws, rules=rules)
    assert default == injected, "같은 카탈로그를 주입하면 결과가 한 글자도 달라지면 안 된다"
    assert default["verdict"] == "BLOCKED"

    # ★ 주입된 카탈로그가 **실제로** 쓰인다 — 룰 1행의 `disposal_type` 만 내리면
    #   BLOCKED → CONDITIONAL 로 갈린다. (자산에 blocker 가 2건이면 이 변경이 verdict 로
    #   드러나지 않는다는 것이 Sprint 6 실측이라, 여기서는 blocker 1건 상태로 고정한다.)
    downgraded = dict(rules)
    downgraded["LIEN-CONSENT"] = dataclasses.replace(
        rules["LIEN-CONSENT"], disposal_type="PRECONDITION"
    )
    out = check_disposal_blockers(facts, at=date(2026, 8, 4), laws=laws, rules=downgraded)
    assert out["verdict"] == "CONDITIONAL"
    assert {p["rule_id"] for p in out["preconditions"]} >= {"LIEN-CONSENT"}

    # 주입 경로라고 D61 게이트를 낮추지 않는다 — 미등록 참조는 판정 시점이 아니라 진입에서 막는다
    dangling = dict(rules)
    dangling["LIEN-CONSENT"] = dataclasses.replace(
        rules["LIEN-CONSENT"], law_refs=["KR-NOT-REGISTERED-999"]
    )
    with pytest.raises(RuleIntegrityError):
        check_disposal_blockers(facts, at=date(2026, 8, 4), laws=laws, rules=dangling)


def test_injection_does_not_touch_the_file_loaders():
    """주입되면 `load_laws()`/`load_rules()` 를 **호출하지 않는다**.

    이게 D82 의 핵심이다 — 소비자가 카탈로그를 넘겼는데 엔진이 파일을 다시 읽으면
    "판정이 본 조문"이 또 갈라지고, 주입점은 장식이 된다.
    """
    import engine

    laws, rules = load_laws(), load_rules(load_laws())
    calls: list[str] = []

    def boom_laws():
        calls.append("load_laws")
        raise AssertionError("주입됐는데 파일 로더가 호출됐다")

    def boom_rules(_laws):
        calls.append("load_rules")
        raise AssertionError("주입됐는데 파일 로더가 호출됐다")

    original = (engine.load_laws, engine.load_rules)
    engine.load_laws, engine.load_rules = boom_laws, boom_rules
    try:
        out = check_disposal_blockers(_full_facts(), at=date(2026, 8, 4), laws=laws, rules=rules)
        assert out["verdict"] == "BLOCKED"
        assert calls == [], f"파일 로더가 호출됐다: {calls}"

        # 패치가 실제로 걸려 있는지 대조 — 주입 없이 부르면 터져야 한다.
        # (이게 없으면 위 단언은 '아무 일도 안 일어났다'로도 통과한다)
        with pytest.raises(AssertionError):
            check_disposal_blockers(_full_facts(), at=date(2026, 8, 4))
    finally:
        engine.load_laws, engine.load_rules = original


def test_facts_used_is_a_shallow_copy_of_the_input():
    """`facts_used` = 입력 facts 의 **얕은 사본**. 재조립·필터하지 않는다 (D82)."""
    facts = _full_facts()
    result = check_disposal_blockers(facts, at=date(2026, 8, 4))

    assert result["facts_used"] == facts, "걸러 내면 '판정이 본 사실'과 '실린 사실'이 갈린다"
    assert result["facts_used"] is not facts, "같은 객체면 호출자가 엔진 입력을 흔들 수 있다"

    result["facts_used"]["has_lien"] = "오염"
    result["facts_used"]["새_키"] = 1
    assert facts["has_lien"] is True and "새_키" not in facts, "사본이 원본을 오염시켰다"

    # 재호출해도 같은 판정이 나온다 — 위 변형이 엔진 내부에 남지 않았다는 뜻
    assert check_disposal_blockers(facts, at=date(2026, 8, 4))["verdict"] == "BLOCKED"

    # 빈 facts 도 그대로 싣는다 (전 룰 INSUFFICIENT_FACTS)
    empty = check_disposal_blockers({}, at=date(2026, 8, 4))
    assert empty["facts_used"] == {} and empty["verdict"] == "INSUFFICIENT_FACTS"


def test_laws_used_covers_every_evaluated_rule():
    """`laws_used` 는 **평가된 전 룰**의 참조 합집합 — 발화한 룰만 세지 않는다 (W7).

    발화분만 실으면 전 룰이 CLEAR 인 자산에서 빈 목록이 되어, "근거를 조회한 결과 해당
    없음"과 "근거를 아예 안 봤다"가 구분되지 않는다.
    """
    laws = load_laws()
    every_ref = sorted({ref for r in load_rules(laws).values() for ref in r.law_refs})

    blocked = check_disposal_blockers(_full_facts(), at=date(2026, 8, 4))
    assert blocked["laws_used"] == every_ref
    assert blocked["laws_used"] == sorted(set(blocked["laws_used"])), "정렬·중복 제거된 목록이다"

    # ★ 아무 룰도 발화하지 않는 자산에서도 비지 않는다
    lift = _asset_row(
        asset_id="AST-L3-LIFT",
        tax_credit_applied=0,
        has_lien=0,
        lien_creditor="",
        lien_consent_ref="",
        insured=0,
        policy_id=None,
        safety_inspection_target=0,
        acquired_at="2023-02-17",
    )
    clear = check_disposal_blockers(
        build_facts(lift, disposal_mode="SCRAP", disposal_date="2028-02-17")
    )
    assert clear["verdict"] == "CLEAR"
    assert clear["laws_used"] == every_ref, "CLEAR 자산의 laws_used 가 비면 W7 이 그대로 남는다"


def test_engine_is_the_single_source_of_not_considered_and_disclaimer():
    """문구의 단일 출처는 엔진이다 (W2·D73).

    소비자가 문자열을 복제하면 엔진이 문장을 고칠 때 그쪽만 조용히 옛 문구를 낸다.
    출력은 상수에서 **직접** 와야 하고, 동시에 상수를 오염시킬 수 없어야 한다.
    """
    import engine

    result = check_disposal_blockers(_full_facts(), at=date(2026, 8, 4))
    assert result["disclaimer"] is engine.DISCLAIMER, "상수 자체가 실려야 복제가 불가능해진다"
    assert tuple(result["not_considered"]) == engine.NOT_CONSIDERED
    assert isinstance(engine.NOT_CONSIDERED, tuple), "상수는 불변형이어야 한다"

    # 응답을 받은 쪽이 append 해도 엔진 상수가 프로세스 전역에서 오염되면 안 된다
    result["not_considered"].append("오염")
    assert len(engine.NOT_CONSIDERED) == 3
    assert check_disposal_blockers(_full_facts(), at=date(2026, 8, 4))["not_considered"] == list(
        engine.NOT_CONSIDERED
    )
