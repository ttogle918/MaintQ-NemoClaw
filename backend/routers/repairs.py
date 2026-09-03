# -*- coding: utf-8 -*-
"""수리 증빙 REST — 제출·서명·반려 (MQ-909, D85·D98).

**상태 전이 = 권한** (`routers/po.py`·`routers/decisions.py` 와 같은 태도). MCP 도구
(`create_repair_record`, §16)는 draft INSERT 만 하고(D10·D98), 전이는 전부 여기를 통한다.

| 경로 | 역할 | 실패 |
|---|---|---|
| `GET /api/repairs` · `GET /api/repairs/{id}` | 제한 없음(읽기) | 404 |
| `POST /{id}/submit` | **technician** | 403 / 404 / 409 |
| `POST /{id}/sign` | **manager** | 403 / 404 / 409 |
| `POST /{id}/reject` | **manager** | 403 / 404 / 409 / 422 |

**403 은 양방향이다** — 정비사가 `sign` 을 부르면 403, 팀장이 `submit` 을 부르면 403.
한쪽만 막으면 "권한 위반 차단 100%" 지표가 반쪽이 된다 (`routers/decisions.py` 주석과 같은 이유).

**409 본문은 `reason` 을 싣는다.** `invalid_transition` 과 `self_sign` 은 사용자가 할 일이
다르다(상태를 다시 확인 vs 다른 사람에게 서명을 요청). `sign` 의 409 `reason` 2종:
`invalid_transition` · `self_sign`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.deps import Caller, caller, require
from backend.services import repairs as svc

router = APIRouter(prefix="/api/repairs", tags=["repairs"])


#: 공유 계층(`data/repair_record.py`)의 실패 `reason` → HTTP. `routers/po.py` 와 같은 형태다.
#: ⛔ 여기 없는 reason 은 500 이다 — 모르는 실패를 4xx 로 반올림하지 않는다(사용자 잘못이
#:   아닌 것을 사용자 잘못처럼 보이게 하면 원인 추적이 끊긴다).
_REASON_HTTP: dict[str, int] = {
    "invalid_input": 422,
    "model_code_pair": 422,
    "invalid_model": 422,
    "integrity": 422,
}


def _status_code(result: dict) -> int:
    """성공(`get_repair()` 셰이프 — `status` 키 자체가 없다)도 200 으로 본다.
    `routers/po.py::_status_code` 와 같은 규약이다."""
    status = result.get("status")
    if status in (None, "ok"):
        return 200
    if status == "not_found":
        return 404
    return _REASON_HTTP.get(result.get("reason"), 500)


class RepairBody(BaseModel):
    """화면이 직접 생성·수정할 때 받는 9필드 (P39).

    ⛔ `expenditure_class`·`part_class`·서명 필드는 **여기 없다** — 서버가 산출하거나
    사람이 서명으로 채운다. D31 이 `unit_price` 를 입력에서 뺀 것과 같은 이유다:
    입력으로 받는 순간 사용자가 서버 계산을 덮어쓸 수 있고, 그러면 그 계산의 존재 이유가
    사라진다. 타입을 좁히지 않는 것도 의도다(D9) — 문자열 숫자도 공유 계층이 받아준다.
    """

    equipment_id: str = Field(..., min_length=1)
    work_type: str = Field(..., description="PLANNED | UNPLANNED (미기재 거부, 12 §7)")
    repair_scope: str = Field(..., description="폴백 금지 — enum 밖이면 422")
    cost: object = Field(..., description="0보다 큰 정수(원)")
    parts: list = Field(..., description="1건 이상. 각 항목 part_no 필수")
    downtime_hours: object | None = None
    model: str | None = None
    error_code: str | None = None
    note: str | None = None


@router.post("")
def create_repair(body: RepairBody, c: Caller = Depends(caller)) -> JSONResponse:
    """화면에서 수리 증빙 초안을 직접 생성한다 (P39). 정비사 전용.

    응답은 `GET /api/repairs/{id}` 와 같은 상세 셰이프다 — 화면이 생성 직후 바로 그릴 수
    있게 별도 조회 없이 준다(D111 의 `POST /api/po` 선례).
    """
    require(c, "technician", "수리 증빙 생성")
    result = svc.create(body.model_dump(), performed_by=c.user_id)
    return JSONResponse(status_code=_status_code(result), content=result)


@router.patch("/{repair_id}")
def update_repair(repair_id: str, body: RepairBody, c: Caller = Depends(caller)) -> JSONResponse:
    """draft 상태 수리 증빙을 수정한다. draft 가 아니면 409, 없으면 404. 정비사 전용."""
    require(c, "technician", "수리 증빙 수정")
    try:
        result = svc.update(repair_id, body.model_dump())
    except KeyError as e:
        raise HTTPException(404, f"수리 증빙을 찾을 수 없습니다: {repair_id}") from e
    except svc.NotEditableError as e:
        # 권한은 맞지만 상태가 틀린 경우 — 403 과 구분해서 409
        raise HTTPException(409, str(e)) from e
    return JSONResponse(status_code=_status_code(result), content=result)


class RejectBody(BaseModel):
    # 사유 없는 반려는 요청자가 뭘 고쳐야 할지 알 수 없다 (D38)
    reason: str = Field(min_length=1)


def _not_found(repair_id: str) -> HTTPException:
    return HTTPException(404, f"수리 증빙을 찾을 수 없습니다: {repair_id}")


def _conflict(reason: str, message: str, **extra) -> JSONResponse:
    """409 본문 규약 — `routers/decisions.py:_conflict` 와 같은 형태."""
    return JSONResponse(status_code=409, content={"reason": reason, "detail": message, **extra})


@router.get("")
def list_repairs(state: str | None = None, c: Caller = Depends(caller)) -> dict:
    """목록. 역할 무관 조회 — 정비사도 자기 요청 상태를 봐야 한다."""
    return {"items": svc.list_repairs(state)}


@router.get("/{repair_id}")
def get_repair(repair_id: str, c: Caller = Depends(caller)) -> dict:
    """상세. `hash_verified` 로 서명 해시 재계산 대조 결과를 싣는다(D84 태도)."""
    r = svc.get_repair(repair_id)
    if r is None:
        raise _not_found(repair_id)
    return r


@router.post("/{repair_id}/submit")
def submit(repair_id: str, c: Caller = Depends(caller)):
    """draft → pending. 정비사의 '팀장 서명 요청' (A3 — 에이전트 루프 밖)."""
    require(c, "technician", "수리 증빙 제출")
    try:
        return svc.submit(repair_id, requested_by=c.user_id)
    except KeyError as e:
        raise _not_found(repair_id) from e
    except svc.RepairTransitionError as e:
        return _conflict("invalid_transition", str(e), state=e.current)


@router.post("/{repair_id}/sign")
def sign(repair_id: str, c: Caller = Depends(caller)):
    """pending → signed. **팀장 전용.** 순서는 `services.repairs.sign()` 이 강제한다."""
    require(c, "manager", "수리 증빙 서명")
    try:
        return svc.sign(repair_id, verified_by=c.user_id)
    except KeyError as e:
        raise _not_found(repair_id) from e
    except svc.RepairTransitionError as e:
        return _conflict("invalid_transition", str(e), state=e.current)
    except svc.SelfSignError as e:
        return _conflict(svc.SelfSignError.reason, str(e))


@router.post("/{repair_id}/reject")
def reject(repair_id: str, body: RejectBody, c: Caller = Depends(caller)):
    """pending → rejected. 사유 필수 (D38 — 공백이면 pydantic 이 422)."""
    require(c, "manager", "수리 증빙 반려")
    try:
        return svc.reject(repair_id, verified_by=c.user_id, reason=body.reason)
    except KeyError as e:
        raise _not_found(repair_id) from e
    except svc.RepairTransitionError as e:
        return _conflict("invalid_transition", str(e), state=e.current)
