# -*- coding: utf-8 -*-
"""정비·부품 발주요청서(02) 미리보기 렌더 — `data/templates/02_정비부품발주요청서.docx` 문안을
`generate_disposal_document.py`의 `render_documents()`와 같은 방식(문안은 코드 상수,
값만 치환, 저장하지 않고 조회 시점에 렌더 — D86)으로 옮긴다 (D118).

여기서 DB 를 다시 읽지 않는다 — 입력은 `backend/services/po.py::get_po()` 가 이미
조립한 `po` dict(그 안의 `quotes`·`inventory`·`alternatives`) 뿐이다. 다시 읽으면
문서가 화면 B(발주 상세)와 다른 시점의 값을 말할 수 있다.

`po_drafts` 는 부품 1건짜리 발주라 템플릿의 다중 품목 표(No 1~3)는 실제로는 항상
1행이다 — 없는 2·3행을 빈 칸으로 채우지 않고 아예 생략한다.
"""

from __future__ import annotations

from typing import Any

import data.doc_review as _doc_review
from data.korean_number import amount_to_korean

_UNKNOWN = "확인되지 않음"

_URGENCY_LABEL = {"urgent": "긴급", "normal": "보통"}

_DOC_STATUS_LABEL = {
    "draft": "초안 (미제출)",
    "pending": "결재 대기",
    "approved": "승인 완료",
    "rejected": "반려",
}

_APPROVAL_RESULT_LABEL = {
    "draft": "미제출",
    "pending": "결재 대기 중",
    "approved": "승인",
    "rejected": "반려",
}


def _val(v: Any) -> str:
    if v is None or (isinstance(v, str) and not v.strip()):
        return _UNKNOWN
    return str(v)


def _won(v: int | None) -> str:
    if v is None:
        return _UNKNOWN
    return f"{v:,}"


def _stock_section(po: dict) -> str:
    inv = po.get("inventory")
    part_no = po["part_no"]
    qty_needed = po["qty"]
    if inv is None:
        verdict = _UNKNOWN
        qty_line = _UNKNOWN
        note = _UNKNOWN
    else:
        qty_line = str(inv["qty"])
        verdict = "충분" if inv["qty"] >= qty_needed else "부족"
        note = _val(inv.get("location"))

    alts = po.get("alternatives") or []
    if alts:
        alt_line = ", ".join(f'{a["alt_part_no"]}({a["alt_part_name"]})' for a in alts)
    else:
        alt_line = "없음 (호환 확인된 대체품 없음)"

    return (
        f"     · 품번: {part_no} / 필요 수량: {qty_needed}\n"
        f"     · 현재고: {qty_line} / 판정: {verdict}\n"
        f"     · 대체품 후보: {alt_line}\n"
        f"     · 비고: {note}"
    )


def _quotes_section(po: dict) -> str:
    quotes = po.get("quotes") or []
    if not quotes:
        return "        · 등록된 공급사 견적 없음"
    lines = []
    for q in quotes:
        selected = "선정" if q["supplier_id"] == po["supplier_id"] else ""
        amount = q["unit_price"] * po["qty"]
        lines.append(
            f'        · {q["name"]} — 리드타임 {q["lead_days"]}일,'
            f' 단가 {_won(q["unit_price"])}원, 견적금액 {_won(amount)}원 {selected}'
        )
    return "\n".join(lines)


def render_po_request_document(po: dict) -> str:
    """`docs/templates/02_정비부품발주요청서.docx` 구조를 옮긴 평문 미리보기.

    입력 `po` 는 `backend/services/po.py::get_po()` 의 반환값(quotes·inventory·
    alternatives 가 이미 붙어 있는 상태)이어야 한다.
    """
    qty = po["qty"]
    unit_price = po["unit_price"]
    subtotal = unit_price * qty
    vat = round(subtotal * 0.1)
    total = subtotal + vat

    diagnosis_doc_no = f"DIAG-{po['session_id']}" if po.get("session_id") else _UNKNOWN
    urgency_label = _URGENCY_LABEL.get(po.get("urgency"), _val(po.get("urgency")))
    doc_status = _DOC_STATUS_LABEL.get(po["state"], po["state"])
    approval_result = _APPROVAL_RESULT_LABEL.get(po["state"], po["state"])

    approver_signed_at = _UNKNOWN if po["state"] in ("approved", "rejected") else "(미기재 — 결재 전)"
    approval_comment = _val(po.get("decision_note"))

    return f"""[정비 · 부품 발주 요청서 — {doc_status}]
요청번호: {po["po_id"]}
요청일시: {_val(po.get("created_at"))}
연계 진단서: {diagnosis_doc_no}
설비 ID: {_UNKNOWN} (po_drafts는 특정 설비 인스턴스를 별도로 기록하지 않는다)
요청자: {_val(po.get("requested_by_name"))} / 소속: {_val(po.get("requested_by_department"))}
긴급도: {urgency_label}

1. 요청 사유
     · {po["reason"]}
     · 미조치 시 예상 영향: {_UNKNOWN}
     · 희망 조치 완료일: {_UNKNOWN}

2. 요청 품목
     · 품번: {po["part_no"]} ({po["part_name"]})
     · 수량: {qty}
     · 단가: {_won(unit_price)}원 (발주 시점 스냅샷 — 이후 가격 변동과 무관)
     · 공급가액: {_won(subtotal)}원
     · 부가세(10%): {_won(vat)}원
     · 합계 금액: {_won(total)}원 ({amount_to_korean(total)})

3. 재고 · 대체품 확인
{_stock_section(po)}

4. 공급사 견적
{_quotes_section(po)}
     · 선정 공급사: {po["supplier_name"]}
     · 선정 사유: {_UNKNOWN} (선정 사유는 시스템이 별도로 기록하지 않는다)

5. 승인
     · 기안(정비사): {_val(po.get("requested_by_name"))} / {_val(po.get("created_at"))}
     · 승인(정비팀장): {_val(po.get("decided_by_name"))} / {approver_signed_at}
     · 승인 결과: {approval_result}
     · 승인 의견 / 반려 사유: {approval_comment}

※ 본 요청서는 정비팀장 승인 전에는 발주가 확정되지 않으며, 승인 이력은 위 5번 항목에 기록됩니다.
※ 기안자는 자신의 요청을 승인할 수 없습니다 (자기결재 금지).
※ {_UNKNOWN}으로 적힌 항목은 「해당 없음」이 아니라 시스템에서 확인되지 않았다는 뜻입니다.
문서 상태: {doc_status} | 생성 시스템: MaintQ
※ {_doc_review.po_request_template_review_notice()}"""
