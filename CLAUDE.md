# MaintQ — 프로젝트 메모리

설비 진단부터 부품 발주까지 연결하는 B2B 제조 보전 AI 에이전트.
Q 시리즈 3번째 (FinAllQ·InsuQ·MaintQ). 주제는 **도구 오케스트레이션**.

## 반드시 먼저 읽을 문서

작업 전 관련 문서를 확인할 것. 설계와 다른 구현을 하려면 먼저 `docs/10_DECISIONS.md`에 결정을 추가하고 진행:

- `docs/README.md` — 문서 지도. 어느 문서를 열지 모를 때 먼저
- `docs/00_MVP_SCOPE.md` — **반드시 구현할 기능 목록**. 착수 전 "이게 MVP인가 백로그인가" 판단
- `docs/10_DECISIONS.md` — 설계 결정 D1~D67. **여기 있는 결정과 충돌하는 코드를 쓰지 말 것**
- `docs/02_SCENARIOS.md` — S1~S4. 모든 기능은 이 시나리오 중 하나에 복무해야 함
- `docs/04_MCP_TOOLS.md` — 도구 입출력 계약. 임의 변경 금지
- `docs/05_DB_SCHEMA.md` — 테이블 10절(실제 11개) + 시드 케이스 맵
- `docs/06_REPO_API.md` — 폴더 구조·API·SSE 이벤트 규격
- `docs/09_RUNTIME.md` — 시퀀스·루프 상한·장애 모드

## 절대 규칙 (위반 금지)

1. **MCP 도구는 po_drafts에 draft INSERT만 가능.** UPDATE 코드를 도구에 추가하지 말 것. 상태 전이는 backend/routers/po.py의 사람 전용 API만 (D10)
2. **에러코드 정의 조회는 lookup(exact match), 절차 서술은 RAG.** 이 경계를 흐리는 코드 금지 (D1)
3. **점검 절차 출력에는 안전 경고 필수** — safety-guardrail 스킬 규칙 준수. 안전 문구는 매뉴얼 근거(페이지) 없이 생성 금지
4. **model 파라미터는 enum('iG5A','S100') 강제** (D6, D13)
5. **`data/raw/`는 읽기 전용** — 매뉴얼 원본 수정 금지, git에도 올리지 않음 (.gitignore 확인)
6. **미지 에러코드에 유사 코드 추측 금지** — not_found면 S4 흐름 (환각률 0% 목표)

## 기술 스택·컨벤션

- Python 3.11+, FastAPI, SQLite(목업), MCP 서버는 backend와 프로세스 분리 (D15)
- 포매터: ruff (PostToolUse 훅으로 자동 실행 — .claude/settings.json)
- 도구는 `mcp_server/tools/` 파일당 1개, status 필드로 실패 반환 (예외 던지지 말 것, D9)
- SSE 이벤트는 token / tool_call / tool_result / block 4종 고정 (D14·D22)
- 커밋 메시지: 한국어 OK, 접두어 `[M1]`~`[M4]` 마일스톤 표기

## 작업 워크플로우 (커맨드)

| 커맨드 | 하는 일 |
|---|---|
| `/sprint N` | 계획만 수립 (PM 배치 → tool-builder 현실성 평가) → `docs/sprints/sprint-N.md`. **코드 안 짬** |
| `/stage M` | 스테이지 실행: tool-builder 병렬 → eval-runner 회귀 → reviewer 게이트 → 커밋 → 수동 체크리스트 |
| `/checkpoint` | 중단 시점 저장 (`sprint-N-wip.md`) |
| `/done` | 세션 마무리 — 로그(`docs/sessions/`) + **D 범위 표기 정합성 점검** |

## 회귀 스위트

계약이 깨지면 여기서 먼저 잡힌다. 코드 변경 후 반드시 실행 (`/stage`가 자동 호출).

- `data/seed.py` — 시드 케이스 맵 자가 검증
- `spikes/` — sp2_mcp_roundtrip · write_tool_contract · api_contract · sp3_sse_events ·
  trace_persist · mcp_client_contract · prompt_rules · lookup_contract · citation_render ·
  db_concurrency · rag_contract · agent_loop_contract · eval_score_contract · s4_smoke ·
  llm_provider_contract
- 정적: `ruff check` · `tsc --noEmit` · `next build`

건수는 러너 출력이 기준이다. **직전 실행보다 줄었다면 테스트가 사라진 것** — 통과했다고 넘기지 말 것.

## 마일스톤

`M1` 데이터 준비 → `M2` 코어(MCP 도구·백엔드·에이전트 루프·trace) → `M3` UI → `M4` 평가·마무리.
단계별 내용은 `docs/00_MVP_SCOPE.md §구현 순서`.

## 지금 어디까지 왔는지 확인하는 법

진행 상태는 이 문서에 적지 않는다(금방 낡는다). 세션 시작 시 아래를 본다:

| 알고 싶은 것 | 어디를 보나 |
|---|---|
| 전체 진행 상태·다음 액션 | `docs/README.md` 맨 아래 "진행 상태" |
| 직전 세션에서 무슨 일이 있었나 | `docs/sessions/` 최신 파일 (특히 "다음 세션" 절) |
| 중단된 작업 재개 | `docs/sprints/sprint-N-wip.md` |
| **사람이 해야 할 일** | `TODO_직접할일.md` — Claude가 대신 처리하지 말 것 (매뉴얼 다운로드, related_parts 최종 검수, 안전 문구 승인) |
| 최근 커밋 흐름 | `git log --oneline -10` (접두어로 마일스톤 확인) |
