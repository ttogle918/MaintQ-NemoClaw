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

from dotenv import load_dotenv

# .env 로드는 앱 진입점인 **여기 한 곳**에서, 그리고 **다른 backend.* import 보다 먼저**
# 한다 (D56). `override=False` 가 핵심 — **OS 환경변수가 우선**이고 .env 는 빈 곳만 채운다.
# 파일이 프로세스 환경을 조용히 덮으면 "어느 키로 돌았는지"를 디버깅할 수 없다.
# MCP 서브프로세스는 D42 의 `env={**os.environ}` 상속으로 같은 값을 본다.
#
# 🔴 순서가 실제로 중요하다 — 아래 `backend.routers` import 가 `backend.deps` →
# `backend.db` 를 연쇄로 끌어오는데, `backend/db.py` 의 `DATABASE_URL` 은 모듈
# import 시점에 `os.environ.get(...)` 으로 **한 번만** 평가되는 전역 상수다. `load_dotenv()`
# 를 이 import 들 뒤에 두면 `.env` 가 아직 안 실려 있는 상태로 `DATABASE_URL` 이 잘못된
# 기본값(`postgresql://localhost/maintq`, 포트 5432·자격증명 없음)으로 영구 고정되고,
# 이후 모든 요청의 `psycopg.connect()` 가 존재하지 않는 대상에 접속을 시도하며 Windows
# 에서 무한정 hang 한다 — 셸에 `DATABASE_URL` 이 직접 export 돼 있지 않으면 100% 재현된다
# (2026-08-24 세션, systematic-debugging 으로 근본원인 확정: py-spy 로 워커 스레드가
# `psycopg.connect` 안의 `select()` 에 멈춰 있는 것을 확인 → 최소 재현으로 import 순서
# 하나가 원인임을 격리).
load_dotenv(override=False)

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from backend import db  # noqa: E402
from backend.agent.mcp_client import McpClient  # noqa: E402
from backend.routers import (  # noqa: E402
    approvals,
    asset_monitoring,
    chat,
    decisions,
    disposal,
    equipment,
    hotspot_status,
    inventory,
    maint_value,
    po,
    repairs,
    session,
    a2a,
)

logger = logging.getLogger(__name__)

# MCP 서브프로세스 기동을 끄는 탈출구. 라우터 계약만 보는 회귀(api_contract)가
# 매번 stdio 서버를 띄우지 않아도 되게 한다. 기본값은 켜짐 — 데모·개발에서
# 끄는 걸 잊으면 도구가 통째로 죽은 걸 늦게 알아차린다.
MCP_AUTOSTART = (os.environ.get("MAINTQ_MCP_AUTOSTART") or "1") not in ("0", "false", "False")


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
        # 커넥션 풀도 여기서 닫는다 (D127). `atexit` 에도 걸려 있지만, lifespan 이
        # 정상 경로라 여기서 먼저 닫아야 재기동(reload) 시 커넥션이 새지 않는다.
        db.close_pool()


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

# `or` 가 핵심이다 — `.get(키, 기본값)` 은 **빈 문자열을 "설정됨"으로** 본다.
# .env.example 을 복사하면 `MAINTQ_CORS_ORIGINS=` 처럼 빈 키가 생기고, D56 의
# load_dotenv 가 그걸 빈 문자열로 os.environ 에 넣는다 — 그 순간 기본 범위(3000~3005)가
# 통째로 사라져 브라우저 fetch 가 전부 CORS 로 죽는다 (Stage 1 브라우저 검증에서 실측).
# D56 취지는 ".env 는 빈 곳만 채운다"이므로 빈 값은 미설정과 같아야 한다.
ALLOWED_ORIGINS = [
    o.strip()
    for o in (os.environ.get("MAINTQ_CORS_ORIGINS") or _DEFAULT_ORIGINS).split(",")
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
app.include_router(disposal.router)
app.include_router(decisions.router)
app.include_router(approvals.router)
app.include_router(maint_value.router)
app.include_router(repairs.router)
app.include_router(inventory.router)
app.include_router(hotspot_status.router)
app.include_router(asset_monitoring.router)
app.include_router(session.router)
app.include_router(a2a.router)



@app.get("/health")
async def health() -> dict:
    # mcp 는 **추가 필드**다 — 기존 `status: ok` 계약은 그대로 둔다 (sp3 가 이 경로로 기동을 기다린다).
    mcp: McpClient | None = getattr(app.state, "mcp", None)
    ready = bool(mcp and mcp.ready)
    # ★ `tools` 가 정본이다 (D69). 프로파일은 **자식 프로세스(MCP 서버)** 가 해석하므로
    #   backend 가 읽은 env 값은 "실제로 무엇이 등록됐는가"의 답이 아니다 — 자식에게
    #   env 가 안 넘어갔거나 서버가 구버전이면 두 값이 갈린다. 그래서 실측을 싣고
    #   `tools_profile` 은 **참고값**으로만 둔다. 미기동이면 개수를 0 이 아니라 null 로
    #   준다 — 0 은 "도구가 없다"는 사실 주장이 되고, 실제로는 모르는 상태다.
    return {
        "status": "ok",
        "mcp": ready,
        "tools": len(await mcp.list_tools()) if ready else None,
        "tools_profile": os.environ.get("MAINTQ_TOOLS_PROFILE") or "core",
    }
