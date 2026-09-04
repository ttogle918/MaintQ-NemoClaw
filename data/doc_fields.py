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


# ── 03 자금집행요청서 (D118·D119) ──────────────────────────────────────────────
# 고정 상수. `backend/services/po_documents.py` 에서 그대로 옮겼다.
FUND_TYPE = "부품 구매대금"  # S1/S2 발주 전용 문서라 항상 이 값 (담보/대출 아님)
FUNDING_METHOD = "계좌이체"  # A2A request-withdrawal 전제
MFA_STATUS_TEXT = "미구현 (MaintQ 에 MFA 시스템 없음)"  # D118 이 이미 확정한 문구

# 담보·대출 자리. **UNKNOWN 이 아니다** — 이 문서 종류가 담보 거래가 아니라는 것은
# 모르는 게 아니라 확정 사실이다(D77 의 vat_invoice_issued=False 와 같은 성질).
# 미리보기도 §3 을 "해당 없음 — 본 문서는 일반 부품 발주(S1/S2) 전용" 으로 적는다.
NOT_APPLICABLE = "해당 없음"
_COLLATERAL_KEYS = (
    "COLLATERAL_TYPE",
    "COLLATERAL_ID",
    "COLLATERAL_VALUE",
    "LOAN_AMOUNT",
    "LTV",
    "REPAYMENT_PLAN",
)


def mask_account(acct: str | None) -> str:
    if not acct:
        return UNKNOWN
    return acct[-4:].rjust(len(acct), "*") if len(acct) > 4 else acct


def fund_a2a_lines(a2a_info: dict | None) -> tuple[str, str, str]:
    """(A2A_DELEGATED, A2A_TARGET, REQUEST_CHAIN_ID) 3필드."""
    if a2a_info is None:
        return "아니오 (아직 전송되지 않음)", UNKNOWN, UNKNOWN
    delegated = "예" if a2a_info.get("status") == "ok" else "예 (전송 실패 또는 처리 중)"
    return delegated, "FinAllQ", a2a_info["request_chain_id"]


def drop_rows_03(ctx: dict) -> set[str]:
    """03 에는 반복 표 행이 없다 — 담보·대출 자리는 지우지 않고 '해당 없음' 으로 채운다.

    지우면 "담보 항목을 검토조차 안 했다" 로 읽힌다. 채우면 "검토했고 해당 없음" 이다.
    반복 품목 행(02 의 `_2`·`_3`)과 성질이 다르다.
    """
    return set()


def fields_03(
    ctx: dict, controls: dict[str, tuple], a2a_info: dict | None, payee: dict | None
) -> dict[str, str]:
    """03 자금집행요청서 — 템플릿 자리 − WITHHELD.

    `controls`·`a2a_info`·`payee` 는 backend 가 조립해 넘긴다 — 내부통제 판정(D119)은
    재무 승인 경로에서만 산출되므로 MCP 읽기 도구는 이 문서를 만들지 않는다(D125).
    """
    from data.korean_number import amount_to_korean

    _, _, total = amounts(ctx)
    budget_ok, budget_evidence = controls["budget"]
    daily_ok, daily_evidence = controls["daily_limit"]
    fds_verdict, fds_evidence = controls["fds"]
    sod_ok, sod_evidence = controls["sod"]
    delegated, target, chain_id = fund_a2a_lines(a2a_info)

    f: dict[str, str] = {
        "FUND_REQUEST_NO": f'FUND-{ctx["po_id"]}',
        "REQUESTED_AT": val(ctx.get("decided_at")),
        "PO_REQUEST_NO": ctx["po_id"],
        "DIAGNOSIS_DOC_NO": f'DIAG-{ctx["po_id"]}' if ctx.get("error_code_def") else UNKNOWN,
        "REQUEST_CHAIN_ID": chain_id,
        "FUND_TYPE": FUND_TYPE,
        "DOC_STATUS": doc_status(ctx),
        "PURPOSE": ctx["reason"],
        "AMOUNT": won(total),
        "AMOUNT_KOREAN": amount_to_korean(total),
        # 시스템이 별도로 기록하지 않음
        "EXECUTION_DATE": UNKNOWN,
        "FUNDING_METHOD": FUNDING_METHOD,
        "PAYEE_NAME": ctx["supplier_name"],
        # suppliers 테이블에 없음
        "PAYEE_BIZ_NO": UNKNOWN,
        "PAYEE_BANK": val(payee.get("bank_code")) if payee else UNKNOWN,
        "PAYEE_ACCOUNT_MASKED": mask_account(payee.get("account_number")) if payee else UNKNOWN,
        "BUDGET_CHECK": "통과" if budget_ok else "초과",
        "BUDGET_EVIDENCE": budget_evidence,
        "DAILY_LIMIT_CHECK": "통과" if daily_ok else "초과",
        "DAILY_LIMIT_EVIDENCE": daily_evidence,
        "FDS_VERDICT": fds_verdict,
        "FDS_EVIDENCE": fds_evidence,
        "SOD_CHECK": sod_evidence if sod_ok is None else ("통과" if sod_ok else "위반"),
        "SOD_EVIDENCE": sod_evidence,
        "APPROVAL_RESULT": approval_result(ctx),
        "MFA_STATUS": MFA_STATUS_TEXT,
        "A2A_DELEGATED": delegated,
        "A2A_TARGET": target,
    }
    f.update({k: NOT_APPLICABLE for k in _COLLATERAL_KEYS})
    return f


