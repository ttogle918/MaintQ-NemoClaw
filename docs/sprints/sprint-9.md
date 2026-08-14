# Sprint 9 — create_repair_record(P25) · actions 회수(P31) · 확장 도구 프론트 노출

**상태**: 📝 계획 수립 완료 · tool-builder 현실성 평가 **대기** (다음 세션)

**수립일 2026-08-14** · 브랜치 `data/part-catalog` 이후 신규 브랜치 권장(머지는 요청 시에만)
**기준선(DoD 에 그대로 쓴다)**: spikes **28스위트 / 635건** · seed **26건** · pytest **46건** · 프론트 라우트 **10개** · `error_codes` **65행**

> ⚠ **이 문서는 계획이다. 코드는 아직 없다.** 실행은 `/stage 1` 부터.
> tool-builder 현실성 평가가 **아직 안 돌았다** — §9 가 비어 있는 이유다.
> 평가 전에는 스테이지 배치·태스크 수가 확정이 아니다(특히 §7 압축 순서).

---

## 0. 착수 전 정정 — 계획을 바꾸는 실측 5건

계획을 짜면서 **문서만 보고는 안 보이는 사실 5건**이 나왔다. 이 5건이 스테이지 배치를 지배한다.

| # | 실측 | 계획에 미치는 영향 |
|---|---|---|
| **①** | `backend/**` 는 `mcp_server/**` 를 **import 할 수 없다**(D15). `backend/services/decisions.py:520` 이 *"도구는 mcp_server 소유라 import 할 수 없다 — 그래서 산식이 두 벌 존재한다"* 고 **자백**하고 있다 | **축 C 는 화면 태스크가 아니라 로직 이동 태스크가 선행이다.** `assess_repair_value`·`get_maintenance_metrics`·`classify_part_criticality`·`classify_expenditure` 의 산출부를 `data/maint_value.py`(공유 데이터 계층 D73)로 옮기지 않으면, REST 노출은 **산식 두 벌**이 되고 D65 추정치가 화면과 도구에서 갈린다 |
| **②** | `build_evidence_bundle` 은 **예외다** — `backend/services/decisions.py:252 rebuild_bundle()` 이 이미 조립을 재현하고 있다(D84 해시 재대조용) | 우선순위 2 는 **신규 중복 0** 으로 노출된다. 얇은 래퍼만 얹으면 된다 |
| **③** | `data/seed.py:1798` 이 `INSERT INTO error_codes VALUES (?,?,?,?,?,?,?,?,?)` — **위치 인자 9개**다 | `actions` 출처 컬럼을 추가하는 순간 이 INSERT 가 조용히 어긋난다. 컬럼 명시로 바꾸는 것이 선행 |
| **④ 🔴** | `data/seed.py:1687 error_codes_gate()` 는 `_status` 에 `"초안"` 이 들어가면 **테이블 전체를 0행으로 만든다.** 그리고 `_status` 는 `ig5a_code_map.json` 에서 **자동 유도**된다(`extract_error_codes.py:438`) | **`actions` 회수분을 `error_codes.json` 에 직접 쓰면 65행이 0행으로 붕괴한다** — CLAUDE.md 가 경고한 그 사고가 *"파서를 고쳤을 뿐인데" 재발*한다. → **후보 파일 격리(D99)** 가 필수 |
| **⑤** | `spikes/approvals_contract.py:177~183` 이 *"kind=repair → 0건"* 을 **명시 검사**한다. seed 에는 `repair_records` 12행(서명 11 · 미서명 1)이 이미 있다 | 축 A 가 큐를 배선하는 순간 이 검사는 **반드시 뒤집힌다.** 그게 정상 신호이고, 뒤집을 때 **양성 축**(0→N, N 의 실측값을 detail 에 인쇄)으로 다시 짜야 한다 |

**코디네이터 지적 ⑤(축 A ↛ 축 C 하드 의존)에 동의한다** — `downtime_hours` 전건 존재이므로 축 C 지표 화면은 축 A 없이도 값이 나온다. 다만 **축 A 가 먼저 끝나면 빈칸이 줄어들므로** 축 A 를 앞 스테이지에, 축 C 화면을 뒤 스테이지에 둔다(사용자 지시와도 일치).

### 0-B. 축 B 전제 정정 — 2026-08-14 코디네이터 실측 (계획 전에 잡혔다)

`docs/07_BACKLOG.md` P31 의 ⓐ 서술(*"소스를 추가하면 된다"*)이 **틀렸다.** 계획 착수 중 실측으로 드러났다.

| | 백로그 서술 | **실측** |
|---|---|---|
| **ⓐ iG5A 11건** | "추출 소스만 추가하면 된다" | ❌ **소스 추가만으로는 0건 채워진다.** 트러블슈팅 청크에서 코드 문자열 **0/11**, **대조군(actions 보유 13종)도 0/13** → `키패드 표시` 컬럼이 **구조적으로 미추출**. 실제 작업은 **한글 명칭↔코드 조인 + 표기 정규화**이고, 명칭 축은 **10/11 · 대조군 13/13** 으로 살아 있다. `ESt`('출력 순시 차단(비상정지)') 1건은 **수기** |
| **ⓑ S100 26건** | "셀 내 줄바꿈 분해 실패 (재추출 후보)" | ✅ **맞다, 그리고 OCR 대상이 아니다.** 코드 문자열 **21/26** 등장 · 결측과 보유가 **같은 페이지(416·417·419)에 혼재** → 페이지 이미지 문제가 아니라 **셀 분해 규칙 결함**. 유료 OCR 은 파서 수정 **잔여분에만** |

> ⚠ **판정에 양성 축이 함께 걸렸다.** iG5A 에서 "코드 0건"만 봤으면 *"11종이 트러블슈팅에 없다"* 로
> 잘못 읽었을 것이다. `actions` 가 **이미 있는** 13종도 똑같이 0건인 것을 확인하고서야
> *"스캐너가 아니라 코드 컬럼이 없다"* 로 바로잡혔다 (CLAUDE.md 부재검사 규칙의 조사판).

**그래서 ⓐ·ⓑ 는 같은 P31 이지만 기술적으로 다른 작업이고, 둘 다 `data/extract_error_codes.py` 를 건드린다 → 같은 스테이지에 병렬로 놓지 않는다.**
그리고 **P29(IE5)가 같은 기술 과제를 이미 분석해 뒀다** — *"원인·대책 표는 한글 명칭으로 인덱싱돼 있어 명칭↔코드 조인이 필요"* · *"'인버터 냉각 핀 과열'(본문) vs '냉각핀 과열'(표)"* 표기 흔들림. **P31-ⓐ 의 정규화 규칙은 P29 착수 시 그대로 재사용되는 자산**이다.

---

## 1. 범위 판정 — MVP 인가 백로그인가

| 축 | 판정 | 근거 |
|---|---|---|
| **A. `create_repair_record`** | ✅ 본 범위 | `00_MVP_SCOPE §확장 기능 9` 에 등재(🟡 부분) · P25 는 *"하기로 정한 일"* 절(D67) · 계약 자리 `kind:"repair"` 를 D85 가 확보 |
| **B. `actions` 결측 37건** | ✅ 본 범위 | `00_MVP_SCOPE §1` *"점검 절차는 RAG / 코드 정의는 룩업"* 의 **룩업 쪽 데이터 결손**이다. P31 은 백로그 승격이 아니라 **이미 만들기로 한 것의 미완**(`error_codes.actions NOT NULL` 인데 37건이 빈 배열) |
| **C. 프론트 노출** | ✅ 본 범위 | `00_MVP_SCOPE §인프라` *"UI 2종"* + Sprint 7 선례(확장 도구의 UI 노출 ⓓ). **사용자 명시 요청** |

**⛔ 승격하지 않는 것**: P32(부품 품번 — 4축 전부 닫혔고 사람 전화가 유일 경로) · P29(IE5) · P30(부재검사 앵커 — 단, 이번에 새로 쓰는 검사는 전부 앵커 규칙을 지킨다) · P2·P17(공급사 추천·MOQ 제안).

### 복무 시나리오 — 솔직하게 적는다

S1~S4 에 **직접** 복무하는 태스크는 축 B 뿐이다(`actions` 는 S1·S3 의 조치 안내와 S4 의 경계에 직결). 축 A 는 **S19**, 축 C 는 **S1+·S9·S10** 이다. 억지로 S1~S4 를 적으면 계획이 사실과 달라진다(sprint-8 §1 이 세운 규약을 그대로 따른다).

---

## 2. 블로커 · 사람 승인 게이트

| 게이트 | 무엇이 막히나 | 배치 |
|---|---|---|
| **G1 🔴 `actions` 37건 사람 검수** (D33 + safety-guardrail) | `error_codes.json` 병합·재적재 → `lookup_error_code` 의 `actions` 값 | **Stage 10(조건부)** 로 격리. Stage 1~9 는 **후보 파일**만 만들고 `error_codes` 는 **65행 불변**이 DoD |
| **G2 🔴 안전 문구 승인** (`SAFETY_BASELINE`·`QUALIFIED_WORKER_NOTE`, 기존 대기) | 없음 — 이번 범위와 무관 | 막지 않음 |
| **G3 `RESIDUAL_AT_LIFE_END=0.50`·`FLOOR=0.10` 가정 동의** (기존 대기) | 축 C 화면을 **막지 않는다.** 단 **미승인 가정임이 화면에 드러나야** 진행 가능(D65·D74) | 축 C 전 화면의 DoD 에 고지 검사 |
| **G4 `ANTHROPIC_API_KEY` + 평가 비용** | `--repeat 3` 기준선 재측정 | **Stage 10 이후.** 스프린트 안에서 지표 개선을 주장하지 않는다 |
| `related_parts`·`part_class`·기준내용연수 | ✅ 전부 해제됨(08-12·08-13) | — |

> **Stage 1~9 는 사람 대기가 0건이다.** G1 은 산출물(검수 패키지)을 만드는 것까지가 스프린트 범위이고, 승인 자체를 기다리지 않는다.

---

## 3. 먼저 등재해야 하는 결정 (D98~D101)

CLAUDE.md 규칙 — 설계와 다른 구현은 **D 를 먼저 추가**한다. 아래 4건은 기존 D 와 충돌하거나 계약을 넓히므로 **MQ-901 이 Stage 1 에서 등재**하고, 그 뒤 태스크가 구현한다.

| D | 내용 | 왜 필요한가 |
|---|---|---|
| **D98** | `create_repair_record` = **세 번째 쓰기 도구**. `db.repair_writer()` 전용 커넥션 · `repair_records` 에 **draft INSERT 만** · **`full` 프로파일 전용**(확장 8→**9종**, core 7 불변) · `performed_by`·`verified_by`·`signed_at`·`record_hash`·`state`·`session_id` 는 **파라미터가 아니다** · `part_class`·`expenditure_class` 는 **서버 산출**(LLM 이 등급·회계 판단을 지어낼 경로 차단) | D10 은 *"쓰기 도구는 `create_po_draft` 하나"*, `00_MVP_SCOPE` 는 *"쓰기 도구는 2종"* 이라고 적혀 있다. 3종이 되는 것은 **문서 정정이 아니라 결정** |
| **D99** | P31 회수분은 **후보 파일**(`data/extracted/error_codes_actions.candidate.json`)에 격리하고 **사람 승인 시에만 병합**한다. `error_codes.json._status` 를 초안으로 되돌리지 않는다. 검수 단위는 **전량 65건이 아니라 변경분 37건** | 실측 ④ — `_status` 유도 로직이 켜지면 **65행 → 0행**. 재승인 범위를 "전량"으로 잡으면 이미 승인된 65건을 다시 태우게 되고, 실제로 바뀌는 건 `actions` 뿐이다 |
| **D100** | `actions` 의 출처를 **`actions_manual_id`·`actions_page` 로 분리 보존**하고 `lookup_error_code` 출력에 `actions_source` 를 더한다. **`null` = "출처 미기록"** 이지 *"manual_page 와 같음"* 이 아니다 | iG5A 조치문은 **다른 PDF**(`ig5a-troubleshooting` p.22~29)에서 온다. 기존 `manual_page`(표준본 p.202~206)로 인용하면 **거짓 인용**이고, 이는 *"안전 문구는 매뉴얼 근거(페이지) 없이 생성 금지"* 를 페이지 층위에서 위반한다. `manual_eda.md:100` 이 이미 *"두 소스 병합 + 출처 페이지 각각 기록"* 이라고 적었는데 스키마가 안 따라갔다 |
| **D101** | 자산가치 4종(`assess_repair_value`·`get_maintenance_metrics`·`classify_part_criticality`·`classify_expenditure`)의 **산출 로직을 `data/maint_value.py` 로 옮긴다**(D73 공유 계층). MCP 도구는 얇은 위임만 남긴다. **REST 노출은 MCP 프로파일과 독립**이다(D73·`check_disposal_blockers` 선례) | 실측 ① — 안 옮기면 산식이 두 벌이 된다. `decisions.py:520` 이 그 대가를 이미 자백했고, **D65 추정치가 화면과 도구에서 갈리는 것**은 D65 가 막으려던 바로 그 실패다 |

