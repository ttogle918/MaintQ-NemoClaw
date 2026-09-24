# -*- coding: utf-8 -*-
"""온보딩 승격·안전 문구 승인 REST — **사람 전용** (MQ-1909, D154·D156·D157).

새 기종(HV600 등) 스테이징 데이터(`05 §25~§29`)를 정본(`error_codes`·`manual_chunks`)으로
승격하는 **유일한 문**이다. MCP 온보딩 도구(`04 §23~§25`)는 스테이징 INSERT 만 하고,
상태 전이(`staged→approved/rejected`)·정본 쓰기는 전부 여기를 거친다(D10·D81 —
`routers/po.py`·`routers/decisions.py`·`routers/repairs.py` 와 같은 태도).

| 경로 | 역할 | 실패 |
|---|---|---|
| `GET /batches` · `GET /batches/{id}/groups` · `GET /safety` · `GET /status` | 제한 없음(읽기) | 404 / 422 |
| `POST /promote` | **manager** | 400 / 403 / 404 / 409 / 422 |
| `POST /rows/{row_id}/reject` | **manager** | 400 / 403 / 404 / 409 / 422 |
| `POST /safety/{cand_id}/approve` | **manager** | 400 / 403 / 404 / 409 / 422 |
| `POST /safety/{cand_id}/reject` | **manager** | 400 / 403 / 404 / 409 / 422 |

- 역할은 `deps.require()` 가 **role 만** 본다(D108). `X-User` 기본값 `tech-01` 은 technician
  이라 헤더 누락은 자연히 403 이다.
- 쓰기 주체(`c.user_id`)가 `users` 에 없으면 400 — `reviewed_by`·`approved_by`·`promoted_by`
  는 `users` FK 라 감사 기록이 비지 않게 앞단에서 막는다.
- 실패 본문은 `{"reason", "detail", ...extra}` (`routers/repairs.py::_conflict` 와 같은 모양).
- ⛔ 승격 취소·승인 취소 API 는 없다(범위 밖 — `TODO_직접할일.md` H10, 06 §2.11).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.db import connect
from backend.deps import Caller, caller, require
from backend.services import onboarding as svc

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


def _error(e: svc.OnboardingError) -> JSONResponse:
    return JSONResponse(
        status_code=e.http_status,
        content={"reason": e.reason, "detail": e.message, **e.extra},
    )


def _require_manager(c: Caller, action: str) -> None:
    """403(역할) → 400(미등록 사용자) 순. 역할 판정이 먼저라 헤더 누락은 항상 403 이다."""
    require(c, "manager", action)
    with connect() as con:
        known = con.execute("SELECT 1 FROM users WHERE user_id = ?", (c.user_id,)).fetchone()
    if not known:
        raise HTTPException(400, f"X-User {c.user_id!r} 는 등록된 사용자가 아닙니다")


# ── 요청 본문 ────────────────────────────────────────────────────────────────


class PromoteRow(BaseModel):
    row_id: int
    norm_id: int


class PromoteBody(BaseModel):
    model: str
    code: str
    primary_row_id: int
    rows: list[PromoteRow] = Field(..., min_length=1)
    acknowledged_flags: list[str] = []


class NoteBody(BaseModel):
    note: str


class SafetyApproveBody(BaseModel):
    approved_text: str
    # `object` 로 받는 이유: bool 로 받으면 pydantic 이 "true"·1 을 True 로 강제 변환한다.
    # 계약은 **`true` 그 자체**만 인정한다(`is not True` → 422, 06 §2.11).
    text_reviewed: object


# ── 읽기 ────────────────────────────────────────────────────────────────────


@router.get("/batches")
def list_batches() -> list[dict]:
    return svc.list_batches()


@router.get("/batches/{batch_id}/groups")
def list_groups(batch_id: int, state: str = Query("staged")) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content=svc.list_groups(batch_id, state))
    except svc.OnboardingError as e:
        return _error(e)


@router.get("/status")
def status(model: str = Query(...)) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content=svc.get_status(model))
    except svc.OnboardingError as e:
        return _error(e)


@router.get("/safety")
def list_safety(model: str = Query(...)) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content=svc.list_safety(model))
    except svc.OnboardingError as e:
        return _error(e)


# ── 쓰기 (manager 전용) ───────────────────────────────────────────────────────


@router.post("/promote")
def promote(body: PromoteBody, c: Caller = Depends(caller)) -> JSONResponse:
    _require_manager(c, "온보딩 승격")
    try:
        result = svc.promote(
            model=body.model,
            code=body.code,
            primary_row_id=body.primary_row_id,
            rows_in=[r.model_dump() for r in body.rows],
            acknowledged_flags=body.acknowledged_flags,
            promoted_by=c.user_id,
        )
    except svc.OnboardingError as e:
        return _error(e)
    return JSONResponse(status_code=201, content=result)


@router.post("/rows/{row_id}/reject")
def reject_row(row_id: int, body: NoteBody, c: Caller = Depends(caller)) -> JSONResponse:
    _require_manager(c, "온보딩 행 반려")
    try:
        result = svc.reject_row(row_id=row_id, note=body.note, reviewed_by=c.user_id)
    except svc.OnboardingError as e:
        return _error(e)
    return JSONResponse(status_code=200, content=result)


@router.post("/safety/{cand_id}/approve")
def approve_safety(
    cand_id: int, body: SafetyApproveBody, c: Caller = Depends(caller)
) -> JSONResponse:
    _require_manager(c, "안전 문구 승인")
    try:
        result = svc.approve_safety(
            cand_id=cand_id,
            approved_text=body.approved_text,
            text_reviewed=body.text_reviewed,
            approved_by=c.user_id,
        )
    except svc.OnboardingError as e:
        return _error(e)
    return JSONResponse(status_code=200, content=result)


@router.post("/safety/{cand_id}/reject")
def reject_safety(cand_id: int, body: NoteBody, c: Caller = Depends(caller)) -> JSONResponse:
    _require_manager(c, "안전 문구 반려")
    try:
        result = svc.reject_safety(cand_id=cand_id, note=body.note)
    except svc.OnboardingError as e:
        return _error(e)
    return JSONResponse(status_code=200, content=result)
