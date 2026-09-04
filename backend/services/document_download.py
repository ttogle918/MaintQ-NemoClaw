# -*- coding: utf-8 -*-
"""document_download — 결재 문서 docx 를 **다운로드 시점에** 조립한다 (D124).

★ 저장하지 않는다 (D86)
────────────────────────────────────────────────────────────────────────────────
`fill_template()` 이 `io.BytesIO` 로만 만들고, 이 모듈은 그 bytes 를 그대로 라우터에
넘긴다. 디스크에도 DB 에도 남기지 않는다 — 저장하면 템플릿·산식이 바뀔 때 저장본이
조용히 낡는다(D57·D86 선례).

★ 신원은 여기서만 얹는다 (D23·D37·D81)
────────────────────────────────────────────────────────────────────────────────
`data/doc_fields.py` 는 `WITHHELD_KEYS` 를 **만들지 않는다.** 그 자리를 이 모듈이 DB 값으로
채운다. "만든 뒤 빼기"가 아니라 "만들지 않고 나중에 얹기"라서, MCP 도구 경로에는 신원이
흐를 수 있는 코드 경로 자체가 없다.

값이 아직 없을 때 `확인되지 않음` 이 아니라 `(미기재 — 결재 전)` 을 쓰는 이유: 미리보기가
이미 그렇게 한다(`po_documents` 의 `approver_signed_at`). "시스템에 원천이 없다"(D62)와
"아직 그 단계가 아니다"는 다른 사실이다.

★ 가용성 규칙은 미리보기와 **같은 조건**을 쓴다
────────────────────────────────────────────────────────────────────────────────
두 곳에 다른 조건을 두면 화면엔 안 보이는데 URL 로는 받아지는 문서가 생긴다.
  · 01 진단보고서 — `error_code_def` 가 없으면 만들지 않는다
  · 03 자금집행요청서 — 재무 승인 단계 상태가 아니면 만들지 않는다

★ 대상은 5종이다
────────────────────────────────────────────────────────────────────────────────
01·02·03·05·06. **04(담보대출심사회신서)는 없다** — D118 이 MaintQ 구현 대상에서
제외했다(FinAllQ 소관).
"""

from __future__ import annotations

from urllib.parse import quote

from backend.services.docx_render import fill_template
from data import doc_fields as df

# 문서 키 → (템플릿 파일명, 파일 이름에 쓸 문서명)
PO_DOCS: dict[str, tuple[str, str]] = {
    "diagnosis": ("01_설비이상진단보고서.docx", "설비이상진단보고서"),
    "po_request": ("02_정비부품발주요청서.docx", "정비부품발주요청서"),
    "fund_execution": ("03_자금집행요청서.docx", "자금집행요청서"),
}

DECISION_DOCS: dict[str, tuple[str, str]] = {
    "approval": ("05_설비처분승인서.docx", "설비처분승인서"),
    "representation_warranty": ("06_진술및보장서.docx", "진술및보장서"),
}

_NOT_YET_APPROVED = "(미기재 — 결재 전)"
_NOT_YET_REVIEWED = "(미기재 — 검토 전)"
_NOT_YET_SIGNED = "(미기재 — 서명 시 기록된다)"
_NO_OVERRIDE = "미적용"


class DocumentUnavailable(Exception):
    """이 발주·결정에서는 그 문서가 성립하지 않는다 → 404. 사유를 메시지에 적는다."""


def content_disposition(filename: str) -> str:
    """한글 파일명은 RFC 5987 `filename*`, ASCII `filename` 은 구형 클라이언트 폴백."""
    ascii_name = filename.encode("ascii", "replace").decode("ascii").replace("?", "_")
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'


