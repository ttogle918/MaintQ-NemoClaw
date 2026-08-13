# Sprint 8 — A2A 신원 식별 **기반층** (스키마·시드·회귀·env)

**수립**: 2026-08-13 · **개정**: 2026-08-13 (tool-builder 현실성 평가 반영) ·
**부제**: 실제 호출은 없다. 호출이 생겼을 때 **거짓말하지 않을 자리**를 먼저 만든다

**사용자 지시 (확정 범위)**: *"전부 스키마·시드·회귀·env 계층이다. 실제 A2A HTTP 호출·오케스트레이터는
범위 밖(QMesh 미착수). `create_repair_record`(P25·S19)는 원래 Sprint 8 예정이었으나 **Sprint 9 로 미룬다**."*

**근거 문서**: `docs/A2A_IDENTITY.md`(전체) · `docs/A2A_CONTRACTS.md` · **D91~D94**
**제약으로 읽은 결정**: D78 · D62 · D60 · D76-2 · D41 · D30 · D56 · D15

---

## ⚠ 읽는 순서

> **§3(결정 정정)과 §A(사용자 확정 사항)가 다른 절보다 우선한다.**
> §3 의 SQL 결함 2건은 **sqlite 3.50.4 에서 실제로 재현·확인**됐고, §A 는 사용자가 확정한 설계 판단이다.
> 다른 절과 충돌하면 이 둘을 따른다.

---

## 0. 선행 상태 (실측)

| 축 | 값 | 확인처 |
|---|---|---|
| 결정 | **D1~D94** (D91~D94 는 전부 *"⚠ 설계 확정·미구현"*) | `docs/10_DECISIONS.md:97~100` |
| DB | 절 **17** / `CREATE TABLE` **18개** | `data/seed.py` SCHEMA · `docs/05_DB_SCHEMA.md:9~13` |
| seed 자가검증 | **21건** (①~㉑) | `data/seed.py:1707~2070` |
| spikes | **27스위트 / 616건** | `CLAUDE.md` 실측 기준선 (2026-08-12, MQ-713b) |
| pytest | **46건** (`data/rules/test_rules.py`) | 〃 |
| 프론트 라우트 | **10개** | 〃 |
| MCP 도구 | 코어 7 + 확장 8 = 15 (기본 `core`, D69·D88) | `spikes/tools_profile_contract.py` |

**이 스프린트가 건드리지 않는 것**: `mcp_server/**` · `backend/routers/**` · `backend/services/**` ·
`backend/agent/**` · `frontend/**` · `eval/**` · `data/rules/**`.
따라서 **pytest 46건·프론트 10라우트·MCP 도구 15종은 숫자가 변하지 않는 것이 정상**이다.

### 이월 (carry-over)

| 항목 | 처리 |
|---|---|
| `create_repair_record` (P25 · S19) | **Sprint 9 로 이월.** 사용자 명시. 이번 스프린트에 태스크로 만들지 않는다. 계약 자리(`GET /api/approvals` 의 `kind:"repair"`, 항상 0건)는 D85 가 이미 확보해 뒀으므로 **계약 변경 없이** 추가된다 |
| 문서의 "Sprint 8" 표기 | `docs/00_MVP_SCOPE.md:162·175·177·194` · `docs/07_BACKLOG.md`(P25) · `docs/02_SCENARIOS.md:82` · `docs/README.md:61` 이 전부 *"Sprint 8"* 이라고 적고 있다 → **MQ-807 이 `Sprint 9` 로 정정**한다. 안 고치면 다음 세션이 "했는데 안 한" 상태를 읽는다 |
| Sprint 7 미완 | 없음 (Stage 7 까지 완료). 사람 대기 1건 = `KR-CITA-ENF-31` 제목 정정 → **2026-08-13 승인 완료**(`18913cd`) |

---

## A. 사용자 확정 사항 — InsuQ building 행은 `external_ref` 를 갖지 않는다

계획 1차안이 던진 grain 질문("InsuQ 행의 `external_ref` 에 무엇을 넣는가")의 **답이 확정됐다.**

```
(finallq, company,  '',      LINKED,     'CMP-MAINTQ-001')   ← 유일하게 external_ref 를 갖는 행
(insuq,   building, 'BLD-A', LINKED,     NULL)
(insuq,   building, 'BLD-B', LINKED,     NULL)
(insuq,   building, 'BLD-C', LINKED,     NULL)
(insuq,   building, 'BLD-D', NOT_LINKED, NULL)               ← 대조군
```

**근거**:
- 증권 식별자는 **`assets.policy_id` 가 정본**(D95)이고 `partner_links` 는 **연결 승인 여부만** 담는다.
  → `POL-2026-FIRE-01` 의 복제가 **0건**이 된다. 1차안(건물 3행에 증권번호 복제)은
  **D91 이 기각한 형태**(회사 단위 사실이 자산 9행에 복제된 `policy_id`)를 결만 바꿔 재발시키는 것이었다.
- 정정된 CHECK(§3)가 `LINKED` + `external_ref IS NULL` 을 허용하므로 **DDL 상 성립한다** —
  CHECK 가 막는 건 *"식별자가 있는데 승인이 없다"* 이지 *"승인은 있는데 식별자가 없다"* 가 아니다.

**이 확정이 바꾼 것**: 검사 ㉔ 의 전제가 바뀐다. 대조할 `external_ref` 가 없으므로
**"복제가 없다"를 확인하는 음성 검사**로 재설계한다(MQ-804 ㉔).

> ⛔ **`link_state` 와 `insured` 를 엮는 검사를 넣지 않는다.** 연결 승인과 부보는 **별개 축**이고,
> `BLD-D` 를 대조군으로 고른 이유가 정확히 그것이다. 엮는 순간 **D78 이 분리한 두 사실을 되붙이는** 셈이 된다.

---

## 1. 범위 판정 — 이건 MVP 인가 백로그인가

⚠ **A2A 신원 식별은 `docs/00_MVP_SCOPE.md` 에도 `docs/07_BACKLOG.md`(P1~P29)에도 없다.**
그러므로 **백로그 승격이 아니다** — 승격이라면 P번호가 있어야 하는데 없다.
근거는 다음 넷이고, 이 중 하나라도 무너지면 이 스프린트는 범위 이탈이다.

1. **사용자 확정 지시**가 있다(범위·비범위를 항목 단위로 지정).
2. **D91~D94 가 이미 등재된 결정**이고 넷 다 *"설계 확정·**미구현**"* 이다. 이번 스프린트는
   새 설계가 아니라 **등재된 결정의 구현**이다.
3. 산출물이 전부 **데이터 계층**이라 MVP 완료 기준 5지표의 분자·분모를 건드리지 않는다.
   그 사실은 **회귀 무증감**(pytest 46 · 프론트 10 · 도구 15)으로 증명된다.
4. `docs/A2A_CONTRACTS.md` 가 이미 이 레포의 문서이고, A2A_Q 표의 MaintQ 행이
   *"요청됨, 회신 대기"* 였다 — `A2A_IDENTITY.md` 가 그 회신이고 이번 스프린트가 그 이행이다.

### 복무 시나리오 — 솔직하게 적는다

`docs/02_SCENARIOS.md` 의 **S1~S4 에 직접 복무하는 태스크는 이 스프린트에 없다.**
A2A 시나리오(S5~S16)의 정본은 A2A_Q 레포에 있다. 이 레포에서의 연결점은 이렇다:

| 이번 산출물 | 잇는 곳 | 이 레포의 시나리오 |
|---|---|---|
| `partner_links` finallq/company 행 | 팀장 승인(`po.py` submit→approved) → FinAllQ `request-withdrawal` 의 **subject** 자리 | **S1 의 꼬리** (발주 승인 이후) |
| `partner_links` insuq/building 행 | 처분 서명(`decisions.py` sign) → InsuQ `notify-asset-change` | **S10 의 꼬리** |
| `traces.request_chain_id` | 실행 trace 시각화(MVP 기능 6)의 멀티홉 확장 자리 | S1~S4 공통 인프라 |
| `backend/a2a/credentials.py` | actor(인증) 보관 위치 — subject 와 분리 | — (D93 위치 확정의 이행) |

> **그래서 각 태스크 명세의 "복무 시나리오" 칸에는 `S1 꼬리` / `S10 꼬리` / `인프라` 로 적었다.**
> S1~S4 중 하나를 억지로 고르면 그 순간 계획이 사실과 달라진다.

---

## 2. 블로커 점검 — **이번 스프린트는 사람 대기가 0건이다**

| 블로커 | 이번 스프린트 영향 |
|---|---|
| `error_codes` 사람 승인 | **해제됨**(65건). 단 **시드 실행 커맨드 함정은 그대로 살아 있다** — §7 참조 |
| `related_parts` 검수 | 해제됨(2026-08-12). 이번 범위와 무관 |
| `ANTHROPIC_API_KEY` | **불필요.** 에이전트 루프·`/run-eval` 을 돌리지 않는다 |
| 임베딩·벡터스토어 미결 | 무관 (RAG 미접촉) |
| **A2A 파트너 자격증명 실값** | ⛔ **블로커가 아니다.** MQ-802 는 **env 읽기만** 하고, 값이 비면 `not_configured` 를 돌려주는 것이 정상 동작이다. 실값이 없어도 회귀가 전부 통과해야 한다 — 그게 이 태스크의 DoD 다 |
| **연결 승인·자격증명 실값 (사람)** | 이번 스프린트를 막지 않지만 **미착수 사실을 남긴다** — MQ-807 이 `TODO_직접할일.md` 에 1줄 추가하고, 시드 값은 **목업임을 검사로 강제**한다(MQ-804 ㉒-ⓕ) |

**결론: 스테이지 배치에서 "사람 승인 대기로 막히는 태스크"를 뒤로 뺄 필요가 없다.**
대신 배치의 지배 변수는 **`data/seed.py` 단일 파일 충돌**이다(§4).

---

## 3. D91 의 DDL 스케치가 SQLite 에서 틀렸다 — **D 를 먼저 추가해야 한다**

`docs/A2A_IDENTITY.md §4.3` 의 DDL 스케치를 SQLite 실제 의미로 검토한 결과 **결함 2건**을 찾았고,
**sqlite 3.50.4 에서 둘 다 직접 재현해 사실로 확인**했다. 여기에 미결 1건을 더해
**D95·D96 두 건**을 MQ-801 에서 등재한 뒤 구현한다(CLAUDE.md 규칙: 설계와 다른 구현은 D 추가 후).

> **왜 D96 하나인가.** 아래 결함 ①②는 **원인이 하나**다 — *"D91 의 DDL 스케치가 SQLite 의
> 3값 논리·PK NULL 특성에서 틀렸다."* 번호를 둘로 나누면 같은 사건이 두 개로 보인다.

### 결함 ① — `CHECK (link_state = 'LINKED' OR external_ref IS NULL)` 는 목적을 절반만 막는다

D91 이 이 CHECK 를 건 목적은 *"식별자만 있고 승인은 없는 상태를 DDL 에서 막는다"* 이다.
그런데 SQLite CHECK 는 **결과가 `NULL` 이면 통과**시킨다(3값 논리).

```
link_state = NULL, external_ref = 'CMP-X' 인 행:
  (link_state = 'LINKED')  →  NULL          -- NULL 과의 = 비교는 NULL
  (external_ref IS NULL)   →  0
  NULL OR 0                →  NULL          -- CHECK 통과 ⛔  (sqlite 3.50.4 재현 확인)
```

즉 **`NOT_LINKED` + 식별자만 막히고, "모름" + 식별자는 그대로 저장된다.**
D91 이 금지한 *"식별자 존재가 곧 승인 판정이 되는 상태"* 가 **가장 애매한 칸에서 통과**한다.

→ **정정**: 두 번째 CHECK 를 **null-safe `IS`** 로 적는다.

```sql
CHECK (external_ref IS NULL OR link_state IS 'LINKED')
--                                        ^^ = 이 아니라 IS. NULL IS 'LINKED' → 0 (거부)
```

`IS` 는 SQLite 에서 *"양쪽 또는 한쪽이 NULL 일 때를 제외하면 `=` 와 같다"* 는 연산자이므로
**첫 번째 CHECK 의 3상태(NULL=모름)는 그대로 유지**된다. D62 가 지킨 "모른다"는 살아 있고,
"모르는데 식별자는 있다"만 죽는다.

### 결함 ② — `subject_ref` 를 NULL 로 두면 PK 가 무력화된다

§4.3 스케치는 `subject_ref TEXT`(nullable) + `-- company 는 NULL(회사가 하나뿐)` 이다.
**SQLite 는 `INTEGER PRIMARY KEY` 가 아닌 PK 컬럼의 NULL 을 허용**하고, NULL 끼리는 서로 다르므로
`('finallq','company',NULL)` 행이 **몇 번이든 중복 INSERT 된다**(재현 확인). 회사 매핑이 2행·3행으로
갈려도 아무도 모른다.

→ **정정**: `subject_ref TEXT NOT NULL` + **회사 결(grain)은 `''`**(확인된 해당 없음).
이 레포는 이미 같은 규약을 쓴다 — `lien_creditor`/`lien_consent_ref` 가 *"담보 없음은 `''`, 모름은 NULL"*
이고 seed 검사 ⑱ 이 그 규약을 데이터 불변식으로 지키고 있다(D62).

### 미결 ③ — `assets.policy_id` ↔ `partner_links` InsuQ 행 (`A2A_IDENTITY §8.2-1`)

사용자와 합의된 제안을 **D95 로 등재**한다: `assets.policy_id` 가 **정본**, `partner_links` 의
InsuQ 행은 **subject 지정용**, 값이 갈리지 않도록 **seed 자가검증이 대조**한다(D60 과 같은 꼴).
§A 의 확정(InsuQ 행 `external_ref` = NULL)으로 **복제 자체가 0건**이 되므로, 대조는
*"복제가 없는가"* 를 보는 **음성 검사**가 된다.

