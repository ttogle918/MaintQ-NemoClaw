# Sprint 12 — S19→S29 시나리오 번호 정정(P33 해소) + 기한·위험등급 UI 노출 (Sprint 11 §7 컷 항목)

**상태**: 계획 확정(2026-08-18) — PM 계획 → tool-builder 현실성 평가(수정 필요 Y, 경미 2건 반영) → 최종 확정.
**Stage 1·2·3 완료(2026-08-18)**. 다음은 `/stage 4`(MQ-1205, 회귀 확장 + 기준선 갱신 + 문서 마감 — 마지막 스테이지).

**수립**: 2026-08-18 · **부제**: 전사 시나리오 번호 충돌을 정리하고, Sprint 11이 명시적으로 미룬 조회 전용 화면 2개를 연다

**근거 문서**: `docs/07_BACKLOG.md`(P33) · `docs/sprints/sprint-11.md §7`(UI 노출 컷) · `TODO_직접할일.md`
(`## Q 시리즈 전사 정합`) · `../A2A_Q/11_A2A_SCENARIOS.md`(외부, 참고) · `docs/02_SCENARIOS.md` ·
`docs/04_MCP_TOOLS.md §17·§18` · `docs/06_REPO_API.md`(asset_monitoring 절) · `data/deadlines.py` ·
`data/risk_grade.py` · `frontend/lib/maintValue.ts`(표시 매퍼 선례) · `spikes/ui_honesty_contract.py`

**제약으로 읽은 결정**: D9 · D10 · D15 · D50 · D62 · D64 · D69 · D71 · D73 · D80 · D87 · D88 · D101 · D102

---

## 0. 왜 지금 이 스프린트인가

**두 갈래 배경이 합쳐진 스프린트다.**

**갈래 1 — P33 해소.** MaintQ가 로컬로 붙인 `S19`(수리 증빙 서명)가 Q 시리즈 전사 지도의
`S19`(FinAllQ 기업 고객 온보딩, 구현 완료)와 충돌한다는 사실이 2026-08-14 발견됐고
(`docs/07_BACKLOG.md` P33), 세 프로젝트가 번호 체계를 공유하므로 MaintQ 혼자 정할 수 없어
`TODO_직접할일.md`에 "🔴 사람 협의 필요"로 대기 중이었다. `../A2A_Q/MaintQ_시나리오맵.html`
(크로스 프로젝트 지도)이 MaintQ의 수리 증빙 서명 시나리오를 **이미 `S29`로 쓰고 있다** —
전사 지도가 `S19`는 FinAllQ에, `S24~S28`은 InsuQ에 이미 배정해 둬 남는 첫 번호가 `S29`이기
때문이다. 2026-08-18 사용자가 "시나리오 29번대로 가자"로 확정했다 — **MaintQ 문서의 `S19`를
`S29`로 정정**한다. 영향 범위는 문서뿐이다 — P33 원문이 이미 "번호는 문서에만 있고 DB·도구
계약·enum에는 없다"고 밝혀 뒀으므로 회귀·계약 변경이 없다.

**갈래 2 — Sprint 11 §7 컷 해제.** Sprint 11(D102)이 `track_deadlines`(§17)·`assess_risk_grade`
(§18) 2개 읽기 전용 도구와 그 REST 노출(`GET /api/deadlines`·`GET /api/buildings/{id}/risk-grade`·
`GET /api/assets/{id}/risk-grade`, D73 — `core` 프로파일에서도 동작)까지 전부 완결했지만,
§7이 "UI 노출 없음 — 화면은 이번 범위에 없다. Sprint 12+ 백로그 후보로 남긴다"고 명시적으로
컷했다. 데이터·산출 로직·REST 전부 이미 존재하므로 이번 스프린트는 **화면만** 만든다 —
새 백엔드 엔드포인트·새 산출 로직·새 DB 컬럼은 하나도 없다.

두 갈래는 파일 영역이 완전히 분리돼 병렬 진행이 가능하다(§5 참고).

---

## 1. 이번 스프린트가 편입하는 것 / 컷 유지하는 것

| 편입 | 컷 유지 |
|---|---|
| `S19`→`S29` MaintQ 문서 전수 정정(살아있는 문서) + 역사 기록 forward-reference | 역사 세션 로그(`docs/sessions/*.md` 8개) — 원문 불변 |
| `track_deadlines`/`assess_risk_grade` 조회 전용 화면 2개(`/manager/deadlines`·`/manager/risk-grade`) | 새 백엔드 엔드포인트·새 산출 로직 — Sprint 11 산출물 재사용만 |
| 자산 하이라이트 대시보드 → 기한 화면 크로스링크 1개 | 전역 내비게이션 허브 메뉴 신설 — 기존 "독립 라우트 + 딥링크" 관행(`/manager/expenditure` 선례) 유지 |
| — | 기한·위험등급의 쓰기 경로(자동 반영·알림 발송) — 절대 규칙 1(쓰기 도구 3종 고정)이 원천 차단 |

---

## 2. 블로커 점검

MaintQ 블로커 체크리스트(`error_codes` 사람 승인 · `related_parts` 검수 · `ANTHROPIC_API_KEY` ·
임베딩·벡터스토어 미결) — **전부 해당 없음**.

- Task 1(S19→S29)은 순수 문서 편집이라 어떤 블로커도 거치지 않는다.
- Task 2(UI 노출)는 `GET /api/deadlines`·`GET /api/buildings/{id}/risk-grade`·
  `GET /api/assets/{id}/risk-grade` 3경로만 호출한다. 이 경로들은 `data.deadlines`/
  `data.risk_grade`만 읽고 에러코드 룩업·RAG·에이전트 루프를 전혀 거치지 않으며, Sprint 11
  MQ-1105에서 `core` 프로파일(D73) 동작이 이미 실측 확인됐다.

---

## 3. 사전 조사 요약 (PM)

- **P33 충돌 범위** — `rg -l "S19" docs/ CLAUDE.md README.md`(루트) 결과 **22개 문서**에서 발견.
  `CLAUDE.md`·루트 `README.md`에는 없음(확인 완료). `spikes/repair_flow_contract.py:2` 독스트링에도
  1건(순수 주석, 회귀 판정 로직과 무관).
