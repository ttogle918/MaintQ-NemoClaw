# ══════════════════════════════════════════════════════════════════════════════
# MaintQ — Northflank 배포용 Dockerfile
#
# 구조:  FastAPI 백엔드 + MCP subprocess (단일 컨테이너)
# DB:    SQLite — 영속 볼륨을 /app/data 에 마운트해야 한다
# 빌드:  docker build -t maintq .
# 실행:  docker run --rm -p 8000:8000 \
#          -e GEMINI_API_KEY=... \
#          -e MAINTQ_LLM_PROVIDER=gemini \
#          -e MAINTQ_LLM_MODEL=gemini-2.5-flash \
#          -v maintq-data:/app/data \
#          maintq
# ══════════════════════════════════════════════════════════════════════════════

# ── Stage 1: 의존성 설치 ─────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

# uv — pyproject.toml + uv.lock 기반 빠른 의존성 설치
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 의존성 레이어 캐시: pyproject.toml / uv.lock 이 바뀔 때만 재설치
COPY pyproject.toml uv.lock ./

# production 의존성만 설치 (dev · analysis 그룹 제외)
RUN uv sync --frozen --no-dev --no-group analysis


# ── Stage 2: 런타임 ──────────────────────────────────────────────────────────
FROM python:3.13-slim

WORKDIR /app

# venv 복사 — builder 에서 설치된 패키지만 가져온다
COPY --from=builder /app/.venv /app/.venv

# ── 애플리케이션 코드 ──
# backend + mcp_server 는 `from data import ...` 으로 data/ 의 Python 모듈을
# 공유한다 (D73). 그래서 data/ 도 함께 복사해야 한다.
COPY backend/     backend/
COPY mcp_server/  mcp_server/

# ── data/ — 런타임이 import 하는 Python 모듈 + 정적 데이터 ──
# backend/services 와 mcp_server/tools 가 `from data import maint_value`,
# `from data.rules import engine` 등으로 직접 참조한다.
# .dockerignore 가 data/raw, data/cache, *.db, data-analysis 등을 제외하므로
# 런타임에 필요한 파일만 들어간다.
COPY data/        data/

# ── data/maintq.db 는 볼륨 마운트로 들어온다 ──
# .dockerignore 가 *.db 를 제외하므로 이미지에 포함되지 않는다.
# Northflank: Volumes 탭에서 볼륨 생성 → 서비스에 /app/data 마운트
# 최초 배포 시: 컨테이너 안에서 seed.py 를 돌려 DB 를 초기화하거나,
#              로컬에서 만든 maintq.db 를 볼륨에 업로드한다.

# ── 환경 ──
ENV PATH="/app/.venv/bin:$PATH"
# 컨테이너 stdout 을 버퍼링 없이 즉시 플러시 (로그 유실 방지)
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Health check — Northflank 가 서비스 상태를 판단하는 엔드포인트
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
