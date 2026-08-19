# MaintQ — 프로젝트 메모리

설비 진단부터 부품 발주까지 연결하는 B2B 제조 보전 AI 에이전트.
주제는 **도구 오케스트레이션**.

## 반드시 먼저 읽을 문서

작업 전 관련 문서를 확인할 것. 설계와 다른 구현을 하려면 먼저 `docs/10_DECISIONS.md`에 결정을 추가하고 진행:

- `docs/README.md` — 문서 지도. 어느 문서를 열지 모를 때 먼저
- `docs/00_MVP_SCOPE.md` — **반드시 구현할 기능 목록**. 착수 전 "이게 MVP인가 백로그인가" 판단
- `docs/10_DECISIONS.md` — 설계 결정 **D1~D102**. **여기 있는 결정과 충돌하는 코드를 쓰지 말 것**
- `docs/02_SCENARIOS.md` — S1~S4. 모든 기능은 이 시나리오 중 하나에 복무해야 함
- `docs/04_MCP_TOOLS.md` — 도구 입출력 계약(코어 7종 §1~§7 + **확장 11종** §8~§18). 임의 변경 금지
- `docs/05_DB_SCHEMA.md` — 테이블 **23절(실제 24개)** + 시드 케이스 맵
  (절 번호는 `§1`~`§9`+`§1-B` 로 10절, Sprint 6 이 `§11`~`§17` 로 이어받고 **Sprint 8 이 `§18`(`partner_links`) 을 더한다**,
   **Sprint 10 이 `§19`(`part_lifecycle_mock`), Sprint 11 이 `§20`~`§23`(F5·F6 4테이블) 을 더한다**
   — **`§10` 은 존재하지 않는다**.
   `§7` 이 `suppliers`·`supplier_parts` 두 테이블을 함께 다뤄 절 수보다 테이블이 1개 많다)
- `docs/06_REPO_API.md` — 폴더 구조·API·SSE 이벤트 규격
- `docs/09_RUNTIME.md` — 시퀀스·루프 상한·장애 모드

## 절대 규칙 (위반 금지)

1. **MCP 도구는 `po_drafts`·`decisions`·`repair_records` 에 draft INSERT만 가능.** UPDATE 코드를 도구에 추가하지 말 것.
   상태 전이는 사람 전용 API만 — `backend/routers/po.py`(발주) · `backend/routers/decisions.py`(처분) ·
   `backend/routers/repairs.py`(수리, D98) (D10·D81)
   - 쓰기 도구는 **3종**: `create_po_draft` · `generate_disposal_document` · `create_repair_record`.
     커넥션도 분리한다(`db.draft_writer()` / `db.decision_writer()` / `db.repair_writer()`) —
     섞으면 TEMP TRIGGER 잠금이 사라진다
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
  - 확장 **11종**은 `MAINTQ_TOOLS_PROFILE=full` 에서만 등록된다. **기본은 `core`** (D69·**D88** — 평가는 `core` 에서만 인정)
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
- `data/rules/test_rules.py` · `backend/agent/test_llm_cache.py` — 룰 카탈로그(근거 무결성 ·
  **발화 가능성**(D77) · **해제 가능성**(D78)) + **LLM 응답 카세트**(D104 — 키·값 직렬화·
  `CachingClient`·`stats_line()`)
  ⚠ 실행 커맨드: **`uv run --with pytest python -m pytest data/rules/test_rules.py backend/agent/test_llm_cache.py -q`**
  (`uv run python -m pytest` 는 pytest 미설치로 **실행되지 않는다**)
- `spikes/` — **30종** (`ls spikes/*.py` 와 일치해야 한다):
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
  **deadline_risk_contract**
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

**실측 기준선 (2026-08-19, P30 해소 후)** — spikes **30스위트 / 872건** · seed **35건**(㉖ `mfr_part_no` D97 ·
㉗~㉙ Sprint 9 `repair_records`/`error_codes` 신설 · ㉚ `error_codes.actions` 병합 검증 MQ-919 ·
㉛ Sprint 10 `part_lifecycle_mock` · ㉜~㉟ Sprint 11 F5·F6 4테이블 `deadlines`/`incidents`/
`ownership_checks`/`risk_profile`) · pytest **70건**(`data/rules/test_rules.py` 46 +
`backend/agent/test_llm_cache.py` 신설 24 — D104 카세트, 커맨드가 2파일 합산으로 바뀐다) ·
프론트 라우트 **18개**(`npx next build` — Sprint 10 MQ-1001 이 `/manager/expenditure`·
`/technician/asset/[assetId]/evidence` 2개, MQ-1002 리뷰 픽스가 `/manager/repair/[repairId]` 1개,
Sprint 12 MQ-1204 가 `/manager/deadlines`·`/manager/risk-grade` 2개 증가: 16→17→18). spikes 스위트별 건수:
`a2a_identity_contract 19` ·
`agent_loop_contract 35` · `api_contract 28` · `approvals_contract 26` · `asset_tools_contract 49` ·
`bundle_integrity 25` · `citation_render 18` · `db_concurrency 13` · `deadline_risk_contract 18` ·
`disposal_api_contract 26` ·
`disposal_sign_contract 26` · `eval_replay_guard 16` · `eval_score_contract 36` · `law_fetch_contract 28` ·
`llm_provider_contract 14` · `lookup_contract 14` · `mcp_client_contract 15` · `ownership_api_contract 10` ·
`prompt_rules 24` · `rag_contract 12` · `repair_flow_contract 19` · `rules_db_load 25` · `s10_smoke 17` ·
`s4_smoke 10` · `sp2_mcp_roundtrip 20` · `sp3_sse_events 22` · `tools_profile_contract 7` ·
`trace_persist 17` · `ui_honesty_contract 253` · `write_tool_contract 30`

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
