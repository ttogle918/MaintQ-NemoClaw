# MaintQ — 프로젝트 메모리

설비 진단부터 부품 발주까지 연결하는 B2B 제조 보전 AI 에이전트.
주제는 **도구 오케스트레이션**.

## 반드시 먼저 읽을 문서

작업 전 관련 문서를 확인할 것. 설계와 다른 구현을 하려면 먼저 `docs/10_DECISIONS.md`에 결정을 추가하고 진행:

- `docs/README.md` — 문서 지도. 어느 문서를 열지 모를 때 먼저
- `docs/00_MVP_SCOPE.md` — **반드시 구현할 기능 목록**. 착수 전 "이게 MVP인가 백로그인가" 판단
- `docs/10_DECISIONS.md` — 설계 결정 **D1~D141**. **여기 있는 결정과 충돌하는 코드를 쓰지 말 것**
- `docs/02_SCENARIOS.md` — S1~S4. 모든 기능은 이 시나리오 중 하나에 복무해야 함
- `docs/04_MCP_TOOLS.md` — 도구 입출력 계약(코어 7종 §1~§7 + **확장 15종** §8~§22, 총 22종 —
  이 CLAUDE.md 는 오래 "11종/18종"으로 잘못 적혀 있었다, 2026-08-24 정정). 임의 변경 금지
- `docs/05_DB_SCHEMA.md` — 테이블 **24절(실제 25개)** + 시드 케이스 맵
  (2026-09-04: `§24 manual_chunks`(dense 임베딩, D117) 절을 추가해 문서와 실제 DB 를
  맞췄다 — D117 에서 스키마 문서화가 빠져 있었다. 절 수보다 테이블이 1개 많은 것은
  `§7` 이 `suppliers`·`supplier_parts` 둘을 함께 다루기 때문이다)
  (절 번호는 `§1`~`§9`+`§1-B` 로 10절, Sprint 6 이 `§11`~`§17` 로 이어받고 **Sprint 8 이 `§18`(`partner_links`) 을 더한다**,
   **Sprint 10 이 `§19`(`part_lifecycle_mock`), Sprint 11 이 `§20`~`§23`(F5·F6 4테이블),
   D117 이 `§24`(`manual_chunks`) 를 더한다**
   — **`§10` 은 존재하지 않는다**.
   `§7` 이 `suppliers`·`supplier_parts` 두 테이블을 함께 다뤄 절 수보다 테이블이 1개 많다)
- `docs/06_REPO_API.md` — 폴더 구조·API·SSE 이벤트 규격
- `docs/09_RUNTIME.md` — 시퀀스·루프 상한·장애 모드

## 절대 규칙 (위반 금지)

1. **MCP 도구는 `po_drafts`·`decisions`·`repair_records` 에 draft INSERT만 가능.** UPDATE 코드를 도구에 추가하지 말 것.
   상태 전이는 사람 전용 API만 — `backend/routers/po.py`(발주) · `backend/routers/decisions.py`(처분) ·
   `backend/routers/repairs.py`(수리, D98) (D10·D81)
   - 🔵 **`get_document_facts` 는 읽기 전용이다** (D125) — 결재 문서에 찍힐 값을 조회만 한다.
     교정은 UPDATE 가 아니라 `create_po_draft` **새 draft INSERT** 또는 사람의 화면 수정
     (`PATCH /api/po`·`/api/repairs`·`/api/decisions`)이다. 같은 요구가 다시 오면
     `docs/07_BACKLOG.md` 「아이디어 주차장」의 거부 경위를 볼 것
   - 쓰기 도구는 **3종**: `create_po_draft` · `generate_disposal_document` · `create_repair_record`.
     커넥션도 분리한다(`db.draft_writer()` / `db.decision_writer()` / `db.repair_writer()`) —
     섞으면 TEMP TRIGGER 잠금이 사라진다
   - `generate_disposal_document` 에 `override`·`override_reason`·`reviewed_by` 파라미터를 **추가하지 말 것** (D81)
   - 🔵 **화면 직접 생성(`POST /api/po`)은 이 규칙(D10) 대상이 아니다** (D111) — MCP 도구가 아니라
     백엔드 쓰기라 처음부터 UPDATE 권한이 있다. 산출 로직은 `data/po_draft.py` 공유 계층에서
     `create_po_draft`(MCP)와 동일하게 검증된다
2. **에러코드 정의 조회는 lookup(exact match), 절차 서술은 RAG.** 이 경계를 흐리는 코드 금지 (D1)
3. **점검 절차 출력에는 안전 경고 필수** — safety-guardrail 스킬 규칙 준수. 안전 문구는 매뉴얼 근거(페이지) 없이 생성 금지
4. **model 파라미터는 enum('iG5A','S100','IE5') 강제** (D6, D13, D109 — IE5 는 정의 조회 경로만.
   `equipment.model` CHECK 는 여전히 2종, 안전 문구·RAG 청킹은 IE5 미확장)
5. **`data/raw/`는 읽기 전용** — 매뉴얼 원본 수정 금지, git에도 올리지 않음 (.gitignore 확인)
   - 🔴 **예외가 셋 있다 (D103, Sprint 13)**:
     ㉠ **git 추적 예외** — `data/raw/external/<source>/*.json`(외부 API 응답 원본) +
     `data/raw/external/README.md` 는 추적한다. 매뉴얼 PDF·배포 CSV·캐시 중간 산물(임시 PDF 조각)은
     여전히 제외(`.gitignore` 의 `!data/raw/external/` negation 이 그 경계를 고정)
     ㉡ **쓰기 예외** — `data/raw/external/README.md` **1건만** `.claude/hooks/guard_writes.py` 가
     쓰기를 허용한다. 그 외 `data/raw/` 하위는 여전히 훅이 차단
     ㉢ **캐시 JSON 은 사람·에이전트 손편집 금지** — `data/raw/external/<source>/*.json` 은
     `data/external/store.py` **한 곳만** 경유해 기입한다(D103 ⓔ). 직접 수정은 append-only ·
     내용 주소 멱등(D60) 규약을 깬다
6. **미지 에러코드에 유사 코드 추측 금지** — not_found면 S4 흐름 (환각률 0% 목표)

## 기술 스택·컨벤션

- Python 3.11+, FastAPI, SQLite(목업), MCP 서버는 backend와 프로세스 분리 (D15)
- 린터: **ruff check** — `.claude/hooks/lint_edited.py`(PostToolUse)가 **방금 편집한 파일 하나만**
  `ruff check --fix` 로 훑는다(안전한 자동 수정만). Stop 훅은 `ruff check data backend mcp_server
  spikes eval` 전체를 0.2초에 돌린다
  🔴 **정정 (2026-09-09 실측)**: 이 줄은 오래 *"포매터: ruff (PostToolUse 훅으로 자동 실행)"* 이었는데
  **두 가지가 함께 틀렸다.** ㉠ 그 훅은 `python -m ruff format .` 이라 **한 번도 돈 적이 없다** —
  시스템 파이썬에 ruff 가 없어 매번 `No module named ruff` 로 죽었고 `|| exit 0` 이 삼켰다.
  포맷이 유지된 건 훅이 아니라 사람이 `uv run ruff check` 를 돌렸기 때문이다.
  ㉡ **이 레포의 규약은 포매터가 아니라 린터다** — `ruff format` 을 실제로 재 보면
  **189개 중 110개 파일을 재포맷한다.** 켜면 기능 3줄 변경에 스타일 500줄이 섞인다.
  전면 스타일 적용을 하려면 훅이 아니라 **의도된 단독 커밋**으로 할 것.
  ⚠ Stop 훅도 같은 병이었다 — `pytest eval/` 을 가리켰는데 `eval/` 에는 테스트 파일이 **0개**라
  `no tests ran` 만 찍고 끝났다. **훅 3개 중 2개가 조용히 무동작이었다.**
  이 문서가 스스로 정한 *"부재 검사에는 liveness 앵커를 함께 건다"* 가 훅에는 적용되지 않은 자리다.
