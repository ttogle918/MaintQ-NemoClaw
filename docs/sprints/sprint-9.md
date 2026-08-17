# Sprint 9 — create_repair_record(P25) · actions 회수(P31) · 확장 도구 프론트 노출

**상태**: ✅ **확정** — tool-builder 현실성 평가 반영 완료 (2026-08-14)

> 🔴 **§4 스테이지 계획과 §7 압축 순서는 §9 가 대체한다.** 평가 결과 §7 의 ③(MQ-907 컷)이 틀렸고
> 스테이지 배치에 🔴 6건이 있었다. **§9 "확정 실행 계획"을 읽고 실행할 것.**
> §6 태스크 상세는 유효하되 **§9-4 의 명세 델타가 우선**한다.

**수립**: 2026-08-14 · **부제**: 두 번 이월된 쓰기 도구를 닫고, 조치문 결측 37건의 **원인을 먼저 재고**,
백엔드에만 있던 확장 도구를 화면으로 꺼낸다

**근거 문서**: `docs/00_MVP_SCOPE.md`(기능 9·확장 7~12) · `docs/07_BACKLOG.md`(P25·P31) ·
`docs/02_SCENARIOS.md`(S19·S1+·S10) · `docs/04_MCP_TOOLS.md §8~§15` · `docs/06_REPO_API.md §2.5~§2.7` ·
`docs/12_MAINT_VALUE.md §2·§7·§9` · `data/analysis/manual_eda.md:97·:100` · `data/analysis/eval_gap_3rd.md §4`

**제약으로 읽은 결정**: D1 · D9 · D10 · D12 · D13 · D15 · D19 · D23 · D24 · D25 · D26 · D29 · D30 ·
D32 · D33 · D37 · D38 · D41 · D56 · D60 · D62 · D63 · D64 · D65 · D69 · D70 · D71 · D73 · D74 · D79 ·
D80 · D81 · D84 · D85 · D86 · D87 · D88 · D89 · D90 · D97

---

## 0. 선행 상태 (실측 · 2026-08-14 기준선)

| 축 | 값 | 확인처 |
|---|---|---|
| 결정 | **D1~D97** | `docs/10_DECISIONS.md` |
| spikes | **28스위트 / 635건** | CLAUDE.md 실측 기준선 · `docs/sessions/2026-08-14.md §검증 상태` |
| seed 자가검증 | **26건** (㉖ = `mfr_part_no`, D97) | 〃 |
| pytest | **46건** | `data/rules/test_rules.py` |
| 프론트 라우트 | **10개** | `npm run build` |
| `error_codes` | **65행** (iG5A 24 / S100 41) | `SELECT count(*) FROM error_codes` |
| MCP 도구 | 코어 7 + 확장 8 = **15** (기본 `core`, D69·D88) | `spikes/tools_profile_contract.py` |
| 쓰기 도구 | **2종** (`create_po_draft` · `generate_disposal_document`) | `mcp_server/db.py` 의 writer 2개 |

### 이월 (carry-over) — Stage 1 최우선 대상이 아닌 이유

| 항목 | 처리 |
|---|---|
| `create_repair_record` (P25 · S19) | **Sprint 7 → 8 에서 두 번 이월.** 이번 스프린트의 축 A 다. ⚠ 그러나 **Stage 1 에 넣지 않는다** — 이 도구는 `repair_records` DDL 확장(신원·시각 컬럼)과 `data/maint_value.classify_expenditure` 를 **둘 다** 선행으로 요구한다. 선행 없이 앞에 두면 스테이지가 통째로 멈춘다. Stage 3 에 배치하고, 그 선행 2건을 Stage 1·2 에 깐다 |
| Sprint 8 미완 | `traces.request_chain_id` 는 **컬럼만**(전 행 NULL 이 정상) · A2A 호출부 미착수. **이번 스프린트 범위 밖** — QMesh 착수 후다(`docs/README.md` 다음 액션 8) |
| 사람 대기 (기존) | `SAFETY_BASELINE`·`QUALIFIED_WORKER_NOTE` 문구 검수 · `RESIDUAL_AT_LIFE_END`/`FLOOR` 가정 동의 · LS 고객센터 팬 품번 문의. **셋 다 이 스프린트를 막지 않는다** (§2) |

---

## 1. 범위 판정 — 이건 MVP 인가 백로그인가

| 축 | 판정 | 근거 |
|---|---|---|
| **A. `create_repair_record`** | ✅ **본 범위** | `00_MVP_SCOPE` 확장 기능 **9번**(수리 증빙 서명)이고 상태가 *"🟡 부분 — 쓰기 도구는 Sprint 9"* 로 이미 적혀 있다. P25 는 "확장 범위 편입분"(D67)이라 **백로그 승격이 아니다** — `07_BACKLOG` 스스로 *"나중에 할지 모를 아이디어가 아니라 하기로 정한 일"* 이라고 구분한다 |
| **B. `actions` 회수 (P31)** | ⚠ **P31 은 백로그 번호지만 승격이 아니다** | 회수 대상은 `error_codes.actions` = **MVP 기능 1(에러코드 진단)의 필수 필드**이고 DDL 이 `NOT NULL` 이다. P31 이 백로그에 있는 것은 *"triage 인프라를 만들자"* 라는 **방법론** 때문이고, 이번에 하는 것은 **이미 MVP 인 필드의 결측 복구**다. 단 ⛔ **유료 OCR 호출·InsuQ 모델 이식은 하지 않는다** — 그건 P31 의 백로그 부분이고 이번 범위 밖이다(§4 MQ-902) |
| **C. 프론트 노출** | ✅ **본 범위** | `00_MVP_SCOPE` 인프라 절의 **UI 2종**과 확장 기능 7·8·11 의 노출이다. Sprint 7 ⓓ 가 이미 *"확장 도구의 UI 노출"* 을 같은 근거로 수행했고(자산 목록·처분 사전판정·실사·서명 화면) 이번은 그 **나머지 5종**이다 |

### 복무 시나리오 — 솔직하게 적는다

`docs/02_SCENARIOS.md` 의 **S1~S4 에 직접 복무하는 태스크는 축 B 뿐이다.** 축 A·C 는 확장 시퀀스(S19·S1+·S10)에
복무한다. Sprint 8 이 세운 선례를 따라 각 태스크의 "복무 시나리오"에 **S19 / S1+ / S10 / S1~S4 / 인프라** 를
그대로 적는다 — S1~S4 중 하나를 억지로 고르면 그 순간 계획이 사실과 달라진다.

| 축 | 시나리오 | 연결 |
|---|---|---|
| A | **S19** (수리 완료 → 증빙 서명) | S10 의 증빙 패키지가 이 레코드를 소비한다(`12 §8` 정비 이력 요약서·핵심부품 갱신 내역) |
| B | **S1 · S3 · S4** (전부) | `lookup_error_code.actions` 는 S1 의 조치 안내 · S3 의 근본원인 점검 · S4 의 "모르면 모른다"의 대조군이다 |
| C | **S1+ · S10** | `assess_repair_value` 3지 판단(S1+) · `build_evidence_bundle`(S10 계층 3) |

---

## 2. 블로커 점검 — 무엇이 막히고, 그래서 어디에 놓았는가

| 블로커 | 이번 스프린트 영향 | 배치 |
|---|---|---|
| `error_codes` 사람 승인 (D33) | 🔴 **축 B 의 지배 변수.** `seed.error_codes_gate()` 는 `_status` 에 `"초안"` 이 들어가면 **전량 미적재(65 → 0행)** 로 떨어뜨린다. 부분 결과를 정본에 쓰면 DB·평가·회귀가 스프린트 내내 죽는다 | **D99 로 우회한다** — 추출은 **후보 파일**에만 쓰고 정본은 손대지 않는다. 승인이 필요한 병합은 **Stage 10(조건부)** 로 뺀다 |
| 🔴 safety-guardrail (`actions` = 점검 절차 서술) | **생성 금지.** 조치문은 PDF 원문 추출이어야 하고 페이지 근거가 있어야 한다 | **코드 게이트 + 사람 게이트 2겹**: MQ-905·907 이 *"후보의 모든 조치문이 해당 페이지 텍스트에 실재하는가"* 를 **자동 대조**로 강제하고(생성이면 실패), MQ-911 이 위험 문구(활선·방전·10분)를 따로 뽑아 사람 검수에 올린다 |
| `related_parts` 검수 | ✅ 해제됨(2026-08-12). 이번 범위와 무관 | — |
| `ANTHROPIC_API_KEY` · 평가 비용 | ⚠ **Stage 1~9 전부 불필요.** 에이전트 루프·`/run-eval` 을 돌리지 않는다 | 평가 재측정은 **Stage 10 이후**, 사람이 비용을 승인해야 시작한다(§5-G3) |
| 임베딩·벡터스토어 미결 | 무관 (RAG 미접촉) | — |
| `RESIDUAL_AT_LIFE_END`·`FLOOR` 가정 미동의 | ⛔ **축 C 를 막지 않는다.** D65·D74 가 이미 *"값은 제공하되 성격을 표시한다"* 로 정리했다 | 대신 화면에 **추정치·가정 미승인 고지를 강제**하고 `spikes/ui_honesty_contract.py` 로 잠근다 |
| LS 팬 품번 (P32) | ⛔ **부재 확정.** 4축 전부 닫혔다 | 이번 스프린트에서 다시 뒤지지 않는다. `mfr_part_no` 는 **읽기만** 한다 |

**결론**: 사람 승인 대기로 막히는 것은 **축 B 의 마지막 한 걸음(병합·적재)뿐**이고, 그것만 Stage 10 으로 뺐다.
Stage 1~9 는 사람 없이 완주 가능하다.

---

## 3. 설계 쟁점 — **D 를 먼저 추가해야 하는 것 4건**

CLAUDE.md 규칙(*"설계와 다른 구현을 하려면 먼저 D 를 추가"*)에 걸리는 것을 전부 앞에 모았다. **MQ-901 이 소유한다.**

### 쟁점 ① 세 번째 쓰기 도구가 기존 구조에 어떻게 들어가는가 → **D98**

현재 쓰기 경계는 **커넥션 이름 = 잠금 범위**로 유지된다(`mcp_server/db.py:70~93`). `draft_writer()` 는
`po_drafts` 트리거만, `decision_writer()` 는 `decisions` 트리거만 건다. 주석이 그 이유를 명시한다 —
*"`draft_writer` 로 `decisions` 를 쓰면 잠겼다고 믿는 지점이 실제로는 안 잠긴다."*
→ **`repair_writer()` 를 같은 형태로 하나 더 만든다.** 기존 둘을 재사용하면 그 문장이 거짓이 된다.

### 쟁점 ② 결측 회수가 `error_codes.json` 정본을 건드리면 DB 가 65 → 0 이 된다 → **D99**

`error_codes_gate()` 는 `_status` 문자열에 `"초안"`·`"승인 전"` 이 있으면 적재를 거부한다. 그리고 `_status` 는
`ig5a_approval_status()` 가 `ig5a_code_map.json` 에서 **유도**한다(D19). 새 조치문 소스가 미검수 상태로 들어오면
`_status` 가 초안으로 되돌아가고 **65행이 통째로 0행이 된다** — CLAUDE.md 가 *"에이전트가 두 번 DB 를 망가뜨렸다"*
로 기록한 바로 그 사고다. → **후보 파일 격리.**

### 쟁점 ③ iG5A 조치문은 **다른 PDF** 에서 온다 → **D100**

`manual_page` 는 표준본(`ig5a-manual`) 페이지인데 조치문은 `ig5a-troubleshooting`(p.22~29)에서 온다.
그대로 두면 인용이 **거짓**이 되고 완료 기준 "근거 페이지 인용률 100%" 가 가짜가 된다.
`manual_eda.md:100` 이 이미 *"두 소스 병합 + 출처 페이지 각각 기록"* 을 요구했다.
→ `error_codes.actions_manual_id`·`actions_page` 신설 + `lookup_error_code` 출력에 `actions_source` 추가.

### 쟁점 ④ backend 는 `mcp_server` 를 import 할 수 없다 → **D101**

REST 로 노출된 두 도구는 **로직이 `data/` 에 있다** — `check_disposal_blockers` → `data/rules/engine.py`,
`verify_ownership` → `data/ownership.py`. 반면 `assess_repair_value` 계열은 `mcp_server/tools/` 안에 있어
**지금 구조로는 REST 노출이 물리적으로 불가능**하다. 그리고 이미 한 번 어긋난 적이 있다 —
`backend/services/decisions.py:520` 이 스스로 *"도구는 mcp_server 소유라 import 할 수 없다(D15).
**그래서 산식이 두 벌 존재한다**"* 라고 적어 뒀다. → **`data/maint_value.py` 로 옮기고 도구는 얇은 위임으로.**

> ⛔ **`build_evidence_bundle` 은 옮기지 않는다.** backend 에 이미 `services/decisions.rebuild_bundle()`
> (D84 재산출 경로)이 있고 그것이 **정식 소비자**다. 새로 옮기면 세 번째 사본이 생긴다.

---

## 4. 스테이지 계획

### Stage 1
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-901 | 결정 4건 등재 — D98(세 번째 쓰기 도구) · D99(후보 파일 격리) · D100(actions 출처) · D101(`data/maint_value.py`) | `docs/10_DECISIONS.md` | — |
| MQ-902 | **추출 품질 triage** — 계측을 먼저 만든다 (네트워크·유료 OCR 호출 0) | `data/extract_triage.py`(신규) · `data/analysis/` | — |

### Stage 2
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-903 | `data/maint_value.py` 신설 — 확장 도구 4종의 **산출 로직 이동**, MCP 도구는 얇은 위임 | `data/` · `mcp_server/tools/` | MQ-901 |
| MQ-904 | `data/seed.py` — `repair_records` DDL 확장 + `error_codes` 출처 컬럼 + 시드 보정 + 자가검증 3건 | `data/seed.py` | MQ-901 |
| MQ-905 | **ⓐ iG5A 11건** — 트러블슈팅 소스 추가 + 명칭↔코드 조인 → **후보 파일** | `data/extract_error_codes.py` · `data/extracted/` | MQ-901, MQ-902 |

### Stage 3
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-906 | **`create_repair_record`** — 세 번째 쓰기 도구 + `repair_writer()` + 프로파일 등록 + `04 §16` | `mcp_server/` · `docs/04_MCP_TOOLS.md` | MQ-903, MQ-904 |
| MQ-907 | **ⓑ S100 26건** — 셀 내 줄바꿈 분해 실패 재추출 (OCR 없음) → 후보 파일 | `data/extract_error_codes.py` | MQ-905 |
| MQ-908 | 확장 도구 **REST 노출 5종** — 서비스·라우터 (평가 경로 무영향) | `backend/services/` · `backend/routers/` · `backend/main.py` | MQ-903 |

### Stage 4
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-909 | 수리 증빙 **제출·서명·반려 API** + 통합 큐 `kind:"repair"` 배선 | `backend/` | MQ-906 |
| MQ-910 | `lookup_error_code` 에 `actions_source` 노출 (현재 전건 `null` 이 정상) | `mcp_server/tools/lookup_error_code.py` | MQ-901, MQ-904 |
| MQ-911 | **사람 검수 패키지** — 37건 코드별 원문 대조표 + 위험 문구 별도 절 + TODO 등재 | `data/analysis/` · `TODO_직접할일.md` | MQ-905, MQ-907 |

### Stage 5
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-912 | 프론트 **공통 배관** — API 클라이언트·타입·상태 매퍼 + `lib/maintValue.ts`(순수 표시 규칙) | `frontend/lib/` | MQ-908, MQ-909 |
| MQ-913 | 회귀 — `write_tool_contract` 확장 · **신규 `repair_flow_contract`** · `approvals_contract ③` 정정 · `lookup_contract`·`tools_profile_contract` 갱신 | `spikes/` | MQ-906, MQ-909, MQ-910 |

### Stage 6
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-914 | **수리 가치 판단 화면** — `assess_repair_value` 중심 + 부품 등급 **드로어** + 지출 **작은 카드** + 지표 **보조 패널** | `frontend/app/(console)/technician/asset/[assetId]/value/` · `frontend/components/asset/` | MQ-912 |

### Stage 7
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-915 | **근거 번들 화면** + **지출 분류 독립 페이지** | `frontend/app/.../evidence/` · `frontend/app/(console)/manager/expenditure/` · `frontend/components/asset/` | MQ-914 |
| MQ-916 | 승인 큐 **`kind:"repair"` 상세** | `frontend/components/queue/` · `frontend/components/screens/ApprovalQueueScreen.tsx` | MQ-912, MQ-909 |

### Stage 8
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-917 | `spikes/ui_honesty_contract.py` 확장 — `null`·`insufficient_data`·추정치·`HOLD`·repair 어휘 | `spikes/ui_honesty_contract.py` · `frontend/lib/__checks__/` | MQ-914, MQ-915, MQ-916 |

### Stage 9
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-918 | 문서·개수 전파 — 기준선·도구 개수·절 번호·시나리오·백로그 상태 | `docs/**` · `CLAUDE.md` · `README.md` | MQ-913, MQ-917 |

### Stage 10 — ⚠ **사람 승인 뒤에만 착수. 이번 스프린트 안에 끝난다고 가정하지 않는다**
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-919 | 승인된 `actions` **병합 적재** + 재시드 + 회귀 + 평가 재측정 절차 안내 | `data/extracted/` · `data/seed.py` · `spikes/lookup_contract.py` | **사람 검수(G1)**, MQ-911, MQ-918 |

### 의존성 그래프

```
MQ-901 ─┬─► MQ-903 ─┬─► MQ-906 ─┬─► MQ-909 ─┬─► MQ-912 ─► MQ-914 ─► MQ-915 ─┐
        │           │           │           │                               ├─► MQ-917 ─► MQ-918 ─► [G1] ─► MQ-919
        ├─► MQ-904 ─┘           │           ├─► MQ-913                      │
        │      └────────────────┼─► MQ-910 ─┘                MQ-916 ────────┘
        └─► MQ-905 ─► MQ-907 ─► MQ-911 ─────────────────────────────────► [G1]
MQ-902 ─────► MQ-905          MQ-903 ─► MQ-908 ─► MQ-912
```

### 스테이지 구성 근거

- **Stage 1 (901·902 병렬)** — 파일 교집합 0(`docs/10_DECISIONS.md` vs 신규 `data/extract_triage.py`).
  **901 을 맨 앞에 두는 이유는 규칙이다** — D98~D101 은 넷 다 *"기존 문서에 적힌 것과 다른 구조"* 를 쓰겠다는
  선언이고(쓰기 도구 2종 → 3종 · 정본 파일 미수정 · 컬럼 신설 · 로직 위치 이동), 결정을 먼저 적지 않고
  코드를 고치면 CLAUDE.md 위반이다.
  **902 를 1스테이지에 두는 이유는 브리핑이 지목한 순서 그대로다** — *"파서를 먼저 바꾸면 좋아졌는지 잴 방법이
  없다."* 905·907 이 손대는 값의 **before 를 902 가 고정**하지 않으면 이 스프린트는 개선을 주장할 수 없다.
- **Stage 2 (903·904·905 병렬)** — 세 태스크가 각각 `data/maint_value.py`+`mcp_server/tools/*` /
  `data/seed.py` / `data/extract_error_codes.py` 로 **완전히 분리**된다. 셋 다 `data/` 아래지만 **같은 파일은
  하나도 없다.**
- **Stage 3 에서 905 → 907 을 쪼갠 이유 (핵심)** — 둘 다 `data/extract_error_codes.py` 다.
  파일 충돌 회피만이면 순서만 지키면 되지만 **검증 단위가 실제로 다르다**:
  ⓐ 905 = *"소스를 추가하면 풀리는가"*(무료 경로) ⓑ 907 = *"기존 소스를 다시 읽으면 풀리는가"*(파서 결함).
  한 태스크로 묶으면 **개선분이 어느 쪽에서 왔는지 영원히 못 가른다** — 그리고 그게 정확히 P31 이 triage 를
  선행으로 요구한 이유다. 907 은 905 의 조인 결과를 회귀 기준으로 삼는다(**iG5A 11건이 다시 비면 907 이 깬 것**).
- **Stage 3 의 906·908 이 903 을 공유하지만 서로 안 만나는 이유** — 906 은 `mcp_server/`, 908 은 `backend/`.
  D15 가 두 프로세스의 상호 import 를 금지하므로 **파일 경계와 프로세스 경계가 일치**한다.
- **Stage 4 에서 909 와 908 을 나눈 이유** — 둘 다 `backend/main.py` 에 라우터를 등록한다. 같은 스테이지에
  두면 병렬 실행이 같은 파일을 덮어쓴다.
- **Stage 5 (912·913 병렬)** — 912 는 `frontend/lib/`, 913 은 `spikes/`. **913 이 906·909·910 뒤인 이유**:
  스파이크가 세 태스크를 **동시에 관통**하므로 어느 하나에 붙이면 자기 코드를 자기가 검증하는 구조가 된다
  (sprint-7 Stage 4 · sprint-8 Stage 4 와 같은 이유).
