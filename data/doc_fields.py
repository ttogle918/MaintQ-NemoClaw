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


# ── 01 설비이상진단보고서 ──────────────────────────────────────────────────────
def basis_entries(ctx: dict) -> list[dict]:
    """`evidence.basis` 중 문서에 실을 항목.

    규칙이 **두 소비자에게 걸려 있어** 여기 한 곳에 둔다 — 미리보기의 근거 블록
    (`po_documents._evidence_lines`)과 템플릿의 근거 표(`EVIDENCE_*`)다. 두 벌로 두면
    한쪽만 고쳐져 서류와 화면이 다른 근거를 말하게 된다(D90 유형).

    ⛔ `lookup_error_code` 는 뺀다 — 매뉴얼 인용 항목과 중복이다.
    ⛔ dict 가 아닌 항목도 뺀다 — evidence 는 LLM 이 자유 형식으로 채우므로(D34) basis 가
      통짜 문자열로 오면 문자 하나하나가 항목으로 들어온다(실측: PO-0121).
    """
    out = []
    for entry in (ctx.get("evidence") or {}).get("basis") or []:
        if not isinstance(entry, dict) or entry.get("tool") == "lookup_error_code":
            continue
        out.append(entry)
    return out


def basis_entry_summary(entry: dict) -> str:
    """`evidence.basis[]` 항목 하나를 사람이 읽을 한 줄로. 알려진 도구별 필드만 뽑는다 —
    모르는 도구 이름이 와도 예외를 던지지 않고 남은 필드를 그대로 나열한다."""
    tool = entry.get("tool")
    rest = {k: v for k, v in entry.items() if k not in ("tool", "manual_page")}
    if tool == "search_inventory":
        return (
            f'{rest.get("part_no", UNKNOWN)} 재고 {rest.get("qty", UNKNOWN)}'
            f' / 안전재고 {rest.get("safety_stock", UNKNOWN)}'
        )
    return ", ".join(f"{k}={v}" for k, v in rest.items()) or UNKNOWN


def _evidence_rows(ctx: dict) -> list[tuple[str, str, str, str]]:
    """(유형, 출처, 위치, 인용) 표 행. 1행은 매뉴얼 인용, 2행부터 도구 근거."""
    ecd = ctx["error_code_def"]
    rows = [
        (
            "매뉴얼(에러코드 정의)",
            f'{ctx["model"]} 매뉴얼',
            f'p.{ecd["manual_page"]}',
            # 인용 좌표만 남고 원문 텍스트는 저장되지 않는다
            UNKNOWN,
        )
    ]
    for entry in basis_entries(ctx):
        page = entry.get("manual_page")
        rows.append(
            (
                "도구 조회",
                val(entry.get("tool")),
                f"p.{page}" if page else "-",
                basis_entry_summary(entry),
            )
        )
    return rows


def drop_rows_01(ctx: dict) -> set[str]:
    """`po_drafts` 는 에러코드 1건짜리 발주라 감지 내역 2행은 **항상** 삭제한다."""
    dropped = {"DETECTED_AT_2", "ERROR_CODE_2", "SYMPTOM_SUMMARY_2", "SEVERITY_2"}
    if len(_evidence_rows(ctx)) < 2:
        dropped |= {"EVIDENCE_TYPE_2", "EVIDENCE_SOURCE_2", "EVIDENCE_LOC_2", "EVIDENCE_QUOTE_2"}
    if len((ctx["error_code_def"]["actions"]) or []) < 2:
        dropped |= {"ACTION_TYPE_2", "ACTION_DESC_2", "ACTION_DURATION_2", "ACTION_COST_2"}
    return dropped


def fields_01(ctx: dict) -> dict[str, str]:
    """01 설비이상진단보고서 — 템플릿 자리 − WITHHELD − drop_rows_01.

    ⚠ 호출 전에 `ctx["error_code_def"]` 가 있는지 확인할 것. 없으면 이 문서 자체가
    성립하지 않는다 — 미리보기도 그 조건에서만 렌더한다(`get_po()`).
    """
    ecd = ctx["error_code_def"]
    symptoms = (ctx.get("evidence") or {}).get("symptoms") or []
    actions = ecd["actions"] or []
    causes = ecd["causes"] or []

    f: dict[str, str] = {
        # 이 시스템은 진단 세션을 별도 저장하지 않아 연계 발주 ID 로 채번한다
        "DOC_NO": f'DIAG-{ctx["po_id"]}',
        "ISSUED_AT": val(ctx.get("created_at")),
        "DOC_STATUS": doc_status(ctx),
        # po_drafts 는 특정 설비 인스턴스를 별도로 기록하지 않는다
        "EQUIPMENT_ID": UNKNOWN,
        "EQUIPMENT_NAME": UNKNOWN,
        "LOCATION": UNKNOWN,
        "REQUEST_CHAIN_ID": UNKNOWN,
        "TRACE_ID": val(ctx.get("session_id")),
        "DETECTED_AT": UNKNOWN,
        "ERROR_CODE": ctx["error_code"],
        "SYMPTOM_SUMMARY": ", ".join(symptoms) if symptoms else ecd["error_name"],
        "SEVERITY": SEVERITY_LABEL.get(ecd["severity"], ecd["severity"]),
        # 설비 인스턴스 ID 가 없어 이력 조회 불가 — get_error_history 는 대화 시점에만 돈다
        "REPEAT_FAULT_FLAG": UNKNOWN,
        "REPEAT_COUNT": UNKNOWN,
        "ROOT_CAUSE_MODE": ", ".join(causes) if causes else UNKNOWN,
        "SAFETY_FLAG": "예" if ecd["severity"] in ("fault", "critical") else UNKNOWN,
        # 안전 문구는 대화 트레이스에서 실시간 생성되며 발주서에 저장되지 않는다
        "SAFETY_WARNING": UNKNOWN,
        "SAFETY_PRECONDITION": UNKNOWN,
        # assess_repair_value 결과는 대화 시점에만 산출되며 저장되지 않는다
        "REPAIR_REPLACE_VERDICT": UNKNOWN,
        "VERDICT_RATIONALE": ctx["reason"],
        "DIAGNOSIS_CONCLUSION": ctx["reason"],
    }
    for i, (etype, source, loc, quote) in enumerate(_evidence_rows(ctx)[:2], start=1):
        f[f"EVIDENCE_TYPE_{i}"] = etype
        f[f"EVIDENCE_SOURCE_{i}"] = source
        f[f"EVIDENCE_LOC_{i}"] = loc
        f[f"EVIDENCE_QUOTE_{i}"] = quote
    for i, action in enumerate(actions[:2], start=1):
        # error_codes 는 조치의 유형·소요시간·비용을 분류하지 않는다 — 지어내지 않는다(D62)
        f[f"ACTION_TYPE_{i}"] = UNKNOWN
        f[f"ACTION_DESC_{i}"] = action
        f[f"ACTION_DURATION_{i}"] = UNKNOWN
        f[f"ACTION_COST_{i}"] = UNKNOWN
    return f
