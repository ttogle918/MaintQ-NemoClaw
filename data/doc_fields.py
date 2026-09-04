# -*- coding: utf-8 -*-
"""doc_fields — 결재 문서 템플릿 필드맵 산출 공유 계층 (D124).

`backend/services/po_documents.py`(미리보기) · `backend/services/document_download.py`(docx) ·
`mcp_server/tools/get_document_facts.py`(읽기 도구)가 이 모듈로 위임한다 —
`data/po_draft.py` · `data/maint_value.py` 와 같은 구조다.

⛔ 이 모듈은 `mcp_server` 도 `backend` 도 import 하지 않는다 (D15 — 두 런타임 프로세스의
상호 import 금지). 커넥션은 호출자가 열어서 넘긴다 — 이 모듈은 DB 경로를 모른다.

★ 신원·서명 필드는 여기서 **만들지 않는다** (D23·D37·D81)
────────────────────────────────────────────────────────────────────────────────
`WITHHELD_KEYS` 는 이 계층이 만들지 않는 자리 목록이다. 다운로드 엔드포인트(backend)가
DB 에서 읽어 마지막에 얹는다.

**"빼는" 것이 아니라 "만들지 않는" 것이 핵심이다.** 만든 뒤 빼면 그건 *규율*이지만,
애초에 만들지 않으면 *구조*다 — 신원이 도구 경로로 흐를 수 있는 코드 경로 자체가 없다.
D10 이 UPDATE 를 규율이 아니라 TEMP TRIGGER 로 막은 것과 같은 태도다.

`OVERRIDE`·`OVERRIDE_REASON` 이 여기 있는 이유는 D81 이다 — 도구가 채울 수 있으면
LLM 이 추징 감수 사유를 지어내 BLOCKING 을 뚫는 경로가 생긴다.

📌 `REQUEST_CHAIN_ID` 는 `WITHHELD_KEYS` 에 **없다** — 결재선 추적 ID 이지 사람이 아니다.
   값 원천이 없는 경로에서는 `UNKNOWN` 이 된다.

★ 값이 없으면 지어내지 않는다 (D62)
────────────────────────────────────────────────────────────────────────────────
원천이 없는 자리는 `UNKNOWN`("확인되지 않음")이다. 빈 문자열로 두지 않는다 — 서류의
빈 칸은 읽는 사람에게 **"해당 없음"으로 읽힌다.**

★ 반복 표 행은 채우지 않고 **지운다**
────────────────────────────────────────────────────────────────────────────────
`drop_rows_*()` 가 실제 항목 수를 넘는 행의 자리를 돌려준다. `po_documents.py` 가
*"없는 2·3행을 빈 칸으로 채우지 않고 아예 생략한다"* 고 못박은 것과 같은 태도다.
"""

from __future__ import annotations

from typing import Any

UNKNOWN = "확인되지 않음"

WITHHELD_KEYS = frozenset(
    {
        # 01 설비이상진단보고서
        "TECHNICIAN_NAME",
        "TECHNICIAN_SIGNED_AT",
        "MANAGER_NAME",
        "MANAGER_SIGNED_AT",
        "SIGNATURE_HASH",
        # 02 정비부품발주요청서 · 03 자금집행요청서
        "REQUESTER_NAME",
        "REQUESTER_DEPT",
        "REQUESTER_SIGNED_AT",
        "APPROVER_NAME",
        "APPROVER_SIGNED_AT",
        "FINANCE_APPROVER",
        "FINANCE_SIGNED_AT",
        # 05 설비처분승인서 · 06 진술및보장서
        "SIGNED_BY",
        "SIGNED_AT",
        "OVERRIDE",
        "OVERRIDE_REASON",
    }
)


