# -*- coding: utf-8 -*-
"""backend/a2a/payloads.py 테스트.

- get_finallq_company_id: partner_links 회사 결(subject_ref='') 조회 + LINKED 게이트
- build_request_withdrawal_payload: supplier_row 직접 전달 vs supplier_id로 DB 조회,
  금액(unit_price*qty) 조립, CP-002 필드(to_account_number/to_bank_code)
- build_lookup_clause_payload: 최소 조립
"""

from __future__ import annotations


from backend.a2a.payloads import (
    build_assess_loan_payload,
    build_lookup_clause_payload,
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
