# MaintQ 문서 인덱스

**3줄 요약:** MaintQ는 인버터/PLC 설비의 **생애주기 전체**를 하나의 대화로 잇는 B2B 보전 에이전트다 — 에러 진단→부품 특정→재고·견적→발주 승인, 그리고 수리 증빙→법정 조건 검사→처분 서명까지. 주제는 도구 오케스트레이션 + **근거 기반 판단**이다. **AI는 근거를 조립하고, 사람이 서명한다.**

| 문서 | 내용 | 언제 열어보나 |
|---|---|---|
| [00_MVP_SCOPE](00_MVP_SCOPE.md) | **반드시 구현할 기능 6종 + 확장 6종 + 인프라 + 완료 기준** (목록만, 상세는 각 문서로 링크) | 착수 전 "이번에 뭘 만드나" 확인, 범위 다툼 날 때 |
| [01_OVERVIEW](01_OVERVIEW.md) | 문제정의·As-Is/CMMS 포지셔닝·페르소나·KPI·기능·OoS·리스크·마일스톤(M1~M4) | 프로젝트 전체 그림이 필요할 때, 발표 준비 |
| [02_SCENARIOS](02_SCENARIOS.md) | S1(순차)·S2(분기)·S3(이력+가드레일)·S4(실패 처리) + 도구 시퀀스 + **확장 시퀀스(S1+·S9·S10·S18·S19, S17 은 v2 제외)** | 기능 구현 전 "이게 어느 시나리오에 복무하나" 확인 |
| [03_WIREFRAME](03_WIREFRAME.html) | 화면 A(진단 콘솔)·A-2(S3 변형)·B(승인 큐) + 주석 10개. **구조 참조 — 실제 화면은 frontend/ 구현이 기준** | UI 작업 전, 디자인 검수 |
| [04_MCP_TOOLS](04_MCP_TOOLS.md) | **코어 7종(읽기 6+쓰기 1) + 확장 8종(§8~§15, 읽기 7+쓰기 1)** 입출력 계약, 프로파일 게이트(D69), 설계 원칙 6개 | 도구 구현·수정 시 (계약 임의 변경 금지) |
| [05_DB_SCHEMA](05_DB_SCHEMA.md) | 테이블 **17절(CREATE TABLE 18개)** + 시드 케이스 맵 7종 | DB·시드 작업 시 |
| [06_REPO_API](06_REPO_API.md) | 모노레포 구조, REST/SSE 규격(이벤트 4종), **`/api/assets` 4종 + D71 HTTP 매핑**, **`/api/decisions`(§2.6)·`/api/approvals`(§2.7)**, 상태 전이, testset 스키마 | 폴더·엔드포인트 만들 때, M1 첫날 |
| [07_BACKLOG](07_BACKLOG.md) | v2 기능 P1~P21 + **확장 범위 P22~P27(진행 표시 — P24 Sprint 7 완료, P25 는 Sprint 8)** + **P28·P29 인프라** + 아이디어 주차장 + 경계 메모 | "이것도 넣을까?" 싶을 때 (답: 백로그로) |
| [08_DESIGN_BRIEF](08_DESIGN_BRIEF.md) | Claude Design 투입 프롬프트 + 검수 체크리스트 | 하이파이 디자인 뽑을 때 |
| [09_RUNTIME](09_RUNTIME.md) | S1 시퀀스 다이어그램, 에이전트 루프 정책, 장애 모드, 스파이크 3종 | 에이전트 루프·SSE 구현 시, 개발 착수 직전 |
| [10_DECISIONS](10_DECISIONS.md) | 설계 결정 D1~D94 + 이유 | "왜 이렇게 했지?" 싶을 때, 설계 변경 전 필독 |
| [11_ASSET_LIFECYCLE](11_ASSET_LIFECYCLE.md) | 처분 법정 조건 · **근거 3계층(계층 3 = Sprint 7 완료)** · 룰 5종 · S9·S10·S18 | 처분·취득 기능 작업 시, "근거를 어떻게 남기나" 확인할 때 |
| [12_MAINT_VALUE](12_MAINT_VALUE.md) | 보전지표 · 수리 이력의 자산가치 · 중고 거래 배경 · S1+·S19 | 수리 판단·증빙 기능 작업 시 |

**규칙:** 설계와 다른 구현을 하려면 10_DECISIONS에 결정을 먼저 추가하고 진행한다. 새 기능 아이디어는 07_BACKLOG로 보낸다.

