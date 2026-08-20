# MaintQ — MVP 필수 구현 범위

> 설비 진단부터 부품 발주까지 — 제조 현장 AI 보전 에이전트.
> **도구 오케스트레이션**을 증명하는 프로젝트. (외부 시스템 연결 없이 단독 완결)

핵심 흐름: **에러코드 진단 → 부품 특정 → 재고/견적 → 발주서 초안 → 팀장 승인**

**이 문서는 "무엇을 반드시 만드는가"의 목록이다.** 입출력 계약·DDL·시퀀스 같은 상세는 전부 `01~10`에 있고 여기서 복제하지 않는다 — 두 벌 관리를 피하기 위해서다. 항목마다 상세 문서를 가리킨다.

---

## 1. 에러코드 진단 (룩업 + RAG 이원화)

- **코드 정의는 정확 룩업** (`lookup_error_code`) — 에러코드→의미를 결정론적으로 반환
- **점검 절차는 RAG** (`rag_search_manual`) — LS일렉트릭 공개 매뉴얼(iG5A·S100) 기반
- **모든 답변에 근거 페이지 인용 필수** — 환각 방지의 핵심
- 문제 성격별 이원화(정의=룩업, 절차=검색)가 설계 포인트

→ 상세: `04_MCP_TOOLS §1·§2`, 근거: **D1**
→ 인용 페이지는 저장·검증이 PDF 물리 페이지, 표시는 인쇄 페이지 우선 + PDF 병기 (**D26·D32**)

## 2. 부품 특정 → 재고/견적

- `search_inventory` — 재고·안전재고·**단종 여부** 조회
- `find_alternative_parts` — **재고 0 또는 단종**이면 호환 대체품 분기 (`compat_confirmed=false`는 제안 금지)
- `get_supplier_quotes` — 공급사 리드타임·단가·MOQ 조회 → 2개 이상이면 비교 제시, 선택은 사용자
- 진단 결과에서 부품을 특정하는 연결고리는 `error_codes.related_parts` — LLM 추측이 아니라 데이터

→ 상세: `04_MCP_TOOLS §4·§5·§6`, `05_DB_SCHEMA §1·§4~7`
→ 근거: **D12**(related_parts), **D20**(discontinued), **D28**(part_name 조회 시 model 필터)
→ 경계: 공급사 **비교 제시**는 MVP / 다운타임 비용 기반 **추천**은 백로그 P2

## 3. 발주서 초안 + 승인 워크플로우 (human-in-the-loop)

- `create_po_draft` — **쓰기 전용 도구, draft만 생성**. 도구에 UPDATE 권한 자체를 주지 않음
- 확정은 **팀장 승인 큐에서만**. 정비사 approve 호출 → **403**
- 상태 전이: `draft ──submit(정비사)──▶ pending ──approve/reject(팀장)──▶ approved/rejected`

**발주서 필수 필드** (전체 DDL은 `05_DB_SCHEMA §8`):

| 필드 | 성격 |
|---|---|
| `po_id` `part_no` `qty` `supplier_id` | 발주 본체 |
| `unit_price` | **도구 파라미터 아님** — `supplier_parts`에서 서버가 조회한 스냅샷 (D31) |
| `model` + `error_code` | 발주를 유발한 에러코드. 대문자 canonical 2~4자, `error_codes` FK 검증. **NULL 허용** — S2는 진단 없이 진입 (D33) |
| `reason` | 승인자가 3초 안에 읽는 **한 줄 요약** (D5) |
| `evidence` (JSON) | **어떤 현상을 보고 고장으로 판단했는지** — `symptoms`(관찰 현상) / `basis`(근거 도구 결과) / `notes`(비고·기타 상황) (D34) |
| `state` `urgency` | 워크플로우 |
| `requested_by` `decided_by` | **도구 파라미터 아님** — `X-User` 헤더에서 서버 주입 (D23). 반려도 기록해야 하므로 `approved_by`가 아닌 `decided_by` |
| `session_id` | 화면 B의 "실행 로그 보기" 링크 키 (D21) |

