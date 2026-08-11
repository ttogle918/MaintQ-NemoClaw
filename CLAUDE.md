# MaintQ — 프로젝트 메모리

설비 진단부터 부품 발주까지 연결하는 B2B 제조 보전 AI 에이전트.
주제는 **도구 오케스트레이션**.

## 반드시 먼저 읽을 문서

작업 전 관련 문서를 확인할 것. 설계와 다른 구현을 하려면 먼저 `docs/10_DECISIONS.md`에 결정을 추가하고 진행:

- `docs/README.md` — 문서 지도. 어느 문서를 열지 모를 때 먼저
- `docs/00_MVP_SCOPE.md` — **반드시 구현할 기능 목록**. 착수 전 "이게 MVP인가 백로그인가" 판단
- `docs/10_DECISIONS.md` — 설계 결정 **D1~D88**. **여기 있는 결정과 충돌하는 코드를 쓰지 말 것**
- `docs/02_SCENARIOS.md` — S1~S4. 모든 기능은 이 시나리오 중 하나에 복무해야 함
- `docs/04_MCP_TOOLS.md` — 도구 입출력 계약(코어 7종 §1~§7 + **확장 8종** §8~§15). 임의 변경 금지
- `docs/05_DB_SCHEMA.md` — 테이블 **17절(실제 18개)** + 시드 케이스 맵
  (절 번호는 `§1`~`§9`+`§1-B` 로 10절, Sprint 6 이 `§11`~`§17` 로 이어받는다 — **`§10` 은 존재하지 않는다**.
   `§7` 이 `suppliers`·`supplier_parts` 두 테이블을 함께 다뤄 절 수보다 테이블이 1개 많다)
- `docs/06_REPO_API.md` — 폴더 구조·API·SSE 이벤트 규격
- `docs/09_RUNTIME.md` — 시퀀스·루프 상한·장애 모드

## 절대 규칙 (위반 금지)

1. **MCP 도구는 `po_drafts`·`decisions` 에 draft INSERT만 가능.** UPDATE 코드를 도구에 추가하지 말 것.
   상태 전이는 사람 전용 API만 — `backend/routers/po.py`(발주) · `backend/routers/decisions.py`(처분) (D10·D81)
   - 쓰기 도구는 **2종**: `create_po_draft` · `generate_disposal_document`. 커넥션도 분리한다
     (`db.draft_writer()` / `db.decision_writer()`) — 섞으면 TEMP TRIGGER 잠금이 사라진다
   - `generate_disposal_document` 에 `override`·`override_reason`·`reviewed_by` 파라미터를 **추가하지 말 것** (D81)
2. **에러코드 정의 조회는 lookup(exact match), 절차 서술은 RAG.** 이 경계를 흐리는 코드 금지 (D1)
3. **점검 절차 출력에는 안전 경고 필수** — safety-guardrail 스킬 규칙 준수. 안전 문구는 매뉴얼 근거(페이지) 없이 생성 금지
4. **model 파라미터는 enum('iG5A','S100') 강제** (D6, D13)
5. **`data/raw/`는 읽기 전용** — 매뉴얼 원본 수정 금지, git에도 올리지 않음 (.gitignore 확인)
6. **미지 에러코드에 유사 코드 추측 금지** — not_found면 S4 흐름 (환각률 0% 목표)

## 기술 스택·컨벤션

- Python 3.11+, FastAPI, SQLite(목업), MCP 서버는 backend와 프로세스 분리 (D15)
- 포매터: ruff (PostToolUse 훅으로 자동 실행 — .claude/settings.json)
- 도구는 `mcp_server/tools/` 파일당 1개, status 필드로 실패 반환 (예외 던지지 말 것, D9)
  - **필수 파라미터에 기본값을 두지 않는다** (D80) — 인자 누락은 MCP 스키마가 앞단에서 막는다. D9 는 도구 **로직**의 실패에 대한 규칙이다
  - 확장 **8종**은 `MAINTQ_TOOLS_PROFILE=full` 에서만 등록된다. **기본은 `core`** (D69·**D88** — 평가는 `core` 에서만 인정)
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
  ⚠ 실행 커맨드: **`uv run python data/seed.py --with-error-codes`**
  **맨몸으로 돌리면 `error_codes` 가 0행으로 리셋된다** (D33 — 사람 승인 전 미적재가 기본).
  그 상태에서는 `api_contract ②-b` 가 FAIL 하고, **평가를 돌리면 전 문항 lookup 이
  `catalog_not_loaded` 로 떨어져 결과가 통째로 무의미해진다.**
  ⛔ `--today` 로 날짜를 핀하지 말 것 — 시드는 실행일 기준 상대일인데 검증 쿼리는 벽시계를 써서
  검사 ⑤(반복 고장)가 위양성 FAIL 한다.
  📌 이 두 함정으로 **에이전트가 두 번(MQ-708·MQ-713a) DB 를 망가뜨렸다.** 재시드 후에는
  `SELECT count(*) FROM error_codes` 가 **65** 인지 확인한다.
