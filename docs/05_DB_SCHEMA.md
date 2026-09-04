# 목업 DB 스키마 v0.3
SQLite 기준 (목업이므로 파일 DB로 충분, 실서비스 가정 시 PostgreSQL 치환 가능)

도구가 읽는 테이블 — 설계하며 6개 → 8개(`error_codes`·`equipment` 추가, D11)
→ 구현 정합화에서 **9개**로 확정: `traces`(실행 로그 영속화, D21) 추가.
→ **Sprint 6 (F1·F2·F4)에서 7개 추가** — `assets`·`law_refs`·`rules`·`decisions`·`flags`·
`repair_records`·`residual_curve` (§11~§17).
→ **Sprint 8 (A2A 신원 식별)에서 1개 추가** — `partner_links` (§18).
→ **Sprint 10 (설비 하이라이트 대시보드)에서 1개 추가** — `part_lifecycle_mock` (§19).
→ **Sprint 11 (기한·사고·실사 보존·위험 프로파일, F5·F6)에서 4개 추가** — `deadlines`·`incidents`·
`ownership_checks`·`risk_profile` (§20~§23). `11_ASSET_LIFECYCLE.md §10-2` 가 초안으로 남겨 둔
4테이블을 DDL로 확정한다 (MQ-1101).

> **세는 단위 주의 — 절과 `CREATE TABLE`은 다른 것을 센다.** 아래 두 숫자는 서로 다른 것을 센다.
> 문장을 읽을 때 *"절"* 을 세는지 *"`CREATE TABLE`"* 을 세는지 반드시 구분할 것.
>
> - **`CREATE TABLE` 은 24개다** (`data/seed.py` 의 `SCHEMA` 기준) —
>   코어 **11개** + Sprint 6 **7개** + Sprint 8 **1개**(`partner_links`) + Sprint 10 **1개**
>   (`part_lifecycle_mock`) + Sprint 11 **4개**(`deadlines`·`incidents`·`ownership_checks`·
>   `risk_profile`).
> - **절(§)은 23절이다** — `§1`~`§9`(+`§1-B`)로 **10절**, `§11`~`§17` **7절**, `§18` **1절**,
>   `§19` **1절**, `§20`~`§23` **4절**.
> - 절보다 `CREATE TABLE` 이 1개 많은 이유는 **`§7`이 `suppliers`와 `supplier_parts`
>   두 테이블을 함께 다루기 때문**이다.
> - **`§10`은 존재하지 않는다** (`§1-B`가 10번째 절이라 번호가 어긋난 것을 그대로 둔 것이며,
>   `sprint-6.md`·확장 도구 명세가 이미 `§11`~`§17`로 참조하고 있다).
>   같은 이유로 **기존 절 번호를 재배치하지 않는다** — Sprint 8 은 `§18`을, Sprint 10 은
>   `§19`를, Sprint 11 은 `§20`~`§23`을 끝에 잇기만 한다.

---

## ERD 개요

```
assets ──< equipment ──< error_history >── error_codes        ← assets 는 D68 의 호스트 설비
  │           │                                 │ (model+code 복합키)
  │           └──< repair_records >─────────────┘             ← 수리는 인버터 단위 (D68 ⓑ)
  ├──< decisions            ← 계층 3 서명. **도구가 draft INSERT · 전이는 사람 API** (D10·D81)
  ├──< flags                ← 법정 조건 상태 (발생→이행→해소)
  └── category ──> residual_curve                             ← (category, age_bucket) 조인

law_refs (계층 1) ──< rules (계층 2)     ← 정본은 data/rules/{laws,rules}/*.json, DB는 사본 (D60)

parts ──< inventory
  │
  ├──< part_alternatives (self-ref)
  └──< supplier_parts >── suppliers
  │
  └──< po_drafts >── suppliers
         │ (session_id)
       traces                        ← 세션별 실행 로그 (D21)

partner_links   ← 외부 파트너 subject 대장. FK 없음(building_id 가 FK 없는 것과 같은 이유) · 인증 정보 아님

equipment ──< part_lifecycle_mock >── parts   ← 하이라이트 🟠(곧 점검) 판정 출처. mock(D65 고지 필수)
```

---

## 1. error_codes — 에러코드 마스터 ★매뉴얼에서 구조화 추출

> **정본은 `data/extracted/error_codes.json`**(`data/extract_error_codes.py` 산출, D60·D33 승인 게이트).
> `lookup_error_code`의 원천. M1에서 매뉴얼 PDF 표 → 이 테이블로 추출하는 게 최대 작업.
> 🔴 승격 절차는 [`data/extracted/README.md`](../data/extracted/README.md) (**D106**) — 이 절은
> **④(drift 자가검증)의 유일한 선례**다(`seed.py` 검사 ㉚). 반대로 §17 은 ④가 없다.

```sql
CREATE TABLE error_codes (
  model        TEXT NOT NULL,          -- 'iG5A' | 'S100'
  code         TEXT NOT NULL,          -- 대문자 canonical: 'OHT', 'OCT' ... (D25, lookup은 case-insensitive)
  display_code TEXT,                   -- 키패드 원표기 보존: 'oht', 'OHt' ... (D25)
  error_name   TEXT NOT NULL,
  severity     TEXT NOT NULL,          -- 'warning' | 'fault' | 'critical'
  causes       TEXT NOT NULL,          -- JSON array
  actions      TEXT NOT NULL,          -- JSON array
  related_parts TEXT,                  -- JSON array of part_no (부품 특정의 연결고리!)
  manual_page  INTEGER NOT NULL,       -- 근거 인용 필수 — PDF 물리 페이지 기준 (D26)
  -- ★ Sprint 9 신설 (D100) — 조치문 출처. 'ig5a-troubleshooting' 등 manifest 의 id.
  --   NULL = 출처 미기록(현재 전건 NULL — 정본 병합은 MQ-919, 아직 사람 승인 전이라 미적재).
  --   actions_page 는 PDF 물리 페이지(D26)이고 actions_manual_id 와 짝이어야 한다.
  actions_manual_id TEXT,
  actions_page      INTEGER,
  PRIMARY KEY (model, code),           -- ★ 복합키 = "같은 코드, 다른 의미" 구현
  -- code 형식 제약 (D33): 대문자·숫자·언더스코어 2~4자.
  -- 실측 64건 전부 이 범위 (3자 51 / 4자 12 / 2자 1, 최장 'FLTL'·'RERR' 등 4자)
  CHECK (length(code) BETWEEN 2 AND 4
         AND code = upper(code)
         AND code NOT GLOB '*[^A-Z0-9_]*'),
  -- ★ Sprint 9 신설 (D100) — 둘 다 있거나 둘 다 없거나
  CHECK ((actions_manual_id IS NULL) = (actions_page IS NULL))
);
```

**설계 포인트:** `related_parts`가 진단→조달을 잇는 다리. 이 컬럼이 없으면 "부품 특정"을 LLM 추측에 맡기게 됨.

## 1-B. users — 사용자 (D41·D52)

> `X-User` 헤더 값의 원천이자 `requested_by`/`decided_by`/`recorded_by`의 FK 대상.
> 표시명이 `backend/services/po.py`에 하드코딩돼 있던 것을 여기로 옮긴다 (D36→D41).

```sql
CREATE TABLE users (
  user_id       TEXT PRIMARY KEY,      -- 'tech-01' — X-User 헤더 값. ASCII (D36)
  email         TEXT UNIQUE,           -- 회사 이메일. 향후 IdP 매칭 키 (D52)
  display_name  TEXT NOT NULL,         -- '김OO' — 화면 표시용. 헤더·DB엔 안 들어간다
  role          TEXT NOT NULL,         -- 권한. 'technician' | 'manager'
  department    TEXT,                  -- 소속. **권한이 아니다** (D108). nullable = 미배정
  auth_provider TEXT NOT NULL DEFAULT 'local',  -- 'local' | 'google'
  external_id   TEXT,                  -- IdP의 sub/oid. 연동 전 NULL
  active        BOOLEAN NOT NULL DEFAULT 1,     -- 퇴사·휴직 시 0
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  CHECK (role IN ('technician','manager')),
  CHECK (department IS NULL OR department IN ('maintenance','finance')),
  CHECK (auth_provider IN ('local','google')),
  CHECK (user_id = lower(user_id) AND user_id NOT GLOB '*[^a-z0-9-]*')
);
```

**행을 지우지 않는다.** 퇴사자는 `active=0`으로 둔다 — 과거 발주의 `decided_by`가 끊기면 감사 추적(P5)이 무너진다.

**`role`은 회사가 사전 부여한다 (D52).** Google 로그인은 "누구인지"만 확인하고 권한을 정하지 않는다. OAuth가 권한을 결정하면 D4(진단자/승인자 분리)가 무의미해진다.

**개인 소셜 로그인은 넣지 않는다 (D52).** `auth_provider`가 `local`·`google` 2종뿐인 이유다. `google`은 **회사 Google Workspace**이며, `hd`(hosted domain) 클레임 + 이 테이블의 사전 등록 두 겹으로 개인 Gmail을 막는다. 실제 인증 플로우 구현은 백로그 **P21**.

**`department`(소속)는 `role`(권한)과 직교다 (D108, P41 ③).** 재무부 담당자(`mgr-02`)도 `role`
은 그대로 `manager` 다 — 승인 권한은 `role` 하나로만 결정되고 `department` 는 어떤 판정 함수도
참조하지 않는다. `role` 과 달리 헤더로 받지 않는다 — **서버가 이 컬럼을 `user_id` 로 조회해
주입**한다(`backend/deps.py:_department_of`, `GET /api/whoami`). 클라이언트가 `X-Dept` 같은
헤더로 자기 부서를 자칭할 길이 구조적으로 없다.

## 2. equipment — 설비 마스터

```sql
CREATE TABLE equipment (
  equipment_id TEXT PRIMARY KEY,       -- 'INV-L3-01'
  line_id      INTEGER NOT NULL,       -- 3
  model        TEXT NOT NULL,          -- 'iG5A'
  installed_at DATE,
  location     TEXT,                   -- '3번 조립라인 분전반'
  asset_id     TEXT REFERENCES assets  -- 호스트 설비 (D68). NULL 허용
);
```

**`asset_id` 확장 (D68, Sprint 6).** 인버터는 **자산의 부품**이지 거래 단위가 아니다 —
처분·감가·시장가는 호스트 설비(`assets`)에 붙고, 고장·수리 판정은 인버터에 붙는다(D68 ⓑ).
시드 10대 중 **`INV-L1-01`(1번 조립라인 분전반)만 `asset_id` NULL** 이다. 배전 위치이지
거래 가능한 기계가 아니라서, 확장 도구 전체의 `status:"not_found", reason:"no_host_asset"`
경로가 이 한 행으로 검증된다.

## 3. error_history — 에러 발생 이력 (확정 기능 ①의 원천)

```sql
CREATE TABLE error_history (
  id           INTEGER PRIMARY KEY,
  equipment_id TEXT NOT NULL REFERENCES equipment,
  code         TEXT NOT NULL,
  occurred_at  DATETIME NOT NULL,      -- UTC (D39)
  action_taken TEXT,                   -- '리셋', '냉각팬 청소' ...
  part_replaced TEXT,                  -- part_no or NULL
  resolved     BOOLEAN DEFAULT 1,
  recorded_by  TEXT REFERENCES users,  -- 기록한 정비사 (D41). 시드분은 NULL
  FOREIGN KEY (recorded_by) REFERENCES users(user_id)
);
```

**시드 전략:** AI허브 「기계시설물 고장 예지 센서」의 고장 유형 4종 분포를 참고해 6개월치 이력 생성. 대부분 단발, **INV-L3-01의 OCt만 30일 내 3건** 심어 S3 트리거.

**쓰기 경로 (D29):** 이 테이블에 INSERT하는 곳은 `POST /api/equipment/{id}/errors` **하나뿐**이며, 정비사가 화면 A에서 명시적으로 기록 액션을 눌렀을 때만 호출된다. MCP 도구에는 쓰기 권한이 없고(D10), 채팅 진입만으로 자동 기록하지 않는다 — 자동 기록하면 `count`가 질문 횟수가 되어 `repeated` 판정이 오염된다.