- 도구는 `mcp_server/tools/` 파일당 1개, status 필드로 실패 반환 (예외 던지지 말 것, D9)
  - **필수 파라미터에 기본값을 두지 않는다** (D80) — 인자 누락은 MCP 스키마가 앞단에서 막는다. D9 는 도구 **로직**의 실패에 대한 규칙이다
  - 확장 **15종**(코어 7 + 확장 15 = 22종)은 `MAINTQ_TOOLS_PROFILE=full` 에서만 등록된다.
    **기본은 `core`** (D69·**D88** — 평가는 `core` 에서만 인정)
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
- `data/rules/test_rules.py` · `backend/agent/test_llm_cache.py` · `data/external/test_elice_docvision.py` ·
  `data/test_expenditure_limits.py`
  — 룰 카탈로그(근거 무결성 · **발화 가능성**(D77) · **해제 가능성**(D78)) + **LLM 응답 카세트**
  (D104 — 키·값 직렬화·`CachingClient`·`stats_line()`) + **Elice 지출 가드**(D105 — 캐시 우선·
  네트워크 전 예외·가격 상수) + **내부통제 판정**(Sprint 17 MQ-1703 — 예산 한도·1일 누적 한도·
  FDS·SoD 4종 순수 함수, D119)
  ⚠ 실행 커맨드(**7파일 합산**): **`DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)"
  uv run --with pytest python -m pytest data/rules/test_rules.py
  backend/agent/test_llm_cache.py backend/agent/test_llm_fallback.py
  data/external/test_elice_docvision.py data/test_expenditure_limits.py
  backend/services/test_docx_render.py backend/services/test_po_documents.py -q`** → **128건**
  (`uv run python -m pytest` 는 pytest 미설치로 **실행되지 않는다**)

  🔴 **정정 (2026-09-04 실측)**: 이 커맨드는 오래 **"4파일 합산 → 114건"** 으로 적혀 있었는데
  **두 가지가 함께 틀렸다.**
  ㉠ **`test_llm_fallback.py`(15건)가 합계에만 더해지고 커맨드에는 없었다** —
     *"114건(99 + `test_llm_fallback.py` 15)"* 이라고 적으면서 정작 실행 목록에 그 파일을
     넣지 않았다. 그대로 복붙해 돌리면 **영원히 114 가 나오지 않는다.**
  ㉡ **기준값 99 도 낡았다** — 실측은 101 이다(`test_llm_cache.py` 가 24→26.
     `docs/07_BACKLOG.md` 가 기록한 `TraceWriter` 가드 회귀 2건이 늘어난 것).
  파일별 실측: `test_rules` 46 · `test_llm_cache` 26 · `test_llm_fallback` 15 ·
  `test_elice_docvision` 13 · `test_expenditure_limits` 16 · **`test_docx_render` 9**(신규,
  D124) · **`test_po_documents` 3**(기존인데 목록 밖이었다) = **128**.
  실제로 도는 파일을 전부 커맨드에 넣었다 — **합계만 고치면 같은 함정이 재발한다.**
  🔴 **`DATABASE_URL` 을 반드시 실어야 한다** (2026-08-29 실측). pytest 실행 경로에는
  `load_dotenv` 가 없어(`backend/main.py` 에만 있다) `backend/db.py:21` 의 기본값
  `postgresql://localhost/maintq` = **포트 5432** 로 떨어지는데 컨테이너는 **5434** 다.
  아무도 듣지 않는 포트라 psycopg 가 타임아웃 없이 **무한 대기**한다 — 실패가 아니라
  멈춤이라 원인 파악이 오래 걸린다. 실제로 `test_llm_cache.py::test_trace_replay_marks_
  events_when_cached` 에서 걸린다(그 테스트가 `TraceWriter` 에 `Path` 를 넘겨 공유 DB 로
  새기 때문 — `docs/07_BACKLOG.md` 「알려진 결함」 참고).
- `backend/a2a/test_auth_header.py` · `test_client.py` · `test_credentials.py` · `test_payloads.py` ·
  `test_trace.py` · `backend/routers/test_a2a.py` · `test_po_a2a_trigger.py` ·
  `backend/services/test_po_a2a_dispatch.py` · `backend/a2a/test_circuit.py` — **9파일 156건**, A2A 아웃바운드(FinAllQ 출금·
  InsuQ 약관조회·assess-loan) 클라이언트·payload 조립·trace 기록·라우터 계약.
  파일별 실측(2026-09-09): `test_auth_header` 5 · `test_client` **26**(16+차단기 연동 6+D139 4) ·
  **`test_circuit` 17**(신규, D136) · `test_credentials` 12 · `test_payloads` **40**(25+S11 9+D138 3+D141 3) ·
  `test_trace` 8 · `routers/test_a2a` **33**(28+S11 5) · `test_po_a2a_trigger` 8 ·
  `test_po_a2a_dispatch` 5 = **156**(2026-09-10 D138 3 + D139 4 · 2026-09-11 D141 멱등키 5).

  🔴 **정정 (2026-09-04 실측)**: 오래 **88** 로 적혀 있었다. 그 값이 어떻게 나왔는지는
  이제 알 수 없지만 **러너 출력과 19건 어긋난다** — 이 문서가 스스로 정한
  *"건수는 러너 출력이 기준이다"* 를 지키지 못한 자리가 또 나온 것이다(2026-08-29 에
  86→88 로 한 번 고친 바로 그 줄이다). 파일별 합과 합산 실행이 **둘 다 107** 로 일치하는
  것을 확인했다.

  ⚠ **측정할 때 `N passed` 만 grep 하지 말 것.** 이 세션에서 실제로 그렇게 재다가
  `test_po_a2a_dispatch` 를 4건으로 잘못 읽었다(실제 5건). skip·error 가 붙은 요약 줄에서
  앞부분만 잘라 오기 때문이다 — **요약 줄 전체**를 보거나 `--collect-only` 로 교차 확인한다.
  ⚠ 실행 커맨드(**pytest-asyncio 추가 필요**): **`uv run --with pytest --with pytest-asyncio
  python -m pytest backend/a2a/test_auth_header.py backend/a2a/test_client.py
  backend/a2a/test_circuit.py backend/a2a/test_credentials.py backend/a2a/test_payloads.py
  backend/a2a/test_trace.py backend/routers/test_a2a.py backend/routers/test_po_a2a_trigger.py
  backend/services/test_po_a2a_dispatch.py -q`** (또는 `backend/a2a/` 디렉터리 통째로)
  (이쪽도 `DATABASE_URL` 을 함께 실어야 한다 — 위와 같은 이유) (`--with pytest-asyncio` 없이 돌리면
  `test_client.py` 등 async 테스트가 전부 "async def functions are not natively supported"
  로 실패한다 — Postgres 와 무관한 별개 함정)