> ⛔ **D 번호 선점 확인**: 착수 시 `rg -n "^\| D9[89]|^\| D10[01]" docs/10_DECISIONS.md` 가 0건이어야 한다. 선점돼 있으면 **번호를 밀지 말고 중단·보고**한다(D 번호는 문서 5곳이 참조하는 식별자).

---

## 4. Sprint 9 스테이지 계획

### Stage 1
| TASK | 제목 | 범위 | 선행 |
|---|---|---|---|
| MQ-901 | 결정 4건 등재 — D98(3번째 쓰기 도구)·D99(후보 파일 격리)·D100(`actions_source`)·D101(`data/maint_value.py`) | `docs/10_DECISIONS.md` | — |
| MQ-902 | **추출 품질 triage** — 계측 먼저 (InsuQ 3단 중 1단만, 네트워크·유료 OCR 호출 0) | `data/extract_triage.py`(신규) · `data/analysis/` | — |

### Stage 2
| TASK | 제목 | 범위 | 선행 |
|---|---|---|---|
| MQ-903 | 자산가치 4종 산출 로직 → `data/maint_value.py` 이동 + 도구는 얇은 위임 | `data/maint_value.py`(신규) · `mcp_server/tools/`(4파일) | MQ-901(D101) |
| MQ-904 | `data/seed.py` — `repair_records` 신원·상태 컬럼 + DDL CHECK 2종 · `error_codes` 출처 컬럼 2종 · 위치 INSERT 정정 · 시드 보정 · 자가검증 26→**29** | `data/seed.py` | MQ-901(D98·D100) |
| MQ-905 | **ⓐ iG5A 11건** — 트러블슈팅 PDF 소스 추가 + 명칭↔코드 조인 → **후보 파일** | `data/extract_error_codes.py` · `data/extracted/` | MQ-902, MQ-901(D99·D100) |

### Stage 3
| TASK | 제목 | 범위 | 선행 |
|---|---|---|---|
| MQ-906 | **`create_repair_record`** — 도구 + `db.repair_writer()` + `server.py` 등록 + `04 §16` 신설 | `mcp_server/` · `docs/04_MCP_TOOLS.md` | MQ-904, MQ-903 |
| MQ-907 | **ⓑ S100 26건** — 셀 내 줄바꿈 분해 실패 수정 → 후보 파일 append | `data/extract_error_codes.py` | MQ-905 |
| MQ-908 | 축 C REST 5종 — `services/maint_value.py` + `routers/maint_value.py` | `backend/services/` · `backend/routers/` · `backend/main.py` | MQ-903 |

### Stage 4
| TASK | 제목 | 범위 | 선행 |
|---|---|---|---|
| MQ-909 | 수리 증빙 REST — 제출·서명·반려 + `record_hash` 산정 + 통합 큐 배선 | `backend/services/repairs.py` · `backend/routers/repairs.py` · `backend/services/approvals.py` · `main.py` | MQ-906 |
| MQ-910 | `lookup_error_code` 에 `actions_source` 출력 (계약 자리 — 현재 전건 `null`) | `mcp_server/tools/lookup_error_code.py` | MQ-901(D100), MQ-904 |
| MQ-911 | **사람 검수 패키지 생성** — 37건 원문 대조표 + 안전 문구 별도 절 + TODO 등재 | `data/analysis/actions_review.md` · `TODO_직접할일.md` | MQ-905, MQ-907 |

### Stage 5
| TASK | 제목 | 범위 | 선행 |
|---|---|---|---|
| MQ-912 | 프론트 공통 배관 — 신규 6엔드포인트 타입·클라이언트 + `repair` 어휘 매퍼 | `frontend/lib/api.ts` · `types.ts` · `mappers.tsx` | MQ-908, MQ-909 |
| MQ-913 | 회귀 — `write_tool_contract` 확장 · **신규 `spikes/repair_flow_contract.py`** · `approvals_contract ③` 뒤집기 · `tools_profile_contract` 9종 · `lookup_contract` | `spikes/` | MQ-909, MQ-910 |

### Stage 6
| TASK | 제목 | 범위 | 선행 |
|---|---|---|---|
| MQ-914 | **화면 ①·우선순위 1·3·4ⓑ·5** — 수리가치 판단 `/technician/asset/[assetId]/value` + 부품 드로어 + 지출 카드 + **지표 보조 패널** | `frontend/app/(console)/technician/asset/[assetId]/value/` · `frontend/components/asset/` | MQ-912 |
| MQ-915 | **승인 큐 `kind:"repair"` 상세** — 서명·반려 바 | `frontend/components/queue/` · `screens/ApprovalQueueScreen.tsx` | MQ-912 |

### Stage 7
| TASK | 제목 | 범위 | 선행 |
|---|---|---|---|
| MQ-916 | **화면 ②③·우선순위 2·4ⓐ** — 근거 번들 `/technician/asset/[assetId]/evidence` + 지출 분류 독립 페이지 `/technician/expenditure` | `frontend/app/(console)/technician/` · `components/asset/` | MQ-914 |

### Stage 8
| TASK | 제목 | 범위 | 선행 |
|---|---|---|---|
| MQ-917 | `spikes/ui_honesty_contract.py` 확장 — 추정치 고지 · `insufficient_data` 오독 방지 · 하위 도구 실패 전파 · `HOLD` 정상 판정 | `spikes/ui_honesty_contract.py` · `frontend/lib/__checks__/` | MQ-914, MQ-915, MQ-916 |

### Stage 9
| TASK | 제목 | 범위 | 선행 |
|---|---|---|---|
| MQ-918 | 개수·상태 전파 (문서 12곳) + 회귀 기준선 실측 기입 | `docs/**` · `CLAUDE.md` · `README.md` | MQ-913, MQ-917 |

### Stage 10 — 🔴 **사람 승인(G1) 후에만 착수. 스프린트 안에 못 끝날 수 있다**
| TASK | 제목 | 범위 | 선행 |
|---|---|---|---|
| MQ-919 | 후보 → `error_codes.json` 병합 + 재적재 + 검사 ㉚ + 인용 무결성 | `data/extracted/` · `data/seed.py` | **G1 승인**, MQ-911, MQ-918 |

```
MQ-901 ─┬─► MQ-903 ─┬─► MQ-906 ─► MQ-909 ─┬─► MQ-912 ─┬─► MQ-914 ─► MQ-916 ─┐
        │           └─► MQ-908 ───────────┘           └─► MQ-915 ───────────┼─► MQ-917 ─► MQ-918 ─► [G1] ─► MQ-919
        ├─► MQ-904 ─┬─► MQ-906                         MQ-913 ──────────────┘
        │           └─► MQ-910 ─► MQ-913
MQ-902 ─► MQ-905 ─► MQ-907 ─► MQ-911 ───────────────────────────────────────► [G1]
```

### 스테이지 구성 근거

- **Stage 1 — 왜 D 등재가 맨 앞인가.** D98 은 `00_MVP_SCOPE:96`(*"쓰기 도구는 2종이다"*)·D10 과 **정면으로 다른 구현**을 하겠다는 선언이고, D100 은 `04 §1` 계약을 넓힌다. 코드를 먼저 짜면 CLAUDE.md 규칙 위반이다. MQ-902 를 같은 스테이지에 두는 이유는 **아무것에도 선행하지 않으면서 축 B 전체의 선행**이기 때문이다 — 그리고 **triage 는 파서를 고치기 전에 돌아야 한다.** 나중에 돌리면 "좋아졌다"의 기준선이 이미 오염돼 있다.
- **Stage 2 의 3태스크는 파일 교집합 0.** `data/maint_value.py`+`mcp_server/tools/*` / `data/seed.py` / `data/extract_error_codes.py`. 셋 다 `data/` 아래지만 **같은 파일이 하나도 없다.**
- **MQ-904 와 MQ-919 를 8스테이지 떼어 놓은 이유.** 둘 다 `data/seed.py` 다. 더 중요한 건 **검증 단위가 다르다**는 것 — MQ-904 는 *"스키마가 서명 없는 확정을 거부하는가"*(데이터 0행에서도 참), MQ-919 는 *"승인된 데이터가 그 스키마 위에서 정합한가"*. 하나로 묶으면 **"시드가 통과했다"가 "CHECK 가 작동한다"의 증거로 오해된다**(sprint-8 §4 가 세운 논거 그대로).
- **MQ-905 → MQ-907 을 나눈 이유.** 같은 파일(`extract_error_codes.py`)이라 **병렬 불가**다. 순서는 ⓐ 먼저 — ⓐ 는 **소스 추가**(구조적 부재)이고 ⓑ 는 **파서 수정**(분해 실패)이라, ⓐ 를 먼저 해야 ⓑ 의 회귀 기준(*"기존 성공분 15건이 한 글자도 안 변한다"*)에 iG5A 쪽 잡음이 섞이지 않는다.
- **MQ-908 과 MQ-909 를 나눈 이유.** 둘 다 `backend/main.py` 의 `include_router` 를 건드린다 → **같은 스테이지 금지.**
- **MQ-912 가 프론트 3태스크의 단일 관문인 이유.** `lib/api.ts`·`mappers.tsx` 는 화면 3개가 전부 손대는 파일이다. 화면 태스크와 같은 스테이지에 두면 **병렬 실행이 서로를 덮어쓴다.** 배관을 먼저 한 스테이지에 격리한다.
- **MQ-913(스파이크)을 구현과 분리한 이유.** MQ-906·909·910 을 **동시에 관통**한다. 셋 중 하나에 붙이면 자기 코드를 자기가 검증한다(sprint-7·8 이 쓴 논거).
- **MQ-917 이 화면 3개 뒤인 이유.** `ui_honesty_contract` 의 L2 스캔은 `components/asset/*.tsx` **글롭**이라 새 컴포넌트가 자동으로 들어온다 — 화면이 다 나온 뒤에 돌려야 스캔 대상 하한(`L2_FILES_FLOOR`)을 실측으로 올릴 수 있다.
- **MQ-918 이 맨 뒤인 이유.** 회귀 건수는 **러너 출력이 기준**이다. 돌려 보기 전에 적으면 그 줄이 거짓이 되고, CLAUDE.md 는 *"직전 실행보다 줄었다면 테스트가 사라진 것"* 을 그 숫자로 판정한다.

### 공유 파일 단일 소유자 격리

| 파일 | 유일 소유 | 스테이지 |
|---|---|---|
| `docs/10_DECISIONS.md`(신규 D 4행) | MQ-901 | 1 |
| `docs/10_DECISIONS.md`(D10·D69·D85 각주) | **MQ-918** | 9 |
| `data/seed.py`(DDL·시드·verify) | MQ-904 | 2 |
| `data/seed.py`(`load_error_codes` 병합분·검사 ㉚) | **MQ-919** | 10 |
| `data/extract_error_codes.py` | MQ-905 → MQ-907 (순차) | 2 → 3 |
| `mcp_server/tools/{assess_repair_value,get_maintenance_metrics,classify_part_criticality,classify_expenditure}.py` | MQ-903 | 2 |
| `mcp_server/server.py` · `mcp_server/db.py` | MQ-906 | 3 |
| `mcp_server/tools/lookup_error_code.py` | MQ-910 | 4 |
| `backend/main.py` | MQ-908(3) → MQ-909(4) | 순차 |
| `backend/services/approvals.py` | MQ-909 | 4 |
| `frontend/lib/{api,types}.ts` · `mappers.tsx` | MQ-912 | 5 |
| `frontend/components/asset/*`(신규 4) | MQ-914 | 6 |
| `frontend/components/asset/*`(신규 2) · `/evidence`·`/expenditure` 라우트 | MQ-916 | 7 |
| `frontend/components/queue/*` · `ApprovalQueueScreen.tsx` | MQ-915 | 6 |
| `spikes/*`(신규 1 + 수정 4) | MQ-913 | 5 |
| `spikes/ui_honesty_contract.py` | MQ-917 | 8 |