## 4. parts — 부품 마스터

```sql
CREATE TABLE parts (
  part_no      TEXT PRIMARY KEY,       -- 'FAN-IG5-01'
  name         TEXT NOT NULL,          -- '냉각팬'
  category     TEXT,                   -- '냉각' | '제어' | '전원' ...
  compatible_models TEXT NOT NULL,     -- JSON array ['iG5A']
  discontinued BOOLEAN DEFAULT 0,      -- 단종 → 대체품 분기 재료
  part_class   TEXT,                   -- 'CONSUMABLE' | 'CRITICAL' (Sprint 6)
  mfr_part_no  TEXT                    -- 제조사 실품번. NULL = 공개돼 있지 않음 (D97)
);
```

**`part_class` 확장 (Sprint 6).** `assess_repair_value` 의 3지 판단이 이 값에 걸린다 —
소모품 교체는 시장가에 반영되지 않고(`12 §1`), 핵심 부품 교체만 잔존수명 회복분을 낸다.
**40종 전부 `data/seed.py`의 `PART_CLASS` 에 명시**하며 누락되면 시드가 중단된다 —
`classify_part_criticality` 는 NULL 이면 `error/part_class_not_set` 을 돌려주고 **추론하지 않는다**
(D12 가 `related_parts` 에서 세운 태도 그대로).
현재 분포는 `CONSUMABLE 14 / CRITICAL 26`, **`FAN-IG5-01` 은 `CRITICAL`**(S1 주인공).

> ⚠ **사람 미검수 초안이다.** `seed.py` 의 `part_class_caveat()` 가 매 실행 말미에 경고를 찍는다.
> **게이트가 아니다** — 막으면 스프린트가 선다(`prompts.py` 안전 문구 미검수를 런타임에서
> 막지 않는 것과 같은 태도). 검수 항목은 `TODO_직접할일.md`.

**`mfr_part_no` 확장 (2026-08-14 · D97).** `part_no` 는 **합성 PK**(`FAN-IG5-01`)이고
제조사 실품번은 **별도 컬럼**에 얹는다. PK 를 실품번으로 바꾸지 않는 이유는 D97 에 있다 —
케이스 맵·평가셋·회귀가 이 문자열에 묶여 있고, 실품번이 있는 부품은 **40종 중 1종**뿐이라
바꾸면 표기 체계가 반반으로 갈린다.

| 상태 | 뜻 |
|---|---|
| 값 있음 | 제조사가 **공개한** 품번을 **사람이 원문에서 확인**했다 |
| **NULL** | **공개돼 있지 않다** — ⛔ *"우리가 아직 못 찾았다"* 가 **아니다** |

현재 **1/40종**: `PCB-IG5-CTRL` → **`SV-iG5A I/OPCBASSY`**(적용 `0.4~7.5KW-2/4`).
나머지 39종의 NULL 은 4개 축 전수 조사 결과이며 근거는
[`data/analysis/part_number_sources.md`](../data/analysis/part_number_sources.md) 에 있다
(핵심: `FAN-IG5-01` 은 **제조사가 대리점 문의로 돌려 품번 자체가 비공개**).

⛔ **넣으면 안 되는 값 3종** — 판매점 주문번호(`32155`) · 완제품 형명(`SV220iG5A-4`) ·
추측 품번. 앞의 둘은 시드 자가검증 **㉖** 이 정규식으로 거부하고, 셋째는 규칙이다
(CLAUDE.md 절대규칙 6 과 같은 계열 — **모르면 NULL 이 정답**).

## 5. part_alternatives — 호환 대체품 (self-reference)

```sql
CREATE TABLE part_alternatives (
  part_no      TEXT REFERENCES parts,
  alt_part_no  TEXT REFERENCES parts,
  compat_confirmed BOOLEAN NOT NULL,   -- false면 도구가 제안 금지
  note         TEXT,
  PRIMARY KEY (part_no, alt_part_no)
);
```

## 6. inventory — 재고

```sql
CREATE TABLE inventory (
  part_no      TEXT PRIMARY KEY REFERENCES parts,
  qty          INTEGER NOT NULL,
  safety_stock INTEGER NOT NULL DEFAULT 0,
  location     TEXT                    -- '자재창고 A-12'
);
```

## 7. suppliers + supplier_parts — 공급사·견적

```sql
CREATE TABLE suppliers (
  supplier_id  TEXT PRIMARY KEY,       -- 'SUP-A'
  name         TEXT NOT NULL,
  contact      TEXT                    -- 에스컬레이션 초안에 사용
);

CREATE TABLE supplier_parts (
  supplier_id  TEXT REFERENCES suppliers,
  part_no      TEXT REFERENCES parts,
  lead_days    INTEGER NOT NULL,
  unit_price   INTEGER NOT NULL,
  moq          INTEGER DEFAULT 1,
  PRIMARY KEY (supplier_id, part_no)
);
```

## 8. po_drafts — 발주서

```sql
CREATE TABLE po_drafts (
  po_id        TEXT PRIMARY KEY,       -- 'PO-0117'
  part_no      TEXT NOT NULL REFERENCES parts,
  qty          INTEGER NOT NULL,
  supplier_id  TEXT NOT NULL REFERENCES suppliers,
  model        TEXT,                   -- 'iG5A' | 'S100' — error_code와 항상 짝 (D33)
  error_code   TEXT,                   -- 이 발주를 유발한 에러코드. 대문자 canonical 2~4자 (D33)
  evidence     TEXT,                   -- JSON. 관찰 현상·판단 근거·비고 (D34)
  unit_price   INTEGER NOT NULL,       -- 발주 시점 단가 스냅샷. create_po_draft가 supplier_parts를 SELECT해 채움 —
                                       --   도구 파라미터가 아니므로 LLM이 가격을 지어낼 경로가 없음 (D31).
                                       --   이후 가격 변동과 무관하게 승인 시점 근거가 보존됨
  reason       TEXT NOT NULL,          -- 진단 근거 (화면 B 근거 카드 소스)
  urgency      TEXT DEFAULT 'normal',
  state        TEXT DEFAULT 'draft',   -- 'draft'|'pending'|'approved'|'rejected'|'finance_approved'|'finance_rejected' (Sprint 17, MQ-1702)
  requested_by TEXT REFERENCES users,  -- 정비사 사용자 ID('tech-01') — X-User 헤더에서 백엔드가 주입
                                       --   (D23 도구 파라미터 아님 / D36 ASCII ID / D41 users FK)
  decided_by   TEXT REFERENCES users,  -- 팀장 사용자 ID('mgr-01') — 승인/반려 시 X-User에서 주입
  decision_note TEXT,                  -- 반려 사유 / 승인 코멘트 (D38). 반려는 필수 —
                                       --   사유 없는 반려는 요청자가 뭘 고쳐야 할지 알 수 없음
  session_id   TEXT,                   -- 이 발주를 만든 대화 세션 (D21) — 화면 B "실행 로그 보기" 링크의 키
  created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
  decided_at            DATETIME,               -- 팀장 결정 시각 (Sprint 17, 기존 gap — approve/reject 도 지금까지 없었다)
  finance_decided_by    TEXT REFERENCES users,   -- 재무 담당 사용자 ID (Sprint 17, MQ-1702)
  finance_decision_note TEXT,                    -- 재무 승인 코멘트 / 반려 사유 (Sprint 17, MQ-1702)
  finance_decided_at    DATETIME,                -- 재무 결정 시각 (Sprint 17, MQ-1702)

  -- (model, error_code)는 error_codes 복합키를 참조 — code 단독으로는 "같은 코드, 다른 의미"가
  -- 발주 이력에서 무너짐 (D13). 존재하지 않는 코드는 FK가 튕겨내므로 LLM이 지어낸 코드로
  -- 발주서를 만들 수 없다 (D23·D31과 같은 논리)
  FOREIGN KEY (model, error_code) REFERENCES error_codes(model, code),

  CHECK (state IN ('draft','pending','approved','rejected','finance_approved','finance_rejected')),
  CHECK (urgency IN ('urgent','normal')),
  -- code 형식: 대문자 canonical, 2~4자 (실측 64건 전부 이 범위 — 3자 51 / 4자 12 / 2자 1)
  CHECK (error_code IS NULL OR (
           length(error_code) BETWEEN 2 AND 4
           AND error_code = upper(error_code)
           AND error_code NOT GLOB '*[^A-Z0-9_]*')),
  -- 둘 다 있거나 둘 다 없거나 (model만 있고 code가 없는 상태를 막음)
  CHECK ((model IS NULL) = (error_code IS NULL)),
  CHECK (evidence IS NULL OR json_valid(evidence))
);
```

**Sprint 17(MQ-1702) 확장 — 재무부 승인 단계.** `approved`가 이제 "팀장 승인 완료, 재무 결정
대기"를 겸한다 — 재무부가 `finance_approved`/`finance_rejected`로 최종 결정한다. `decided_at`은
그동안 없던 gap이었다(팀장 결정 시각을 저장할 컬럼 자체가 없었다) — 이번에 함께 메웠다.
`finance_decided_by`/`finance_decision_note`/`finance_decided_at`은 팀장 승인 3종
(`decided_by`/`decision_note`/`created_at` 대신 `decided_at`)과 같은 역할을 재무 결정에
대해 한 벌 더 갖는 구조다. `finance_decision_note`도 반려 시 필수(D38과 동일한 원칙 — Sprint
17 회귀 픽스처 PO-0119 참고).

> ⚠️ **`PRAGMA foreign_keys=ON`을 커넥션마다 실행할 것.** SQLite는 FK 검증이 **기본 OFF**다. 이걸 안 켜면 위 복합 FK가 조용히 무시되어 매뉴얼에 없는 코드로도 발주서가 만들어진다 — D33의 보증이 통째로 사라진다. `mcp_server/db.py`의 커넥션 팩토리에서 강제한다.

**검증 완료 (2026-07-23):** 위 DDL을 SQLite에서 실제로 실행해 9개 케이스를 확인했다 — 정상 발주·코드 없는 발주(S2)는 통과, 지어낸 코드(FK)·소문자·5자·특수문자·model만 있는 상태·깨진 JSON·**기종 오배정(S100 코드를 iG5A로)**은 전부 거부.

**`error_code`가 NULL 허용인 이유 (D33):** S2는 **진단 없이 중간 진입**한다("S100 인버터 제어보드 교체해야 해"). 에러코드 없는 발주가 예외가 아니라 정상 케이스이므로 NOT NULL로 잠그면 S2가 막힌다. 대신 값이 있으면 FK로 실재하는 코드임을 강제한다.

### `evidence` JSON 구조 (D34)

`reason`(한 줄 요약)과 역할이 다르다. **`reason`은 승인자가 3초 안에 읽는 헤드라인**(D5, 화면 B 근거 카드의 제목), **`evidence`는 펼쳐서 확인하는 뒷받침**이다.

```json
{
  "symptoms": ["냉각팬 소음 증가", "3번 라인 2회 정지"],
  "basis": [
    { "tool": "lookup_error_code",  "code": "OHT", "manual_page": 202 },
    { "tool": "get_error_history",  "count": 3, "window_days": 30, "repeated": true },
    { "tool": "search_inventory",   "part_no": "FAN-IG5-01", "qty": 1, "safety_stock": 3 }
  ],
  "notes": "야간조 정비사 육안 확인 — 팬 회전 불량"
}
```

| 키 | 내용 | 출처 |
|---|---|---|
| `symptoms` | **어떤 현상을 보고 고장으로 판단했는지** — 관찰된 증상 | 사용자 발화에서 에이전트가 추출 |
| `basis` | 판단을 뒷받침한 도구 결과 (코드 정의·이력·재고) | 도구 출력 — `traces`와 대조 가능 |
| `notes` | 자유 비고·기타 상황 (구두 보고, 현장 특이사항 등) | 사용자 발화 / 정비사 입력 |

