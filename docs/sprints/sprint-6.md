# Sprint 6 — 확장 범위 F1·F2·F4 · 읽기 판정 도구 7종

**수립**: 2026-08-09 · **부제**: 근거 계층을 DB로 내리고, 판정 도구 7종을 얹는다

**사용자 지시**: "성능 튜닝(3차 평가·지표 개선)은 나중으로 미루고, **기능 구현을 싹 다 먼저** 한다."

> 🔀 **이 스프린트는 병행 세션과 같은 저장소에서 돌았다.** 상대 세션(`4dc6448`·`c3a46c8`)이
> **D76(도구 결과 구조 보존)** 을 먼저 가져갔고, 이쪽에서 D76 으로 기입했던 룰 정합 결정은
> **D77 로 재번호**했다. 회귀 기준선도 상대 세션의 `agent_loop_contract` +5 를 반영해
> **303건**(273 + `law_fetch` 25 + `agent_loop` 5)이 정본이다.
> 파일 교집합은 없었다 — 상대는 `backend/agent/`·`spikes/`, 이쪽은 `data/`.

**선행 상태**: M1~M4 완료. Sprint 5 종료(`sprint-5.md`) — 회귀 **273건(17스위트)** + 정적 3종 통과.
> ⚠ 계획 수립 시 인용한 "257건(16스위트)"은 **오집계였다**(Sprint 4 기준선 248 + 9 로 계산하며 `eval_replay_guard` 16건을 누락). `sprint-5.md:554-577` 의 2026-08-08 실측 정정치 **273건 · 17스위트**가 정본이다. Stage 1 실측으로 재확인됨.
S1~S4 파이프라인은 실 서버·실 LLM·실 MCP로 20문항 2회 완주 확인됨. 완료 기준 5지표 중 3개 미달이나
**사용자 방침에 따라 이번 스프린트에서 다루지 않는다.**

---

## 범위

`docs/00_MVP_SCOPE.md §범위 확장 (D67)` 의 **추가 기능 7~12번** = `11 §8` 의 **F1·F2·F3·F4** + `12` 의 도구·테이블.

**단 한 스프린트로는 불가 — Sprint 6 / Sprint 7 로 분할한다.** 근거는 §스프린트 크기 판정.

| | Sprint 6 (이 문서) | Sprint 7 |
|---|---|---|
| 성격 | **읽기 · 판정 · 근거** | **쓰기 · 서명 · 승인 큐 · UI** |
| 범위 | F1(근거계층 DB화) · F2(처분 차단) · F4(취득 검증) · 기능 7·8의 읽기측 | F3(서명) · S19(수리 증빙) · 승인 큐 공유 · 프론트 |
| 도구 | 읽기 7종 | 쓰기 2종 |
| 프론트 | **0** | 큐 3종 렌더·서명 UI |

### 실측 범위 크기 (요청 범위의 정정)

| 항목 | 실측 |
|---|---|
| 신규 MCP 도구 | **9종** (12종 아님) |
| 신규 테이블 | **7종** (10종 아님) + `equipment`·`parts` 컬럼 확장 |

> "도구 12종·테이블 10종"은 **F5·F6 포함 수치**였다. `11 §10-3` 의 3종(`track_deadlines`·
> `detect_law_revision`·`assess_risk_grade`)과 `11 §10-2` 의 4테이블은 사용자가 제외한 F5·F6이다.

### 범위 밖 (의도적)

- **3차 평가 실행 · 지표 튜닝 · README TBD 교체** — 사용자 지시. D69가 이걸 나중에 정상적으로 할 수 있게 기준선을 지킨다
- **F5·F6** (`deadlines`·`incidents`·`ownership_checks`·`risk_profile` + 도구 3종) — `11 §10-5` 가 "F1~F4 뒤"로 못박음. 단 `assets.building_id` 컬럼 자리만 잡아 둔다
- **P1~P21·P29 승격 없음.** P11(기종 확장)은 사람 검수 3건이 새로 붙으므로 F1~F4 뒤
- `related_parts` 검수 · 안전 문안 검수 · 시드 가격 감수 — 사람 전담
- **SSE 이벤트 종류 확장 없음** (D14·D22 4종 고정) · **MCP 도구의 UPDATE 권한 없음** (D10) · **런타임 외부 API 호출 없음**

---

## 사전 조사 핵심 발견 (PM + tool-builder 실측)

### 🚨 하드 블로커 — `LAW_API_OC` 미발급

`.env` 에 키 이름은 있으나 **값이 빈 문자열**(len=0). 실호출 결과
`{"result":"필수입력요소 검증에 실패하였습니다"}`. `11 §8` 체크리스트의 "OPEN API 이용 신청"도 미체크다.
→ **MQ-602(법령 원문 수집)를 스프린트에서 제거**하고 사람 선행작업으로 승격. 실수집은 Sprint 7.

**다른 12태스크는 막지 않는다.** `engine.py:129-131` 의 미등록 법령 참조 검사가 `ref in laws`(파일 존재)만
보고 `is_fetched` 를 보지 않으므로, `fetch_status:"PENDING"` 상태로도 **판정과 조문 인용이 전부 동작**한다
(`test_rules.py` 19건이 지금 그 상태로 통과 중).

| 대상 | 조문 미수집 시 |
|---|---|
| `check_disposal_blockers`(F2) · `verify_ownership`(F4) | ✅ 동작. `evidence_completeness:"LAW_TEXT_PENDING"` 으로 정직하게 표시 |
| `classify_expenditure` | ⚠️ 조문 **등록**만 되면 동작 (수집 불필요) → `MQ-602L` 이 파일만 추가 |
| `build_evidence_bundle` | ❌ **의도적 거부**(`law_text_unavailable`). `text_hash` 가 null 인 번들은 무결성을 증명하지 못한다 |
| S10 데모 | ❌ 막힘 → Sprint 7 로 미룬 또 하나의 이유 |

### 환경 · 데이터 실측

- **`pytest` 미설치** — `pyproject.toml` dev 의존성이 ruff 뿐. `uv run python -m pytest` 는 `ModuleNotFoundError`.
  → 전 DoD 를 **`uv run --with pytest python -m pytest …`** 로 통일한다.
  **dev 그룹에 추가하지 않는 이유**: `.claude/settings.json` Stop 훅이 매 턴 `pytest eval/ -q` 를 돌리는데
  `eval/` 에는 `test_*` 파일이 하나도 없어(Sprint 5 에서 의도적 명명) 설치 즉시 훅이 **매 턴 exit 5**("no tests ran")를 뱉는다.
- **중진공 CSV 카테고리 오기** — 실제 원본은 `환경  설비`(**공백 2칸**). `data/data_list.md §6-1` 이 `환경설비` 로 잘못 옮겼다.
  → 문자열을 문서에서 베끼지 않고 **스크립트 출력 바이트를 그대로** 쓴다.
- **유효 표본 5,396 재현 불가** — 결측제외 5,911 / 가격>0 5,685 / **가격≥10,000 → 5,475**.
  → 필터를 `연도 파싱 성공 ∧ 희망가격 ≥ 10,000` 으로 고정하고 기대치를 5,475 로 정정.
- **잔가곡선 base 구간(age≤2)이 데이터 공백대** — 5종 카테고리 **전부 age=2 표본 0건**, age 3·4 도 0~5건.
  `제조년월` 최빈 이상값 `2025-01-13`(51건) 등 등록일 오염 정황. → **연차 버킷 + base=age≤5** (D72).
- **`spikes/` 실제 16파일**인데 `CLAUDE.md` 목록은 15개 (`eval_replay_guard.py` 누락).
- **P28 본문 오기** — "`data/rules/README.md`·`11 §7` 이 SQLite 적재라고 쓴다"에서 `README.md` 에는 그 문장이 **없다**.

### 검증된 인용 (PM 명세의 근거)

`engine.py:129-131` ✅ · `evaluate_rule` 216행 `f not in facts` ✅ · `loop.py:262` `list_tools()` ✅ ·
`fetch_laws.py:31` + `NotImplementedError` 46행 + `check_revisions()` 56행 ✅ · `seed.py:279-290` ✅ ·
`seed_po_drafts(con, with_codes)` 게이트 선례 512~514행 ✅ · 중진공 CSV 경로·cp949·16,011건 ✅ ·
`D68` 이 마지막 D ✅ · `D1~D68` 표기 4곳 ✅ · `prompt_rules.py:52` `len(RULES)==11` ✅

---

## 제안 결정 D69~D73 (⚠ 사람 승인 필요 — 착수 전제)

CLAUDE.md 규칙상 설계 공백을 코드가 임의로 메우면 근거가 사라진다. 아래 5건은 `10_DECISIONS.md` 와
충돌은 아니지만 **문서에 없는 공백**이다. 승인 후 MQ-613 이 본문을 기입한다.

| D | 결정 | 대안 | 이유 |
|---|---|---|---|
| **D69** | MCP 도구 노출을 `MAINTQ_TOOLS_PROFILE=core\|full`(**기본 `core`**)로 게이트한다 — `core`=코어 7종, `full`=코어 7 + 확장 7. **시스템 프롬프트는 이 env 를 읽지 않고, 루프가 `client.list_tools()` 로 받은 실제 도구 목록으로 조립한다**(`build_system_prompt(tool_names=…)`). `/health` 는 등록 개수 실측치를 싣는다 | 전 도구 무조건 노출 / 프롬프트도 env 분기 / 기본값 `full` | `loop.py:262` 가 도구를 **동적 등록**하므로 서버에 얹는 순간 14종이 프롬프트에 들어간다. 현재 지표는 부품특정 26.7%·인용률 83.3%(2차)이고 **미측정 수정 4건**이 대기 중이라, 도구를 7종 늘린 뒤 3차를 돌리면 "수정 효과 vs 도구 증가 효과"를 영원히 분리할 수 없다 — D56 이 "모델을 바꾸면 분리 불가"라 판단한 것과 같은 함정. 기본을 `core` 로 두는 이유: `eval/run_eval.py` 가 부모 env 를 상속해 서버를 띄우므로(D56), 기본이 `full` 이면 평가가 아무 표시 없이 확장 프롬프트로 돈다. **프롬프트가 env 를 읽지 않는 이유**: 등록은 자식 프로세스(MCP), 프롬프트는 백엔드가 만들어 **두 곳이 같은 env 를 각자 해석하면 어긋난다** — 실제 목록을 넘기면 "목록에 없는 도구 사용법을 지시"하는 상태가 구조적으로 불가능해진다 |
| **D70** | MTBF 는 **달력 기준 평균 고장 간격(일)** 으로 산출하고, 출력에 `mtbf_basis:"calendar_days"` 와 고지를 강제한다. 가동시간 기반 산식·OEE 원재료는 원천 확보 전까지 쓰지 않는다 | `12 §2` 문언대로 총 가동시간 ÷ 고장 횟수 / `assets` 에 `operating_hours` 를 만들어 시드로 채움 | **저장소에 가동시간 원천이 없다** — `equipment`·`error_history` 어디에도 없고 컨트롤러 로그도 없다. 시드로 지어내면 D65 가 막으려던 것과 같은 가짜 정밀도가 되고, 그 값으로 산출한 MTBF 가 매각 증빙(S10)에 실린다. 달력 기준은 실재하는 `error_history` 만 쓰므로 조작 여지가 없고, 산식이 다르다는 사실을 **필드로 드러내면** 나중에 원천이 생겼을 때 교체 지점이 명확하다 |
| **D71** | 처분 판정의 HTTP 매핑: `BLOCKED`·`HOLD`·`INSUFFICIENT_FACTS` → **409**, `CONDITIONAL`·`CLEAR` → **200**, 룰 카탈로그 미적재 → **503**. 판정 전용 엔드포인트는 `POST /api/assets/{id}/disposal/precheck`(**무저장**)이며 처분 요청 생성·서명은 별도 경로다. 이 경로에는 **역할 게이트를 두지 않는다** | HOLD 를 200 으로 / `/disposal` 한 경로에서 판정과 생성을 겸함 / precheck 에도 403 게이트 | `11 §3` 은 BLOCKING→409 만 정했다. HOLD·INSUFFICIENT_FACTS 를 200 으로 주면 D62("알 수 없다 ≠ 통과")가 API 경계에서 무너진다 — 클라이언트는 200 을 진행 가능으로 읽는다. 저장하지 않는 POST 를 `/disposal` 로 부르면 계약이 거짓말이 된다. **역할 게이트를 안 두는 이유**: 읽기 판정에 403 을 만들면 "권한 위반 403 차단 100%" 지표에 법정 조건 미충족이 섞인다(D38 이 403/409 를 나눈 바로 그 이유) |
| **D72** | `residual_curve` 는 신품가 분모 없이 **연차 버킷별 상대 잔가율**로 산출한다 — `base = median(희망가격 \| age ≤ 5)`, 격자는 `0-2/3-5/6-10/11-15/16-20/21-30`, 버킷 표본 <10 또는 base 표본 <30 이면 **행을 만들지 않는다**. 유효 표본 필터는 `연도 파싱 성공 ∧ 희망가격 ≥ 10,000`(실측 5,475건). D65 의 추정치 고지 강제는 그대로 | 조달청 신품가를 분모로 수작업 매칭 / `age ≤ 2` 를 base 로 / 표본 부족 구간을 인접 연차로 보간 | 취득원가 컬럼이 없어 잔가**율**을 직접 낼 수 없다. 조달청 분모는 규격·수량이 민간과 달라 그대로 시장 신품가가 아니고 매칭이 수작업이라 유보 상태다. **`age ≤ 2` 를 버린 이유**: 5종 카테고리 **전부 age=2 표본 0건**이고 age 0~1 에는 `2025-01-13`(51건) 같은 등록일 오염 정황이 있어 base 자체가 오염된다. 보간 금지 이유는 D65 와 같다 — 없는 정확도를 만들지 않는다 |
| **D73** | `data/` 는 **두 프로세스가 공유해도 되는 데이터 계층**이다 — `backend` 와 `mcp_server` 가 각자 `data.rules.engine` 을 import 해도 D15 위반이 아니다. 금지되는 것은 **`backend` ↔ `mcp_server` 상호 import** 이며, DB 커넥션 계층(`backend/db.py` / `mcp_server/db.py`)의 의도적 중복은 유지한다 | 룰 엔진을 공용 패키지로 승격 / backend 가 판정을 MCP 도구 호출로만 수행 / `engine.py` 를 양쪽에 복제 | D15 가 막으려던 것은 "목업 DB 를 실제 ERP 로 갈아끼울 때 MCP 서버만 교체"라는 구조가 **코드 공유로 무너지는 것**이고, 그 대상은 **런타임 두 프로세스**다. `data/` 는 매뉴얼·시드·룰 카탈로그가 있는 **데이터 자산**이고 `mcp_server/rag.py` 가 이미 `data/extracted/` 를 읽는 선례가 있다. **backend 가 MCP 호출로만 판정하는 안을 버린 이유**: D69 의 `core` 프로파일에서 확장 도구가 등록되지 않아 REST 판정이 통째로 죽는다 — 사람용 API 가 에이전트 도구 노출 설정에 종속되면 안 된다. 복제안은 판정 로직이 두 벌이 되어 룰 개정 시 조용히 어긋난다 |

---

## Sprint 6 최종 실행 계획

| 스테이지 | 태스크 | 병렬 | 예상 결과물 |
|---|---|---|---|
| **Stage 1** | MQ-603, MQ-602L | ✅ (파일 교집합 0) | 잔가곡선 JSON + 분석문서 · `KR-CITA-ENF-31` 등록 + `LAW_API_OC` 개명 + 수집 계약 회귀 |
| **Stage 2** | MQ-601a | — | 7테이블 DDL + 시드(잔가 격자와 공동 설계) + `verify` ⑫⑬⑭⑯ |
| **Stage 3** | MQ-601b | — | `engine.py` DB 로더·`build_facts`·`asset_id` 전환 + `verify` ⑮ + `rules_db_load` 회귀 |
| **Stage 4** | MQ-604, 605, 606, 607, 608 | ✅ (도구당 파일 1개) | 읽기 도구 5종 |
| **Stage 5** | MQ-609, 610, 611 | ✅ (교집합 0) | 3지 판단 · 근거 번들 · S9 REST 409 |
| **Stage 6** | MQ-612, 613 | ✅ (코드 / 문서) | MCP 등록·프로파일·프롬프트·회귀 전량 · 계약 문서 정합 |