# ── 05 설비처분승인서 · 06 진술및보장서 ────────────────────────────────────────
# 문안 상수는 `mcp_server/tools/generate_disposal_document.py` 에서 그대로 옮겼다.
# 미리보기(도구)와 docx(다운로드)가 같은 문장을 써야 하므로 정본을 여기 둔다 (D124).

# 자산 단위 verdict 5종의 뜻. **판정하지 않는다** — 엔진이 낸 값을 문서용 한 줄로 옮길 뿐이다.
# 없는 키는 `.get` 으로 흘려 원문 verdict 를 그대로 적는다 (모르는 판정을 통과로 포장 금지).
VERDICT_LINES: dict[str, str] = {
    "BLOCKED": "법정 차단 조건이 발화했다. 해소 없이 처분하면 법령 위반·추징 위험이 있다.",
    "HOLD": "경계 구간이라 사람의 검토가 필요하다. 조건 미해당이라는 뜻이 아니다.",
    "INSUFFICIENT_FACTS": "확인되지 않은 사실이 있어 판정을 확정할 수 없다. 문제 없음이 아니다.",
    "CONDITIONAL": "선행 조건을 이행하면 처분할 수 있다.",
    "CLEAR": "확인된 범위에서 처분을 막는 조건이 발견되지 않았다.",
}

VERDICT_UNKNOWN = "시스템이 정의하지 않은 판정값이다. 통과로 해석하지 말 것."

# 문서에 그대로 실리는 고정 문장. **verdict 와 무관하게 붙는다** (D63).
NO_AUTO_BLOCK_LINE = (
    "이 판정은 처분을 자동으로 차단하지 않는다. 차단 사실이 이 초안에 기록된 채 결재에 "
    "올라가며, 예외 적용 여부와 그 사유는 승인자가 서명 시 기록한다."
)

UNKNOWN_LINE = (
    f"'{UNKNOWN}' 으로 적힌 항목은 '해당 없음'이 아니라 시스템에서 확인되지 않았다는 뜻이다 — "
    "매도인이 별도로 확인해 보완해야 한다."
)


def fact(facts: dict, key: str) -> str:
    """값 사실. 키가 없거나 빈 문자열이면 '확인되지 않음'."""
    value = facts.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        return UNKNOWN
    return str(value)


def law_lines(bundle: dict) -> str:
    laws = bundle.get("laws") or []
    if not laws:
        return "        · 인용된 법령 조문 없음 (발화한 조건이 없거나 계약 근거만 인용됨)"
    return "\n".join(
        f"        · {law.get('law_ref_id')} (시행 {law.get('effective_from') or UNKNOWN})"
        f" {law.get('text_hash') or UNKNOWN}"
        for law in laws
    )


