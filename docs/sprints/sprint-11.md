# Sprint 11 — 기한·사고·위험 감시 계층 (백로그 P36 F5·F6, D102)

**상태**: 계획 확정(2026-08-18) — PM 계획 → tool-builder 현실성 평가(수정 필요 Y, 3건 반영) → 최종 확정.
**Stage 1·2·3·4 완료(2026-08-18)**. 다음은 `/stage 5`(MQ-1106, 회귀 스위트 신설 + 문서 전파 마감).

### Stage 1 완료 (2026-08-18)
**커밋**: `d7a5375` — `[M4] feat: Sprint 11 Stage 1 — 기한·사고·위험 감시 4테이블 신설 (MQ-1101, D102)`

#### MQ-1101
- 구현 파일: `data/seed.py`(SCHEMA §20~§23 신설, `seed_incidents`·`seed_ownership_checks`·`seed_risk_profile`,
  `verify()` ㉜~㉟ 4건) · `docs/05_DB_SCHEMA.md`(§20~§23 + 카운트 19절/20개→23절/24개) ·
  `docs/11_ASSET_LIFECYCLE.md`(§10-2 초안→확정, `equipment_id`→`asset_id`·`status`→`state` 정정 이력 기록)
- 회귀: seed 35(31+4) · sp2 20 · write_tool 30 · api_contract 28 · sp3 22 · asset_tools 49 ·
  disposal_api 26 · ownership_api 10 · rules_db_load 25 · db_concurrency 13 · bundle_integrity 25 ·
  pytest 46 · ruff clean — 전부 기존 건수 그대로, 회귀 없음. `sqlite_master` 테이블 20→24개.
- reviewer: **PASS** — D10·D68·D9·D62·liveness 앵커 전부 준수 확인(`ownership_checks` 시드를
  `verify_ownership` 실제 출력과 37/38항목 정적 대조, 나머지 1항목은 RNG 의존이라 실행 재현 권고만).
  경고 2건은 정보성(블로커 아님) — 반복 고장 패턴 1행 미재현 확인, `§10-2` 문구 잔재 정리 권고.

### Stage 2 완료 (2026-08-18)
**커밋**: `3694ed4` — `[M4] feat: Sprint 11 Stage 2 — track_deadlines·assess_risk_grade 산출 로직 (MQ-1102·1103)`

#### MQ-1102 · MQ-1103
- 구현 파일: `data/deadlines.py`(신규, `track_deadlines`) · `data/risk_grade.py`(신규, `risk_grade`)
- 회귀: seed 35 · sp2 20 · write_tool 30 · api_contract 28 · sp3 22 · rules_db_load 25 · asset_tools 49 ·
  disposal_api 26 · db_concurrency 13 · pytest 46 · ruff clean — 전부 기존 건수 그대로.
- 신규 모듈 재현 검증(eval-runner 독립 실행): `track_deadlines(con)` 기본 호출 0건(정상) ·
  `track_deadlines(con, window_days=500)` → `AST-L2-SPDL`/`UPCOMING`/`days_remaining=457` ·
  `risk_grade(con, building_id="BLD-C")` → `changed=true` · `BLD-A` → `changed=false`. 전부 기대값과 일치.
- **DoD 수치 정정**: 계획 문서가 `days_remaining=456`으로 적었던 것은 1일 오차 — 실제 날짜 연산(2026-08-18→
  2027-11-18)으로 457이 맞음을 확인, 코드 문제 아님. 위 MQ-1102 절 DoD도 정정 반영.
- reviewer: **PASS** — 위반 0건. `_months_between`을 `data/rules/engine.py`의 비공개 헬퍼와 동일 로직으로
  복제한 지점을 두 파일 직접 대조로 확인(갈림 없음), either-or 미등록 사유 3종 어휘가 명세 대안 표기와
  일치함을 확인.

### Stage 3 완료 (2026-08-18)
**커밋**: `a8abac2` — `[M4] feat: Sprint 11 Stage 3 — track_deadlines·assess_risk_grade MCP 도구 등록 (MQ-1104)`

#### MQ-1104
- 구현 파일: `mcp_server/tools/track_deadlines.py`(신규) · `mcp_server/tools/assess_risk_grade.py`(신규) ·
  `mcp_server/server.py`(수정, full 프로파일 등록) · `docs/04_MCP_TOOLS.md`(§17·§18 신설 + 헤더/공통설계원칙5
  갱신) · `docs/02_SCENARIOS.md`(S9·S18 문단에 참조 추가, 새 S번호 없음)
- 회귀: seed 35 · sp2 20 · write_tool 30 · api_contract 28 · sp3 22 · mcp_client_contract 15 ·
  agent_loop_contract 35 · pytest 46 · ruff clean — 전부 기존 건수 그대로. `full`=18종(코어7+확장11)·
  `core`=7종을 런타임+정적 카운트 이중 확인. `tools_profile_contract` ①만 예상된 FAIL(하드코딩 기대값
  갱신은 Stage 5/MQ-1106 배정, ②~⑦은 PASS) — 계획된 스테이지 경계, 회귀 아님.