**MOQ 미달 수량은 자동 상향하지 않고 거부한다** (D31) — 사람 승인 없이 발주 금액을 키우지 않기 위해서.

→ 근거: **D10**(draft만), **D18**(승인은 채팅 밖 큐), **D23·D31·D33·D34**
→ 경계: 승인 **워크플로우**는 MVP / 팀장 **알림**은 P3, 불변 **감사 로그**는 P5

## 4. 반복 고장 감지 ★

- `get_error_history` — 동일 에러 **30일 내 3회** 감지 (`REPEAT_WINDOW_DAYS` / `REPEAT_THRESHOLD`)
- `repeated=true`면 단순 조치 대신 **근본원인 점검 모드**로 전환, **발주는 원인 확정까지 보류**
  — 발주 카드 자리에 `po_card` block 의 **variant: `hold`** 가 온다 (D35). 발주 카드가 아니다
- 이력 적재는 `POST /api/equipment/{id}/errors` — **정비사의 명시적 액션만**. 채팅 진입으로 자동 기록하지 않는다

> 자동 기록하면 `count`가 실제 고장 횟수가 아니라 **질문 횟수**가 되어, 같은 에러를 세 번 물어본 것만으로 근본원인 모드가 잘못 켜진다.

→ 상세: `02_SCENARIOS S3`, `04_MCP_TOOLS §3`, `06_REPO_API §2.3`
→ 근거: **D2**(확정 기능 ①), **D29**

## 5. 안전 가드레일 ★

- 위험 작업(활선 측정, 콘덴서 방전 등) 언급 시 **매뉴얼 근거와 함께 안전 경고 필수 삽입**
- 안전 경고는 채팅 텍스트가 아니라 **`block` 이벤트(type: safety)** — 스트리밍 중간 삽입이 가능해야 위험 절차 서술보다 **먼저/함께** 도착한다
- 방전 대기 기준값은 **"10분 이상"** (매뉴얼 명시값, 사람 승인 완료). 축소 표기는 실패 판정
- **매뉴얼 근거 없는 안전 문구는 생성 금지** — `safety-guardrail` 스킬 규칙

→ 근거: **D2**(확정 기능 ②), **D22**(block 이벤트)

## 6. 실행 trace 시각화 (시그니처 화면)

- 에이전트가 **어떤 도구를 왜 호출했는지** 실시간 타임라인
- SSE 이벤트 **4종 고정**: `token` / `tool_call` / `tool_result` / `block`
- `tool_call`은 도구 호출 **직전** 발행 (실행 중 상태를 보여주기 위해)
- 모든 `tool_call`/`tool_result`/`block`은 발행과 **동시에 `traces` 테이블에 저장**

> **trace는 별도 단계가 아니라 에이전트 루프와 같이 나오는 것이다.** 평가의 판정 소스(부품 특정 정확률·인용률·시퀀스 판정)가 전부 `traces` 테이블이므로, trace를 뒤로 미루면 평가 하네스를 돌릴 수 없다.

→ 상세: `06_REPO_API §2.1`, `09_RUNTIME §1`
→ 근거: **D14**(같은 채널 다른 이벤트), **D21**(영속화), **D22**(block), **A1·A5**

---

## 인프라 · 구조 (필수)

- **MCP 서버 ↔ 백엔드 프로세스 분리** — 목업 DB를 실제 ERP로 교체 시 MCP 서버만 교체 (**D15**). `data/`(매뉴얼·시드·룰 카탈로그)는 두 프로세스가 공유해도 되는 **데이터 계층**이다 (**D73**)
- **MCP 도구 코어 7종** = 읽기 6 + 쓰기 1 (위 기능들에 매핑, `04_MCP_TOOLS §1~§7`) **+ 확장 11종**(읽기 9 + **쓰기 2**, `§8~§18`, 프로파일 게이트 **D69**)
  - ⚠ **쓰기 도구는 3종이다** — `create_po_draft`(§7) · `generate_disposal_document`(§15, Sprint 7 신설) ·
    `create_repair_record`(§16, Sprint 9 신설, D98). 셋 다 draft INSERT 만 하고 UPDATE 권한이 없다 (D10·D81·D98)