세 키 모두 optional. 승인자가 "왜 이 부품을 지금 사야 하는가"를 대화를 안 읽고 판단할 수 있게 하는 게 목적이다.

**권한 규칙(코드 레벨 강제):** MCP 도구는 `state='draft'`로 INSERT만 가능. `draft→pending`은 정비사 UI("승인 요청"), `pending→approved/rejected`는 팀장 UI만. 도구에 UPDATE 권한 자체를 안 줌.

## 9. traces — 에이전트 실행 로그 (D21)

> SSE로 흘려보낸 trace 이벤트의 영속 사본. `GET /api/chat/{session_id}/trace`(SSE 끊김 폴백),
> 화면 B의 "실행 로그 전체 보기"(po_drafts.session_id 조인), scenario-smoke의 시퀀스 판정이 이 테이블을 읽는다.
> 도구 결과 **원문**도 여기 저장 (세션 이력에는 요약본만 — 09_RUNTIME 참조).
> **`token`은 저장하지 않는다 (D41).** `CHECK`가 3종만 허용하며, 이는 버그가 아니라 설계다 —
> 대화 전문을 DB에 쌓는 일이고 D18("팀장은 대화를 안 읽는다")과도 어긋난다.
> A5의 "모든 이벤트"는 tool_call/tool_result/block 3종을 뜻한다.

```sql
CREATE TABLE traces (
  id           INTEGER PRIMARY KEY,
  session_id   TEXT NOT NULL,
  seq          INTEGER NOT NULL,       -- 세션 내 이벤트 순번 (시퀀스 판정용)
  event_type   TEXT NOT NULL,          -- 'tool_call' | 'tool_result' | 'block'
  tool         TEXT,                   -- 도구명 (block 이벤트는 NULL 가능)
  payload      TEXT NOT NULL,          -- SSE data 와 **바이트 동일** (D30)
  tool_payload TEXT,                   -- 도구 결과 원본 JSON. tool_result 행만 (D76-2)
  request_chain_id TEXT,               -- A2A 멀티홉 추적용 (D94-ⓐ). nullable
  ts           DATETIME DEFAULT CURRENT_TIMESTAMP,
  -- token 은 없다 (D41): 저장하지 않는 게 설계다. backend/agent/trace.py 참조
  CHECK (event_type IN ('tool_call','tool_result','block')),
  -- seq 중복이 조용히 통과하면 순서 판정(scenario-smoke)·타임라인·Last-Event-ID(P18)가
  -- 깨진 걸 아무도 모른다 (D41)
  UNIQUE (session_id, seq)
);
CREATE INDEX idx_traces_session ON traces(session_id, seq);
```

**`payload` 와 `tool_payload` 를 나눈 이유 (D76-2).** `payload` 는 **SSE 로 흘려보낸 `data` 와
바이트 동일**이 계약이고(D30), `spikes/trace_persist.py ②`·`sp3_sse_events ⑬` 이 바이트 단위로
대조한다. 도구 결과 **원본**은 화면·평가가 요약본이 아닌 원문을 봐야 할 때 필요한데, 이걸
`payload` 에 섞으면 "발행한 것과 저장한 것이 같다"는 대조가 조용히 깨진다. 그래서 컬럼을 따로 둔다.
`tool_result` 행에만 값이 있으므로 **nullable** 이며, `tool_call`·`block` 행에는 NULL 이다.

> ⚠ **Sprint 6 은 컬럼만 만든다.** 값을 쓰는 쪽(`backend/agent/trace.py` 의 큐·배리어)은
> D76-2 담당이 별도로 처리한다. 시드는 `traces` 에 행을 넣지 않는다.

**`request_chain_id` 를 컬럼으로 둔 이유 (D94-ⓐ).** A2A 는 한 요청이 여러 파트너를 거치므로
*"이 이벤트들이 같은 호출 사슬인가"* 를 사후에 이어 붙일 키가 필요하다. 이 키는 **이벤트 종류가
아니라 이벤트의 속성**이므로 컬럼이며, `event_type` 은 **3종 그대로**다 — `a2a_call` 같은 종류를
신설하면 DDL CHECK·SSE 4종 고정(D14·D22)·`sp3_sse_events`·`trace_persist` 를 동시에 고쳐야 한다.
나간 **요청+응답 봉투 원문**은 `tool_result` 행의 **`tool_payload`** 에 싣고(`tool` = `'a2a:<skill>'`),
`tool_call` 행은 그대로 NULL 이다(`trace_persist ⑫-b` 가 검사). subject(company/policy 매핑값)는
**trace 컬럼으로 복제하지 않는다** — `link_state` 는 변할 수 있어(연결 해지) 과거 행에 박힌 값이
현재 매핑과 어긋나면 어느 쪽이 맞는지 판정할 근거가 없다. *"그때 어느 subject 로 보냈나"* 는
**그 이벤트의 원문을 여는 것**이 정식 경로다. ⛔ **인증 헤더는 저장 대상에서 제외**한다 — 대장에
자격증명을 두지 않는 것(D93)과 같은 이유다.

> ⚠ **Sprint 8 은 컬럼만 만든다.** 쓰는 쪽(A2A 호출부)은 **미착수**이며 **현재 전 행 NULL 이
> 정상**이다. `spikes/a2a_identity_contract.py` 와 시드 검사 ㉕ 가 *"값이 비었다"* 가 아니라
> *"쓰는 쪽이 없다"* 를 명시적 라벨로 기록한다 — `tool_payload` 가 컬럼만 있고 쓰는 쪽이 없어
> 3차 평가까지 전부 NULL 이었던 전례를 반복하지 않기 위해서다.

**테이블로 두지 않는 것:** 제조사 A/S 연락처(S4 안내용)는 데이터가 아니라 **설정(config) 상수** — 공급사(suppliers.contact)와 성격이 다르고 기종당 1개뿐이라 테이블이 과함.

---

# Sprint 6 확장 — 근거 계층·처분 판정·자산가치 (F1·F2·F4)

> `docs/11_ASSET_LIFECYCLE.md` §7~§8 · `docs/12_*` 의 도구 명세가 읽는 테이블 7종.
> **§10은 없다** — 위 "세는 단위 주의" 참조.

## 11. assets — 호스트 설비 (D68)

> 확장 기능 6종의 **판정 대상**. `equipment`(인버터)는 이 자산의 부품이다.

```sql
CREATE TABLE assets (
  asset_id      TEXT PRIMARY KEY,          -- 'AST-L3-CONV'
  name          TEXT NOT NULL,
  category      TEXT NOT NULL,             -- residual_curve 조인 키 (원본 CSV 바이트 그대로)
  line_id       INTEGER NOT NULL,
  building_id   TEXT,                      -- risk_profile(F6) 자리. 참조 테이블 없으므로 FK 없음
  acquired_at   DATE,
  acquisition_cost INTEGER,
  book_value    INTEGER,
  status        TEXT NOT NULL DEFAULT 'IN_USE',
  -- 법정 조건 사실 (11 §7). NULL = "모른다" → 엔진의 INSUFFICIENT_FACTS 경로 (D62)
  tax_credit_applied       BOOLEAN,
  has_lien                 BOOLEAN,
  lien_creditor            TEXT,
  lien_consent_ref         TEXT,
  insured                  BOOLEAN,        -- D78. NULL=모름 / 0=확인된 미부보 / 1=부보
  policy_id                TEXT,           -- 증권 식별자 전용. 판정은 insured 가 한다 (D78)
  safety_inspection_target BOOLEAN,
  last_inspection_date     DATE,
  inspection_valid_until   DATE,
  -- 자산가치 (12 §9)
  cumulative_repair_cost INTEGER NOT NULL DEFAULT 0,
  last_overhaul_at       DATE,
  controller_generation  TEXT,
  parts_eol_flag         BOOLEAN NOT NULL DEFAULT 0,
  CHECK (status IN ('IN_USE','IDLE','DISPOSAL_PENDING','DISPOSED'))
);
```

**법정 조건 사실이 `equipment` 가 아니라 여기 있는 이유 (D68).** `11 §7` 은 "equipment 확장"이라
썼지만 D68이 대상을 호스트 설비로 바꿨다. 담보·세액공제·안전검사는 **거래 단위**에 붙는 사실이고,
인버터 한 대만 따로 처분하는 일은 없다.

**`NULL`은 `CLEAR`가 아니다 (D62).** 이 절의 사실 컬럼이 NULL 이면 룰 엔진의
`required_facts` 검사에서 누락으로 잡혀 `INSUFFICIENT_FACTS` 가 된다. 시드는 이 경로를
`AST-L4-DUST`(`tax_credit_applied = NULL`)로 재현한다. **"모른다"를 0/false 로 채우지 않는다.**

> ⚠ 정확히는 **엔진이 아니라 `engine.build_facts` 가** 이 성질을 만든다. `evaluate_rule` 의
> 누락 검사는 `f not in facts` 로 **키 존재만** 보므로 `{"tax_credit_applied": None}` 을 그대로
> 넘기면 "값이 있다"로 읽혀 조용히 `CLEAR` 가 된다. `build_facts` 가 NULL 컬럼의 **키를 빼기
> 때문에** NULL→`INSUFFICIENT_FACTS` 가 성립한다. 도구는 `dict(row)` 를 판정기에 직접
> 넘기지 말고 반드시 `build_facts` 를 경유할 것 (`test_rules.py` 가 이 계약을 고정한다).
> 같은 이유로 **판독 불가한 날짜**(`acquired_at='2025/03/01'` 등)도 키째 빠진다 — 원천만 남기면
> `months_since_acquisition` 파생이 실패한 채 `lt` 비교가 False 를 내어 `TAX-CREDIT-2Y` 가
> 조용히 `CLEAR` 로 통과한다.

**`insured` 와 `policy_id` 를 나눈 이유 (D78).** `policy_id` 한 컬럼이 "부보돼 있는가"와
"증권 번호가 무엇인가" 두 질문을 겸하면 **"확인된 미부보"를 적을 자리가 없다** — 값이 있으면
`INSURANCE-NOTIFY` 가 항상 발화하고, 없으면 `required_facts` 누락으로 `INSUFFICIENT_FACTS` 라
**어떤 사실 조합으로도 해제되지 않는 룰**이 된다. `has_lien`/`lien_creditor` 와 같은 꼴로
불리언을 분리해 **NULL=모름 / 0=확인된 미부보 / 1=부보** 세 상태를 전부 표현한다.
시드 9건 중 `AST-L3-LIFT` 만 `insured=0`·`policy_id=NULL` 이고, 이 자산이 유일한 `CLEAR` 재료다.

**안전검사 이력은 대상 기계에만 채운다.** `last_inspection_date`·`inspection_valid_until` 은
`safety_inspection_target = 1` 인 `AST-L2-SPDL` 1건만 값이 있고 **나머지 8건은 NULL** 이다.
비대상 기계에는 검사 자체가 존재하지 않으므로 날짜를 넣으면 **없는 법정 사실을 지어내는 것**이다
(D62·D65). 한때 `SAFETY-INSPECTION.required_facts` 가 트리거가 읽지도 않는 이 두 필드를 요구해
비대상까지 `INSUFFICIENT_FACTS` 가 됐지만, **그건 룰의 결함이었지 시드가 데이터로 덮을 일이 아니었다** —
`required_facts` 정합은 **D77 이 Stage 3(MQ-601b)에서 처리했다**(해당 룰 v2). 데이터로 덮었다면 검증 ⑮
("룰 카탈로그가 실제로 5종 판정을 내는가")가 거짓 통과했을 것이다.

`lien_creditor`·`lien_consent_ref` 는 반대다 — 담보가 **없다**는 건 확인된 사실이므로
"해당 없음"(빈 문자열)이 맞고 NULL 이 아니다. **없음과 모름을 구분하는 게 D62의 요지다.**

