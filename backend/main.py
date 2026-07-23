# -*- coding: utf-8 -*-
"""FastAPI 백엔드.

MCP 세션은 **lifespan 이 단독으로 소유**한다 (D42) — 라우터는 `request.app.state.mcp`
로 받아 쓰기만 한다. 에이전트 루프는 M2(MQ-306).
실행:  uv run uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.agent.mcp_client import McpClient
from backend.routers import chat, equipment, po

logger = logging.getLogger(__name__)

# MCP 서브프로세스 기동을 끄는 탈출구. 라우터 계약만 보는 회귀(api_contract)가
# 매번 stdio 서버를 띄우지 않아도 되게 한다. 기본값은 켜짐 — 데모·개발에서
# 끄는 걸 잊으면 도구가 통째로 죽은 걸 늦게 알아차린다.
MCP_AUTOSTART = os.environ.get("MAINTQ_MCP_AUTOSTART", "1") not in ("0", "false", "False")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """MCP 세션의 수명은 여기 하나뿐이다 (D42).

    라우터·스트리밍 제너레이터는 세션을 **열지 않고** `request.app.state.mcp` 로 받아
    `call()` 만 한다. 제너레이터 안에서 stdio 세션을 열면 클라이언트 조기 종료 시
    cancel scope 가 다른 태스크에서 닫히며 무관한 태스크까지 취소된다 (실측).

    기동 실패는 앱을 죽이지 않는다 — 도구 서버가 없어도 승인 큐(사람 API)는 떠야 한다.
    이때 `call()` 이 `status:"error"` 를 돌려주고 09_RUNTIME §3 대로 안내된다.
    """
    client = McpClient()
    app.state.mcp = client

    if MCP_AUTOSTART:
        if not await client.start():
            logger.warning("MCP 세션 없이 기동합니다 — 도구 호출은 status:error 로 응답합니다")
    try:
        yield
    finally:
        await client.stop()


app = FastAPI(title="MaintQ API", version="0.1.0", lifespan=lifespan)

# 목업 단계라 로컬 오리진만 허용한다.
#
# 포트를 하나로 박아두면 그 포트가 다른 프로젝트에 물려 있을 때 바로 막힌다 (실제로 3000 이
# 그랬다). 프론트 포트는 3002 로 고정하되(package.json), CORS 는 **범위로 열어** 포트를
# 한 칸 옮겨도 백엔드를 건드릴 일이 없게 한다. 자동 할당은 하지 않는다 —
# 포트가 매번 바뀌면 API_BASE·문서·데모 스크립트가 전부 흔들린다.
DEV_PORTS = range(3000, 3006)
_DEFAULT_ORIGINS = ",".join(
    f"http://{host}:{port}" for port in DEV_PORTS for host in ("localhost", "127.0.0.1")
)

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("MAINTQ_CORS_ORIGINS", _DEFAULT_ORIGINS).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(po.router)
app.include_router(equipment.router)


@app.get("/health")
def health() -> dict:
    # mcp 는 **추가 필드**다 — 기존 `status: ok` 계약은 그대로 둔다 (sp3 가 이 경로로 기동을 기다린다).
    mcp: McpClient | None = getattr(app.state, "mcp", None)
    return {"status": "ok", "mcp": bool(mcp and mcp.ready)}