> ⚠ **D95 의 채택 이유로 *"D78 판정 로직이 `policy_id` 를 읽으므로 못 옮긴다"* 라고 쓰면 안 된다 —
> 그 문장은 거짓이다.** 실측: `data/rules/rules/INSURANCE-NOTIFY.json` 의 `required_facts` 는
> `["insured"]` 뿐이고 trigger 도 `insured`·`risk_grade_changed` 다. `data/rules/test_rules.py:222`
> 는 오히려 *"policy_id 는 이제 증권 식별자일 뿐 — 있어도 판정을 바꾸지 않는다"* 를 **명시적으로 검사**한다.
> **그게 D78 의 요지다.** 실제 의존처는 §5 MQ-801 에 목록으로 적었다.
> 같은 거짓 문장이 `docs/A2A_IDENTITY.md §8.2-1` 에 **이미 커밋돼 있다** → MQ-807 이 정정한다.

---

## 4. 스테이지 계획

### Stage 1
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-801 | 결정 2건 등재 — D95(policy_id 정본·대조) · D96(DDL 정정: null-safe CHECK + `subject_ref NOT NULL`) + **D91 supersede 각주** | `docs/10_DECISIONS.md` | — |
| MQ-802 | 파트너 자격증명 읽기 층 — `backend/a2a/credentials.py` + `.env.example` 절 (D93) | `backend/a2a/` · `.env.example` | — |

### Stage 2
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-803 | `data/seed.py` **DDL 만** — `partner_links` 신설 + `traces.request_chain_id` 신설 | `data/seed.py`(SCHEMA) | MQ-801 |

### Stage 3
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-804 | `data/seed.py` **시드 5행 + 자가검증 4건**(21→25) + 목업 고지 | `data/seed.py`(마스터·시드·verify) | MQ-803, MQ-801 |

### Stage 4
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-805 | 신규 스파이크 `spikes/a2a_identity_contract.py` (27→**28스위트**) | `spikes/` | MQ-803, MQ-804, MQ-802 |

### Stage 5
| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-806 | `docs/05_DB_SCHEMA.md` — §18 신설 · §9 갱신 · **절/테이블 개수 정정** · 자가검증 목록 | `docs/05_DB_SCHEMA.md` | MQ-803, MQ-804 |
| MQ-807 | 개수·상태 전파 — 회귀 기준선 · D 범위 · **D91~D94 마커** · A2A 계약 상태 · 거짓 문장 정정 · 이월 표기 · 사람 TODO | `CLAUDE.md` · `README.md` · `docs/README.md` · `docs/00_MVP_SCOPE.md` · `docs/07_BACKLOG.md` · `docs/02_SCENARIOS.md` · `docs/06_REPO_API.md` · `docs/09_RUNTIME.md` · `docs/10_DECISIONS.md`(마커만) · `docs/A2A_*.md` · `docs/status/*.html` · `TODO_직접할일.md` · `.claude/agents/reviewer.md` | MQ-805 |

```
MQ-801 ──► MQ-803 ──► MQ-804 ──┬──► MQ-805 ──┬──► MQ-806
                                │             └──► MQ-807
MQ-802 ─────────────────────────┘
```

### 스테이지 구성 근거

- **Stage 1 (801·802 병렬)** — 파일 교집합 0. 801 은 `docs/10_DECISIONS.md` 한 파일,
  802 는 `backend/a2a/**` + `.env.example`. **801 을 맨 앞에 두는 이유는 규칙이다** —
  §3 의 D96 은 `A2A_IDENTITY §4.3` 스케치와 **다른 DDL** 을 쓰겠다는 것이므로,
  결정을 먼저 적지 않고 코드를 고치면 CLAUDE.md 의 *"설계와 다른 구현을 하려면 먼저 D 를 추가"* 위반이다.
  **802 를 1스테이지에 두는 이유**: 어느 것에도 선행하지 않고 `data/seed.py` 를 건드리지 않아
  스프린트 어디에도 끼울 수 있는데, 유일한 소비자인 MQ-805 가 뒤에 있으므로 가장 앞이 낭비가 없다.
- **Stage 2·3 을 나누는 이유 (핵심)** — 둘 다 `data/seed.py` 다. 파일 충돌 회피만이면 순서만 지키면 되지만,
  **검증 단위가 실제로 다르다**:
  - Stage 2 = *"잘못된 상태를 스키마가 거부하는가"* — **데이터 0행에서도 참**이어야 한다.
  - Stage 3 = *"시드가 그 스키마 위에서 정합한가"*.
  하나로 묶으면 **"시드가 통과했다"가 "CHECK 가 작동한다"의 증거로 오해**된다. 이 레포는 그 함정을
  이미 알고 있다 — 검사 ⑳ 이 음성 2건에 **양성 대조 1건**을 붙인 이유가 정확히 같다.
  그리고 §3 결함 ①(3값 논리)은 **시드 행이 들어가기 전에** 단독으로 확인해야 한다.
- **Stage 4 단독** — 스파이크는 **803(DDL)·804(시드)·802(credentials)를 동시에 관통**한다.
  셋 중 하나에 붙이면 자기 코드를 자기가 검증하는 구조가 된다(sprint-7 Stage 4 와 같은 이유).
  그리고 이 스파이크가 **"쓰는 쪽이 없다"는 사실을 기록하는 유일한 자리**다(§5 MQ-805).
- **Stage 5 (806·807 병렬)** — 파일 교집합 0. **807 이 805 뒤인 이유**: 회귀 기준선 숫자는
  **러너 출력이 기준**이라 스파이크를 실제로 돌려 보기 전에는 적을 수 없다. 지어내면 그 줄이
  거짓이 되고, CLAUDE.md 는 *"직전 실행보다 줄었다면 테스트가 사라진 것"* 을 그 숫자로 판정한다.

### 공유 파일 단일 소유자 격리

| 파일 | 유일 소유 | 스테이지 |
|---|---|---|
| `data/seed.py` (SCHEMA 블록) | **MQ-803** | 2 |
| `data/seed.py` (마스터 상수·시드 함수·`verify()`·docstring) | **MQ-804** | 3 |
| `docs/10_DECISIONS.md` (**D95·D96 신설 + D91 각주**) | MQ-801 | 1 |
| `docs/10_DECISIONS.md` (**D91~D94 의 미구현 마커만**) | MQ-807 | 5 |
| `backend/a2a/**` · `.env.example` | MQ-802 | 1 |
| `spikes/a2a_identity_contract.py` | MQ-805 | 4 |
| `docs/05_DB_SCHEMA.md` | MQ-806 | 5 |
| `CLAUDE.md` · `README.md` · `docs/README.md` · `docs/00_MVP_SCOPE.md` · `docs/07_BACKLOG.md` · `docs/02_SCENARIOS.md` · `docs/06_REPO_API.md` · `docs/09_RUNTIME.md` · `docs/A2A_IDENTITY.md` · `docs/A2A_CONTRACTS.md` · `docs/status/maintq-status.html` · `docs/status/maintq-data-map.html` · `docs/status/maintq-diagrams.html` · `TODO_직접할일.md` · `.claude/agents/reviewer.md` | MQ-807 | 5 |

> ⚠ **같은 파일을 두 태스크가 소유하는 곳이 2군데다. 둘 다 스테이지가 다르다.**
> `data/seed.py`(803: SCHEMA 문자열만 / 804: 그 밖) · `docs/10_DECISIONS.md`(801: 신규 D 행 + D91 각주 /
> 807: D91~D94 마커 문구). 같은 스테이지에 넣으면 병렬 실행이 같은 파일을 덮어쓴다.

---

## 5. 태스크별 상세 구현 명세

---

#### MQ-801 — 결정 2건 등재 (D95 · D96) + D91 supersede 각주

- **복무 시나리오**: 인프라 (S1 꼬리·S10 꼬리의 선행 규약)
- **변경 파일**: `docs/10_DECISIONS.md` (수정 — 표 끝에 2행 추가 + **D91 행에 각주 추가**)
- **인터페이스**: 문서. 기존 표 형식 그대로 `| D95 | 결정 | 대안 | 채택 이유 |`.
  D91~D94 와 달리 **`⚠설계 확정·미구현` 마커를 붙이지 않는다** — 이번 스프린트가 구현하기 때문이다.
- **핵심 로직**:

  **1. D95 — `assets.policy_id` 가 정본, `partner_links` 는 subject 지정용**
  - 결정: `policy_id` 를 **옮기지도 복제하지도 않는다.** §A 확정에 따라 **InsuQ 행의 `external_ref` 는
    NULL** 이고, `partner_links` 는 **연결 승인 여부만** 담는다. seed 자가검증 ㉔ 가
    *"`partner_links` 어디에도 증권 식별자가 복제되지 않았다"* 를 확인한다.
  - 대안: ① `partner_links` 로 `policy_id` 이전 ② InsuQ 행 `external_ref` 에 증권번호 복제(1차안)
    ③ `insuq_policy_id` 신설 ④ 대조 없이 병존.
  - **채택 이유 (⚠ 아래 문장을 그대로 쓸 것 — 실측 목록이다)**:
    - **판정은 `insured` 가 한다 (D78).** `policy_id` 는 증권 식별자일 뿐 판정을 바꾸지 않으며,
      `data/rules/test_rules.py:222` 가 그 사실을 **직접 검사**한다. 그러므로 ①을 기각하는 근거는
      *"룰이 그 컬럼을 읽어서"* 가 **아니다**.
    - ①을 기각하는 진짜 근거는 **의존처가 룰 밖에 흩어져 있다**는 것이다 — 실측:
      `data/rules/engine.py:301~302`(`ASSET_FACT_COLUMNS` 가 `assets` 에서 사실을 조립) ·
      `mcp_server/tools/generate_disposal_document.py:252`(증권 식별자 렌더) ·
      `data/ownership.py:533` · `spikes/rules_db_load.py:220` · `spikes/approvals_contract.py:330`
      (`UPDATE assets SET policy_id=...` 로 **번들 무결성 시나리오를 만든다**). 컬럼을 옮기면
      이 다섯이 동시에 깨진다.
    - ②(1차안)를 기각하는 이유가 이 결정의 핵심이다: **D91 이 기각한 형태의 재발**이다.
      D91 은 *"회사 단위 사실이 자산 9행에 복제돼 drift 가 시작된다"* 를 근거로 `assets` 확장을
      기각했는데, 건물 3행에 `POL-2026-FIRE-01` 을 복제하면 **결만 바꾼 같은 복제**가 된다.
      §A 확정으로 복제는 **0건**이다.
    - ③은 D91 이 이미 명시적으로 금지했다. ④는 두 값이 조용히 갈린다 —
      **D60 이 계층 1 사본을 파일 목록과 대조하는 것(검사 ⑬)과 같은 이유로** 대조를 건다.
  - ⛔ 함께 적을 것: **`NOT_LINKED` 건물의 자산이 `policy_id` 를 갖고 있는 것은 모순이 아니다** —
    *"부보돼 있다"(보험 사실)* 와 *"InsuQ 와 A2A 연결이 승인됐다"(파트너 대장)* 는 **별개 축**이다.
    이 구분이 D91 의 actor/subject 분리를 데이터로 보여 주는 지점이며, **두 축을 엮는 검사를
    만들지 않는 이유**이기도 하다(엮으면 D78 이 분리한 것을 되붙인다).

  **2. D96 — `partner_links` DDL 정정 (null-safe CHECK + `subject_ref NOT NULL`)**
  - 결정: ⓐ `CHECK (external_ref IS NULL OR link_state IS 'LINKED')` — **`=` 가 아니라 `IS`**
    ⓑ `subject_ref TEXT NOT NULL`, **회사 결은 `''`**(확인된 해당 없음)
    ⓒ **CHECK 는 필수 2종**(`link_state` enum + 식별자/승인 결합)이고 `partner`·`subject_type` 에는
    CHECK 를 걸지 않는다 — 파트너가 늘 때마다 DDL 을 고치게 되고, `traces.tool` 이 CHECK 없는
    자유 TEXT 이고 D94-ⓑ 가 `a2a:<skill>` 접두어를 **규약으로만** 둔 것과 같은 태도다.
    값 규약은 **회귀가 본다**(㉒ · 스파이크 ②).
  - 대안: ⓐ 원문 `=` 유지 → *"모름 + 식별자"* 통과(§3 결함 ①) · ⓑ `link_state NOT NULL` 로 3상태를
    2상태 축소 → **D62·D78 정면 위반** · ⓒ `COALESCE(link_state,'')='LINKED'` → 동작은 같으나
    `IS` 가 SQLite 표준 표현이고 **DDL 파싱 회귀(스파이크 ③)로 되돌림을 잡기 쉽다** ·
    ⓓ `subject_ref` nullable 유지 + 부분 유니크 인덱스 → 유니크 규칙이 두 곳으로 갈린다 ·
    ⓔ 회사 행에 `'MAINTQ'` 같은 가짜 로컬 키 → 없는 키를 지어낸다(D65).
  - 채택 이유: §3 의 재현 결과(3값 논리 · PK NULL 중복)를 **표에 그대로 인용**한다.
    D62 규약(없음=`''` / 모름=NULL)과 검사 ⑱ 선례를 함께 적는다.

  **3. D91 행에 supersede 각주** — `D58` 이 쓴 형식을 그대로 따른다(`docs/10_DECISIONS.md:64`):
  D91 결정 셀의 DDL 관련 문장 끝에
  *"→ **DDL 세부는 D96 으로 개정됨(superseded)** — `=`→`IS`, `subject_ref NOT NULL`"* 를 덧붙인다.
  **D91 의 나머지(판정/식별자 분리·인증 아님·`insuq_policy_id` 금지)는 유효하므로 취소선을 긋지 않는다.**

