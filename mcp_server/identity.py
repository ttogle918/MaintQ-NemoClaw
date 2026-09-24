# -*- coding: utf-8 -*-
"""MCP-HTTP 입구의 요청자 신원 — `X-User` 헤더에서 읽는다 (D152).

## 왜 도구 파라미터가 아닌가 (D23 유지)

신원이 도구 스키마에 있으면 LLM 이 채울 수 있다 = 타인 명의 발주를 위조할 수 있다.
그래서 신원은 **HTTP 요청 헤더**에서 온다. FastMCP 의 `Context` 파라미터는 도구 입력
스키마에 노출되지 않으므로, 도구가 `ctx` 로 헤더를 읽어도 LLM 이 건드릴 경로가 없다.
헤더를 싣는 쪽은 에이전트 런타임 설정(OpenClaw `mcp.servers.<name>.headers`)이다.

## 왜 D37(백엔드 stamp)을 그대로 못 쓰나

stdio 경로는 백엔드가 도구 호출 직후 같은 요청 안에서 `stamp_identity()` 로 신원을 새긴다.
MCP-HTTP 로 붙는 에이전트(OpenClaw)는 백엔드를 거치지 않으므로 stamp 할 주체가 없고,
`requested_by` 가 영영 NULL 로 남는다(2026-09-24 실측 — `PO-0122`). D37 이 "MCP 세션
컨텍스트로 전달" 을 기각한 이유는 *stdio 라 사용자별로 서버를 띄워야 한다* 였는데,
HTTP 는 요청마다 헤더가 오므로 그 전제가 없다.

## 전송 판별

`ctx.request_context.request` 가 **None 이면 stdio** 다 — 이때는 신원을 요구하지 않고
기존 D37 경로(백엔드 stamp)를 그대로 탄다. HTTP 일 때만 헤더를 요구한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

USER_HEADER = "x-user"
SESSION_HEADER = "mcp-session-id"

#: ASCII 사용자 ID (D36). 백엔드 `deps.caller()` 는 `isascii()` 만 보지만 여기는 쓰기
#: 귀속이라 더 좁힌다 — 공백·제어문자·구분자가 감사 로그에 섞이지 않게.
_USER_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


@dataclass(frozen=True)
class Requester:
    transport: str  # "stdio" | "http"
    user_id: str | None = None
    session_id: str | None = None
    error: str | None = None  # "identity_missing" | "identity_invalid"


def _http_request(ctx: Any) -> Any | None:
    """HTTP 요청 객체. stdio 이거나 요청 컨텍스트 밖이면 None."""
    if ctx is None:
        return None
    try:
        return ctx.request_context.request
    except (AttributeError, LookupError, ValueError):
        # 요청 컨텍스트 밖(직접 호출·테스트)에서 접근하면 SDK 가 ValueError 를 낸다
        return None


def resolve(ctx: Any) -> Requester:
    """요청자 신원을 판정한다. 예외를 던지지 않는다 — 판정 결과를 돌려준다 (D9)."""
    req = _http_request(ctx)
    if req is None:
        return Requester(transport="stdio")
    headers = getattr(req, "headers", None) or {}
    raw = (headers.get(USER_HEADER) or "").strip()
    session = (headers.get(SESSION_HEADER) or "").strip() or None
    if not raw:
        return Requester(transport="http", session_id=session, error="identity_missing")
    if not _USER_ID.fullmatch(raw):
        return Requester(transport="http", session_id=session, error="identity_invalid")
    return Requester(transport="http", user_id=raw, session_id=session)
