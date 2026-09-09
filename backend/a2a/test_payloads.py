# -*- coding: utf-8 -*-
"""backend/a2a/payloads.py 테스트.

- get_finallq_company_id: partner_links 회사 결(subject_ref='') 조회 + LINKED 게이트
- build_request_withdrawal_payload: supplier_row 직접 전달 vs supplier_id로 DB 조회,
  금액(unit_price*qty) 조립, CP-002 필드(to_account_number/to_bank_code)
- build_lookup_clause_payload: 최소 조립
"""

from __future__ import annotations


import pytest


from backend.a2a.payloads import (
    build_assess_loan_payload,
    build_assess_used_equipment_loan_payload,
    build_lookup_clause_payload,
    build_notify_asset_change_payload,
    build_request_settlement_payload,
    build_request_withdrawal_payload,
    get_finallq_company_id,
)


# ---- get_finallq_company_id -------------------------------------------------


def test_get_finallq_company_id_returns_none_when_no_row(db_path: str):
    assert get_finallq_company_id(db_path) is None


def test_get_finallq_company_id_returns_none_when_not_linked(db_path: str, link_finallq):
    link_finallq(link_state="NOT_LINKED")
    assert get_finallq_company_id(db_path) is None


def test_get_finallq_company_id_returns_external_ref_when_linked(db_path: str, link_finallq):
    link_finallq(external_ref="CMP-MAINTQ-001", link_state="LINKED")
    assert get_finallq_company_id(db_path) == "CMP-MAINTQ-001"


# ---- build_request_withdrawal_payload ---------------------------------------


def _po(**overrides) -> dict:
    base = {
        "po_id": "PO-001",
        "unit_price": 10000,
        "qty": 3,
        "supplier_name": "테스트 거래처",
        "decided_by": "mgr-01",
        "reason": "부품 교체",
        "error_code": "E01",
    }
    base.update(overrides)
    return base


def test_build_payload_computes_amount_from_unit_price_and_qty(db_path: str, link_finallq):
    link_finallq()
    payload = build_request_withdrawal_payload(_po(unit_price=15000, qty=4), db_path=db_path)
    assert payload["amount"] == 60000


def test_build_payload_uses_supplier_row_directly_without_db_lookup(db_path: str, link_finallq):
    """supplier_row가 주어지면 suppliers 테이블을 조회하지 않는다 — po에 supplier_id가
    없어도(=DB에 없는 값이어도) 동작해야 한다."""
    link_finallq()
    po = _po(supplier_id="DOES-NOT-EXIST")
    payload = build_request_withdrawal_payload(
        po,
        supplier_row={"account_number": "999-000-111", "bank_code": "088"},
        db_path=db_path,
    )
    assert payload["to_account_number"] == "999-000-111"
    assert payload["to_bank_code"] == "088"


def test_build_payload_looks_up_supplier_by_id_when_row_not_given(db_path: str, link_finallq, seed_po):
    link_finallq()
    seed_po(supplier_id="SUP-001", account_number="110-222-333", bank_code="004")
    po = _po(supplier_id="SUP-001")
    payload = build_request_withdrawal_payload(po, db_path=db_path)
    assert payload["to_account_number"] == "110-222-333"
    assert payload["to_bank_code"] == "004"


def test_build_payload_blank_account_when_supplier_id_missing(db_path: str, link_finallq):
    link_finallq()
    po = _po()
    po.pop("supplier_id", None)
    payload = build_request_withdrawal_payload(po, db_path=db_path)
    assert payload["to_account_number"] == ""
    assert payload["to_bank_code"] is None


def test_build_payload_blank_account_when_supplier_row_missing_in_db(db_path: str, link_finallq):
    """suppliers.account_number 마이그레이션 갭(세션 로그 2026-08-21) 회귀 —
    supplier_id는 있지만 DB에 매칭 행이 없으면 예외 없이 빈 값으로 채운다."""
    link_finallq()
    po = _po(supplier_id="NOT-IN-DB")
    payload = build_request_withdrawal_payload(po, db_path=db_path)
    assert payload["to_account_number"] == ""
    assert payload["to_bank_code"] is None


def test_build_payload_uses_finallq_company_id_from_partner_links(db_path: str, link_finallq):
    link_finallq(external_ref="CMP-XYZ")
    payload = build_request_withdrawal_payload(_po(), db_path=db_path)
    assert payload["requester"]["finallq_company_id"] == "CMP-XYZ"


