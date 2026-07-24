# Sprint 3 — M2 완주 (에이전트 루프 + trace 관통)

**수립일**: 2026-07-23 · **상태**: **Stage 1·2 완료** · Stage 3 착수 전 (선행 2건)

## 목표

`00_MVP_SCOPE §6`의 "trace는 별도 단계가 아니라 에이전트 루프와 같이 나온다"를 실제로 관통시킨다.
**에이전트 루프 → SSE 4종 → `traces` 영속화 → `GET /trace` → 화면 B 링크 착지**까지가 끊기지 않게 만든다.

**범위 밖 (의도적)**
- 화면 A(`DiagnosticConsole`) 라이브 SSE 연동 — M3
- `eval/testset.json` 20문항 — 기대 정답 확정이 사람 항목(`TODO_직접할일.md`)
- 환각률 LLM judge — API 키 필요
- `07_BACKLOG` P1~P20 — 한 건도 승격하지 않음

---

## 1. 계획 수립 경과

`/sprint 3` 파이프라인: PM 초안 → tool-builder 현실성 평가 → PM 재계획 → 확정.

**tool-builder 평가 결론: 계획 수정 필요 (Y).** 실증 실험 2건으로 설계 결함 3개를 잡았다.

### 실측으로 깨진 것

| # | 결함 | 근거 | 영향 |
|---|---|---|---|
| 1 | `traces` CHECK가 `token`을 거부 | `data/seed.py:155` `CHECK (event_type IN ('tool_call','tool_result','block'))`. 실측 `IntegrityError` | 초안대로면 TraceWriter가 첫 턴에 실패 |
| 2 | **async generator 안에서 MCP stdio 세션을 열면 깨진다** | 실측: 소비자 취소 시 `RuntimeError: Attempted to exit cancel scope in a different task`. 실패한 cancel scope가 **무관한 후속 태스크까지 취소** | `StreamingResponse` + 클라이언트 조기 종료가 정확히 이 패턴. 초안의 MQ-306 구조 전제가 무효 |
| 3 | MCP SDK가 env를 화이트리스트만 상속 | `env=None`이면 `get_default_environment()`. `spikes/write_tool_contract.py:68`만 우회 중 | `MAINTQ_DB` 격리가 조용히 실패 → **테스트가 실 DB에 draft를 쓴다** |

3번이 특히 위험하다 — 테스트는 통과하면서 실 데이터를 오염시키는 종류다.

### 그 외 지적 (요약)

- 계약 공백 4건(`GET /trace` 응답 스키마 · `TraceStatus`에 error/timeout 부재 · `po_card` hold 페이로드 · 타임아웃 status)이 병렬 태스크를 서로 다른 가정으로 몰아넣는다
- `rag_search_manual` 부재로 MQ-310이 **통과 불가능한 지표**를 구현하게 된다 (D30 인용률이 "lookup **또는 rag** 결과 page"를 요구)
- S100 안전 페이지 물리 p.2에 `print_page_offset=16` 적용 시 **인쇄 p.-14**
- `create_po_draft` 응답에 `part_name`·`supplier_name`·`lead_days`가 없어 po_card 조립처 미정
- 오프셋을 읽는 manifest 로더가 레포에 **하나도 없다** — D32의 "백엔드 렌더 1곳"이 구현체 없이 비어 있었다
- MCP 서브프로세스와 백엔드가 같은 SQLite에 동시 쓰기 → `database is locked` 가능. `busy_timeout`·WAL 둘 다 없음

### 범위 결정

PM은 **(b) `rag_search_manual`을 스프린트에 추가**를 택했다.
근거: D30 인용률 분모가 rag 결과 page에 걸려 있어 rag 없이는 MQ-310이 구조적으로 통과 불가.
D1이 정한 건 "정의=룩업 / 절차=검색"이라는 **경계**이지 검색 알고리즘이 아니므로,
검색 백엔드를 교체 가능한 형태로 두면 임베딩 미결과 무관하게 진행된다 (D47·D48 선행).

**결과: 태스크 11개 → 14개, Stage 1이 5개 → 7개.**

---

## 2. 확정된 결정 (D40~D52) — `10_DECISIONS.md` 반영 완료

사용자 검토에서 **3건이 바뀌었다**:

| 원안 | 확정 |
|---|---|
| D47 키워드만으로 시작 | **키워드 + 임베딩 하이브리드** — 인터페이스를 먼저 고정하고 dense scorer 는 주입식. 임베딩 모델·가중치는 **D51**로 분리(`rag_sizing.md` 실측 후) |
| D41 `traces` UNIQUE 만 | **스키마 보강 4건** — `traces` UNIQUE + **`users` 테이블 신설** + `po_drafts`/`error_history` FK + `error_history.recorded_by`. MQ-301 에 합침 |
| (인증 미논의) | **D52** — 회사 IdP(Google Workspace) 1종만, **개인 소셜 로그인 제외**. 실제 인증 플로우는 백로그 **P21** |

세부 문안은 `10_DECISIONS.md` D40~D52 참조.