- **살아있는 문서 중 실제 `S19` 표기 지점**(전부 순수 텍스트 치환 대상): `docs/02_SCENARIOS.md:82` ·
  `docs/12_MAINT_VALUE.md:218`(절 제목) · `docs/00_MVP_SCOPE.md:188` · `docs/04_MCP_TOOLS.md:891·1149` ·
  `docs/06_REPO_API.md:476` · `docs/07_BACKLOG.md:47·90`(P25·P33 행) · `docs/README.md:9·19·102·113·115` ·
  `docs/status/maintq-status.html:292·413·608~610·735·808` · `docs/status/maintq-diagrams.html:237·286` ·
  `docs/status/maintq-data-map.html:519·822` · `TODO_직접할일.md:238~252`.
  - ⚠ `docs/status/*.html` 3종은 오늘 세션에서 Sprint 11 반영은 끝났지만 S19→S29 정정은 아직 안 됨 —
    `maintq-status.html:610`이 "권장안은 `S29`로 이동"이라고 **서술은 하면서 정작 옆의 `S19` 라벨
    자체는 안 바꾼** 상태를 실측으로 확인. `:605~613`은 아직 "🔴 사람 승인 대기" 카드로 남아 있다.
- **역사 기록**(그대로 둠, forward-reference만): `docs/sessions/*.md` 8개 — 전부 미터치.
  `docs/sprints/sprint-6~10.md` — 당시엔 정확한 서술이었으므로 텍스트 보존, forward-reference 1줄만
  추가(선례: `sprint-9.md:785` "Sprint 9 시점 — Sprint 11이 이후 다시 11개·18개로 갱신했다" 패턴).
- **블로커 체크리스트**(§2) — 두 태스크 모두 해당 없음.
- **Task 2 재사용 확인** — REST 3경로·`data/deadlines.py`·`data/risk_grade.py` 전부 이미 동작(Sprint 11
  완료). `GET /api/assets`가 `SELECT a.*`로 이미 `building_id`를 응답에 포함하지만
  (`backend/services/disposal.py:130~133`), `frontend/lib/api.ts`의 `ApiAsset` 타입에는 아직 명시
  필드가 없다(캐치올로만 접근 가능) — 건물 목록을 새 백엔드 엔드포인트 없이 자산 목록에서 파생할 수
  있다는 근거.
- **D87 정직성 규약 적용 지점** — `frontend/lib/maintValue.ts`(showMetric/showTrend, React·별칭
  미의존 순수 매퍼) + `frontend/components/asset/MetricsAside.tsx`(KIND_COLOR 로컬 맵, 컴포넌트에
  상태 리터럴 비교 없음)가 정확히 같은 모양의 선례 — deadlines/risk-grade도 같은 패턴을 복제한다.
- **L2 정적 스캔 자동 편입 확인** — `spikes/ui_honesty_contract.py:85`
  `L2_GLOBS = ("components/asset/*.tsx", "components/queue/Decision*.tsx", "app/(console)/**/*.tsx")`.
  신규 컴포넌트를 `components/asset/`에, 신규 페이지를 `app/(console)/`에 두면 글롭 수정 없이 자동
  스캔 대상이 된다(Sprint 10 MQ-1001 선례와 동일 — 별도 `L2_EXTRA` 등재 태스크 불필요).
- **`/manager/expenditure`(MQ-1001) 선례** — 허브 메뉴 없이 독립 라우트로 존재하고, 다른 자산 화면
  (`technician/asset/[assetId]/evidence/page.tsx:100`)에서 딥링크만 걸려 있다. 신규 두 화면도 동일
  패턴(독립 라우트 + 관련 화면에서 딥링크 1개)을 따른다.

---

## 4. 현실성 평가 (tool-builder)

**결론: 계획 수정 필요 — Y(경미, 2건).** 그 밖의 전제는 전부 실측으로 확인, PM 주장과 일치:

- `docs/sprints/sprint-9.md`의 `S19` 위치·개수, `docs/07_BACKLOG.md` P25·P33 행 위치,
  `docs/status/*.html` 3종의 현재 상태(정정 미반영), `spikes/ui_honesty_contract.py`의 `L2_GLOBS`·
  `L2_FILES_FLOOR=32`, `backend/services/disposal.py`의 `SELECT a.*`가 이미 `building_id`를
  포함하는 사실, `data/deadlines.py`의 `DEFAULT_WINDOW_DAYS=180`, `frontend/lib/maintValue.ts`/
  `MetricsAside.tsx`의 표시 매퍼 패턴 — **전부 실측 확인.**
- **파일 충돌 없음** — Stage 간·Stage 내 전부 직접 대조 확인. MQ-1201(문서 전용)과 MQ-1202
  (`frontend/lib/*`)는 완전히 분리된 파일 영역, MQ-1205(Stage 4)가 `docs/README.md`·
  `docs/06_REPO_API.md`·`docs/02_SCENARIOS.md`를 다시 건드리지만 Stage 1과 순서가 갈려 있어
  병렬 충돌이 아니다.
- **수정 필요 2건** (전부 아래 §6 최종본에 반영 완료):
  1. **MQ-1201 DoD 수치 오류** — `docs/sprints/sprint-9.md`의 `S19` 언급 건수를 계획 초안이
     "11건 그대로 유지"로 적었으나, `grep -c "S19" docs/sprints/sprint-9.md`와 `grep -o` 둘 다
     실측한 결과 **15건**이다. DoD 문구를 **"15건 그대로 유지"**로 정정했다.
  2. **MQ-1201 스코프 누락** — `docs/sprints/sprint-11.md:159`("`S19` 충돌 건과 같은 사정")도
     `S19`를 언급하는 살아있는 문서인데 계획 초안의 대상 목록(치환 대상에도, 역사 보존 대상에도)
     어디에도 없었다. **판단: forward-reference만 추가(전면 치환 아님)** — 이유는 아래 참고.