```
MQ-603 ──────────► MQ-601a ──► MQ-601b ─┬─► MQ-604 ─┬──────────► MQ-610 ─┐
                                         │   MQ-605  │                     │
MQ-602L ─────────────────────────────────┼─► MQ-608  ├─► MQ-609 ───────────┼─► MQ-612 ─┐
                                         │   MQ-606 ─┤                     │           ├─► 종료
                                         └─► MQ-607 ─┘   MQ-604 ─► MQ-611 ─┘  MQ-613 ──┘
```

### 스테이지 구성 근거

- **Stage 1 이 MQ-603 을 품는 이유**: 잔가곡선의 **실제 연차 격자**가 나와야 MQ-601a 의 `acquired_at`·
  `repair_records` 배분을 설계할 수 있다. 병렬로 두면 MQ-609 DoD 가 **구조적으로 실패**한다
  (tool-builder 실측: 초안 시드의 age 1/2/3 은 잔가곡선 행이 없어 전 자산 `HOLD` 로 수렴).
  MQ-602L 은 `data/rules/laws/`·`fetch_laws.py`·`.env.example`·신규 spike 만 건드려 교집합 0.
- **MQ-601 을 601a/601b 로 쪼갠 이유**: ⓐ 단일 태스크로 과대(7테이블 DDL+시드+엔진+문서)
  ⓑ **파일 소유가 자연히 갈린다** — 601a=`seed.py`·`05_DB_SCHEMA.md`, 601b=`engine.py`·`test_rules.py`
  ⓒ 601b 의 검증(`build_facts` 가 NULL 키를 빼는가 → `INSUFFICIENT_FACTS`)은 601a 가 만든 DB 가 있어야 성립.
  **병렬 불가라 스테이지를 나눈 것이지 쪼개서 병렬화한 게 아니다.**
- **Stage 4 를 5병렬로 둘 수 있는 근거**: CLAUDE.md "파일당 1도구" 규칙 덕에 `mcp_server/tools/*.py`
  신규 5파일이 서로 독립이다. **공유 파일 3개(`server.py`·`prompts.py`·`mcp_client.py`)를 전부 MQ-612 로
  몰아냈기 때문에** 이 병렬이 성립한다 — 도구마다 등록·프롬프트를 같이 고치게 하면 5태스크가 같은 3파일을 동시 편집한다.
- **Stage 5 가 별도인 이유**: MQ-609 는 MQ-606·607 의 **시그니처를 import** 하고, MQ-610 은 MQ-604 의
  findings 구조를 소비한다. 같은 스테이지에 두면 tool-builder 가 아직 없는 심볼을 추측한다.
- **Stage 6 이 마지막인 이유**: MQ-612 의 DoD 가 "서버 기동 → `list_tools()` 14종 확인"이라
  **도구 7개가 전부 존재해야 검증이 성립**한다. MQ-613 은 문서 전용이라 코드와 교집합 0.
- **스테이지가 6개로 늘어난 대가**: Stage 2·3 이 각 1태스크라 직렬 구간이 길어진다.
  대신 Stage 4 의 5병렬이 **완전히 안전**해진다(스키마·엔진이 둘 다 고정된 뒤 시작).
- **이월 없음** — `sprint-5.md:566` 이 "F1 은 이 스프린트에 없다"고 닫았고, 유일한 잔여(README TBD)는
  3차 평가 산출물로 이관돼 Sprint 6 대상이 아니다.

### 공유 파일 단일 소유자 격리

| 공유 파일 | 유일 소유 태스크 | 스테이지 |
|---|---|---|
| `data/seed.py` · `docs/05_DB_SCHEMA.md` | **MQ-601a** | 2 |
| `data/rules/engine.py` · `data/rules/test_rules.py` | **MQ-601b** | 3 |
| `data/rules/laws/*.json` · `fetch_laws.py` · `.env.example` · `data/rules/README.md` | **MQ-602L** | 1 |
| `mcp_server/server.py` · `backend/agent/prompts.py` · `backend/agent/mcp_client.py` · `spikes/prompt_rules.py` | **MQ-612** | 6 |
| `backend/main.py` · `backend/routers/equipment.py` | **MQ-611** | 5 |
| `docs/04·06·07·10·11·12·README` · `CLAUDE.md` | **MQ-613** | 6 |

---

## 태스크별 상세 구현 명세

### Stage 1

#### MQ-602L — 법령 참조 등록 · `LAW_API_OC` 개명 · 수집 계약 회귀 (네트워크 무관)

> 🔴 **구 MQ-602(법령 원문 실수집)는 삭제됐다.** `LAW_API_OC` 미발급으로 하드 블로커.
> 실수집은 Sprint 7 Stage 1. 이 태스크는 **키 없이 완주**해야 한다.

- **복무 시나리오**: S9(근거 인용) · S1+(`classify_expenditure` 선행)
- **변경 파일**: `data/rules/laws/KR-CITA-ENF-31.json`(신규) · `data/rules/fetch_laws.py`(수정) ·
  `.env.example`(수정) · `data/rules/README.md`(수정) · `spikes/law_fetch_contract.py`(신규)
- ⛔ **실호출 금지.** ⛔ `engine.py`·`test_rules.py`·`seed.py` 접근 금지

- **핵심 로직**
  1. **신규 법령 참조 1건** — MQ-608 이 근거 없이는 존재할 수 없다(불변식 1·2):
     ```json
     {"law_ref_id":"KR-CITA-ENF-31","law_name":"법인세법 시행령","article":"31",
      "title":"즉시상각의제","text":null,"fetch_status":"PENDING",
      "source_url":"https://www.law.go.kr/법령/법인세법 시행령",
      "verification_note":"자본적 지출 정의가 실제 몇 조 몇 항인지 API 응답으로 확정할 것. 어긋나면 law_ref_id 정정"}
     ```
     **손으로 원문을 채우지 않는다** (`11 §8`).
  2. **개명** — `fetch_laws.py:31` `API_KEY = os.environ.get("LAW_API_KEY")` →
     `LAW_API_OC` 우선·`LAW_API_KEY` 폴백. 인증값이 API 키가 아니라 **신청 이메일 ID 앞부분**이라 변수명이
     사실과 어긋나 있었다. `.env.example:52-54` 의 "개명 예정" 주석 2줄 제거,
     **키가 비어 있을 때의 증상**(`필수입력요소 검증에 실패` 응답)을 주석으로 남긴다.
  3. `fetch_from_api` 는 **`NotImplementedError` 유지**. 메시지를 "키 발급 후 Sprint 7 에서 구현.
     `MST` 조회 → `JO` 형식 실호출 확인 → 조문번호·제목 대조 순서"로 구체화.
     **추측한 URL 파라미터 형식을 코드에 박지 말 것** — `JO` 형식은 실호출로만 확인 가능하다.
  4. `apply_fetch(law_ref_id, fetched, *, force=False) -> str` 을 **지금 구현한다**
     (`'FILLED'|'UNCHANGED'|'REVISION_PENDING'`). 수집기(실호출)와 적용기(파일 조작)를 분리하면
     후자는 합성 픽스처로 지금 검증할 수 있다. 최초 PENDING→FETCHED 는 in-place 기입,
     이미 FETCHED 인데 해시 상이면 **덮어쓰지 않고** `pending_revisions/` (append-only, D60).
  5. `text_hash` = `engine.text_hash(text)` — **재구현 금지**.
  6. `README.md` 체크리스트를 실제 상태로: "신청 미완료(사람)" · "`fetch_from_api` 미구현(Sprint 7)" ·
     "`apply_fetch` 완료" 를 정직하게 나눈다.

- **엣지 케이스**: 조문번호·제목 불일치 픽스처 → **파일 미수정** + 불일치 보고 /
  `여신거래기본약관`(CONTRACT 근거)은 수집 대상 아님 / 키 미설정 → `RuntimeError`, 다른 태스크 무영향
- **지켜야 할 결정**: D59(법령은 룩업, RAG 아님 — 벡터 인덱싱 금지) · D60 · D61(불변식 2) · D19
  6-1. **정체성 대조 키 누락도 중단한다** (Stage 1 reviewer W5 반영) — `IDENTITY_KEYS = ("article","title")` 를
     상수로 두고 **누락 검사를 불일치 검사보다 먼저** 수행한다. `None`·`""`·공백 전부 누락으로 보고 `LawMismatchError`.
     ⚠ **선택적 필드(`effective_from`·`promulgation_no` 등)는 대상이 아니다** — 과잉 게이트면 Sprint 7 수집이 통째로 막힌다.
     근거: 대조할 값이 없는 것은 대조를 통과한 것이 아니다 (D50·D62 와 같은 유형).
  6-2. **`applied` 는 3상태 + `requires_signature`** (Stage 1 reviewer N7 반영 · **D75**) —
     `null`(반영 시도 없음) / `"intent"`(기입 직전) / `"confirmed"`(기입 성공 후 승격).
     `force=True` 경로는 **기입 전에 `intent` 로 직전 원문 스냅샷을 확보**하고, `_write_law` 성공 후
     `_confirm_pending_revision` 이 상태 3필드만 전이한다(스냅샷 payload 불변).
     Sprint 7 서명 큐는 **`requires_signature == true` 로 필터**한다.

- **DoD**
  - `uv run --with pytest python -m pytest data/rules/test_rules.py -q` → **19 passed**
  - `uv run python spikes/law_fetch_contract.py` 통과 **25건**, **네트워크 미사용** —
    ⓐ 합성 응답 → `FILLED`, 파일에 `text_hash` 기입 ⓑ 조문번호 불일치 → 중단·파일 바이트 불변
    ⓒ FETCHED + 해시 상이 → `pending_revisions/` 생성·원본 불변 ⓓ 전각/공백 변형 해시 동치
    **ⓑ-W5-a** `article` 키 누락 → 중단·파일 불변 · **ⓑ-W5-b** `title` 공백 → 중단 ·
    **ⓑ-W5-c** 선택적 필드 부재는 `FILLED` 허용(과잉 게이트 아님) ·
    **ⓒ-5** `_write_law` 에 `OSError` 주입 → 법령 파일 불변 · 기록은 `intent`·`requires_signature:true` ·
    **ⓒ-6** `intent→confirmed` 전이가 스냅샷 payload 6키 불변 · **ⓒ-7** 서명 큐 필터 동작
  - `git grep -n LAW_API_KEY` → **이 태스크 소유 파일 기준 0건**(`fetch_laws.py` 폴백 1곳은 허용).
    ⚠ 문서 잔여 3곳(`docs/11_ASSET_LIFECYCLE.md`·`data/data_list.md`·`docs/sessions/`)은 **MQ-613 소유**이므로
    이 DoD 의 판정 대상이 아니다 — 저장소 전역 grep 으로 판정하면 이 게이트는 구조적으로 통과 불가다
  - `data/rules/laws/*.json` **7개**, 전부 `fetch_status:"PENDING"` · 회귀 실행 전후 md5 불변
  - `ruff check` 통과

---

#### MQ-603 — 잔가곡선 산출 (**D74** — D72 는 실측으로 반증돼 supersede 됨)

> 🔄 **이 절은 Stage 1 실행 중 개정됐다.** 최초 명세(D72: 중진공 호가 중앙값 기반 상대 잔가율)로 산출해 본
> 결과 **5종 카테고리 전부 우상향**했고(신품보다 20년 된 설비가 비쌈), `카테고리2` 층화·동일 모델명 비교로도
> 사라지지 않았다. **호가는 연차가 아니라 기계 규격이 지배한다** → D74 로 값 원천을 목업 공식으로 교체.
> 아래 명세는 개정 후 기준이며, **원 D72 분석은 삭제하지 않고 `residual_curve.md §4` 한계 실증으로 보존한다.**

- **복무 시나리오**: S1+ (`assess_repair_value` 의 시장가 축) · S10
- **변경 파일**: `data/build_residual_curve.py`(신규) · `data/extracted/residual_curve.json`(신규, **커밋**) ·
  `data/analysis/residual_curve.md`(신규)
- **원천**: `data/raw/external/중소벤처기업진흥공단_자산거래중개장터 매물정보_20251231.csv` (**cp949**, 16,011행)

- **핵심 로직**
  1. **카테고리 문자열을 문서에서 베끼지 않는다.** 실제 원본에 `환경  설비`(**공백 2칸**)가 있고
     `data/data_list.md §6-1` 이 이를 `환경설비` 로 잘못 옮겼다. 스크립트가 `카테고리1` **유일값을 건수와 함께
     출력**하고, **그 출력 바이트를 그대로** `residual_curve.category` 와 MQ-601a 의 `assets.category` 시드에 쓴다.
     `residual_curve.md` 에 유일값 목록을 `repr()` 로 기록한다(공백이 보이게).
  2. **`확인불가` 함정** — 제조년월 결측률이 0% 로 나오는 이유는 결측 대신 `확인불가` **문자열**이 채워져 있기 때문.
     이걸 결측으로 처리하지 않으면 분모가 16,011 이 되어 잔가곡선이 통째로 틀어진다.
  3. **필터 고정**: `유효 = 제조년월에서 연도 파싱 성공 ∧ 희망가격 ≥ 10,000`.
     스크립트가 **3단계 감소를 전부 출력**한다 (참고 실측: 결측제외 5,911 → 가격>0 5,685 → **가격≥10,000 = 5,475**).
     최종이 **5,475 와 다르면 경고**(중단 아님 — 원본 갱신 감지).
  > ⚠ 위 1~3 은 **(B) 한계 실증 분석** 경로에만 적용된다. 곡선 값은 아래 (A) 가 만든다.

  4. **스크립트를 두 경로로 나눈다** — (A) 곡선 생성(목업 공식, **외부 파일 무의존**) / (B) 실데이터 분석(중진공 CSV).
     **CSV 가 없으면 (B)만 건너뛰고 (A)는 정상 동작해야 한다** — `SystemExit` 대상이 아니다. 곡선이 CI 에서 재생성 가능해야 하기 때문.
  5. **(A) 목업 공식 (D74)**:
     ```
     residual(age) = max((1 - r) ** age, FLOOR)
     r             = 1 - RESIDUAL_AT_LIFE_END ** (1 / N)     # 상수 하드코딩 금지, N 에서 유도
     ```
     - 격자는 D72 그대로: `age_bucket ∈ {'0-2','3-5','6-10','11-15','16-20','21-30'}`
     - **버킷 대표연차는 중앙값** (`1 / 4 / 8 / 13 / 18 / 25`), 어느 값을 썼는지 md 에 표로 남긴다
     - **파라미터 근거를 md 에 반드시 남긴다** — "왜 N=이 값, 왜 FLOOR=이 값"이 없으면 목업이 아니라 지어낸 숫자다
     - **평활 금지는 유지**되나 목업 공식은 정의상 단조 감소한다 → assert 로 검증
  6. **(B) 한계 실증 분석** — 위 1~3 의 집계 + `카테고리2` 층화 + 동일 `모델명` 상관 **3단 근거**.
     산출물은 `residual_curve.md` 에만 가고 **JSON 에는 들어가지 않는다.**
     오염 제거(단일 `제조년월` 일자가 카테고리 표본의 1% 이상이면 제외)·표본 문턱(버킷 <10 · base <30)·
     상위 0.5% 클리핑은 **이 경로에만** 남는다.
  7. `source` 필드에 **목업임을 명시** (예: `"법정 기준내용연수 N년 기반 정률법 추정 (목업) — 실거래 데이터 아님"`).
  8. **표본 필드 4종(`n_samples`·`base_n`·`p25_ratio`·`p75_ratio`)은 전부 `null`** — 목업에 표본은 없다.
     채우면 거짓말이므로 스크립트가 assert 로 강제한다 (MQ-601a DDL 도 nullable 로 정정됨).

