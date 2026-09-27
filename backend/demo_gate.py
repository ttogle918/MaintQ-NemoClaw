# -*- coding: utf-8 -*-
"""공개 배포용 데모 토큰 게이트 (D159).

`X-Role`/`X-User` 는 헤더 시뮬레이션이라(P21 미구현) URL 만 알면 누구나 발주를 승인할 수 있다.
공개 URL 에 올릴 때 그 앞에 **공유 토큰 하나**를 세운다 — 인증이 아니라 문지기다.

- `MAINTQ_DEMO_TOKEN` 이 비어 있으면 **아무것도 하지 않는다** (로컬 개발·회귀 스위트 무영향).
- 통과: CORS 프리플라이트(OPTIONS) · `/health` · **loopback 클라이언트** — 같은 컨테이너의
  MCP 자식이 `MAINTQ_BACKEND_BASE_URL=http://localhost:8000` 으로 부르는 A2A 경로(D93).
  uvicorn 은 `X-Forwarded-For` 를 127.0.0.1 피어에게서만 믿으므로 외부에서 loopback 을 위장할 수 없다.
- 순수 ASGI 로 쓴다 — `BaseHTTPMiddleware` 는 SSE 스트림(D14)을 감싸며 버퍼링 이슈를 낳은 전례가 있다.
- CORS 미들웨어보다 **안쪽**에 둬야 401 응답에도 CORS 헤더가 붙는다 (`main.py` 등록 순서).
"""

from __future__ import annotations

import hmac
import json
import os

HEADER = b"x-demo-token"
_EXEMPT_PATHS = frozenset({"/health"})
_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


def configured_token() -> str:
    return (os.environ.get("MAINTQ_DEMO_TOKEN") or "").strip()


class DemoTokenGate:
    def __init__(self, app, token: str | None = None) -> None:
        self.app = app
        self.token = configured_token() if token is None else token.strip()

    async def __call__(self, scope, receive, send) -> None:
        if not self.token or scope["type"] != "http" or self._exempt(scope):
            await self.app(scope, receive, send)
            return
        got = dict(scope.get("headers") or []).get(HEADER, b"").decode("latin-1")
        if got and hmac.compare_digest(got, self.token):
            await self.app(scope, receive, send)
            return
        body = json.dumps({"detail": "demo_token_required"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    def _exempt(scope) -> bool:
        if scope.get("method") == "OPTIONS" or scope.get("path") in _EXEMPT_PATHS:
            return True
        client = scope.get("client")
        return bool(client) and client[0] in _LOOPBACK
