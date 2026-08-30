# -*- coding: utf-8 -*-
"""MaintQ A2A Payload 조립 및 subject 조회 유틸리티.

- partner_links 테이블에서 external_ref 조회
- S5 request-withdrawal payload 조립
- InsuQ lookup-clause payload 조립
"""

from __future__ import annotations

from typing import Any

from backend.db import connect


def get_finallq_company_id(db_path: str | None = None) -> str | None:
    """partner_links에서 finallq 파트너의 company 결 external_ref를 조회한다.

    회사 결은 subject_ref=''(D96)로 고정돼 있다.
    link_state != 'LINKED'면 None을 반환한다.
    """
    with connect(db_path) as con:
        r = con.execute(
            "SELECT external_ref, link_state FROM partner_links"
            " WHERE partner = 'finallq' AND subject_type = 'company' AND subject_ref = ''"
        ).fetchone()
    if r is None or r["link_state"] != "LINKED":
        return None
    return r["external_ref"]


def build_request_withdrawal_payload(
    po: dict[str, Any],
    supplier_row: dict[str, Any] | None = None,
    request_chain_id: str = "",
    db_path: str | None = None,
) -> dict[str, Any]:
    """S5 request-withdrawal 스킬 payload를 조립한다."""
    account_number = ""
    bank_code = None
    if supplier_row:
        account_number = supplier_row.get("account_number", "")
        bank_code = supplier_row.get("bank_code")
    elif po.get("supplier_id"):
        with connect(db_path) as con:
            s_row = con.execute(
                "SELECT account_number, bank_code FROM suppliers WHERE supplier_id = ?",
                (po["supplier_id"],),
            ).fetchone()
            if s_row:
                account_number = s_row["account_number"] or ""
                bank_code = s_row["bank_code"]


    return {
        "requester": {
            "finallq_company_id": get_finallq_company_id(db_path) or "",
        },
        "request_chain_id": request_chain_id,
        "po_id": po["po_id"],
        "amount": po["unit_price"] * po["qty"],
        "supplier": po.get("supplier_name", po.get("supplier", "")),
        "approved_by": po.get("decided_by") or "",
        "purpose": po.get("reason", ""),
        # A2A_Q 계약(request-withdrawal.json)·FinAllQ 실 구현 둘 다 error_code 를 필수
        # 문자열로 요구한다(널 불가) — po_drafts.error_code 는 화면에서 직접 만든 발주서라면
        # NULL 일 수 있다(D111, 진단 없이 만든 PO). `.get(key, default)` 는 키가 아예 없을
        # 때만 default 를 쓰고 값이 None 이면 그대로 돌려주므로(흔한 함정), 여기서만은
        # `or` 로 None 도 함께 걸러야 한다 — 실제로 FinAllQ 어댑터가 이 값 때문에
        # 400(schema_validation_failed)을 낸 것을 실측으로 확인했다.
        "error_code": po.get("error_code") or "",
        "to_account_number": account_number,
        "to_bank_code": bank_code,
    }



def build_lookup_clause_payload(
    question: str,
    request_chain_id: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    """InsuQ lookup-clause 스킬 payload를 조립한다."""
    return {
        "requester": {
            "finallq_company_id": get_finallq_company_id(db_path) or "",
        },
        "request_chain_id": request_chain_id,
        "question": question,
    }


def build_assess_loan_payload(
    loan_amount: float,
    purpose: str,
    collateral_building_id: str,
    request_chain_id: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    """FinAllQ assess-loan 스킬(S8, 설비 담보 대출 사전 판정) payload를 조립한다."""
    return {
        "requester": {
            "finallq_company_id": get_finallq_company_id(db_path) or "",
        },
        "request_chain_id": request_chain_id,
        "loan_amount": loan_amount,
        "purpose": purpose,
        "collateral_building_id": collateral_building_id,
    }


def build_assess_used_equipment_loan_payload(
    asset_id: str,
    loan_amount: float,
    request_chain_id: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    """FinAllQ assess-used-equipment-loan 스킬(S13, 중고 설비 담보 대출 심사) payload.

    S8(`build_assess_loan_payload`)과 달리 **자산 하나에서 4필드를 파생한다** —
    호출자는 `asset_id` 와 `loan_amount` 만 준다. `build_request_withdrawal_payload`
    가 `supplier_id` 로 `suppliers` 를 조회하는 것과 같은 관례다.

    ⚠️ `equipment_year`: 계약은 **제조연도**를 요구하지만 MaintQ 는 그것을 저장하지
    않는다. 가장 가까운 값인 `acquired_at`(취득일)의 연도를 보내되, 무엇을 보냈는지
    `inspection_data.equipment_year_basis` 로 함께 알린다 — 지어내지 않고, 수신부가
    잔존연수를 재산정할 수 있게 한다 (D62·D74 태도).
    """
    with connect(db_path) as con:
        a = con.execute(
            "SELECT building_id, acquired_at, last_inspection_date,"
            " inspection_valid_until, safety_inspection_target"
            " FROM assets WHERE asset_id = ?",
            (asset_id,),
        ).fetchone()
        if a is None:
            raise ValueError(f"알 수 없는 asset_id: {asset_id}")
        checks = con.execute(
            "SELECT category, check_item, state FROM ownership_checks"
            " WHERE asset_id = ? ORDER BY check_id",
            (asset_id,),
        ).fetchall()

    # 계약이 "S18 verify_ownership 결과 참조 가능"이라 적은 자리 — ownership_checks 가 그것이다.
    inspection: dict[str, Any] = {
        "equipment_year_basis": "acquired_at",
        "ownership_checks": [
            {"category": c["category"], "check_item": c["check_item"], "state": c["state"]}
            for c in checks
        ],
    }
    # NULL 은 키 자체를 생략한다 (D62) — 빈 문자열·0 으로 채우면 "모름"이 "없음"으로 둔갑한다.
    for key in ("last_inspection_date", "inspection_valid_until"):
        if a[key] is not None:
            inspection[key] = str(a[key])
    if a["safety_inspection_target"] is not None:
        inspection["safety_inspection_target"] = bool(a["safety_inspection_target"])

    acquired = a["acquired_at"]
    return {
        "requester": {"finallq_company_id": get_finallq_company_id(db_path) or ""},
        "request_chain_id": request_chain_id,
        "loan_amount": loan_amount,
        "collateral_building_id": a["building_id"] or "",
        "equipment_year": int(str(acquired)[:4]) if acquired else 0,
        "inspection_data": inspection,
    }