**범위가 넓어졌다 (D67).** `11`·`12`는 이제 본 범위다 — 당초 Phase 2로 미뤄 둔 것(D58)을 열었다. 단 **순서는 그대로** — 완료 기준 5개와 S1~S4 관통이 먼저고, 그다음 근거 계층, 그 위에 나머지가 얹힌다. 룰 카탈로그는 `data/rules/` 에 있다(pytest 통과, **법령 원문 8건 전부 `FETCHED`** — Sprint 7 MQ-701 이 6건, 08-13 에 `KR-OSHA-ENR-126` 추가분과 `KR-CITA-ENF-31` 사람 승인분이 채워졌다).

---

## 진행 상태 (Sprint 7 Stage 7 시점 · 2026-08-10)

**M1~M4 는 완주했고, Sprint 6 에서 확장 범위(F1·F2·F4)를 열었으며 Sprint 7 이 F3(계층 3 서명)을 닫았다.**

| 축 | 상태 |
|---|---|
| 코어 도구 7종 · 백엔드 · 에이전트 루프 · trace · UI · 평가 하네스 | ✅ 동작 |
| **확장 도구 8종** (`check_disposal_blockers` · `verify_ownership` · `classify_part_criticality` · `get_maintenance_metrics` · `classify_expenditure` · `assess_repair_value` · `build_evidence_bundle` · **`generate_disposal_document`**) | ✅ 구현 — 계약은 `04 §8~§15`. **노출은 `MAINTQ_TOOLS_PROFILE=full` 에서만**(기본 `core`, D69·D88) |
| **쓰기 도구** | **2종** — `create_po_draft`(`po_drafts`) · `generate_disposal_document`(`decisions`). 둘 다 **draft INSERT 만**, UPDATE 권한 없음 (D10·D81) |
| DB | 코어 11 + 확장 7 = **테이블 18개**(실측 `data/seed.py`). `decisions` 에 컬럼 5개 + **CHECK 2종** 추가(MQ-707) |
| 룰 카탈로그 | 5종 전부 **트리거 정합**(D77·D78) — 판정 5종(`BLOCKED`/`HOLD`/`INSUFFICIENT_FACTS`/`CONDITIONAL`/`CLEAR`, D79)이 시드에서 전부 도달 가능 |
| REST | `GET /api/assets` · `/{id}` · `/{id}/ownership` · `POST /{id}/disposal/precheck`(무저장, D71) · **`/api/decisions`(제출·서명·반려)** · **`/api/approvals`(통합 큐, 읽기 전용 — D85)**. ⚠ `/api/po` 는 **형태 불변** |
| 프론트 | 라우트 **10개** (실측 `npm run build`) — 정비사 콘솔 · 자산 목록 · 처분 사전판정 · 실사 · 팀장 큐 · 처분서 상세/서명 · trace |
| 회귀 (실측 2026-08-12) | spikes **27스위트 / 616건** · seed **21건** · pytest **46건**. ⚠ Windows 소켓 고갈로 연속 실행 시 1건이 산발 실패할 수 있다 — **재시도로 통과**(CLAUDE.md 회귀 절) |
| 잔가곡선 | **목업 정률 공식**으로 확정(D74) — 중진공 호가로는 감가를 식별할 수 없다는 한계 실증을 `data/analysis/residual_curve.md` 에 보존 |
| 계층 1 (법령 원문) | ✅ **8/8 `FETCHED` 완성 (2026-08-13)** — 총 **8,197자** · 해시 전건 무결. 마지막 `PENDING` 이던 `KR-CITA-ENF-31` 은 등록 제목(`즉시상각의제` → `즉시상각의 의제`) 사람 승인 후 수집됐다. 수집기(`fetch_from_api`)·적용기(`apply_fetch`) 둘 다 완료(D75). 근거: `../data/analysis/law_fetch.md` |

> **계층 1 현재값 (Sprint 7 MQ-701 실수집 이후)** — `KR-CITA-ENF-31` 만 `PENDING` 이다.
> 등록 제목(`즉시상각의제`)이 API 값(`즉시상각의 의제`)과 달라 `apply_fetch` 가 `LawMismatchError` 로
> **파일을 손대기 전에 중단**했다 — 조용히 덮어쓰지 않은 것이 정상 동작이며 **사람 승인 대기**다.
> 처분 룰 5종이 인용하는 조문은 나머지 6건에 전부 포함되므로 `check_disposal_blockers` 의
> `evidence_completeness` 실 DB 정상값은 **`COMPLETE`** 이고, `build_evidence_bundle` 은
> 9자산 × SALE/SCRAP **18조합 전부 `status:"ok"`**(`law_text_unavailable` 0건)다.
> **이 미수집 경로가 다시 발화하는 때**: 새 조문을 등록했는데 아직 안 받았을 때 ·
> 개정으로 `pending_revisions` 가 열렸을 때 · `KR-CITA-ENF-31` 처럼 정체성 대조에 실패했을 때.