**sprint-11.md:159 처리 방향 결정 근거**: tool-builder는 "같은 세션에 작성된 현재 진행형 계획
문서라 sprint-6~10 같은 완결된 회고와는 성격이 다르다"는 의견을 냈으나, 실측 확인 결과
`docs/sprints/sprint-11.md` 상단 상태 줄이 **"전 스테이지 완료(2026-08-18) — Sprint 11 종료"**로
이미 완결·병합·푸시가 끝난 문서다(오늘 세션 배경 설명과 일치) — "현재 진행형"이 아니라 "오늘 완결된
과거 기록"이라는 점에서 sprint-6~10과 성격이 다르지 않다. 게다가 **PM 최초 계획 자체가 이미
"docs/sprints/sprint-6~11.md(당시엔 S19가 맞는 서술이었으므로 사실을 지우지 않는다)"로
sprint-11.md를 그 역사 보존 그룹에 포함시켜 뒀었다** — 즉 이번 수정은 새 판단을 도입하는 것이
아니라 최초 계획에 이미 있던 분류를 파일 목록에 실제로 반영하는 누락 교정이다. 또한
`:159`의 문장은 sprint-6~10처럼 "S19를 그 시절의 정식 명칭으로 서술"한 것이 아니라 **"S19 충돌
건과 같은 사정"이라며 그 충돌 자체를 메타적으로 참조**하는 문장이라, 문장 구조를 갈아엎지 않고
좁은 인라인 첨언만 붙이는 sprint-10.md:252 방식(원 문장 보존 + 문장 끝에 정정 사실 추가)이 더
정확하게 들어맞는다. 전면 치환하지 않는 이유: sprint-11.md 본문이 "그 시점엔 전사 지도에 `S19`
충돌이 있었다"는 사실을 서술한 것이므로, `S19`를 지우면 "그 스프린트가 왜 새 S번호를 안 만들고
기존 S9·S18에 얹기로 했는지"의 근거 문장이 실제로 있었던 사실과 달라진다.

---

## 5. 스테이지 계획 (확정)

### Stage 1 (병렬)
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1201 | S19→S29 문서 전수 정정 (P33 해소) | `docs/02_SCENARIOS.md`·`docs/12_MAINT_VALUE.md`·`docs/00_MVP_SCOPE.md`·`docs/04_MCP_TOOLS.md`·`docs/06_REPO_API.md`·`docs/07_BACKLOG.md`·`docs/README.md`·`docs/status/*.html`(3종)·`TODO_직접할일.md`·`docs/sprints/sprint-6~10.md`(forward-ref만)·`docs/sprints/sprint-11.md:159`(forward-ref만, 인라인)·`spikes/repair_flow_contract.py`(주석, 선택) | — |
| MQ-1202 | 기한·위험등급 프론트 데이터 계층 (API 클라이언트 + 표시 매핑) | `frontend/lib/api.ts`(수정)·`frontend/lib/deadlines.ts`(신규)·`frontend/lib/riskGrade.ts`(신규)·`frontend/lib/__checks__/ui_honesty.ts`(수정) | — |

### Stage 2
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1203 | 컴포넌트 2종 — `DeadlinesPanel`·`RiskGradeGrid` | `frontend/components/asset/DeadlinesPanel.tsx`(신규)·`frontend/components/asset/RiskGradeGrid.tsx`(신규) | MQ-1202 |

### Stage 3
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1204 | 페이지 2종 + 자산 화면 크로스링크 | `frontend/app/(console)/manager/deadlines/page.tsx`(신규)·`frontend/app/(console)/manager/risk-grade/page.tsx`(신규)·`frontend/app/(console)/technician/equipment-status/[assetId]/page.tsx`(수정) | MQ-1203 |

### Stage 4
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1205 | 회귀 확장 + 기준선 갱신 + 문서 마감 | `spikes/ui_honesty_contract.py`(수정, `L2_FILES_FLOOR`)·`CLAUDE.md`(수정, 실측 기준선)·`docs/README.md`(수정, 진행상태 항목)·`docs/sprints/sprint-11.md`(수정, §7 addendum)·`docs/06_REPO_API.md`·`docs/02_SCENARIOS.md`(1줄씩 UI 참조) | MQ-1204 |

### 스테이지 구성 근거

- **Stage 1 병렬**: MQ-1201(문서 전용)과 MQ-1202(`frontend/lib/*`)는 완전히 분리된 파일 영역이다 —
  둘 다 선행 없이 동시 착수 가능. 둘 다 다른 어떤 스테이지 태스크와도 파일이 겹치지 않는다
  (MQ-1205가 나중에 `docs/README.md`·`docs/06_REPO_API.md`·`docs/02_SCENARIOS.md`를 다시
  건드리지만 **Stage 4**로 순서가 밀려 있어 병렬 충돌이 아니다).
- **Stage 2 단독**: 컴포넌트가 `lib/api.ts`의 신규 함수와 `lib/deadlines.ts`/`lib/riskGrade.ts`의
  표시 매퍼를 직접 import하므로 MQ-1202 완료가 선행이어야 한다.
- **Stage 3 단독**: 페이지는 컴포넌트를 조립만 하므로 MQ-1203 완료 후. 크로스링크 대상 파일은
  이번 스프린트의 다른 어떤 태스크도 건드리지 않아 이 스테이지에 안전하게 넣을 수 있다.
- **Stage 4 마지막**: `L2_FILES_FLOOR` 갱신은 신규 파일이 전부 존재해야 정확한 실측값을 낼 수
  있고(Stage 2·3 완료 후), `CLAUDE.md` 기준선(라우트 개수·spikes 건수)도 전 계층이 붙은 뒤에만
  참값이다. 문서 마감을 먼저 하면 Sprint 11 MQ-1106이 배운 교훈("완성 전 ✅ 표시 금지")을 어긴다.
- 이월 태스크 없음(Sprint 11 완결). 블로커 우회 확인은 §2 참고.

---

## 6. 태스크별 상세 구현 명세

### MQ-1201 — S19→S29 문서 전수 정정 (P33 해소)
- **복무 시나리오**: 인프라(시나리오 번호 정합 — 어떤 S1~S4에도 직접 복무하지 않음, 문서
  정합성 작업)