- reviewer: **1차 FAIL → 수정 → 재검토 PASS**. FAIL 사유: §17·§18 문서가 `db_missing` 사유를 명시했는데
  코드는 `except Exception` 단일 계층이라 그 경로가 없어 문서-코드 불일치(체크리스트 4·6 위반). 수정:
  기존 확장 도구(`create_repair_record`·`build_evidence_bundle`·`generate_disposal_document`) 관례대로
  `except FileNotFoundError`를 `except Exception`보다 먼저 추가해 `db_missing`을 실제로 내도록 코드를
  문서에 맞춤(문서를 낮추지 않음). 재검토에서 예외 순서·반환 형식·diff 범위 전부 확인 후 PASS.

### Stage 4 완료 (2026-08-18)
**커밋**: `d59857a` — `[M4] feat: Sprint 11 Stage 4 — 기한·위험등급 REST 노출 (MQ-1105, D73)`

#### MQ-1105
- 구현 파일: `backend/services/asset_monitoring.py`(신규) · `backend/routers/asset_monitoring.py`(신규,
  `GET /api/deadlines`·`GET /api/buildings/{building_id}/risk-grade`·`GET /api/assets/{asset_id}/risk-grade`) ·
  `backend/main.py`(라우터 등록 1줄) · `docs/06_REPO_API.md`
- 회귀: seed 35 · sp2 20 · write_tool 30 · api_contract 28 · sp3 22 · asset_tools 49 · disposal_api 26 ·
  ownership_api 10 · approvals_contract 26 · pytest 46 · ruff clean — 전부 기존 건수 그대로.
  `tools_profile_contract` ①만 예상된 FAIL(Stage 5 배정), ②~⑦ PASS.
- **D73 핵심 DoD**: `MAINTQ_TOOLS_PROFILE` 미설정(core) 상태로 실서버 기동해 5경로 전부 200/404/422
  확인(eval-runner 독립 재현 + reviewer가 `require()` 미호출을 코드로 구조적 확인).
- reviewer: **PASS** — 위반 0건. `risk_grade` 모듈명/함수명 충돌 회피용 별칭(`risk_grade_data`) 필요성 확인,
  세 번째 `mode=ro` 헬퍼 미신설(`disposal.read_only` 재사용) 확인, `rule_catalog_not_loaded`→500 매핑이
  스펙·D50과 일치함을 확인(정보성 — verdict 우선순위 라우터의 503 패턴과는 다른 성격이라 블로커 아님).

## 0. 왜 지금 이 스프린트인가

Sprint 9(수리 증빙, P25)·Sprint 10(근거 번들·지출 분류 화면 + 수리 증빙 승인 큐 상세, P37·P38)이 완료되면서
`docs/00_MVP_SCOPE.md`의 MVP 완료 기준 — 핵심 기능 1~6 + D67로 열린 확장 기능 7~12 — 이 **전부 ✅ 달성**됐다
(2026-08-18 확인). 다음 범위를 정하며 백로그 **P36**(F5·F6 — 기한·사고·위험 감시 계층)을 검토했는데,
`docs/11_ASSET_LIFECYCLE.md §10-3`이 "셋 다 v2 다 — Sprint 7 에서 제외를 확정했다"고 명시해 둔 항목이었다.
`/sprint` 스킬의 "백로그 항목을 태스크로 승격하지 않는다" 원칙과 정면으로 부딪히는 지점이라, 먼저 사용자에게
확인하고 **D102**(`docs/10_DECISIONS.md`)를 새로 추가해 이 v2 제외를 의도적으로 뒤집었다 — D67이 11·12
문서를 열었던 것과 같은 절차다. **`detect_law_revision`(S17)만은 제외를 그대로 유지**한다(`02_SCENARIOS.md:83`이
확정한 별개 결정이라 D102가 다시 열지 않는다).

이 스프린트에 앞서 다음 문서가 이미 갱신됐다:
- `docs/10_DECISIONS.md` — **D102** 신설
- `docs/00_MVP_SCOPE.md` — "추가 기능" 표에 항목 **13**(기한 추적)·**14**(실사 보존·위험 프로파일) 신설, 🟡 Sprint 11 착수 예정
- `docs/11_ASSET_LIFECYCLE.md §10-3·§10-5` — v2 제외 문구를 D102 편입 반영으로 정정
- `docs/07_BACKLOG.md` — P36 행을 🟡 Sprint 11 예정으로 갱신

## 1. 이번 스프린트가 편입하는 것 / 안 하는 것

| 편입 | 제외 유지 |
|---|---|
| `deadlines`·`incidents`·`ownership_checks`·`risk_profile` 4테이블 | — |
| `track_deadlines`·`assess_risk_grade` 2도구(읽기 전용) | `detect_law_revision`(S17) — 별도 결정, D102가 다시 열지 않음 |

**절대 규칙 1과의 관계**: MCP 쓰기 도구는 여전히 `create_po_draft`·`generate_disposal_document`·
`create_repair_record` 3종뿐이다. 이는 곧 `deadlines`·`ownership_checks`에 **어떤 MCP 도구도 INSERT할 수
없다**는 뜻이다 — 이 두 테이블은 이번 스프린트에서 스키마+seed만 갖고, 실 쓰기 경로는 `flags`(Sprint 6)와
같은 이유로 미룬다.

## 2. 블로커 점검

