# MaintQ 문서 인덱스

**3줄 요약:** MaintQ는 인버터/PLC 설비의 **생애주기 전체**를 하나의 대화로 잇는 B2B 보전 에이전트다 — 에러 진단→부품 특정→재고·견적→발주 승인, 그리고 수리 증빙→법정 조건 검사→처분 서명까지. 주제는 도구 오케스트레이션 + **근거 기반 판단**이다. **AI는 근거를 조립하고, 사람이 서명한다.**

| 문서 | 내용 | 언제 열어보나 |
|---|---|---|
| [00_MVP_SCOPE](00_MVP_SCOPE.md) | **반드시 구현할 기능 6종 + 확장 6종 + 인프라 + 완료 기준** (목록만, 상세는 각 문서로 링크) | 착수 전 "이번에 뭘 만드나" 확인, 범위 다툼 날 때 |
| [01_OVERVIEW](01_OVERVIEW.md) | 문제정의·As-Is/CMMS 포지셔닝·페르소나·KPI·기능·OoS·리스크·마일스톤(M1~M4) | 프로젝트 전체 그림이 필요할 때, 발표 준비 |
| [02_SCENARIOS](02_SCENARIOS.md) | S1(순차)·S2(분기)·S3(이력+가드레일)·S4(실패 처리) + 도구 시퀀스 + **확장 시퀀스(S1+·S9·S10·S18·S29, S17 은 v2 제외)** | 기능 구현 전 "이게 어느 시나리오에 복무하나" 확인 |
| [03_WIREFRAME](03_WIREFRAME.html) | 화면 A(진단 콘솔)·A-2(S3 변형)·B(승인 큐) + 주석 10개. **구조 참조 — 실제 화면은 frontend/ 구현이 기준** | UI 작업 전, 디자인 검수 |
| [04_MCP_TOOLS](04_MCP_TOOLS.md) | **코어 7종(읽기 6+쓰기 1) + 확장 11종(§8~§18, 읽기 9+쓰기 2)** 입출력 계약, 프로파일 게이트(D69), 설계 원칙 6개 | 도구 구현·수정 시 (계약 임의 변경 금지) |
| [05_DB_SCHEMA](05_DB_SCHEMA.md) | 테이블 **23절(CREATE TABLE 24개)** + 시드 케이스 맵 7종 | DB·시드 작업 시 |
| [06_REPO_API](06_REPO_API.md) | 모노레포 구조, REST/SSE 규격(이벤트 4종), **`/api/assets` 4종 + D71 HTTP 매핑**, **`/api/decisions`(§2.6)·`/api/approvals`(§2.7)**, 상태 전이, testset 스키마 | 폴더·엔드포인트 만들 때, M1 첫날 |
| [07_BACKLOG](07_BACKLOG.md) | v2 기능 P1~P21 + **확장 범위 P22~P27(진행 표시 — P24·P25 Sprint 7·9 완료)** + **P28~P36 인프라·데이터 품질** + **P40·P41 UI·결재 워크플로우** + 아이디어 주차장 + 경계 메모 | "이것도 넣을까?" 싶을 때 (답: 백로그로) |
| [08_DESIGN_BRIEF](08_DESIGN_BRIEF.md) | Claude Design 투입 프롬프트 + 검수 체크리스트 | 하이파이 디자인 뽑을 때 |
| [09_RUNTIME](09_RUNTIME.md) | S1 시퀀스 다이어그램, 에이전트 루프 정책, 장애 모드, 스파이크 3종 | 에이전트 루프·SSE 구현 시, 개발 착수 직전 |
| [10_DECISIONS](10_DECISIONS.md) | 설계 결정 D1~D110 + 이유 | "왜 이렇게 했지?" 싶을 때, 설계 변경 전 필독 |
| [11_ASSET_LIFECYCLE](11_ASSET_LIFECYCLE.md) | 처분 법정 조건 · **근거 3계층(계층 3 = Sprint 7 완료)** · 룰 5종 · S9·S10·S18 | 처분·취득 기능 작업 시, "근거를 어떻게 남기나" 확인할 때 |
| [12_MAINT_VALUE](12_MAINT_VALUE.md) | 보전지표 · 수리 이력의 자산가치 · 중고 거래 배경 · S1+·S29 | 수리 판단·증빙 기능 작업 시 |
| [13_DEPLOYMENT](13_DEPLOYMENT.md) | 배포 설계 — 런타임 3조각 · **단일 인스턴스 제약** · 벡터DB 부재 · SQLite 유지 근거 · 미결정 3건 | 배포 논의 전, 인프라 스택 고를 때 |