- **`residual_curve.md` 구성 (필수)**
  - **§ 곡선 (목업)** — 공식·파라미터·근거·버킷 대표연차 표·산출 값 표
  - **§ 한계 실증 — 왜 실데이터를 쓰지 못하는가** — 3단 근거(카테고리1 집계 우상향 / `카테고리2` 층화 후에도 잔존 /
    동일 모델명 내 상관 ≈ 0). 카테고리 유일값 `repr()` 표·오염 제거 기록·표본 감소 수치를 여기 보존
  - **§ 한계** — 호가지 실거래가 아님 · 연 1회 스냅샷 · **목업 공식이며 실거래가와 무관** ·
    age 2~4 구간 표본 공백

- **엣지 케이스**: CSV 부재 → **(A)는 정상 산출**, (B)만 스킵 + 안내(`SystemExit` 아님).
  `residual_curve.md` 는 **덮어쓰지 않고 보존**(한계 실증 절 유실 방지).
  **회귀 스위트에 넣지 않는다**(원본이 git 제외라 CI 재현 불가). 산출물 JSON 은 커밋
- **지켜야 할 결정**: D65 · **D74**(D72 supersede) · D68 · D19(원본 읽기 전용)
- **DoD**
  - `uv run python data/build_residual_curve.py` → (A) 파라미터·곡선·카테고리 `repr()` 출력 → (B) 3단 근거 출력
  - **CSV 를 치운 상태에서도 exit 0** 이고 JSON md5 가 동일할 것 (곡선의 외부 무의존 증명)
  - **카테고리 유일값을 `repr()` 로 출력**하고 `residual_curve.md` 와 일치 (`환경  설비` 공백 2칸이 보일 것)
  - `residual_curve.json` **42행**(카테고리 7 × 버킷 6, 격자 공백 없음 — N-12 로 `공조냉각유공압` 추가) · 전 행 `0 < residual_ratio ≤ 1` ·
    **버킷 순 단조 감소** · **표본 필드 4종 전부 `null`** · `source` 에 목업 표기
  - **연차 격자표를 `residual_curve.md` 에 남긴다 — MQ-601a 의 시드 설계 입력이다**
  - 멱등성(연속 2회 json·md md5 동일) · `ruff check` 통과

---

### Stage 2

#### MQ-601a — 스키마 7테이블 · 시드 · 자가검증

- **복무 시나리오**: S9·S10·S18·S1+·S19 (전 확장 시나리오의 토대)
- **변경 파일**: `data/seed.py` · `docs/05_DB_SCHEMA.md`
- ⛔ `engine.py`·`test_rules.py`·`data/rules/laws/` 접근 금지 (MQ-601b·MQ-602L 소유)

> ### 🔗 D76-2 편입 (2026-08-09 추가 — 병행 세션에서 인계)
>
> **`traces` 에 `tool_payload TEXT` 컬럼을 함께 추가한다.** `data/seed.py` 가 이 태스크의
> 단독 소유라 여기서 처리해야 충돌이 없다.
>
> ```sql
> ALTER TABLE traces ADD COLUMN tool_payload TEXT;   -- 도구 원본 JSON. tool_result 행만, nullable
> ```
>
> - ⚠️ **기존 `payload` 컬럼을 재사용하지 말 것.** `payload` 는 **SSE `data` 와 바이트 동일**이
>   계약이고(D30) `spikes/trace_persist.py ②`·`sp3_sse_events ⑬` 이 바이트 단위로 검증한다.
>   여기에 도구 원본을 넣으면 평가의 두 소스 대조가 깨진다.
> - `tool_payload` 는 **nullable** — `tool_call`·`block` 행에는 없다.
> - 쓰는 쪽(`backend/agent/trace.py` 의 큐·배리어)은 **D76-2 담당자가 별도로** 처리한다.
>   이 태스크는 **컬럼 추가와 `05_DB_SCHEMA` 반영까지만**.
> - 근거·전체 맥락: **D76**(도구 결과 구조 보존 — 병행 세션 결정). ⚠ **D77 이 아니다** —
>   D77 은 룰 `required_facts` 정합이며 무관하다

- **DDL — 신규 7테이블**

```sql
-- §11 assets — 호스트 설비 (D68). 확장 기능 6종의 대상
CREATE TABLE assets (
  asset_id      TEXT PRIMARY KEY,          -- 'AST-L3-CONV'
  name          TEXT NOT NULL,
  category      TEXT NOT NULL,             -- residual_curve 조인 키 (MQ-603 출력 바이트 그대로)
  line_id       INTEGER NOT NULL,
  building_id   TEXT,                      -- risk_profile(F6) 자리. 참조 테이블 없으므로 FK 없음
  acquired_at   DATE,
  acquisition_cost INTEGER,
  book_value    INTEGER,
  status        TEXT NOT NULL DEFAULT 'IN_USE',
  -- 법정 조건 사실 (11 §7). NULL = "모른다" → 엔진의 INSUFFICIENT_FACTS 경로
  tax_credit_applied       BOOLEAN,
  has_lien                 BOOLEAN,
  lien_creditor            TEXT,
  lien_consent_ref         TEXT,
  policy_id                TEXT,
  safety_inspection_target BOOLEAN,
  last_inspection_date     DATE,
  inspection_valid_until   DATE,
  -- 자산가치 (12 §9)
  cumulative_repair_cost INTEGER NOT NULL DEFAULT 0,
  last_overhaul_at       DATE,
  controller_generation  TEXT,
  parts_eol_flag         BOOLEAN NOT NULL DEFAULT 0,
  CHECK (status IN ('IN_USE','IDLE','DISPOSAL_PENDING','DISPOSED'))
);

-- §12 law_refs — 계층 1 조회용 사본 (정본은 data/rules/laws/*.json, D60)
CREATE TABLE law_refs (
  law_ref_id TEXT PRIMARY KEY,
  law_name TEXT NOT NULL, article TEXT NOT NULL, clause TEXT,
  title TEXT NOT NULL, text TEXT,
  fetch_status TEXT NOT NULL,
  effective_from DATE, effective_to DATE,
  promulgation_no TEXT, source_url TEXT, retrieved_at DATETIME,
  text_hash TEXT, supersedes TEXT, verification_note TEXT,
  CHECK (fetch_status IN ('PENDING','FETCHED','FAILED'))
);

-- §13 rules — 계층 2 조회용 사본. (rule_id, rule_version) 복합 PK = "해석은 개정된다"
CREATE TABLE rules (
  rule_id TEXT NOT NULL, rule_version INTEGER NOT NULL,
  label TEXT NOT NULL, category TEXT NOT NULL,
  disposal_type TEXT NOT NULL, source_type TEXT NOT NULL,
  law_refs TEXT NOT NULL, contract_refs TEXT NOT NULL,   -- JSON array
  interpretation TEXT NOT NULL, required_facts TEXT NOT NULL,
  trigger TEXT NOT NULL, boundary TEXT,
  message TEXT NOT NULL, resolve_options TEXT NOT NULL,
  confidence TEXT NOT NULL, requires_expert_review BOOLEAN NOT NULL,
  PRIMARY KEY (rule_id, rule_version),
  CHECK (disposal_type IN ('BLOCKING','PRECONDITION','AUTO_CLOSE')),
  CHECK (source_type IN ('LAW','CONTRACT')),
  CHECK (json_valid(law_refs) AND json_valid(contract_refs) AND json_valid(trigger))
);

-- §14 decisions — 계층 3 서명 (쓰기 경로는 Sprint 7)
CREATE TABLE decisions (
  decision_id TEXT PRIMARY KEY,
  asset_id  TEXT NOT NULL REFERENCES assets,
  decision_type TEXT NOT NULL,           -- 'DISPOSAL' | 'REPAIR'
  evidence_bundle TEXT NOT NULL,         -- JSON: {laws[], rules[], facts{}}
  bundle_hash TEXT NOT NULL,
  verdict_at_signing TEXT NOT NULL,
  override BOOLEAN NOT NULL DEFAULT 0,
  override_reason TEXT,
  reviewed_by TEXT REFERENCES users,
  signed_at DATETIME,
  state TEXT NOT NULL DEFAULT 'draft',
  -- D63 을 스키마로 잠근다 — 사유 없는 override 는 저장 자체가 불가
  CHECK (override = 0 OR (override_reason IS NOT NULL AND length(trim(override_reason)) > 0)),
  CHECK (json_valid(evidence_bundle)),
  CHECK (state IN ('draft','pending','signed','rejected'))
);

-- §15 flags — 법정 조건 상태 (발생 → 이행 → 해소). deadlines(F5)와 성격이 다름
CREATE TABLE flags (
  flag_id INTEGER PRIMARY KEY,
  asset_id TEXT NOT NULL REFERENCES assets,
  rule_id TEXT NOT NULL, rule_version INTEGER NOT NULL,
  disposal_type TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'OPEN',
  raised_at DATETIME NOT NULL, resolved_at DATETIME,
  resolved_by TEXT REFERENCES users, evidence_ref TEXT,
  CHECK (state IN ('OPEN','IN_PROGRESS','RESOLVED','WAIVED'))
);

-- §16 repair_records — 수리 증빙 (12 §9). 쓰기 경로는 Sprint 7
CREATE TABLE repair_records (
  repair_id TEXT PRIMARY KEY,
  equipment_id TEXT NOT NULL REFERENCES equipment,   -- 수리는 인버터 단위 (D68 ⓑ)
  model TEXT, error_code TEXT,
  part_class TEXT,
  work_type TEXT NOT NULL,               -- PLANNED | UNPLANNED  ★미기재 거부 (12 §7)
  expenditure_class TEXT,                -- CAPITAL | REVENUE | HOLD
  cost INTEGER NOT NULL,
  downtime_hours REAL,                   -- MTTR 산식의 유일한 원천 (아래 ⚠)
  parts TEXT,                            -- JSON array
  performed_by TEXT REFERENCES users, verified_by TEXT REFERENCES users,
  signed_at DATETIME, record_hash TEXT,
  state TEXT NOT NULL DEFAULT 'draft',
  FOREIGN KEY (model, error_code) REFERENCES error_codes(model, code),  -- D13·D33
  CHECK (work_type IN ('PLANNED','UNPLANNED')),
  CHECK ((model IS NULL) = (error_code IS NULL)),
  CHECK (parts IS NULL OR json_valid(parts)),
  CHECK (expenditure_class IS NULL OR expenditure_class IN ('CAPITAL','REVENUE','HOLD'))
);

-- §17 residual_curve — 잔가율 (D65·D74). 정본은 data/extracted/residual_curve.json
-- ⚠ D74 로 값 원천이 목업 공식으로 바뀌었다 → 표본 필드 4종은 전부 NULL 이 정상이다.
--    NOT NULL 을 걸면 "표본이 없는데 표본 수를 채우는" 거짓말을 스키마가 강제하게 된다.
CREATE TABLE residual_curve (
  category   TEXT NOT NULL,
  age_bucket TEXT NOT NULL,          -- '0-2'|'3-5'|'6-10'|'11-15'|'16-20'|'21-30'
  residual_ratio REAL NOT NULL,
  n_samples INTEGER,                 -- 목업이면 NULL (D74)
  p25_ratio REAL, p75_ratio REAL,    -- 목업이면 NULL
  base_n    INTEGER,                 -- 목업이면 NULL (D74)
  source TEXT NOT NULL,              -- 목업임이 이 필드에 명시된다
  PRIMARY KEY (category, age_bucket)
);

-- equipment 확장 — D68. 컬럼 1개만 늘린다
ALTER: equipment.asset_id TEXT REFERENCES assets   -- NULL 허용
-- parts 확장 — 12 §9
ALTER: parts.part_class TEXT   -- 'CONSUMABLE' | 'CRITICAL'
```

> ⚠ **`downtime_hours` 는 `12 §9` 에 없는 컬럼이다.** `12 §2` 가 MTTR 을 요구하는데 저장소에 수리 시간
> 원천이 전혀 없어 추가한다. `12 §9` 반영은 MQ-613 이 한다.
> ⚠ **법정 조건 사실 컬럼을 `equipment` 가 아니라 `assets` 에 둔다.** `11 §7` 은 "equipment 확장"이라 쓰지만
> D68 이 대상을 호스트 설비로 바꿨다. 문서 수정은 MQ-613.

- **`assets` 시드 9건** (10건 아님) — `equipment.location` 문자열에서 유도 (`seed.py:279-290` 실측):

| asset_id | name | line | 연결 equipment |
|---|---|---|---|
| AST-L1-CONV | 1번 조립라인 컨베이어 | 1 | INV-L1-02 |
| AST-L2-SPDL | 2번 가공라인 주축 | 2 | INV-L2-01 |
| AST-L2-CLNT | 2번 가공라인 절삭유 펌프 | 2 | INV-L2-02 |
| AST-L3-CONV | 3번 조립라인 반송 컨베이어 | 3 | INV-L3-01 |
| AST-L3-EXFAN | 3번 조립라인 배기팬 | 3 | INV-L3-02 |
| AST-L3-LIFT | 3번 조립라인 리프터 | 3 | INV-L3-03 |
| AST-L4-CONV | 4번 포장라인 컨베이어 | 4 | INV-L4-01 |
| AST-L4-WRAP | 4번 포장라인 랩핑기 | 4 | INV-L4-02 |
| AST-L4-DUST | 4번 포장라인 집진기 | 4 | INV-L4-03 |

> **`INV-L1-01`(1번 조립라인 분전반)은 `asset_id` NULL** — 배전 위치이지 거래 가능한 기계가 아니다.
> 이게 S9 의 "호스트 자산 없음" 케이스 재료가 되고, 전 확장 도구의 `no_host_asset` 경로로 배선된다.

- **★ 시드 ↔ 잔가 격자 공동 설계** — MQ-603 의 격자표를 읽고 `assess_repair_value` 의 verdict 5종이
  **결정론적으로** 재현되게 배치한다:

| asset | age(→bucket) | 설정 | MQ-609 기대 verdict |
|---|---|---|---|
| `AST-L3-CONV` | 6 (6-10) | `error_history` OCT 30일 3회(기존 S3 시드 유지) | **ROOT_CAUSE_FIRST** |
| `AST-L2-SPDL` | 16 (16-20) | `acquisition_cost` 有, 누적수리비/취득원가 ≈ 0.15, MTBF stable | **REPAIR_RECOMMENDED** |
| `AST-L4-DUST` | 12 (11-15) | `parts_eol_flag=1` | **REPLACE_RECOMMENDED** |
| `AST-L4-WRAP` | 20 (16-20) | MTBF declining, 수리비 > 회복 후 시장가 | **SELL_AS_IS** |
| `AST-L3-LIFT` | 3 (3-5) | **`acquisition_cost` NULL** | **HOLD** (시장가 산출 불가) |

  - `category` 값은 **MQ-603 이 출력한 바이트 그대로**. 격자에 값이 없는 (category, bucket) 조합은 시드에 쓰지 않는다.
  - `acquired_at` 은 기존 관례대로 **실행일 기준 상대 날짜**(`today - N개월`).
  - `repair_records` 12건을 **`AST-L3-CONV` 에 몰지 않는다** — 위 4자산에 분산해 `cumulative_repair_ratio`·
    `downtime_hours`·`planned_ratio` 가 전부 non-null 이 되게. **1건은 `signed_at=NULL`**
    ("서명 없는 레코드는 지표 계산 제외", `12 §11` 회귀 재료).

- **처분 시나리오 시드** — 각 룰이 최소 1건씩 트리거되게 못박는다:
  - `AST-L3-CONV`: `tax_credit_applied=1`, `acquired_at = today - 17개월`, `has_lien=1`,
    `lien_consent_ref=NULL` → **BLOCKED 2건**(TAX-CREDIT-2Y + LIEN-CONSENT)
  - `AST-L4-WRAP`: `acquired_at = today - 23개월` → **HOLD**(경계 구간 22~26)
  - `AST-L2-SPDL`: `has_lien=0`, `safety_inspection_target=1` → **CONDITIONAL**
  - `AST-L4-DUST`: `tax_credit_applied=NULL` → **INSUFFICIENT_FACTS**
  - `AST-L3-LIFT`: 전 사실 채움·무해당 → **CLEAR**

  > ⚠ 처분 age 요구(17/23개월)와 잔가 age 요구(6/16/12/20/3년)가 **같은 자산에 동시에 걸린다.**
  > `acquired_at` 은 잔가 격자 기준으로 잡고, 처분 룰의 `months_since_acquisition` 은
  > `disposal_date` 를 조절해 트리거한다(도구 파라미터이므로 시드와 독립).

