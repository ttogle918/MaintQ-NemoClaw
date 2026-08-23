# -*- coding: utf-8 -*-
"""MaintQ A2A 공용 HTTP 클라이언트.

어댑터(A2A_Q)의 /a2a/skills/{skill_id} 엔드포인트를 호출하고 에러를 매핑한다.
"""

from __future__ import annotations

from typing import Any
import httpx

from backend.a2a.auth_header import build_auth_header


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


async def call_skill(
    partner: str,
    skill_id: str,
    payload: dict[str, Any],
    request_chain_id: str,
    base_url: str,
    timeout: float = 10.0,
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

    url = f"{base_url.rstrip('/')}/a2a/skills/{skill_id}"

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise A2ATimeoutError(f"A2A request to {partner}/{skill_id} timed out", detail=str(exc)) from exc
        except httpx.ConnectError as exc:
            raise A2AUpstreamUnavailableError(f"Cannot connect to A2A adapter at {base_url}", detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise A2AUpstreamUnavailableError(f"HTTP error communicating with {partner}/{skill_id}", detail=str(exc)) from exc

    if resp.status_code in (200, 202):
        try:
            return resp.json()
        except Exception as exc:
            raise A2AClientError(f"Invalid JSON response from {partner}/{skill_id}", status_code=resp.status_code) from exc

    if resp.status_code in (502, 503, 504):
        raise A2AUpstreamUnavailableError(
            f"A2A adapter {partner} returned {resp.status_code}",
            status_code=resp.status_code,
            detail=resp.text,
        )

    raise A2AClientError(
        f"A2A request failed with status {resp.status_code}",
        status_code=resp.status_code,
        detail=resp.text,
    )