| # | 결정 | 대안 / 채택 이유 | 차단 |
|---|---|---|---|
| D40 | LLM 호출을 `LlmClient` 인터페이스로 분리, 회귀는 **스크립트 드라이버**. `get_client()`는 키 없으면 **조용히 폴백하지 않고 실패** | 실 API만 / VCR 녹화. 루프 정책·traces는 평가 판정 소스인데 API 키·과금에 묶이면 회귀가 상시로 못 돈다. 폴백 금지는 데모에서 가짜 응답을 진짜로 착각하는 사고 방지 | Stage 2 |
| D41 | **스키마 보강 4건** — `traces` `UNIQUE(session_id, seq)` + **`users` 테이블 신설** + `po_drafts`/`error_history` users FK + `error_history.recorded_by`. **`token`은 SSE만, 저장 안 함** | seq 중복 허용 / 표시명 하드코딩 유지. seq 중복이 조용히 통과하면 순서 판정이 깨진 걸 아무도 모른다. `users`는 `po.py`의 하드코딩 `USER_NAMES`를 대체하고 감사 추적(P5)의 FK 대상을 만든다 | **Stage 1** |
| D42 | MCP 세션은 **백엔드 lifespan이 소유하는 단일 워커 태스크**가 열고 닫는다. 스트리밍 제너레이터는 세션을 열지 않고 큐로 위임. `env={**os.environ}` **명시 상속** | 턴/호출당 세션 생성. 실측 결함 2·3의 직접 대응. 성능도 같은 결론(spawn 0.9~1.2s vs 호출 0.01s → 8콜에 +8초) | **Stage 1** |
| D43 | `GET /trace` 응답 스키마 고정 `{session_id, count, events:[{seq,event,tool,data,ts}]}`. **없는 세션은 404가 아니라 200+`count:0`**, 역할 제한 없음 | 404. 404면 `services/po.trace_url`이 항상 유효하다는 전제가 깨져 프론트 분기가 늘어난다 | Stage 2 |
| D44 | 프론트 `TraceStatus`에 **`"error"` 추가**(4종→5종). **timeout은 타입 신설 없이** `error` + summary `✗ timeout` 표기 | warn 재사용 / timeout까지 타입 신설. 09_RUNTIME §3이 "✗ error"(붉은 점)를 요구하는데 warn(주황)으로 뭉개면 장애와 분기를 구분 못 한다 | Stage 3 |
| D45 | `po_card(variant:"hold")` payload 고정: `{variant, reason, checklist:[{label, citation}], repeated:{count, window_days}}` | 없음. D35가 "같은 슬롯의 variant"까지만 정하고 페이로드를 비워 둔 구멍 | Stage 2 |
| D46 | 도구 타임아웃은 **`status:"error"` + `reason:"timeout"`**. D9의 status 4종 유지, 세분화는 `reason`이 담당 | status 5종 확장. `create_po_draft`가 이미 `reason:"moq_not_met"`으로 같은 패턴을 쓴다. status를 늘리면 S2·S4 분기와 평가 판정이 전부 영향받음 | Stage 2 |
| D47 | **키워드 + 임베딩 하이브리드.** `search(model, query, top_k, dense=None)` 인터페이스를 먼저 고정하고 dense scorer는 **주입식**. 초기엔 키워드만 활성 | 키워드만 / 임베딩만 / 결정까지 보류. 이 도메인은 키워드가 강하지만(에러코드·품번) 정비사 발화는 자연어일 수 있어 dense가 필요하다. **가중치는 실측으로 정해야 하므로** 인터페이스만 먼저 고정 | **Stage 1** |
| D48 | 검색 **구현체는 MCP 서버 쪽(`mcp_server/rag.py`)**. `backend/rag/`는 만들지 않고 ingest는 `data/chunk_manual.py`가 겸함 | 06 트리 원안 유지. 도구는 MCP 프로세스에서 실행되므로 `backend/rag/`를 import하면 **D15 프로세스 분리가 코드 공유로 깨진다** | **Stage 1** |
| D49 | 인쇄 페이지 환산 결과가 **1 미만이면 오프셋 미적용**, 물리 페이지만 표시 | 음수 노출 / 케이스별 하드코딩. S100 안전 지침 물리 p.2 → 인쇄 p.-14. 표지·안전지침은 본문 쪽번호 체계 밖. D26·D32 유지하고 그 1곳에 경계 조건만 추가 | **Stage 1** |
| D50 | `error_codes`가 **0행이면** `not_found`가 아니라 **`status:"error"`, `reason:"catalog_not_loaded"`** | 미적재도 not_found 처리. **0행은 가정이 아니라 현재 상태다**(승인 게이트). not_found를 주면 모든 코드가 S4로 흘러 **지표가 가짜 100%**가 되고 스모크도 위양성으로 통과한다 | **Stage 1** |
| D51 | 임베딩 모델·벡터스토어·**하이브리드 가중치**는 `rag_sizing.md`(MQ-305 산출) 실측을 보고 결정. 그 전까지 dense 비활성 | 지금 임의 선택. 청크 수·토큰량을 모르면 로컬/API 선택 근거가 없고, 가중치도 eval로 조정할 값이라 사전에 정하면 숫자를 지어내는 셈 | Stage 2 (dense 활성화만) |
| D52 | 인증은 **회사 IdP(Google Workspace) 1종**만. **개인 소셜 제외**. `hd` 클레임 + `users` 사전 등록 **두 겹**, **`role`은 OAuth가 아니라 `users`가 부여**. 구현은 백로그 **P21** | 개인 소셜 다종 / 자체 비밀번호. 개인 계정이면 퇴사 후 `decided_by` 추적이 끊겨 감사 로그(P5)가 무너진다. role을 OAuth가 정하면 D4(역할 분리)가 무의미 | 스프린트 밖 (P21) |

> 문서 반영: D41→`05_DB_SCHEMA`·`seed.py`, D43·D45→`06_REPO_API §2.1`, D46→`04_MCP_TOOLS`, D47·D48→`06_REPO_API §1`.
> **문서 수정은 태스크 DoD에서 제외**하고 `/done`에서 일괄 반영한다 — 같은 문서를 여러 태스크가 고치면 그게 곧 충돌이다.

---

## 3. 스테이지 계획

### Stage 1 — 블로커 무관 기반 (병렬 7)

| TASK | 제목 | 범위 | 선행 |
|---|---|---|---|
| MQ-301 | traces 영속화·조회 + 스키마 보강 | `backend/agent/trace.py`, `data/seed.py` | D41 |
| MQ-302 | MCP 클라이언트 — lifespan 워커 구조 | `backend/agent/mcp_client.py`, `backend/main.py` | D42 |
| MQ-303 | 시스템 프롬프트 + 안전 상수 | `backend/agent/prompts.py`, `TODO_직접할일.md` | — |
| MQ-304 | `lookup_error_code` (6/7) | `mcp_server/` | D50 |
| MQ-305 | 매뉴얼 청킹 파이프라인 + 사이징 자료 | `data/chunk_manual.py` | D47·D48 |
| MQ-312 | manifest 로더 + 인쇄 페이지 환산 | `backend/manifest.py`, `backend/sse.py` | D49 |
| MQ-313 | SQLite 동시성 (WAL + busy_timeout) | `backend/db.py`, `mcp_server/db.py` | — |

### Stage 2 — 루프 · 조회 · 검색 (병렬 3)

| TASK | 제목 | 범위 | 선행 |
|---|---|---|---|
| MQ-306 | 에이전트 루프 + LLM 추상화 | `backend/agent/{llm,loop}.py` | MQ-301·302·303·312, D40·D45·D46 |
| MQ-307 | `GET /api/chat/{session_id}/trace` | `backend/routers/chat.py` | MQ-301, D43 |
| MQ-314 | `rag_search_manual` + 키워드 retriever (7/7) | `mcp_server/rag.py`, `mcp_server/tools/` | MQ-305, D47·D48 |

### Stage 3 — 관통 배선 (병렬 2)

| TASK | 제목 | 범위 | 선행 |
|---|---|---|---|
| MQ-308 | `POST /api/chat` 루프 배선 (replay 재작성 포함) | `backend/routers/chat.py` | MQ-306·307 |
| MQ-309 | 화면 B trace 페이지 | `frontend/` | MQ-307, D43·D44 |

### Stage 4 — 판정기 · 스모크 (병렬 2)

| TASK | 제목 | 범위 | 선행 |
|---|---|---|---|
| MQ-310 | traces 기반 지표 판정 `eval/score.py` | `eval/`, `spikes/` | MQ-301·314 |
| MQ-311 | S4 관통 스모크 (위양성 방지) | `spikes/` | MQ-308 |

### 구성 근거