- **변경 파일**:
  - `docs/02_SCENARIOS.md` — `:82` 테이블 행 `**S19**` → `**S29**`
  - `docs/12_MAINT_VALUE.md` — `:218` 절 제목 `## 7. S19 —` → `## 7. S29 —`
  - `docs/00_MVP_SCOPE.md` — `:188` `create_repair_record`(P25·S19)` → `(P25·S29)`
  - `docs/04_MCP_TOOLS.md` — `:891` 헤딩 `(S19)` → `(S29)`, `:1149` 테이블 `**S19**` → `**S29**`
  - `docs/06_REPO_API.md` — `:476` `### 2.8 수리 증빙 — 제출·서명·반려 (S19 · D85·D98, ...)` →
    `(S29 · D85·D98, ...)`
  - `docs/07_BACKLOG.md` — `:47` P25 행 `(S19)`→`(S29)`. `:90` **P33 행 전체 재작성**:
    🔴(사람 협의) → **✅ 완료(Sprint 12, 2026-08-18)**. 결론(`S29` 채택, 첫 번째 빈 번호 근거
    `../A2A_Q/11_A2A_SCENARIOS.md:98`)과 사용자 승인 사실을 남기고, 대안 ⓐⓑ 서술은 "채택안 ⓐ"로
    마무리. `:94` 부근의 "P33~P35는 전부 지금 하지 않을 것…다만 P33만은…" 문단을 "**P33은
    Sprint 12에서 해소됐다(S29 확정) — 아래는 P34·P35에만 해당한다**"로 정정
  - `docs/README.md` — `:9`·`:19` 본문 내 `S19`→`S29`. `:102`(항목 7) `(P25·S19)`→`(P25·S29)`.
    `:113`(항목 14) "🔴 사람 협의 필요" → "✅ ~~사람 협의~~ — 완료. S29로 확정(2026-08-18),
    MaintQ 문서 전수 정정 완료(Sprint 12 MQ-1201)"로 교체. `:115` "사람 승인 대기 **3건**" →
    **2건**(안전 문구 검수·A2A 파트너 자격증명만 남음, 항목 14 언급 제거)
  - `docs/status/maintq-status.html` — `:292`·`:413`·`:735` 라벨 `S19`→`S29`(문자 그대로 치환).
    `:605~613`의 이슈 카드 삭제하고 `:809`의 "✅ 해제됨" 목록에 `· S19→S29 정정 완료(P33, 08-18)`
    항목 추가. `:808` 사람 승인 대기 목록에서 "시나리오 번호 `S19` 충돌 정정 방향(P33)" 문구 제거
  - `docs/status/maintq-diagrams.html` — `:237`·`:286` `S19`→`S29`
  - `docs/status/maintq-data-map.html` — `:519`·`:822` `S19`→`S29`
  - `TODO_직접할일.md` — `:238~252` 체크박스는 이미 `[x]`(방향 결정 완료)이므로 유지하되,
    `:252` 다음에 1줄 추가: "✅ 실행 완료 — 2026-08-18 Sprint 12(MQ-1201)에서 MaintQ 문서 전수
    S29 정정 완료."
  - `docs/sprints/sprint-6.md`·`sprint-7.md`·`sprint-8.md`·`sprint-9.md` — 각 파일 상단(제목·상태
    줄 직후)에 forward-reference 1줄만 추가: `> ℹ️ 시나리오 번호 정정(2026-08-18, Sprint 12,
    P33) — 이 문서의 S19 표기는 계획 당시 번호다. 이후 S29로 정정됐다. 본문은 수립 당시 그대로
    보존한다.` 본문의 S19 표기 자체는 건드리지 않는다
  - `docs/sprints/sprint-10.md` — `:252`의 기존 인라인 경고 문구에 덧붙이기만: 문장 끝에
    "— 2026-08-18 Sprint 12에서 S29로 정정 확정" 추가(문장 재작성 금지, 추가만)
  - **`docs/sprints/sprint-11.md` — `:159`(신규 편입, §4 판단 근거 참고)** — 본문 문장은
    보존하고, `S19` 뒤에 짧은 인라인 첨언만 추가: `` `S19` `` 충돌 건과 같은 사정(→ 2026-08-18
    Sprint 12에서 S29로 정정 확정))"` 형태로 괄호 안에 forward-reference 삽입. 전면 치환하지
    않는다(이유는 §4)
  - `spikes/repair_flow_contract.py` — `:2` 독스트링 `S19`→`S29 (구 S19)` (선택, 기능 영향 없음)
- **핵심 로직**: 기계적 문자열 치환 + 상태 서술 갱신. 살아있는 문서(현재 상태를 서술)는 전부
  `S29`로 교체. 역사 기록(그 시점의 계획·실행 로그)은 본문을 지우지 않고 forward-reference만
  얹는다.
- **엣지 케이스**:
  - `docs/sessions/*.md` 8개 파일은 어떤 경우에도 편집하지 않는다 — 실행 중 이 파일들에 `S19`가
    걸리면 스킵할 것.
  - `docs/11_ASSET_LIFECYCLE.md`에는 애초에 `S19`가 없다(확인 완료) — 건드릴 것 없음.
  - `docs/status/maintq-status.html:609`처럼 P33 충돌 자체를 설명하는 역사적 서술 문장 안의
    `S19`는 그 문맥에서는 정확한 사실이므로, 카드를 삭제하며 문장째 제거되는 것이 맞다(개별
    토큰만 바꾸지 말 것).
  - `docs/sprints/sprint-11.md:159`는 **본문을 재작성하지 않는다** — 괄호 안 첨언만 추가(§4의
    판단 근거 그대로).
- **지켜야 할 결정**: 없음 — P33 원문이 이미 "번호는 문서에만 있고 DB·도구 계약·enum에는 없다"고
  명시해 새 D 결정 불필요. 순수 표기 정정.
- **DoD**:
  - `rg -n "S19" docs/02_SCENARIOS.md docs/12_MAINT_VALUE.md docs/00_MVP_SCOPE.md
    docs/04_MCP_TOOLS.md docs/06_REPO_API.md docs/07_BACKLOG.md docs/README.md
    docs/status/maintq-status.html docs/status/maintq-diagrams.html
    docs/status/maintq-data-map.html` → **0건**
  - `rg -n "S29" docs/02_SCENARIOS.md` → `:82` 1건
  - `rg -c "S19" docs/sprints/sprint-9.md` → 기존 건수(**15**) 그대로 유지(historical 텍스트
    보존 확인) + 상단에 forward-reference 신규 1건
  - `rg -n "S19" docs/sprints/sprint-11.md` → `:159` 1건 그대로 존재(본문 보존 확인) + 같은 줄에
    "S29로 정정 확정" 첨언 포함
  - 회귀: 코드·계약 변경이 없으므로 전체 스위트 재실행은 불필요. `spikes/repair_flow_contract.py`를
    건드렸다면 `uv run python spikes/repair_flow_contract.py` PASS만 확인

---