- **`parts.part_class` 40종 전부 명시** (LLM 추측 금지, D12 태도).
  소모품·필터·그리스·라벨·글랜드·단자대·V벨트 → `CONSUMABLE` /
  PCB·IGBT·모터·베어링·엔코더·전원모듈·정류브리지·감속 계열 → `CRITICAL`.
  **`FAN-IG5-01` 은 `CRITICAL`** (S1 주인공이므로 3지 판단 데모가 성립해야 함).
- **사람 감수 대응 (D12 선례 복제)** — `seed.py` 에 `related_parts_caveat()`(538행)과 같은 형태의
  `part_class_caveat() -> str` 을 추가해 시드 출력 말미에 경고를 찍는다:
  "`parts.part_class` 40종은 **미검수 초안**이다 — `assess_repair_value` 3지 판단에 직접 영향.
  `TODO_직접할일.md` 참조". **게이트로 만들지 않는다**(막으면 스프린트가 멈춘다).

- **근거 계층 적재** — `seed_rule_catalog(con)`:
  - `engine.load_laws()` → `law_refs` INSERT / `engine.load_rules(laws)` → `rules` INSERT
  - **`load_rules` 를 반드시 경유**한다 — 이 함수가 D61 무결성 게이트다. 우회해 직접 INSERT 하면
    근거 없는 룰이 DB 에 들어갈 경로가 생긴다.
  - `RuleIntegrityError` → **시드 전체 중단**(exit 1). 부분 적재된 DB 를 남기지 않는다.
- `seed_residual_curve(con)` — `residual_curve.json` 있으면 적재, 없으면 0행 + 경고(시드는 성공).

- **`verify()` 추가 검사** (⑮ 는 MQ-601b 소유)
  - ⑫ `assets` **9행** · `equipment.asset_id` NULL 정확히 1건(`INV-L1-01`)
  - ⑬ `law_refs` 행 수 == `data/rules/laws/*.json` 파일 수 (**하드코딩 금지** — MQ-602L 이 파일을 추가하므로 동적 비교)
  - ⑭ `rules` 5행, 전 행 `law_refs`+`contract_refs` 비어있지 않음
  - ⑯ `parts.part_class` NULL 0건 · `residual_curve` 적재 시 **42행**(카테고리 7 × 버킷 6, 격자 공백 없음) ·
    전 행 `0 < residual_ratio ≤ 1` · **버킷 순서대로 단조 감소** · `source` 에 목업 표기 존재
    (⚠ `base_n ≥ 30` 검사는 **폐기** — D74 로 표본 개념이 사라졌다)

- **엣지 케이스**

| 상황 | 동작 |
|---|---|
| `residual_curve.json` 부재 | 0행 적재 + 경고. 시드는 성공 |
| `RuleIntegrityError` | 시드 **중단**(exit 1) |
| `--with-error-codes` 없이 실행 | `repair_records.model/error_code = NULL` (`seed_po_drafts` 선례 512~514행). FK 미위반 |
| `laws/` 6→7건 (MQ-602L) | ⑬ 이 동적 비교라 통과 |
| 기존 DB 존재 | `.db.bak` 백업 후 재생성 (기존 동작 그대로) |

- **지켜야 할 결정**: D68 · D60 · D61 · D62 · D63 · D13·D33 · D39 · D41 · D50 · D12
- **DoD**
  - `uv run python data/seed.py` → ①~⑯ 전부 PASS (⑮ 제외, ⑧ 은 0건이 정상)
  - `uv run python data/seed.py --with-error-codes` → 동일 + ⑧ 65건
  - **`part_class_caveat` 출력 확인**
  - `ruff check` 통과 · 기존 회귀 **273건** 무영향

---

### Stage 3

#### MQ-601b — 근거계층 DB 로더 · `build_facts` · `asset_id` 전환

- **복무 시나리오**: S9·S10·S18 (전 확장 도구의 공통 진입)
- **변경 파일**: `data/rules/engine.py` · `data/rules/test_rules.py` · **`data/rules/rules/*.json`(신규 소유 — D77)** ·
  `spikes/rules_db_load.py`(신규) · `data/seed.py`(⑮ 1건만 추가 — MQ-601a 완료 후이므로 순차 편집, 충돌 없음)

- **🔴 선행 과제 — 룰 카탈로그 정합 (D77, Stage 2 실측으로 발견)**

  **현재 처분 판정 5종 중 `CONDITIONAL`·`CLEAR` 가 어떤 시드로도 도달 불가다.** 룰 5종 중 3종의
  `required_facts` 가 자기 트리거와 어긋나 **모든 자산에서 항상 `INSUFFICIENT_FACTS`** 를 만들기 때문이다.
  이걸 먼저 고치지 않으면 **이 태스크의 verify ⑮ 와 MQ-604 DoD 가 구조적으로 통과할 수 없다.**

  | 룰 | `required_facts` 수정 | 근거 |
  |---|---|---|
  | `LIEN-CONSENT` | `lien_consent_ref` **제거** → `["has_lien","lien_creditor"]` | 부재가 곧 트리거 조건(`is_null`)이라 선언하면 논리적으로 발화 불가 |
  | `INSURANCE-NOTIFY` | **최종: `["insured"]`** (D78). 중간 단계로 `["policy_id"]` 를 거쳤으나 그 상태로는 `CLEAR` 가 도달 불가여서 D78 로 `assets.insured` 를 신설하고 트리거 첫 분기를 `insured eq true` 로 개정했다 | `risk_grade_*` 는 F6 원천 부재. `policy_id` 한 컬럼이 "부보 여부"와 "증권 번호"를 겸해 **"확인된 미부보"를 표현할 자리가 없었다** |
  | `VAT-INVOICE` | `sale_amount`·`buyer_biz_no` **제거**, `vat_invoice_issued` **추가** → `["disposal_mode","vat_invoice_issued"]` | 거래 사실은 자산 사실이 아니다. 트리거가 실제 읽는 것은 `vat_invoice_issued` 인데 선언돼 있지 않았다 |
  | **`SAFETY-INSPECTION`** (Stage 2 추가 발견) | `last_inspection_date`·`inspection_valid_until` **제거** → `["safety_inspection_target","disposal_mode"]` | 트리거가 `safety_inspection_target` 만 읽는다. 두 날짜는 메시지·체크리스트용이라 D77 원칙 ③ 대상. **이 4번째 룰을 안 고치면 3종만 고쳐도 `CONDITIONAL`·`CLEAR` 는 여전히 미도달**(eval-runner 실측: 5자산 전부 `missing=['disposal_mode']`) |

  > ⚠ **Stage 2 에서 시드가 이 결함을 데이터로 덮었다가 되돌렸다** — 안전검사 **비대상** 자산 8건에
  > `last_inspection_date` 를 채워 넣었던 것을 reviewer 가 D62·D65 위반으로 잡았다(없는 법정 사실 생성).
  > 되돌린 결과 **비대상 자산은 NULL** 이므로, 이 룰을 고치기 전에는 `verify ⑮` 가 정직하게 실패한다.
  > **그게 정상이다** — 허위 데이터로 GREEN 을 만들지 않는다.

  - ⛔ **`trigger`·`boundary`·`interpretation`·`law_refs` 는 건드리지 마라.** `required_facts` 만 고친다
    — **예외 1건**: `INSURANCE-NOTIFY.trigger` 첫 분기는 **D78 이 명시적으로 허가**했다. 그 외에는 결정 없이 열지 말 것
  - ⛔ **`rule_version` 을 올려라** — 해석이 바뀐 게 아니라 선언 오류 정정이지만, `rules` 테이블이
    `(rule_id, rule_version)` 복합 PK 이고 D60 이 "해석은 개정된다"를 전제한다. 변경 사유를 파일에 남길 것
  - **`build_facts` 가 `vat_invoice_issued` 를 채운다** — precheck 는 **거래 성립 전**이므로 `False` 가 확정 사실이다.
    ⚠ 지어내는 게 아니라 **판정 시점의 정의**이며, 그 근거를 docstring 에 남겨라. 다른 거래 사실은 채우지 마라
  - **`risk_score_delta_pct` 경계 확인** — `INSURANCE-NOTIFY.boundary` 가 이 필드를 읽는데 원천이 없다.
    **키 부재 시 경계 검사가 예외를 내거나 잘못 `HOLD` 로 빠지지 않는지** 실제로 확인하고, 문제가 있으면 보고해라
  - **`test_rules.py` 에 발화 가능성(satisfiability) 회귀 추가 (D77)** — 룰 5종 **각각**에 대해
    "`TRIGGERED` 를 만드는 사실 조합이 존재한다"를 검사한다. 지금의 `LIEN-CONSENT` 가 이 테스트에 걸려야 정상이다

- **인터페이스**

```python
def load_laws_from_db(con: sqlite3.Connection) -> dict[str, LawRef]: ...

def load_rules_from_db(con: sqlite3.Connection, laws: dict[str, LawRef]) -> dict[str, Rule]:
    """파일 로더(load_rules)와 **완전히 같은 불변식**을 적용한다 — 근거 없는 룰 거부(D61),
    미등록 법령 참조 거부. DB 사본이 무결성 검사를 우회하는 경로를 만들지 않는다."""

def build_facts(
    asset_row: sqlite3.Row | dict, *,
    disposal_mode: str | None = None,
    disposal_date: str | None = None,
    at: date | None = None,
) -> dict:
    """assets 행 → 룰 엔진 facts.

    ★ 가장 중요한 규칙: **값이 None 인 키는 dict 에 넣지 않는다.**
      evaluate_rule(216행)이 `f not in facts` 로 사실 누락을 판정하므로, None 을 넣으면
      "모른다"가 "조건 미해당(CLEAR)"으로 조용히 바뀐다 — 불변식 4(D62)가 통째로 무너지는
      단 하나의 버그 지점이다. False/0 은 값이므로 반드시 포함한다.

    파생 필드:
      months_since_acquisition — acquired_at·disposal_date 둘 다 있을 때만 계산
      risk_grade_before/after, risk_score_delta_pct — risk_profile(F6) 부재로 산출 불가.
                                 **키를 넣지 않는다** → INSURANCE-NOTIFY 는
                                 INSUFFICIENT_FACTS 가 정답이다 (억지로 CLEAR 만들지 말 것)
    """
```

  또한 엔진 함수 `check_disposal_blockers()` 의 반환 키 `"equipment_id"` → **`"asset_id"`**,
  `facts.get("equipment_id")` → `facts.get("asset_id")`. `test_rules.py` 의 `_full_facts()` 도 함께.

- **`verify` ⑮ 추가**: 처분 시나리오 5자산의 `check_disposal_blockers(build_facts(row))` verdict 가
  MQ-601a 시드의 기대값과 일치
- **지켜야 할 결정**: D61 · D62 · **D77** · D68 · D60
- **DoD**
  - `uv run --with pytest python -m pytest data/rules/test_rules.py -q` → **19 passed** (`asset_id` 전환 후 개수 유지)
  - `uv run python spikes/rules_db_load.py` 통과 — ⓐ 파일 로더 == DB 로더(`LawRef`/`Rule` dataclass 동치)
    ⓑ DB 에 근거 없는 룰 행을 심으면 `RuleIntegrityError` ⓒ NULL 컬럼이 facts 키에서 빠짐
    (`"tax_credit_applied" not in facts`) ⓓ 그 결과 verdict 가 `INSUFFICIENT_FACTS`(**≠`CLEAR`**)
  - `uv run python data/seed.py` → ⑮ 포함 전부 PASS · `ruff check`
  - **처분 판정 5종이 전부 재현된다** — `AST-L3-CONV`→BLOCKED(**blockers 2건**: TAX-CREDIT-2Y + LIEN-CONSENT) ·
    `AST-L4-WRAP`→HOLD · `AST-L2-SPDL`→**CONDITIONAL** · `AST-L4-DUST`→INSUFFICIENT_FACTS · `AST-L3-LIFT`→**CLEAR**
    (뒤 두 종은 D77 수정 전에는 도달 불가였다 — 이게 이 태스크의 실질 관문이다)
  - `data/rules/rules/*.json` **5개 유지**(파일 추가·삭제 없음).
    `rule_version` 은 **판정이 실제로 달라지는 룰만** 올린다 — `TAX-CREDIT-2Y` 는 변경이 없으므로 **v1 유지**가 맞다
    (판정 불변인 룰에 버전만 올리면 `rule_version` 이 개정 신호로서 무의미해진다, D60 취지).
    `trigger` 는 **`INSURANCE-NOTIFY` 만** 변경(D78), 나머지 4종 무변경
  - **발화 가능성 회귀**가 5종 전부에 대해 통과 (D77)

---

### Stage 4 — 읽기 도구 5종

> **공통 규약 (5태스크 전부 준수).** `04_MCP_TOOLS` 원칙 그대로.
> - 파일 상단에 `DESCRIPTION` 상수(언제 쓰고 언제 쓰지 말지 명시) — MQ-612 가 그대로 등록한다
> - **예외를 던지지 않는다.** 전부 `status: "ok"|"not_found"|"empty"|"error"` + `reason` (D9·D46)
> - `from ..db import read_only` 만 사용. **쓰기 커넥션 금지** (D10)
> - `asset_id` 를 받되 `equipment_id` 만 주어지면 `equipment.asset_id` 로 해석. 그 값이 NULL 이면
>   `status:"not_found", reason:"no_host_asset"` — `INV-L1-01`(분전반)이 정확히 이 케이스
> - `mcp_server` 가 `backend` 를 import 하지 않는다 (D15). **`data.rules.engine` import 는 허용 (D73)** —
>   `server.py:28` 이 레포 루트를 `sys.path` 에 넣으므로 `from data.rules.engine import ...` 가 동작한다
> - 판정 결과에는 **항상** `not_considered[]` 와 `disclaimer` 를 싣는다 (불변식 6)
> - 🔴 **`assets` 행을 판정기에 직접 넘기지 마라 — 반드시 `engine.build_facts()` 를 경유한다 (D62).**
>   `evaluate_rule` 은 **키 존재**만 보므로 `dict(row)` 를 그대로 넘기면 **NULL 이 "값 있음"으로 읽혀 조용히 `CLEAR`** 가 된다.
>   "모른다"를 "조건 미해당"으로 바꾸는 단 하나의 지점이다. 상세: `05_DB_SCHEMA §11` 경고 블록
> - **`disposal_mode` 는 `engine.DISPOSAL_MODES` 를 단일 출처로 import 해 검증**한다. enum 밖 값(`"SELL"`·`"sale"`)을
>   그대로 흘리면 `VAT-INVOICE` 트리거(`eq "SALE"`)를 빗나가 **오타 하나가 `CONDITIONAL` 을 `CLEAR` 로 만든다**
> - **`engine` 은 예외를 던진다**(`RuleIntegrityError`·`KeyError`·`TypeError` 등). 도구는 `RuleIntegrityError` 하나만
>   잡지 말고 **광범위하게 포착해 `status:"error"` 로 닫아야** "어떤 입력에도 예외가 새어나오지 않음" DoD 를 만족한다
> - ⛔ **공유 파일(`server.py`·`prompts.py`·`mcp_client.py`) 일절 접근 금지** — MQ-612 소유

#### MQ-604 — `check_disposal_blockers` (S9 진입점)

- **변경 파일**: `mcp_server/tools/check_disposal_blockers.py` (신규)
- **인터페이스**