MaintQ 블로커 체크리스트(`error_codes` 사람 승인·`related_parts` 검수·`ANTHROPIC_API_KEY`·임베딩 미결) —
**전부 해당 없음**. `track_deadlines`·`assess_risk_grade`는 둘 다 `assets`/`risk_profile`만 읽고 에러코드
룩업·RAG·에이전트 루프를 전혀 거치지 않는다.

## 3. 사전 조사 요약 (PM)

- `11_ASSET_LIFECYCLE.md §10-2`의 테이블 스키마는 명시적으로 **"초안"**이었다. 실측으로 정정한 지점 3곳:
  1. `incidents`·`ownership_checks`의 FK를 초안은 `equipment_id`로 적었으나, **D68**(처분·취득·자산가치
     판정 단위는 언제나 호스트 자산)과 어긋난다. `verify_ownership` 실측(`AST-L3-LIFT`: 9카테고리·38항목,
     `state`가 `VERIFIED`/`UNVERIFIED`이고 `evidence`/`limit`이 그 상태에 종속되는 either-or 구조)도 판정
     단위가 자산임을 보여준다. **`asset_id`로 정정**.
  2. `deadlines`는 초안이 `decision_id`만 FK로 뒀으나, `track_deadlines`의 존재 이유(결정이 생기기 전에
     미리 알림)는 자산 사실에서 계산돼야 한다. **`asset_id NOT NULL` + `decision_id` nullable로 정정**.
  3. 초안의 상태 컬럼명 `status`는 MCP 응답 봉투의 예약어(D9)와 겹친다 — 워크플로우류 상태 컬럼은 기존에
     전부 `state`(`decisions.state`·`repair_records.state`·`flags.state`)를 쓰므로 **`state`로 통일**.
- **시드 실측**: `assets.building_id`는 이미 `BLD-A~D` 4건이 채워져 있다 — `risk_profile` PK 4행은 신규
  계산 없이 바로 매핑된다.
- **시드 실측 함정 ①**: 현재 9자산은 전부 취득 후 24개월을 이미 경과했다 — `TAX-CREDIT-2Y` 경로는 기본
  호출에서 정직하게 0건이다(D62). 10번째 자산을 새로 추가하면 `assets 9행` 검증·`disposal_sign_contract`의
  9×3=27조합 등 광범위한 기존 회귀가 흔들리므로 하지 않는다. 대신 `data/deadlines.py`가 `today`를 주입
  가능하게 설계해(`data/hotspot_status.py`의 `today` 파라미터 선례) 회귀 테스트가 결정론적으로 검증한다.
- **시드 실측 함정 ②** (tool-builder 발견, 아래 §5에서 반영): `AST-L2-SPDL.inspection_valid_until`은 오늘
  기준 **456일** 남아 있어, `window_days` 기본값 180으로는 SAFETY-INSPECTION 경로도 기본 호출에서 0건이다.
- `04_MCP_TOOLS.md`는 §16까지 차 있으므로 신규 도구는 **§17**(`track_deadlines`)·**§18**(`assess_risk_grade`).
  `05_DB_SCHEMA.md`는 §19까지 차 있으므로 신규 테이블은 **§20~§23**.
- **시나리오 번호**: `TODO_직접할일.md:238-252`에 따르면 `S1~S29`가 전사적으로 이미 전부 배정돼 있다(`S19`
  충돌 건과 같은 사정). **새 S번호를 만들지 않는다** — `track_deadlines`는 기존 **S9**(처분 차단)의 사전
  경보로, `assess_risk_grade`는 기존 **S18**(중고 취득 검증)의 실사 보존 확장으로 문서에 명시한다.

## 4. 현실성 평가 (tool-builder)

DB에 직접 쿼리하고 `verify_ownership`을 실제로 호출해 PM 계획을 검증했다. 결론: **계획 수정 필요 — Y**
(경미, 3건). 검증 결과:

- D102·D68 원문, `assets` 컬럼(`tax_credit_applied`·`safety_inspection_target`·`inspection_valid_until`·
  `building_id`) 실존, `TAX-CREDIT-2Y.json`의 `review_band:[22,26]`, `hotspot_status`의 `today` 주입 선례,
  `verify_ownership(AST-L3-LIFT)` 9카테고리/38항목 실측, `sqlite_master` 20개 베이스라인, `maint_value.py`
  3단 구조 선례 — **전부 실측으로 확인, PM 주장과 일치**.
- **파일 충돌 없음** — Stage 간·Stage 내 전부 직접 대조 확인(`data/seed.py`는 Stage 1만, `mcp_server/tools/*`·
  `server.py`·`04_MCP_TOOLS.md §17·18`은 Stage 3만).
- **숨은 순서 의존성 없음** — MQ-1102·MQ-1103은 서로 다른 신규 파일이고 서로를 참조하지 않아 진짜 병렬 안전.
- **수정 필요 3건** (전부 아래 §5·§6 최종본에 반영 완료):
  1. **MQ-1102 고위험** — 기본 호출 데모로 `AST-L2-SPDL`(SAFETY-INSPECTION)을 들었으나 실제 잔여 456일이라
     기본 `window_days=180` 안에 안 들어옴 → DoD를 "기본 호출은 두 경로 모두 정직한 0건 확인 + 데모는
     `window_days=500` 명시 호출로 검증"으로 정정.
  2. **MQ-1104 누락** — `04_MCP_TOOLS.md`의 "공통 설계 원칙 5"(either-or 파라미터 목록, 기존 4종)에
     `assess_risk_grade`를 추가해 5종으로 갱신하는 작업이 범위에 없었음 → 추가.
  3. **MQ-1106 범위 확장** — `docs/README.md`·`CLAUDE.md`·`00_MVP_SCOPE.md:95`에 남는 "확장 9종/16종"
     표기가 갱신 대상에서 빠져 있었음 → MQ-1106 범위에 추가.