**`acquired_at` 은 실행 연도 기준 상대값이다.** `assess_repair_value` 가
`age = 오늘연도 - year(acquired_at)` 으로 잔가 버킷을 잡으므로, 날짜를 고정하면 해가 바뀔 때
버킷이 조용히 밀린다(반복 고장 상대 날짜와 같은 이유).

## 12. law_refs — 계층 1 법령 스냅샷 (조회용 사본)

> **정본은 `data/rules/laws/*.json` 이다 (D60).** 이 테이블은 조인·조회 편의를 위한 사본이며,
> 개정 반영은 파일에서 일어난다.

```sql
CREATE TABLE law_refs (
  law_ref_id TEXT PRIMARY KEY,
  law_name TEXT NOT NULL, article TEXT NOT NULL, clause TEXT,
  title TEXT NOT NULL, text TEXT,
  fetch_status TEXT NOT NULL,
  effective_from DATE, effective_to DATE,
  promulgation_no TEXT, source_url TEXT, retrieved_at DATETIME,
  text_hash TEXT, supersedes TEXT, verification_note TEXT,
  CHECK (fetch_status IN ('PENDING','FETCHED','FAILED'))
);
```

**적재는 반드시 `engine.load_laws()` → `engine.load_rules(laws)` 를 경유한다 (D61).**
파일을 직접 파싱해 INSERT 하면 **근거 없는 룰이 DB 로 들어가는 우회로**가 생긴다.
`RuleIntegrityError` 가 나면 시드는 **전체 중단**하고 만들던 DB 파일을 지운다 — 부분 적재된 DB는
"룰이 몇 개 빠진 채로 전부 CLEAR" 를 만들어내므로 없는 것보다 나쁘다.

**`fetch_status='PENDING'` 이어도 판정과 조문 인용은 정상 동작**한다 — 인용은 조문 번호·제목
기준이기 때문이다. 도구는 `evidence_completeness:"LAW_TEXT_PENDING"` 으로 그 사실을 표시하고,
`build_evidence_bundle` 만 의도적으로 거부한다 — `text_hash` 가 null 이면 해시할 사실이 없다.

> **현재값 (Sprint 7 MQ-701 실수집 이후)** — 조문 7건 중 **6건 `FETCHED` · 1건 `PENDING`**
> (`KR-CITA-ENF-31`, 등록 제목이 API 값과 불일치해 사람 승인 대기). 처분 룰 5종이 인용하는 조문은
> 그 6건에 모두 포함되므로 **실 DB 의 `evidence_completeness` 정상값은 `COMPLETE`** 이고
> `build_evidence_bundle` 은 9자산 × SALE/SCRAP 18조합 전부 `status:"ok"` 다. 근거: `../data/analysis/law_fetch.md`
>
> 위 문단의 `LAW_TEXT_PENDING`·번들 거부 서술은 **삭제하지 않는다** — 새 조문 등록 직후,
> 개정 감지로 `pending_revisions` 가 열렸을 때, 정체성 대조 실패(`KR-CITA-ENF-31`) 때 다시 발화하는 계약이다.

⚠ **JSON 을 채운 뒤 재시드가 필요하다** (`uv run python data/seed.py --with-error-codes`).
이 테이블은 사본이라(D60) 빠뜨리면 파일만 바뀌고 도구·REST 는 옛 DB 를 본다.

## 13. rules — 계층 2 해석 룰 (조회용 사본)

```sql
CREATE TABLE rules (
  rule_id TEXT NOT NULL, rule_version INTEGER NOT NULL,
  label TEXT NOT NULL, category TEXT NOT NULL,
  disposal_type TEXT NOT NULL, source_type TEXT NOT NULL,
  law_refs TEXT NOT NULL, contract_refs TEXT NOT NULL,   -- JSON array
  interpretation TEXT NOT NULL, required_facts TEXT NOT NULL,
  trigger TEXT NOT NULL, boundary TEXT,
  message TEXT NOT NULL, resolve_options TEXT NOT NULL,
  confidence TEXT NOT NULL, requires_expert_review BOOLEAN NOT NULL,
  PRIMARY KEY (rule_id, rule_version),
  CHECK (disposal_type IN ('BLOCKING','PRECONDITION','AUTO_CLOSE')),
  CHECK (source_type IN ('LAW','CONTRACT')),
  CHECK (json_valid(law_refs) AND json_valid(contract_refs) AND json_valid(trigger))
);
```

**`(rule_id, rule_version)` 복합 PK = "해석은 개정된다".** 같은 룰의 옛 버전을 지우면
과거 결정이 어떤 해석 아래 내려졌는지 재현할 수 없다 — `decisions.evidence_bundle` 이
`rule_version` 을 박아 두는 것과 짝이다.

정본은 `data/rules/rules/*.json`(5건). **지출 판정 룰을 이 디렉토리에 넣지 말 것** —
`check_disposal_blockers` 가 디렉토리 전체를 로드하므로 처분 판정에 섞여 들어간다.

## 14. decisions — 계층 3 서명

> **⚠ 이 테이블에는 MCP 도구가 쓴다.** `generate_disposal_document`(`04 §15`)가 **`state='draft'`
> INSERT 만** 한다 (D81). UPDATE·DELETE 는 TEMP TRIGGER 로 **물리 차단**된다
> (`mcp_server/db.py:decision_writer`, D10). 상태 전이는 전부 사람 전용 API(`06 §2.6`)를 통한다.
> `po_drafts` 와 **정확히 같은 태도**다 — 도구는 초안을 올릴 뿐, 확정은 사람이 서명한다.
>
> (이 절은 Sprint 6 까지 *"MCP 도구는 이 테이블에 손대지 않는다"* 라고 **거짓을 말하고 있었다** —
> reviewer W-9. D81 착지로 뒤집혔고 MQ-712 가 DDL 본문까지 정정했다.)

**아래 DDL 은 `data/seed.py` 의 `SCHEMA`(정본, `§14 decisions`)와 대조한 실제 형태다.**

```sql
CREATE TABLE decisions (
  decision_id TEXT PRIMARY KEY,
  asset_id  TEXT NOT NULL REFERENCES assets,
  decision_type TEXT NOT NULL,           -- 'DISPOSAL' | 'REPAIR'
  evidence_bundle TEXT NOT NULL,         -- JSON 5키 (D83): {laws[], rules[], evaluated[], contracts[], facts{}}
  bundle_hash TEXT NOT NULL,
  verdict_at_signing TEXT NOT NULL,      -- draft 시점 판정. 서명 시 백엔드가 재산출해 덮는다 (D84)
  override BOOLEAN NOT NULL DEFAULT 0,
  override_reason TEXT,
  reviewed_by TEXT REFERENCES users,
  signed_at DATETIME,
  state TEXT NOT NULL DEFAULT 'draft',
  -- ── Sprint 7 (MQ-707) 보강 컬럼 5개 ───────────────────────────────────────
  reason TEXT,                           -- 도구가 채우는 요청 사유. `po_drafts.reason` 과 같은 자리
  requested_by TEXT REFERENCES users,    -- ★ 도구가 채우지 않는다 (D23·D37) — 백엔드가 stamp
  session_id TEXT,                       -- ★ 같음. 도구 스키마에 있으면 LLM 위조 경로가 된다
  decision_note TEXT,                    -- 반려 사유 / 서명 코멘트 (`po_drafts.decision_note` 와 같은 역할)
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,   -- 통합 큐(D85)가 created_at DESC 로 정렬
  -- ── CHECK 5종 (그중 아래 2종이 Sprint 7 신설) ────────────────────────────
  -- D63 을 스키마로 잠근다 — 사유 없는 override 는 저장 자체가 불가
  CHECK (override = 0 OR (override_reason IS NOT NULL AND length(trim(override_reason)) > 0)),
  CHECK (json_valid(evidence_bundle)),
  CHECK (state IN ('draft','pending','signed','rejected')),
  -- ★ 신설 ① "서명 없는 처분 확정 0건"
  CHECK (state <> 'signed' OR (signed_at IS NOT NULL
                               AND reviewed_by IS NOT NULL
                               AND length(trim(bundle_hash)) > 0)),
  -- ★ 신설 ② "BLOCKING 우회 처분 0건"
  CHECK (state <> 'signed' OR override = 1
         OR verdict_at_signing IN ('CONDITIONAL','CLEAR'))
);
```

**`created_at` 에 `DEFAULT` 가 있는 이유**: 도구의 draft INSERT 컬럼 목록이 **한 글자도 바뀌지
않는다.** `requested_by`·`session_id`·`decision_note` 도 NULL 허용이라 같다 — `po_drafts` 와 같은 패턴이다.

**⚠ `decision_note` 는 명세(MQ-707)에 없던 컬럼이다.** 3컬럼만 두면 `POST /sign{note}`·
`/reject{reason}` 의 값을 담을 자리가 없어 **사유가 저장되지 않는다** — D38 이 요구한 것은 반려
사유를 *받는 것*이 아니라 *남기는 것*이다.

### CHECK 2종이 "두 문장"의 **마지막 층**이다

위쪽 층은 전부 코드다 — 도구는 UPDATE 권한이 없고(D10), 서명 API 는 순서를 강제한다(D84).
**그러나 코드 층은 버그로 뚫린다.** 미래의 잘못된 UPDATE 한 줄, 마이그레이션 스크립트, 콘솔에서
친 SQL — 어느 것이든 코드를 우회한다. **스키마는 우회할 수 없다.**

- 신설 ① — `signed` 는 *"누가 언제 무엇에 서명했는가"* 가 전부 있어야 성립하는 상태다.
  셋 중 하나라도 없는 행은 **서명처럼 보이는 행**이지 서명이 아니다.
- 신설 ② — 차단 판정(`BLOCKED`·`HOLD`·`INSUFFICIENT_FACTS`)에 서명하려면 `override=1` 이어야 하고,
  `override=1` 이면 위 D63 CHECK 가 사유를 강제한다. **두 CHECK 가 맞물려 "사유 없는 우회 서명"이
  스키마 수준에서 표현 불가능**해진다.
- ⚠ ② 에 열거된 두 값은 `engine.VERDICTS` 의 **비차단** 어휘다. 엔진이 어휘를 늘리면 이 목록이
  조용히 낡으므로 **시드 검증 ㉑ 이 DDL 문자열을 파싱해 엔진과 대조**한다.

**D63을 문서가 아니라 스키마로 잠갔다.** "override 하려면 사유를 쓰라"를 애플리케이션 검증에만
두면 경로 하나만 빠뜨려도 사유 없는 무시가 저장된다. 시드 검증 **⑰⑲⑳㉑** 이 실제로 INSERT 를
시도해 CHECK 가 거부하는지 확인한다(⑩ FK 프로브와 같은 이유 — 한 번도 실행되지 않는 제약은
있는 셈 치기 쉽다). `spikes/disposal_sign_contract.py` 가 **9자산 × 3모드 27조합 전수**로 4층을
각각 독립 확인한다.

## 15. flags — 법정 조건 상태

```sql
CREATE TABLE flags (
  flag_id INTEGER PRIMARY KEY,
  asset_id TEXT NOT NULL REFERENCES assets,
  rule_id TEXT NOT NULL, rule_version INTEGER NOT NULL,
  disposal_type TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'OPEN',
  raised_at DATETIME NOT NULL, resolved_at DATETIME,
  resolved_by TEXT REFERENCES users, evidence_ref TEXT,
  CHECK (state IN ('OPEN','IN_PROGRESS','RESOLVED','WAIVED'))
);
```

발생 → 이행 → 해소의 **상태**를 남긴다. 기한 추적(`deadlines`, F5)과 성격이 다르다 —
이쪽은 "무엇이 걸렸고 누가 어떻게 풀었는가"이고 저쪽은 "언제까지"다. **Sprint 6 시드는 0행**
(쓰기 경로가 Sprint 7이므로 지어낸 이력을 넣지 않는다).

## 16. repair_records — 수리 증빙

> **Sprint 9(MQ-904, D98) 개정 — 15컬럼 → 19컬럼 + CHECK 3종.** 쓰기 도구 `create_repair_record`
> (`04 §16`)가 `state='draft'` INSERT 만 하고, 전이는 `POST /api/repairs/*`(`06 §2.8`)가 한다.
> **DDL 정본은 `data/seed.py` 의 `SCHEMA` 문자열**이고 아래는 그 사본이다.