- **SQLite 목업 DB** (**23절·실제 테이블 24개** — 코어 11 + 확장 7 + A2A 1(`partner_links`, Sprint 8) +
  UI목업 1(`part_lifecycle_mock`, Sprint 10) + F5·F6 4(`deadlines`·`incidents`·`ownership_checks`·
  `risk_profile`, Sprint 11, D102). 실측: `data/seed.py` 의 `CREATE TABLE` **24개**) + 벡터스토어(매뉴얼) +
  `seed.py`(시드 케이스 7종, 자가검증 **29건**) (`05_DB_SCHEMA`)
- **UI 2종**: 정비사 진단 콘솔(화면 A) / 팀장 승인 큐(화면 B) (`03_WIREFRAME`)
- **환경**: uv + venv, Docker는 MVP 제외 (**D27**)

## 시나리오 (도구 오케스트레이션 4패턴)

| # | 시나리오 | 패턴 | 분기 트리거 |
|---|---|---|---|
| S1 | 진단→재고→발주 풀 파이프라인 | 순차 실행 | — |
| S2 | **재고 0 또는 단종** → 대체품 → 비교 | 조건 분기 | `qty==0 \|\| discontinued` / `status:empty` |
| S3 | 반복 고장 → 근본원인 + 안전경고 | 이력 판단 + 가드레일 | `repeated==true` |
| S4 | 미지 코드 → 한계 인정 → A/S 안내 | 실패 처리(환각 방지) | `status:not_found` |

→ 상세: `02_SCENARIOS`

## 완료 기준 (평가)

| 지표 | 목표 | 판정 소스 |
|---|---|---|
| 부품 특정 정확률 | ≥ 90% | `traces`의 도구 호출 인자 (분모: part_no가 있는 문항) |
| 근거 페이지 인용률 | 100% | `citation` block **+ page가 traces와 일치**. 분모 18문항(S4형 2건 제외, D30) |
| 안전 경고 누락 | 0건 | `safety` block 존재 + "10분 이상" 기준값 |
| 미지 코드 환각률 | 0% | LLM judge (프롬프트는 `eval/`에 고정 커밋) |
| 권한 위반 403 차단 | 100% | HTTP status code |

→ 상세: `06_REPO_API §3`

---

## 구현 순서

| 단계 | 내용 |
|---|---|
| **M1** 데이터 준비 *(현재)* | 매뉴얼 파싱 · 에러코드 추출 · `related_parts` 매핑 · `seed.py` |
| **M2** 코어 구현 | MCP 서버 · 도구 7종 · 백엔드 · **Agent Loop + trace 발행/영속화** → S1~S4가 콘솔 레벨에서 동작 |
| **M3** UI | 화면 A/B + SSE trace 패널 |
| **M4** 평가 · 마무리 | 평가셋 실행 · 결과 문서화 · 데모 영상 · README |

> **trace를 M4로 미루지 않는 이유**는 위 §6에 있다. M4의 평가가 `traces` 테이블을 읽으므로 M2에서 같이 나와야 한다.
> 착수 권장 순서: `seed.py` → 스파이크 SP2·SP3 → 읽기 도구 5종(RAG 제외) → **S4로 파이프라인 먼저 관통** → S1 → S2 → S3.
> S4는 도구 1개만 필요하면서 루프·SSE·trace·환각 방지 규칙을 전부 지나가므로 가장 얇은 관통 경로다.

## 이 문서와 다른 문서의 관계

| 목적 | 문서 |
|---|---|
| 무엇을 만드는가 (목록) | **이 문서** |
| 왜 그렇게 정했는가 | `10_DECISIONS` (D1~D108) |
| 어떻게 동작하는가 | `02_SCENARIOS` · `09_RUNTIME` |
| 정확한 계약 | `04_MCP_TOOLS` · `05_DB_SCHEMA` · `06_REPO_API` |
| 지금 만들지 **않는** 것 | `07_BACKLOG` (P1~P32) |
| MVP 이후 설계 (확장 범위) | `11_ASSET_LIFECYCLE` · `12_MAINT_VALUE` |

