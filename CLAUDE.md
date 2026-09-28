# MaintQ

설비 진단부터 부품 발주까지 잇는 B2B 제조 보전 AI 에이전트. 주제는 **도구 오케스트레이션**.

**작업 전 읽을 문서** — `docs/README.md`(문서 지도) · `docs/00_MVP_SCOPE.md`(MVP 범위) · `docs/10_DECISIONS.md`(설계 결정 D1~D159, 충돌하는 코드 금지 · 설계와 다르게 가려면 결정부터 추가) · `docs/04_MCP_TOOLS.md`(도구 계약: 코어 7 + 확장 15 + 온보딩 3, 임의 변경 금지)

## 절대 규칙
1. MCP 도구의 쓰기는 `po_drafts`·`decisions`·`repair_records` draft INSERT와 온보딩 스테이징 INSERT뿐이다. UPDATE 금지. 상태 전이는 사람 전용 API(`backend/routers/{po,decisions,repairs}.py`)만 (D10·D81·D154). `get_document_facts`는 읽기 전용(D125), `generate_disposal_document`에 `override` 계열 파라미터 추가 금지. 쓰기 커넥션은 대상 테이블별로 분리한다.
2. 에러코드 정의는 lookup(exact match), 절차 서술은 RAG. 경계를 흐리지 않는다 (D1).
3. 점검 절차에는 안전 경고 필수, 매뉴얼 근거(페이지) 없이 안전 문구 생성 금지 (`safety-guardrail` 스킬).
4. `model` 은 enum `iG5A·S100·IE5·HV600` 강제. HV600 은 DB 온보딩 승격 상태로 게이트한다 (D6·D146).
5. `data/raw/` 읽기 전용. 예외는 `data/raw/external/*.json` 이며 `data/external/store.py` 로만 기입 (D103).
6. 미지 에러코드에 유사 코드를 추측하지 않는다. `not_found` 면 S4 흐름.

## 컨벤션
Python 3.11+ · FastAPI · Postgres · MCP 서버는 backend 와 프로세스 분리(D15). 도구는 `mcp_server/tools/` 파일당 1개, 실패는 예외 대신 `status` 필드로 반환(D9), 필수 파라미터에 기본값 금지(D80). 확장 도구는 `MAINTQ_TOOLS_PROFILE=full` 에서만 등록(기본 `core`). SSE 이벤트는 token/tool_call/tool_result/block 4종 고정. 린터는 `ruff check`(포매터 아님). 커밋 접두어 `[M1]`~`[M4]`.

## 회귀 테스트 — 코드 변경 후 실행
모든 명령 앞에 `DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)"` 를 붙인다. 없으면 5432 포트로 새어 무한 대기한다.
- pytest(412건): `uv run --with pytest --with pytest-asyncio python -m pytest data backend mcp_server -q`
- 시드: `uv run python data/seed.py --with-error-codes` — 옵션 없이 돌리면 `error_codes` 가 0행이 된다. `--today` 금지. 온보딩 스테이징 5테이블도 비우므로 데모 전 재시드 금지. 이후 `error_codes` 는 70행이어야 한다.
- 계약 스파이크: `uv run python spikes/<name>.py`. `law_fetch_contract` ⓚ 1건은 알려진 오탐이다. 그 외 실패는 진짜 회귀이고, 실패한 스위트는 단독 재실행해 확인한다.
- 건수는 러너 출력이 기준이며, 직전보다 줄었다면 테스트가 사라진 것이다.