```sql
CREATE TABLE repair_records (
  repair_id TEXT PRIMARY KEY,
  equipment_id TEXT NOT NULL REFERENCES equipment,   -- 수리는 인버터 단위 (D68 ⓑ)
  model TEXT, error_code TEXT,
  part_class TEXT,
  work_type TEXT NOT NULL,               -- PLANNED | UNPLANNED  ★미기재 거부 (12 §7)
  expenditure_class TEXT,                -- CAPITAL | REVENUE | HOLD
  cost INTEGER NOT NULL,
  downtime_hours REAL,                   -- MTTR 산식의 유일한 원천
  parts TEXT,                            -- JSON array
  performed_by TEXT REFERENCES users, verified_by TEXT REFERENCES users,
  signed_at DATETIME, record_hash TEXT,
  state TEXT NOT NULL DEFAULT 'draft',
  -- ★ Sprint 9 신설 (D98) — 도구는 이 넷을 채우지 않는다. 백엔드가 X-User·세션에서 stamp 한다
  --   (D23·D37). `data/repair_hash.py` 가 `record_hash` 규약의 단일 출처다.
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  requested_by TEXT REFERENCES users,
  session_id TEXT,
  note TEXT,                             -- 반려 사유·서명 메모 (D38 — 반려는 이유가 필수)
  FOREIGN KEY (model, error_code) REFERENCES error_codes(model, code),  -- D13·D33
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
```

**`downtime_hours` 는 `12 §9` 에 없는 컬럼이다.** `12 §2` 가 MTTR 을 요구하는데 저장소에
수리 시간 원천이 전혀 없어 추가했다. (`12 §9` 본문 반영은 MQ-613.)

**`created_at` 은 '요청(draft INSERT) 시각'이지 '수리 시각'이 아니다.** MTTR·예방보전 비율·
누적 수리비를 `window_months` 로 자르는 원천으로는 여전히 쓸 수 없다 — 실제 수리가 일어난
시점을 담는 컬럼은 이 테이블에 없고, 그 사실이 `get_maintenance_metrics.excluded[]` 에 실린다
(`data/maint_value.py` 주석 참조). Sprint 9 이전에는 "수리 시각 컬럼이 없다"고 적혀 있었는데
`created_at` 신설로 문장이 낡았다 — 컬럼은 생겼지만 **수리 시각의 원천은 여전히 없다**.

**`signed_at IS NULL` 인 레코드는 지표에서 제외된다 (`12 §11`).** 시드 12건 중
**`RPR-2403`(INV-L3-01) 1건이 미서명**이며, `get_maintenance_metrics` 의 `excluded[]` 문장과
`planned_ratio` 분모 제외가 이 한 행으로 검증된다. `assets.cumulative_repair_cost` 도
**서명분만** 합산한다.

**`(model, error_code)` 는 짝이거나 둘 다 NULL 이다 (D13·D33).** `--with-error-codes` 없이
시드하면 `error_codes` 가 0행이라 복합 FK 를 만족시킬 수 없어 둘 다 NULL 로 넣는다
(`po_drafts` 와 같은 처리). 계획 정비(`PLANNED`)는 애초에 에러코드가 없어 항상 NULL 이다.

**`record_hash` 는 서명 11건 전량 값이 있다 (Sprint 9 이전에는 전량 NULL 이었다).**
서명 해시 규약(키 정렬·구분자 고정)은 `data/repair_hash.py`(`HASHED_KEYS`·`canonical_json`·
`compute_record_hash`, MQ-904)가 단일 출처이고, 시드 검사 ㉙ 이 서명 11행 전건을 재계산해
저장값과 대조한다(D84 태도). 미서명 1건(`RPR-2403`)만 `record_hash IS NULL` 이다.

## 17. residual_curve — 잔가율 격자 (D65·D74)

> 정본은 `data/extracted/residual_curve.json`(`data/build_residual_curve.py` 산출).
> 🔴 **파생 결과를 새로 테이블로 올리려면 먼저 [`data/extracted/README.md`](../data/extracted/README.md) 를 읽을 것**
> — 승격 게이트 조건과 4단계 절차가 거기 있다 (**D106**). ⚠ 이 절(`residual_curve`)은 **4단계 중 ④(파일↔DB
> drift 자가검증)가 없다** — 베낄 때 ④는 `error_codes` 검사 ㉚ 을 보고 채운다.

```sql
CREATE TABLE residual_curve (
  category   TEXT NOT NULL,
  age_bucket TEXT NOT NULL,          -- '0-2'|'3-5'|'6-10'|'11-15'|'16-20'|'21-30'
  residual_ratio REAL NOT NULL,
  n_samples INTEGER,                 -- 목업이면 NULL (D74)
  p25_ratio REAL, p75_ratio REAL,    -- 목업이면 NULL
  base_n    INTEGER,                 -- 목업이면 NULL (D74)
  source TEXT NOT NULL,              -- 목업임이 이 필드에 명시된다
  PRIMARY KEY (category, age_bucket)
);
```

**표본 필드 4종이 nullable 인 이유 (D74).** 값 원천이 호가 중앙값에서 **목업 정률 공식**으로
바뀌면서 표본 개념 자체가 사라졌다. `NOT NULL` 을 걸면 "표본이 없는데 표본 수를 채우는"
거짓말을 스키마가 강제하게 된다.

**현재 42행 = 카테고리 7 × 버킷 6, 격자 공백 없음.** 검증 ⑯ 은 행 수를 하드코딩하지 않고
`총행수 == 카테고리수 × 버킷수` 로 본다 — 검사해야 할 성질은 "36행"이 아니라 **격자에 구멍이
없는가**이고, 카테고리가 늘 때마다 상수를 고치면 그 사이 위양성 FAIL 이 난다.

**`category` 문자열은 원본 CSV 바이트 그대로다.** `'환경  설비'` 는 **공백 2칸**이며
`data/data_list.md §6-1` 의 `환경설비` 표기가 오기다. 문서에서 베끼지 말 것.
카테고리 선정 기준은 `data/analysis/residual_curve.md §2-6`.

**곡선이 없으면 시드는 0행으로 성공한다.** 소비 측(`assess_repair_value`)이 `HOLD` 를 내는 게
정답이지, 시드가 죽어 DB 자체가 없어지는 건 과잉이다.

---

# Sprint 8 확장 — A2A 신원 식별 기반층

> `docs/A2A_IDENTITY.md`·`docs/A2A_CONTRACTS.md` 가 참조하는 **기반층 1종**.
> 이 절이 더해져(Sprint 8 시점) `CREATE TABLE` 은 **19개**, 절은 **18절**이 됐다 — Sprint 10 이
> `part_lifecycle_mock`(§19)을 더해 **20개 / 19절**, Sprint 11 이 §20~§23(`deadlines`·`incidents`·
> `ownership_checks`·`risk_profile`)을 더해 지금은 **24개 / 23절**이다(서두 "세는 단위 주의" 참조).
> ⚠ **A2A 호출부는 미착수다** — 이 스프린트가 만드는 것은 **대장(테이블)과 계측 자리**뿐이다.

## 18. partner_links — 외부 파트너 subject 매핑 대장 (D91·D92·D95·D96)

> *"나가는 A2A 요청의 **subject**(누구 건인가)를 무엇으로 적을 것인가"* 의 원천.
> `link_state` 가 연결 승인 여부를, `external_ref` 가 상대 시스템 식별자를 담는다.
> **DDL 정본은 `data/seed.py` 의 `SCHEMA` 문자열**이고 아래는 그 사본이다.

```sql
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
  -- ⚠ 날짜가 아니라 **시각**이다 (D96-ⓓ) — 자격증명 발급이 이 시점에 붙으므로 감사에는
  --    "며칠"이 아니라 "몇 시 몇 분"이 필요하다. **저장은 UTC** (D39, `traces.ts` 와 같은 규약).
  linked_at    DATETIME,
  PRIMARY KEY (partner, subject_type, subject_ref),
  -- NULL 은 이 CHECK 에서 NULL 로 평가돼 통과한다 = "모름"이 표현 가능하다 (D62). 의도된 동작이다
  CHECK (link_state IN ('NOT_LINKED','LINKED')),
  -- ★ null-safe `IS` (D96). `=` 로 쓰면 (link_state NULL, external_ref 있음) 이 조용히 통과한다
  CHECK (external_ref IS NULL OR link_state IS 'LINKED')
);
```

### ⛔ 인증 정보가 아니다 (actor / subject 분리)

여기 행이 있다는 사실은 **"우리가 아는 상대 식별자"** 일 뿐이며 상대 시스템의 **승인 근거가
되지 않는다.** **actor**(누가 호출했나)는 파트너 토큰이 담당하고(D93 — `.env` + 프로세스 메모리
캐시, `backend/a2a/credentials.py` 한 곳), 이 대장은 **나가는 요청 payload 의 subject 값**만
공급한다. 그래서 **자격증명을 이 테이블에 넣지 않는다** — 넣는 순간 D91 이 세운 actor/subject
분리가 스키마에서 무너진다. MCP 도구는 이 테이블에 쓰지 않는다(절대 규칙 1 — 쓰기 도구는 3종뿐).

### 왜 `assets` 확장이 아닌가 (결/grain, D91)

A2A_Q 의 원 요청은 `assets.finallq_company_id` 컬럼 추가였는데 **결이 어긋난다.**
`finallq_company_id` 는 **회사 1개** 단위 사실인데 `assets` 는 **9행**이라 같은 값이 9번 복제되고,
한 행만 안 고쳐지는 종류의 drift 가 시작된다(D60 — 원본은 하나). 이건 가정이 아니라 **이미 벌어져
있는 일**이다: `policy_id` 가 9건 중 **8건 모두 `POL-2026-FIRE-01`** 로, 이름과 달리 자산 단위가
아니라 **건물·회사 단위 사실이 자산 행에 복제된 상태**다(화재보험 목적물은 원래 건물이다).
그래서 사실의 결마다 행을 갖는 **별도 대장**으로 두고, 결은 `subject_type`(`company`/`building`/
`asset`)이 표현한다.

### 왜 판정(`link_state`)과 식별자(`external_ref`)를 나누는가 (D78 패턴)

`insured` / `policy_id` 를 나눈 것과 **같은 이유**다. 한 컬럼이 *"연결돼 있는가"* 와 *"상대 키가
무엇인가"* 를 겸하면 **"확인된 미연결"을 적을 자리가 없고**, 더 나쁘게는 **식별자 존재가 곧 승인
판정이 되어** *"식별자만으로 승인"* 상태가 스키마에 박힌다. 나누면 그 성격이 주석이 아니라
**구조**로 표현된다.

| `link_state` | 뜻 | `external_ref` |
|---|---|---|
| `NULL` | **모름** (아직 확인 안 함) — D62 의 3상태 | NULL 만 가능 |
| `'NOT_LINKED'` | **확인된 미연결** | NULL 만 가능 |
| `'LINKED'` | 사람 **연결 승인 완료** | NULL 도 값도 가능 |

CHECK 가 막는 것은 *"식별자가 있는데 승인이 없다"* 이지 *"승인은 있는데 식별자가 없다"* 가
**아니다** — 그래서 InsuQ 의 `LINKED` + `external_ref IS NULL` 행이 DDL 상 성립한다.

### 왜 `=` 가 아니라 `IS` 인가 (D96-ⓐ — 3값 논리)

SQLite CHECK 는 **결과가 NULL 이면 통과**시킨다. sqlite 3.50.4 에서 직접 재현한 결과:

```
-- 원문 CHECK (link_state = 'LINKED' OR external_ref IS NULL) 에
INSERT (link_state=NULL, external_ref='CMP-001')  →  NULL OR 0 → NULL  →  ★ 통과했다
-- 정정 CHECK (external_ref IS NULL OR link_state IS 'LINKED') 에서 같은 행
INSERT (link_state=NULL, external_ref='CMP-001')  →  0 OR 0  → 0       →  거부
INSERT (link_state=NULL, external_ref=NULL)       →  1                 →  통과 (=모름은 살아 있다)
```

