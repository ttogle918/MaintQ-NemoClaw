# -*- coding: utf-8 -*-
"""자산 조회 · 처분 사전판정 REST (S9 · `docs/11_ASSET_LIFECYCLE.md §3`).

**D71 — 판정 → HTTP 매핑**

| verdict | HTTP | 사용자가 할 일 |
|---|---|---|
| `BLOCKED` | 409 | 차단 사유를 해소하거나 override(서명·사유 필수) |
| `HOLD` | 409 | 경계 구간 — 전문가 검토 |
| `INSUFFICIENT_FACTS` | 409 | 누락된 사실을 입력 |
| `CONDITIONAL` · `CLEAR` | 200 | 체크리스트 이행 후 진행 |

`HOLD`·`INSUFFICIENT_FACTS` 를 200 으로 주지 않는 이유: **클라이언트는 200 을 "진행 가능"
으로 읽는다.** 그러면 D62("알 수 없다 ≠ 통과")가 API 경계에서 무너진다 — 엔진이 애써
구분해 둔 세 가지가 HTTP 한 칸에서 뭉개진다.

**역할 게이트를 두지 않는다.** `require()` 를 호출하지 않으므로 이 경로에서 403 은 나오지
않는다. 읽기 판정에 403 을 만들면 "권한 위반 403 차단 100%" 지표에 **법정 조건 미충족이
섞인다** — D38 이 403(권한)과 409(상태)를 나눈 바로 그 이유다.

**저장하지 않는다.** POST 지만 `decisions`·`flags` 를 건드리지 않는다. 그래서 경로가
`/disposal` 이 아니라 `/disposal/precheck` 다 — 저장하지 않는 POST 를 `/disposal` 로 부르면
계약이 거짓말이 된다.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from backend.deps import Caller, caller
from backend.services import disposal as svc

router = APIRouter(prefix="/api/assets", tags=["assets"])

# D71 매핑. 키 집합이 판정 어휘와 어긋나면 기동 시점에 터진다 — 새 verdict 가 생겼는데
# 매핑을 빠뜨리면 런타임 KeyError(500) 로 늦게 발견된다.
HTTP_BY_VERDICT: dict[str, int] = {
    "BLOCKED": 409,
    "HOLD": 409,
    "INSUFFICIENT_FACTS": 409,
    "CONDITIONAL": 200,
    "CLEAR": 200,
}
assert set(HTTP_BY_VERDICT) == set(svc.VERDICTS), (
    "D71 HTTP 매핑이 판정 어휘(D79)와 어긋났다 — engine.VERDICTS 를 단일 출처로 맞출 것"
)


class PrecheckBody(BaseModel):
    """`disposal_mode` 는 `engine.DISPOSAL_MODES` 가 단일 출처다 (폴백 금지)."""

    disposal_mode: str
    disposal_date: str | None = None

    @field_validator("disposal_mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        return svc.validate_disposal_mode(v)  # InvalidDisposalMode(ValueError) → 422

    @field_validator("disposal_date")
    @classmethod
    def _date(cls, v: str | None) -> str | None:
        # 판독 불가한 날짜를 통과시키면 `build_facts` 가 조용히 키를 빼고, 사용자는
        # 오타 때문에 INSUFFICIENT_FACTS 를 받은 것을 알 수 없다. 입력 오류는 입력에서 막는다.
        if v is not None:
            date.fromisoformat(v)
        return v


@router.get("")
def list_assets(
    line_id: int | None = None,
    status: str | None = None,
    c: Caller = Depends(caller),
) -> dict:
    """자산 목록. `line_id`·`status` 필터 (모르는 status 는 0건)."""
    return {"items": svc.list_assets(line_id, status)}


@router.get("/{asset_id}")
def get_asset(asset_id: str, c: Caller = Depends(caller)) -> dict:
    """자산 상세 + 하위 equipment 목록 (D68)."""
    asset = svc.get_asset(asset_id)
    if asset is None:
        raise HTTPException(404, f"자산을 찾을 수 없습니다: {asset_id}")
    return asset


@router.post("/{asset_id}/disposal/precheck")
def disposal_precheck(
    asset_id: str, body: PrecheckBody, c: Caller = Depends(caller)
) -> JSONResponse:
    """처분 사전판정 — **판정만 하고 아무것도 저장하지 않는다** (D71).

    `svc.precheck` 는 엔진 예외를 `RuleCatalogError` 로 흡수해 올려 준다. 여기서 500 으로
    흘리지 않는 이유: 룰 카탈로그가 안 실린 것은 서버 **설정** 문제이고, 클라이언트가 할
    행동(재시도·관리자 문의)이 일반 서버 오류와 다르다.
    """
    try:
        result = svc.precheck(
            asset_id,
            disposal_mode=body.disposal_mode,
            disposal_date=body.disposal_date,
        )
    except svc.AssetNotFound as e:
        raise HTTPException(404, f"자산을 찾을 수 없습니다: {asset_id}") from e
    except svc.InvalidDisposalMode as e:  # 본문 검증을 통과해도 서비스가 마지막으로 막는다
        raise HTTPException(422, str(e)) from e
    except svc.RuleCatalogError as e:
        raise HTTPException(503, {"reason": e.reason, "message": e.message}) from e

    status = HTTP_BY_VERDICT[result["verdict"]]
    if status == 409:
        # 409 본문은 200 과 **같은 형태 + `detail`** 이다 — 클라이언트가 차단 시에도
        # blockers/holds/insufficient/resolve_options 를 그대로 렌더할 수 있어야 한다.
        result = {**result, "detail": svc.precheck_detail(result)}
    return JSONResponse(status_code=status, content=result)