### MQ-1202 — 기한·위험등급 프론트 데이터 계층
- **복무 시나리오**: S9(처분 사전 경보 UI) · S18(실사 보존 확장 UI)
- **변경 파일**: `frontend/lib/api.ts`(수정) · `frontend/lib/deadlines.ts`(신규) ·
  `frontend/lib/riskGrade.ts`(신규) · `frontend/lib/__checks__/ui_honesty.ts`(수정)

**`lib/api.ts` 추가분**:
```ts
// ApiAsset 에 필드 추가 (기존 캐치올에서 명시 필드로 승격)
building_id: string | null;

export interface ApiDeadlineItem {
  asset_id: string;
  type: string;            // "TAX-CREDIT-2Y" | "SAFETY-INSPECTION" — 원 어휘 그대로
  law_refs: string[];
  due_date: string;
  days_remaining: number;
  state: string;           // "UPCOMING" | "IN_REVIEW_BAND" | "OVERDUE" — 원 어휘 그대로
  message: string;
  resolve_options: string[];
  [k: string]: unknown;
}
export interface ApiDeadlines {
  status: string;
  evaluated_at?: string; window_days?: number;
  items?: ApiDeadlineItem[]; not_considered?: string[]; disclaimer?: string;
  reason?: string; message?: string;
  [k: string]: unknown;
}
export const getDeadlines = (role: Role, params?: { assetId?: string; windowDays?: number }) => { /* GET /api/deadlines */ };

export interface ApiRiskGrade {
  status: string;
  building_id?: string;
  facts?: { fire_handling: string | null; hazmat_volume: string | null; power_capacity: string | null; product_type: string | null };
  current_grade?: string | null; stored_grade?: string | null; stored_grade_updated_at?: string | null;
  changed?: boolean; grade_scale?: string[]; rationale?: string;
  not_considered?: string[]; disclaimer?: string; reason?: string; message?: string;
  [k: string]: unknown;
}
export const getBuildingRiskGrade = (role: Role, buildingId: string) => { /* GET /api/buildings/{id}/risk-grade */ };
export const getAssetRiskGrade = (role: Role, assetId: string) => { /* GET /api/assets/{id}/risk-grade */ };
```
`endpoints` 객체에도 `deadlines`·`buildingRiskGrade`·`assetRiskGrade` 항목 추가(기존 관행 유지).

**`lib/deadlines.ts`(신규, React·`@/` 별칭 미의존 — `lib/maintValue.ts`와 동일 제약)**:
```ts
export type Tone = "ok" | "warn" | "error" | "unknown";
export interface StateView { label: string; tone: Tone; }
// 총 맵 1곳 — 맵 밖 값은 unknown + 원문 보존 (D87)
export function deadlineStateView(state: string): StateView;   // UPCOMING→warn · IN_REVIEW_BAND→warn(+"사람 검토 필요") · OVERDUE→error · 그외→unknown+"미상(state)"
export function deadlineTypeLabel(type: string): string;       // TAX-CREDIT-2Y→"투자세액공제 사후관리" · SAFETY-INSPECTION→"안전검사" · 그외→"미상(type)"
```

**`lib/riskGrade.ts`(신규, 같은 제약)**:
```ts
export type Tone = "ok" | "warn" | "error" | "unknown";
export interface GradeView { label: string; tone: Tone; }
// current_grade === null(미산출)과 grade 문자열 둘 다 받는다 — null 을 "LOW"로 접지 않는다 (D62)
export function gradeView(grade: string | null): GradeView;    // null→unknown+"미산출" · LOW→ok · MEDIUM→warn · HIGH→error · 그외→unknown+"미상(grade)"
```

- **핵심 로직**: `lib/maintValue.ts`의 `showMetric`/`showTrend` 패턴을 그대로 복제 — 서버 원 어휘를
  보존하며 맵 밖 값은 절대 `ok`/`warn`(정상 경고)과 같은 톤으로 떨어지지 않고 전용 `unknown` 톤 +
  원문을 반환한다(`ui_honesty.ts` L1-3·L1-9와 동일 불변식).
- **엣지 케이스**: `current_grade: null`(risk_grade.py의 3속성 중 하나라도 NULL) →
  `gradeView(null)`이 `unknown`/"미산출"을 반환해야 하며 `LOW`로 오분류되지 않아야 한다(가장 중요한
  회귀 포인트). `deadlines.state`에 계약 밖 새 어휘가 와도 컴포넌트가 깨지지 않고 `unknown`으로
  떨어진다.
- **지켜야 할 결정**: D62(모름·없음 구분) · D87(총 맵 1곳, React·별칭 미의존 → `ui_honesty` L1
  단독 컴파일 대상) · D9/D50(원 어휘 보존, 서버 어휘를 UI가 재해석해 다른 말로 지어내지 않음)
- **DoD**:
  - `lib/__checks__/ui_honesty.ts`에 L1-14(`deadlineStateView`: 맵 밖 상태 3~4종이 unknown+원문,
    `OVERDUE`≠`IN_REVIEW_BAND` 톤)·L1-15(`gradeView(null)`이 `LOW`로도 `ok`로도 안 됨 + 맵 밖 값
    검사) 추가 — 기존 13건(`L1-13`까지) + 2건 = **15건** 전부 PASS
  - `cd frontend && npx tsc lib/__checks__/ui_honesty.ts --outDir <tmp> --module commonjs
    --target es2020 --skipLibCheck && node <tmp>/__checks__/ui_honesty.js` →
    `L1-SUMMARY|PASS|총 15건 · 실패 0건`
  - `npx tsc --noEmit` 전체 통과

### Stage 1 완료 (2026-08-18)
**커밋**: `f808f39`(MQ-1201) · `939e595`(MQ-1202)

#### MQ-1201
- 구현 파일: `docs/02_SCENARIOS.md`·`docs/12_MAINT_VALUE.md`·`docs/00_MVP_SCOPE.md`·`docs/04_MCP_TOOLS.md`·
  `docs/06_REPO_API.md`·`docs/07_BACKLOG.md`·`docs/README.md`·`docs/status/*.html`(3종)·`TODO_직접할일.md`·
  `docs/sprints/sprint-6~11.md`(forward-ref/인라인 첨언)·`spikes/repair_flow_contract.py`
- 회귀: 문서 정합성 grep 9파일 0건 · `sprint-9.md` 16건(기존 15+forward-ref 1) · `sprint-11.md:159`
  존재+첨언 확인 · `spikes/repair_flow_contract.py` 19건 · 코드 계약 무변경(회귀 스위트 영향 없음).