- **엣지 케이스**:
  - D 번호가 이미 D95 이상으로 선점돼 있으면(다른 세션) **번호를 밀지 말고 중단**하고 보고한다 —
    D 번호는 문서 5곳이 참조하는 식별자다.
  - 표 셀 안에 `|` 를 쓰면 표가 깨진다. 기존 행들처럼 `\|` 로 이스케이프.
  - **D97 을 만들지 않는다.** 결함 ①②는 원인이 하나다.
- **지켜야 할 결정**: D91(판정/식별자 분리·인증 아님은 유지, DDL 세부만 개정) · D62(NULL 3상태) ·
  D78(판정은 `insured`) · D60(정본 하나 + 대조) · D65(없는 값을 지어내지 않는다).
- **DoD**:
  - `rg -n "^\| D9[56] " docs/10_DECISIONS.md` → **2행**.
  - `rg -n "D96" docs/10_DECISIONS.md` → **2건** (D96 행 + **D91 각주**).
  - `rg -n "D97" docs/10_DECISIONS.md` → **0건**.
  - D95 셀에 **`test_rules.py:222`·`engine.py:301`·`generate_disposal_document.py:252`·
    `ownership.py:533`·`approvals_contract.py:330`** 5개 위치가 인용돼 있다.
  - D95 셀에 *"D78 판정 로직이 policy_id 를 읽는다"* 류의 문장이 **없다**.
  - ⚠ D 범위 표기(5곳)·D91~D94 마커 갱신은 **MQ-807 소유**다. 여기서 하지 않는다.

---

#### MQ-802 — 파트너 자격증명 읽기 층 (D93)

- **복무 시나리오**: 인프라 (actor 보관 위치 — S1 꼬리·S10 꼬리가 나갈 때 쓴다)
- **변경 파일**:
  - `backend/a2a/__init__.py` (신규 — 빈 패키지. 어댑터·오케스트레이터는 범위 밖임을 docstring 1줄로 명시)
  - `backend/a2a/credentials.py` (신규)
  - `.env.example` (수정 — 새 절 추가)
- **인터페이스**:

```python
PARTNERS: Final[tuple[str, ...]] = ("finallq", "insuq")
ENV_PREFIX: Final[str] = "MAINTQ_A2A_"

def env_names(partner: str) -> tuple[str, str]:
    """('MAINTQ_A2A_FINALLQ_CLIENT_ID', 'MAINTQ_A2A_FINALLQ_CLIENT_SECRET')"""

@dataclass(frozen=True)
class PartnerCredential:
    partner: str
    status: str            # 'configured' | 'incomplete' | 'not_configured' | 'unknown_partner'
    client_id: str = ""
    client_secret: str = field(default="", repr=False)   # ⛔ repr 에 싣지 않는다
    @property
    def usable(self) -> bool: ...                        # status == 'configured'
    def __repr__(self) -> str: ...                       # 값 대신 길이만: secret_len=N
    __str__ = __repr__

def load(partner: str) -> PartnerCredential: ...
def status_report() -> dict[str, str]: ...   # {'finallq': 'not_configured', 'insuq': ...} — 값 없음
```

> ⚠ **`load()` 는 호출할 때마다 `os.environ` 을 읽는다 — 모듈 수준 캐시를 두지 않는다.**
> 캐시하면 첫 import 시점의 값이 굳어 **스파이크 ⑯ 이 env 를 갈아끼우며 4상태를 검사하는 것이
> 원리적으로 불가능**해지고, 실운영에서도 *"어느 값으로 돌았는지"* 를 디버깅할 수 없다(D56 의 취지).

- **핵심 로직**:
  1. `os.environ` 만 읽는다. **`load_dotenv()` 를 호출하지 않는다** — D56 이 그 호출을
     `backend/main.py` **한 곳**으로 못박았고, 여기서 또 부르면 "어느 파일이 이겼는지" 디버깅이 불가능해진다.
  2. `partner` 를 `strip().lower()` 하고 `PARTNERS` 밖이면 `status="unknown_partner"` (값은 읽지 않는다).
  3. `client_id`·`client_secret` 을 각각 `.strip()`. 판정:
     - 둘 다 비었다 → `not_configured`
     - **한쪽만 있다 → `incomplete`** (⛔ 부분값으로 호출을 시도할 수 있는 상태를 만들지 않는다)
     - 둘 다 있다 → `configured`
  4. `status_report()` 는 **상태 문자열만** 담은 dict 를 돌려준다. 값·길이·마스킹본 어느 것도 싣지 않는다.
  5. **토큰 캐시를 만들지 않는다.** D93 이 *"액세스 토큰은 프로세스 메모리 캐시"* 라고 정했지만
     **소비자가 없다** — 소비자 없는 코드는 회귀 부담만 늘린다(D56 이 OpenAI 클라이언트를 안 붙인 이유와 동일).
     모듈 docstring 에 *"토큰 캐시는 A2A 호출부가 생기는 스프린트가 만든다"* 를 명시한다.
  6. **금지 목록** (구조로 지킨다): `sqlite3` import 금지 · 문자열 `partner_links` 금지
     (D93 이 ②"자격증명을 대장 테이블에" 를 기각한 근거를 코드 구조로 유지) ·
     `httpx`/`requests` 등 네트워크 라이브러리 import 금지 · `logging` 으로 값을 찍는 코드 금지.
- **`.env.example` 추가 절** — `MAINTQ_MCP_AUTOSTART` **아래**, `══ 외부 데이터 원천 ══` 구분선 **위**에 넣는다.
  ⛔ 수집 스크립트 키 절 **안에 넣지 않는다** — 그 절의 규칙 문장이 *"backend/·mcp_server/ 는 아래 키를
  절대 참조하지 않는다"* 인데 A2A 는 **런타임에 백엔드가** 읽으므로, 같은 절에 두면 그 문장이 거짓이 된다(D93 ③ 기각).

```
# ══ A2A 파트너 자격증명 (QMesh · 호출부 미착수) ══
# ⚠ LLM 키와 성격이 다르다: 이 자격증명으로 나가는 요청은 돈을 움직인다(S5).
#    발급 주체는 상대 시스템의 ADMIN 콘솔이며, 사람 간 연결 승인 후에만 발급된다.
#    한도·허용 작업·유효기간이 함께 발급되므로 만료 처리가 필요하다.
# 읽는 곳: backend/a2a/credentials.py 한 곳. **MCP 도구는 접근하지 않는다** (D15·D93).
# 비어 있어도 앱 기동·회귀·평가에 영향이 없다 → status='not_configured'.
# ⛔ 실제 값을 이 파일·세션 로그·주석 어디에도 적지 말 것.
MAINTQ_A2A_FINALLQ_CLIENT_ID=
MAINTQ_A2A_FINALLQ_CLIENT_SECRET=
MAINTQ_A2A_INSUQ_CLIENT_ID=
MAINTQ_A2A_INSUQ_CLIENT_SECRET=
```

- **엣지 케이스**:
  | 입력 | 반환 |
  |---|---|
  | env 미설정 | `status='not_configured'`, `client_id=''`, `client_secret=''` — **예외를 던지지 않는다** |
  | `..._CLIENT_ID` 만 설정 | `status='incomplete'` (⚠ `configured` 로 올리지 않는다) |
  | 값이 공백뿐(`"  "`) | `strip()` 후 빈 문자열 → 미설정과 같게 취급 |
  | `load("FinAllQ")` | 소문자 정규화 후 정상 처리 |
  | `load("qmesh")` | `status='unknown_partner'` (env 를 읽지도 않는다) |
  | 같은 프로세스에서 env 를 바꾸고 재호출 | **바뀐 값이 반영된다**(캐시 금지) |
  | `print(cred)` / f-string | 마스킹된 repr — **secret 원문이 나오면 결함** |
- **지켜야 할 결정**: D56(OS env 우선 · `load_dotenv` 1곳) · D93(위치·토큰 비영속) ·
  D15(MCP 프로세스 분리 — 도구는 이 모듈을 보지 않는다) · 절대규칙 1(A2A 호출은 사람 승인 뒤 백엔드의 일).
- **DoD**:
  - `uv run python -c "from backend.a2a import credentials as c; print(c.status_report()); print(c.load('finallq'))"`
    → 상태만 출력되고 **어떤 비밀값도 찍히지 않는다**(미설정 환경에서 `not_configured`).
  - `uv run ruff check backend` 통과.
  - `rg -n "load_dotenv|sqlite3|partner_links|httpx|requests" backend/a2a/` → **0건**.
  - `rg -n "^_[A-Z_]+\s*=|lru_cache|functools.cache" backend/a2a/credentials.py` → **모듈 수준 값 캐시 0건**.
  - `.env.example` 의 4키가 `외부 데이터 원천` 구분선 **위**에 있다.
  - ⚠ `backend/main.py` 를 수정하지 않는다 — `/health` 노출은 범위 밖(호출부가 생길 때 함께).

---

#### MQ-803 — `data/seed.py` DDL: `partner_links` + `traces.request_chain_id`

- **복무 시나리오**: S1 꼬리 · S10 꼬리 (subject 대장) / 인프라 (멀티홉 trace 자리)
- **변경 파일**: `data/seed.py` — **`SCHEMA` 문자열만** (수정)
- **인터페이스 (DDL 확정형)**:

```sql
CREATE TABLE traces (
  ...
  tool_payload TEXT,
  -- A2A 멀티홉 추적용 (D94-ⓐ). nullable — 기존 행·기존 INSERT 문에 영향이 없다.
  -- ⚠⚠ **쓰는 쪽이 아직 없다.** A2A 호출부(QMesh)가 미착수라 **현재 전 행 NULL 이 정상**이며,
  --     spikes/a2a_identity_contract.py 가 그 사실을 **명시적 라벨로 기록**한다.
  --     D76-2 가 컬럼만 만들고 쓰는 쪽이 없어 3차 평가까지 전부 NULL 이었던 전례를 반복하지 않기
  --     위해, "값이 비었다"가 아니라 "쓰는 쪽이 없다"를 회귀가 말하게 한다.
  request_chain_id TEXT,
  ts           DATETIME DEFAULT CURRENT_TIMESTAMP,
  CHECK (event_type IN ('tool_call','tool_result','block')),   -- ⛔ 3종 그대로 (D94 채택 근거)
  UNIQUE (session_id, seq)
);

-- §18 partner_links — 외부 파트너 subject 매핑 대장 (D91·D92·D96)
-- ⛔ **인증 정보가 아니다.** 여기 행이 있다는 사실은 "우리가 아는 상대 식별자"일 뿐이며
--    상대 시스템의 승인 근거가 되지 않는다 — actor(누가 호출했나)는 파트너 토큰(D93)이 담당하고,
--    **나가는 요청 payload 의 subject 값을 이 대장에서 가져온다** (A2A_Q A2A_IDENTITY 결정 1).
CREATE TABLE partner_links (
  partner      TEXT NOT NULL,   -- 'finallq' | 'insuq'  ★ CHECK 를 걸지 않는다 (D96-ⓒ)
  subject_type TEXT NOT NULL,   -- 'company' | 'building' | 'asset'  (결/grain)
  subject_ref  TEXT NOT NULL,   -- MaintQ 로컬 키. **회사 결은 ''** (D96 — NULL 이면 PK 가 무력화된다)
  -- ★ D78 패턴: 판정과 식별자를 분리한다. NULL=모름 / 'NOT_LINKED'=확인된 미연결 / 'LINKED'=사람 승인 완료
  link_state   TEXT,
  -- 상대 시스템 식별자(subject 지정용). **판정 근거가 아니다.**
  -- ⚠ InsuQ building 행은 NULL 이다 — 증권 식별자의 정본은 assets.policy_id 이고
  --    여기에 복제하지 않는다 (D95).
  external_ref TEXT,
  -- 연결 승인 시점 (사람 단계). NOT_LINKED 행은 NULL.
  -- ⚠ 날짜가 아니라 **시각**이다 (D96-ⓓ). **저장은 UTC** (D39, `traces.ts` 와 같은 규약)
  linked_at    DATETIME,
  PRIMARY KEY (partner, subject_type, subject_ref),
  -- NULL 은 이 CHECK 에서 NULL 로 평가돼 통과한다 = "모름"이 표현 가능하다 (D62). 의도된 동작이다
  CHECK (link_state IN ('NOT_LINKED','LINKED')),
  -- ★ null-safe `IS` (D96). `=` 로 쓰면 (link_state NULL, external_ref 있음) 이 조용히 통과한다
  CHECK (external_ref IS NULL OR link_state IS 'LINKED')
);
```

- **핵심 로직**:
  1. `traces` 블록에 `request_chain_id TEXT` 를 `tool_payload` **다음**, `ts` **앞**에 넣는다.
     `event_type` CHECK·`UNIQUE`·`idx_traces_session` 은 **한 글자도 건드리지 않는다**.
  2. `partner_links` DDL 을 `SCHEMA` 문자열 **맨 끝**(`residual_curve` 뒤)에 추가한다.
  3. **`partner`·`subject_type` 에 CHECK 를 걸지 않는다** (D96-ⓒ). 값 규약은 회귀가 본다.
  4. **`NOT_LINKED` → `linked_at IS NULL` 도 CHECK 로 걸지 않는다.** 데이터 불변식으로 잡는다(㉒) —
     검사 ⑱(`has_lien=1` 인데 `lien_consent_ref=''`)이 쓴 방식 그대로다.
  5. **시드 행을 여기서 넣지 않는다.** 데이터는 MQ-804 소유다.