- **Stage 6 이 단일 태스크인 이유** — 914 한 화면에 **도구 4종(1·3·4·5)이 모인다.** 코디네이터가 인용한
  `04 §13` 계약(*"하위 도구 실패를 삼키지 않는다 — `classify_part_criticality`·`get_maintenance_metrics` 중
  하나라도 `status != "ok"` 면 그 `status`·`reason` 을 그대로 전파"*)이 **화면 구조를 이미 정해 놓았다.**
  화면을 셋으로 쪼개면 그 전파 경로가 셋으로 갈라져 *"삼키지 않는가"* 를 한 곳에서 검증할 수 없다.
- **Stage 7 (915·916 병렬)** — 915 는 `components/asset/*` + 신규 라우트 2개, 916 은 `components/queue/*` +
  `ApprovalQueueScreen.tsx`. 교집합 0. **915 가 914 뒤인 이유**: 지표 보조 패널(`MetricsAside`)을 914 가 만들고
  915 가 **import 만** 한다(수정하지 않는다) — 같은 스테이지면 아직 없는 컴포넌트를 import 하게 된다.
- **Stage 8 단독** — ui_honesty 스파이크는 914·915·916 **세 화면 전부**를 스캔한다(L2 글롭이
  `components/asset/*.tsx` 를 자동 포함하므로 세 태스크가 끝나기 전에 돌리면 **없는 파일을 통과로 읽는다**).
- **Stage 9 가 마지막인 이유** — 회귀 기준선 숫자는 **러너 출력이 기준**이라 실제로 돌려 보기 전에는 적을 수
  없다. 지어내면 그 줄이 거짓이 되고, CLAUDE.md 는 *"직전 실행보다 줄었다면 테스트가 사라진 것"* 을 그 숫자로
  판정한다.
- **Stage 10 을 스프린트 본체에서 뗀 이유** — **사람 승인이 유일한 입력**이다. 앞에 두면 스프린트가 통째로 멈춘다.

### 공유 파일 단일 소유자 격리

| 파일 | 유일 소유 | 스테이지 |
|---|---|---|
| `docs/10_DECISIONS.md` (D98~D101 **신설**) | MQ-901 | 1 |
| `docs/10_DECISIONS.md` (기존 행 **마커·각주만**) | MQ-918 | 9 |
| `data/extract_triage.py` | MQ-902 | 1 |
| `data/maint_value.py` · `mcp_server/tools/{assess_repair_value,get_maintenance_metrics,classify_part_criticality,classify_expenditure}.py` | MQ-903 | 2 |
| `data/seed.py` | **MQ-904** | 2 |
| `data/seed.py` (**병합 적재 경로만**) | MQ-919 | 10 |
| `data/extract_error_codes.py` (**iG5A 경로**) | MQ-905 | 2 |
| `data/extract_error_codes.py` (**S100 경로**) | MQ-907 | 3 |
| `mcp_server/tools/create_repair_record.py` · `mcp_server/db.py` · `mcp_server/server.py` | MQ-906 | 3 |
| `mcp_server/tools/lookup_error_code.py` | MQ-910 | 4 |
| `backend/services/maint_value.py` · `backend/routers/maint_value.py` · `backend/main.py` | MQ-908 | 3 |
| `backend/services/repairs.py` · `backend/routers/repairs.py` · `backend/services/approvals.py` · `backend/main.py` | MQ-909 | 4 |
| `frontend/lib/api.ts` · `types.ts` · `mappers.tsx` · `maintValue.ts` | **MQ-912** | 5 |
| `frontend/components/asset/{RepairValuePanel,CriticalityDrawer,ExpenditureCard,MetricsAside}.tsx` + `.../value/page.tsx` | MQ-914 | 6 |
| `frontend/components/asset/{EvidenceBundlePanel,ExpenditureForm}.tsx` + `.../evidence/page.tsx` + `manager/expenditure/page.tsx` | MQ-915 | 7 |
| `frontend/components/queue/RepairDetail.tsx` · `ApprovalQueueScreen.tsx` | MQ-916 | 7 |
| `spikes/{write_tool_contract,approvals_contract,lookup_contract,tools_profile_contract}.py` · `spikes/repair_flow_contract.py` | MQ-913 | 5 |
| `spikes/ui_honesty_contract.py` · `frontend/lib/__checks__/ui_honesty.ts` | MQ-917 | 8 |
| `docs/**`(그 밖) · `CLAUDE.md` · `README.md` · `TODO_직접할일.md` | MQ-918 | 9 |
| `data/analysis/actions_review.md` · `TODO_직접할일.md`(§actions 절만) | MQ-911 | 4 |

> ⚠ **같은 파일을 두 태스크가 소유하는 곳이 4군데다. 전부 스테이지가 다르다.**
> `docs/10_DECISIONS.md`(901/918) · `data/seed.py`(904/919) · `data/extract_error_codes.py`(905/907) ·
> `TODO_직접할일.md`(911 은 §actions 절만 / 918 이 나머지).

---

## 5. 사람 승인 게이트 — 어느 스테이지에서 걸리는가

| 게이트 | 무엇을 | 언제 걸리나 | 막는 것 |
|---|---|---|---|
| **G1** 🔴 | **`actions` 후보 37건 검수** — 코드별 조치문·출처 페이지 대조 + **위험 문구(활선·방전·"10분 이상") 안전 검수** | **Stage 4 종료 후**(MQ-911 이 검수 패키지를 산출한 시점) | **MQ-919 만** 막는다. Stage 5~9 는 계속 진행된다 |
| **G2** | `error_codes` **재승인 범위 확정** — 전량 65건인가 **변경분 37건**인가 | G1 과 동시 | D99 가 *"변경분 37건"* 을 제안한다. 기존 65건의 `code`·`error_name`·`causes`·`manual_page` 는 **한 글자도 바뀌지 않으므로** 재승인 대상이 아니다. 그 사실을 MQ-919 가 **해시 대조로 증명**한다 |
| **G3** | **평가 재측정 비용 승인** (`--repeat 3` × 2회 = 병합 전/후) | MQ-919 이후 | 지표 개선 주장. ⛔ **비용을 지어내지 않는다** — `run_eval.py:237 estimate_cost()` 가 실행 시 출력한다 |
| G4 (기존) | `SAFETY_BASELINE`·`QUALIFIED_WORKER_NOTE` 문구 검수 | 이미 대기 중 | **이 스프린트를 막지 않는다.** 단 G1 의 안전 검수와 **같은 회차에 처리하면** 왕복이 준다 |
| G5 (기존) | `RESIDUAL_AT_LIFE_END=0.50`·`FLOOR=0.10` 가정 동의 | 이미 대기 중 | **축 C 를 막지 않는다** — D65·D74 가 "값은 제공하되 성격을 표시"로 정리했고, MQ-917 이 **화면에 고지가 있는지**를 회귀로 잠근다 |

> ⛔ **G1 을 Stage 1 에 끌어오지 않는다.** 검수 대상(후보 37건)이 MQ-905·907 의 **산출물**이라
> 그 전에는 검수할 것이 존재하지 않는다.

---

## 6. 태스크별 상세 구현 명세

---

#### MQ-901 — 결정 4건 등재 (D98 · D99 · D100 · D101)

- **복무 시나리오**: 인프라 (S19 · S1~S4 · S1+ 의 선행 규약)
- **변경 파일**: `docs/10_DECISIONS.md` (수정 — 표 끝에 4행 추가)
- **인터페이스**: 문서. 기존 표 형식 그대로 `| D98 | 결정 | 대안 | 채택 이유 |`.
- **핵심 로직**:

  **1. D98 — `create_repair_record` 는 세 번째 쓰기 도구이며 `repair_writer()` 전용 커넥션을 갖는다**
  - 결정: ⓐ `mcp_server/db.py` 에 `repair_writer()` 를 추가하고 `repair_records` 전용 TEMP TRIGGER
    2개(UPDATE·DELETE ABORT)를 건다. ⓑ 도구는 `state='draft'` **INSERT 만** 한다.
    ⓒ **프로파일 `full` 전용**(D69) — 확장 8종 → **9종**, 총 15 → **16**. **코어 7종은 불변**이므로
    D88 의 `tools > 7` 게이트는 그대로 작동하고 **평가 실적에 영향이 없다.**
    ⓓ `performed_by`·`verified_by`·`signed_at`·`record_hash`·`state`·`session_id` 는 **파라미터가 아니다.**
    ⓔ `part_class`·`expenditure_class` **도 파라미터가 아니다** — 전자는 `parts` 테이블 조회,
    후자는 `data/maint_value.classify_expenditure()` 산출.
    ⓕ state 어휘 **4종** `draft|pending|signed|rejected`.
  - 대안: ① `draft_writer()` 재사용 → `mcp_server/db.py:70~74` 주석이 이미 기각한 형태
    (*"잠겼다고 믿는 지점이 실제로는 안 잠긴다"*) ② 도구가 곧바로 `signed` 로 INSERT →
    D10 정면 위반이며 `12 §7` 의 *"서명된 레코드는 수정 불가"* 가 **사람 서명 없이 성립**해 버린다
    ③ `expenditure_class` 를 파라미터로 → **LLM 이 자본적지출/수익적지출을 지어낸다.** D31 이 `unit_price` 를,
    D81 이 `override_reason` 을 파라미터에서 뺀 것과 **같은 종류의 위험**이다(금액·회계 판정)
    ④ 코어 프로파일 등록 → D88 이 코드로 막는다(`tools > 7` → `SystemExit(2)`).
  - 채택 이유에 반드시 적을 것: **`kind:"repair"` 는 D85 가 이미 예약해 둔 자리라 API 계약이 변하지 않는다.**
    변하는 것은 *"항상 0건"* 이라는 **사실**뿐이고, 그 사실을 적은 곳 3군데(`services/approvals.py:27~29` 주석 ·
    `06 §2.7` · `spikes/approvals_contract.py ③`)를 **함께** 고친다.

  **2. D99 — `actions` 회수분은 후보 파일에 격리하고, 승인 시에만 정본에 병합한다**
  - 결정: 추출 태스크는 `data/extracted/error_codes.json` 을 **읽기만** 하고
    `data/extracted/error_codes_actions.candidate.json` 에만 쓴다. 정본 병합은 승인 후 별도 태스크.
  - 대안: ① 정본에 직접 쓰고 `_status` 를 초안으로 → **65 → 0행.** `error_codes_gate()` 는 코드 단위가 아니라
    **파일 단위** 게이트다 ② 정본에 쓰되 `_status` 를 승인 유지 → **미검수 조치문이 그대로 DB·에이전트 응답으로
    나간다.** 안전 규칙 위반 ③ `actions` 만 담는 별도 테이블 → 결(grain)이 `(model, code)` 로 1:1 인데 나눈다
    (D97 이 `mfr_parts` 를 기각한 것과 같은 이유).
  - 채택 이유: CLAUDE.md 가 **두 번의 실제 사고**(MQ-708·MQ-713a)로 기록한 함정을 구조로 막는다.
    그리고 **검수 단위를 변경분 37건으로 좁힐 수 있는 것이 이 격리의 부수 효과**다 — 후보 파일에는 바뀌는 것만
    들어 있으므로 사람이 "무엇이 새로 들어오는가"를 파일 하나로 볼 수 있다.

  **3. D100 — `actions` 의 출처는 `actions_manual_id`·`actions_page` 로 따로 보존한다**
  - 결정: `error_codes` 에 nullable 2컬럼 신설 + `lookup_error_code` 출력에
    `actions_source: {manual_id, page, print_page} | null` 추가. **`null` 의 뜻은 "출처 미기록"이며
    "본문과 같은 페이지"가 아니다.**
  - 대안: ① `manual_page` 하나로 통일 → **iG5A 는 거짓 인용이 된다**(표준본 p.204 를 가리키는데 문장은
    트러블슈팅 p.24 에 있다). 완료 기준 "인용률 100%" 의 판정 소스가 오염된다 ② JSON 파일에만 남기고 DB 에는
    안 넣음 → 도구가 못 읽으므로 응답에 근거를 실을 수 없다 ③ `actions` 를 문장별 객체 배열로 승격
    (`[{text, page}]`) → **`04 §1` 의 `actions: [str]` 계약이 깨지고** 프론트·평가·스파이크가 함께 흔들린다.
  - 함께 적을 것: **D26 불변**(저장·검증은 물리 페이지) · **D32**(표시는 인쇄 + PDF 병기, 오프셋 원천은
    `manifest.json` — `ig5a-troubleshooting` 은 `print_page_offset: 0`).

  **4. D101 — 확장 도구의 산출 로직은 `data/maint_value.py` 에 두고 MCP 도구는 위임한다 (D73 적용)**
  - 결정: `get_maintenance_metrics`·`classify_part_criticality`·`classify_expenditure`·`assess_repair_value`
    **4종의 계산부**를 `data/maint_value.py` 로 옮긴다. 커넥션은 **호출자가 `mode=ro` 로 열어 넘긴다**
    (`data/ownership.verify(con, ...)` 시그니처 그대로).
  - 대안: ① backend 가 재구현(복제) → `backend/services/decisions.py:520` 이 *"산식이 두 벌 존재한다"* 라고
    **스스로 적어 둔 상태의 확대 재생산**. D65 추정치가 두 벌이 되면 화면과 채팅이 다른 잔가를 말한다
    ② backend 가 MCP 클라이언트로 도구 호출 → **`core` 에서 도구가 등록되지 않는다**(D69). 사람용 REST 가
    에이전트 노출 설정에 종속되는 순간 D73 이 무너진다 ③ `mcp_server` 를 backend 가 import → **D15 정면 위반**.
  - 채택 이유: **이미 REST 로 노출된 두 도구가 정확히 이 구조다** — `check_disposal_blockers` →
    `data/rules/engine.py`, `verify_ownership` → `data/ownership.py`. 즉 새 패턴이 아니라 **선례의 적용**이며,
    `06 §2.5` 가 *"`core` 프로파일에서도 살아 있다 (D73)"* 로 그 근거를 이미 문서화했다.

- **엣지 케이스**:
  - D 번호가 이미 D98 이상으로 선점돼 있으면 **번호를 밀지 말고 중단**하고 보고한다.
  - 표 셀 안의 `|` 는 `\|` 로 이스케이프.
  - **D 를 5개로 늘리지 않는다** — 쟁점은 정확히 4개다.
- **지켜야 할 결정**: D10 · D15 · D19 · D23 · D26 · D32 · D33 · D37 · D69 · D73 · D80 · D81 · D85 · D88 · D97
- **회귀**: 없음(문서). 단 MQ-918 이 D 범위 표기 5곳을 갱신한다 — **여기서 하지 않는다.**
- **DoD**:
  - `rg -n "^\| D(98|99|100|101) " docs/10_DECISIONS.md` → **4행**.
  - `rg -n "D102" docs/10_DECISIONS.md` → **0건**.
  - D98 셀에 `mcp_server/db.py:70~74` · `services/approvals.py:27~29` 인용이 있다.
  - D101 셀에 `backend/services/decisions.py:520` 인용이 있다.
  - D99 셀에 `error_codes_gate()` 와 **"65 → 0행"** 이 명시돼 있다.

---

#### MQ-902 — 추출 품질 triage (계측을 먼저 만든다)

- **복무 시나리오**: S1 · S3 · S4 (조치문 품질은 세 시나리오의 응답 본문이다) / 인프라
- **변경 파일**:
  - `data/extract_triage.py` (신규)
  - `data/analysis/extract_triage.md` (신규 — 리포트)
  - `data/extracted/extract_triage.json` (신규 — 기계 판독용 스냅샷)
- **인터페이스**:

```python
SIGNALS: Final[tuple[str, ...]] = ("field_missing", "length_outlier", "table_collapse")
LABELS:  Final[tuple[str, ...]] = ("SOURCE_MISSING", "CELL_SPLIT", "RE_OCR_CANDIDATE", "OK")

@dataclass(frozen=True)
class PageVerdict:
    manual_id: str          # 'ig5a-manual' | 'ig5a-troubleshooting' | 's100-manual'
    page: int               # PDF 물리 페이지 (D26)
    label: str              # LABELS
    codes_total: int
    codes_missing_actions: int
    code_tokens_found: int  # ★ 양성 축 — 이 페이지 텍스트에서 실제로 발견된 코드 토큰 수
    signals: dict[str, float]
    note: str

def scan() -> list[PageVerdict]: ...
def summarize(verdicts: list[PageVerdict]) -> dict: ...
def estimate_ocr_cost(verdicts: list[PageVerdict], won_per_page: int = 45) -> dict: ...
def main() -> None: ...   # 리포트·JSON 산출
```

- **핵심 로직**:
  1. `error_codes.json` 의 65건을 `(model, code)` 로 순회하며 `causes`·`actions` 결측을 센다.
     **기대값을 브리핑 실측으로 고정한다** — `S100: 41 / actions 결측 26 / causes 결측 0`,
     `iG5A: 24 / actions 결측 11 / causes 결측 0`, `_unparsed 0`, `_pending_review 0`.
     ⚠ 이 값이 다르면 **입력이 이미 바뀐 것**이므로 스크립트가 경고하고 실측값을 그대로 리포트한다
     (하드코딩 assert 로 죽이지 않는다 — 이 도구는 계측기다).
  2. **양성 축(liveness anchor)을 반드시 함께 잰다.** 각 후보 페이지 텍스트에서 코드 토큰
     (`[A-Z0-9]{2,4}` 중 `error_codes` 에 실재하는 것)을 세어 `code_tokens_found` 에 넣는다.
     - `codes_missing_actions > 0` **and** `code_tokens_found == 0` → `SOURCE_MISSING`
       (그 페이지에 아예 없다 = **소스를 바꿔야 풀린다**)
     - `codes_missing_actions > 0` **and** `code_tokens_found > 0` → `CELL_SPLIT`
       (같은 페이지에서 어떤 코드는 성공했다 = **파서 결함**)
     - 두 신호가 다 없고 길이 이상치/표 붕괴만 있으면 `RE_OCR_CANDIDATE`
  3. **신호 2종만 쓴다** — `length_outlier`(셀 텍스트 길이 z-score) · `table_collapse`(행당 유효 셀 수의
     급감). ⛔ **문자 깨짐 계열은 넣지 않는다** — InsuQ 실측에서 그 코퍼스 전체 0건이었고, 한국어 나열
     구분자(`ㆍ`)를 고립 자모로 오탐한 전례가 있다(P31 기록). 없는 신호를 넣으면 오탐만 늘린다.
  4. `estimate_ocr_cost()` 는 **페이지 수 × 45원** 을 계산만 한다. ⛔ **네트워크 호출 0** —
     `httpx`·`requests` import 금지. "무엇을 살지 고르는 것까지"가 이 모듈의 경계다.
  5. 리포트에는 **결론이 아니라 두 축의 실측값**을 찍는다(CLAUDE.md 부재검사 규칙) —
     `"iG5A p.204: missing 11 / code_tokens 0 → SOURCE_MISSING"` 형태.
- **엣지 케이스**:
  | 상황 | 반환 |
  |---|---|
  | `error_codes.json` 없음 | `sys.exit(1)` + 안내 (추출 미완) |
  | 매뉴얼 PDF 해시 불일치 | `check_manifest()` 를 재사용해 **중단**한다 (D19) |
  | 모든 페이지가 `OK` | 리포트에 *"결측 0 — 신호 없음"* 과 **스캔한 페이지 수**를 함께 찍는다 (스캐너 실명 구분) |
  | 코드 토큰 정규식이 0건만 반환 | **양성 축 자체가 죽은 것**이므로 `SCANNER_BLIND` 경고를 최상단에 찍는다 |
- **지켜야 할 결정**: D19(manifest 해시 게이트) · D24(추출 전략) · D26(물리 페이지) ·
  **CLAUDE.md 부재검사 규칙**(양성 축 필수) · D65 태도(모르는 것을 0으로 메우지 않는다)
- **회귀**: 신규 스파이크를 만들지 않는다 — 이 스크립트 **자체가 계측기**이고, 905·907 의 DoD 가
  이 출력의 변화를 인용한다. `ruff check data` 대상에는 들어간다.
- **DoD**:
  - `uv run python data/extract_triage.py` 가 **네트워크 없이** 완주하고
    `data/analysis/extract_triage.md` + `data/extracted/extract_triage.json` 을 남긴다.
  - 리포트에 브리핑 실측이 재현된다 — **S100 26 · iG5A 11 · causes 0 · `_unparsed` 0**.
  - iG5A 조치 결측 코드가 **`SOURCE_MISSING`**, S100 결측 페이지가 **`CELL_SPLIT`** 으로 라벨링된다
    (⚠ 실측이 다르면 **라벨이 아니라 실측을 적는다** — 계획이 데이터를 이기지 않는다).
  - `rg -n "httpx|requests|urllib|socket" data/extract_triage.py` → **0건**.
  - `SELECT count(*) FROM error_codes` = **65** (이 태스크는 DB 를 건드리지 않는다).

---

#### MQ-903 — `data/maint_value.py` 신설 · MCP 도구 4종 위임 (D101)

- **복무 시나리오**: S1+ (3지 판단) / 인프라 (축 C 의 물리적 선행)
- **변경 파일**:
  - `data/maint_value.py` (신규)
  - `mcp_server/tools/get_maintenance_metrics.py` · `classify_part_criticality.py` ·
    `classify_expenditure.py` · `assess_repair_value.py` (수정 — **얇은 위임으로 축소**)
- **인터페이스**:

```python
# data/maint_value.py — 커넥션은 호출자가 mode=ro 로 열어 넘긴다 (data/ownership.py 와 같은 규약)
def maintenance_metrics(con, *, asset_id: str, window_months: int | None = None) -> dict: ...
def part_criticality(con, *, part_no: str) -> dict: ...
def expenditure(con, *, part_class: str, repair_scope: str, amount: int | str) -> dict: ...
def repair_value(con, *, equipment_id: str, failed_part: str,
                 repair_cost: int | str, repair_scope: str = "RESTORE") -> dict: ...
```

```python
# mcp_server/tools/assess_repair_value.py (위임 후 형태)
DESCRIPTION = "..."          # ★ 정본은 여기 그대로 남는다 (04 §설계원칙 3)
def assess_repair_value(equipment_id: str, failed_part: str,
                        repair_cost: int | str, repair_scope: str = "RESTORE") -> dict:
    try:
        with read_only() as con:
            return maint_value.repair_value(con, equipment_id=equipment_id, ...)
    except FileNotFoundError:
        return {"status": "error", "reason": "db_missing"}
```

- **핵심 로직**:
  1. **출력 dict 를 한 글자도 바꾸지 않는다.** 이 태스크는 리팩터이지 기능 변경이 아니다.
  2. `DESCRIPTION` 상수는 **도구 파일에 남긴다** — `04 §설계원칙 3` 이 *"각 도구 파일의 `DESCRIPTION`
     상수가 정본"* 이라고 못박았고, `data/` 로 옮기면 정본 위치가 흔들린다.
  3. **파라미터 기본값 규약(D80)은 도구 시그니처가 유지**한다 — 필수 3종에 기본값 없음,
     `repair_scope` 만 optional. `data/` 쪽 함수의 키워드 기본값은 **MCP 스키마와 무관**하다.
  4. `int | str` 유니온을 **좁히지 않는다**(`spikes/tools_profile_contract.py ③` 이 검사한다).
  5. 도구 간 직접 호출(`assess → criticality`·`metrics`)은 **`data/` 안에서 함수 호출**로 바뀐다.
     ⚠ `04 §13` 의 *"하위 도구 실패를 삼키지 않는다"* 계약을 그대로 유지 — `status != "ok"` 면
     그 `status`·`reason` 을 **재포장 없이** 전파한다.
  6. `data/maint_value.py` 는 **`mcp_server` 를 import 하지 않는다**(반대 방향도 금지 대상은 아니지만
     이 모듈은 순수 데이터 계층이다). `read_only()` 도 import 하지 않는다 — 커넥션은 받는다.
- **엣지 케이스**:
  | 상황 | 기대 |
  |---|---|
  | `spikes/asset_tools_contract.py` **49건** | ⚠ **한 건도 수정하지 않고 통과해야 한다.** 수정이 필요하면 그 자체가 리팩터 실패 신호다 |
  | `mcp_server/tools/_asset_ref.py` 의존 | `data/` 로 함께 옮길지 판단 — 도구 전용 정규화라면 도구에 남긴다 |
  | `data/rules/engine.ASSET_FACT_COLUMNS` import | 그대로 유지(이미 `data/` 안이다) |
  | 순환 import (`data/maint_value` ↔ `data/rules/engine`) | 단방향만 허용. 역참조가 필요하면 **중단하고 보고** |
- **지켜야 할 결정**: D101(신설) · D73(공유 데이터 계층) · D15(프로세스 분리) · D80(기본값) ·
  D9(예외 대신 status) · D65·D70·D74(고지 필드 유지) · D64(OEE 불산출 유지)
- **회귀**: `spikes/asset_tools_contract.py`(**49건 무변경 통과**) · `spikes/tools_profile_contract.py`(7건) ·
  `spikes/sp2_mcp_roundtrip.py`(20건). **새 검사를 추가하지 않는다** — 이 태스크의 성공 판정은
  *"기존 검사가 하나도 안 바뀌고 통과"* 다.
- **DoD**:
  - `uv run python spikes/asset_tools_contract.py` → **49건 전건 통과**, 파일 diff **0**.
  - `uv run python spikes/tools_profile_contract.py` → 7건 통과.
  - `rg -n "^from mcp_server|^import mcp_server" data/maint_value.py` → **0건**.
  - `rg -n "def (maintenance_metrics|part_criticality|expenditure|repair_value)" data/maint_value.py` → **4건**.
  - `uv run ruff check data mcp_server`.

---

#### MQ-904 — `data/seed.py`: `repair_records` DDL 확장 · `error_codes` 출처 컬럼 · 시드 보정 · 자가검증 3건

- **복무 시나리오**: S19 (증빙의 신원·시각) / S1·S3 (조치 출처)
- **변경 파일**: `data/seed.py` — `SCHEMA` · `REPAIR_RECORDS` 시드 함수 · `load_error_codes()` · `verify()`
- **인터페이스 (DDL 확정형)**:

```sql
-- §16 repair_records — 수리 증빙 (D98)
CREATE TABLE repair_records (
  repair_id TEXT PRIMARY KEY,
  equipment_id TEXT NOT NULL REFERENCES equipment,
  model TEXT, error_code TEXT,
  part_class TEXT,
  work_type TEXT NOT NULL,
  expenditure_class TEXT,
  cost INTEGER NOT NULL,
  downtime_hours REAL,
  parts TEXT,
  performed_by TEXT REFERENCES users, verified_by TEXT REFERENCES users,
  signed_at DATETIME, record_hash TEXT,
  state TEXT NOT NULL DEFAULT 'draft',
  -- ★ Sprint 9 신설 (D98) — 도구는 이 셋을 채우지 않는다. 백엔드가 X-User·세션에서 stamp 한다 (D23·D37)
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  requested_by TEXT REFERENCES users,
  session_id TEXT,
  note TEXT,                             -- 반려 사유·서명 메모 (D38 — 반려는 이유가 필수)
  FOREIGN KEY (model, error_code) REFERENCES error_codes(model, code),
  CHECK (work_type IN ('PLANNED','UNPLANNED')),
  CHECK ((model IS NULL) = (error_code IS NULL)),
  CHECK (parts IS NULL OR json_valid(parts)),
  CHECK (expenditure_class IS NULL OR expenditure_class IN ('CAPITAL','REVENUE','HOLD')),
  -- ★ 신설 ① 상태 어휘 4종 (D98)
  CHECK (state IN ('draft','pending','signed','rejected')),
  -- ★ 신설 ② "서명 없는 확정 0건" 을 스키마로 잠근다 (decisions 의 DDL CHECK 2종과 같은 태도)
  CHECK (state <> 'signed' OR (signed_at IS NOT NULL AND record_hash IS NOT NULL
                               AND verified_by IS NOT NULL)),
  -- ★ 신설 ③ 미서명은 지표에 들어갈 수 없다 (12 §11) — signed_at 은 서명의 결과지 원인이 아니다
  CHECK (signed_at IS NULL OR state = 'signed')
);

-- §1 error_codes — 조치문 출처 (D100)
  actions_manual_id TEXT,   -- 'ig5a-troubleshooting' 등 manifest 의 id. NULL = 출처 미기록
  actions_page      INTEGER -- PDF 물리 페이지 (D26). actions_manual_id 와 짝
  ...
  CHECK ((actions_manual_id IS NULL) = (actions_page IS NULL))   -- 짝이거나 둘 다 NULL
```

- **핵심 로직**:
  1. `repair_records` DDL 에 컬럼 4개 + CHECK 3종 추가. **기존 CHECK 4종은 한 글자도 건드리지 않는다.**
  2. `error_codes` DDL 에 컬럼 2개 + CHECK 1종 추가.
  3. ⚠ **`load_error_codes()` 의 `INSERT INTO error_codes VALUES (?,?,?,?,?,?,?,?,?)` 를
     명시적 컬럼 목록으로 바꾼다.** 위치 인자 9개짜리 INSERT 는 컬럼이 늘어나는 순간 조용히 깨진다.
     새 두 컬럼은 JSON 에 키가 있으면 채우고 없으면 `None` (**현재는 전건 `None` 이 정상** — 병합은 MQ-919).
  4. 시드 12행에 `created_at`(실행일 기준 상대일 — ⛔ `--today` 로 핀하지 않는다) ·
     `requested_by='tech-01'` · `session_id=NULL` · `note=NULL` 을 채운다.
     **`state` 는 기존 그대로** `'signed'` 11 / `'draft'` 1 (`RPR-2403`).
     ⚠ `'signed'` 11행은 새 CHECK ②를 만족해야 하므로 **`record_hash` 를 채워야 한다** —
     `05 §16` 이 *"시드 전량 NULL"* 이라고 적은 근거는 *"해시 규약을 Sprint 7 이 정한다"* 였고
     그 규약이 이번에 정해진다. 시드도 **같은 규약으로 계산**해 넣는다(MQ-909 와 동일 함수를
     `data/` 에 두고 양쪽이 읽는다 — D73).
  5. 자가검증 **3건 추가 (26 → 29)**:
     - **㉗** `repair_records` 불변식 — ⓐ `state='signed'` ⇔ `signed_at`·`record_hash`·`verified_by`
       전부 non-null(양성 축: 11행) ⓑ `state IN` 어휘 밖 **0건**(음성 축) ⓒ **미서명 1행이 존재**한다
       (이게 사라지면 `get_maintenance_metrics.excluded[]` 검증이 공허해진다).
       detail 에 **두 축의 실측값**을 찍는다.
     - **㉘** `error_codes` 출처 컬럼 짝 불변식 — `(actions_manual_id IS NULL) = (actions_page IS NULL)`
       위반 **0건** + **양성 축**: `error_codes` 총 행수 65 (0행이면 이 검사는 무의미하다).
     - **㉙** `record_hash` 재계산 대조 — 시드 11행의 저장 해시와 재계산 해시가 **전건 일치**
       (D84 가 처분 번들에 건 대조를 수리 증빙에도 건다).
- **엣지 케이스**:
  | 상황 | 기대 |
  |---|---|
  | `--with-error-codes` 없이 실행 | `error_codes` 0행 → `repair_records` 의 `(model,error_code)` 는 NULL (기존 동작 유지). ㉘ 의 양성 축은 **0행일 때 SKIP 이 아니라 FAIL** 로 두지 않는다 — 게이트 상태를 detail 에 적고 통과시킨다(기존 검사들과 같은 태도) |
  | 기존 DB 파일이 남아 있음 | `seed.py` 는 DROP/CREATE 재생성이므로 무영향 |
  | `state='signed'` 인데 `record_hash` 미계산 | **CHECK 가 INSERT 를 거부한다** — 시드가 즉시 죽는 것이 정상 |
  | `spikes/ownership_api_contract.py:62` 가 `repair_records` 를 SELECT | 명시적 컬럼인지 확인. `SELECT *` 면 컬럼 추가로 깨질 수 있다 → **확인 후 명시적으로 고친다** |
- **지켜야 할 결정**: D98 · D100 · D13·D33(복합 FK) · D23·D37(신원은 서버 stamp) · D39(UTC) ·
  D41(users FK) · D62(NULL 의 뜻) · D84 태도(해시 재대조) · **CLAUDE.md 시드 함정 2건**
- **회귀**: `data/seed.py` 자가검증 **26 → 29**. `spikes/ownership_api_contract.py`(10건) ·
  `spikes/approvals_contract.py`(26건) 무증감 통과.
- **DoD**:
  - `uv run python data/seed.py --with-error-codes` → **29건 전건 통과** ·
    `SELECT count(*) FROM error_codes` = **65**.
  - `PRAGMA table_info(repair_records)` → **19컬럼**, `state.notnull=1`.
  - `PRAGMA table_info(error_codes)` 에 `actions_manual_id`·`actions_page` 존재, 둘 다 `notnull=0`.
  - 음성 확인: `INSERT ... state='signed', record_hash=NULL` 이 **ABORT** 된다(수동 SQL 1줄로 확인,
    결과를 커밋 메시지에 적는다).
  - `rg -n "INSERT INTO error_codes VALUES" data/seed.py` → **0건**(명시적 컬럼 목록으로 바뀌었다).
  - `uv run ruff check data`.

---

#### MQ-905 — ⓐ iG5A 11건: 트러블슈팅 소스 추가 + 명칭↔코드 조인 → 후보 파일

- **복무 시나리오**: S1 · S3 (조치 절차 안내) · S4 (대조군)
- **변경 파일**:
  - `data/extract_error_codes.py` (수정 — **iG5A 경로만**)
  - `data/extracted/ig5a_action_map.json` (신규 — 조인 대장, 사람 검수 대상)
  - `data/extracted/error_codes_actions.candidate.json` (신규 — 후보 산출물)
- **인터페이스**:

```python
IG5A_TROUBLE_PAGES = range(22, 30)          # PDF 물리 p.22~29 (manifest: print_page_offset 0)
IG5A_ACTION_MAP = EXTRACTED / "ig5a_action_map.json"
CANDIDATE = EXTRACTED / "error_codes_actions.candidate.json"

def norm_name(s: str) -> str:
    """조인 키 정규화 — 공백 제거 · 괄호 내용 분리 · '인버터' 접두어 제거 · 조사 제거.
    P29 가 경고한 표기 흔들림('인버터 냉각 핀 과열' vs '냉각핀 과열')을 흡수한다."""

def parse_ig5a_trouble(pdf_path: Path) -> dict[str, dict]:
    """{norm_name: {'actions': [str], 'page': int, 'raw': str}} — 트러블슈팅 p.22~29"""

def join_actions(entries: list[dict], trouble: dict, amap: dict) -> tuple[list[dict], list[dict]]:
    """(채워진 후보, pending_review) — 조인 실패는 **버린다**(근처 항목으로 흘리지 않는다)"""

def verify_verbatim(cand: list[dict], pdf_path: Path) -> list[str]:
    """★ 각 조치문이 해당 페이지 텍스트에 **실재**하는지 대조. 반환 = 위반 목록(비어야 정상)"""
```

후보 파일 스키마:

```json
{
  "_status": "초안 — 사람 검수 대기 (D99). ⛔ 이 파일은 DB 에 적재되지 않는다",
  "_source_of_truth": "data/extracted/error_codes.json (이 파일은 병합 후보다)",
  "generated_at": "2026-08-xx",
  "counts": {"iG5A": 11, "S100": 0},
  "entries": [
    {
      "model": "iG5A", "code": "OHT",
      "actions": ["...원문 그대로..."],
      "actions_manual_id": "ig5a-troubleshooting",
      "actions_page": 24,
      "join_key": "냉각핀과열",
      "confidence": "high",
      "evidence_excerpt": "...대조용 원문 발췌..."
    }
  ],
  "_pending_review": ["iG5A ESt: 트러블슈팅에 대응 항목 없음 — 수기 매핑 필요"]
}
```

- **핵심 로직**:
  1. `check_manifest()` 를 그대로 재사용해 `ig5a-troubleshooting` 해시를 검증한다(D19).
     ⛔ `data/raw/` 는 읽기 전용 — 파일을 수정하지 않는다.
  2. p.22~29 를 `column_sentences()`(기존 함수) 로 읽어 **항목명 → 조치문** 사전을 만든다.
  3. `norm_name()` 으로 정규화해 기존 `error_codes.json` 의 `error_name` 과 조인한다.
     **조인 결과는 `ig5a_action_map.json` 에 대장으로 남긴다** — 무엇이 무엇에 붙었는지가
     검수의 대상이기 때문이다(`ig5a_code_map.json` 과 같은 형태·같은 이유, D19).
  4. **조인 실패는 버린다.** `span_key()` 주석이 이미 규약을 적어 뒀다 —
     *"가장 가까운 항목으로 흘려보내면 남의 조치문이 붙는다 … 엉뚱한 에러코드에 붙은 조치는 누락보다 나쁘다."*
     실패분은 `_pending_review` 로 간다.
  5. 🔴 **`verify_verbatim()` 을 반드시 통과해야 파일을 쓴다.** 정규화(공백·개행) 후 각 조치문이
     해당 페이지 텍스트의 **부분 문자열**이어야 한다. 하나라도 아니면 **파일을 쓰지 않고 중단**한다 —
     이것이 *"추출이 아니라 생성으로 새는 것"* 을 코드가 막는 지점이다(safety-guardrail).
  6. ⛔ **`error_codes.json` 을 쓰지 않는다** (D99). 열어서 읽기만 한다.
- **엣지 케이스**:
  | 상황 | 반환 |
  |---|---|
  | 조인 0건 | **`SCANNER_BLIND` 로 중단**한다. "없다"와 "정규식이 죽었다"를 구분해야 한다 |
  | 한 코드에 후보 2개 이상 | `confidence: "ambiguous"` + `_pending_review` 로. **자동 선택하지 않는다** |
  | `ESt`(로더 이상 계열) 처럼 대응 항목이 아예 없음 | `_pending_review` 에 남기고 `actions` 를 비운다. **지어내지 않는다** |
  | 조치문에 "10분" 이 아닌 값(5분 등)이 있음 | 그대로 추출하되 `_pending_review` 에 **안전 문구 플래그**를 단다 → MQ-911 이 별도 절로 올린다 |
  | `verify_verbatim` 위반 1건 이상 | **파일 미생성 + exit 1** |
- **지켜야 할 결정**: D99(후보 격리) · D100(출처 기록) · D19(manifest·승인 유도) · D24(추출 전략) ·
  D26(물리 페이지) · **절대규칙 3**(안전 문구는 매뉴얼 근거 없이 생성 금지) · **절대규칙 5**(`data/raw/` 읽기 전용)
- **회귀**: 신규 스파이크 없음. 대신 **MQ-902 의 triage 재실행**이 판정 소스다.
  `data/extracted/error_codes.json` 의 **sha256 불변**을 DoD 로 건다.
- **DoD**:
  - `uv run python data/extract_error_codes.py` 재실행 후:
    - `data/extracted/error_codes.json` **해시 불변** · `SELECT count(*) FROM error_codes` = **65**.
    - `error_codes_actions.candidate.json` 의 `entries` 가 **iG5A 11건 중 N건**(N 실측 기록) ·
      `_pending_review` 에 나머지가 **이유와 함께** 남는다.
    - `verify_verbatim()` 위반 **0건** (출력에 대조한 문장 수를 함께 찍는다 = 양성 축).
  - `uv run python data/extract_triage.py` → iG5A 라벨이 `SOURCE_MISSING` → **`OK`(후보 반영 기준)** 로
    이동한 건수가 리포트에 찍힌다.
  - `uv run ruff check data`.

---

#### MQ-907 — ⓑ S100 26건: 셀 내 줄바꿈 분해 실패 재추출 (OCR 없음)

- **복무 시나리오**: S1 · S3
- **변경 파일**: `data/extract_error_codes.py` (수정 — **S100 경로만**) ·
  `data/extracted/error_codes_actions.candidate.json` (추가 기입)
- **인터페이스**: 기존 `parse_s100()` 내부의 remedy 분해 로직만 교체. **공개 시그니처 변경 없음.**
- **핵심 로직**:
  1. 원인은 `manual_eda.md:97` 이 이미 지목했다 — *"셀 내 줄바꿈이 **문장 중간에서** 발생."*
     기존 코드도 이미 그 자리에 주석을 남겼다(`:260` *"bbox is None 을 건너뛰면 actions 가 통째로 비고"*).
     → **bbox 없는 셀·y 구간 밖 문장의 처리**를 고친다.
  2. 불릿 재조립: `split_bullets()` 가 문장 중간 개행을 **먼저 이어 붙인 뒤** 불릿 기호로 자르도록 순서를 고친다.
  3. **`span_key()` 의 "못 고르면 버린다" 규약은 그대로 유지한다.** 회수율을 올리려고 이 규약을 풀면
     *"Out Phase Open 이 이웃 항목 조치 6건을 흡수"* 한 사고가 재발한다.
  4. 회수분은 **후보 파일에 append**(D99). 정본 미수정.
  5. ⛔ **유료 OCR 을 호출하지 않는다.** 이 태스크로도 안 풀리는 페이지는 triage 의
     `RE_OCR_CANDIDATE` 로 남기고 **비용 견적만** 리포트에 적는다.
- **엣지 케이스**:
  | 상황 | 기대 |
  |---|---|
  | 🔴 **기존 성공분 오염** | **S100 의 기존 보유 15건 `actions` 가 한 글자도 변하지 않아야 한다.** 파서 수정 전후 diff **0** 을 DoD 로 건다 — 이게 이 태스크에서 가장 중요한 안전망이다 |
  | `causes` 가 변함 | ⛔ **범위 밖.** `causes` 는 결측 0건이므로 손댈 이유가 없다. 변하면 회귀다 |
  | `_unparsed` 증가 | 증가 0 이어야 한다 |
  | MQ-905 의 iG5A 후보가 사라짐 | 같은 파일을 순차 수정하므로 **append 로만** 쓴다. iG5A 11건이 남아 있는지 확인 |
- **지켜야 할 결정**: D99 · D100 · D24 · D26 · 절대규칙 3 · 절대규칙 5
- **회귀**: MQ-902 triage 재실행 + `verify_verbatim()`(905 가 만든 함수를 S100 페이지에도 적용).
- **DoD**:
  - S100 `actions` 결측 **26 → M**(M 실측 기록. ⛔ 목표치를 지어내지 않는다).
  - **기존 보유 15건 diff 0** (스크립트가 대조 결과를 출력한다).
  - `_unparsed` 증가 **0** · `causes` 변화 **0** · `error_codes.json` 해시 **불변**.
  - `verify_verbatim()` 위반 **0건** · iG5A 후보 11건 **잔존 확인**.
  - `uv run python data/extract_triage.py` 의 `CELL_SPLIT` 페이지 수 감소분이 리포트에 찍힌다.

---

#### MQ-906 — `create_repair_record` (세 번째 쓰기 도구) · `04 §16`

- **복무 시나리오**: **S19**
- **변경 파일**:
  - `mcp_server/tools/create_repair_record.py` (신규)
  - `mcp_server/db.py` (수정 — `repair_writer()` + `_REPAIR_GUARDS`)
  - `mcp_server/server.py` (수정 — `full` 프로파일 블록에 등록)
  - `docs/04_MCP_TOOLS.md` (수정 — **§16 신설** + 머리말 개수 8 → 9 / 15 → 16)
- **인터페이스**:

```json
// input — equipment_id·work_type·repair_scope·cost·parts 는 **필수**(기본값 없음, D80)
{
  "equipment_id": "INV-L3-01",          // ★ required
  "work_type": "UNPLANNED",             // ★ required. PLANNED | UNPLANNED (12 §7 — 미기재 거부)
  "repair_scope": "RESTORE",            // ★ required. RESTORE|UPGRADE|OVERHAUL|REPLACE_UNIT
  "cost": 850000,                       // ★ required. > 0 인 정수
  "parts": [{"part_no": "FAN-IG5-01", "serial": "SN-88214", "qty": 2}],  // ★ required, 1건 이상
  "downtime_hours": 6.5,                // optional. MTTR 의 유일한 원천 (12 §9)
  "model": "iG5A", "error_code": "OHT", // optional (짝). enum(D6·D13) + FK 검증(D33)
  "note": "냉각팬 교체"                  // optional. 승인자가 3초에 읽는 한 줄 (D5 태도)
}
// output
{
  "status": "ok",
  "repair_id": "RPR-2413",              // 채번 RPR-%04d — 시드 2401~2412 다음
  "state": "draft",                     // ★ 리터럴. 파라미터가 아니다
  "equipment_id": "INV-L3-01",
  "work_type": "UNPLANNED",
  "part_class": "CRITICAL",             // ★ parts 테이블 조회 결과. 파라미터가 아니다
  "expenditure_class": "REVENUE",       // ★ data/maint_value.expenditure() 산출. 파라미터가 아니다
  "expenditure_reason": "…",            // 산출 근거 (HOLD 도 정상 값이다)
  "cost": 850000, "downtime_hours": 6.5,
  "record_hash": null,                  // ★ 서명 시 백엔드가 계산한다 (12 §7 · D84 태도)
  "next_step": "이 기록은 확정이 아니다. 제출 후 팀장이 서명해야 증빙이 된다.",
  "disclaimer": "…"                     // 지출 분류는 회계 판단의 참고값이라는 고지 (D65 태도)
}
```

- **핵심 로직**:
  1. **입력 검증 → 조회 → 산출 → INSERT** 순서. 거부할 입력으로 DB 를 열지 않는다
     (`create_po_draft`·`generate_disposal_document` 와 같은 어휘).
  2. `parts[*].part_no` 를 `parts` 테이블에서 전부 조회한다. 하나라도 없으면 `error/unknown_part`
     (+ `missing[]`). **LLM 이 지어낸 품번이 정비 이력에 남을 경로를 막는다** — D33 이 에러코드에 건 방어를
     부품에도 건다.
  3. `part_class` 산출: 조회한 부품 중 **하나라도 `CRITICAL` 이면 `CRITICAL`**, 전부 `CONSUMABLE` 이면
     `CONSUMABLE`, 값이 없는 부품이 섞이면 **`NULL` + `not_considered` 문장**(0 이나 임의값으로 메우지 않는다).
  4. `expenditure_class` 산출: `data.maint_value.expenditure(con, part_class=…, repair_scope=…, amount=cost)`.
     **`HOLD` 는 실패가 아니라 판정**이므로 그대로 저장한다(DDL CHECK 가 허용).
     `part_class` 가 NULL 이면 지출 분류도 **NULL + 사유**(입력 없이 판정하지 않는다).
  5. `(model, error_code)` 는 짝이거나 둘 다 NULL. `model` 은 enum(`iG5A`|`S100`) 강제(D6·D13),
     `error_code` 는 대문자 canonical 2~4자 + FK.
  6. `db.repair_writer()` 로 **INSERT 만**. `state='draft'`, `performed_by/verified_by/signed_at/
     record_hash/requested_by/session_id` 는 **NULL 리터럴**로 박는다.
  7. `repair_id` 채번: `SELECT max(...)` 로 `RPR-` 접두 4자리 숫자의 최대 + 1.
     동시성 한계는 **P19 그대로**(단일 사용자 데모 전제) — 새 P 를 만들지 않는다.
  8. `server.py` 등록은 **`if TOOLS_PROFILE == "full":` 블록 안에만.**
- **엣지 케이스**:
  | 입력 | 반환 |
  |---|---|
  | `parts` 가 빈 배열 | `error` / `invalid_input` — 부품 없는 수리 증빙은 §8 증빙 패키지에서 쓸모가 없다 |
  | `cost <= 0` · 정수 아님 | `error` / `invalid_input` (폴백 금지 — `assess_repair_value` 와 같은 태도) |
  | `work_type` enum 밖 | `error` / `invalid_input`. **미기재 거부는 `12 §7` 의 명시 규칙** |
  | `repair_scope` enum 밖 | `error` / `invalid_input` (모르는 scope 를 RESTORE 로 접지 않는다) |
  | `equipment_id` 미존재 | `error` / `unknown_equipment` |
  | `error_code` 가 `error_codes` 에 없음 | `error` / `integrity` — **FK 가 막는다.** S4 의 환각 방지가 정비 이력까지 이어진다 |
  | `error_codes` 0행 상태(게이트 전) | 같은 `integrity`. 코드 없이 부르면 정상 동작한다 |
  | 도구가 UPDATE 를 시도 | TEMP TRIGGER 가 **ABORT** (스파이크가 실제 SQL 로 증명한다) |
  | DB 파일 없음 | `error` / `db_missing` (예외를 던지지 않는다, D9) |
- **지켜야 할 결정**: **D98**(전용 writer·프로파일·비파라미터 목록) · D10(draft INSERT 만) ·
  D9(status 반환) · D80(필수 기본값 없음) · D12 태도(등급을 추측하지 않는다) · D13·D33(복합키 FK) ·
  D6(model enum) · D23·D37(신원 서버 stamp) · D65(고지) · D69·D88(프로파일)
- **회귀**: `spikes/write_tool_contract.py` **2종 → 3종**(㉓~ 추가) — MQ-913 소유. ·
  `spikes/tools_profile_contract.py` core 7 / full **16**.
- **DoD**:
  - `MAINTQ_TOOLS_PROFILE=full` 로 서버 기동 시 도구 **16종**, 기본(`core`)에서 **7종**.
  - `rg -n "override|signed_at|record_hash|performed_by|verified_by|session_id|requested_by" \
    mcp_server/tools/create_repair_record.py` → **파라미터 시그니처에 0건**.
  - `docs/04_MCP_TOOLS.md` 에 **§16** 이 있고 머리말이 *"확장 9종(읽기 7 + 쓰기 2)= 총 16종"* 으로 갱신됐다.
  - `uv run python data/seed.py --with-error-codes` 후 도구 1회 호출 → `repair_records` 1행 추가,
    `state='draft'`, `signed_at IS NULL`, **`get_maintenance_metrics` 의 `n_repairs_signed` 불변**
    (미서명은 지표에 안 든다 — 이게 D98 CHECK ③의 목적이다).
  - `uv run ruff check mcp_server`.

---

#### MQ-908 — 확장 도구 REST 노출 5종 (D73·D101)

- **복무 시나리오**: S1+ (3지 판단) · S10 (근거 번들)
- **변경 파일**:
  - `backend/services/maint_value.py` (신규)
  - `backend/routers/maint_value.py` (신규)
  - `backend/main.py` (수정 — 라우터 등록)
- **인터페이스**:

```
GET  /api/assets/{asset_id}/metrics?window_months=12          → get_maintenance_metrics
POST /api/equipment/{equipment_id}/repair-value               → assess_repair_value   (무저장)
       body: { failed_part, repair_cost, repair_scope? }
GET  /api/parts/{part_no}/criticality                         → classify_part_criticality
POST /api/expenditure/classify                                → classify_expenditure  (무저장)
       body: { part_no? | part_class?, repair_scope, amount }
GET  /api/assets/{asset_id}/evidence-bundle?disposal_mode=SALE&disposal_date=
                                                              → build_evidence_bundle 상당
```

- **핵심 로직**:
  1. 앞의 넷은 `data.maint_value` 를 호출한다(MQ-903 산출물). **`mcp_server` 를 import 하지 않는다**(D15).
  2. **다섯 번째는 옮기지 않는다** — `backend/services/decisions.rebuild_bundle(con, asset_id,
     disposal_mode, disposal_date)` 가 **이미 `build_evidence_bundle` 의 조립을 그대로 재현**한다(D84 경로).
     라우터는 그것을 부르고 `(bundle, bundle_hash)` 를 응답한다. **세 번째 사본을 만들지 않는다.**
  3. **역할 게이트를 두지 않는다** — 전부 읽기 판정이다. `require()` 를 부르지 않으므로 403 이 나오지 않고,
     그래야 완료 기준 *"권한 위반 403 차단 100%"* 에 권한과 무관한 것이 섞이지 않는다(D38·D71 선례).
  4. **아무것도 저장하지 않는다.** `POST` 두 개는 입력이 본문이라 POST 일 뿐이고, 그 사실을 라우터
     docstring 과 `06_REPO_API` 에 명시한다(`/disposal/precheck` 가 이름으로 한 것을 문서로 한다).
  5. 오류 매핑: 도구 `status`/`reason` 을 **재포장하지 않고** 본문에 그대로 싣는다.
     - `not_found` 계열(`unknown_asset`·`unknown_equipment`·`unknown_part`·`no_host_asset`) → **404 + 본문**
     - `invalid_input` → **422**
     - `rule_catalog_not_loaded` → **503**(재시도로 풀리는 것만 503 — `06 §2.6` 규약)
     - `law_text_unavailable` → **409**(재시도해도 같은 답)
     - 그 밖 `error` → **500**
  6. `build_evidence_bundle` 응답에는 **`hash_fixed` 의미를 그대로 싣는다** — 번들 해시가 고정하는 것은
     **5키뿐**이고 렌더된 문서는 그 밖이다(`12 §8`).
- **엣지 케이스**:
  | 상황 | 기대 |
  |---|---|
  | `MAINTQ_TOOLS_PROFILE` 미설정(core) | **5개 전부 200 이어야 한다** (D73). 이게 이 태스크의 핵심 DoD |
  | `window_months` 가 음수·비정수 | 422. 조용히 무시하지 않는다 |
  | 지표가 전부 `null` 인 자산(9자산 중 6) | **200 이고 정상 응답이다.** `null` 을 404 로 바꾸지 않는다 — "데이터 부족"은 실패가 아니다 |
  | `classify_expenditure` 가 `HOLD` | **200.** `HOLD` 는 실패가 아니라 *"경계 사안이라 단정하지 않는다"* 는 판정이다. 4xx 로 만들면 계약 위반 |
  | `part_no` 와 `part_class` 를 **둘 다** 보냄 | 422 (`either-or`). 둘이 어긋나면 어느 쪽이 이겼는지 아무도 모른다 |
  | `part_no` 만 보냄 | 서버가 `classify_part_criticality` 로 채운다 — **④ 입력 의존을 서버가 해소**한다 |
- **지켜야 할 결정**: D101 · D73 · D15 · D38·D71(403/409 분리) · D62(null 은 null) · D64(OEE 불산출) ·
  D65·D70·D74(고지 필드 그대로 전달) · D84·D86(번들·렌더 구분)
- **회귀**: `spikes/api_contract.py`(28건) **무증감** — `/api/po` 는 한 줄도 건드리지 않는다.
  신규 검사는 MQ-913 이 `repair_flow_contract` 에 붙이지 않고 **별도로 `asset_tools_contract` 에 REST 축을
  추가하지 않는다** — 대신 MQ-913 이 `spikes/ownership_api_contract.py` 패턴을 따라 **5경로 × core 프로파일**
  검사를 신규 스위트에 넣는다.
- **DoD**:
  - `MAINTQ_TOOLS_PROFILE` **미설정** 상태에서 5경로 전부 200(또는 정의된 4xx) 응답.
  - `GET /health` 의 `tools` = **7**, `tools_profile` = `core` — **평가 경로 무영향의 증명**.
  - `rg -n "mcp_server" backend/services/maint_value.py backend/routers/maint_value.py` → **0건**.
  - `rg -n "def rebuild_bundle" backend/services/decisions.py` → **1건**(새로 만들지 않았다는 증명).
  - `uv run python spikes/api_contract.py` → **28건 무증감 통과**.
  - `uv run ruff check backend`.

---

#### MQ-909 — 수리 증빙 제출·서명·반려 API + 통합 큐 배선 (D85)

- **복무 시나리오**: **S19** (+ S10 의 증빙 소비)
- **변경 파일**:
  - `backend/services/repairs.py` (신규)
  - `backend/routers/repairs.py` (신규)
  - `backend/services/approvals.py` (수정 — `_repair_item()` + 조립)
  - `backend/main.py` (수정 — 라우터 등록)
  - `data/repair_hash.py` (신규 — **해시 규약 단일 출처**, seed 와 backend 가 함께 읽는다, D73)
- **인터페이스**:

```
GET  /api/repairs?state=pending          # 역할 무관 조회 (정비사도 자기 요청 상태를 본다)
GET  /api/repairs/{repair_id}
POST /api/repairs/{repair_id}/submit     # draft → pending     (**technician만**, 아니면 403)
POST /api/repairs/{repair_id}/sign       # pending → signed    (**manager만**, 아니면 403)
POST /api/repairs/{repair_id}/reject     # pending → rejected  (**manager만**, body: {reason} 필수)
```

```python
# data/repair_hash.py — 서명 해시 규약의 단일 출처 (05 §16 이 미뤄 둔 규약)
HASHED_KEYS: Final[tuple[str, ...]] = (
    "repair_id", "equipment_id", "model", "error_code", "part_class", "work_type",
    "expenditure_class", "cost", "downtime_hours", "parts", "performed_by",
    "verified_by", "signed_at",
)
def canonical_json(obj) -> str: ...          # decisions.canonical_json 과 **동일 규약**
def compute_record_hash(row: dict) -> str:   # "sha256:…"
```

- **핵심 로직**:
  1. 상태 전이는 **`ALLOWED_FROM` 한 곳**을 지난다(`po.py`·`decisions.py` 선례). 불가 전이는 **409
     `invalid_transition`**.
  2. `submit`: `requested_by`·`performed_by` 를 `X-User` 로 stamp(D23·D37), `session_id` 는
     `COALESCE` 로 최초 1회만.
  3. `sign`: ⓐ `verified_by = X-User` ⓑ `signed_at = UTC now`(D39) ⓒ `record_hash =
     compute_record_hash(row)` — **세 값을 같은 UPDATE 에서** 쓴다. DDL CHECK ②가 하나라도 빠지면 거부한다.
     ⓓ **`performed_by == verified_by` 면 409 `self_sign`** — D4(진단자/승인자 분리)가 발주에서 한 것을
     증빙에서도 한다.
  4. `reject`: `reason` 필수(D38) → `note` 에 저장. `rejected` 는 종착역(P15 는 백로그).
  5. **append-only**: `signed` 이후 어떤 경로로도 UPDATE 하지 않는다. 정정은 새 레코드(`12 §7`) —
     **이번 스프린트는 정정 레코드 경로를 만들지 않는다**(범위 밖임을 docstring 에 명시).
  6. `approvals._repair_item()`:
     `title = f"{equipment_id} 수리 · {work_type_label}"` · `state` **원 어휘 그대로** ·
     `urgency: None`(수리 증빙에는 긴급도가 없다) · `verdict: None` · `requires_override: None` ·
     `detail_path = f"/api/repairs/{id}"`. **`_po_item`·`_decision_item` 과 같은 형태**.
  7. `services/approvals.py:27~29` 의 *"repair 는 항상 0건"* 주석을 **사실에 맞게 고친다.**
- **엣지 케이스**:
  | 상황 | 기대 |
  |---|---|
  | 🔴 **시드 12행이 큐에 나타난다** | `list_approvals()` 는 필터 없으면 전부 준다(po·disposal 과 동일). **11 signed + 1 draft = 12건이 보이는 것이 정상**이고, `spikes/approvals_contract.py ③` 의 *"0건"* 기대를 **정정해야 한다** |
  | 정비사가 `sign` | **403** |
  | 팀장이 `submit` | **403** (양방향으로 막아야 지표가 반쪽이 되지 않는다) |
  | `signed` 를 다시 `sign` | 409 `invalid_transition` |
  | `reason` 없이 `reject` | 422 |
  | 서명 후 해시 재계산 대조 | 같은 값이어야 한다(멱등) — `GET /api/repairs/{id}` 가 `hash_verified: true/false` 를 싣는다 |
  | seed 의 11행 해시와 규약 불일치 | **MQ-904 ㉙ 이 먼저 잡는다** — 같은 모듈을 쓰므로 어긋날 수 없다 |
- **지켜야 할 결정**: D98 · D10 · D23·D37 · D38(403/409·반려 사유) · D39(UTC) · D41(users FK) ·
  D84 태도(해시 대조) · D85(큐 형태·`state` 원 어휘·`null` vs `false`) · D73(해시 규약 공유)
- **회귀**: `spikes/approvals_contract.py` ③ **정정** · 신규 `spikes/repair_flow_contract.py`(MQ-913).
- **DoD**:
  - `GET /api/approvals?kind=repair` → **12건**(양성 축) · `kinds` 는 여전히
    `["po","disposal","repair"]` · `kind=nope` → **422**(음성 축 유지).
  - `GET /api/approvals` 전체 건수 = 기존 + 12.
  - 403 양방향 확인(정비사 sign / 팀장 submit).
  - `POST /repairs/{id}/sign` 후 `state='signed'` · `signed_at` non-null · `record_hash` 가
    `sha256:` 로 시작 · `get_maintenance_metrics` 의 `n_repairs_signed` 가 **+1**.
  - `rg -n "항상 0건" backend/services/approvals.py docs/06_REPO_API.md` → **0건**(MQ-918 이 문서 쪽을 맡되
    여기서 코드 주석은 고친다).
  - `uv run python spikes/api_contract.py` → 28건 무증감.

---

#### MQ-910 — `lookup_error_code` 에 `actions_source` 노출 (D100)

- **복무 시나리오**: S1 · S3 · S4
- **변경 파일**: `mcp_server/tools/lookup_error_code.py` (수정) · `docs/04_MCP_TOOLS.md §1`(MQ-918 이 문서 반영)
- **인터페이스**:

```json
{
  "status": "ok", "model": "iG5A", "code": "OHT",
  "actions": ["..."],
  "actions_source": null            // ★ 신설. {manual_id, page, print_page} | null
}
```

- **핵심 로직**:
  1. `actions_manual_id`·`actions_page` 를 SELECT 해서 **둘 다 있을 때만** 객체를 만든다.
  2. `print_page` 는 `manifest.json` 의 `print_page_offset` 을 적용해 **표시용으로만** 함께 싣는다(D32).
     저장·검증은 물리 페이지 그대로(D26).
  3. **`null` 의 뜻을 docstring·`04 §1` 에 명시** — *"출처가 기록되지 않았다"* 이지
     *"본문과 같은 페이지"* 가 아니다.
  4. ⛔ 다른 키를 건드리지 않는다. `actions` 배열 자체는 그대로다.
- **엣지 케이스**:
  | 상황 | 반환 |
  |---|---|
  | 컬럼이 전건 NULL(현재 상태) | `actions_source: null` — **전건 null 이 정상**이며, 그 사실을 스파이크가 **라벨로 기록**한다(D76-2 재발 방지 형식) |
  | 한쪽만 NULL | **DDL CHECK 가 애초에 막는다**(MQ-904). 도구는 방어 코드를 넣지 않는다 |
  | `manifest.json` 에 없는 `manual_id` | `print_page` 를 **생략**한다(오프셋을 0 으로 가정하지 않는다) |
- **지켜야 할 결정**: D100 · D26 · D32 · D1(정의는 lookup) · D9
- **회귀**: `spikes/lookup_contract.py` 12 → **+2**(MQ-913 소유) — ⓐ 키 존재 ⓑ *"현재 전건 null 이며
  그 이유는 병합 미완"* 을 **양성 축(65행 조회 성공)과 함께** 기록.
- **DoD**:
  - `uv run python spikes/lookup_contract.py` → **14건** 통과.
  - 응답 JSON 에 `actions_source` 키가 **항상 존재**한다(값이 null 이어도 키는 있다 — D54 가
    `pages` 에서 세운 규약과 같다).
  - `uv run ruff check mcp_server`.

---

#### MQ-911 — 사람 검수 패키지 (G1 의 입력)

- **복무 시나리오**: S1 · S3 (안전) / 인프라
- **변경 파일**: `data/analysis/actions_review.md` (신규) · `TODO_직접할일.md` (수정 — **§actions 절만**)
- **인터페이스**: 문서. 후보 파일에서 **기계적으로 생성**한다(손으로 옮겨 적지 않는다 — 옮기다 바뀐다).
- **핵심 로직**:
  1. 표 1 — **코드별 대조표**: `model` · `code` · `error_name` · 후보 `actions` · `actions_manual_id` ·
     `actions_page`(+ 인쇄 페이지 병기) · `join_key` · `confidence` · **자동/수기 구분**.
  2. 표 2 — 🔴 **안전 문구 별도 절**: 후보 조치문 중 활선·방전·대기시간·감전·고전압 키워드가 걸린 항목만.
     각 항목에 **원문 발췌**와 페이지를 붙인다. *"매뉴얼 명시값 '10분 이상' 과 어긋나는 표기가 있는가"* 를
     검수자가 한 화면에서 볼 수 있어야 한다(`00_MVP_SCOPE §5` · `manual_eda.md:76`).
  3. 표 3 — **`_pending_review`**: 조인 실패·모호 항목과 그 이유.
  4. 절 4 — **재승인 범위 제안(G2)**: *"기존 65건의 `code`·`error_name`·`causes`·`manual_page` 는
     변경 0 이며, 병합은 `actions`·`actions_manual_id`·`actions_page` 3필드만 건드린다."*
     그 주장을 **MQ-919 가 해시로 증명한다**는 사실을 함께 적는다.
  5. `TODO_직접할일.md` 에 3줄 등재 — ① 조치문 코드별 확인 ② **안전 문구 확인**
     ③ 승인 시 절차(`_status` 를 어디에 어떻게 적는가).
- **엣지 케이스**:
  | 상황 | 기대 |
  |---|---|
  | 후보가 0건 | 문서를 만들되 **"검수할 것이 없다"** 와 그 이유(추출 실패)를 적는다. 빈 표를 성공처럼 보이게 하지 않는다 |
  | 안전 키워드 0건 | *"키워드 스캔 대상 N건 중 0건 적중"* 으로 **스캔 규모를 함께** 적는다(양성 축) |
  | 후보 문장이 매우 김 | 표에서 자르지 않는다 — 잘린 절차문은 뒷부분을 지어낼 여지를 만든다(D53 태도) |
- **지켜야 할 결정**: D99 · D100 · D19 · D26·D32(페이지 표기) · **절대규칙 3** ·
  **CLAUDE.md**(사람 할 일은 Claude 가 대신 처리하지 않는다)
- **회귀**: 없음(문서). 단 생성 스크립트를 쓴다면 `ruff` 대상.
- **DoD**:
  - `data/analysis/actions_review.md` 에 표 3종 + 재승인 범위 절이 있다.
  - 표 1 의 행 수 = 후보 `entries` 수(**기계 생성 증명** — 두 수가 다르면 손으로 옮긴 것이다).
  - `TODO_직접할일.md` 에 `## actions 검수` 절이 신설되고 3항목이 **미체크** 상태다.
  - ⛔ 이 태스크는 **승인하지 않는다.** 승인 문구를 대신 적으면 게이트가 무의미해진다.

---

#### MQ-912 — 프론트 공통 배관 (API·타입·매퍼·표시 규칙)

- **복무 시나리오**: S1+ · S10 · S19 / 인프라
- **변경 파일**: `frontend/lib/api.ts` · `frontend/lib/types.ts` · `frontend/lib/mappers.tsx` ·
  `frontend/lib/maintValue.ts` (신규)
- **인터페이스**:

```ts
// api.ts — MQ-908·909 의 8경로
export const getMetrics       = (role: Role, assetId: string, windowMonths?: number) => ...
export const postRepairValue  = (role: Role, equipmentId: string, body: RepairValueBody) => ...
export const getCriticality   = (role: Role, partNo: string) => ...
export const postExpenditure  = (role: Role, body: ExpenditureBody) => ...
export const getEvidenceBundle= (role: Role, assetId: string, mode: string, date?: string) => ...
export const getRepairs       = (role: Role, state?: string) => ...
export const getRepair        = (role: Role, repairId: string) => ...
export const submitRepair / signRepair / rejectRepair = ...

// maintValue.ts — ★ 순수 함수만. React 무의존 · `@/` 별칭 무사용 (ui_honesty L1 의 전제)
export type Displayable = { text: string; kind: "value" | "insufficient" | "unknown" };
export function showMetric(v: number | null, unit: string): Displayable;
export function showTrend(t: string | null): Displayable;      // "insufficient_data" → 판단 근거 부족
export function estimateNotice(o: { source?: string }): string | null;   // D65·D74 고지 문구 유도
export function isHoldVerdict(v: string): boolean;             // HOLD 는 에러가 아니다
```

- **핵심 로직**:
  1. **`null`·`"insufficient_data"` 를 절대 빈칸·`0`·`"양호"` 로 접지 않는다.**
     `showMetric(null)` → `{text: "판단 근거 부족", kind: "insufficient"}`.
     근거: 코디네이터 실측 — **핵심 4지표 null 15/36(42%) · `mtbf_trend` `insufficient_data` 7/9**.
     도구 계약이 직접 경고한다 — *"값이 null 이거나 `mtbf_trend` 가 `insufficient_data` 면 데이터가
     부족한 것이지 '문제 없음'이 아니다."*
  2. `mappers.tsx` 에 **repair 어휘**를 추가한다. `state` 는 백엔드 원 어휘 그대로 받고
     **전역 매퍼가 표시를 정한다**(D87) — 컴포넌트가 상태 문자열을 갖지 않는다.
  3. `kind` 는 **유니온이 아니라 `string`** 으로 받는 기존 규약을 유지한다(백엔드가 어휘를 늘려도 안 깨진다).
  4. `maintValue.ts` 는 **React·별칭 무의존**이어야 한다 — 그래야 `ui_honesty` L1 이 단독 `tsc` 로 돈다.
     (⚠ 이 제약은 계약이다. `lib/ownership.ts` 가 같은 전제로 서 있다.)
- **엣지 케이스**:
  | 상황 | 기대 |
  |---|---|
  | 백엔드가 4xx + 본문 | **본문의 `reason` 을 버리지 않는다.** 축 C 의 핵심 계약(`04 §13` 하위 도구 실패 전파)이 여기서 죽으면 화면이 삼킨다 |
  | `verdict === "HOLD"` | 정상 판정. 에러 경로로 보내지 않는다 |
  | `mtbf_trend: null` vs `"insufficient_data"` | **다르게 표시**한다(전자는 미산출, 후자는 근거 부족) |
  | 새 `state` 값이 옴 | 매퍼가 **모르는 값을 성공색으로 칠하지 않는다** — 중립 + 원문 표시 |
- **지켜야 할 결정**: D87(전역 매퍼) · D62 · D65·D70·D74(고지) · D85(원 어휘) · D64(성능 점수화 금지)
- **회귀**: `tsc --noEmit` · `next build`. 검사 추가는 MQ-917.
- **DoD**:
  - `cd frontend && npx tsc --noEmit` 통과 · `npm run build` **라우트 10개 유지**(화면은 아직 없다).
  - `rg -n "from \"react\"|@/" frontend/lib/maintValue.ts` → **0건**.
  - `rg -n "\"insufficient_data\"|판단 근거 부족" frontend/lib/maintValue.ts` → 양쪽 다 존재.

---

#### MQ-914 — 수리 가치 판단 화면 (우선순위 1 + 3 + 4 + 5 집결)

- **복무 시나리오**: **S1+**
- **변경 파일**:
  - `frontend/app/(console)/technician/asset/[assetId]/value/page.tsx` (신규 라우트)
  - `frontend/components/asset/RepairValuePanel.tsx` (신규 — 3지 판단 본체)
  - `frontend/components/asset/CriticalityDrawer.tsx` (신규 — **드로어**)
  - `frontend/components/asset/ExpenditureCard.tsx` (신규 — **작은 카드**)
  - `frontend/components/asset/MetricsAside.tsx` (신규 — **근거 옆 보조 패널**)
- **인터페이스·배치 (사용자 확정 형태)**:

```
┌ /technician/asset/{id}/value ────────────────────────────────────────────┐
│ [AssetHeader]                                                            │
│ ┌ RepairValuePanel (assess_repair_value) ─────────┐ ┌ MetricsAside ────┐ │
│ │  verdict: REPAIR|REPLACE|SELL_AS_IS|HOLD|       │ │ (보조·근거 옆)    │ │
│ │           ROOT_CAUSE_FIRST                       │ │ MTBF/추세/MTTR/  │ │
│ │  estimates[] ← 추정치 고지 (D65·D74)             │ │ 가용도/예방비    │ │
│ │  not_considered[] ← 무엇을 보지 않았는가         │ │ ⚠ 대시보드 아님   │ │
│ │  [부품 칩] 클릭 → CriticalityDrawer 펼침         │ │                  │ │
│ │  ┌ ExpenditureCard (작은 카드) ────────────┐     │ │                  │ │
│ │  │ CAPITAL | REVENUE | HOLD + 근거          │     │ │                  │ │
│ │  └──────────────────────────────────────────┘     │ │                  │ │
│ └──────────────────────────────────────────────────┘ └──────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

- **핵심 로직**:
  1. **한 화면에 모으는 근거는 계약이다.** `04 §13`: *"하위 도구 실패를 삼키지 않는다 —
     `classify_part_criticality`·`get_maintenance_metrics` 중 하나라도 `status != "ok"` 면 그
     `status`·`reason` 을 그대로 전파한다."* → **UI 도 삼키지 않는다.**
     하위 실패 시 패널은 값을 비우고 **`reason` 을 그대로 표시**한다.
  2. `CriticalityDrawer` 는 **전용 페이지가 아니다** — 부품 칩 클릭 시 옆에서 펼쳐진다.
     닫아도 상위 판정은 유지된다(라우트 이동 없음).
  3. `ExpenditureCard` 는 **`part_class` 를 이미 갖고 있으므로** 입력 없이 렌더된다 —
     도구 설명이 요구한 *"`part_class` 는 추측하지 말고 먼저 확인해 넣을 것"* 이 구조적으로 충족된다.
     **`HOLD` 는 경고색이되 에러가 아니다.**
  4. `MetricsAside` 는 **격자 대시보드가 아니다.** 값 6개를 **근거 문장과 함께** 세로로 놓고,
     `null`/`insufficient_data` 는 **"판단 근거 부족"** 으로 표기한다.
     ⛔ **점수·등급·색 랭킹을 만들지 않는다** — D64 의 실질 위험은 OEE 계산이 아니라
     **MTBF·가용도를 성능 점수처럼 나열해 사실상 OEE 대시보드가 되는 것**이다(도구는 이미 OEE 를
     계산도 출력도 하지 않고 `not_considered` 에 금지 사유만 남긴다).
  5. **추정치 고지(D65·D74)는 접히지 않는 위치**에 둔다. `RESIDUAL_AT_LIFE_END`·`FLOOR` 가
     **아직 사람 동의 전인 가정**이라는 사실도 함께 노출한다.
  6. 상태 어휘·색 판정은 **전역 매퍼만** 쓴다(D87) — 컴포넌트에 상태 문자열·색 토큰·비교 0건.
- **엣지 케이스**:
  | 상황 | 화면 |
  |---|---|
  | 자산에 서명된 수리 0건(9자산 중 5) | 지표 대부분 "판단 근거 부족". **빈칸 아님** |
  | `verdict: ROOT_CAUSE_FIRST` | **3지 선택지를 그리지 않는다**(도구가 안 낸다 — 규칙 14). 반복 고장 안내가 먼저 |
  | 하위 도구 실패 | 값 없음 + `reason` 노출. ⛔ "일시적 오류"로 바꿔 쓰지 않는다 |
  | `market_value_*` null | 추정 불가 표기 + 사유. 0원으로 그리지 않는다 |
  | 부품이 `mfr_part_no: null` | **"공개되지 않음"**(D97). "미조사"·"없음"이 아니다 |
- **지켜야 할 결정**: **D64**(성능 점수화 금지) · D65·D70·D74(추정치·`mtbf_basis`·가정 고지) ·
  D87(전역 매퍼) · D97(NULL 의 뜻) · D62 · `04 §13`(하위 실패 전파)
- **회귀**: `spikes/ui_honesty_contract.py` L2 글롭이 `components/asset/*.tsx` 를 **자동 포함**하므로
  새 4파일이 즉시 스캔 대상이 된다. 검사 추가는 MQ-917.
- **DoD**:
  - `npm run build` → 라우트 **11개**.
  - 하위 도구 실패를 강제(예: 존재하지 않는 부품)했을 때 화면에 **`reason` 문자열이 그대로 보인다**.
  - 지표가 전부 null 인 자산에서 **"판단 근거 부족"** 이 6칸에 표시되고 **빈칸·0·"양호" 가 0건**.
  - `rg -n "REPAIR|REPLACE|HOLD|CLEAR|CRITICAL" frontend/components/asset/{RepairValuePanel,CriticalityDrawer,ExpenditureCard,MetricsAside}.tsx`
    → **판정 어휘 직접 비교·지역 맵 0건**(D87 · L2 규칙).
  - `npx tsc --noEmit` 통과.

---

#### MQ-915 — 근거 번들 화면 (우선순위 2) + 지출 분류 독립 페이지 (우선순위 4-ⓐ)

- **복무 시나리오**: **S10**(번들) · S1+(지출)
- **변경 파일**:
  - `frontend/app/(console)/technician/asset/[assetId]/evidence/page.tsx` (신규 라우트)
  - `frontend/app/(console)/manager/expenditure/page.tsx` (신규 라우트)
  - `frontend/components/asset/EvidenceBundlePanel.tsx` (신규)
  - `frontend/components/asset/ExpenditureForm.tsx` (신규)
- **핵심 로직**:
  1. **근거 번들 화면** — `build_evidence_bundle` 의 **5키**(D83)를 그대로 보여준다:
     `facts` · `laws` · `rules` · `evaluated` · `judgment` + `bundle_hash`.
     🔴 **`hash_fixed` 의 의미를 화면에 명시**한다 — 해시가 고정하는 것은 **5키뿐**이고 렌더된 문서·증빙
     패키지는 그 밖이다(`12 §8`). 이 사실을 숨기면 계층 3의 존재 이유가 무너진다.
  2. `MetricsAside`(MQ-914 산출물)를 **여기서도 근거 옆 보조로 재사용**한다 — import 만 하고 수정하지 않는다.
     사용자 지정 배치(*"근거 옆에 보조로"*)가 문자 그대로 성립하는 지점이다.
  3. **지출 분류 독립 페이지** — 입력을 어디서 얻는가:
     ⓐ **부품 선택기**(`parts` 목록) → 서버가 `classify_part_criticality` 로 `part_class` 를 채운다.
     ⓑ 사용자가 `part_class` 를 **직접 고르는 경로를 만들지 않는다** — 도구 설명이 *"추측하지 말고
     먼저 확인해 넣을 것"* 이라고 못박았고, 드롭다운은 그 추측을 UI 가 권하는 것이 된다.
     ⓒ `repair_scope`·`amount` 는 사용자 입력. `amount` 는 정수·> 0.
  4. `HOLD` 는 **경계 판정**으로 렌더한다(에러 아님). `HOLD` 사유 문장을 함께 보여준다.
- **엣지 케이스**:
  | 상황 | 화면 |
  |---|---|
  | `law_text_unavailable`(409) | **번들을 그리지 않는다.** 무엇이 없는지(`missing_law_refs`)와 할 일을 보여준다 |
  | `rule_catalog_not_loaded`(503) | 재시도 안내(이것만 재시도로 풀린다) |
  | 자산이 처분 대상이 아님 | 404 본문의 `reason` 을 그대로. "문제 없음"으로 읽히지 않게 |
  | `amount` 미입력 | 제출 버튼 비활성 + 사유. 0 을 기본값으로 넣지 않는다 |
  | 지출 판정 `HOLD` | 경계 표시 + 사유. **빨간 실패색 금지** |
- **지켜야 할 결정**: D83(번들 5키) · D84(해시) · D86(렌더는 저장본이 아니다) · D65 · D87 · D62
- **회귀**: MQ-917 이 `hash_fixed` 고지·`HOLD` 렌더를 검사로 고정.
- **DoD**:
  - `npm run build` → 라우트 **13개**.
  - 번들 화면에 **5키 전부**와 `bundle_hash`, **`hash_fixed` 설명 문장**이 있다.
  - `rg -n "hash_fixed" frontend/components/asset/EvidenceBundlePanel.tsx` → 존재.
  - 지출 페이지에 **`part_class` 직접 선택 UI 가 없다**(부품 선택만).
  - `npx tsc --noEmit` 통과.

---

#### MQ-916 — 승인 큐 `kind:"repair"` 상세

- **복무 시나리오**: **S19**
- **변경 파일**: `frontend/components/queue/RepairDetail.tsx` (신규) ·
  `frontend/components/screens/ApprovalQueueScreen.tsx` (수정)
- **핵심 로직**:
  1. 기존 구조를 그대로 따른다 — 목록은 `/api/approvals`, **상세는 `kind` 로 갈린다**
     (`po` → `PoDetail` · `disposal` → `DecisionDetail` · **`repair` → `RepairDetail`**).
  2. `RepairDetail` 은 `GET /api/repairs/{id}` 를 부른다. 부품·시리얼·`work_type`·`downtime_hours`·
     `part_class`·`expenditure_class`·`cost` 와 **서명 상태**를 보여준다.
  3. 서명 바는 `SignBar` 패턴을 따르되 **`override` 개념이 없다** — 수리 증빙에는 차단 판정이 없다.
     `verdict`·`requires_override` 가 `null` 로 오는 것을 **`false` 로 접지 않는다**(D62).
  4. `state` 표시는 **전역 매퍼**(MQ-912)만 쓴다.
  5. 🔴 **`self_sign` 409 를 사용자 언어로 보여준다** — "본인이 수행한 수리는 본인이 서명할 수 없습니다".
- **엣지 케이스**:
  | 상황 | 화면 |
  |---|---|
  | 목록에 12건이 갑자기 나타남 | 정상. 필터(`state`)로 좁힐 수 있게 한다 |
  | `signed` 항목 | 서명 바 대신 **서명 사실 + `record_hash` 앞 12자** 표시(불변 증빙임을 보여준다) |
  | `rejected` | 종착역. 재요청 버튼을 만들지 않는다(**P15 는 백로그**) |
  | `verdict: null` | 판정 칸 자체를 그리지 않는다. "통과"로 그리면 D62 위반 |
- **지켜야 할 결정**: D85(큐 형태) · D87 · D62 · D38(403·반려 사유) · **P15 승격 금지**
- **회귀**: `spikes/ui_honesty_contract.py` L2 글롭이 `components/queue/Decision*.tsx` 만 잡으므로
  **`RepairDetail.tsx` 를 L2 대상에 추가**해야 한다 → MQ-917 이 처리.
- **DoD**:
  - `npm run build` → 라우트 **13개 유지**(큐 안이라 라우트가 늘지 않는다).
  - 팀장 큐에서 repair 항목 선택 → 상세 렌더 · 서명 → 목록 상태 갱신.
  - `rg -n "\"pending\"|\"signed\"|\"draft\"" frontend/components/queue/RepairDetail.tsx` → **0건**(매퍼 경유).
  - `npx tsc --noEmit` 통과.

---

#### MQ-913 — 회귀 스파이크 (쓰기 도구 3종 · 수리 흐름 · 큐 · lookup · 프로파일)

- **복무 시나리오**: 인프라 (S19·S1~S4 계약 방어선)
- **변경 파일**:
  - `spikes/write_tool_contract.py` (수정 — **2종 → 3종**)
  - `spikes/repair_flow_contract.py` (**신규 — 28 → 29스위트**)
  - `spikes/approvals_contract.py` (수정 — ③ 정정)
  - `spikes/lookup_contract.py` (수정 — +2)
  - `spikes/tools_profile_contract.py` (수정 — full 15 → 16)
- **핵심 로직**:
  1. **`write_tool_contract` 에 `create_repair_record` 축 추가** — 기존 2종과 같은 방식으로 **증명**한다:
     ⓐ `repair_writer()` 커넥션으로 실제 UPDATE·DELETE SQL 을 날려 **ABORT 확인**
     (⛔ `draft_writer()`·`decision_writer()` 로 확인하지 않는다 — 잠기지 않은 경로를 통과시킨다)
     ⓑ 스키마에 `override`/`signed_at`/`record_hash`/`performed_by`/`verified_by`/`state` **키가 없다**
     ⓒ 미존재 부품 → `unknown_part` 이고 **`repair_records` 행 수가 그대로다**
     (실패했다고 "말하는" 것이 아니라 **아무것도 쓰지 않았음**을 센다)
     ⓓ `expenditure_class` 가 도구 산출값과 **DB 저장값이 일치**.
  2. **신규 `repair_flow_contract.py`** — REST 왕복:
     draft → submit(403 양방향) → sign(`self_sign` 409) → 해시 재계산 대조 → `signed` 재서명 409 →
     `reject` 사유 필수 → **서명 후 `get_maintenance_metrics` 의 `n_repairs_signed` +1**.
     그리고 **MQ-908 의 5경로를 `core` 프로파일에서 호출**해 200 을 확인한다(D73 증명).
  3. `approvals_contract ③` 정정 — *"0건"* → **양성 축(12건 · `kind` 별 분포) + 음성 축(`kind=nope` 422)**.
     ⛔ detail 에 결론이 아니라 **실측값**을 찍는다(`"repair=12 · kinds=3 · 422 확인"`).
  4. `lookup_contract` +2 — `actions_source` 키 존재 · 현재 전건 null.
     🔴 **부재 검사에 양성 축을 건다**: `not filled and rows == 65` 형태.
  5. `tools_profile_contract` — core **7** / full **16** · `create_repair_record` 의 required 3~5종 ·
     `int | str` 유니온 유지.
- **엣지 케이스**:
  | 상황 | 기대 |
  |---|---|
  | 실 DB 오염 | **임시 사본 + `MAINTQ_DB` 주입**(기존 스파이크 규약 그대로) |
  | Windows 소켓 고갈로 1건 실패 | **단독 재실행으로 확인**하고 그 사실을 보고에 적는다(CLAUDE.md 규약) |
  | 시드 12행 의존 | 행 수를 하드코딩하지 말고 **사본에서 실측**한 뒤 상대 비교 |
- **지켜야 할 결정**: D98 · D10 · D85 · D88 · D100 · **CLAUDE.md 부재검사 규칙**(양성 축 · detail 실측값)
- **DoD**:
  - `ls spikes/*.py` → **29개**.
  - 5스위트 전건 통과 · 총 건수가 **635 + Δ**(Δ 실측 기록). ⛔ 줄었으면 테스트가 사라진 것이다.
  - `uv run python spikes/write_tool_contract.py` 출력에 **UPDATE·DELETE ABORT 실측 문구**가 있다.
  - `rg -n "draft_writer|decision_writer" spikes/repair_flow_contract.py` → **0건**.

---

#### MQ-917 — `ui_honesty_contract` 확장 (D65·D74·D87·D64 방어선)

- **복무 시나리오**: 인프라 (축 C 전체의 방어선)
- **변경 파일**: `spikes/ui_honesty_contract.py` · `frontend/lib/__checks__/ui_honesty.ts`
- **핵심 로직**:
  1. **L1(순수 함수) 추가** — `lib/maintValue.ts` 를 컴파일해 `node` 로 실행:
     ⓐ `showMetric(null)` 이 `"0"`·`""`·`"양호"` **어느 것도 반환하지 않는다**
     ⓑ `showTrend("insufficient_data")` 가 `kind: "insufficient"`
     ⓒ `isHoldVerdict("HOLD") === true` 이고 **에러 종류로 분류되지 않는다**
     ⓓ `estimateNotice()` 가 목업 잔가 입력에 대해 **반드시 문자열을 반환**(고지 누락 불가)
  2. **L2 스캔 대상 확대** — `L2_EXTRA` 에 `components/queue/RepairDetail.tsx` 추가.
     (`components/asset/*.tsx` 는 기존 글롭이 자동 포함 — **그래서 MQ-914·915 이후에 돌려야 한다**.)
  3. **뮤턴트 추가 (방어선이 실제로 깨지는지 확인)**:
     ⓐ `showMetric(null) → "0"` 으로 바꾸면 L1 이 **깨져야 한다**
     ⓑ 컴포넌트에 `verdict === "REPAIR"` 를 주입하면 L2 가 **잡아야 한다**
     ⓒ 고지 문자열을 지우면 검사가 **깨져야 한다**
  4. **D64 축 신설** — 스캔 대상에 `OEE`·`종합효율`·`성능가동률` 문자열 **0건** +
     **양성 축**(스캔한 파일 수 > 0 · 지표 문자열이 실제로 발견됨). *"없다"* 만 주장하지 않는다.
  5. `L2_FILES_FLOOR` 를 실측에 맞게 올린다(줄면 파일이 빠진 것이다).
- **엣지 케이스**:
  | 상황 | 기대 |
  |---|---|
  | 새 컴포넌트가 글롭에 안 잡힘 | `L2_FILES_FLOOR` 가 잡는다 |
  | `maintValue.ts` 가 React 를 import | **제약 게이트가 FAIL** — L1 이 단독 `tsc` 로 못 돈다 |
  | 뮤턴트가 안 깨짐 | **그 검사는 방어선이 아니다** → 판정 실패로 보고 |
- **지켜야 할 결정**: D87 · D65 · D74 · D64 · D62 · **CLAUDE.md 부재검사 규칙** · **P30**(기존 결함 2건은
  이번 범위 밖 — 새 검사에 같은 결함을 만들지 않는 것이 이 태스크의 책임)
- **DoD**:
  - `uv run python spikes/ui_honesty_contract.py` → **68 + Δ건** 통과(Δ 실측 기록).
  - 뮤턴트 3종이 **전부 실패를 유발**한다(출력에 실측 표시).
  - `L3_NOTICE`(실 데이터 렌더는 검증하지 않는다)가 여전히 출력 말미에 있다.

---

#### MQ-918 — 문서·개수 전파

- **복무 시나리오**: 인프라
- **변경 파일**: `CLAUDE.md` · `README.md` · `docs/README.md` · `docs/00_MVP_SCOPE.md` ·
  `docs/02_SCENARIOS.md` · `docs/04_MCP_TOOLS.md` · `docs/05_DB_SCHEMA.md` · `docs/06_REPO_API.md` ·
  `docs/07_BACKLOG.md` · `docs/10_DECISIONS.md`(**마커만**) · `docs/12_MAINT_VALUE.md` ·
  `docs/status/*.html` · `TODO_직접할일.md`(§actions 외)
- **핵심 로직 (전파 목록 — 빠뜨리면 다음 세션이 "했는데 안 한" 상태를 읽는다)**:
  1. **회귀 기준선** — spikes **29스위트/N건** · seed **29건** · pytest 46 · 프론트 라우트 **13개** ·
     `error_codes` **65건**. ⚠ 러너 출력을 그대로 옮긴다.
  2. **도구 개수** — 코어 7 + 확장 **9** = **16**, 쓰기 도구 **3종**.
     고칠 곳: `CLAUDE.md`·`docs/README.md`·`00_MVP_SCOPE`(인프라 절·확장 표 9번)·
     `04_MCP_TOOLS`(머리말·§16·reason 색인)·`07_BACKLOG`(경계 메모).
  3. **DB** — `05_DB_SCHEMA §1`(출처 컬럼)·**§16 개정**(컬럼 4 + CHECK 3) · 자가검증 목록 26 → 29.
     ⚠ **절 번호를 재배치하지 않는다**(§10 부재 규약 유지).
  4. **API** — `06_REPO_API` 에 **§2.8 수리 증빙** 신설 + §2.5 에 확장 REST 5종 + §2.7 의
     *"repair 는 현재 항상 0건"* **정정**.
  5. **시나리오** — `02_SCENARIOS` S19 행을 *"미구현 — Sprint 9"* → **구현 완료 + 도구 시퀀스**로.
  6. **백로그** — P25 를 ✅ 완료(Sprint 9)로 · P31 을 🟡 부분(triage + ⓐⓑ 회수, **병합은 사람 승인 대기**)으로.
     ⛔ **P30·P32 를 건드리지 않는다.**
  7. **D 범위 표기 5곳** — `D1~D97` → **`D1~D101`**.
  8. `docs/status/*.html` 의 개수·상태.
- **엣지 케이스**:
  - 숫자를 **기억으로 적지 않는다** — 러너를 실제로 돌려 출력에서 옮긴다.
  - `07_BACKLOG` P31 을 **✅ 완료로 쓰지 않는다** — 병합이 남아 있다.
  - `TODO_직접할일.md` 의 `## actions 검수` 절은 **MQ-911 소유** — 여기서 덮어쓰지 않는다.
- **DoD**:
  - `rg -n "D1~D97|D1-D97" docs/ CLAUDE.md README.md` → **0건**.
  - `rg -n "확장 8종|총 15종|쓰기 도구는 2종|항상 0건" docs/ CLAUDE.md backend/` → **0건**.
  - `rg -n "라우트 10개|28스위트|635건|자가검증 26" docs/ CLAUDE.md` → **0건**.
  - `docs/06_REPO_API.md` 에 `§2.8` 이 있고 `docs/04_MCP_TOOLS.md` 에 `§16` 이 있다.

---

#### MQ-919 — (조건부) 승인된 `actions` 병합 적재 + 재시드 + 회귀

- ⚠ **선행: 사람 검수(G1)·재승인 범위 확정(G2). 승인 전에는 착수하지 않는다.**
- **복무 시나리오**: S1 · S3 · S4
- **변경 파일**: `data/extracted/error_codes.json`(병합) · `data/extracted/ig5a_action_map.json`(승인 반영) ·
  `data/seed.py`(병합 검증 1건) · `spikes/lookup_contract.py`(전건 null 검사 → 실측 대조로 전환)
- **핵심 로직**:
  1. 후보 파일 중 **승인된 항목만** 정본에 병합한다. `actions`·`actions_manual_id`·`actions_page`
     **3필드만** 쓴다.
  2. 🔴 **병합 전후 해시 대조로 "그 밖은 안 바뀌었다"를 증명한다** — 각 엔트리의
     `(code, error_name, causes, manual_page, severity, display_code, related_parts)` 를 정준 직렬화해
     **병합 전후 해시가 65건 전건 동일**해야 한다. 하나라도 다르면 **중단**한다(G2 의 근거가 무너진다).
  3. `_status` 승격은 **`ig5a_action_map.json` 의 `pending_review` 가 비고 전 항목이 `high` 일 때만**
     유도된다(D19 방식 그대로 — 손으로 문자열을 쓰지 않는다).
  4. 재시드 → `SELECT count(*) FROM error_codes` = **65** 확인.
  5. `lookup_contract` 의 *"전건 null"* 검사를 **실측 대조**로 바꾼다(양성 축: 채워진 건수 = 승인 건수).
  6. **평가 재측정 절차만 문서화한다 (실행은 G3 승인 후)**:
     - `uv run python eval/run_eval.py --yes --repeat 3` 를 **병합 전/후 각각** 1회.
     - 판정은 **`stable_fail` → `stable_pass` 로 넘어간 칸으로만** 한다
       (`eval_gap_3rd.md §4`: 같은 코드·같은 문항이 2·3차에서 **7문항 뒤집혔다** — 단일 실행 비교는 무의미).
     - ⛔ `MAINTQ_TOOLS_PROFILE=full` 로 돌리지 않는다(D88 이 `SystemExit(2)` 로 막는다).
       확장 9번째 도구는 **core 에 없으므로** 평가 조건이 변하지 않는다.
- **엣지 케이스**:
  | 상황 | 기대 |
  |---|---|
  | 사람이 **일부만** 승인 | 승인분만 병합. 나머지는 후보 파일에 남는다 |
  | 안전 문구 수정 요구 | ⛔ **자동 반영 금지.** 원문과 다른 문장을 넣는 것은 생성이다 → 매뉴얼 재확인 후 별도 처리 |
  | 해시 대조 실패 | **병합 중단 + 보고.** 파일을 손대기 전에 멈춘다(`apply_fetch` 의 `LawMismatchError` 선례) |
  | 승인 0건 | 아무것도 하지 않는다. **실패가 아니다** |
- **지켜야 할 결정**: D99 · D100 · D19 · D33 · D60 · D88 · 절대규칙 3
- **DoD**:
  - `uv run python data/seed.py --with-error-codes` → 전건 통과 · `error_codes` **65**.
  - 병합 전후 **비-actions 필드 해시 65/65 동일**(출력에 실측).
  - `actions` 결측 **37 → K**(K 실측).
  - `uv run python spikes/lookup_contract.py` 통과.
  - ⛔ 평가 지표 개선을 **주장하지 않는다** — G3 이후 `--repeat 3` 2회 결과로만 말한다.

---

## 7. 범위가 크다 — 압축 순서 (tool-builder 가 판단할 것)

**19태스크 / 10스테이지는 이 레포의 스프린트 중 가장 크다**(Sprint 8 = 7태스크 / 5스테이지).
축이 셋이라 그렇다. 줄여야 한다면 **아래 순서로** 덜어낸다 — 위에서부터 잘라야 남는 것이 서로를 안 무너뜨린다.

| 순위 | 덜어낼 것 | 남는 것에 미치는 영향 |
|---|---|---|
| ① | **MQ-915**(근거 번들 화면 + 지출 독립 페이지) | 없음. 우선순위 2·4-ⓐ 가 다음 스프린트로. **914 가 이미 4-ⓑ(작은 카드)를 덮는다** |
| ② | **MQ-916**(큐 repair 상세) | 축 A 는 **API 까지 완결**된다. 화면 없이도 `/api/repairs` 로 검증 가능. 단 데모 서사가 반쪽 |
| ③ | **MQ-907**(ⓑ S100 26건) | ⓐ 11건만 회수. **triage(902)가 남아 있으므로 다음 스프린트가 이어받을 수 있다** — 그게 902 를 먼저 만든 이유다 |
| ④ | **MQ-910**(`actions_source` 노출) | D100 은 등재된 채로 남고 DDL 도 있다. 도구 출력만 다음으로 |
| ⑤ | **축 C 전체**(903·908·912·914~917) | ⚠ 이때 **MQ-901 의 D101 도 함께 보류**해야 한다. 결정만 남기고 안 지키면 문서가 거짓이 된다 |

⛔ **덜어내면 안 되는 것**: MQ-901(결정) · MQ-902(triage 계측) · MQ-904(DDL) · MQ-906(쓰기 도구) ·
MQ-909(서명 API) · MQ-913(회귀) · MQ-918(전파). 이 7개가 **축 A 의 최소 완결 집합**이고,
902 는 축 B 를 **다음 스프린트가 이어받을 수 있게 만드는 유일한 조각**이다.

---

## 참고 파일 경로 (절대 경로)

| 무엇 | 경로 |
|---|---|
| 쓰기 경계 (커넥션·트리거) | `C:\Users\ttogl\workspace\MaintQ\mcp_server\db.py` (`:70~93`) |
| 통합 큐 조립기 · *"repair 는 항상 0건"* 주석 | `C:\Users\ttogl\workspace\MaintQ\backend\services\approvals.py` (`:27~29`, `:105`) |
| 번들 재산출 (D84) — **세 번째 사본을 만들지 않는 근거** | `C:\Users\ttogl\workspace\MaintQ\backend\services\decisions.py` (`:252`, `:520`) |
| 산식이 두 벌이라는 자백 | `C:\Users\ttogl\workspace\MaintQ\backend\services\decisions.py:520` |
| REST 노출 선례 (역할 게이트 없음·무저장) | `C:\Users\ttogl\workspace\MaintQ\backend\routers\disposal.py` |
| `data/` 공유 계층 시그니처 규약 | `C:\Users\ttogl\workspace\MaintQ\data\ownership.py:764` (`verify(con, *, ...)`) |
| 추출 파이프라인 (iG5A `:369` · S100 `:260` · 승인 유도 `:438`) | `C:\Users\ttogl\workspace\MaintQ\data\extract_error_codes.py` |
| `error_codes` 적재 게이트 · 위치 인자 INSERT | `C:\Users\ttogl\workspace\MaintQ\data\seed.py` (`:1687`, `:1798`) |
| `repair_records` DDL · 시드 12행 | `C:\Users\ttogl\workspace\MaintQ\data\seed.py` (`:333`, `:873`, `:1317`) |
| 매뉴얼 대장 (`ig5a-troubleshooting` 등록·해시·오프셋) | `C:\Users\ttogl\workspace\MaintQ\data\raw\manifest.json` |
| 결측 원인 원문 | `C:\Users\ttogl\workspace\MaintQ\data\analysis\manual_eda.md` (`:97`, `:100`) |
| 실행 간 요동 · 판정 규칙 | `C:\Users\ttogl\workspace\MaintQ\data\analysis\eval_gap_3rd.md` (`§4`) · `C:\Users\ttogl\workspace\MaintQ\eval\run_eval.py` (`:44~48`, `:649~658`) |
| UI 정직성 방어선 (L2 글롭·뮤턴트) | `C:\Users\ttogl\workspace\MaintQ\spikes\ui_honesty_contract.py` (`:53~58`) |
| 쓰기 도구 계약 검증 선례 | `C:\Users\ttogl\workspace\MaintQ\spikes\write_tool_contract.py` |
| 큐 `kind=repair` 0건 기대 (정정 대상) | `C:\Users\ttogl\workspace\MaintQ\spikes\approvals_contract.py` (`:177~183`) |
| 프로파일 게이트 | `C:\Users\ttogl\workspace\MaintQ\mcp_server\server.py` (`:75~78`, `:154`, `:183`) |

---

## 8. 현실성 평가 (tool-builder · 2026-08-14)

> ⚠ 이 절의 번호는 원래 `## 7` 로 중복돼 있었다(§7 압축 순서와 같은 번호). **§8 로 정정했다.**

**규모 판정: 과대 · 계획 수정 필요: Y**

### 8-1. 계획서 주장의 실측 검증

계획서가 사실이라고 주장한 것을 **파일에서 직접 확인**했다. 계획을 믿고 넘기지 않았다.

| 계획서의 주장 | 실측 | 판정 |
|---|---|---|
| `mcp_server/db.py:70~93` writer 2개 + *"잠겼다고 믿는 지점이 실제로는 안 잠긴다"* 주석 | `:70~74` 주석 실재 · `_PO_GUARDS`(75~83) · `_DECISION_GUARDS`(85~93) · `_guarded_writer(guards)` 팩토리(96~116). `repair_writer()` 는 `_REPAIR_GUARDS` + 3줄로 추가 가능 | ✅ 참 |
| `backend/services/decisions.py:520` *"산식이 두 벌 존재한다"* | 정확히 그 문장. `_metrics()` 는 `:517` | ✅ 참 |
| `backend/services/approvals.py:27~29` *"repair 는 항상 0건"* · D85 가 자리를 예약 | `:27~29` 실재(`:39`·`:105` 에도 같은 주장). `KINDS=("po","disposal","repair")` | ✅ 참 |
| `data/seed.py` `repair_records` DDL(`:333`, 15컬럼·CHECK 4종) · 시드 12행(signed 11 / draft 1) · 위치인자 `INSERT INTO error_codes VALUES (?×9)`(`:1798`) | 전건 일치. `record_hash` 는 현재 **전건 NULL** | ✅ 참 |
| `error_codes.json` 실측: 총 65 / iG5A 24(actions 결측 11) / S100 41(결측 26) / causes 결측 0 / `_unparsed` 0 / `_pending_review` 0 | 직접 카운트 — **전건 일치** | ✅ 참 |
| `spikes/asset_tools_contract.py` 49건이 MQ-903 리팩터 후 무변경 통과 가능 | 실행 **49건 전건 PASS**. import 가 공개 진입점 6종뿐이고 내부 상수·`_assess`·`_decide` 참조 **0건** | ✅ 참 |
| `ui_honesty_contract.py` L2 글롭이 `components/asset/*.tsx` 자동 포함 | `:55 L2_GLOBS` 확인 · `:312~314` 확장 · `L2_FILES_FLOOR=8` | ✅ 참 |
| `RepairDetail.tsx` 는 L2 글롭(`Decision*.tsx`)에 안 잡혀 `L2_EXTRA` 필요 | 확인 | ✅ 참 |
| `ig5a-troubleshooting` PDF 실재 + manifest 등록 + p.22~29 에 조치문 표 존재 | `iG5A_Troubleshooting_Rev1.0_150415.pdf`(46p) 실재 · manifest 에 sha256·`role=supplement` 등록 · **PDF 직접 열람** 결과 물리 p.22~28 에 `키패드 표시/고장 상태/내용` + `원인 \| 조치사항` 표가 코드별로 존재(과전류·과전류2·인버터 과부하·출력 결상·저전압·브레이크 제어 이상 …). 한글 항목명 조인키 성립 | ✅ 참 — **축 B-ⓐ 는 실현 가능하다** |
| 확장 도구 4종에 `_asset_ref.py` 의존이 있을 수 있다(MQ-903 엣지케이스) | `_asset_ref` 는 **처분 3종 전용**이고 이 4종은 쓰지 않는다. `data/rules/engine.py` 도 `data.*` 를 import 하지 않아 순환 없음 | ⚠ **기우 — 엣지케이스 삭제 대상** |
| `ownership_api_contract.py:62` 가 `SELECT *` 라 컬럼 추가로 깨질 수 있다 | `:57` 은 `SELECT COUNT(*)`. `SELECT *` 는 `assets` 에만 | ⚠ **기우 — 무해** |
| manifest `ig5a-troubleshooting.print_page_offset: 0` (D100 §3-쟁점③ 이 전제로 삼음) | ❌ **거짓.** PDF 실측 — 물리 p.20→인쇄 "19", p.22→"21", p.24→"23", p.28→"27". `backend/manifest.py:141`(`printed = page - offset`) 규약으로 **실제 offset = 1**. manifest `:28~29` 는 값도 `page_note`(*"물리 = 인쇄"*)도 틀렸다 | ❌ **거짓** |
| MQ-905 DoD *"재실행 후 `error_codes.json` 해시 불변"* | ❌ **거짓.** `extract_error_codes.py:483` 이 정본을 **무조건 덮어쓰고** `:474 generated_at=date.today()`(현재 파일은 `2026-08-05`) · `:473 _status` 재유도 | ❌ **거짓** |
| *"19태스크/10스테이지는 이 레포 최대"* | sprint-7 = 13계획(분할 후 20 실행)/8스테이지 · sprint-8 = 7/5. **계획 시점 기준 최대 맞음** | ✅ 참 |

#### 코디네이터 정정 — 오프셋 위험의 **범위**

tool-builder 는 오프셋 오류가 *"`backend/manifest.py`·`sse.py`·`frontend/lib/citation.ts` 를 통해 인용이 전건 −1 로 표시된다"* 고 보고했다. **이 부분은 과장이다.**
`backend/manifest.py:84~93 manual_entry()` 는 조회 키가 **model** 이고 `role="primary"` 를 우선한다
(docstring: *"보충 자료는 오프셋 원천이 아님"*). `ig5a-troubleshooting` 은 `supplement` 이라
**현재 소비 경로가 존재하지 않는다.** `spikes/citation_render.py:140` 의 ⑨ 검사도 `role=="primary"` 만 읽는다.
→ **오늘 깨진 화면은 없다.** 그러나 위험은 사라진 게 아니라 **MQ-910 으로 옮겨져 있다**:
`actions_source: {manual_id, page, print_page}` 를 노출하는 순간 오프셋을 **manual_id 로 조회**해야 하는데
`manifest.py` 에는 그 함수가 없고 **어느 태스크도 소유하지 않는다.** (→ R7)

### 8-2. 리스크

| # | 스테이지 | TASK | 리스크 | 심각도 |
|---|---|---|---|---|
| R1 | 3→5 | MQ-906 / MQ-913 | 16번째 도구가 Stage 3 에 들어오는데 스파이크 정정은 Stage 5. `tools_profile_contract.py:146` 은 `names == CORE ∪ EXT` **집합 동일**을 요구하고 `s10_smoke.py:73 EXPECTED_TOOLS_FULL = 15` 다 → **Stage 3·4 회귀 게이트가 설계상 반드시 빨간불** | 🔴 |
| R2 | — | MQ-913 | **`spikes/s10_smoke.py`(17건)가 어느 태스크의 소유도 아니다.** §4 격리표·MQ-913 변경파일 목록 어디에도 없다 | 🔴 |
| R3 | 4→5 | MQ-909 / MQ-913 | `approvals_contract.py:177~183` 이 `items == []` 를 단정. MQ-909 이 12행을 노출하는 순간 Stage 4 게이트 FAIL, 정정은 Stage 5 | 🔴 |
| R4 | 2 vs 4 | MQ-904 ↔ MQ-909 | MQ-904 의 새 CHECK ②가 `state='signed'` 에 `record_hash NOT NULL` 을 강제 → 시드 11행 해시가 필요 → `data/repair_hash.py` 가 필요한데 **그 파일은 MQ-909(Stage 4) 소유**다. **Stage 2 에서 시드가 죽는다.** §4 격리표에 `data/repair_hash.py` 자체가 부재 | 🔴 |
| R5 | 2 | MQ-903 | `data/maint_value.py` 가 `REPEAT_THRESHOLD`/`REPEAT_WINDOW_DAYS` 를 필요로 하는데(`get_maintenance_metrics.py:25`·`assess_repair_value.py:57` 이 `from .get_error_history import` 로 조달) 단일 출처가 **코어 도구**다. DoD 의 `rg "^from mcp_server" data/maint_value.py → 0건` 과 **정면 충돌**. 방치하면 빌더가 **4번째 사본**을 만든다(`data/ownership.py:70~71`·`data/seed.py:1089~90` 에 이미 사본 2개) | 🔴 |
| R6 | 2 | MQ-905 | `extract_error_codes.py:483` 이 정본을 무조건 덮어쓰고 `_status` 를 재유도한다 → **D99 의 전제가 코드에 없다.** 재실행 한 번이 CLAUDE.md 가 기록한 **65→0행 사고를 재현**할 수 있다 | 🔴 |
| R7 | 4 | MQ-910 / MQ-901(D100) | manifest 오프셋이 실측과 다르고(0 vs 1), `manifest.py` 에 **manual_id 키 오프셋 조회가 없다.** 이 상태로 `actions_source.print_page` 를 내면 *"근거 페이지 인용률 100%"* 의 판정 소스가 오염된다 | 🔴 |
| R8 | — | (미배정) | `backend/agent/prompts.py::_selected()` 는 **모르는 도구명을 조용히 뺀다.** `_EXT_TOOL_LINES`(`:368~390`)에 `create_repair_record` 가 없으면 LLM 에게 도구가 보이지 않아 **S19 를 채팅으로 시연할 수 없다.** 어느 태스크도 `prompts.py` 를 소유하지 않는다 | 🟡 |
| R9 | 3 | MQ-908 | D101 의 **명분이 해소되지 않는다** — `decisions._metrics()`(`:517~520`)를 위임으로 바꾸는 태스크가 없고 `decisions.py` 는 무소유다. 결과: 산식 사본이 그대로 2벌 | 🟡 |
| R10 | 2 | MQ-903 | 실물 규모 **4파일 1,378줄**(assess 588 / metrics 355 / expenditure 317 / criticality 118). `_assess` 가 `read_only()` 를 **두 번**(`:272`·`:395`) 열고 그 사이에서 하위 도구 2종이 각자 커넥션을 연다 → 호출자 주입으로 바꾸면 **커넥션 생명주기가 통째로 재배치**된다. "출력 dict 무변경"은 가능하지만 **단일 태스크로는 크다** | 🟡 |
| R11 | 6 | MQ-914 | 4컴포넌트 + 신규 라우트 + API 4종 + D64/D65/D87 방어선. 크기가 상한선. (신규 `components/asset/*.tsx` 가 L2 규칙 6종에 자동 노출되는 것은 **정상 동작이며 위험이 아니다**) | 🟡 |
| R12 | 10 | MQ-919 | 스프린트 안에 끝난다고 가정하지 않음 — **배치가 옳다** | 🟢 |
| **R13** | 4 | MQ-910 | 🔴 **코디네이터 추가 발견 (tool-builder 미검출).** 명세 핵심로직 2 가 `lookup_error_code` 에 manifest 오프셋을 적용해 `print_page` 를 싣게 하는데, **고치려는 그 파일의 docstring**(`mcp_server/tools/lookup_error_code.py:11`)이 *"환산은 백엔드 렌더 1곳(backend/manifest.py)만 담당한다 (D32)"* 라고 적혀 있다. `mcp_server/rag.py:23` 도 동일. 실제로 **`mcp_server` 는 manifest 를 읽지 않는다**(grep 0건). 명세대로 하면 ⓐ 환산 지점이 2곳이 되어 **D32 가 깨지고** ⓑ `mcp_server` 에 새 의존이 생긴다 | 🔴 |

### 8-3. 명세 보완이 필요한 곳

- **MQ-903** — ① `REPEAT_THRESHOLD`/`REPEAT_WINDOW_DAYS` 조달 경로가 공란(R5). `data/ownership.py` 의 상수를 쓰고 `verify_ownership.py:34` 와 **같은 드리프트 assert** 를 건다고 못박을 것. ② `mcp_server/server.py:183` 이 `assess_repair_value` 에서 `DEFAULT_REPAIR_SCOPE` 도 import 하므로 `DESCRIPTION` 외에 **이 상수도 도구 파일에 남긴다**를 명시. ③ `_asset_ref` 엣지케이스는 **삭제**(무관).
- **MQ-904** — `data/repair_hash.py` 의 **소유·생성 시점이 미정의**(R4). `HASHED_KEYS` 가 MQ-909 절에만 있는데 MQ-904 가 먼저 써야 한다. 또 `created_at` 신설이 `decisions.py:602`(*"수리 시각 컬럼이 없어 window_months 로 자를 수 없다"*)를 낡게 만드는데 후속 처리가 없다.
- **MQ-905** — ① `main()` 정본 덮어쓰기 해결책 미기재(R6). ② 물리 p.20~21 의 **고장/경보 일람표**(분류·고장표시·설명·Page)가 훨씬 안정적인 조인 소스인데 언급이 없다 — 단 그 Page 열은 **인쇄 페이지**라 +1 보정 필요. ③ `print_page_offset: 0` 전제가 틀렸다.
- **MQ-906** — `backend/agent/prompts.py` 노출 여부 미결정(R8). 등록만 하고 프롬프트에 안 실으면 **도구가 존재하되 호출 불가**.
- **MQ-908** — `decisions._metrics` 처리 방침(위임/유지) 미결정(R9). 유지라면 **D101 채택 이유에서 `:520` 인용을 빼야** 문서가 참이 된다.
- **MQ-913** — 소유 파일에 `spikes/s10_smoke.py` 누락(R2). `EXPECTED_REQUIRED`(tools_profile ②)에 `create_repair_record` 를 넣을지도 미기재.
- **MQ-918** — 전파 대상에 `data/raw/manifest.json`(오프셋 정정)과 `docs/05_DB_SCHEMA.md §16` 컬럼 수(15→19)가 빠지면 안 된다.

### 8-4. 결론 — §7 압축 순서를 **그대로 쓰지 말 것**

§7 은 ①MQ-915 ②MQ-916 ③MQ-907 ④MQ-910 ⑤축 C 전체 순서를 제안했다. 실측 결과 **③이 틀렸다.**

1. **§7 ①②(MQ-915·916)는 유효** — 파일 교집합 0, 하위 의존 없음. 먼저 덜어낸다.
2. **MQ-907 을 3순위로 자르지 않는다** — PDF 실물 확인으로 축 B 의 **회수 가능성이 오히려 입증**됐다. 자를 이유가 없다. 대신 **선행 2건을 추가**해야 한다: manifest 오프셋 정정(R7) · `main()` 쓰기 가드(R6). 이걸 안 하면 착수 자체가 **DB 파괴 경로**다.
3. **자를 후보는 MQ-903 이다** — 1,378줄 4파일 리팩터가 Stage 2 병렬 슬롯 하나에 들어 있고 상수 조달 경로가 미정이라(R5·R10) 빌더가 사본을 늘릴 위험이 실재한다. **2태스크로 분할하거나 이번 스프린트에서 제외**. 제외 시 §7 ⑤대로 **D101 도 함께 보류**한다(결정만 남기고 안 지키면 문서가 거짓이 된다).
4. **자르지 않더라도 스테이지 재배치는 필수** — MQ-913 을 Stage 4 로 · `data/repair_hash.py` 를 MQ-904 소유로 · `s10_smoke.py` 를 MQ-913 소유로 · `prompts.py` 를 MQ-906 소유로. 이 넷을 안 고치면 **Stage 3·4 회귀 게이트가 설계상 반드시 실패**하고, 그때 CLAUDE.md 의 *"Windows 소켓 고갈 재시도"* 규약과 섞여 **진짜 회귀를 놓친다.**

### 8-5. 사람 결정 (2026-08-14)

**선택: 평가 권고안.** MQ-915·916 컷 · MQ-903 분할 · **MQ-907 유지** · 재배치 4건 + 선행 2건 적용.
→ 확정 내용은 **§9**.

---

## 9. 확정 실행 계획 (§4·§7 을 대체한다)

### 9-1. 무엇이 바뀌었나

| 구분 | 내용 | 근거 |
|---|---|---|
| **컷 2건** | **MQ-915**(근거 번들 화면 + 지출 독립 페이지) · **MQ-916**(큐 repair 상세) | §7 ①② — 파일 교집합 0, 하위 의존 없음. 축 A 는 **API 까지 완결**되고 축 C 는 핵심 화면 1개(914)가 남는다 |
| **컷 안 함** | **MQ-907**(S100 26건) — §7 ③ 을 **기각**한다 | PDF 실물 확인으로 축 B 의 회수 가능성이 **입증**됐다(§8-1). 자를 근거가 사라졌다 |
| **분할 1건** | **MQ-903** → MQ-903(3종) + **MQ-922**(`assess_repair_value`) | R10 — 4파일 1,378줄 중 assess 혼자 588줄이고 `read_only()` 를 2회 연다. 병렬 슬롯 하나에 넣을 크기가 아니다 |
| **신설 2건** | **MQ-920**(manifest 오프셋 정정) · **MQ-921**(정본 쓰기 가드) | R6·R7·R13 — 둘 다 **선행이다.** 없으면 MQ-905 는 DB 파괴 경로이고 MQ-910 은 거짓 인용을 만든다 |
| **소유 이관 4건** | `data/repair_hash.py` 909→**904** · `tools_profile_contract`+`s10_smoke` 913→**906** · `approvals_contract ③` 913→**909** · `prompts.py` 무소유→**906** | R1~R4·R8 |

> **§8-4 ④ 의 "MQ-913 을 Stage 4 로" 를 더 낫게 고쳤다.**
> 문제의 본질은 스테이지가 아니라 **기대값 갱신이 생산자와 떨어져 있는 것**이다.
> → **기계적 기대값 갱신(도구 개수 15→16 · 큐 0건→12건)은 생산자 태스크가 함께 한다.**
> 자기 코드를 자기가 검증하는 우려는 **새 계약 검사**에만 해당하고, 상수 하나 바꾸는 데는 과한 원칙이다
> (tool-builder 도 R3 에서 같은 판단을 했다).
> **MQ-913 에는 실질 신규 검증만 남긴다** — `repair_flow_contract`(신규) · `write_tool_contract` 확장 · `lookup_contract` +2.

**규모의 정직한 보고**: 태스크 수는 19 → **20**, 스테이지는 10 → **10** 이다. **숫자는 줄지 않았다.**
줄어든 것은 **작업량**이다 — 프론트 라우트 2개 + 컴포넌트 3개가 빠지고, 들어온 셋 중 MQ-922 는
**새 일이 아니라 MQ-903 을 쪼갠 절반**이며 MQ-920·921 은 각각 수십 줄짜리 방어 태스크다.
⛔ *"17태스크로 줄였다"* 고 적지 않는다 — 그건 사실이 아니다.

### 9-2. 확정 스테이지

| 스테이지 | 태스크 | 병렬 | 파일 교집합 | 선행 |
|---|---|---|---|---|
| **1** | MQ-901 · MQ-902 · **MQ-920** · **MQ-921** | ✅ 4 | 0 — `docs/10_DECISIONS.md` / `data/extract_triage.py` / `data/raw/manifest.json`+`backend/manifest.py`+`spikes/citation_render.py` / `data/extract_error_codes.py` | — |
| **2** | MQ-903 · MQ-904 · MQ-905 | ✅ 3 | 0 — `data/maint_value.py`+도구 3종 / `data/seed.py`+**`data/repair_hash.py`** / `data/extract_error_codes.py`(iG5A) | 901 · 902 · 921 |
| **3** | **MQ-922** · MQ-906 · MQ-907 | ✅ 3 | 0 — `tools/assess_repair_value.py` / `tools/create_repair_record.py`+`db.py`+`server.py`+`prompts.py`+스파이크 2 / `data/extract_error_codes.py`(S100) | 903 · 904 · 905 |
| **4** | MQ-908 · MQ-910 · MQ-911 | ✅ 3 | 0 — `backend/{services,routers}/maint_value.py`+`main.py` / `tools/lookup_error_code.py` / `data/analysis/`+`TODO`(§actions) | 903 · 922 · 920 · 907 |
| **5** | MQ-909 | 단독 | `backend/main.py` 를 908 과 공유 → **반드시 분리** | 906 · 904 |
| **6** | MQ-912 · MQ-913 | ✅ 2 | 0 — `frontend/lib/` / `spikes/` | 908 · 909 · 910 |
| **7** | MQ-914 | 단독 | 도구 4종이 한 화면에 모인다(§4 근거 유지) | 912 |
| **8** | MQ-917 | 단독 | L2 글롭이 914 산출물을 스캔 | 914 |
| **9** | MQ-918 | 단독 | 기준선 숫자는 러너 출력이 기준 | 913 · 917 |
| **10** | MQ-919 | ⚠ 조건부 | **G1·G2 승인 후에만** | 911 · 918 · **사람** |

```
MQ-901 ─┬─► MQ-903 ─┬─► MQ-922 ─┬─► MQ-908 ─┐
        │           │           │           ├─► MQ-912 ─► MQ-914 ─► MQ-917 ─┐
        ├─► MQ-904 ─┴─► MQ-906 ─┴─► MQ-909 ─┘                               ├─► MQ-918 ─► [G1·G2] ─► MQ-919
MQ-920 ─┴────────────────────────► MQ-910 ─────────► MQ-913 ────────────────┘
MQ-921 ──► MQ-905 ─► MQ-907 ─► MQ-911 ──────────────────────────────► [G1]
MQ-902 ──► MQ-905
```

**스테이지 5 가 단독인 이유**: MQ-908·909 가 **둘 다 `backend/main.py` 에 라우터를 등록**한다.
원안이 Stage 3/4 로 나눈 이유가 그대로 살아 있고, 908 이 MQ-922 때문에 Stage 4 로 밀리면서 909 가 5 로 간다.

### 9-3. 신설 태스크 2건

#### MQ-920 — manifest 오프셋 정정 + `manual_id` 키 조회 (R7·R13 의 선행)

- **복무 시나리오**: 인프라 (D26·D32 방어선)
- **변경 파일**: `data/raw/manifest.json`(수정) · `backend/manifest.py`(함수 1개 추가) · `spikes/citation_render.py`(검사 추가)
- **핵심 로직**:
  1. `ig5a-troubleshooting` 의 `print_page_offset` 을 **0 → 1** 로 고치고 `page_note` 를
     *"물리 = 인쇄 + 1 (PDF 실측: 물리 p.22 → 인쇄 21)"* 로 바꾼다.
     ⚠ **`data/raw/` 읽기 전용 규칙(절대규칙 5)은 PDF 원본에 대한 것**이고 `manifest.json` 은 대장이다 —
     `sha256`·`file`·`source_url` 은 **한 글자도 건드리지 않는다**(그게 읽기 전용의 실체다).
  2. `backend/manifest.py` 에 **`manual_offset(manual_id: str) -> int`** 를 추가한다.
     기존 `print_page_offset(model)` 은 **그대로 둔다**(`role="primary"` 우선 규약 유지).
     `to_print_page` 와 같은 D49 경계 조건(`< 1` 이면 미적용)을 적용한 `to_print_page_for_manual()` 도 함께.
  3. `spikes/citation_render.py` ⑨ 는 `role=="primary"` 만 대조한다 → **supplement 축을 추가**한다.
     🔴 **양성 축 필수**: `대조한 매뉴얼 수 > 0 and 불일치 0`. detail 에 `{id: offset}` 실측을 찍는다.
- **엣지 케이스**: PDF 를 다시 열어 재확인하지 않는다(이미 실측). / 다른 매뉴얼 오프셋(`iG5A` 0 · `S100` 16)은 **건드리지 않는다**.
- **지켜야 할 결정**: D19(manifest 단일 원천) · D26(저장은 물리) · D32(환산 1곳) · D49(경계) · 절대규칙 5
- **DoD**:
  - `rg -n '"print_page_offset": 1' data/raw/manifest.json` → **1건**(`ig5a-troubleshooting`).
  - `rg -n "물리 = 인쇄 \(오프셋 없음\)" data/raw/manifest.json` → **1건만 남는다**(`ig5a-manual`).
  - `uv run python spikes/citation_render.py` → **13 + Δ건** 통과, detail 에 매뉴얼별 오프셋 실측.
  - manifest 의 `sha256` 값이 **변경 0** (`git diff` 로 확인해 커밋 메시지에 적는다).

#### MQ-921 — `extract_error_codes.py` 정본 쓰기 가드 (R6 — D99 를 코드로 만든다)

- **복무 시나리오**: 인프라 (S1·S3·S4 의 데이터 방어선)
- **변경 파일**: `data/extract_error_codes.py`(수정 — `main()` 과 출력 경로만)
- **핵심 로직**:
  1. 🔴 **문제**: `:483 OUTPUT.write_text(...)` 가 정본을 **무조건 덮어쓴다.** `:474 generated_at=date.today()`
     때문에 **내용이 같아도 해시가 바뀌고**, `:473 _status` 가 `ig5a_approval_status()` 로 재유도된다.
     MQ-905·907 빌더가 스크립트를 한 번 돌리면 **CLAUDE.md 가 기록한 65→0행 사고가 재현될 수 있다.**
  2. **`--candidates-only` 플래그 신설** — MQ-905·907 은 **이 모드로만** 돌린다. 정본을 열지 않는다.
  3. **정본 경로에 무변경 가드**: `generated_at` 을 **제외한 정준 직렬화**가 기존 파일과 같으면
     **파일을 쓰지 않고** *"변경 없음 — 기록 생략"* 을 출력한다. 다르면 **diff 요약을 찍고 확인을 요구**한다.
  4. `_status` 가 승인 → 초안으로 **되돌아가는 경우 무조건 중단**한다(`error_codes_gate()` 가 65→0 을 만드는
     정확한 조건이다). 이 판정에 **양성 축**을 건다 — `기존 entries 수 > 0 and 새 _status 가 초안`.
- **엣지 케이스**:
  | 상황 | 기대 |
  |---|---|
  | 정본이 없음(최초 추출) | 가드 없이 정상 기록. **가드는 회귀 방지지 최초 생성 금지가 아니다** |
  | `--candidates-only` 인데 후보 로직 미구현(현재) | 후보 파일만 만들고 정본 미접촉으로 **정상 종료** |
  | 내용 동일 + `generated_at` 만 다름 | **쓰지 않는다.** 이게 MQ-905 DoD *"해시 불변"* 을 참으로 만드는 유일한 방법 |
  | 내용이 실제로 달라짐 | 파일을 쓰지 않고 **exit 1 + diff 요약**. 사람이 판단한다 |
- **지켜야 할 결정**: **D99** · D19 · D33 · **CLAUDE.md 시드 함정 2건**(MQ-708·MQ-713a)
- **DoD**:
  - `uv run python data/extract_error_codes.py` **2회 연속 실행** → `data/extracted/error_codes.json`
    **sha256 불변** (실측 해시를 커밋 메시지에 적는다).
  - `uv run python data/extract_error_codes.py --candidates-only` → 정본 **mtime·해시 둘 다 불변**.
  - `SELECT count(*) FROM error_codes` = **65** (재시드 없이 확인 — 이 태스크는 DB 를 안 건드린다).
  - `uv run ruff check data`.

#### MQ-922 — `assess_repair_value` 위임 (MQ-903 에서 분할)

- **복무 시나리오**: S1+ · 인프라
- **변경 파일**: `mcp_server/tools/assess_repair_value.py`(수정) · `data/maint_value.py`(**`repair_value()` 추가**)
- **핵심 로직**:
  1. MQ-903 이 만든 `data/maint_value.py` 에 **`repair_value(con, *, …)` 만** 더한다.
  2. 🔴 **커넥션 생명주기 재배치가 이 태스크의 본체다** — 현재 `_assess` 가 `read_only()` 를
     **`:272`·`:395` 두 번** 열고 그 사이에서 하위 도구 2종이 각자 또 연다.
     → `data/` 쪽은 **호출자가 넘긴 커넥션 하나만** 쓰고, 하위는 **함수 호출**로 바뀐다.
  3. `04 §13` *"하위 도구 실패를 삼키지 않는다"* 를 유지 — `status != "ok"` 면 **재포장 없이** 전파.
  4. **`DESCRIPTION` 과 `DEFAULT_REPAIR_SCOPE` 는 도구 파일에 남긴다.**
     `mcp_server/server.py:183` 이 후자를 import 하므로, 남겨야 **`server.py` 를 안 건드리고**
     같은 스테이지의 MQ-906(= `server.py` 소유)과 충돌하지 않는다. ⛔ **`server.py` 를 수정하지 말 것.**
- **지켜야 할 결정**: D101 · D73 · D15 · D80 · D9 · D65·D70·D74 · D64 · `04 §13`
- **DoD**:
  - `uv run python spikes/asset_tools_contract.py` → **49건 전건 통과, 검사 파일 diff 0.**
  - `rg -n "read_only\(\)" mcp_server/tools/assess_repair_value.py` → **1건**(2→1).
  - `rg -n "DEFAULT_REPAIR_SCOPE|^DESCRIPTION" mcp_server/tools/assess_repair_value.py` → 둘 다 존재.
  - `git diff --stat mcp_server/server.py` → **변경 없음**.

### 9-4. §6 명세 델타 (§6 보다 **이 표가 우선**한다)

| TASK | 무엇을 고치나 | 왜 |
|---|---|---|
| **MQ-901** | D100 셀에 ⓐ `ig5a-troubleshooting` 오프셋을 **1**(MQ-920 정정)로 적는다 — §3 쟁점③ 의 *"`print_page_offset: 0`"* 은 **틀렸다** ⓑ **`actions_source` 는 `{manual_id, page}` 만 담고 `print_page` 는 담지 않는다** 를 명시 | R7 · **R13** |
| **MQ-903** | ⓐ 범위를 **3종**(metrics·criticality·expenditure)으로 축소 ⓑ 🔴 `REPEAT_THRESHOLD`·`REPEAT_WINDOW_DAYS` 는 **`data/ownership.py:70~71` 의 상수를 쓰고 `verify_ownership.py:34` 와 같은 드리프트 assert 를 건다** — 새 사본을 만들지 않는다 ⓒ `_asset_ref` 엣지케이스 **삭제**(이 4종은 안 쓴다) | R5 · §8-1 |
| **MQ-904** | ⓐ **`data/repair_hash.py` 를 이 태스크가 만든다**(`HASHED_KEYS`·`canonical_json`·`compute_record_hash`). MQ-909 는 **import 만** ⓑ `ownership_api_contract:62` 엣지케이스 **삭제**(`:57` 은 `COUNT(*)`, 무해) ⓒ `created_at` 신설이 `decisions.py:602` 주석을 낡게 만든다 → **MQ-918 전파 목록에 추가** | R4 · §8-1 |
| **MQ-905** | ⓐ `IG5A_TROUBLE_PAGES` 주석의 *"print_page_offset 0"* → **1** ⓑ DoD *"해시 불변"* 은 **MQ-921 의 가드가 보장**한다(905 가 따로 구현하지 않는다) ⓒ **조인 소스 후보 추가**: 물리 p.20~21 의 고장/경보 일람표(분류·고장표시·설명·Page)가 더 안정적이다 — 단 그 `Page` 열은 **인쇄 페이지라 +1 보정** 필요 ⓓ 🔴 **`EST`(비상정지) 1건은 트러블슈팅본에도 명칭이 없다** — MQ-902 탐침 실측(결측 11건 중 명칭 실재 **10건**). 별도로 다루고 **지어내지 않는다** ⓔ MQ-921 이 만든 `--candidates-only` 의 docstring 은 *"정본을 열지도 쓰지도 않는다"* 인데 905 는 정본을 **읽어야** 한다 → 문구를 *"쓰지 않는다"* 로 좁힌다 | R6·R7 · §8-3 · **Stage 1 실측** |
| **MQ-906** | 소유 파일 **4개 추가**: `backend/agent/prompts.py`(`_EXT_TOOL_LINES` 에 `create_repair_record` 1행 — **안 넣으면 LLM 에게 도구가 안 보여 S19 를 채팅으로 시연 못 한다**) · `spikes/tools_profile_contract.py`(full 15→**16**) · `spikes/s10_smoke.py`(`EXPECTED_TOOLS_FULL` 15→**16**). ⚠ `EXT_RULES` 확장은 `assert len(EXT_RULES)==len(_EXT_RULE_TOOLS)` 때문에 **신중히** | R1·R2·R8 |
| **MQ-908** | 🔴 **`decisions._metrics()`(`:517~520`) 방침을 정해야 한다** — ⓐ `data.maint_value.maintenance_metrics` 위임으로 전환하거나 ⓑ 유지하되 **D101 채택 이유에서 `:520` 인용을 뺀다**. ⛔ 지금처럼 두면 *"산식이 두 벌"* 을 근거로 삼고서 두 벌을 그대로 남기는 셈이라 **문서가 거짓이 된다** | R9 |
| **MQ-909** | ⓐ `data/repair_hash.py` 는 **MQ-904 산출물** — import 만 ⓑ `spikes/approvals_contract.py ③` 정정을 **이 태스크가 한다**(0건 → 12건 실측 + `kind=nope` 422 음성 축) | R3·R4 |
| **MQ-910** | 🔴 **`print_page` 를 출력에서 뺀다.** `actions_source: {manual_id, page} \| null` 만. 인쇄 환산은 `backend/sse.py:citation_for()` 1곳 유지(D32) — **고치려는 파일 `:11` 의 docstring 이 그렇게 적혀 있다** | **R13** |
| **MQ-911** | 표 1 의 "인쇄 페이지 병기"는 **MQ-920 정정값(offset 1)** 을 쓴다 | R7 |
| **MQ-913** | 범위 **축소** — 남는 것: `spikes/repair_flow_contract.py`(신규) · `write_tool_contract` 확장(2→3종) · `lookup_contract` +2. **이관**: `tools_profile_contract`·`s10_smoke` → MQ-906 · `approvals_contract ③` → MQ-909 ⓑ 🔴 **추가**: MQ-921 의 정본 쓰기 가드에 **회귀가 0건**이다 — 65→0행 사고를 막는 유일한 코드(`extract_error_codes.write_canonical()`)가 사람이 손으로 두 번 돌리는 DoD 로만 지켜진다. *"정본 쓰기 경로는 `write_canonical` 하나 · exit 1/2 계약 · `--candidates-only` 는 `OUTPUT` 미접촉"* 을 **양성 축과 함께** 넣는다 | R1·R2·R3 · **Stage 1 reviewer 권고 4** |
| **MQ-917** | `L2_EXTRA` 에 `RepairDetail.tsx` 추가 **삭제**(MQ-916 컷) | 컷 반영 |
| **MQ-918** | ⓐ 프론트 라우트 **13 → 11**(914 만 추가) ⓑ 전파 대상에 **`data/raw/manifest.json` 오프셋 정정**·**`05_DB_SCHEMA §16` 컬럼 수 15→19** 추가 ⓒ **MQ-915·916 을 `07_BACKLOG` 에 "Sprint 10 이월"로 등재**(조용히 사라지게 두지 않는다) ⓓ `decisions.py:602` 주석 갱신 ⓔ 🔴 **D69 원문이 낡았다** — *"코어 7 + 확장 7"* 로 적혀 있는데 실측은 **확장 8**(Sprint 9 후 9). 갱신 대상 ⓕ **기존 `D74`·`D77` 행은 셀 안 `\|` 가 이스케이프돼 있지 않아** 마크다운에서 열이 밀린다(셀 파싱 6개·5개). **Stage 1 이 발견했고 손대지 않았다** — 여기서 정정 ⓖ **정본 갱신 경로가 바뀐 사실**을 전파한다 — MQ-921 이후 *"정정은 `extract_error_codes.py` 재실행으로만"* 은 더 이상 참이 아니다(`TODO_직접할일.md:24` · `data/analysis/ig5a_code_mapping.md:62` · `data-analysis/reports/preprocessing_report.md:94`). 셋 다 **완료 기록(과거형)이라 당장 거짓은 아니지만** 앞으로의 경로를 함께 적는다 ⓗ ✅ **§6 핵심로직 7(D 범위 표기)은 Stage 1 종료 시 선행 처리됐다** — `D1~D97`(일부 `D1~D96`)→ **`D1~D101`** 6곳. `.claude/agents/reviewer.md` 가 낡아 있으면 **Stage 2 reviewer 가 D98~D101 을 지나칠 실제 위험**이 있어 미룰 수 없었다. 여기서는 **재확인만** 한다 | 컷 반영 · §8-3 · **Stage 1 실측·reviewer 권고 5** |
| **MQ-919** | 변경 없음 | — |

### 9-5. 이월 (다음 스프린트)

| 항목 | 이유 |
|---|---|
| **MQ-915** — 근거 번들 화면 + 지출 독립 페이지 | 규모 압축. **REST(MQ-908)·`api.ts`(MQ-912)는 이번에 만들어 두므로** 다음 스프린트는 화면만 그리면 된다 |
| **MQ-916** — 큐 `kind:"repair"` 상세 | 같음. 축 A 는 **API 까지 완결**되어 `/api/repairs` 로 검증 가능하다. ⚠ **데모 서사는 반쪽이다** — 서명을 화면으로 못 보여준다 |
| `traces.request_chain_id` A2A 호출부 | 원래 범위 밖 (§0) |

⛔ **MQ-912 의 `getEvidenceBundle` 은 남겨 둔다** — MQ-913 이 core 프로파일에서 5경로를 검증하므로
소비자가 없어도 계약은 살아 있다. 다음 스프린트가 바로 쓴다.

### 9-6. 실행

```
/stage 1     →  MQ-901 · MQ-902 · MQ-920 · MQ-921  (4병렬)   ✅ 완료 (§10)
/stage 2     →  MQ-903 · MQ-904 · MQ-905           (3병렬)
```

---

## 10. Stage 1 완료 (2026-08-14)

**브랜치**: `sprint-9-repair-record` (⛔ master 미머지 — 머지는 사람 요청 시에만)

### 10-1. 태스크별 결과

| TASK | 산출 | 회귀 |
|---|---|---|
| **MQ-901** | `docs/10_DECISIONS.md` **+4행 / −0** (D98·D99·D100·D101). 인용 4곳 전부 실제 파일과 대조 확인 | 문서 |
| **MQ-902** | `data/extract_triage.py` · `data/analysis/extract_triage.md` · `data/extracted/extract_triage.json` | 계측기 자체가 판정 소스 |
| **MQ-920** | `data/raw/manifest.json`(**2줄**) · `backend/manifest.py`(함수 3개) · `spikes/citation_render.py` | **13 → 18건** |
| **MQ-921** | `data/extract_error_codes.py` — `write_canonical()` 가드 + `--candidates-only` | ⚠ **회귀 0건** → MQ-913 |

### 10-2. 회귀 실측 (전건 통과 · 감소 0 · 재시도 0)

`seed 26` · `sp2 20` · `write_tool 23` · `api 28` · `sse 22` · **`citation_render 18`**(13+5) ·
`rag 12` · `lookup 12` · `tools_profile 7` · `pytest 46` · `ruff` 통과 · `spikes/*.py` **28개**.
재시드 후 `error_codes` **65행**. Windows 소켓 고갈 징후 없음(스위트 1개씩 분리 호출).

정본 무접촉 증명: `data/extracted/error_codes.json` sha256 = `2033f896…4a981d` **불변**,
`generated_at` = `2026-08-05` 유지(오늘 계산값 `2026-08-14` 가 **기록되지 않았다** = 가드 작동),
`_status` = `승인 완료 (2026-07-28)` 되돌림 0.

### 10-3. 🔴 계획의 가정 하나가 데이터에 뒤집혔다 (MQ-905 에 직접 영향)

MQ-902 DoD 는 *"iG5A 결측 11건이 `SOURCE_MISSING` 으로 라벨링된다"* 를 기대했으나 **실측은 다르다**:

```
ig5a-manual p.202: missing  3 / code_tokens 0 → SOURCE_MISSING  (anchor_conflict)
ig5a-manual p.203: missing  8 / code_tokens 4 → CELL_SPLIT      ← 기대와 다름
s100-manual p.416~419: missing 26 / tokens 5,6,1,3 → CELL_SPLIT (26/26 기대대로)
```

**원인은 파서가 아니라 양성 축 자체의 적용 범위다.** iG5A 추출은 ASCII 코드 토큰이 아니라
**한글 명칭**으로 조인해서, 조치문 추출에 **성공한** 코드가 6·4건 있는 페이지에서도 토큰이 0 이다.
→ ⛔ **iG5A 에서 `code_tokens_found` 를 소스 유무의 증거로 쓰면 안 된다.**

**그래서 독립 축을 하나 더 쟀다** (명세에 없던 추가분 — `probe_supplement()`):

> `ig5a-troubleshooting` 물리 p.20~29 · 6,683자 · **결측 11건 중 명칭 실재 10건** (미발견: `EST` 1건)

**MQ-905 의 전제("소스를 추가하면 풀린다")를 뒷받침하는 것은 라벨이 아니라 이 실측이다.**
계획이 데이터를 이기지 않도록 라벨을 고치지 않고 **실측을 그대로 적었다**(MQ-902 명세의 명시 규칙).

### 10-4. reviewer 게이트 — 커밋 가능 **Y** (블로커 0건)

커밋 전에 반영한 권고 3건:

| 권고 | 조치 |
|---|---|
| 🔴 `anchor_conflict` 가 **산문에만** 있어 `label` 로 필터링하는 MQ-905 에게 통째로 증발한다 | `PageVerdict` 에 **`anchor_conflict: bool`·`scanned: bool`** 신설(`asdict` 로 JSON 자동 반영). 실측 결과 `p.202`·`p.204` 2건이 `True` 로 실렸다 |
| 스캔 불가를 `SOURCE_MISSING` 으로 접는 것은 *"재지 못함"* 을 **결론**으로 바꾸는 것(D65) | `LABELS` 에 **`UNSCANNED`** 추가 + `scanned=False`. note 에 *"이 0 들은 실측이 아니라 재지 못함"* 명시 |
| `citation_render ⑨` 의 `len(by_id) > len(primary)` 는 **supplement 축이 죽어도 통과**한다 (P30 유형) | supplement 를 **이름으로** 세도록 교체 — `len(supplements) > 0 and len(supp_compared) == len(supplements)`. detail 에 `supplement 1/1=['ig5a-troubleshooting']` 실측 인쇄 |

다음 스테이지로 넘긴 것: **권고 4**(정본 가드 회귀 → MQ-913) · **권고 5**(갱신 경로 전파 → MQ-918) ·
**지목 7**(D101 이 인용한 *"산식이 두 벌"* 을 MQ-908 이 해소하지 않으면 **그 시점에 D101 이 거짓이 된다**).

### 10-5. 사전 결함 2건 발견 (이번 변경 아님 — MQ-918 로 이관)

- **`D69` 원문이 낡았다** — *"코어 7 + 확장 7"* 인데 실측은 확장 **8**
- **`D74`·`D77` 행의 셀 안 `|` 미이스케이프** — 마크다운 열이 밀린다(셀 파싱 6개·5개)

---

## 11. Stage 2 완료 (2026-08-16)

**브랜치**: `sprint-9-repair-record` (⛔ master 미머지 — 머지는 사람 요청 시에만)
**커밋**: `2f955fd` — `[M1] Sprint 9 Stage 2 — data/maint_value.py 위임(D101) · repair_records DDL 확장(D98) · iG5A actions 후보 추출(D99)`

### 11-1. 태스크별 결과

| TASK | 산출 | 실측 |
|---|---|---|
| **MQ-903** | `data/maint_value.py`(신규) · `mcp_server/tools/{get_maintenance_metrics,classify_part_criticality,classify_expenditure}.py`(위임) | `asset_tools_contract` **49건 무변경 통과(diff 0)** · `tools_profile_contract` 7건 · `sp2_mcp_roundtrip` 20건. `REPEAT_THRESHOLD`/`WINDOW`는 `data/ownership.py:70~71` 재사용 + 드리프트 assert |
| **MQ-904** | `repair_records` DDL +4컬럼·CHECK 3종 · `error_codes` 출처 컬럼 2종 · `data/repair_hash.py`(신규) | seed 자가검증 **26 → 29**(㉗㉘㉙). `record_hash=NULL`+`state='signed'` INSERT **ABORT 확인**(음성). `INSERT INTO error_codes VALUES` 위치 인자 **0건**(명시 컬럼 전환) |
| **MQ-905** | `data/extract_error_codes.py`(iG5A 조인 경로) · `error_codes_actions.candidate.json` · `ig5a_action_map.json`(신규) | 후보 **entries 2건**(`RERR`·`ETB`) · `_pending_review` **9건**(공유 조치행 애매성 — 지어내지 않음). `verify_verbatim()` 위반 **0건**. 정본 `error_codes.json` sha256 **불변**, `error_codes` count **65 불변** |

### 11-2. 회귀 실측 (전건 통과 · 감소 0 · 재시도 0)

seed **29건** · pytest **46건** · spikes **28스위트**(Stage 1 기준선 **640건**과 완전 동일 — Stage 2 는 신규 스파이크 검사를 추가하지 않는다) · `ruff check data backend mcp_server spikes` 통과.
Windows 소켓 고갈 징후 없음(스위트 1개씩 분리 호출).

### 11-3. 계획 대비 편차 2건 — reviewer 가 판정, 블로커 아님으로 결론

| # | 편차 | reviewer 판정 |
|---|---|---|
| ① | MQ-905 후보 반영이 §9-4 델타의 기대치(*"명칭 실재 10건"*)와 다르게 **entries 2건**만 채워짐 | **정확한 해석.** 트러블슈팅 PDF 의 한 조치 행이 고장명 5개를 공유하는 구조라, "조인 실패는 버린다"(가장 가까운 항목으로 흘리지 않는다) 원칙을 지켜 **공유 행을 전부 `ambiguous` 로 분류**한 것 — 과도한 폐기가 아니라 D99·안전규칙3·`span_key()` 선례에 부합. `_variant_pair()` 로 원문이 명시 병기한 경우(`RERR`·`ETB`)만 예외 회수 |
| ② | MQ-905 DoD *"`extract_triage.py` 재실행 → 라벨 이동 건수"* 가 실측 불가 — `extract_triage.py` 가 후보 파일·supplement 매뉴얼을 읽는 경로 자체가 없음 | **코드 결함이 아니라 명세 공백.** `data/extract_triage.py` 는 공유 파일 단일 소유자 표(§4)에서 **MQ-902(Stage 1) 전용**이라 MQ-905 가 손댈 수 없다. **다음 스테이지(MQ-911/918)로 이관** — 아래 §11-5 |

부수 확인: MQ-903 의 `read_only()` 예외 처리 순서 변화(DB 없음+잘못된 입력 **동시** 발생하는 병적 조합에서만 `reason` 이 바뀔 수 있음, 정상 경로 영향 0) · `get_maintenance_metrics` 의 try/except 보호 범위 확장(D9 방향 개선) — **둘 다 계약 위반 아님**.

### 11-4. reviewer 게이트 — 커밋 가능 **Y** (블로커 0건)

비블로커 권고 2건, 둘 다 다음 태스크로 이관:

| 권고 | 이관처 |
|---|---|
| MQ-905 DoD 의 `extract_triage.py` 라벨 이동 조건이 현재 실측 불가함을 §9-4 델타 표에 명시 | MQ-911 또는 MQ-918 |
| `_fuzzy_contains()`(부분수열 매칭, 명세 인터페이스 스케치 밖 추가 함수)를 문서 인터페이스 절에 소급 반영 | MQ-907 또는 MQ-911(같은 파일을 다루는 다음 태스크) |

### 11-5. Stage 3 착수 전 참고

- MQ-907(S100 26건 재추출)은 **`error_codes_actions.candidate.json` 에 append** 하는 태스크다 — MQ-905 가 남긴 iG5A entries 2건 + pending 9건이 **잔존하는지 확인**하는 것이 DoD 에 이미 포함돼 있다.
- MQ-911(사람 검수 패키지)이 만들 대조표는 **entries 2건**(iG5A, S100 추가분은 MQ-907 이후 결정)을 기준으로 작성해야 한다 — §9-3 MQ-905 명세의 "10건" 기대치를 그대로 베끼지 않는다.
- `decisions.py:602` 주석 갱신(MQ-904 가 남긴 메모 — `repair_records.created_at` 신설로 낡음)은 **MQ-918 전파 목록에 추가할 것**.

---

## 12. Stage 3 완료 (2026-08-16)

**브랜치**: `sprint-9-repair-record` (⛔ master 미머지 — 머지는 사람 요청 시에만)
**커밋**: `b16d946` — `[M2] Sprint 9 Stage 3 — create_repair_record 신설(D98·16번째 도구) · assess_repair_value 위임 · S100 재추출`

### 12-1. 태스크별 결과

| TASK | 산출 | 실측 |
|---|---|---|
| **MQ-922** | `mcp_server/tools/assess_repair_value.py`(위임) · `data/maint_value.py`(`repair_value()` 추가) | `asset_tools_contract` **49건 무변경 통과** · `read_only()` 2→1회 · `server.py` **무접촉 확인** |
| **MQ-906** | `mcp_server/tools/create_repair_record.py`(신규) · `mcp_server/db.py`(`repair_writer()`) · `mcp_server/server.py` · `docs/04_MCP_TOOLS.md §16`(신설) | `full` 프로파일 **15 → 16종**, `core` 7종 불변. 도구 1회 실호출 → `repair_records` 1행 추가, `n_repairs_signed` 불변 확인. 델타 소유 파일(`prompts.py`·`tools_profile_contract.py`·`s10_smoke.py`) 반영 + 연쇄로 `spikes/prompt_rules.py`(하드코딩 도구 개수 어서션 파손) 도 수정 |
| **MQ-907** | `data/extract_error_codes.py`(S100 조인 함수 신규 추가, `parse_s100()` 본체 무수정) · `error_codes_actions.candidate.json`(append) | S100 결측 26건 중 **FANW 1건만 회수**(나머지 25건은 매뉴얼 원문에 조치 자체가 없음 — 지어내지 않고 `_pending_review`). 기존 보유 15건 diff **0**. `verify_verbatim()`에 표 열 재크롭 대조(합집합) 추가 |

### 12-2. reviewer 게이트 — 1차 FAIL → 수정 → 2차 PASS

| 회차 | 판정 | 사유 |
|---|---|---|
| 1차 | **FAIL**(블로커 1건) | `create_repair_record.py` 조회~산출 블록(구 206~274행)에 **D9 가 요구하는 범용 `except Exception` 안전망이 빠져 있었다.** 같은 등급의 형제 쓰기 도구 `generate_disposal_document.py` 는 조회~INSERT 를 단일 try 로 묶고 3단 캐치를 거는데, 이 도구는 두 블록으로 쪼개면서 앞쪽의 안전망을 빠뜨렸다 — 파일 자체 docstring(D9 명시)과 코드가 어긋난 상태였다 |
| 수정 | — | 조회~산출 블록 끝에 `except Exception as e: return _fail("internal_error", ...)` 추가(`generate_disposal_document.py` 패턴 그대로) |
| 2차 | **PASS**(블로커 0건) | 수정 후 ruff·`verify_verbatim` 재검증(대조 3건·위반 0건, iG5A 2건 재확인)·seed 29건·pytest 46건·spikes 28스위트 전건 재실행 통과 |

비블로커 권고 4건, 전부 정보용으로 판정(재작업 요구 아님):
- `part_class` 집계 우선순위(CRITICAL > NULL > CONSUMABLE)가 `docs/04_MCP_TOOLS.md:930` 에 문서화돼 코드-문서 일치 확인 — 사람 승인 체크리스트에 이 우선순위를 명시적으로 얹을 것을 권고
- `expenditure()` 하위 실패 시 INSERT 생략 — `04 §13` "하위 실패를 삼키지 않는다" 원칙과 일치, 타당
- `verify_verbatim`/`_page_haystack` 합집합 확장(안전 관련) — 이론상 검사를 더 관대하게 만들 수 있는 방향이나, 후보 파일이 DB 미적재·사람 검수(G1) 필수 경유라 즉각 위험은 낮음. **권고**: 조작된 문장(fabricated string)이 실제로 걸러지는 음성 테스트를 MQ-913(`repair_flow_contract`) 또는 별도 pytest 에 추가할 것
- `docs/04_MCP_TOOLS.md` 프리앰블(공통 규약·설계원칙 6) 손질은 §16 신설과 직접 얽힌 자기모순 방지 목적으로 범위 침범 아님

### 12-3. 회귀 실측 (전건 통과 · 감소 0 · 재시도 0)

seed **29건** · pytest **46건** · spikes **28스위트**(Stage 2 기준선 **640건**과 완전 동일 — 도구 개수·프로파일 상수만 바뀌었고 스파이크 **검사 건수**는 아직 안 늘었다. `write_tool_contract` 3종 확장은 MQ-913(Stage 5) 소관으로 이월) · `ruff check data backend mcp_server spikes` 통과.
Windows 소켓 고갈 징후 없음(1회차 완주 후 D9 수정 반영해 재실행, 2회차도 완주).

### 12-4. Stage 4 착수 전 참고

- MQ-913(Stage 5) 의 `repair_flow_contract` 신설 시 `write_tool_contract` 2→3종 확장에 **`create_repair_record` 의 D9 안전망 재발 방지 검사**(임의 예외를 흡수하는지)를 넣을 것 — 이번 스테이지는 사람이 리뷰로 잡았고 회귀가 아직 못 잡는다.
- MQ-913 또는 별도 pytest 에 **`verify_verbatim` 음성 테스트**(조작된 문장이 위반으로 걸러지는지) 신설 권고가 이월됨(§12-2).
- MQ-908(Stage 4) 착수 전 정할 것 — `decisions._metrics()` 방침(§9-4 델타 MQ-908 행, D101 이 인용한 "산식이 두 벌"을 해소할지 인용을 뺄지)은 **아직 미결**이다.

---

## 13. Stage 4 완료 (2026-08-16)

**브랜치**: `sprint-9-repair-record` (⛔ master 미머지 — 머지는 사람 요청 시에만)
**커밋**: `1ec937e` — `[M2] Sprint 9 Stage 4 — 확장 도구 REST 노출 5종(D73) · decisions._metrics() 위임(D101) · lookup_error_code actions_source(D100) · 사람 검수 패키지(G1 입력)`

### 13-1. 착수 전 결정 — `decisions._metrics()` 방침 확정 (사람, ⓐ 위임)

§12-4 가 남긴 미결 사항. **ⓐ(`data.maint_value.maintenance_metrics()` 위임)로 확정** — `_metrics()` 출력이 들어가는 정비 이력 요약서 섹션이 `decisions.py:788` 부근에서 이미 `hash_fixed: False` 로 강제돼 있어(서명 해시가 고정하는 건 `evidence_bundle` 5키뿐) 위임해도 서명 해시가 깨질 위험이 없다는 것을 확인한 뒤 내렸다. 위임 후 4개 자산(`AST-L3-CONV`·`L4-WRAP`·`L2-SPDL`·`L3-LIFT`)에서 위임 전/후 출력 완전 동일 확인, `spikes/approvals_contract.py ⑳`(도구-백엔드 산식 대조 드리프트 감시) 무증감 통과, "산식이 두 벌 존재한다"는 옛 서술을 코드에서 제거 — **D101 이 인용한 근거가 이제 실제로 해소됐다.**

### 13-2. 태스크별 결과

| TASK | 산출 | 실측 |
|---|---|---|
| **MQ-908** | `backend/services\|routers/maint_value.py`(신규, REST 5경로) · `backend/services/decisions.py`(`_metrics()` 위임 전환) | `core` 프로파일에서 5경로 전부 200/정의된 4xx · `GET /health` `tools:7, tools_profile:"core"` · `api_contract` 28건·`approvals_contract` 26건 무증감 |
| **MQ-910** | `mcp_server/tools/lookup_error_code.py`(`actions_source` 신설) | `actions_source: {manual_id,page}\|null` 키 항상 존재, `print_page` 0건(D32 재발 없음 확인) |
| **MQ-911** | `data/analysis/actions_review.md`(신규) · `TODO_직접할일.md`(`## actions 검수` 절) | 표 1=3건(entries 수와 기계 대조 일치) · 표 3=35건(`_pending_review`와 일치) · 안전 키워드 스캔 대상 3건 중 **0건 적중**(양성 축과 함께 기록) · TODO 3항목 미체크, 승인 문구 없음 확인 |

### 13-3. reviewer 게이트 — PASS(블로커 0건) + 코디네이터가 직접 고친 것 2건

reviewer 판정은 1차부터 **PASS** — 이번 스테이지는 Stage 3 와 달리 재작업 없이 통과했다. 단 스테이지 진행 중 코디네이터가 직접 고친 것이 2건 있다(reviewer 검토 **전**에 이미 반영):

| # | 무엇을 | 왜 |
|---|---|---|
| ① | `spikes/lookup_contract.py` 의 합성 DDL·`FIXTURE`·`CONTRACT_KEYS` 갱신 | MQ-910 이 SELECT 에 `actions_manual_id`·`actions_page` 를 추가하자, 이 스파이크가 쓰는 **합성 DB**(Stage 2 에서 실 스키마에 이미 추가된 두 컬럼을 반영 못 함)에서 체크 ④가 `KeyError` 로 죽는 회귀가 났다. MQ-910 은 태스크 범위(스파이크 미수정)를 지켜 그대로 뒀고, **코디네이터가 직접 고쳤다** — DDL 에 두 컬럼+짝 CHECK 추가, `FIXTURE` 3행에 `None,None` 추가, `CONTRACT_KEYS` 에 `"actions_source"` 추가. 신규 검사 추가가 아니라 **기존 12건 픽스처를 실 스키마와 동기화**한 것이라 MQ-913(Stage 5, 신규 검사 담당)의 몫을 침범하지 않는다 — reviewer 도 이 판단에 동의 |
| ② | `backend/routers/decisions.py` 의 `get_decision`·`submit`·`sign`·`reject` 4곳에 `except RuntimeError` 추가 | reviewer 가 비블로커로 지목: `_metrics()` 위임 전환 후 실패 시 `RuntimeError` 를 던지는데(전에는 절대 실패하지 않던 함수), 라우터 어디도 이걸 안 잡아서 **서명이 실제로 성공했는데 응답 조립 단계에서 구조 없는 500** 이 날 수 있었다. 4곳에 `500 + {reason:"metrics_assembly_failed"}` 구조화 응답 추가. `api_contract`·`approvals_contract`·`disposal_api_contract`·`disposal_sign_contract` 재실행 무증감 통과 확인 후 반영 |

reviewer 가 상세 확인한 것(문제 없음으로 결론): evidence-bundle 라우터 응답이 명세 스케치("(bundle, bundle_hash)")보다 넓지만 `docs/04_MCP_TOOLS.md §14` 정본과 필드 단위로 정확히 일치, 복제된 `HASH_SPEC`·disclaimer 문자열이 도구 원본과 바이트 단위로 동일, `actions_source` 방어 코드 생략이 실제 DDL CHECK(`data/seed.py`)로 뒷받침됨, MQ-911 표 1의 `error_name`/`join_key` 병기가 D99 를 흐리지 않음.

### 13-4. 회귀 실측 (전건 통과 · 감소 0 · 재시도 0)

seed **29건** · pytest **46건** · spikes **28스위트**(Stage 3 기준선과 완전 동일 — `lookup_contract`·`api_contract`·`approvals_contract`·`disposal_api_contract`·`disposal_sign_contract` 는 코디네이터 수정 반영 후 **재확인 완료**) · `ruff check data backend mcp_server spikes` 통과.

### 13-5. Stage 5 착수 전 참고 — reviewer 비블로커 권고 이월

- `docs/06_REPO_API.md` 에 이번에 신설된 REST 5경로가 **아직 등재돼 있지 않다**(grep 0건) — **MQ-918 전파 목록에 추가할 것**.
- `backend/routers/maint_value.py` 의 `HASH_SPEC`/disclaimer 복제본에 **자동 드리프트 감시가 없다**(현재는 수동 대조로만 일치 확인) — `data/ownership.py` 상수 재사용 + 드리프트 assert 선례와 다른 패턴이다. **MQ-913(Stage 5)의 REST 계약 스파이크에 문자열 동일성 체크 추가를 권고**.
- MQ-913 착수 시 §12-5(Stage 3 이월)와 합쳐서 확인할 목록: ① `create_repair_record` D9 재발 방지 검사 ② `verify_verbatim` 음성 테스트(조작 문장 검출) ③ `lookup_contract` 신규 검사 +2(actions_source 키 존재·null 사유) ④ **이번에 추가된 REST 5경로의 문자열 드리프트 체크**.

---

## 14. 🔴 스테이지 순서 오류 — "Stage 5" 로 잘못 실행된 것을 정정 (2026-08-16)

### 14-1. 무슨 일이 있었나

`§9-2 확정 스테이지` 표는 **Stage 5 = MQ-909(수리 증빙 제출·서명·반려 API) 단독**, **Stage 6 = MQ-912·913 병렬**로 명시돼 있었다. 코디네이터(에이전트)가 Stage 4 완료 직후 이 표를 다시 읽지 않고 "다음은 프론트 배관 + 회귀 스파이크"라고 **기억으로 판단**해 MQ-912·913 을 "Stage 5" 로 잘못 실행했다. 그 과정에서 코디네이터는 두 tool-builder 프롬프트에 *"`GET/POST /api/repairs/*` 는 아직 없다 — MQ-909 가 이번 스프린트에서 컷돼 §9-5 에 따라 다음 스프린트로 이월됐다"* 는 **근거 없는 전제**를 직접 써넣었다. 실제로는:

- `§9-5`(이월 목록)에 MQ-909 는 없다 — 있는 것은 MQ-915·MQ-916·`traces.request_chain_id` 3건뿐.
- `§7`(압축 순서)은 오히려 MQ-909(서명 API)를 **"덜어내면 안 되는 것" 7건 중 하나로 명시 보호**한다.
- `§9-1`은 MQ-915·916 컷의 근거로 *"축 A(수리 증빙)는 **API 까지 완결된다**"*를 들었는데, 이건 MQ-909 가 실제로 있어야만 참인 문장이다.

두 구현 에이전트(MQ-912·913)는 이 거짓 전제를 그대로 믿고 `/api/repairs/*` REST 왕복을 **스킵**했고, 그 사실을 `frontend/lib/api.ts`·`frontend/lib/types.ts`·`spikes/repair_flow_contract.py`·`spikes/approvals_contract.py` **4개 파일**에 "MQ-909 이월, §9-5 참조"로 반복 기재했다. reviewer 1차 패스가 이걸 **블로커**로 잡아냈다(문서 대조로 §9-5 에 MQ-909 가 없음을 직접 확인).

### 14-2. 정정 경위

1. 커밋 전이었으므로 **되돌릴 것 없이** 진짜 Stage 5(MQ-909)를 그 자리에서 실행 → 커밋 `8b0f809`.
2. MQ-909 가 실재하게 된 뒤, 코디네이터가 직접 4개 파일의 허위 문구를 실제 REST 경로로 교체:
   - `spikes/repair_flow_contract.py` — 스킵했던 REST 왕복(submit 403 양방향·self_sign 409·sign+해시대조·재서명 409·reject 422/200·`n_repairs_signed` +1)을 `run_repair_flow_rest_axis()`로 실제 구현. 10건 → **19건**.
   - `spikes/approvals_contract.py ③` — "0건"(REST 미노출) 우회 대신 **REST 응답 건수 == `repair_records` 실측 건수** 직접 대조로 교체.
   - `frontend/lib/api.ts` — `/api/repairs/*` 관련 docstring·주석에서 "아직 없다" 삭제, `ApiRepair` 필드를 실제 백엔드 출력(`performed_by_name`·`verified_by_name`·`hash_verified`)에 맞춰 정정, `signRepair`의 불필요한 body 파라미터 제거(백엔드 `sign` 라우트는 body 없음).
3. reviewer 재검토(Stage 5+6 통합) — **1차 FAIL**: 같은 허위 전제가 `frontend/lib/types.ts:36`(`RepairState` 타입 주석)에 **한 곳 더** 남아 있었다(지시받은 3파일 검색으로는 안 걸리는 사각지대). `ApprovalKind`(`:45`)의 "Sprint 7 에서 항상 0건"도 낡아 있었다. 코디네이터가 두 곳 정정 → **2차 PASS**.
4. reviewer 가 발견했으나 이번 판정 범위 밖으로 남긴 것: `docs/06_REPO_API.md:376~385`(§2.3 통합 승인 큐)가 여전히 "repair 는 항상 0건 · POST 없음"으로 낡아 있다 — **MQ-918 전파 목록에 추가**(아래 §14-4).

### 14-3. 커밋 분리

두 스테이지 작업물은 실제 소유 태스크 기준으로 분리 커밋했다(§9-2 표의 스테이지 경계 그대로):
- `8b0f809` — Stage 5(MQ-909): `backend/routers|services/repairs.py`(신규) · `backend/services/approvals.py` · `backend/main.py`.
- `f294a61` — Stage 6(MQ-912·913, 정정 반영): `frontend/lib/*` · `spikes/{write_tool_contract,repair_flow_contract,approvals_contract,lookup_contract}.py`.

### 14-4. 재발 방지 + 다음 스테이지 참고

- **재발 방지**: 이후 스테이지 착수 전 반드시 `§9-2 확정 스테이지` 표를 다시 읽고 스테이지 번호·소속 태스크를 확인한다 — 기억으로 다음 스테이지를 판단하지 않는다.
- `docs/06_REPO_API.md §2.3`(repair 는 항상 0건·POST 없음 서술)이 낡았다 — **MQ-918 전파 목록에 추가할 것**.
- 회귀 실측: seed **29건** · pytest **46건** · spikes **29스위트 / 668건**(Stage 4 기준선 640 + lookup +2 + write_tool +7 + repair_flow 신규 19) · `ruff` 통과 · frontend `tsc --noEmit`·`npm run build`(라우트 10개 유지) 통과. 감소 0·재시도 0.
- **Stage 7(MQ-914) 착수 전 §9-2 표를 다시 확인할 것** — 이번 사고의 재발 방지 규칙을 스스로 지키는 첫 적용이다.

---

## 15. Stage 7 완료 (2026-08-17)

**브랜치**: `sprint-9-repair-record` (⛔ master 미머지 — 머지는 사람 요청 시에만)
**커밋**: `bb2ae93` — `[M3] Sprint 9 Stage 7 — 수리 가치 판단 화면 (S1+, MQ-914)`

착수 전 §9-2 표 재확인(§14 재발 방지 규칙 적용): Stage 7 = **MQ-914 단독** 확인 후 실행. MQ-915·916 은 §9-5 에 실제로 이월 등재돼 있음을 재확인(Stage 5 사고와 달리 이번엔 사실).

### 15-1. 산출

`frontend/app/(console)/technician/asset/[assetId]/value/page.tsx`(신규 라우트) ·
`RepairValuePanel`·`CriticalityDrawer`·`ExpenditureCard`·`MetricsAside`(신규 4종) ·
`mappers.tsx`(판정 매퍼 4종 추가: `repairValueVerdictView`·`expenditureVerdictView`·`partClassView`·`expenditureEvidenceView`).

### 15-2. reviewer 게이트 — 1차 PASS(블로커 0건)

판단이 필요했던 지점 4건, 전부 정당함을 코드로 확인:
- `RepairValuePanel`의 입력 폼 — 명세 배치도는 조회 전용으로 그렸지만 `assess_repair_value`가 `equipment_id`·`failed_part`·`repair_cost`를 필수 자유 입력으로 받는 도구 계약(D80)이라 폼이 불가피 — 다이어그램 쪽 누락이지 구현 결함 아님
- `ExpenditureCard`가 `asset_id`를 안 보내 `materiality`가 항상 `NOT_EVALUATED` — Stage 6 의 `ExpenditureBody` 계약 자체에 그 필드가 없어서(백엔드 라우터 제약)이고, D65 가 요구하는 정직한 표시 — 실질 개선은 별도 D-결정 필요(비블로커 권고)
- `CriticalityDrawer`의 fixed-position 오버레이 구현이 "라우트 이동 없음·닫아도 상위 판정 유지" 요구를 충족함을 코드로 확인
- `MetricsAside`의 "6칸 전부 null" 데모가 실측 데이터로는 안 나온다는 보고(MTBF 는 서명 여부 무관 — 달력 기준 계산)는 은폐가 아니라 정직한 보고, null-safety 자체는 코드로 확인됨

### 15-3. 회귀 실측 (전건 통과 · 감소 0 · 재시도 0)

seed **29건** · pytest **46건** · spikes **29스위트**(`ui_honesty_contract` 만 L2 글롭이 신규 4파일을 자동 포함해 **계약 57→81건**으로 증가, 그 밖 28스위트는 Stage 6 기준선과 동일 — 감소 0) · `ruff` 통과 · frontend `tsc --noEmit` 통과 · `npm run build` **라우트 11개**(10 + 1).

### 15-4. Stage 8 착수 전 참고

- MQ-917(`ui_honesty_contract` 확장)이 다음 스테이지다 — L2 스캔 대상에 `RepairDetail.tsx`(MQ-916 이월로 아직 없음)를 추가하는 부분은 **건드리지 않는다**(파일이 없으므로).
- `ExpenditureCard` 의 `asset_id` 미전달 문제는 실질 개선을 원하면 별도 D-결정 + 백엔드 라우터 변경이 필요하다는 게 reviewer 권고 — 이번 스프린트 범위에는 없음, 백로그 후보로만 기록.

---

## 16. Stage 8 완료 (2026-08-17)

**브랜치**: `sprint-9-repair-record` (⛔ master 미머지 — 머지는 사람 요청 시에만)
**커밋**: `9f2fd34` — `[M3] Sprint 9 Stage 8 — ui_honesty_contract 확장 (D65·D74·D87·D64 방어선, MQ-917)`

착수 전 §9-2 표 재확인(§14 재발 방지 규칙 적용): Stage 8 = **MQ-917 단독** 확인 후 실행.

### 16-1. 산출

`spikes/ui_honesty_contract.py` · `frontend/lib/__checks__/ui_honesty.ts` — L1(순수함수) 검사 13건 신설 · D64 축 신설(주석 필터링으로 위양성 방지, 양성 축 포함) · 뮤턴트 3종 추가(ⓕⓖⓗ, 전부 실제로 방어선을 깨뜨리는 것을 실증) · `L2_FILES_FLOOR` 8→12 실측 갱신 · `STATE_WORDS`에 `assess_repair_value` verdict enum 4종 추가(`04_MCP_TOOLS.md`와 대조 일치).

### 16-2. 명세 델타 준수

원 명세는 "`L2_EXTRA`에 `RepairDetail.tsx` 추가"를 요구했으나 §9-4 델타가 이를 삭제(MQ-916 컷으로 그 파일 자체가 없음) — 실제로 `RepairDetail` 문자열이 스위트에 0건임을 reviewer가 코드로 재확인.

### 16-3. reviewer 게이트 — 1차 PASS(블로커 0건)

뮤턴트 3종(ⓕⓖⓗ)이 실제로 방어선을 깨뜨리는지 코드 레벨로 대조 확인(공허 통과 방지 장치 — `mutate_l1`이 치환 실패 시 자체 FAIL). D64 축의 주석 필터링(`strip_comments`)이 검사를 무력화하는 구멍이 아니라 "실제 코드에 없다"를 증명하는 정당한 방식임을 자체 픽스처 검증·뮤턴트 ⓔ로 확인. `L2_FILES_FLOOR` 12가 실측(글롭 직접 카운트)과 정확히 일치.

### 16-4. 회귀 실측 (전건 통과 · 감소 0 · 재시도 0)

seed **29건** · pytest **46건** · spikes **29스위트**(`ui_honesty_contract` 기준선 92건 → **102건**, 그 밖 28스위트 무증감) · `ruff` 통과 · frontend `tsc --noEmit` 통과 · `npm run build` **라우트 11개 유지**(이번 태스크는 프론트 컴포넌트를 만들지 않음).

### 16-5. Stage 9 착수 전 참고

- 다음 스테이지는 MQ-918(문서·개수 전파) — §9-2 표 재확인 결과 **단독**.
- 이번까지 누적된 전파 대상: `docs/06_REPO_API.md §2.3`(repair 낡은 서술, §14-4에서 발견) · `decisions.py:602` 주석(§11-5) · `L2_FILES_FLOOR`가 컴포넌트 증가마다 갱신 필요하다는 사실(§16-1) · D 범위 표기 `D1~D101` 등.

---

## 17. Stage 9 완료 (2026-08-17)

**브랜치**: `sprint-9-repair-record` (⛔ master 미머지 — 머지는 사람 요청 시에만)
**커밋**: `ae96912` — `[M3] Sprint 9 Stage 9 — 문서·개수 전파 (MQ-918)`

착수 전 §9-2 표 재확인(§14 재발 방지 규칙 적용): Stage 9 = **MQ-918 단독** 확인. 코디네이터가 착수 전 spikes 29스위트를 직접 실행해 정확한 스위트별 건수(총 702건)를 실측한 뒤 실행에 착수(기억으로 적지 않는다는 CLAUDE.md 규칙 준수).

### 17-1. 산출

`CLAUDE.md`·`README.md`·`docs/README.md`·`docs/00_MVP_SCOPE.md`·`docs/02_SCENARIOS.md`·`docs/05_DB_SCHEMA.md`(§1·§16 DDL 전면 교체, 자가검증 26→29)·`docs/06_REPO_API.md`(§2.8 신설, §2.5·§2.7 정정)·`docs/07_BACKLOG.md`(P25 ✅ 완료, P31 🟡 유지)·`docs/10_DECISIONS.md`(D69·D74·D77 사실관계·렌더링 결함만 정정)·`docs/12_MAINT_VALUE.md`·`docs/status/*.html`(3개)·`TODO_직접할일.md`·`data/maint_value.py`(주석만).

### 17-2. reviewer 게이트 — 1차 FAIL(블로커 2건) → 수정 → 2차 PASS

| 회차 | 판정 | 사유 |
|---|---|---|
| 1차 | **FAIL** | ⓐ `docs/07_BACKLOG.md`에 MQ-915·916(§9-5 이월 확정)이 등재돼 있지 않아 **정본 백로그에서 조용히 사라진 상태** — §9-4 델타 ⓒ가 명시적으로 막으려던 바로 그 상황이 재현됨. ⓑ `CLAUDE.md:24-25`(절대 규칙 1) 본체가 여전히 `po_drafts`·`decisions`/`po.py`·`decisions.py`만 언급하고 `repair_records`·`backend/routers/repairs.py`(D98)가 빠짐 — 하위 불릿(쓰기 도구 3종)은 정정됐는데 정작 규칙 제목이 낡은 채 남음 |
| 수정 | — | `docs/07_BACKLOG.md`에 **P37**(MQ-915)·**P38**(MQ-916)을 "🟡 Sprint 10 이월"로 신규 등재(API는 이미 완결·화면만 남았다는 근거 포함) · `CLAUDE.md` 규칙 1 본체에 `repair_records`·`backend/routers/repairs.py` 추가 |
| 2차 | **PASS** | reviewer가 P37·P38 내용을 실제 라우터 코드(`backend/routers/maint_value.py`·`repairs.py`)와 대조해 근거 검증, `CLAUDE.md` 정정 확인, P36 서술 훼손 없음·P 번호 중복 없음 확인 |

reviewer가 "마커만" 제약(§4, `docs/10_DECISIONS.md`) 위반 여부도 별도 확인: D69·D74·D77 수정은 §9-4 델타 ⓔⓕ가 지시한 **사실관계 오탈자(도구 개수)·마크다운 렌더링 결함(`|` 미이스케이프)** 정정뿐이고 결정의 판단·이유·채택근거는 한 글자도 안 바뀌었음을 diff 대조로 확인 — 제약 위반 아님, 새 D 등재 대상도 아님.

### 17-3. 회귀 실측 (전건 통과 · 감소 0 · 재시도 0)

seed **29건** · pytest **46건** · spikes **29스위트 / 702건**(무증감 — 이번 스테이지는 코드 로직을 건드리지 않음, `data/maint_value.py`도 주석만) · `ruff` 통과.

### 17-4. Stage 10 착수 전 참고

- 다음은 **MQ-919(조건부)** — G1(사람 검수)·G2(재승인 범위 확정) **승인 후에만** 착수. `TODO_직접할일.md`의 `## actions 검수` 절(MQ-911 산출, 3항목 미체크) 승인이 선행 조건.
- 승인 전까지는 **스프린트 사실상 종료 상태** — Stage 1~9(MQ-901~918, MQ-920·921 포함) 전부 완료, 이월 확정 2건(MQ-915·916, P37·P38로 백로그 등재) 남음.
- `/done` 실행 시 D 범위 표기 정합성(이미 D1~D101로 최신) 재확인은 형식적으로만 필요 — 이번 스테이지에서 이미 검증됨.

---

## 18. G1·G2 사람 승인 (2026-08-17)

사용자가 `TODO_직접할일.md`의 `## actions 검수` 절 3항목 전부를 채팅에서 직접 승인("응 승인할게") — 커밋 `a4261b3`. `data/extracted/error_codes_actions.candidate.json`의 `_status`를 "초안 — 사람 검수 대기"→"승인 완료 (2026-08-17)"로 갱신, TODO 3항목 체크. G1(검수)·G2(재승인 범위 확정)가 동시에 충족돼 MQ-919 착수 조건이 열렸다.

## 19. Stage 10 완료 (2026-08-17) — 마지막 스테이지

**브랜치**: `sprint-9-repair-record` (⛔ master 미머지 — 머지는 사람 요청 시에만)
**커밋**: `d29143a` — `[M1] Sprint 9 Stage 10 — 승인된 actions 3건 정본 병합 (D99·G1·G2, MQ-919)`

🔴 이 스테이지는 `CLAUDE.md`가 두 번의 DB 파괴 사고(MQ-708·MQ-713a)를 기록한 `data/extracted/error_codes.json`(정본)을 직접 수정하는 가장 위험한 작업이었다. 코디네이터가 착수 전 현재 상태를 직접 조회해 확보한 뒤(65 entries, 승인 대상 3건의 정확한 현재값), 매우 상세한 안전 지침과 함께 위임했다.

### 19-1. 산출

`data/merge_approved_actions.py`(신규, 멱등 병합 스크립트) · `data/extracted/error_codes.json`(정본, 3건만 변경) · `data/extracted/ig5a_action_map.json`(`_status` 동적 갱신) · `data/seed.py`(자가검증 29→30) · `spikes/lookup_contract.py`(⑭ 전건 null → 실측 대조).

### 19-2. 핵심 설계 판단 — `write_canonical()`을 재사용하지 않았다

Stage 1(MQ-921)이 만든 정본 쓰기 가드 `write_canonical()`은 자체 문서에 "내용이 달라지면 항상 거부한다 — 의도한 갱신이면 사람이 검토 후 **직접 반영**하라"고 명시돼 있어, 이번처럼 **의도적으로 승인된 변경**을 기록하는 것 자체를 거부하도록 설계돼 있다. 그래서 `merge_approved_actions.py`는 그 함수를 안 쓰고, 대신:
- `APPROVED = [("iG5A","RERR"),("iG5A","ETB"),("S100","FANW")]` **하드코딩 3건만** 순회(후보 파일 전체 자동 병합 아님 — 다음 스프린트가 후보 파일에 이어 써도 이 스크립트가 안 건드린다)
- 병합 전/후 65건을 `(model,code)` 키로 짝지어 `actions`·`actions_manual_id`·`actions_page` 3필드를 제외한 나머지 전부를 정준 직렬화·해시 대조 — **하나라도 불일치하면 파일을 쓰지 않고 중단**
- `ig5a_action_map.json`의 `_status`는 `pending_review` 9건이 남아 있어 낙관적으로 "승인 완료"로 안 바꾸고 실측(mappings 2건·pending 9건)을 반영한 동적 문구로("부분 반영") 갱신(D19 원칙)

### 19-3. reviewer 게이트 — 1차부터 PASS(블로커 0건)

reviewer가 해시 대조 로직(`_entry_hash` 제외 필드 3종 정확성 · `(model,code)` 키별 개별 비교 · 쓰기 전 중단 순서)을 코드 레벨로 직접 추적해 확인, `git diff`로 65건 중 정확히 3건만·그 3건도 승인된 3필드만 변경됐음을 재확인. 코디네이터도 사전에 `git diff`를 직접 읽어 대조.

### 19-4. 실측 검증 (전건 통과·감소 0)

- 병합 스크립트 실행: "비-actions 필드 65건 중 65건 일치 · 불일치 0건" 실측 출력.
- `error_codes.json` entries 수 **65 불변**.
- `data/seed.py --with-error-codes` → **30/30 통과**, `error_codes` 65행.
- `SELECT ... WHERE actions_manual_id IS NOT NULL` → **정확히 3행**, 값이 후보와 일치.
- `spikes/lookup_contract.py` → **14/14 통과**.
- **멱등성**: 스크립트 3회 재실행 후 `git hash-object`로 파일 해시 불변 확인.
- 전체 회귀: seed 30건 · pytest 46건 · spikes 29스위트 전건 통과(`s4_smoke` 1회 Windows 소켓 고갈 재시도 후 통과, CLAUDE.md 기록된 정상 현상) · ruff 통과.
- ⛔ `eval/run_eval.py` 미실행 — G3(평가 재측정 비용 승인) 대기 중, 이번 스테이지 범위 밖.

### 19-5. Sprint 9 종료

Stage 1~10(MQ-901~921, MQ-919 포함) **전부 완료**. 이월 확정 2건(MQ-915·916)은 백로그 P37·P38로 등재됨. 남은 사람 승인 대기: G3(평가 재측정 비용), `SAFETY_BASELINE`/`QUALIFIED_WORKER_NOTE` 문안 검수, `RESIDUAL_AT_LIFE_END`/`FLOOR` 가정 동의, `KR-CITA-ENF-31` 정정 확인, A2A 파트너 자격증명 실값 — 전부 기존 이월 항목이며 이번 스프린트 완료를 막지 않는다.