def test_build_payload_blank_company_id_when_not_linked(db_path: str):
    payload = build_request_withdrawal_payload(_po(), db_path=db_path)
    assert payload["requester"]["finallq_company_id"] == ""


def test_build_payload_maps_po_fields(db_path: str, link_finallq):
    link_finallq()
    payload = build_request_withdrawal_payload(
        _po(po_id="PO-777", decided_by="mgr-02", reason="긴급 교체", error_code="E42"),
        request_chain_id="CHAIN-1",
        db_path=db_path,
    )
    assert payload["po_id"] == "PO-777"
    assert payload["approved_by"] == "mgr-02"
    assert payload["purpose"] == "긴급 교체"
    assert payload["error_code"] == "E42"
    assert payload["request_chain_id"] == "CHAIN-1"


def test_build_payload_supplier_falls_back_to_supplier_key(db_path: str, link_finallq):
    """po dict가 supplier_name 대신 supplier 키를 쓰는 경우도 지원한다."""
    link_finallq()
    po = _po()
    po.pop("supplier_name")
    po["supplier"] = "다른 거래처"
    payload = build_request_withdrawal_payload(po, db_path=db_path)
    assert payload["supplier"] == "다른 거래처"


# ---- build_lookup_clause_payload --------------------------------------------


def test_build_lookup_clause_payload_minimal(db_path: str, link_finallq):
    link_finallq(external_ref="CMP-MAINTQ-001")
    payload = build_lookup_clause_payload(
        question="화재 특약 보장 범위는?", request_chain_id="CHAIN-CLAUSE-1", db_path=db_path
    )
    assert payload == {
        "requester": {"finallq_company_id": "CMP-MAINTQ-001"},
        "request_chain_id": "CHAIN-CLAUSE-1",
        "question": "화재 특약 보장 범위는?",
    }


# ---- build_assess_loan_payload -----------------------------------------------


def test_build_assess_loan_payload_minimal(db_path: str, link_finallq):
    link_finallq(external_ref="CMP-MAINTQ-001")
    payload = build_assess_loan_payload(
        loan_amount=50000000,
        purpose="설비 증설 자금",
        collateral_building_id="BLD-001",
        request_chain_id="CHAIN-LOAN-1",
        db_path=db_path,
    )
    assert payload == {
        "requester": {"finallq_company_id": "CMP-MAINTQ-001"},
        "request_chain_id": "CHAIN-LOAN-1",
        "loan_amount": 50000000,
        "purpose": "설비 증설 자금",
        "collateral_building_id": "BLD-001",
    }


# ---- build_assess_used_equipment_loan_payload (S13) --------------------------
#
# ⚠ 계획서는 `tmp_db` 픽스처를 쓰지만 이 레포에는 없다 — 관례는 `db_path`(격리 스키마,
#   빈 DB)이고 자산은 테스트가 직접 심는다(`seed_po` 선례). 그래서 아래 헬퍼를 둔다.


def test_assess_used_equipment_loan_payload_derives_fields_from_asset(db_path, seed_assets):
    """자산 하나에서 계약 4필드가 파생된다 — 호출자는 asset_id 와 금액만 준다."""
    p = build_assess_used_equipment_loan_payload(
        asset_id="AST-L3-CONV", loan_amount=5_000_000.0,
        request_chain_id="CHAIN-TEST-1", db_path=db_path,
    )

    assert p["loan_amount"] == 5_000_000.0
    assert p["request_chain_id"] == "CHAIN-TEST-1"
    assert p["collateral_building_id"] == "BLD-A"
    assert p["equipment_year"] == 2019
    assert isinstance(p["inspection_data"], dict)


def test_inspection_data_carries_ownership_checks(db_path, seed_assets):
    """계약이 'S18 verify_ownership 결과 참조 가능'이라 적었고 그게 ownership_checks 다."""
    p = build_assess_used_equipment_loan_payload(
        asset_id="AST-L3-CONV", loan_amount=1.0, request_chain_id="C", db_path=db_path,
    )
    checks = p["inspection_data"]["ownership_checks"]

    assert isinstance(checks, list) and checks
    assert set(checks[0]) == {"category", "check_item", "state"}
    assert checks[0]["state"] in ("VERIFIED", "UNVERIFIED")