- 정보성(참고, 강제 아님): D68 인용문이 원문("처분·취득·자산가치")과 살짝 다른 단어("실사")를 썼던 지점 —
  결론(asset_id 정정)은 `verify_ownership` 실측으로 더 강하게 뒷받침되므로 계획은 그대로 두고, §6의 문서
  갱신 근거를 "D68 + verify_ownership 실제 출력"으로 이중 인용했다.

## 5. 스테이지 계획 (확정)

### Stage 1
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1101 | 4테이블 DDL + seed 데이터 + 자가검증 확장 | `data/seed.py`, `docs/05_DB_SCHEMA.md`, `docs/11_ASSET_LIFECYCLE.md §10-2` | — |

### Stage 2 (병렬)
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1102 | `track_deadlines` 산출 로직 | `data/deadlines.py`(신규) | MQ-1101 |
| MQ-1103 | `assess_risk_grade` 산출 로직 | `data/risk_grade.py`(신규) | MQ-1101 |

### Stage 3
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1104 | MCP 도구 등록 2종 + 계약 문서 | `mcp_server/tools/track_deadlines.py`(신규)·`assess_risk_grade.py`(신규), `mcp_server/server.py`, `docs/04_MCP_TOOLS.md §17·§18 + 공통설계원칙5`, `docs/02_SCENARIOS.md` | MQ-1102, MQ-1103 |

### Stage 4
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1105 | REST 노출 (D73 패턴) | `backend/services/asset_monitoring.py`(신규), `backend/routers/asset_monitoring.py`(신규), `backend/main.py`, `docs/06_REPO_API.md` | MQ-1104 |

### Stage 5
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1106 | 회귀 스위트 신설 + 프로파일 카운트 갱신 + 범위 문서 마감 | `spikes/deadline_risk_contract.py`(신규, 30번째), `spikes/tools_profile_contract.py`, `docs/00_MVP_SCOPE.md`, `docs/07_BACKLOG.md`, `docs/README.md`, `CLAUDE.md` | MQ-1105 |

### 스테이지 구성 근거

- **Stage 1 단독**: `data/seed.py`의 `SCHEMA`·시드 함수·`verify()`는 한 파일이다. 4테이블을 쪼개면 동시에
  같은 파일을 건드려 충돌한다. 이후 모든 스테이지가 이 스키마 위에서 동작하므로 최우선.
- **Stage 2 병렬**: `data/deadlines.py`·`data/risk_grade.py`는 서로 다른 신규 파일이고 서로를 참조하지
  않는다(위험등급 산식은 룰 카탈로그도 반복고장 상수도 안 씀). 둘 다 MQ-1101 산출물만 읽으므로 안전.
- **Stage 3 단독**: `mcp_server/server.py`는 도구 등록이 몰린 단일 파일 — 두 계산 모듈이 모두 끝난 뒤 한
  태스크로 묶어 등록한다.
- **Stage 4 단독**: REST 오류 매핑표는 MCP 도구의 `status`/`reason` 어휘가 확정된 뒤에야 정확히 쓸 수
  있다(Stage 3 의존). `backend/main.py` 라우터 등록도 단일 지점.
- **Stage 5 마지막**: 회귀 스위트는 DDL·도구·REST 전부가 있어야 전 계층을 동시에 잠글 수 있다. 문서
  마감(전사 카운트 갱신 포함)도 전체 검증 후에 해야 미완성 상태를 ✅/18종으로 먼저 표시하는 걸 막는다.
- 이월 태스크 없음(Sprint 10 완결). 블로커 우회 확인은 §2 참고.

## 6. 태스크별 상세 구현 명세

### MQ-1101 — 4테이블 DDL + seed 데이터 + 자가검증 확장
- **복무 시나리오**: S9(처분 사전 경보의 저장 기반) · S18(실사 보존의 저장 기반)
- **변경 파일**: `data/seed.py`(수정) · `docs/05_DB_SCHEMA.md`(수정, §20~§23 신설 + 테이블 카운트 19→23절,
  20→24개 갱신) · `docs/11_ASSET_LIFECYCLE.md`(수정, §10-2 스키마를 "확정"으로 갱신, 근거는 **D68 +
  `verify_ownership` 실제 출력** 이중 인용)

**DDL (§20 deadlines)**:
```sql
CREATE TABLE deadlines (
  deadline_id INTEGER PRIMARY KEY,
  asset_id    TEXT NOT NULL REFERENCES assets,     -- ★ §10-2 초안 정정: decision 이전 자산 사실에서 계산되므로 anchor
  decision_id TEXT REFERENCES decisions,           -- nullable — 특정 서명 결정에서 파생된 기한만 채움(미래 확장)
  type        TEXT NOT NULL,                       -- 'TAX-CREDIT-2Y' | 'SAFETY-INSPECTION'
  due_date    DATE NOT NULL,
  state       TEXT NOT NULL DEFAULT 'OPEN',        -- 'OPEN' | 'DISMISSED' — flags.state 관행 재사용 (컬럼명 'status' 아님, D9)
  reminder_sent_at DATETIME,
  CHECK (type IN ('TAX-CREDIT-2Y','SAFETY-INSPECTION')),
  CHECK (state IN ('OPEN','DISMISSED'))
);
```