- reviewer: **PASS** — `docs/07_BACKLOG.md:90`의 잔존 `S19` 11회 전부 과거 사실 서술·인용문으로
  확인(치환 누락 아님). 역사 문서(sprint-6~9) 본문 무변경, `docs/sessions/*.md` 8개 미편집 확인.
  ⚠ 정보성: `frontend/` 코드 주석 4곳(`api.ts:793`·`RepairDetail.tsx:23`·`mappers.tsx:177`·
  `types.ts:31`)에 `S19` 잔존 — 이번 태스크 범위 밖(Sprint 9·10 산출물), 후속 정리 대상으로 기록.

#### MQ-1202
- 구현 파일: `frontend/lib/api.ts`(수정)·`frontend/lib/deadlines.ts`(신규)·`frontend/lib/riskGrade.ts`(신규)·
  `frontend/lib/__checks__/ui_honesty.ts`(수정)
- 회귀: `ui_honesty.ts` L1-14·L1-15 신규 — 총 15건 전부 PASS. `npx tsc --noEmit` clean.
- reviewer: **PASS** — `gradeView(null)`이 `LOW`로 오분류 안 됨(명시적 `null` 얼리 리턴 확인, D62),
  두 신규 파일 React·`@/` 별칭 미의존 확인(D87), 서버 어휘(`data/deadlines.py`·`data/risk_grade.py`)와
  프론트 매핑 테이블 정확히 일치, `ApiAsset.building_id` 타입 승격이 백엔드 `SELECT a.*` 응답과 정합.

---

### MQ-1203 — 컴포넌트 2종
- **복무 시나리오**: S9 · S18
- **변경 파일**: `frontend/components/asset/DeadlinesPanel.tsx`(신규) ·
  `frontend/components/asset/RiskGradeGrid.tsx`(신규)

**`DeadlinesPanel`**:
```tsx
"use client";
export function DeadlinesPanel({ assetId }: { assetId?: string }): JSX.Element
```
- 상태: `windowDays`(기본 **180** — `data/deadlines.py`의 `DEFAULT_WINDOW_DAYS`와 일치시킨다),
  `data`, `loading`, `failure`.
- 프리셋 버튼 4개: **180(기본)·365·500·730** — 버튼 클릭 시 `getDeadlines("manager", { assetId,
  windowDays })` 재호출. 자유 숫자 입력은 이번 스코프에 넣지 않는다(범위 최소화).
- `items.length === 0`일 때 — 정직한 빈 상태를 명시적으로 렌더: "선택한 범위(N일) 내 임박한 법정
  기한이 없습니다. 범위를 넓혀 확인할 수 있습니다." (성공색·체크마크 없이 중립 톤, D62 — "없다"를
  "정상"으로 포장하지 않는다).
- 항목 렌더: `asset_id`·`deadlineTypeLabel(type)`·`due_date`·`days_remaining`·
  `deadlineStateView(state)`(로컬 `TONE_COLOR: Record<Tone,string>` 맵을 통해서만 색상 결정,
  `MetricsAside.tsx`의 `KIND_COLOR` 패턴 그대로)·`message`.
- `not_considered`·`disclaimer`는 `MetricsAside.tsx`의 `<details>` 접이식 패턴 재사용.
- 로딩/실패 처리는 `MetricsAside.tsx`와 동일(`ApiError`·`errorBody`·`extractDetail`).

**`RiskGradeGrid`**:
```tsx
"use client";
export function RiskGradeGrid(): JSX.Element
```
- 1) `getAssets("manager")` 호출 → 응답에서 `building_id` 고유값 추출(null 제외, 정렬).
- 2) 각 `building_id`에 대해 `getBuildingRiskGrade("manager", id)`를 `Promise.all`로 병렬
  호출(`technician/equipment-status/page.tsx`의 자산별 병렬 조회 패턴 재사용).
- 3) 건물별 카드: `building_id`·3속성(화기취급·위험물보관량·수전용량, 라벨은
  `data/risk_grade.py`의 `_SCORED_ATTRS` 한글 라벨과 동일하게 하드코딩) +
  `gradeView(current_grade)`와 `gradeView(stored_grade)` 나란히 표시 + `rationale` 문장(서버가
  조립한 문장을 그대로 표시, UI가 재작성 안 함).
- 4) `changed === true`일 때 — 중립 톤 알림("산출 결과가 마지막 저장 등급과 다릅니다 — 자동
  반영되지 않으며 갱신 여부는 사람이 판단합니다") — 경고색은 쓰되 "오류"로 읽히지 않게 문구
  설계. 아무 버튼도 달지 않는다(쓰기 경로 자체가 없음, D10).
- 5) 건물 목록이 0개(자산에 `building_id`가 전부 null)이거나 `getAssets` 실패 시 정직한
  빈/실패 상태.
- **엣지 케이스**: `getBuildingRiskGrade`가 개별 건물에서 `404 unknown_building`을 반환해도
  전체 그리드를 죽이지 않고 그 카드만 실패 표기(`Promise.allSettled` 사용 권장).
- **지켜야 할 결정**: D87(컴포넌트에 상태 문자열 리터럴 비교·색 토큰 직접 대입 금지 — 전부
  `deadlineStateView`/`gradeView`를 거친 로컬 `TONE_COLOR` 맵으로만) · D64(퍼센트 진행바·랭킹
  정렬 금지 — 점수 숫자는 `rationale` 문장 안에서만 노출, 별도 스코어바 안 만듦) · D10(쓰기
  버튼 없음).
- **DoD**: `npx tsc --noEmit` 통과. 로컬 백엔드 기동 후 수동 확인: `DeadlinesPanel`을
  `windowDays=500`으로 열면 `AST-L2-SPDL` 1건 `UPCOMING` 렌더. `RiskGradeGrid`에서 `BLD-C`가
  `changed=true` 알림과 함께, `BLD-A`는 알림 없이 렌더.

### Stage 2 완료 (2026-08-18)
**커밋**: `0bca340`

#### MQ-1203 (+ Stage 1 결함 수정)
- 구현 파일: `frontend/components/asset/DeadlinesPanel.tsx`(신규)·`RiskGradeGrid.tsx`(신규)·
  `spikes/ui_honesty_contract.py`(수정 — L1 건수 13→15 정정, 제약 게이트 C5~C8 신설)