- **엣지 케이스**:
  | 상황 | 기대 |
  |---|---|
  | 기존 `traces` INSERT 코드 (`backend/agent/trace.py:195`) | **무영향** — 컬럼 목록이 명시적이다(실측 확인) |
  | `eval/run_eval.py:528` 덤프 | **무영향**(명시적 SELECT). 전 행 NULL 이라 덤프에 추가하지 않는다 — 값이 생기는 스프린트가 함께 고친다 |
  | `spikes/trace_persist.py`·`api_contract.py` | 둘 다 명시적 컬럼. `SELECT * FROM traces` 는 레포 전체에 **0건**(실측) |
  | `link_state='linked'`(소문자) | 첫 CHECK 가 0 → 거부 |
  | `subject_ref` 누락 | `NOT NULL` 위반 → 거부 |
- **지켜야 할 결정**: D94(ⓐ 컬럼 신설 · `event_type` 3종 유지 · ⓔ `payload` 바이트 동일) ·
  D30(payload == SSE data — 이 태스크는 `payload` 를 건드리지 않는다) · D41(UNIQUE 유지) ·
  D91(판정/식별자 분리) · D96(DDL 세부) · D95(복제 금지) · D62(NULL 3상태).
- **DoD**:
  - `uv run python data/seed.py --with-error-codes` → **21건 전부 통과**(검사 수는 아직 그대로) ·
    `SELECT count(*) FROM error_codes` = **65**.
  - `PRAGMA table_info(partner_links)` → 6컬럼, `subject_ref.notnull=1` ·
    `PRAGMA table_info(traces)` 에 `request_chain_id` 존재·`notnull=0`.
  - **회귀 무증감**: `spikes/trace_persist.py` **17건** · `spikes/sp3_sse_events.py` **22건** ·
    `spikes/api_contract.py` **28건** 이 전부 그대로 통과.
    ⚠ **이 세 스위트 중 하나라도 수정이 필요하다면 그 자체가 설계 위반이다**(D94 의 채택 근거가
    *"기존 스파이크를 하나도 수정하지 않는다"* 였다).
  - `uv run ruff check data`.

---

#### MQ-804 — `data/seed.py` 시드 5행 + 자가검증 4건 (21 → **25**) + 목업 고지

- **복무 시나리오**: S1 꼬리(FinAllQ company) · S10 꼬리(InsuQ building)
- **변경 파일**: `data/seed.py` — 마스터 상수 · 시드 함수 · `main()` 호출·출력 · `verify()` · 모듈 docstring (수정)
- **인터페이스**:

```python
# ── partner_links 시드 (D92·D95) ─────────────────────────────────────────
# ⚠ 시드 전제(목업)다 — 실제 연결 승인·발급값이 아니다. PARTNER_LINKS_MOCK 참조.
# ★ InsuQ building 행의 external_ref 는 **전부 NULL** — 증권 식별자의 정본은 assets.policy_id 다 (D95).
# (partner, subject_type, subject_ref, link_state, external_ref, linked_days_ago)
PARTNER_LINKS: list[tuple[str, str, str, str | None, str | None, int | None]] = [
    ("finallq", "company",  "",      "LINKED",     "CMP-MAINTQ-001", 30),
    ("insuq",   "building", "BLD-A", "LINKED",     None,             30),
    ("insuq",   "building", "BLD-B", "LINKED",     None,             30),
    ("insuq",   "building", "BLD-C", "LINKED",     None,             30),
    ("insuq",   "building", "BLD-D", "NOT_LINKED", None,             None),  # ★ 대조군
]

# 실제 연결 승인·자격증명 발급 여부. 사람이 실값을 받으면 False 로 바꾼다 (TODO_직접할일.md).
# 문구를 하드코딩하지 않고 이 플래그에서 유도한다 — part_class_caveat() 와 같은 형태 (D90).
PARTNER_LINKS_MOCK: bool = True

def partner_links_caveat() -> str: ...
def seed_partner_links(con: sqlite3.Connection, today: date) -> None: ...
```

- **핵심 로직**:
  1. `linked_at` 은 **실행일 기준 상대 시각**이다 (D96-ⓓ 로 `DATE`→`DATETIME` 변경됨).
     고정 값을 박으면 해가 바뀔 때 조용히 밀린다(시드 전체 규약, `acquired_at`·반복 고장과 동일).
     ⚠ **저장은 UTC** (D39). `datetime.utcnow()` 기준으로 `timedelta(days=linked_days_ago)` 를 빼고
     `'YYYY-MM-DD HH:MM:SS'` 로 적는다 — `traces.ts`(`CURRENT_TIMESTAMP`, UTC)와 같은 모양이다.
     ⛔ **로컬 시각을 쓰지 마라.** 시드는 실행일 기준 상대값인데 검증(㉒-ⓓ)이 다른 시계를 보면
     자정 근처에서 위양성 FAIL 이 난다 — CLAUDE.md 가 경고한 `--today` 함정과 같은 계열이다.
  2. `main()` 에서 `seed_assets(...)` **직후** 호출한다. FK 는 없지만 `building_id` 를 참조하므로
     자산이 먼저 들어간 뒤가 읽기 쉽다.
  3. **회사 결 `subject_ref = ''`** (D96). `None` 을 쓰면 `NOT NULL` 위반으로 즉시 죽는다 — 그게 맞다.
  4. **목업 고지** — `partner_links_caveat()` 가 `PARTNER_LINKS_MOCK` **상태에서 문구를 유도**하고,
     `main()` 이 `part_class_caveat()` 와 같은 자리(**통과 표 뒤**)에 출력한다.
     PASS 표 안에 넣으면 초록색에 묻혀 아무도 안 본다(D12 태도). 검수가 끝나도 줄을 없애지 않는다(D90).
  5. 모듈 docstring 과 `verify()` docstring 의 검사 범위 문구(현재 *"7종(①~⑧) + D41(⑨~⑪)"*)에
     **Sprint 8 항목(㉒~㉕)** 을 덧붙인다.

  **★ 대조군을 `BLD-D` 로 정한 근거 (시드 실측):**

  | building | 자산 | `insured` / `policy_id` |
  |---|---|---|
  | `BLD-A` | `AST-L1-CONV` | 1 / `POL-2026-FIRE-01` |
  | `BLD-B` | `AST-L2-SPDL`·`AST-L2-CLNT` | 1 / `POL-2026-FIRE-01` |
  | `BLD-C` | `AST-L3-CONV`·`AST-L3-EXFAN` / **`AST-L3-LIFT`** | 1 / `POL…` · **0 / NULL** |
  | **`BLD-D`** | `AST-L4-CONV`·`AST-L4-WRAP`·`AST-L4-DUST` | **전부 1 / `POL-2026-FIRE-01`** |

  - `BLD-C` 를 대조군으로 쓰면 **"미부보(`insured=0`)"와 "미연결(`NOT_LINKED`)"이 한 건물에 겹쳐**
    두 축이 섞인다 — 데모에서 *"보험이 없어서 못 쏘는 것"* 으로 오독된다.
  - `BLD-D` 는 **자산 3건이 전부 부보돼 있는데도 미연결**이다. 그래서
    *"부보돼 있어도 A2A 연결 승인이 없으면 S11·S14 를 못 쏜다"* 가 **한눈에 보인다** —
    D91 의 actor/subject 분리를 데이터가 직접 증명한다.
  - 자산 수가 가장 많아(3건) 화면·쿼리에서 눈에 띈다. `A2A_IDENTITY §5` 의 예시(*"예컨대 BLD-D"*)와도 일치.
  - **D78 이 `AST-L3-LIFT` 한 건을 `insured=0` 으로 남겨 `CLEAR` 경로를 확보한 것과 같은 설계**다.

- **자가검증 4건** (`verify()` 의 ㉑ 뒤, `return results` 앞):

  | # | 검사 | 판정 내용 |
  |---|---|---|
  | **㉒** | `partner_links` 시드 정합 · **`NOT_LINKED` 대조군 존재** · 목업 고지 (D92) | ⓐ `LINKED` ≥ 1 **그리고** `NOT_LINKED` ≥ 1 ⓑ `partner` ⊆ {`finallq`,`insuq`} · `subject_type` ⊆ {`company`,`building`,`asset`} ⓒ **insuq 의 `building` 결 행**(⚠ `subject_type='building'` 으로 좁힌다 — 권고 ④. insuq 에 company 결이 늘면 `''` 때문에 집합이 어긋나는데 그 실패는 "대장 누락"이 아니다)**의 `subject_ref` 집합 == `SELECT DISTINCT building_id FROM assets WHERE building_id IS NOT NULL`** — detail 에 **`building_id` NULL 자산 건수를 별도 표기**(현재 0건이지만 생기면 대장에서 조용히 빠진다) ⓓ `linked_at` 은 `LINKED` 행만 non-null 이고 **현재 UTC 시각 이전**(D96-ⓓ·D39 — 비교도 반드시 UTC 로. 로컬 시계와 섞으면 자정 근처 위양성) · 값이 `'YYYY-MM-DD HH:MM:SS'` 로 **시·분·초를 포함**한다 ⓔ company 행의 `subject_ref == ''` (D96) ⓕ **`PARTNER_LINKS_MOCK` 이 True 인 동안 `partner_links_caveat()` 가 '목업'을 포함한 비어 있지 않은 문구를 돌려준다** (검사 ⑯ 의 `source LIKE '%목업%'` 선례). ⚠ **문구와 접두 기호 두 축을 함께 잠근다**(권고 ②) — `main()` 이 라벨을 `startswith('✓')` 로 고르므로 문구 축만 보면 *"`[사람 확인]` ⚠ … 목업 전제 …"* 라는 **자기모순 라벨**이 통과한다(D90 이 기각한 ③과 같은 유형) |
  | **㉓** | `partner_links` **CHECK 음성 3 + 양성 2** (D91·D96·D62) | `SAVEPOINT` 로 실제 INSERT 시도 후 되돌린다(⑩·⑰·⑳ 패턴). **음성** ⓐ `('NOT_LINKED','X')` 거부 ⓑ **`(NULL,'X')` 거부 ← `IS` 가 아니면 통과한다** ⓒ `link_state='linked'` 거부 / **양성** ⓓ `(NULL, NULL)` **통과**(=모름을 적을 수 있다) ⓔ `('LINKED','CMP-X')` 통과. ⚠ 양성이 없으면 "전부 거부하는 CHECK" 도 통과해 검사가 방어선이 아니게 된다 |
  | **㉔** | **`partner_links` 가 증권 식별자를 복제하지 않는다** (D95) — **음성 검사** | ⓐ `partner='insuq'` 행의 `external_ref` 가 **전부 NULL**(`link_state` 무관 — 증권은 `assets.policy_id` 가 정본) ⓑ `SELECT count(*) FROM partner_links WHERE external_ref IN (SELECT policy_id FROM assets WHERE policy_id IS NOT NULL)` = **0** (값 수준 복제 0건) ⓒ finallq 행의 `external_ref` 는 non-null 이고 `'CMP-'` 로 시작 ⓓ `assets` 의 distinct `policy_id` 와 건수를 detail 에 출력해 **"정본은 여기"** 를 보이게 하고, **정본 존재를 판정 조건에도 넣는다**(`and bool(policies)` — Stage 3 reviewer 권고 ③). ⓑ 의 `IN (SELECT policy_id …)` 은 **우변이 공집합이면 무조건 0** 이라, `assets.policy_id` 가 전부 NULL 이 되면 ⓑ 가 **공허참으로 통과**한다. ⛔ **`link_state` 와 `insured` 를 엮는 조건을 넣지 않는다** — 별개 축이다(§A) |
  | **㉕** | `traces.request_chain_id` 컬럼 존재 · nullable (D94-ⓐ) | `PRAGMA table_info(traces)` (검사 ⑲ 의 방식). detail 에 **"쓰는 쪽 없음 — A2A 호출부 미착수, 계측 회귀는 `spikes/a2a_identity_contract.py` 가 본다"** 를 반드시 적는다 |

- **엣지 케이스**:
  | 상황 | 기대 |
  |---|---|
  | `PARTNER_LINKS` 에 회사 행을 `None` 으로 적음 | `NOT NULL` 위반 → 시드 즉시 실패 (설계대로) |
  | `assets` 에 새 `building_id` 가 늘어남 | ㉒-ⓒ 가 **FAIL** → 대장 누락을 즉시 잡는다 (하드코딩 4종이 아니라 **동적 대조**여야 하는 이유 — 검사 ⑬ 와 같은 논리) |
  | `assets.building_id` 가 NULL 인 자산이 생김 | ㉒-ⓒ 의 비교에서 **제외**되고, detail 에 건수가 따로 찍힌다 (조용히 사라지지 않게) |
  | 누가 InsuQ 행에 증권번호를 채움 | ㉔-ⓐⓑ 가 **FAIL** → D95 복제 금지가 실제로 지켜진다 |
  | ㉓ 의 프로브 행이 남음 | `ROLLBACK TO` + `RELEASE` + `commit()` 3종을 ⑩·⑰ 과 동일하게 쓴다. 빠뜨리면 다음 검사가 다른 커넥션에서 잠긴다 |
  | `--with-error-codes` 없이 실행 | `partner_links` 검사 4건은 `error_codes` 와 무관하므로 통과한다. **그래도 이 커맨드로 돌리지 말 것** — §7 |