- `backend/services/test_a2a_history.py` · `test_lien.py` · `test_po.py` — **3파일 20건**
  (A2A 이력 조회 D114 · 유치권 판정 · 발주 서비스). 🔴 **2026-09-04 신규 편입** — 레포에
  존재하고 통과하는데 **이 목록 어디에도 없었다.** 위 두 파일군과 같은 계열의 누락이다
  (`5895c2e` 의 8파일이 그랬듯 커밋은 됐는데 목록에 안 실렸다).
  ⚠ 실행 커맨드: **`uv run --with pytest --with pytest-asyncio python -m pytest
  backend/services/test_a2a_history.py backend/services/test_lien.py
  backend/services/test_po.py -q`** (`DATABASE_URL` 필수)

  📌 **pytest 총계는 이제 22파일 348건이다** (7파일군 128 + A2A 9파일군 156 + 서비스 3파일 20 + mcp_server 3파일 44).
  🔵 **2026-09-09 갱신**: D136(A2A 차단기, P35 해소)이 `backend/a2a/test_circuit.py` **17건**을
  신설하고 `test_client.py` 를 16→**22건**으로 늘렸다(107 → 130). 이어서 **S11
  `notify-asset-change`** 구현이 `test_payloads` 25→34 · `routers/test_a2a` 28→33 으로
  **130 → 144** 를 만들었다. 차단기는 **프로세스 전역
  상태**라 `test_client.py` 에 `registry().reset()` autouse 픽스처가 함께 들어갔다 —
  **없으면 전송 실패 테스트 3건이 차단기를 열어 뒤따르는 5건이 조용히 다른 예외를 받는다**
  (도입 즉시 실측으로 드러났다).
  🔴 **2026-09-11 — `mcp_server/tools/test_*.py` 3파일 43건이 목록 밖이었다** (네 번째 누락).
  `test_assess_equipment_loan` **17**(2026-09-11 — D139 5xx 분리를 형제에서 이식, 16→17) · `test_search_insurance_clause` 13 · **`test_assess_used_equipment_loan` 14**(신규, D140).
  ⚠ **가드 자신에게 사각지대가 있었다** — 아래 확인 커맨드가 `backend data` 만 훑어
  `mcp_server/` 를 **아예 보지 않았다.** 누락을 막으려고 세운 검사가 그 누락을 못 봤다.
  ⚠ 실행 커맨드: **`uv run --with pytest python -m pytest mcp_server/tools/ -q`** → **44건**
  (A2A 자격증명을 안 다루는 얇은 HTTP 래퍼라 `httpx.post` monkeypatch 만으로 돈다 — DB 불필요)

  목록이 맞는지 보려면 **`find backend data mcp_server -name 'test_*.py' -not -path '*__pycache__*'`**
  가 반환하는 파일이 전부 위 네 군에 들어 있는지 확인한다 — 이 검사를 안 하면 같은
  누락이 반복된다(이번까지 **네 번째**다). **`mcp_server` 를 뺀 옛 커맨드로는 못 잡는다.**

- `spikes/` — **34종**(`ls spikes/*.py` 는 38개를 반환한다 — 남는 4개는 아직 이 공식 목록 밖,
  `docs/sprints/sprint-16-wip.md` "스코프 밖 발견" 참고):
  sp2_mcp_roundtrip · write_tool_contract · api_contract · sp3_sse_events ·
  trace_persist · mcp_client_contract · prompt_rules · lookup_contract · citation_render ·
  db_concurrency · rag_contract · agent_loop_contract · eval_score_contract · s4_smoke ·
  llm_provider_contract · eval_replay_guard ·
  law_fetch_contract · rules_db_load · disposal_api_contract · asset_tools_contract ·
  tools_profile_contract ·
  bundle_integrity · approvals_contract · ownership_api_contract ·
  disposal_sign_contract · s10_smoke · ui_honesty_contract ·
  a2a_identity_contract ·
  repair_flow_contract ·
  deadline_risk_contract ·
  external_store_contract ·
  ie5_extract_contract ·
  **a2a_partner_tools_contract** · **docx_contract**
- 정적: `ruff check` · `tsc --noEmit` · `next build`

건수는 러너 출력이 기준이다. **직전 실행보다 줄었다면 테스트가 사라진 것** — 통과했다고 넘기지 말 것.
스위트 **개수**도 같다 — 위 목록과 `ls spikes/*.py` 가 어긋나면 목록이 낡은 것이다.

> ⚠ **부재 검사에는 반드시 liveness 앵커를 함께 건다.** `"X" not in src` · `not hits` 처럼
> **"없다"를 주장하는 검사**는 원리적으로 *"사실이 참"* 과 *"스캐너가 눈이 멀었다"* 를 구분하지 못한다.
> 정규식이 안 맞거나 파일이 비거나 경로가 바뀌면 **조용히 통과**한다.
> 규칙: 판정에 **양성 축**을 함께 넣는다(`not bad and anchors > 0`, `not leaks and bool(scanned)`).
> **detail 에는 결론이 아니라 두 축의 실측값을 찍는다** — `"쓰기 경로 없음"` 같은 하드코딩 문구는
> FAIL 일 때도 그대로 인쇄돼 표를 읽는 사람이 정반대로 이해한다.
> 실제 사례: Sprint 8 에서 `⑪-b` 판정식이 **blob 조립 방식에 따라** 살고 죽는 것이 드러났다
> (`spikes/a2a_identity_contract.py` 상단 주석). 기존 스위트에 남아 있던 같은 결함 2건(**P30**)은
> **2026-08-19 해소됐다** — `agent_loop_contract ⑯ A7` 은 앵커 3종 + 스캐너 생존을 판정에 넣고
> 하드코딩 detail 을 실측값으로 바꿨고, `ui_honesty_contract` 의 C1~C8(대상 `lib/*.ts` 4개가
> **import 0개인 것이 정상**이라 앵커를 못 만든다)은 **오라클 메타검사 1건**을 스파이크 안에 세웠다.
> 뮤턴트로 실증했다 — `module_specifiers` 를 `return []` 로 망가뜨리면 새 오라클만 FAIL 하고
> **C1~C8 은 전건 PASS 한다**. 그게 이 결함의 정의다.