def val(v: Any) -> str:
    """값 → 문자열. None·공백이면 UNKNOWN."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return UNKNOWN
    return str(v)


def won(v: int | None) -> str:
    return UNKNOWN if v is None else f"{v:,}"


def yn(d: dict, key: str) -> str:
    """불리언 사실 → 예/아니오. **키가 없으면 UNKNOWN** (D62 — 빈칸은 '아니오'로 읽힌다)."""
    if key not in d:
        return UNKNOWN
    v = d[key]
    return ("예" if v else "아니오") if isinstance(v, bool) else str(v)


# ── 공통 라벨 ──────────────────────────────────────────────────────────────────
# `backend/services/po_documents.py` 에서 **그대로 옮긴 것**이다. 문안을 새로 쓰지 않는다.

URGENCY_LABEL = {"urgent": "긴급", "normal": "보통"}

DOC_STATUS_LABEL = {
    "draft": "초안 (미제출)",
    "pending": "결재 대기",
    "approved": "승인 완료",
    "rejected": "반려",
    "finance_approved": "재무 승인 완료",
    "finance_rejected": "재무 반려",
}

APPROVAL_RESULT_LABEL = {
    "draft": "미제출",
    "pending": "결재 대기 중",
    "approved": "승인",
    "rejected": "반려",
    "finance_approved": "재무 승인",
    "finance_rejected": "재무 반려",
}

SEVERITY_LABEL = {"warning": "경고", "fault": "고장", "critical": "위험"}

DECIDED_STATES = ("approved", "rejected", "finance_approved", "finance_rejected")


def amounts(ctx: dict) -> tuple[int, int, int]:
    """(공급가액, 부가세, 합계). 02·03 이 같은 값을 써야 하므로 한 곳에서만 계산한다."""
    subtotal = ctx["unit_price"] * ctx["qty"]
    vat = round(subtotal * 0.1)
    return subtotal, vat, subtotal + vat


def doc_status(ctx: dict) -> str:
    return DOC_STATUS_LABEL.get(ctx["state"], ctx["state"])


def approval_result(ctx: dict) -> str:
    return APPROVAL_RESULT_LABEL.get(ctx["state"], ctx["state"])


# ── 02 정비부품발주요청서 ──────────────────────────────────────────────────────
def drop_rows_02(ctx: dict) -> set[str]:
    """채울 항목이 없는 표 행의 자리.

    `po_drafts` 는 부품 1건짜리 발주라 품목 표 2·3행은 **항상** 삭제한다. `PART_NO_2` 는
    품목 표(t2 r2)와 재고 표(t4 r2) **두 곳**에 있어 이름 하나로 두 행이 함께 지워진다 —
    둘 다 "두 번째 품목" 행이므로 의도한 동작이다.
    """
    dropped = {
        "PART_NO_2", "PART_NAME_2", "QTY_2", "UNIT_PRICE_2", "AMOUNT_2",
        "PART_NO_3", "PART_NAME_3", "QTY_3", "UNIT_PRICE_3", "AMOUNT_3",
        "STOCK_QTY_2", "STOCK_VERDICT_2", "ALT_PART_2", "STOCK_NOTE_2",
    }  # fmt: skip
    if len(ctx.get("quotes") or []) < 2:
        dropped |= {"QUOTE_NO_2", "VENDOR_2", "LEAD_TIME_2", "QUOTE_AMOUNT_2", "SELECTED_2"}
    return dropped


def fields_02(ctx: dict) -> dict[str, str]:
    """02 정비부품발주요청서 — 템플릿 자리 − WITHHELD − drop_rows_02."""
    from data.korean_number import amount_to_korean

    qty = ctx["qty"]
    subtotal, vat, total = amounts(ctx)
    inv = ctx.get("inventory")
    quotes = ctx.get("quotes") or []
    alts = ctx.get("alternatives") or []

    f: dict[str, str] = {
        "PO_REQUEST_NO": ctx["po_id"],
        "REQUESTED_AT": val(ctx.get("created_at")),
        "DIAGNOSIS_DOC_NO": f"DIAG-{ctx['session_id']}" if ctx.get("session_id") else UNKNOWN,
        # po_drafts 는 특정 설비 인스턴스를 별도로 기록하지 않는다
        "EQUIPMENT_ID": UNKNOWN,
        "REQUEST_CHAIN_ID": UNKNOWN,
        "URGENCY": URGENCY_LABEL.get(ctx.get("urgency"), val(ctx.get("urgency"))),
        "DOC_STATUS": doc_status(ctx),
        "REQUEST_REASON": ctx["reason"],
        "IMPACT_IF_DEFERRED": UNKNOWN,
        "TARGET_COMPLETION_DATE": UNKNOWN,
        "PART_NO_1": ctx["part_no"],
        "PART_NAME_1": ctx["part_name"],
        "QTY_1": str(qty),
        "UNIT_PRICE_1": won(ctx["unit_price"]),
        "AMOUNT_1": won(subtotal),
        "SUBTOTAL": won(subtotal),
        "VAT": won(vat),
        "TOTAL_AMOUNT": won(total),
        "TOTAL_AMOUNT_KOREAN": amount_to_korean(total),
        "STOCK_QTY_1": str(inv["qty"]) if inv else UNKNOWN,
        "STOCK_VERDICT_1": ("충분" if inv["qty"] >= qty else "부족") if inv else UNKNOWN,
        "STOCK_NOTE_1": val(inv.get("location")) if inv else UNKNOWN,
        "ALT_PART_1": (
            ", ".join(f'{a["alt_part_no"]}({a["alt_part_name"]})' for a in alts)
            if alts
            else "없음 (호환 확인된 대체품 없음)"
        ),
        # 선정 사유는 시스템이 별도로 기록하지 않는다
        "VENDOR_SELECTION_REASON": UNKNOWN,
        "APPROVAL_RESULT": approval_result(ctx),
        "APPROVAL_COMMENT": val(ctx.get("decision_note")),
    }
    for i, q in enumerate(quotes[:2], start=1):
        f[f"QUOTE_NO_{i}"] = f'Q-{ctx["po_id"]}-{q["supplier_id"]}'
        f[f"VENDOR_{i}"] = q["name"]
        f[f"LEAD_TIME_{i}"] = f'{q["lead_days"]}일'
        f[f"QUOTE_AMOUNT_{i}"] = won(q["unit_price"] * qty)
        f[f"SELECTED_{i}"] = "선정" if q["supplier_id"] == ctx["supplier_id"] else ""
    return f
