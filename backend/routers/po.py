# -*- coding: utf-8 -*-
"""발주 승인 워크플로우 (docs/06_REPO_API.md §2.2).

**상태 전이 = 권한.** MCP 도구는 draft 생성만 하고(D10), 전이는 전부 여기를 통한다.
정비사가 approve 를 호출하면 403 — 평가 지표(권한 위반 차단 100%)의 대상이다.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from backend.deps import Caller, caller, require
from backend.services import document_download as dl
from backend.services import po as svc
from backend.services.docx_render import DOCX_MIME

router = APIRouter(prefix="/api/po", tags=["po"])
logger = logging.getLogger(__name__)


class RejectBody(BaseModel):
    # 사유 없는 반려는 요청자가 뭘 고쳐야 할지 알 수 없다 (D38)
    reason: str = Field(min_length=1)


class ApproveBody(BaseModel):
    note: str | None = None


@router.get("")
def list_pos(state: str | None = None, c: Caller = Depends(caller)) -> dict:
    """승인 큐. 팀장 화면이 주 사용처지만 정비사도 자기 요청 상태를 본다."""
    return {"items": svc.list_pos(state)}


@router.get("/{po_id}")
def get_po(po_id: str, c: Caller = Depends(caller)) -> dict:
    po = svc.get_po(po_id)
    if po is None:
        raise HTTPException(404, f"발주서를 찾을 수 없습니다: {po_id}")
    return po


class CreatePoBody(BaseModel):
    part_no: str
    qty: int
    supplier_id: str
    reason: str
    urgency: str = "normal"
    model: str | None = None
    error_code: str | None = None
    evidence: dict | None = None


class UpdatePoBody(BaseModel):
    part_no: str
    qty: int
    supplier_id: str
    reason: str
    urgency: str = "normal"
    model: str | None = None
    error_code: str | None = None
    evidence: dict | None = None


# status/reason → HTTP. svc.create/update 가 data.po_draft.validate_and_price·
# 자체 _validate_input 이 돌려주는 reason 전부를 여기 매핑한다 — 목록 밖은 500.
_REASON_HTTP: dict[str, int] = {
    "invalid_input": 422,
    "reason_required": 422,
    "model_code_pair": 422,
    "invalid_model": 422,
    "unknown_error_code": 422,
    "moq_not_met": 422,
    "integrity": 422,
}


def _status_code(result: dict) -> int:
    # svc.create()/svc.update() 성공 시엔 get_po() 셰이프를 그대로 돌려주는데(PO_DETAIL_KEYS,
    # `status` 키 자체가 없다) — 실패 dict(_validate_input·validate_and_price)만 `status` 를
    # 갖는다. 그래서 "status 키가 없다"도 성공으로 본다.
    status = result.get("status")
    if status in (None, "ok"):
        return 200
    if status == "not_found":
        return 404
    return _REASON_HTTP.get(result.get("reason"), 500)


@router.get("/{po_id}/documents/{doc}.docx")
def download_po_document(po_id: str, doc: str, c: Caller = Depends(caller)) -> Response:
    """결재 문서 docx — **저장하지 않고** 여기서 조립해 스트림한다 (D86·D124).

    가용성 규칙은 `documents_preview` 와 **같은 조건**을 쓴다(`document_download` 가
    같은 판정을 한다) — 두 곳에 다른 조건을 두면 화면엔 안 보이는데 URL 로는 받아지는
    문서가 생긴다.

    권한은 조회와 같다 — 미리보기를 이미 볼 수 있는 사람이면 다운로드도 된다.
    새 권한 경계를 만들지 않는다(D38 지표를 오염시키지 않기 위해서다).
    """
    if doc not in dl.PO_DOCS:
        raise HTTPException(404, f"알 수 없는 문서: {doc}")
    po = svc.get_po(po_id)
    if po is None:
        raise HTTPException(404, f"발주서를 찾을 수 없습니다: {po_id}")

    fund_inputs = svc.get_fund_execution_inputs(po) if doc == "fund_execution" else None
    try:
        data, filename = dl.build_po_docx(po, doc, fund_inputs)
    except dl.DocumentUnavailable as e:
        raise HTTPException(404, str(e)) from e

    return Response(
        content=data,
        media_type=DOCX_MIME,
        headers={"Content-Disposition": dl.content_disposition(filename)},
    )


@router.get("/quotes/{part_no}")
def get_quotes(part_no: str, c: Caller = Depends(caller)) -> dict:
    """부품의 공급사별 견적. `/technician/po/new` 화면이 공급사를 고르기 전에 부른다.

    이 경로가 `/api/po` 아래 있는 건 po_id 스코프가 아니라 "발주 초안을 만들기 위한
    사전 조회"라는 성격 때문이다 — 부품 조회 REST(`routers/maint_value.py`)와는
    목적이 다르다. 부품·공급사가 없으면 빈 리스트(404 아님, D62).
    """
    return {"part_no": part_no, "quotes": svc.quotes_for_part(part_no)}


@router.post("")
def create_po(body: CreatePoBody, c: Caller = Depends(caller)) -> JSONResponse:
    """화면에서 발주 초안을 직접 생성한다 (P39 축소판). 정비사 전용.

    응답은 GET /api/po/{po_id} 와 같은 상세 셰이프다(quotes·inventory·trace_url 포함,
    trace_url 은 session_id 가 없으므로 항상 null) — 화면이 생성 직후 바로 상세를
    그릴 수 있게 별도 조회 없이 준다.
    """
    require(c, "technician", "발주 초안 생성")
    result = svc.create(
        part_no=body.part_no, qty=body.qty, supplier_id=body.supplier_id,
        reason=body.reason, urgency=body.urgency, model=body.model,
        error_code=body.error_code, evidence=body.evidence, requested_by=c.user_id,
    )
    return JSONResponse(status_code=_status_code(result), content=result)


@router.patch("/{po_id}")
def update_po(po_id: str, body: UpdatePoBody, c: Caller = Depends(caller)) -> JSONResponse:
    """draft 상태 발주 초안을 수정한다. draft 가 아니면 409. 정비사 전용
    (요청자 본인이 아니어도 technician 이면 누구나 — 2026-08-21 설계 §4)."""
    require(c, "technician", "발주 초안 수정")
    try:
        result = svc.update(
            po_id, part_no=body.part_no, qty=body.qty, supplier_id=body.supplier_id,
            reason=body.reason, urgency=body.urgency, model=body.model,
            error_code=body.error_code, evidence=body.evidence,
        )
    except KeyError as e:
        raise HTTPException(404, f"발주서를 찾을 수 없습니다: {po_id}") from e
    except svc.NotEditableError as e:
        raise HTTPException(409, str(e)) from e
    return JSONResponse(status_code=_status_code(result), content=result)


def _transition(po_id: str, target: str, decided_by: str | None, note: str | None) -> dict:
    try:
        return svc.transition(po_id, target, decided_by=decided_by, note=note)
    except KeyError as e:
        raise HTTPException(404, f"발주서를 찾을 수 없습니다: {po_id}") from e
    except svc.TransitionError as e:
        # 권한은 맞지만 순서가 틀린 경우 — 403 과 구분해서 409
        raise HTTPException(409, str(e)) from e


@router.post("/{po_id}/submit")
def submit(po_id: str, c: Caller = Depends(caller)) -> dict:
    """draft → pending. 정비사의 '팀장 승인 요청' (A3 — 에이전트 루프 밖)."""
    require(c, "technician", "발주 승인 요청")
    return _transition(po_id, "pending", None, None)


@router.post("/{po_id}/approve")
def approve(po_id: str, body: ApproveBody | None = None, c: Caller = Depends(caller)) -> dict:
    """pending → approved. 팀장 전용 — 정비사가 부르면 403.

    FinAllQ 출금 요청 전송은 더 이상 여기서 하지 않는다 — 재무 승인(finance-approve)
    시점으로 이동했다(D119). 팀장 승인은 재무 승인 대기 상태로 넘기는 것뿐이다.
    """
    require(c, "manager", "발주 승인")
    return _transition(po_id, "approved", c.user_id, body.note if body else None)


@router.post("/{po_id}/reject")
def reject(po_id: str, body: RejectBody, c: Caller = Depends(caller)) -> dict:
    """pending → rejected. 사유 필수 (D38)."""
    require(c, "manager", "발주 반려")
    return _transition(po_id, "rejected", c.user_id, body.reason)


def _finance_transition_http(
    po_id: str, target: str, finance_decided_by: str, note: str | None
) -> dict:
    try:
        return svc._finance_transition(po_id, target, finance_decided_by, note)
    except KeyError as e:
        raise HTTPException(404, f"발주서를 찾을 수 없습니다: {po_id}") from e
    except svc.TransitionError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/{po_id}/finance-approve")
async def finance_approve(
    po_id: str, body: ApproveBody | None = None, c: Caller = Depends(caller)
) -> dict:
    """approved → finance_approved. 재무부 소속 manager 전용 (SoD, D119).
    승인 직후 FinAllQ에 출금 요청(A2A request-withdrawal, S5)을 보낸다 — approve()가
    갖던 자리에서 이동해 왔다. 전송 실패는 승인 자체를 되돌리지 않는다."""
    require(c, "manager", "자금집행 승인")
    if c.department != "finance":
        raise HTTPException(403, "자금집행 승인은 재무부 소속만 수행할 수 있습니다 (D119)")
    result = _finance_transition_http(
        po_id, "finance_approved", c.user_id, body.note if body else None
    )
    try:
        await svc.dispatch_a2a_withdrawal_request(po_id)
    except Exception:
        logger.exception("A2A request-withdrawal 전송 실패: po_id=%s", po_id)
    return result


@router.post("/{po_id}/finance-reject")
def finance_reject(po_id: str, body: RejectBody, c: Caller = Depends(caller)) -> dict:
    """approved → finance_rejected. 사유 필수 (D38). 재무부 소속 manager 전용 (D119)."""
    require(c, "manager", "자금집행 반려")
    if c.department != "finance":
        raise HTTPException(403, "자금집행 반려는 재무부 소속만 수행할 수 있습니다 (D119)")
    return _finance_transition_http(po_id, "finance_rejected", c.user_id, body.reason)
