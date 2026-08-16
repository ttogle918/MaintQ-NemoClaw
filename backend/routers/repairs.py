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
