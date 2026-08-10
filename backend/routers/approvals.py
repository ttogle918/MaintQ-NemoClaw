# -*- coding: utf-8 -*-
"""통합 승인 큐 REST (D85) — `GET /api/approvals`.

**읽기 전용이다.** 이 라우터에는 POST 가 없다 — 전이는 종류별 경로(`/api/po/*`,
`/api/decisions/*`)가 각자의 역할 게이트와 함께 수행한다. 통합 경로에 전이를 두면
`kind` 마다 다른 역할 규칙을 한 함수가 분기하게 되고, 그 분기가 곧 403 지표의 구멍이 된다.

역할 게이트 없음 — 목록 **조회**다. `/api/po` 도 조회에는 역할을 요구하지 않는다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.deps import Caller, caller
from backend.services import approvals as svc

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("")
def list_approvals(
    state: str | None = None,
    kind: str | None = None,
    c: Caller = Depends(caller),
) -> dict:
    """통합 큐. `kind` ∈ `("po","disposal","repair")` — **`repair` 는 현재 항상 0건**이다
    (Sprint 8 이 계약 변경 없이 채운다). `state` 는 각 종류의 **원 어휘** 그대로 필터한다."""
    try:
        items = svc.list_approvals(state=state, kind=kind)
    except svc.InvalidKind as e:
        raise HTTPException(422, str(e)) from e
    return {"items": items, "kinds": list(svc.KINDS)}
