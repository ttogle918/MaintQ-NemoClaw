# A2A 신원 식별 — MaintQ 측 현황 조사 및 설계 메모

> 작성 2026-08-13. **조사·정리 문서이며 구현은 하지 않았다.**
> 상대 문서: `A2A_Q/docs/A2A_IDENTITY.md`(2026-08-13 개정, QMesh 확정본) ·
> `FinAllQ/docs/A2A_IDENTITY.md`(원본 조사, 훨씬 상세). 절 구성은 나중에 합치기 쉽도록
> FinAllQ 문서의 뼈대(조사 → 스키마 판단 → 온보딩 → 미해결)를 따라갔다.
>
> A2A_Q §"각 프로젝트가 지금 준비해야 할 것" 표의 MaintQ 행이 **"요청됨, 회신 대기"**
> 상태다. **이 문서가 그 회신이다.**

## 0. 두 층을 구분한다

FinAllQ 문서와 같은 구분을 쓴다.

| 층 | 내용 | 이 문서의 상태 |
|---|---|---|
| **① 조사** | 지금 이 레포에 무엇이 있고 무엇이 없는가 (실측) | §1~§3. 확정 사실 |
| **② 설계** | 무엇을 어떤 모양으로 채울 것인가 | §4~§7. **2026-08-13 확정.** 아직 **코드는 없다** — D 번호 부여와 구현은 별도 |

## 0.5. 네 줄 요약

1. **`building_id`가 가리키는 테이블이 아예 없다.** `assets.building_id`는 FK 없는 맨 `TEXT`
   컬럼이고, 참조 대상인 `risk_profile`(건물 마스터)은 `11_ASSET_LIFECYCLE §10-2`에
   **제안만 되어 있고 미구현·후순위**다. 즉 `finallq_company_id`를 붙일 자산 마스터가
   그 자체로 없다.
2. **`policy_id`는 이미 있다.** `assets.policy_id`에 `POL-2026-FIRE-01`이 9건 중 8건에
   시드돼 있다. **`insuq_policy_id`를 새로 만들면 안 된다** — 기존 컬럼과 이중 진실이 된다.
3. **`request_chain_id` 자리는 trace에 없다.** 전제가 사실과 다르다 — §6에서 정정한다.
   `traces` 테이블에는 없고, `docs/A2A_CONTRACTS.md`의 **payload 스펙 문장**에만 있다.
4. **"이 값만으로 승인하면 안 된다"는 요구는 이 레포가 이미 푼 문제다** — D78(`insured` ↔
   `policy_id` 분리)이 정확히 같은 모양이다. §4는 그 패턴을 그대로 재사용한다.

---

## 1. 조사 ① — 자산 마스터에 외부 식별자 자리가 있는가

### 1.1 결론: 없다. 그리고 붙일 테이블 자체가 없다

`assets` 실측 (`docs/05_DB_SCHEMA.md §11`, `data/seed.py:86~`):

```sql
CREATE TABLE assets (
  asset_id      TEXT PRIMARY KEY,          -- 'AST-L3-CONV'
  name          TEXT NOT NULL,
  category      TEXT NOT NULL,
  line_id       INTEGER NOT NULL,
  building_id   TEXT,     -- risk_profile(F6) 자리. 참조 테이블 없으므로 FK 없음
  ...
  insured       BOOLEAN,  -- D78. NULL=모름 / 0=확인된 미부보 / 1=부보
  policy_id     TEXT,     -- 증권 식별자 전용. 판정은 insured 가 한다 (D78)
  ...
);
```

- 외부 시스템 참조 컬럼(`finallq_company_id` 류)은 **0개**다.
- `building_id`는 `'BLD-A'`~`'BLD-D'` 4종이 9개 자산에 시드돼 있으나 **참조 테이블이 없다.**
  스키마 주석이 직접 그렇게 말한다 — *"참조 테이블 없으므로 FK 없음"*.

### 1.2 "건물/자산 마스터(목업)"의 실제 위치

