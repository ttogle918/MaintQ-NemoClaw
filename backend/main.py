# -*- coding: utf-8 -*-
"""FastAPI 백엔드 (SP3 골격).

지금은 SSE 스트리밍 규격만 검증하는 최소 형태다. 에이전트 루프·MCP 연결은 M2 에서.
실행:  uv run uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import chat, equipment, po

app = FastAPI(title="MaintQ API", version="0.1.0")

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
    return {"status": "ok"}