```python
DESCRIPTION = (
    "설비 자산의 처분(매각·폐기·이전) 가능 여부를 법정 조건으로 판정한다. "
    "처분·매각·폐기 이야기가 나오면 가장 먼저 호출할 것. 판정은 조문 근거와 함께 나오며, "
    "BLOCKED 면 처분을 진행하지 말고 해소 경로를 안내할 것. "
    "HOLD·INSUFFICIENT_FACTS 를 '문제 없음'으로 해석하지 말 것 — 각각 경계 구간과 사실 부족이다. "
    "이 도구는 판정만 한다. 처분 확정은 사람의 서명으로만 이뤄진다."
)

def check_disposal_blockers(
    asset_id: str | None = None,
    equipment_id: str | None = None,
    disposal_mode: str = "SALE",       # SALE | SCRAP | TRANSFER
    disposal_date: str | None = None,
) -> dict
```
```jsonc
{"status":"ok","asset_id":"AST-L3-CONV","evaluated_at":"2026-08-09",
 "verdict":"BLOCKED",              // BLOCKED | HOLD | INSUFFICIENT_FACTS | CONDITIONAL | CLEAR  (5종, D79)
 "blockers":[{"rule_id","label","citations","law_refs","reasoning","resolve_options",
              "requires_expert_review","rule_version"}],
 "preconditions":[…],"holds":[…],"insufficient":[…],
 "evidence_completeness":"LAW_TEXT_PENDING",   // COMPLETE | LAW_TEXT_PENDING
 "not_considered":[…],"disclaimer":"…"}
```

- **핵심 로직**
  1. asset 해석(공통 규약) → `assets` 1행. 없으면 `not_found`/`unknown_asset`.
  2. `engine.load_laws_from_db(con)` + `load_rules_from_db(con, laws)`.
     **`law_refs` 0행이면 `status:"error", reason:"rule_catalog_not_loaded"`** — `not_found` 가 아니다.
     (D50 과 같은 논리: 미적재를 "조건 없음"으로 주면 모든 자산이 CLEAR 로 통과한다)
  3. `engine.build_facts(row, …)` → `evaluate_rule` 전 룰 → 4버킷 분류.
  4. **`evidence_completeness`** — 인용된 법령 중 `fetch_status != 'FETCHED'` 가 하나라도 있으면
     `"LAW_TEXT_PENDING"` + `disclaimer` 에 "조문 원문 미수집 상태이며 인용은 조문 번호·제목 기준이다" 덧붙임.
     **판정 자체는 막지 않는다** — 근거 참조 무결성(불변식 1·2)은 파일 존재로 이미 보장된다.
  5. `verdict` 우선순위 (**D79 — 5종**): `blockers > holds > insufficient > preconds > CLEAR`.
     ⚠ `insufficient` 를 `HOLD` 에 흡수하던 구 4종 로직으로 되돌리지 마라 — D71 의 HTTP 매핑이 깨진다.
  6. `RuleIntegrityError` → `status:"error", reason:"rule_integrity"` (도구는 예외를 던지지 않는다).

- **엣지 케이스**

| 상황 | 반환 |
|---|---|
| `asset_id`·`equipment_id` 둘 다 없음 | `error`/`invalid_input` |
| `equipment.asset_id` NULL (`INV-L1-01`) | `not_found`/`no_host_asset` |
| `disposal_mode` enum 밖 | `error`/`invalid_input` (폴백 금지) |
| 사실 전부 NULL | `verdict:"INSUFFICIENT_FACTS"`(D79) + `insufficient` 다건. **CLEAR 로 내려가면 안 된다** |
| `law_refs`/`rules` 0행 | `error`/`rule_catalog_not_loaded` |

- **지켜야 할 결정**: D61 · D62 · D59 · D50 · D68 · D9·D46
- **DoD**
  - `AST-L3-CONV` → `verdict:"BLOCKED"`, blockers 2건, 전 항목 `citations` 비어있지 않음
  - `AST-L4-WRAP`→`HOLD` · `AST-L2-SPDL`→`CONDITIONAL` · `AST-L4-DUST`→**`INSUFFICIENT_FACTS`**+insufficient(D79) ·
    `AST-L3-LIFT`→**`disposal_mode='SCRAP'` 일 때만 `CLEAR`**, `SALE` 이면 `CONDITIONAL`(D78 부수 확정 —
    매각은 `VAT-INVOICE` 때문에 정의상 최소 `CONDITIONAL`)
  - `equipment_id='INV-L1-01'` → `no_host_asset`
  - **`evidence_completeness` 는 `"LAW_TEXT_PENDING"` 을 단언**한다 (조문 미수집이 현재 정상 상태 —
    `"COMPLETE"` 를 기대하지 않는다)
  - 어떤 입력에도 예외가 새어나오지 않음(빈 dict·잘못된 타입 포함)
  - `ruff check` · 회귀 **273건** 무영향(아직 서버 미등록)

#### MQ-605 — `verify_ownership` (S18)

- **변경 파일**: `mcp_server/tools/verify_ownership.py` (신규)
- **인터페이스**: `verify_ownership(asset_id=None, equipment_id=None) -> dict`
```jsonc
{"status":"ok","asset_id":"AST-L2-SPDL",
 "verdict":"PARTIAL",                       // VERIFIED | PARTIAL | UNVERIFIED
 "categories":[{"category":"권리관계","items":[
     {"item":"동산담보등기 조회","state":"UNVERIFIED","evidence":null,
      "limit":"개별 물건 조회 수단이 없다 — 등기정보광장은 집계 통계만 제공"}]}],
 "verified":[…],"unverified":[…],
 "residual_risk":"리스 물건일 가능성 배제 불가",
 "mitigation":"진술보장 + 손해배상 특약으로 계약상 배분 권고",
 "not_considered":[…],"disclaimer":"…"}
```
- **핵심 로직**
  1. `12 §6` **9개 카테고리를 고정 상수**로: 물리적 상태 / 가동 이력 / 정비 이력 / 기술적 진부화 /
     권리관계 / 법정 요건 / 재무·회계 / 시장·가격 / 이전 비용
  2. 항목별 판정 원천을 **명시적으로** 매핑. 원천이 없으면 무조건 `UNVERIFIED` + `limit` 문자열:

     | 카테고리 | 항목 | 원천 |
     |---|---|---|
     | 정비 이력 | 정기점검·핵심부품 교체 | `repair_records`(**서명된 것만**) |
     | 정비 이력 | **반복 고장 패턴** | `error_history` 30일 3회 — **인버터 단위**(D68 ⓑ), asset 하위 equipment 전체 집계 |
     | 기술적 진부화 | 부품 단종 | `parts.discontinued`(D20) · `assets.parts_eol_flag` |
     | 기술적 진부화 | 제어기 세대 | `assets.controller_generation` |
     | 권리관계 | 담보 | `assets.has_lien`·`lien_creditor`·`lien_consent_ref` |
     | 권리관계 | **리스 여부** | 원천 없음 → `UNVERIFIED` (고정) |
     | 법정 요건 | 안전검사 | `assets.safety_inspection_target`·`last_inspection_date`·`inspection_valid_until` |
     | 재무·회계 | 감가상각 | `assets.acquisition_cost`·`book_value` |
     | 시장·가격 | 동일 기종 거래가 | `residual_curve`(있으면). 0행이면 `UNVERIFIED` |
     | 물리적 상태 / 가동 이력 / 이전 비용 | 전 항목 | 원천 없음 → `UNVERIFIED` |

  3. **`verdict` 규칙**: `UNVERIFIED` 가 하나라도 있으면 최대 `PARTIAL`. 전 항목 `VERIFIED` 일 때만 `VERIFIED`.
     **`PARTIAL` 은 어떤 조건으로도 `VERIFIED` 로 승격되지 않는다** (`11 §6`). **코드에 승격 경로 자체를 만들지 않는다.**
  4. ⛔ **외부 API 런타임 호출 금지.** `.env.example:40-43` 이 "`backend/`·`mcp_server/` 는 이 절의 키를
     절대 참조하지 않는다 — 요청마다 외부 기관을 호출하면 서명 시점 스냅샷 재현 전제가 깨진다"고 못박았다.
     해당 항목은 `UNVERIFIED` + `limit:"사전 수집 스냅샷 없음"`.
  5. `residual_risk`·`mitigation` 은 **UNVERIFIED 항목에서 조립**. 전부 확인되면 `residual_risk: null`.
- **엣지 케이스**: 자산 없음 → `not_found` / `repair_records` 0행 → 정비 이력 `UNVERIFIED`
  (**빈 이력을 "문제 없음"으로 읽지 않는다**) / `residual_curve` 0행 → 시장·가격 `UNVERIFIED`
- **지켜야 할 결정**: D62 · D65 · D68 ⓑ · D9 · `11 §6`
- **DoD**
  - 시드 9자산 전부에서 `verdict` 가 `PARTIAL` 이하 (`VERIFIED` 가 나오면 판정이 헐거운 것)
  - 9개 카테고리 전부 출력에 존재, 각 항목에 `state` 와 (UNVERIFIED면) `limit` 존재
  - **코드에 `verdict = "VERIFIED"` 로 승격하는 분기가 없음** (reviewer 확인 항목)
  - `git grep -n "DATA_GO_KR\|IROS_API\|LAW_API" mcp_server/` → **0건**
  - `ruff check`

#### MQ-606 — `classify_part_criticality`

- **변경 파일**: `mcp_server/tools/classify_part_criticality.py` (신규)
- **인터페이스**: `classify_part_criticality(part_no: str) -> dict`
```jsonc
{"status":"ok","part_no":"FAN-IG5-01","part_class":"CRITICAL",
 "basis":"parts.part_class (데이터 조회)","name":"냉각팬 (iG5A 표준)",
 "category":"냉각","discontinued":false,
 "reviewed":false,"note":"part_class 는 미검수 초안"}
```
- **핵심 로직**: `parts` 단순 조회. **추론하지 않는다** — `part_class` 가 NULL 이면
  `status:"error", reason:"part_class_not_set"`. 부품 등급을 도구가 추측하면 `assess_repair_value` 의
  3지 판단이 근거를 잃는다 (D12 가 `related_parts` 에서 세운 태도 그대로).
  **`reviewed: false` 필드 필수** — `related_parts.seed.json` 의 `reviewed` 플래그와 같은 성격이고,
  이 값이 `assess_repair_value` verdict 를 가른다.
- **엣지 케이스**: 미등록 part_no → `not_found` / `part_class` NULL → `error`/`part_class_not_set` /
  빈 문자열 → `error`/`invalid_input`
- **지켜야 할 결정**: D12 · D20 · D9
- **DoD**: `FAN-IG5-01`→CRITICAL · 소모품 1종→CONSUMABLE · 미등록→not_found ·
  **`reviewed` 필드 존재** · 40종 전부 NULL 아님 · `ruff check`

#### MQ-607 — `get_maintenance_metrics`

- **변경 파일**: `mcp_server/tools/get_maintenance_metrics.py` (신규)
- **인터페이스**: `get_maintenance_metrics(asset_id=None, equipment_id=None, window_months=24) -> dict`
```jsonc
{"status":"ok","asset_id":"AST-L3-CONV","window_months":24,
 "mtbf_days":41.2,"mtbf_basis":"calendar_days","mtbf_trend":"declining",
 "mttr_hours":3.8,"availability":null,
 "planned_ratio":0.33,"n_repairs_signed":11,"n_repairs_unsigned":1,
 "cumulative_repair_cost":18400000,"acquisition_cost":120000000,
 "cumulative_repair_ratio":0.153,
 "repeat_failure":true,
 "excluded":["서명되지 않은 수리 레코드 1건은 지표에서 제외했다"],
 "not_considered":["가동시간·스핀들 시간(원천 없음)","OEE(거래 판정 사용 금지 — D64)"],
 "disclaimer":"MTBF 는 가동시간이 아니라 달력 기준 평균 고장 간격이다(D70)."}
```
- **핵심 로직**
  1. asset 하위 `equipment` 전체를 모아 집계 (D68 ⓑ — 판정 기준은 인버터 단위, **집계만** asset 단위).
  2. **MTBF (D70)**: `error_history.occurred_at` 오름차순 인접 간격(일)의 평균.
     이벤트 <2건이면 `null`(**0으로 채우지 않는다**). `mtbf_basis:"calendar_days"` 필수.
  3. **추세**: 최근 12개월 MTBF vs 이전 12개월. 어느 쪽이든 이벤트 <2건이면
     `mtbf_trend:"insufficient_data"` — **`"stable"` 로 대체하지 않는다.**
  4. **MTTR**: `signed_at IS NOT NULL` 인 `repair_records.downtime_hours` 평균. 전부 NULL 이면 `null`.
  5. **가용도**: MTBF 는 일, MTTR 은 시간이라 **단위가 다르다.** MTTR 을 일로 환산해 계산하되
     `mtbf_days` 가 `null` 이면 `availability:null`. **단위를 코드 주석에 명시**(단위 혼동은 지표를 조용히 틀리게 하는 대표 사례).
  6. **예방보전 비율**: `PLANNED / (PLANNED+UNPLANNED)`, **서명된 레코드만** (`12 §11`).
     제외 건수를 `excluded` 에 문장으로 남긴다(숨기지 않는다).
  7. `repeat_failure`: `get_error_history` 의 판정 기준(30일 3회)을 **재사용** — 상수를 재정의하지 말고 같은 값을 쓴다(D2·D29).
  8. `availability`·`mtbf_trend` 가 `null`/`insufficient_data` 여도 `status:"ok"`. 도구 실패가 아니라 데이터 부족이며 그 사실이 필드로 드러난다.
- **엣지 케이스**: `error_history` 0건 → 전 지표 null + `status:"ok"`(empty 아님 — 자산은 실재한다) /
  서명 레코드 0건 → `planned_ratio:null` + excluded 문장 / `acquisition_cost` NULL → `cumulative_repair_ratio:null`
- **지켜야 할 결정**: **D70(승인 필요)** · D64(**OEE 금지 — 계산도 출력도 하지 않는다**) · D68 ⓑ · D2·D29 · D9
- **DoD**: `AST-L3-CONV` 에서 5지표 전부 산출 · 미서명 1건이 `excluded` 에 나타나고 `planned_ratio` 분모에서 빠짐 ·
  이력 0건 자산에서 예외 없이 null 반환 · **출력에 `oee` 키 부재** · `ruff check`

#### MQ-608 — `classify_expenditure`

- **변경 파일**: `mcp_server/tools/classify_expenditure.py` (신규)
- **선행**: **MQ-602L** (`KR-CITA-ENF-31` 등록) — 없으면 근거 없는 판정이 되어 만들 수 없다(불변식 1)
- **인터페이스**
```python
def classify_expenditure(
    part_class: str,          # CONSUMABLE | CRITICAL
    repair_scope: str,        # RESTORE | UPGRADE | OVERHAUL | REPLACE_UNIT
    amount: int,
    asset_id: str | None = None,
) -> dict
```
```jsonc
{"status":"ok","verdict":"CAPITAL",       // CAPITAL | REVENUE | HOLD
 "law_refs":["KR-CITA-ENF-31"],
 "citations":["법인세법 시행령 제31조(즉시상각의제)"],
 "reasoning":"…","requires_expert_review":true,
 "evidence_completeness":"LAW_TEXT_PENDING",
 "not_considered":[…],"disclaimer":"…"}
```
- **핵심 로직**
  1. **근거 검증 먼저** — `law_refs` 테이블에서 `KR-CITA-ENF-31` 조회. 없으면 `status:"error", reason:"law_ref_missing"`.
     불변식 2(미등록 법령 참조 거부)를 도구 안에서 직접 강제한다.
  2. 판정 규칙(결정론적):
     - `UPGRADE`·`OVERHAUL` → `CAPITAL`
     - `RESTORE` + `CONSUMABLE` → `REVENUE`
     - `RESTORE` + `CRITICAL` → **`HOLD`** (원상 회복인지 내용연수 연장인지가 실무 최대 논쟁 지점 — `12 §3`)
     - `REPLACE_UNIT` → `HOLD`
     - `asset_id` 주어지고 `amount / acquisition_cost ≥ 0.20` 이면 결과와 무관하게 **`HOLD` 로 격상**. 사유를 `reasoning` 에 남긴다.
  3. `HOLD` 일 때 `requires_expert_review: true` + "세무 전문가 확인 필요". **`CAPITAL`/`REVENUE` 로 반올림하지 않는다.**
  4. ⛔ **룰 카탈로그(`data/rules/rules/`)에 파일을 추가하지 말 것.** 그 디렉토리는 처분 플래그 전용이고
     (`disposal_type` 필수), `check_disposal_blockers` 가 `RULES_DIR` 전체를 로드하므로 지출 판정 룰을 넣으면
     **처분 판정에 섞여 들어간다.** `test_rules.py` 의 `COVERED` 집합도 깨진다.
