#!/usr/bin/env bash
# MaintQ 백엔드(+MCP stdio 자식)를 GCP Cloud Run 에 배포한다 — docs/13_DEPLOYMENT.md §5, D159.
#
# 사용:
#   SUPABASE_DATABASE_URL='postgresql://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require' \
#   MAINTQ_DEMO_TOKEN='<공유 토큰>' \
#   FRONTEND_ORIGIN='https://<site>.netlify.app' \
#   deploy/cloudrun/deploy.sh
#
# ⚠ Supabase 는 **Session pooler(5432)** 문자열을 쓴다 — 직결(db.<ref>.supabase.co)은 IPv6 전용이라
#   Cloud Run(IPv4 egress)에서 닿지 않고, Transaction pooler(6543)는 D10 가드의 세션 GUC 검증이 없다(§3).
# LLM·임베딩 설정(NVIDIA_API_KEY 등)은 레포 루트 .env 에서 읽는다. 값은 커밋되지 않는 임시 파일로만 넘긴다.
set -euo pipefail

cd "$(dirname "$0")/../.."

: "${SUPABASE_DATABASE_URL:?Supabase Session pooler 연결 문자열이 필요합니다}"
: "${MAINTQ_DEMO_TOKEN:?공개 배포는 데모 토큰 게이트(D159) 없이 하지 않습니다}"
FRONTEND_ORIGIN="${FRONTEND_ORIGIN:-}"
SERVICE="${SERVICE:-maintq-backend}"
REGION="${REGION:-asia-northeast3}"
PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
TOOLS_PROFILE="${MAINTQ_TOOLS_PROFILE:-core}"

env_from_dotenv() { grep -m1 "^$1=" .env 2>/dev/null | cut -d= -f2- || true; }

NVIDIA_API_KEY="$(env_from_dotenv NVIDIA_API_KEY)"
[ -n "$NVIDIA_API_KEY" ] || { echo "✗ .env 에 NVIDIA_API_KEY 가 없습니다" >&2; exit 1; }

ENV_FILE="$(mktemp)"
trap 'rm -f "$ENV_FILE"' EXIT
yaml() { printf '%s: %s\n' "$1" "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$2")" >> "$ENV_FILE"; }

yaml DATABASE_URL          "$SUPABASE_DATABASE_URL"
yaml MAINTQ_DEMO_TOKEN     "$MAINTQ_DEMO_TOKEN"
yaml MAINTQ_LLM_PROVIDER   "$(env_from_dotenv MAINTQ_LLM_PROVIDER)"
yaml MAINTQ_LLM_MODEL      "$(env_from_dotenv MAINTQ_LLM_MODEL)"
yaml NVIDIA_API_KEY        "$NVIDIA_API_KEY"
yaml NVIDIA_EMBED_MODEL    "$(env_from_dotenv NVIDIA_EMBED_MODEL)"
yaml MAINTQ_MCP_AUTOSTART  "1"
yaml MAINTQ_TOOLS_PROFILE  "$TOOLS_PROFILE"
# MCP 확장 도구가 같은 컨테이너의 백엔드 REST 를 부른다 — loopback 이라 토큰 게이트 면제(D159)
yaml MAINTQ_BACKEND_BASE_URL "http://localhost:8000"
# 빈 값이면 main.py 가 로컬 개발 기본 범위로 떨어진다 — 배포에서는 프론트 도메인을 반드시 넣는다
[ -n "$FRONTEND_ORIGIN" ] && yaml MAINTQ_CORS_ORIGINS "$FRONTEND_ORIGIN"

echo "▶ $PROJECT / $REGION / $SERVICE (tools=$TOOLS_PROFILE, cors=${FRONTEND_ORIGIN:-<미설정>})"
gcloud run deploy "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --source . \
  --allow-unauthenticated \
  --port 8000 \
  --memory 1Gi \
  --cpu 1 \
  --timeout 900 \
  --min-instances 0 \
  --max-instances 2 \
  --env-vars-file "$ENV_FILE"

URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format='value(status.url)')"
echo "✓ 배포 완료: $URL"
echo "  헬스체크: curl -s $URL/health"
echo "  프론트 빌드 변수: NEXT_PUBLIC_API_BASE=$URL"