**DDL (§21 incidents)**:
```sql
CREATE TABLE incidents (
  incident_id INTEGER PRIMARY KEY,
  asset_id    TEXT NOT NULL REFERENCES assets,     -- ★ 물리적 사고는 호스트 자산 단위 (D68)
  type        TEXT NOT NULL,                       -- 'COLLISION' | 'ALIGNMENT_LOSS' | 'FIRE' | 'FLOOD' | 'OTHER'
  occurred_at DATETIME NOT NULL,
  book_value_at_loss INTEGER,                      -- NULL 허용 — 그 시점 장부가를 모를 수 있음 (D62)
  description TEXT,
  recorded_by TEXT REFERENCES users,               -- 시드분은 NULL (error_history 관행)
  CHECK (type IN ('COLLISION','ALIGNMENT_LOSS','FIRE','FLOOD','OTHER'))
);
```

**DDL (§22 ownership_checks)**:
```sql
CREATE TABLE ownership_checks (
  check_id     INTEGER PRIMARY KEY,
  asset_id     TEXT NOT NULL REFERENCES assets,    -- ★ verify_ownership(§9)의 판정 단위와 일치 (D68)
  category     TEXT NOT NULL,                      -- verify_ownership 9카테고리 라벨 그대로
  check_item   TEXT NOT NULL,
  state        TEXT NOT NULL,                       -- 'VERIFIED' | 'UNVERIFIED'
  evidence_ref TEXT,                                -- VERIFIED 일 때만
  limit_note   TEXT,                                -- UNVERIFIED 일 때만
  checked_at   DATETIME NOT NULL,
  checked_by   TEXT REFERENCES users,
  CHECK (state IN ('VERIFIED','UNVERIFIED')),
  CHECK (evidence_ref IS NULL OR state = 'VERIFIED'),
  CHECK (limit_note IS NULL OR state = 'UNVERIFIED')
);
```

**DDL (§23 risk_profile)**:
```sql
CREATE TABLE risk_profile (
  building_id   TEXT PRIMARY KEY,                  -- assets.building_id 재사용. FK 없음(참조 테이블 없음, §11 주석과 같은 사유)
  fire_handling  TEXT,                              -- 'LOW'|'MEDIUM'|'HIGH'. NULL=모름
  hazmat_volume  TEXT,
  power_capacity TEXT,
  product_type   TEXT,                              -- 자유 서술, 점수화 안 함
  risk_grade     TEXT,                              -- 마지막 저장된 등급. NULL=미산출
  risk_grade_updated_at DATETIME,
  CHECK (fire_handling  IS NULL OR fire_handling  IN ('LOW','MEDIUM','HIGH')),
  CHECK (hazmat_volume  IS NULL OR hazmat_volume  IN ('LOW','MEDIUM','HIGH')),
  CHECK (power_capacity IS NULL OR power_capacity IN ('LOW','MEDIUM','HIGH')),
  CHECK (risk_grade     IS NULL OR risk_grade     IN ('LOW','MEDIUM','HIGH'))
);
```

**시드 데이터**:
- `deadlines`: **0행**(쓰기 경로 없음, 절대 규칙 1 — `flags`와 같은 이유).
- `incidents`: 2행 — `AST-L2-SPDL`/`COLLISION`(약 2년 전, `book_value_at_loss`는 그 시점 추정치,
  `description='지게차 충돌 — 주축 정렬 손상 의심'`), `AST-L4-WRAP`/`OTHER`. `recorded_by=NULL`.
- `ownership_checks`: `AST-L3-LIFT`의 `verify_ownership` 실제 출력(9카테고리·38항목 전량)을 그대로 옮겨
  심는다. `checked_at`≈1개월 전, `checked_by=NULL`.
- `risk_profile`: 4행 고정.

| building_id | fire_handling | hazmat_volume | power_capacity | 점수 | 산출 등급 | 저장 `risk_grade` | `changed` |
|---|---|---|---|---|---|---|---|
| BLD-A | LOW | LOW | MEDIUM | 4 | LOW | LOW | false |
| BLD-B | MEDIUM | LOW | HIGH | 6 | MEDIUM | MEDIUM | false |
| BLD-C | HIGH | MEDIUM | MEDIUM | 7 | **HIGH** | **LOW**(의도적 불일치) | **true** ★ 데모 케이스 |
| BLD-D | LOW | HIGH | LOW | 5 | MEDIUM | MEDIUM | false |

`risk_grade_updated_at`은 BLD-C만 오래된 날짜(≈14개월 전), 나머지는 최근(≈3개월 전).

**검증 함수(4건 추가)**: ㉜ `deadlines` CHECK 프로브(음성, 0행 유지 확인) · ㉝ `incidents` 2행/FK/enum ·
㉞ `ownership_checks` 행수(=`verify_ownership(AST-L3-LIFT)` 실측 항목 수와 일치)/either-or CHECK 음성 검사 ·
㉟ `risk_profile` 4행/`building_id` 집합 동적 대조(`SELECT DISTINCT building_id FROM assets`)/점수식 재계산 일치.