**규칙:** 설계와 다른 구현을 하려면 10_DECISIONS에 결정을 먼저 추가하고 진행한다. 새 기능 아이디어는 07_BACKLOG로 보낸다.

**범위가 넓어졌다 (D67).** `11`·`12`는 이제 본 범위다 — 당초 Phase 2로 미뤄 둔 것(D58)을 열었다. 단 **순서는 그대로** — 완료 기준 5개와 S1~S4 관통이 먼저고, 그다음 근거 계층, 그 위에 나머지가 얹힌다. 룰 카탈로그는 `data/rules/` 에 있다(pytest 통과, **법령 원문 8건 전부 `FETCHED`** — Sprint 7 MQ-701 이 6건, 08-13 에 `KR-OSHA-ENR-126` 추가분과 `KR-CITA-ENF-31` 사람 승인분이 채워졌다).

---

## 진행 상태 (2026-08-19 · Sprint 13 완료 시점)

**M1~M4 는 완주했고, Sprint 6 에서 확장 범위(F1·F2·F4)를 열었으며 Sprint 7 이 F3(계층 3 서명)을 닫았다.
Sprint 8 은 A2A 신원 계층을 깔았다 — 스키마·시드·자격증명 env 층까지이고 호출부는 없다.
Sprint 9 가 P25(수리 증빙, `create_repair_record`, D98~D101)를 닫았고, 같은 브랜치
(`sprint-9-repair-record`)에서 재고 드로어·설비 하이라이트 대시보드(브레인스토밍 산출물)와
Sprint 10(P37·P38 — 근거 번들·지출 분류 화면, 수리 증빙 승인 큐 상세)까지 이어서 완료했다.
**Sprint 11 이 백로그 P36(F5·F6 기한·사고·위험 감시 계층)을 D102 로 의도적으로 본 범위에 편입해
착수·완료했다** — MVP 완료 기준(핵심 1~6 + 확장 7~12) 달성 후 여는 새 범위의 첫 사례.
Sprint 12 가 시나리오 번호 정정(S29, P33)과 `track_deadlines`/`assess_risk_grade` UI 노출을 마쳤다.
**Sprint 13 이 백로그 P28 ⓐ(외부 응답 원본 보관 규약, D103)와 P31(`actions` 결측 34건 3자 대조,
D105 로 Elice DocVision 도입)을 5스테이지로 완결했다** — 대조 엔진은 캐시 0건에서도 전건
`INCONCLUSIVE` 로 완주하도록 설계해 사람 승인이 스프린트를 막지 않게 했고, 승인 후 실판독까지
같은 세션에서 이어졌다.
⛔ master 미병합 — 머지는 사람이 요청할 때만.**

**2026-08-14 (스프린트 아님 · 데이터 조사)** — `data/part-catalog` 브랜치에서 **P32(부품 품번) 종결**.
4축 전수 조사 결과 **`parts` 40종 중 공개된 실품번은 1종**(`PCB-IG5-CTRL` → `SV-iG5A I/OPCBASSY`)이고,
케이스 맵 주인공 `FAN-IG5-01`(iG5A 소용량 냉각팬)은 **제조사가 대리점 문의로 돌려 품번 자체가 비공개**다.
결과를 **`parts.mfr_part_no`(nullable, D97)** 로 스키마에 고정했다 — **`NULL` = "미조사"가 아니라 "미공개"**.
전문 [`../data/analysis/part_number_sources.md`](../data/analysis/part_number_sources.md).
⛔ **부품 특정 지표는 안 움직였다** — 데이터가 세상에 없다는 것이 실증됐을 뿐이다.
⚠ **수치 정정(2026-08-14)**: 이 줄은 오래 `42.2%` 로 적혀 있었는데 그건 **4차 기준선**(`20260812-021820`) 값이다.
**현재 코드의 기준선은 `20260812-060312` 의 `40.0%`** 이고(마지막 실행 `075303` 은 MQ-714 가 들어간 상태이며 그 코드는 `ac7547f` 로 원복됐다),
`eval_gap_4th.md:151` 이 `part 42.2 → 40.0%` 라고 적은 뒤 바로 다음 줄에 *"흔들림이 9~11칸으로 지배적이라 비율 비교가 성립하지 않는다"* 를 덧붙였다 —
즉 **−2.2pt 는 개선도 회귀도 아니고 판정 불가**다.

