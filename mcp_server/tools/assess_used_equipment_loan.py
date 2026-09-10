# -*- coding: utf-8 -*-
"""assess_used_equipment_loan — 중고 설비 담보 심사 (S13, docs/04_MCP_TOOLS.md §22).

FinAllQ(외부 금융 파트너, 내부적으로 InsuQ 2차 조회 포함)에 **자산 하나를 담보로 한**
대출 심사를 A2A 로 문의한다. 형제 `assess_equipment_loan`(S8, 건물 담보)과 달리
호출자는 `asset_id` 와 금액만 준다 — 담보 건물·연식·점검 이력·**취득원가**는 백엔드
빌더가 `assets`·`ownership_checks` 에서 파생한다 (D138).

⛔ **원가를 도구 인자로 받지 않는다.** 받으면 모델이 그 값을 지어낼 자리가 생긴다.
   원가는 `assets.acquisition_cost` 가 정본이고, 없으면 payload 에서 키가 빠진다(D62).

이 도구는 파트너 자격증명을 직접 다루지 않는다 — MaintQ 백엔드 REST
(`POST /api/a2a/assess-used-equipment-loan`)를 HTTP 로 호출할 뿐이다 (D15·D93).
실패는 예외가 아니라 status 로 반환한다 (D9).

## 503 을 502 와 뭉개지 않는다 (D136·D139)

형제 파일은 `502·503·504` 를 한 덩어리로 `upstream_unavailable` 에 넣는데, 그러면
**«상대가 죽었다»와 «우리가 스스로 막았다»가 같은 말이 된다.** 503 은 차단기가 연
것이고 사용자에게 할 안내가 다르다 — *"연속 실패로 잠시 차단됐다(잠시 후 재시도)"* 는
상대 장애가 아니라 우리 판단이다. 504 도 따로 둔다: 시간이 다한 것과 닿지 못한 것은
다른 사건이다.
"""

from __future__ import annotations

import os

import httpx

DESCRIPTION = (
    "보유 설비 하나를 담보로 한 대출 심사를 FinAllQ(외부 금융 파트너, 내부적으로 InsuQ "
    "2차 조회 포함)에 문의한다. `asset_id` 와 `loan_amount` 만 주면 되고 담보 건물·연식·"
    "점검 이력·취득원가는 서버가 자산 대장에서 파생한다 — 그 값들을 추측해 넣지 말 것. "
    "사용자가 설비를 담보로 한 자금 조달을 명시적으로 물을 때만 호출할 것. "
    "🔴 응답의 `decision:\"approved\"` 를 **«대출이 승인됐다»로 옮기지 말 것** — 그것은 "
    "상대가 담보 조건을 충족한다고 본 판정이고, 실제 여신 승인은 상대 담당자의 결재가 "
    "남아 있다(상대 장부는 심사중 상태로 남는다). 「담보 조건 충족」으로 전하고 결재가 "
    "남았음을 함께 밝힐 것. `appraised_value`·`collateral_check` 는 상대가 준 값을 그대로 "
    "전달하고 우리가 다시 계산하지 말 것."
)

_DEFAULT_BASE_URL = "http://localhost:8000"
_ENV_BASE_URL = "MAINTQ_BACKEND_BASE_URL"

#: HTTP 상태 → 실패 사유. 뭉개면 에이전트가 사용자에게 같은 말을 하게 된다 (모듈 docstring).
_STATUS_REASON: dict[int, str] = {
    502: "upstream_unavailable",  # 상대 뒤(2차 홉·자기 upstream)가 죽었다
    503: "circuit_open",  # **우리가** 막았다 — 차단기 (D136·D139)
    504: "upstream_timeout",  # 상대가 시간 안에 답하지 못했다
}


def assess_used_equipment_loan(asset_id: str, loan_amount: float) -> dict:
    """두 파라미터 전부 필수 (D80). 실패는 status 로 반환한다 (D9)."""
    if not isinstance(asset_id, str) or not asset_id.strip():
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": "asset_id 가 비어 있습니다.",
        }
    # ⚠ `isinstance(True, int)` 가 참이라 bool 을 먼저 거른다 — 금액으로 새면 조용히 1 이 된다
    if (
        not isinstance(loan_amount, (int, float))
        or isinstance(loan_amount, bool)
        or loan_amount <= 0
    ):
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": "loan_amount 는 0 보다 큰 숫자여야 합니다.",
        }

    base_url = os.environ.get(_ENV_BASE_URL) or _DEFAULT_BASE_URL
    url = f"{base_url.rstrip('/')}/api/a2a/assess-used-equipment-loan"
    payload = {"asset_id": asset_id.strip(), "loan_amount": loan_amount}

    try:
        resp = httpx.post(url, json=payload, timeout=12.0)
    except httpx.TimeoutException as exc:
        # 우리 타임아웃 — 상대의 504(상대가 판단해 보낸 응답)와 다른 사건이다
        return {"status": "error", "reason": "timeout", "message": str(exc)}
    except httpx.HTTPError as exc:
        # 백엔드 프로세스 자체(연결 거부 등)에 못 닿은 경우 — A2A 파트너 실패와 구분한다
        return {"status": "error", "reason": "backend_unreachable", "message": str(exc)}

    if resp.status_code == 200:
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "reason": "invalid_response", "message": str(exc)}

        skill_status = data.get("status") if isinstance(data, dict) else None
        if skill_status == "completed":
            # 상대가 준 필드를 통째로 올린다 — 여기서 문장을 만들면 도구가 주지 않은
            # 정보가 사실처럼 보인다. `decision` 해석은 DESCRIPTION 이 규율한다.
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

    detail: str | None
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
