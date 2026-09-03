# -*- coding: utf-8 -*-
"""처분 결정 REST — 제출·서명·반려 (S10 계층 3 확정).

**상태 전이 = 권한** (`routers/po.py` 와 같은 태도). MCP 도구는 draft INSERT 만 하고(D10·D81),
전이는 전부 여기를 통한다.

| 경로 | 역할 | 실패 |
|---|---|---|
| `GET /api/decisions` · `GET /api/decisions/{id}` | 제한 없음(읽기) | 404 |
| `POST /{id}/submit` | **technician** | 403 / 404 / 409 |
| `POST /{id}/sign` | **manager** | 403 / 404 / 409 / 422 / 503 |
| `POST /{id}/reject` | **manager** | 403 / 404 / 409 / 422 |

**403 은 양방향이다** — 팀장이 `submit` 을 부르면 403, 정비사가 `sign` 을 부르면 403.
한쪽만 막으면 "권한 위반 차단 100%" 지표가 반쪽이 된다.

**⚠ `precheck` 에는 여전히 역할 게이트를 두지 않는다 (D71).** 읽기 판정과 확정 경로를
섞으면 403 지표에 *법정 조건 미충족*이 섞인다 — D38 이 403(권한)과 409(상태)를 나눈 이유다.

**409 본문은 `reason` 을 싣는다.** `evidence_changed` 와 `override_required` 는 사용자가
할 일이 완전히 다르다(근거 재확인 vs 사유 기재). HTTP 코드 하나로 뭉개면 프론트가
두 상황을 구분할 수 없다 — `precheck` 이 409 본문에 `verdict` 를 실은 것과 같은 규약이다.
`sign` 의 409 `reason` 5종: `invalid_transition` · `law_text_unavailable` ·
`cited_rule_missing`(인용 룰 소실 — 503 `rule_catalog_invalid` 와 다른 상태다) · `evidence_changed` · `override_required`.

**503 은 "재시도하라"는 말이다.** 그러니 재시도로 풀리는 것만 503 이다 — 카탈로그 **미적재**
(`rule_catalog_not_loaded`)가 그것이고, *판정이 인용한 룰만 사라진* 경우는 근거가 바뀐 것이라
409 다. 재시도해도 같은 답이 오는 상태에 503 을 주면 클라이언트를 영원히 돌게 만든다.

**⛔ `override_reason` 공백을 pydantic 으로 막지 않는 이유**: 본문 검증은 라우팅 직후라
서비스의 ①~④(404·409·evidence_changed·override_required)보다 **먼저** 실행된다. 그러면
없는 결정이나 근거가 바뀐 결정에 422 가 돌아가 D84 가 정한 순서가 깨진다.
그래서 검증은 `services.decisions.sign()` 의 ⑤ 자리에서 하고 여기서 422 로 매핑한다.
(DB CHECK 가 2차 방어선 — D63.)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.deps import Caller, caller, require
from backend.services import decisions as svc
from backend.services.disposal import RuleCatalogError

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


class DisposalDraftBody(BaseModel):
    """화면이 직접 생성·수정할 때 받는 4필드 (P39).

    ⛔ **`override`·`override_reason`·`reviewed_by` 는 여기 없다** (D81). 예외 적용은
    서명 화면 전용이고, 초안 생성·수정 경로가 그걸 받으면 D81 이 막으려던 우회가 그대로
    열린다. `verdict_at_signing`·`bundle_hash` 도 없다 — 서버가 **재판정으로** 산출한다.
    """

    asset_id: str = Field(..., min_length=1)
    disposal_mode: str = Field("SALE", description="SALE | SCRAP | TRANSFER 등 — 룰 입력")
    disposal_date: str | None = Field(None, description="YYYY-MM-DD. 룰 입력이라 판정을 바꾼다")
    reason: str = Field(..., min_length=1, description="처분 사유 (D5 — 대필 금지)")


def _draft_result(result: dict) -> JSONResponse:
    """성공(`get_decision()` 셰이프 — `status` 키가 없다)은 200. 실패는 reason 으로 매핑."""
    if result.get("status") == "error":
        code = 422 if result.get("reason") == "reason_required" else 500
        raise HTTPException(code, result.get("message") or result.get("reason") or "실패")
    return JSONResponse(status_code=200, content=result)


@router.post("")
def create_decision(body: DisposalDraftBody, c: Caller = Depends(caller)) -> JSONResponse:
    """화면에서 처분 초안을 직접 생성한다 (P39). 정비사 전용.

    ⛔ **BLOCKED 여도 생성한다** (D63) — 차단 사실이 초안에 기록된 채 결재에 올라간다.
    막는 것은 서명이지 초안 생성이 아니다.
    """
    require(c, "technician", "처분 초안 생성")
    try:
        result = svc.create(
            asset_id=body.asset_id,
            disposal_mode=body.disposal_mode,
            disposal_date=body.disposal_date,
            reason=body.reason,
            requested_by=c.user_id,
        )
    except KeyError as e:
        raise HTTPException(404, f"자산을 찾을 수 없습니다: {body.asset_id}") from e
    except svc.CitedRuleMissing as e:
        raise HTTPException(409, str(e)) from e
    except RuleCatalogError as e:
        # 룰 카탈로그 미적재 — 판정할 근거가 없다 (D71, precheck 와 같은 게이트)
        raise HTTPException(503, str(e)) from e
    return _draft_result(result)


@router.patch("/{decision_id}")
def update_decision(
    decision_id: str, body: DisposalDraftBody, c: Caller = Depends(caller)
) -> JSONResponse:
    """draft 상태 처분 초안을 수정한다. draft 가 아니면 409, 없으면 404. 정비사 전용.

    🔴 수정은 **재판정**을 부른다 — `disposal_mode`·`disposal_date` 가 룰 입력이라
    `evidence_bundle`·`bundle_hash`·`verdict_at_signing` 이 함께 바뀐다. 서명 시점의
    재대조(D84)는 그대로 살아 있으므로 이 갱신이 서명 게이트를 약화시키지 않는다.
    """
    require(c, "technician", "처분 초안 수정")
    try:
        result = svc.update(
            decision_id,
            asset_id=body.asset_id,
            disposal_mode=body.disposal_mode,
            disposal_date=body.disposal_date,
            reason=body.reason,
        )
    except svc.NotEditableError as e:
        raise HTTPException(409, str(e)) from e
    except KeyError as e:
        # 결정이 없거나(_locked_row) 자산이 없다(rebuild_bundle) — 둘 다 404 다
        raise HTTPException(404, f"찾을 수 없습니다: {e}") from e
    except svc.CitedRuleMissing as e:
        raise HTTPException(409, str(e)) from e
    except RuleCatalogError as e:
        raise HTTPException(503, str(e)) from e
    return _draft_result(result)


class SignBody(BaseModel):
    """서명 본문. `override` 는 **사람만** 넣을 수 있다 — 도구 스키마에는 이 키가 없다(D81)."""

    override: bool = False
    override_reason: str | None = None
    note: str | None = None


class RejectBody(BaseModel):
    # 사유 없는 반려는 요청자가 뭘 고쳐야 할지 알 수 없다 (D38)
    reason: str = Field(min_length=1)


def _not_found(decision_id: str) -> HTTPException:
    return HTTPException(404, f"처분 결정을 찾을 수 없습니다: {decision_id}")


def _conflict(reason: str, message: str, **extra) -> JSONResponse:
    """409 본문 규약 — `reason` 으로 원인을 구분하고 필요한 재료를 함께 싣는다."""
    return JSONResponse(status_code=409, content={"reason": reason, "detail": message, **extra})


@router.get("")
def list_decisions(state: str | None = None, c: Caller = Depends(caller)) -> dict:
    """목록. 역할 무관 조회 — 정비사도 자기 요청 상태를 봐야 한다."""
    return {"items": svc.list_decisions(state)}


@router.get("/{decision_id}")
def get_decision(decision_id: str, c: Caller = Depends(caller)) -> dict:
    """상세 + 렌더된 문서·증빙 패키지 (D86 — 저장하지 않고 조립 시점 계산)."""
    try:
        d = svc.get_decision(decision_id)
    except RuntimeError as e:
        # `svc._metrics()` 의 위임 호출 실패(불변식 위반) — 조용히 삼키지 않고 구조화된
        # 500 으로 닫는다 (MQ-908 이후 새로 생긴 실패 경로, 종전엔 이 함수가 실패하지 않았다).
        raise HTTPException(500, {"reason": "metrics_assembly_failed", "message": str(e)}) from e
    if d is None:
        raise _not_found(decision_id)
    return d


@router.post("/{decision_id}/submit")
def submit(decision_id: str, c: Caller = Depends(caller)):
    """draft → pending. 정비사의 '팀장 승인 요청' (A3 — 에이전트 루프 밖)."""
    require(c, "technician", "처분 승인 요청")
    try:
        return svc.submit(decision_id, requested_by=c.user_id)
    except KeyError as e:
        raise _not_found(decision_id) from e
    except svc.DecisionTransitionError as e:
        return _conflict("invalid_transition", str(e), state=e.current)
    except RuntimeError as e:
        raise HTTPException(500, {"reason": "metrics_assembly_failed", "message": str(e)}) from e


@router.post("/{decision_id}/sign")
def sign(decision_id: str, body: SignBody | None = None, c: Caller = Depends(caller)):
    """pending → signed. **팀장 전용.** 순서는 `services.decisions.sign()` 이 강제한다 (D84)."""
    require(c, "manager", "처분 서명")
    b = body or SignBody()
    try:
        return svc.sign(
            decision_id,
            reviewed_by=c.user_id,
            override=b.override,
            override_reason=b.override_reason,
            note=b.note,
        )
    except KeyError as e:
        raise _not_found(decision_id) from e
    except svc.DecisionTransitionError as e:
        return _conflict("invalid_transition", str(e), state=e.current)
    except svc.LawTextUnavailable as e:
        # `evidence_changed` 로 뭉개지 않는다 — 원인을 정확히 말한다
        return _conflict("law_text_unavailable", str(e), missing_law_refs=e.missing)
    except svc.CitedRuleMissing as e:
        # **503 이 아니다.** 카탈로그는 적재돼 있고 *판정이 인용한 룰만* 사라진 상태 —
        # 재시도로 풀리지 않고 사람의 재검토가 필요하다. `law_text_unavailable` 을
        # `evidence_changed` 에서 분리한 것과 같은 논리 (적재 미완 0행은 아래 503 에 남는다).
        return _conflict(e.reason, str(e), missing_rules=e.missing)
    except svc.EvidenceChanged as e:
        return _conflict(
            "evidence_changed", str(e), bundle_hash=e.stored, recomputed_hash=e.recomputed
        )
    except svc.OverrideRequired as e:
        # S4 태도 — "안 된다"로 끝내지 않고 무엇이 막고 있고 무엇을 하면 풀리는지 함께 준다
        j = e.judgment
        return _conflict(
            "override_required",
            str(e),
            verdict=e.verdict,
            blockers=j.get("blockers") or [],
            holds=j.get("holds") or [],
            insufficient=j.get("insufficient") or [],
            resolve_options=sorted(
                {
                    opt
                    for bucket in ("blockers", "holds", "insufficient", "preconditions")
                    for f in (j.get(bucket) or [])
                    for opt in (f.get("resolve_options") or [])
                }
            ),
        )
    except svc.OverrideReasonRequired as e:
        raise HTTPException(422, str(e)) from e
    except RuleCatalogError as e:
        # 룰 카탈로그가 **적재되지 않았거나 무결성이 깨진** 상태 — 요청 결함이 아니고
        # 재시도·관리자 문의가 맞는 행동이다 (precheck 과 동일, D71).
        # ⚠ *인용 룰 소실*은 여기 오지 않는다 — 위 `CitedRuleMissing` 이 409 로 먼저 잡는다.
        raise HTTPException(503, {"reason": e.reason, "message": e.message}) from e
    except RuntimeError as e:
        raise HTTPException(500, {"reason": "metrics_assembly_failed", "message": str(e)}) from e


@router.post("/{decision_id}/reject")
def reject(decision_id: str, body: RejectBody, c: Caller = Depends(caller)):
    """pending → rejected. 사유 필수 (D38 — 공백이면 pydantic 이 422)."""
    require(c, "manager", "처분 반려")
    try:
        return svc.reject(decision_id, reviewed_by=c.user_id, reason=body.reason)
    except KeyError as e:
        raise _not_found(decision_id) from e
    except svc.DecisionTransitionError as e:
        return _conflict("invalid_transition", str(e), state=e.current)
    except RuntimeError as e:
        raise HTTPException(500, {"reason": "metrics_assembly_failed", "message": str(e)}) from e