| Sprint 8 (A2A 신원) 축 | 상태 |
|---|---|
| `partner_links` 테이블 (D91·D96) | ✅ 구현 — 판정(`link_state` 3상태)과 식별자(`external_ref`)를 **DDL CHECK 로 분리**. null-safe `IS` · `subject_ref NOT NULL`(회사 결 `''`) · `linked_at DATETIME`(UTC) |
| 연결 전제 시드 (D92) | ✅ 5행 — `LINKED` 4 / **`NOT_LINKED` 대조군 `BLD-D`** 1. ⚠ **목업**(`PARTNER_LINKS_MOCK=True`) |
| 증권 식별자 정본 (D95) | ✅ `assets.policy_id` 하나 — `partner_links` 복제 **0건**(seed ㉔ 음성 검사) |
| 파트너 자격증명 (D93) | 🟡 **env 층만** — `.env.example` 4키(값 전부 빈칸) + `backend/a2a/credentials.py`. **토큰 캐시 미착수** · `mcp_server/**` 에서 안 보임(D15) |
| `traces.request_chain_id` (D94-ⓐ) | 🟡 **컬럼만** — **쓰는 쪽이 없어 전 행 NULL 이 정상**. 스파이크 `⑪-b` 가 *"쓰는 코드 0건"* 을 명시 기록(D76-2 재발 방지) |
| 나가는 A2A 요청 (호출부) | ⛔ **미착수** — `docs/A2A_CONTRACTS.md` 의 호출 목록 10종은 전부 미구현이다 |

