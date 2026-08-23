
CREATE TABLE error_codes (
  model        TEXT NOT NULL,
  code         TEXT NOT NULL,
  display_code TEXT,
  error_name   TEXT NOT NULL,
  severity     TEXT NOT NULL,
  causes       TEXT NOT NULL,
  actions      TEXT NOT NULL,
  related_parts TEXT,
  manual_page  INTEGER NOT NULL,
  -- ★ Sprint 9 신설 (D100) — 조치문 출처. 'ig5a-troubleshooting' 등 manifest 의 id.
  --   NULL = 출처 미기록. MQ-919 가 승인 3건(iG5A RERR·ETB, S100 FANW)만 채웠고
  --   나머지 62건은 여전히 NULL 이 정상이다(검사 ㉚). actions_page 는 PDF 물리 페이지(D26)
  --   이고 actions_manual_id 와 짝이어야 한다.
  actions_manual_id TEXT,
  actions_page      INTEGER,
  PRIMARY KEY (model, code),
  CHECK (severity IN ('warning','fault','critical')),
  -- code 형식 (D33): 대문자·숫자·언더스코어 2~4자
  CHECK (length(code) BETWEEN 2 AND 4
         AND code = upper(code)
         AND code ~ '^[A-Z0-9_]+$'),
  CHECK ((actions_manual_id IS NULL) = (actions_page IS NULL))
);

-- 사용자 (D41·D52) — X-User 헤더 값의 원천이자 표시명 매핑 소스.
-- 표시명이 backend/services/po.py 에 하드코딩돼 있던 것을 여기로 옮겼다 (D36→D41).
-- 행을 지우지 않는다: 퇴사자는 active = FALSE. decided_by 가 끊기면 감사 추적(P5)이 무너진다.
CREATE TABLE users (
  user_id       TEXT PRIMARY KEY,         -- 'tech-01' — 헤더로 오가는 ASCII ID (D36)
  email         TEXT UNIQUE,              -- 회사 이메일. 향후 IdP 매칭 키 (D52)
  display_name  TEXT NOT NULL,            -- '김OO' — 화면 표시용
  role          TEXT NOT NULL,            -- 권한. 회사가 사전 부여. OAuth 가 정하지 않는다 (D52)
  department    TEXT,                     -- 소속. **권한이 아니다** — require() 는 안 본다 (D108)
                                           -- NULL 허용 = 미배정. 헤더로 받지 않고 이 컬럼에서만 주입
  auth_provider TEXT NOT NULL DEFAULT 'local',
  external_id   TEXT,                     -- IdP 의 sub/oid. 연동 전 NULL
  active        BOOLEAN NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CHECK (role IN ('technician','manager')),
  CHECK (department IS NULL OR department IN ('maintenance','finance')),
  CHECK (auth_provider IN ('local','google')),
  CHECK (user_id = lower(user_id) AND user_id ~ '^[a-z0-9-]+$')
);

-- §11 assets — 호스트 설비 (D68). 확장 기능 6종의 판정 대상.
-- equipment(인버터)는 자산의 부품이다 — 거래·처분·감가의 단위는 이쪽이다.
CREATE TABLE assets (
  asset_id      TEXT PRIMARY KEY,          -- 'AST-L3-CONV'
  name          TEXT NOT NULL,
  category      TEXT NOT NULL,             -- residual_curve 조인 키 (MQ-603 출력 바이트 그대로)
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
  -- ★ 부보 여부와 증권 식별자를 **분리**한다 (D78). policy_id 한 컬럼이 "부보돼 있는가"와
  --   "증권 번호가 무엇인가" 두 질문을 겸하면 **"확인된 미부보"를 적을 자리가 없다** —
  --   값이 있으면 항상 TRIGGERED, 없으면 required_facts 누락으로 INSUFFICIENT_FACTS 라
  --   INSURANCE-NOTIFY 가 어떤 사실 조합으로도 해제되지 않았다. has_lien/lien_creditor 와 같은 꼴.
  --   NULL = 모름 / 0 = 확인된 미부보 / 1 = 부보
  insured                  BOOLEAN,
  policy_id                TEXT,   -- 증권 식별자 전용. 판정은 insured 가 한다 (D78)
  safety_inspection_target BOOLEAN,
  last_inspection_date     DATE,
  inspection_valid_until   DATE,
  -- 자산가치 (12 §9)
  cumulative_repair_cost INTEGER NOT NULL DEFAULT 0,
  last_overhaul_at       DATE,
  controller_generation  TEXT,
  parts_eol_flag         BOOLEAN NOT NULL DEFAULT FALSE,
  CHECK (status IN ('IN_USE','IDLE','DISPOSAL_PENDING','DISPOSED'))
);

