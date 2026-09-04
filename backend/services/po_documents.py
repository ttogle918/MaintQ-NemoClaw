# -*- coding: utf-8 -*-
"""정비·부품 발주요청서(02)·설비이상진단보고서(01) 미리보기 렌더 —
`data/templates/`의 두 docx 문안을 `generate_disposal_document.py`의
`render_documents()`와 같은 방식(문안은 코드 상수, 값만 치환, 저장하지 않고 조회
시점에 렌더 — D86)으로 옮긴다 (D118).

여기서 DB 를 다시 읽지 않는다 — 입력은 `backend/services/po.py::get_po()` 가 이미
조립한 `po` dict(그 안의 `quotes`·`inventory`·`alternatives`·`error_code_def`) 뿐이다.
다시 읽으면 문서가 화면 B(발주 상세)와 다른 시점의 값을 말할 수 있다.

`po_drafts` 는 부품 1건짜리 발주라 템플릿의 다중 품목 표(No 1~3)는 실제로는 항상
1행이다 — 없는 2·3행을 빈 칸으로 채우지 않고 아예 생략한다.

★ 01(진단보고서)의 스코프 한계 — 정직하게 적는다
────────────────────────────────────────────────────────────────────────────────
MaintQ 는 "진단 세션"을 별도 테이블로 저장하지 않는다. 진단의 결과가 발주로
이어진 경우에만 `po_drafts.evidence`·`reason`·`(model,error_code)` 로 그 흔적이
남는다 — 그래서 이 렌더는 **po_draft 를 입력으로 받는다.** 대화 트레이스(`traces`)의
LLM 서술 텍스트(token 이벤트)는 애초에 영속화되지 않으므로(D41, 근본적으로 저장
안 함) "진단 결론" 문장은 `po["reason"]`(사람이 한 줄 요약, D80)을 그대로 쓴다 —
새로 지어내지 않는다. 설비 인스턴스 ID·안전 문구 실측 텍스트도 `po_drafts` 에
저장되지 않으므로 `확인되지 않음`으로 남긴다(D62) — 에이전트 루프가 실시간으로만
만드는 안전 블록(`backend/agent/loop.py`)을 이 문서가 재구성할 근거가 없다.
"""

from __future__ import annotations


import data.doc_fields as _df
import data.doc_review as _doc_review

# 상수·헬퍼는 `data/doc_fields.py` 가 정본이다 (D124) — 미리보기와 docx 가 같은 값을
# 쓰게 하려면 두 벌이 있어서는 안 된다. 이름을 그대로 둔 것은 이 파일의 블록 헬퍼
# (`_stock_section` 등)가 계속 쓰기 때문이다.
_UNKNOWN = _df.UNKNOWN
_URGENCY_LABEL = _df.URGENCY_LABEL
_DOC_STATUS_LABEL = _df.DOC_STATUS_LABEL
_APPROVAL_RESULT_LABEL = _df.APPROVAL_RESULT_LABEL
_val = _df.val
_won = _df.won


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
    f = _df.fields_02(po)

    approver_signed_at = (
        _UNKNOWN if po["state"] in _df.DECIDED_STATES else "(미기재 — 결재 전)"
    )

    return f"""[정비 · 부품 발주 요청서 — {f["DOC_STATUS"]}]
요청번호: {f["PO_REQUEST_NO"]}
요청일시: {f["REQUESTED_AT"]}
연계 진단서: {f["DIAGNOSIS_DOC_NO"]}
설비 ID: {f["EQUIPMENT_ID"]} (po_drafts는 특정 설비 인스턴스를 별도로 기록하지 않는다)
요청자: {_val(po.get("requested_by_name"))} / 소속: {_val(po.get("requested_by_department"))}
긴급도: {f["URGENCY"]}

1. 요청 사유
     · {f["REQUEST_REASON"]}
     · 미조치 시 예상 영향: {f["IMPACT_IF_DEFERRED"]}
     · 희망 조치 완료일: {f["TARGET_COMPLETION_DATE"]}

2. 요청 품목
     · 품번: {f["PART_NO_1"]} ({f["PART_NAME_1"]})
     · 수량: {f["QTY_1"]}
     · 단가: {f["UNIT_PRICE_1"]}원 (발주 시점 스냅샷 — 이후 가격 변동과 무관)
     · 공급가액: {f["SUBTOTAL"]}원
     · 부가세(10%): {f["VAT"]}원
     · 합계 금액: {f["TOTAL_AMOUNT"]}원 ({f["TOTAL_AMOUNT_KOREAN"]})

3. 재고 · 대체품 확인
{_stock_section(po)}

4. 공급사 견적
{_quotes_section(po)}
     · 선정 공급사: {po["supplier_name"]}
     · 선정 사유: {f["VENDOR_SELECTION_REASON"]} (선정 사유는 시스템이 별도로 기록하지 않는다)

5. 승인
     · 기안(정비사): {_val(po.get("requested_by_name"))} / {f["REQUESTED_AT"]}
     · 승인(정비팀장): {_val(po.get("decided_by_name"))} / {approver_signed_at}
     · 승인 결과: {f["APPROVAL_RESULT"]}
     · 승인 의견 / 반려 사유: {f["APPROVAL_COMMENT"]}

※ 본 요청서는 정비팀장 승인 전에는 발주가 확정되지 않으며, 승인 이력은 위 5번 항목에 기록됩니다.
※ 기안자는 자신의 요청을 승인할 수 없습니다 (자기결재 금지).
※ {_UNKNOWN}으로 적힌 항목은 「해당 없음」이 아니라 시스템에서 확인되지 않았다는 뜻입니다.
문서 상태: {f["DOC_STATUS"]} | 생성 시스템: MaintQ
※ {_doc_review.po_request_template_review_notice()}"""