- **지켜야 할 결정**: D92(seed A안 + `NOT_LINKED` 1건) · D95(정본·복제 금지) · D96 · D62 · D78 · D90(고지 문구는 상태에서 유도) · D12(사람 검수 항목은 표 뒤에 출력).
- **DoD**:
  - `uv run python data/seed.py --with-error-codes` → **전부 통과 (25건)** 이 출력되고
    `SELECT count(*) FROM error_codes` = **65**.
  - 통과 표 **뒤에** 목업 고지 1줄이 출력된다.
  - ㉓ 의 detail 에 **음성 3·양성 2 가 개별 문자열로** 보인다(뭉뚱그린 True/False 금지).
  - ⚠ **검사 번호 ㉒·㉔ 가 `D96`·`D95` 본문이 인용한 번호와 일치**하는지 대조한다
    (Stage 1 reviewer 권고). 번호가 밀리면 **이미 커밋된 D 본문이 조용히 거짓이 된다** —
    번호를 바꿔야 하면 `docs/10_DECISIONS.md` 도 같은 커밋에서 고친다.
  - **뮤턴트 확인 (제출 전 필수)**: `SCHEMA` 의 두 번째 CHECK 를 `IS` → `=` 로 임시 변경 →
    **㉓-ⓑ 가 FAIL** 하는 것을 눈으로 본 뒤 되돌린다. FAIL 하지 않으면 그 검사는 아무것도 지키지 않는다.
    **되돌린 뒤 `git diff --stat data/seed.py` 로 SCHEMA 블록 변경이 0줄임을 확인한다** —
    임시 편집이 남으면 MQ-803 의 산출물이 조용히 뒤집힌다.
    ⚠ **하드 게이트다 (Stage 2 reviewer 권고 1).** MQ-803 이 넣은 `IS` 를 지키는 검사는
    **MQ-805 가 아니라 이 ㉓-ⓑ 가 유일한 행동 방어선**이다(MQ-805 ③ 은 "왜 실패했는지"를
    말해 주는 DDL 파싱 보완이지 대체가 아니다). **FAIL 을 눈으로 본 증거(실제 출력)를
    보고에 그대로 남길 것** — 통과했다는 말만으로는 이 게이트가 작동한 근거가 되지 않는다.
  - `uv run ruff check data`.
  - 회귀 무증감: `trace_persist 17` · `sp3_sse_events 22` · `api_contract 28` ·
    `uv run --with pytest python -m pytest data/rules/test_rules.py -q` → **46건**.

---

#### MQ-805 — 신규 스파이크 `spikes/a2a_identity_contract.py` (27 → **28스위트**)

- **복무 시나리오**: 인프라 (S1 꼬리·S10 꼬리 계약 회귀)
- **변경 파일**: `spikes/a2a_identity_contract.py` (신규)
- **인터페이스**: 다른 스파이크와 동일 규약 — `results: list[tuple[str,bool,str]]` · `check()` ·
  `main()` 이 표를 찍고 실패 시 `SystemExit`. 실행: `uv run python spikes/a2a_identity_contract.py`.
  **임시 DB 전용** — `data/maintq.db` 를 열지 않고 `seed.SCHEMA` 로 빈 DB 를 만든다
  (`trace_persist.make_db()` 와 같은 방식). 마지막에 실 DB **mtime 불변**을 검사한다.
- **핵심 로직 (검사 19건)**:

  | # | 검사 | 무엇을 막는가 |
  |---|---|---|
  | ① | `partner_links` 존재 · 컬럼 6종 · PK 3열 · `subject_ref.notnull=1` | 스키마 드리프트 |
  | ② | **필수 CHECK 2종이 존재**하고 `partner`·`subject_type` 에는 CHECK 가 **없다** | D96-ⓒ. ⚠ **개수 상한을 잠그지 않는다** — 나중에 정당한 CHECK 가 추가될 수 있다. 보는 것은 *"두 개가 있는가 + 저 두 컬럼엔 없는가"* 다 |
  | ③ | **DDL 문자열 파싱** — 두 번째 CHECK 가 `link_state IS 'LINKED'`(null-safe) | **`=` 로 되돌리는 회귀.** 동작 검사(⑤)만 있으면 왜 실패했는지 알 수 없다. 검사 ㉑ 이 DDL 을 파싱해 엔진과 대조한 선례 |
  | ④ | 음성 — `('NOT_LINKED','X')` 거부 | D91 본래 목적 |
  | ⑤ | 음성 — **`(NULL,'X')` 거부** | §3 결함 ①. ③의 동작 증명 |
  | ⑥ | 음성 — `'linked'`·`'LINK'` 등 enum 밖 거부 | 오타 |
  | ⑦ | **양성 — `(NULL, NULL)` 통과** | "모름"을 적을 자리가 사라지는 것(D62·D78 위반)을 막는다 |
  | ⑧ | 양성 — `('LINKED','CMP-X')` **및 `('LINKED', NULL)`** 통과 | 과잉 차단. **후자가 §A(InsuQ 행)의 성립 조건**이다 |
  | ⑨ | PK — `('finallq','company','')` 중복 INSERT 거부 · `subject_ref=NULL` 거부 | D96(SQLite PK NULL 중복) |
  | ⑩ | `traces.request_chain_id` 존재 · nullable · 기본 NULL | D94-ⓐ |
  | **⑪-a** | **행동** — `TraceWriter` 로 `tool_call`·`tool_result`·`block` 을 실제 발행한 뒤 **전 행 `request_chain_id IS NULL`** | **영구 검사.** 호출부가 생겨도 이 세션에는 값이 없어야 한다(무관한 이벤트에 값이 새는 것) |
  | **⑪-b** | **정적** — `backend/**`·`mcp_server/**` 에 `request_chain_id` 를 **쓰는 코드 0건** | D76-2 재발. **호출부가 생기면 이 검사를 뒤집는다**(아래 별항) |
  | ⑫ | `traces.event_type` CHECK 가 **여전히 3종** · `'a2a_call'` INSERT 거부 | D94 가 `event_type` 신설을 기각한 근거 |
  | ⑬ | `TraceWriter` 로 발행한 `payload` == SSE `data` **바이트 동일**, `request_chain_id` 는 그 안에 없다 | D30. 컬럼 추가가 payload 로 새지 않았는가 |
  | ⑭ | `.env.example` 에 4키 존재 · **값이 전부 빈칸** · **수집 키 절 밖**(`외부 데이터 원천` 구분선 위) | 실값 커밋 · D93 ③ 기각 |
  | ⑮ | `mcp_server/**` 에 `MAINTQ_A2A_`·`backend.a2a`·`partner_links` **0건** | **D15·D93** — 도구가 자격증명·파트너 대장을 보지 않는다 |
  | ⑯ | `credentials.load()` 상태 4종 — `not_configured`/`incomplete`/`configured`/`unknown_partner` | 부분 설정으로 호출을 시도하는 상태. **모듈 캐시가 있으면 이 검사가 성립하지 않는다** |
  | ⑰ | `repr(cred)`·`str(cred)`·`status_report()` 어디에도 secret 원문 부재 | 토큰 평문 노출 |
  | ⑱ | `data/maintq.db` **mtime 불변** | 스파이크가 실 DB 를 건드리는 사고 (`trace_persist ⑬` 선례) |

  **⑪ 을 둘로 나눈 이유 (성격이 다르다).** `spikes/trace_persist.py ⑫-b` 주석이 직접 경고한다:
  > *"Sprint 6 이 컬럼만 만들고 **쓰는 쪽이 없어서** 3차 평가까지 전부 NULL 이었다.
  > 컬럼이 있다는 사실만으로 통과시키면 '저장했다고 믿었는데 안 한' 상태가 굳는다."*

  - **⑪-a 는 영구 검사**다. 호출부가 생겨도 *"A2A 와 무관한 세션의 trace 에는 값이 없다"* 는 참이어야 한다.
  - **⑪-b 는 한시 검사**다. 검사 이름에 사실을 적는다 —
    `"⑪-b request_chain_id 를 쓰는 코드 0건 (A2A 호출부 미착수 — 생기면 이 검사를 뒤집는다)"`.
    스파이크 docstring 에 *"호출부가 생기는 스프린트의 DoD 는 ⑪-b 를 **'쓰는 쪽이 계측한다'로 교체**하는 것"*
    을 명시한다. 안 적으면 미래의 누군가가 검사를 **지우고** 넘어간다.

  **⑪-b 판정식 (명세로 박는다).** MQ-803 이 넣는 **DDL 주석이 바로 오탐원**이므로 단순 grep 을 쓰지 않는다.
  - 탐색 대상: `backend/**/*.py` · `mcp_server/**/*.py` — **제외**: `spikes/**` · `data/**` · `docs/**` · `eval/**`
  - 주석·docstring 제외: `ast.parse()` 로 파일을 파싱해 **문자열 상수만** 수집하되,
    `ast.get_docstring()` 이 돌려주는 module/class/function docstring 노드는 **제외**한다.
    (`#` 주석은 `ast` 가 애초에 버린다.)
  - 파일별로 남은 문자열 상수를 이어붙인 뒤:
    ```python
    # ⚠ 아래는 초안이며 **쓰지 말 것** — Stage 4 실측으로 폐기됐다(사유는 바로 아래).
    # STMT = re.compile(r"(?is)(insert\s+into\s+traces|update\s+traces)(.{0,400}?)(?=;|insert\s+into|update\s+|$)")
    ANCHOR     = re.compile(r"(?is)insert\s+into\s+traces|update\s+traces")
    STMT_END   = re.compile(r"(?is);|insert\s+into|update\s+")
    STMT_WINDOW = 400
    # 앵커마다 윈도우를 떠서, 종결자가 있으면 거기서 자르고 없으면 400자까지 본다
    ```
    → **전 파일에서 `hit` 이 0건**이고 **`anchors > 0`** 이어야 통과. (`backend/agent/trace.py:195`
    처럼 SQL 이 인접 문자열 리터럴로 쪼개져 있어도, 상수를 이어붙였으므로 잡힌다.)

    ⚠ **초안 단일 정규식을 폐기한 이유 (Stage 4 교차 검증, 2026-08-13).** 그 정규식은
    lookahead 종결자(`;`·두 번째 `insert into`·`update `·`$`)가 400자 안에 없으면 **매치 자체가
    실패**하고, 그러면 `hit` 이 항상 `False` 가 되어 검사가 **공허하게 통과**한다.
    더 나쁜 것은 **생사가 blob 조립 방식에 좌우된다**는 점이다 — 같은 `backend/agent/trace.py` 라도
    `ast.walk()` 순서 + `""` 조인이면 뮤턴트를 **잡고**, `lineno` 정렬 + `"\n"` 조인(= 구현이 쓰는
    방식)이면 **놓친다**(양쪽 다 실측). 앵커에서 종결자까지의 거리가 창(400)에 **근접**해 있어
    조립 순서·조인 문자·로그 문구 한 줄이 결과를 뒤집는다.
    ⛔ **구체 매치 수를 논거로 적지 말 것** — 소스가 바뀌면 그 수치가 낡고, 수치가 틀리면 이 문단
    전체의 신뢰가 무너진다. 불변인 명제는 *"판정의 생사가 무관한 구현 세부에 좌우된다"* 이고,
    재현이 필요하면 `sql_blob()` 로 blob 을 만들어 두 판정식을 각각 돌려 비교한다.
    즉 결함은 "정규식이 틀렸다"가 아니라
    **"판정식의 생사가 무관한 구현 세부에 좌우된다"** 이다.
    → 그래서 **`anchors > 0` 을 판정에 넣는다.** 앵커가 0이면 *"쓰는 코드가 없다"* 가 아니라
    *"판정식이 죽었다"* 이고, 둘을 구분하지 못하면 이 검사는 언제든 조용히 공허해진다.

- **엣지 케이스**:
  | 상황 | 처리 |
  |---|---|
  | `MAINTQ_A2A_*` 가 개발자 OS env 에 **실제로 설정돼 있음** | ⑯ 은 `os.environ` 을 **직접 조작해 격리**한다(설정/삭제 후 복원). 안 하면 개발자 머신에서만 다른 결과가 나온다 |
  | ⑯ 이 secret 을 assert 문에 담음 | ⚠ **금지** — 실패 메시지에 값이 찍힌다. 길이·상태만 비교한다 |
  | ⑪-b 가 DDL 주석·docstring 에 걸림 | **오탐이다.** `ast` 기반 추출로 원천 차단하고, DoD 에서 직접 확인한다 |
  | `backend.a2a` import 시 `MAINTQ_DB` 오염 | `credentials.py` 는 DB 를 열지 않으므로 무관. ⑬ 전에 `MAINTQ_DB` 를 임시 DB 로 심는다(`trace_persist.main()` 방식) |
  | Windows 소켓 고갈로 1건 실패 | CLAUDE.md 규칙 — **단독 재실행**해 확인하고, 재시도로 통과하면 보고에 적는다 |