- **Stage 1(MQ-1202)이 남긴 실제 결함 발견·수정**: `ui_honesty_contract.py`가 여전히 L1 건수를
  13건으로 하드코딩하고 있어(실제 15건) 그대로 두면 반드시 FAIL — Stage 1 회귀 때 이 스위트를
  안 돌려서 놓쳤던 것. `constraint_gate()` 헬퍼로 C1~C4 로직을 파라미터화해 C5~C8(신규
  `deadlines.ts`·`riskGrade.ts`용) 재사용 — 새 판정 로직 없이 순수 확장.
- 회귀: `ui_honesty_contract.py` **240/240**(L1 15·L2 204·게이트 8·뮤턴트 8) · seed 35 · sp2 20 ·
  write_tool 30 · api_contract 28 · sp3 22 · ruff clean · tsc clean — 오케스트레이터가 tool-builder
  보고를 그대로 믿지 않고 독립 재실행해 확인.
- reviewer: **PASS** — D87(색상은 전부 `deadlineStateView`/`gradeView`→`TONE_COLOR` 경유, 리터럴
  비교 없음) · D64(진행바·랭킹 없음, 점수는 `rationale` 안에서만) · D10(`RiskGradeGrid`에 쓰기
  액션 전무) · D62(빈 상태·`gradeView(null)` 중립 톤 확인) 전부 검증. `TONE_COLOR.ok`가 `--ok`
  대신 `--blue-tx`를 쓴 것은 `RepairDetail.tsx`의 `HashVerified` 선례와 일치함을 확인. 정보성
  1건(JSDoc 절 번호 오기 §14/§15→§17/§18) 발견해 커밋 전 직접 정정.

---

### MQ-1204 — 페이지 2종 + 크로스링크
- **복무 시나리오**: S9 · S18 (읽기 전용 — 승인·서명 없음)
- **변경 파일**: `frontend/app/(console)/manager/deadlines/page.tsx`(신규) ·
  `frontend/app/(console)/manager/risk-grade/page.tsx`(신규) ·
  `frontend/app/(console)/technician/equipment-status/[assetId]/page.tsx`(수정)

**`manager/deadlines/page.tsx`**: `manager/expenditure/page.tsx`와 동일한
`ConsoleFrame`/`ConsoleHeader` 셸("조회 전용 화면 — 아무것도 기록하지 않습니다" 안내 문구
재사용). `useSearchParams()`로 `?asset_id=` 선택적 읽기 → `<DeadlinesPanel assetId={...} />`.

**`manager/risk-grade/page.tsx`**: 동일 셸, `<RiskGradeGrid />` 렌더. 파라미터 없음(항상 전체
건물).

**크로스링크**: `technician/equipment-status/[assetId]/page.tsx`의 기존 "← 목록" 줄 옆에 링크
1개 추가:
```tsx
<Link href={`/manager/deadlines?asset_id=${encodeURIComponent(assetId)}`}>기한 확인 →</Link>
```
(`technician/asset/[assetId]/evidence/page.tsx:100`이 `/manager/expenditure`로 넘어가는 것과
동일한 크로스-역할 딥링크 패턴.)

- **엣지 케이스**: 두 페이지 다 역할 게이트가 없다(백엔드 라우터가 `require()`를 호출하지
  않음, D73) — 프론트도 role 파라미터를 `"manager"`로 고정 호출하되 403을 다루는 코드를 넣지
  않는다.
- **지켜야 할 결정**: D71(무저장 화면 안내 문구) · D73(REST가 `core` 프로파일에서도 동작 — 화면이
  `MAINTQ_TOOLS_PROFILE`에 의존하지 않음을 재확인).
- **DoD**: `npx next build` → 프론트 라우트 **16 → 18**(신규 `page.tsx` 2개).
  `MAINTQ_TOOLS_PROFILE` 미설정(core) 상태의 로컬 백엔드로 두 라우트 정상 렌더 확인(수동).

### Stage 3 완료 (2026-08-18)
**커밋**: `a66bc5e`

#### MQ-1204
- 구현 파일: `frontend/app/(console)/manager/deadlines/page.tsx`(신규)·`manager/risk-grade/page.tsx`(신규)·
  `technician/equipment-status/[assetId]/page.tsx`(수정, 크로스링크 1개)
- **구현 편차(계약 변경 아님)**: 명세의 `useSearchParams()` 훅 대신 기존 코드베이스 관행(`technician/
  page.tsx`가 이미 쓰는 `searchParams` prop 패턴)을 채택 — App Router의 `<Suspense>` 경계 요구를
  피하기 위함. 리뷰에서 `?asset_id=X` 방문 시 `DeadlinesPanel`까지 값이 정확히 전달됨을 코드로 확인,
  출력 동작 차이 없음.
- 회귀: `next build` 라우트 16→18 · `ui_honesty_contract` L2 204→216(+12, 신규 page 2개×6건)
  232/232 PASS · seed 35 · sp2 20 · write_tool 30 · api_contract 28 · sp3 22 · ruff/tsc clean —
  오케스트레이터 독립 재실행 확인. `core` 프로파일 실서버로 `/manager/deadlines`·`/manager/risk-grade`
  200 렌더 확인(curl + 컴파일된 JS 번들 대조로 크로스링크 존재도 확인).
- reviewer: **PASS** — D71(무저장 안내 문구) · D73(역할 게이트 부재) · 크로스링크 정확성(기존
  "← 목록" 손상 없음, `evidence/page.tsx` 선례와 스타일 일관) · 페이지가 새 API/상태 로직 없이
  Stage 2 컴포넌트에 전적 위임 확인.

---

### MQ-1205 — 회귀 확장 + 기준선 갱신 + 문서 마감
- **복무 시나리오**: S9 · S18 (+ 인프라: 회귀·기준선)
- **변경 파일**: `spikes/ui_honesty_contract.py`(수정) · `CLAUDE.md`(수정) ·
  `docs/README.md`(수정) · `docs/sprints/sprint-11.md`(수정) · `docs/06_REPO_API.md`(수정) ·
  `docs/02_SCENARIOS.md`(수정)

