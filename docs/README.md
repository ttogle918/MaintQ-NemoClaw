# MaintQ 문서 인덱스

**3줄 요약:** MaintQ는 인버터/PLC 설비의 **생애주기 전체**를 하나의 대화로 잇는 B2B 보전 에이전트다 — 에러 진단→부품 특정→재고·견적→발주 승인, 그리고 수리 증빙→법정 조건 검사→처분 서명까지. 주제는 도구 오케스트레이션 + **근거 기반 판단**이다. **AI는 근거를 조립하고, 사람이 서명한다.**

| 문서 | 내용 | 언제 열어보나 |
|---|---|---|
| [00_MVP_SCOPE](00_MVP_SCOPE.md) | **반드시 구현할 기능 6종 + 확장 6종 + 인프라 + 완료 기준** (목록만, 상세는 각 문서로 링크) | 착수 전 "이번에 뭘 만드나" 확인, 범위 다툼 날 때 |
| [01_OVERVIEW](01_OVERVIEW.md) | 문제정의·As-Is/CMMS 포지셔닝·페르소나·KPI·기능·OoS·리스크·마일스톤(M1~M4) | 프로젝트 전체 그림이 필요할 때, 발표 준비 |
| [02_SCENARIOS](02_SCENARIOS.md) | S1(순차)·S2(분기)·S3(이력+가드레일)·S4(실패 처리) + 도구 시퀀스 | 기능 구현 전 "이게 어느 시나리오에 복무하나" 확인 |
| [03_WIREFRAME](03_WIREFRAME.html) | 화면 A(진단 콘솔)·A-2(S3 변형)·B(승인 큐) + 주석 10개. **구조 참조 — 실제 화면은 frontend/ 구현이 기준** | UI 작업 전, 디자인 검수 |
| [04_MCP_TOOLS](04_MCP_TOOLS.md) | **코어 7종(읽기 6+쓰기 1) + 확장 7종(§8~§14)** 입출력 계약, 프로파일 게이트(D69), 설계 원칙 6개 | 도구 구현·수정 시 (계약 임의 변경 금지) |
| [05_DB_SCHEMA](05_DB_SCHEMA.md) | 테이블 **17절(CREATE TABLE 18개)** + 시드 케이스 맵 7종 | DB·시드 작업 시 |
| [06_REPO_API](06_REPO_API.md) | 모노레포 구조, REST/SSE 규격(이벤트 4종), **`/api/assets` 3종 + D71 HTTP 매핑**, 상태 전이, testset 스키마 | 폴더·엔드포인트 만들 때, M1 첫날 |
| [07_BACKLOG](07_BACKLOG.md) | v2 기능 P1~P21 + **확장 범위 P22~P27(진행 표시)** + **P28·P29 인프라** + 아이디어 주차장 + 경계 메모 | "이것도 넣을까?" 싶을 때 (답: 백로그로) |
| [08_DESIGN_BRIEF](08_DESIGN_BRIEF.md) | Claude Design 투입 프롬프트 + 검수 체크리스트 | 하이파이 디자인 뽑을 때 |
| [09_RUNTIME](09_RUNTIME.md) | S1 시퀀스 다이어그램, 에이전트 루프 정책, 장애 모드, 스파이크 3종 | 에이전트 루프·SSE 구현 시, 개발 착수 직전 |
| [10_DECISIONS](10_DECISIONS.md) | 설계 결정 D1~D80 + 이유 | "왜 이렇게 했지?" 싶을 때, 설계 변경 전 필독 |
| [11_ASSET_LIFECYCLE](11_ASSET_LIFECYCLE.md) | 처분 법정 조건 · **근거 3계층** · 룰 5종 · S9·S10·S18 | 처분·취득 기능 작업 시, "근거를 어떻게 남기나" 확인할 때 |
| [12_MAINT_VALUE](12_MAINT_VALUE.md) | 보전지표 · 수리 이력의 자산가치 · 중고 거래 배경 · S1+·S19 | 수리 판단·증빙 기능 작업 시 |

**규칙:** 설계와 다른 구현을 하려면 10_DECISIONS에 결정을 먼저 추가하고 진행한다. 새 기능 아이디어는 07_BACKLOG로 보낸다.