- **지켜야 할 결정**: D91·D92·D93·D94·D95·D96 · D30 · D62 · D15 · D76-2(재발 방지).
- **DoD**:
  - `uv run python spikes/a2a_identity_contract.py` → **19건 통과**(실제 건수는 러너 출력 기준).
  - ⚠ **검사 번호 ②·③ 이 `D96` 본문이 인용한 번호와 일치**하는지 대조한다 (Stage 1 reviewer 권고).
    어긋나면 `docs/10_DECISIONS.md` 를 같은 커밋에서 고친다.
  - ⑰ 에 **`dataclasses.asdict(cred)` 경로**를 1건 추가한다 (Stage 1 reviewer 권고) —
    `repr`/`str` 은 막혀 있으나 `asdict`·`astuple` 은 `client_secret` 원문을 그대로 낸다.
    지금은 소비자가 없어 무해하지만, 호출부가 생기는 스프린트의 `JSONResponse(asdict(cred))`
    같은 사고를 앞단에서 막는다.
  - 뮤턴트 5종이 **각각 다른 검사**를 FAIL 시킨다(직접 확인 후 원복):
    ⓐ CHECK `IS`→`=` → ③⑤ / ⓑ `subject_ref` `NOT NULL` 제거 → **①·⑨**(① 에 `subject_ref.notnull` 이
    들어 있어 필연적으로 겹친다 — 1:1 을 강제하면 방어선을 하나 지우는 셈이라 **중복이 정답**이다) /
    ⓒ `.env.example` 4키 제거 → ⑭ / ⓓ `mcp_server/db.py` 에 `partner_links` 참조 1줄 → ⑮ /
    ⓔ **`backend/agent/trace.py` 의 INSERT 에 `request_chain_id` 추가 → ⑪-b**.
    ⚠ **ⓔ 는 반드시 "동작하는" 뮤턴트여야 한다** (2026-08-13 실측) — 컬럼만 넣고 placeholder 를
    안 맞추면(`8컬럼/7값`) `TraceWriter` 쓰기가 실패해 `traces` 가 0행이 되고, ⑬ 이 먼저 죽어
    **표가 인쇄되기 전에 프로세스가 끝난다.** 그러면 ⑪-b 가 평가조차 되지 않는다.
    컬럼과 값을 함께 맞출 것: `VALUES (?,?,?,?,?,?,NULL,?)`.
    (그 크래시 자체는 스파이크 결함이기도 해서 ⑬ 을 `None` 안전하게 고쳤다.)
  - **오탐 확인**: MQ-803 의 DDL 주석과 `trace.py` docstring 이 `request_chain_id` 를 언급해도
    ⑪-b 가 **통과**한다(주석·docstring 제외가 실제로 동작).
  - `ls spikes/*.py` = **28개**.
  - 전체 회귀 재실행: 28스위트 전부 통과 · `seed 25` · `pytest 46`.
  - `uv run ruff check spikes`.

---

#### MQ-806 — `docs/05_DB_SCHEMA.md` 갱신 (⚠ 절 번호 함정)

- **복무 시나리오**: 인프라 (스키마 정본 문서)
- **변경 파일**: `docs/05_DB_SCHEMA.md` (수정)
- **인터페이스**: 문서. 다른 절과 같은 형식(제목 → 인용 요약 → `sql` 블록 → 설계 근거 문단).
- **핵심 로직**:
  1. **개수 표기 정정 — 이게 이 태스크의 함정이다.** 현재 서두(`:4~13`):
     *"9개 → Sprint 6 에서 7개 추가(§11~§17)"* + *"코어 **11개** + Sprint 6 **7개 = 18개**"* +
     *"절 번호는 §1~§9(+§1-B)로 10절, Sprint 6 이 §11 부터 이어받는다 — **§10 은 존재하지 않는다**"*.
     → **Sprint 8 이 §18 `partner_links` 1개를 더한다**:
     - `CREATE TABLE` **18개 → 19개** (코어 11 + Sprint 6 7 + **Sprint 8 1**)
     - 절 **17 → 18** (`§1`~`§9`+`§1-B` 10절 + `§11`~`§17` 7절 + **`§18` 1절**)
     - **`§10` 은 여전히 존재하지 않는다** — 그 문장을 지우지 말 것.
     - `§7` 이 두 테이블(`suppliers`·`supplier_parts`)을 다뤄 **절보다 테이블이 1개 많다**는 설명도 유지.
  2. **`## 18. partner_links — 외부 파트너 subject 매핑 대장 (D91·D92·D95·D96)`** 절 신설.
     - 파일 맨 끝(`§17 residual_curve` 뒤)에 `# Sprint 8 확장 — A2A 신원 식별 기반층` 헤더와 함께.
     - DDL 전문 + **왜 `assets` 확장이 아닌가**(결/grain, D91) + **왜 판정과 식별자를 나누는가**(D78 패턴) +
       **왜 `IS` 인가**(D96, 3값 논리 예시 3줄) + **왜 `subject_ref=''` 인가**(D96) +
       **⛔ 인증 정보가 아니다**(actor/subject).
     - **`assets.policy_id` 와의 관계 (D95)** — *"정본은 `assets.policy_id` 이고 **InsuQ 행의
       `external_ref` 는 NULL 이다**. `partner_links` 는 연결 승인 여부만 담는다. 복제 0건을 ㉔ 가 확인한다."*
       ⚠ *"판정은 `insured` 가 한다(D78) — `policy_id` 는 증권 식별자일 뿐"* 도 함께 적어 오해를 차단한다.
     - 시드 5행 표 + **`BLD-D` 대조군 근거**(MQ-804 의 표를 그대로) +
       **⚠ *"시드 전제(목업) — 실제 발급값·연결 승인이 아니다"*** 고지(㉒-ⓕ 가 검사한다는 사실 포함).
     - ⛔ *"`link_state` 와 `insured` 를 엮지 않는다 — 별개 축"* 을 명시.
  3. **§9 traces 갱신** — DDL 블록에 `request_chain_id` 추가 + D94 근거 문단(원문은 `tool_result` 행의
     `tool_payload`, `event_type` 신설 없음, 인증 헤더 제외) + **`tool_payload` 의 기존 경고 박스와
     같은 형식으로** *"⚠ Sprint 8 은 컬럼만 만든다 — 쓰는 쪽(A2A 호출부)은 미착수이며 전 행 NULL 이 정상"* 박스.
  4. **ERD 개요**에 1줄: `partner_links   ← 외부 파트너 subject 대장. FK 없음(building_id 가 FK 없는 것과 같은 이유) · 인증 정보 아님`.
  5. **자가 검증 목록 표**에 ㉒~㉕ 4행 추가 + 하단 실측 문구를 **`전부 통과 (25건)` + 실행일**로 갱신.
- **엣지 케이스**:
  - "18" 이라는 숫자가 **테이블 수(19)와 절 번호(§18)로 동시에 등장**한다 → 문장마다
    *"절"* 인지 *"`CREATE TABLE`"* 인지 명시할 것. 이 혼동이 CLAUDE.md 가 경고한 바로 그 함정이다.
  - `sprint-6.md`·확장 도구 명세가 `§11`~`§17` 로 참조 중 — **기존 절 번호를 재배치하지 않는다**.
  - `docs/A2A_IDENTITY.md`·`CLAUDE.md`·`00_MVP_SCOPE.md:97` 의 개수 표기는 **MQ-807 소유**다.
- **지켜야 할 결정**: D91·D92·D94·D95·D96 · D78 · D62.
- **DoD**:
  - `rg -n "18개|17절|19개|18절" docs/05_DB_SCHEMA.md` → 새 표기만 남고 옛 표기 0건.
  - `rg -n "§10" docs/05_DB_SCHEMA.md` → *"§10 은 없다"* 문장이 **살아 있다**.
  - `## 18. partner_links` 절과 §9 의 `request_chain_id` 가 **`data/seed.py` 의 DDL 과 바이트 수준으로
    같은 컬럼·CHECK**를 싣는다(직접 대조).
  - 새 절에 **`external_ref` = NULL(InsuQ)** · **목업 고지** · **`insured` 와 엮지 않음** 세 문장이 있다.
  - 자가검증 표가 25행 체계(①~㉕)를 반영한다.

---

#### MQ-807 — 개수·상태 전파 + 거짓 문장 정정 + 이월/사람 TODO 표기

- **복무 시나리오**: 인프라
- **변경 파일** (전부 수정): `CLAUDE.md` · `README.md`(루트) · `docs/README.md` · `docs/00_MVP_SCOPE.md` ·
  `docs/07_BACKLOG.md` · `docs/02_SCENARIOS.md` · `docs/06_REPO_API.md` · `docs/09_RUNTIME.md` ·
  `docs/10_DECISIONS.md`(**마커만**) · `docs/A2A_IDENTITY.md` · `docs/A2A_CONTRACTS.md` ·
  `docs/status/maintq-status.html` · `docs/status/maintq-data-map.html` · `docs/status/maintq-diagrams.html` ·
  `TODO_직접할일.md` · `.claude/agents/reviewer.md`
- **핵심 로직**:
  1. **회귀 기준선 (`CLAUDE.md`)** — 스위트 목록에 **`a2a_identity_contract`** 추가(27→**28종**),
     실측 기준선 줄을 *"spikes **28스위트 / N건** · seed **25건** · pytest **46건** · 프론트 **10개**"* 로 갱신하고
     **스위트별 건수 목록에도 새 스위트를 추가**한다. ⛔ **숫자는 러너 출력을 그대로 옮긴다**(추정 금지).
  2. **`CLAUDE.md` 05 참조 줄** — *"테이블 17절(실제 18개)"* → *"**18절(실제 19개)**"*,
     괄호 설명(`§10` 부재 · `§7` 이 2테이블)은 유지하고 *"Sprint 6 이 §11~§17 로 이어받는다"* 뒤에
     *"**Sprint 8 이 §18 을 더한다**"* 를 잇는다.
  3. **D 범위 표기 5곳** `D1~D94` → **`D1~D96`**: `CLAUDE.md:12` · `README.md:120` ·
     `docs/README.md:17` · `.claude/agents/reviewer.md:3` · `docs/00_MVP_SCOPE.md:144`.
  4. **`docs/10_DECISIONS.md` — D91~D94 의 `⚠설계 확정·미구현` 마커를 부분 구현 문구로 정확히 갱신**
     (⚠ 이 파일에서 **마커 문구 외에는 아무것도 건드리지 않는다**. 신규 D 행·D91 각주는 MQ-801 소유):
     | 결정 | 새 마커 |
     |---|---|
     | D91 | **구현 완료 (Sprint 8)** — DDL 세부는 D96 으로 개정 |
     | D92 | **구현 완료 (Sprint 8)** — 시드 5행 + `NOT_LINKED` 대조군 `BLD-D` |
     | D93 | **env 층 구현 (Sprint 8) · 토큰 캐시 미착수** — 호출부가 없다 |
     | D94 | **ⓐ 컬럼만 구현 (Sprint 8) · ⓑ~ⓔ 미착수** — 나간 요청 원문·`a2a:` 접두어는 호출부와 함께 |
  5. **거짓 문장 정정 (`docs/A2A_IDENTITY.md §8.2-1`)** — *"D78 판정 로직(`INSURANCE-NOTIFY`·
     `test_rules.py`)이 `assets.policy_id` 를 읽으므로 그 컬럼은 못 옮긴다"* 는 **사실과 다르다**
     (§3 미결 ③ 참조). D95 본문과 같은 실측 의존처 목록으로 교체하고, 절을 **종결** 처리한다.
  6. **`docs/A2A_IDENTITY.md` 나머지** — ⓐ §4.3 DDL 스케치를 **D96 반영본**(`subject_ref NOT NULL`, `IS`)으로
     정정하고 *"왜 스케치와 달라졌는가"* 를 각주로 남긴다 ⓑ §5 예시 행을 **§A 확정형**(InsuQ `external_ref` NULL)
     으로 교체 ⓒ §8.1 상태표를 *"✅ 확정 · **Sprint 8 구현 완료(MQ-801~807)**"* 로 ⓓ §8.2-4 종결(㉒~㉕)
     ⓔ §8.2-2(`tool_payload` 조회 수단)·§8.2-3(`risk_profile`)은 **미결로 남긴다**(범위 밖)
     ⓕ **`:408` 의 D 범위 문장은 과거 사실이므로 덮어쓰지 않는다** — *"→ Sprint 8 에서 **D96 까지 확장**"* 을 **덧붙인다**.
  7. **`docs/A2A_CONTRACTS.md`** — *"이 레포가 채워야 할 자리"* 표의 상태를 갱신:
     `partner_links`·seed·자격증명(env 층)·`request_chain_id` → **구현(스키마·시드·env 계층)** ·
     **나간 요청 원문(`tool_payload`)** 은 **미구현 유지**(쓰는 쪽이 없다). 호출 목록 표는 **불변**.
     subject 매핑 행에 *"InsuQ 는 `external_ref` 없이 연결 승인만 — 증권은 `assets.policy_id`(D95)"* 를 명시.
  8. **`docs/06_REPO_API.md`** — `:109` *"**27종**"* → **28종** · 폴더 트리 `backend/` 아래에
     **`a2a/  # 파트너 자격증명 읽기 (D93). MCP 는 참조하지 않는다 (D15)`** 1줄 추가 ·
     스파이크 목록에 `a2a_identity_contract.py` 1줄 추가.
  9. **`docs/09_RUNTIME.md`** — `:117` *"3종 → 27종 · 총 **593건**"*(이미 낡음) → **28종 · 실측 건수** ·
     `:119` *"27스위트를 연속 실행하면"* → **28스위트**.
  10. **`docs/status/*.html` 3파일** — `maintq-status.html:306·557·678·765` ·
      `maintq-data-map.html:228·243·286` · `maintq-diagrams.html:180·854` 의
      *"27스위트 / 616건 / seed 21 / 18테이블"* 표기를 갱신. ⚠ `:477`(618→616 설명)은 **과거 사건 기록**이므로
      건드리지 않는다.
  11. **`docs/00_MVP_SCOPE.md:97`** — *"**17절·실제 테이블 18개** … 자가검증 **21건**"* →
      **18절·19개 · 25건**. **`docs/README.md:40`** — 회귀 줄을 **28스위트/실측 건수 · seed 25** 로.
  12. **`create_repair_record` 이월 표기** — `docs/00_MVP_SCOPE.md`(추가기능 9 · Sprint 7 결과 ⓒ ·
      "Sprint 8 잔여" · 경계 표) · `docs/07_BACKLOG.md` P25 · `docs/02_SCENARIOS.md:82`(S19) ·
      `docs/README.md` 다음 액션 7 을 **`Sprint 9`** 로 정정. ⚠ *"이번에 안 했다"* 를 지우지 말고
      **미룬 사실과 이유(범위 확정)를 남긴다.**
  13. **`TODO_직접할일.md`** — *"A2A 연결 승인·파트너 자격증명 실값 — **미착수**"* 1줄 추가
      (시드는 목업이며 `PARTNER_LINKS_MOCK=True` · `.env` 4키는 비어 있음, 받으면 플래그를 False 로).
      기존 절 구조를 따라 새 절(`## Sprint 8 — A2A`)로 넣는다.
  14. **`docs/README.md` 진행 상태** — Sprint 8 절과 *"다음 액션"* 갱신
      (다음: `create_repair_record` · A2A 호출부는 QMesh 착수 후).