**다음 액션 (Sprint 7 Stage 7 → Sprint 8)**

1. ✅ ~~**사람** — `related_parts` 최종 승인~~ — **2026-08-12 완료.** 부품 특정 정확률이 "판정 불가" → **"미달 40.0%"**(목표 ≥90%) 로 바뀌었다 (D12 해제)
2. ✅ ~~**사람** — 처분 승인서·진술보장서 **문안 검수**~~ — **2026-08-13 완료.** 19시나리오(판정 5종 전부) 렌더링본을 확인하고 **수정 없이 승인**. 출력 키가 `unreviewed_template_notice` → **`template_review_notice`** 로 바뀌었다 (**D90**) — 값이 "검수 완료"가 되는데 키에 `unreviewed` 가 남으면 자기모순이다
3. 🟡 **사람** — `KR-CITA-ENF-31` 등록 제목 정정 승인(`즉시상각의제` → API 값 `즉시상각의 의제`). 계층 1 의 마지막 `PENDING` 이며 `classify_expenditure` 전용이라 **S10 에는 영향이 없다**
4. ✅ ~~**사람** — `parts.part_class` 40종 감수~~ — **2026-08-13 완료.** 40종 전량 확인 후 **초안 그대로 승인**(변경 0건). `assess_repair_value` 3지 판단을 실적으로 인용할 수 있다 (`seed.py` 의 `PART_CLASS_REVIEWED = True`)
5. ✅ ~~**사람** — 기준내용연수 `N` 법령 원문 대조~~ — **2026-08-13 완료.** 별표서식 API 로 **별표6** 실수집 대조 → 업종을 KSIC **`29`** 로 고정하고 **`N = 8 → 10`**(별표6 제5호) 정정 (**D89**). 3지 판정은 27조합 중 1건만 이동. ⚠ `RESIDUAL_AT_LIFE_END=0.50`·`FLOOR=0.10` 은 여전히 **가정**이다
6. ~~**MQ-713/714** — 지표 튜닝~~ — **종료.** 코드 축(A·C) 채택 · 프롬프트 축(A′·B)과 루프 축(MQ-714) **전부 기각·원복**. 판정 규칙은 `--repeat 3` 의 `안정실패 → 안정통과` 승격 칸 수. ⛔ `MAINTQ_TOOLS_PROFILE=full` 로 평가하지 않는다 (D88 이 코드로 막는다)
7. **Sprint 8** — `create_repair_record`(P25·S19). 계약 자리는 `GET /api/approvals` 의 `kind: "repair"`(현재 항상 0건)로 확보돼 있다

> **사람 검수 3건이 풀렸다** — `related_parts`(08-12) · `parts.part_class`(08-13) ·
> **기준내용연수 `N`**(08-13, D89). 남은 것은 **문안 검수**(2번)와 `KR-CITA-ENF-31`
> **제목 정정**(3번)이다.
>
> ⚠ **`N` 이 확정됐다고 잔가곡선이 실측이 된 것은 아니다** — `RESIDUAL_AT_LIFE_END=0.50`·
> `FLOOR=0.10` 은 근거 미확보 **가정**으로 남아 있고 D74·D65 의 추정치 고지는 유지된다.
> 문안 검수 자료는 `data/analysis/disposal_docs_review.md` 에 19시나리오(판정 5종 전부) 뽑아 뒀다.

사람이 해야 할 일 전체는 [../TODO_직접할일.md](../TODO_직접할일.md).

<details><summary>지난 이력</summary>

설계 검토·정합화 완료(2026-07-18, D20~D23) → M1(데이터 준비). 문서 정합성 2차 점검(2026-07-23)에서 계약 구멍 5건 보완 → **D28~D32**, MVP 범위 문서화 + 발주서 추적 필드 → **D33·D34**, 프론트 구현에서 발견한 block 계약 누락 → **D35**.
매뉴얼 3종 확보 + 스파이크 SP1(표 추출) 완료 → D24~D27. `error_codes` = **65건**(iG5A 24 / S100 41, 2026-07-28 사람 승인 후 적재), 두 기종 공통 표기 코드 12종 확보(D6 "같은 코드, 다른 의미" 실증).
`related_parts` 는 8코드 위임 판정(2026-08-05) 후 **사람 최종 승인 완료(2026-08-12)** — D12 게이트 해제. 실적 인용 시 위임 → 승인 두 단계를 함께 밝힐 것.

</details>