- **Stage 1의 7개는 서로 파일이 겹치지 않고 선행이 없다.** 사람 승인에도 막히지 않는 유일한 묶음이다.
- **MQ-312를 Stage 2로 미루면 안 된다** — MQ-306이 `print_page`를 스스로 계산하게 되어 D32의 "변환은 1곳"이 두 곳으로 벌어진다.
- **MQ-313을 미루면 안 된다** — Stage 2 이후 모든 스파이크가 `database is locked`를 랜덤하게 맞는다.
- **`chat.py`를 만지는 건 MQ-307·MQ-308뿐이고 스테이지를 갈랐다.** `mcp_server/server.py`를 만지는 MQ-304·MQ-314도 마찬가지.
- **MQ-309의 파일 금지 완화**: D44가 `TraceStatus` 확장을 요구하는데 색·글리프가 `TraceStep.tsx` 하드코딩이라 수정 불가피. 이번 스프린트에 화면 A 태스크가 없어 충돌 상대가 없고, **추가만 하고 기존 4종의 의미·색은 바꾸지 않는다**는 제약으로 M3 리스크를 막는다.

### 선행 관계

```
MQ-301 ─┬──────────────► MQ-306 ──┬─► MQ-308 ─► MQ-311
MQ-302 ─┤                         │
MQ-303 ─┤                         │
MQ-312 ─┘                         │
MQ-301 ───► MQ-307 ───────────────┴─► MQ-309
MQ-301 ─┐
MQ-305 ───► MQ-314 ───► MQ-310
MQ-304, MQ-313  (독립)
```

---

## 4. 태스크 명세 (실행 기준)

각 태스크의 전체 명세는 길어 요점만 남긴다. **tool-builder에 전달할 때는 아래 항목을 그대로 인용한다.**

### MQ-301 traces 영속화 + 스키마 보강 (D41 — 범위 확대)

**스키마 변경 4건을 이 태스크가 전부 소유한다** (`data/seed.py` 를 만지는 Stage 1 태스크는 MQ-301뿐):
1. `traces` 에 `UNIQUE(session_id, seq)`
2. **`users` 테이블 신설** — DDL 은 `05_DB_SCHEMA §1-B` 그대로. 시드는 `tech-01`(김OO)·`tech-02`(이OO)·`mgr-01`(박OO) 3행, `auth_provider='local'`, 회사 이메일 형식 예시
3. `po_drafts.requested_by`/`decided_by` → `users` FK
4. `error_history.recorded_by` 추가 + FK (시드분은 NULL)

**표시명 매핑 이관**: `backend/services/po.py` 의 하드코딩 `USER_NAMES` 를 제거하고 `display_name()` 을 `users` 조회로 바꾼다. **함수 시그니처는 유지** — MQ-306·307 이 호출한다.

**주의**: FK 가 걸리므로 시드 순서가 `users` → `po_drafts`/`error_history` 여야 한다. `PRAGMA foreign_keys=ON` 상태에서 순서가 틀리면 즉시 실패한다.

- `TraceWriter(session_id)` — `tool_call`/`tool_result`/`block`/`citation` 메서드가 **SSE 이벤트 생성 + traces INSERT를 한 몸으로** 수행(A5를 코드로 강제). `read_trace(session_id)` → D43 스키마
- **token 메서드를 두지 않는다** (D41). docstring에 "CHECK가 3종만 허용하며 token INSERT는 즉시 실패 — 버그가 아니라 설계"를 근거와 함께 명시
- seq는 `MAX(seq)+1`로 시작해 이어쓴다. UNIQUE 위반 시 **삼키지 말고** 1회 재시도 후 `persist_errors` + `logging.error`
- INSERT 실패(DB 잠금 등)는 예외를 삼키고 `persist_errors += 1` — trace 저장 실패로 사용자 스트림이 끊기면 안 된다. 단 `logging.warning`
- `payload`는 SSE `data`와 **바이트 동일** (평가가 두 소스를 대조 — D30). `ts`는 UTC `...Z` (D39)
- **DoD**: `spikes/trace_persist.py` ≥10건 (token INSERT 거부 · seq 이어쓰기 · UNIQUE 위반 · 재시도 · payload 동일성 · 쓰기 실패 시 이벤트는 정상 반환). **임시 DB에서만 실행**
- **DoD 추가 (D41 확대분)**: `data/seed.py` 케이스 맵 8건 회귀 + **⑨ users 3행 적재** ⑩ `po_drafts.requested_by` 가 실재하지 않는 user_id 면 FK 거부 ⑪ `display_name('tech-01') == '김OO'` 이 DB 조회로 동작 ⑫ 하드코딩 `USER_NAMES` 가 코드에서 사라졌는지(grep). 스키마 변경 후 `api_contract.py`·`write_tool_contract.py` 회귀

### MQ-302 MCP 클라이언트 (lifespan 워커)
- `start()`/`stop()`/`call()`/`list_tools()`/`ready`. 세션은 **워커 태스크 안에서 enter/call/exit** — 초안의 "run_turn이 `async with`로 감싼다"는 폐기 (D42)
- 호출자는 future를 큐에 넣고 `await asyncio.wait_for(asyncio.shield(fut), timeout)`. **`shield` 필수** — 제너레이터가 취소돼도 워커의 진행 중 호출이 중단되지 않아야 세션이 산다
- **`env={**os.environ}` 명시 전달** (D42) — 없으면 `MAINTQ_DB`가 자식에 안 가고 테스트가 실 DB를 오염시킨다
- 수명은 `backend/main.py` lifespan. 라우터는 `request.app.state.mcp`로 접근
- 타임아웃 → `status:"error"`, `reason:"timeout"` (D46). `summarize_result()`는 도구별 한 줄 요약
- **DoD**: `spikes/mcp_client_contract.py` ≥9건. 도구 목록은 **부분집합 비교**(MQ-304·314가 도구를 추가하므로). **⑧ 취소 안전성** — `call()` 중 취소 후 곧바로 다른 `call()`이 성공하고 cancel scope 예외 없음. **⑨ env 격리** — 임시 DB에만 행이 늘고 `data/maintq.db` 불변(mtime + row count). `assert "mcp_server" not in sys.modules` (D15)

### MQ-303 시스템 프롬프트
- `SYSTEM_PROMPT`(규칙 11개: D1 도구 경계 / S4 환각 금지 / D12 부품 특정 / S2 분기 / D35 S3 보류 / A2 다음 턴 / A6·D31 MOQ / D23·D31 지어내기 금지 / D6·D13 model enum + 확인 질문 / 안전 문구 창작 금지 / 인용은 시스템이 생성)
- `SAFETY_BASELINE` — text에 **"10분 이상"**, pages는 **물리 페이지 그대로**(iG5A 4, S100 2). **환산 금지, 소유자는 MQ-312**
- 규칙 10에 추가: "타임아웃·연결 실패로 못 조회한 항목은 '확인하지 못했다'고 말하고 공백을 지식으로 메우지 않는다"
- `TODO_직접할일.md`에 검수 대상 경로·항목 명시 (**Stage 1에서 이 파일을 만지는 태스크는 MQ-303뿐**)
- **DoD**: `spikes/prompt_rules.py` ≥10건 정적 검사 (LLM 호출 없음). "5분" 미포함 · pages 값 · "추측" 금지 문구 · A2 "다음 턴" · MOQ 상향 금지 · `build_system_prompt("iS7")` → ValueError · **`SAFETY_BASELINE`에 `print_page` 키 없음**