def rule_lines(bundle: dict) -> str:
    rules = bundle.get("rules") or []
    if not rules:
        return "        · 인용된 해석 룰 없음"
    return "\n".join(
        f"        · {r.get('rule_id')} v{r.get('rule_version')} {r.get('rule_hash') or UNKNOWN}"
        for r in rules
    )


def contract_lines(bundle: dict) -> str:
    contracts = bundle.get("contracts") or []
    if not contracts:
        return "        · 인용된 계약 근거 없음"
    return "\n".join(f"        · {c.get('contract_ref')}" for c in contracts)


def open_condition_lines(bundle: dict) -> str:
    """발화·보류·사실부족으로 남은 룰. **재판정이 아니라 번들 `evaluated[]` 의 전재**다."""
    rows = [e for e in (bundle.get("evaluated") or []) if e.get("verdict") != "CLEAR"]
    if not rows:
        return "        · 미해소 항목 없음 (평가한 룰이 전부 CLEAR)"
    return "\n".join(
        f"        · {e.get('rule_id')} v{e.get('rule_version')} — {e.get('verdict')}"
        f" (근거 조문: {', '.join(e.get('law_refs') or []) or '없음'})"
        for e in rows
    )


def _disposal_common(bundle: dict, verdict: str, bundle_hash: str, decision_id: str,
                     doc_state: str, created_at: str, request_chain_id: str) -> dict[str, str]:
    """05·06 이 함께 쓰는 자리."""
    facts = bundle.get("facts") or {}
    return {
        "DECISION_ID": decision_id,
        "DOC_STATE": doc_state,
        "CREATED_AT": created_at,
        "REQUEST_CHAIN_ID": request_chain_id,
        "ASSET_ID": fact(facts, "asset_id"),
        "ASSET_STATUS": fact(facts, "status"),
        "ACQUIRED_AT": fact(facts, "acquired_at"),
        "BUILDING_ID": fact(facts, "building_id"),
        "DISPOSAL_MODE": fact(facts, "disposal_mode"),
        "DISPOSAL_DATE": fact(facts, "disposal_date"),
        "VERDICT": verdict,
        "BUNDLE_HASH": bundle_hash,
        "OPEN_CONDITIONS": open_condition_lines(bundle),
        "TEMPLATE_REVIEW_NOTICE": _template_review_notice(),
    }


def _template_review_notice() -> str:
    # 지연 import — `data/doc_review.py` 는 순수 계층이지만 import 순서를 이 모듈이
    # 강제하지 않도록 함수 안에서 부른다 (`fields_02` 의 korean_number 와 같은 방식).
    import data.doc_review as _doc_review

    return _doc_review.template_review_notice()


def fields_05(
    bundle: dict,
    *,
    verdict: str,
    bundle_hash: str,
    reason: str,
    decision_id: str,
    doc_state: str = UNKNOWN,
    created_at: str = UNKNOWN,
    request_chain_id: str = UNKNOWN,
) -> dict[str, str]:
    """05 설비처분승인서 — 템플릿 자리 − WITHHELD.

    `doc_state`·`created_at`·`request_chain_id` 는 `decisions` **행**에서 오는데
    `render_documents()` 는 번들과 판정값만 받는다. 도구 경로(초안 생성 직후)에서는 아직
    알 수 없으므로 기본값 UNKNOWN 이고, 다운로드 엔드포인트가 실제 값을 넘긴다.

    ⛔ SIGNED_BY·SIGNED_AT·OVERRIDE·OVERRIDE_REASON 은 인자로도 받지 않는다 (D81·D23).
    """
    evaluated = bundle.get("evaluated") or []
    fired = [e for e in evaluated if e.get("verdict") != "CLEAR"]
    f = _disposal_common(
        bundle, verdict, bundle_hash, decision_id, doc_state, created_at, request_chain_id
    )
    f.update(
        {
            "REASON": reason,
            "VERDICT_LINE": VERDICT_LINES.get(verdict, VERDICT_UNKNOWN),
            "RULES_EVALUATED": str(len(evaluated)),
            "RULES_OPEN": str(len(fired)),
            "LAW_COUNT": str(len(bundle.get("laws") or [])),
            "LAW_LINES": law_lines(bundle),
            "RULE_COUNT": str(len(bundle.get("rules") or [])),
            "RULE_LINES": rule_lines(bundle),
            "CONTRACT_COUNT": str(len(bundle.get("contracts") or [])),
            "CONTRACT_LINES": contract_lines(bundle),
        }
    )
    return f