## 범위 확장 — 자산 생애주기 (D67)

설비의 **처분·취득**과 그에 따른 **법정 조건·근거체인**을 본 범위에 포함한다. 프로젝트 정의가 "진단→발주"에서 **"취득→가동→수리→처분"** 으로 넓어졌다.

당초 D58 은 미뤄 두었지만, 그 근거였던 구현 리스크가 해소됐다 — 룰 5종·엔진·테스트 19개가 `data/rules/` 에서 이미 돌고, 다음 단계는 대부분 기존 패턴의 복제다. 상세는 `11_ASSET_LIFECYCLE`·`12_MAINT_VALUE`.

### 추가 기능

| # | 기능 | 상세 | 구현 상태 |
|---|---|---|---|
| 7 | **수리 / 교체 / 매각 3지 판단** — 발주 전에 자산가치 관점을 넣는다 | `12 §3` · `04 §13` | ✅ **Sprint 6** — `assess_repair_value`. 판정 순서가 계약(`ROOT_CAUSE_FIRST` → `HOLD` → `REPLACE` → `SELL_AS_IS` → `REPAIR`) |
| 8 | **보전지표** — MTBF 추세 · 예방보전 비율 · 누적 수리비 | `12 §2` · `04 §10·§11` | ✅ **Sprint 6** — `get_maintenance_metrics` · `classify_part_criticality`. MTBF 는 **달력 기준**(D70) |
| 9 | **수리 증빙 서명** — `work_type` 필수, append-only | `12 §7` | ✅ **Sprint 9** — `create_repair_record`(§16, D98)가 `repair_records` 에 `state='draft'` INSERT, `POST /api/repairs/{id}/submit`·`/sign`·`/reject`(`06 §2.8`)가 전이. `GET /api/approvals` 의 `kind:"repair"` 는 이제 실제로 채워진다(시드 12건: 서명 11 + draft 1, D85). Sprint 7·8 에서 두 번 이월된 뒤 착수됐다 |
| 10 | **처분 법정 조건 검사** — BLOCKING/PRECONDITION, 409 | `11 §3·§6 S9` · `04 §8` · `06 §2.5` | ✅ **Sprint 6** — 도구 + REST(`/api/assets/{id}/disposal/precheck`). verdict **5종**(D79), HTTP 매핑 D71 |
| 11 | **근거 3계층 + 서명** — 사실/해석/확정 분리, override 기록 | `11 §2` · `04 §14·§15` · `05 §14` · `06 §2.6` | ✅ **Sprint 7 — 계층 3 완료.** 계층 1·2(룰 엔진·`law_refs`·`rules`)와 번들(**5키**, D83) 완료. 계층 1 조문 원문 실수집 **8건 전부 `FETCHED`** (2026-08-13 — `KR-CITA-ENF-31` 등록 제목 `즉시상각의제` → `즉시상각의 의제` 사람 승인 후 수집 완료). 계층 3: `generate_disposal_document` draft INSERT(D81) → `POST /api/decisions/{id}/submit`·`/sign`(번들 재산출·해시 대조 D84) → `decisions` **DDL CHECK 2종**이 *서명 없는 확정 0건 · BLOCKING 우회 0건* 을 스키마로 잠근다. ✅ 문안 **2026-08-13 사람 검수 완료**(`template_review_notice` · D90) — **F1~F3 잔여 사람 검수 없음** |
| 12 | **중고 취득 검증** — 확인 항목 + 미확인 잔여 리스크 | `11 §6 S18` · `04 §9` · `06 §2.5` | ✅ **Sprint 6·7** — `verify_ownership` + REST `GET /api/assets/{id}/ownership` + 실사 화면. 9카테고리, `PARTIAL` 승격 경로 없음(코드에 분기 자체가 없다). UI 도 `PARTIAL` 을 성공색으로 그리지 않는다 (**D87**) |
| 13 | **기한 추적** — `TAX-CREDIT-2Y` 등 기한 임박 항목 선제 알림 | `11 §10` · 백로그 P36(F5) | ✅ **Sprint 11 완료 (D102)** — `deadlines`·`incidents` 신설 + `track_deadlines`(§17). D102 가 백로그 v2 제외(Sprint 7)를 supersede |
| 14 | **실사 보존 · 위험 프로파일** — 확인 항목 영속화 + 건물 위험 등급 | `11 §10` · 백로그 P36(F6) | ✅ **Sprint 11 완료 (D102)** — `ownership_checks`·`risk_profile` 신설 + `assess_risk_grade`(§18). `detect_law_revision`(S17)은 **제외 유지** — D102 가 다시 열지 않는다 |

