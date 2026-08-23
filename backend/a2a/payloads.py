# -*- coding: utf-8 -*-
"""MaintQ A2A Payload 조립 및 subject 조회 유틸리티.

- partner_links 테이블에서 external_ref 조회
- S5 request-withdrawal payload 조립
- InsuQ lookup-clause payload 조립
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.db import connect


def get_finallq_company_id(db_path: Path | str | None = None) -> str | None:
    """partner_links에서 finallq 파트너의 company 결 external_ref를 조회한다.

    회사 결은 subject_ref=''(D96)로 고정돼 있다.
    link_state != 'LINKED'면 None을 반환한다.
    """
    with connect(Path(db_path) if db_path else None) as con:
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
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """S5 request-withdrawal 스킬 payload를 조립한다."""
    account_number = ""
    bank_code = None
    if supplier_row:
        account_number = supplier_row.get("account_number", "")
        bank_code = supplier_row.get("bank_code")
    elif po.get("supplier_id"):
        with connect(Path(db_path) if db_path else None) as con:
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
        "approved_by": po.get("decided_by", ""),
        "purpose": po.get("reason", ""),
        "error_code": po.get("error_code", ""),
        "to_account_number": account_number,
        "to_bank_code": bank_code,
    }



def build_lookup_clause_payload(
    question: str,
    request_chain_id: str,
    db_path: Path | str | None = None,
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
    db_path: Path | str | None = None,
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