**지켜야 할 결정**: D68·D62·D9·D10·D65
**DoD**: `uv run python data/seed.py --with-error-codes` 전체 통과(seed 31→**35**건), `sqlite_master` 테이블
20→**24**개, `docs/05_DB_SCHEMA.md` §20~§23 존재.

---

### MQ-1102 — `track_deadlines` 산출 로직
- **복무 시나리오**: S9
- **변경 파일**: `data/deadlines.py`(신규)
- **인터페이스**:
```python
DEFAULT_WINDOW_DAYS = 180

def track_deadlines(
    con: sqlite3.Connection, *,
    asset_id: str | None = None,
    window_days: int | str = DEFAULT_WINDOW_DAYS,
    today: date | None = None,   # 주입 가능 — hotspot_status.hotspot_status 의 today 선례
) -> dict
```
출력 예:
```json
{
  "status": "ok", "evaluated_at": "2026-08-18", "window_days": 180,
  "items": [{
    "asset_id": "AST-L2-SPDL", "type": "SAFETY-INSPECTION",
    "law_refs": ["KR-OSHA-93", "KR-OSHA-ENR-126"],
    "due_date": "2027-11-18", "days_remaining": 456, "state": "UPCOMING",
    "message": "…", "resolve_options": ["재검사 일정 확보", "…"]
  }],
  "not_considered": [...], "disclaimer": "…"
}
```

**핵심 로직**:
1. `today = today or date.today()`.
2. **TAX-CREDIT-2Y 경로**: `assets.tax_credit_applied=1`인 행 스캔. `due_date = acquired_at + 24개월`.
   `data.rules.engine.load_rules(engine.load_laws())`로 `review_band`를 하드코딩 없이 로드(D101 태도).
   `months_since_acquisition`으로 판정: `>= review_band[1](26)`이면 제외(정직한 0건, D62) ·
   `review_band[0] <= months_since < review_band[1]`이면 `IN_REVIEW_BAND` ·
   `months_since < review_band[0]` and 잔여일 `<= window_days`이면 `UPCOMING` · 그 외 제외.
3. **SAFETY-INSPECTION 경로**: `assets.safety_inspection_target=1 AND inspection_valid_until IS NOT NULL`인
   행 스캔. `due_date < today`면 `OVERDUE`(항상 포함 — 만료 후가 더 위험하므로 window 무관) ·
   잔여일 `<= window_days`면 `UPCOMING` · 그 외 제외.
4. `asset_id` 필터 시 두 경로 모두 그 자산만.
5. `days_remaining` 오름차순 정렬(OVERDUE는 음수라 최상단).
6. NULL 컬럼은 건너뛰고 `not_considered`에 사유 기록(D62).

**엣지 케이스**: 미존재 `asset_id`→`not_found`/`unknown_asset`. `window_days` 음수·비정수→`error`/
`invalid_input`. 룰 파일 미적재→`error`/`rule_catalog_not_loaded`(D50 어휘).
**지켜야 할 결정**: D101·D73·D62·D9·D50

**DoD (실측 반영 정정)**:
- **기본 호출**(`window_days=180`, `today` 미주입): TAX-CREDIT-2Y 경로 0건(전 자산 24개월 초과) +
  SAFETY-INSPECTION 경로도 0건(`AST-L2-SPDL` 잔여 456일 > 180일) — **두 경로 모두 정확히 0건임을 확인하는
  것 자체가 DoD**(정직한 실패 없음, D62). 이 결과를 실패로 취급하지 말 것.
- **SAFETY-INSPECTION 데모**: `track_deadlines(con, window_days=500)` 명시 호출 → `AST-L2-SPDL` 1건,
  `state="UPCOMING"`, `days_remaining=457`(계획 수립 시 456으로 적었던 것은 1일 오차 — 2026-08-18→
  2027-11-18 실제 날짜 연산 재검증으로 457이 맞음을 확인, 코드가 아니라 문서 쪽 오류였다).
- **TAX-CREDIT-2Y 데모**: `today=AST-L3-CONV.acquired_at + 23개월` 주입 → `state="IN_REVIEW_BAND"` 재현.

---

### MQ-1103 — `assess_risk_grade` 산출 로직
- **복무 시나리오**: S18
- **변경 파일**: `data/risk_grade.py`(신규)
- **인터페이스**:
```python
GRADE_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
GRADE_SCALE = ("LOW", "MEDIUM", "HIGH")

def risk_grade(con: sqlite3.Connection, *, building_id: str | None = None, asset_id: str | None = None) -> dict
```
출력 예:
```json
{
  "status": "ok", "building_id": "BLD-C",
  "facts": {"fire_handling": "HIGH", "hazmat_volume": "MEDIUM", "power_capacity": "MEDIUM", "product_type": "…"},
  "current_grade": "HIGH", "stored_grade": "LOW", "stored_grade_updated_at": "2025-06-18",
  "changed": true, "grade_scale": ["LOW", "MEDIUM", "HIGH"],
  "rationale": "화기 취급 HIGH·위험물 보관량 MEDIUM·수전용량 MEDIUM → 점수 7 → HIGH",
  "not_considered": [...], "disclaimer": "이 등급은 통상 기준 목업 산식이다. 실제 화재·환경 규제상 위험평가를 대체하지 않는다."
}
```

