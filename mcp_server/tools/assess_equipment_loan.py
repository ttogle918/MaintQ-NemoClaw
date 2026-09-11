# -*- coding: utf-8 -*-
"""assess_equipment_loan — 설비 담보 대출 사전판정 (docs/04_MCP_TOOLS.md, Sprint 16 신설).

FinAllQ(외부 금융 파트너, 내부적으로 InsuQ 2차 조회 포함)에 설비 담보 대출 사전판정을
A2A 로 문의한다. 이 도구는 파트너 자격증명을 직접 다루지 않는다 — MaintQ 백엔드
REST(`POST /api/a2a/assess-loan`)를 HTTP 로 호출할 뿐이다 (D15·D93 — mcp_server
프로세스는 A2A 자격증명·파트너 대장을 알지 못한다). 실패는 예외가 아니라 status 로
반환한다 (D9).

## 503 을 502 와 뭉개지 않는다 (D136·D139)

이 파일은 오래 `502·503·504` 를 한 덩어리로 `upstream_unavailable` 에 넣고 있었다.
그러면 **«상대가 죽었다»와 «우리가 스스로 막았다»가 같은 말이 된다.** 503 은 차단기가
연 것이고 사용자에게 할 안내가 다르다 — *"연속 실패로 잠시 차단됐다(잠시 후 재시도)"* 는
상대 장애가 아니라 우리 판단이다. 504 도 따로 둔다: 시간이 다한 것과 닿지 못한 것은
다른 사건이다. 동생 `assess_used_equipment_loan` 이 D139 에서 먼저 세운 경계를 옮긴 것이다.
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

#: HTTP 상태 → 실패 사유. 뭉개면 에이전트가 사용자에게 같은 말을 하게 된다 (모듈 docstring).
_STATUS_REASON: dict[int, str] = {
    502: "upstream_unavailable",  # 상대 뒤(2차 홉·자기 upstream)가 죽었다
    503: "circuit_open",  # **우리가** 막았다 — 차단기 (D136·D139)
    504: "upstream_timeout",  # 상대가 시간 안에 답하지 못했다
}


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

    reason = _STATUS_REASON.get(resp.status_code)
    if reason:
        return {
            "status": "error",
            "reason": reason,
            "message": _upstream_message(reason, resp),
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


def _upstream_message(reason: str, resp: httpx.Response) -> str:
    """실패 사유를 사람 말로. 차단기는 **상대 장애가 아니라 우리 판단**임을 밝힌다."""
    if reason == "circuit_open":
        body = (resp.text or "").strip()[:200]
        return (
            "연속 실패로 FinAllQ 호출이 잠시 차단된 상태입니다 (상대 장애가 아니라 "
            f"우리 쪽 차단기입니다 — 잠시 후 다시 시도하십시오). {body}".strip()
        )
    if reason == "upstream_timeout":
        return "FinAllQ 가 시간 안에 응답하지 않았습니다 (HTTP 504)."
    return f"FinAllQ A2A 어댑터에 연결할 수 없습니다 (HTTP {resp.status_code})."