---

## 5. 축 C — 무엇을 노출하고 무엇을 왜 미루는가

사용자 확정 우선순위·형태를 그대로 따른다. **전부 노출한다**(5종). 다만 **형태로 위험을 가른다.**

| # | 도구 | 형태 | 근거 |
|---|---|---|---|
| 1 | `assess_repair_value` | **전용 화면 중심**(`/technician/asset/[id]/value`) | `04 §13` — **하위 도구 실패를 삼키지 않는다.** 이 도구가 3·5 를 이미 호출하므로 **한 화면에 세 도구 값이 자연스럽게 모인다.** 화면 3개가 아니라 **1을 중심으로 3·5를 붙이는 구조**가 계약과 일치 |
| 2 | `build_evidence_bundle` | **근거 화면**(`/technician/asset/[id]/evidence`) | 백엔드 재현부(`rebuild_bundle`)가 **이미 있다** → 신규 중복 0. ⚠ 번들 해시가 고정하는 것은 **5키뿐**이고 렌더는 보호 범위 밖(`12 §8`) → `hash_fixed:false` 를 화면이 말해야 한다 |
| 3 | `classify_part_criticality` | **전용 페이지 아님 — 부품 행 클릭 시 드로어** | 단독으로는 한 줄 판정이라 페이지가 과하다. 3지 판단의 **입력**이므로 그 옆에서 펼쳐지는 게 맞다 |
| 4 | `classify_expenditure` | **ⓐ 독립 페이지 + ⓑ 3지 판단 화면의 작은 카드** | ⓑ 는 `part_class` 를 **화면이 이미 갖고 있어** 입력 의존이 자연스럽다. **ⓐ 독립 페이지에서는 `part_class` 를 사용자가 고르지 않는다** — 부품을 고르면 서버가 `classify_part_criticality` 로 채운다(도구 설명의 *"추측하지 말고 먼저 확인해 넣을 것"* 을 UI 가 지킨다) |
| 5 | `get_maintenance_metrics` | **독립 대시보드 아님 — 근거 옆 보조 패널** | 9자산 실측: **핵심 4지표 null 15/36(42%) · `mtbf_trend` insufficient_data 7/9.** 격자 대시보드는 **빈칸을 "문제 없음"으로 읽히게 만든다.** 도구 계약이 직접 경고하는 오독이다 |

**D64 리스크의 정확한 위치 (명세에 이 구분을 적는다):** 도구는 OEE 를 **계산도 출력도 하지 않고** `not_considered` 에 금지 사유만 남긴다 — 즉 축 C 의 위험은 *"OEE 를 계산하는 것"* 이 **아니라** **MTBF·가용도·예방보전비율을 성능 점수처럼 나열해 사실상 OEE 대시보드가 되는 것**이다. 5번의 배치가 그 방어다.

### 참고 — `get_maintenance_metrics` 9자산 실측 (2026-08-14)

```
asset             MTBF              추세   MTTR   가용도   예방비     수리비  반복
AST-L1-CONV        7.3  insufficient_data     —      —      —         0  False
AST-L2-CLNT        5.7  insufficient_data     —      —      —         0  False
AST-L2-SPDL       90.0             stable   6.8   1.00   0.67  18000000  False
AST-L3-CONV        5.5  insufficient_data   4.8   0.97   0.50  14000000  True
AST-L3-EXFAN      13.4  insufficient_data     —      —      —         0  False
AST-L3-LIFT        9.4  insufficient_data     —      —      —         0  False
AST-L4-CONV        7.5  insufficient_data     —      —      —         0  False
AST-L4-DUST        8.2  insufficient_data   5.3   0.97   0.33   9000000  False
AST-L4-WRAP       75.6          declining   6.8   1.00   0.33  12000000  False

핵심 4지표 null: 15/36 (42%) · mtbf_trend insufficient_data: 7/9
```

`repair_records` **12행 중 서명 11 · `downtime_hours` 전건 존재** → 축 C 지표 화면은 **축 A 없이도 값이 나온다**(하드 선행 아님).

---

## 6. 태스크별 상세 구현 명세

---

#### MQ-901 — 결정 4건 등재 (D98·D99·D100·D101)

- **복무 시나리오**: 인프라 (S19·S1+ 의 선행 규약)
- **변경 파일**: `docs/10_DECISIONS.md` (수정 — 표 끝에 4행 추가)
- **인터페이스**: 기존 표 형식 `| D98 | 결정 | 대안 | 채택 이유 |`. **`⚠설계 확정·미구현` 마커를 붙이지 않는다** — 이번 스프린트가 구현한다.
- **핵심 로직**: §3 의 4행을 쓴다. 각 행에 **반드시 포함할 실측 인용**:
  - D98 → `mcp_server/db.py:75~93`(테이블별 TEMP TRIGGER 분리) · `04 §15` 의 *"`draft_writer()` 를 재사용하지 않는다"* · D88 게이트는 `tools > 7` 이므로 **core 7 불변이면 무영향**.
  - D99 → `data/seed.py:1687 error_codes_gate()` · `extract_error_codes.py:438 ig5a_approval_status()` · **"65 → 0 붕괴"** 를 재현 경로로 적는다. 재승인 범위는 **변경분 37건**.
  - D100 → `manual_eda.md:100`(*"두 소스 병합 + 출처 페이지 각각 기록"*) · `manifest.json` 의 `ig5a-troubleshooting`(`print_page_offset: 0`) · **`null` 의 뜻은 "출처 미기록"** 임을 못박는다.
  - D101 → `backend/services/decisions.py:520`(*"산식이 두 벌 존재한다"*) · `data/ownership.py:764 verify(con, …)` 시그니처(커넥션은 호출자가 연다) · **REST 노출은 MCP 프로파일과 독립**(D73, `check_disposal_blockers` 선례).
- **엣지 케이스**: D 번호 선점 시 **밀지 말고 중단** · 표 셀의 `|` 는 `\|` 이스케이프 · **D102 를 만들지 않는다**(4건으로 충분).
- **지켜야 할 결정**: D10(권한 자체를 주지 않는다는 태도 유지) · D33(사람 승인 게이트) · D69·D88(core 기준선) · D73(공유 데이터 계층) · D26·D32(인용 페이지).
- **회귀**: 없음(문서). D 범위 표기 갱신은 **MQ-918 소유** — 여기서 하지 않는다.
- **DoD**: `rg -n "^\| D(98|99|100|101) " docs/10_DECISIONS.md` → **4행** · `rg -c "D102" docs/10_DECISIONS.md` → 0 · D99 셀에 `error_codes_gate` 와 `65` 가 **둘 다** 인용돼 있다 · D101 셀에 `decisions.py:520` 이 인용돼 있다.

---

#### MQ-902 — 추출 품질 triage (계측 먼저)

- **복무 시나리오**: S1·S3 (조치 안내의 데이터 품질) — 인프라 성격
- **변경 파일**: `data/extract_triage.py`(신규) · `data/analysis/extract_triage.md`(신규) · `data/extracted/extract_triage.json`(신규 산출물)
- **인터페이스**:

```python
SIGNALS: Final[tuple[str, ...]] = ("field_missing", "length_outlier", "table_collapse", "code_absent")
LABELS:  Final[tuple[str, ...]] = ("SOURCE_MISSING", "CELL_SPLIT", "RE_OCR_CANDIDATE", "OK")
OCR_WON_PER_PAGE: Final[int] = 45          # InsuQ 실측 단가. **호출은 하지 않는다**

def scan(model: str, pages: Iterable[int]) -> list[PageReport]: ...
def label(report: PageReport) -> str: ...          # LABELS 중 하나
def main() -> int: ...                             # md·json 산출, 종료코드 0
```

- **핵심 로직**:
  1. `error_codes.json` 을 읽어 (model, code) 별 `causes`·`actions` 결측을 센다 → **`field_missing`**.
  2. 각 코드의 `manual_page` 원문을 `pdfplumber` 로 열어 **코드 문자열·한글 명칭이 그 페이지에 존재하는가**를 본다 → **`code_absent`**(양성 축). *이 신호 하나가 **구조적 미추출(ⓐ)** 과 **셀 분해 실패(ⓑ)** 를 가른다.*
  3. InsuQ 신호 2종만 가져온다 — **길이 이상치**·**표 구조 붕괴**(행별 셀 수 분산). ⛔ **문자 깨짐 계열은 넣지 않는다** — InsuQ 코퍼스에서 전부 0건이었고, `ㆍ`(아래아)가 *"전화ㆍ우편ㆍ인터넷"* 처럼 **정상 나열 구분자**인데 고립 자모로 잡혀 전 코퍼스 오탐이 났다.
  4. 라벨링: 같은 페이지에 **성공·실패가 혼재** → `CELL_SPLIT` / 코드 자체가 그 문서에 없음 → `SOURCE_MISSING` / 둘 다 아님 → `RE_OCR_CANDIDATE`.
  5. `RE_OCR_CANDIDATE` 페이지 수 × 45원을 **비용 견적으로만** 인쇄한다.
  6. **⛔ 네트워크 호출 0.** `import httpx|requests|openai` 금지. InsuQ 3단 중 **1단(선별)만** 옮긴다.
- **엣지 케이스**: PDF 없음 → `data/raw/` 는 git 밖이므로 **친절히 중단**(`sys.exit` + 경로 안내), 예외 트레이스로 죽지 않는다 · 페이지 인덱스 초과 → 그 페이지만 `skipped` 로 기록하고 계속 · `error_codes.json` 이 없으면 *"M1 미완료"* 로 중단.
- **지켜야 할 결정**: D24(pdfplumber 텍스트 규칙 파싱) · D26(물리 페이지) · D19(manifest sha256 대조 — `check_manifest()` 재사용) · **절대규칙 5**(`data/raw/` 읽기 전용).
- **회귀 스위트**: 신규 스파이크를 만들지 않는다(**분석 도구**이고 제품 경로가 아니다). 대신 **산출 JSON 을 MQ-905·907 의 회귀 기대값으로 고정**한다.
- **DoD**:
  - `uv run python data/extract_triage.py` → `SOURCE_MISSING`·`CELL_SPLIT`·`RE_OCR_CANDIDATE` 별 **페이지 목록**과 코드 수 출력.
  - **판정 기대값(사전 실측과 일치해야 한다)**: iG5A `actions` 결측 **11** · S100 **26** · `causes` 결측 **0** · `_unparsed` **0**.
  - iG5A 결측분이 **`SOURCE_MISSING`** 으로, S100 결측분이 **`CELL_SPLIT`** 으로 라벨링된다 → *이 라벨이 "유료 OCR 이 필요 없다"의 기계적 근거다.*
  - `rg -n "httpx|requests|openai|Elice|elice" data/extract_triage.py` → **0건**.
  - `data/extracted/error_codes.json` **해시 불변** · `SELECT count(*) FROM error_codes` = **65**.

---

#### MQ-903 — 자산가치 4종 산출 로직 → `data/maint_value.py` (D101)

- **복무 시나리오**: S1+ (축 C 전체의 선행)
- **변경 파일**: `data/maint_value.py`(신규) · `mcp_server/tools/{get_maintenance_metrics,classify_part_criticality,classify_expenditure,assess_repair_value}.py`(수정 — **위임만 남긴다**)
- **인터페이스** (`data/ownership.py:764` 와 **같은 규약** — 커넥션은 호출자가 읽기 전용으로 연다):

```python
def maintenance_metrics(con, *, asset_id: str, window_months: int | None = None) -> dict: ...
def part_criticality(con, *, part_no: str) -> dict: ...
def expenditure(con, *, part_class: str, repair_scope: str, amount: int | str) -> dict: ...
def repair_value(con, *, equipment_id: str, failed_part: str,
                 repair_cost: int | str, repair_scope: str = "RESTORE") -> dict: ...
```