질문에서 말한 백로그 항목은 **`docs/07_BACKLOG.md`에 없다.** 실제 위치는
`docs/11_ASSET_LIFECYCLE.md §10-2`의 신규 테이블 4종 제안 중 하나다:

```
risk_profile       건물 단위 속성
  building_id, fire_handling, hazmat_volume, power_capacity,
  product_type, risk_grade, risk_grade_updated_at
```

그리고 같은 절이 이렇게 못박아 뒀다 — *"넷 중 내부 활용도가 가장 낮으므로 **후순위**로 둔다."*

> ⚠ **이게 A2A에는 역전된다.** 내부(처분 판정·실사)에서 가장 쓸모가 적어서 후순위였던
> 테이블이, **S7·S11·S14(InsuQ 통지)에서는 가장 먼저 필요한 테이블**이 된다.
> `risk_grade`·`fire_handling`은 S14("위험등급 변동 통지")가 보낼 내용 그 자체다.
> 후순위 판단의 근거가 A2A 편입으로 바뀌었다는 점은 기록해 둘 가치가 있다.

### 1.3 `policy_id`는 이미 있고, 이미 denormalize 돼 있다

| 자산 | `insured` | `policy_id` |
|---|---|---|
| `AST-L1-CONV` … `AST-L4-DUST` (8건) | 1 | `POL-2026-FIRE-01` |
| `AST-L3-LIFT` | 0 (확인된 미부보) | NULL |

**8건이 같은 증권 하나를 공유한다.** 즉 `policy_id`는 이름과 달리 자산 단위 사실이
아니라 **사실상 건물·회사 단위 사실이 자산 행에 복제된 것**이다. (화재보험이 원래
그렇다 — 목적물은 건물이다.)

이 사실이 §4의 컬럼 배치 판단을 결정한다.

---

## 2. 조사 ② — 세 식별자의 "결(grain)"이 서로 다르다

이게 이 조사의 핵심이다. 세 값은 같은 층위가 아니다.

| 값 | 소유 도메인 | 실제 결 | 지금 저장 위치 |
|---|---|---|---|
| `finallq_company_id` | FinAllQ | **회사** 1개 | 없음 |
| `policy_id` | InsuQ | **건물**(≈증권 목적물) | `assets.policy_id` — 자산마다 복제 |
| `building_id` | MaintQ | **건물** | `assets.building_id` — 자산마다 복제, 참조 테이블 없음 |
| `asset_id` | MaintQ | **자산** | `assets.asset_id` (PK) |

`finallq_company_id`를 `assets`에 그냥 얹으면 **9행에 같은 값이 복제**된다.
`policy_id`가 이미 그 상태이고, 자산이 늘면 drift가 시작된다(한 행만 안 고쳐지는 종류의
사고). D60이 "원본은 하나, 나머지는 사본"을 원칙으로 삼은 것과도 어긋난다.

**따라서 `assets`에 컬럼을 더 붙이는 방향은 권장하지 않는다.** §4 참조.

---

## 3. 조사 ③ — 지금 trace 구조 위에 A2A를 실을 수 있는가

`traces` 실측 (`docs/05_DB_SCHEMA.md §9`, `data/seed.py:207~227`):

```sql
CREATE TABLE traces (
  id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, seq INTEGER NOT NULL,
  event_type TEXT NOT NULL, tool TEXT, payload TEXT NOT NULL,
  tool_payload TEXT, ts DATETIME DEFAULT CURRENT_TIMESTAMP,
  CHECK (event_type IN ('tool_call','tool_result','block')),
  UNIQUE (session_id, seq)
);
```

**`request_chain_id` 컬럼은 없다.** 레포 전체 grep 결과 이 문자열은
`docs/A2A_CONTRACTS.md`의 payload 스펙 두 줄에만 존재한다 — 즉 **"계약 문서에 자리가
있다"이지 "trace에 자리를 마련해뒀다"가 아니다.** §6에서 다시 다룬다.

