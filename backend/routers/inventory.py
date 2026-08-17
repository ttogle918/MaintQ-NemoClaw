# -*- coding: utf-8 -*-
"""재고 조회 REST 노출 (D73).

```
GET /api/inventory?part_no=...                    → search_inventory
GET /api/inventory?part_name=...&model=...         → search_inventory
```

역할 게이트를 두지 않는다 — 읽기 판정이라 403이 나오지 않는다(`maint_value.py` 5경로와
같은 이유). `core` 프로파일에서도 동작한다(MCP 프로세스를 거치지 않는다, D73).

**오류 매핑** — 도구 `status`/`reason` 을 재포장하지 않고 본문에 그대로 싣는다(`06 §2.6` 규약).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from backend.deps import Caller, caller
from backend.services import inventory as svc

router = APIRouter(prefix="/api", tags=["inventory"])

_REASON_HTTP: dict[str, int] = {
    "invalid_input": 422,
    "invalid_model": 422,
}


def _status_code(result: dict) -> int:
    status = result.get("status")
    if status == "ok":
        return 200
    if status == "not_found":
        return 404
    return _REASON_HTTP.get(result.get("reason"), 500)


@router.get("/inventory")
def get_inventory(
    part_no: str | None = None,
    part_name: str | None = None,
    model: str | None = None,
    c: Caller = Depends(caller),
) -> JSONResponse:
    """재고·안전재고·단종 여부 조회. `part_no` 또는 `part_name`(+선택 `model`) 중 하나 필요."""
    result = svc.search(part_no=part_no, part_name=part_name, model=model)
    return JSONResponse(status_code=_status_code(result), content=result)
