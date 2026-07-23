# -*- coding: utf-8 -*-
"""FastAPI 백엔드 (SP3 골격).

지금은 SSE 스트리밍 규격만 검증하는 최소 형태다. 에이전트 루프·MCP 연결은 M2 에서.
실행:  uv run uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import chat

app = FastAPI(title="MaintQ API", version="0.1.0")

# 프론트(Next.js dev)는 3000 포트. 목업 단계라 로컬 오리진만 허용한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