주의할 제약 2가지:

- `event_type`에 **DDL CHECK 3종**이 걸려 있다. A2A 호출을 `a2a_call` 같은 새 이벤트로
  흘리려면 CHECK·D14·D22(SSE 4종 고정)를 동시에 건드려야 하고, `sp3_sse_events`·
  `trace_persist`가 즉시 깨진다. **이벤트 종류를 늘리는 방향은 비싸다.**
- `payload`는 **SSE로 나간 바이트와 동일**이 계약이다(D30, `trace_persist ②`가 바이트
  대조). payload에 A2A 필드를 끼워 넣는 것도 막혀 있다.

---

## 4. 결정 ① — 스키마: D78 패턴을 그대로 쓴다 (subject 지정용, 인증 아님)

### 4.1 요구사항을 다시 읽으면

QMesh 결정 1은 이렇게 말한다:

> `building_id`·`company_id`는 이제 "인증 정보"가 아니라 **"이 요청이 누구 건인지
> 지정하는 값(subject)"**으로만 쓰인다. 실제 인증은 파트너 토큰(actor)이 한다.

**스키마가 이 성격을 어떻게 표현하는가**가 질문의 핵심이다. 컬럼 주석에 "인증용 아님"
이라고 쓰는 건 지켜지지 않는다 — 주석은 강제력이 없다.

### 4.2 이 레포는 이미 같은 문제를 풀었다 — D78

`docs/05_DB_SCHEMA.md`가 `insured`/`policy_id`를 나눈 이유:

> `policy_id` 한 컬럼이 "부보돼 있는가"와 "증권 번호가 무엇인가" 두 질문을 겸하면
> **"확인된 미부보"를 적을 자리가 없다** — 값이 있으면 `INSURANCE-NOTIFY`가 항상
> 발화하고, 없으면 `INSUFFICIENT_FACTS`라 어떤 사실 조합으로도 해제되지 않는 룰이 된다.

**A2A 연결이 정확히 같은 모양이다.** `finallq_company_id` 한 컬럼이 "연결 승인됐는가"와
"상대 식별자가 무엇인가"를 겸하면:

- 값이 있으면 = 연결됨 → **식별자 존재가 곧 승인 판정이 된다.** 이게 바로 결정 1이
  금지한 것이다("이 값만으로 상대 시스템이 요청을 승인하면 안 된다").
- 값이 없으면 = 모름인지, 확인된 미연결인지 구분 불가.

그래서 **판정 컬럼과 식별자 컬럼을 나눈다.** 나누는 순간 "식별자만으로는 아무것도
판정되지 않는다"가 **주석이 아니라 구조로** 표현된다.

### 4.3 확정 형태 — 새 테이블 `partner_links`

§2에서 본 결(grain) 문제 때문에 `assets` 확장이 아니라 별도 테이블을 제안한다.

```sql
-- 외부 파트너 시스템과의 연결 대장. (미확정 제안)
-- ⛔ 이 테이블은 **인증 정보가 아니다.** 여기 행이 있다는 사실은
--    "우리가 아는 상대 식별자"일 뿐, 상대 시스템의 승인 근거가 되지 않는다.
--    실제 인증은 파트너 자격증명(토큰, §5)이 한다 — A2A_Q A2A_IDENTITY 결정 1.
CREATE TABLE partner_links (
  partner        TEXT NOT NULL,      -- 'finallq' | 'insuq'
  subject_type   TEXT NOT NULL,      -- 'company' | 'building' | 'asset'  (§2의 결)
  subject_ref    TEXT,               -- MaintQ 로컬 키. company 는 NULL(회사가 하나뿐)
  -- ★ D78 패턴: 판정과 식별자를 분리한다
  link_state     TEXT,               -- NULL=모름 / 'NOT_LINKED'=확인된 미연결
                                     -- / 'LINKED'=사람 승인 완료(§5 2단계 중 1단계 끝)
  external_ref   TEXT,               -- 상대 시스템 식별자(subject 지정용). 판정 근거 아님
  linked_at      DATE,               -- 연결 승인 시점 (사람 단계)
  PRIMARY KEY (partner, subject_type, subject_ref),
  CHECK (link_state IN ('NOT_LINKED','LINKED')),
  -- 미연결인데 식별자가 있으면 모순이다. 조용히 통과시키지 않는다
  CHECK (link_state = 'LINKED' OR external_ref IS NULL)
);
```