즉 `=` 로 쓰면 D91 이 금지한 *"식별자 존재가 곧 승인"* 이 **가장 애매한 칸에서 통과**한다.
`IS` 로 바꾸면 그 행만 죽고 **D62 의 "모름"(NULL+NULL)은 그대로 통과**한다 — D78 이 분리한
판정/식별자를 되붙이지 않는다. 시드 검사 ㉓ 이 **음성 3 + 양성 2** 로 이 두 CHECK 를 잠근다
(양성이 없으면 "전부 거부하는 CHECK" 도 통과해 검사가 방어선이 아니게 된다).

### 왜 회사 결의 `subject_ref` 가 `''` 인가 (D96-ⓑ)

SQLite 는 `INTEGER PRIMARY KEY` 가 아닌 PK 컬럼의 NULL 을 허용하고 **NULL 끼리는 서로 다르다.**
실제로 `subject_ref=NULL` 인 **동일 행을 3회 INSERT 했더니 전부 통과해 3행이 남았다** — 회사 매핑이
2행·3행으로 갈려도 아무도 모른다. 그래서 `NOT NULL` + **확인된 해당 없음은 `''`** 이다.
이 레포의 기존 선례 그대로다 — `lien_creditor`/`lien_consent_ref` 가 *"담보 없음은 `''`, 모름은
NULL"* 이고 검사 ⑱ 이 그 규약을 지킨다(D62). 가짜 로컬 키(`'MAINTQ'`)를 지어내지 않는 것은 D65.

**`partner`·`subject_type` 에는 CHECK 를 걸지 않는다** (D96-ⓒ) — 파트너가 늘 때마다 DDL 을 고치게
된다. 값 규약은 **회귀가 본다**(시드 검사 ㉒-ⓑ). `traces.tool` 이 CHECK 없는 자유 TEXT 이고
`a2a:<skill>` 접두어를 규약으로만 둔 것(D94-ⓑ)과 같은 태도다.

### `assets.policy_id` 와의 관계 (D95)

**증권 식별자의 정본은 `assets.policy_id` 하나**이고, **InsuQ 행의 `external_ref` 는 NULL 이다.**
`partner_links` 는 **연결 승인 여부만** 담는다. 옮기지도 복제하지도 않으며, **복제 0건**을 시드
검사 ㉔ 가 음성 검사로 확인한다(`external_ref IN (SELECT policy_id FROM assets …)` = 0).
건물 3행에 `POL-2026-FIRE-01` 을 복제하면 D91 이 기각한 형태(단위가 다른 사실의 복제)를 **결만
바꿔 재발**시키는 것이 된다.

⚠ **판정은 `insured` 가 한다 (D78) — `policy_id` 는 증권 식별자일 뿐**이며 있어도 판정을 바꾸지
않는다(`data/rules/test_rules.py` 가 직접 검사). 그러므로 이 컬럼을 옮기지 않는 이유는 *"룰이
읽어서"* 가 아니라 **의존처가 룰 밖에 흩어져 있어서**다(`data/rules/engine.py` 의
`ASSET_FACT_COLUMNS` · `generate_disposal_document` 의 증권 식별자 렌더 · `data/ownership.py` ·
`spikes/rules_db_load.py` · `spikes/approvals_contract.py`).

### 시드 5행 (D92) — `BLD-D` 가 대조군인 이유

| partner | subject_type | subject_ref | link_state | external_ref |
|---|---|---|---|---|
| `finallq` | `company` | `''` | `LINKED` | `CMP-MAINTQ-001` ← 유일하게 식별자를 갖는 행 |
| `insuq` | `building` | `BLD-A` | `LINKED` | **NULL** |
| `insuq` | `building` | `BLD-B` | `LINKED` | **NULL** |
| `insuq` | `building` | `BLD-C` | `LINKED` | **NULL** |
| `insuq` | `building` | **`BLD-D`** | **`NOT_LINKED`** | **NULL** ← **대조군** |

`LINKED` 만 심으면 *"연결 승인은 사람 단계"* 라는 전제가 **데모에서 한 번도 드러나지 않는다.**
`NOT_LINKED` 건물이 1건 있으면 *"연결 안 된 건물에는 S11·S14 를 못 쏜다"* 가 실제로 보인다 —
D78 이 `AST-L3-LIFT` 한 건만 `insured=0` 으로 남겨 `CLEAR` 경로를 확보한 것과 **같은 설계**다.

대조군을 `BLD-D` 로 고른 근거 (시드 실측):

| building | 자산 | `insured` / `policy_id` |
|---|---|---|
| `BLD-A` | `AST-L1-CONV` | 1 / `POL-2026-FIRE-01` |
| `BLD-B` | `AST-L2-SPDL`·`AST-L2-CLNT` | 1 / `POL-2026-FIRE-01` |
| `BLD-C` | `AST-L3-CONV`·`AST-L3-EXFAN` / **`AST-L3-LIFT`** | 1 / `POL…` · **0 / NULL** |
| **`BLD-D`** | `AST-L4-CONV`·`AST-L4-WRAP`·`AST-L4-DUST` | **전부 1 / `POL-2026-FIRE-01`** |

- `BLD-C` 를 대조군으로 쓰면 **미부보(`insured=0`)와 미연결(`NOT_LINKED`)이 한 건물에 겹쳐**
  두 축이 섞인다 — 데모에서 *"보험이 없어서 못 쏘는 것"* 으로 오독된다.
- `BLD-D` 는 **자산 3건이 전부 부보돼 있는데도 미연결**이다. 그래서 *"부보돼 있어도 A2A 연결
  승인이 없으면 S11·S14 를 못 쏜다"* 가 한눈에 보인다 — D91 의 actor/subject 분리를 **데이터가
  직접 증명**한다. 자산 수가 가장 많아(3건) 화면·쿼리에서도 눈에 띈다.

> ⛔ **`link_state` 와 `insured` 를 엮지 않는다 — 별개 축이다.** *"부보돼 있다"(보험 사실)* 와
> *"InsuQ 와 A2A 연결이 승인됐다"(파트너 대장)* 는 서로 다른 사실이며, `NOT_LINKED` 건물의 자산이
> `policy_id` 를 갖고 있는 것은 **모순이 아니다.** 두 축을 엮는 검사·쿼리를 만들면 **D78 이 분리한
> 두 사실을 되붙이는** 셈이 된다 — 검사 ㉔ 도 그래서 `link_state` 조건을 넣지 않는다.

> ⚠ **시드 전제(목업)다 — 실제 발급값·연결 승인이 아니다.** `LINKED` 4행도 `CMP-MAINTQ-001` 도
> 사람이 받은 실값이 아니고 **A2A 호출부 자체가 미착수**다. 고지 문구는 하드코딩이 아니라
> `data/seed.py` 의 `PARTNER_LINKS_MOCK` **상태에서 유도**되며(`partner_links_caveat()`, D90 —
> `part_class_caveat()` 선례), **시드 검사 ㉒-ⓕ 가 문구와 접두 기호 두 축을 함께 잠근다**
> (문구 축만 보면 *"`[사람 확인]` ⚠ … 목업 …"* 같은 **자기모순 라벨**이 통과한다).
> 사람이 실값을 받으면 플래그를 `False` 로 바꾸고, **줄은 없애지 않고 문구만 바꾼다**(D90).

**FK 를 걸지 않는다.** `subject_ref` 는 결에 따라 회사(`''`)·건물(`assets.building_id`)·자산을
가리키는 **다형 참조**라 걸 대상이 하나로 정해지지 않는다 — `building_id` 자체가 FK 없는 것과 같은
이유다. 대신 **검사 ㉒-ⓒ 가 insuq 의 `building` 결 행 집합을 `assets` 의 distinct `building_id` 와
동적으로 대조**한다(하드코딩 4종이 아니라 동적 대조여야, 건물이 늘 때 대장 누락을 즉시 잡는다).

**`linked_at` 은 실행일 기준 상대 시각이고 UTC 로 적는다** (D96-ⓓ·D39). 고정 값을 박으면 해가
바뀔 때 조용히 밀리고, 로컬 시각을 쓰면 검증(㉒-ⓓ)이 다른 시계를 보고 **자정 근처에서 위양성
FAIL** 한다. ⛔ `--today` 로 날짜를 핀하면 `linked_at` 이 *"지금보다 미래"* 가 되어 같은 검사가
위양성 FAIL 한다 — 감사 시점은 재현 대상이 아니다.

## 19. part_lifecycle_mock — 부품 생애주기 경고 목업 (Sprint 10 브레인스토밍 D)

> 설비 하이라이트 대시보드(`GET /api/assets/{asset_id}/hotspot-status`, `docs/06_REPO_API.md`)가
> 🟠(곧 점검) 판정에 쓰는 **유일한 출처**. `equipment` × 하이라이트 대상 부품 3종(냉각팬·키패드·
> 제어보드 — `frontend/lib/hotspots.ts`·`data/hotspot_status.py`의 `MODEL_HOTSPOT_PARTS`와 `part_no`가
> 짝이어야 한다) 조합마다 "다음 점검 예정일" 1행을 둔다.

```sql
-- §19 part_lifecycle_mock — 생애주기 경고(D) 목업 (Sprint 10 브레인스토밍).
-- ⛔ 실 텔레메트리·정비 이력에서 유도하지 않는다 — 사용자가 명시적으로 "새 가짜 필드,
--    부품별 다음 점검일 직접 부여"를 선택했다. 화면에 mock 고지 필수(D65).
CREATE TABLE part_lifecycle_mock (
  equipment_id TEXT NOT NULL REFERENCES equipment,
  part_no      TEXT NOT NULL REFERENCES parts,
  next_maintenance_due DATE NOT NULL,
  PRIMARY KEY (equipment_id, part_no)
);
```

### 설계 포인트

**실 텔레메트리가 아니라 명시적 목업이다** — 이 프로젝트에 정비 이력 기반 예지보전 로직이 없고
(spec §4-5), 사용자가 "새 가짜 필드로 부품별 다음 점검일을 직접 부여" 방식을 선택했다. 그래서
화면(`EquipmentHotspotDiagram.tsx` 확대 패널)은 이 값을 보여줄 때 **"생애주기 mock 데이터입니다 —
실제 정비 이력에서 유도한 값이 아닙니다"** 고지를 함께 렌더해야 한다(D65) — 수동 확인(Task 10)에서
🟠 항목마다 이 문구가 뜨는 것을 확인했다.

`equipment`·`parts` 에 FK 를 걸되 **`next_maintenance_due` 자체에는 CHECK 를 두지 않는다** — 이미
지난 날짜(overdue)도 유효한 상태이고(임박도를 판정하는 것은 `data/hotspot_status.py`의
`M_UPCOMING_DAYS` 창이지 DDL 이 아니다), 날짜 하한을 스키마에 박으면 "지금 막 지난 점검일"을
표현할 자리가 없어진다. 색 우선순위는 🔴(이상탐지) > 🔵(최근 수리) > 🟠(곧 점검) 이므로 같은
부품에 진단 이력이나 최근 서명 수리가 있으면 이 테이블 값은 조회는 되어도 최종 색에는 반영되지
않는다 — `hotspot_status()` 가 순서대로 판정하고 하나만 고른다.

시드는 9개 자산(`equipment`) × 부품 3종 = **27행** 고정이며, `next_maintenance_due` 는
`--today` 기준 상대 오프셋(`PART_LIFECYCLE_MOCK` 의 `offset_days`)으로 계산한다 — 이미 지난 것
(음수)·임박·여유 있는 것을 섞어 데모 다양성을 확보한다. 시드 검사 ㉛ 이 행수 27과 모델-부품 정합
(`model` 이 `iG5A` 면 `part_no` 에 `IG5`, `S100` 이면 `S100` 포함)을 확인한다.