- **엣지 케이스**: enum 밖 → `error`/`invalid_input`(폴백 금지) / `amount ≤ 0` → `error`/`invalid_input` /
  법령 미등록 → `error`/`law_ref_missing` / 조문 `PENDING` → 판정 진행 + `evidence_completeness:"LAW_TEXT_PENDING"`
- **지켜야 할 결정**: D61·불변식 2 · D62 · D59 · D9
- **DoD**: 5개 입력 조합 → CAPITAL/REVENUE/HOLD 정확 · `law_refs` 행 삭제 후 호출 → `law_ref_missing` ·
  **`data/rules/rules/` 파일 수 5 유지** · `uv run --with pytest python -m pytest data/rules/test_rules.py -q` 19 passed · `ruff check`

---

### Stage 5

#### MQ-609 — `assess_repair_value` (S1+ 3지 판단)

- **변경 파일**: `mcp_server/tools/assess_repair_value.py` (신규)
- **선행**: MQ-606·MQ-607(심볼 import) · MQ-603(residual_curve)
- **인터페이스**: `assess_repair_value(equipment_id, failed_part, repair_cost, repair_scope="RESTORE") -> dict`
```jsonc
{"status":"ok","asset_id":"AST-L3-CONV","equipment_id":"INV-L3-01",
 "failed_part":"FAN-IG5-01","part_class":"CRITICAL",
 "repair_cost":8500000,"book_value":63333333,
 "market_value_before":42000000,"market_value_after":51000000,
 "value_recovery":9000000,"recovery_ratio":1.06,
 "mtbf_trend":"declining","repeat_failure":false,"cumulative_repair_ratio":0.21,
 "verdict":"REPAIR_RECOMMENDED",   // REPAIR_RECOMMENDED | REPLACE_RECOMMENDED | SELL_AS_IS | ROOT_CAUSE_FIRST | HOLD
 "alternatives":[{"option":"REPLACE","cost":null,"note":"신규 취득 단가 원천 없음"},
                 {"option":"SELL_AS_IS","proceeds":42000000,"note":"수리 없이 현상 매각(추정)"}],
 "estimates":["market_value_before","market_value_after","value_recovery"],
 "not_considered":[…],"disclaimer":"시장가는 목업 잔가곡선 기반 추정치. 실거래가와 다를 수 있음"}
```
- **핵심 로직**
  1. `equipment` → `asset_id` 해석. NULL 이면 `no_host_asset`.
  2. `classify_part_criticality(failed_part)` · `get_maintenance_metrics(asset_id=…)` 호출(모듈 import).
     어느 하나라도 `status != "ok"` 면 **그 status·reason 을 그대로 전파** — 실패를 삼키고 기본값으로 진행하면
     없는 근거로 판단하게 된다.
  3. **★ 최우선 분기**: `repeat_failure == true` 면 **다른 계산을 하기 전에** `verdict:"ROOT_CAUSE_FIRST"` 로
     즉시 반환하고 `alternatives` 를 비운다. `12 §11`·D2 가 "3지 판단보다 근본원인이 먼저"라 명시했고,
     S3 발주 보류(`po_card` variant `hold`, D35)가 그대로 적용돼야 한다. 3지 선택지를 함께 주면 에이전트가 그중 하나를 고른다.
  4. 시장가: `age = 오늘연도 - year(assets.acquired_at)` → **버킷 매핑** → `residual_curve` 의
     `(category, age_bucket)` 조회 → `market_value_before = acquisition_cost × residual_ratio`.
     **버킷 밖(31년 이상)이거나 행이 없으면 `null`** — 인접 버킷으로 **보간하지 않는다** (D65).
     `market_value_after`: `part_class == "CRITICAL"` 일 때만 잔존수명 회복분 반영, 계수는 코드 상수 + `estimates` 명시.
     `CONSUMABLE` 이면 `market_value_after = market_value_before` (소모품 교체는 가격에 직접 반영되지 않는다, `12 §1`).
  5. `verdict` 규칙(결정론적):
     - `recovery_ratio ≥ 1.0` → `REPAIR_RECOMMENDED`
     - `cumulative_repair_ratio ≥ 0.5` 또는 `parts_eol_flag=1` → `REPLACE_RECOMMENDED`
     - `market_value_before` 가 `null` → **`HOLD`** + 사유. 값이 없는데 판단하면 지어내는 것이다
     - `mtbf_trend == "declining"` + `repair_cost > market_value_after` → `SELL_AS_IS`
  6. **`estimates[]` 필수** — 추정치인 필드명을 명시적으로 나열. D65 의 "고지 강제"를 문장이 아니라
     **필드로** 구현해 UI·평가가 기계적으로 확인할 수 있게 한다.
- **엣지 케이스**: `residual_curve` 0행 → `HOLD` + 사유 / `acquisition_cost` NULL → `HOLD` /
  `repair_cost ≤ 0` → `error`/`invalid_input` / `failed_part` 미등록 → `not_found` 전파
- **지켜야 할 결정**: D2·D35 · D65 · D64 · D31 · D68 · D9
- **DoD** — MQ-601a 시드가 보장하는 결정론적 5케이스:

| 호출 | 기대 |
|---|---|
| `INV-L3-01`(→`AST-L3-CONV`) | `ROOT_CAUSE_FIRST`, `alternatives` 빈 배열, **다른 필드 계산 없이 즉시 반환** |
| `AST-L2-SPDL` 하위 equipment | `REPAIR_RECOMMENDED`, `estimates` 존재 |
| `AST-L4-DUST` 하위 | `REPLACE_RECOMMENDED` |
| `AST-L4-WRAP` 하위 | `SELL_AS_IS` |
| `AST-L3-LIFT` 하위 (`acquisition_cost` NULL) | `HOLD` + 사유 문장 |

  - `residual_curve` 를 비우고 재호출 → **전 자산 `HOLD`** (잔가 원천 없음). **값을 지어내지 않음을 증명**
  - 출력에 `estimates[]` 존재 · `oee` 키 부재 · `repair_cost ≤ 0` → `invalid_input`
  - 하위 도구가 `status != "ok"` 면 그 status·reason 그대로 전파 · `ruff check`

#### MQ-610 — `build_evidence_bundle`

- **변경 파일**: `mcp_server/tools/build_evidence_bundle.py` (신규)
- **인터페이스**: `build_evidence_bundle(asset_id=None, equipment_id=None, disposal_mode="SALE", disposal_date=None) -> dict`
```jsonc
{"status":"ok","asset_id":"AST-L3-CONV",
 "evidence_bundle":{
   "laws":[{"law_ref_id":"KR-STTC-24","effective_from":"2025-01-01","text_hash":"sha256:…"}],
   "rules":[{"rule_id":"TAX-CREDIT-2Y","rule_version":1}],
   "facts":{"acquired_at":"2025-03-01","tax_credit_applied":true,…}},
 "bundle_hash":"sha256:…","verdict":"BLOCKED",
 "built_at":"2026-08-09T05:12:00Z","disclaimer":"…"}
```
- **핵심 로직**
  1. `check_disposal_blockers` 를 호출해 판정과 인용 룰 집합을 얻는다(**중복 구현 금지**).
  2. `laws[]` = 인용된 룰들의 `law_refs` 합집합. 각 항목에 `effective_from`·`text_hash` 를 DB 에서 싣는다.
  3. **★ 미수집 조문이 하나라도 있으면 `status:"error", reason:"law_text_unavailable"`** + 어느 `law_ref_id` 인지 나열.
     번들의 존재 이유가 "이 결정이 참조한 근거가 변조되지 않았음"의 증명인데 `text_hash` 가 null 이면
     해시할 사실이 없어 **번들이 빈 약속이 된다.** 조용히 null 을 해시하면 계층 1의 존재 이유가 무너진다(`11 §2`).
  4. `facts` = `build_facts` 결과 그대로(NULL 키는 애초에 없다).
  5. **`bundle_hash`**: `json.dumps(evidence_bundle, ensure_ascii=False, sort_keys=True, separators=(",",":"))`
     → `engine.text_hash()`. **키 정렬과 구분자를 고정**해야 같은 사실이 같은 해시를 낸다.
     이 규칙을 docstring 에 명시 — **Sprint 7 의 서명 검증이 같은 함수를 쓴다.**
  6. 이 도구는 **아무것도 저장하지 않는다.** `decisions` INSERT 는 Sprint 7 의 사람 전용 API (D10 태도 유지).
- **지켜야 할 결정**: D60 · D63 · D10 · D9
- **DoD** (⚠ 법령이 전부 `PENDING` 이므로 실 DB 에서 이 도구는 **설계상 항상 실패한다.**
  "성공 시 ok + 해시"는 이번 스프린트에 검증할 수 없다)
  1. **실패 경로 정확성** — 실 DB `AST-L3-CONV` 호출 → `status:"error", reason:"law_text_unavailable"` +
     `missing_law_refs` 가 인용 룰의 `law_refs` 합집합과 **정확히 일치**
  2. **성공 경로 + 해시 안정성(합성 픽스처)** — `MAINTQ_DB` 로 임시 DB 를 띄우고 `law_refs` 의
     `fetch_status='FETCHED'`·`text_hash`·`effective_from` 을 주입 → `status:"ok"` + `bundle_hash`.
     **같은 입력 2회 호출 해시 동일**
  3. **직렬화 안정성** — `facts` 키 삽입 순서만 다른 동일 내용 번들이 **같은 해시**를 낸다
  4. **부작용 없음** — 호출 전후 `decisions` 행 수 불변
  5. 인용 룰 0건(CLEAR 자산) → `laws`·`rules` 빈 배열 + 해시는 산출(빈 근거도 사실이다)
  - ②③④ 는 Stage 6 에서 `spikes/asset_tools_contract.py` 에 흡수(회귀 영속화) · `ruff check`

#### MQ-611 — S9 REST · 자산 조회 API

- **변경 파일**: `backend/routers/disposal.py`(신규) · `backend/services/disposal.py`(신규) ·
  `backend/routers/equipment.py`(수정) · `backend/main.py`(수정) · `spikes/disposal_api_contract.py`(신규)
- **인터페이스** (D71 승인 전제)
```
GET  /api/assets                               # 목록. line_id·status 필터
GET  /api/assets/{asset_id}                    # 상세 + 하위 equipment 목록
POST /api/assets/{asset_id}/disposal/precheck  # 판정 전용, 저장 없음
     body: {disposal_mode: "SALE"|"SCRAP"|"TRANSFER", disposal_date?: "YYYY-MM-DD"}
     200 → {verdict:"CONDITIONAL"|"CLEAR", preconditions:[…], checklist:[…]}
     409 → {verdict:"BLOCKED"|"HOLD", blockers:[…], holds:[…], insufficient:[…], resolve_options:[…], detail:"…"}
     404 → 자산 없음   422 → disposal_mode enum 위반   503 → rule_catalog_not_loaded
GET  /api/equipment  (수정)                     # 응답에 asset_id 추가 (nullable)
```
- **핵심 로직**
  1. `backend/services/disposal.py` 가 판정을 수행한다. **`mcp_server` 를 import 하지 않는다** (D15).
     `data.rules.engine` 은 양쪽이 공유해도 되는 데이터 계층이므로 backend 도 직접 import 한다 (**D73**).
  2. **권한 게이트를 걸지 않는다.** `require()` 를 호출하지 않는다 — 읽기 판정이고, 여기에 403 을 만들면
     "권한 위반 403 차단 100%" 지표에 법정 조건 미충족이 섞인다 (D38·`11 §3`).
  3. **409 vs 403 vs 422**: 권한=403(해당 없음) / 상태상 불가=409 / 요청 본문 검증=422.
     `backend/routers/po.py` 기존 패턴 그대로.
  4. `checklist`: PRECONDITION 룰들의 `resolve_options` 를 항목화. **각 항목에 `citations` 를 붙인다** —
     근거 없는 체크리스트 항목을 만들지 않는다.
  5. 응답 시각은 UTC ISO-8601 (D39, `services/po.iso_utc` 규약과 동일).
  6. **저장하지 않는다.** 응답에 `"note":"판정 결과이며 처분 요청이 생성되지 않았습니다. 확정은 서명으로만 이뤄집니다."`
- **⚠ 리뷰 필수 항목**: `GET /api/equipment` 에 `asset_id` 추가는 **작동 중인 API 계약 변경**(가산)이다.
  `spikes/api_contract.py` 가 이 응답의 키 집합을 단언하는지 **먼저 확인**하고, 단언한다면 spike 를 함께 갱신한다.
  가산이므로 깨지지 않아야 정상이지만, 확인 없이 넘기면 조용히 깨질 수 있는 종류다.
  프론트 `frontend/lib/mappers.tsx` 타입이 초과 키를 허용하는지 `tsc --noEmit` 로 확인(프론트 코드 변경 없이 통과해야 함).
- **엣지 케이스**: 없는 asset → 404 / `disposal_mode` 잘못 → 422 / 룰 카탈로그 0행 → **500 아니라 503** /
  `INSUFFICIENT_FACTS` 만 있는 자산 → 409(`verdict:"HOLD"`)
- **지켜야 할 결정**: **D71(승인 필요)** · **D73** · D38 · D15 · D39 · D62 · D68
- **DoD**
  - `uv run python spikes/disposal_api_contract.py` 통과 — `AST-L3-CONV`→409·blockers 2건 /
    `AST-L2-SPDL`→200·checklist 비어있지 않음 / `AST-L4-DUST`→409·`verdict:"HOLD"` / 없는 자산→404 /
    `disposal_mode:"GIFT"`→422 / **호출 전후 `decisions`·`flags` 행 수 불변**
  - `X-Role: technician` 으로도 200/409 (403 아님) 확인
  - `GET /api/equipment` 응답에 `asset_id` 존재, `INV-L1-01` 은 `null`
  - `uv run python spikes/api_contract.py` 통과(기존 건수 유지) · `ruff check` · `tsc --noEmit`

---

### Stage 6

#### MQ-612 — MCP 등록 · 도구 프로파일 · 프롬프트 확장 · trace 요약

- **변경 파일**: `mcp_server/server.py` · `backend/agent/prompts.py` · `backend/agent/mcp_client.py` ·
  `spikes/prompt_rules.py`(수정) · `spikes/asset_tools_contract.py`(신규)
- **선행**: MQ-604~610 전부

- **도구 프로파일 (D69)**
```python
# mcp_server/server.py
TOOLS_PROFILE = os.environ.get("MAINTQ_TOOLS_PROFILE", "core")   # core | full
if TOOLS_PROFILE not in ("core", "full"):
    raise SystemExit(f"MAINTQ_TOOLS_PROFILE 은 core|full 이어야 합니다: {TOOLS_PROFILE!r}")
```
  모듈 레벨 `if TOOLS_PROFILE == "full":` 안에 확장 7종의 `@mcp.tool` 데코레이터를 넣는다.
  `mcp_client` 가 `env={**os.environ}` 로 자식에 전달하므로 두 프로세스 값이 자동 일치.

- **★ 프롬프트는 env 를 읽지 않는다** (tool-builder 지적 반영)
```python
RULES: tuple[str, ...]       # 11개 — 개수·순서 고정 (기존 그대로, 지우지 않는다)
EXT_RULES: tuple[str, ...]   # 3개 — 규칙 12·13·14
_TOOL_MAP_CORE: str          # 7줄 (기존 그대로)
_TOOL_MAP_EXT:  str          # 7줄

def build_system_prompt(
    model=None, *, equipment_id=None, tool_names: Sequence[str] | None = None
) -> str:
    """tool_names 는 loop.py 가 `await client.list_tools()` 로 받은 실제 목록.
    None 이면 코어 7종으로 간주한다 — 프롬프트가 목록에 없는 도구 사용법을 지시할 수 없게
    **구조적으로** 막는다(env 를 두 곳에서 읽으면 어긋난다)."""
```
  `loop.py:262` 가 이미 `tools = await client.list_tools()` 를 갖고 있으므로 그 이름 목록을 그대로 넘긴다.