### MQ-304 lookup_error_code
- 04_MCP_TOOLS §1 계약 그대로. `code`는 `strip().upper()` (D25), `(model, code)` 복합키 (D13), `related_parts` 포함 (D20), `manual_page`는 물리 페이지 무가공 (D26)
- **0행이면 `status:"error"`, `reason:"catalog_not_loaded"`** (D50) — not_found를 주면 S4 지표가 가짜 100%가 된다
- **DoD**: `spikes/lookup_contract.py` ≥9건. **임시 DB + 합성 픽스처 3행**(iG5A/OHT, iG5A/OCT, S100/OHT — 같은 코드 다른 의미). **`error_codes.json`을 읽어 넣지 말 것 — 승인 게이트 우회다.** ⑨ 정상 코드가 1건이라도 있으면 미지 코드는 `not_found`(미적재와 실제로 갈리는지). `sp2` 전건 PASS

### MQ-305 매뉴얼 청킹
- manifest sha256 **실제 계산 후 대조**, 불일치면 중단 (D19). pdfplumber `extract_text()` (D24)
- **청크는 페이지 경계를 넘지 않는다** — 넘으면 어느 페이지를 인용할지 모호해져 D30 판정이 흔들린다
- JSONL 키 **정확히 7개**: `chunk_id/manual_id/model/page/section/text/char_len` (MQ-314의 입력 계약)
- **`print_page`를 넣지 않는다** (D32 — 변환 지점이 둘이 되면 안 된다). `backend/rag/`를 만들지 않는다 (D48)
- `rag_sizing.md`는 "무엇을 고를까"가 아니라 **"D47 키워드 baseline에서 벡터로 갈아탈 근거가 있는가"** 판단 자료
- **DoD**: 두 번 실행 → 산출물 sha256 동일(멱등). 페이지 경계 초과 청크 0건(자가 assert). `data/raw/` mtime 불변

### MQ-306 에이전트 루프
- `run_turn(*, session_id, message, equipment_id, user_id, llm, client, trace, store)` — **MCP 세션을 열지 않고 주입받은 `client.call()`만** (D42)
- A1 순서: `trace.tool_call` yield → `client.call` → `trace.tool_result` yield. 순서 변경 금지
- 루프 탈출: 동일 도구·동일 입력이 직전 호출과 같으면 실행하지 않고 중단. 상한 8/10/50
- **안전 블록**: 텍스트를 **문장 단위로 버퍼링**하고 flush 직전 `needs_safety_block()` 검사 → 참이면 문장보다 **먼저** safety block 발행. 문구는 반드시 `SAFETY_BASELINE["text"]` 상수(LLM 생성 금지). **근거 페이지가 없으면 안전 블록도 위험 서술도 내지 않는다**
- **citation**: `backend.sse.citation_for(model, page, section)` (MQ-312) 사용. **LLM이 말한 페이지를 쓰지 않는다** — 코드가 도구 결과에서 만들어야 D30 판정이 성립
- **po_card(draft)**: `create_po_draft` 응답에 없는 `part_name`·`supplier_name`·`lead_days`는 **도구 계약을 확장하지 않고** `services.po.get_po(po_id)`로 조립. 이어서 `stamp_identity` (D37)
- **po_card(hold)**: D45 스키마. checklist의 citation은 **rag 결과 page에서만** (근거 없는 체크리스트 금지)
- 세션 이력 20개, 도구 결과는 요약만 + `PRESERVE_FIELDS`(part_no·supplier_id·qty·unit_price·moq·lead_days·po_id)는 유실 금지 (A2)
- **`POST /api/equipment/{id}/errors`를 호출하지 않는다** (A7·D29)
- **DoD**: `spikes/agent_loop_contract.py` ≥14건, 전부 `ScriptedClient`(**API 키 불필요**). ⑫ 스트림 취소 후 재호출 정상(D42) · ⑬ hold 블록이 D45 4개 키 · ⑭ draft po_card에 part_name·supplier_name·lead_days
- `.env.example` 생성 — **모델 ID를 지어내 기본값으로 박지 말 것**, 키만 두고 주석으로 안내

### MQ-307 GET /trace
- `read_trace()` 반환을 그대로. **없는 세션은 200 + `count:0`**, 역할 제한 없음 (D43)
- 경로는 `/chat/{session_id}/trace` (prefix `/api`)
- **기존 `_replay_s1`을 건드리지 않는다** — 재작성은 MQ-308
- **DoD**: `api_contract.py` 전건 + 신규 3건 (`trace_url` 그대로 GET → 200 · 없는 세션 200/count 0 · 무작위 순서 INSERT 후 seq 오름차순). ① technician 헤더로도 200

### MQ-308 POST /chat 배선
- **작업 성격 정정**: `_replay_s1`은 `str`을 yield하는 평범한 제너레이터라 TraceWriter 경유로 바꾸려면 **본문 전면 재작성**이다. "쿼리 하나 추가"가 아니다
- `replay=s1` 쿼리로 고정 재생 보존(단 TraceWriter 경유) — SP3 회귀가 API 키 없이 계속 돌고, **MQ-309를 API 키 없이 눈으로 확인**할 수 있다
- **`chat.py`의 raw `Header` → `Depends(caller)` 교체**를 명시적 작업으로 승격. 현재 `x_user`가 ASCII·역할 검증을 안 거치는데 `stamp_identity`로 흘러간다 = **D36 위반 값이 DB에 들어갈 경로**
- `get_client()` 실패 시 500이 아니라 첫 이벤트로 안내 token
- **DoD**: `sp3` 전건 + 신규 2건(replay 후 traces에 행 · 같은 session_id 두 번 호출 시 seq 이어짐). ① `X-User`에 한글 → 400 (D36 회귀) ② 연결 끊고 재요청 → 200 + cancel scope 예외 없음 (D42 회귀)

### MQ-309 화면 B trace 페이지
- `/manager/trace/[sessionId]` + `lib/trace.ts` 매퍼. **`types.ts`·`TraceStep.tsx` 수정 허용** (D44) — 단 **추가만, 기존 4종의 의미·색 변경 금지**
- **페어링**: pair 키가 없으므로 같은 `tool`의 미완료 `tool_call` 중 가장 이른 것과 다음 `tool_result`를 **FIFO**로. 근거는 D42 워커 큐 직렬 소비 — 주석에 남긴다
- status 매핑: `ok→ok` / `not_found`·`empty→warn` / `error→error` / 결과 없는 call→`pending` / hold 합성 스텝→`held`. `reason=="timeout"`이면 summary 앞에 `✗ timeout ·`
- `label`=`SESSION #{id}` · `meta`=`{elapsed 합}s · {call 수} calls` · `accent`= held 있으면 orange
- `session_id`가 null인 발주는 `mappers.tsx`에서 TRACE 행을 만들지 않는다 — **현재 `/manager/trace/null` 링크가 생성되는 버그를 여기서 없앤다**
- **DoD**: `npm run build` 성공. replay로 세션 흘린 뒤 페이지에서 5스텝 렌더. 없는 세션 → 빈 상태(에러 아님). 화면 B TRACE 행 클릭 → 이동 (**깨진 링크 해소**). error status가 붉은 점 + `✗`로 렌더