| 축 | 상태 |
|---|---|
| 코어 도구 7종 · 백엔드 · 에이전트 루프 · trace · UI · 평가 하네스 | ✅ 동작 |
| **확장 도구 11종** (`check_disposal_blockers` · `verify_ownership` · `classify_part_criticality` · `get_maintenance_metrics` · `classify_expenditure` · `assess_repair_value` · `build_evidence_bundle` · `generate_disposal_document` · `create_repair_record` · **`track_deadlines`** · **`assess_risk_grade`**) | ✅ 구현 — 계약은 `04 §8~§18`. **노출은 `MAINTQ_TOOLS_PROFILE=full` 에서만**(기본 `core`, D69·D88) |
| **쓰기 도구** | **3종** — `create_po_draft`(`po_drafts`) · `generate_disposal_document`(`decisions`) · `create_repair_record`(`repair_records`). 셋 다 **draft INSERT 만**, UPDATE 권한 없음 (D10·D81·D98) |
| DB | 코어 11 + 확장 7 + A2A 1 + UI 목업 1 + F5·F6 4 = **테이블 24개**(실측 `data/seed.py`). `decisions` 에 컬럼 5개 + **CHECK 2종** 추가(MQ-707) · **`partner_links` 신설**(Sprint 8, D91·D96) · `traces.request_chain_id` 컬럼 신설(D94-ⓐ, **전 행 NULL 이 정상**) · **`part_lifecycle_mock` 신설**(Sprint 10, §19 — 설비 하이라이트 대시보드용 부품 생애주기 경고 목업) · **`deadlines`·`incidents`·`ownership_checks`·`risk_profile` 신설**(Sprint 11, §20~§23, F5·F6, D102) |
| 룰 카탈로그 | 5종 전부 **트리거 정합**(D77·D78) — 판정 5종(`BLOCKED`/`HOLD`/`INSUFFICIENT_FACTS`/`CONDITIONAL`/`CLEAR`, D79)이 시드에서 전부 도달 가능 |
| REST | `GET /api/assets` · `/{id}` · `/{id}/ownership` · `POST /{id}/disposal/precheck`(무저장, D71) · **`/api/decisions`(제출·서명·반려)** · **`/api/repairs`(제출·서명·반려, D98)** · **`/api/approvals`(통합 큐, 읽기 전용 — D85)**. ⚠ `/api/po` 는 **형태 불변** |
| 프론트 | 라우트 **18개** (실측 `npx next build`, Sprint 12 이후 무변경) — 정비사 콘솔 · 자산 목록 · 처분 사전판정 · 실사 · 팀장 큐 · 처분서 상세/서명 · trace · 설비 하이라이트 대시보드 · 근거 번들/지출 분류 · 수리 증빙 상세 · 기한·위험등급 조회 |
| 외부 응답 보관 | ✅ **`data/external/store.py`(D103)** — `data/raw/external/<source>/<key>.json` 에 git 추적 봉투(요청 파라미터·헤더·인증값 미저장, allowlist 강제). 소비자 2종: `fetch_laws` payload 소급 보관 · **Elice DocVision**(D105, 독립 2차 판독기, 정답지 아님) 캐시 |
| 회귀 (실측 2026-08-20, IE5 검수 이월 항목 반영 후) | spikes **32스위트 / 976건**(`ie5_extract_contract` 에 A⑯·C⑪·C⑫·D④ 4건 추가, 972→976) · seed **36건**(`error_codes`=65 불변, `users` 자가검증에 ⑨-b 신설) · pytest **83건**(3파일 합산 — `data/rules/test_rules.py` 46 + `backend/agent/test_llm_cache.py` 24 + `data/external/test_elice_docvision.py` 13) · ruff clean · `next build` 재실행 불필요(프론트 무변경, 18 라우트 유지) · `ui_honesty_contract` **253/253**(전 계약 PASS). ⚠ Windows 소켓 고갈로 연속 실행 시 1건이 산발 실패할 수 있다 — **재시도로 통과**(CLAUDE.md 회귀 절), 이번 32스위트 전수 실행은 재시도 0회 |
| 잔가곡선 | **목업 정률 공식**으로 확정(D74) — 중진공 호가로는 감가를 식별할 수 없다는 한계 실증을 `data/analysis/residual_curve.md` 에 보존 |
| 계층 1 (법령 원문) | ✅ **8/8 `FETCHED` 완성 (2026-08-13)** — 총 **8,197자** · 해시 전건 무결. 마지막 `PENDING` 이던 `KR-CITA-ENF-31` 은 등록 제목(`즉시상각의제` → `즉시상각의 의제`) 사람 승인 후 수집됐다. 수집기(`fetch_from_api`)·적용기(`apply_fetch`) 둘 다 완료(D75). 근거: `../data/analysis/law_fetch.md` |

> **계층 1 — Sprint 7 MQ-701 시점의 기록** (⚠ **현재값 아님**. 현재는 위 표대로 **8/8 `FETCHED` 완성**,
> `KR-CITA-ENF-31` 은 2026-08-13 사람 승인으로 해소됐다. 아래는 *그 미수집 경로가 어떻게 동작했는가* 의 기록이다)
> — 당시 `KR-CITA-ENF-31` 만 `PENDING` 이었다.
> 등록 제목(`즉시상각의제`)이 API 값(`즉시상각의 의제`)과 달라 `apply_fetch` 가 `LawMismatchError` 로
> **파일을 손대기 전에 중단**했다 — 조용히 덮어쓰지 않은 것이 정상 동작이며 **사람 승인 대기**다.
> 처분 룰 5종이 인용하는 조문은 나머지 6건에 전부 포함되므로 `check_disposal_blockers` 의
> `evidence_completeness` 실 DB 정상값은 **`COMPLETE`** 이고, `build_evidence_bundle` 은
> 9자산 × SALE/SCRAP **18조합 전부 `status:"ok"`**(`law_text_unavailable` 0건)다.
> **이 미수집 경로가 다시 발화하는 때**: 새 조문을 등록했는데 아직 안 받았을 때 ·
> 개정으로 `pending_revisions` 가 열렸을 때 · `KR-CITA-ENF-31` 처럼 정체성 대조에 실패했을 때.

**다음 액션 (Sprint 13 완료 — P28 ⓐ·P31 닫힘, 2026-08-19)**