**핵심 로직**:
1. `building_id`·`asset_id` **either-or**(D80 예외 패턴). `asset_id`면 `assets.building_id`로 해석.
2. `risk_profile` SELECT — 없으면 `not_found`/`unknown_building`(또는 `unknown_asset`/`no_building`).
3. 3속성 중 하나라도 NULL이면 `current_grade=null` + `not_considered`(추측 금지, D62).
4. 셋 다 있으면 `GRADE_ORDER` 합산 → `<=4 LOW / 5~6 MEDIUM / >=7 HIGH`(이 모듈의 정본 상수).
5. `changed = current_grade is not None and current_grade != stored_grade`. `stored_grade` NULL이면
   `changed=false` + "최초 산출" 명시.
6. **아무것도 쓰지 않는다** — `risk_profile.risk_grade` UPDATE 경로 자체가 없음(절대 규칙 1, `risk_profile`은
   3종 쓰기 도구 밖).

**엣지 케이스**: `building_id`·`asset_id` 둘 다 없거나 둘 다 있으면 `error`/`invalid_input`.
**지켜야 할 결정**: D101·D65·D62·D10
**DoD**: `risk_grade(con, building_id="BLD-C")`→`changed=true`. `building_id="BLD-A"`→`changed=false`.
`asset_id="AST-L3-CONV"`→`BLD-C`로 해석돼 동일 결과.

---

### MQ-1104 — MCP 도구 등록 2종 + 계약 문서
- **복무 시나리오**: S9 · S18
- **변경 파일**: `mcp_server/tools/track_deadlines.py`(신규) · `assess_risk_grade.py`(신규) ·
  `mcp_server/server.py`(수정) · `docs/04_MCP_TOOLS.md`(수정, §17·§18 신설 + 헤더 "확장 9종"→"확장 11종"[총
  16→18종] + 시나리오 매핑 표에 S9·S18 행 추가 + **공통 설계 원칙 5의 either-or 파라미터 목록을
  `check_disposal_blockers`·`verify_ownership`·`get_maintenance_metrics`·`build_evidence_bundle` 4종 →
  `assess_risk_grade` 추가한 5종으로 갱신**) · `docs/02_SCENARIOS.md`(수정, S9·S18 문단에 도구 참조 추가,
  새 S번호 안 만듦)

**인터페이스**:
```python
# mcp_server/tools/track_deadlines.py — classify_part_criticality.py 와 같은 얇은 래퍼
def track_deadlines(asset_id: str | None = None, window_days: int | str = DEFAULT_WINDOW_DAYS) -> dict:
    try:
        with read_only() as con:
            return deadlines.track_deadlines(con, asset_id=asset_id, window_days=window_days)
    except Exception as e:  # noqa: BLE001 — D9
        return {"status": "error", "reason": "db_error", "message": str(e)}
```
```python
# mcp_server/tools/assess_risk_grade.py — 동일 패턴
def assess_risk_grade(building_id: str | None = None, asset_id: str | None = None) -> dict:
    try:
        with read_only() as con:
            return risk_grade.risk_grade(con, building_id=building_id, asset_id=asset_id)
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "reason": "db_error", "message": str(e)}
```
`server.py` 등록은 기존 `if TOOLS_PROFILE == "full":` 블록 안, `create_repair_record` 다음. 파라미터 타입은
넓게(`window_days: int | str`) — D80 좁히기 금지.

**핵심 로직**: 로직은 MQ-1102·MQ-1103이 이미 끝냈다. 이 태스크는 커넥션 수명(`read_only()`)·예외→status
변환·`server.py` 등록·문서 갱신(either-or 5종화 포함) 네 가지만.
**지켜야 할 결정**: D9·D80·D69·D15(D73으로 `data.deadlines`/`data.risk_grade` import 허용)
**DoD**: `full` 프로파일 기동 시 `list_tools()`에 두 도구 존재(총 18종=코어7+확장11). `core`(미설정) 기동 시
미등록. `04_MCP_TOOLS.md` 헤더 "확장 11종=총 18종", 공통 설계 원칙 5가 "5종".

---

### MQ-1105 — REST 노출 (D73 패턴)
- **복무 시나리오**: S9 · S18 (화면은 이번 범위 밖 — 명시적 컷, §7 참고)
- **변경 파일**: `backend/services/asset_monitoring.py`(신규) · `backend/routers/asset_monitoring.py`(신규) ·
  `backend/main.py`(수정, `include_router()` 1줄) · `docs/06_REPO_API.md`(수정)

**인터페이스**:
```
GET /api/deadlines?asset_id=&window_days=            → track_deadlines 상당
GET /api/buildings/{building_id}/risk-grade          → assess_risk_grade 상당
GET /api/assets/{asset_id}/risk-grade                → assess_risk_grade 상당 (asset_id 해석 편의)
```
```python
# backend/services/asset_monitoring.py — maint_value.py 와 같은 얇은 어댑터
def deadlines(*, asset_id=None, window_days=None, db_path=None) -> dict: ...
def risk_grade(*, building_id=None, asset_id=None, db_path=None) -> dict: ...
```
둘 다 `backend/services/disposal.read_only` 재사용(세 번째 `mode=ro` 헬퍼를 만들지 않는다).

