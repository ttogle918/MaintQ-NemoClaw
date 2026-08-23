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

from backend.a2a.client import A2AClientError, A2ATimeoutError, A2AUpstreamUnavailableError, call_skill
from backend.a2a.payloads import build_assess_loan_payload, build_lookup_clause_payload
from backend.a2a.trace import record_a2a_trace

router = APIRouter(prefix="/api/a2a", tags=["a2a"])
logger = logging.getLogger(__name__)


class LookupClauseRequest(BaseModel):
    question: str = Field(..., min_length=1, description="약관 관련 질의 문장")
    session_id: str | None = Field(None, description="MaintQ 세션 ID")
    request_chain_id: str | None = Field(None, description="멀티홉 추적용 체인 ID")


@router.post("/lookup-clause")
async def lookup_clause_endpoint(req: LookupClauseRequest) -> dict[str, Any]:
    """InsuQ A2A lookup-clause 스킬을 호출해 약관 근거와 답변을 조회한다."""
    base_url = os.environ.get("MAINTQ_A2A_INSUQ_BASE_URL") or "http://localhost:9102"
    chain_id = req.request_chain_id or f"CHAIN-CLAUSE-{uuid.uuid4().hex[:8]}"

    payload = build_lookup_clause_payload(question=req.question, request_chain_id=chain_id)

    try:
        res = await call_skill(
            partner="insuq",
            skill_id="lookup-clause",
            payload=payload,
            request_chain_id=chain_id,
            base_url=base_url,
        )

        record_a2a_trace(
            session_id=req.session_id or "",
            skill_id="lookup-clause",
            request_payload=payload,
            response_payload=res,
            request_chain_id=chain_id,
            status="ok",
        )
        return res

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

        record_a2a_trace(
            session_id=req.session_id or "",
            skill_id="assess-loan",
            request_payload=payload,
            response_payload=res,
            request_chain_id=chain_id,
            status="ok",
        )
        return res

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