- `link_state`가 **NULL 3상태**를 그대로 재현한다(D62·D78의 "모른다"를 0으로 적지 않는다).
- 마지막 CHECK가 **"식별자만 있고 승인은 없는 상태"를 DDL 레벨에서 불가능**하게 만든다.
  D81·D84가 CHECK로 잠근 것과 같은 태도다("두 문장의 마지막 층").
- `policy_id`는 **여기로 옮기지 않고 `assets`에 그대로 둔다.** D78 판정 로직
  (`INSURANCE-NOTIFY` 룰·`test_rules.py`)이 그 컬럼을 읽고 있어 건드리면 회귀가 깨진다.
  `partner_links`의 InsuQ 행은 `assets.policy_id`와 **중복이 아니라 상위 사실**
  (건물 단위 증권)이라는 정리가 필요하다 — **미결, §8-2**.

### 4.4 검토했으나 권하지 않는 대안

| 대안 | 왜 안 되나 |
|---|---|
| `assets`에 `finallq_company_id` 컬럼 추가 (A2A_Q 표의 원 요청) | §2 — 9행 복제 → drift. 회사 단위 사실을 자산 결에 저장 |
| 컬럼 하나(`finallq_company_id`)만 두고 NULL로 미연결 표현 | §4.2 — "확인된 미연결"을 적을 자리가 없고, 식별자 존재가 곧 판정이 된다 |
| `risk_profile`(건물 마스터)에 얹기 | 건물 결은 맞지만 **회사 결(FinAllQ)이 안 맞는다.** 게다가 그 테이블 자체가 미구현 |
| 하드코딩 상수 (`config.py`) | 회사가 하나뿐인 목업이라 유혹적이지만, `link_state` 3상태를 표현 못 하고 S11/S14가 건물 단위로 갈라진다 |

---

## 5. 결정 ② — "이미 연결돼 있다"는 전제를 어떻게 표현할까

**확정: A안(seed) + `NOT_LINKED` 대조군 1건. 단, B안의 어휘를 미리 쓴다.**

### A안 — seed에 심는다 (전제로 고정)

```python
# data/seed.py — 예시
("finallq", "company",  None,    "LINKED", "CMP-MAINTQ-001", "2026-07-01"),
("insuq",   "building", "BLD-A", "LINKED", "POL-2026-FIRE-01", "2026-07-01"),
```

- **근거:** 이 레포는 이미 같은 방식을 쓴다. `policy_id = POL-2026-FIRE-01`이
  "이 건물은 이미 화재보험에 가입돼 있다"는 전제를 시드로 심은 것이고,
  A2A_Q 문서도 InsuQ S7이 *"전제: 기가입 보험 존재"* 패턴을 쓴다고 인정하며
  **"MaintQ가 먼저 등록되어 있다는 것을 전제로 S5~S16을 설계한다"**고 명시했다.
- **비용:** 낮다. `seed.py` 자가검증 1건 추가.
- **위험:** 전제가 **보이지 않게** 된다. 시드에 `LINKED`가 박혀 있으면 "연결 승인이
  사람 단계"라는 결정 2의 핵심이 데모에서 한 번도 드러나지 않는다.
  → **완화:** `AST-L3-LIFT`가 `insured=0`으로 남아 있는 것과 같은 이유로,
  **`NOT_LINKED` 행을 최소 1건 시드에 심는다.** 예컨대 `BLD-D`를 InsuQ 미연결로 두면
  "연결 안 된 건물에는 S11/S14를 못 쏜다"가 데모에서 실제로 보인다.
  D78이 `AST-L3-LIFT` 한 건으로 `CLEAR` 경로를 확보한 것과 정확히 같은 설계다.

