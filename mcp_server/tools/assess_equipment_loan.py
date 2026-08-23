# -*- coding: utf-8 -*-
"""assess_equipment_loan — 설비 담보 대출 사전판정 (docs/04_MCP_TOOLS.md, Sprint 16 신설).

FinAllQ(외부 금융 파트너, 내부적으로 InsuQ 2차 조회 포함)에 설비 담보 대출 사전판정을
A2A 로 문의한다. 이 도구는 파트너 자격증명을 직접 다루지 않는다 — MaintQ 백엔드
REST(`POST /api/a2a/assess-loan`)를 HTTP 로 호출할 뿐이다 (D15·D93 — mcp_server
프로세스는 A2A 자격증명·파트너 대장을 알지 못한다). 실패는 예외가 아니라 status 로
반환한다 (D9).
"""

from __future__ import annotations

import os

import httpx

DESCRIPTION = (
    "설비를 담보로 한 대출 사전판정을 FinAllQ(외부 금융 파트너, 내부적으로 InsuQ 2차 "
    "조회 포함)에 문의한다. 사용자가 설비 담보 대출을 명시적으로 물을 때만 호출할 것. "
    "현재 파트너 쪽 연동이 아직 준비되지 않아 실패 응답이 정상적으로 나올 수 있다 — "
    "실패를 오류로 취급하지 말고 결과를 있는 그대로 전달할 것."
)

_DEFAULT_BASE_URL = "http://localhost:8000"
_ENV_BASE_URL = "MAINTQ_BACKEND_BASE_URL"


def assess_equipment_loan(loan_amount: float, purpose: str, collateral_building_id: str) -> dict:
    if not isinstance(loan_amount, (int, float)) or isinstance(loan_amount, bool) or loan_amount <= 0:
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": "loan_amount 는 0보다 큰 숫자여야 합니다.",
        }
    if not isinstance(purpose, str) or not purpose.strip():
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": "purpose 가 비어 있습니다.",
        }
    if not isinstance(collateral_building_id, str) or not collateral_building_id.strip():
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": "collateral_building_id 가 비어 있습니다.",
        }

    base_url = os.environ.get(_ENV_BASE_URL) or _DEFAULT_BASE_URL
    url = f"{base_url.rstrip('/')}/api/a2a/assess-loan"
    payload = {
        "loan_amount": loan_amount,
        "purpose": purpose,
        "collateral_building_id": collateral_building_id,
    }

    try:
        resp = httpx.post(url, json=payload, timeout=12.0)
    except httpx.TimeoutException as exc:
        return {"status": "error", "reason": "timeout", "message": str(exc)}
    except httpx.HTTPError as exc:
        # 백엔드 프로세스 자체(연결 거부 등)에 못 닿은 경우 — A2A 파트너 실패와 구분한다.
        return {"status": "error", "reason": "backend_unreachable", "message": str(exc)}

    if resp.status_code == 200:
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "reason": "invalid_response", "message": str(exc)}

        skill_status = data.get("status") if isinstance(data, dict) else None
        if skill_status == "completed":
            result = dict(data)
            result["status"] = "ok"
            result["skill_status"] = skill_status
            return result

        reason = "no_answer" if skill_status in ("input-required", "rejected") else "unexpected_status"
        return {
            "status": "error",
            "reason": reason,
            "message": "FinAllQ 로부터 확답을 받지 못했습니다.",
            "skill_status": skill_status,
        }

    if resp.status_code in (502, 503, 504):
        return {
            "status": "error",
            "reason": "upstream_unavailable",
            "message": f"FinAllQ A2A 어댑터에 연결할 수 없습니다 (HTTP {resp.status_code}).",
        }

    detail: str
    try:
        body = resp.json()
        detail = body.get("detail") if isinstance(body, dict) else None
    except Exception:  # noqa: BLE001
        detail = None
    if not detail:
        detail = resp.text[:200]
    return {"status": "error", "reason": "a2a_error", "message": detail}