### MQ-310 지표 판정
- `score_session(events, expected) -> list[Verdict]`. 4지표: 부품 특정 / 인용 / 안전 / 시퀀스
- 인용 page 소스 = `lookup.manual_page` **+ `rag.chunks[*].page`** 합집합 (D30 원문)
- **분모 규칙**: 인용은 `applicable = not expect_not_found` (S4 제외 — D30)
- **S4 판정 보강**: `expect_not_found` 문항은 lookup status가 **`not_found`여야 pass**. `catalog_not_loaded` error는 **fail** — 미적재를 S4 성공으로 세면 지표가 가짜다
- **판정 기준을 데이터에 맞춰 완화하지 말 것**
- `testset.json`은 만들지 않는다 — 기대 정답 확정은 사람 항목
- **DoD**: `spikes/eval_score_contract.py` ≥9건, 전부 합성 traces (DB·API 불필요). citation page 불일치 → fail · safety "5분" → fail · S3에서 create_po_draft → sequence fail · `catalog_not_loaded` S4 → fail

### MQ-311 S4 관통 스모크
- `run_turn`을 **in-process 호출** (HTTP 미경유 — SSE 프레이밍은 sp3가 검증). `ScriptedClient` 주입
- **픽스처에 정상 코드 1건(iG5A/OHT)을 반드시 넣는다** — 0행이면 D50에 따라 `error`라 애초에 통과 못 하고, 정상 코드가 있어야 **"정상은 ok / 미지는 not_found"** 대비가 성립해 위양성이 사라진다
- 판정: lookup 1건 · not_found · 응답에 "확인되지 않" · **citation 0건**(S4는 인용이 없는 게 정답) · create_po_draft 미호출 · traces에 행 · 재조회 없음 · ⑧ `OHt` 조회는 ok · ⑨ 0행 DB에서는 error이고 스모크가 fail로 판정
- **한계 명시**: 스크립트 응답을 쓰므로 "LLM이 추측 안 했는가"가 아니라 **"루프가 not_found를 왜곡 없이 흘리는가"**를 본다. 실제 환각률은 LLM judge(다음 스프린트)
- **DoD**: 9건 PASS, `data/maintq.db` mtime 불변

### MQ-312 manifest 로더 + 인쇄 페이지 환산 (신규)
- `backend/manifest.py`: `load_manifest`(1회 캐시) · `manual_label` · `print_page_offset` · `to_print_page`
- `to_print_page`: `p = page - offset`; **`p < 1`이면 `page` 그대로** (D49)
- `backend/sse.py`에 `citation_for(model, page, section)` 추가. **기존 `citation_block` 시그니처를 바꾸거나 삭제하지 않는다** — Stage 1 시점에 `chat.py`가 아직 호출 중이라 깨진다
- manifest 없거나 모델 미등록 → offset 0 폴백 + `logging.warning`. 인용률은 `page`로 판정하므로 지표 영향 없음 (D26)
- **DoD**: `spikes/citation_render.py` ≥6건. **③ S100 p.2 → 음수 없이 `"S100 매뉴얼 p.2"`, payload `print_page == 2`** · ④ payload의 `page`는 항상 물리 원본 · ⑥ 기존 `citation_block` 하위 호환

### MQ-313 SQLite 동시성 (신규)
- 쓰기 커넥션(`backend.db.connect`, `mcp_server.db.draft_writer`)에 `PRAGMA journal_mode=WAL` + `busy_timeout=5000`
- **읽기 전용(`mode=ro`)에서는 `journal_mode`를 바꿀 수 없다** → `busy_timeout`만. 분기 필수
- 두 모듈은 **여전히 코드를 공유하지 않는다** (D15) — 같은 두 줄을 각자 갖는다
- `.gitignore`에 `*.db-wal`·`*.db-shm` 추가
- WAL 전환 실패해도 앱이 죽지 않아야 한다 → 예외 잡고 `logging.warning`
- **DoD**: `spikes/db_concurrency.py` ≥5건. ③ 쓰기 트랜잭션 중 다른 커넥션 INSERT가 `database is locked` 없이 성공 · ④ `read_only()`가 WAL DB에서도 열리고 **쓰기는 여전히 거부**(D10 회귀) · ⑤ `draft_writer` UPDATE 차단 트리거 유지. `sp2` 전건 PASS

### MQ-314 rag_search_manual (신규 — D47 하이브리드 반영)
- 04_MCP_TOOLS §2 계약 그대로. `mcp_server/rag.py`에 `search(model, query, top_k, dense=None)` (D47·D48)
- **하이브리드 구조로 짓되 dense 는 초기 비활성**: `search()` 가 keyword scorer 와 dense scorer 를 **둘 다 받고 가중 융합**하는 형태여야 한다. `dense=None` 이면 키워드 점수만 사용. 가중치 상수(`KEYWORD_WEIGHT`/`DENSE_WEIGHT`)를 모듈에 두되 **초기값을 실측인 양 적지 말고** "D51 에서 eval 로 조정" 주석을 남긴다
- 임베딩 모델·벡터스토어·가중치는 **D51** — `rag_sizing.md` 수치를 보고 결정한다. 이 태스크에서 임베딩을 고르지 말 것
- **model 필터 먼저** 적용 (04 §2 "model 필터 필수", D28과 같은 논리)
- 스코어링: 토큰 포함 빈도 / 청크 길이 정규화. **동점은 `page` 오름차순** — 같은 질의는 항상 같은 결과여야 평가가 재현된다
- `score`는 계약에 없으므로 **도구 레이어에서 제거**. `text`는 400자 절단. **`page`는 절대 가공하지 않는다** (D26)
- **인덱스 파일 없음 → `status:"error"`, `reason:"index_not_built"`** — `empty`로 주면 "매뉴얼에 없다"는 잘못된 신호가 되어 에이전트가 절차를 지어낼 여지가 생긴다
- 매칭 0건 → `empty` (D9)
- **DoD**: `spikes/rag_contract.py` ≥7건. ② 같은 질의 2회 동일 결과(결정론) · ④ 인덱스 없음 → `index_not_built` · ⑦ 출력에 `score` 키 없음(계약 준수). `sp2` 전건 PASS (등록 7종, **부분집합 비교**)

---

## 5. 최종 실행 계획

| 스테이지 | 태스크 | 병렬 | 예상 결과물 |
|---|---|---|---|
| Stage 1 | MQ-301·302·303·304·305·312·313 | ✅ 7 | 루프 부품 4종 + 도구 6/7 + 인용 렌더러 + 동시성 방어 |
| Stage 2 | MQ-306·307·314 | ✅ 3 | 에이전트 루프 + `GET /trace` + **도구 7/7 완성** |
| Stage 3 | MQ-308·309 | ✅ 2 | `POST /api/chat` 관통 + trace 페이지(깨진 링크 해소) |
| Stage 4 | MQ-310·311 | ✅ 2 | 지표 판정(lookup+rag) + S4 스모크(위양성 방지) |