- **핵심 로직**:
  1. 본문을 **그대로** 옮긴다. **출력 dict 를 한 글자도 바꾸지 않는다** — 키 순서·`disclaimer` 문구·`not_considered[]`·`mtbf_basis`·`excluded[]` 전부 동일.
  2. MCP 도구 파일에는 **`DESCRIPTION` 상수와 시그니처만** 남기고 `with read_only() as con: return maint_value.xxx(con, …)` 로 위임한다. **`DESCRIPTION` 은 도구 파일이 정본**이다(`04 §서두`) — `data/` 로 옮기지 않는다.
  3. 필수 파라미터 기본값 금지(**D80**)를 도구 시그니처에서 유지한다. `data/` 쪽 함수는 키워드 전용.
  4. 하위 도구 호출 관계(`repair_value` → `part_criticality`·`maintenance_metrics`)는 **모듈 내부 함수 호출**로 바뀐다. **실패 전파 규약은 그대로** — `status != "ok"` 면 그 `status`·`reason` 을 **그대로** 올린다(재포장 금지).
  5. `data/` 는 `mcp_server` 를 import 하지 않는다(역방향 의존 금지).
- **엣지 케이스**: `ASSET_FACT_COLUMNS`·`build_facts` 는 이미 `data/rules/engine.py` 에 있으므로 import 경로가 `..` 에서 `data.rules.engine` 으로 **평평해진다** — 순환 import 주의(`data.rules.engine` 은 `data.maint_value` 를 몰라야 한다) · `REPEAT_THRESHOLD`·`REPEAT_WINDOW_DAYS` 는 **`get_error_history` 가 정본**이므로 도구에서 읽어 넘기거나 `data/` 로 함께 옮긴다(둘 중 하나를 택하고 주석으로 근거를 남긴다 — **두 벌은 만들지 않는다**, D2·D29).
- **지켜야 할 결정**: D101(위치) · D73(공유 계층) · D15(상호 import 금지) · D9(예외 대신 status) · D80(기본값 없음) · D65·D70·D74(고지 문구 불변) · D64(OEE 계산·출력 금지 유지).
- **회귀 스위트**: **새 검사를 추가하지 않는다.** `spikes/asset_tools_contract.py` **49건**과 `tools_profile_contract.py` **7건**이 **한 건도 수정 없이** 그대로 통과하는 것이 이 태스크의 증명이다. ⚠ **이 두 스위트를 고쳐야 한다면 그 자체가 실패**다(리팩터가 계약을 바꿨다는 뜻).
- **DoD**:
  - `uv run python spikes/asset_tools_contract.py` → **49/49** (수정 0줄).
  - `uv run python spikes/tools_profile_contract.py` → **7/7**.
  - `rg -n "^(import|from) mcp_server" data/maint_value.py` → **0건**.
  - 이동 전후 출력 동일성: 4종을 각 3케이스씩 호출해 `json.dumps(…, sort_keys=True)` 가 **바이트 동일**(임시 스크립트로 확인, 커밋하지 않음).
  - `uv run ruff check data mcp_server`.

---

#### MQ-904 — `data/seed.py` DDL·시드·자가검증 (26 → **29**)

- **복무 시나리오**: S19(수리 증빙) · S1·S3(에러코드 출처)
- **변경 파일**: `data/seed.py` — `SCHEMA` · `REPAIR_RECORDS` 시드 · `load_error_codes()` · `verify()` · 모듈 docstring
- **인터페이스 (DDL 확정형)**:

```sql
CREATE TABLE repair_records (
  repair_id TEXT PRIMARY KEY,
  ...                                    -- 기존 컬럼 전부 그대로
  state TEXT NOT NULL DEFAULT 'draft',
  -- ↓ 신설 (D98). 발주·처분과 같은 신원 규약 (D23·D37·D21)
  requested_by TEXT REFERENCES users,    -- = 수리를 올린 사람. 도구 파라미터 아님
  session_id   TEXT,                     -- 화면의 "실행 로그 보기" 링크 키 (D21)
  created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
  note         TEXT,                     -- 반려 사유·서명 메모 (D38 — 반려는 사유 필수)
  CHECK (work_type IN ('PLANNED','UNPLANNED')),
  CHECK (state IN ('draft','pending','signed','rejected')),          -- ★ 신설
  -- ★ "서명 없는 확정 0건" 을 스키마가 잠근다 (decisions 의 DDL CHECK 2종과 같은 형태)
  -- ⚠ record_hash 는 조건에서 뺀다 — 아래 핵심 로직 3-㉘ 참조 (시드 11건이 해시 규약 이전 데이터)
  CHECK (state <> 'signed' OR (signed_at IS NOT NULL AND verified_by IS NOT NULL)),
  ...
);

CREATE TABLE error_codes (
  ...
  manual_page INTEGER NOT NULL,
  -- ↓ 신설 (D100). NULL = **출처 미기록**. "manual_page 와 같다"는 뜻이 아니다
  actions_manual_id TEXT,        -- manifest.json 의 id ('ig5a-manual'|'ig5a-troubleshooting'|'s100-manual')
  actions_page      INTEGER,
  CHECK ((actions_manual_id IS NULL) = (actions_page IS NULL)),      -- 짝이거나 둘 다 NULL
  ...
);
```

- **핵심 로직**:
  1. `load_error_codes()` 의 **위치 INSERT 를 컬럼 명시로 바꾼다** (실측 ③ — `VALUES (?,?,?,?,?,?,?,?,?)` 는 컬럼이 늘면 조용히 어긋난다). 새 두 키는 JSON 에 있으면 싣고 없으면 `None`. **`error_codes.json` 은 이 태스크가 건드리지 않는다.**
  2. `REPAIR_RECORDS` 12행에 `requested_by='tech-01'`·`created_at`(실행일 기준 **상대일** — ⛔ `--today` 로 핀 금지)·`session_id=None`·`note=None` 을 채운다. `state` 는 **기존 그대로** `'signed'` 11 / `'draft'` 1.
  3. 자가검증 3건 추가 (26 → **29**). **전부 양성 축 + 음성 축 동시**(CLAUDE.md 부재검사 규칙):
     - **㉗** `repair_records` 신원 — `requested_by` 전건 `users` FK 유효(양성: 12행) **and** `state` 어휘가 4종 밖 0건.
     - **㉘** *"서명 없는 확정 0건"* — 🔴 **명세 도중 발견된 모순**: `state='signed'` 인 시드 11행은 **`record_hash` 가 전량 NULL** 이다(`05 §16`). 원래 제안한 `CHECK (… AND record_hash IS NOT NULL)` 은 **자기 시드를 거부한다.** → **채택: CHECK 에서 `record_hash IS NOT NULL` 을 뺀다.** 즉 `CHECK (state <> 'signed' OR (signed_at IS NOT NULL AND verified_by IS NOT NULL))` 이고, `record_hash` 는 **MQ-909 가 새로 서명한 건에만** 생긴다. 그 사실을 DDL 주석과 `05 §16` 에 *"시드는 해시 규약 이전 데이터다"* 로 남긴다. 검사는 **음성 주입**으로 짠다 — 임시 트랜잭션에서 `state='signed', signed_at=NULL` INSERT 를 시도해 **`IntegrityError` 가 나는지** 확인하고 롤백(양성 축 = 정상 행 INSERT 는 성공).
     - **㉙** `error_codes` 출처 컬럼 — 짝 CHECK 가 살아 있고(음성 주입 1건) **현재 전건 NULL 인 것이 정상**임을 detail 에 **실측값으로** 인쇄(`actions_source 기록 0 / 65` — *"없다"를 하드코딩 문구로 적지 않는다*).
  4. 모듈 docstring 에 **`--with-error-codes` 함정**과 **`--today` 금지**를 이미 있는 문장 그대로 유지한다.
- **엣지 케이스**: `PRAGMA foreign_keys=ON` 이 꺼져 있으면 `requested_by` FK 가 조용히 사라진다(`_configure` 확인) · `--with-error-codes` 없이 실행하면 `error_codes` 0행이라 `repair_records` 의 `(model,error_code)` 는 둘 다 NULL(**기존 처리 유지**) · 기존 검사 번호(①~㉖)를 **재배치하지 않는다**.
- **지켜야 할 결정**: D98·D100 · D23·D37(신원은 서버 주입) · D21(session_id) · D38(반려 사유) · D41(users FK) · D62(NULL 3상태 태도) · D13·D33(복합 FK).
- **회귀 스위트**: `data/seed.py` 자가검증 **㉗㉘㉙ 신설**(26→29). 기존 스위트는 **무증감이 정상**.
- **DoD**:
  - `uv run python data/seed.py --with-error-codes` → **29건 전부 통과** · `SELECT count(*) FROM error_codes` = **65**.
  - `PRAGMA table_info(repair_records)` → `requested_by`·`session_id`·`created_at`·`note` 존재 · `PRAGMA table_info(error_codes)` → `actions_manual_id`·`actions_page` 존재.
  - **회귀 무증감**: `spikes/{approvals_contract,asset_tools_contract,ownership_api_contract,lookup_contract,api_contract}.py` **수정 없이** 전건 통과.
  - `uv run --with pytest python -m pytest data/rules/test_rules.py -q` → **46건**.

---

#### MQ-905 — ⓐ iG5A 11건: 트러블슈팅 소스 추가 + 명칭 조인 (**후보 파일**)

- **복무 시나리오**: S1·S3 (점검 조치 안내)
- **변경 파일**: `data/extract_error_codes.py`(수정) · `data/extracted/ig5a_action_map.json`(신규) · `data/extracted/error_codes_actions.candidate.json`(신규 산출물)
- **인터페이스**:

```python
TROUBLESHOOTING_PAGES = range(22, 30)      # 물리 p.22~29 (D26)

def norm_name(s: str) -> str: ...          # 공백·괄호·접두어·조사 정규화 (P29 가 경고한 표기 흔들림)
def parse_ig5a_troubleshooting(pdf_path: Path) -> dict[str, RemedyBlock]: ...
def join_actions(entries: list[dict], remedies: dict[str, RemedyBlock],
                 action_map: dict) -> tuple[list[dict], list[str]]:
    """→ (candidates, pending_review). 못 고르면 **버린다**."""
```

```jsonc
// error_codes_actions.candidate.json
{ "_status": "검수 대기 — data/analysis/actions_review.md (D99)",
  "_generated_at": "…", "_source_gate": "사람 승인 전 error_codes.json 병합 금지",
  "entries": [{
    "model": "iG5A", "code": "OHT",
    "actions": ["…원문 그대로…"],
    "actions_manual_id": "ig5a-troubleshooting", "actions_page": 24,
    "join_key": "인버터냉각핀과열", "confidence": "high",
    "evidence_excerpt": "…해당 페이지 원문 발췌…"
  }],
  "_pending_review": ["ESt: 트러블슈팅 문서에 대응 항목 없음"] }
```

- **핵심 로직**:
  1. `check_manifest()` 로 `ig5a-troubleshooting` 해시를 대조한다(D19). **이미 manifest 에 등록·해시 기록돼 있다** — 새로 추가할 것이 없다.
  2. p.22~29 의 원인/대책 표를 **한글 명칭 키**로 인덱싱한다. 조인은 `norm_name()` 후 수행 — *"인버터 냉각 핀 과열"* vs *"냉각핀 과열"* 처럼 **띄어쓰기·접두어가 다르다**(P29 실측).
  3. **못 고르면 비운다.** 기존 `span_key()` 의 태도를 그대로 쓴다 — *"가장 가까운 항목으로 흘려보내면 남의 조치문이 붙는다(실측: Out Phase Open 이 이웃 6건 흡수). **엉뚱한 에러코드에 붙은 조치는 누락보다 나쁘다.**"*
  4. 🔴 **생성 금지.** `actions` 문자열은 **PDF 추출 원문 그대로**다. 요약·재작성·문장 다듬기 전부 금지 — 이건 안전 절차 서술이고 safety-guardrail 규칙이 직접 걸린다. **자동 대조 검사를 스크립트 안에 내장한다**: 각 action 문자열이 정규화 후 해당 페이지 텍스트의 **부분 문자열**로 존재하지 않으면 그 항목을 **버리고 `_pending_review` 에 사유를 남긴다.**
  5. 산출은 **후보 파일에만** 쓴다. ⛔ **`error_codes.json` 을 열지도 쓰지도 않는다**(D99 — 실측 ④).
  6. 자동 조인 실패분(**실측: `ESt`**)은 `ig5a_action_map.json` 에 **사람 기입 자리**로 남기고 `_pending_review` 에 넣는다. **"11건 자동"이 아니라 "10 자동 + 1 수기"** 로 적는다 — 전자로 적으면 실행 때 조용히 어긋난다.
