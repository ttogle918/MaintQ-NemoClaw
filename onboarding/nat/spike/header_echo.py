# -*- coding: utf-8 -*-
"""ⓘ 헤더 도달 확인용 최소 HTTP 서버 (MQ-1901).

NAT `mcp_client`(streamable-http)가 실제로 `Authorization`·`X-User` 헤더를 실어
보내는지만 보면 되므로, MCP 프로토콜을 흉내 낼 필요가 없다 — 받은 요청 헤더를
stdout 에 한 줄씩 찍고 MCP 초기화가 실패하도록 빈 몸통 202 를 돌려준다(NAT 쪽은
"initialize 실패"로 끝나도 상관없다 — 우리가 보려는 것은 헤더뿐이다).

MaintQ 코드베이스에는 디버그 경로를 만들지 않는다 — 이 스크립트는 `onboarding/nat`
스파이크 전용이고 레포 본 서버(`mcp_server/`)를 건드리지 않는다.

실행: uv run python spike/header_echo.py [port]
"""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class EchoHandler(BaseHTTPRequestHandler):
    def _echo(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        print(f"--- {self.command} {self.path} ---", flush=True)
        for k, v in self.headers.items():
            print(f"{k.lower()}: {v}", flush=True)
        print("---", flush=True)
        # MCP 초기화는 여기서 성립하지 않는다 — 헤더만 보면 된다.
        self.send_response(202)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error":"header_echo spike stub - not a real MCP server"}')

    def do_POST(self) -> None:
        self._echo()

    def do_GET(self) -> None:
        self._echo()

    def do_DELETE(self) -> None:
        self._echo()

    def log_message(self, fmt: str, *args) -> None:  # noqa: A002 - stdlib signature
        pass


def main(argv: list[str]) -> int:
    port = int(argv[1]) if len(argv) > 1 else 8799
    server = HTTPServer(("127.0.0.1", port), EchoHandler)
    print(f"header_echo listening on 127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
