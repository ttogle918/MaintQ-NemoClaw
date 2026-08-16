# -*- coding: utf-8 -*-
"""보전지표·부품 등급·지출 판정·수리가치 판단·근거 번들 REST 노출 5종 (MQ-908, D73·D101).

```
GET  /api/assets/{asset_id}/metrics?window_months=12          → get_maintenance_metrics
POST /api/equipment/{equipment_id}/repair-value                → assess_repair_value   (무저장)
GET  /api/parts/{part_no}/criticality                          → classify_part_criticality
POST /api/expenditure/classify                                 → classify_expenditure  (무저장)
GET  /api/assets/{asset_id}/evidence-bundle                    → build_evidence_bundle 상당
```

**앞의 넷은 `services/maint_value.py` 를 거쳐 `data.maint_value` 를 호출한다** — 도구 서버
패키지를 import 하지 않는다(D15). **다섯 번째(근거 번들)는 옮기지 않는다** — `services/decisions.
rebuild_bundle()` 이 `build_evidence_bundle` 도구의 조립을 이미 그대로 재현하므로(D84 경로)
여기서는 그것을 부르고 형태를 맞춰 응답한다. 세 번째 사본을 만들지 않는다.

**역할 게이트를 두지 않는다.** 전부 읽기 판정이다 — `require()` 를 부르지 않으므로 이 경로
에서 403 은 나오지 않는다(`/disposal/precheck`·`/assets/{id}/ownership` 와 같은 이유, D38·D71).

**아무것도 저장하지 않는다.** `POST` 두 개는 입력이 본문이라 POST 일 뿐이다.

**오류 매핑** — 도구 `status`/`reason` 을 재포장하지 않고 본문에 그대로 싣는다(`06 §2.6` 규약):

| `status`/`reason` | HTTP |
|---|---|
| `status="ok"` | 200 |
| `status="not_found"` (`unknown_asset`·`unknown_equipment`·`unknown_part`·`no_host_asset`) | 404 |
| `reason="invalid_input"` | 422 |
| `reason="rule_catalog_not_loaded"` | 503 (재시도로 풀리는 것만 503) |
| `reason="law_text_unavailable"` | 409 (재시도해도 같은 답) |
| 그 밖 `status="error"` | 500 |

**`core` 프로파일(D69 기본값)에서도 5경로 전부 200(또는 정의된 4xx)이다** (D73 — 이게 이
모듈의 핵심 DoD). 앞의 넷은 애초에 MCP 프로세스를 거치지 않고, 다섯 번째도 `data.rules.
engine` 을 직접 쓰는 `rebuild_bundle` 을 거치므로 도구 등록 여부와 무관하다.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.deps import Caller, caller
from backend.services import decisions as decisions_svc
from backend.services import maint_value as svc
from backend.services.disposal import (
    InvalidDisposalMode,
    RuleCatalogError,
    read_only,
    validate_disposal_mode,
)

router = APIRouter(prefix="/api", tags=["maint-value"])

# `status`/`reason` → HTTP. 순서가 아니라 **집합**이 계약이다 — `status` 를 먼저 보고,
# 그다음 `reason` 을 본다. 목록 밖 `reason` 은 전부 500(그 밖 오류).
_REASON_HTTP: dict[str, int] = {
    "invalid_input": 422,
    "rule_catalog_not_loaded": 503,
    "law_text_unavailable": 409,
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


@router.get("/assets/{asset_id}/metrics")
def get_metrics(
    asset_id: str, window_months: int | None = None, c: Caller = Depends(caller)
) -> JSONResponse:
    """자산 보전지표(MTBF·MTTR·가용도·예방보전 비율·누적 수리비·반복 고장 여부).

    `window_months` 를 생략하면 도구 기본값(24개월)이 적용된다. 지표가 전부 `null` 인
    자산도 200 이다 — "데이터 부족"은 실패가 아니다(D62).
    """
    kwargs = {} if window_months is None else {"window_months": window_months}
    return _respond(svc.metrics(asset_id=asset_id, **kwargs))


class RepairValueBody(BaseModel):
    failed_part: str
    repair_cost: int
    repair_scope: str | None = None


@router.post("/equipment/{equipment_id}/repair-value")
def post_repair_value(
    equipment_id: str, body: RepairValueBody, c: Caller = Depends(caller)
) -> JSONResponse:
    """수리 / 교체 / 현상매각 3지 판단. **무저장** — 입력이 본문이라 POST 일 뿐이다.

    `verdict="ROOT_CAUSE_FIRST"` 면 반복 고장이 우선이라 `alternatives` 가 빈 배열이다(D2).
    """
    kwargs = {} if body.repair_scope is None else {"repair_scope": body.repair_scope}
    return _respond(
        svc.repair_value(
            equipment_id=equipment_id,
            failed_part=body.failed_part,
            repair_cost=body.repair_cost,
            **kwargs,
        )
    )


@router.get("/parts/{part_no}/criticality")
def get_part_criticality(part_no: str, c: Caller = Depends(caller)) -> JSONResponse:
    """`parts.part_class` 조회. 등급 미등록·비정상 값은 추정하지 않는다(D12)."""
    return _respond(svc.part_criticality(part_no=part_no))


class ExpenditureBody(BaseModel):
    part_no: str | None = None
    part_class: str | None = None
    repair_scope: str
    amount: int


@router.post("/expenditure/classify")
def post_expenditure(body: ExpenditureBody, c: Caller = Depends(caller)) -> JSONResponse:
    """지출을 CAPITAL | REVENUE | HOLD 로 분류한다. **무저장.**

    `part_no`·`part_class` 는 either-or 다 — 둘 다 오면 422. `part_no` 만 오면 서버가
    `classify_part_criticality` 로 등급을 채운다. `HOLD` 는 실패가 아니라 판정이므로 200.
    """
    return _respond(
        svc.expenditure(
            part_no=body.part_no,
            part_class=body.part_class,
            repair_scope=body.repair_scope,
            amount=body.amount,
        )
    )


# ── 5번째: 근거 번들 — `services/decisions.rebuild_bundle` 을 그대로 부른다 (옮기지 않는다) ──

# 도구 서버의 `tools/build_evidence_bundle.py:HASH_SPEC`·`:_DISCLAIMER` 와 **동일 문자열**이다.
# 두 프로세스가 이 상수를 공유할 import 경로가 없다(D15) — `services/decisions.py` 가 이미
# 같은 이유로 번들 조립 규약을 한 벌 더 갖고 있는 것과 같은 태도다.
_HASH_SPEC = "sha256/nfkc-ws/canonical-json-v1"
_EVIDENCE_BUNDLE_DISCLAIMER = (
    "이 번들은 판정 시점의 근거 스냅샷이며 판정 자체가 아니다. bundle_hash 는 evidence_bundle "
    "다섯 항목(laws·rules·evaluated·contracts·facts)만을 대상으로 하며 built_at·hash_spec 은 "
    "포함하지 않는다(같은 사실은 언제 조립해도 같은 해시). "
    "변조 없음의 기준은 바이트 동일이 아니라 NFKC + 공백 정규화 후 동일이다 — 전각/반각·"
    "연속 공백 차이는 같은 근거로 본다(hash_spec 참조). "
    "contracts 항목은 원문 원천이 저장소에 없어 해시로 고정되지 않는다(hash_fixed=false). "
    "처분 확정은 사람의 서명으로만 이뤄지고, 시스템 판정과 다른 결정은 사유 기재와 함께 기록된다."
)


@router.get("/assets/{asset_id}/evidence-bundle")
def get_evidence_bundle(
    asset_id: str,
    disposal_mode: str = "SALE",
    disposal_date: str | None = None,
    c: Caller = Depends(caller),
) -> JSONResponse:
    """처분 판정의 근거를 묶고 해시로 고정한다 — `build_evidence_bundle` 상당 (D84 경로).

    **아무것도 저장하지 않는다.** `services/decisions.rebuild_bundle()` 을 그대로 부른다 —
    그 함수는 `decisions.sign()` 이 서명 시점 재산출에 쓰는 것과 **같은 조립**이다. 세 번째
    사본을 만들지 않는다.
    """
    try:
        mode = validate_disposal_mode(disposal_mode)
    except InvalidDisposalMode as e:
        raise HTTPException(422, str(e)) from e
    if disposal_date is not None:
        try:
            date.fromisoformat(disposal_date)
        except ValueError as e:
            raise HTTPException(
                422, f"disposal_date 는 ISO-8601 날짜입니다: {disposal_date!r}"
            ) from e

    try:
        with read_only() as con:
            bundle, bundle_hash, judgment = decisions_svc.rebuild_bundle(
                con, asset_id, mode, disposal_date
            )
    except KeyError as e:
        raise HTTPException(404, f"자산을 찾을 수 없습니다: {asset_id}") from e
    except decisions_svc.LawTextUnavailable as e:
        return JSONResponse(
            status_code=409,
            content={
                "reason": "law_text_unavailable",
                "detail": str(e),
                "missing_law_refs": e.missing,
            },
        )
    except decisions_svc.CitedRuleMissing as e:
        # 카탈로그는 적재돼 있고 판정이 인용한 룰만 사라진 상태 — 503(재시도)이 아니다.
        return JSONResponse(
            status_code=409,
            content={"reason": e.reason, "detail": str(e), "missing_rules": e.missing},
        )
    except RuleCatalogError as e:
        raise HTTPException(503, {"reason": e.reason, "message": e.message}) from e

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "asset_id": asset_id,
            "evidence_bundle": bundle,
            "bundle_hash": bundle_hash,
            "hash_spec": _HASH_SPEC,
            "verdict": judgment["verdict"],
            "not_considered": judgment["not_considered"],
            "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "disclaimer": _EVIDENCE_BUNDLE_DISCLAIMER,
        },
    )