- **엣지 케이스**:
  - 스위트 건수를 **기억으로 적으면 안 된다** — 실행 로그를 옆에 두고 옮긴다.
    CLAUDE.md 는 이 숫자로 *"직전보다 줄었으면 테스트가 사라진 것"* 을 판정한다.
  - **`docs/07_BACKLOG.md` 의 항목을 승격하지 않는다.** P25 는 *"Sprint 8 → Sprint 9"* **표기 정정만**이다.
  - `docs/sprints/**` 의 과거 문서(이 문서 포함)는 **당시 사실의 기록**이므로 숫자를 고치지 않는다.
- **지켜야 할 결정**: 전 범위(D95·D96 포함). **새 결정을 만들지 않는다.**
- **DoD**:
  - **D 범위** — `rg -n "D1~D[0-9]+" -g '!docs/sessions/**' -g '!docs/sprints/**'` 로 **전 히트를 뽑아**
    각각을 **선언 / 과거 기록**으로 분류하고, **선언은 전부 `D1~D96`** 이어야 한다.
    ⚠ **열거 목록만 믿지 말 것** — Stage 5 에서 열거 밖 선언이 둘 나왔다:
    `docs/status/maintq-status.html`(`D1~D88`, **8단계 낡음**) · `.claude/commands/stage.md`(`D1~D39`,
    **57단계 낡아 리뷰 범위를 좁히고 있었다**). 그래서 스코프에 **`.claude/**` 와 `docs/status/*.html`** 를 포함한다.
    ⛔ **기록은 검사에 맞추지 않는다** — 전역 카운트로 재면 `A2A_IDENTITY` 의 **D 번호 부여 이력**이
    섞여, 검사를 맞추려고 **과거 기록의 표기를 고치는** 일이 벌어진다(Stage 5 에서 실제로 발생 → 원표기 복원).
  - `rg -n "a2a_identity_contract" CLAUDE.md docs/06_REPO_API.md` → 각 파일에 존재(CLAUDE.md 는 **2곳**).
  - `rg -n "27스위트|593건|616건|17절|테이블 18개|seed 21" -g '!docs/sprints/**' -g '!docs/status/maintq-status.html:477'`
    → 갱신 누락 0건(과거 기록 줄 제외).
  - `create_repair_record`·`flags` 에 대해 **일정을 Sprint 8 로 지정하는 줄이 0건**이다.
    ⚠ *"Sprint 8 은 이 도구를 만들지 않았다"* 류의 **이월 사실 서술은 남긴다**(그게 이 태스크의 요구다).
    ⛔ **문자열 부재로 재지 말 것** — `docs/sprints/**`·`docs/sessions/**` 는 당시 기록이라 원리상 0건이
    불가능하고, `create_repair_record` 토큰이 **같은 줄에 없는** 일정 지정(status HTML 7곳)은
    그 grep 이 놓친다(Stage 5 reviewer 실측).
    ✅ **탐지축을 도구명이 아니라 스프린트 번호로 뒤집는다**:
    `rg -n "Sprint 8" docs/status/*.html docs/00_MVP_SCOPE.md docs/07_BACKLOG.md docs/02_SCENARIOS.md`
    `  docs/README.md TODO_직접할일.md` → 히트 전건을 **일정 지정 / 이월 사실 서술**로 육안 분류.
    (이번에 놓친 7곳이 전부 이 grep 에 걸린다. 다음 스프린트에는 토큰이 `Sprint 9` 로 바뀐다.)
  - `rg -n "policy_id 를 읽으므로|판정 로직.*policy_id" docs/A2A_IDENTITY.md` → **0건**(거짓 문장 제거 확인).
  - ⚠ **`A2A_IDENTITY.md §4.3` 의 DDL 스케치를 실제 `data/seed.py` 와 동기화**한다. 현재 **3곳이 어긋나 있다**
    (Stage 2 시점 실측): ⓐ `subject_ref TEXT` → **`NOT NULL`** 이고 회사 결은 `''`(주석의 *"company 는
    NULL"* 은 **거짓**) ⓑ `CHECK (link_state = 'LINKED' ...)` → **`IS`** ⓒ `linked_at DATE` → **`DATETIME`**.
    셋 다 **D96 이 supersede 한 것**이므로 스케치를 고치거나, 그 블록에 *"D96 이전 초안"* 표기를 단다.
    ⛔ 고치지 않으면 §4.3 이 **`§8.2-1` 거짓 문장과 같은 유형의 부채**가 된다.
  - `rg -n "설계 확정·미구현" docs/10_DECISIONS.md` → **D91~D94 행에 0건**(부분 구현 문구로 대체).
  - ⚠ **조건부 이월 (Stage 2 reviewer 권고 2)** — `data/seed.py` 의 `request_chain_id` DDL 주석이
    *"`spikes/a2a_identity_contract.py` 가 그 사실을 명시적 라벨로 기록한다"* 고 **현재형**으로 쓴다.
    **MQ-805 가 누락되거나 파일명이 바뀌면 이 주석을 반드시 정정**하라(미래형으로 바꾸거나 파일명 갱신).
    없는 파일을 계속 가리키면 **D76-2 재발을 막으려고 쓴 문장이 그 자체로 거짓**이 되어,
    이번 스프린트가 정정하기로 한 `A2A_IDENTITY §8.2-1` 거짓 문장과 **같은 유형의 부채**가 된다.
    MQ-805 가 정상 완료됐으면 이 항목은 해당 없음으로 넘긴다.
  - `ls spikes/*.py` 개수(28)와 CLAUDE.md·06_REPO_API 목록이 일치.
  - `/done` 의 D 범위 표기 정합성 점검을 통과한다.

---

## 6. 완료 기준 (스프린트 전체)

| # | 기준 | 판정 |
|---|---|---|
| 1 | `partner_links` 가 **"식별자만 있고 승인은 없는 상태"를 3상태 전부에서** 거부한다 | seed ㉓ 음성 3 + spike ④⑤⑥. **`(NULL,'X')` 거부가 핵심** |
| 2 | **"모른다"를 여전히 적을 수 있다** (D62·D78 무회귀) | seed ㉓ 양성 ⓓ · spike ⑦ |
| 3 | **`NOT_LINKED` 대조군 1건**이 시드에 있고, **부보 축과 섞이지 않는다** | seed ㉒ · ㉔(엮는 조건 부재) |
| 4 | **증권 식별자가 `partner_links` 에 복제되지 않았다** (D95·§A) | seed ㉔ ⓐⓑ · spike ⑧(`LINKED`+NULL 통과) |
| 5 | **기존 trace 회귀가 한 건도 수정되지 않았다** | `trace_persist 17` · `sp3_sse_events 22` · `api_contract 28` **그대로 통과** · `git diff --stat` 에 세 파일 부재 |
| 6 | `request_chain_id` 가 **"쓰는 쪽 없음"으로 명시 기록**된다 (D76-2 재발 방지) | spike **⑪-a(행동)·⑪-b(정적)** 분리 · ⑪-b **검사 이름에 사실이 있다** |
| 7 | 자격증명이 **MCP 에서 보이지 않는다** (D15·D93) | spike ⑮ |
| 8 | **목업임을 시스템이 스스로 말한다** | seed ㉒-ⓕ + 통과 표 뒤 고지 + `TODO_직접할일.md` 1줄 |
| 9 | 회귀 총량이 **늘기만 한다** | spikes 27→**28스위트** · seed 21→**25** · pytest **46 불변** · 프론트 **10 불변** |

## 7. 회귀 실행 (CLAUDE.md 그대로 — 바꾸지 말 것)

```bash
uv run python data/seed.py --with-error-codes     # ⚠ 맨몸 실행 금지 → error_codes 0행 리셋
                                                  # ⛔ --today 금지 → 검사 ⑤ 위양성 FAIL
#   재시드 후 확인:  SELECT count(*) FROM error_codes  → 65
uv run python spikes/a2a_identity_contract.py     # ★ 신규
uv run python spikes/trace_persist.py             # 17건 — **수정 금지 대상**
uv run python spikes/sp3_sse_events.py            # 22건 — **수정 금지 대상**
uv run python spikes/api_contract.py              # 28건
uv run --with pytest python -m pytest data/rules/test_rules.py -q   # 46건
uv run ruff check data backend mcp_server spikes
```

> ⚠ **Windows 소켓 고갈** — 28스위트를 연속 실행하면 매번 **다른** 스위트가 1건 실패할 수 있다
> (`OSError: [WinError 10014]`). **코드 결함이 아니다.** 실패한 스위트는 **반드시 단독 재실행**하고,
> 재시도로 통과하면 그 사실을 보고에 적는다. 재시도해도 실패하면 진짜 회귀다.

프론트는 변경이 없으므로 `tsc`·`next build` 를 돌릴 필요가 없다 — **돌려야 한다면 범위를 벗어난 것이다.**

## 8. 이 스프린트에서 하지 않는 것 (태스크로 만들지 말 것)

| 항목 | 근거 |
|---|---|
| A2A HTTP 어댑터 · 오케스트레이터 · 실제 스킬 호출 | 사용자 확정 범위 밖 (QMesh 미착수) |
| 액세스 토큰 캐시 | 소비자 없음 — 만들면 회귀 부담만 는다 (D56 의 OpenAI 미착수 논리) |
| `/health` 에 `a2a` 상태 노출 · `backend/main.py` 수정 | 호출부가 생길 때 함께. 지금 넣으면 "연결된 것처럼" 보인다(D87 태도) |
| **`link_state` ↔ `insured` 를 엮는 검사·컬럼** | 별개 축이다(§A). 엮으면 **D78 이 분리한 두 사실을 되붙인다** |
| `risk_profile`(건물 마스터) | `A2A_IDENTITY §8.2-3` — 선행 조건 아님. `building_id` 는 지금도 FK 없이 쓴다 |
| `tool_payload` 조회 API | `§8.2-2` — A2A 실호출이 생길 때 |
| `eval/run_eval.py` 의 `dump_traces` 에 `request_chain_id` 추가 | 전 행 NULL 이라 실을 값이 없다. **값이 생기는 스프린트가 함께 고친다** |
| `event_type` 에 `a2a_call` 추가 · `payload` 에 A2A 필드 | **D94 가 명시적으로 기각**. 하는 순간 D30·D14·D22 와 2스위트가 깨진다 |
| `mcp_server/db.py` 에 `partner_links` 쓰기 차단 트리거 | 읽기 커넥션이 이미 `mode=ro` 라 **쓰기는 물리적으로 불가**. 남은 위험("읽어서 쓴다")은 spike ⑮ 가 잡는다 |
| **D97 신설** | 결함 ①②는 **원인이 하나** — D96 한 건으로 등재한다 |
| `create_repair_record`(P25·S19) | **Sprint 9 이월** — 사용자 확정 |
| `docs/07_BACKLOG.md` 항목 승격 | 금지. P25 는 표기 정정만 |

---

## Stage 1 완료 (2026-08-13)

**커밋**: `2f2b7f6` — `[A2A] Sprint 8 Stage 1 — D95·D96 등재 + 파트너 자격증명 읽기 층`
**브랜치**: `sprint-8-a2a-identity`

### MQ-801 — 결정 2건 등재 + D91 각주
- `docs/10_DECISIONS.md` — D95(101행) · D96(102행) 추가, D91(97행)에 supersede 각주(취소선 없음)
- DoD 전부 충족: `^| D9[56] ` **2행** · `D96` **2건**(각주+본문) · `D97` **0건** ·
  인용 5곳 실재 · 금지 문장 **0건**
- D 범위 표기 5곳·D91~D94 마커는 **미접촉**(MQ-807 소유)

### MQ-802 — 파트너 자격증명 읽기 층
- `backend/a2a/__init__.py`(신규) · `backend/a2a/credentials.py`(신규) · `.env.example`(44~47행)
- import 3개(`os`·`dataclasses`·`typing`) — DB·네트워크 접근이 **구조적으로 불가능**
- 엣지 케이스 표 8항목 전부 실측 확인. 누출면 9종(`repr`·`str`·f-string·`format`·`%s`·
  list/dict repr·`status_report`·예외) **전부 leak=False**
- `raise` **0건** → 예외 메시지 누출 경로 없음

### 회귀
spikes **27스위트 / 616건** · seed **21건**(`error_codes` 65) · pytest **46** · ruff 통과.
기준선 대비 **증감 0**. 소켓 고갈 미발생 — **단독 재실행한 스위트 없음**.
⚠ `eval/run_eval.py`·S1~S4 스모크는 **돌리지 않았다** — 기존 코드 경로 변경이 0이고
신규 모듈을 import 하는 곳이 없어 지표가 움직일 근거가 없다.

### reviewer
**PASS** — 블로커 0 · 필수 수정 0. D95 인용 5곳을 실물 대조로 검증.
권고 3건 중 2건을 **MQ-804·MQ-805 DoD 에 반영**했다(검사 번호 정합 대조 · `asdict` 누출 경로).
나머지 1건(경로 명시 스테이징)은 이번 커밋에서 이미 적용.

### 다음
`/stage 2` — MQ-803 (`data/seed.py` DDL: `partner_links` + `traces.request_chain_id`)

---

## Stage 2 완료 (2026-08-13)

**커밋**: `cb58333` — `[A2A] Sprint 8 Stage 2 — partner_links DDL + traces.request_chain_id`

### MQ-803 — `data/seed.py` DDL
- `SCHEMA` 문자열만 **+28 / -0**. 삭제 0줄이므로 MQ-804 소유 구역(마스터 상수·시드 함수·
  `verify()`·`main()`) 무접촉이 **diff 자체로 증명**된다.
- `PRAGMA table_info(traces)` — `request_chain_id` cid=**7**, notnull=0, `tool_payload`(6)와
  `ts`(8) 사이. HEAD 의 SCHEMA 를 인메모리 복원해 대조한 결과 **기존 8컬럼 이름·순서 완전 동일**.
- `PRAGMA table_info(partner_links)` — 6컬럼, `subject_ref.notnull=1`, PK 3열 복합.
- CHECK 실증 INSERT **7케이스**(명세는 4케이스 요구, 구현이 양성 대조·PK 중복까지 늘림) —
  전부 기대대로. 확인 후 재시드로 원상복구(`partner_links` 0행 · `traces` 0행 · `error_codes` 65).

### 회귀
spikes **27스위트 / 616건** · seed **21** · pytest **46** · ruff 통과. 기준선 대비 **증감 0**,
**재시도 0건**(소켓 고갈 미발생). `trace_persist 17` · `sp3_sse_events 22` · `api_contract 28`
**무수정 통과** — D94 의 채택 근거가 실측으로 성립했다. 근본 원인까지 확인됨:
`traces` 접근이 전부 명시적 컬럼 목록이고 `SELECT *` 가 레포 전체 0건이라 중간 위치
컬럼 삽입이 **구조적으로 무해**하다.

### reviewer
**PASS** — 블로커 0 · 필수 수정 0 · 권고 2. 권고 2건 모두 계획에 반영:
- 권고 1 → MQ-804 ㉓-ⓑ 뮤턴트 확인을 **하드 게이트**로 명시(FAIL 실제 출력을 보고에 남길 것).
  `IS` 를 지키는 **행동 방어선은 MQ-805 가 아니라 ㉓-ⓑ 가 유일**하다는 판단에 따른 것.
- 권고 2 → MQ-807 DoD 에 **조건부 이월** 1건(주석이 가리키는 스파이크가 안 생기면 주석 정정).

### ⚠ 남은 공백 (Stage 3·4 가 메운다)
회귀 616건은 이번 변경이 **"깨지지 않았다"만 증명하고 "새 계약이 맞다"는 증명하지 않는다**
(eval-runner 관찰). `partner_links` 의 두 CHECK 와 `request_chain_id` 의 nullable 성질을
검증하는 스파이크가 **아직 0건**이다 — MQ-804(행동)·MQ-805(정적)가 채운다.

### 다음
`/stage 3` — MQ-804 (시드 5행 + 자가검증 4건 21→25 + 목업 고지)

---

## Stage 3 완료 (2026-08-13)

**커밋**: `06f264b` — `[A2A] Sprint 8 Stage 3 — partner_links 시드 5행 + 자가검증 4건 (21→25)`

### MQ-804 — 시드 + 자가검증
- `PARTNER_LINKS` 5행 · `PARTNER_LINKS_MOCK` · `seed_partner_links(con, now_utc: datetime)` ·
  `partner_links_caveat()` · `verify()` 검사 **㉒~㉕** · `main()` 고지 출력 · 모듈 docstring.
- **SCHEMA 블록 변경 0줄** — diff hunk 가 전부 1071행 이후(SCHEMA 는 47~389).
- `linked_at` **UTC 실측 확인**: `08:16` / `CURRENT_TIMESTAMP` `08:19` / 로컬 `17:19`.

### 하드 게이트 — 뮤턴트가 실제로 작동했다
`IS` → `=` 로 임시 변경 시 ㉓ 의 5개 중 **음성ⓑ 하나만** 거부→통과로 뒤집혔다.
나머지 4개는 그대로 — 이 검사가 **정확히 `IS`/`=` 하나를 겨냥**한다는 증거다.

### reviewer 권고 4건 반영 (같은 커밋)
| # | 내용 | 근거 |
|---|---|---|
| ② | ㉒-ⓕ 에 **접두 기호 축** 추가 | 문구 축만 보면 *"`[사람 확인]` ⚠ … 목업 …"* 자기모순 라벨이 통과 |
| ③ | ㉔ 판정에 `and bool(policies)` | `IN (SELECT …)` 우변이 공집합이면 **공허참**. 사본에서 `policy_id` 전부 NULL → ㉔ 가 실제로 **FAIL** 하는 것 확인 |
| ④ | ㉒-ⓒ 를 `building` 결로 한정 | insuq 에 company 결이 늘면 `''` 로 어긋나는데 "대장 누락"으로 오독 |
| ① | D96-ⓓ 에 *"기준은 `--today` 가 아니라 벽시계 UTC"* 명시 | 시그니처가 계획 스케치와 달라진 근거 |

권고 ⑤(㉓ 프로브 잔존 자기확인)는 **보류** — ⑩·⑰·⑳ 이 같은 구조라 이번 스프린트 고유 결함이 아니다.

### 회귀
seed **25건**(21→25, 이 태스크의 산출물) · `error_codes` 65 · spikes **27스위트 616건**(증감 0) ·
pytest **46** · ruff 통과 · **재시도 0건**.

### 다음
`/stage 4` — MQ-805 (`spikes/a2a_identity_contract.py` 신설, 27→28스위트)

---

## Stage 4 완료 (2026-08-13)

**커밋**: `e8b88aa` (스파이크) · `f65d30e` (liveness 앵커 규약 + P30)

### MQ-805 — `spikes/a2a_identity_contract.py` 19건
- spikes **27 → 28스위트**, 총 **616 → 635건**. 기존 27스위트 **전부 무증감**.
- 임시 DB 전용. ⑱ 이 실 DB mtime 을 보고, eval-runner 가 바깥에서 **sha256 까지** 대조해 동일 확인.
- ⑪-a(행동·영구) / ⑪-b(정적·한시) 분리. ⑪-b 는 **검사 이름 자체에** *"A2A 호출부 미착수 —
  생기면 이 검사를 뒤집는다"* 를 적었고, 모듈 docstring 에 *"지우는 것이 아니라 '쓰는 쪽이
  계측한다'로 교체하는 것"* 을 명시했다.
- `data/seed.py` 의 두 문장(DDL 주석·검사 ㉕ detail)이 가리키던 파일이 **실재하게 됐다.**

### ⚠ 이번 스테이지의 핵심 발견 — 계획서 판정식이 조건부로 죽어 있었다
초안 정규식은 lookahead 종결자가 창(400) 안에 없으면 **매치 자체가 실패**해 `hit` 이 항상
`False` 가 되고 검사가 **공허하게 통과**한다. 교차 검증 결과 **생사가 blob 조립 방식에
좌우됐다** — `ast.walk()` 순서 + `""` 조인이면 뮤턴트를 **잡고**, `lineno` 정렬 + `"\n"` 조인
(구현이 쓰는 방식)이면 **놓친다**.
→ 앵커+윈도우로 쪼개고 **`anchors > 0` 을 판정에 포함**. 앵커 0 = *"쓰는 코드가 없다"* 가
아니라 *"판정식이 죽었다"* 다. 초안은 지우지 않고 **폐기 표기**로 남겼다.
→ 이 교훈을 **CLAUDE.md 회귀 절에 규약으로 등재**하고, 같은 결함이 남은 기존 스위트 2건을
**P30** 으로 백로그에 넣었다(`agent_loop_contract ⑯` · `ui_honesty_contract C1·C2`).

### reviewer 권고 반영
| 내용 | 근거 |
|---|---|
| ① 에 `linked_at` **선언 타입 `DATETIME`** 검사 추가 | SQLite 는 `DATE`/`DATETIME` 둘 다 NUMERIC affinity 라 되돌려도 값은 그대로 저장되고 seed ㉒-ⓓ 도 통과한다 — **사람이 확정한 D96-ⓓ 를 잠그는 검사가 없었다.** 뮤턴트 확인: `DATETIME`→`DATE` 면 ① FAIL |
| ⑮ 평문 검색이 **의도**임을 주석에 명시 | ⑪-b 와 달리 주석·docstring 을 안 걷어낸다. 도구가 `partner_links` 를 docstring 에서라도 부를 이유가 없다(D15). `ast` 로 바꾸면 약해진다 |
| 뮤턴트 ⓑ → **①·⑨** 로 명세 정정 | 1:1 을 강제하면 방어선을 하나 지우는 셈. 중복이 defense-in-depth |
| 구체 매치 수를 논거에서 제거 | 소스가 바뀌면 낡고, 틀리면 문단 전체 신뢰가 무너진다 |

### 회귀
spikes **28스위트 635건** · seed **25** · pytest **46** · ruff · **재시도 0건**.
실 DB sha256 불변 · `partner_links` 5 · `error_codes` 65.

### 다음
`/stage 5` — MQ-806(`05_DB_SCHEMA` §18 신설) · MQ-807(개수·상태 전파) **병렬**

---

## Stage 5 완료 (2026-08-13) — 스프린트 종료

**커밋**: `da653f8` — `[A2A] Sprint 8 Stage 5 — 05_DB_SCHEMA §18 신설 + 개수·상태 전파`

### MQ-806 · MQ-807
- `05_DB_SCHEMA` 절 **17→18** · `CREATE TABLE` **18→19**. *"§10 은 없다"* · *"§7 이 2테이블"* 유지.
  §18 DDL 은 `data/seed.py` 와 **주석까지 바이트 동일**.
- §9 에 `CHECK (event_type IN (...))` **복원** — 본문 산문은 *"CHECK 가 3종만 허용"* 이라 하는데
  DDL 블록에 그 줄이 없어 **문서가 자기 진술과 어긋나 있었다.**
- D 범위 5곳 `D1~D96` · 스위트 28종/635건 · 테이블 19개 전파. D91~D94 마커를 부분 구현 문구로.
- `A2A_IDENTITY §8.2-1` 거짓 문장 제거 · `§4.3` DDL 스케치 동기화(3곳).

### ⚠ 이 스테이지가 남긴 교훈 — 문자열 카운트 DoD 가 **세 번 뚫렸다**

reviewer 가 두 라운드에 걸쳐 잡았고, 셋 다 **grep 사각지대**였다.

| # | 무엇 | 왜 안 걸렸나 |
|---|---|---|
| F1 | status HTML 낡은 수치 5곳 — 특히 **`D1~D88`(8단계 낡음)** | 패턴이 `D1~D94` 만 본다. **몇 단계 낡으면 패턴 자체를 벗어난다** |
| F2 | *"Sprint 8"* 일정 지정 **7곳** | `create_repair_record` 토큰이 **같은 줄에 없다.** `maintq-status:643` 은 *"쓰기 도구는 Sprint 8(P25)"* 로 P25→Sprint 9 정정과 **정면 충돌**하고 있었다 |
| F3 | 과거 기록 표기를 **DoD 때문에 고친 것** | 검사가 통과했다 — **대상이 검사에 맞춰졌기 때문에** |

**F3 이 제일 나쁘다.** `A2A_IDENTITY:446`(D 번호 부여 **이력**)의 표기를 카운트 맞추려고 고쳤고,
그래서 DoD 는 초록이 됐다. **원표기를 복원하고 DoD 쪽을 고쳤다** — *기록은 검사에 맞추지 않는다.*

### 그래서 DoD 를 고쳤다 (다음 스프린트가 같은 함정을 밟지 않도록)
- **D 범위** — 전 히트를 뽑아 **선언/과거기록으로 분류**하는 2단. 스코프에 **`.claude/**`·`docs/status/*.html`** 포함.
- **이월 표기** — 탐지축을 **도구명이 아니라 스프린트 번호**로 뒤집는다.
- **`.claude/commands/stage.md` 가 리뷰 범위를 `D1~D39` 로 좁히고 있었다**(**57단계 낡음**) →
  *"전 범위"* 로 바꾸고 **번호를 박지 말라**고 명시. 이건 문서가 아니라 **지시문**이라 실제 리뷰가 좁아진다.

### 내 부분 수정이 만든 모순도 닫았다
`data-map:238` 만 8조문으로 고쳐 **같은 페이지가 7과 8을 동시에** 말하게 됐다.
계층 1 실측(**8파일 전부 `FETCHED` · 8,197자** · `KR-CITA-ENF-31` 08-13 해소)으로 status HTML **3파일 11곳** 정정.
끝난 사람 승인이 *"대기"* 배지로 남아 있던 것도 고쳤다 — **D87 의 역방향**(해소된 것을 미완으로 렌더).

### 회귀
spikes **28스위트 635건** · seed **25** · pytest **46** · ruff · **재시도 0건** · 프론트 라우트 **10개**(실측).
**코드 변경 0** — 문서 전용 스테이지.

---

## Sprint 8 종료

| 스테이지 | 커밋 | 산출 |
|---|---|---|
| 1 | `2f2b7f6` | D95·D96 등재 + `backend/a2a/credentials.py` |
| 2 | `cb58333` | `partner_links` DDL + `traces.request_chain_id` |
| 3 | `06f264b` | 시드 5행 + 자가검증 4건 (21→25) |
| 4 | `e8b88aa`·`f65d30e`·`389f9fa` | 스파이크 19건 (27→28스위트) + liveness 규약·P30 |
| 5 | `da653f8` | `05_DB_SCHEMA §18` + 개수·상태 전파 |

**다음** — `/stage` 없음. `/done` 으로 세션 마무리.
Sprint 9 는 `create_repair_record`(P25·S19, **두 번 이월**). A2A 호출부는 QMesh 착수 후다.