### B안 — 온보딩 절차로 다룬다 (런타임에 채운다)

연결 승인 API(`POST /api/partners/{partner}/link` 류) + 승인 큐 편입으로,
사람이 승인해야 `link_state='LINKED'`가 되는 흐름.

- **근거:** 결정 2의 2단계 모델을 그대로 구현하는 정직한 형태. 이 레포에는 이미
  **딱 맞는 선례가 있다** — D85 통합 승인 큐(`GET /api/approvals`, `kind` enum).
  `kind`에 `partner_link`를 추가하면 발주·처분과 같은 승인 UX를 그대로 재사용한다.
- **비용:** 높다. 라우터 + 상태 전이(`ALLOWED_FROM`) + 역할 게이트 + 계약 테스트.
  그리고 **A2A_Q가 이걸 명시적으로 범위 밖에 뒀다** — *"연결 승인은 QMesh 프로토콜
  밖의 일회성 절차로 두고, QMesh는 그 결과물(발급된 자격증명)만 전제로 삼는다 —
  연결 자체의 승인 UX까지 A2A 프로토콜로 묶으려고 하지 않는다(과잉설계)."*

### 확정 — A안

**A안(seed) + `NOT_LINKED` 대조군 1건.** 이유:

1. A2A_Q가 "전제로 설계한다"고 이미 결정했고, 연결 승인 UX를 만드는 건 과잉설계라고
   명시적으로 배제했다. B안은 그 결정을 되돌리는 일이다.
2. 그런데 **A안을 택하더라도 스키마 어휘는 B안의 것을 쓴다** — `link_state`·`linked_at`이
   그것이다. 나중에 B안으로 갈 때 **테이블이 아니라 채우는 주체만 바뀐다**(seed → API).
   D75의 2단계 기입(`applied` 3상태)이 같은 방식으로 확장 여지를 남긴 선례다.
3. `NOT_LINKED` 1건이 A안의 유일한 약점(전제가 안 보임)을 없앤다.

---

## 6. 결정 — 실행 trace (질문 ④)

**확정 (2026-08-13): `request_chain_id`는 nullable 컬럼으로 `traces`에 추가한다.
subject는 컬럼으로 복제하지 않는다. 나간 요청 원문을 `tool_payload`에 남기고,
"그때 어느 company_id로 보냈나"는 그 원문을 여는 것을 정식 판정 경로로 삼는다.
`event_type` 신설은 하지 않는다.**

근거: `link_state`는 나중에 바뀔 수 있지만(연결 해지) **과거 trace의 원문은 그 시점
그대로 남는다** — 파생값을 복제할 때 생기는 재현성 문제가 애초에 발생하지 않는다.
D84가 처분 서명에서 "서명 시점 스냅샷 재현"을 번들 해시로 고정한 것과 같은 태도다.

### 6.1 먼저 정정

**"실행 trace에 이미 `request_chain_id` 자리를 마련해뒀다"는 사실과 다르다.**
`traces` 테이블에 그 컬럼은 없고(§3), 레포 전체에서 이 문자열은
`docs/A2A_CONTRACTS.md`의 **outbound payload 스펙**에만 나온다. 마련돼 있는 건
**나가는 요청 body의 자리**이지 **실행 로그의 자리**가 아니다.

### 6.2 그래서 trace에 무엇을 넣을 것인가

`request_chain_id`를 trace에 넣는 것 자체는 **필요하다.** S8(FinAllQ → 내부 2차홉
InsuQ)처럼 멀티홉이 생기면 "우리 세션 X의 요청이 저쪽 체인 Y가 됐다"를 이어 붙일
유일한 끈이기 때문이다. 그런데 §3의 제약 때문에 넣는 **방법**이 갈린다.