---

# Sprint 11 확장 — 기한·사고·실사 보존·위험 프로파일 (F5·F6)

> `docs/11_ASSET_LIFECYCLE.md §10-2` 가 초안으로 남겨 둔 4테이블을 DDL 로 확정한다(MQ-1101,
> D102 로 F5·F6 가 본 범위에 편입). **DDL 정본은 `data/seed.py` 의 `SCHEMA` 문자열**이고
> 아래는 그 사본이다(D60 과 같은 사본 규약). 넷 다 `assets`(또는 `assets.building_id`)를
> 참조하는 결이라 **`seed_assets()` 이후**에 적재한다.
>
> ⛔ **D10 — MCP 쓰기 도구는 `create_po_draft`·`generate_disposal_document`·`create_repair_record`
> 3종뿐이다.** 넷 중 어느 테이블도 이 3종의 쓰기 대상이 아니고, **향후에도 그렇다** — 새 도구가
> 이 절의 테이블에 쓰게 하려면 그 자체가 계약 변경(새 쓰기 도구 4번째)이라 이 문서 수정만으로는
> 안 된다. `deadlines`·`ownership_checks`는 이번 스프린트에서 **시드가** INSERT 하지만, 그건
> "MCP 도구가 쓴다"가 아니라 "사람이 승인한 값을 시드/백엔드 서비스가 채운다"는 뜻이다.

## 20. deadlines — 기한 추적

> *시점*을 관리한다. `flags`(§15)는 *상태*(발생→이행→해소)를 관리해 성격이 다르다 —
> 같은 사안이 양쪽에 각각 걸린다: `LIEN-CONSENT` 는 flag, "세액공제 사후관리 24개월"은 deadline.
> `TAX-CREDIT-2Y`(`11 §3`)가 `months_since_acquisition` 을 쓰고 경계(`review_band [22,26]`)까지
> 있는데, 기한이 다가오는 걸 미리 알 방법이 없었다 — 지금은 처분을 요청해야만 `BLOCKED` 를 안다.

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

**anchor 가 `decision_id` 가 아니라 `asset_id` 인 이유** — §10-2 초안은 `decision_id` 를 anchor로
적었으나, 기한은 **결정 이전에** 자산 사실(취득일 등)에서 바로 계산된다. 결정에 종속시키면
"아직 처분을 시도한 적 없는 자산의 기한"을 표현할 자리가 없어져 `track_deadlines`(F5, MQ-1102)의
핵심 가치("BLOCKED 를 미리 안다")가 성립하지 않는다. `decision_id` 는 특정 서명 결정에서 파생된
기한만 채우는 **nullable 부가 필드**로 남긴다.

**시드는 0행이다** — `flags` 와 같은 이유로 쓰기 경로가 없다(절대 규칙 1). 시드 검사 ㉜ 이
0행 유지와 함께 **잘못된 `type` 값의 INSERT 를 실제로 시도**해 CHECK 가 거부하는지 확인한다.

## 21. incidents — 물리적 사고 이력