def _po_identity(po: dict, doc: str) -> dict[str, str]:
    """01·02·03 의 신원·서명 자리. **여기서만 DB 값을 얹는다** (D23·D37)."""
    decided = po["state"] in df.DECIDED_STATES
    requester = df.val(po.get("requested_by_name"))
    dept = df.val(po.get("requested_by_department"))
    created = df.val(po.get("created_at"))
    manager = df.val(po.get("decided_by_name"))
    decided_at = df.val(po.get("decided_at")) if decided else _NOT_YET_APPROVED

    if doc == "diagnosis":
        return {
            "TECHNICIAN_NAME": requester,
            "TECHNICIAN_SIGNED_AT": created,
            "MANAGER_NAME": manager,
            "MANAGER_SIGNED_AT": df.val(po.get("decided_at")) if decided else _NOT_YET_REVIEWED,
            # po_drafts 에 서명 해시 자리가 없다 — 지어내지 않는다 (D62)
            "SIGNATURE_HASH": df.UNKNOWN,
        }
    if doc == "po_request":
        return {
            "REQUESTER_NAME": requester,
            "REQUESTER_DEPT": dept,
            "REQUESTER_SIGNED_AT": created,
            "APPROVER_NAME": manager,
            "APPROVER_SIGNED_AT": decided_at,
        }
    return {  # fund_execution
        "REQUESTER_NAME": requester,
        "REQUESTER_DEPT": dept,
        "REQUESTER_SIGNED_AT": created,
        "MANAGER_NAME": manager,
        "MANAGER_SIGNED_AT": decided_at,
        "FINANCE_APPROVER": df.val(po.get("finance_decided_by_name")),
        "FINANCE_SIGNED_AT": df.val(po.get("finance_decided_at")),
    }


def build_po_docx(po: dict, doc: str, fund_inputs: tuple | None = None) -> tuple[bytes, str]:
    """(bytes, 파일명). 문서가 성립하지 않으면 `DocumentUnavailable`.

    `po` 는 `backend/services/po.py::get_po()` 의 반환값이어야 한다 — 미리보기와 **같은
    조립 결과**를 써야 화면과 docx 가 갈리지 않는다.
    """
    if doc not in PO_DOCS:
        raise DocumentUnavailable(f"알 수 없는 문서 키: {doc}")
    template, label = PO_DOCS[doc]

    if doc == "diagnosis":
        if not po.get("error_code_def"):
            raise DocumentUnavailable(
                "이 발주는 에러코드 진단에서 시작하지 않아 진단보고서가 성립하지 않습니다"
            )
        fields, dropped = df.fields_01(po), df.drop_rows_01(po)
    elif doc == "po_request":
        fields, dropped = df.fields_02(po), df.drop_rows_02(po)
    else:
        if fund_inputs is None:
            raise DocumentUnavailable(
                "재무 승인 단계 이전에는 자금집행요청서가 성립하지 않습니다"
                f" (현재 상태: {po['state']})"
            )
        fields = df.fields_03(po, *fund_inputs)
        dropped = df.drop_rows_03(po)

    data = fill_template(template, fields | _po_identity(po, doc), drop_rows=dropped)
    return data, f'{po["po_id"]}_{label}.docx'


def _decision_identity(row: dict) -> dict[str, str]:
    """05·06 의 서명·예외 자리 (D81 — 도구는 못 채우고 서명 화면만 채운다)."""
    return {
        "SIGNED_BY": df.val(row.get("signed_by_name")) if row.get("signed_at") else _NOT_YET_SIGNED,
        "SIGNED_AT": df.val(row.get("signed_at")) if row.get("signed_at") else _NOT_YET_SIGNED,
        "OVERRIDE": "적용" if row.get("override") else _NO_OVERRIDE,
        "OVERRIDE_REASON": df.val(row.get("override_reason")),
        "REQUESTER_NAME": df.val(row.get("requested_by_name")),
        "REQUESTER_DEPT": df.val(row.get("requested_by_department")),
    }


def build_decision_docx(ctx: dict, doc: str, row: dict) -> tuple[bytes, str]:
    """(bytes, 파일명). `ctx` 는 `data/doc_fields.disposal_context()` 결과."""
    if doc not in DECISION_DOCS:
        raise DocumentUnavailable(f"알 수 없는 문서 키: {doc}")
    template, label = DECISION_DOCS[doc]

    common = {
        "verdict": ctx["verdict"],
        "bundle_hash": ctx["bundle_hash"],
        "decision_id": ctx["decision_id"],
        "doc_state": ctx["state"],
        "created_at": ctx["created_at"],
        "request_chain_id": df.val(row.get("session_id")),
    }
    if doc == "approval":
        fields = df.fields_05(ctx["bundle"], reason=ctx["reason"], **common)
    else:
        fields = df.fields_06(ctx["bundle"], **common)

    # 05 는 REQUESTER_*, 06 은 SIGNED_* 만 쓴다 — 템플릿에 없는 키는 fill_template 이
    # 초과로 잡으므로 실제 자리에 맞춰 좁힌다.
    from backend.services.docx_render import template_placeholders

    identity = _decision_identity(row)
    identity = {k: v for k, v in identity.items() if k in template_placeholders(template)}

    data = fill_template(template, fields | identity)
    return data, f'{ctx["decision_id"]}_{label}.docx'
