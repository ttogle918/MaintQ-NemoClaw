# -*- coding: utf-8 -*-
"""search_insurance_clause — 보험 약관 조회 (docs/04_MCP_TOOLS.md, Sprint 16 신설).

InsuQ(외부 보험 파트너)에 화재보험 등 보장 여부를 A2A 로 문의한다. 이 도구는 파트너
자격증명을 직접 다루지 않는다 — MaintQ 백엔드 REST(`POST /api/a2a/lookup-clause`)를
HTTP 로 호출할 뿐이다 (D15·D93 — mcp_server 프로세스는 A2A 자격증명·파트너 대장을
알지 못한다). 실패는 예외가 아니라 status 로 반환한다 (D9).
"""

from __future__ import annotations

import os

import httpx

DESCRIPTION = (
    "화재보험 등 보험 약관의 보장 여부를 InsuQ(외부 보험 파트너)에 문의한다. 정비사가 "
    "설비 고장·손해의 보험 보장 여부를 명시적으로 물을 때만 호출할 것. MaintQ 매뉴얼 "
    "근거가 아니라 외부 파트너의 응답이므로 결과를 그대로 전달하고 추측을 덧붙이지 말 것. "
    "실패 시 확답을 못 얻었다는 사실을 정직하게 알릴 것."
)

_DEFAULT_BASE_URL = "http://localhost:8000"
_ENV_BASE_URL = "MAINTQ_BACKEND_BASE_URL"


def search_insurance_clause(question: str) -> dict:
    if not isinstance(question, str) or not question.strip():
        return {
            "status": "error",
            "reason": "question_required",
            "message": "question 이 비어 있습니다.",
        }

    base_url = os.environ.get(_ENV_BASE_URL) or _DEFAULT_BASE_URL
    url = f"{base_url.rstrip('/')}/api/a2a/lookup-clause"

    try:
        resp = httpx.post(url, json={"question": question}, timeout=12.0)
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
            "message": "InsuQ 로부터 확답을 받지 못했습니다.",
            "skill_status": skill_status,
        }

    if resp.status_code in (502, 503, 504):
        return {
            "status": "error",
            "reason": "upstream_unavailable",
            "message": f"InsuQ A2A 어댑터에 연결할 수 없습니다 (HTTP {resp.status_code}).",
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