- **규칙 3개 추가** (각 규칙에 근거 D 태그 — 기존 관례):
  - **규칙 12 — 처분 판정 경계 (D59·D62).** 법령 조문의 정의·인용은 `check_disposal_blockers` 결과의
    `citations` 만 쓴다. 조문 번호·내용을 네가 적지 마라. `HOLD`·`INSUFFICIENT_FACTS` 를 "문제 없음"으로
    옮기지 마라 — 각각 "경계 구간이라 사람 검토가 필요하다", "확인되지 않은 사실이 있다"로 말한다.
  - **규칙 13 — 추정치는 추정치로 (D65).** `estimates[]` 에 나열된 필드는 단정적 금액으로 쓰지 마라.
    "추정 약 N원"으로 말하고 `disclaimer` 를 함께 전한다. 시장가·잔존가치를 네가 계산하지 마라.
  - **규칙 14 — 반복 고장이면 3지 판단보다 근본원인이 먼저 (D2·S3).** `assess_repair_value` 가
    `ROOT_CAUSE_FIRST` 를 반환하면 수리/교체/매각 선택지를 제시하지 마라. 기존 규칙 5(발주 보류)가 그대로 이어진다.

- **`/health` 는 실측을 싣는다**:
  `{"status":"ok","mcp":true,"tools": <len(await client.list_tools())>, "tools_profile": <env 값, 참고>}`.
  **`tools` 가 정본** — 프로파일은 자식 프로세스가 해석하므로 backend 의 env 값은 실제 등록 결과가 아니다.
  MCP 미기동이면 `tools: null`.

- **`server.py` 등록 시 주의**: 각 `@mcp.tool` 래퍼에서 **파라미터 타입을 좁히지 말 것.**
  `get_error_history` 의 `line_id: int | str | None` 주석(`server.py:100-102`)이 이유를 남겼다 —
  타입을 좁히면 스키마 검증이 예외를 던져 도구가 `status` 로 실패를 못 돌려준다(D9 위반).
  `asset_id`·`equipment_id`·`disposal_date` 는 전부 `str | None`, `repair_cost`·`amount` 는 `int | str` 로 넓게 받는다.

> 🔀 **병행 세션의 D76(커밋 `4dc6448`) 영향 — Stage 6 착수 전 재확인 필수.**
> 도구 결과가 프로즈 요약 대신 **원본 dict** 로 LLM 에 가고, `PRESERVE_FIELDS` 화이트리스트가
> **블랙리스트로 뒤집혔다**. `summarize_result` 는 살아 있으나 역할이 바뀌었다 —
> `loop.py:124` 가 이를 `_summary` 로 **trimmed dict 안에 넣어 LLM 입력에도 싣는다**(이전엔 trace·SSE 전용).
> 따라서 신규 7종 분기는 **화면 문자열이자 LLM 이 읽는 요약**이 된다. 더더욱 **결과에 있는 값만** 써야 한다.
> D76 ⓑ(`traces.tool_payload` 컬럼)는 **아직 미구현**이며 `data/seed.py` SCHEMA 를 건드리므로
> **MQ-601a 산출물과 충돌 가능** — Stage 6 착수 전 `git log` 로 진행 여부를 확인할 것.

- **`mcp_client.summarize_result` 7종 분기 추가** — 화면·`traces` 에 그대로 저장되므로 **결과에 있는 값만** 쓴다:
  `check_disposal_blockers` → `"BLOCKED · 차단 2건 (TAX-CREDIT-2Y, LIEN-CONSENT)"` /
  `verify_ownership` → `"PARTIAL · 확인 4 / 미확인 5"` / `get_maintenance_metrics` → `"MTBF 41일(달력) · 예방보전 33%"` /
  `assess_repair_value` → `"REPAIR_RECOMMENDED · 회수비 1.06 (추정)"` / `classify_expenditure` → `"HOLD · 전문가 확인 필요"` /
  `classify_part_criticality` → `"CRITICAL"` / `build_evidence_bundle` → `"번들 해시 sha256:9d1e…"`

- **⛔ `loop.py` 의 `_pages_from`·`_parts_from`(D54·D66)은 건드리지 않는다.** 신규 도구는 매뉴얼 페이지도
  부품 목록도 생산하지 않으므로 현재 구현이 빈 리스트를 싣는 게 정확하다. 손대면 인용률·부품 특정 판정이 오염된다.

- **엣지 케이스**: `MAINTQ_TOOLS_PROFILE` enum 밖 → `SystemExit`(폴백 금지) /
  `core` → `list_tools()` 7종, 프롬프트도 7종, **기존 회귀·평가가 완전히 이전과 동일** /
  `full` → 14종, `MAX_TOOL_CALLS_PER_TURN=8` **그대로**(상한을 올리지 않는다, `09_RUNTIME §2`)
- **지켜야 할 결정**: **D69(승인 필요)** · D9·D46 · D14·D22(이벤트 4종 고정) · D54·D66 · D40·D56
- **DoD**
  - `MAINTQ_TOOLS_PROFILE=core` 기동 → `/health` `tools: 7`, `spikes/sp2_mcp_roundtrip.py` **19건 통과**(기존과 동일)
  - `MAINTQ_TOOLS_PROFILE=full` 기동 → `/health` `tools: 14`, 신규 7종 전부 `description` 비어있지 않음
  - `uv run python spikes/prompt_rules.py` 통과 — **env 를 설정하지 않은 상태에서**
    `len(RULES)==11 and len(EXT_RULES)==3` 고정 검사(기존 52행 단언 **유지**) ·
    `build_system_prompt(tool_names=CORE_7)` → EXT 규칙·확장 도구명 **부재** ·
    `build_system_prompt(tool_names=ALL_14)` → EXT 규칙 3개 존재 + 각 D 태그 존재
  - `uv run python spikes/asset_tools_contract.py` 통과 — 도구 7종 × (정상/잘못된 입력/없는 대상)
    **전부 예외 없이 `status` 반환** · `verify_ownership` 이 `VERIFIED` 를 내지 않음 ·
    사실 부족이 `CLEAR` 가 아님 · `assess_repair_value` 에 `estimates` 존재 · **MQ-610 해시 안정성 픽스처 흡수**
  - **회귀 전량**: 기존 **303건**(273 + law_fetch 25 + agent_loop 5) + 신규 3스위트(`law_fetch_contract` **25** · `rules_db_load` · `disposal_api_contract` ·
    `asset_tools_contract`) → **303건(병행 세션 4dc6448 의 agent_loop +5 반영) 미만이면 실패 판정.** `ruff check` · `tsc --noEmit` · `next build`

#### MQ-613 — 계약 문서 정합

- **변경 파일**: `docs/04_MCP_TOOLS.md` · `docs/06_REPO_API.md` · `docs/11_ASSET_LIFECYCLE.md` ·
  `docs/12_MAINT_VALUE.md` · `docs/10_DECISIONS.md` · `docs/00_MVP_SCOPE.md` · `docs/07_BACKLOG.md` ·
  `docs/README.md` · `CLAUDE.md` · `TODO_직접할일.md` · **`data/data_list.md`**(신규 배정 — 아래 12번)
- ⛔ `docs/05_DB_SCHEMA.md` 는 MQ-601a 가 이미 갱신 — **손대지 않는다**(중복 편집 방지)
- **핵심 로직**
  1. `04_MCP_TOOLS` — 제목을 "읽기 6+쓰기 1 = 7종" → **"코어 7종 + 확장 7종(프로파일 게이트, D69)"**.
     신규 7종 입출력 계약을 §8~§14 로 추가. **각 도구 파일의 `DESCRIPTION` 상수를 그대로 인용**(두 벌 관리 금지).
  2. `06_REPO_API` — §1 레포 구조에 `mcp_server/tools/` 7파일·`backend/routers/disposal.py`·
     `backend/services/disposal.py` 추가. §2 에 `/api/assets` 3종 + **403/409/422/503 매핑표**(D71).
     `GET /api/equipment` 응답에 `asset_id` 명시.
  3. `11_ASSET_LIFECYCLE` — **D68 미반영분 해소**: §5 도구 시그니처 `equipment_id`→`asset_id`,
     §7 "equipment 확장" → **"assets 신규(법정 조건 사실은 자산에 붙는다)"** 로 수정하고 `equipment` 확장은
     `asset_id` 1개만. §5 출력 예시 `"equipment_id":"INV-L3-01"` → `"asset_id":"AST-L3-CONV"`.
     §8 F1 체크리스트를 **실제 상태로**(`LAW_API_KEY`→`LAW_API_OC`, 신청 미완료(사람),
     `fetch_from_api` 미구현(Sprint 7), `apply_fetch` 완료).
  4. `12_MAINT_VALUE` — §3 3지 판단 JSON 에 `asset_id` 추가, §9 `repair_records` 에 `downtime_hours` 추가,
     §2 MTBF 산식에 **D70 각주**(달력 기준·가동시간 원천 부재).
  5. `10_DECISIONS` — **D69~D77 은 이미 기입돼 있다**(D69~D74 Stage 1 착수 전 · D75 Stage 1 reviewer 반영 · D77 Stage 2 실측 반영)(승인 문안 그대로). MQ-613 은 **기입이 아니라 전파**를 담당한다 —
     특히 **D74(D72 supersede)** · **D75(계층 1 2단계 기록)** · **D77(룰 `required_facts` 정합)** 이
     `11`·`12`·`00_MVP_SCOPE`·`07_BACKLOG` 어디에도 아직 반영되지 않았다. **D77 은 `11 §3` 룰 5종 표의 근거 서술과 직결된다.**
  6. `00_MVP_SCOPE` — §범위 확장 표의 기능 7~12 에 **구현 상태 열** 추가(어느 부분이 Sprint 6/7인지).
     **완료 기준 5개는 손대지 않는다**(D67: 범위를 넓히는 것과 품질 기준을 느슨하게 하는 것은 다른 일).
  7. `07_BACKLOG` — P22~P27 진행 표시. **P28 은 ⓑ만 해소로 표시하고 ⓐⓒ 는 열어 둔다.**
     **P28 본문 오기 정정** — "`data/rules/README.md`·`11 §7` 이 SQLite 적재라고 쓴다"에서
     **`data/rules/README.md` 를 뺀다**(실제로 그 문장은 `11 §7` 261행에만 있다). P29 는 손대지 않는다.
  8. **D 범위 표기 4곳** (`CLAUDE.md`·`docs/README.md`·`.claude/agents/reviewer.md`·`docs/00_MVP_SCOPE.md`)
     → **`D1~D77`** (현재 전부 `D1~D68`). ⚠ 최종 D 번호는 커밋 시점에 `10_DECISIONS.md` 마지막 행으로 재확인할 것 —
     Stage 1 처럼 스테이지 도중 결정이 추가될 수 있다.
  9. **`CLAUDE.md` 회귀 스위트 목록을 실제와 맞춘다** — 현재 15개인데 `spikes/` 는 **16파일**
     (`eval_replay_guard.py` 누락). 신규 4종을 더해 **20개**로 갱신.
  10. **pytest 실행 커맨드 기록** — `CLAUDE.md`·`data/rules/README.md:19` 에
      `uv run --with pytest python -m pytest data/rules/test_rules.py -q`
      (현재 `uv run python -m pytest` 는 실행되지 않는다).
  11. **`TODO_직접할일.md`** — law.go.kr 활용신청·`.env` 기입(**Sprint 7 하드 선행**),
      `parts.part_class` 40종 감수 신규 등재, **`N=8` 기준내용연수 법령 대조** 신규 등재.
  12. **`data/data_list.md` 정정 (신규 배정)** — ⓐ `§6-1` 의 카테고리 표기 `환경설비` → **`환경  설비`**(공백 2칸,
      원본 바이트). 이 오기가 MQ-603 명세로 전파됐다 ⓑ `:115` "구현 남은 일 ① `LAW_API_KEY` → `LAW_API_OC` 개명"은
      **MQ-602L 에서 완료됐으므로** 완료 표시 ⓒ `A2`(취득원가 없어 잔가율 산출 불가)·`A7`(조달청 분모 조건부 유보)
      항목에 **D74 로 결론이 났음**을 링크. 이 파일은 지금까지 어느 태스크 소유도 아니어서 낡은 채 남아 있었다.
- **엣지 케이스**: D 번호가 사람 승인 과정에서 바뀜 → 코드 주석의 D 참조도 함께 정정
- **지켜야 할 결정**: D67(완료 기준 불변) · D68 · 신규 **D69~D77**
- **DoD**: `git grep -n "D1~D68\|D1~D73"` → **0건** (제외: `docs/sessions/`·`docs/sprints/` — 이력 문서) ·
  `git grep -n LAW_API_KEY` → `data/rules/fetch_laws.py` 폴백 1곳 외 **0건** (같은 제외 범위 적용) ·
  `git grep -n "equipment_id" docs/11_ASSET_LIFECYCLE.md docs/12_MAINT_VALUE.md` → 남은 건 전부 "인버터 단위" 문맥 ·
  04·06 문서의 시그니처를 실제 코드와 1:1 대조 · `ls spikes/*.py` 개수와 `CLAUDE.md` 목록 일치 · **코드 변경 0건**

---

## 스프린트 크기 판정

### 결론: **분할한다. Sprint 6 / Sprint 7.**

**왜 한 스프린트로 안 되는가 — 근거 4가지**

1. **공유 파일이 두 무리로 갈린다.** 읽기측은 `data/` + `mcp_server/tools/` 로 병렬이 잘 되지만,
   쓰기·서명측은 `backend/services/`·`backend/routers/po.py`·`frontend/components/queue/*` 5파일 +
   `mappers.tsx` 를 동시에 건드린다. 같은 스프린트에 넣으면 후반 스테이지가 사실상 전부 직렬이 되어 병렬의 이점이 사라진다.
2. **계층 1 수집 결과가 서명 설계를 바꾼다.** 법령 미수집 상태에서 `build_evidence_bundle` 은
   `law_text_unavailable` 로 떨어지고, 그 위에 얹는 서명(계층 3)은 **해시할 사실이 없는 빈 약속**이 된다.
   Sprint 6 에서 수집 성공/실패를 확정한 뒤 Sprint 7 의 서명을 설계하는 것이 블로커 회피 원칙에 맞다.
3. **승인 큐 공유는 기존 계약 변경이다.** `GET /api/po?state=pending` 이 발주서 전용이고 프론트
   `mappers.tsx` 가 `po_drafts` 형태를 전제한다. 여기에 처분서·수리 증빙을 얹는 건 신규 기능이 아니라
   **작동 중인 화면 B 의 계약 변경**이라, 신규 도구 7종과 같은 스테이지에서 검증하면 회귀 원인 분리가 안 된다.
4. **회귀 부담.** Sprint 6 만 해도 신규 4스위트 + `prompt_rules`·`test_rules`·`seed.verify` 갱신이다.

**분할 경계를 "읽기 / 쓰기"로 잡은 이유** — "F1+F2+F3(처분 라인 완결) / F4+12번"으로 자르는 대안은
Sprint 6 안에 프론트·서명·큐 계약이 들어와 위 1·3번 문제가 그대로 남고, `12_MAINT_VALUE` 의 읽기 도구
4종(전부 독립·병렬 가능)이 Sprint 7 로 밀려 병렬 효율이 나빠진다. **읽기/쓰기 경계는 파일 소유권 경계와 정확히 일치한다.**

### Sprint 7 윤곽 (확정은 다음 `/sprint`)