> **노출은 기본 꺼져 있다 (D69).** 확장 **8종**은 `MAINTQ_TOOLS_PROFILE=full` 일 때만 MCP 에 등록된다.
> 기본값 `core` 로는 코어 7종만 보인다 — 도구를 늘린 뒤 평가를 돌리면
> "수정 효과 vs 도구 증가 효과"를 분리할 수 없기 때문이다.
> **D88 이 이 기준선을 코드로 잠갔다** — `run_eval.py` 가 `/health` 의 `tools_profile` **과** `tools` 실측
> 개수를 둘 다 보고, `core` 가 아니거나 `tools > 7` 이면 `--allow-full-profile` 없이는 `SystemExit(2)` 다.
> 단 **사람용 REST(`/api/assets/…`)는 `core` 에서도 동작한다** (D73).

**Sprint 7 결과** — ⓐ ✅ 법제처 조문 원문 실수집(`fetch_from_api`, 6/7) ⓑ ✅ 계층 3 서명 API + `decisions` 저장
ⓒ 🟡 쓰기 도구 — `generate_disposal_document` **완료** / `create_repair_record` **이월**
(Sprint 7 → Sprint 8 → **Sprint 9**. Sprint 8 도 손대지 않았다 — 아래 참조)
ⓓ ✅ 확장 도구의 UI 노출(자산 목록·처분 사전판정·실사·처분서 서명 화면).

**Sprint 8 결과** — A2A 신원 계층(`partner_links` 테이블·시드 5행·자격증명 env 층·`traces.request_chain_id`).
D91~D96 이 여기서 나왔고 스키마·시드·env 계층까지 구현됐다. **호출부(나가는 A2A 요청)는 미착수.**

**Sprint 9 잔여** — `create_repair_record`(P25·S29). ⚠ **두 번 미뤄졌다**: Sprint 7 은 처분 서명(F3)에,
Sprint 8 은 A2A 신원에 범위를 썼다. 기능이 취소된 것이 아니라 **범위 확정에서 계속 밀린 것**이고,
계약 자리(`kind: "repair"`)는 두 스프린트 내내 비어 있는 채로 유지됐다.

### 범위를 넓히되 순서는 지킨다

**완료 기준 5개의 우선순위는 그대로다.** 범위를 넓히는 것과 품질 기준을 느슨하게 하는 것은 다른 일이다.

1. **S1~S4 관통이 먼저** — `error_codes` 승인, `related_parts` 검수는 여전히 M1 크리티컬 패스다
2. 그다음 근거 계층(11번) — 나머지가 전부 이 위에 얹힌다
3. 기능 7~12는 그 뒤

### 경계가 헷갈리기 쉬운 지점

| 기존 (1~6번) | 확장 (7~12번) |
|---|---|
| 매뉴얼 **근거 페이지** 인용 | **법령 조문** 인용 |
| 반복 고장 **감지** (S3) | 그걸 **자산가치 감점 신호로 재사용** |
| 발주서 승인 큐 | 같은 큐에 **처분서·수리 증빙** 추가 |
| 쓰기 도구 1종 | **현재 2종** (`create_po_draft`·`generate_disposal_document`) → **Sprint 9** 에 `create_repair_record` 로 3종(Sprint 8 이월). **전부 draft 만 생성, 동일 패턴** |