**차단 조건**: ~~결정 승인~~ **해소됨(D40~D52 확정)**. 남은 건 D51(임베딩)뿐이고, D47 이 인터페이스를 고정해 뒀으므로 **Stage 1~4 진행을 막지 않는다**

**종료 시 상태**
- MCP 도구 **7/7**, 에이전트 루프·trace 영속화·`GET /trace`·화면 B trace 페이지 완성
- S1 시퀀스가 스크립트 드라이버로 관통, 지표 4종 판정 가능
- 회귀 스위트 67건 → 약 130건
- **`error_codes` 승인 전이라 실데이터 S1/S3는 `catalog_not_loaded`로 정직하게 실패한다** — 가짜 통과가 아니라 실패로 드러나는 게 이번 수정(D50)의 요점

**다음 스프린트 후보**: 환각률 LLM judge · `eval/testset.json` 20문항 + `run_eval.py` · 화면 A 라이브 SSE 연동(M3) · S1/S2/S3 시나리오 스모크 · 벡터 검색 전환(rag_sizing 판단 후)

---

## 6. 사람에게 남는 것

| # | 항목 | 급함 |
|---|---|---|
| 1 | ~~결정 승인~~ — **완료 (D40~D52)** | ✅ |
| 2 | `error_codes` iG5A 매핑 승인 → `_status` 변경 → `seed.py --with-error-codes` | ★★ |
| 3 | `ANTHROPIC_API_KEY` + `MAINTQ_LLM_MODEL` (`.env`) | ★★ |
| 4 | `backend/agent/prompts.py`의 `SAFETY_BASELINE` 문구·페이지 검수 | ★★ |
| 5 | `related_parts` 7건 검수 (평가 실적 인용의 전제) | ★ |
| 6 | **`rag_sizing.md` 확인 후 임베딩 모델·가중치 결정 (D51)** — Stage 2 의 dense 활성화 전제 | ★★ |


---

## 7. 실행 기록

### Stage 1 완료 (2026-07-23)
**커밋**: `3b14c2b` — `[M2] Sprint 3 Stage 1 — 루프 기반 7종 (회귀 153건)`
**reviewer**: PASS (블로커 0 · 경고 12)

| TASK | 산출 | 스파이크 |
|---|---|---|
| MQ-301 | `backend/agent/{__init__,trace}.py` · `data/seed.py`(스키마 4건) · `backend/services/po.py`(users 이관) | `trace_persist.py` 14 |
| MQ-302 | `backend/agent/mcp_client.py` · `backend/main.py`(lifespan) | `mcp_client_contract.py` 15 |
| MQ-303 | `backend/agent/prompts.py` · `TODO_직접할일.md` | `prompt_rules.py` 16 |
| MQ-304 | `mcp_server/tools/lookup_error_code.py` · `server.py`(6/7) | `lookup_contract.py` 12 |
| MQ-305 | `data/chunk_manual.py` · `manual_chunks.jsonl`(1,035청크) · `rag_sizing.md` | 자가 검증(멱등·경계) |
| MQ-312 | `backend/manifest.py` · `backend/sse.py`(`citation_for`) | `citation_render.py` 13 |
| MQ-313 | `backend/db.py` · `mcp_server/db.py` · `.gitignore` | `db_concurrency.py` 13 |

**회귀 153건 전건 통과** — seed 11 · trace 14 · mcp_client 15 · prompt 16 · lookup 12 · citation 13 · db_concurrency 13 · SP2 15 · write_tool 14 · api 19 · SP3 11

### 구현 중 잡힌 실제 결함 (계획에 없던 것)

| 태스크 | 결함 | 왜 안 잡혔을 뻔했나 |
|---|---|---|
| MQ-305 | `chunks[-2] += chunks.pop()` — `pop()` 이 리스트를 줄인 뒤 `-2` 가 재계산돼 **165개 페이지에서 두 청크가 동일**해지고 앞부분이 유실 | 부분 문자열 검사도 멱등성 검사도 통과한다 — **매번 똑같이 틀리기** 때문. "페이지 재구성 일치" assert 를 추가해 방어 |
| MQ-302 | `_child_env` 역검증 | SDK 기본(`get_default_environment()`)으로 바꿔치기하니 실 DB 오염이 재현됨 — 스파이크가 실제로 이를 잡는다는 걸 확인 |
| MQ-313 | `mode=ro` 커넥션에서 `journal_mode=WAL` → `attempt to write a readonly database` | 이미 WAL 인 DB 면 조용히 통과 → **특정 상태에서만 터지는** 종류. `_configure`/`_enable_wal` 분리로 방어 |

### Stage 2 착수 전 처리 (reviewer 권고, 우선순위)

1. **W-2** `TraceWriter.citation(manual, page, print_page, …)` 이 `print_page` 를 **인자로 받는다** — MQ-306 이 쓰면 D32 의 "변환은 1곳"이 두 갈래로 벌어진다. `citation(model, page, section)` 으로 바꾸거나 삭제하고 `emit(sse.citation_for(...))` 만 남길 것
2. **W-10** rag `text` 400자 절단 — 평균 청크 548자의 27%, p90 778자의 절반을 자른다. 절차 문단이 중간에서 끊기면 환각 표면이 생긴다. 상한을 800자로 올리거나 `truncated: true` 를 실을 것. **04_MCP_TOOLS §2 계약 변경이라 D 필요** · MQ-314 착수 전
3. **W-6** `reason` 키를 모든 error 반환의 필수로 승격 — 지금 12곳이 `message` 만 준다. 도구가 7종으로 늘기 전이 최저 비용
4. **W-3·W-4** 문서 정정 — `TOOL_TIMEOUT_SEC` 위치(09_RUNTIME §2 를 코드에 맞춰 정정) · `MAINTQ_MCP_AUTOSTART` 를 06_REPO_API 환경변수 표에 기재
5. **W-11** 안전 문구 근거 불일치 — `QUALIFIED_WORKER_NOTE` 의 S100 근거 p.3 이 문장 주장과 어긋난다(사람 검수 항목)

### 아직 성립하지 않는 것 (정직하게)

- **A5 가 런타임에서 아직 성립하지 않는다** — `chat.py` 의 유일한 SSE 경로가 `sse.*` 를 직접 호출해 traces 에 한 행도 안 남는다. MQ-308 이 배선한다
- **`error_codes` 0행** — lookup 실데이터 관통은 사람 승인 후. 지금은 모든 코드가 `catalog_not_loaded` 로 정직하게 실패한다
- **평가 지표 5종 산출 불가** — `eval/` 이 아직 없다. API 호출 0건, 비용 0