CREATE TABLE equipment (
  equipment_id TEXT PRIMARY KEY,
  line_id      INTEGER NOT NULL,
  model        TEXT NOT NULL,
  installed_at DATE,
  location     TEXT,
  asset_id     TEXT REFERENCES assets,     -- D68. NULL 허용 = 호스트 자산 없음(분전반 등)
  CHECK (model IN ('iG5A','S100'))
);

CREATE TABLE error_history (
  id BIGSERIAL PRIMARY KEY,
  equipment_id TEXT NOT NULL REFERENCES equipment,
  code         TEXT NOT NULL,             -- 대문자 canonical (D25)
  occurred_at  TIMESTAMP NOT NULL,
  action_taken TEXT,
  part_replaced TEXT,
  resolved     BOOLEAN DEFAULT TRUE,
  recorded_by  TEXT REFERENCES users      -- 기록한 정비사 (D41). 시드분은 NULL
);
CREATE INDEX idx_history_eq_code ON error_history(equipment_id, code, occurred_at);

CREATE TABLE parts (
  part_no      TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  category     TEXT,
  compatible_models TEXT NOT NULL,        -- JSON array
  discontinued BOOLEAN DEFAULT FALSE,
  part_class   TEXT,                      -- 'CONSUMABLE' | 'CRITICAL' (12 §9). ⚠ 미검수 초안 (D12)
  mfr_part_no  TEXT                       -- 제조사 실품번. NULL = **공개돼 있지 않음** (D97)
);

CREATE TABLE part_alternatives (
  part_no      TEXT REFERENCES parts,
  alt_part_no  TEXT REFERENCES parts,
  compat_confirmed BOOLEAN NOT NULL,      -- false면 도구가 제안 금지
  note         TEXT,
  PRIMARY KEY (part_no, alt_part_no)
);

CREATE TABLE inventory (
  part_no      TEXT PRIMARY KEY REFERENCES parts,
  qty          INTEGER NOT NULL,
  safety_stock INTEGER NOT NULL DEFAULT 0,
  location     TEXT
);

CREATE TABLE suppliers (
  supplier_id    TEXT PRIMARY KEY,
  name           TEXT NOT NULL,
  contact        TEXT,
  account_number TEXT,
  bank_code      TEXT
);

CREATE TABLE supplier_parts (
  supplier_id  TEXT REFERENCES suppliers,
  part_no      TEXT REFERENCES parts,
  lead_days    INTEGER NOT NULL,
  unit_price   INTEGER NOT NULL,
  moq          INTEGER DEFAULT 1,
  PRIMARY KEY (supplier_id, part_no)
);

CREATE TABLE po_drafts (
  po_id        TEXT PRIMARY KEY,
  part_no      TEXT NOT NULL REFERENCES parts,
  qty          INTEGER NOT NULL,
  supplier_id  TEXT NOT NULL REFERENCES suppliers,
  model        TEXT,                      -- error_code 와 항상 짝 (D33)
  error_code   TEXT,
  evidence     TEXT,                      -- JSON (D34)
  unit_price   INTEGER NOT NULL,          -- supplier_parts 스냅샷 (D31)
  reason       TEXT NOT NULL,
  urgency      TEXT DEFAULT 'normal',
  state        TEXT DEFAULT 'draft',
  requested_by TEXT REFERENCES users,     -- ASCII 사용자 ID (D36) + users FK (D41)
  decided_by   TEXT REFERENCES users,
  decision_note TEXT,                   -- 반려 사유 / 승인 코멘트 (D38)
  session_id   TEXT,
  created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (model, error_code) REFERENCES error_codes(model, code),
  CHECK (state IN ('draft','pending','approved','rejected')),
  CHECK (urgency IN ('urgent','normal')),
  CHECK (error_code IS NULL OR (
           length(error_code) BETWEEN 2 AND 4
           AND error_code = upper(error_code)
           AND error_code ~ '^[A-Z0-9_]+$')),
  CHECK ((model IS NULL) = (error_code IS NULL)),
  CHECK (evidence IS NULL OR (evidence::jsonb IS NOT NULL))
);