def test_equipment_year_is_labelled_as_acquisition_year(db_path, seed_assets):
    """MaintQ 는 제조연도를 저장하지 않는다 — 취득연도를 보내되 그 사실을 함께 보낸다."""
    p = build_assess_used_equipment_loan_payload(
        asset_id="AST-L3-CONV", loan_amount=1.0, request_chain_id="C", db_path=db_path,
    )

    assert p["inspection_data"]["equipment_year_basis"] == "acquired_at"


def test_missing_inspection_dates_are_omitted_not_blanked(db_path, seed_assets):
    """NULL 은 키 자체를 생략한다 — 빈 문자열·0 으로 채우지 않는다 (D62)."""
    p = build_assess_used_equipment_loan_payload(
        asset_id="AST-NO-INSPECTION", loan_amount=1.0, request_chain_id="C", db_path=db_path,
    )

    assert "last_inspection_date" not in p["inspection_data"]
    assert "inspection_valid_until" not in p["inspection_data"]
    # 양성 축 — 생략이 "스캐너가 눈이 멀었다"가 아니라 "값이 없다"임을 보인다
    assert p["inspection_data"]["equipment_year_basis"] == "acquired_at"


def test_unknown_asset_raises(db_path, seed_assets):
    """없는 자산으로 payload 를 만들지 않는다 — 조용히 빈 값을 보내면 수신부가 400 을 낸다."""
    with pytest.raises(ValueError, match="AST-NOPE"):
        build_assess_used_equipment_loan_payload(
            asset_id="AST-NOPE", loan_amount=1.0, request_chain_id="C", db_path=db_path,
        )


# ---- build_request_settlement_payload (S12) ----------------------------------


def test_request_settlement_payload_reads_lien_creditor_via_decision(
    db_path, seed_lien_decisions
):
    """decision_id → decisions.asset_id → assets.lien_creditor 로 타고 간다."""
    p = build_request_settlement_payload(
        decision_id="DEC-0001", sale_amount=8_000_000.0, outstanding_loan=3_000_000.0,
        approved_by="U-FIN-01", prepayment_fee=None,
        request_chain_id="CHAIN-SET-1", db_path=db_path,
    )

    assert p["decision_id"] == "DEC-0001"
    assert p["lien_creditor"] == "한빛은행 여신부"
    assert p["sale_amount"] == 8_000_000.0
    assert p["outstanding_loan"] == 3_000_000.0
    assert p["approved_by"] == "U-FIN-01"


def test_prepayment_fee_omitted_when_none(db_path, seed_lien_decisions):
    """계약상 optional 이다 — None 이면 키를 생략한다 (0 으로 채우지 않는다)."""
    p = build_request_settlement_payload(
        decision_id="DEC-0001", sale_amount=1.0, outstanding_loan=1.0,
        approved_by="U", prepayment_fee=None, request_chain_id="C", db_path=db_path,
    )

    assert "prepayment_fee" not in p


def test_prepayment_fee_included_when_zero(db_path, seed_lien_decisions):
    """0 은 '없음'이 아니라 '수수료 0원'이라는 사실이다 — 생략하지 않는다."""
    p = build_request_settlement_payload(
        decision_id="DEC-0001", sale_amount=1.0, outstanding_loan=1.0,
        approved_by="U", prepayment_fee=0.0, request_chain_id="C", db_path=db_path,
    )

    assert p["prepayment_fee"] == 0.0


def test_draft_decision_is_accepted(db_path, seed_lien_decisions):
    """decision_id 는 **미서명 draft** 를 가리킨다 — 그것이 정상 경로다.

    담보 자산은 LIEN-CONSENT(BLOCKING)로 서명이 막혀 있고, 그 담보를 푸는 수단이
    이 스킬 자신이다. 서명 후 호출은 구조적으로 불가능하다.
    """
    p = build_request_settlement_payload(
        decision_id="DEC-0001", sale_amount=1.0, outstanding_loan=1.0,
        approved_by="U", prepayment_fee=None, request_chain_id="C", db_path=db_path,
    )

    assert p["decision_id"] == "DEC-0001"


def test_unknown_decision_raises(db_path, seed_lien_decisions):
    with pytest.raises(ValueError, match="DEC-NOPE"):
        build_request_settlement_payload(
            decision_id="DEC-NOPE", sale_amount=1.0, outstanding_loan=1.0,
            approved_by="U", prepayment_fee=None, request_chain_id="C", db_path=db_path,
        )


