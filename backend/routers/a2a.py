# -*- coding: utf-8 -*-
"""MaintQ A2A 크로스도메인 호출 라우터.

화면 또는 시스템에서 A2A 협력사(InsuQ, FinAllQ)로 나가는 조회형/상담형 요청을 중계한다.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.a2a.client import (
    A2ACircuitOpenError,
    A2AClientError,
    A2APolicyBlockedError,
    A2ATimeoutError,
    A2AUpstreamUnavailableError,
    call_skill,
)
from backend.a2a.payloads import (
    idempotency_key_for_asset_change,
    build_assess_loan_payload,
    build_assess_used_equipment_loan_payload,
    build_lookup_clause_payload,
    build_notify_asset_change_payload,
    build_request_settlement_payload,
)
from backend.a2a.trace import record_a2a_trace
from backend.services.a2a_history import list_a2a_history
from backend.services.lien import resolve_lien_consent

router = APIRouter(prefix="/api/a2a", tags=["a2a"])
logger = logging.getLogger(__name__)

#: D149 — 샌드박스 정책상 발신을 시도조차 하지 않았을 때의 안내문. 세 발신 경로가 공유한다.
_POLICY_BLOCKED_MESSAGE = "샌드박스 정책상 외부 A2A 발신이 차단돼 시도하지 않았습니다 (D149)"


async def _dispatch(
    *,
    skill_id: str,
    payload: dict[str, Any],
    chain_id: str,
    session_id: str,
    base_url: str,
    partner_label: str,
    partner: str = "finallq",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """A2A 발신 + trace 기록 + 오류 매핑. 스킬마다 같은 블록을 복제하지 않는다.

    상태코드 매핑은 기존 `lookup-clause`·`assess-loan` 과 동일하다:
    timeout→504 · unavailable→502 · client error→그쪽 status(없으면 400).

    ⛔ **기존 두 엔드포인트를 이 헬퍼로 바꾸지 않았다** — 동작하는 코드를 함께
    건드리면 회귀 위험만 커진다. 신규 2종(S12·S13)만 쓴다. 기존 것 정리는 별건이다.
    """

    def _trace(status: str, response: dict[str, Any]) -> None:
        record_a2a_trace(
            session_id=session_id,
            skill_id=skill_id,
            request_payload=payload,
            response_payload=response,
            request_chain_id=chain_id,
            status=status,
        )

    try:
        res = await call_skill(
            partner=partner,
            skill_id=skill_id,
            payload=payload,
            request_chain_id=chain_id,
            base_url=base_url,
            idempotency_key=idempotency_key,
        )
        # 파트너가 echo 안 해도 상관관계 키를 보장한다 (기존 두 엔드포인트와 같은 태도)
        res["request_chain_id"] = chain_id
        _trace("ok", res)
        return res
    except A2APolicyBlockedError as exc:
        # ⚠ A2ACircuitOpenError·A2AUpstreamUnavailableError 보다 **먼저** 잡는다 — 정책
        #   차단은 상대 장애가 아니다 (D149).
        _trace("policy_blocked", {"error": str(exc)})
        raise HTTPException(
            status_code=503,
            detail={"reason": "policy_blocked", "message": _POLICY_BLOCKED_MESSAGE},
        ) from exc
    except A2ATimeoutError as exc:
        _trace("timeout", {"error": str(exc)})
        raise HTTPException(
            status_code=504, detail=f"{partner_label} A2A adapter timeout"
        ) from exc
    except A2ACircuitOpenError as exc:
        # ⚠ 반드시 A2AUpstreamUnavailableError 보다 **먼저** 잡는다 (하위 타입이다).
        _trace("circuit_open", {"error": str(exc)})
        raise HTTPException(
            status_code=503,
            detail=f"{partner_label} A2A 차단기가 열려 있습니다 (연속 실패 {exc.failure_count}회)",
            headers={"Retry-After": str(max(1, int(exc.retry_after)))},
        ) from exc
    except A2AUpstreamUnavailableError as exc:
        _trace("unavailable", {"error": str(exc)})
        raise HTTPException(
            status_code=502, detail=f"{partner_label} A2A adapter unavailable"
        ) from exc
    except A2AClientError as exc:
        _trace("error", {"error": str(exc)})
        raise HTTPException(
            status_code=exc.status_code or 400, detail=exc.detail or str(exc)
        ) from exc


class LookupClauseRequest(BaseModel):
    question: str = Field(..., min_length=1, description="약관 관련 질의 문장")
    session_id: str | None = Field(None, description="MaintQ 세션 ID")
    request_chain_id: str | None = Field(None, description="멀티홉 추적용 체인 ID")


@router.post("/lookup-clause")
async def lookup_clause_endpoint(req: LookupClauseRequest) -> dict[str, Any]:
    """InsuQ A2A lookup-clause 스킬을 호출해 약관 근거와 답변을 조회한다."""
    # InsuQ 가 lookup-clause 를 FastAPI 어댑터(:9102)에서 Spring backend(:8081) 로
    # 이관하면서 `a2a_adapter/` 와 compose 서비스 정의를 지웠다 — **:9102 는 이제
    # 존재하지 않는다**(2026-08-30). 경로·헤더 규격은 그대로라 바뀌는 건 포트뿐이다.
    base_url = os.environ.get("MAINTQ_A2A_INSUQ_BASE_URL") or "http://localhost:8081"
    chain_id = req.request_chain_id or f"CHAIN-CLAUSE-{uuid.uuid4().hex[:8]}"

    payload = build_lookup_clause_payload(question=req.question, request_chain_id=chain_id)

    try:
        res = await call_skill(
            partner="insuq",
            skill_id="lookup-clause",
            payload=payload,
            request_chain_id=chain_id,
            base_url=base_url,
            # InsuQ RAG 파이프라인 실측 응답 시간이 ~11초라 기본 10초보다 길다(2026-08-24 리허설 확인,
            # curl 직결 시 11.302s) — 다른 두 스킬(request-withdrawal·assess-loan)은 기본값으로 충분해
            # 여기만 늘린다.
            timeout=25.0,
        )

        res["request_chain_id"] = chain_id  # 파트너가 echo 안 해도 MCP 도구가 항상 상관관계 키를 받게 한다

        record_a2a_trace(
            session_id=req.session_id or "",
            skill_id="lookup-clause",
            request_payload=payload,
            response_payload=res,
            request_chain_id=chain_id,
            status="ok",
        )
        return res

    except A2APolicyBlockedError as exc:
        # ⚠ A2ACircuitOpenError·A2AUpstreamUnavailableError 보다 **먼저** 와야 한다 (D149).
        record_a2a_trace(
            session_id=req.session_id or "",
            skill_id="lookup-clause",
            request_payload=payload,
            response_payload={"error": str(exc)},
            request_chain_id=chain_id,
            status="policy_blocked",
        )
        raise HTTPException(
            status_code=503,
            detail={"reason": "policy_blocked", "message": _POLICY_BLOCKED_MESSAGE},
        ) from exc

    except A2ATimeoutError as exc:
        record_a2a_trace(
            session_id=req.session_id or "",
            skill_id="lookup-clause",
            request_payload=payload,
            response_payload={"error": str(exc)},
            request_chain_id=chain_id,
            status="timeout",
        )
        raise HTTPException(status_code=504, detail="InsuQ A2A adapter timeout") from exc

    except A2ACircuitOpenError as exc:
        # ⚠ A2AUpstreamUnavailableError 의 하위 타입이라 **먼저** 와야 한다.
        record_a2a_trace(
            session_id=req.session_id or "",
            skill_id="lookup-clause",
            request_payload=payload,
            response_payload={"error": str(exc)},
            request_chain_id=chain_id,
            status="circuit_open",
        )
        raise HTTPException(
            status_code=503,
            detail=f"InsuQ A2A 차단기가 열려 있습니다 (연속 실패 {exc.failure_count}회)",
            headers={"Retry-After": str(max(1, int(exc.retry_after)))},
        ) from exc

    except A2AUpstreamUnavailableError as exc:
        record_a2a_trace(
            session_id=req.session_id or "",
            skill_id="lookup-clause",
            request_payload=payload,
            response_payload={"error": str(exc)},
            request_chain_id=chain_id,
            status="unavailable",
        )
        raise HTTPException(status_code=502, detail="InsuQ A2A adapter unavailable") from exc

    except A2AClientError as exc:
        record_a2a_trace(
            session_id=req.session_id or "",
            skill_id="lookup-clause",
            request_payload=payload,
            response_payload={"error": str(exc)},
            request_chain_id=chain_id,
            status="error",
        )
        raise HTTPException(status_code=exc.status_code or 400, detail=exc.detail or str(exc)) from exc


class AssessLoanRequest(BaseModel):
    loan_amount: float = Field(..., gt=0, description="설비 담보 대출 희망 금액")
    purpose: str = Field(..., min_length=1, description="대출 목적")
    collateral_building_id: str = Field(..., min_length=1, description="담보 건물 ID")
    session_id: str | None = Field(None, description="MaintQ 세션 ID")
    request_chain_id: str | None = Field(None, description="멀티홉 추적용 체인 ID")


class RequestSettlementRequest(BaseModel):
    decision_id: str = Field(
        ..., min_length=1, description="처분 결정 ID(미서명 draft 여도 된다)"
    )
    sale_amount: float = Field(..., gt=0, description="설비 매각 금액")
    outstanding_loan: float = Field(..., ge=0, description="잔여 대출 원금")
    approved_by: str = Field(
        ..., min_length=1, description="정산 요청 승인자(처분 서명자가 아니다)"
    )
    prepayment_fee: float | None = Field(None, ge=0, description="중도상환 수수료(선택)")
    session_id: str | None = Field(None, description="MaintQ 세션 ID")
    request_chain_id: str | None = Field(None, description="멀티홉 추적용 체인 ID")


class AssessUsedEquipmentLoanRequest(BaseModel):
    asset_id: str = Field(..., min_length=1, description="담보로 잡을 MaintQ 자산 ID")
    loan_amount: float = Field(..., gt=0, description="중고 설비 담보 대출 희망 금액")
    session_id: str | None = Field(None, description="MaintQ 세션 ID")
    request_chain_id: str | None = Field(None, description="멀티홉 추적용 체인 ID")


@router.post("/assess-loan")
async def assess_loan_endpoint(req: AssessLoanRequest) -> dict[str, Any]:
    """FinAllQ A2A assess-loan 스킬을 호출해 설비 담보 대출 사전 판정을 조회한다(S8)."""
    base_url = os.environ.get("MAINTQ_A2A_FINALLQ_BASE_URL") or "http://localhost:9101"
    chain_id = req.request_chain_id or f"CHAIN-LOAN-{uuid.uuid4().hex[:8]}"

    payload = build_assess_loan_payload(
        loan_amount=req.loan_amount,
        purpose=req.purpose,
        collateral_building_id=req.collateral_building_id,
        request_chain_id=chain_id,
    )

    try:
        res = await call_skill(
            partner="finallq",
            skill_id="assess-loan",
            payload=payload,
            request_chain_id=chain_id,
            base_url=base_url,
        )

        res["request_chain_id"] = chain_id  # 파트너가 echo 안 해도 MCP 도구가 항상 상관관계 키를 받게 한다

        record_a2a_trace(
            session_id=req.session_id or "",
            skill_id="assess-loan",
            request_payload=payload,
            response_payload=res,
            request_chain_id=chain_id,
            status="ok",
        )
        return res

    except A2APolicyBlockedError as exc:
        # ⚠ A2ACircuitOpenError·A2AUpstreamUnavailableError 보다 **먼저** 와야 한다 (D149).
        record_a2a_trace(
            session_id=req.session_id or "",
            skill_id="assess-loan",
            request_payload=payload,
            response_payload={"error": str(exc)},
            request_chain_id=chain_id,
            status="policy_blocked",
        )
        raise HTTPException(
            status_code=503,
            detail={"reason": "policy_blocked", "message": _POLICY_BLOCKED_MESSAGE},
        ) from exc

    except A2ATimeoutError as exc:
        record_a2a_trace(
            session_id=req.session_id or "",
            skill_id="assess-loan",
            request_payload=payload,
            response_payload={"error": str(exc)},
            request_chain_id=chain_id,
            status="timeout",
        )
        raise HTTPException(status_code=504, detail="FinAllQ A2A adapter timeout") from exc

    except A2ACircuitOpenError as exc:
        # ⚠ A2AUpstreamUnavailableError 의 하위 타입이라 **먼저** 와야 한다.
        record_a2a_trace(
            session_id=req.session_id or "",
            skill_id="assess-loan",
            request_payload=payload,
            response_payload={"error": str(exc)},
            request_chain_id=chain_id,
            status="circuit_open",
        )
        raise HTTPException(
            status_code=503,
            detail=f"FinAllQ A2A 차단기가 열려 있습니다 (연속 실패 {exc.failure_count}회)",
            headers={"Retry-After": str(max(1, int(exc.retry_after)))},
        ) from exc

    except A2AUpstreamUnavailableError as exc:
        record_a2a_trace(
            session_id=req.session_id or "",
            skill_id="assess-loan",
            request_payload=payload,
            response_payload={"error": str(exc)},
            request_chain_id=chain_id,
            status="unavailable",
        )
        raise HTTPException(status_code=502, detail="FinAllQ A2A adapter unavailable") from exc

    except A2AClientError as exc:
        record_a2a_trace(
            session_id=req.session_id or "",
            skill_id="assess-loan",
            request_payload=payload,
            response_payload={"error": str(exc)},
            request_chain_id=chain_id,
            status="error",
        )
        raise HTTPException(status_code=exc.status_code or 400, detail=exc.detail or str(exc)) from exc


@router.post("/assess-used-equipment-loan")
async def assess_used_equipment_loan_endpoint(
    req: AssessUsedEquipmentLoanRequest,
) -> dict[str, Any]:
    """FinAllQ assess-used-equipment-loan 스킬로 중고 설비 담보 대출 심사를 요청한다(S13).

    S8(`assess-loan`)과 달리 호출자는 `asset_id` 와 금액만 준다 — 계약이 요구하는
    담보 건물·연식·점검 이력은 빌더가 `assets`·`ownership_checks` 에서 파생한다.
    """
    base_url = os.environ.get("MAINTQ_A2A_FINALLQ_BASE_URL") or "http://localhost:9101"
    chain_id = req.request_chain_id or f"CHAIN-UELOAN-{uuid.uuid4().hex[:8]}"

    try:
        payload = build_assess_used_equipment_loan_payload(
            asset_id=req.asset_id,
            loan_amount=req.loan_amount,
            request_chain_id=chain_id,
        )
    except ValueError as exc:
        # 없는 자산이다 — **발신하지 않는다.** 조용히 빈 값을 보내면 수신부가 400 을 낸다
        # (request-withdrawal 이 error_code=None 으로 schema_validation_failed 를 맞은 전례).
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await _dispatch(
        skill_id="assess-used-equipment-loan",
        payload=payload,
        chain_id=chain_id,
        session_id=req.session_id or "",
        base_url=base_url,
        partner_label="FinAllQ",
    )


@router.post("/request-settlement")
async def request_settlement_endpoint(req: RequestSettlementRequest) -> dict[str, Any]:
    """FinAllQ request-settlement 로 매각대금 정산 판정을 요청한다(S12).

    **MaintQ 발신 스킬 중 유일하게 응답이 MaintQ 상태를 바꾼다** —
    `lien_released: true` 면 LIEN-CONSENT 를 해소한다. 단 **서명하지는 않는다**:
    "서명 없는 처분 확정 0건" 불변식을 A2A 경로로 우회하지 않는다.

    ⚠️ 응답의 `remaining_balance` 는 FinAllQ 장부에 반영된 잔액이 아니라 **산술 결과**다
    (`decide_settlement` 는 DB 조회 0인 순수 함수이고 `loan_id` 가 없다, TASK-195).
    MaintQ 는 `lien_released` 만 소비하고 나머지는 trace 에만 남긴다.
    """
    base_url = os.environ.get("MAINTQ_A2A_FINALLQ_BASE_URL") or "http://localhost:9101"
    chain_id = req.request_chain_id or f"CHAIN-SETTLE-{uuid.uuid4().hex[:8]}"

    try:
        payload = build_request_settlement_payload(
            decision_id=req.decision_id,
            sale_amount=req.sale_amount,
            outstanding_loan=req.outstanding_loan,
            approved_by=req.approved_by,
            prepayment_fee=req.prepayment_fee,
            request_chain_id=chain_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    res = await _dispatch(
        skill_id="request-settlement",
        payload=payload,
        chain_id=chain_id,
        session_id=req.session_id or "",
        base_url=base_url,
        partner_label="FinAllQ",
    )

    # 응답 소비 — 담보 해소는 `lien_released` 가 **명시적으로 True** 일 때만 한다.
    # 키가 없거나 다른 값이면 아무것도 쓰지 않는다(조용한 해소 금지).
    # `is True` 인 이유: truthy 검사면 "true" 문자열·1 도 통과해 계약 밖 값이 담보를 푼다.
    if res.get("lien_released") is True:
        # 참조값은 `A2A-SETTLE-<chain_id>` — 비어 있지 않고(BLOCKING 룰 미발화 방지),
        # `traces` 에서 그 정산 왕복을 그대로 되짚을 수 있다.
        resolved = resolve_lien_consent(req.decision_id, f"A2A-SETTLE-{chain_id}")
        res["maintq_lien_consent_updated"] = resolved
        logger.info(
            "LIEN-CONSENT 해소 %s (decision=%s, chain=%s) — 서명은 사람이 한다",
            "완료" if resolved else "생략(이미 근거 있음)",
            req.decision_id,
            chain_id,
        )
    return res


@router.get("/history")
def a2a_history_endpoint(
    skill: str | None = None,
    po_id: str | None = None,
    building_id: str | None = None,
    chain_id: str | None = None,
    limit: int = 50,
) -> dict:
    """A2A 호출 감사 이력 (D114) — `read_trace`(D76-2 ⓑ)와 달리 tool_payload 원문을 연다."""
    return list_a2a_history(skill=skill, po_id=po_id, building_id=building_id, chain_id=chain_id, limit=limit)


class NotifyAssetChangeRequest(BaseModel):
    decision_id: str = Field(..., min_length=1, description="서명 완료된 처분 결정 ID")
    change_type: str = Field("REMOVE", description="REMOVE | ADD")
    session_id: str | None = Field(None, description="MaintQ 세션 ID")
    request_chain_id: str | None = Field(None, description="멀티홉 추적용 체인 ID")


@router.post("/notify-asset-change")
async def notify_asset_change_endpoint(req: NotifyAssetChangeRequest) -> dict[str, Any]:
    """InsuQ notify-asset-change 로 부보 목적물 변경을 통지한다(S11).

    처분이 **서명으로 확정된 뒤** 보내는 통지다 — 조립 단계에서 서명·부보 여부를 막으므로
    (`build_notify_asset_change_payload`), 조건에 안 맞으면 **발신하지 않고 400 으로 돌려준다.**
    조용히 빈 값을 실어 보내면 수신부가 `schema_validation_failed` 를 낸다(전례 있음).

    ⛔ **응답으로 MaintQ 상태를 바꾸지 않는다** — 통지는 알리는 것이지 되받는 것이 아니다.
    `receipt_no`·`premium_adjustment` 는 trace 에만 남는다. 보험료 조정을 자산 장부에 반영하려면
    사람이 하는 별도 경로가 필요하다(S12 가 `lien_released` 를 소비하는 것과는 성격이 다르다).
    """
    base_url = os.environ.get("MAINTQ_A2A_INSUQ_BASE_URL") or "http://localhost:9102"
    chain_id = req.request_chain_id or f"CHAIN-ASSETCHG-{uuid.uuid4().hex[:8]}"

    try:
        payload = build_notify_asset_change_payload(
            decision_id=req.decision_id,
            request_chain_id=chain_id,
            change_type=req.change_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await _dispatch(
        skill_id="notify-asset-change",
        payload=payload,
        chain_id=chain_id,
        session_id=req.session_id or "",
        base_url=base_url,
        partner_label="InsuQ",
        partner="insuq",
        # 같은 처분의 재전송은 같은 키 → 상대가 저장된 응답을 재생한다. 내용이 바뀌면 409 다
        # (사람이 봐야 할 상황이므로 막히는 것이 맞다). D141
        idempotency_key=idempotency_key_for_asset_change(req.decision_id, req.change_type),
    )
