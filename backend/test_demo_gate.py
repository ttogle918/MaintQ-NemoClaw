# -*- coding: utf-8 -*-
"""데모 토큰 게이트(D159) — DB 불필요. 미니 앱에 게이트+CORS 를 `main.py` 와 같은 순서로 얹는다."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from backend.demo_gate import DemoTokenGate

ORIGIN = "https://maintq.example"


def _client(token: str, client_host: str = "testclient") -> TestClient:
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/po")
    def po():
        return {"items": []}

    app.add_middleware(DemoTokenGate, token=token)
    app.add_middleware(CORSMiddleware, allow_origins=[ORIGIN], allow_methods=["*"], allow_headers=["*"])
    return TestClient(app, client=(client_host, 50000))


def test_unset_token_is_noop():
    assert _client("").get("/api/po").status_code == 200


def test_missing_token_rejected_with_cors_header():
    r = _client("s3cret").get("/api/po", headers={"Origin": ORIGIN})
    assert r.status_code == 401
    assert r.json() == {"detail": "demo_token_required"}
    # 게이트가 CORS 안쪽이라야 브라우저가 401 본문을 읽는다
    assert r.headers.get("access-control-allow-origin") == ORIGIN


def test_wrong_token_rejected():
    assert _client("s3cret").get("/api/po", headers={"X-Demo-Token": "nope"}).status_code == 401


def test_right_token_passes():
    assert _client("s3cret").get("/api/po", headers={"X-Demo-Token": "s3cret"}).status_code == 200


def test_health_and_preflight_exempt():
    c = _client("s3cret")
    assert c.get("/health").status_code == 200
    pre = c.options(
        "/api/po",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "x-demo-token"},
    )
    assert pre.status_code == 200


def test_loopback_client_exempt():
    # 같은 컨테이너의 MCP 자식이 A2A 경로를 부를 때 (MAINTQ_BACKEND_BASE_URL=localhost)
    assert _client("s3cret", client_host="127.0.0.1").get("/api/po").status_code == 200