> 📍 **지금**: 브랜치 `sprint-13-external-store`. Sprint 9(P25 수리 증빙) → 브랜치 내 후속 작업
> (재고 드로어·설비 하이라이트 대시보드) → Sprint 10(P37·P38 근거 번들·지출 분류 화면, 수리 증빙
> 승인 큐 상세) → Sprint 11(P36 — D102 로 편입한 기한·사고·위험 감시 계층) → Sprint 12(S29 정정 ·
> UI 노출) → **Sprint 13(P28 ⓐ·P31 — 외부 응답 원본 보관 + `actions` 결측 3자 대조)** 까지 전부 완료.
> 계획은 `docs/sprints/sprint-9.md`~`sprint-13.md`, 세션 기록은 `docs/sessions/2026-08-18.md`.
> ⛔ master 미머지 — 머지는 사람이 요청할 때만.
>
> ✅ **Sprint 13 이 5스테이지 전부 끝났다** — 설계 근거는
> [`docs/superpowers/specs/2026-08-19-actions-absence-verification-and-external-store-design.md`](superpowers/specs/2026-08-19-actions-absence-verification-and-external-store-design.md)
> (§9 실행 결과 주석 추가). Stage 1~4(네트워크·지출 0)로 보관 규약(D103)·소비자 2종·대조 엔진·
> 회귀(31스위트)를 완주했고, **사람 승인 뒤 Stage 5 가 같은 세션에 이어졌다** — Elice DocVision
> 34페이지 실판독(**1,530원**, 2단 구매: 파일럿 90원 → 본판독 1,440원)과 대조 확정. 새 D-결정
> **3건**: **D103**(외부 응답 원본 보관 규약) · **D104**(LLM 응답 카세트, 병행 브랜치가 먼저 등재해
> 번호가 밀림) · **D105**(Elice DocVision 도입, 정답지로 취급하지 않음). P39 는 여전히
> 스코프아웃(브레인스토밍부터 다시).
>
> 🎯 **판독 결과** — `CONFIRMED_ABSENT` **24** · `DISAGREE` **6** · `STILL_AMBIGUOUS` **3** ·
> `RECOVERABLE` **1** · `INCONCLUSIVE` **0**. `_pending_review`(MQ-911)의 *"매뉴얼에 원래 없음"*
> 주장 28건 중 24건이 확정됐고, `extract_triage` 의 *"S100 25건은 파서 결함(`CELL_SPLIT`)"* 가설은
> **기각**됐다 — 유료 OCR 로 데이터를 늘리려던 기대는 성립하지 않았다. 회수 가능은 `iG5A NTC`
> **1건뿐**이고 D99 재승인 대기다.

