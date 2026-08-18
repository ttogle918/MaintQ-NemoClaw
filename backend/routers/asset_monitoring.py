# -*- coding: utf-8 -*-
"""기한 추적 · 위험등급 REST 노출 (MQ-1105, D73·D101).

```
GET /api/deadlines?asset_id=&window_days=            → track_deadlines 상당
GET /api/buildings/{building_id}/risk-grade          → assess_risk_grade 상당
GET /api/assets/{asset_id}/risk-grade                → assess_risk_grade 상당 (asset_id 해석 편의)
```

**`services/asset_monitoring.py` 를 거쳐 `data.deadlines`/`data.risk_grade` 를 호출한다** —
도구 서버 패키지를 import 하지 않는다(D15).

**역할 게이트를 두지 않는다.** 둘 다 읽기 판정이다 — `require()` 를 부르지 않으므로 이
경로에서 403 은 나오지 않는다(`/disposal/precheck`·`maint_value.py` 와 같은 이유, D38·D71).

**아무것도 저장하지 않는다.**

**오류 매핑** — 도구 `status`/`reason` 을 재포장하지 않고 본문에 그대로 싣는다:

| `status`/`reason` | HTTP |
|---|---|
| `status="ok"` | 200 |
| `status="not_found"` (`unknown_asset`·`unknown_building`·`no_building`) | 404 |
| `reason="invalid_input"` | 422 |
| 그 밖 `status="error"` (`db_missing`·`db_error`·`internal_error`·`rule_catalog_not_loaded` 등) | 500 |

`window_days` 를 쿼리 문자열로 잘못 보내(예: 숫자가 아닌 값) FastAPI 타입 검증에서 걸리면
**이 표와 무관하게** FastAPI 가 자체적으로 422 를 낸다 — 그건 이 라우터 도달 전 단계이고,
표의 `invalid_input` 은 타입은 맞았지만 값이 부적절한 경우(음수 등)를 두 데이터 모듈이
판정한 결과다. 두 층위를 섞지 않는다.

**`core` 프로파일(D69 기본값)에서도 두 경로 전부 200(또는 정의된 4xx)이다** (D73 — 이게 이
모듈의 핵심 DoD). MCP 프로세스를 애초에 거치지 않으므로 도구 등록 여부와 무관하다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from backend.deps import Caller, caller
from backend.services import asset_monitoring as svc

router = APIRouter(prefix="/api", tags=["asset-monitoring"])

# `status`/`reason` → HTTP. `status` 를 먼저 보고, 그다음 `reason` 을 본다.
# 목록 밖 `reason` 은 전부 500(그 밖 오류).
_REASON_HTTP: dict[str, int] = {
    "invalid_input": 422,
}


def _status_code(result: dict) -> int:
    status = result.get("status")
    if status == "ok":
        return 200
    if status == "not_found":
        return 404
    return _REASON_HTTP.get(result.get("reason"), 500)


def _respond(result: dict) -> JSONResponse:
    return JSONResponse(status_code=_status_code(result), content=result)


@router.get("/deadlines")
def get_deadlines(
    asset_id: str | None = None,
    window_days: int | None = None,
    c: Caller = Depends(caller),
) -> JSONResponse:
    """법정 기한(투자세액공제 사후관리·안전검사) 사전 경보. 0건도 200이다 — 실패가 아니다(D62).

    `window_days` 를 생략하면 도구 기본값(180일)이 적용된다.
    """
    kwargs: dict = {} if window_days is None else {"window_days": window_days}
    if asset_id is not None:
        kwargs["asset_id"] = asset_id
    return _respond(svc.deadlines(**kwargs))


@router.get("/buildings/{building_id}/risk-grade")
def get_building_risk_grade(building_id: str, c: Caller = Depends(caller)) -> JSONResponse:
    """건물 단위 위험등급 산출. 3속성 중 하나라도 미확인이면 `current_grade` 는 null(D62)."""
    return _respond(svc.risk_grade(building_id=building_id))


@router.get("/assets/{asset_id}/risk-grade")
def get_asset_risk_grade(asset_id: str, c: Caller = Depends(caller)) -> JSONResponse:
    """`assets.building_id` 로 해석한 뒤 건물 단위 위험등급을 산출한다(조회 편의)."""
    return _respond(svc.risk_grade(asset_id=asset_id))