- **엣지 케이스**: 같은 명칭이 두 코드에 매칭 → **둘 다 버린다**(모호는 오배치보다 낫다) · 조치 셀이 비었는데 원인 셀만 있음 → `actions` 는 빈 배열 유지(`causes` 를 조치로 승격 금지) · 표준본에 **이미 actions 가 있는 13건**은 **건드리지 않는다**(후보 대상은 결측 11건뿐) · PDF 없음 → 친절히 중단.
- **지켜야 할 결정**: D99(후보 격리) · D100(출처 기록) · D24(추출 전략) · D26(물리 페이지) · D19(manifest 해시) · **절대규칙 3**(안전 문구는 매뉴얼 근거 없이 생성 금지) · D6·D13(model enum·복합키).
- **회귀 스위트**: `spikes/citation_render.py`·`lookup_contract.py` **무증감**이 정상(값이 아직 DB 에 없다).
- **DoD**:
  - `uv run python data/extract_error_codes.py` → 후보 파일 생성, **자동 채움 건수·`_pending_review` 건수를 stdout 에 실측 인쇄**(지어내지 않는다).
  - **원문 대조 전건 통과** — 대조 실패 항목이 후보 파일에 **0건**.
  - `data/extracted/error_codes.json` **sha256 불변** (착수 전후 대조) · `SELECT count(*) FROM error_codes` = **65**.
  - `SELECT count(*) FROM error_codes WHERE json_array_length(actions)=0` = **37** (아직 안 변한 것이 정상).
  - 후보 전건에 `actions_manual_id`·`actions_page` 가 **채워져 있다**(D100).

---

#### MQ-906 — `create_repair_record` (세 번째 쓰기 도구, D98)

- **복무 시나리오**: **S19**
- **변경 파일**: `mcp_server/tools/create_repair_record.py`(신규) · `mcp_server/db.py`(수정 — `repair_writer()`) · `mcp_server/server.py`(수정 — 확장 등록 9번째) · `docs/04_MCP_TOOLS.md`(§16 신설)
- **인터페이스**:

```jsonc
// input — 전부 **기본값 없음**(D80). optional 은 downtime_hours·model·error_code 뿐
{
  "equipment_id": "INV-L3-01",          // ★ required
  "work_type": "UNPLANNED",             // ★ required. PLANNED|UNPLANNED — 미기재 거부 (12 §7)
  "repair_scope": "RESTORE",            // ★ required. RESTORE|UPGRADE|OVERHAUL|REPLACE_UNIT
  "cost": 8500000,                      // ★ required. > 0
  "parts": [{"part_no": "FAN-IG5-01", "serial": "SN-88214", "qty": 2}],  // ★ required, 1건 이상
  "downtime_hours": 6.5,                // optional — MTTR 의 유일한 원천
  "model": "iG5A", "error_code": "OHT"  // optional, **짝** (D13·D33)
}
// output
{ "status": "ok", "repair_id": "RPR-2413", "state": "draft",
  "equipment_id": "INV-L3-01", "work_type": "UNPLANNED",
  "part_class": "CRITICAL",             // ★ 서버 산출 (parts 테이블 조회) — 파라미터 아님
  "expenditure_class": "CAPITAL",       // ★ 서버 산출 (data.maint_value.expenditure) — 파라미터 아님
  "expenditure_reason": "…",            // HOLD 면 그 사유. **HOLD 는 실패가 아니다**
  "cost": 8500000, "downtime_hours": 6.5, "record_hash": null,
  "next_step": "이 기록은 확정이 아니다. 제출 후 팀장이 서명해야 증빙이 된다." }
```

- **핵심 로직**:
  1. `db.repair_writer()` 신설 — `_guarded_writer(_REPAIR_GUARDS)`. TEMP TRIGGER 2개(UPDATE·DELETE ABORT). ⛔ **`draft_writer()`·`decision_writer()` 를 재사용하지 않는다** — `04 §15` 가 명시한 이유 그대로(*"잠겼다고 믿는 지점이 실제로는 안 잠긴다"*).
  2. **검증 순서**: 입력 어휘 → `equipment_id` 존재 → `parts[*].part_no` 존재 → `(model,error_code)` 짝·FK → **그 다음에** DB 를 연다. *거부할 입력으로 DB 를 열 이유가 없다*(`create_po_draft` 어휘).
  3. `part_class` = `parts` 테이블 조회. **하나라도 `CRITICAL` 이면 `CRITICAL`**, 전부 `CONSUMABLE` 이면 `CONSUMABLE`, 등급 미기재가 섞이면 **`null` + `not_considered` 에 사유**(지어내지 않는다).
  4. `expenditure_class` = `data.maint_value.expenditure(part_class, repair_scope, cost)`. **`HOLD` 도 그대로 저장**한다(DDL CHECK 가 허용). *회계 판단을 LLM 이 지어내지 못하게 파라미터에서 뺀 것이 이 설계의 핵심이다* — D31(단가)·D81(override)과 같은 태도.
  5. INSERT 는 `state='draft'`, `performed_by=NULL`·`requested_by=NULL`·`session_id=NULL`·`signed_at=NULL`·`record_hash=NULL`·`verified_by=NULL` 을 **리터럴로 박는다**. 신원 stamp 는 백엔드(MQ-909).
  6. 채번 `RPR-%04d` — 기존 시드 `RPR-2401~2412` 의 숫자 접미어 `max+1`. `create_po_draft` 와 같은 방식이며 **동시성은 P19 그대로 미룬다**(단일 사용자 데모 전제).
  7. `server.py` 의 `if TOOLS_PROFILE == "full":` 블록에 등록 → 확장 **9종**, 총 **16종**. ⛔ **core 7종에 넣지 않는다**(D69·D88 — 평가 기준선).
- **엣지 케이스**:

  | 입력 | 반환 |
  |---|---|
  | `work_type` 누락 | **MCP 스키마가 앞단에서 막는다** (D80 — 도구까지 도달하지 않는다) |
  | `work_type="EMERGENCY"` | `error/invalid_input` (enum 밖 — 폴백 금지) |
  | `cost <= 0` / 해석 불가 | `error/invalid_input` |
  | `parts` 빈 배열 | `error/invalid_input` — 부품 없는 수리 증빙은 증빙이 아니다 |
  | `part_no` 가 `parts` 에 없음 | `error/unknown_part` (+ 목록) — **지어낸 품번이 증빙에 남을 경로 차단**(D33 태도) |
  | `equipment_id` 없음 | `error/unknown_equipment` |
  | `model` 만 있고 `error_code` 없음 | `error/invalid_input` (DDL CHECK 이전에 도구가 막는다) |
  | `error_codes` 0행 상태에서 코드 지정 | `error/integrity` — **가려서 삼키지 않는다** |
  | UPDATE 시도 | TEMP TRIGGER ABORT → `error/integrity` |

- **지켜야 할 결정**: **D98** · D10(draft INSERT 만) · D80(기본값 없음) · D23·D37(신원은 서버) · D13·D33(복합 FK) · D9(예외 대신 status) · D69·D88(프로파일) · D12 태도(부품은 데이터에서).
- **회귀 스위트**: MQ-913 이 `write_tool_contract.py` 에 **⑮ 이후 블록 신설**(트리거 실제 ABORT 확인 · `state='draft'` 리터럴 · 파라미터 부재 6종 · `unknown_part`) · `tools_profile_contract.py` 확장 목록 9종.
- **DoD**:
  - `MAINTQ_TOOLS_PROFILE=full` 로 서버 기동 → `list_tools()` **16종** · 기본(core) → **7종**.
  - `rg -n "performed_by|verified_by|signed_at|record_hash|state=|session_id" mcp_server/tools/create_repair_record.py` 결과에 **파라미터 선언이 0건**(리터럴·NULL 만).
  - `04 §16` 신설 — `§15` 와 같은 형식(경계 표 + status/reason 표).
  - `uv run python data/seed.py --with-error-codes` **29건** · `error_codes` **65**.

---

#### MQ-907 — ⓑ S100 26건: 셀 내 줄바꿈 분해 실패 수정

- **복무 시나리오**: S1·S3
- **변경 파일**: `data/extract_error_codes.py`(수정 — `parse_s100` 의 remedy 경로만) · 후보 파일 append
- **핵심 로직**:
  1. MQ-902 의 `CELL_SPLIT` 라벨이 지목한 페이지(p.416~419 구간)만 손댄다.
  2. 원인은 `manual_eda.md:97` — *"셀 내 줄바꿈이 **문장 중간에서** 발생"*. `column_sentences()` 가 이미 단어 좌표로 문장을 재조립하는데, `bbox is None` 인 행과 y 구간 밖 문장이 버려진다(`:260` 주석이 *"bbox is None 을 건너뛰면 actions 가 통째로 빈다"* 고 이미 경고). **불릿 기준 재조립 + y 구간 경계 완화**를 이 경로에만 적용한다.
  3. ⛔ **OCR 을 쓰지 않는다.** 남는 결측은 후보 파일의 `_pending_review` 와 triage 의 `RE_OCR_CANDIDATE` 로 넘긴다 — *"소스 추가·파서 수정으로 풀리는 것을 45원/p 로 태우지 않는다"* 가 P31 의 요지다.
  4. `actions_manual_id="s100-manual"` · `actions_page`(물리) 를 함께 기록(D100). ⚠ S100 은 `print_page_offset=16` — **저장은 물리**(D26).
- **엣지 케이스**: 🔴 **기존 성공분 15건이 오염될 수 있다** — 이게 이 태스크의 가장 큰 위험이다 · 병합 셀 세로 전파가 이웃 항목을 흡수 → `span_key()` 의 *"못 고르면 버린다"* 를 유지 · 결측이 0 이 되지 않아도 **실패가 아니다**(실측값을 정직하게 기록).
- **지켜야 할 결정**: D24 · D26 · D99 · D100 · 절대규칙 3(생성 금지 — MQ-905 의 원문 대조 검사를 S100 에도 적용).
- **DoD**:
  - 🔴 **기존 성공분 무오염**: 착수 전 `actions` 가 비어 있지 않던 **S100 15건**의 값이 **한 글자도 변하지 않는다**(before/after JSON diff = 0). *이게 통과하지 않으면 회수 건수가 아무리 늘어도 실패다.*
  - 회수 건수를 **실측으로 기록**(26 → N). 개선폭을 예측·추정하지 않는다.
  - `_unparsed` 증가 **0건** · 원문 대조 전건 통과.
  - `error_codes.json` sha256 불변 · `error_codes` **65**.
  - `uv run python data/extract_triage.py` 재실행 → **`field_missing` 감소가 triage 수치로 확인된다**(계측을 먼저 만든 이유가 여기서 회수된다).

---

#### MQ-908 — 축 C REST 5종 (`services/maint_value.py` + `routers/maint_value.py`)

- **복무 시나리오**: S1+ · S9 · S10
- **변경 파일**: `backend/services/maint_value.py`(신규) · `backend/routers/maint_value.py`(신규) · `backend/main.py`(수정 — include 1줄)
- **인터페이스**:

```
GET  /api/assets/{asset_id}/metrics?window_months=12          → get_maintenance_metrics
POST /api/equipment/{equipment_id}/repair-value               → assess_repair_value   (무저장)
     body { failed_part, repair_cost, repair_scope? }
GET  /api/parts/{part_no}/criticality                         → classify_part_criticality
POST /api/expenditure/classify                                → classify_expenditure  (무저장)
     body { part_no, repair_scope, amount }     ← ★ part_class 를 받지 않는다
GET  /api/assets/{asset_id}/evidence-bundle?disposal_mode=SALE&disposal_date=
                                                              → services.decisions.rebuild_bundle 래퍼
```