### Stage 2 완료 (2026-07-23)
**커밋**: `579e6ac` — `[M2] Sprint 3 Stage 2 — 에이전트 루프 · GET /trace · rag (도구 7/7, 회귀 190건)`
**reviewer**: FAIL(블로커 2) → 수정 → **PASS** (블로커 0 · 경고 5)

| TASK | 산출 | 스파이크 |
|---|---|---|
| MQ-306 | `backend/agent/{llm,loop}.py` · `.env.example` · `trace.py`(W-2 해소) | `agent_loop_contract.py` 21 |
| MQ-307 | `backend/routers/chat.py` GET /trace | `api_contract.py` 19→23 |
| MQ-314 | `mcp_server/rag.py` · `tools/rag_search_manual.py` · `server.py`(7/7) | `rag_contract.py` 12 |

**회귀 190건** — Stage 1 대비 +37 (`rag` 12 · `agent_loop` 21 신규, `api` +4)

> **tool-builder 3개가 세션 한도로 중단돼 메인이 직접 마무리했다.** MQ-307 은 거의 완성,
> MQ-314 는 `rag.py` 만 있었고, MQ-306 은 미착수 상태였다.

### 이 스테이지에서 잡힌 결함

| # | 결함 | 왜 안 잡혔을 뻔했나 |
|---|---|---|
| 블로커1 | **안전 블록 인용이 엉뚱한 페이지** — `st.pages[0]`(rag p.204)를 붙였는데 안전 문구 근거는 `SAFETY_BASELINE["pages"]`(iG5A p.4) | 스파이크 ⑤⑥ 이 **문구와 순서만 보고 페이지를 안 봤다.** ⑥-b 추가로 방어 |
| 블로커2 | 중첩 citation 이 `{page}` 뿐 → 프론트 `undefined p.204`, S100 은 물리를 인쇄로 표시 | 백엔드 스파이크가 payload **형태**를 안 봤다. ⑥-c·⑩-b 추가 |
| N-1 | `window_days` 폴백이 **도구가 주지 않는 키**를 읽어 항상 30 | 방어 코드가 들어가 목표를 달성한 것처럼 보였다. 도구 **입력**의 `days` 를 쓰도록 수정 |
| N-2 | label dedup 이 `(label,page)` 라 한 절이 두 페이지에 걸치면 중복 | **픽스처 청크가 1건이라 검사가 공회전.** 3청크(같은 절 2페이지 포함)로 교체 |
| 별건 | SP3 간헐 실패 — `wait_ready` 폴링이 uvicorn 의 startup 전 바인딩 창에서 연결을 중단시켜 Windows Proactor accept 루프를 `WinError 64` 로 깨뜨림 | lifespan(MQ-302)이 startup 창을 늘리며 드러났다. 요청 적게·타임아웃 넉넉히 |

### Stage 3 착수 전 (reviewer 권고)

1. **N-4 잔여** — 안전 인용 회귀에 S100 케이스 추가 완료(⑩-c). 추가 조치 없음
2. **C-11** `frontend/lib/mappers.tsx` 오프셋 — 주석은 "백엔드가 적용"이라는데 실제로는 물리 페이지에 `printPage: page` 를 붙인다. **MQ-309 범위에서 같이**
3. **C-5** 실 Anthropic 경로 미검증 — **MQ-308 DoD 에 "실 클라이언트 1턴 스모크(수동 1회)" 를 넣을 것.** 이력에 assistant `tool_use` 를 안 남기고 도구 결과를 `role:"user"` 텍스트로 넣는 구조가 실 API 에서 견디는지가 관건. 여기서 문제가 나면 루프 구조 수정이라 늦게 발견되면 비싸다
4. **C-6·C-7** — A1 스파이크 강도(`FakeMcp.on_call` 훅)·스트림 취소 회귀는 MQ-308 DoD 에 이미 있음
5. 보류 가능: C-8(rag page 검증) · C-9(D51 가드) · W-11(사람 검수)

### Stage 3 완료 (2026-07-23)
**커밋**: `704a8aa` — `[M2] Sprint 3 Stage 3 — POST /chat 루프 관통 배선 · 화면 B trace 페이지`
**reviewer**: FAIL(블로커 1) → 수정 → **PASS** (블로커 0 · 경고 2 · 노트 3)

| TASK | 산출 | 스파이크 |
|---|---|---|
| MQ-308 | `backend/routers/chat.py` 전면 재작성 (`_replay_s1` → `SseEvent`, `Depends(caller)`, `app.state.mcp` 주입) | `sp3_sse_events.py` 11→21 |
| MQ-309 | `app/(console)/manager/trace/[sessionId]/page.tsx` · `lib/trace.ts` 신규 · `lib/{api,mappers,types}` · `components/trace/TraceStep.tsx` | `tsc --noEmit` · `next build` |

**회귀 200건** — Stage 2 대비 +10 (SP3 +10). ruff · tsc · next build 통과.

#### 이 스테이지가 해소한 것

- **A5(발행=저장)가 런타임에서 성립한다.** 그전까지 `chat.py` 의 유일한 SSE 경로가
  `sse.*` 를 직접 불러 `traces` 가 0행이었다. 이제 `?replay=s1` 도 `TraceWriter` 를 거치고,
  SP3 ⑬ 이 저장 payload 와 SSE `data` 를 **바이트 단위로 대조**한다
- **화면 B 근거 카드의 깨진 TRACE 링크 해소** — `/manager/trace/{session_id}` 착지점 신설
- **C-11** — `mappers.tsx` 가 물리 페이지에 `printPage` 를 박아 S100(offset 16)에서
  물리를 인쇄로 표시하던 문제. `/api/po/{id}` 에 인쇄 페이지가 없으므로 **채우지 않는 것**이 정답
  (프론트 변환은 D32 위반)

#### 이 스테이지에서 잡힌 결함

| # | 결함 | 왜 안 잡혔을 뻔했나 |
|---|---|---|
| 블로커 | **MCP 가드가 `mcp is None` 만 봤다.** lifespan 은 기동 실패해도 객체를 남기므로(승인 큐는 살아야 함) 실제 다운 상태는 `ready=False` 다. 그대로 진입하면 도구 0건으로 LLM 이 근거 없이 진단을 서술한다 — **절대규칙 6 위반 경로** | 주석은 "09_RUNTIME §3 — 공백을 지식으로 메우지 않는다"라고 적혀 있었다. **가드는 있는데 조건이 실제 상태와 어긋난** 유형. SP3 가 replay 만 돌아 `_agent_stream` 을 한 번도 실행하지 않았다 |
| W-1 | `elapsed` 가 **생산자 없는 `_elapsed` 키**를 읽어 상시 0.0 → 방금 만든 trace 패널이 "0.0s · 5 calls"라는 거짓을 표시 | Stage 2 의 N-1(`window_days`)과 **같은 유형의 재발**. 계약 필드가 상시 거짓이면 감사 화면의 신뢰가 통째로 무너진다 |
| W-2 | `✗ timeout ·` 접두의 소유권이 **양쪽에 반대로** 적혀 있었다 — `mcp_client` docstring 은 "프론트가 붙인다", 실제로는 `loop.py` 가 붙임. 프론트 분기는 `reason` 필드가 payload 에 없어 **도달 불가 死코드** | 양쪽 다 대응하게 짜여 겉으로 깨지는 게 없었다. 판정: **백엔드 소유** — traces 는 평가 판정 소스라 저장값이 자기설명적이어야 한다 |
| W-3 | SP3 ⑰⑱ 이 "D42 회귀"를 자칭하지만 replay 전용이라 `_agent_stream` 에 `stdio_client` 를 부활시켜도 **통과한다** | 검사 이름이 사정거리를 과장. 이름을 낮추고 실제 D42 회귀는 `agent_loop_contract` 소관임을 명시 |
| W-4 | 안전 블록 **인용 페이지**에 회귀가 없었다 — Stage 2 블로커 1 이 `chat.py` 재생본에서 재발해도 전 검사 통과 | ⑦(순서)·⑨(타입)·⑪(독립 citation 키)만 보고 safety 블록 **안**의 citation 을 안 봤다. ⑦-b 추가 |