def fields_06(
    bundle: dict,
    *,
    verdict: str,
    bundle_hash: str,
    decision_id: str,
    doc_state: str = UNKNOWN,
    created_at: str = UNKNOWN,
    request_chain_id: str = UNKNOWN,
) -> dict[str, str]:
    """06 진술및보장서 — 템플릿 자리 − WITHHELD."""
    facts = bundle.get("facts") or {}
    f = _disposal_common(
        bundle, verdict, bundle_hash, decision_id, doc_state, created_at, request_chain_id
    )
    f.update(
        {
            "HAS_LIEN": yn(facts, "has_lien"),
            "LIEN_CREDITOR": fact(facts, "lien_creditor"),
            "LIEN_CONSENT_REF": fact(facts, "lien_consent_ref"),
            "INSURED": yn(facts, "insured"),
            "POLICY_ID": fact(facts, "policy_id"),
            "SAFETY_INSPECTION_TARGET": yn(facts, "safety_inspection_target"),
            "LAST_INSPECTION_DATE": fact(facts, "last_inspection_date"),
            "INSPECTION_VALID_UNTIL": fact(facts, "inspection_valid_until"),
            "TAX_CREDIT_APPLIED": yn(facts, "tax_credit_applied"),
            "MONTHS_SINCE_ACQUISITION": fact(facts, "months_since_acquisition"),
            "VAT_INVOICE_ISSUED": yn(facts, "vat_invoice_issued"),
        }
    )
    return f


# ── DB 컨텍스트 ────────────────────────────────────────────────────────────────
# 커넥션은 **호출자가 열어 넘긴다** — 이 모듈은 DB 경로를 모른다 (data/po_draft.py 규약).
# backend 는 `connect()`, MCP 는 `read_only()` 로 연다. 권한은 커넥션의 종류가 정한다.

PO_SELECT = (
    "SELECT p.*, pt.name AS part_name, s.name AS supplier_name,"
    " ru.display_name AS requested_by_name, ru.department AS requested_by_department,"
    " du.display_name AS decided_by_name,"
    " fu.display_name AS finance_decided_by_name"
    " FROM po_drafts p"
    " JOIN parts pt ON pt.part_no = p.part_no"
    " JOIN suppliers s ON s.supplier_id = p.supplier_id"
    " LEFT JOIN users ru ON ru.user_id = p.requested_by"
    " LEFT JOIN users du ON du.user_id = p.decided_by"
    " LEFT JOIN users fu ON fu.user_id = p.finance_decided_by"
)


def iso_utc(ts: str | None) -> str | None:
    """DB 의 naive 문자열 → 타임존이 명시된 ISO-8601.

    `CURRENT_TIMESTAMP` 는 **UTC** 인데 'YYYY-MM-DD HH:MM:SS' 로만 저장돼 타임존 표기가
    없다. 그대로 내보내면 브라우저가 로컬 시각으로 해석해 KST 기준 9시간이 어긋난다
    (실제로 "방금"이 "9시간 전"으로 보였다). 저장은 UTC, 전송은 UTC 명시, 표시는
    클라이언트가 로컬로 — 경계를 여기서 긋는다 (D39).

    ⚠ `backend/services/po.py` 가 이 함수를 재수출한다 — 기존 import 5곳
    (`agent/trace.py`·`routers/equipment.py`·`services/decisions.py`·`disposal.py`·
    `repairs.py`)이 그대로 동작한다. 여기로 옮긴 이유는 `po_context()` 가 backend 를
    import 할 수 없기 때문이다(D15).
    """
    if not ts:
        return ts
    return ts.replace(" ", "T") + ("" if ts.endswith("Z") or "+" in ts else "Z")