> `error_history` 와 별개다 — 그건 인버터 에러코드 트립이고 이것은 충돌·정렬 손상처럼
> **회복 불가능한** 감가 신호다(`12 §1`이 "충돌·사고 이력은 마이너스다 — 베드·주축 정렬이
> 영구히 틀어지면 정밀도가 회복되지 않는다"고 써 뒀지만 담을 테이블이 없었다).
> `verify_ownership`(§9)의 '가동 이력 → 알람 이력' 항목이 이미 이 구분을 그대로 쓴다:
> *"error_history 는 인버터 에러코드 이력이며 자산 전체의 알람 이력이 아니다"*(D68 ⓑ).

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

**시드 2행**: `AST-L2-SPDL`/`COLLISION`(약 2년 전, `book_value_at_loss` 는 그 시점 정액법 추정치
6,000,000 — `seed_assets` 의 `BOOK_VALUE_LIFE_YEARS`·`BOOK_VALUE_FLOOR_RATIO` 산식을 사고 시점
연차에 적용), `AST-L4-WRAP`/`OTHER`(`book_value_at_loss=NULL` — 모르는 값을 0 으로 채우지 않는다,
D62). `recorded_by=NULL`. 시드 검사 ㉝ 이 2행·FK 정합(고아 0건)·`type` enum 밖 0건을 확인한다.

## 22. ownership_checks — 권리관계·실사 확인 결과 보존

> `verify_ownership`(S18, `04 §9`)이 9개 카테고리를 확인한 **결과를 남길 자리가 없어서**
> 매번 처음부터 다시 확인해야 했다. 이 테이블은 그 판정의 **스냅샷**만 담는다 — `verify_ownership`
> 자체의 판정 스키마(9카테고리·38항목, `PARTIAL` 비승격, `11 §6`)는 바꾸지 않는다.

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

**시드 38행**: `AST-L3-LIFT` 의 `verify_ownership` **실제 출력**(`data/ownership.py:verify()` 를
직접 호출해 확인, 추측 금지)을 그대로 옮겨 심는다 — 9카테고리(물리적 상태 5·가동 이력 5·정비
이력 4·기술적 진부화 4·권리관계 6·법정 요건 3·재무·회계 3·시장·가격 3·이전 비용 5 = **38항목**).
`checked_at` ≈ 1개월 전, `checked_by=NULL`. 시드 검사 ㉞ 가 DB 행수를 **하드코딩 38이 아니라
`verify_ownership()` 을 그 자리에서 다시 호출한 실측치와 대조**하고(판정기가 항목을 늘리면 시드가
조용히 낡는 것을 막는다), either-or CHECK 2종(`VERIFIED`인데 `limit_note` 채움 / `UNVERIFIED`인데
`evidence_ref` 채움)에 대해 **실제 INSERT 를 시도해** 거부되는지 확인한다(음성 검사).

## 23. risk_profile — 건물 단위 위험 프로파일

> `SAFETY-INSPECTION`(`11 §3`) 대상 판정과 `verify_ownership` '법정 요건' 카테고리(안전검사·
> 안전인증·환경 규제)는 **건물 조건**에 걸리는데, `equipment.location` 은
> `"3번 조립라인 반송 컨베이어"` 같은 **문자열**이라 담을 자리가 없었다.

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

**시드 4행 — `BLD-C` 가 의도적 데모 케이스다**:

| building_id | fire_handling | hazmat_volume | power_capacity | 점수 | 산출 등급 | 저장 `risk_grade` |
|---|---|---|---|---|---|---|
| `BLD-A` | LOW | LOW | MEDIUM | 4 | LOW | LOW |
| `BLD-B` | MEDIUM | LOW | HIGH | 6 | MEDIUM | MEDIUM |
| `BLD-C` | HIGH | MEDIUM | MEDIUM | 7 | **HIGH** | **LOW**(의도적 불일치) |
| `BLD-D` | LOW | HIGH | LOW | 5 | MEDIUM | MEDIUM |

`BLD-C` 는 "저장된 등급이 최신 산출과 어긋날 수 있다"(재실사·재산정 지연)를 보여주는 자리다 —
실 산정 로직(`assess_risk_grade`, F6, MQ-1103)이 아직 없으므로 `data/seed.py` 의 점수식은
**self-check 전용**(`_RISK_LEVEL_SCORE`)이며 정본이 아니다. `risk_grade_updated_at` 은 `BLD-C`
만 오래된 값(≈14개월 전), 나머지는 최근(≈3개월 전)이다. 시드 검사 ㉟ 가 4행·`building_id`
집합이 `SELECT DISTINCT building_id FROM assets` 와 **동적으로 일치**하는지(하드코딩 4종 대조가
아니라 건물이 늘 때 대장 누락을 즉시 잡는 방식, `partner_links` ㉒-ⓒ 선례와 동형), 그리고
점수식 재계산이 위 표(BLD-C 는 의도된 불일치 그대로)와 일치하는지 확인한다.

---

## 24. manual_chunks — 매뉴얼 청크 dense 임베딩 (D117)

> **이 절은 오래 비어 있었다.** 테이블은 `scripts/postgres_schema.sql` 에 `§24` 로 정식
> 정의돼 있고 `mcp_server/dense_scorer.py` 가 실제로 읽는데, 이 문서에는 한 줄도 없었다
> (2026-09-04 실측으로 발견 — D130 작업 중 "문서 24개 vs 실제 DB 25개" 차이의 정체).

```sql
CREATE EXTENSION IF NOT EXISTS vector;        -- pgvector (D117)

CREATE TABLE manual_chunks (
  chunk_id    TEXT PRIMARY KEY,               -- jsonl 의 chunk_id 를 그대로 쓴다
  manual_id   TEXT NOT NULL,
  model       TEXT NOT NULL,                  -- iG5A | S100 | IE5 (D109)
  page        INTEGER NOT NULL,               -- 물리 페이지 (D26 — 인쇄 페이지 변환은 manifest 소관)
  section     TEXT NOT NULL,
  text        TEXT NOT NULL,                  -- ⚠ 정본이 아니다 (아래 참고)
  char_len    INTEGER NOT NULL,
  embedding   vector(2048),                   -- NULL = 아직 임베딩 안 됨
  embedded_at TIMESTAMP,
  CHECK (model IN ('iG5A','S100','IE5'))
);

CREATE INDEX idx_manual_chunks_model ON manual_chunks(model);
```

### 정본은 이 테이블이 아니라 파일이다 (D48)

| | 정본 | 크기 |
|---|---|---|
| 청크 원문·페이지·절 | **`data/extracted/manual_chunks.jsonl`** | 1,229행 / 1.4MB |
| 임베딩 벡터 | `manual_chunks.embedding` | — |

`mcp_server/rag.py` 의 **키워드 검색은 jsonl 파일만 읽는다** — 이 테이블에 의존하지 않는다.
그래서 테이블이 비어 있어도 RAG 는 정상 동작한다(dense 가꺼질 뿐). `text`·`page`·`section`
컬럼을 같이 둔 것은 디버깅 편의이지 두 번째 정본을 만들려는 게 아니다 — **둘이 어긋나면
jsonl 이 맞다.**

### 채우는 주체는 하나뿐 · 사람이 명시 실행한다

`scripts/migrate_vectors.py` 만 이 테이블에 INSERT 한다. 자동 실행되지 않는다 —
임베딩은 외부 API 과금이라 `D105`(Elice 지출 가드)와 같은 태도로 **사람이 의도를 밝혀야**
돈다. 배포 절차의 4단계다(`13_DEPLOYMENT §5-2`).

MCP 쓰기 도구 3종은 이 테이블에 관여하지 않는다 — **D10 대상 밖**이다(판정·발주 흐름이
아니라 검색 인덱스다).

### 차원 2048 은 모델 고정값이다

`nvidia/nemotron-3-embed-1b` 의 출력 차원이다(D117). **모델을 바꾸면 이 컬럼을 다시
만들어야 한다** — 벡터공간이 달라 기존 값을 재사용할 수 없다. `embedding` 이 NULL 이면
그 청크는 dense 후보에서 빠지고 키워드 점수만으로 순위가 정해진다(조용히 틀린 결과가
아니라 **기능 축소**로 떨어지는 설계).

### 현재 상태 — 0행

`error_codes` 처럼 "사람 승인 전 미적재"가 아니라 **비용 게이트** 때문이다(위 참고).
`mcp_server/dense_scorer.py` 는 이 상태에서 *"dense 스코어러 비활성"* 을 로그로 남기고
키워드 검색만으로 동작한다.

✅ **격리 스키마에도 복제된다** — `data/pg_isolation.py` 의 `_CLONE_TABLES` 에 오래
빠져 있었다(24개). 테이블 자체는 `_SCHEMA_SQL` 로 만들어지므로 **에러 없이 조용히 0행**이
됐고, `public` 도 0행이던 동안은 차이가 드러나지 않았다. 코퍼스를 임베딩한 뒤에는
**격리 스파이크만 dense 결과가 비는** 상태가 됐을 것이다 — 실패가 아니라 "검색 결과 없음"
으로 보여 알아채기 어려운 종류라, 그렇게 되기 전에 목록에 넣었다(2026-09-04, 25개).

---

## 시드 데이터 전략 — "일부러 꼬아놓은" 케이스 맵

| 케이스 | 시드 | 검증 시나리오 |
|---|---|---|
| 정상 발주 | FAN-IG5-01: qty 1, safety_stock 3 (미달) | S1 |
| 재고 0 + 대체품 有 | PCB-S100-CTRL: qty 0, 단종, 대체품 R2 (confirmed) | S2 |
| 대체품도 없음 | 특정 전원모듈: qty 0, 대체품 無 | S2 서브 (에스컬레이션) |
| 리드타임 트레이드오프 | 냉각팬: A사 3일/₩38,000 vs B사 14일/₩29,000/MOQ 10 | S1·화면 B 비교 |
| 반복 고장 | INV-L3-01 OCt 30일 내 3건 (매번 '리셋'만) | S3 |
| 미확인 호환 | 대체품 1건 compat_confirmed=false | 제안 금지 검증 |
| 규모감 | 부품 ~40종, 설비 ~10대, 공급사 4곳, 이력 ~200건 | 데모 현실감 |

### Sprint 6 확장 케이스 맵 (assets 9건)

`age` 는 **실행 연도 기준 상대 연차**다. `disposal_date` 는 시드 컬럼이 아니라 **도구
파라미터**이며, 잔가 버킷 요구(연 단위)와 처분 룰 요구(취득 후 개월)가 같은 자산에 동시에
걸리므로 `acquired_at` 은 잔가 기준으로 고정하고 `months_since_acquisition` 은 이 값으로 만든다.
`seed.py` 실행 시 자산별 프로브 날짜를 출력한다.

| asset_id | category | age→bucket | 처분 사실 | 기대 (처분) | 기대 (assess_repair_value) |
|---|---|---|---|---|---|
| `AST-L1-CONV` | `일반산업` | 5 → `3-5` | 무해당 | — | — |
| `AST-L2-SPDL` | `공작 기계` | 16 → `16-20` | `has_lien=0`, `safety_inspection_target=1` | CONDITIONAL | REPAIR_RECOMMENDED |
| `AST-L2-CLNT` | `공조냉각유공압` | 9 → `6-10` | 무해당 | — | — |
| `AST-L3-CONV` | `일반산업` | 6 → `6-10` | `tax_credit_applied=1`, `has_lien=1`, `lien_consent_ref=NULL`, 취득 후 17개월 | BLOCKED | ROOT_CAUSE_FIRST |
| `AST-L3-EXFAN` | `공조냉각유공압` | 8 → `6-10` | 무해당 | — | — |
| `AST-L3-LIFT` | `일반산업` | 3 → `3-5` | 전 사실 채움·무해당 | CLEAR | HOLD (`acquisition_cost` NULL) |
| `AST-L4-CONV` | `일반산업` | 4 → `3-5` | 무해당 | — | — |
| `AST-L4-WRAP` | `기타` | 20 → `16-20` | 취득 후 **23개월**(경계 22~26) | HOLD | SELL_AS_IS |
| `AST-L4-DUST` | `환경  설비` | 12 → `11-15` | `tax_credit_applied=NULL` | INSUFFICIENT_FACTS | REPLACE_RECOMMENDED (`parts_eol_flag=1`) |

`error_history` 는 두 대를 손으로 형상화해 MTBF 추세를 결정론적으로 만든다 —
`INV-L2-01`(90일 등간격 → `stable`) · `INV-L4-02`(직전 12M 140일 → 최근 12M 46일 → `declining`).
잡음 생성에서 이 둘을 제외하고, **다른 설비가 우연히 30일 3회를 채우지 못하게 막는다** —
`repeat_failure` 가 켜지면 `assess_repair_value` 가 전부 `ROOT_CAUSE_FIRST` 로 수렴해
3지 판단 데모가 사라진다. 반복 고장은 `INV-L3-01` 전용이다.

> ✅ **위 5종은 Stage 3(MQ-601b)에서 전부 재현됐다** — D77(룰 `required_facts` 정합) ·
> D78(`assets.insured` 분리) · D79(`verdict` 5종) 을 거친 결과다. 그전에는
> `CONDITIONAL`·`CLEAR` 가 **어떤 시드로도 도달 불가**였다: 룰 4종이 원천 없는 사실을
> 요구하거나(`sale_amount`·`risk_grade_*`) 부재가 곧 트리거인 필드를 선언해
> (`lien_consent_ref`) 전 자산이 `INSUFFICIENT_FACTS` 로 수렴했다.
>
> ⚠ **`AST-L3-LIFT` 의 `CLEAR` 는 `disposal_mode='SCRAP'` 에서만 나온다.** `VAT-INVOICE` 가
> `disposal_mode='SALE' ∧ vat_invoice_issued=false` 로 발화하는데 precheck 은 거래 성립 전이라
> `vat_invoice_issued` 는 **항상 false** 이므로, **매각 판정은 정의상 최소 `CONDITIONAL`** 이다
> (세금계산서 발급이 언제나 남아 있다). 결함이 아니라 도메인 사실이며 D78 이 명시했다.
> 같은 자산을 `SALE` 로 부르면 `CONDITIONAL` 이 정답이고, 검증 ⑮ 가 두 경우를 함께 잠근다.

## 다음 단계 (M1 착수 순서)
1. LS 매뉴얼 2종(iG5A, S100) 다운로드 → 에러코드 표 추출 → `error_codes` 적재 (최대 리스크 구간)
2. 시드 생성 스크립트 (`seed.py`) — 위 케이스 맵 그대로
3. MCP 서버 골격 + 도구 7종(읽기 6+쓰기 1) 연결

## 자가 검증 목록 (`uv run python data/seed.py`)

| # | 검사 | 근거 |
|---|---|---|
| ①~⑦ | 시드 케이스 맵 7종 | 위 표 |
| ⑧ | `error_codes` 적재 (`--with-error-codes` 시 70건 — iG5A/S100 65건 + Sprint 15 IE5 5건 병합, 기본 0건) | 사람 승인 게이트 |
| ⑨~⑪ | `users` 3행 · 미등록 user_id FK 거부 · `display_name` DB 조회 | D41 |
| ⑫ | `assets` 9행 · `equipment.asset_id` NULL 정확히 1건(`INV-L1-01`) | D68 |
| ⑬ | `law_refs` 사본 == `data/rules/laws/*.json` **파일 목록** (하드코딩 금지) | D60 |
| ⑭ | `rules` 5행 · 근거(`law_refs`+`contract_refs`) 없는 룰 0건 | D61 |
| ⑮ | 처분 5자산의 `check_disposal_blockers` verdict + 버킷 건수 일치 · `LIFT` 의 SALE/SCRAP 대조 | D77·D78·D79 |
| ⑯ | `parts.part_class` NULL 0건 · 잔가 격자 공백 0 · 단조 감소 · 목업 표기 | D12·D74 |
| ⑰ | 사유 없는 `override` INSERT → CHECK 거부 | D63 |
| ⑱ | `has_lien=1` 인데 `lien_consent_ref=''` 인 자산 0건 | D62·D77 |
| ⑲ | `decisions` 신규 컬럼 3종 + `requested_by` FK + 부가 컬럼(`decision_note`·`created_at`) | MQ-706 draft 계약 |
| ⑳ | 서명 없는 확정 / BLOCKING 우회 INSERT → CHECK 거부 (**양성 대조 포함** — 정상 서명은 통과해야 한다) | 완료 기준 ②③ |
| ㉑ | DDL 의 비차단 verdict 목록 == `engine.VERDICTS` 파생 (하드코딩 대조가 아니라 **파싱 대조**) | D79 |
| ㉒ | `partner_links` 시드 정합 · **`NOT_LINKED` 대조군 존재** · `subject_ref` 집합 == `assets.building_id` **동적 대조** · 회사 결 `''` · `linked_at` UTC·과거 · **목업 고지(문구+접두 기호 두 축)** | D92·D95·D96·D90 |
| ㉓ | `partner_links` CHECK **음성 3 + 양성 2** (`NULL`+식별자 거부 ← `IS` 가 아니면 통과한다 / `NULL`+`NULL` 은 통과) | D91·D96·D62 |
| ㉔ | **`partner_links` 가 증권 식별자를 복제하지 않는다 — 음성 검사** (insuq `external_ref` 전부 NULL · 값 복제 0건 · 정본 존재 확인). ⛔ `link_state` 와 `insured` 를 엮지 않는다 | D95·D78 |
| ㉕ | `traces.request_chain_id` 컬럼 존재 · nullable — detail 에 **"쓰는 쪽 없음(A2A 호출부 미착수)"** 을 명시 | D94-ⓐ |
| ㉖ | `parts.mfr_part_no` 컬럼 존재·nullable · **정본(`MFR_PART_NO`) 과 DB 완전 일치**(양성) · 판매점 주문번호·완제품 형명 등 금지값 **0건**(음성) — NULL 39종은 "미조사"가 아니라 "미공개" | D97 |
| ㉗ | `repair_records` **상태 불변식**(D98) — `state='signed' ⇔ signed_at·record_hash·verified_by 전부 non-null` 을 **양방향**(iff)으로 검사, 어휘 밖 상태 0건 + 미서명 정확히 1건(`RPR-2403`) | D98 |
| ㉘ | `error_codes` **출처 컬럼 짝 불변식**(D100) — `actions_manual_id`·`actions_page` 짝 불일치 0건(음성). `--with-error-codes` 없이 실행하면 0행이 정상(FAIL 아님) | D100 |
| ㉙ | `repair_records.record_hash` **재계산 대조**(D84 태도) — `data/repair_hash.compute_record_hash()` 로 서명 11행을 다시 계산해 저장 해시와 전건 일치하는지 확인 | D84·D98 |
| ㉚ | `error_codes.actions` **병합 검증**(MQ-919) — 채워진 3건이 후보값과 내용 대조로 일치, NULL **67건**(Sprint 15 IE5 5건 병합으로 62→67)은 기대치 | MQ-919 |
| ㉛ | `part_lifecycle_mock` **27행**(9자산 × 부품 3종) · **모델-부품 정합**(`equipment.model` 이 `iG5A` 면 `part_no` 에 `IG5`, `S100` 이면 `S100` 포함, 불일치 0건) | Sprint 10 브레인스토밍 D |
| ㉜ | `deadlines` **CHECK 프로브**(음성) — 잘못된 `type` 값 INSERT 를 **실제로 시도**해 `IntegrityError` 로 거부되는지 확인, 정상 상태는 0행 유지(양성) | D10·`11 §10-2` |
| ㉝ | `incidents` **2행** · FK 정합(자산 고아 0건) · `type` enum 밖 0건 | D68·`11 §10-2` |
| ㉞ | `ownership_checks` 행수 == `verify_ownership(AST-L3-LIFT)` **실측 항목 수**(하드코딩 아닌 그 자리에서 재호출한 값과 대조) · either-or CHECK 2종 음성 검사(`VERIFIED`+`limit_note`, `UNVERIFIED`+`evidence_ref` 각각 INSERT 시도 → 거부 확인) | S18·D68 |
| ㉟ | `risk_profile` **4행** · `building_id` 집합이 `SELECT DISTINCT building_id FROM assets` 와 **동적으로 일치** · 점수식 재계산이 시드 표와 일치(`BLD-C` 의 의도적 불일치 포함) | D102·`11 §10-2` |
| ㊱ | `error_codes` **IE5 5건 병합 검증**(Sprint 15 MQ-1507) — `model='IE5'` 행 정확히 5건(양성) · `causes`/`actions` 가 빈 배열인 행 0건(음성). `--with-error-codes` 없이 실행하면 0행이 정상(FAIL 아님) | D109 |

> **실측 (2026-08-18)** — `uv run python data/seed.py --with-error-codes` → **전부 통과 (35건)**.
> 건수는 러너 출력이 기준이다. 직전 실행보다 줄었다면 검사가 사라진 것이다.