| Stage | 내용 |
|---|---|
| 1 | **법령 원문 실수집**(키 발급 후) — `fetch_from_api` 구현 · `MST` 조회 → `JO` 형식 실호출 확인 → 조문번호·제목 대조 |
| 2 | `generate_disposal_document`·`create_repair_record`(쓰기 2종, `po_drafts` 트리거 잠금 패턴을 `decisions`·`repair_records` 에 복제) · 서명 서비스(`bundle_hash` 검증·override 422) |
| 3 | 승인 큐 공유 계약 (`GET /api/approvals` 신설 vs `/api/po` 확장 — Stage 2 에서 결정) · 상태 전이 API |
| 4 | 프론트 — 큐 3종 렌더 · 처분서/수리증빙 상세 · 서명 UI · `requires_expert_review` 안내 |
| 5 | S10·S19 스모크 · 확장 시나리오 평가셋 |

---

## 사람 선행 / 승인 항목

### 🔴 스프린트 착수 전 (승인 필요)

- [x] ~~**D69~D73 승인**~~ — **2026-08-09 승인 완료**, `10_DECISIONS.md` 기입됨(Stage 1 착수 전).
      D69 는 기본 프로파일 **`core`** 로 확정
- [x] ~~**D74 승인**~~ — **2026-08-09 승인 완료.** D72 가 실측으로 반증돼 supersede (§MQ-603 개정 참조)
- [ ] **`N = 8`(제조업 기계장치 기준내용연수) 법령 원문 대조** — 잔가곡선 전체가 이 값에 걸려 있는데
      `법인세법 시행규칙` 별표 원문과 대조되지 않았다. `residual_curve.md §2-2` 에 미검증으로 표시돼 있다.
      law.go.kr 키 확보 시 **기준내용연수 별표를 함께 수집**해 재검증할 것

### 🔴 Sprint 7 하드 선행 (지금 시작해야 함)

- [ ] **law.go.kr OPEN API 활용신청 → `.env` 의 `LAW_API_OC` 에 신청 이메일 ID 앞부분 기입**
  - 현재 `.env` 에 키는 있으나 **값이 빈 문자열**이고 실호출이 `필수입력요소 검증에 실패` 로 떨어진다
  - 확인법: `https://www.law.go.kr/DRF/lawSearch.do?OC=<값>&target=law&type=JSON&query=조세특례제한법`
  - 이게 없으면 계층 1 이 영구히 `PENDING` 이고 **S10(서명·증빙)이 성립하지 않는다** — Sprint 7 의 유일한 외부 블로커

### 🟡 Sprint 6 중 (막지 않음, 병행)

- [ ] **`parts.part_class` 40종 감수** (신규) — `assess_repair_value` 3지 판단에 직접 영향.
      `related_parts` 와 같은 성격(D12). 미검수 상태로도 코드는 돌고, 시드가 매 실행 경고를 찍는다
- [ ] `related_parts` 사람 최종 승인 (기존, 미해소)
- [ ] `SAFETY_BASELINE`/`QUALIFIED_WORKER_NOTE` 문안 검수 (기존)
- [ ] 시드 부품명·가격 현실성 감수 (기존)
- [ ] `data/raw/IE5_..._200617 (1).pdf` 중복 사본 삭제 (기존)

---

실행: `/stage 1`


---

## Stage 1 완료 (2026-08-09)

**태스크**: MQ-602L · MQ-603 (병렬, 파일 교집합 0)

### MQ-602L — 법령 참조 등록 · `LAW_API_OC` 개명 · 수집 계약 회귀

- `data/rules/laws/KR-CITA-ENF-31.json`(신규) · `data/rules/fetch_laws.py` · `.env.example` ·
  `data/rules/README.md` · `spikes/law_fetch_contract.py`(신규 **25건**)
- **법제처 API 미호출 확인** — `data/rules/` 에 `requests|httpx|urllib|http.client` grep **0건**
- 부수 수확: 기존 `check_revisions()` 가 `pending_revisions/{id}.json` 으로 **이전 기록을 덮어쓰던 결함**
  발견·수정(타임스탬프+seq 파일명). D60 append-only 를 실제로는 안 지키고 있던 지점
- reviewer 지적 반영 → **D75 도출**(정체성 키 누락 중단 · `applied` 3상태)

### MQ-603 — 잔가곡선 (**D72 → D74 로 개정하며 재작업**)

- `data/build_residual_curve.py`·`data/extracted/residual_curve.json`(36행)·`data/analysis/residual_curve.md`
- **D72 가 실측으로 반증됨** — 산출 곡선이 5종 카테고리 전부 우상향. `카테고리2` 층화·동일 모델명 비교로도
  사라지지 않음(모델 내 상관 `|r| ≤ 0.17`, 단순 상관은 오히려 양수) → **호가는 연차가 아니라 기계 규격이 지배**
- **D74** 로 값 원천을 목업 공식(`residual(age) = max((1-r)**age, FLOOR)`, `r` 은 `N` 에서 유도)으로 교체.
  중진공 분석은 `residual_curve.md §4` 한계 실증으로 **보존**
- 표본 필드 4종 전부 `null` (목업에 표본은 없다) → MQ-601a DDL 을 nullable 로 정정

### 검증

- 회귀 **298건 / 18스위트** 전건 통과 (기준선 273 + `law_fetch_contract` 25). 감소 0
  > 🔀 커밋 직후 병행 세션의 `4dc6448` 이 `agent_loop_contract` 를 24→29 로 올려 **직전값은 303건**이 됐다.
  > Stage 2 는 그 위에서 시작한다.
- `ruff check` clean · `data/rules/test_rules.py` 19 passed · 정본 `laws/*.json` 7파일 md5 불변
- 프론트 무변경이라 `tsc --noEmit`·`next build` 생략
- reviewer: 1차 **FAIL**(블로커 B1 — D74 인용 수치가 산출물과 불일치) → 수정 후 2차 **PASS**(블로커 0)

### 기준선 정정

계획 수립 시 인용한 **257건(16스위트)은 오집계**였다(`eval_replay_guard` 16건 누락).
`sprint-5.md:554-577` 의 2026-08-08 실측 **273건·17스위트**가 정본이며, `sprint-6.md` 4곳을 정정했다.

### Stage 2 인계 사항

1. **`residual_curve` DDL 은 표본 필드 nullable** — 이미 §MQ-601a 에 반영됨. `NOT NULL` 로 두면 시드가 깨진다
2. **`assets.category` 에 쓸 값은 `residual_curve.json` 의 6종**(원본 바이트 그대로, `'환경  설비'` 공백 2칸 포함).
   `residual_curve.md` 의 연차 격자표가 시드 `acquired_at` 설계 입력이다
3. **곡선이 전 카테고리 동일값**이라 `assess_repair_value` 에서 카테고리는 판정에 영향을 주지 않는다
   (조인 키로만 존재). 데모에서 "카테고리별 잔가 차이"는 보여줄 수 없다
4. `/stage` 스킬의 회귀 명령에 있는 **`--today 2026-07-23` 은 쓰지 말 것** — 데이터는 `--today` 기준 상대일로
   생성되는데 검증 쿼리(`data/seed.py:644`)는 벽시계를 써서 시드 검사 ⑤ 가 위양성 FAIL 한다

### 이월 (Stage 1 reviewer 경고 — 커밋 차단 아님)

| ID | 내용 | 처리 시점 |
|---|---|---|
| N-4·N-5 | `applied` 에 **종결 상태 부재** — 기입 실패 확정 건이 큐에서 빠질 수 없다. README 의 "필터 축 = `requires_signature` / 처리 분기 축 = `applied`" 분리도 미흡 | Sprint 7 착수 전 |
| N-6 | `_write_law`·`_confirm_pending_revision` 이 **원자적 쓰기가 아니다**(truncate-then-write). 특히 confirm 이 스냅샷 파일을 재기입해 유일 복구원이 파손될 창이 남아 D75 (b) 선택 근거를 약화 → `tmp + os.replace` 로 | Sprint 7 착수 전 |
| N-7·N-8 | `pending_revisions` **열람 경로 없음**(`--pending` 부재). `check_revisions` 의 except 에 `OSError` 미포함 → 1건 실패가 전체 스캔 중단 | Sprint 7 |
| N-9 | `affected_rules` → `load_laws()` 가 `laws_dir` 주입을 무시하고 정본을 읽는다(읽기 전용이라 오염은 없음) | Sprint 7 |
| N-10 | `build_residual_curve.py` 자가검증 assert 가 표본 4종 중 2종만 검사 | Stage 5 전 |
| N-11 | `카테고리1` **전량 유일값 표가 stdout 에 없다**(md §4-1 뿐) → CSV 부재 시 확인 불가 | Stage 5 전 |
| N-12 | 곡선 카테고리 6종의 선정 근거가 **폐기된 표본 문턱**(`base_n≥30`)이다. `'식품관련'`(원본 3위 1,282건)이 빠져 D74 문언과 어긋난다. 전 카테고리 동일값이라 정보 손실은 0 | Stage 2 착수 시 함께 판단 |

---

## Stage 3 완료 (2026-08-09)

**태스크**: MQ-601b (단독) · **결정 신규**: D77(Stage 2 도출) · **D78** · **D79**

### 관문 통과 — 처분 판정 5종이 전부 재현된다

Stage 2 종료 시점엔 5종 중 3종만 나왔고 `CONDITIONAL`·`CLEAR` 는 **구조적으로 도달 불가**였다.

| 자산 | mode | verdict | 근거 |
|---|---|---|---|
| `AST-L3-CONV` | SALE | **BLOCKED** | blockers 2건 (`LIEN-CONSENT` 부활 + `TAX-CREDIT-2Y`) |
| `AST-L4-WRAP` | SALE | **HOLD** | 경계 23개월 |
| `AST-L4-DUST` | SALE | **INSUFFICIENT_FACTS** | D79 승격 |
| `AST-L2-SPDL` | SALE | **CONDITIONAL** | D77 수정 전 미도달 |
| `AST-L3-LIFT` | SALE / **SCRAP** | **CONDITIONAL** / **CLEAR** | D78 + 도메인 사실 |

**`CLEAR` 는 `SCRAP`·`TRANSFER` 에서만 나온다** — `VAT-INVOICE` 가 매각 precheck 을 정의상 최소
`CONDITIONAL` 로 만들기 때문이며, 이는 결함이 아니라 도메인 사실이다(D78 부수 확정).
이 대조를 **3중으로 고정**했다: pytest · 시드 ⑮(`DISPOSAL_MODE_CONTRAST`) · `spikes/rules_db_load ⑱⑲`.
"CLEAR 가 안 나온다"는 회귀도, **"SALE 인데 CLEAR 가 나온다"는 회귀도** 잡힌다.

### 도입된 개념 한 쌍 — 발화 가능성 / 해제 가능성

| 회귀 | 막는 것 | 수정 전 실패 확인 |
|---|---|---|
| **satisfiability** | 어떤 사실 조합으로도 `TRIGGERED` 될 수 없는 룰 | `LIEN-CONSENT` 1건 단독 실패 ✅ |
| **clearability** | 어떤 사실 조합으로도 `CLEAR` 될 수 없는 룰 | `INSURANCE-NOTIFY` 1건 단독 실패 ✅ |

둘 다 **고치기 전에 실패를 먼저 확인**했다 — 테스트가 실제로 무언가를 잡는다는 증명이다.
`_candidate_space` 가 **룰 파일에서 필드·연산자·경계를 읽어** 후보를 생성하므로 기대 조합이 하드코딩돼 있지 않다.

**`HOLD`·`INSUFFICIENT_FACTS` 를 해제로 세지 않는다** — 사실을 빼서 트리거를 피하는 건 해제가 아니라 **회피**이고,
그걸 성공으로 세면 D78 이 잡으려던 결함(있으면 TRIGGERED / 없으면 INSUFFICIENT)이 그대로 통과한다.
reviewer 판정: *"완화가 아니라 테스트를 강하게 만드는 방향. 이게 없으면 회귀가 D62 를 검사하면서 스스로 D62 를 위반한다."*

### `TAX-CREDIT-2Y` 파생 실패 — 검사가 아니라 구조로 닫았다

판독 불가한 날짜는 **원천 키 자체를 facts 에서 뺀다.** 그러면 "원천 2개가 있는데 파생이 없는" 상태가
**구성상 불가능**해진다. 결과는 `INSUFFICIENT_FACTS` + `missing_facts=['acquired_at']` 로 **범인이 찍힌다.**

기각한 대안 3가지: ⓐ 예외 → D9 위반이고 나머지 4룰의 정상 판정까지 버린다
ⓑ 원천은 남기고 파생만 건너뛴다 → `required_facts` 충족 + `lt` 가 False → **`CLEAR`**(추징 대상이 무표시 통과)
ⓒ 파생을 오늘로 메운다 → "모른다"가 "오늘 처분"이 된다

### `rule_version` 최종

`INSURANCE-NOTIFY` **3**(D78, trigger 개정) · `LIEN-CONSENT`·`SAFETY-INSPECTION`·`VAT-INVOICE` **2** ·
`TAX-CREDIT-2Y` **1 유지** — 판정 불변인 룰에 버전만 올리면 개정 신호로서 무의미해진다(D60 취지).

### 검증

- 회귀 **330건** — spikes 18스위트 **312**(기존 292 + `rules_db_load` 20) + seed **18**
- `pytest data/rules/test_rules.py` **41 passed** (19 → +22)
- `ruff` clean · `mcp_server/`·`backend/`·`frontend/` 참조 0건(기존 도구 7종 무영향)
- reviewer 1차 **FAIL**(블로커 1건 — MQ-604 계약 스케치가 D79 이전 상태) → **문서 2줄 수정 후 해소**

### Stage 4 인계 사항 (⚠ 공통 규약에 반영 완료)

1. 🔴 **`assets` 행을 판정기에 직접 넘기지 마라 — 반드시 `engine.build_facts()` 경유 (D62).**
   `evaluate_rule` 은 **키 존재**만 보므로 `dict(row)` 를 그대로 넘기면 **NULL 이 "값 있음"으로 읽혀 조용히 `CLEAR`** 가 된다.
   Stage 4 도구 5종이 전부 이 경로를 탄다
2. **`disposal_mode` 는 `engine.DISPOSAL_MODES` 를 단일 출처로 import 해 검증** — 오타 하나가 `CONDITIONAL` 을 `CLEAR` 로 만든다
3. **`engine` 은 예외를 던진다** — `RuleIntegrityError` 하나만 잡지 말고 광범위 포착 후 `status:"error"`
4. **⑮ 프로브 키가 `(asset_id, disposal_mode)` 튜플**이다. 도구도 같은 전제를 따라야 한다 —
   같은 자산에 mode 별로 다른 판정을 캐시하거나 섞으면 안 된다

### 이월 (Stage 3 reviewer 경고)

| 내용 | 처리 시점 |
|---|---|
| **DB 로더가 `trigger = NULL` 을 조용히 통과** — 파일 로더는 `KeyError` 를 내는데 DB 로더는 기본값 `None` 을 준다. 실 스키마는 `NOT NULL` 이라 막히지만 `LOOSE_DDL`(ERP 사본) 픽스처에서는 뚫리고, `RuleIntegrityError` 가 아니라 `_eval_trigger` 의 `TypeError` 로 **D61 이 막겠다던 지점보다 훨씬 뒤에서** 터진다 | Stage 4 전 |
| `INSURANCE-NOTIFY` 두 번째 분기(`risk_grade_changed`)가 **"죽은 게 아니라 뒤집혀" 있다** — F6 로 이 사실이 채워지면 `insured=false` 자산이 발화해 **증권 없는 자산에 통지 의무를 선언**한다. `all_of` 재구조화 필요(trigger 변경이라 새 결정 필요). `revision_note` 에 경고 기록 완료 | F5·F6 착수 시 |
| `SAFETY-INSPECTION.required_facts` 에 `disposal_mode` 잔존 — 트리거가 안 읽으므로 엄밀히 D77 원칙 ③ 대상. `build_facts` 가 항상 채워 실 경로 무해 | 다음 룰 정합 |
| ⑮ docstring 이 "DB 사본으로 로드한다"고 하는데 `verdict` 는 파일 로더에서 온다(버킷 4종만 DB 룰) | Stage 5 전 |
| `engine.py:389-392` 의 `assert` 2개는 `python -O` 에서 사라진다(실제 방어선은 원천 키 제거라 무해) | 참고 |