- **핵심 로직**:
  1. 서비스는 `data.maint_value` 를 import 한다. ⛔ `mcp_server` import 금지(D15). 커넥션은 `backend/db.py` 의 **읽기 전용**만.
  2. **`POST /api/expenditure/classify` 는 `part_class` 를 받지 않는다** — `part_no` 로 서버가 `part_criticality` 를 구해 넣는다. 도구 설명(*"`part_class` 는 추측하지 말고 먼저 확인해 넣을 것"*)을 **API 경계에서 구조적으로 강제**하는 것이다. 응답에 `part_class` 와 **그 출처**(`derived_from: "classify_part_criticality"`)를 싣는다.
  3. **역할 게이트를 두지 않는다** — 5종 전부 읽기 판정이다. `require()` 를 부르지 않는다. *읽기 판정에 403 을 만들면 "권한 위반 403 차단 100%" 지표에 권한과 무관한 것이 섞인다*(D38, precheck·ownership 선례).
  4. **저장하지 않는다.** POST 2종도 `mode=ro` 커넥션만 쓴다. 경로 이름에 저장 어감이 없다(`/disposal/precheck` 가 `/disposal` 을 피한 것과 같은 이유를 docstring 에 적는다).
  5. `evidence-bundle` 은 `services.decisions.rebuild_bundle()` 을 **그대로** 부른다 — **신규 중복 0**. 응답에 `bundle`·`bundle_hash` 를 싣되, **번들 자체는 5키 해시로 고정되고 고정되지 않는 것은 파생 렌더**라는 구분을 필드로 드러낸다(`bundle_hash` + `render_hash_fixed: false`, `12 §8`).
  6. HTTP 매핑: 도구 `status` → `ok:200` · `not_found:404` · `invalid_input:422` · `rule_catalog_not_loaded:503` · `law_text_unavailable:409`. **`HOLD`·`insufficient_data` 는 200 이다** — 정상 판정이지 오류가 아니다. 매핑 dict 는 `assert set(...) == set(어휘)` 로 기동 시 검증(`disposal.py:49` 선례).
  7. 🔴 **하위 도구 실패를 삼키지 않는다** — `repair-value` 가 내부에서 `part_criticality`·`metrics` 실패를 받으면 그 `status`·`reason` 을 **그대로** 응답에 싣는다(`04 §13`).
- **엣지 케이스**: `window_months` 가 음수·비정수 → 422 · `part_no` 미존재 → 404 + `reason` · `asset_id` 미존재 → 404 · `disposal_mode` enum 밖 → 422(`engine.DISPOSAL_MODES` 단일 출처) · **`core` 프로파일에서도 200 이어야 한다**(D73).
- **지켜야 할 결정**: D101·D73·D15 · D38(403 은 전이에만) · D71(판정→HTTP) · D62(모른다 ≠ 통과) · D64·D65·D70·D74(고지 유지) · D85(`/api/po` 형태 불변 — 손대지 않는다).
- **회귀 스위트**: MQ-913 이 **5종 엔드포인트 계약 검사**를 `repair_flow_contract.py` 에 함께 싣는다(스위트 수 증가를 1로 억제).
- **DoD**:
  - `MAINTQ_TOOLS_PROFILE` **미설정**(core)에서 5종 전부 200/정상 판정 → `GET /health` 의 `tools` = **7** · `tools_profile` = **core**. *이것이 "평가 경로 무영향"의 증명이다.*
  - `rg -n "^(from|import) mcp_server" backend/services/maint_value.py backend/routers/maint_value.py` → **0건**.
  - `rg -n "require\(" backend/routers/maint_value.py` → **0건**(403 없음).
  - `spikes/api_contract.py` **28건** 수정 없이 통과(`/api/po` 무변경 증명).
  - `uv run ruff check backend`.

---

#### MQ-909 — 수리 증빙 REST + 통합 큐 배선 (S19 완성)

- **복무 시나리오**: **S19** (+ S10 승인 큐 공유)
- **변경 파일**: `backend/services/repairs.py`(신규) · `backend/routers/repairs.py`(신규) · `backend/services/approvals.py`(수정) · `backend/main.py`(수정)
- **인터페이스**:

```
GET  /api/repairs?state=pending          # 역할 무관 조회 (정비사도 자기 요청 상태를 본다)
GET  /api/repairs/{id}
POST /api/repairs/{id}/submit            # draft → pending    (technician 만, 아니면 403)
POST /api/repairs/{id}/sign              # pending → signed   (manager 만, 아니면 403)
POST /api/repairs/{id}/reject            # pending → rejected (manager 만, body {reason} 필수 → 422)
```

```python
def stamp_identity(repair_id, *, requested_by: str, session_id: str | None) -> bool: ...
def compute_record_hash(row: sqlite3.Row) -> str:   # "sha256:…"
    """정준 직렬화는 services.decisions.canonical_json 과 **동일 규약**."""
```

- **핵심 로직**:
  1. 상태 전이는 `ALLOWED_FROM` 한 곳(`po.py`·`decisions.py` 선례). **조건부 UPDATE**(`WHERE state = ?`)로 쓴다.
  2. `sign` 이 하는 일: `verified_by = X-User` · `signed_at = UTC now`(D39) · **`record_hash` 계산**. 해시 대상 키를 **고정 목록**으로 못박는다: `repair_id, equipment_id, model, error_code, part_class, work_type, expenditure_class, cost, downtime_hours, parts, performed_by, verified_by, signed_at`. `canonical_json` 결과를 **그대로** 해시한다(재직렬화 금지 — D84 가 처분에서 겪은 함정).
  3. **append-only**: `signed` 이후 전이 없음. 재서명 → **409 `invalid_transition`**. 정정은 **정정 레코드 추가**(`12 §7`) — 이번 스프린트는 정정 경로를 만들지 않고 그 사실을 문서에 남긴다.
  4. `services/approvals.py` 에 `_repair_item()` 추가 + `list_approvals` 의 `kind in (None,"repair")` 분기를 **실제 조회로 교체**. 필드 규약:
     - `title` = `f"{equipment_id} 수리 · {work_type_label}"`
     - `state` = **원 어휘 그대로**(`draft|pending|signed|rejected`) — ⛔ `approved`·`signed` 로 번역 금지(D85)
     - `urgency: null` · `verdict: null` · `requires_override: null` — **`false` 가 아니라 `null`**(발주·처분과 같은 규약, D62)
     - `detail_path` = `/api/repairs/{id}`
  5. 🔴 **`services/approvals.py:27~29` 의 *"repair 는 항상 0건"* 주석을 지운다.** 남겨 두면 코드가 거짓말을 한다.
  6. 신원 stamp 를 **에이전트 루프에 붙이지 않는다** — `create_po_draft` 는 `_emit_po_card` 에서 stamp 하지만, 수리 증빙은 **`po_card` 카드가 없고 block 3종은 고정**이다(D14·D22). S10 의 착지 방식(*요청은 prefill, 제출은 화면*)을 그대로 따라 **제출 화면에서 stamp** 한다.
- **엣지 케이스**: 팀장이 `submit` → **403** · 정비사가 `sign` → **403**(양방향, D38) · `reject` 사유 공백 → 422(pydantic 이 아니라 서비스에서 — 404 보다 먼저 터지면 순서가 깨진다, D84 선례) · 없는 id → 404 · `draft` 에 `sign` → 409 · 동시 서명 → **P19 그대로**(낙관적 락 미도입, 조건부 UPDATE 로 나중 것이 0행 갱신 → 409).
- **지켜야 할 결정**: D98 · D10(전이는 사람 API 만) · D23·D37(X-User) · D38(403/409 분리 · 반려 사유) · D39(UTC) · D85(큐 형태·어휘) · D21(session_id).
- **회귀 스위트**: MQ-913 — **신규 `spikes/repair_flow_contract.py`**.
- **DoD**:
  - 도구로 draft 생성 → submit → sign 왕복이 성공하고 `record_hash` 가 `sha256:` 로 시작한다.
  - **403 양방향**·**409 재서명**·**422 사유 공백** 이 각각 재현된다.
  - `GET /api/approvals?kind=repair` → **0건이 아니다**(시드 12 + 신규분). ⚠ 이 순간 `spikes/approvals_contract.py ③` 이 **깨지는 것이 정상**이고 MQ-913 이 뒤집는다.
  - `spikes/api_contract.py` **28건**·`spikes/approvals_contract.py` 의 **③ 이외** 검사 전건 통과.
  - `rg -n "항상 0건|Sprint 8" backend/services/approvals.py` → **0건**.

---

#### MQ-910 — `lookup_error_code` 에 `actions_source` (계약 자리 · D100)

- **복무 시나리오**: S1·S3·S4
- **변경 파일**: `mcp_server/tools/lookup_error_code.py` · `docs/04_MCP_TOOLS.md §1`
- **인터페이스**: 출력에 1키 추가.

```jsonc
"actions_source": null
// 또는 { "manual_id": "ig5a-troubleshooting", "page": 24 }
```

- **핵심 로직**:
  1. DB 의 `actions_manual_id`·`actions_page` 를 읽어 조립. **둘 다 NULL 이면 `null`**.
  2. 🔴 **`print_page` 를 도구 출력에 넣지 않는다.** 초안에는 넣었으나, **저장·검증은 물리 페이지**(D26)이고 **표시 변환은 기존 렌더 경로 1곳**이 담당한다(D32). 도구가 변환하면 오프셋 산술 지점이 둘이 된다 → **채택: `{manual_id, page}` 2키만.**
  3. 🔴 **`null` 의 뜻을 문서에 못박는다** — *"출처 미기록"* 이지 *"`manual_page` 와 같다"* 가 아니다. 지금은 **전건 `null` 이 정상**이고, MQ-919(승인 후)에 값이 생긴다.
- **엣지 케이스**: 한쪽만 NULL → DDL CHECK 가 이미 막지만 도구도 `null` 로 접는다(방어) · `manual_id` 가 manifest 에 없는 값 → 그대로 싣되 스파이크가 어휘를 검사.
- **지켜야 할 결정**: D100 · D1(정의는 룩업 / 절차는 RAG — **경계를 흐리지 않는다**: `actions` 는 이미 룩업에 있던 필드이고 이 태스크는 **출처만** 더한다) · D26·D32 · D9.
- **회귀 스위트**: MQ-913 이 `spikes/lookup_contract.py`(12건)에 **2건 추가** — ⓐ 키 존재(**전건 `null` 이 현재의 정답**) ⓑ **liveness 앵커**: `actions_manual_id` 를 임시 DB 사본에 1건 주입하면 그 값이 **실제로 올라온다**(*"항상 null 을 반환하는 코드"* 와 *"진짜로 비어 있다"* 를 구분).
- **DoD**: `lookup_contract` **12 → 14건** · 65코드 전건 `actions_source: null` · 주입 케이스에서 값이 올라온다 · `04 §1` 갱신.

---

#### MQ-911 — 사람 검수 패키지 (G1 을 여는 열쇠)

- **복무 시나리오**: S1·S3 (승인 없이는 값이 못 들어간다)
- **변경 파일**: `data/analysis/actions_review.md`(신규) · `TODO_직접할일.md`(수정)
- **핵심 로직**:
  1. 후보 파일을 읽어 **코드별 1블록** 문서를 생성한다: `model·code·error_name` / **후보 `actions` 원문** / **출처**(문서 id · 물리 p · 인쇄 p 병기, D32) / **원문 발췌**(대조용) / 조인 키 / `confidence` / 자동·수기 구분.
  2. 🔴 **안전 관련 문구를 별도 절로 뽑는다** — `활선`·`방전`·`대기`·`분`·`감전`·`접지`·`커버` 등 키워드가 걸린 항목. **`10분 이상`(매뉴얼 명시값) 이 축소 표기되지 않았는지**가 검수 1순위다. 이 절이 safety-guardrail 게이트의 실물이다.
  3. **iG5A 11건은 코드별 개별 확인**을 요구한다 — 명칭 조인은 틀릴 수 있고 틀리면 **엉뚱한 코드에 엉뚱한 조치**가 붙는다(`related_parts` 8코드 위임 판정과 같은 성격). **S100 회수분은 표본 확인**으로 충분함을 근거와 함께 적는다 — 조인이 아니라 같은 셀의 분해라 **코드-조치 대응 관계가 바뀌지 않는다**.
  4. **자동으로 승인하지 않는다.** 문서 말미에 승인 절차를 적는다 — ⓐ 검수자가 항목별 O/X ⓑ `ig5a_action_map.json` 의 `pending_review` 를 비운다 ⓒ 후보 파일 `_status` 를 승인으로 바꾼다 ⓓ **그때 MQ-919 를 착수**한다.
  5. `TODO_직접할일.md` 에 3항목 등재(조인 11건 확인 · 안전 문구 확인 · 병합 승인). **Claude 가 대신 처리하지 않는다.**