**실측 기준선 (2026-08-23, Sprint 16 SQLite→Postgres 마이그레이션 완결 후 재실행 — 아래 문단 참고)** —
spikes **34스위트 / 1,212건**(2026-09-06 — 1,202 + `eval_score_contract` **D135 오특정/미특정 분리 축 10건**(⑫-g~⑫-n, ⑫-k 는 3케이스 루프). 뮤턴트 2종으로 실증했다 — 판정을 `return PART_WRONG` 으로 망가뜨리면 3건이, 렌더를 지우면 **⑫-m 하나만** FAIL 한다(렌더 검사가 제 몫을 한다는 뜻).
직전 1,202 = 1,197 + `eval_score_contract` D133 견적 근거 축 5건(⑫-b~⑫-f).
직전 1,197 = 1,192 + `eval_replay_guard` D132 스트림 실패 분모 축 5건(⑥-a~⑥-e).
직전 1,192 = 1,190 + `db_concurrency` D126 채번 사본 정적 검사 2건(㉑㉒).
직전 1,190 = 1,186 + D127·D130 가드 4건(⑰⑱⑲⑳).
직전 1,186 = 1,183 + D126 잠금 축 3건(⑭⑮⑯).
직전 값 1,183 = 1,120 + docx_contract 63. 직전 갱신은 2026-09-03 — 아래 표 합산과 일치. 직전 1,075 에서 +45:
`agent_loop_contract` 35→37(②-b 빈 응답 · ②-c 이력 절삭, 둘 다 실사고 회귀) ·
`repair_flow_contract` 19→28(P39 화면 직접 생성 축) · `ui_honesty_contract` 303→321
(P39 수리증빙 신규 파일 3개 × 6항목). **처분서까지 마치며 +16 더**: `disposal_api_contract` 26→36(화면 직접 생성 축) · `ui_honesty_contract` 321→327(`DisposalDraftForm` 1파일 × 6). **프론트 라우트는 25 그대로다** — 처분은 새 라우트 없이 기존 `/technician/asset/[assetId]/disposal` 에 붙였다. 그 전 값은 아래 문단 참고 —
`bundle_integrity` 포함 —
1,052 에서 `api_contract`(+11, Sprint 17 D119 재무부 승인·doc3 계약)·`ui_honesty_contract`
(+12, Sprint 18 대시보드 신규 파일 2건×6 — `EquipmentCard.tsx`·`manager/finance/page.tsx`)
반영해 2026-08-24 재계산).
**32→33**: Sprint 16 Stage 4(MQ-1613, 다른 세션이 이 세션 착수 전 이미
커밋·push)가 `a2a_partner_tools_contract.py`(22건)를 신설했는데 이 문서 목록에 반영이 안 돼
있었다 — `ls spikes/*.py` 실측으로 뒤늦게 발견해 여기서 정정한다. (`ls spikes/*.py` 는 37개를
반환한다 — 나머지 4개 중 2개(`test_elice_stream.py` 는 gitignore 대상 미추적 파일 · 
`demo_recommendation_1_and_2.py` 는 PASS/FAIL 단언 없는 시연 스크립트)는 의도적으로 공식
목록 밖이고, 나머지 2개(`a2a_outbound_contract.py`·`a2a_e2e_integration_spike.py`)는 진짜
계약 스파이크이지만 아직 공식 33종에 편입할지 결정 전이다 — 포팅은 완료됨,
`docs/sprints/sprint-16-wip.md` "4차 체크포인트" 참고) · seed **43건**(불변 아님 —
DB 미개봉 — ㉖ `mfr_part_no` D97 · ㉗~㉙ Sprint 9 `repair_records`/`error_codes` 신설 ·
㉚ `error_codes.actions` 병합 검증 MQ-919 · ㉛ Sprint 10 `part_lifecycle_mock` · ㉜~㉟ Sprint 11
F5·F6 4테이블 `deadlines`/`incidents`/`ownership_checks`/`risk_profile` · ㊱ Sprint 15
`error_codes` IE5 5건 병합 검증(D109) · **㊶~㊷ InsuQ 발급 증권번호 체계 고정(2026-09-16)** —
`policy_id` 목업 1종을 실번호 4종으로 바꾸며 형식(`[A-Z]{2,3}-\d{4}-\d{4}`)과
건물↔증권 짝을 함께 잠갔다. ⚠ **접두사가 2~3글자 가변**이라(`SB`/`DS`/`SBP`) 형식 검사에
**양성 축(접두사 3종 생존)을 함께 걸었다** — `{2}` 로 좁히면 `SBP` 2행에서 FAIL 하는 것을
뮤턴트로 실증했다) · pytest **128건**(위 커맨드 정정 참고)
(`data/rules/test_rules.py` 46 + `backend/agent/test_llm_cache.py` 24 — D104 카세트 +
`data/external/test_elice_docvision.py` 신설 13 — D105 지출 가드, 커맨드가 **3파일 합산**으로 바뀐다) ·
프론트 라우트 **25개**(`npx next build` — ⚠ `find frontend/app -name page.tsx` 로 세면 하나 적다.
차이 1은 Next.js App Router 가 자동 생성하는 `/_not-found` 로, **둘 다 맞는 값이고 세는 대상이
다르다**. '정정'하지 말 것 — 이 기준선은 빌드 출력 기준이다. — **Sprint 13 은 프론트 무변경이라
재실행 불필요**, Sprint 10 MQ-1001 이 `/manager/expenditure`·`/technician/asset/[assetId]/evidence`
2개, MQ-1002 리뷰 픽스가 `/manager/repair/[repairId]` 1개, Sprint 12 MQ-1204 가
`/manager/deadlines`·`/manager/risk-grade` 2개 증가: 16→17→18. **18→19**: P40 v2 Plan 1(MUI 레이아웃
격리 확인, 2026-08-21)이 `/v2/manager/po/[poId]` 를 신설했으나 이 문서에는 반영이 안 돼 있었다 —
D111 작업 중 `npx next build` 실측으로 뒤늦게 발견해 여기서 함께 정정한다. **19→21**: D111이
`/technician/po/new`·`/technician/po/[poId]` 2개를 더했다(P39 축소판). 18→21. **21→22**(2026-08-24,
"빠른 정리" 세션): 계정 선택 화면 작업이 `/manager/finance`(재무담당 전용 랜딩)를 신설했다.
**22→25**(2026-09-03, P39 수리증빙): `/technician/repair/new`·`/technician/repair/[repairId]`
2개를 더했다 — 그런데 22+2=24 인데 실측이 **25** 다. 차이 1은 **`22` 를 적을 때 이미
`/v2/manager/po/[poId]` 가 빠져 있었기 때문**이다(P40 v2 가 신설한 그 파일 — 이 문단이
"19→21" 로 한 번 정정한 바로 그 누락이 **또** 났다). 소스 파일 수로 교차 확인했다:
`find frontend/app -name page.tsx` = 24, 빌드 출력 25(차이 1은 `/_not-found`). spikes 스위트별 건수:
`a2a_identity_contract 19` · `a2a_partner_tools_contract 22` ·
`agent_loop_contract 37` · `api_contract 52` · `approvals_contract 26` · `asset_tools_contract 49` ·
`bundle_integrity 26`(Postgres 포팅 완료 — 아래 Sprint 16 문단 참고) ·
`citation_render 19` · `db_concurrency 16`(Postgres 재설계 + D126 잠금 축 3건 + D127·D130 가드 4건 + D126 채번 사본 정적 검사 2건 — 아래 참고) · `deadline_risk_contract 18` ·
`disposal_api_contract 36` · `docx_contract 63` ·
`disposal_sign_contract 26` · `eval_replay_guard 21` · `eval_score_contract 51` · `external_store_contract 47` ·
`ie5_extract_contract 54` · `law_fetch_contract 28` ·
`llm_provider_contract 23`(D115 — 아래 참고) · `lookup_contract 14` · `mcp_client_contract 15` · `ownership_api_contract 10` ·
`prompt_rules 24` · `rag_contract 13` · `repair_flow_contract 28` · `rules_db_load 25` · `s10_smoke 17` ·
`s4_smoke 10` · `sp2_mcp_roundtrip 20` · `sp3_sse_events 22` · `tools_profile_contract 7` ·
`trace_persist 17` · `ui_honesty_contract 327` · `write_tool_contract 30`

> 🔴 **정정 (2026-08-20 전수 재실행)**: 이 문단은 오래 **872→916(872+44)** 으로 적혀 있었으나
> **같은 문서 안의 다른 두 값과 어긋났다** — 스위트별 표가 `external_store_contract` 를 **47**
> 로 적고 헤드라인이 **919** 를 적는다. 전수 실측(31스위트 합)이 **919** 로 나와 헤드라인·표가
> 맞고 **이 문단의 `44`·`916` 이 틀렸다**. MQ-1205 의 `prompt_rules` 23→24 정정과 같은 유형이다.
> **872→919**: Sprint 13 이 신설 스위트 `external_store_contract`(D103·D105 왕복 검증)를 더한 것이
> 전부다(872+47=919) — 기존 30스위트는 Stage 1~3 을 거치는 동안 건수가 **하나도 바뀌지 않았다**
> (`law_fetch_contract` 는 `fetch_laws.py` 에 저장 소급 호출이 붙었지만 28건 그대로 — MQ-1305 가
> `_store_payload` 를 함수 내부 지연 import 로 격리해 스파이크 최상단 `sys.path` 제약을 건드리지
> 않았기 때문이다). pytest **70→83**: `data/external/test_elice_docvision.py` 신설 13건(D105
> 지출 가드) 그대로.

> **919→969**: Sprint 14 Stage 1 이 신설 스위트 `ie5_extract_contract`(D107 · 괘선 없는 표
> 추출 왕복 검증)를 더한 것이 전부다(919+50=969) — 2026-08-20 전수 재실행에서 **기존 31스위트는
> 건수가 하나도 바뀌지 않았고 FAIL 0 · 소켓 고갈 재시도 0회**였다. 이 스위트는 `data/raw/` 의 IE5
> PDF 가 `.gitignore` 대상이라 **기하 픽스처만으로 돈다** — PDF 가 있으면 대조 축 3건이 더 붙고,
> 없으면 **`SKIPPED 3` 을 건수와 함께 인쇄**하고 통과한다(PASS 47 + SKIPPED 3, 종료코드 0).
>
> **969→972**: P41 ③(부서 분리, D108)이 `spikes/api_contract.py` 에 department 신뢰 경계
> 검사 3건(헤더 스푸핑 무시·`GET /api/whoami` 왕복·미등록 사용자 처리)을 더했다
> (969+3=972). `seed.py` 자가검증도 ⑨-b(department 가 role 을 안 바꾸는지) 신설로
> 35→**36건**이 됐다 — 이건 spikes 969/972 건과 **별도 카운트**다.
>
> **972→976**: IE5 검수 이월 항목(§8·§9, TODO_직접할일.md Sprint 14절) 반영이
> `ie5_extract_contract` 에 4건을 더했다(50→**54**, 972+4=976) — A⑯(`page.lines` 세로선
> 0개 = D107 전제 회귀 고정) · C⑪(`code_pages_exact`/`code_pages_case_folded` 분리) ·
> C⑫(`IOL`↔`IOLt` 명칭 충돌 상호참조) · D④(`_warnings` 실패 경로 liveness). 나머지
> 31스위트는 무변경(FAIL 0 · 소켓 고갈 재시도 0회, 32스위트 전수 재실행). seed **36건**·
> pytest **83건** 그대로. PDF 없을 때는 `ie5` 가 PASS 51 + **SKIPPED 3**(종료코드 0).
>
> **976→977**: Sprint 15(P11, D109)가 model enum 을 3종(iG5A·S100·IE5)으로 확장하고 IE5 5건을
> 정본에 병합했다. spikes 변화는 `citation_render`(18→19, IE5 왕복 검증 신규) **하나뿐**이고
> 나머지 31스위트는 건수 무변화(976+1=977). seed **36→37건**(신규 검사 ㊱, IE5 5건 병합 검증).
> `error_codes` **65→70건**. pytest 83건·프론트 18라우트·MCP 도구 18종·DB 24테이블 전부 무변경.
>
> **977→978**: D110(같은 날, 같은 세션)이 D109 ⓑ("RAG 는 별도 스프린트 대상")를 재조사로
> 뒤집었다 — 실측 결과 막힌 지점은 `data/chunk_manual.py` 의 하드코딩 2종 assert 하나뿐이었고
> IE5 PDF 는 코드 변경 없이 194청크로 정상 처리됐다(총 1,229청크). spikes 변화는
> `rag_contract`(12→13, IE5 실 인덱스 검색 신규 검사) **하나뿐**(977+1=978). seed·pytest·
> `error_codes`·프론트·도구·DB 전부 무변경. D109 ⓐ(안전 문구 미확장)·ⓒ(equipment CHECK 2종)는
> 그대로 유지 — 안전 게이트(`needs_safety_block`)가 텍스트 내용 기반이라 데이터 출처와 무관하게
> 동작함을 `backend/agent/loop.py:360-382` 직접 확인 후 결정했다.
>
> **978→988**: D111(P39 축소판 — 화면이 발주 초안을 직접 생성·수정)이 `api_contract`에
> 10건을 더했다(31→41, 978+10=988) — 견적 사전 조회·화면 생성 권한 403·MOQ 미달 422·
> draft 수정·전이 409·404. 나머지 31스위트는 무변경. `write_tool_contract`(`create_po_draft`
> 리팩터 대상, 30건)도 리팩터 전후 동일 건수로 재확인됨 — 산출 로직을 `data/po_draft.py`로
> 옮겼지만 출력 dict는 한 글자도 안 바뀌었다. seed·pytest·`error_codes`·MCP 도구 18종·DB
> 24테이블 전부 무변경. 프론트 라우트는 `/technician/po/new`·`/technician/po/[poId]` 신설로
> 함께 늘었다 — 위 프론트 라우트 문단(18→21)·`ui_honesty_contract` 문단(253→271) 참고.
>
> `ui_honesty_contract` 는 세 단계로 늘었다. **102→114**: 이 브랜치가 `components/asset/*.tsx`
> 에 `InventoryDrawer.tsx`·`EquipmentHotspotDiagram.tsx` **2파일**을 신설해 L2 스캔 대상이
> 12→14개가 되며 컴포넌트당 L2 검사 6건씩 자연 추가된 것(2×6=12) — 파일 1개가 아니라 두
> 플랜(재고 서랍·핫스팟 대시보드) 각각의 신규 파일이 합쳐진 결과다. **114→186**: 병합 전
> 최종 리뷰 픽스로 `L2_GLOBS` 에 `app/(console)/**/*.tsx` 를 더해 라우트 페이지 12개가
> 스캔에 편입된 것(12×6=72) — 코드 수정 없이 글롭이 잡는다. 이 확장으로 이전엔 스캔되지
> 않던 기존 `disposal/page.tsx`·`ownership/page.tsx` 에서 사전에 있던 D87 위반 4건이
> 새로 드러났다(이 브랜치가 만든 위반이 아님). 같은 브랜치에서 트리아지 후 즉시 수정 —
> `disposal/page.tsx` 는 `state === "draft"` 직접비교를 `lib/queueState.isDraftState()` 로,
> `ownership/page.tsx` 는 로컬 `MOCK`·`TONE_BANNER` 상수를 `lib/ownership.ts` 로 이관해
> 해소했다. 건수는 FAIL→PASS 전환이라 186건 그대로였다 — 스위트는 **PASS 186/186**.
> **186→222**: Sprint 10 이 두 스테이지에 걸쳐 다시 늘렸다. Stage 1(MQ-1001·MQ-1002)이
> 이미 걸려 있던 글롭에 새 파일 5개를 자연 편입시켰다 — `components/asset/*.tsx` 신규
> `EvidenceBundlePanel.tsx`·`ExpenditureForm.tsx` 2파일(2×6=12) + `app/(console)/**/*.tsx` 신규
> `evidence/page.tsx`·`manager/expenditure/page.tsx`·`manager/repair/[repairId]/page.tsx`
> 3파일(3×6=18) = 30건. Stage 2(MQ-1003)가 `L2_EXTRA` 에 `components/queue/RepairDetail.tsx` 를
> **명시 등재**했다 — `components/queue/*.tsx` 글롭이 `Decision*.tsx` 패턴만 잡아 자동 편입되지
> 않으므로 별도 태스크로 추가(1×6=6). 30+6=36, 186+36=222 — 산술과 실측이 일치한다. 이 확장
> 과정에서 `RepairDetail.tsx`의 실제 D87 위반 1건(`HashVerified`가 `--ok-tx` 색 토큰 직접 사용)이
> 드러나 `--blue-tx` 로 교체해 같은 커밋(`213b62d`)에서 해소했다 — 스위트는 **PASS 222/222**.
> **222→252**: Sprint 12 가 세 갈래로 늘렸다. MQ-1202(Stage 1)가 `lib/deadlines.ts`(2함수)·
> `lib/riskGrade.ts`(1함수)를 신설해 L1 13→15(+2)건, 이 두 파일이 L1 전제(React·`@/` 별칭 미사용)를
> 지켜야 하므로 제약 게이트도 파일당 2건씩 늘어 4→8(+4)건이 됐다. MQ-1201·1203·1204(Stage 1·3)가
> `components/asset/DeadlinesPanel.tsx`·`RiskGradeGrid.tsx`(asset 글롭) + `app/(console)/manager/
> deadlines/page.tsx`·`manager/risk-grade/page.tsx`(app 글롭) 4파일을 신설해 기존 글롭에 자동
> 편입, L2 32→36파일(+4×6=24건)이 됐다. 뮤턴트 8종·메타 4건은 무변경. 2+4+24=30, 222+30=252 —
> 산술과 실측(`uv run python spikes/ui_honesty_contract.py` 출력 "통과 — 계약 232건 + 제약 8 +
> 뮤턴트 8 + 메타 4" = 252)이 일치한다 — 스위트는 **PASS 252/252**(신규 D87 위반 없음).
> **252→253**: P30 해소(2026-08-19)가 **메타 4→5** 로 1건 더했다 — `IMPORT_SPEC` 오라클.
> C1~C8 은 전부 부재 검사인데 대상 `frontend/lib/*.ts` 4개는 **import 문이 0개인 것이 정상**이라
> 파일 안에 걸 앵커가 없다. 그래서 알려진 픽스처(from·부수효과·require·동적 import 4문법)를
> `module_specifiers()` 에 넣어 **추출기가 살아 있음**을 단언하는 오라클을 스파이크 안에 뒀다
> (L2 뮤턴트 메타검사와 같은 방식). 계약 232 + 제약 8 + 뮤턴트 8 + **메타 5** = 253 —
> 스위트는 **PASS 253/253**.
> ⚠ **부수 정정(MQ-1205)**: 같은 전수 재실행에서 `prompt_rules` 실측이 **24건**으로 확인됐다 — 직전
> 기록(23)과 어긋난다. `git log -- spikes/prompt_rules.py` 로 대조하면 Sprint 11 Stage 5(`390e7a9`)
> 이후 이 파일은 무변경이라 **코드가 아니라 기록이 낡았던 것**(전사 표기 정리 때 옮겨 적은 값이
> 틀렸을 가능성) — 24로 정정. 총계 870 이 아니라 **871** 인 이유가 이 +1 이다(252 델타 30 과는
> 무관, 두 정정이 겹쳐 870→871 이 아니라 840→871 로 보인다: 기존 840 자체가 이미 23으로 잰
> 합계였으므로 24 반영 시 841, 여기에 ui_honesty +30 을 더해 871).
> **871→872**: P30 이 `ui_honesty_contract` 에 오라클 1건을 더한 것(252→253)이 전부다.
> 나머지 29스위트는 전건 무변경 — 2026-08-19 전수 재실행에서 스위트별 건수가 위 표와
> 하나도 어긋나지 않았고 **FAIL 0 · 소켓 고갈 재시도 0회**였다.
> **253→271**: D111(P39 축소판)이 신규 파일 3개를 기존 글롭에 편입시켰다 —
> `components/asset/PoForm.tsx`(`components/asset/*.tsx` 글롭, ×6=6) + `technician/po/new`·
> `technician/po/[poId]` 2페이지(`app/(console)/**/*.tsx` 글롭, 2×6=12) = 18, 253+18=271.
> 이 확장 과정에서 `technician/po/[poId]/page.tsx`의 `ReadOnlyCard`가 `po.state === "draft"`
> 3항 연쇄로 상태를 직접 비교하던 실제 D87 위반 1건(L2-18.4·18.5)이 드러나 `stateView("po",
> po.state)` 호출로 즉시 교체했다 — 같은 커밋에서 해소, 신규 위반이 남지 않았다. 스위트는
> **PASS 271/271**.

> **Sprint 16 — SQLite→Postgres 마이그레이션 완성 (2026-08-23, MQ-1614).** 다른 세션이 시작한
> 마이그레이션(스키마 변환·`scripts/postgres_guards.sql`·데이터 이관 스크립트)이 "코드만
> 전환되고 접속 가능한 Postgres 가 없는" 상태로 남아 있었다 — 이 세션이 로컬 Postgres(Docker,
> 포트 5434)를 띄우고 마이그레이션을 실제로 완성했다: `data/dbcompat.py`(sqlite3 호환 계층)·
> `data/pg_isolation.py`(스파이크별 격리 스키마) 신설, `backend/db.py`·`mcp_server/db.py` 의
> `read_only()` 물리적 강제 재구현, `disposal.py`(read_only 미전환으로 `disposal_api_contract`
> 의 이전 "26/26" 이 스테일 SQLite 파일을 읽은 가짜 통과였음을 발견·수정) 등. **33/33 스파이크
> 전부 실 Postgres 위에서 재검증 완료**(`bundle_integrity` 는 픽스처 DB 변형 7종이 전부
> `sqlite3.connect()` 직결이라 포팅 규모가 커 3차 체크포인트에서는 사용자 승인으로 skip했으나,
> 이어받은 세션(4차 체크포인트)이 완료했다 — 아래 참고).
>
> **1,051→1,052 (4차 체크포인트, 이어받은 세션)**: `bundle_integrity.py` 를 `data/pg_isolation.py`·
> `data/dbcompat.py` 기존 인프라로 포팅 완료 — 픽스처 7종을 격리 Postgres 스키마로 교체하고
> `sqlite3.connect()` 직결을 걷어냈다. 검사 건수는 **25→26**(원본 25건 + 신설 "격리 스키마
> 잔존 확인" 1건, 1,026+26=1,052). 로직이 바뀐 검사는 ⑫(자산 DELETE → `asset_disappeared`)
> 단 1건뿐 — SQLite 는 `foreign_keys` 기본 OFF 라 자산 행을 그냥 지울 수 있었지만 Postgres 는
> `equipment.asset_id → assets.asset_id` FK 를 강제해 `DELETE` 전에 `equipment.asset_id` 를
> NULL 로 비워야 했다(검사 의미는 동일). 나머지 24건은 기계적 포팅. 포팅 착수 전 사전 오염
> 사고를 하나 발견·정리했다 — 미포팅 `a2a_e2e_integration_spike.py` 가 과거 실행에서
> `db_path` 를 `Path` 객체로 넘겨 `backend/db.py::connect()` 의 `isinstance(db_path, str)`
> 분기를 벗어나 조용히 공유 `public` 에 썼다(`po_drafts.PO-0117` 이 `approved` 로 남고
> `traces` 에 `session_id='S1'` 잔여 2행). `data/seed.py --with-error-codes` 재시드로 정리
> (37/37, `error_codes` 70행, `PO-0117` `pending` 복구 확인). 같은 방식으로
> `a2a_outbound_contract.py`(4건)·`a2a_e2e_integration_spike.py`(2건)도 함께 포팅했다 — 이
> 둘은 아직 공식 33종 밖이라 위 헤드라인 1,052건에는 포함하지 않았다(포함하면 1,058). 세
> 파일 전부 격리 스키마 잔존 0개·`error_codes` 70행·ruff clean 확인. **부수 발견 및 같은
> 세션에서 즉시 수정**: 커밋 `5895c2e`("A2A 코드 테스트 75건 추가")가 만든 pytest 8파일
> (`backend/a2a/test_*.py` 5개 + `backend/routers/test_a2a.py`·`test_po_a2a_trigger.py`·
> `backend/services/test_po_a2a_dispatch.py`)이 CLAUDE.md 공식 pytest 목록(3파일·83건)에
> 전혀 반영이 안 돼 있었고, 첫 실측 결과 86건 중 46건 FAIL 이었다. 사용자 승인으로 같은
> 세션에서 바로 원인을 고쳤다 — 근본 원인은 `backend/a2a/payloads.py`·`backend/a2a/trace.py`
> 의 `connect(Path(db_path) if db_path else None)` 패턴(DSN 문자열을 `Path()` 로 감싸면
> `isinstance(db_path, str)` 검사를 벗어나 조용히 실 DB로 샌다, 위 오염 사고와 동일 계열)과
> `backend/conftest.py` 의 `db_path`/`seed_po`/`link_finallq` 픽스처가 여전히 SQLite 파일을
> 만들던 것(격리가 애초에 안 됐다) 두 가지였다. `Path()` 래핑 제거 + 픽스처를
> `data/pg_isolation.create_isolated_schema()` 기반으로 교체 + 파일 내부 `_traces()` 헬퍼
> 3곳 · `MAINTQ_DB` env var 세팅 2곳(Postgres 가 안 읽는 SQLite 시절 변수, `s10_smoke.py` 와
> 같은 함정)을 같은 패턴으로 정리 — **86/86 PASS**. 별개로 `test_client.py` 등 async
> 테스트가 `pytest-asyncio` 미설치로 떨어지고 있던 것도 발견(Postgres 무관, 실행 커맨드에
> `--with pytest-asyncio` 필요). 공식 목록에 이 8파일을 반영해 pytest 총 **83→169건**
> (3파일군 + 4파일군, 위 "회귀 스위트" 절에 반영 완료).
>
> 건수 변화 3가지, 이번 마이그레이션과 무관한 것까지 섞여 있어 구분해 적는다:
> - **`db_concurrency` 13→7** (이번 세션 원인). WAL·busy_timeout·`journal_mode` 는 SQLite
>   전용 개념이라 Postgres 판 `backend/db.py`·`mcp_server/db.py` 에는 그 코드 자체가 없다 —
>   해당 검사(원본 ①②③⑤⑥⑧⑨)는 이식이 아니라 "대상 없음"으로 명시하고 1건으로 합쳤다. D10
>   트리거·D15 경계 검사는 그대로 포팅했고, "동시 쓰기가 안 막힌다"는 주장은 MVCC 식으로
>   재실측(④')했다.
> - **`llm_provider_contract` 14→23** (이번 마이그레이션과 무관 — 표 갱신 누락이었을 뿐).
>   D115(Elice LLM provider 추가, `docs/10_DECISIONS.md` 에 이미 등재)가 검사 9건(⑮~㉓)을
>   더한 것이 원인 — 코드·스파이크는 이미 커밋돼 있었고 이 표만 반영이 안 돼 있었다.
> - **`ui_honesty_contract` 271→291** (이번 마이그레이션과 무관 — 다음 세션이 원인을 확정했다).
>   `git show 7ff38b2 --stat -- frontend/`(Sprint 16 Stage 3, A2A 응답 표시 4종 — 다른 세션이
>   이 세션 착수 전 이미 push)로 대조한 결과, **원인은 이미 `spikes/ui_honesty_contract.py`
>   자신의 주석(MQ-1611)에 다 적혀 있었다** — CLAUDE.md 로 옮겨 적는 것만 빠졌던 것이다.
>   +20 은 계약 +18 · 게이트 +2 두 갈래: **계약(L2) +18** = L2 스캔 파일 39→42(+3) × 6항목 —
>   `components/asset/LoanAssessmentHistory.tsx`·`app/(console)/manager/a2a/page.tsx`(기존
>   글롭에 자동 편입) + `components/queue/WithdrawalStatusPanel.tsx`(`Decision*.tsx` 접두어
>   불일치로 `L2_EXTRA` 에 수동 등재, `RepairDetail.tsx` 선례와 같은 방식). `components/chat/
>   A2aResultCard.tsx` 는 `components/chat/*.tsx` 글롭 자체가 없어 편입 안 됨(의도적 사각지대,
>   다른 chat 컴포넌트와 동일). **게이트 +2** = Stage 3 신설 `frontend/lib/a2a.ts`(skillView·
>   a2aStatusTone, D87)가 제약 게이트 C9·C10(MQ-1605)으로 새로 등재됨(`ownership.ts`·
>   `maintValue.ts`·`deadlines.ts`·`riskGrade.ts` 4파일 8건 → 5파일 10건). 뮤턴트 8종·메타 5건은
>   무변경. 18+2=20, 271+20=291 — 실행 결과("신규 계약 검사 268건(L1 15·L2 252·D64 1) + 제약
>   게이트 10 + 뮤턴트 8 + 메타 5 = 291")와 산술이 정확히 일치, PASS 291/291(신규 D87 위반 없음).
>
> 그 외 **29스위트는 건수 무변화** — SQLite 커넥션을 Postgres 로 바꿔도 계약 자체(검사 개수·
> 의미)는 그대로였다는 뜻이다. 이 과정에서 실제 버그 2건을 발견·수정했다(스파이크가 아니라
> 마이그레이션 배선 자체의 결함):
> - `s10_smoke.py`·`sp3_sse_events.py` — 실 uvicorn/MCP stdio 서브프로세스에 `MAINTQ_DB`
>   (SQLite 시절 변수, Postgres 코드는 안 읽는다)만 넘기고 있어서, 자식이 조용히 **공유
>   `public` 스키마에 실제로 썼다.** `s10_smoke` 는 최초 무수정 실행에서 `decisions` 테이블에
>   `DEC-0001`·`DEC-0002` 가 실제로 남는 것을 확인(`docker exec ... psql` 로 직접 봄) —
>   `data/seed.py --with-error-codes` 재시드로 정리(37/37 재확인). `sp3_sse_events` 는 연속
>   재실행에서 `traces` 에 72행이 누적돼 두 번째 실행의 seq 연속성 검사(⑭)를 실제로 깨뜨렸다.
>   두 스파이크 모두 자식 프로세스 env 를 `MAINTQ_DB` 대신 `DATABASE_URL`(격리 스키마 DSN,
>   `data/pg_isolation.py`)로 바꿔 해소 — **서브프로세스를 띄우는 스파이크는 전부 이 패턴을
>   따라야 한다**(D10 절대 규칙과 별개로, 격리 자체가 깨지면 회귀가 통째로 무의미해진다).
> - `disposal_sign_contract`·`approvals_contract` 의 "mutant table" 기법(CHECK 제약을 벗긴
>   사본 테이블에서 같은 SQL 이 통과하는지 대조)이 Postgres 에 없는 `sqlite_master` 에
>   의존해 두 스파이크 모두 부분 미구현(N/A) 상태였다 — `CREATE TABLE ... (LIKE decisions
>   INCLUDING ALL)` + `pg_get_constraintdef()` 이름 조회 기반으로 재구현해 해소(disposal_sign
>   24/27→26/26, approvals 는 N/A 항목이 정상 대조로 전환).
>
> **재발 방지책이 필요하면**: `docs/10_DECISIONS.md` 에 Postgres 마이그레이션 자체를 다루는
> D-결정이 아직 없다 — 다음 세션이 D10 가드 재구현 방식·`dbcompat` 계층·`pg_isolation` 스키마
> 전략·"서브프로세스는 `DATABASE_URL` 을 격리 DSN 으로 받아야 한다" 규칙을 D 번호로 등재할 것.

> **pytest 83→99 · spikes 1,052→1,075 · seed 37→41 (2026-08-24, "빠른 정리" 세션)**:
> `data/test_expenditure_limits.py`(16건, MQ-1703 — 예산 한도·1일 누적 한도·FDS·SoD 4종
> 순수 함수, D119)가 커밋 시점부터 이미 존재했으나 위 "회귀 스위트" 절 공식 목록에 반영이 안
> 돼 있었다 — 실측(`uv run --with pytest python -m pytest data/test_expenditure_limits.py -q`,
> 16 passed)으로 확인 후 공식 목록에 편입하며 커맨드를 3파일 합산 → **4파일 합산**으로 갱신했다.
> 같은 세션에서 이미 실측 확정돼 있던 spikes(`api_contract` 52·`ui_honesty_contract` 303,
> Sprint 17·18 반영분)·seed 41건(D119 CHECK 제약 검증 ㊲~㊵ 4건 추가)도 위 스위트별 표·헤드라인에
> 함께 정정했다 — 실행 결과가 표기와 어긋나 있던 것을 이 세션에서 발견·정리.

> **1,120→1,183 (2026-09-04, D124·D125 docx 배선 + facts 읽기 도구)**: 신설 스위트
> `docx_contract` **63건**이 델타의 **전부**다 — 기존 33스위트는 건수가 하나도 바뀌지 않았다.
> `prompt_rules`(24) · `tools_profile_contract`(7) · `s10_smoke`(17) 은 **기대값만** 고쳤고
> 검사 개수는 그대로다(도구 20→21종 반영).
>
> 🔴 **기존 스위트 2개가 진짜 회귀를 잡았다 — 기록해 둔다.** 도구를 `server.py` 에 등록하고
> `backend/agent/prompts.py` 의 `EXT_TOOLS` 에 올리지 않아 `prompt_rules ㉔` 가 FAIL 했다.
> 그 검사는 *"Sprint 11 이 `track_deadlines`·`assess_risk_grade` 로 똑같이 한 적이 있다"* 는
> 이유로 만들어진 것이고, **이번에 같은 실수가 실제로 재발했다.** `s10_smoke ②` 는 `/health`
> 의 도구 수 20 을 하드코딩해 함께 걸렸다. 둘 다 같은 세션에서 해소.
>
> 🟡 **`a2a_partner_tools_contract ⑤-a` 는 이 브랜치와 무관한 기존 오염이다** — 공유 `public`
> 스키마의 `traces` 에 `CHAIN-LOAN-verify0903`(세션 `S-verify-0903`, 2026-09-03 05:42 UTC)
> 4번째 a2a 체인이 남아 있어 *"필터 없음 → 3스킬"* 이 `count=4` 로 떨어진다. 이 브랜치 첫
> 커밋(21:56 KST)보다 7시간 앞서고, 이 브랜치는 a2a·trace 파일을 한 줄도 건드리지 않았다.
> **근본 원인은 그 스파이크가 `MAINTQ_DB` 를 쓴다는 것**이다 — Postgres 는 그 변수를 읽지
> 않으므로 격리가 안 되고 공유 `public` 을 본다(CLAUDE.md 가 이미 기록한 함정).
>
> ✅ **2026-09-04 해소 (D130).** 위 진단은 방향은 맞았지만 **한 걸음 모자랐다** — 그 스파이크는
> 공유 `public` 을 *보기만* 한 게 아니라 실행마다 **직접 6행을 썼다**(실측: `traces` 0 → 6,
> `session_id='sess-a2a-spike'`). `record_a2a_trace()` 가 `backend/db.py` 를 거치는데 그쪽은
> `MAINTQ_DB` 를 읽지 않아 상속받은 `DATABASE_URL` 로 실 DB 에 쓴 것이다. 즉 *"남아 있던
> 기존 오염"* 의 출처가 바로 이 스파이크 자신이었다. `pg_isolation` 격리 스키마로 전환해
> 해소했다(22건 유지 · `traces` 0 → 0 확인).

> ⚠ **러너 신뢰성 — 재시도가 필요할 수 있다 (Windows).** 29스위트를 연속 실행하면 **소켓 고갈**로
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
| **사람이 해야 할 일** | `TODO_직접할일.md` — Claude가 대신 처리하지 말 것 (매뉴얼 다운로드, 처분 문서 문안 검수, 안전 문구 승인) |
| 최근 커밋 흐름 | `git log --oneline -10` (접두어로 마일스톤 확인) |
