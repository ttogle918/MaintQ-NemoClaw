# -*- coding: utf-8 -*-
"""MaintQ A2A Payload 조립 및 subject 조회 유틸리티.

- partner_links 테이블에서 external_ref 조회
- S5 request-withdrawal payload 조립
- InsuQ lookup-clause payload 조립
- S11 notify-asset-change payload 조립 (InsuQ 부보 목적물 변경 통지)
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


def building_link_state(
    building_id: str, partner: str = "insuq", db_path: str | None = None
) -> str | None:
    """`partner_links` 에서 건물 결의 연결 승인 상태를 읽는다 (D142).

    ⛔ **이 값은 MaintQ 쪽 대장**이다 — 상대 시스템의 상태가 아니다. 상대가 그 건물을
    알고 있어도 우리 대장에 승인이 없으면 `LINKED` 가 아니다. 그 둘이 다른 것은 결함이
    아니라 정상이며, 실제로 다르다(InsuQ 2026-09-16 회신: 4동 전부 `active`).

    행이 없으면 `None` 을 돌려준다 — **`'NOT_LINKED'` 로 뭉개지 않는다.** «승인이 반려됐다»
    와 «대장에 아예 없다» 는 다른 사실이고, 호출부가 메시지에 그대로 실어 사람이 구분할 수
    있어야 한다(D62 — 모르는 것을 아는 것으로 반올림하지 않는다).
    """
    with connect(db_path) as con:
        r = con.execute(
            "SELECT link_state FROM partner_links"
            " WHERE partner = ? AND subject_type = 'building' AND subject_ref = ?",
            (partner, building_id),
        ).fetchone()
    return None if r is None else r["link_state"]


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

    🔵 `inspection_data.original_cost`: **원가를 함께 보낸다 (D138).** 계약에는 원가
    필드가 없고, FinAllQ 는 그것이 없으면 `original_cost` 를 **`loan_amount` 로 대체**한다
    (그쪽 `a2a_adapter/mapping.py` 가 "보수적 근사치"로 둔 폴백). 그러면 감정가 =
    신청액 × 잔존율 이라 **언제나 신청액보다 작아** 승인이 구조적으로 불가능하다
    (2026-09-10 실 E2E 로 확인 — 같은 자산에 3,000,000 신청 시 감정가 1,500,000,
    1,000,000 신청 시 500,000). 우리는 그 값을 실제로 보유하므로(`assets.acquisition_cost`)
    지어내는 것이 아니고, 무엇을 보냈는지 `original_cost_basis` 로 함께 알린다.

    ⛔ **`book_value`(장부가액)는 보내지 않는다.** FinAllQ 는 `inspection_data.
    appraised_value` 가 있으면 감가상각 계산 자체를 건너뛰고 그 값을 감정가로 쓴다 —
    장부가액은 회계 수치이지 감정가가 아니다. 보내면 우리가 모르는 것을 아는 것처럼
    말하게 된다 (D62).
    """
    with connect(db_path) as con:
        a = con.execute(
            "SELECT building_id, acquired_at, last_inspection_date,"
            " inspection_valid_until, safety_inspection_target, acquisition_cost"
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
    # NULL 이면 키 자체를 생략한다 — 0 으로 채우면 "모름"이 "무가치"로 둔갑하고,
    # 수신부는 그 0 을 원가로 믿어 감정가 0 을 낸다 (D62·D138)
    if a["acquisition_cost"] is not None:
        inspection["original_cost"] = a["acquisition_cost"]
        inspection["original_cost_basis"] = "acquisition_cost"

    acquired = a["acquired_at"]
    return {
        "requester": {"finallq_company_id": get_finallq_company_id(db_path) or ""},
        "request_chain_id": request_chain_id,
        "loan_amount": loan_amount,
        "collateral_building_id": a["building_id"] or "",
        "equipment_year": int(str(acquired)[:4]) if acquired else 0,
        "inspection_data": inspection,
    }


#: 상대(InsuQ) `IdempotencyStore` 의 키 길이 상한. 넘으면 조용히 잘리거나 거부된다.
_IDEMPOTENCY_MAX_LEN = 128


def idempotency_key_for_asset_change(decision_id: str, change_type: str) -> str:
    """S11 통지의 멱등키 — **업무 정체성에서 결정론적으로 파생**한다 (D141).

    ⛔ **난수를 쓰지 않는다.** 재전송이 다른 키가 되면 멱등성이 성립하지 않는다 —
    같은 처분을 두 번 통지했을 때 증권이 두 번 고쳐진다.

    상대 저장 키는 **3중 복합키 `(requester, skill_id, idempotency_key)`** 라 전역
    유일성이 필요 없다. 「MaintQ 안에서, 그 스킬 안에서」만 유일하면 되므로
    `decision_id` + `change_type` 으로 충분하다. 상대 동작(공개받은 구현):
      - 같은 3중키 + 같은 payload SHA-256 → 저장된 응답을 재계산 없이 그대로 재생
      - 같은 3중키 + **다른** payload → 409 `idempotency_conflict`

    `change_type` 을 반드시 넣는다 — 같은 결정이라도 REMOVE 와 ADD 는 **다른 통지**다.
    키가 같으면 뒤엣것이 재생으로 처리돼 조용히 사라진다.

    ⚠️ 상한(128자)을 넘으면 앞을 자른다. `change_type` 은 **뒤에** 두어 잘려도 남게 한다 —
    REMOVE/ADD 가 섞이는 것이 길이 초과보다 나쁘다.

    📌 계약면에는 이 헤더를 적을 자리가 없다(CP-006 이 그 자리를 만드는 중이다).
    다만 상대 의미론은 **추측이 아니라 배포된 동작으로 공개**받았으므로, 계약이 서도
    이 파생은 달라지지 않는다.
    """
    suffix = f":{change_type}"
    head = decision_id[: _IDEMPOTENCY_MAX_LEN - len(suffix)]
    return f"{head}{suffix}"


def build_request_settlement_payload(
    decision_id: str,
    sale_amount: float,
    outstanding_loan: float,
    approved_by: str,
    prepayment_fee: float | None,
    request_chain_id: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    """FinAllQ request-settlement 스킬(S12, 매각대금 정산·근저당 말소) payload.

    **`decision_id` 는 미서명 draft 결정을 가리킨다 — 그것이 정상 경로다.**
    담보 자산은 LIEN-CONSENT(BLOCKING)로 서명이 막혀 있고 그 담보를 푸는 수단이
    이 스킬 자신이므로(같은 룰의 `resolve_options[1]` "대출 상환 후 근저당 말소"),
    정산 요청이 서명보다 먼저 일어나야 한다. 계약도 이를 명시한다.

    `approved_by` 는 **정산 요청 승인자**이지 처분 서명자가 아니다 — draft 결정은
    `reviewed_by` 가 NULL 이라 거기서 읽으면 항상 빈다. 호출자가 준다.

    ⚠️ FinAllQ `decide_settlement()` 는 DB 조회 0인 순수 함수라 응답의
    `remaining_balance` 는 산술 결과일 뿐 장부 반영 잔액이 아니다(TASK-195).
    MaintQ 는 `lien_released` 만 소비한다.
    """
    with connect(db_path) as con:
        row = con.execute(
            "SELECT a.has_lien, a.lien_creditor FROM decisions d"
            " JOIN assets a ON a.asset_id = d.asset_id"
            " WHERE d.decision_id = ?",
            (decision_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"알 수 없는 decision_id: {decision_id}")
    if not row["has_lien"] or not row["lien_creditor"]:
        raise ValueError(f"{decision_id} 의 자산에 담보가 없다 — 정산 요청 대상이 아니다.")

    payload: dict[str, Any] = {
        "requester": {"finallq_company_id": get_finallq_company_id(db_path) or ""},
        "request_chain_id": request_chain_id,
        "decision_id": decision_id,
        "sale_amount": sale_amount,
        "lien_creditor": row["lien_creditor"],
        "outstanding_loan": outstanding_loan,
        "approved_by": approved_by,
    }
    # optional — None 이면 키를 생략한다. 단 **0.0 은 "수수료 0원"이라는 사실**이므로 싣는다.
    # `if prepayment_fee:` 로 쓰면 0 이 조용히 사라져 "모름"과 "0원"이 같아진다.
    if prepayment_fee is not None:
        payload["prepayment_fee"] = prepayment_fee
    return payload


#: S11 이 InsuQ 에 알릴 수 있는 변경 종류 (계약 `notify-asset-change.json` 의 enum).
ASSET_CHANGE_TYPES = ("REMOVE", "ADD")


def build_notify_asset_change_payload(
    decision_id: str,
    request_chain_id: str,
    change_type: str = "REMOVE",
    db_path: str | None = None,
) -> dict[str, Any]:
    """InsuQ notify-asset-change 스킬(S11, 부보 목적물 변경 통지) payload.

    **S12 와 정반대로 서명 뒤에 온다.** S12(정산)는 담보를 푸는 수단이라 서명보다 **앞서야**
    했지만, S11 은 계약이 *"설비 처분 **확정**에 따른"* 변경이라고 못박는다 — 확정은 서명이다.
    미서명 draft 로 통지하면 보험사가 아직 일어나지 않은 처분으로 증권을 고치게 된다.
    그래서 `signed_at IS NULL` 이면 조립하지 않는다.

    ⛔ **부보되지 않은 자산은 통지하지 않는다** — `insured=false` 이거나 `policy_id` 가 없으면
    InsuQ 에 고칠 증권 자체가 없다. 시드의 `AST-L3-LIFT` 가 실제로 그런 자산이다.
    빈 문자열로 채워 보내면 수신부가 `schema_validation_failed` 를 낸다
    (`request-withdrawal` 이 `error_code=None` 으로 정확히 그 400 을 맞은 전례가 있다).

    `effective_date` 는 **서명일**이지 오늘이 아니다 — 부보 목적물이 빠지는 시점은
    처분이 확정된 날이고, 통지가 늦어도 그 사실은 바뀌지 않는다.
    """
    if change_type not in ASSET_CHANGE_TYPES:
        raise ValueError(
            f"알 수 없는 change_type: {change_type} (가능: {', '.join(ASSET_CHANGE_TYPES)})"
        )

    with connect(db_path) as con:
        row = con.execute(
            "SELECT d.decision_id, d.signed_at, a.asset_id, a.name, a.building_id,"
            "       a.policy_id, a.insured"
            "  FROM decisions d JOIN assets a ON a.asset_id = d.asset_id"
            " WHERE d.decision_id = ?",
            (decision_id,),
        ).fetchone()

    if row is None:
        raise ValueError(f"알 수 없는 decision_id: {decision_id}")
    if not row["signed_at"]:
        raise ValueError(
            f"{decision_id} 는 서명 전이다 — 처분 확정 통지(S11)는 서명 뒤에만 보낸다."
        )
    if not row["insured"] or not row["policy_id"]:
        raise ValueError(
            f"{row['asset_id']} 는 부보 자산이 아니다 — InsuQ 에 변경할 증권이 없다."
        )
    if not row["building_id"]:
        raise ValueError(f"{row['asset_id']} 에 building_id 가 없다 — 부보 목적물을 특정할 수 없다.")

    # D142 — 연결 승인은 주석이 아니라 여기서 강제된다. 위 4가드와 같은 자리다.
    # ⛔ `partner_links` 는 **MaintQ 쪽 대장**이다. 상대 대장과 다를 수 있고 다른 것이 정상이다 —
    #    이 가드가 말하는 것은 *"상대가 받아 줄까"* 가 아니라 *"우리 쪽 승인이 끝났는가"* 다.
    #    2026-09-11 에 `NOT_LINKED` 인 BLD-D 로 S11 이 그냥 나가 200 completed 를 받았다.
    #    시드 주석은 그때도 "연결 승인이 없으면 못 쏜다"고 적고 있었다 — 그 거짓을 닫는다.
    link_state = building_link_state(row["building_id"], partner="insuq", db_path=db_path)
    if link_state != "LINKED":
        raise ValueError(
            f"{row['building_id']} 는 InsuQ 연결 승인 상태가 아니다"
            f" (link_state={link_state!r}) — 통지를 보내지 않는다."
        )

    # 요청자 식별자가 비면 수신부가 `schema_validation_failed` 를 낸다 —
    # `request-withdrawal` 이 `error_code=None` 으로 정확히 그 400 을 맞은 전례가 있다.
    # 빈 값을 실어 보내느니 나가기 전에 멈춘다(D142).
    company_id = get_finallq_company_id(db_path)
    if not company_id:
        raise ValueError(
            "finallq 회사 결 연결 승인이 없다 — 요청자 식별자 없이 통지를 보내지 않는다."
        )

    return {
        "requester": {
            "finallq_company_id": company_id,
            "building_id": row["building_id"],
            "policy_id": row["policy_id"],
        },
        "request_chain_id": request_chain_id,
        "building_id": row["building_id"],
        "policy_id": row["policy_id"],
        "change_type": change_type,
        # 계약은 배열이다. MaintQ 의 처분 결정은 자산 1건 단위라 항상 1개짜리 배열이다 —
        # 여러 건을 한 통지로 묶으려면 결정도 묶여야 하므로 그건 다른 스킬이다.
        "equipment": [row["name"]],
        "effective_date": str(row["signed_at"])[:10],
        "decision_id": row["decision_id"],
    }
