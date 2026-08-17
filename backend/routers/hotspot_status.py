# -*- coding: utf-8 -*-
"""설비 하이라이트 상태 REST 노출 (spec §4-6, D73).

```
GET /api/assets/{asset_id}/hotspot-status
```

역할 게이트를 두지 않는다 — 읽기 판정이라 403이 나오지 않는다(`maint_value.py` 선례와
같은 이유). `core` 프로파일에서도 동작한다(MCP 프로세스를 거치지 않는다).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from backend.deps import Caller, caller
from backend.services import hotspot_status as svc

router = APIRouter(prefix="/api/assets", tags=["hotspot-status"])


def _status_code(result: dict) -> int:
    status = result.get("status")
    if status == "ok":
        return 200
    if status == "not_found":
        return 404
    return 500


@router.get("/{asset_id}/hotspot-status")
def get_hotspot_status(asset_id: str, c: Caller = Depends(caller)) -> JSONResponse:
    """부품별 하이라이트 색(red/blue/orange/null) + 근거. 자산에 연결된 인버터가 없으면 404."""
    result = svc.get(asset_id)
    return JSONResponse(status_code=_status_code(result), content=result)