- **엣지 케이스**: 후보가 0건이면 문서를 만들지 말고 그 사실을 보고(빈 검수 문서를 만들면 "검수했다"의 근거로 오독된다) · 발췌가 길면 자르되 **잘랐다는 표시**를 남긴다(D53 태도 — 잘린 절차문은 뒷부분을 지어낼 여지를 만든다) · 후보가 0건인 코드는 **표에 남기고 "회수 실패"로 표시**한다(빠뜨리면 다음 사람이 "다 됐다"로 읽는다).
- **지켜야 할 결정**: D33(사람 승인) · D99(변경분 37건 단위) · **절대규칙 3** · D26·D32.
- **DoD**: 후보 전건이 문서에 1블록씩 있다 · 안전 키워드 절이 별도로 존재한다 · `TODO_직접할일.md` 에 3항목 · **`error_codes` 65행 불변** · ⚠ **이 태스크는 승인을 받지 않는다.** 자료 제출까지가 DoD 다.

---

#### MQ-912 — 프론트 공통 배관

- **복무 시나리오**: S1+ · S19
- **변경 파일**: `frontend/lib/api.ts` · `frontend/lib/types.ts` · `frontend/lib/mappers.tsx`
- **인터페이스**: 클라이언트 함수(`getMetrics`·`assessRepairValue`·`getCriticality`·`classifyExpenditure`·`getEvidenceBundle`·`getRepair`/`listRepairs`/`submitRepair`/`signRepair`/`rejectRepair`) + 응답 타입.
- **핵심 로직**:
  1. **`kind`·`state` 를 유니온이 아니라 `string` 으로 받는 기존 규약을 유지한다**(`api.ts:225` — *"백엔드가 어휘를 늘리면…"*).
  2. `mappers.tsx` 에 `repair` 배지·상태 매핑 추가. **어휘 번역 금지** — `signed` 는 `signed` 로 보여준다(D85).
  3. **null 을 false 로 접지 않는다.** `verdict`·`urgency`·`requires_override` 가 `null` 인 항목을 렌더 분기에서 `?? false` 로 처리하면 **없는 사실이 생긴다**.
  4. 지표·추정 응답 타입에서 `number | null`·`"insufficient_data"` 를 **타입으로 살린다**(옵셔널로 뭉개면 화면이 빈칸을 만든다).
- **엣지 케이스**: `X-Role`/`X-User` 헤더 규약 기존 그대로 · 409/422 본문의 `reason` 을 **버리지 않는다**(S4 태도).
- **지켜야 할 결정**: D85 · D87 · D62 · D35(block 계약 무변경).
- **회귀**: `tsc --noEmit` · `npm run build` 라우트 **10개 유지**(아직 화면 없음).
- **DoD**: `tsc --noEmit` 통과 · `rg -n "\?\? false|\|\| false" frontend/lib/api.ts frontend/lib/mappers.tsx` → **0건** · 빌드 라우트 10개.

---

#### MQ-913 — 회귀 (신규 1스위트 + 기존 4 수정)

- **복무 시나리오**: 인프라
- **변경 파일**: `spikes/repair_flow_contract.py`(신규) · `write_tool_contract.py` · `approvals_contract.py` · `tools_profile_contract.py` · `lookup_contract.py`
- **핵심 로직**:
  1. **신규 `repair_flow_contract.py`** — ⓐ 도구 draft 생성 ⓑ **TEMP TRIGGER 실증**: `repair_writer()` 커넥션으로 UPDATE·DELETE 를 **실제로 날려** ABORT 확인 (⛔ `draft_writer()` 로 확인하지 않는다) ⓒ 403 양방향 ⓓ 409 재서명 ⓔ 422 사유 공백 ⓕ `record_hash` 재계산 일치 ⓖ **축 C REST 5종** 계약(코어 프로파일에서 200 · 403 없음 · `HOLD`·`insufficient_data` 가 200).
  2. **`approvals_contract ③` 뒤집기** — *"0건"* → *"N건 + 양성 축"*. 판정식: `n > 0 and set(states) <= {"draft","pending","signed","rejected"} and kinds == ["po","disposal","repair"]`. **detail 에 결론이 아니라 실측값**(`repair n=13 · states={signed:11,draft:1,pending:1}`)을 인쇄한다 — *"repair 배선됨"* 같은 하드코딩 문구는 FAIL 일 때도 그대로 인쇄돼 표를 읽는 사람이 정반대로 이해한다(CLAUDE.md 규칙 · P30).
  3. `tools_profile_contract` — 확장 **9종**·full **16종**·core **7종**. **core 7 이 그대로임을 명시 검사**(D88 게이트의 전제).
  4. `write_tool_contract` — 쓰기 도구 **3종**으로 docstring·검사 확장. **`create_po_draft`·`generate_disposal_document` 기존 검사는 한 줄도 안 고친다**(고쳐야 한다면 그게 회귀다).
  5. `lookup_contract` — MQ-910 의 2건(liveness 앵커 포함).
  6. 도구 개수를 세는 다른 스위트 전수 확인: `rg -n "15\b|확장 8|extended.*8" spikes/` 로 낡은 숫자를 찾아 고친다.
- **지켜야 할 결정**: D98·D85·D69·D88·D100 · **CLAUDE.md 부재검사 규칙 · P30**(양성 축 + 실측 detail).
- **DoD**: **29스위트** · 전건 통과(⚠ Windows 소켓 고갈로 산발 실패 시 **단독 재실행 확인** 후 보고에 명시) · 건수는 **러너 출력 기준으로 기록**(지어내지 않는다) · `approvals_contract ③` 이 뮤턴트(배선 제거)로 **실제 FAIL** 하는 것을 확인.

---

#### MQ-914 — 화면 ① 수리가치 판단 (우선순위 1·3·4ⓑ·5)

- **복무 시나리오**: **S1+**
- **변경 파일**: `frontend/app/(console)/technician/asset/[assetId]/value/page.tsx`(신규) · `frontend/components/asset/{RepairValuePanel,CriticalityDrawer,ExpenditureCard,MetricsAside}.tsx`(신규 4)
- **핵심 로직**:
  1. **중심은 `assess_repair_value`** — 3지 판단(`ROOT_CAUSE_FIRST`→`HOLD`→`REPLACE`→`SELL_AS_IS`→`REPAIR`)과 `estimates[]`.
  2. 🔴 **하위 도구 실패를 UI 가 삼키지 않는다** — 응답의 `status != "ok"` 나 하위 전파 `reason` 이 오면 **판정 카드 자리에 그 사유를 그대로 표시**한다. 빈 화면·스피너·"데이터 없음" 으로 덮지 않는다(`04 §13` 계약).
  3. **`classify_part_criticality` = 드로어** — 부품 행 클릭 시 옆에서 펼쳐진다. **전용 페이지를 만들지 않는다.**
  4. **`classify_expenditure` = 작은 카드** — `part_class` 는 화면이 이미 갖고 있다. ⚠ **`HOLD` 를 에러로 렌더하지 않는다** — *"경계 사안이라 단정하지 않는다"* 는 **판정**이다. 색·아이콘을 실패 계열로 쓰면 계약 위반.
  5. **`get_maintenance_metrics` = `MetricsAside` 보조 패널** — *근거 절 옆*. ⛔ **격자 대시보드 금지.** `null` → **"판단 근거 부족"**, `insufficient_data` → **"추세 판단 불가(이벤트 2건 미만)"**. **빈칸·0·"양호"·"정상" 으로 렌더하지 않는다.** 실측 근거를 주석에 남긴다: *핵심 4지표 null 15/36(42%) · mtbf_trend insufficient_data 7/9.*
  6. **D64 방어**: MTBF·가용도·예방보전비율을 **점수·게이지·등급으로 나열하지 않는다.** 각 값 옆에 `mtbf_basis: calendar_days` 고지(D70)를 붙인다. **OEE 라는 단어를 화면에 쓰지 않는다.**
  7. **D65·D74 추정치 고지 강제** — `estimates[]` 의 시장가·잔가는 *"목업 정률 공식 기반 추정치"* 이고 **`RESIDUAL_AT_LIFE_END=0.50`·`FLOOR=0.10` 은 아직 사람 동의 전 가정**이다. `disclaimer` 를 **접거나 툴팁 뒤로 숨기지 않는다.**
  8. **D87 준수**: 컴포넌트는 스스로 "확인/통과" 를 말할 수단을 갖지 않는다 — 상태 문자열·색 토큰·판정 어휘 비교를 **컴포넌트 안에 두지 않고** 전역 매퍼에 위임(`ui_honesty_contract` L2 가 자동 스캔한다).
- **엣지 케이스**: `ROOT_CAUSE_FIRST` → **3지 선택지를 그리지 않는다**(S3 우선, D2) · 404/409 → `reason` 표시 · `estimates` 빈 배열 → *"추정 원천 없음"*.
- **지켜야 할 결정**: D64·D65·D70·D74·D87·D62·D2·D101.
- **회귀**: MQ-917 이 `ui_honesty_contract` 에 검사 추가. `L2_FILES_FLOOR` 상향.
- **DoD**: `npm run build` 라우트 **10 → 11** · `tsc --noEmit` · 9자산 중 **`insufficient_data` 자산(예: AST-L1-CONV)** 을 열었을 때 화면에 **"판단 근거 부족"** 이 보이고 **0·빈칸·"양호" 가 보이지 않는다**(수동 체크리스트) · `rg -n "OEE" frontend/` → **0건**.

---

#### MQ-915 — 승인 큐 `kind:"repair"` 상세

- **복무 시나리오**: **S19**
- **변경 파일**: `frontend/components/queue/{RepairDetail,RepairSignBar}.tsx`(신규) · `frontend/components/screens/ApprovalQueueScreen.tsx`(수정)
- **핵심 로직**:
  1. `ApprovalQueueScreen:101~103` 의 `kind` 분기에 `repair` 를 더한다(`po`→`PoDetail` · `disposal`→`DecisionDetail` · **`repair`→`RepairDetail`**).
  2. 상세는 `GET /api/repairs/{id}`. 표시: `work_type`(**PLANNED/UNPLANNED 를 뭉개지 않는다** — 예방보전 비율의 원천) · `part_class`·`expenditure_class`(**서버 산출임을 명시**) · `downtime_hours` · 부품·시리얼 · `record_hash`(**서명 전에는 "서명 시 생성"**).
  3. 서명 바: manager 만 활성. **정비사에게는 버튼 자체가 없다**(403 을 유일 방어선으로 두지 않는다 — 다만 서버 403 이 정본).
  4. `state` 어휘 **번역 금지**. 배지는 전역 매퍼가 만든다(D87).
- **엣지 케이스**: `record_hash` NULL 인 **시드 11건의 `signed`** — *"해시 규약 이전 데이터"* 라고 표시한다(빈칸으로 두면 위변조 의심으로 오독) · 반려 사유 미입력 → 버튼 비활성 + 422 를 그대로 표시 · 기본 필터를 `state=pending` 으로 두어 초기 화면이 과거 서명분으로 도배되지 않게 한다(단, 필터 해제 시 전건 보임 — 숨기지 않는다).
- **지켜야 할 결정**: D85(어휘·형태) · D87 · D38 · D62 · D63 태도(기록을 지우지 않는다).
- **DoD**: 라우트 **증가 없음**(큐 내부) · 시드 12건이 큐에 보이고 상세가 열린다 · `tsc --noEmit` · 정비사 역할로 서명 시도 시 **403 이 화면에 표시된다**.

---

#### MQ-916 — 화면 ②③ 근거 번들 + 지출 분류 독립 페이지 (우선순위 2·4ⓐ)

- **복무 시나리오**: **S10**(번들) · S1+(지출)
- **변경 파일**: `frontend/app/(console)/technician/asset/[assetId]/evidence/page.tsx`(신규) · `frontend/app/(console)/technician/expenditure/page.tsx`(신규) · `frontend/components/asset/{EvidenceBundlePanel,ExpenditureForm}.tsx`(신규 2)
- **핵심 로직**:
  1. **근거 화면** — 5키 번들(`facts`·`laws`·`rules`·`judgment`·`meta` 계열, D83)과 `bundle_hash` 를 **키 단위로** 보여준다. 🔴 **`bundle_hash` 가 고정하는 것은 5키뿐**이고 **파생 렌더(증빙 패키지)는 보호 범위 밖**이라는 사실을 화면이 말한다(`12 §8` — *"고정되지 않는다는 사실을 숨기면 계층 3의 존재 이유가 무너진다"*).
  2. **`MetricsAside` 를 여기서 재사용**한다 — 사용자 지시의 *"근거 옆에 보조로"* 의 정본 자리가 여기다. **컴포넌트를 복제하지 않는다.**
  3. `law_text_unavailable` → **번들을 그리지 않고 그 사유와 `missing_law_refs[]` 를 보여준다**(근거 없는 서류는 만들지 않는다).
  4. **지출 분류 독립 페이지** — 입력은 **부품 선택** + `repair_scope` + `amount`. ⛔ **`part_class` 를 사용자가 고르지 않는다** — 부품을 고르면 서버가 채우고, 화면은 **"이 등급은 `classify_part_criticality` 가 판정했다"** 를 출처와 함께 표시한다. `HOLD` 는 **정상 판정**으로 렌더.
