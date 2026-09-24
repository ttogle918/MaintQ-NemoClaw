# -*- coding: utf-8 -*-
"""MaintQ A2A 공용 HTTP 클라이언트.

어댑터(A2A_Q)의 /a2a/skills/{skill_id} 엔드포인트를 호출하고 에러를 매핑한다.
"""

from __future__ import annotations

from typing import Any
import httpx

from backend.a2a.auth_header import build_auth_header
from backend.a2a.circuit import CircuitOpen, registry


class A2AClientError(Exception):
    """A2A 클라이언트 호출 에러 기본 클래스."""

    def __init__(self, message: str, status_code: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class A2AUpstreamUnavailableError(A2AClientError):
    """502/504 또는 연결 실패 등 원격 어댑터 도달 불가."""


class A2ATimeoutError(A2AClientError):
    """요청 타임아웃."""


class A2APolicyBlockedError(A2AClientError):
    """샌드박스 정책상 외부 발신이 불가해 **시도하지 않았다** (D149). 네트워크·차단기 무관.

    ⚠ `A2AUpstreamUnavailableError` 의 하위 타입으로 두지 **않는다** — 기존
    `except A2AUpstreamUnavailableError` 가 이 예외를 잡으면 「상대 불가」(502 계열)로
    오기록된다. 정책은 우리 쪽 사정이지 상대의 장애가 아니다.
    """


class A2ACircuitOpenError(A2AUpstreamUnavailableError):
    """차단기가 열려 있어 **호출을 시도조차 하지 않았다** (P35).

    `A2AUpstreamUnavailableError` 를 상속하는 것은 의도적이다 — 이 예외를 모르는 기존
    호출부도 "상대에 못 닿았다"로 안전하게 처리한다. 구분해서 다루고 싶은 곳만
    이 타입을 먼저 잡으면 된다.

    ⚠ *못 닿았다*와 *닿아 보지도 않았다*는 다르다. 운영자가 로그에서 그 둘을 구분하지
    못하면 "상대가 죽었다"와 "우리가 스스로 막고 있다"를 혼동한다 — 그래서 별도 타입이다.
    """

    def __init__(self, message: str, retry_after: float, failure_count: int):
        super().__init__(message)
        self.retry_after = retry_after
        self.failure_count = failure_count


async def call_skill(
    partner: str,
    skill_id: str,
    payload: dict[str, Any],
    request_chain_id: str,
    base_url: str,
    timeout: float = 10.0,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """A2A 어댑터의 POST /a2a/skills/{skill_id}를 호출한다.

    - Authorization 헤더: build_auth_header(partner)
    - X-Request-Chain-Id 헤더: request_chain_id (body와 동일해야 함)
    - 응답: 200/202 (status: completed/input-required/rejected) -> payload dict 반환
    """
    if not base_url:
        raise ValueError(f"base_url for partner '{partner}' is not configured")

    if not request_chain_id:
        raise ValueError("request_chain_id must be provided")

    payload_chain_id = payload.get("request_chain_id")
    if payload_chain_id and payload_chain_id != request_chain_id:
        raise ValueError(
            f"request_chain_id mismatch: header={request_chain_id} vs body={payload_chain_id}"
        )

    headers = {
        "Content-Type": "application/json",
        "X-Request-Chain-Id": request_chain_id,
        **build_auth_header(partner),
    }
    # 스킬마다 요구가 다르다 — InsuQ 는 notify-asset-change 에서 이 헤더가 없으면 400 이고
    # lookup-clause 는 없이도 통과한다. 그래서 클라이언트가 임의로 만들지 않고 **호출자가
    # 업무 정체성에서 파생해 넘긴다**(D141, `payloads.idempotency_key_for_asset_change`).
    # ⚠ 계약면(schemas·agent_cards)에 헤더를 적을 자리가 없다 — CP-006 이 그 자리를 만드는 중.
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    url = f"{base_url.rstrip('/')}/a2a/skills/{skill_id}"

    # ── 샌드박스 정책 관문 (D149). ValueError 검사들보다 **뒤**, 차단기 관문보다 **앞**.
    #    `MAINTQ_SANDBOX=openshell` 이면 egress 정책상 파트너 호스트가 열려 있지 않다 —
    #    보낼 수 없다는 것을 호출 전에 알 수 있으므로 시도조차 하지 않는다. `registry()` 를
    #    아예 호출하지 않는다 — 차단기 성공·실패 카운터를 건드리면 안 된다(정책 차단은
    #    상대의 장애가 아니다).
    from backend.agent.llm import sandbox_mode  # 지연 import — 순환 방지

    if sandbox_mode():
        raise A2APolicyBlockedError(
            f"샌드박스 정책상 A2A 발신이 차단되었습니다: {partner}/{skill_id} (D149)"
        )

    # ── 차단기 관문 (P35). 위의 ValueError 들보다 **뒤**에 둔다 —
    #    설정 오류는 우리 문제이지 상대의 장애가 아니라서 차단기와 무관하다.
    breaker = registry()
    try:
        breaker.before_call(partner)
    except CircuitOpen as exc:
        raise A2ACircuitOpenError(
            str(exc), retry_after=exc.retry_after, failure_count=exc.failure_count
        ) from exc

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            breaker.on_unreachable(partner)
            raise A2ATimeoutError(f"A2A request to {partner}/{skill_id} timed out", detail=str(exc)) from exc
        except httpx.ConnectError as exc:
            breaker.on_unreachable(partner)
            raise A2AUpstreamUnavailableError(f"Cannot connect to A2A adapter at {base_url}", detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            breaker.on_unreachable(partner)
            raise A2AUpstreamUnavailableError(f"HTTP error communicating with {partner}/{skill_id}", detail=str(exc)) from exc

    # 여기부터는 전부 «상대가 응답을 돌려줬다» = 살아 있다는 증거다 (D139).
    # 죽은 프로세스는 502 를 만들지 못한다 — 502·503·504 는 상대가 살아서 요청을 파싱하고
    # 자기 upstream 이 실패했다고 **판단해** 그 판단을 응답으로 써 보낸 것이다.
    # 그래서 상태코드와 **무관하게** 차단기를 닫는다: 판정 축은 "이 응답이 성공인가"가
    # 아니라 "응답이 있었는가"다. 4xx 계약 오류도 같은 이유다(모듈 docstring 경계 2).
    #
    # 🔴 이 줄이 5xx 검사보다 **위**에 있어야 한다. 아래에 두면 2차 홉 장애가 파트너
    #    전체를 막는다 — 2026-09-10 E2E 에서 InsuQ 가 죽자 FinAllQ 는 멀쩡한데
    #    `finallq` 차단기가 열려 InsuQ 와 무관한 request-withdrawal·request-settlement
    #    까지 막히는 것이 실측됐다(D136 이 경계 ⓑ 로 막으려던 바로 그 병리).
    # ⚠ 비용이 큰 경우는 이 규칙으로도 덮인다 — 상대가 아플 만큼 느리면 우리 타임아웃이
    #    먼저 걸려 위쪽 `httpx.TimeoutException` 경로로 정상적으로 열린다(응답이 없다).
    #    상대의 504(상대가 판단해 보낸 응답)와 우리 타임아웃(응답 없음)은 다른 사건이다.
    breaker.on_reachable(partner)

    if resp.status_code in (502, 503, 504):
        # 어댑터는 살아 있고 그 뒤(2차 홉·자기 upstream)가 죽은 것.
        # 호출부 계약은 그대로 502 계열이다 — 차단기 회계만 위에서 달라졌다.
        raise A2AUpstreamUnavailableError(
            f"A2A adapter {partner} returned {resp.status_code}",
            status_code=resp.status_code,
            detail=resp.text,
        )

    if resp.status_code in (200, 202):
        try:
            return resp.json()
        except Exception as exc:
            raise A2AClientError(f"Invalid JSON response from {partner}/{skill_id}", status_code=resp.status_code) from exc

    raise A2AClientError(
        f"A2A request failed with status {resp.status_code}",
        status_code=resp.status_code,
        detail=resp.text,
    )
