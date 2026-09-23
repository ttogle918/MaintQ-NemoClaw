# -*- coding: utf-8 -*-
"""MCP 를 streamable-http 로 여는 **두 번째 입구** (D150).

기본 입구는 여전히 stdio 다(`server.py::mcp.run()`) — 백엔드는 그쪽만 쓰고
`mcp_server` 를 import 하지 않는다(D15). 이 파일은 **샌드박스 밖 에이전트**
(NemoClaw 의 OpenClaw 등)가 붙기 위한 입구다. NemoClaw 는 stdio MCP 를 받지 않고
HTTPS + 서버당 bearer 1개를 요구하기 때문이다.

## 도구를 복제하지 않는다

`server.py` 의 **같은 `FastMCP` 인스턴스**를 그대로 노출한다. 도구 정의·입력 스키마·
프로필(`MAINTQ_TOOLS_PROFILE`, D69·D88)이 전송마다 갈라질 자리가 원리적으로 없다.
두 벌을 두면 한쪽이 조용히 낡는다 — 그게 이 설계의 요점이다.

## 가드 3종

1. **토큰이 없으면 기동을 거부한다.** 열린 채로 뜨는 것보다 안 뜨는 게 낫다
   (D143 의 "샌드박스 안에 키가 보이면 기동 거부" 와 같은 발상).
2. **loopback 에만 바인딩한다.** 바깥으로 나가는 길은 OpenShell 게이트웨이
   (`openshell service expose`) 하나뿐이고, 거기서 mTLS HTTPS 가 붙는다.
3. **bearer 비교는 상수 시간**(`secrets.compare_digest`).

## 바뀌지 않는 것

D10 은 전송이 아니라 **도구 안**에 있다 — 쓰기 도구 3종, `draft_writer`/
`decision_writer`/`repair_writer` 커넥션 분리, TEMP TRIGGER. HTTP 로 들어와도
UPDATE 는 똑같이 거부된다.

실행:
    MAINTQ_MCP_TOKEN=... uv run python -m mcp_server.http_entry
"""

from __future__ import annotations

import os
import secrets
import sys

#: 노출 경로 — NemoClaw `mcp add --url <base>/mcp` 가 가리키는 자리.
DEFAULT_PATH = "/mcp"
DEFAULT_PORT = 8765
#: 바인딩은 loopback 고정. env 로 열 수 있게 두지 않는다 — 실수로 0.0.0.0 이 되면
#: 게이트웨이를 우회하는 두 번째 입구가 생긴다.
BIND_HOST = "127.0.0.1"

TOKEN_ENV = "MAINTQ_MCP_TOKEN"
PORT_ENV = "MAINTQ_MCP_HTTP_PORT"


class TokenMissing(RuntimeError):
    """`MAINTQ_MCP_TOKEN` 부재 — 기동하지 않는다."""


def read_token(env: dict[str, str] | None = None) -> str:
    """토큰을 읽는다. 없거나 비면 **예외** — 기본값을 만들어 내지 않는다.

    D9(도구는 status 로 실패)는 도구 **로직**의 규칙이다. 기동 전 설정 오류는
    조용히 통과시키면 안 되므로 여기서는 예외가 맞다.
    """
    src = os.environ if env is None else env
    token = (src.get(TOKEN_ENV) or "").strip()
    if not token:
        raise TokenMissing(
            f"{TOKEN_ENV} 가 없다 — 토큰 없이 MCP HTTP 입구를 열지 않는다 (D150). "
            "NemoClaw 는 서버당 bearer 1개를 요구한다."
        )
    return token


def token_ok(header: str | None, token: str) -> bool:
    """`Authorization: Bearer <token>` 검사. 상수 시간 비교."""
    if not header:
        return False
    prefix = "bearer "
    if len(header) < len(prefix) or header[: len(prefix)].lower() != prefix:
        return False
    return secrets.compare_digest(header[len(prefix) :].strip(), token)


def build_app(token: str):
    """`server.py` 의 FastMCP 인스턴스에 bearer 검사를 씌운 ASGI 앱.

    import 는 함수 안에서 한다 — 토큰 검사가 서버 import(도구 22종 로딩)보다
    **먼저** 끝나야 "토큰 없으면 아무것도 안 뜬다" 가 실제로 성립한다.
    """
    from starlette.responses import JSONResponse

    from mcp_server.server import mcp

    mcp.settings.host = BIND_HOST
    mcp.settings.streamable_http_path = DEFAULT_PATH
    inner = mcp.streamable_http_app()

    async def app(scope, receive, send):
        if scope["type"] != "http":
            await inner(scope, receive, send)
            return
        header = None
        for k, v in scope.get("headers") or ():
            if k == b"authorization":
                header = v.decode("latin-1")
                break
        if not token_ok(header, token):
            # 본문에 원인을 적지 않는다 (D40·D131 — 실패 원인은 타입까지만).
            resp = JSONResponse({"error": "unauthorized"}, status_code=401)
            await resp(scope, receive, send)
            return
        await inner(scope, receive, send)

    return app


def main(argv: list[str] | None = None) -> int:
    try:
        token = read_token()
    except TokenMissing as exc:
        print(f"[실패] {exc}", file=sys.stderr)
        return 2

    port = int(os.environ.get(PORT_ENV) or DEFAULT_PORT)
    import uvicorn

    print(
        f"MCP streamable-http — http://{BIND_HOST}:{port}{DEFAULT_PATH} "
        f"(bearer 필수 · 프로필 {os.environ.get('MAINTQ_TOOLS_PROFILE') or 'core'})",
        flush=True,
    )
    uvicorn.run(build_app(token), host=BIND_HOST, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