**검증·갱신 항목**:
1. `spikes/ui_honesty_contract.py`의 `L2_FILES_FLOOR`를 실측으로 갱신 — 예상치(신규 4파일:
   `components/asset/DeadlinesPanel.tsx`·`RiskGradeGrid.tsx` + `app/(console)/manager/deadlines
   /page.tsx`·`manager/risk-grade/page.tsx`, 기존 관행상 파일당 6건이므로 32 → **36 근사**)를
   실제 실행 결과로 확정하고 주석에 산술 근거를 남긴다(기존 관행 그대로).
2. `CLAUDE.md`의 "실측 기준선" 문단 갱신: 프론트 라우트 **16개→18개**, `spikes` **30스위트**
   (변동 없음, 신규 스위트 없음) 총 건수 중 `ui_honesty_contract` 항목을 새 실측치로,
   `L2_FILES_FLOOR` 델타 설명 1문단 추가(기존 서술 스타일 — "102→114→186→222"에 이어
   "222→N" 항목 추가).
3. `docs/README.md`의 "진행 상태" 섹션에 항목 추가: "✅ ~~**Sprint 12** — S19→S29 정정(P33 해소)
   + `track_deadlines`/`assess_risk_grade` UI 노출~~ — 완료." Sprint 11 항목(10번)의 "UI 노출은
   명시적으로 컷 — 다음 스프린트 후보" 문구를 "→ **Sprint 12에서 노출 완료**"로 정정.
4. `docs/sprints/sprint-11.md` §7("이번 스프린트가 명시적으로 컷한 것")의 "UI 노출 없음" 항목에
   addendum 1줄: "→ **Sprint 12(MQ-1203·1204)가 노출했다** — `/manager/deadlines`·
   `/manager/risk-grade`."
5. `docs/06_REPO_API.md`의 기한·위험등급 REST 절에 1줄 추가: "UI: `/manager/deadlines`·
   `/manager/risk-grade` (Sprint 12)."
6. `docs/02_SCENARIOS.md`의 S9·S18 확장 시퀀스 행 끝에 각각 짧은 UI 참조 추가(예: S9 행 끝에
   "· UI: `/manager/deadlines`").
7. 전체 회귀 재실행: **30스위트**(`spikes/*.py`) 전부 + `pytest data/rules/test_rules.py`
   (무변경 확인) + `ruff check`. Windows 소켓 고갈로 실패가 나오면 해당 스위트만 단독 재실행해
   재확인하고 결과에 기록(CLAUDE.md 경고 절차 그대로 따름).
- **엣지 케이스**: `L2_FILES_FLOOR` 예상치(36)와 실측이 다르면 실측을 채택하고 실행 로그에 차이를
  설명한다 — 암산이 아니라 실행 결과를 옮겨 적는다(기존 관행).
- **지켜야 할 결정**: CLAUDE.md "부재 검사엔 liveness 앵커" 원칙(해당 없음 — 이번 태스크는 신설
  검사가 아니라 카운트 갱신) · D88(평가 실적은 `core`에서만 — 회귀 재실행 시 실수로 `full`
  프로파일 셸 변수가 남아있지 않은지 확인).
- **DoD**:
  - `ls spikes/*.py` 개수와 스위트 실행 로그 개수 **30개 일치**(신규 스위트 없음, 기존 30개
    전부 PASS)
  - `L2_FILES_FLOOR` 갱신 후 `uv run python spikes/ui_honesty_contract.py` PASS
  - `CLAUDE.md`의 라우트 개수·`ui_honesty_contract` 건수가 실측과 일치(`npx next build`
    로그 대조)
  - `rg -n "다음 스프린트 후보" docs/sprints/sprint-11.md` → §7 문맥에서 addendum이 그 뒤에
    붙어 있음을 확인
  - `uv run ruff check`, `uv run --with pytest python -m pytest data/rules/test_rules.py -q`
    통과

---

## 7. 이번 스프린트가 명시적으로 컷한 것

- **새 백엔드 엔드포인트 없음** — `GET /api/deadlines`·`GET /api/buildings/{id}/risk-grade`·
  `GET /api/assets/{id}/risk-grade` 3경로는 Sprint 11 MQ-1105 산출물을 그대로 재사용한다.
- **새 산출 로직·새 DB 컬럼 없음** — `data/deadlines.py`·`data/risk_grade.py`는 무변경.
- **전역 내비게이션 허브 메뉴 없음** — `/manager/expenditure` 선례대로 독립 라우트 + 딥링크
  1개(크로스링크)만 둔다.
- **기한 화면의 자유 숫자 입력 없음** — 프리셋 버튼(180/365/500/730)만. 임의 값 입력 UI는
  범위 밖(스코프 최소화).
- **쓰기·승인 경로 없음** — 두 화면 다 조회 전용. `changed=true` 알림에도 "반영" 버튼을 달지
  않는다(절대 규칙 1).
- **새 D 결정 없음** — P33 해소는 순수 문서 표기 정정이라 계약·DB·enum 변경이 없다.
- **`detect_law_revision`(S17) 미포함** — Sprint 11이 이미 확정한 제외를 이번 스프린트가 다시
  열지 않는다.

---

## 참고 파일 경로

`docs/07_BACKLOG.md`(P33) · `docs/sprints/sprint-11.md` · `TODO_직접할일.md` ·
`docs/02_SCENARIOS.md` · `docs/12_MAINT_VALUE.md` · `docs/00_MVP_SCOPE.md` ·
`docs/04_MCP_TOOLS.md` · `docs/06_REPO_API.md` · `docs/README.md` · `docs/status/maintq-status.html` ·
`docs/status/maintq-diagrams.html` · `docs/status/maintq-data-map.html` ·
`docs/sprints/sprint-6.md`~`sprint-10.md` · `spikes/repair_flow_contract.py` ·
`data/deadlines.py` · `data/risk_grade.py` · `backend/routers/asset_monitoring.py` ·
`backend/services/asset_monitoring.py` · `backend/services/disposal.py` ·
`frontend/lib/api.ts` · `frontend/lib/maintValue.ts` · `frontend/lib/__checks__/ui_honesty.ts` ·
`frontend/components/asset/MetricsAside.tsx` ·
`frontend/app/(console)/technician/equipment-status/page.tsx` ·
`frontend/app/(console)/technician/equipment-status/[assetId]/page.tsx` ·
`frontend/app/(console)/manager/expenditure/page.tsx` ·
`frontend/components/asset/ExpenditureForm.tsx` · `spikes/ui_honesty_contract.py` · `CLAUDE.md`

---

실행: `/stage 1`