def row_to_po(r) -> dict:
    import json

    d = dict(r)
    d["evidence"] = json.loads(d["evidence"]) if d.get("evidence") else None
    # 미등록·NULL 이면 ID 를 그대로 (display_name() 과 같은 규칙)
    d["requested_by_name"] = d.get("requested_by_name") or d.get("requested_by") or ""
    d["decided_by_name"] = d.get("decided_by_name") or d.get("decided_by") or ""
    d["finance_decided_by_name"] = (
        d.get("finance_decided_by_name") or d.get("finance_decided_by") or ""
    )
    d["created_at"] = iso_utc(d.get("created_at"))
    return d


def po_context(con, po_id: str) -> dict | None:
    """발주 1건 → 문서 3종(01·02·03)이 쓰는 컨텍스트. 없으면 None (예외 아님).

    `backend/services/po.py::get_po()` 가 하던 SELECT+조인을 그대로 옮긴 것이다.
    ⛔ `controls`·`a2a_info`·`payee`(03 내부통제·A2A·수취인)는 **여기 없다** — 그 조립은
      `backend.services.a2a_history` 와 `data.expenditure_limits` 를 함께 쓰는 backend
      로직이라 MCP 가 재사용할 수 없다(D15). `get_po()` 가 그 위에 얹는다.
    """
    import json

    from data import po_draft

    r = con.execute(PO_SELECT + " WHERE p.po_id = ?", (po_id,)).fetchone()
    if r is None:
        return None
    ctx = row_to_po(r)

    ctx["quotes"] = po_draft.list_quotes(con, part_no=ctx["part_no"])
    inv = con.execute(
        "SELECT qty, safety_stock, location FROM inventory WHERE part_no = ?",
        (ctx["part_no"],),
    ).fetchone()
    ctx["inventory"] = dict(inv) if inv else None
    # find_alternative_parts 와 같은 쿼리 (D118 발주요청서 §3 "재고·대체품 확인").
    # compat_confirmed=false 는 제안 금지 대상이라 여기서도 걸러 낸다.
    ctx["alternatives"] = [
        dict(alt)
        for alt in con.execute(
            "SELECT a.alt_part_no, pt2.name AS alt_part_name, a.note"
            " FROM part_alternatives a JOIN parts pt2 ON pt2.part_no = a.alt_part_no"
            " WHERE a.part_no = ? AND a.compat_confirmed = true"
            " ORDER BY a.alt_part_no",
            (ctx["part_no"],),
        ).fetchall()
    ]
    # 설비이상진단보고서(01) 용 — 이미 사람 승인을 거친 error_codes 정본(D33)에서
    # severity·causes·actions·manual_page 를 그대로 인용한다.
    ecd = None
    if ctx.get("model") and ctx.get("error_code"):
        ecd = con.execute(
            "SELECT error_name, severity, causes, actions, manual_page"
            " FROM error_codes WHERE model = ? AND code = ?",
            (ctx["model"], ctx["error_code"]),
        ).fetchone()
    if ecd:
        ecd = dict(ecd)
        ecd["causes"] = json.loads(ecd["causes"])
        ecd["actions"] = json.loads(ecd["actions"])
    ctx["error_code_def"] = ecd
    return ctx


def disposal_context(con, decision_id: str) -> dict | None:
    """처분 결정 1건 → 문서 2종(05·06)이 쓰는 컨텍스트. 없으면 None (예외 아님).

    ⛔ `signed_by`·`signed_at`·`override`·`override_reason` 은 **읽지 않는다** — 이 계층이
      만들지 않는 자리다(WITHHELD_KEYS). 다운로드 엔드포인트가 DB 에서 따로 읽어 얹는다.
    """
    import json

    r = con.execute(
        "SELECT decision_id, asset_id, state, verdict_at_signing, bundle_hash,"
        " evidence_bundle, reason, created_at"
        " FROM decisions WHERE decision_id = ?",
        (decision_id,),
    ).fetchone()
    if r is None:
        return None
    d = dict(r)
    return {
        "decision_id": d["decision_id"],
        "asset_id": d["asset_id"],
        "state": d["state"],
        "verdict": d["verdict_at_signing"],
        "bundle_hash": d["bundle_hash"],
        "bundle": json.loads(d["evidence_bundle"]),
        "reason": val(d.get("reason")),
        "created_at": iso_utc(d.get("created_at")) or UNKNOWN,
    }