1. ✅ ~~**사람** — `related_parts` 최종 승인~~ — **2026-08-12 완료.** 부품 특정 정확률이 "판정 불가" → **"미달 40.0%"**(목표 ≥90%) 로 바뀌었다 (D12 해제)
2. ✅ ~~**사람** — 처분 승인서·진술보장서 **문안 검수**~~ — **2026-08-13 완료.** 19시나리오(판정 5종 전부) 렌더링본을 확인하고 **수정 없이 승인**. 출력 키가 `unreviewed_template_notice` → **`template_review_notice`** 로 바뀌었다 (**D90**) — 값이 "검수 완료"가 되는데 키에 `unreviewed` 가 남으면 자기모순이다
3. ✅ ~~**사람** — `KR-CITA-ENF-31` 등록 제목 정정 승인~~ — **2026-08-13 완료.** 등록 `즉시상각의제` → API 값 `즉시상각의 의제`. **계층 1 이 8/8 `FETCHED` 로 완성됐다**
4. ✅ ~~**사람** — `parts.part_class` 40종 감수~~ — **2026-08-13 완료.** 40종 전량 확인 후 **초안 그대로 승인**(변경 0건). `assess_repair_value` 3지 판단을 실적으로 인용할 수 있다 (`seed.py` 의 `PART_CLASS_REVIEWED = True`)
5. ✅ ~~**사람** — 기준내용연수 `N` 법령 원문 대조~~ — **2026-08-13 완료.** 별표서식 API 로 **별표6** 실수집 대조 → 업종을 KSIC **`29`** 로 고정하고 **`N = 8 → 10`**(별표6 제5호) 정정 (**D89**). 3지 판정은 27조합 중 1건만 이동. ⚠ `RESIDUAL_AT_LIFE_END=0.50`·`FLOOR=0.10` 은 여전히 **가정**이다
6. ~~**MQ-713/714** — 지표 튜닝~~ — **종료.** 코드 축(A·C) 채택 · 프롬프트 축(A′·B)과 루프 축(MQ-714) **전부 기각·원복**. 판정 규칙은 `--repeat 3` 의 `안정실패 → 안정통과` 승격 칸 수. ⛔ `MAINTQ_TOOLS_PROFILE=full` 로 평가하지 않는다 (D88 이 코드로 막는다)
7. ✅ ~~**Sprint 9** — `create_repair_record`(P25·S29)~~ — **완료.** 쓰기 도구(D98)·`/api/repairs` 제출·서명·반려(D85)까지 붙었고, `GET /api/approvals` 의 `kind: "repair"` 가 채워진다. 정본 병합(**MQ-919**, `actions` 결측 회수)도 **2026-08-17 사용자 최종 승인 완료** — 남은 항목 없음
8. ✅ ~~**브랜치 후속** — 재고 드로어 + 설비 하이라이트 대시보드~~ — **완료.** 16태스크(subagent-driven-development). 최종 브랜치 리뷰에서 드러난 사전 존재 D87 위반 2건도 함께 해소
9. ✅ ~~**Sprint 10** — 근거 번들·지출 분류 화면(P37) + 수리 증빙 승인 큐 상세(P38)~~ — **완료.** `/sprint 10` → `/stage 1~3` 전 스테이지 자동 파이프라인 통과. 브라우저 실사용 검증(Claude-in-Chrome) 중 발견한 실버그 1건(`RepairDetail` 상태 미갱신)도 같은 세션에서 수정
10. ✅ ~~**Sprint 11** — 기한·사고·위험 감시 계층(백로그 P36, D102 로 편입)~~ — **완료.**
    `deadlines`·`incidents`·`ownership_checks`·`risk_profile` 4테이블 + `track_deadlines`·
    `assess_risk_grade` 2도구(읽기 전용) + REST 노출(D73) + 에이전트 시스템 프롬프트 배선까지
    5스테이지 전부 완결. `detect_law_revision`(S17)은 계획대로 제외 유지. UI 노출은 명시적으로 컷
    → **Sprint 12에서 노출 완료**
11. ✅ ~~**Sprint 12** — S19→S29 정정(P33 해소) + `track_deadlines`/`assess_risk_grade` UI 노출~~ —
    **완료.** Stage 1: 문서 시나리오 번호 `S19`→`S29` 전수 정정 + 프론트 데이터 계층(`lib/
    deadlines.ts`·`lib/riskGrade.ts`). Stage 2: `DeadlinesPanel.tsx`·`RiskGradeGrid.tsx` 2컴포넌트.
    Stage 3: `/manager/deadlines`·`/manager/risk-grade` 2페이지 + 크로스링크. Stage 4: 회귀 확장
    (`ui_honesty_contract` `L2_FILES_FLOOR` 32→36 실측 갱신, spikes 30스위트 871건) + 기준선·문서
    마감. 신규 D-결정 없음(카운트·노출 갱신만)
12. **A2A 호출부는 QMesh 착수 후** — 나가는 요청·원문 보관(`tool_payload`)·토큰 캐시는 상대 서버가 서야 의미가 생긴다. 지금 만들면 검증할 상대가 없고, `request_chain_id` 를 쓰는 순간 스파이크 `⑪-b` 를 **뒤집어야 한다**(그게 정상 신호다)
13. 🟡 **사람** — A2A 연결 승인·파트너 자격증명 **실값**은 미착수다. 시드는 목업 전제(`PARTNER_LINKS_MOCK=True`)이고 `.env` 4키는 비어 있다 → [../TODO_직접할일.md](../TODO_직접할일.md) `## Sprint 8 — A2A`
14. 🟡 **사람** — 시스템 프롬프트 안전 문구 최종 검수(`SAFETY_BASELINE`·`QUALIFIED_WORKER_NOTE`) — 여전히 대기. 검수 전에도 런타임은 막지 않는다(게이트하면 안전 블록이 아예 안 나가 더 위험) → `TODO_직접할일.md` `## M2~M4 중`
15. ✅ ~~**사람 협의**~~ — 완료. `S29`로 확정(2026-08-18), MaintQ 문서 전수 정정 완료(Sprint 12 MQ-1201)
16. ✅ ~~**P30** — 부재 검사 liveness 앵커 2건~~ — **완료 (2026-08-19, `28c4f69`).** `agent_loop_contract ⑯ A7`
    에 양성 축 2개(앵커 3종 + 스캐너 생존), `ui_honesty_contract` 에 `IMPORT_SPEC` 오라클 메타검사 1건.
    **뮤턴트로 실증** — 추출기를 망가뜨리면 새 오라클만 FAIL 하고 C1~C8 은 전건 PASS 한다(그 결함의 정의).
    기준선 **30스위트 / 872건**. 같은 커밋에서 백로그 P31·P22 표기 정정
