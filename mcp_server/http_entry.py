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
#: 기본 바인딩은 loopback. 샌드박스 안에서 돌 때는 이것만으로 충분하다 —
#: 바깥으로 나가는 길이 `openshell service expose` 하나뿐이기 때문이다.
BIND_HOST = "127.0.0.1"

TOKEN_ENV = "MAINTQ_MCP_TOKEN"
PORT_ENV = "MAINTQ_MCP_HTTP_PORT"
BIND_ENV = "MAINTQ_MCP_BIND"
TLS_CERT_ENV = "MAINTQ_MCP_TLS_CERT"
TLS_KEY_ENV = "MAINTQ_MCP_TLS_KEY"
ALLOWED_HOSTS_ENV = "MAINTQ_MCP_ALLOWED_HOSTS"

#: 기본 허용 Host. MCP SDK 의 DNS 리바인딩 보호(`enable_dns_rebinding_protection`)는
#: **끄지 않는다** — 목록에 더할 뿐이다. 실측: 에이전트 샌드박스가 `host.openshell.internal`
#: 로 부르면 SDK 가 `421 Invalid Host header` 를 낸다. 그 보호를 끄면 브라우저가 로컬
#: MCP 를 재바인딩 공격으로 부를 수 있게 되므로, **필요한 이름만 명시**한다.
DEFAULT_ALLOWED_HOSTS = ("127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*")

#: loopback 으로 간주하는 주소. 이 밖으로 바인드하면 평문이 랜에 노출되므로 TLS 를 의무화한다.
LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


class TokenMissing(RuntimeError):
    """`MAINTQ_MCP_TOKEN` 부재 — 기동하지 않는다."""


class TlsRequired(RuntimeError):
    """loopback 밖 바인딩인데 TLS 인증서가 없다 — 기동하지 않는다."""


def resolve_bind(env: dict[str, str] | None = None) -> tuple[str, str | None, str | None]:
    """(bind host, cert, key) 를 돌려준다.

    **loopback 밖으로 바인드하려면 TLS 가 필수다.** 호스트에서 돌릴 때(에이전트
    샌드박스가 `host.openshell.internal` 로 닿는 배선) 평문으로 열리면 같은 망의
    아무나 bearer 없이 스캔할 수 있고, NemoClaw 도 `https://` 아닌 URL 을 거부한다
    (*"Authenticated MCP server URLs must use https:// so the configured MCP client
    uses TLS when OpenShell forwards credential-bearing requests"*).

    기본값은 그대로 loopback 이라 샌드박스 안 실행은 아무것도 바뀌지 않는다.
    """
    src = os.environ if env is None else env
    host = (src.get(BIND_ENV) or BIND_HOST).strip() or BIND_HOST
    cert = (src.get(TLS_CERT_ENV) or "").strip() or None
    key = (src.get(TLS_KEY_ENV) or "").strip() or None
    if host not in LOOPBACK and not (cert and key):
        raise TlsRequired(
            f"{BIND_ENV}={host!r} 는 loopback 이 아니다 — {TLS_CERT_ENV}/{TLS_KEY_ENV} 없이 열지 않는다 (D150). "
            "평문으로 열면 bearer 가 망에 그대로 흐르고, NemoClaw 도 https 가 아닌 URL 을 거부한다."
        )
    return host, cert, key


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


def allowed_hosts(env: dict[str, str] | None = None) -> list[str]:
    """허용 Host 목록. env 로 **추가**할 수 있고, 기본값을 지우지는 못한다."""
    src = os.environ if env is None else env
    extra = [h.strip() for h in (src.get(ALLOWED_HOSTS_ENV) or "").split(",") if h.strip()]
    out = list(DEFAULT_ALLOWED_HOSTS)
    for h in extra:
        if h not in out:
            out.append(h)
        port_glob = f"{h}:*"
        if ":" not in h and port_glob not in out:
            out.append(port_glob)
    return out


def transport_security():
    """DNS 리바인딩 보호는 **켠 채로** 허용 목록만 넓힌다."""
    from mcp.server.transport_security import TransportSecuritySettings

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts(),
        allowed_origins=[],
    )


def build_app(token: str):
    """`server.py` 의 FastMCP 인스턴스에 bearer 검사를 씌운 ASGI 앱.

    import 는 함수 안에서 한다 — 토큰 검사가 서버 import(도구 22종 로딩)보다
    **먼저** 끝나야 "토큰 없으면 아무것도 안 뜬다" 가 실제로 성립한다.
    """
    from starlette.responses import JSONResponse

    from mcp_server.server import mcp

    mcp.settings.streamable_http_path = DEFAULT_PATH
    mcp.settings.transport_security = transport_security()
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
        host, cert, key = resolve_bind()
    except (TokenMissing, TlsRequired) as exc:
        print(f"[실패] {exc}", file=sys.stderr)
        return 2

    port = int(os.environ.get(PORT_ENV) or DEFAULT_PORT)
    import uvicorn

    scheme = "https" if cert else "http"
    print(
        f"MCP streamable-http — {scheme}://{host}:{port}{DEFAULT_PATH} "
        f"(bearer 필수 · 프로필 {os.environ.get('MAINTQ_TOOLS_PROFILE') or 'core'})",
        flush=True,
    )
    uvicorn.run(
        build_app(token),
        host=host,
        port=port,
        log_level="info",
        ssl_certfile=cert,
        ssl_keyfile=key,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