def test_asset_without_lien_raises(db_path, seed_lien_decisions):
    """담보가 없는 자산에 정산을 요청하지 않는다 — lien_creditor 가 빈 채로 나가면
    수신부가 400 을 낸다(계약 필수 필드)."""
    with pytest.raises(ValueError, match="담보"):
        build_request_settlement_payload(
            decision_id="DEC-NOLIEN", sale_amount=1.0, outstanding_loan=1.0,
            approved_by="U", prepayment_fee=None, request_chain_id="C", db_path=db_path,
        )


# ---- build_notify_asset_change_payload (S11) --------------------------------


def test_notify_asset_change_builds_contract_fields(db_path: str, seed_signed_disposals, link_finallq):
    link_finallq(external_ref="CMP-MAINTQ-001")
    p = build_notify_asset_change_payload(
        decision_id="DEC-SIGNED", request_chain_id="CHAIN-1", db_path=db_path
    )
    # 계약(notify-asset-change.json) required 8종이 전부 있어야 한다
    for key in (
        "requester", "request_chain_id", "building_id", "policy_id",
        "change_type", "equipment", "effective_date", "decision_id",
    ):
        assert key in p, key
    assert p["building_id"] == "BLD-C"
    assert p["policy_id"] == "POL-2026-FIRE-01"
    assert p["change_type"] == "REMOVE"
    assert p["decision_id"] == "DEC-SIGNED"
    assert p["requester"]["finallq_company_id"] == "CMP-MAINTQ-001"


def test_notify_asset_change_equipment_is_an_array_of_names(db_path: str, seed_signed_disposals):
    p = build_notify_asset_change_payload(
        decision_id="DEC-SIGNED", request_chain_id="CHAIN-1", db_path=db_path
    )
    assert p["equipment"] == ["3라인 금속 컨베이어"]


def test_notify_asset_change_effective_date_is_the_signing_date(db_path: str, seed_signed_disposals):
    """오늘이 아니라 **서명일**이다 — 통지가 늦어도 처분이 확정된 날은 바뀌지 않는다."""
    p = build_notify_asset_change_payload(
        decision_id="DEC-SIGNED", request_chain_id="CHAIN-1", db_path=db_path
    )
    assert p["effective_date"] == "2026-08-15"


def test_notify_asset_change_refuses_unsigned_decision(db_path: str, seed_signed_disposals):
    """S12 와 정반대다 — 확정(서명) 전에는 보내지 않는다."""
    with pytest.raises(ValueError, match="서명 전"):
        build_notify_asset_change_payload(
            decision_id="DEC-DRAFT", request_chain_id="CHAIN-1", db_path=db_path
        )


def test_notify_asset_change_refuses_uninsured_asset(db_path: str, seed_signed_disposals):
    """부보되지 않은 자산은 InsuQ 에 고칠 증권이 없다 — 빈 policy_id 로 보내지 않는다."""
    with pytest.raises(ValueError, match="부보 자산이 아니다"):
        build_notify_asset_change_payload(
            decision_id="DEC-UNINSURED", request_chain_id="CHAIN-1", db_path=db_path
        )


def test_notify_asset_change_refuses_missing_building(db_path: str, seed_signed_disposals):
    with pytest.raises(ValueError, match="building_id"):
        build_notify_asset_change_payload(
            decision_id="DEC-NOBLDG", request_chain_id="CHAIN-1", db_path=db_path
        )


def test_notify_asset_change_refuses_unknown_decision(db_path: str, seed_signed_disposals):
    with pytest.raises(ValueError, match="알 수 없는 decision_id"):
        build_notify_asset_change_payload(
            decision_id="DEC-NOPE", request_chain_id="CHAIN-1", db_path=db_path
        )


def test_notify_asset_change_rejects_bad_change_type(db_path: str, seed_signed_disposals):
    """계약 enum 은 REMOVE|ADD 뿐이다 — 조립 단계에서 막는다."""
    with pytest.raises(ValueError, match="change_type"):
        build_notify_asset_change_payload(
            decision_id="DEC-SIGNED", request_chain_id="CHAIN-1",
            change_type="DELETE", db_path=db_path,
        )


def test_notify_asset_change_accepts_add(db_path: str, seed_signed_disposals):
    p = build_notify_asset_change_payload(
        decision_id="DEC-SIGNED", request_chain_id="CHAIN-1",
        change_type="ADD", db_path=db_path,
    )
    assert p["change_type"] == "ADD"