CREATE TABLE traces (
  id BIGSERIAL PRIMARY KEY,
  session_id   TEXT NOT NULL,
  seq          INTEGER NOT NULL,
  event_type   TEXT NOT NULL,
  tool         TEXT,
  payload      TEXT NOT NULL,
  -- 도구 결과 **원본** JSON (D76-2). `tool_result` 행에만 들어가므로 nullable.
  -- ⛔ payload 를 재사용하지 않는 이유: payload 는 **SSE data 와 바이트 동일**이 계약이고
  --    (D30) trace_persist ② · sp3_sse_events ⑬ 이 바이트 단위로 대조한다. 여기에 원본을
  --    섞으면 평가의 두 소스 대조가 조용히 깨진다.
  -- ⚠ 이 스프린트는 **컬럼만** 만든다. 값을 쓰는 쪽(backend/agent/trace.py)은 D76-2 담당.
  tool_payload TEXT,
  -- A2A 멀티홉 추적용 (D94-ⓐ). nullable — 기존 행·기존 INSERT 문에 영향이 없다.
  -- ✅ **쓰는 쪽이 생겼다** — backend/a2a/trace.py(record_a2a_trace)가 A2A 호출부(request-
  --     withdrawal·lookup-clause·assess-loan)에서 실제로 이 컬럼에 값을 채운다. A2A 와
  --     무관한 세션(정비 대화 등)의 행은 여전히 NULL 이 정상이며, 이 회귀도 그 경계를 본다.
  --     spikes/a2a_identity_contract.py ⑪-a/⑪-b 가 그 사실을 실측(스캐너)으로 확인한다.
  --     D76-2 가 컬럼만 만들고 쓰는 쪽이 없어 3차 평가까지 전부 NULL 이었던 전례를 반복하지 않기
  --     위해, ⑪-b 는 "값이 비었다"가 아니라 "누가 쓰는가"를 회귀가 말하게 한다.
  request_chain_id TEXT,
  ts           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  -- token 은 없다 (D41): 저장하지 않는 게 설계다. backend/agent/trace.py 참조
  CHECK (event_type IN ('tool_call','tool_result','block')),
  -- seq 중복이 조용히 통과하면 순서 판정(scenario-smoke)·타임라인·Last-Event-ID(P18)가
  -- 깨진 걸 아무도 모른다 (D41)
  UNIQUE (session_id, seq)
);
CREATE INDEX idx_traces_session ON traces(session_id, seq);