> **음성 검증** — 가드를 `mcp is None` 으로 되돌리자 ⑲ 가 실제로 FAIL 했다
> (첫 토큰이 LLM 키 안내로 바뀜). ⑳ 은 키가 없으면 공허 통과라는 점을 주석에 명시했다.

#### Stage 4 착수 전 남긴 것

1. **W-5 (먼저 결정할 것)** — replay 가 `traces` 에 **실 도구 결과와 구분 불가능한 합성 행**을
   쓴다. `po_card` 가 실재하는 PO-0117 을 `state:"draft"` 로 주장하는데 DB 는 `pending` 이다.
   **`eval/score.py`(MQ-310)가 traces 를 읽기 시작하기 전에** 결론을 내야 한다 — 지금 상태로
   지표를 돌리면 재생 데이터가 실적에 섞인다
2. **W-7 / C-5 이월** — 실 Anthropic 1턴 스모크는 이번에도 미수행(키 없음).
   `loop.py` 가 assistant `tool_use` 를 이력에 안 남기고 도구 결과를 `role:"user"` 텍스트로
   넣는 구조가 실 API 에서 견디는지 미지수. 실패 시 수정 대상은 `loop.py`·`llm.py`
3. **W-A** 가드는 진입 1회 — 턴 **도중** MCP 가 죽으면 비위험 서술의 환각 방지가 프롬프트뿐.
   후속: 루프에 "이 턴 `status=="ok"` 도구 0건이면 진단 대신 실패 고지" 게이트 + 중도 하강 회귀
4. **W-8** `_encode` 의 broad except 가 루프 버그를 "생성 실패"로 위장할 여지
5. **N-b** replay 의 `elapsed` 는 하드코딩(0.4/1.2/…)인데 실 경로는 실측 — 같은 필드에 두 의미
6. **N-c** `error` 글리프 `✗` + summary 접두 `✗ timeout ·` 이중 표기
7. **N-3** DoD 의 "5스텝"은 목업 기준. replay 는 도구 4쌍이라 **4스텝**이 맞다
8. **W-6** S100 근거 카드 라벨을 `"PDF p.416"` 으로 명시하면 더 정직 (계약 변경 없이 가능)
9. `CLAUDE.md` 의 "회귀 스위트(고정)" 목록이 낡았다 (5스위트 → 실제 13스위트)

### Stage 4 완료 (2026-07-24)
**커밋**: `2a926c9` — `[M2] Sprint 3 Stage 4 — 지표 판정기 · S4 관통 스모크`
**reviewer**: **PASS** (블로커 0 · 경고 2 · 노트 4) — 경고 2건은 커밋 전 문서·라벨 정합으로 처리

| TASK | 산출 | 스파이크 |
|---|---|---|
| MQ-310 | `eval/score.py` · `eval/__init__.py` | `eval_score_contract.py` 14 |
| MQ-311 | `spikes/s4_smoke.py` (in-process `run_turn` + 실 `McpClient`) | (자체 10건) |

**회귀 224건** — Stage 3 대비 +24 (eval_score 14 · s4_smoke 10 신규). ruff 통과.
`data/maintq.db` mtime 두 신규 스파이크 전후 불변 확인(둘 다 임시 사본 작업).

#### Sprint 3 로 완성된 것 (M2 관통)

- **에이전트 루프**가 도구 7종을 오케스트레이션하고, 모든 SSE 이벤트가 `traces` 에 남는다(A5).
- **화면 B trace 페이지**로 팀장이 발주 근거를 도구 호출 단위로 감사할 수 있다(깨진 링크 해소, 브라우저 검증 완료).
- **지표 판정기**가 합성 traces 로 4지표(부품·인용·안전·시퀀스)를 판정하고, D50 위양성(미적재를 S4 성공으로 셈)을 거른다.
- **S4 스모크**가 "루프가 not_found 를 왜곡 없이 흘리는가"를 관통 검증한다.

#### 이 스테이지에서 드러난 것 (reviewer 경고)

| # | 내용 | 처리 |
|---|---|---|
| W-1 | **인용률 strict 판정이 실 배선에서 영구 degraded** — `tool_result` 가 요약본(`{tool,status,summary,elapsed}`)이라 근거 page 소스가 항상 빈 집합. `eval/score.py` 는 "citation 블록 존재 = 발행=근거"로 내려가 **"블록은 있고 숫자는 지어낸" 경우를 못 막는다.** `06_REPO_API §216` 이 막겠다고 적은 바로 그 케이스 | **문서에 미해소 전제로 명시.** 실제 해소는 loop 이 tool_result 에 근거 page 를 싣는 **계약 확장(D 필요)** — Stage 4 이후 |
| W-2 | `eval_score_contract ②` 가 loop.py 가 만들지 않는 rich payload 로 strict 를 통과시켜 **실 방어력을 과대 표시** (이 프로젝트가 5번 겪은 "검사는 통과하는데 대상은 깨진" 유형) | **라벨을 "합성 rich payload 한정"으로 정직화.** 실 형태 방어는 ⑪(degraded)이 담당함을 주석화 |

#### Sprint 4(또는 M3 착수) 전 남긴 것

1. **W-1 계약 결정** — tool_result 에 근거 page 를 실을지. 인용률 지표를 실 eval 근거로 쓰기 전 필수.
   이건 Stage 3 의 **W-5(재생 trace 오염)와 한 묶음**이다 — 둘 다 "traces 를 실적 판정에 쓰기 전에" 정해야 한다.
2. **실 Anthropic 1턴 스모크(C-5)** — 여전히 미수행. `loop.py` 이력 구조가 실 API 에서 견디는지.
3. **N-c 이중 `✗` 표기**(브라우저 검증에서 육안 확인) · **N-b elapsed 재생 하드코딩** · **W-6 S100 라벨** — M3 표시 규약 정리.
4. `CLAUDE.md` 회귀 스위트 목록 갱신(5스위트 → 14스위트, 총 224건).
