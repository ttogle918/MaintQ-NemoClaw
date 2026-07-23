# -*- coding: utf-8 -*-
"""발주 승인 워크플로우 (docs/06_REPO_API.md §2.2).

**상태 전이 = 권한.** MCP 도구는 draft 생성만 하고(D10), 전이는 전부 여기를 통한다.
정비사가 approve 를 호출하면 403 — 평가 지표(권한 위반 차단 100%)의 대상이다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.deps import Caller, caller, require
from backend.services import po as svc

router = APIRouter(prefix="/api/po", tags=["po"])


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
    """pending → approved. 팀장 전용 — 정비사가 부르면 403."""
    require(c, "manager", "발주 승인")
    return _transition(po_id, "approved", c.user_id, body.note if body else None)


@router.post("/{po_id}/reject")
def reject(po_id: str, body: RejectBody, c: Caller = Depends(caller)) -> dict:
    """pending → rejected. 사유 필수 (D38)."""
    require(c, "manager", "발주 반려")
    return _transition(po_id, "rejected", c.user_id, body.reason)