| 방식 | 평가 |
|---|---|
| `traces`에 `request_chain_id` 컬럼 추가 | 무난. nullable이면 기존 행에 영향 없고 CHECK도 안 건드린다. `tool_payload`가 "컬럼만 먼저 만든다"로 들어온 선례가 있다(D76-2) |
| `event_type`에 `a2a_call` 추가 | **비싸다.** DDL CHECK + D14/D22(SSE 4종 고정) + `sp3_sse_events`·`trace_persist` 동시 수정 |
| `payload`에 끼워넣기 | **불가.** D30 바이트 동일 계약이 깨진다 |

### 6.3 원문을 **어느 행에** 남기는가 — 실측 제약이 자리를 하나로 좁힌다

"`tool_payload`에 남긴다"까지는 확정이지만 **어느 행의** `tool_payload`인지는
기존 회귀가 이미 답을 정해 놨다. `spikes/trace_persist.py ⑫-b`:

```python
"⑫-b D76-2 tool_payload 에 도구 원본 JSON 저장 · tool_call 행은 NULL",
len(tp_rows) == 2 and tp_rows[0][2] is None and saved_raw == raw,
```

**`tool_call` 행의 `tool_payload`는 NULL이어야 한다**가 회귀로 잠겨 있다 —
나간 요청 원문을 `tool_call` 행에 실을 수 없다.

**확정 배치:**

| 항목 | 값 |
|---|---|
| `event_type` | `'tool_result'` (신설 없음 — CHECK 3종 그대로) |
| `tool` | `'a2a:request-withdrawal'` 등. **`tool` 컬럼에는 CHECK가 없다** — 자유 TEXT라 접두어 규칙만 정하면 된다 |
| `tool_payload` | **요청 + 응답 봉투 전체.** subject(`finallq_company_id` 등)는 요청 쪽에 자연히 포함된다 |
| `request_chain_id` | 신설 nullable 컬럼 |
| `payload` | SSE data와 바이트 동일 유지(D30) — A2A 원문을 절대 섞지 않는다 |

`tool_call`/`tool_result` 두 행을 쓰되 원문은 `tool_result` 행에만 싣는다.
**이 배치는 기존 스파이크를 하나도 수정하지 않는다** — ⑫-b(tool_call NULL) ·
⑫-c(D30 바이트 동일) · ⑫-d(read_trace에 tool_payload 미포함)가 그대로 통과한다.

**세션 귀속은 문제없다.** S5는 팀장 승인 시점(`po.py` submit→approved)에 나가므로
대화 세션이 이미 닫힌 뒤인데, `TraceWriter._next_seq()`가 `MAX(seq)+1`을 **DB에서
읽고**(`backend/agent/trace.py:176`) UNIQUE 충돌 시 캐시를 버리고 재시도한다(D41).
주석이 직접 *"같은 세션에 두 번째 턴이 붙어도 순번이 겹치지 않게"*라고 적어 뒀다 —
`po_drafts.session_id`에 뒤늦게 이어 붙이는 용법이 이미 지원된다.

### 6.4 이 결정에 딸려오는 것 3가지 (구현 시 처리)

1. **D76-2 문구를 넓혀야 한다.** 지금 정의는 *"도구가 돌려준 **원본 dict**"*
   (`backend/agent/trace.py:114`)인데 A2A는 **요청**도 함께 담는다. 컬럼·회귀는
   그대로 두고 **정의 문장만** "도구 또는 외부 호출의 원문(A2A는 요청+응답 봉투)"으로
   확장한다. 코드 변경 없음.
2. **⛔ 자격증명은 `tool_payload`에 들어가지 않는다.** 토큰은 헤더(actor)이지 payload가
   아니다(§7). 원문을 통째로 저장하는 결정이므로 **헤더를 저장 대상에서 명시적으로
   제외**해야 한다 — 안 그러면 액세스 토큰이 DB에 평문으로 남는다.
