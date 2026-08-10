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
from backend.services import ownership as own_svc

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

# ── 실사 판정(S18) → HTTP. **`04 §9` status 3종이 그대로 매핑된다.**
#
# ⛔ `PARTIAL` 을 409 로 만들지 않는다. 처분 사전판정(D71)의 409 는 *"지금 상태로는 진행할
#    수 없다"* 는 뜻인데, 실사 `PARTIAL` 은 **정상 결과**다 — "미확인 항목이 남았다"는 것이
#    이 판정이 낼 수 있는 가장 좋은 답이고(`11 §6`: PARTIAL 은 승격 불가), 애초에 전 항목
#    VERIFIED 는 구조적으로 도달할 수 없다. 이걸 409 로 주면 D71 이 처분 판정에 부여한
#    "409 = 사용자가 해소해야 할 상태"라는 의미가 흐려지고, 클라이언트는 해소할 수 없는
#    것을 해소하라고 안내하게 된다. 회귀 `spikes/ownership_api_contract.py` 가 명시 검사한다.
#
# `not_found` 는 404 이되 **본문에 reason 과 사유를 싣는다** — 특히 `no_host_asset`
# (분전반 `INV-L1-01`)은 "문제 없음"이 아니라 "실사 대상이 아니다"라는 판정 결과다.
HTTP_BY_OWNERSHIP_STATUS: dict[str, int] = {"ok": 200, "not_found": 404, "error": 500}
assert set(HTTP_BY_OWNERSHIP_STATUS) == set(own_svc.STATUSES), (
    "실사 판정 HTTP 매핑이 `04 §9` status 어휘와 어긋났다 — data.ownership.STATUSES 가 단일 출처"
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


@router.get("/{asset_id}/ownership")
def get_ownership(asset_id: str, c: Caller = Depends(caller)) -> JSONResponse:
    """중고 거래 실사 체크리스트 9개 카테고리 판정 (S18 · `11 §6`).

    **판정은 MCP 도구와 같은 함수에서 나온다** (`data/ownership.py`) — 채팅으로 물었을 때와
    화면으로 봤을 때 결과가 달라지지 않는다. 응답 본문도 도구 출력 그대로다.

    **역할 게이트를 두지 않는다** — `require()` 를 호출하지 않으므로 이 경로에서 403 은
    나오지 않는다. `/disposal/precheck` 와 같은 이유다(D38): 읽기 판정에 403 을 만들면
    "권한 위반 403 차단 100%" 지표에 권한과 무관한 것이 섞인다.

    **저장하지 않는다.** `mode=ro` 커넥션만 쓴다.

    경로 식별자는 자산·설비 **어느 쪽이든** 받는다 — 등록부 조회로 판별한다
    (`services/ownership.verify_ref`). 설비에 호스트 자산이 없으면 404 `no_host_asset` 이고,
    그건 "확인 결과 문제 없음"이 아니라 "실사 대상이 아니다"라는 뜻이다.
    """
    result = own_svc.verify_ref(asset_id)
    return JSONResponse(status_code=HTTP_BY_OWNERSHIP_STATUS[result["status"]], content=result)


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