**핵심 로직**: `maint_value.py`/`routers/maint_value.py`와 같은 3단 구조(서비스가 커넥션 열고 위임 → 예외는
`db_missing`/`db_error`/`internal_error` → 라우터가 HTTP 매핑: `ok`→200, `not_found`→404,
`invalid_input`→422, 그 외 `error`→500). **역할 게이트 없음**(읽기 판정). `core` 프로파일에서도 동작해야
함(D73 핵심 — MCP 프로세스를 거치지 않고 `data.deadlines`/`data.risk_grade`를 직접 호출).
**지켜야 할 결정**: D73·D101·D38·D71
**DoD**: `MAINTQ_TOOLS_PROFILE` 미설정 상태로 두 REST 경로 200(또는 정의된 4xx) 확인.

---

### MQ-1106 — 회귀 스위트 신설 + 프로파일 카운트 갱신 + 범위 문서 마감
- **복무 시나리오**: S9 · S18
- **변경 파일**: `spikes/deadline_risk_contract.py`(신규, **30번째**) · `spikes/tools_profile_contract.py`(수정,
  9→11·16→18) · `docs/00_MVP_SCOPE.md`(수정, 항목 13·14 🟡→✅, **95행** "확장 9종(§8~§16)"→"확장
  11종(§8~§18)", 테이블 개수 19개→23개) · `docs/07_BACKLOG.md`(수정, P36 "✅ 완료(Sprint 11)") ·
  `docs/README.md`(수정, **11행**·**59행**의 "확장 9종"→"확장 11종", 도구명 나열에 신규 2종 추가) ·
  `CLAUDE.md`(수정, **14행**·**43행**의 "확장 9종 §8~§16"→"확장 11종 §8~§18")

**검증 항목**:
1. DDL 무결성 — `deadlines`(type enum 밖 거부)·`incidents`(FK 위반 거부)·`ownership_checks`(either-or CHECK
   양성+음성)·`risk_profile`(risk_grade enum 밖 거부).
2. `track_deadlines` — `today` 주입으로 `IN_REVIEW_BAND`·`UPCOMING`·`OVERDUE`·제외 4상태 재현 + **기본
   호출이 정확히 0건**임을 확인하는 케이스(MQ-1102 DoD를 회귀로 고정) + `window_days` 경계값.
3. `assess_risk_grade` — BLD-C `changed=true`, BLD-A `changed=false`, 미등록 building_id `not_found`.
4. 프로파일 게이트 양방향(`core` 미등록/`full` 등록).
5. REST 오류 매핑 — `core` 프로파일 실 서버로 200/4xx 확인(D73 고정).
6. **liveness 앵커**(CLAUDE.md 경고 반영) — "MCP 쓰기 경로 없음" 음성 검사는 양성 축(스캔 대상 파일 수 > 0)과
   함께 detail에 실측값 병기.

**지켜야 할 결정**: CLAUDE.md "부재 검사엔 liveness 앵커" · D88
**DoD**: `deadline_risk_contract.py` PASS · 전체 29→**30**스위트(`ls spikes/*.py`와 개수 일치) · 실패 스위트는
단독 재실행으로 재확인 · `pytest data/rules/test_rules.py` PASS(룰 카탈로그 무변경 확인) · `ruff check` 통과 ·
`grep -rn "확장 9종\|총 16종" docs/ CLAUDE.md` 결과 **0건**.

## 7. 이번 스프린트가 명시적으로 컷한 것

- **UI 노출 없음** — `track_deadlines`/`assess_risk_grade`를 보여주는 화면(기한 임박 배지, 건물별 위험등급
  대시보드 등)은 D102·MVP_SCOPE 항목 13·14 어디에도 커밋돼 있지 않다. Sprint 12+ 백로그 후보로 남긴다.
- **`incidents`의 `assess_repair_value` 연동 없음** — `§10-4`의 "감점 신호를 완성한다" 서술은 저장 자리
  확보까지만 이번 범위다. 잔가·수리가치 판정 로직 변경은 별도 결정 없이는 손대지 않는다.
- **`deadlines`의 실 쓰기 경로 없음** — 절대 규칙 1이 원천 차단(§1 참고).
- **`detect_law_revision`/S17 미포함** — D102가 명시적으로 다시 열지 않은 대상.

## 참고 파일 경로

`docs/11_ASSET_LIFECYCLE.md` · `docs/10_DECISIONS.md`(D68·D69·D73·D80·D88·D101·D102) ·
`docs/00_MVP_SCOPE.md` · `docs/04_MCP_TOOLS.md` · `docs/05_DB_SCHEMA.md` · `docs/06_REPO_API.md` ·
`docs/07_BACKLOG.md`(P36) · `docs/02_SCENARIOS.md` · `TODO_직접할일.md` · `data/seed.py` ·
`data/ownership.py` · `data/maint_value.py` · `data/hotspot_status.py` · `data/rules/engine.py` ·
`mcp_server/server.py` · `mcp_server/tools/check_disposal_blockers.py` ·
`mcp_server/tools/classify_part_criticality.py` · `backend/routers/maint_value.py` ·
`backend/services/maint_value.py` · `docs/README.md` · `CLAUDE.md`

---

실행: `/stage 1`