- **엣지 케이스**: `assets` 없는 설비 → `no_host_asset` 을 *"문제 없음"* 이 아니라 **"대상이 아니다"** 로 표시(D62·ownership 선례) · 번들 5키 중 일부가 비면 **빈 키를 숨기지 않는다**.
- **지켜야 할 결정**: D83·D84·D86·D87·D62·D65·D64.
- **DoD**: 라우트 **11 → 13** · `tsc --noEmit`·`npm run build` · `rg -n "MetricsAside" frontend/components frontend/app` → **정의 1 + 사용 2**(복제 0) · 번들 화면에 `hash_fixed` 경계 문구가 보인다.

---

#### MQ-917 — `ui_honesty_contract` 확장 (68건 → 실측 증가)

- **복무 시나리오**: 인프라 (D87 방어선)
- **변경 파일**: `spikes/ui_honesty_contract.py` · `frontend/lib/__checks__/ui_honesty.ts`
- **핵심 로직** — 신규 검사 4군 + 뮤턴트:
  1. **N1 지표 정직성** — `null`·`"insufficient_data"` 가 빈칸·`0`·`"양호"`·`"정상"` 으로 렌더되지 않는다. L1 순수 함수(`formatMetric`)로 검증하고, **뮤턴트**(`?? 0` 주입)가 **실제로 FAIL** 하는지 매 실행 확인.
  2. **N2 추정치 고지** — `estimates[]` 렌더 경로에 `disclaimer` 가 **항상** 동반된다(D65·D74). 양성 축: 고지 문자열이 **실제로 발견된 횟수**를 detail 에 인쇄.
  3. **N3 판정 어휘** — 신규 컴포넌트에 상태 문자열·색 토큰·`=== "CLEAR"` 류 비교가 **0건**(L2 글롭이 `components/asset/*.tsx` 를 자동 포함 — `L2_FILES_FLOOR` **8 → 실측치**로 상향).
  4. **N4 `HOLD` 는 실패가 아니다** — `HOLD`·`insufficient_data` 가 **실패 색 토큰과 함께 쓰이지 않는다.**
  5. ⚠ **P30 규약을 이 태스크에서 지킨다** — 모든 부재 검사에 양성 축(`not bad and scanned > 0`)을 붙이고, **detail 에는 결론이 아니라 두 축의 실측값**을 인쇄한다.
- **지켜야 할 결정**: D87·D65·D70·D74·D64·D62 · P30 규약.
- **DoD**: `uv run python spikes/ui_honesty_contract.py` → **68건 → N건**(러너 출력 기록) · 뮤턴트 신규 2종이 **실제로 FAIL** 함을 확인 · `L2_FILES_FLOOR` 가 실측 파일 수로 올라갔다.

---

#### MQ-918 — 개수·상태 전파

- **복무 시나리오**: 인프라
- **변경 파일**: `CLAUDE.md`(기준선·스위트 목록·쓰기 도구 2→3) · `README.md` · `docs/README.md`(진행 상태) · `docs/00_MVP_SCOPE.md`(§9 · 쓰기 도구 3종 · 확장 9종) · `docs/07_BACKLOG.md`(P25 완료 · P31 진행) · `docs/02_SCENARIOS.md`(S19 구현) · `docs/04_MCP_TOOLS.md`(총 16종 · 서두) · `docs/05_DB_SCHEMA.md`(§1·§16 개정) · `docs/06_REPO_API.md`(§2.7 *"repair 항상 0건"* 정정 + **§2.8 수리 증빙** + 축 C 엔드포인트 5종) · `docs/12_MAINT_VALUE.md`(§7 구현 반영) · `docs/10_DECISIONS.md`(D10·D69·D85 **각주만**) · `TODO_직접할일.md` · `docs/status/*.html`
- **핵심 로직**: 러너 출력을 실측해 기입한다. **지어내지 않는다.** 특히 정정해야 할 **거짓이 될 문장 5곳**: ⓐ *"쓰기 도구는 2종"*(00_MVP:96·201) ⓑ *"확장 8종"*(04 서두·D69) ⓒ *"repair 는 현재 항상 0건"*(06 §2.7·D85) ⓓ *"S19 미구현 — Sprint 9"*(02:82) ⓔ `05 §16` 의 *"쓰기 경로는 Sprint 7"*.
  ⚠ **P31 은 "부분"이다** — ⓐ 회수 후보 11건·ⓑ 회수 X건은 **후보 파일에 있고 DB 에는 없다**. `error_codes` 는 **여전히 65건**이고 `actions` 결측은 **여전히 37건**이다. 여기서 "회수 완료"라고 쓰면 다음 세션이 없는 데이터를 있다고 읽는다.
  ⚠ `docs/07_BACKLOG.md` P31 의 ⓐ 서술(*"소스를 추가하면 된다"*)을 **§0-B 실측으로 정정**한다.
- **DoD**: `rg -n "쓰기 도구는? \*?\*?2종|확장 8종|항상 0건" docs/ CLAUDE.md` → **0건**(단 D85·D98 의 *역사 서술*은 예외로 각주 형태로 남긴다) · 기준선 숫자가 **러너 출력과 일치**(spikes 29스위트/N건 · seed 29 · pytest 46 · 라우트 13 · `error_codes` **65**) · D 범위 표기 5곳이 **D1~D101**.

---

#### MQ-919 — 🔴 **G1 승인 후에만** — `actions` 병합 적재

- **복무 시나리오**: S1·S3
- **변경 파일**: `data/extracted/error_codes.json`(병합) · `data/seed.py`(`load_error_codes` 병합분 · 검사 ㉚)
- **핵심 로직**:
  1. **승인 확인이 먼저다** — 후보 파일 `_status` 가 승인이고 `_pending_review` 가 비었는지 확인. 아니면 **중단**.
  2. 병합은 `actions`·`actions_manual_id`·`actions_page` **3키만** 덮어쓴다. `causes`·`manual_page`·`related_parts` 는 **손대지 않는다**.
  3. `_status` 는 **승인 상태를 유지**한다(D99). 병합 이력(누가·언제·몇 건)을 `_승인_이력` 으로 남긴다(`related_parts.seed.json` 선례).
  4. 재시드 → **`SELECT count(*) FROM error_codes` 가 65 인지 반드시 확인**(CLAUDE.md).
  5. 검사 **㉚** 신설 — `actions` 결측 수와 `actions_source` 기록 수를 **양성·음성 두 축의 실측값**으로 인쇄.
- **엣지 케이스**: 병합 후 `error_codes` 가 65 가 아니면 **즉시 중단·롤백**(백업 사본 선행) · 승인분이 37건 미만이어도 정상(부분 승인 허용, 나머지는 후보에 남는다) · 검수에서 반려된 코드 → 후보에서 제거하고 결측으로 남긴다(억지로 채우지 않는다).
- **지켜야 할 결정**: D33·D99·D100·D26·D32 · 절대규칙 3.
- **DoD**: `uv run python data/seed.py --with-error-codes` → **30건** · **`error_codes` 65행** · 결측 37 → 실측 N · 인용 페이지가 **문서별로 올바르다**(iG5A 조치는 `ig5a-troubleshooting`) · `spikes/citation_render.py`·`lookup_contract.py` 전건 통과.
- **⛔ 평가 지표에 대해**: 이 태스크는 **개선을 주장하지 않는다.** 병합 전/후 각각 `uv run python eval/run_eval.py --yes --repeat 3` 을 돌려 **`안정 실패 → 안정 통과` 로 넘어간 칸 수**로만 판정한다(`eval_gap_3rd.md §4` — 단일 실행 비교로는 개선과 요동을 구분할 수 없다). **⛔ `MAINTQ_TOOLS_PROFILE=full` 로 평가하지 않는다**(D88 이 코드로 막는다) — 이번 스프린트가 도구를 9종으로 늘렸으므로 이 규율이 특히 중요하다. **비용 승인은 사람(G4)** 이다.

---

## 7. 범위가 크다 — 압축 순서 (tool-builder 판단용)

19태스크 / 10스테이지는 **단일 스프린트로 크다.** 잘라야 한다면 **이 순서로** 자른다(뒤에서부터).

| 순위 | 자를 것 | 근거 |
|---|---|---|
| 1 | **MQ-916**(근거 번들·지출 독립 페이지) → Sprint 10 | 우선순위 2·4ⓐ 지만 **번들은 이미 처분 상세에 파생 렌더로 보인다**. 완전 미노출인 1·3·4ⓑ·5 보다 급하지 않다 |
| 2 | **MQ-907**(ⓑ S100 26건) → Sprint 10 | ⓐ 는 소스 추가로 확실히 풀리지만 ⓑ 는 **파서 수정이라 회수량이 불확실**하다. triage(MQ-902)와 검수 패키지(MQ-911)만 서면 다음 스프린트가 바로 이어받는다 |
| 3 | **MQ-915**(큐 repair 상세) | 백엔드(MQ-909)가 끝나 있으면 **API 로 시연 가능**하다. 다만 자르면 S19 의 "팀장이 서명한다"가 화면에서 안 보인다 — 서사 손실이 크므로 3순위 |
| ⛔ | **자르면 안 되는 것** | **MQ-901**(D 등재 — 안 하면 규칙 위반) · **MQ-902**(triage — 안 하면 축 B 전체가 "좋아졌는지 잴 수 없다") · **MQ-903**(로직 이동 — 안 하면 산식 두 벌) · **MQ-913·MQ-917**(회귀 — 안 하면 방어선 없이 기능만 늘어난다) |

---

## 8. 관련 파일 (절대 경로)

- 계획 근거: `C:\Users\ttogl\workspace\MaintQ\docs\00_MVP_SCOPE.md` · `docs\07_BACKLOG.md`(P25·P31) · `docs\10_DECISIONS.md` · `docs\02_SCENARIOS.md` · `docs\06_REPO_API.md` · `docs\04_MCP_TOOLS.md` · `docs\05_DB_SCHEMA.md` · `docs\12_MAINT_VALUE.md`
- 실측 확인처: `C:\Users\ttogl\workspace\MaintQ\data\seed.py`(`error_codes_gate():1687` · `load_error_codes():1772` · `INSERT … VALUES (?,?,?,?,?,?,?,?,?):1798` · `repair_records` DDL `:333`) · `data\extract_error_codes.py`(`parse_ig5a():369` · `ig5a_approval_status():438`) · `mcp_server\db.py`(`draft_writer`/`decision_writer` `:119~135`) · `backend\services\approvals.py`(`:27~29` *"repair 는 항상 0건"*) · `backend\services\decisions.py`(`rebuild_bundle():252` · `:520` *"산식이 두 벌 존재한다"*) · `data\ownership.py`(`verify(con, …):764`) · `spikes\approvals_contract.py:177~183` · `spikes\ui_honesty_contract.py`(`L2_GLOBS:55` · `L2_FILES_FLOOR:58`) · `data\raw\manifest.json`(`ig5a-troubleshooting` 등록·해시 기록됨) · `data\analysis\manual_eda.md:97,100` · `data\analysis\eval_gap_3rd.md:119~128`
- 축 B 실측 근거(2026-08-14 코디네이터): `docs\sessions\2026-08-14.md` · 본 문서 §0-B

---

## 9. 현실성 평가 (tool-builder)

> ⏳ **미실시 — 다음 세션.** `/sprint` Step 2 가 남아 있다.
>
> 평가자가 볼 것 (스킬 규격):
> - [ ] 명세가 구현에 충분한가
> - [ ] 병렬 실행 시 파일 충돌이 있는가 (§4 공유 파일 단일 소유자 표 검증)
> - [ ] 스테이지 내 숨은 순서 의존성이 있는가
> - [ ] **사람 승인 대기 항목에 막히는가** (§2 G1~G4)
> - [ ] **19태스크/10스테이지가 과대한가** → 과대하면 §7 압축 순서대로 자른다