_SEVERITY_LABEL = _df.SEVERITY_LABEL  # 정본은 data/doc_fields.py (D124)


def _causes_lines(causes: list[str]) -> str:
    if not causes:
        return "        · 확인되지 않음"
    return "\n".join(f"        · {c}" for c in causes)


def _actions_lines(actions: list[str]) -> str:
    if not actions:
        return "     · 확인되지 않음"
    return "\n".join(f"     · {a}" for a in actions)


_basis_entry_summary = _df.basis_entry_summary  # 정본은 data/doc_fields.py (D124)


def _evidence_lines(po: dict, ecd: dict) -> str:
    lines = [
        f'        · 매뉴얼(에러코드 정의) — {po["model"]} 매뉴얼 p.{ecd["manual_page"]}'
        f" — 원문 인용: {_UNKNOWN} (인용 좌표만 남고 원문 텍스트는 저장되지 않는다)"
    ]
    # 어떤 항목을 싣는가(비-dict 제외 · lookup_error_code 중복 제외)의 규칙은
    # `data/doc_fields.basis_entries()` 가 정본이다 — 템플릿의 근거 표도 같은 규칙을
    # 써야 서류와 화면이 다른 근거를 말하지 않는다 (D124).
    for entry in _df.basis_entries(po):
        page = entry.get("manual_page")
        loc = f"p.{page}" if page else "-"
        lines.append(f'        · {entry.get("tool")} — {loc} — {_basis_entry_summary(entry)}')
    return "\n".join(lines)


def render_diagnosis_document(po: dict) -> str:
    """`data/templates/01_설비이상진단보고서.docx` 구조를 옮긴 평문 미리보기.

    `po["error_code_def"]` (error_codes 정본 조회 결과)가 반드시 있어야 한다 —
    호출부(`get_po`)가 이미 그 조건일 때만 이 함수를 부른다.
    """
    ecd = po["error_code_def"]
    f = _df.fields_01(po)

    manager_signed_at = (
        _UNKNOWN if po["state"] in _df.DECIDED_STATES else "(미기재 — 검토 전)"
    )

    return f"""[설비 이상 진단 보고서 — {f["DOC_STATUS"]}]
문서번호: {f["DOC_NO"]} (이 시스템은 진단 세션을 별도 저장하지 않아 연계 발주 ID로 채번한다)
작성일시: {f["ISSUED_AT"]}
설비 ID: {f["EQUIPMENT_ID"]} (po_drafts는 특정 설비 인스턴스를 별도로 기록하지 않는다)
설비명 / 설치 위치: {f["EQUIPMENT_NAME"]} / {f["LOCATION"]}
담당 정비사: {_val(po.get("requested_by_name"))}
진단 세션: {f["TRACE_ID"]}

1. 이상 감지 내역
     · 에러코드: {f["ERROR_CODE"]} ({ecd["error_name"]}) — 기종: {po["model"]}
     · 증상 요약: {f["SYMPTOM_SUMMARY"]}
     · 심각도: {f["SEVERITY"]}
     · 반복 고장 여부: {f["REPEAT_FAULT_FLAG"]} (설비 인스턴스 ID가 없어 이력 조회 불가 — get_error_history 는 대화 시점에만 호출된다)

2. 진단 결과 및 근거
     · 진단 결론: {f["DIAGNOSIS_CONCLUSION"]}
     · 근거 자료
{_evidence_lines(po, ecd)}
     · 근거가 확보되지 않은 항목은 「확인되지 않음」으로 표기하며, 추정으로 채우지 않는다.

3. 안전 경고
     · 위험 작업 해당: {f["SAFETY_FLAG"]}
     · 경고 내용: {f["SAFETY_WARNING"]} (안전 문구는 대화 트레이스에서 실시간 생성되며 발주서에는 저장되지 않는다)
     · 필수 선행 조치: {f["SAFETY_PRECONDITION"]}

4. 조치 권고 (매뉴얼 정의 기준, {po["model"]} p.{ecd["manual_page"]})
{_actions_lines(ecd["actions"])}
     · 발생 원인 후보
{_causes_lines(ecd["causes"])}
     · 판정 (수리/교체/매각): {f["REPAIR_REPLACE_VERDICT"]} (assess_repair_value 결과는 대화 시점에만 산출되며 저장되지 않는다)
     · 판정 근거: {f["VERDICT_RATIONALE"]}

5. 확인
     · 작성(정비사): {_val(po.get("requested_by_name"))} / {f["ISSUED_AT"]}
     · 검토(정비팀장): {_val(po.get("decided_by_name"))} / {manager_signed_at}

본 보고서는 AI 에이전트가 근거를 수집·정리하여 작성한 초안이며, 최종 확인과 서명은 사람이 수행합니다.
※ {_UNKNOWN}으로 적힌 항목은 「해당 없음」이 아니라 시스템에서 확인되지 않았다는 뜻입니다.
문서 상태: {f["DOC_STATUS"]} | 생성 시스템: MaintQ | 서명 시점 해시: {_UNKNOWN}
※ {_doc_review.diagnosis_template_review_notice()}"""


