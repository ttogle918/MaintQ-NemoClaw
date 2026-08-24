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
    "finance_approved": "재무 승인 완료",
    "finance_rejected": "재무 반려",
}

_APPROVAL_RESULT_LABEL = {
    "draft": "미제출",
    "pending": "결재 대기 중",
    "approved": "승인",
    "rejected": "반려",
    "finance_approved": "재무 승인",
    "finance_rejected": "재무 반려",
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

    approver_signed_at = (
        _UNKNOWN
        if po["state"] in ("approved", "rejected", "finance_approved", "finance_rejected")
        else "(미기재 — 결재 전)"
    )
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


_SEVERITY_LABEL = {"warning": "경고", "fault": "고장", "critical": "위험"}


def _causes_lines(causes: list[str]) -> str:
    if not causes:
        return "        · 확인되지 않음"
    return "\n".join(f"        · {c}" for c in causes)


def _actions_lines(actions: list[str]) -> str:
    if not actions:
        return "     · 확인되지 않음"
    return "\n".join(f"     · {a}" for a in actions)


def _basis_entry_summary(entry: dict) -> str:
    """`evidence.basis[]` 항목 하나를 사람이 읽을 한 줄로. 알려진 도구별 필드만 뽑는다 —
    모르는 도구 이름이 와도 예외를 던지지 않고 남은 필드를 그대로 나열한다."""
    tool = entry.get("tool")
    rest = {k: v for k, v in entry.items() if k not in ("tool", "manual_page")}
    if tool == "search_inventory":
        return f'{rest.get("part_no", _UNKNOWN)} 재고 {rest.get("qty", _UNKNOWN)} / 안전재고 {rest.get("safety_stock", _UNKNOWN)}'
    return ", ".join(f"{k}={v}" for k, v in rest.items()) or _UNKNOWN


def _evidence_lines(po: dict, ecd: dict) -> str:
    lines = [
        f'        · 매뉴얼(에러코드 정의) — {po["model"]} 매뉴얼 p.{ecd["manual_page"]}'
        f" — 원문 인용: {_UNKNOWN} (인용 좌표만 남고 원문 텍스트는 저장되지 않는다)"
    ]
    for entry in (po.get("evidence") or {}).get("basis") or []:
        # evidence는 LLM이 create_po_draft 호출 시 자유 형식으로 채운다(D34, 스키마
        # 강제 없음) — basis가 리스트가 아니라 통짜 문자열로 오면 문자 하나하나가
        # entry로 들어온다(실측: PO-0121). 이 함수의 "모르는 도구 이름도 던지지
        # 않는다"는 관용은 dict 항목 안에서만 성립하므로 dict가 아닌 항목은 건너뛴다.
        if not isinstance(entry, dict):
            continue
        tool = entry.get("tool")
        if tool == "lookup_error_code":
            continue  # 위 매뉴얼 인용과 중복
        page = entry.get("manual_page")
        loc = f"p.{page}" if page else "-"
        lines.append(f"        · {tool} — {loc} — {_basis_entry_summary(entry)}")
    return "\n".join(lines)


def render_diagnosis_document(po: dict) -> str:
    """`data/templates/01_설비이상진단보고서.docx` 구조를 옮긴 평문 미리보기.

    `po["error_code_def"]` (error_codes 정본 조회 결과)가 반드시 있어야 한다 —
    호출부(`get_po`)가 이미 그 조건일 때만 이 함수를 부른다.
    """
    ecd = po["error_code_def"]
    evidence = po.get("evidence") or {}
    symptoms = evidence.get("symptoms") or []
    symptom_summary = ", ".join(symptoms) if symptoms else ecd["error_name"]
    severity_label = _SEVERITY_LABEL.get(ecd["severity"], ecd["severity"])
    is_dangerous = ecd["severity"] in ("fault", "critical")

    doc_status = _DOC_STATUS_LABEL.get(po["state"], po["state"])
    manager_signed_at = (
        _UNKNOWN
        if po["state"] in ("approved", "rejected", "finance_approved", "finance_rejected")
        else "(미기재 — 검토 전)"
    )

    return f"""[설비 이상 진단 보고서 — {doc_status}]
문서번호: DIAG-{po["po_id"]} (이 시스템은 진단 세션을 별도 저장하지 않아 연계 발주 ID로 채번한다)
작성일시: {_val(po.get("created_at"))}
설비 ID: {_UNKNOWN} (po_drafts는 특정 설비 인스턴스를 별도로 기록하지 않는다)
설비명 / 설치 위치: {_UNKNOWN} / {_UNKNOWN}
담당 정비사: {_val(po.get("requested_by_name"))}
진단 세션: {_val(po.get("session_id"))}

1. 이상 감지 내역
     · 에러코드: {po["error_code"]} ({ecd["error_name"]}) — 기종: {po["model"]}
     · 증상 요약: {symptom_summary}
     · 심각도: {severity_label}
     · 반복 고장 여부: {_UNKNOWN} (설비 인스턴스 ID가 없어 이력 조회 불가 — get_error_history 는 대화 시점에만 호출된다)

2. 진단 결과 및 근거
     · 진단 결론: {po["reason"]}
     · 근거 자료
{_evidence_lines(po, ecd)}
     · 근거가 확보되지 않은 항목은 「확인되지 않음」으로 표기하며, 추정으로 채우지 않는다.

3. 안전 경고
     · 위험 작업 해당: {"예" if is_dangerous else "확인되지 않음"}
     · 경고 내용: {_UNKNOWN} (안전 문구는 대화 트레이스에서 실시간 생성되며 발주서에는 저장되지 않는다)
     · 필수 선행 조치: {_UNKNOWN}

4. 조치 권고 (매뉴얼 정의 기준, {po["model"]} p.{ecd["manual_page"]})
{_actions_lines(ecd["actions"])}
     · 발생 원인 후보
{_causes_lines(ecd["causes"])}
     · 판정 (수리/교체/매각): {_UNKNOWN} (assess_repair_value 결과는 대화 시점에만 산출되며 저장되지 않는다)
     · 판정 근거: {po["reason"]}

5. 확인
     · 작성(정비사): {_val(po.get("requested_by_name"))} / {_val(po.get("created_at"))}
     · 검토(정비팀장): {_val(po.get("decided_by_name"))} / {manager_signed_at}

본 보고서는 AI 에이전트가 근거를 수집·정리하여 작성한 초안이며, 최종 확인과 서명은 사람이 수행합니다.
※ {_UNKNOWN}으로 적힌 항목은 「해당 없음」이 아니라 시스템에서 확인되지 않았다는 뜻입니다.
문서 상태: {doc_status} | 생성 시스템: MaintQ | 서명 시점 해시: {_UNKNOWN}
※ {_doc_review.diagnosis_template_review_notice()}"""


_FUND_TYPE = "부품 구매대금"  # 고정 — S1/S2 발주 전용 문서라 항상 이 값 (담보/대출 아님)
_FUNDING_METHOD = "계좌이체"  # 고정 — A2A request-withdrawal 전제
_MFA_STATUS_TEXT = "미구현 (MaintQ 에 MFA 시스템 없음)"  # D118 이 이미 이 문구를 확정


def _mask_account(acct: str | None) -> str:
    if not acct:
        return _UNKNOWN
    return acct[-4:].rjust(len(acct), "*") if len(acct) > 4 else acct


def _fund_a2a_lines(a2a_info: dict | None) -> tuple[str, str, str]:
    """(A2A_DELEGATED, A2A_TARGET, REQUEST_CHAIN_ID) 3필드."""
    if a2a_info is None:
        return "아니오 (아직 전송되지 않음)", _UNKNOWN, _UNKNOWN
    delegated = "예" if a2a_info.get("status") == "ok" else "예 (전송 실패 또는 처리 중)"
    return delegated, "FinAllQ", a2a_info["request_chain_id"]


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
    qty, unit_price = po["qty"], po["unit_price"]
    subtotal = unit_price * qty
    vat = round(subtotal * 0.1)
    total = subtotal + vat

    budget_ok, budget_evidence = controls["budget"]
    daily_ok, daily_evidence = controls["daily_limit"]
    fds_verdict, fds_evidence = controls["fds"]
    sod_ok, sod_evidence = controls["sod"]

    delegated, target, chain_id = _fund_a2a_lines(a2a_info)
    payee_bank = _val(payee.get("bank_code")) if payee else _UNKNOWN
    payee_account = _mask_account(payee.get("account_number")) if payee else _UNKNOWN

    doc_status = _DOC_STATUS_LABEL.get(po["state"], po["state"])
    approval_result = _APPROVAL_RESULT_LABEL.get(po["state"], po["state"])
    diagnosis_doc_no = f"DIAG-{po['po_id']}" if po.get("error_code_def") else _UNKNOWN

    return f"""[자금집행 요청서 — {doc_status}]
요청번호: FUND-{po["po_id"]}
요청일시: {_val(po.get("decided_at"))}
연계 발주요청서: {po["po_id"]}
연계 진단서: {diagnosis_doc_no}
기안 부서/기안자: {_val(po.get("requested_by_department"))} / {_val(po.get("requested_by_name"))}
결재선(Chain ID): {chain_id}
자금 종류: {_FUND_TYPE}

1. 집행 목적 및 금액
     · 목적: {po["reason"]}
     · 금액: {_won(total)}원 ({amount_to_korean(total)})
     · 집행 예정일: {_UNKNOWN} (시스템이 별도로 기록하지 않음)
     · 집행 방법: {_FUNDING_METHOD}

2. 수취인
     · 수취인명(공급사): {po["supplier_name"]}
     · 사업자번호: {_UNKNOWN} (suppliers 테이블에 없음)
     · 은행: {payee_bank}
     · 계좌(마스킹): {payee_account}

3. 담보 · 대출 (해당 시)
     · 해당 없음 — 본 문서는 일반 부품 발주(S1/S2) 전용이며 담보·대출 취급 대상이 아니다

4. 내부통제 확인
     · 예산 한도: {budget_evidence} — {"통과" if budget_ok else "초과"}
     · 1일 누적 한도: {daily_evidence} — {"통과" if daily_ok else "초과"}
     · FDS 판정: {fds_verdict} — {fds_evidence}
     · 직무분리(SoD): {sod_evidence if sod_ok is None else ("통과" if sod_ok else "위반")} — {sod_evidence}

5. 서명
     · 기안(정비사): {_val(po.get("requested_by_name"))} / {_val(po.get("created_at"))}
     · 승인(정비팀장): {_val(po.get("decided_by_name"))} / {_val(po.get("decided_at"))}
     · 재무 승인(재무담당): {_val(po.get("finance_decided_by_name"))} / {_val(po.get("finance_decided_at"))}
     · 승인 결과: {approval_result}
     · 재무 의견 / 반려 사유: {_val(po.get("finance_decision_note"))}

6. A2A 위임 전송
     · 위임 여부: {delegated}
     · 대상 시스템: {target}
     · MFA 상태: {_MFA_STATUS_TEXT}

※ {_UNKNOWN}으로 적힌 항목은 「해당 없음」이 아니라 시스템에서 확인되지 않았다는 뜻입니다.
문서 상태: {doc_status} | 생성 시스템: MaintQ
※ {_doc_review.fund_execution_template_review_notice()}"""
