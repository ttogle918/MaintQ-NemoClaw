# ══════════════════════════════════════════════════════════════════════════════
# MaintQ — GCP Cloud Run 배포용 Dockerfile (2026-08-24 정정 — 배포 타깃을 Northflank에서
# GCP Cloud Run + Supabase(Postgres+pgvector) + Vercel/Netlify(frontend)로 확정했다,
# docs/13_DEPLOYMENT.md 참고. 아래 빌드·실행·최초 배포 절차 자체는 플랫폼 무관이라 그대로 유효.
#
# 구조:  FastAPI 백엔드 + MCP subprocess (단일 컨테이너)
# DB:    Postgres (Sprint 16 MQ-1614 — SQLite→Postgres 전환 완료). 컨테이너는
#        DB를 담지 않는다 — DATABASE_URL 로 외부 Postgres(Supabase 등 관리형,
#        또는 자체 운영)에 접속만 한다. 볼륨 마운트 불필요.
#          예) DATABASE_URL=postgresql://user:pass@host:5432/dbname?sslmode=require
#        Supabase 를 쓸 경우 **Session pooler(포트 5432, 세션 고정)** 또는 직결을
#        권장한다 — Transaction pooler(6543)를 쓰려면 mcp_server/db.py 의 D10 쓰기
#        가드가 `SET LOCAL` 로 트랜잭션 범위임을 이미 확인했지만(Sprint 16 4차
#        체크포인트), 검증되지 않은 다른 세션 상태 의존이 코드에 새로 생기지 않게
#        주의할 것.
# 벡터:  RAG(`mcp_server/rag.py`)는 현재 **키워드 검색만 활성**이다(D51 — 임베딩·
#        벡터스토어는 data/analysis/rag_sizing.md 실측 후 사람이 결정하기 전까지
#        의도적으로 비활성). 인덱스 원본은 data/extracted/manual_chunks.jsonl 파일이고
#        이 이미지에 COPY 로 그대로 들어간다 — DB 접속과 무관하게 동작한다. 나중에
#        dense 검색을 켤 때는 Postgres 에 pgvector 확장(Supabase 기본 제공,
#        로컬 개발은 docker-compose.yml 의 pgvector/pgvector:pg15)을 쓰는 것이 기본
#        방향이다 — 별도 벡터 DB 서비스를 새로 들이지 않는다. 스키마(`manual_chunks`
#        테이블)는 scripts/migrate_vectors.py 가 이미 준비해 뒀지만 아직 검색 코드가
#        안 읽는다.
# 빌드:  docker build -t maintq .
# 실행:  docker run --rm -p 8000:8000 \
#          -e DATABASE_URL=postgresql://user:pass@host:5432/dbname?sslmode=require \
#          -e GEMINI_API_KEY=... \
#          -e MAINTQ_LLM_PROVIDER=gemini \
#          -e MAINTQ_LLM_MODEL=gemini-2.5-flash \
#          maintq
#
# 최초 배포 시 (컨테이너가 대신 해주지 않는다 — DATABASE_URL 을 가리키는 Postgres에
# 미리 적용해야 한다):
#   1) psql "$DATABASE_URL" -f scripts/postgres_schema.sql
#   2) psql "$DATABASE_URL" -f scripts/postgres_guards.sql     (D10 쓰기 가드)
#   3) DATABASE_URL=... uv run python data/seed.py --with-error-codes
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

# ── DB는 이제 컨테이너 밖 Postgres다 — 볼륨 마운트 불필요 ──
# data/ 는 여전히 통째로 COPY한다: backend/mcp_server가 공유하는 Python 모듈(D73)
# 외에도 RAG 키워드 검색이 읽는 data/extracted/manual_chunks.jsonl 이 런타임에
# 필요하다(위 "벡터" 절 참고 — 이 검색은 DB 접속 없이 로컬 파일만으로 동작한다).
# .dockerignore 가 data/raw(매뉴얼 원본 PDF)·data/cache(LLM 캐시)는 계속 제외한다.
# 최초 배포 시 스키마·시드 적용 절차는 위 "최초 배포 시" 절 참고.

# ── 환경 ──
ENV PATH="/app/.venv/bin:$PATH"
# 컨테이너 stdout 을 버퍼링 없이 즉시 플러시 (로그 유실 방지)
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Health check — Cloud Run 이 서비스 상태를 판단하는 엔드포인트
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