3. **여는 경로가 지금은 없다.** ⑫-d가 검사하듯 `read_trace`(D43)는 `tool_payload`를
   **의도적으로 싣지 않는다.** "원문을 여는 것이 정식 판정 경로"라면 여는 수단이
   있어야 하는데 현재는 DB 직접 조회뿐이다. 사람 전용 조회 API가 필요한지는
   **미결 — §8-2.**

---

## 7. 결정 — 파트너 자격증명 보관 (질문 ③)

구현하지 않는다. **위치만** 확정한다.

### 7.1 이 레포의 기존 비밀 관리 두 갈래

`.env.example`이 이미 두 종류를 명확히 갈라 놨다:

| 갈래 | 예 | 규칙 |
|---|---|---|
| **런타임 키** | `GEMINI_API_KEY`·`ANTHROPIC_API_KEY` | 서버가 요청 처리 중에 읽는다. D56 — **OS 환경변수 우선**, `.env`는 빈 곳만 채운다(`load_dotenv(override=False)`, `backend/main.py` 1곳) |
| **수집 스크립트 전용 키** | `LAW_API_OC`·`IROS_API_KEY_*` | *"backend/·mcp_server/ 는 아래 키를 절대 참조하지 않는다 — 요청마다 외부 기관을 호출하면 서명 시점 스냅샷 재현 전제가 깨진다"* |

### 7.2 파트너 자격증명은 **세 번째 갈래**다

둘 중 어디에도 깔끔히 안 들어간다:

- 수집 키가 아니다 — **런타임에**, 팀장 승인 직후(S5) 나간다.
- 그렇다고 LLM 키와도 다르다 — **돈이 움직이는 요청에 서명**하고, 결정 2에 따라
  **한도·허용 작업·유효기간이 함께 발급**되며 **폐기(revoke) 가능**해야 한다.

### 7.3 확정 자리

```
.env.example
  # ══ A2A 파트너 자격증명 (QMesh · 미착수) ══
  # ⚠ LLM 키와 성격이 다르다: 이 자격증명으로 나가는 요청은 돈을 움직인다(S5).
  #    발급 주체는 FinAllQ ADMIN 콘솔이며, 사람 간 연결 승인 후에만 발급된다.
  #    한도·허용 작업·유효기간이 함께 발급되므로 만료 처리가 필요하다.
  MAINTQ_A2A_FINALLQ_CLIENT_ID=
  MAINTQ_A2A_FINALLQ_CLIENT_SECRET=
  MAINTQ_A2A_INSUQ_CLIENT_ID=
  MAINTQ_A2A_INSUQ_CLIENT_SECRET=

읽는 곳 (제안)  backend/a2a/credentials.py  ← 새 모듈
```

판단 근거:

- **`.env` + OS env 우선 (D56 그대로).** 목업 단계에서 시크릿 저장소(Vault·AWS SM)를
  들이는 건 과잉이고, D56이 이미 "어느 키로 돌았는지 디버깅 가능해야 한다"는 이유로
  이 순서를 정해 뒀다. 같은 이유가 그대로 적용된다.
- **`client_secret`은 env, 발급받은 access token은 env가 아니다.** 토큰은 만료되므로
  프로세스 메모리 캐시가 맞다(파일·DB에 쓰면 만료 관리 주체가 둘이 된다).
- **`partner_links` 테이블에 자격증명을 넣지 않는다.** 그 테이블은 subject 대장이고,
  §4.3 주석대로 **인증 정보가 아니다.** 둘을 한 테이블에 두면 결정 1의 actor/subject
  분리가 스키마에서 다시 무너진다.
- **DB·`data/`에는 절대 두지 않는다.** `.env`는 이미 git 제외이고, `.env.example`이
  *"⛔ 실제 값을 이 파일·세션 로그·주석 어디에도 적지 말 것"*을 이미 규칙으로 갖고 있다.
