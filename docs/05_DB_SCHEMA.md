# 목업 DB 스키마 v0.3
SQLite 기준 (목업이므로 파일 DB로 충분, 실서비스 가정 시 PostgreSQL 치환 가능)

도구가 읽는 테이블 — 설계하며 6개 → 8개(`error_codes`·`equipment` 추가, D11)
→ 구현 정합화에서 **9개**로 확정: `traces`(실행 로그 영속화, D21) 추가.
→ **Sprint 6 (F1·F2·F4)에서 7개 추가** — `assets`·`law_refs`·`rules`·`decisions`·`flags`·
`repair_records`·`residual_curve` (§11~§17).

> **세는 단위 주의:** 위 숫자는 아래 **절(§) 개수**다. §7이 `suppliers`와 `supplier_parts`
> 두 테이블을 함께 다루므로 실제 `CREATE TABLE` 은 코어 **11개** + Sprint 6 **7개 = 18개**다
> (`data/seed.py` 기준). 절 번호는 `§1`~`§9`(+`§1-B`)로 10절, Sprint 6 이 `§11`부터 이어받는다
> — **`§10`은 존재하지 않는다**(`§1-B`가 10번째 절이라 번호가 어긋난 것을 그대로 둔 것이며,
> `sprint-6.md`·확장 도구 명세가 이미 `§11`~`§17`로 참조하고 있다).

---

## ERD 개요

```
assets ──< equipment ──< error_history >── error_codes        ← assets 는 D68 의 호스트 설비
  │           │                                 │ (model+code 복합키)
  │           └──< repair_records >─────────────┘             ← 수리는 인버터 단위 (D68 ⓑ)
  ├──< decisions            ← 계층 3 서명 (쓰기는 Sprint 7)
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
```

---

## 1. error_codes — 에러코드 마스터 ★매뉴얼에서 구조화 추출

> `lookup_error_code`의 원천. M1에서 매뉴얼 PDF 표 → 이 테이블로 추출하는 게 최대 작업.

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
  PRIMARY KEY (model, code),           -- ★ 복합키 = "같은 코드, 다른 의미" 구현
  -- code 형식 제약 (D33): 대문자·숫자·언더스코어 2~4자.
  -- 실측 64건 전부 이 범위 (3자 51 / 4자 12 / 2자 1, 최장 'FLTL'·'RERR' 등 4자)
  CHECK (length(code) BETWEEN 2 AND 4
         AND code = upper(code)
         AND code NOT GLOB '*[^A-Z0-9_]*')
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
  role          TEXT NOT NULL,         -- 'technician' | 'manager'
  auth_provider TEXT NOT NULL DEFAULT 'local',  -- 'local' | 'google'
  external_id   TEXT,                  -- IdP의 sub/oid. 연동 전 NULL
  active        BOOLEAN NOT NULL DEFAULT 1,     -- 퇴사·휴직 시 0
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  CHECK (role IN ('technician','manager')),
  CHECK (auth_provider IN ('local','google')),
  CHECK (user_id = lower(user_id) AND user_id NOT GLOB '*[^a-z0-9-]*')
);
```

**행을 지우지 않는다.** 퇴사자는 `active=0`으로 둔다 — 과거 발주의 `decided_by`가 끊기면 감사 추적(P5)이 무너진다.

**`role`은 회사가 사전 부여한다 (D52).** Google 로그인은 "누구인지"만 확인하고 권한을 정하지 않는다. OAuth가 권한을 결정하면 D4(진단자/승인자 분리)가 무의미해진다.

**개인 소셜 로그인은 넣지 않는다 (D52).** `auth_provider`가 `local`·`google` 2종뿐인 이유다. `google`은 **회사 Google Workspace**이며, `hd`(hosted domain) 클레임 + 이 테이블의 사전 등록 두 겹으로 개인 Gmail을 막는다. 실제 인증 플로우 구현은 백로그 **P21**.

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
  part_class   TEXT                    -- 'CONSUMABLE' | 'CRITICAL' (Sprint 6)
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
  state        TEXT DEFAULT 'draft',   -- 'draft'|'pending'|'approved'|'rejected'
  requested_by TEXT REFERENCES users,  -- 정비사 사용자 ID('tech-01') — X-User 헤더에서 백엔드가 주입
                                       --   (D23 도구 파라미터 아님 / D36 ASCII ID / D41 users FK)
  decided_by   TEXT REFERENCES users,  -- 팀장 사용자 ID('mgr-01') — 승인/반려 시 X-User에서 주입
  decision_note TEXT,                  -- 반려 사유 / 승인 코멘트 (D38). 반려는 필수 —
                                       --   사유 없는 반려는 요청자가 뭘 고쳐야 할지 알 수 없음
  session_id   TEXT,                   -- 이 발주를 만든 대화 세션 (D21) — 화면 B "실행 로그 보기" 링크의 키
  created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,

  -- (model, error_code)는 error_codes 복합키를 참조 — code 단독으로는 "같은 코드, 다른 의미"가
  -- 발주 이력에서 무너짐 (D13). 존재하지 않는 코드는 FK가 튕겨내므로 LLM이 지어낸 코드로
  -- 발주서를 만들 수 없다 (D23·D31과 같은 논리)
  FOREIGN KEY (model, error_code) REFERENCES error_codes(model, code),

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
  ts           DATETIME DEFAULT CURRENT_TIMESTAMP,
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

현재 7건 전부 `fetch_status='PENDING'` 이다(`LAW_API_OC` 미발급). **판정과 조문 인용은 정상
동작**하며, 도구는 `evidence_completeness:"LAW_TEXT_PENDING"` 으로 그 사실을 표시한다.
`build_evidence_bundle` 만 의도적으로 거부한다 — `text_hash` 가 null 이면 해시할 사실이 없다.

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

> **쓰기 경로는 Sprint 7의 사람 전용 API.** MCP 도구는 이 테이블에 손대지 않는다 (D10 태도).

```sql
CREATE TABLE decisions (
  decision_id TEXT PRIMARY KEY,
  asset_id  TEXT NOT NULL REFERENCES assets,
  decision_type TEXT NOT NULL,           -- 'DISPOSAL' | 'REPAIR'
  evidence_bundle TEXT NOT NULL,         -- JSON: {laws[], rules[], facts{}}
  bundle_hash TEXT NOT NULL,
  verdict_at_signing TEXT NOT NULL,
  override BOOLEAN NOT NULL DEFAULT 0,
  override_reason TEXT,
  reviewed_by TEXT REFERENCES users,
  signed_at DATETIME,
  state TEXT NOT NULL DEFAULT 'draft',
  -- D63 을 스키마로 잠근다 — 사유 없는 override 는 저장 자체가 불가
  CHECK (override = 0 OR (override_reason IS NOT NULL AND length(trim(override_reason)) > 0)),
  CHECK (json_valid(evidence_bundle)),
  CHECK (state IN ('draft','pending','signed','rejected'))
);
```

**D63을 문서가 아니라 스키마로 잠갔다.** "override 하려면 사유를 쓰라"를 애플리케이션 검증에만
두면 경로 하나만 빠뜨려도 사유 없는 무시가 저장된다. 시드 검증 **⑰** 이 실제로 INSERT 를
시도해 CHECK 가 거부하는지 확인한다(⑩ FK 프로브와 같은 이유 — 한 번도 실행되지 않는 제약은
있는 셈 치기 쉽다).

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
  FOREIGN KEY (model, error_code) REFERENCES error_codes(model, code),  -- D13·D33
  CHECK (work_type IN ('PLANNED','UNPLANNED')),
  CHECK ((model IS NULL) = (error_code IS NULL)),
  CHECK (parts IS NULL OR json_valid(parts)),
  CHECK (expenditure_class IS NULL OR expenditure_class IN ('CAPITAL','REVENUE','HOLD'))
);
```