**범위가 넓어졌다 (D67).** `11`·`12`는 이제 본 범위다 — 당초 Phase 2로 미뤄 둔 것(D58)을 열었다. 단 **순서는 그대로** — 완료 기준 5개와 S1~S4 관통이 먼저고, 그다음 근거 계층, 그 위에 나머지가 얹힌다. 룰 카탈로그는 `data/rules/` 에 있다(pytest 통과, **법령 원문은 수집 대기 — `LAW_API_OC` 미발급**).

---

## 진행 상태 (Sprint 6 종료 시점 · 2026-08-09)

**M1~M4 는 완주했고, Sprint 6 에서 확장 범위(F1·F2·F4)를 열었다.**

| 축 | 상태 |
|---|---|
| 코어 도구 7종 · 백엔드 · 에이전트 루프 · trace · UI 2종 · 평가 하네스 | ✅ 동작 |
| **확장 도구 7종** (`check_disposal_blockers` · `verify_ownership` · `classify_part_criticality` · `get_maintenance_metrics` · `classify_expenditure` · `assess_repair_value` · `build_evidence_bundle`) | ✅ 구현 — 계약은 `04 §8~§14`. **노출은 `MAINTQ_TOOLS_PROFILE=full` 에서만**(기본 `core`, D69) |
| DB | 코어 11 + 확장 7 = **테이블 18개**. `assets` 신설(D68) · `assets.insured` 신설(D78) |
| 룰 카탈로그 | 5종 전부 **트리거 정합**(D77·D78) — 판정 5종(`BLOCKED`/`HOLD`/`INSUFFICIENT_FACTS`/`CONDITIONAL`/`CLEAR`, D79)이 시드에서 전부 도달 가능 |
| REST | `GET /api/assets` · `GET /api/assets/{id}` · `POST /api/assets/{id}/disposal/precheck`(무저장, D71) |
| 잔가곡선 | **목업 정률 공식**으로 확정(D74) — 중진공 호가로는 감가를 식별할 수 없다는 한계 실증을 `data/analysis/residual_curve.md` 에 보존 |
| 계층 1 (법령 원문) | ⛔ **미수집** — 참조 7건 전부 `fetch_status:"PENDING"`. 적용기(`apply_fetch`)는 완료(D75), **수집기(`fetch_from_api`)는 Sprint 7** |

**다음 액션 (Sprint 7)**

1. 🔴 **사람** — law.go.kr OPEN API 활용신청 → `.env` 의 `LAW_API_OC` 기입. **모든 계층 1 작업의 하드 선행 조건**이다
2. 🔴 **사람** — 기준내용연수 `N=8` 법령 원문 대조 (잔가곡선 전체가 이 값에 걸려 있다) · `parts.part_class` 40종 감수 · `related_parts` 최종 승인
3. 조문 원문 실수집 → `build_evidence_bundle` 이 `law_text_unavailable` 을 벗어난다 → 계층 3 서명 API
4. 쓰기 도구 2종(`generate_disposal_document` · `create_repair_record`)
5. 3차 평가 — 확장 도구를 켠 상태와 끈 상태를 **분리해서** 돌린다 (D69 가 지키려는 것)

사람이 해야 할 일 전체는 [../TODO_직접할일.md](../TODO_직접할일.md).

<details><summary>지난 이력</summary>

설계 검토·정합화 완료(2026-07-18, D20~D23) → M1(데이터 준비). 문서 정합성 2차 점검(2026-07-23)에서 계약 구멍 5건 보완 → **D28~D32**, MVP 범위 문서화 + 발주서 추적 필드 → **D33·D34**, 프론트 구현에서 발견한 block 계약 누락 → **D35**.
매뉴얼 3종 확보 + 스파이크 SP1(표 추출) 완료 → D24~D27. `error_codes` = **65건**(iG5A 24 / S100 41, 2026-07-28 사람 승인 후 적재), 두 기종 공통 표기 코드 12종 확보(D6 "같은 코드, 다른 의미" 실증).
`related_parts` 는 8코드 위임 판정 완료(2026-08-05) — **사람 최종 승인은 미완**이라 부품 특정 정확률 실적 인용 시 그 사실을 함께 밝힐 것 (D12).

</details>