- **읽는 위치를 새 모듈로 분리하는 이유:** D15(MCP ↔ backend 프로세스 분리)에 따라
  **MCP 도구는 이 자격증명을 보면 안 된다.** A2A 호출은 사람 승인 뒤 백엔드가 하는
  일이지 도구가 하는 일이 아니다(절대규칙 1 — 도구는 draft INSERT만).

---

## 8. 남은 것

### 8.1 확정됐고 남은 절차

| 항목 | 상태 |
|---|---|
| §4 `partner_links`(D78 패턴) | ✅ 확정. **A2A_Q 표의 원 요청("`assets`에 `finallq_company_id` 컬럼 추가")과 다른 답이므로**, A2A_Q 갱신 시 그 행을 함께 고쳐야 한다 |
| §5 seed A안 + `NOT_LINKED` 1건 | ✅ 확정 |
| §6 trace(원문 보관·컬럼 신설·event_type 유지) | ✅ 확정 |
| §7 자격증명 위치 | ✅ 확정 |
| `docs/A2A_CONTRACTS.md` 갱신 | ✅ **2026-08-13 완료** — actor/subject 구분 반영, 해소된 "미해결" 문구 제거 |
| **D 번호 부여** | ✅ **2026-08-13 완료** — **D91**(`partner_links`) · **D92**(seed A안) · **D93**(자격증명 위치) · **D94**(trace). 넷 다 *"⚠ 설계 확정·미구현"* 으로 표기했다. D 범위 표기 5곳(`CLAUDE.md` · 루트 `README.md` · `docs/README.md` · `.claude/agents/reviewer.md` · `docs/00_MVP_SCOPE.md`)도 `D1~D94` 로 갱신 |

### 8.2 여전히 미해결 — 결정이 필요한 것

1. **`assets.policy_id`와 `partner_links`의 InsuQ 행 관계.** 중복인가 상하 관계인가.
   `insuq_policy_id`를 새로 만들지 않는다는 것과, D78 판정 로직(`INSURANCE-NOTIFY` ·
   `test_rules.py`)이 `assets.policy_id`를 읽으므로 **그 컬럼은 못 옮긴다**는 것까지가 확정.
   남은 건 "건물 단위 증권(`partner_links`) ↔ 자산 행의 사본(`assets.policy_id`)"을
   **어느 쪽이 정본인지** 정하고 seed 자가검증으로 대조를 거는 일이다(D60과 같은 꼴).
2. **`tool_payload` 조회 수단** (§6.4-3). "원문을 여는 것이 정식 판정 경로"인데
   `read_trace`(D43)가 의도적으로 싣지 않아 **지금은 DB 직접 조회뿐이다.**
   사람 전용 조회 API를 둘지, 감사 목적이므로 DB 조회로 충분하다고 볼지.
3. **`risk_profile` 우선순위 재조정.** §1.2 — A2A 편입으로 "후순위" 판단의 근거가 바뀌었다.
   S14가 보낼 내용(`risk_grade`·`fire_handling`)이 그 테이블에 있다.
4. **`seed.py` 자가검증 항목 추가.** `partner_links`가 생기면 검증 목록(현재 21건)에
   최소 2건이 붙는다 — `NOT_LINKED` 대조군 존재 · `link_state`/`external_ref` CHECK 정합.

## 관련 문서

- `A2A_Q/docs/A2A_IDENTITY.md` — QMesh 확정본 (결정 1·2의 원본 인용처)
- `FinAllQ/docs/A2A_IDENTITY.md` — 최초 조사 원본 (§2.5·§3.2·§5)
- `docs/A2A_CONTRACTS.md` — 이 레포의 outbound 호출 목록
- `docs/05_DB_SCHEMA.md` §9(traces)·§11(assets) — 실측 근거
- `spikes/trace_persist.py` ⑫-b·⑫-c·⑫-d — §6.3 배치를 좁힌 회귀
- `docs/11_ASSET_LIFECYCLE.md` §10-2 — `risk_profile`(건물 마스터) 제안 원본