17. ✅ ~~**P31 · P28 ⓐ 설계**~~ — **완료 (2026-08-19, `5bf18ad`).** 같은 `actions` 결측 34건에 대해
    저장소 안에 **서로 충돌하는 진단이 셋** 있고 아무도 대조한 적이 없다는 것이 드러났다. 목표는 회수가
    아니라 **불일치 해소** — 부재가 사실로 확정되는 것도 유효한 산출이다. 구현은 Sprint 13 으로 진행
18. ✅ ~~**Sprint 13** — 외부 응답 원본 보관(P28 ⓐ, D103) + `actions` 결측 3자 대조(P31, D105)~~ —
    **완료.** Stage 1: `data/external/store.py`(보관 모듈) · `.gitignore` 추적 경계 · D103 등재.
    Stage 2: `fetch_laws` 소급 보관 · Elice DocVision 클라이언트 이식 · D105 등재 · 지출 가드
    pytest 13건. Stage 3: 3자 대조 엔진(`data/verify_actions_absence.py`, 캐시 0건에서도 완주) +
    신규 스파이크 `external_store_contract`(스위트 30→31). Stage 4: 회귀 전수(31스위트/919건) +
    기준선·절대규칙 5 예외 명문화. **Stage 5(사람 승인 후, 같은 세션)**: Elice 34페이지 실판독
    1,530원 집행 → `CONFIRMED_ABSENT` 24·`DISAGREE` 6·`STILL_AMBIGUOUS` 3·`RECOVERABLE` 1·
    `INCONCLUSIVE` 0 확정, 백로그 P28·P31 상태 갱신

> **남은 사람 승인 4건** — **`iG5A NTC` 1건 D99 재승인**(18번 Stage 5 회수분, 정본 병합 대기) ·
> **`DISAGREE` 중 `iG5A EEP`·`HWT` 2건 확인**(18번, 위양성 여부 육안 대조) · **안전 문구 검수**(14번) ·
> **A2A 파트너 자격증명 실값**(13번, QMesh 착수 전까지는 급하지 않음). 나머지는 전부 완료됐다.
>
> ⚠ **`N` 이 확정됐다고 잔가곡선이 실측이 된 것은 아니다** — `RESIDUAL_AT_LIFE_END=0.50`·
> `FLOOR=0.10` 은 근거 미확보 **가정**으로 남아 있고 D74·D65 의 추정치 고지는 유지된다.

사람이 해야 할 일 전체는 [../TODO_직접할일.md](../TODO_직접할일.md).

<details><summary>지난 이력</summary>

설계 검토·정합화 완료(2026-07-18, D20~D23) → M1(데이터 준비). 문서 정합성 2차 점검(2026-07-23)에서 계약 구멍 5건 보완 → **D28~D32**, MVP 범위 문서화 + 발주서 추적 필드 → **D33·D34**, 프론트 구현에서 발견한 block 계약 누락 → **D35**.
매뉴얼 3종 확보 + 스파이크 SP1(표 추출) 완료 → D24~D27. `error_codes` = **65건**(iG5A 24 / S100 41, 2026-07-28 사람 승인 후 적재), 두 기종 공통 표기 코드 12종 확보(D6 "같은 코드, 다른 의미" 실증).
`related_parts` 는 8코드 위임 판정(2026-08-05) 후 **사람 최종 승인 완료(2026-08-12)** — D12 게이트 해제. 실적 인용 시 위임 → 승인 두 단계를 함께 밝힐 것.

</details>