**`downtime_hours` 는 `12 §9` 에 없는 컬럼이다.** `12 §2` 가 MTTR 을 요구하는데 저장소에
수리 시간 원천이 전혀 없어 추가했다. (`12 §9` 본문 반영은 MQ-613.)

**`signed_at IS NULL` 인 레코드는 지표에서 제외된다 (`12 §11`).** 시드 12건 중
**`RPR-2403`(INV-L3-01) 1건이 미서명**이며, `get_maintenance_metrics` 의 `excluded[]` 문장과
`planned_ratio` 분모 제외가 이 한 행으로 검증된다. `assets.cumulative_repair_cost` 도
**서명분만** 합산한다.

**`(model, error_code)` 는 짝이거나 둘 다 NULL 이다 (D13·D33).** `--with-error-codes` 없이
시드하면 `error_codes` 가 0행이라 복합 FK 를 만족시킬 수 없어 둘 다 NULL 로 넣는다
(`po_drafts` 와 같은 처리). 계획 정비(`PLANNED`)는 애초에 에러코드가 없어 항상 NULL 이다.

**`record_hash` 는 시드 전량 NULL 이다.** 서명 해시 규약(키 정렬·구분자 고정)은 Sprint 7의
서명 API 와 `build_evidence_bundle` 의 `bundle_hash` 가 함께 정한다 — 지금 임의 규약을 심으면
나중 검증이 조용히 어긋난다.

## 17. residual_curve — 잔가율 격자 (D65·D74)

> 정본은 `data/extracted/residual_curve.json`(`data/build_residual_curve.py` 산출).

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
| ⑧ | `error_codes` 적재 (`--with-error-codes` 시 65건, 기본 0건) | 사람 승인 게이트 |
| ⑨~⑪ | `users` 3행 · 미등록 user_id FK 거부 · `display_name` DB 조회 | D41 |
| ⑫ | `assets` 9행 · `equipment.asset_id` NULL 정확히 1건(`INV-L1-01`) | D68 |
| ⑬ | `law_refs` 사본 == `data/rules/laws/*.json` **파일 목록** (하드코딩 금지) | D60 |
| ⑭ | `rules` 5행 · 근거(`law_refs`+`contract_refs`) 없는 룰 0건 | D61 |
| ⑮ | 처분 5자산의 `check_disposal_blockers` verdict + 버킷 건수 일치 · `LIFT` 의 SALE/SCRAP 대조 | D77·D78·D79 |
| ⑯ | `parts.part_class` NULL 0건 · 잔가 격자 공백 0 · 단조 감소 · 목업 표기 | D12·D74 |
| ⑰ | 사유 없는 `override` INSERT → CHECK 거부 | D63 |
| ⑱ | `has_lien=1` 인데 `lien_consent_ref=''` 인 자산 0건 | D62·D77 |