# 고정 상수·헬퍼의 정본은 data/doc_fields.py 다 (D124)
_FUND_TYPE = _df.FUND_TYPE
_FUNDING_METHOD = _df.FUNDING_METHOD
_MFA_STATUS_TEXT = _df.MFA_STATUS_TEXT
_mask_account = _df.mask_account
_fund_a2a_lines = _df.fund_a2a_lines


def render_fund_execution_document(
    po: dict,
    controls: dict[str, tuple],
    a2a_info: dict | None,
    payee: dict | None,
) -> str:
    """`data/templates/03_자금집행요청서.docx` 구조를 옮긴 평문 미리보기 (D118·D119).

    입력 `po`는 `render_po_request_document()`와 같은 조립 결과여야 하고,
    `controls`·`a2a_info`는 `backend/services/po.py`(MQ-1708)가 만든 모양 그대로,
    `payee`는 공급사 계좌 정보(`{"account_number", "bank_code"}` | None)다.
    """
    f = _df.fields_03(po, controls, a2a_info, payee)

    return f"""[자금집행 요청서 — {f["DOC_STATUS"]}]
요청번호: {f["FUND_REQUEST_NO"]}
요청일시: {f["REQUESTED_AT"]}
연계 발주요청서: {f["PO_REQUEST_NO"]}
연계 진단서: {f["DIAGNOSIS_DOC_NO"]}
기안 부서/기안자: {_val(po.get("requested_by_department"))} / {_val(po.get("requested_by_name"))}
결재선(Chain ID): {f["REQUEST_CHAIN_ID"]}
자금 종류: {f["FUND_TYPE"]}

1. 집행 목적 및 금액
     · 목적: {f["PURPOSE"]}
     · 금액: {f["AMOUNT"]}원 ({f["AMOUNT_KOREAN"]})
     · 집행 예정일: {f["EXECUTION_DATE"]} (시스템이 별도로 기록하지 않음)
     · 집행 방법: {f["FUNDING_METHOD"]}

2. 수취인
     · 수취인명(공급사): {f["PAYEE_NAME"]}
     · 사업자번호: {f["PAYEE_BIZ_NO"]} (suppliers 테이블에 없음)
     · 은행: {f["PAYEE_BANK"]}
     · 계좌(마스킹): {f["PAYEE_ACCOUNT_MASKED"]}

3. 담보 · 대출 (해당 시)
     · 해당 없음 — 본 문서는 일반 부품 발주(S1/S2) 전용이며 담보·대출 취급 대상이 아니다

4. 내부통제 확인
     · 예산 한도: {f["BUDGET_EVIDENCE"]} — {f["BUDGET_CHECK"]}
     · 1일 누적 한도: {f["DAILY_LIMIT_EVIDENCE"]} — {f["DAILY_LIMIT_CHECK"]}
     · FDS 판정: {f["FDS_VERDICT"]} — {f["FDS_EVIDENCE"]}
     · 직무분리(SoD): {f["SOD_CHECK"]} — {f["SOD_EVIDENCE"]}

5. 서명
     · 기안(정비사): {_val(po.get("requested_by_name"))} / {_val(po.get("created_at"))}
     · 승인(정비팀장): {_val(po.get("decided_by_name"))} / {_val(po.get("decided_at"))}
     · 재무 승인(재무담당): {_val(po.get("finance_decided_by_name"))} / {_val(po.get("finance_decided_at"))}
     · 승인 결과: {f["APPROVAL_RESULT"]}
     · 재무 의견 / 반려 사유: {_val(po.get("finance_decision_note"))}

6. A2A 위임 전송
     · 위임 여부: {f["A2A_DELEGATED"]}
     · 대상 시스템: {f["A2A_TARGET"]}
     · MFA 상태: {f["MFA_STATUS"]}

※ {_UNKNOWN}으로 적힌 항목은 「해당 없음」이 아니라 시스템에서 확인되지 않았다는 뜻입니다.
문서 상태: {f["DOC_STATUS"]} | 생성 시스템: MaintQ
※ {_doc_review.fund_execution_template_review_notice()}"""