- `data/rules/test_rules.py` — 룰 카탈로그 (근거 무결성 · **발화 가능성**(D77) · **해제 가능성**(D78))
  ⚠ 실행 커맨드: **`uv run --with pytest python -m pytest data/rules/test_rules.py -q`**
  (`uv run python -m pytest` 는 pytest 미설치로 **실행되지 않는다**)
- `spikes/` — **27종** (`ls spikes/*.py` 와 일치해야 한다):
  sp2_mcp_roundtrip · write_tool_contract · api_contract · sp3_sse_events ·
  trace_persist · mcp_client_contract · prompt_rules · lookup_contract · citation_render ·
  db_concurrency · rag_contract · agent_loop_contract · eval_score_contract · s4_smoke ·
  llm_provider_contract · eval_replay_guard ·
  law_fetch_contract · rules_db_load · disposal_api_contract · asset_tools_contract ·
  tools_profile_contract ·
  **bundle_integrity** · **approvals_contract** · **ownership_api_contract** ·
  **disposal_sign_contract** · **s10_smoke** · **ui_honesty_contract**
- 정적: `ruff check` · `tsc --noEmit` · `next build`

건수는 러너 출력이 기준이다. **직전 실행보다 줄었다면 테스트가 사라진 것** — 통과했다고 넘기지 말 것.
스위트 **개수**도 같다 — 위 목록과 `ls spikes/*.py` 가 어긋나면 목록이 낡은 것이다.

**실측 기준선 (2026-08-11, MQ-713b ③)** — spikes **27스위트 / 611건** · seed **21건** · pytest **46건** ·
프론트 라우트 **10개**(`npm run build`). spikes 스위트별 건수:
`agent_loop_contract 32` · `api_contract 28` · `approvals_contract 26` · `asset_tools_contract 49` ·
`bundle_integrity 25` · `citation_render 13` · `db_concurrency 13` · `disposal_api_contract 26` ·
`disposal_sign_contract 26` · `eval_replay_guard 16` · `eval_score_contract 34` · `law_fetch_contract 28` ·
`llm_provider_contract 14` · `lookup_contract 12` · `mcp_client_contract 15` · `ownership_api_contract 10` ·
`prompt_rules 23` · `rag_contract 12` · `rules_db_load 25` · `s10_smoke 17` · `s4_smoke 10` ·
`sp2_mcp_roundtrip 20` · `sp3_sse_events 22` · `tools_profile_contract 7` · `trace_persist 17` ·
`ui_honesty_contract 68` · `write_tool_contract 23`

> ⚠ **러너 신뢰성 — 재시도가 필요할 수 있다 (Windows).** 27스위트를 연속 실행하면 **소켓 고갈**로
> 매번 **다른** 스위트가 1건 실패하는 일이 있다(`OSError: [WinError 10014]`, `socket.socketpair()`).
> **코드 결함이 아니며 해당 스위트를 단독 재실행하면 통과한다.**
> 이 사실을 모르면 두 방향으로 잘못 보고하게 된다 — 실패를 보고 "회귀가 깨졌다"고 하거나,
> 반대로 실패를 무시하는 습관이 들어 **진짜 실패도 함께 넘긴다.**
> 규칙: **실패한 스위트는 반드시 단독 재실행해서 확인**하고, 재시도로 통과하면 그 사실을 보고에 적는다.
> 재시도해도 실패하면 그건 진짜 회귀다.

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