-- §12 law_refs — 계층 1 조회용 **사본**. 정본은 data/rules/laws/*.json 이다 (D60).
-- 적재는 반드시 engine.load_laws() 를 경유한다 — 파일을 직접 파싱해 넣으면 무결성 게이트가 뚫린다.
CREATE TABLE law_refs (
  law_ref_id TEXT PRIMARY KEY,
  law_name TEXT NOT NULL, article TEXT NOT NULL, clause TEXT,
  title TEXT NOT NULL, text TEXT,
  fetch_status TEXT NOT NULL,
  effective_from DATE, effective_to DATE,
  promulgation_no TEXT, source_url TEXT, retrieved_at TIMESTAMP,
  text_hash TEXT, supersedes TEXT, verification_note TEXT,
  CHECK (fetch_status IN ('PENDING','FETCHED','FAILED'))
);

-- §13 rules — 계층 2 조회용 사본. (rule_id, rule_version) 복합 PK = "해석은 개정된다"
CREATE TABLE rules (
  rule_id TEXT NOT NULL, rule_version INTEGER NOT NULL,
  label TEXT NOT NULL, category TEXT NOT NULL,
  disposal_type TEXT NOT NULL, source_type TEXT NOT NULL,
  law_refs TEXT NOT NULL, contract_refs TEXT NOT NULL,   -- JSON array
  interpretation TEXT NOT NULL, required_facts TEXT NOT NULL,
  "trigger" TEXT NOT NULL, boundary TEXT,
  message TEXT NOT NULL, resolve_options TEXT NOT NULL,
  confidence TEXT NOT NULL, requires_expert_review BOOLEAN NOT NULL,
  PRIMARY KEY (rule_id, rule_version),
  CHECK (disposal_type IN ('BLOCKING','PRECONDITION','AUTO_CLOSE')),
  CHECK (source_type IN ('LAW','CONTRACT')),
  CHECK ((law_refs::jsonb IS NOT NULL) AND (contract_refs::jsonb IS NOT NULL) AND ("trigger"::jsonb IS NOT NULL))
);

-- §14 decisions — 계층 3 서명. 쓰기 경로는 Sprint 7 (D10 태도 유지: 도구는 draft INSERT 만)
--
-- ★ 이 테이블의 CHECK 3종이 *"BLOCKING 우회 처분 0건 · 서명 없는 처분 확정 0건"* 의 **마지막 층**이다.
--   위쪽 층은 전부 코드다 — 도구는 UPDATE 권한이 없고(D10), 서명 API 는 순서를 강제한다(D84).
--   그러나 코드 층은 **버그로 뚫린다.** 미래의 잘못된 UPDATE 한 줄, 마이그레이션 스크립트,
--   콘솔에서 친 SQL — 어느 것이든 코드를 우회한다. 스키마는 우회할 수 없다.
--   D63 이 "사유 없는 override" 를 CHECK 로 막은 것과 같은 태도이며, 그 CHECK 가 이미
--   `seed.py ⑰` 로 검증돼 있다는 사실이 이 확장의 선례다.
CREATE TABLE decisions (
  decision_id TEXT PRIMARY KEY,
  asset_id  TEXT NOT NULL REFERENCES assets,
  decision_type TEXT NOT NULL,           -- 'DISPOSAL' | 'REPAIR'
  evidence_bundle TEXT NOT NULL,         -- JSON 5키: {laws[], rules[], evaluated[], contracts[], facts{}} (D83)
  bundle_hash TEXT NOT NULL,
  verdict_at_signing TEXT NOT NULL,
  override BOOLEAN NOT NULL DEFAULT FALSE,
  override_reason TEXT,
  reviewed_by TEXT REFERENCES users,
  signed_at TIMESTAMP,
  state TEXT NOT NULL DEFAULT 'draft',
  -- ── Sprint 7 (MQ-707) 보강 컬럼 ────────────────────────────────────────────
  -- 도구(generate_disposal_document)가 채우는 요청 사유. `po_drafts.reason` 과 같은 자리다.
  reason TEXT,
  -- 신원·세션은 **도구가 채우지 않는다** (D23·D37) — 백엔드가 같은 요청 안에서 stamp 한다.
  -- 도구 스키마에 requested_by 가 있으면 LLM 이 그 값을 채울 수 있다 = 위조 경로다.
  requested_by TEXT REFERENCES users,
  session_id TEXT,
  -- 반려 사유 / 서명 코멘트. `po_drafts.decision_note` 와 같은 역할이다 (D38).
  -- ⚠ 명세(MQ-707)에는 3컬럼만 적혀 있으나 `POST /sign{note}`·`/reject{reason}` 의 값을
  --   담을 자리가 없어 그대로면 **사유가 저장되지 않는다** — "사유 없는 반려는 요청자가 뭘
  --   고쳐야 할지 알 수 없다"(D38)는 반려 사유를 *받는 것*이 아니라 *남기는 것*이 목적이다.
  decision_note TEXT,
  -- 통합 승인 큐(D85)가 `created_at DESC` 로 정렬한다. DEFAULT 가 있으므로 MQ-706 의
  -- draft INSERT 계약(컬럼 목록)은 한 글자도 바뀌지 않는다 — `po_drafts` 와 같은 패턴.
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  -- D63 을 스키마로 잠근다 — 사유 없는 override 는 저장 자체가 불가
  CHECK (override = FALSE OR (override_reason IS NOT NULL AND length(trim(override_reason)) > 0)),
  CHECK ((evidence_bundle::jsonb IS NOT NULL)),
  CHECK (state IN ('draft','pending','signed','rejected')),
  -- ★ "서명 없는 처분 확정 0건" — state='signed' 인데 서명자·서명시각·번들해시가 비면 거부.
  --   `signed` 는 "누가 언제 무엇에 서명했는가"가 전부 있어야 성립하는 상태다.
  --   셋 중 하나라도 없는 행은 *서명처럼 보이는 행*이지 서명이 아니다.
  CHECK (state <> 'signed' OR (signed_at IS NOT NULL
                               AND reviewed_by IS NOT NULL
                               AND length(trim(bundle_hash)) > 0)),
  -- ★ "BLOCKING 우회 처분 0건" — 차단 판정(BLOCKED·HOLD·INSUFFICIENT_FACTS)에 서명하려면
  --   override = TRUE 이어야 하고, override = TRUE 이면 위 D63 CHECK 가 사유를 강제한다.
  --   두 CHECK 가 맞물려 **"사유 없는 우회 서명"이 스키마 수준에서 표현 불가능**해진다.
  --   ⚠ 여기 열거된 두 값은 `engine.VERDICTS` 의 **비차단** 어휘다. 엔진이 어휘를 늘리면
  --     이 목록이 조용히 낡으므로 `verify()` ㉑ 이 DDL 문자열을 파싱해 엔진과 대조한다.
  CHECK (state <> 'signed' OR override = TRUE
         OR verdict_at_signing IN ('CONDITIONAL','CLEAR'))
);

-- §15 flags — 법정 조건 상태 (발생 → 이행 → 해소). deadlines(F5)와 성격이 다름
CREATE TABLE flags (
  flag_id BIGSERIAL PRIMARY KEY,
  asset_id TEXT NOT NULL REFERENCES assets,
  rule_id TEXT NOT NULL, rule_version INTEGER NOT NULL,
  disposal_type TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'OPEN',
  raised_at TIMESTAMP NOT NULL, resolved_at TIMESTAMP,
  resolved_by TEXT REFERENCES users, evidence_ref TEXT,
  CHECK (state IN ('OPEN','IN_PROGRESS','RESOLVED','WAIVED'))
);

-- §16 repair_records — 수리 증빙 (12 §9). 쓰기 경로는 Sprint 7
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
  signed_at TIMESTAMP, record_hash TEXT,
  state TEXT NOT NULL DEFAULT 'draft',
  -- ★ Sprint 9 신설 (D98) — 도구는 이 셋을 채우지 않는다. 백엔드가 X-User·세션에서 stamp 한다
  --   (D23·D37). `data/repair_hash.py` 가 `record_hash` 규약의 단일 출처다.
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  requested_by TEXT REFERENCES users,
  session_id TEXT,
  note TEXT,                             -- 반려 사유·서명 메모 (D38 — 반려는 이유가 필수)
  FOREIGN KEY (model, error_code) REFERENCES error_codes(model, code),  -- D13·D33
  CHECK (work_type IN ('PLANNED','UNPLANNED')),
  CHECK ((model IS NULL) = (error_code IS NULL)),
  CHECK (parts IS NULL OR (parts::jsonb IS NOT NULL)),
  CHECK (expenditure_class IS NULL OR expenditure_class IN ('CAPITAL','REVENUE','HOLD')),
  -- ★ 신설 ① 상태 어휘 4종 (D98)
  CHECK (state IN ('draft','pending','signed','rejected')),
  -- ★ 신설 ② "서명 없는 확정 0건" 을 스키마로 잠근다 (decisions 의 DDL CHECK 2종과 같은 태도)
  CHECK (state <> 'signed' OR (signed_at IS NOT NULL AND record_hash IS NOT NULL
                               AND verified_by IS NOT NULL)),
  -- ★ 신설 ③ 미서명은 지표에 들어갈 수 없다 (12 §11) — signed_at 은 서명의 결과지 원인이 아니다
  CHECK (signed_at IS NULL OR state = 'signed')
);

-- §17 residual_curve — 잔가율 (D65·D74). 정본은 data/extracted/residual_curve.json
-- ⚠ D74 로 값 원천이 목업 공식이 되어 **표본 필드 4종은 전부 NULL 이 정상**이다.
--    NOT NULL 을 걸면 "표본이 없는데 표본 수를 채우는" 거짓말을 스키마가 강제하게 된다.
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
  -- ⚠ 날짜가 아니라 **시각**이다 (D96-ⓓ) — 자격증명 발급이 이 시점에 붙으므로 감사에는
  --    "며칠"이 아니라 "몇 시 몇 분"이 필요하다. **저장은 UTC** (D39, `traces.ts` 와 같은 규약).
  linked_at    TIMESTAMP,
  PRIMARY KEY (partner, subject_type, subject_ref),
  -- NULL 은 이 CHECK 에서 NULL 로 평가돼 통과한다 = "모름"이 표현 가능하다 (D62). 의도된 동작이다
  CHECK (link_state IN ('NOT_LINKED','LINKED')),
  -- ★ null-safe `IS` (D96). `=` 로 쓰면 (link_state NULL, external_ref 있음) 이 조용히 통과한다
  CHECK (external_ref IS NULL OR link_state IS NOT DISTINCT FROM 'LINKED')
);

-- §19 part_lifecycle_mock — 생애주기 경고(D) 목업 (Sprint 10 브레인스토밍).
-- ⛔ 실 텔레메트리·정비 이력에서 유도하지 않는다 — 사용자가 명시적으로 "새 가짜 필드,
--    부품별 다음 점검일 직접 부여"를 선택했다. 화면에 mock 고지 필수(D65).
CREATE TABLE part_lifecycle_mock (
  equipment_id TEXT NOT NULL REFERENCES equipment,
  part_no      TEXT NOT NULL REFERENCES parts,
  next_maintenance_due DATE NOT NULL,
  PRIMARY KEY (equipment_id, part_no)
);

-- §20 deadlines — 기한 추적 (F5, `11 §10-2`). *시점*을 관리한다 — flags(§15)는 *상태*
-- (발생→이행→해소)를 관리해 성격이 다르다: LIEN-CONSENT 는 flag, "세액공제 사후관리 24개월"은
-- deadline. ⛔ **MCP 쓰기 도구 3종(create_po_draft·generate_disposal_document·
-- create_repair_record) 중 어느 것도 이 테이블에 쓰지 않는다** — 향후 도구가 늘어도 여기 INSERT
-- 는 추가하지 않는다(D10, 절대 규칙 1). 시드는 flags 와 같은 이유로 **0행**(쓰기 경로 없음).
CREATE TABLE deadlines (
  deadline_id BIGSERIAL PRIMARY KEY,
  asset_id    TEXT NOT NULL REFERENCES assets,     -- ★ §10-2 초안 정정: decision 이전 자산 사실에서 계산되므로 anchor
  decision_id TEXT REFERENCES decisions,           -- nullable — 특정 서명 결정에서 파생된 기한만 채움(미래 확장)
  type        TEXT NOT NULL,                       -- 'TAX-CREDIT-2Y' | 'SAFETY-INSPECTION'
  due_date    DATE NOT NULL,
  state       TEXT NOT NULL DEFAULT 'OPEN',        -- 'OPEN' | 'DISMISSED' — flags.state 관행 재사용 (컬럼명 'status' 아님, D9)
  reminder_sent_at TIMESTAMP,
  CHECK (type IN ('TAX-CREDIT-2Y','SAFETY-INSPECTION')),
  CHECK (state IN ('OPEN','DISMISSED'))
);

-- §21 incidents — 물리적 사고 이력 (F5, `11 §10-2`). error_history 와 별개다 — 그건 인버터
-- 에러코드 트립이고 이건 충돌·정렬 손상처럼 회복 불가능한 감가 신호다(`12 §1`). verify_ownership
-- 의 '알람 이력' 항목이 이 구분을 이미 그대로 쓴다(D68 ⓑ). MCP 쓰기 도구는 이 테이블에 쓰지 않는다(D10).
CREATE TABLE incidents (
  incident_id BIGSERIAL PRIMARY KEY,
  asset_id    TEXT NOT NULL REFERENCES assets,     -- ★ 물리적 사고는 호스트 자산 단위 (D68)
  type        TEXT NOT NULL,                       -- 'COLLISION' | 'ALIGNMENT_LOSS' | 'FIRE' | 'FLOOD' | 'OTHER'
  occurred_at TIMESTAMP NOT NULL,
  book_value_at_loss INTEGER,                      -- NULL 허용 — 그 시점 장부가를 모를 수 있음 (D62)
  description TEXT,
  recorded_by TEXT REFERENCES users,               -- 시드분은 NULL (error_history 관행)
  CHECK (type IN ('COLLISION','ALIGNMENT_LOSS','FIRE','FLOOD','OTHER'))
);

-- §22 ownership_checks — 권리관계·실사 확인 결과 보존 (S18, F6, `11 §10-2`). verify_ownership
-- (`04 §9`)의 판정 스키마(9카테고리·38항목, PARTIAL 비승격)는 이 테이블이 생겨도 바뀌지 않는다 —
-- 여기 담기는 건 그 판정 **결과의 스냅샷**뿐이다. ⛔ **verify_ownership 은 읽기 전용(D10)이고
-- 이 테이블에 INSERT 하지 않는다.** MCP 쓰기 도구 3종 중 어느 것도 이 테이블에 쓰지 않으며,
-- 향후에도 그렇다 — 채우는 주체는 시드와 사람 승인을 거치는 백엔드 서비스뿐이다.
CREATE TABLE ownership_checks (
  check_id BIGSERIAL PRIMARY KEY,
  asset_id     TEXT NOT NULL REFERENCES assets,    -- ★ verify_ownership(§9)의 판정 단위와 일치 (D68)
  category     TEXT NOT NULL,                      -- verify_ownership 9카테고리 라벨 그대로
  check_item   TEXT NOT NULL,
  state        TEXT NOT NULL,                       -- 'VERIFIED' | 'UNVERIFIED'
  evidence_ref TEXT,                                -- VERIFIED 일 때만
  limit_note   TEXT,                                -- UNVERIFIED 일 때만
  checked_at   TIMESTAMP NOT NULL,
  checked_by   TEXT REFERENCES users,
  CHECK (state IN ('VERIFIED','UNVERIFIED')),
  CHECK (evidence_ref IS NULL OR state = 'VERIFIED'),
  CHECK (limit_note IS NULL OR state = 'UNVERIFIED')
);

-- §23 risk_profile — 건물 단위 위험 프로파일 (F6, `11 §10-2`). SAFETY-INSPECTION 대상 판정과
-- verify_ownership '법정 요건' 카테고리는 건물 조건에 걸리는데 equipment.location 은 문자열이라
-- 담을 자리가 없었다. FK 없음 — assets.building_id 와 같은 이유(참조 테이블 자체가 없다).
CREATE TABLE risk_profile (
  building_id   TEXT PRIMARY KEY,                  -- assets.building_id 재사용. FK 없음(참조 테이블 없음, §11 주석과 같은 사유)
  fire_handling  TEXT,                              -- 'LOW'|'MEDIUM'|'HIGH'. NULL=모름
  hazmat_volume  TEXT,
  power_capacity TEXT,
  product_type   TEXT,                              -- 자유 서술, 점수화 안 함
  risk_grade     TEXT,                              -- 마지막 저장된 등급. NULL=미산출
  risk_grade_updated_at TIMESTAMP,
  CHECK (fire_handling  IS NULL OR fire_handling  IN ('LOW','MEDIUM','HIGH')),
  CHECK (hazmat_volume  IS NULL OR hazmat_volume  IN ('LOW','MEDIUM','HIGH')),
  CHECK (power_capacity IS NULL OR power_capacity IN ('LOW','MEDIUM','HIGH')),
  CHECK (risk_grade     IS NULL OR risk_grade     IN ('LOW','MEDIUM','HIGH'))
);
