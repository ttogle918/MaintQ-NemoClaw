# -*- coding: utf-8 -*-
"""목업 DB 시드 (M1) — docs/05_DB_SCHEMA.md의 스키마와 시드 케이스 맵 7종을 구현한다.

출력 : data/maintq.db (기존 파일은 .bak 으로 백업 후 재생성)
검증 : 실행 끝에 케이스 맵 7종(①~⑧) + D41 스키마 보강(⑨~⑪) + Sprint 6~7 확장(⑫~㉑)
       + Sprint 8 partner_links·A2A 계측 자리(㉒~㉕) + parts.mfr_part_no(㉖)
       + Sprint 9 repair_records 상태 불변식·error_codes 출처 컬럼·해시 재대조(㉗~㉙)
       + actions 병합 검증(㉚, MQ-919) + part_lifecycle_mock(㉛)
       + Sprint 11 deadlines·incidents·ownership_checks·risk_profile DDL 확정(㉜~㉟, MQ-1101)
       + Sprint 15 error_codes IE5 병합(㊱) + Sprint 17 po_drafts finance 확장(㊲~㊵, MQ-1702)
       + InsuQ 발급 증권번호 체계 고정(㊶~㊷, 2026-09-16)
       를 SQL로 자가 검증하고 통과/실패 표를 출력

원칙
  - `PRAGMA foreign_keys=ON` 필수 (기본 OFF, 안 켜면 D33의 FK 보증이 조용히 사라짐)
  - 적재 순서는 `users` → `po_drafts`/`error_history` (D41 FK). 순서가 틀리면 즉시 실패한다
  - 반복 고장 날짜는 실행일 기준 **상대 날짜** — 데모 날짜가 밀려도 S3가 트리거돼야 함
  - `error_codes`는 시드가 아니라 `data/extracted/error_codes.json`에서 적재.
    단 **사람 승인 전에는 적재하지 않는다** (TODO_직접할일.md / JSON의 _status).
    승인 후 `--with-error-codes` 로 적재한다.

사용
    uv run python data/seed.py
    uv run python data/seed.py --with-error-codes     # iG5A 매핑 승인 후
    uv run python data/seed.py --today 2026-07-23     # 재현용 기준일 고정
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent  # data/

# `python data/seed.py` 로 직접 실행하면 `data/` 가 sys.path[0] 라 `import dbcompat` 이
# 되지만, `from data.seed import ...` 로 패키지 서브모듈처럼 임포트하는 스파이크들
# (rules_db_load.py 등)에서는 repo root 만 sys.path 에 있고 `data/` 자체는 없다 —
# 그런 경우를 위해 repo root 를 먼저 보장한 뒤 패키지 경로로 임포트한다.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))
from data import dbcompat  # noqa: E402
from data.dbcompat import DbConnection, DbRow  # noqa: E402
EXTRACTED = ROOT / "extracted"
ERROR_CODES_JSON = EXTRACTED / "error_codes.json"
RELATED_PARTS_JSON = ROOT / "related_parts.seed.json"
RESIDUAL_CURVE_JSON = EXTRACTED / "residual_curve.json"  # MQ-603 산출물 (D74)
LAWS_DIR = ROOT / "rules" / "laws"  # 계층 1 정본 (D60). DB 행 수를 여기와 대조한다
DB_PATH = ROOT / "maintq.db"

# 시드 난수는 고정 — 같은 기준일이면 같은 DB가 나와야 한다
RNG_SEED = 20260723

# ────────────────────────────────────────────────────────────── 스키마

SCHEMA = """
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
         AND code NOT GLOB '*[^A-Z0-9_]*'),
  CHECK ((actions_manual_id IS NULL) = (actions_page IS NULL))
);

-- 사용자 (D41·D52) — X-User 헤더 값의 원천이자 표시명 매핑 소스.
-- 표시명이 backend/services/po.py 에 하드코딩돼 있던 것을 여기로 옮겼다 (D36→D41).
-- 행을 지우지 않는다: 퇴사자는 active=0. decided_by 가 끊기면 감사 추적(P5)이 무너진다.
CREATE TABLE users (
  user_id       TEXT PRIMARY KEY,         -- 'tech-01' — 헤더로 오가는 ASCII ID (D36)
  email         TEXT UNIQUE,              -- 회사 이메일. 향후 IdP 매칭 키 (D52)
  display_name  TEXT NOT NULL,            -- '김OO' — 화면 표시용
  role          TEXT NOT NULL,            -- 권한. 회사가 사전 부여. OAuth 가 정하지 않는다 (D52)
  department    TEXT,                     -- 소속. **권한이 아니다** — require() 는 안 본다 (D108)
                                           -- NULL 허용 = 미배정. 헤더로 받지 않고 이 컬럼에서만 주입
  auth_provider TEXT NOT NULL DEFAULT 'local',
  external_id   TEXT,                     -- IdP 의 sub/oid. 연동 전 NULL
  active        BOOLEAN NOT NULL DEFAULT 1,
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  CHECK (role IN ('technician','manager')),
  CHECK (department IS NULL OR department IN ('maintenance','finance')),
  CHECK (auth_provider IN ('local','google')),
  CHECK (user_id = lower(user_id) AND user_id NOT GLOB '*[^a-z0-9-]*')
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
  parts_eol_flag         BOOLEAN NOT NULL DEFAULT 0,
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
  id           INTEGER PRIMARY KEY,
  equipment_id TEXT NOT NULL REFERENCES equipment,
  code         TEXT NOT NULL,             -- 대문자 canonical (D25)
  occurred_at  DATETIME NOT NULL,
  action_taken TEXT,
  part_replaced TEXT,
  resolved     BOOLEAN DEFAULT 1,
  recorded_by  TEXT REFERENCES users      -- 기록한 정비사 (D41). 시드분은 NULL
);
CREATE INDEX idx_history_eq_code ON error_history(equipment_id, code, occurred_at);

CREATE TABLE parts (
  part_no      TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  category     TEXT,
  compatible_models TEXT NOT NULL,        -- JSON array
  discontinued BOOLEAN DEFAULT 0,
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
  created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
  decided_at            DATETIME,                 -- 팀장 결정 시각 (기존 gap — approve/reject 도 지금까지 없었다)
  finance_decided_by    TEXT REFERENCES users,     -- 재무 담당 사용자 ID
  finance_decision_note TEXT,                      -- 재무 승인 코멘트 / 반려 사유
  finance_decided_at    DATETIME,                  -- 재무 결정 시각
  FOREIGN KEY (model, error_code) REFERENCES error_codes(model, code),
  CHECK (state IN ('draft','pending','approved','rejected','finance_approved','finance_rejected')),
  CHECK (urgency IN ('urgent','normal')),
  CHECK (error_code IS NULL OR (
           length(error_code) BETWEEN 2 AND 4
           AND error_code = upper(error_code)
           AND error_code NOT GLOB '*[^A-Z0-9_]*')),
  CHECK ((model IS NULL) = (error_code IS NULL)),
  CHECK (evidence IS NULL OR json_valid(evidence))
);

CREATE TABLE traces (
  id           INTEGER PRIMARY KEY,
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
  ts           DATETIME DEFAULT CURRENT_TIMESTAMP,
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
  promulgation_no TEXT, source_url TEXT, retrieved_at DATETIME,
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
  trigger TEXT NOT NULL, boundary TEXT,
  message TEXT NOT NULL, resolve_options TEXT NOT NULL,
  confidence TEXT NOT NULL, requires_expert_review BOOLEAN NOT NULL,
  PRIMARY KEY (rule_id, rule_version),
  CHECK (disposal_type IN ('BLOCKING','PRECONDITION','AUTO_CLOSE')),
  CHECK (source_type IN ('LAW','CONTRACT')),
  CHECK (json_valid(law_refs) AND json_valid(contract_refs) AND json_valid(trigger))
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
  override BOOLEAN NOT NULL DEFAULT 0,
  override_reason TEXT,
  reviewed_by TEXT REFERENCES users,
  signed_at DATETIME,
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
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  -- D63 을 스키마로 잠근다 — 사유 없는 override 는 저장 자체가 불가
  CHECK (override = 0 OR (override_reason IS NOT NULL AND length(trim(override_reason)) > 0)),
  CHECK (json_valid(evidence_bundle)),
  CHECK (state IN ('draft','pending','signed','rejected')),
  -- ★ "서명 없는 처분 확정 0건" — state='signed' 인데 서명자·서명시각·번들해시가 비면 거부.
  --   `signed` 는 "누가 언제 무엇에 서명했는가"가 전부 있어야 성립하는 상태다.
  --   셋 중 하나라도 없는 행은 *서명처럼 보이는 행*이지 서명이 아니다.
  CHECK (state <> 'signed' OR (signed_at IS NOT NULL
                               AND reviewed_by IS NOT NULL
                               AND length(trim(bundle_hash)) > 0)),
  -- ★ "BLOCKING 우회 처분 0건" — 차단 판정(BLOCKED·HOLD·INSUFFICIENT_FACTS)에 서명하려면
  --   override=1 이어야 하고, override=1 이면 위 D63 CHECK 가 사유를 강제한다.
  --   두 CHECK 가 맞물려 **"사유 없는 우회 서명"이 스키마 수준에서 표현 불가능**해진다.
  --   ⚠ 여기 열거된 두 값은 `engine.VERDICTS` 의 **비차단** 어휘다. 엔진이 어휘를 늘리면
  --     이 목록이 조용히 낡으므로 `verify()` ㉑ 이 DDL 문자열을 파싱해 엔진과 대조한다.
  CHECK (state <> 'signed' OR override = 1
         OR verdict_at_signing IN ('CONDITIONAL','CLEAR'))
);

-- §15 flags — 법정 조건 상태 (발생 → 이행 → 해소). deadlines(F5)와 성격이 다름
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
  signed_at DATETIME, record_hash TEXT,
  state TEXT NOT NULL DEFAULT 'draft',
  -- ★ Sprint 9 신설 (D98) — 도구는 이 셋을 채우지 않는다. 백엔드가 X-User·세션에서 stamp 한다
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
  linked_at    DATETIME,
  PRIMARY KEY (partner, subject_type, subject_ref),
  -- NULL 은 이 CHECK 에서 NULL 로 평가돼 통과한다 = "모름"이 표현 가능하다 (D62). 의도된 동작이다
  CHECK (link_state IN ('NOT_LINKED','LINKED')),
  -- ★ null-safe `IS` (D96). `=` 로 쓰면 (link_state NULL, external_ref 있음) 이 조용히 통과한다
  CHECK (external_ref IS NULL OR link_state IS 'LINKED')
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

-- §21 incidents — 물리적 사고 이력 (F5, `11 §10-2`). error_history 와 별개다 — 그건 인버터
-- 에러코드 트립이고 이건 충돌·정렬 손상처럼 회복 불가능한 감가 신호다(`12 §1`). verify_ownership
-- 의 '알람 이력' 항목이 이 구분을 이미 그대로 쓴다(D68 ⓑ). MCP 쓰기 도구는 이 테이블에 쓰지 않는다(D10).
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

-- §22 ownership_checks — 권리관계·실사 확인 결과 보존 (S18, F6, `11 §10-2`). verify_ownership
-- (`04 §9`)의 판정 스키마(9카테고리·38항목, PARTIAL 비승격)는 이 테이블이 생겨도 바뀌지 않는다 —
-- 여기 담기는 건 그 판정 **결과의 스냅샷**뿐이다. ⛔ **verify_ownership 은 읽기 전용(D10)이고
-- 이 테이블에 INSERT 하지 않는다.** MCP 쓰기 도구 3종 중 어느 것도 이 테이블에 쓰지 않으며,
-- 향후에도 그렇다 — 채우는 주체는 시드와 사람 승인을 거치는 백엔드 서비스뿐이다.
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
  risk_grade_updated_at DATETIME,
  CHECK (fire_handling  IS NULL OR fire_handling  IN ('LOW','MEDIUM','HIGH')),
  CHECK (hazmat_volume  IS NULL OR hazmat_volume  IN ('LOW','MEDIUM','HIGH')),
  CHECK (power_capacity IS NULL OR power_capacity IN ('LOW','MEDIUM','HIGH')),
  CHECK (risk_grade     IS NULL OR risk_grade     IN ('LOW','MEDIUM','HIGH'))
);
"""

# ────────────────────────────────────────────────────────────── 마스터 데이터

# (user_id, email, display_name, role, auth_provider) — D41·D52
# auth_provider 는 전부 'local' : 회사 IdP 연동(google)은 백로그 P21 이고, 개인 소셜은 넣지 않는다.
# 이메일은 회사 도메인 형식 예시 (.example 은 RFC 2606 예약 도메인 — 실제로 발송되지 않는다)
# department: 소속. role(권한) 과 직교 — P41 ③ (D108). 재무부 담당자도 role 은 그대로 'manager' 다.
USERS = [
    ("tech-01", "kim@maintq.example", "김OO", "technician", "maintenance", "local"),
    ("tech-02", "lee@maintq.example", "이OO", "technician", "maintenance", "local"),
    ("mgr-01", "park@maintq.example", "박OO", "manager", "maintenance", "local"),
    ("mgr-02", "choi@maintq.example", "최OO", "manager", "finance", "local"),
]

SUPPLIERS = [
    ("SUP-A", "에이스산전", "02-555-0101 / sales@acesanjeon.example", "110-384-928103", "088"),  # 신한은행
    ("SUP-B", "비전파츠", "031-777-0202 / order@visionparts.example", "302-8491-0294-11", "011"),  # 농협
    ("SUP-C", "대한전기자재", "051-333-0303 / cs@daehan-elec.example", "029-21-0849201", "004"),   # 국민은행
    ("SUP-D", "한빛오토메이션", "032-999-0404 / help@hanbit-auto.example", "1002-941-839201", "020"),  # 우리은행
]


# (part_no, name, category, compatible_models, discontinued)
PARTS: list[tuple[str, str, str, list[str], int]] = [
    # ── 케이스 맵의 주인공들
    ("FAN-IG5-01", "냉각팬 (iG5A 표준)", "냉각", ["iG5A"], 0),
    ("PCB-S100-CTRL", "제어보드", "제어", ["S100"], 1),  # 단종 → S2
    ("PCB-S100-CTRL-R2", "제어보드 (후속 리비전)", "제어", ["S100"], 0),
    ("PWR-S100-MOD", "전원모듈", "전원", ["S100"], 0),  # 대체품 없음 → S2 서브
    ("FAN-GEN-40", "범용 냉각팬 40mm", "냉각", ["iG5A", "S100"], 0),  # 미확인 호환
    # ── 냉각
    ("FAN-S100-01", "냉각팬 (S100 표준)", "냉각", ["S100"], 0),
    ("FAN-IG5-02", "냉각팬 (iG5A 대용량)", "냉각", ["iG5A"], 0),
    ("HSK-IG5-01", "히트싱크", "냉각", ["iG5A"], 0),
    ("THM-GEN-01", "서멀 그리스", "냉각", ["iG5A", "S100"], 0),
    ("FLT-AIR-01", "흡기 필터", "냉각", ["iG5A", "S100"], 0),
    # ── 제어
    ("PCB-IG5-CTRL", "제어보드 (iG5A)", "제어", ["iG5A"], 0),
    ("PCB-IG5-IO", "I/O 확장보드", "제어", ["iG5A"], 0),
    ("KPD-IG5-01", "키패드/로더", "제어", ["iG5A"], 0),
    ("KPD-S100-01", "키패드/로더 (S100)", "제어", ["S100"], 0),
    ("PCB-S100-IO", "I/O 확장보드 (S100)", "제어", ["S100"], 0),
    ("CBL-COMM-RS485", "RS485 통신 케이블", "제어", ["iG5A", "S100"], 0),
    # ── 전원
    ("IGBT-IG5-2K2", "IGBT 모듈 2.2kW", "전원", ["iG5A"], 0),
    ("IGBT-S100-4K0", "IGBT 모듈 4.0kW", "전원", ["S100"], 0),
    ("CAP-DC-450", "DC링크 콘덴서 450V", "전원", ["iG5A", "S100"], 0),
    ("REC-BRG-01", "정류 브리지", "전원", ["iG5A"], 0),
    ("FUSE-30A", "퓨즈 30A", "전원", ["iG5A", "S100"], 0),
    ("FUSE-50A", "퓨즈 50A", "전원", ["S100"], 0),
    ("MC-40A", "전자접촉기 40A", "전원", ["iG5A", "S100"], 0),
    ("SPD-01", "서지보호기", "전원", ["iG5A", "S100"], 0),
    ("PWR-IG5-MOD", "전원모듈 (iG5A)", "전원", ["iG5A"], 0),
    # ── 구동
    ("MTR-3P-2K2", "3상 유도전동기 2.2kW", "구동", ["iG5A"], 0),
    ("MTR-3P-4K0", "3상 유도전동기 4.0kW", "구동", ["S100"], 0),
    ("MTR-CBL-IG5", "모터 출력 케이블", "구동", ["iG5A"], 0),
    ("MTR-CBL-S100", "모터 출력 케이블 (S100)", "구동", ["S100"], 0),
    ("BRG-6205", "베어링 6205", "구동", ["iG5A", "S100"], 0),
    ("BLT-V-A50", "V벨트 A50", "구동", ["iG5A", "S100"], 0),
    ("CPL-JAW-01", "커플링", "구동", ["iG5A", "S100"], 0),
    ("BRK-RES-200", "제동저항 200W", "구동", ["iG5A"], 0),
    # ── 센서·계측
    ("SNS-TEMP-PT100", "온도센서 PT100", "센서", ["iG5A", "S100"], 0),
    ("SNS-CT-100A", "전류센서 CT 100A", "센서", ["iG5A", "S100"], 0),
    ("SNS-VIB-01", "진동센서", "센서", ["iG5A", "S100"], 0),
    ("ENC-1024", "엔코더 1024PPR", "센서", ["S100"], 0),
    # ── 소모품
    ("TRM-BLK-12", "단자대 12P", "소모품", ["iG5A", "S100"], 0),
    ("GLD-PG16", "케이블 글랜드 PG16", "소모품", ["iG5A", "S100"], 0),
    ("LBL-WARN-01", "경고 라벨 세트", "소모품", ["iG5A", "S100"], 0),
]

# 케이스 맵이 고정하는 재고 (나머지는 아래에서 생성)
INVENTORY_FIXED: dict[str, tuple[int, int, str]] = {
    "FAN-IG5-01": (1, 3, "자재창고 A-12"),  # 케이스 1: 안전재고 미달 → S1
    "PCB-S100-CTRL": (0, 1, "자재창고 B-03"),  # 케이스 2: 재고 0 + 단종 → S2
    "PWR-S100-MOD": (0, 2, "자재창고 B-07"),  # 케이스 3: 재고 0 + 대체품 없음
    "PCB-S100-CTRL-R2": (4, 2, "자재창고 B-03"),
}

# (part_no, alt_part_no, compat_confirmed, note)
# compat_confirmed=0 은 **정확히 1건**만 둔다 (케이스 맵 ⑥ — "제안 금지" 검증용)
ALTERNATIVES = [
    ("PCB-S100-CTRL", "PCB-S100-CTRL-R2", 1, "동일 사양 후속 리비전 — 제조사 호환 확인"),
    ("FAN-IG5-01", "FAN-GEN-40", 0, "치수는 동일하나 풍량·내열 등급 미확인 — 제안 금지"),
    ("FAN-IG5-01", "FAN-IG5-02", 1, "상위 대용량 팬, 취부 호환"),
    ("FUSE-30A", "FUSE-50A", 1, "정격 상향 — 보호 협조 확인 완료"),
]

# 케이스 맵이 고정하는 견적 (S1 트레이드오프)
SUPPLIER_PARTS_FIXED = [
    ("SUP-A", "FAN-IG5-01", 3, 38000, 1),
    ("SUP-B", "FAN-IG5-01", 14, 29000, 10),
    ("SUP-A", "PCB-S100-CTRL-R2", 5, 264000, 1),
    ("SUP-C", "PCB-S100-CTRL-R2", 12, 231000, 1),
    ("SUP-D", "PWR-S100-MOD", 21, 415000, 1),
]

# (equipment_id, line_id, model, installed_at, location, asset_id)
# asset_id 는 D68 — 인버터의 호스트 설비. `INV-L1-01`(분전반)만 NULL 이다:
# 배전 위치이지 거래 가능한 기계가 아니라서, 전 확장 도구의 `no_host_asset` 경로 재료가 된다.
EQUIPMENT = [
    ("INV-L1-01", 1, "iG5A", "2021-04-12", "1번 조립라인 분전반", None),
    ("INV-L1-02", 1, "iG5A", "2021-04-12", "1번 조립라인 컨베이어", "AST-L1-CONV"),
    ("INV-L2-01", 2, "S100", "2022-09-30", "2번 가공라인 주축", "AST-L2-SPDL"),
    ("INV-L2-02", 2, "S100", "2022-09-30", "2번 가공라인 절삭유 펌프", "AST-L2-CLNT"),
    ("INV-L3-01", 3, "iG5A", "2020-11-05", "3번 조립라인 반송 컨베이어", "AST-L3-CONV"),
    ("INV-L3-02", 3, "iG5A", "2020-11-05", "3번 조립라인 배기팬", "AST-L3-EXFAN"),
    ("INV-L3-03", 3, "S100", "2023-02-17", "3번 조립라인 리프터", "AST-L3-LIFT"),
    ("INV-L4-01", 4, "S100", "2023-06-01", "4번 포장라인 컨베이어", "AST-L4-CONV"),
    ("INV-L4-02", 4, "S100", "2023-06-01", "4번 포장라인 랩핑기", "AST-L4-WRAP"),
    ("INV-L4-03", 4, "iG5A", "2019-08-22", "4번 포장라인 집진기", "AST-L4-DUST"),
]

# ── parts.part_class 40종 (12 §9) ─────────────────────────────────────────
# **LLM 추측 금지 (D12 태도).** 40종을 전부 여기 명시하고, 누락되면 시드가 중단된다.
# ⚠ 이 분류는 **사람 미검수 초안**이다 — `part_class_caveat()` 가 매 실행 경고를 찍는다.
#   `assess_repair_value` 의 3지 판단이 이 값에 직접 걸리므로 검수 대상이다 (TODO_직접할일.md).
#
# 기준 (명세): 소모품·필터·그리스·라벨·글랜드·단자대·V벨트 → CONSUMABLE /
#              PCB·IGBT·모터·베어링·엔코더·전원모듈·정류브리지·감속 계열 → CRITICAL
# 명세가 열거하지 않은 품목(히트싱크·키패드·센서·접촉기·서지보호기·커플링·케이블·퓨즈·
# 제동저항)은 **판단으로 채웠다.** 이 9종이 검수에서 가장 먼저 뒤집힐 후보다.
PART_CLASS: dict[str, str] = {
    # 냉각 — 팬은 전량 CRITICAL. FAN-IG5-01 은 S1 주인공이라 3지 판단 데모가 성립해야 한다
    "FAN-IG5-01": "CRITICAL",
    "FAN-IG5-02": "CRITICAL",
    "FAN-S100-01": "CRITICAL",
    "FAN-GEN-40": "CRITICAL",
    "HSK-IG5-01": "CRITICAL",  # 판단: 히트싱크는 마모품이 아니라 열설계 구성품
    "THM-GEN-01": "CONSUMABLE",  # 그리스
    "FLT-AIR-01": "CONSUMABLE",  # 필터
    # 제어 — PCB 계열
    "PCB-S100-CTRL": "CRITICAL",
    "PCB-S100-CTRL-R2": "CRITICAL",
    "PCB-IG5-CTRL": "CRITICAL",
    "PCB-IG5-IO": "CRITICAL",
    "PCB-S100-IO": "CRITICAL",
    "KPD-IG5-01": "CRITICAL",  # 판단: 키패드/로더는 PCB 조립품
    "KPD-S100-01": "CRITICAL",  # 판단
    "CBL-COMM-RS485": "CONSUMABLE",  # 판단: 배선 부속
    # 전원
    "PWR-S100-MOD": "CRITICAL",  # 전원모듈
    "PWR-IG5-MOD": "CRITICAL",  # 전원모듈
    "IGBT-IG5-2K2": "CRITICAL",
    "IGBT-S100-4K0": "CRITICAL",
    "CAP-DC-450": "CRITICAL",  # DC링크 콘덴서 — 교체가 사실상 오버홀
    "REC-BRG-01": "CRITICAL",  # 정류브리지
    "FUSE-30A": "CONSUMABLE",  # 판단: 소모성 보호부품
    "FUSE-50A": "CONSUMABLE",  # 판단
    "MC-40A": "CONSUMABLE",  # 판단: 접점 수명 기반 정기 교체품
    "SPD-01": "CONSUMABLE",  # 판단: 서지 흡수 후 희생되는 부품
    # 구동
    "MTR-3P-2K2": "CRITICAL",  # 모터
    "MTR-3P-4K0": "CRITICAL",  # 모터
    "BRG-6205": "CRITICAL",  # 베어링
    "BLT-V-A50": "CONSUMABLE",  # V벨트
    "CPL-JAW-01": "CONSUMABLE",  # 판단: 조 커플링 엘라스토머는 마모 교체품
    "BRK-RES-200": "CRITICAL",  # 판단: 제동회로 구성품
    "MTR-CBL-IG5": "CONSUMABLE",  # 판단: 배선 부속
    "MTR-CBL-S100": "CONSUMABLE",  # 판단
    # 센서·계측 — 보호·피드백 경로라 CRITICAL (엔코더는 명세 명시)
    "ENC-1024": "CRITICAL",
    "SNS-TEMP-PT100": "CRITICAL",  # 판단
    "SNS-CT-100A": "CRITICAL",  # 판단
    "SNS-VIB-01": "CRITICAL",  # 판단
    # 소모품
    "TRM-BLK-12": "CONSUMABLE",  # 단자대
    "GLD-PG16": "CONSUMABLE",  # 글랜드
    "LBL-WARN-01": "CONSUMABLE",  # 라벨
}

# `part_class` 사람 검수 여부. 검수가 끝나면 사람이 True 로 바꾼다 (TODO_직접할일.md).
# 문구를 하드코딩하지 않고 이 플래그에서 유도한다 — related_parts_caveat() 와 같은 형태.
#
# 승인 이력 (related_parts.seed.json 의 `_승인_이력` 과 같은 수준으로 남긴다 —
#            누가 무엇을 언제 판단했는지가 지워지면 승인의 의미가 사라진다):
#   2026-08-05? · Sprint 6 Stage 2 — 초안 분류. `12 §9` 명세 열거를 따르되
#                 **열거 밖 9종은 추측으로 분류**했다(히트싱크·키패드·센서 3종·접촉기·
#                 SPD·커플링·제동저항·케이블)
#   2026-08-13  · 사용자 — 40종 전량 확인 후 **초안 그대로 승인**(변경 0건).
#                 추측 9종과 `FAN-IG5-01 = CRITICAL`(S1 주인공, 3지 판단 데모 성립 조건)에
#                 모두 동의. 이로써 `assess_repair_value` 3지 판단을 실적으로 인용할 수 있다.
PART_CLASS_REVIEWED = True

# ── part_lifecycle_mock — 생애주기 경고(D) 목업 데이터 ───────────────────────
# 하이라이트 대상 부품(냉각팬·키패드·제어보드, frontend/lib/hotspots.ts 와 part_no 짝) ×
# asset_id 가 있는 9개 설비 = 27행. offset_days 는 오늘(시드 실행일) 기준
# next_maintenance_due 오프셋 — 이미 지난 것(음수)·임박·여유 있는 것을 섞어 데모 다양성을 준다.
PART_LIFECYCLE_MOCK: list[tuple[str, str, int]] = [
    ("INV-L1-02", "FAN-IG5-01", -12),
    ("INV-L1-02", "KPD-IG5-01", 45),
    ("INV-L1-02", "PCB-IG5-CTRL", 210),
    ("INV-L3-01", "FAN-IG5-01", 18),
    ("INV-L3-01", "KPD-IG5-01", 95),
    ("INV-L3-01", "PCB-IG5-CTRL", -5),
    ("INV-L3-02", "FAN-IG5-01", 300),
    ("INV-L3-02", "KPD-IG5-01", -30),
    ("INV-L3-02", "PCB-IG5-CTRL", 60),
    ("INV-L4-03", "FAN-IG5-01", 8),
    ("INV-L4-03", "KPD-IG5-01", 150),
    ("INV-L4-03", "PCB-IG5-CTRL", 40),
    ("INV-L2-01", "FAN-S100-01", 55),
    ("INV-L2-01", "KPD-S100-01", -18),
    ("INV-L2-01", "PCB-S100-CTRL", 120),
    ("INV-L2-02", "FAN-S100-01", 25),
    ("INV-L2-02", "KPD-S100-01", 400),
    ("INV-L2-02", "PCB-S100-CTRL", -2),
    ("INV-L3-03", "FAN-S100-01", 175),
    ("INV-L3-03", "KPD-S100-01", 33),
    ("INV-L3-03", "PCB-S100-CTRL", 9),
    ("INV-L4-01", "FAN-S100-01", -22),
    ("INV-L4-01", "KPD-S100-01", 80),
    ("INV-L4-01", "PCB-S100-CTRL", 250),
    ("INV-L4-02", "FAN-S100-01", 47),
    ("INV-L4-02", "KPD-S100-01", 15),
    ("INV-L4-02", "PCB-S100-CTRL", -40),
]


def seed_part_lifecycle_mock(con: DbConnection, today: date) -> int:
    """§19 part_lifecycle_mock 적재. `today`(--today 인자)기준 상대 오프셋 — 데모 날짜가

    밀려도 임박/여유 분포가 유지된다.
    """
    rows = [
        (equipment_id, part_no, (today + timedelta(days=offset)).isoformat())
        for equipment_id, part_no, offset in PART_LIFECYCLE_MOCK
    ]
    con.executemany("INSERT INTO part_lifecycle_mock VALUES (?,?,?)", rows)
    return len(rows)


# ── parts.mfr_part_no — 제조사 실품번 (D97) ────────────────────────────────
#
# ⛔ **여기 없는 부품은 "우리가 아직 못 찾은 것"이 아니라 "세상에 공개돼 있지 않은 것"이다.**
#    2026-08-14 에 4개 축을 전수 조사했고 결과가 `data/analysis/part_number_sources.md` 에 있다:
#      ⓐ 공공데이터(조달청) — 부품 8종 0건 (대조군 케이블 958·전동기 21 정상 검출)
#      ⓑ LS 매뉴얼 1,035청크 전수 스캔 — 품번 토큰 34종이 제동유닛·EMC필터·MCCB 세 계열뿐.
#         **냉각/팬 0 · 제어보드 0 · 키패드 0**(같은 스캐너가 제동유닛을 잡으므로 양성 축 살아 있음)
#      ⓒ 국내 유통(나비엠알오·미스미) — 완제품 SKU 만
#      ⓓ 해외 전문 판매점 부품 목록 **사람 전수 확인** — iG5A 는 아래 1종뿐.
#         같은 목록에 팬이 4종 있는데(S100 11~15 · S100 18.5~45 · iS7 30~45 · **iS7 5.5kW**)
#         **iG5A 팬만 0건**이다. 소용량이라 안 파는 것도 아니다(iS7 5.5kW 존재) → **품목 부재**
#    근본 원인은 유통 정책이다 — 매뉴얼이 *"FAN교체는 구입처나 LS산전 고객센터에 문의하십시오"*
#    라고 **명시**한다. 그래서 **검색을 더 해도 채워지지 않는다.** 남은 경로는 대리점 문의(사람).
#
# ⚠ **넣으면 안 되는 값 3종** (조사 중 실제로 헷갈렸던 것들):
#   ① 판매점 주문번호(`Order code: 32155`) — 같은 물건도 판매점마다 다르다. 품번이 아니다
#   ② 완제품 형명(`SV220iG5A-4`·`LSLV0004G100-2EONN`) — 인버터 1대이지 교체 부품이 아니다
#   ③ 추측·유추한 품번 — CLAUDE.md 절대규칙 6 과 같은 계열이다. **모르면 NULL 이 정답이다**
MFR_PART_NO: dict[str, str] = {
    # 제어보드 + 로컬 키패드 일체형. 판매점 페이지가 `Part number:` 로 명시했고
    # 적용 범위 `0.4~7.5KW-2/4` 가 MaintQ 자산 용량대(2.2·4.0kW)를 덮는다.
    # 확인: 2026-08-14 사람 · 출처: `data/analysis/part_number_sources.md §③`
    "PCB-IG5-CTRL": "SV-iG5A I/OPCBASSY",
}

# ── assets 9건 (D68) ──────────────────────────────────────────────────────
# `age_years` 는 **실행 연도 기준 상대 연차**다 — acquired_at 의 연도 = today.year - age_years.
# `assess_repair_value` 가 `age = 오늘연도 - year(acquired_at)` 으로 버킷을 잡으므로,
# 날짜를 하드코딩하면 해가 바뀔 때 버킷이 조용히 밀린다 (반복 고장 상대 날짜와 같은 이유).
#
# `category` 는 MQ-603 이 출력한 **원본 CSV 바이트 그대로** — `'환경  설비'` 는 공백 2칸이다.
# ⚠ 자산 → 카테고리 매핑은 **추정치다.** 중고 장터의 매물 분류축을 우리 설비에 씌운 것이라
#   대응이 정확하지 않다(포장기계 대응 분류가 없어 랩핑기는 `'기타'`). 목업 곡선은 전 카테고리
#   값이 같아 지금은 판정에 영향이 없지만, 진짜 카테고리별 곡선이 들어오면 재검토 대상이다 (D65).
ASSETS: list[dict] = [
    {
        "asset_id": "AST-L1-CONV",
        "name": "1번 조립라인 컨베이어",
        "category": "일반산업",
        "line_id": 1,
        "building_id": "BLD-A",
        "age_years": 5,  # 3-5
        "acq_md": (4, 12),
        "acquisition_cost": 52_000_000,
        "status": "IN_USE",
        "tax_credit_applied": 0,
        "has_lien": 0,
        "insured": 1,
        "policy_id": "SB-2023-0001",
        "safety_inspection_target": 0,
        "controller_generation": "iG5A/2020",
        "overhaul_years_ago": None,
        "parts_eol_flag": 0,
    },
    {
        "asset_id": "AST-L2-SPDL",
        "name": "2번 가공라인 주축",
        "category": "공작 기계",
        "line_id": 2,
        "building_id": "BLD-B",
        "age_years": 16,  # 16-20
        "acq_md": (5, 20),
        "acquisition_cost": 120_000_000,
        "status": "IN_USE",
        # 처분 시나리오: 담보 없음 + 안전검사 대상 → PRECONDITION 만 → CONDITIONAL 기대
        "tax_credit_applied": 0,
        "has_lien": 0,
        "insured": 1,
        "policy_id": "DS-2024-0002",
        "safety_inspection_target": 1,
        "controller_generation": "S100/2018",
        "overhaul_years_ago": 3,
        "parts_eol_flag": 0,
    },
    {
        "asset_id": "AST-L2-CLNT",
        "name": "2번 가공라인 절삭유 펌프",
        "category": "공조냉각유공압",  # N-12 로 곡선에 추가된 분류
        "line_id": 2,
        "building_id": "BLD-B",
        "age_years": 9,  # 6-10
        "acq_md": (5, 20),
        "acquisition_cost": 18_000_000,
        "status": "IN_USE",
        "tax_credit_applied": 0,
        "has_lien": 0,
        "insured": 1,
        "policy_id": "DS-2024-0002",
        "safety_inspection_target": 0,
        "controller_generation": "S100/2018",
        "overhaul_years_ago": None,
        "parts_eol_flag": 0,
    },
    {
        "asset_id": "AST-L3-CONV",
        "name": "3번 조립라인 반송 컨베이어",
        "category": "일반산업",
        "line_id": 3,
        "building_id": "BLD-C",
        "age_years": 6,  # 6-10
        "acq_md": (2, 10),
        "acquisition_cost": 80_000_000,
        "status": "IN_USE",
        # 처분 시나리오: 세액공제 + 무동의 담보 → BLOCKING 2건 기대
        "tax_credit_applied": 1,
        "has_lien": 1,
        "lien_creditor": "한빛은행 여신부",
        "lien_consent_ref": None,  # 동의서 없음 → LIEN-CONSENT trigger 재료
        "insured": 1,
        "policy_id": "SBP-2022-0003",
        "safety_inspection_target": 0,
        "controller_generation": "iG5A/2020",
        "overhaul_years_ago": None,
        "parts_eol_flag": 0,
    },
    {
        "asset_id": "AST-L3-EXFAN",
        "name": "3번 조립라인 배기팬",
        "category": "공조냉각유공압",
        "line_id": 3,
        "building_id": "BLD-C",
        "age_years": 8,  # 6-10
        "acq_md": (2, 10),
        "acquisition_cost": 22_000_000,
        "status": "IN_USE",
        "tax_credit_applied": 0,
        "has_lien": 0,
        "insured": 1,
        "policy_id": "SBP-2022-0003",
        "safety_inspection_target": 0,
        "controller_generation": "iG5A/2020",
        "overhaul_years_ago": None,
        "parts_eol_flag": 0,
    },
    {
        "asset_id": "AST-L3-LIFT",
        "name": "3번 조립라인 리프터",
        "category": "일반산업",
        "line_id": 3,
        "building_id": "BLD-C",
        "age_years": 3,  # 3-5
        "acq_md": (2, 17),
        # ★ 취득원가 미상 → 시장가 산출 불가 → assess_repair_value 는 HOLD 여야 한다.
        #   0 이 아니라 NULL 이다. "모른다"를 0 으로 적으면 값이 생겨버린다 (D62)
        "acquisition_cost": None,
        "status": "IN_USE",
        # 처분 시나리오: 전 사실 채움·무해당 → CLEAR 기대.
        # ★ 9자산 중 **유일하게 미부보**다 (D78) — 전 자산이 부보돼 있으면 INSURANCE-NOTIFY 가
        #   항상 발화해 CLEAR 가 어떤 조합으로도 나오지 않는다. `insured=0` 은 "모름"(NULL)이
        #   아니라 **확인된 미부보**이고, 그래서 policy_id 도 NULL 이다(증권이 없으니까).
        # ⚠ 그래도 `disposal_mode='SALE'` 이면 VAT-INVOICE 가 발화해 CONDITIONAL 이다 —
        #   매각 precheck 이 최소 CONDITIONAL 인 건 도메인 사실이라(D78 부수 확정),
        #   이 자산의 CLEAR 는 **SCRAP·TRANSFER 에서만** 나온다.
        "tax_credit_applied": 0,
        "has_lien": 0,
        "insured": 0,
        "policy_id": None,
        "safety_inspection_target": 0,
        "controller_generation": "S100/2022",
        "overhaul_years_ago": None,
        "parts_eol_flag": 0,
    },
    {
        "asset_id": "AST-L4-CONV",
        "name": "4번 포장라인 컨베이어",
        "category": "일반산업",
        "line_id": 4,
        "building_id": "BLD-D",
        "age_years": 4,  # 3-5
        "acq_md": (6, 1),
        "acquisition_cost": 48_000_000,
        "status": "IN_USE",
        "tax_credit_applied": 0,
        "has_lien": 0,
        "insured": 1,
        "policy_id": "SB-2024-0004",
        "safety_inspection_target": 0,
        "controller_generation": "S100/2022",
        "overhaul_years_ago": None,
        "parts_eol_flag": 0,
    },
    {
        "asset_id": "AST-L4-WRAP",
        "name": "4번 포장라인 랩핑기",
        # 원본 `카테고리1` 에 포장기계 대응 분류가 없다 → 수용처인 `'기타'`
        "category": "기타",
        "line_id": 4,
        "building_id": "BLD-D",
        "age_years": 20,  # 16-20
        "acq_md": (6, 1),
        "acquisition_cost": 60_000_000,
        "status": "IN_USE",
        # 처분 시나리오: months_since_acquisition 경계(22~26) → HOLD 기대
        "tax_credit_applied": 1,
        "has_lien": 0,
        "insured": 1,
        "policy_id": "SB-2024-0004",
        "safety_inspection_target": 0,
        "controller_generation": "S100/2012",
        "overhaul_years_ago": 6,
        "parts_eol_flag": 0,
    },
    {
        "asset_id": "AST-L4-DUST",
        "name": "4번 포장라인 집진기",
        "category": "환경  설비",  # ← 공백 2칸. 원본 CSV 바이트 그대로 (MQ-603 §2-6)
        "line_id": 4,
        "building_id": "BLD-D",
        "age_years": 12,  # 11-15
        "acq_md": (8, 22),
        "acquisition_cost": 45_000_000,
        "status": "IN_USE",
        # 처분 시나리오: 세액공제 적용 여부 **미상** → INSUFFICIENT_FACTS 기대 (CLEAR 아님, D62)
        "tax_credit_applied": None,
        "has_lien": 0,
        "insured": 1,
        "policy_id": "SB-2024-0004",
        "safety_inspection_target": 0,
        "controller_generation": "iG5A/2014",
        "overhaul_years_ago": None,
        "parts_eol_flag": 1,  # 핵심 부품 단종 → REPLACE_RECOMMENDED 재료
    },
]

# 처분 룰 트리거용 `disposal_date` — **시드 컬럼이 아니라 도구 파라미터다.**
# 잔가 버킷 요구(age 3~20년)와 처분 룰 요구(취득 후 17·23개월)가 같은 자산에 동시에 걸리는데,
# `acquired_at` 은 잔가 기준으로 고정하고 `months_since_acquisition` 은 이 값으로 만든다.
# → 결과적으로 **과거 날짜**가 된다(취득 17개월 뒤 시점의 처분 검토). 판정 엔진은 이 값을
#   기간 계산에만 쓰고 미래/과거를 검증하지 않으므로 두 요구가 실제로 양립한다.
DISPOSAL_PROBE_MONTHS: dict[str, int] = {
    "AST-L3-CONV": 17,  # < 24 이고 경계(22~26) 밖 → TAX-CREDIT-2Y TRIGGERED
    "AST-L4-WRAP": 23,  # 경계 안 → HOLD
    "AST-L2-SPDL": 60,  # 창 밖 → TAX 는 CLEAR, 안전검사만 남음
    "AST-L4-DUST": 60,
    "AST-L3-LIFT": 60,
}

# ⑮ 의 기대값 (MQ-601b · D77·D78·D79). **검사할 성질만** 적는다 —
# `blockers`/`holds`/`insufficient` 개수를 함께 잠그는 이유: verdict 만 보면 룰이 **엉뚱한
# 이유로 같은 답**을 내도 통과한다(경계 때문인지 사실 부족 때문인지가 안 보인다).
#
# ★ `AST-L3-LIFT` 만 `SCRAP` 으로 프로브한다 — 매각 precheck 은 VAT-INVOICE 때문에
#   **정의상 최소 CONDITIONAL** 이므로(D78 부수 확정) `CLEAR` 는 SCRAP·TRANSFER 에서만 나온다.
#   같은 자산을 SALE 로 부르면 CONDITIONAL 이 정답이고, 그것도 아래서 함께 잠근다.
DISPOSAL_EXPECTATIONS: dict[str, dict] = {
    # 세액공제 사후관리 기간 내 + 무동의 담보 → BLOCKING 2종
    "AST-L3-CONV": {
        "mode": "SALE",
        "verdict": "BLOCKED",
        "n_blockers": 2,
        "n_insufficient": 0,
    },
    # months=23 이 경계(22~26) 안 → 단정하지 않는다 (D62)
    "AST-L4-WRAP": {
        "mode": "SALE",
        "verdict": "HOLD",
        "n_blockers": 0,
        "n_holds": 1,
        "n_insufficient": 0,
    },
    # BLOCKING 없음 · 사실 부족 없음 · PRECONDITION 만 → D77 수정 전에는 도달 불가였다
    "AST-L2-SPDL": {
        "mode": "SALE",
        "verdict": "CONDITIONAL",
        "n_blockers": 0,
        "n_insufficient": 0,
    },
    # tax_credit_applied 가 NULL → 사실 부족. **CLEAR 로 내려가면 안 된다** (D62).
    # D79 로 INSUFFICIENT_FACTS 가 최상위 verdict 로 승격됐다 — HOLD 와 해소 경로가 다르다
    # (HOLD=전문가 검토 / INSUFFICIENT_FACTS=데이터 입력). n_holds=0 으로 둘을 갈라 둔다
    "AST-L4-DUST": {
        "mode": "SALE",
        "verdict": "INSUFFICIENT_FACTS",
        "n_blockers": 0,
        "n_holds": 0,
        "n_insufficient": 1,
    },
    # 법정 조건 전부 무해당 + 확인된 미부보(insured=0, D78) + SCRAP → 유일한 CLEAR
    "AST-L3-LIFT": {
        "mode": "SCRAP",
        "verdict": "CLEAR",
        "n_blockers": 0,
        "n_holds": 0,
        "n_insufficient": 0,
        "n_preconditions": 0,
    },
}

# 같은 자산·같은 날짜인데 `disposal_mode` 만 다르면 판정이 갈린다는 **도메인 사실**을 잠근다.
# 이게 없으면 "LIFT 는 CLEAR"만 남아, 나중에 누가 VAT-INVOICE 를 잘못 손봐도 안 걸린다.
DISPOSAL_MODE_CONTRAST = ("AST-L3-LIFT", "SALE", "CONDITIONAL")

# ── repair_records 12건 (12 §9) ───────────────────────────────────────────
# `AST-L3-CONV` 에 몰지 않는다 — 4자산에 분산해야 MTTR·planned_ratio·누적수리비가
# 여러 자산에서 non-null 이 된다. **1건은 signed_at=NULL** (미서명은 지표에서 제외, 12 §11).
# (repair_id, equipment_id, code_key, part_class, work_type, expenditure_class,
#  cost, downtime_hours, parts, performed_by, verified_by, signed)
# code_key 는 --with-error-codes 일 때만 (model, error_code) 로 채워진다 (seed_po_drafts 선례).
REPAIR_RECORDS = [
    # AST-L3-CONV / INV-L3-01 — 서명 2 + 미서명 1
    (
        "RPR-2401",
        "INV-L3-01",
        None,
        "CONSUMABLE",
        "PLANNED",
        "REVENUE",
        4_500_000,
        3.5,
        ["FLT-AIR-01", "BLT-V-A50"],
        "tech-01",
        "mgr-01",
        True,
    ),
    (
        "RPR-2402",
        "INV-L3-01",
        ("iG5A", "OCT"),
        "CRITICAL",
        "UNPLANNED",
        "HOLD",
        9_500_000,
        6.0,
        ["IGBT-IG5-2K2"],
        "tech-02",
        "mgr-01",
        True,
    ),
    (
        "RPR-2403",
        "INV-L3-01",
        ("iG5A", "OHT"),
        "CRITICAL",
        "UNPLANNED",
        None,
        2_800_000,
        4.0,
        ["FAN-IG5-01"],
        "tech-01",
        None,
        False,
    ),  # ★ 미서명 1건
    # AST-L2-SPDL / INV-L2-01 — 누적수리비 / 취득원가 = 18,000,000 / 120,000,000 = 0.15
    (
        "RPR-2404",
        "INV-L2-01",
        None,
        "CRITICAL",
        "PLANNED",
        "CAPITAL",
        6_000_000,
        8.0,
        # FAN-S100-01 은 하이라이트 대상 부품(§4-5) — 90일 이내 서명 수리로 잡혀
        # 🔵 "최근 수리" 색이 최소 1건은 실제로 나오게 한다(그 전에는 도달 불가였다).
        ["BRG-6205", "CPL-JAW-01", "FAN-S100-01"],
        "tech-01",
        "mgr-01",
        True,
    ),
    (
        "RPR-2405",
        "INV-L2-01",
        None,
        "CONSUMABLE",
        "PLANNED",
        "REVENUE",
        7_500_000,
        5.5,
        ["THM-GEN-01", "FLT-AIR-01"],
        "tech-02",
        "mgr-01",
        True,
    ),
    (
        "RPR-2406",
        "INV-L2-01",
        ("S100", "OHT"),
        "CRITICAL",
        "UNPLANNED",
        "HOLD",
        4_500_000,
        7.0,
        ["FAN-S100-01"],
        "tech-01",
        "mgr-01",
        True,
    ),
    # AST-L4-DUST / INV-L4-03 — 9,000,000 / 45,000,000 = 0.20
    (
        "RPR-2407",
        "INV-L4-03",
        None,
        "CONSUMABLE",
        "PLANNED",
        "REVENUE",
        3_000_000,
        2.5,
        ["FLT-AIR-01"],
        "tech-02",
        "mgr-01",
        True,
    ),
    (
        "RPR-2408",
        "INV-L4-03",
        ("iG5A", "FAN"),
        "CRITICAL",
        "UNPLANNED",
        "HOLD",
        2_500_000,
        4.5,
        ["FAN-IG5-02"],
        "tech-01",
        "mgr-01",
        True,
    ),
    (
        "RPR-2409",
        "INV-L4-03",
        ("iG5A", "OLT"),
        "CRITICAL",
        "UNPLANNED",
        "CAPITAL",
        3_500_000,
        9.0,
        ["MTR-3P-2K2"],
        "tech-02",
        "mgr-01",
        True,
    ),
    # AST-L4-WRAP / INV-L4-02 — 12,000,000 / 60,000,000 = 0.20
    (
        "RPR-2410",
        "INV-L4-02",
        ("S100", "OCT"),
        "CRITICAL",
        "UNPLANNED",
        "HOLD",
        5_000_000,
        11.0,
        ["IGBT-S100-4K0"],
        "tech-01",
        "mgr-01",
        True,
    ),
    (
        "RPR-2411",
        "INV-L4-02",
        ("S100", "OVT"),
        "CRITICAL",
        "UNPLANNED",
        "CAPITAL",
        4_000_000,
        6.5,
        ["PCB-S100-CTRL-R2"],
        "tech-02",
        "mgr-01",
        True,
    ),
    (
        "RPR-2412",
        "INV-L4-02",
        None,
        "CONSUMABLE",
        "PLANNED",
        "REVENUE",
        3_000_000,
        3.0,
        ["BLT-V-A50", "MC-40A"],
        "tech-01",
        "mgr-01",
        True,
    ),
]

# MTBF 추세(D70)를 결정론적으로 만들기 위한 이력 형상.
# `get_maintenance_metrics` 는 최근 12개월 MTBF 와 직전 12개월 MTBF 를 비교하므로,
# 6개월치 잡음만으로는 양쪽 창이 채워지지 않아 전부 `insufficient_data` 가 된다.
# 아래 2대는 **잡음 생성에서 제외**하고 간격을 손으로 고정한다.
MTBF_SHAPED: dict[str, list[tuple[int, str]]] = {
    # AST-L2-SPDL — stable: 전 구간 90일 등간격 (최근 12M ≈ 직전 12M)
    "INV-L2-01": [
        (700, "OHT"),
        (610, "LVT"),
        (520, "OHT"),
        (430, "OVT"),
        (340, "OHT"),
        (250, "LVT"),
        (160, "OHT"),
        (70, "OVT"),
    ],
    # AST-L4-WRAP — declining: 직전 12M 은 140일 간격, 최근 12M 은 30~60일 간격
    "INV-L4-02": [
        (700, "OCT"),
        (560, "OVT"),
        (420, "OCT"),
        (300, "OVT"),
        (240, "OCT"),
        (185, "LVT"),
        (135, "OCT"),
        (90, "OVT"),
        (50, "OCT"),
        (20, "LVT"),
    ],
}

# 이력 생성에 쓰는 코드 (추출 결과에 실재하는 코드만 — 대문자 canonical, D25)
CODES_BY_MODEL = {
    "iG5A": ["OCT", "OHT", "OLT", "LVT", "GFT", "FAN"],
    "S100": ["OCT", "OHT", "LVT", "OVT", "FAN", "NTC"],
}

# 반복 고장 판정 기준 — `docs/04_MCP_TOOLS.md §3` 계약값이자
# `mcp_server/tools/get_error_history.py` 의 REPEAT_WINDOW_DAYS·REPEAT_THRESHOLD 와 같은 값.
# 시드가 mcp_server 를 import 하지 않으려고 상수만 복제한다 (data → mcp_server 의존 금지).
# 값이 갈라지면 검사 ⑤ 가 먼저 깨진다.
REPEAT_WINDOW_DAYS = 30
REPEAT_THRESHOLD = 3

# 고장 유형 분포 참고: AI허브 「기계시설물 고장 예지 센서」 4종 분포 (D16)
ACTIONS = ["리셋", "냉각팬 청소", "단자 재조임", "부품 교체", "파라미터 재설정", "배선 점검"]

PART_BY_ACTION = {
    "부품 교체": ["FAN-IG5-01", "FUSE-30A", "CAP-DC-450", "BRG-6205", "BLT-V-A50"],
}

# ── partner_links 시드 (D92·D95) ─────────────────────────────────────────
# ⚠ 시드 전제(목업)다 — 실제 연결 승인·발급값이 아니다. PARTNER_LINKS_MOCK 참조.
# ★ InsuQ building 행의 external_ref 는 **전부 NULL** — 증권 식별자의 정본은 assets.policy_id 다 (D95).
#   건물 3행에 증권번호를 복제하면 D91 이 기각한 형태(회사·건물 단위 사실의 복제)를
#   결(grain)만 바꿔 재발시키는 것이 된다. 확정안에서 복제는 **0건**이고 검사 ㉔ 가 그걸 본다.
# ★ BLD-D 가 대조군인 이유: 자산 3건이 **전부 부보(insured=1)** 돼 있는데도 미연결이다 —
#   "부보돼 있어도 A2A 연결 승인이 없으면 못 쏜다"가 한눈에 보인다. BLD-C 를 쓰면
#   미부보(AST-L3-LIFT)와 미연결이 한 건물에 겹쳐 **별개인 두 축이 섞인다**(D78·§A).
# (partner, subject_type, subject_ref, link_state, external_ref, linked_days_ago)
PARTNER_LINKS: list[tuple[str, str, str, str | None, str | None, int | None]] = [
    ("finallq", "company", "", "LINKED", "CMP-MAINTQ-001", 30),
    ("insuq", "building", "BLD-A", "LINKED", None, 30),
    ("insuq", "building", "BLD-B", "LINKED", None, 30),
    ("insuq", "building", "BLD-C", "LINKED", None, 30),
    ("insuq", "building", "BLD-D", "NOT_LINKED", None, None),  # ★ 대조군
]

# 실제 연결 승인·자격증명 발급 여부. 사람이 실값을 받으면 False 로 바꾼다 (TODO_직접할일.md).
PARTNER_LINKS_MOCK: bool = True


# ────────────────────────────────────────────────────────────── 적재


def create_schema(con: DbConnection) -> None:
    # 전역 dbcompat.USE_POSTGRES(=DATABASE_URL 설정 여부)가 아니라 **이 커넥션 자체의
    # 타입**으로 분기한다 — rules_db_load.py 같은 스파이크는 Postgres 타겟에서 실행 중일
    # 때도 `sqlite3.connect()` 로 직접 연 격리 fixture DB(loose/broken 스키마 등, 무결성
    # 게이트를 sqlite3 로 직접 흔든다)에 이 함수를 그대로 재사용한다 — 전역 플래그로
    # 분기하면 그 DbConnection 에 Postgres DDL 을 시도해 즉시 깨진다.
    # ⛔ 여기는 **런타임 isinstance 검사**다 — 타입 힌트가 아니다. `sqlite3.Connection`
    # 을 `DbConnection`(D129 타입 별칭)으로 바꾸면 안 된다: 그 별칭은 런타임에 `object`
    # 라 `isinstance(con, object)` 가 **항상 True** 가 되고, Postgres 타겟에서도 아래
    # `else` 의 SQLite SCHEMA 를 실행해 `NOT GLOB` 문법 오류로 죽는다(2026-09-04 실측).
    if not isinstance(con, sqlite3.Connection):
        # Postgres 타겟은 raw SCHEMA(SQLite 문법) 대신 convert_ddl.py 가 미리 변환해 둔
        # scripts/postgres_schema.sql + D10 가드(scripts/postgres_guards.sql)를 적용한다.
        con.executescript("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        scripts_dir = ROOT.parent / "scripts"
        con.executescript((scripts_dir / "postgres_schema.sql").read_text(encoding="utf-8"))
        con.executescript((scripts_dir / "postgres_guards.sql").read_text(encoding="utf-8"))
    else:
        con.executescript(SCHEMA)


def seed_users(con: DbConnection) -> None:
    """**가장 먼저** 적재한다 — po_drafts.requested_by/decided_by 와 error_history.recorded_by 가
    FK 로 이 테이블을 참조한다 (D41). `PRAGMA foreign_keys=ON` 상태라 순서가 틀리면 즉시 실패한다.
    """
    con.executemany(
        "INSERT INTO users (user_id, email, display_name, role, department, auth_provider)"
        " VALUES (?,?,?,?,?,?)",
        USERS,
    )


def seed_masters(con: DbConnection) -> None:
    """⚠ `seed_assets` 보다 **뒤에** 호출한다 — equipment.asset_id 가 assets 를 참조한다 (D68)."""
    missing = [p for p, *_ in PARTS if p not in PART_CLASS]
    if missing:
        # 부품 등급을 도구가 추측하면 3지 판단이 근거를 잃는다 (D12). 누락은 조용히 넘기지 않는다
        sys.exit(f"[중단] parts.part_class 미지정: {missing}")

    unknown = sorted(set(MFR_PART_NO) - {p for p, *_ in PARTS})
    if unknown:
        # 없는 부품에 실품번이 달려 있으면 조용히 버려진다 — 조사 결과가 사라지는 셈이다
        sys.exit(f"[중단] MFR_PART_NO 가 존재하지 않는 part_no 를 가리킨다: {unknown}")

    con.executemany("INSERT INTO suppliers VALUES (?,?,?,?,?)", SUPPLIERS)
    con.executemany(
        "INSERT INTO parts VALUES (?,?,?,?,?,?,?)",
        [
            (p, n, c, json.dumps(m, ensure_ascii=False), d, PART_CLASS[p], MFR_PART_NO.get(p))
            for p, n, c, m, d in PARTS
        ],
    )
    con.executemany("INSERT INTO equipment VALUES (?,?,?,?,?,?)", EQUIPMENT)
    con.executemany("INSERT INTO part_alternatives VALUES (?,?,?,?)", ALTERNATIVES)


# ───────────────────────────────────────── assets · 근거 계층 · 수리 증빙 (Sprint 6)


def _shift_months(d: date, months: int) -> str:
    """달력 개월 이동. `date` 에 개월 연산이 없어 직접 구현한다 (dateutil 미의존)."""
    total = (d.year * 12 + (d.month - 1)) + months
    year, month = divmod(total, 12)
    month += 1
    # 말일 보정 — 1/31 + 1개월 = 2/28
    day = min(
        d.day,
        [
            31,
            29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28,
            31,
            30,
            31,
            30,
            31,
            31,
            30,
            31,
            30,
            31,
        ][month - 1],
    )
    return date(year, month, day).isoformat()


# 장부가 목업 — 정액법 12년·잔존율 5%. **회계 실적이 아니라 데모용 자리표시자다.**
# 잔가곡선(residual_curve)은 시장가 축이고 이건 장부가 축이라 산식이 다르다. 섞지 말 것.
BOOK_VALUE_LIFE_YEARS = 12
BOOK_VALUE_FLOOR_RATIO = 0.05


def seed_assets(con: DbConnection, today: date) -> dict[str, str]:
    """assets 9건. `equipment` 보다 **먼저** 적재한다 (FK).

    반환: asset_id → acquired_at (검증·출력용)
    """
    repair_by_asset: dict[str, int] = {}
    eq_asset = {eq: a for eq, _l, _m, _i, _loc, a in EQUIPMENT}
    for rec in REPAIR_RECORDS:
        repair_id, equipment_id, _code, _pc, _wt, _ec, cost, *_rest = rec
        signed = rec[-1]
        asset_id = eq_asset[equipment_id]
        if signed and asset_id:
            # 미서명 레코드는 지표에서 제외되므로 누적수리비에도 넣지 않는다 (12 §11)
            repair_by_asset[asset_id] = repair_by_asset.get(asset_id, 0) + cost

    rows, acquired = [], {}
    for a in ASSETS:
        month, day = a["acq_md"]
        acq = date(today.year - a["age_years"], month, day).isoformat()
        acquired[a["asset_id"]] = acq

        cost = a["acquisition_cost"]
        if cost is None:
            book = None  # 취득원가를 모르면 장부가도 모른다. 0 으로 채우지 않는다 (D62)
        else:
            ratio = max(BOOK_VALUE_FLOOR_RATIO, 1 - a["age_years"] / BOOK_VALUE_LIFE_YEARS)
            book = round(cost * ratio)

        # 담보가 없으면 채권자·동의서는 "해당 없음"(빈 문자열)이다. NULL 로 두면 룰 엔진이
        # "모른다"로 읽어 INSUFFICIENT_FACTS 가 된다 — 없음과 모름은 다르다 (D62)
        #
        # ★ 안전검사 이력은 **대상 기계에만** 채운다. 비대상은 검사 자체가 없으므로 NULL 이
        #   정답이다 (D62·D65). 한때 전 자산에 채워 뒀는데, 그건
        #   `SAFETY-INSPECTION.required_facts` 가 트리거가 읽지도 않는 2개 필드를 요구해
        #   비대상까지 INSUFFICIENT_FACTS 가 되는 것을 **데이터로 덮으려던 것**이었다.
        #   "9개월 전 검사 완료, 15개월 후까지 유효"는 없는 법정 사실을 지어낸 것이고,
        #   그 결과 ⑮(룰 카탈로그가 5종 판정을 실제로 내는가)가 거짓 통과한다.
        #   룰의 required_facts 결함은 **D77 로 Stage 3(MQ-601b)에서 고친다** — 시드가 아니라.
        if a["safety_inspection_target"]:
            last_insp, insp_until = _shift_months(today, -9), _shift_months(today, 15)
        else:
            last_insp = insp_until = None

        rows.append(
            (
                a["asset_id"],
                a["name"],
                a["category"],
                a["line_id"],
                a["building_id"],
                acq,
                cost,
                book,
                a["status"],
                a["tax_credit_applied"],
                a["has_lien"],
                a.get("lien_creditor", ""),
                a.get("lien_consent_ref", ""),
                a["insured"],
                a["policy_id"],
                a["safety_inspection_target"],
                last_insp,
                insp_until,
                repair_by_asset.get(a["asset_id"], 0),
                None
                if a["overhaul_years_ago"] is None
                else _shift_months(today, -12 * a["overhaul_years_ago"]),
                a["controller_generation"],
                a["parts_eol_flag"],
            )
        )
    con.executemany(
        "INSERT INTO assets (asset_id, name, category, line_id, building_id, acquired_at,"
        " acquisition_cost, book_value, status, tax_credit_applied, has_lien, lien_creditor,"
        " lien_consent_ref, insured, policy_id, safety_inspection_target, last_inspection_date,"
        " inspection_valid_until, cumulative_repair_cost, last_overhaul_at,"
        " controller_generation, parts_eol_flag)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    return acquired


def seed_partner_links(con: DbConnection, now_utc: datetime) -> int:
    """partner_links 5행 (D92 A안). `seed_assets` **직후** 호출한다.

    FK 는 없지만 `subject_ref` 가 `assets.building_id` 를 참조하는 결(grain)이라
    자산이 먼저 들어간 뒤가 읽기 쉽다. 검사 ㉒-ⓒ 가 그 대응을 동적으로 대조한다.

    ⚠ 시그니처가 `today: date` 가 아니라 `now_utc: datetime` 인 이유 (D96-ⓓ):
      `linked_at` 은 날짜가 아니라 **시각**이다. 그리고 기준을 `--today` 가 아니라
      **실제 UTC 현재 시각**으로 잡는다 — `--today` 로 미래 날짜를 핀하면 `linked_at` 이
      "지금보다 미래"가 되어 검사 ㉒-ⓓ 가 위양성 FAIL 한다. 이 값은 재현 대상(이력 분포)이
      아니라 **감사 시점**이므로 벽시계를 따르는 것이 맞다.

    ⛔ 로컬 시각 금지 — 저장은 UTC (D39). `traces.ts`(CURRENT_TIMESTAMP) 와 같은 모양의
      `'YYYY-MM-DD HH:MM:SS'` 문자열이고 타임존 접미사를 붙이지 않는다. 시드가 로컬,
      검증이 UTC 를 보면 자정 근처에서 조용히 갈린다 (CLAUDE.md 의 `--today` 함정과 같은 계열).
    """
    base = now_utc.astimezone(timezone.utc).replace(tzinfo=None)
    rows = [
        (
            partner,
            subject_type,
            subject_ref,
            link_state,
            external_ref,
            None
            if days_ago is None
            else (base - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S"),
        )
        for partner, subject_type, subject_ref, link_state, external_ref, days_ago in PARTNER_LINKS
    ]
    con.executemany(
        "INSERT INTO partner_links (partner, subject_type, subject_ref, link_state,"
        " external_ref, linked_at) VALUES (?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


# ───────────────────────────────────────── §20~§23 확장 (Sprint 11, MQ-1101, `11 §10-2`)

# §21 incidents 2행. `seed_assets` 이후 호출한다(FK). `months_ago` 는 `--today` 기준 상대값 —
# 반복 고장·처분 프로브와 같은 이유로 절대 날짜를 박지 않는다.
INCIDENTS: list[dict] = [
    {
        "asset_id": "AST-L2-SPDL",
        "type": "COLLISION",
        "months_ago": 24,  # 약 2년 전
        # 사고 시점 장부가 추정치 — seed_assets 와 같은 정액법 산식(BOOK_VALUE_LIFE_YEARS·
        # BOOK_VALUE_FLOOR_RATIO)을 사고 시점 연차(age_years=16 - 2년=14)에 적용한 값.
        # ratio = max(0.05, 1-14/12) = 0.05 → 120,000,000 * 0.05 = 6,000,000.
        "book_value_at_loss": 6_000_000,
        "description": "지게차 충돌 — 주축 정렬 손상 의심",
    },
    {
        "asset_id": "AST-L4-WRAP",
        "type": "OTHER",
        "months_ago": 8,
        # 장부가 추정 불가 시점 — "모른다"를 0 으로 채우지 않는다 (D62)
        "book_value_at_loss": None,
        "description": "설비 프레임 변형 발견 — 충돌·화재·침수 4종 어디에도 해당하지 않아 OTHER 로 기록. 원인 미상",
    },
]


def seed_incidents(con: DbConnection, today: date) -> int:
    """§21 incidents 적재. MCP 쓰기 도구는 이 테이블에 쓰지 않는다(D10) — 시드만이 채운다."""
    rows = [
        (
            i["asset_id"],
            i["type"],
            f"{_shift_months(today, -i['months_ago'])} 09:00:00",
            i["book_value_at_loss"],
            i["description"],
        )
        for i in INCIDENTS
    ]
    con.executemany(
        "INSERT INTO incidents (asset_id, type, occurred_at, book_value_at_loss, description)"
        " VALUES (?,?,?,?,?)",
        rows,
    )
    return len(rows)


# §22 ownership_checks — `verify_ownership(con, asset_id='AST-L3-LIFT')`(`data/ownership.py`)의
# **실제 출력**을 그대로 옮겨 심는다 (추측 금지 — 태스크 지시). 9카테고리·38항목.
# (category, check_item, state, evidence_ref, limit_note)
OWNERSHIP_CHECKS_LIFT: list[tuple[str, str, str, str | None, str | None]] = [
    ('물리적 상태', '정밀도 검사', 'UNVERIFIED', None, '현장 실사 원천 없음 — 육안·계측 결과를 담는 테이블이 저장소에 없다'),
    ('물리적 상태', '진동·소음 측정', 'UNVERIFIED', None, '현장 실사 원천 없음 — 육안·계측 결과를 담는 테이블이 저장소에 없다'),
    ('물리적 상태', '누유 점검', 'UNVERIFIED', None, '현장 실사 원천 없음 — 육안·계측 결과를 담는 테이블이 저장소에 없다'),
    ('물리적 상태', '전장부 상태', 'UNVERIFIED', None, '현장 실사 원천 없음 — 육안·계측 결과를 담는 테이블이 저장소에 없다'),
    ('물리적 상태', '베드·가이드 마모', 'UNVERIFIED', None, '현장 실사 원천 없음 — 육안·계측 결과를 담는 테이블이 저장소에 없다'),
    ('가동 이력', '누적 가동시간', 'UNVERIFIED', None, '가동시간 원천 없음 — 컨트롤러 로그·가동시간 컬럼이 저장소에 없다 (D70)'),
    ('가동 이력', '스핀들 시간', 'UNVERIFIED', None, '가동시간 원천 없음 — 컨트롤러 로그·가동시간 컬럼이 저장소에 없다 (D70)'),
    ('가동 이력', '알람 이력', 'UNVERIFIED', None, "error_history 는 인버터 에러코드 이력이며 자산 전체의 알람 이력이 아니다 — '반복 고장 패턴' 항목에서만 인버터 단위로 사용한다 (D68 ⓑ)"),
    ('가동 이력', '교대 패턴', 'UNVERIFIED', None, '생산 운영 원천 없음 — 교대·가공 실적을 담는 테이블이 없다'),
    ('가동 이력', '가공 소재', 'UNVERIFIED', None, '생산 운영 원천 없음 — 교대·가공 실적을 담는 테이블이 없다'),
    ('정비 이력', '정기점검 기록', 'UNVERIFIED', None, "서명된 정기점검 레코드 0건 — 점검을 안 한 것인지 기록이 없는 것인지 구분할 수 없다 (빈 이력은 '문제 없음'이 아니다)"),
    ('정비 이력', '핵심부품 교체', 'UNVERIFIED', None, '서명된 핵심부품 교체 레코드 0건 — 교체 이력 없음으로 읽을 수 없다'),
    ('정비 이력', '오버홀', 'UNVERIFIED', None, 'assets.last_overhaul_at 이 비어 있다 — 오버홀 미실시인지 기록 누락인지 구분할 수 없다'),
    ('정비 이력', '반복 고장 패턴', 'VERIFIED', '반복 고장 미감지 — 30일 내 2건 (인버터별 최대 2회 < 3회)', None),
    ('기술적 진부화', '제어기 세대', 'VERIFIED', 'S100/2022 (assets.controller_generation)', None),
    ('기술적 진부화', '부품 단종', 'VERIFIED', '호환 부품 28종 중 단종 1종 (PCB-S100-CTRL) · assets.parts_eol_flag=0', None),
    ('기술적 진부화', '통신 규격', 'UNVERIFIED', None, '통신 옵션·프로토콜을 기록하는 컬럼이 없다'),
    ('기술적 진부화', '제조사 존속', 'UNVERIFIED', None, '사전 수집 스냅샷 없음 — 외부 기관을 런타임에 조회하지 않는다 (.env.example §외부 데이터 원천)'),
    ('권리관계', '담보 설정 (사내 기록)', 'VERIFIED', '사내 기록상 담보 설정 없음 (assets.has_lien=0)', None),
    ('권리관계', '부보 여부', 'VERIFIED', '확인된 미부보 (assets.insured=0) — 사실은 확인됐으나 무보험 위험은 그대로 남는다', None),
    ('권리관계', '소유자 실재·처분 권한', 'UNVERIFIED', None, '사전 수집 스냅샷 없음 — 외부 기관을 런타임에 조회하지 않는다 (.env.example §외부 데이터 원천)'),
    ('권리관계', '동산담보등기 조회', 'UNVERIFIED', None, '개별 물건 조회 수단이 없다 — 등기정보광장은 집계 통계만 제공'),
    ('권리관계', '리스 여부', 'UNVERIFIED', None, '원천 없음 — 리스는 동산담보등기 대상이 아니고 저장소에 리스 계약 원천이 없다 (점유가 곧 권리 외관이라 육안으로도 구분되지 않는다)'),
    ('권리관계', '압류·가압류', 'UNVERIFIED', None, '원천 없음 — 집행 기록을 담는 테이블이 없다'),
    ('법정 요건', '안전검사', 'VERIFIED', '안전검사 비대상으로 기록됨 (safety_inspection_target=0)', None),
    ('법정 요건', '안전인증', 'UNVERIFIED', None, '인증서 원천 없음 — 인증번호를 기록하는 컬럼이 없다'),
    ('법정 요건', '환경 규제 대상 여부', 'UNVERIFIED', None, '환경 인허가 원천 없음'),
    ('재무·회계', '감가상각 명세', 'UNVERIFIED', None, 'acquisition_cost · book_value 이 NULL — 장부가를 산출할 수 없다'),
    ('재무·회계', '매도인 세액공제', 'VERIFIED', '세액공제 미적용 (assets.tax_credit_applied)', None),
    ('재무·회계', '내용연수 결정', 'UNVERIFIED', None, '내용연수 결정 근거 원천 없음 — 잔가곡선의 기준내용연수는 목업 파라미터이지 이 자산의 내용연수 결정이 아니다 (D65·D74)'),
    ('시장·가격', '동일 기종 거래가', 'UNVERIFIED', None, "실거래 비교가 아님 — 참고 잔가율 0.7579 (카테고리 '일반산업' · 연차 3-5) 는 법정 기준내용연수 10년 기반 정률법 추정 (목업) — 실거래 데이터 아님 [r=0.0670, floor=0.1, D74]"),
    ('시장·가격', '감정평가서', 'UNVERIFIED', None, '감정평가서 원천 없음'),
    ('시장·가격', '매도 사유', 'UNVERIFIED', None, '매도인 진술 원천 없음'),
    ('이전 비용', '해체·상차', 'UNVERIFIED', None, '이전 견적 원천 없음 — 해체·운송·설치 비용은 현장 조사 후 견적으로만 산출된다'),
    ('이전 비용', '운송', 'UNVERIFIED', None, '이전 견적 원천 없음 — 해체·운송·설치 비용은 현장 조사 후 견적으로만 산출된다'),
    ('이전 비용', '반입 경로', 'UNVERIFIED', None, '이전 견적 원천 없음 — 해체·운송·설치 비용은 현장 조사 후 견적으로만 산출된다'),
    ('이전 비용', '설치·정렬', 'UNVERIFIED', None, '이전 견적 원천 없음 — 해체·운송·설치 비용은 현장 조사 후 견적으로만 산출된다'),
    ('이전 비용', '시운전', 'UNVERIFIED', None, '이전 견적 원천 없음 — 해체·운송·설치 비용은 현장 조사 후 견적으로만 산출된다'),
]


def seed_ownership_checks(con: DbConnection, today: date) -> int:
    """§22 ownership_checks — `AST-L3-LIFT` 실사 스냅샷 38행. `checked_at` ≈ 1개월 전.

    verify_ownership 은 읽기 전용이라(D10) 이 테이블에 쓰지 않는다 — 채우는 건 시드뿐이다.
    """
    checked_at = f"{_shift_months(today, -1)} 10:00:00"
    rows = [
        ("AST-L3-LIFT", category, item, state, evidence, limit, checked_at)
        for category, item, state, evidence, limit in OWNERSHIP_CHECKS_LIFT
    ]
    con.executemany(
        "INSERT INTO ownership_checks (asset_id, category, check_item, state, evidence_ref,"
        " limit_note, checked_at) VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


# §23 risk_profile 4행. `stored_grade` 는 **마지막으로 저장된 등급**이고 BLD-C 는 의도적으로
# 재계산 등급(HIGH)과 다르게 둔다(LOW) — "저장된 값이 최신 산출과 어긋날 수 있다"는 데모 케이스.
# LOW=1/MEDIUM=2/HIGH=3 합산 점수는 `_risk_grade_from_score()` 참고(self-check 전용, 아래).
RISK_PROFILE: list[dict] = [
    {
        "building_id": "BLD-A",
        "fire_handling": "LOW", "hazmat_volume": "LOW", "power_capacity": "MEDIUM",
        "product_type": "일반 조립품 (경공정)",
        "stored_grade": "LOW", "months_ago": 3,
    },
    {
        "building_id": "BLD-B",
        "fire_handling": "MEDIUM", "hazmat_volume": "LOW", "power_capacity": "HIGH",
        "product_type": "정밀 가공품 (고전력 설비)",
        "stored_grade": "MEDIUM", "months_ago": 3,
    },
    {
        "building_id": "BLD-C",
        "fire_handling": "HIGH", "hazmat_volume": "MEDIUM", "power_capacity": "MEDIUM",
        "product_type": "도장·코팅 공정품 (인화성 도료 취급)",
        "stored_grade": "LOW",  # ★ 의도적 불일치 — 재계산 등급은 HIGH (검사 ㉟ 이 대조)
        "months_ago": 14,
    },
    {
        "building_id": "BLD-D",
        "fire_handling": "LOW", "hazmat_volume": "HIGH", "power_capacity": "LOW",
        "product_type": "화학 자재 보관 (포장동)",
        "stored_grade": "MEDIUM", "months_ago": 3,
    },
]

# self-check 전용 점수식 — **정본이 아니다.** 실 산정 로직은 Sprint 11 Stage 2(MQ-1103)의
# `data/risk_grade.py` 가 만든다. 여기서는 시드 표(sprint-11.md §6)의 "산출 등급" 열을 검사 ㉟
# 에서 재현하기 위한 최소 역산일 뿐이다.
_RISK_LEVEL_SCORE = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


def _risk_grade_from_score(score: int) -> str:
    if score <= 4:
        return "LOW"
    if score <= 6:
        return "MEDIUM"
    return "HIGH"


def seed_risk_profile(con: DbConnection, today: date) -> int:
    """§23 risk_profile 4행. `building_id` 는 `assets.building_id` 재사용 — FK 없음(참조 테이블 없음)."""
    rows = [
        (
            r["building_id"],
            r["fire_handling"],
            r["hazmat_volume"],
            r["power_capacity"],
            r["product_type"],
            r["stored_grade"],
            f"{_shift_months(today, -r['months_ago'])} 00:00:00",
        )
        for r in RISK_PROFILE
    ]
    con.executemany(
        "INSERT INTO risk_profile (building_id, fire_handling, hazmat_volume, power_capacity,"
        " product_type, risk_grade, risk_grade_updated_at) VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


def seed_repair_records(con: DbConnection, with_codes: bool, today: date) -> None:
    """수리 증빙 12건. 쓰기 경로는 Sprint 9 (MQ-909) 이고 여기서는 시드만 넣는다.

    `--with-error-codes` 없이 실행하면 `error_codes` 가 0행이라 `(model, error_code)`
    복합 FK 를 만족시킬 수 없다 → 둘 다 NULL (`seed_po_drafts` 선례 그대로).
    DDL 의 `CHECK ((model IS NULL) = (error_code IS NULL))` 이 짝을 강제한다.

    `record_hash` 는 **`state='signed'` 11행만** 채운다 — 새 DDL CHECK ②가
    `state='signed'` 에 `signed_at`·`record_hash`·`verified_by` 전부 non-null 을 강제하므로,
    채우지 않으면 시드가 즉시 죽는다(그게 정상 동작이다). 해시는 `data/repair_hash.py`
    (단일 출처, D73) 로 계산 — `backend/services/repairs.py`(MQ-909)의 서명 API 가
    같은 모듈을 읽으므로 규약이 갈릴 수 없다.

    `created_at`·`requested_by`·`session_id`·`note` (D98 신설 4컬럼): 도구/시드가 아니라
    백엔드가 X-User·세션에서 stamp 하는 게 원칙(D23·D37)이지만, 시드는 사람 대신 데이터를
    박아 넣는 예외적 자리라 `requested_by='tech-01'` 을 직접 채운다. `session_id`·`note` 는
    시드 시점엔 의미 있는 값이 없어 `NULL` (D62 — 모름이 아니라 "해당 없음"에 더 가깝다).
    """
    sys.path.insert(0, str(ROOT.parent))
    from data.repair_hash import compute_record_hash  # noqa: PLC0415

    rows = []
    for i, rec in enumerate(REPAIR_RECORDS):
        (
            repair_id,
            equipment_id,
            code_key,
            part_class,
            work_type,
            expenditure_class,
            cost,
            downtime,
            parts,
            performed_by,
            verified_by,
            signed,
        ) = rec
        model, error_code = code_key if (with_codes and code_key) else (None, None)
        parts_json = json.dumps(parts, ensure_ascii=False)
        # 서명 시각은 실행일 기준 상대값 (UTC, D39)
        signed_at = (
            datetime.combine(today - timedelta(days=20 + i * 17), datetime.min.time())
            .replace(tzinfo=timezone.utc)
            .strftime("%Y-%m-%d %H:%M:%S")
            if signed
            else None
        )
        # 요청 시각은 서명보다 앞서야 하므로 서명 오프셋보다 더 과거 (실행일 기준 상대값)
        created_at = (
            datetime.combine(today - timedelta(days=27 + i * 17), datetime.min.time())
            .replace(tzinfo=timezone.utc)
            .strftime("%Y-%m-%d %H:%M:%S")
        )
        record_hash = (
            compute_record_hash(
                {
                    "repair_id": repair_id,
                    "equipment_id": equipment_id,
                    "model": model,
                    "error_code": error_code,
                    "part_class": part_class,
                    "work_type": work_type,
                    "expenditure_class": expenditure_class,
                    "cost": cost,
                    "downtime_hours": downtime,
                    "parts": parts_json,
                    "performed_by": performed_by,
                    "verified_by": verified_by,
                    "signed_at": signed_at,
                }
            )
            if signed
            else None
        )
        rows.append(
            (
                repair_id,
                equipment_id,
                model,
                error_code,
                part_class,
                work_type,
                expenditure_class,
                cost,
                downtime,
                parts_json,
                performed_by,
                verified_by,
                signed_at,
                record_hash,
                "signed" if signed else "draft",
                created_at,
                "tech-01",
                None,
                None,
            )
        )
    con.executemany(
        "INSERT INTO repair_records (repair_id, equipment_id, model, error_code, part_class,"
        " work_type, expenditure_class, cost, downtime_hours, parts, performed_by, verified_by,"
        " signed_at, record_hash, state, created_at, requested_by, session_id, note)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )


def seed_rule_catalog(con: DbConnection) -> tuple[int, int]:
    """근거 계층 1·2 를 DB **사본**으로 적재한다. 정본은 파일이다 (D60).

    ★ 반드시 `engine.load_laws()` → `engine.load_rules(laws)` 를 경유한다.
      `load_rules` 가 D61 무결성 게이트(근거 없는 룰 거부 · 미등록 법령 참조 거부)이고,
      파일을 직접 파싱해 INSERT 하면 **근거 없는 룰이 DB 로 들어가는 우회로**가 생긴다.
      `RuleIntegrityError` 는 잡지 않는다 — 호출부가 시드 전체를 중단시킨다.
    """
    sys.path.insert(0, str(ROOT.parent))
    from data.rules import engine  # noqa: PLC0415

    laws = engine.load_laws()
    rules = engine.load_rules(laws)  # ← 여기서 무결성 검사가 돈다

    con.executemany(
        "INSERT INTO law_refs (law_ref_id, law_name, article, title, text, fetch_status,"
        " effective_from, effective_to, source_url, text_hash, verification_note)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                lw.law_ref_id,
                lw.law_name,
                lw.article,
                lw.title,
                lw.text,
                lw.fetch_status,
                lw.effective_from,
                lw.effective_to,
                lw.source_url,
                lw.text_hash,
                lw.verification_note,
            )
            for lw in laws.values()
        ],
    )
    j = lambda v: json.dumps(v, ensure_ascii=False)  # noqa: E731
    con.executemany(
        "INSERT INTO rules (rule_id, rule_version, label, category, disposal_type, source_type,"
        " law_refs, contract_refs, interpretation, required_facts, trigger, boundary, message,"
        " resolve_options, confidence, requires_expert_review)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                r.rule_id,
                r.rule_version,
                r.label,
                r.category,
                r.disposal_type,
                r.source_type,
                j(r.law_refs),
                j(r.contract_refs),
                r.interpretation,
                j(r.required_facts),
                j(r.trigger),
                None if r.boundary is None else j(r.boundary),
                r.message,
                j(r.resolve_options),
                r.confidence,
                int(r.requires_expert_review),
            )
            for r in rules.values()
        ],
    )
    return len(laws), len(rules)


def seed_residual_curve(con: DbConnection) -> tuple[int, str]:
    """잔가곡선 적재. 정본은 `data/extracted/residual_curve.json` (D60·D74).

    파일이 없으면 0행 + 경고이고 **시드는 성공한다** — 곡선이 없으면 소비 측 도구가
    `HOLD` 를 내는 게 정답이지, 시드가 죽어서 DB 자체가 없어지는 건 과잉이다.
    """
    if not RESIDUAL_CURVE_JSON.exists():
        return 0, f"{RESIDUAL_CURVE_JSON.name} 없음 — assess_repair_value 는 전 자산 HOLD 가 된다"
    doc = json.loads(RESIDUAL_CURVE_JSON.read_text(encoding="utf-8"))
    rows = [
        (
            r["category"],
            r["age_bucket"],
            r["residual_ratio"],
            r["n_samples"],
            r["p25_ratio"],
            r["p75_ratio"],
            r["base_n"],
            r["source"],
        )
        for r in doc["rows"]
    ]
    con.executemany("INSERT INTO residual_curve VALUES (?,?,?,?,?,?,?,?)", rows)
    return len(rows), doc.get("_status", "")


def seed_inventory(con: DbConnection, rng: random.Random) -> None:
    rows = []
    zones = ["자재창고 A", "자재창고 B", "자재창고 C"]
    for i, (part_no, *_rest) in enumerate(PARTS):
        if part_no in INVENTORY_FIXED:
            qty, safety, loc = INVENTORY_FIXED[part_no]
        else:
            safety = rng.choice([1, 2, 2, 3, 5])
            # 대부분 안전재고 이상 — 미달 케이스가 눈에 띄어야 한다
            qty = safety + rng.choice([0, 1, 2, 3, 5, 8])
            loc = f"{zones[i % 3]}-{(i % 20) + 1:02d}"
        rows.append((part_no, qty, safety, loc))
    con.executemany("INSERT INTO inventory VALUES (?,?,?,?)", rows)


def seed_supplier_parts(con: DbConnection, rng: random.Random) -> None:
    rows = list(SUPPLIER_PARTS_FIXED)
    # 케이스 맵이 고정한 부품은 랜덤 견적을 붙이지 않는다 —
    # 냉각팬은 "A사 3일/비쌈 vs B사 14일/쌈(MOQ 10)" 2건 비교가 정확히 보여야 한다
    fixed_parts = {p for _s, p, *_ in SUPPLIER_PARTS_FIXED}
    for part_no, *_rest in PARTS:
        if part_no in fixed_parts:
            continue
        # 부품마다 공급사 1~3곳
        for sup in rng.sample([s[0] for s in SUPPLIERS], rng.choice([1, 2, 2, 3])):
            base = rng.choice([9000, 18000, 27000, 45000, 88000, 130000])
            rows.append(
                (
                    sup,
                    part_no,
                    rng.choice([2, 3, 5, 7, 10, 14, 21]),
                    int(base * rng.choice([0.92, 1.0, 1.08])),
                    rng.choice([1, 1, 1, 5, 10]),
                )
            )
    con.executemany("INSERT INTO supplier_parts VALUES (?,?,?,?,?)", rows)


def seed_error_history(con: DbConnection, rng: random.Random, today: date) -> None:
    """6개월치 이력 ~200건. 대부분 단발, INV-L3-01의 OCT만 30일 내 3건 (S3 트리거).

    시각은 **UTC** 로 저장한다 — SQLite 의 datetime('now') 비교가 UTC 기준이라
    로컬 시각을 섞으면 한 DB 안에 두 개의 시간 기준이 생긴다 (D39).
    """
    rows: list[tuple] = []
    recent30: dict[str, int] = {}  # equipment_id → 최근 30일 이벤트 수

    # ── S3 케이스: 실행일 기준 상대 날짜 (하드코딩 금지)
    #    today=2026-07-23 이면 07-01 / 07-11 / 07-19 — 문서·UI의 예시와 일치
    for days_ago in (22, 12, 4):
        occurred = datetime.combine(today - timedelta(days=days_ago), datetime.min.time())
        occurred += timedelta(hours=rng.randint(8, 18), minutes=rng.randint(0, 59))
        rows.append(("INV-L3-01", "OCT", occurred.isoformat(sep=" "), "리셋", None, 1))
    recent30["INV-L3-01"] = 3

    # ── MTBF 추세 형상 (D70). 24개월 창을 채워야 `mtbf_trend` 가 산출된다
    for eq_id, events in MTBF_SHAPED.items():
        for days_ago, code in events:
            occurred = datetime.combine(today - timedelta(days=days_ago), datetime.min.time())
            occurred += timedelta(hours=rng.randint(6, 20), minutes=rng.randint(0, 59))
            action = rng.choice(ACTIONS)
            part = rng.choice(PART_BY_ACTION[action]) if action in PART_BY_ACTION else None
            rows.append((eq_id, code, occurred.isoformat(sep=" "), action, part, 1))
            if days_ago <= REPEAT_WINDOW_DAYS:
                recent30[eq_id] = recent30.get(eq_id, 0) + 1

    # ── 나머지: 6개월치 잡음. S3 케이스를 오염시키지 않도록 제약을 건다
    noise_pool = [e for e in EQUIPMENT if e[0] not in MTBF_SHAPED]
    target = 200
    while len(rows) < target:
        eq_id, _line, model, *_ = rng.choice(noise_pool)
        code = rng.choice(CODES_BY_MODEL[model])
        days_ago = rng.randint(4, 180)
        # INV-L3-01 + OCT 조합은 최근 30일 안에 추가로 만들지 않는다 (count 정확히 3)
        if eq_id == "INV-L3-01" and code == "OCT" and days_ago <= REPEAT_WINDOW_DAYS:
            continue
        # 반복 고장(30일 3회)은 **INV-L3-01 전용**이다. 다른 설비에서 잡음이 우연히
        # 3회를 채우면 `repeat_failure` 가 켜져 assess_repair_value 가 전부
        # ROOT_CAUSE_FIRST 로 수렴한다 — 3지 판단 데모가 통째로 사라진다
        if days_ago <= REPEAT_WINDOW_DAYS:
            if eq_id != "INV-L3-01" and recent30.get(eq_id, 0) >= REPEAT_THRESHOLD - 1:
                continue
            recent30[eq_id] = recent30.get(eq_id, 0) + 1
        occurred = datetime.combine(today - timedelta(days=days_ago), datetime.min.time())
        occurred += timedelta(hours=rng.randint(6, 20), minutes=rng.randint(0, 59))
        action = rng.choice(ACTIONS)
        part = rng.choice(PART_BY_ACTION[action]) if action in PART_BY_ACTION else None
        rows.append((eq_id, code, occurred.isoformat(sep=" "), action, part, 1))

    rows.sort(key=lambda r: r[2])
    con.executemany(
        "INSERT INTO error_history (equipment_id, code, occurred_at, action_taken,"
        " part_replaced, resolved) VALUES (?,?,?,?,?,?)",
        rows,
    )


def seed_po_drafts(con: DbConnection, with_codes: bool) -> None:
    """화면 B 승인 큐용.

    에러코드 FK는 error_codes 적재 여부에 따라 채운다 (D33).
    requested_by/decided_by 는 표시명이 아니라 ASCII 사용자 ID (D36).
    """
    evidence_0117 = {
        "symptoms": ["냉각팬 소음 증가", "3번 라인 2회 정지"],
        "basis": [
            {"tool": "lookup_error_code", "code": "OHT", "manual_page": 202},
            {"tool": "search_inventory", "part_no": "FAN-IG5-01", "qty": 1, "safety_stock": 3},
        ],
        "notes": "야간조 정비사 육안 확인 — 팬 회전 불량",
    }
    # (po_id, part_no, qty, supplier_id, model, code, evidence, unit_price,
    #  reason, urgency, state, requested_by, decided_by, decision_note, session_id,
    #  decided_at, finance_decided_by, finance_decision_note, finance_decided_at)
    rows = [
        (
            "PO-0117",
            "FAN-IG5-01",
            2,
            "SUP-A",
            "iG5A",
            "OHT",
            json.dumps(evidence_0117, ensure_ascii=False),
            38000,
            "iG5A OHt 과열 진단, 냉각팬 고장 유력 (매뉴얼 p.202). 재고 1/안전재고 3 미달",
            "urgent",
            "pending",
            "tech-01",
            None,
            None,
            "S1",
            None,
            None,
            None,
            None,
        ),
        (
            "PO-0116",
            "PCB-S100-CTRL-R2",
            1,
            "SUP-A",
            None,
            None,
            None,
            264000,
            "S100 제어보드 단종 — 호환 확정 후속 리비전(R2)으로 대체 발주",
            "normal",
            "pending",
            "tech-02",
            None,
            None,
            "S2",
            None,
            None,
            None,
            None,
        ),
        (
            "PO-0115",
            "FUSE-30A",
            10,
            "SUP-C",
            None,
            None,
            None,
            9000,
            "2번 라인 정기 교체분 — 소모품 보충",
            "normal",
            "pending",
            "tech-01",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
        (
            "PO-0114",
            "BLT-V-A50",
            1,
            "SUP-D",
            None,
            None,
            None,
            18000,
            "4번 포장라인 V벨트 마모 — 육안 점검에서 균열 확인",
            "normal",
            "approved",
            "tech-01",
            "mgr-01",
            "긴급 라인 정지 예방 — 승인",
            None,
            "2026-08-05 03:20:00",
            None,
            None,
            None,
        ),
        (
            "PO-0113",
            "IGBT-S100-4K0",
            1,
            "SUP-B",
            None,
            None,
            None,
            130000,
            "예비 인버터 확보 요청",
            "normal",
            "rejected",
            "tech-02",
            "mgr-01",
            "예산 초과 — 차기 분기 재검토",
            None,
            "2026-08-04 07:10:00",
            None,
            None,
            None,
        ),
        (
            "PO-0118",
            "FAN-IG5-01",
            2,
            "SUP-A",
            "iG5A",
            "OHT",
            None,
            15000,
            "냉각팬 예비분 확보 — 저액 소모품 발주",
            "normal",
            "finance_approved",
            "tech-01",
            "mgr-01",
            "정상 승인",
            None,
            "2026-08-06 09:00:00",
            "mgr-02",
            "승인 — 예산·한도 이내",
            "2026-08-06 10:30:00",
        ),
        (
            "PO-0119",
            "PCB-S100-CTRL-R2",
            2,
            "SUP-A",
            None,
            None,
            None,
            3000000,
            "S100 제어보드 대량 확보 요청 — 예비 재고 확충",
            "normal",
            "finance_rejected",
            "tech-02",
            "mgr-01",
            "긴급 확보 필요 — 승인",
            None,
            "2026-08-07 09:00:00",
            "mgr-02",
            "예산 한도 초과 — 반려",
            "2026-08-07 11:15:00",
        ),
        (
            "PO-0120",
            "FUSE-30A",
            10,
            "SUP-C",
            None,
            None,
            None,
            9000,
            "3번 라인 정기 교체분 — 소모품 보충",
            "normal",
            "approved",
            "tech-01",
            "mgr-01",
            "정상 승인 — 재무 결정 대기",
            None,
            "2026-08-08 09:00:00",
            None,
            None,
            None,
        ),
    ]
    if not with_codes:
        # error_codes 가 비어 있으면 FK를 만족할 수 없다 → 코드 필드를 비운다
        rows = [r[:4] + (None, None) + r[6:] for r in rows]

    con.executemany(
        "INSERT INTO po_drafts (po_id, part_no, qty, supplier_id, model, error_code,"
        " evidence, unit_price, reason, urgency, state, requested_by, decided_by,"
        " decision_note, session_id, decided_at, finance_decided_by,"
        " finance_decision_note, finance_decided_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )


# ────────────────────────────────────────────── error_codes (승인 게이트)


def error_codes_gate() -> tuple[bool, str]:
    """적재 가능 여부와 사유. 사람 승인 전에는 막는다 (TODO_직접할일.md)."""
    if not ERROR_CODES_JSON.exists():
        return False, "M1 추출 미완료 — data/extracted/error_codes.json 이 없습니다"
    doc = json.loads(ERROR_CODES_JSON.read_text(encoding="utf-8"))
    status = str(doc.get("_status", ""))
    if "초안" in status or "승인 전" in status:
        return False, f"사람 승인 전입니다 — _status: {status!r}"
    return True, "승인 확인됨"


def related_parts_caveat() -> str:
    """related_parts 의 검수 상태를 파일에서 읽어 한 줄 경고로 돌려준다.

    문구를 하드코딩하면 검수가 끝난 뒤에도 "사람 검수 전"이라고 계속 출력해
    거짓 경고가 된다. 반대로 경고를 지우면 미검수 상태가 조용히 넘어간다 —
    그래서 상태를 **파일에서 유도**한다 (D12: 부품 특정 정확률의 뿌리).
    """
    if not RELATED_PARTS_JSON.exists():
        return "⚠ related_parts 매핑 파일 없음 — 부품 특정이 동작하지 않는다"

    rp = json.loads(RELATED_PARTS_JSON.read_text(encoding="utf-8"))
    mappings = rp.get("mappings", [])
    pending = [m for m in mappings if not m.get("reviewed")]
    if pending:
        codes = ", ".join(f"{m['model']}/{m['code']}" for m in pending)
        return f"⚠ 미검수 {len(pending)}건 ({codes}) — 평가 결과를 실적으로 인용하지 말 것"

    reviewers = {str(m.get("reviewed_by", "")).lower() for m in mappings}
    if any("claude" in r for r in reviewers):
        return (
            f"⚠ {len(mappings)}개 코드 검수 완료 — 단 Claude 위임 판정이며 사람 최종 승인은 아니다"
            " (TODO_직접할일.md 참조)"
        )
    return f"✓ {len(mappings)}건 사람 검수 완료"


def part_class_caveat() -> str:
    """`parts.part_class` 의 검수 상태를 한 줄 경고로 돌려준다 (D12 — related_parts 선례).

    ⚠ **게이트가 아니다.** 미검수를 이유로 시드를 막으면 스프린트가 통째로 선다.
      `backend/agent/prompts.py` 의 안전 문구 미검수를 런타임에서 막지 않는 것과 같은 태도 —
      막는 대신 **매 실행 눈에 띄게 만든다.**

    문구를 하드코딩하지 않고 데이터에서 유도한다: 검수가 끝난 뒤에도 "검수 전"이라고
    계속 출력하면 거짓 경고가 되고, 경고를 지우면 미검수가 조용히 넘어간다.
    """
    total = len(PART_CLASS)
    missing = [p for p, *_ in PARTS if p not in PART_CLASS]
    if missing:
        return f"⚠ part_class 미지정 {len(missing)}건 ({', '.join(missing)}) — 3지 판단 불가"

    counts: dict[str, int] = {}
    for cls in PART_CLASS.values():
        counts[cls] = counts.get(cls, 0) + 1
    dist = " / ".join(f"{k} {v}" for k, v in sorted(counts.items()))
    if not PART_CLASS_REVIEWED:
        return (
            f"⚠ parts.part_class {total}종은 **미검수 초안**이다 ({dist}) — "
            "assess_repair_value 3지 판단에 직접 영향. TODO_직접할일.md 참조"
        )
    return f"✓ part_class {total}종 사람 검수 완료 ({dist})"


def partner_links_caveat() -> str:
    """partner_links 시드가 목업 전제인지 한 줄로 돌려준다 (D90 — part_class_caveat 선례).

    문구를 하드코딩하지 않고 `PARTNER_LINKS_MOCK` **상태에서 유도**한다. 하드코딩하면
    사람이 실값을 받은 뒤에도 "목업"이라고 계속 출력해 거짓 경고가 되고, 반대로 줄을
    지우면 목업 전제가 조용히 넘어간다 — 검수가 끝나도 **줄을 없애지 않고 문구만 바꾼다**(D90).

    ⚠ **게이트가 아니다.** 값이 목업이라고 시드를 막지 않는다 (part_class_caveat 와 같은 태도).
    """
    states = [row[3] for row in PARTNER_LINKS]
    linked = states.count("LINKED")
    not_linked = states.count("NOT_LINKED")
    shape = f"{len(PARTNER_LINKS)}행 (LINKED {linked} / NOT_LINKED {not_linked})"
    if PARTNER_LINKS_MOCK:
        return (
            f"⚠ partner_links {shape}은 **목업 전제**다 — 실제 파트너 연결 승인·자격증명"
            " 발급이 아니다. A2A 호출부도 미착수. TODO_직접할일.md 참조"
        )
    return f"✓ partner_links {shape} 사람 연결 승인 확인 완료"


def load_error_codes(con: DbConnection) -> tuple[int, int]:
    """추출 JSON → error_codes. related_parts 는 임시 매핑 파일로 덧씌운다 (검수 전).

    ⚠ **명시적 컬럼 목록으로 INSERT 한다** — 위치 인자 INSERT 는 컬럼이 늘어나는 순간
      조용히 깨진다(어느 값이 어느 컬럼에 들어갔는지 SQLite 가 검증해 주지 않는다).
      `actions_manual_id`·`actions_page` (D100) 는 JSON 에 키가 있으면 채우고 없으면
      `None` — MQ-919 가 승인 3건(iG5A RERR·ETB, S100 FANW)만 정본에 채웠으므로 그 3건만
      값이 있고 나머지 67건은 `None` 이 정상이다(Sprint 15 가 IE5 5건을 더해 62→67, 검사 ㉚).
    """
    doc = json.loads(ERROR_CODES_JSON.read_text(encoding="utf-8"))
    overlay: dict[tuple[str, str], list[str]] = {}
    if RELATED_PARTS_JSON.exists():
        rp = json.loads(RELATED_PARTS_JSON.read_text(encoding="utf-8"))
        overlay = {(m["model"], m["code"]): m["parts"] for m in rp.get("mappings", [])}

    rows, mapped = [], 0
    for e in doc["entries"]:
        parts = overlay.get((e["model"], e["code"]))
        if parts:
            mapped += 1
        rows.append(
            (
                e["model"],
                e["code"],
                e.get("display_code"),
                e["error_name"],
                e["severity"],
                json.dumps(e["causes"], ensure_ascii=False),
                json.dumps(e["actions"], ensure_ascii=False),
                json.dumps(parts, ensure_ascii=False) if parts else None,
                e["manual_page"],
                e.get("actions_manual_id"),
                e.get("actions_page"),
            )
        )
    con.executemany(
        "INSERT INTO error_codes (model, code, display_code, error_name, severity, causes,"
        " actions, related_parts, manual_page, actions_manual_id, actions_page)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    return len(rows), mapped


# ────────────────────────────────────────────────────────────── 검증


def _disposal_verdicts(con: DbConnection) -> dict[tuple[str, str], dict]:
    """처분 시나리오 자산 5종을 **실제 판정기에 통과시켜** 결과를 모은다 (⑮).

    DB 사본(`load_*_from_db`)으로 로드한다 — 파일 로더로 돌리면 "시드가 적재한 사본이
    판정에 쓸 수 있는 상태인가"를 검증하지 못한다. `disposal_date`·`disposal_mode` 는
    시드 컬럼이 아니라 도구 파라미터이므로 `DISPOSAL_PROBE_MONTHS` 로 만든다.

    반환 키가 `(asset_id, disposal_mode)` 인 이유: 같은 자산도 매각/폐기에 따라 판정이
    갈리는 게 **도메인 사실**이라(D78) 자산 하나에 답이 하나가 아니다.
    """
    sys.path.insert(0, str(ROOT.parent))
    from data.rules import engine  # noqa: PLC0415

    prev_factory = con.row_factory
    con.row_factory = DbRow
    probes = {(a, e["mode"]) for a, e in DISPOSAL_EXPECTATIONS.items()}
    probes.add(DISPOSAL_MODE_CONTRAST[:2])
    try:
        laws = engine.load_laws_from_db(con)
        rules = engine.load_rules_from_db(con, laws)
        out: dict[tuple[str, str], dict] = {}
        for asset_id, mode in sorted(probes):
            row = con.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone()
            months = DISPOSAL_PROBE_MONTHS[asset_id]
            probe = _shift_months(date.fromisoformat(row["acquired_at"]), months)
            facts = engine.build_facts(row, disposal_mode=mode, disposal_date=probe)
            findings = [engine.evaluate_rule(r, facts, laws) for r in rules.values()]
            buckets = {
                "n_blockers": sum(
                    f.verdict == "TRIGGERED" and f.disposal_type == "BLOCKING" for f in findings
                ),
                "n_preconditions": sum(
                    f.verdict == "TRIGGERED" and f.disposal_type == "PRECONDITION" for f in findings
                ),
                "n_holds": sum(f.verdict == "HOLD" for f in findings),
                "n_insufficient": sum(f.verdict == "INSUFFICIENT_FACTS" for f in findings),
            }
            out[(asset_id, mode)] = {
                "verdict": engine.check_disposal_blockers(facts)["verdict"],
                "disposal_date": probe,
                **buckets,
            }
        return out
    finally:
        con.row_factory = prev_factory


def verify(con: DbConnection, with_codes: bool, db_path: Path) -> list[tuple[str, bool, str]]:
    """docs/05_DB_SCHEMA.md 시드 케이스 맵 7종(⑧까지) + D41 스키마 보강(⑨~⑪) 자가 검증.

    Sprint 6~7 확장(⑫~㉑) · Sprint 8 partner_links 3건 + A2A 계측 자리 1건(㉒~㉕) ·
    parts.mfr_part_no 1건(㉖) · Sprint 9 repair_records 상태 불변식(D98)·error_codes 출처
    컬럼 짝(D100)·record_hash 재계산 대조(D84 태도) 3건(㉗~㉙) · actions 병합 검증
    (MQ-919) 1건(㉚) · part_lifecycle_mock 1건(㉛, Sprint 10 브레인스토밍 D) ·
    Sprint 11 deadlines·incidents·ownership_checks·risk_profile 4건(㉜~㉟, MQ-1101) ·
    Sprint 15 error_codes IE5 병합 1건(㊱) · Sprint 17 po_drafts finance 확장 4건
    (㊲~㊵, MQ-1702)이 뒤에 붙는다.
    ⚠ 검사 번호는 `docs/10_DECISIONS.md` 본문이 인용한다 — D96 이 ㉒ 를, D95 가 ㉔ 를,
      D97 이 ㉖ 을 지목한다.
      번호를 바꾸면 이미 커밋된 D 본문이 조용히 거짓이 되므로 결정 문서를 같은 커밋에서 고칠 것.
    """
    q = lambda sql, *a: con.execute(sql, a).fetchone()  # noqa: E731
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        results.append((name, ok, detail))

    r = q("SELECT qty, safety_stock FROM inventory WHERE part_no='FAN-IG5-01'")
    check("① 정상 발주 (안전재고 미달)", r == (1, 3), f"qty={r[0]}, safety={r[1]}")

    inv = q("SELECT qty FROM inventory WHERE part_no='PCB-S100-CTRL'")
    disc = q("SELECT discontinued FROM parts WHERE part_no='PCB-S100-CTRL'")
    alt = q(
        "SELECT count(*) FROM part_alternatives"
        " WHERE part_no='PCB-S100-CTRL' AND compat_confirmed=1"
    )
    check(
        "② 재고 0 + 단종 + 대체품 有",
        inv[0] == 0 and disc[0] == 1 and alt[0] >= 1,
        f"qty={inv[0]}, discontinued={disc[0]}, 확정대체품={alt[0]}건",
    )

    inv2 = q("SELECT qty FROM inventory WHERE part_no='PWR-S100-MOD'")
    alt2 = q("SELECT count(*) FROM part_alternatives WHERE part_no='PWR-S100-MOD'")
    check(
        "③ 대체품 없음 (에스컬레이션)",
        inv2[0] == 0 and alt2[0] == 0,
        f"qty={inv2[0]}, 대체품={alt2[0]}건",
    )

    quotes = con.execute(
        "SELECT supplier_id, lead_days, unit_price, moq FROM supplier_parts"
        " WHERE part_no='FAN-IG5-01' ORDER BY supplier_id"
    ).fetchall()
    check(
        "④ 리드타임 트레이드오프",
        quotes == [("SUP-A", 3, 38000, 1), ("SUP-B", 14, 29000, 10)],
        str(quotes),
    )

    cnt = q(
        "SELECT count(*) FROM error_history WHERE equipment_id='INV-L3-01' AND code='OCT'"
        " AND occurred_at >= datetime('now','-30 day')"
    )
    acts = con.execute(
        "SELECT DISTINCT action_taken FROM error_history WHERE equipment_id='INV-L3-01'"
        " AND code='OCT' AND occurred_at >= datetime('now','-30 day')"
    ).fetchall()
    check(
        "⑤ 반복 고장 (30일 3회, 전부 리셋)",
        cnt[0] == 3 and acts == [("리셋",)],
        f"count={cnt[0]}, actions={[a[0] for a in acts]}",
    )

    unconf = q("SELECT count(*) FROM part_alternatives WHERE compat_confirmed=0")
    check("⑥ 미확인 호환 정확히 1건", unconf[0] == 1, f"{unconf[0]}건")

    p = q("SELECT count(*) FROM parts")[0]
    e = q("SELECT count(*) FROM equipment")[0]
    s = q("SELECT count(*) FROM suppliers")[0]
    h = q("SELECT count(*) FROM error_history")[0]
    check(
        "⑦ 규모감",
        35 <= p <= 45 and 8 <= e <= 12 and s == 4 and 180 <= h <= 220,
        f"parts={p}, equipment={e}, suppliers={s}, history={h}",
    )

    ec = q("SELECT count(*) FROM error_codes")[0]
    check(
        "⑧ error_codes 적재",
        (ec > 0) if with_codes else (ec == 0),
        f"{ec}건" + ("" if with_codes else " (사람 승인 전이라 의도적으로 비움)"),
    )

    # ── D41 스키마 보강 4건 회귀
    users = con.execute(
        "SELECT user_id, display_name, role, department FROM users ORDER BY user_id"
    ).fetchall()
    check(
        "⑨ users 4행 적재 (D41·D108)",
        users
        == [
            ("mgr-01", "박OO", "manager", "maintenance"),
            ("mgr-02", "최OO", "manager", "finance"),
            ("tech-01", "김OO", "technician", "maintenance"),
            ("tech-02", "이OO", "technician", "maintenance"),
        ],
        f"{len(users)}행 {[u[0] for u in users]}",
    )
    # department 는 role 과 직교다 — 재무부(mgr-02)도 role 은 여전히 'manager' (D108)
    dept_role_check = con.execute(
        "SELECT count(*) FROM users WHERE department='finance' AND role != 'manager'"
    ).fetchone()[0]
    check(
        "⑨-b department 는 role 을 바꾸지 않는다 (D108)",
        dept_role_check == 0,
        f"finance 소속인데 role≠manager 인 행 {dept_role_check}건",
    )

    # 실재하지 않는 user_id 로는 발주가 만들어지지 않는다 (D41 FK).
    # 실제로 INSERT 를 시도해야 검증이 되므로 SAVEPOINT 로 감싸고 되돌린다
    con.execute("SAVEPOINT fk_probe")
    fk_detail = "INSERT 가 통과해버림 (FK 미적용?)"
    try:
        con.execute(
            "INSERT INTO po_drafts (po_id, part_no, qty, supplier_id, unit_price, reason,"
            " requested_by) VALUES ('PO-FK00','FAN-IG5-01',1,'SUP-A',1000,'FK 검증','ghost-99')"
        )
        fk_rejected = False
    except sqlite3.IntegrityError as exc:
        fk_rejected, fk_detail = True, str(exc)
    finally:
        con.execute("ROLLBACK TO fk_probe")
        con.execute("RELEASE fk_probe")
        con.commit()  # 다음 검사가 다른 커넥션으로 읽으므로 트랜잭션을 남기지 않는다
    check("⑩ 미등록 user_id 발주 → FK 거부", fk_rejected, fk_detail)

    # 표시명은 하드코딩이 아니라 DB 조회여야 한다 (D41 — po.USER_NAMES 이관)
    sys.path.insert(0, str(ROOT.parent))
    from backend.services.po import display_name  # noqa: PLC0415

    # ⚠ `db_path` 는 SQLite 시절의 파일 경로(Path)다. Postgres 에서는 `backend/db.py::
    #   connect()` 가 DSN 문자열만 존중하므로 이 Path 는 **조용히 무시되고 DATABASE_URL
    #   로 갔다** — 마침 검증 대상과 같은 DB 라 우연히 맞아 왔다(2026-08-29 가드 도입으로
    #   드러남). 의도를 명시한다: Postgres 면 None 을 넘겨 DATABASE_URL 을 쓰게 한다.
    backend_db = None if dbcompat.USE_POSTGRES else db_path
    dn = display_name("tech-01", db_path=backend_db)
    unknown = display_name("ghost-99", db_path=backend_db)
    check(
        "⑪ display_name 이 users 조회로 동작",
        dn == "김OO" and unknown == "ghost-99",
        f"tech-01 → {dn!r}, 미등록 → {unknown!r} (ID 그대로)",
    )

    # ── Sprint 6 확장 (D68·D60·D61·D12·D74). ⑮ 는 MQ-601b 소유 — 여기 없는 게 정상이다
    n_assets = q("SELECT count(*) FROM assets")[0]
    orphan = con.execute(
        "SELECT equipment_id FROM equipment WHERE asset_id IS NULL ORDER BY equipment_id"
    ).fetchall()
    bad_fk = q(
        "SELECT count(*) FROM equipment e LEFT JOIN assets a ON a.asset_id = e.asset_id"
        " WHERE e.asset_id IS NOT NULL AND a.asset_id IS NULL"
    )[0]
    check(
        "⑫ assets 9행 · 호스트 없는 설비 1건",
        n_assets == 9 and [o[0] for o in orphan] == ["INV-L1-01"] and bad_fk == 0,
        f"assets={n_assets}행, asset_id NULL={[o[0] for o in orphan]}, 미해결 FK={bad_fk}",
    )

    # 파일이 정본이고 DB 는 사본이다 (D60) — 개수를 하드코딩하면 MQ-602L 이 파일을
    # 추가했을 때 사본 누락을 못 잡는다. 그래서 **파일 수와 동적으로 대조**한다
    law_files = sorted(p.stem for p in LAWS_DIR.glob("*.json"))
    law_rows = [r[0] for r in con.execute("SELECT law_ref_id FROM law_refs ORDER BY 1")]
    check(
        "⑬ law_refs 사본 == laws/*.json 파일 (D60)",
        law_rows == law_files,
        f"파일 {len(law_files)}개 / DB {len(law_rows)}행"
        + ("" if law_rows == law_files else f" · 차집합 {set(law_files) ^ set(law_rows)}"),
    )

    rule_rows = con.execute("SELECT rule_id, law_refs, contract_refs FROM rules").fetchall()
    evidenceless = [r[0] for r in rule_rows if not json.loads(r[1]) and not json.loads(r[2])]
    check(
        "⑭ rules 5행 · 근거 없는 룰 0건 (D61)",
        len(rule_rows) == 5 and not evidenceless,
        f"{len(rule_rows)}행, 근거 없는 룰 {evidenceless}",
    )

    # ⑮ 룰 카탈로그가 **실제로 5종 판정을 내는가** (MQ-601b · D77).
    #    ⑭ 는 룰이 적재됐는지만 본다 — 적재된 룰이 어떤 사실 조합에도 발동하지 않아도 통과한다.
    #    그 구멍이 D77 이 잡은 결함이라, 여기서는 시드 자산에 실제로 판정을 돌린다.
    actual, expect_detail = _disposal_verdicts(con), []
    verdict_ok = True
    for asset_id, expected in DISPOSAL_EXPECTATIONS.items():
        mode = expected["mode"]
        got = actual[(asset_id, mode)]
        ok = all(got[k] == v for k, v in expected.items() if k != "mode")
        verdict_ok = verdict_ok and ok
        expect_detail.append(
            f"{asset_id}/{mode}={got['verdict']}" + ("" if ok else f"(≠{expected})")
        )
    # 같은 자산·다른 mode → 다른 판정 (도메인 사실, D78)
    c_asset, c_mode, c_expected = DISPOSAL_MODE_CONTRAST
    contrast = actual[(c_asset, c_mode)]
    contrast_ok = contrast["verdict"] == c_expected
    check(
        "⑮ 처분 판정 5종 재현 (D77·D78·D79)",
        verdict_ok and contrast_ok,
        " · ".join(expect_detail)
        + f" · [대조] {c_asset}/{c_mode}={contrast['verdict']}"
        + ("" if contrast_ok else f"(≠{c_expected})")
        + " (매각은 VAT-INVOICE 때문에 최소 CONDITIONAL — CLEAR 는 SCRAP·TRANSFER 에서만)",
    )

    # ⑯ part_class 전량 + 잔가곡선 격자. 행 수를 하드코딩하지 않는다 —
    #    MQ-603 이 카테고리를 늘리면(N-12 로 6→7종) 하드코딩은 위양성 FAIL 이 된다.
    #    검사해야 할 성질은 "격자에 공백이 없다"이지 "36행"이 아니다
    pc_null = q("SELECT count(*) FROM parts WHERE part_class IS NULL")[0]
    pc_bad = q("SELECT count(*) FROM parts WHERE part_class NOT IN ('CONSUMABLE','CRITICAL')")[0]
    fan = q("SELECT part_class FROM parts WHERE part_no='FAN-IG5-01'")[0]
    rc_total = q("SELECT count(*) FROM residual_curve")[0]
    rc_cats = q("SELECT count(DISTINCT category) FROM residual_curve")[0]
    rc_buckets = q("SELECT count(DISTINCT age_bucket) FROM residual_curve")[0]
    rc_range = q(
        "SELECT count(*) FROM residual_curve WHERE NOT (residual_ratio > 0 AND residual_ratio <= 1)"
    )[0]
    rc_mock = q("SELECT count(*) FROM residual_curve WHERE source NOT LIKE '%목업%'")[0]
    order = ["0-2", "3-5", "6-10", "11-15", "16-20", "21-30"]
    mono = True
    for (cat,) in con.execute("SELECT DISTINCT category FROM residual_curve"):
        vals = dict(
            con.execute(
                "SELECT age_bucket, residual_ratio FROM residual_curve WHERE category=?", (cat,)
            ).fetchall()
        )
        seq = [vals[b] for b in order if b in vals]
        mono = mono and len(seq) == len(order) and seq == sorted(seq, reverse=True)
    # ★ 격자 **내부** 성질만 보면 N-12 같은 결함을 못 잡는다 — 곡선 자체는 6종 × 6버킷으로
    #   멀쩡했는데 시드 자산이 쓰는 `'공조냉각유공압'` 이 없어서 조인이 비었던 게 N-12 다.
    #   조인 미스 = 0 을 잠그면 `'환경  설비'` **공백 2칸 바이트 일치**까지 같이 잠긴다
    #   (문자열이 한 칸만 어긋나도 여기서 즉시 FAIL 한다).
    orphan_cats = con.execute(
        "SELECT DISTINCT a.category FROM assets a"
        " LEFT JOIN residual_curve r ON r.category = a.category"
        " WHERE r.category IS NULL ORDER BY 1"
    ).fetchall()
    join_ok = rc_total == 0 or not orphan_cats  # 곡선 미적재 시엔 조인을 따지지 않는다
    rc_ok = rc_total == 0 or (
        rc_total == rc_cats * rc_buckets  # 격자 공백 없음
        and rc_buckets == len(order)
        and rc_range == 0
        and rc_mock == 0
        and mono
    )
    check(
        "⑯ part_class 전량 · 잔가 격자 · assets 조인",
        pc_null == 0 and pc_bad == 0 and fan == "CRITICAL" and rc_ok and join_ok,
        f"part_class NULL={pc_null}, enum 밖={pc_bad}, FAN-IG5-01={fan} · "
        + (
            "residual_curve 0행 (json 부재)"
            if rc_total == 0
            else f"곡선 {rc_total}행 ({rc_cats}카테고리×{rc_buckets}버킷),"
            f" 범위밖={rc_range}, 목업표기누락={rc_mock}, 단조감소={mono},"
            f" 조인 미스={[c[0] for c in orphan_cats] or 0}"
        ),
    )

    # D63 은 스키마로 잠근 결정이다 — CHECK 가 실제로 거부하는지 INSERT 로 확인한다.
    # 한 번도 실행되지 않는 CHECK 는 있는 셈 치기 쉽다 (⑩ FK 프로브와 같은 이유)
    con.execute("SAVEPOINT d63_probe")
    d63_detail = "사유 없는 override 가 저장돼 버림 (CHECK 미작동)"
    try:
        con.execute(
            "INSERT INTO decisions (decision_id, asset_id, decision_type, evidence_bundle,"
            " bundle_hash, verdict_at_signing, override, override_reason)"
            " VALUES ('DEC-CHK','AST-L3-CONV','DISPOSAL','{}','sha256:x','BLOCKED',1,NULL)"
        )
        d63_rejected = False
    except sqlite3.IntegrityError as exc:
        d63_rejected, d63_detail = True, str(exc)
    finally:
        con.execute("ROLLBACK TO d63_probe")
        con.execute("RELEASE d63_probe")
        con.commit()
    check("⑰ 사유 없는 override → CHECK 거부 (D63)", d63_rejected, d63_detail)

    # ⑱ 담보 자산의 동의서 표기 규약 (W2). `''` = 확인된 해당 없음 / NULL = 모름.
    #    D77 로 `lien_consent_ref` 가 LIEN-CONSENT.required_facts 에서 빠지면서
    #    **마지막 안전망이 사라졌다** — has_lien=1 인 자산에 동의서 필드를 깜빡 잊어 `''` 가
    #    채워지면 `is_null`(a is None)이 False 라 BLOCKING 룰이 조용히 미발화하고,
    #    required_facts 가드도 없어 verdict 가 CLEAR/CONDITIONAL 로 떨어진다.
    #    = "담보 있는 자산을 동의서 없이 처분 가능" — 키 하나 빠뜨림으로 나는 최악의 오판.
    #    룰로는 막을 수 없으므로(그 조합을 표현할 필드가 없다) **데이터 불변식으로 잠근다.**
    lien_blind = con.execute(
        "SELECT asset_id FROM assets WHERE has_lien = 1"
        " AND lien_consent_ref IS NOT NULL AND trim(lien_consent_ref) = ''"
        " ORDER BY asset_id"
    ).fetchall()
    lien_total = q("SELECT count(*) FROM assets WHERE has_lien = 1")[0]
    check(
        "⑱ 담보 자산의 동의서 공백 표기 0건 (W2)",
        not lien_blind,
        f"has_lien=1 {lien_total}건 중 lien_consent_ref='' {len(lien_blind)}건"
        + (
            f" {[r[0] for r in lien_blind]} — BLOCKING 룰이 조용히 미발화한다" if lien_blind else ""
        ),
    )

    # ── Sprint 7 (MQ-707) — `decisions` 스키마 게이트 3건 ─────────────────────────
    # ⑲ 컬럼 존재. MQ-706 의 draft INSERT 가 `reason` 을 쓰고, 백엔드 `submit()` 이
    #    `requested_by` 를 stamp 한다(D23·D37). 컬럼이 없으면 도구가 INSERT 단계에서 죽는다.
    #    ⚠ `session_id` 는 **아직 아무도 채우지 않는다**(Sprint 8 예약). `create_po_draft` 는
    #      `loop.py` 가 stamp 하지만 처분 초안에는 대응물이 없어, 에이전트가 만든 초안이
    #      어느 대화에서 나왔는지 추적되지 않는다. 컬럼만 미리 뚫어 둔 상태다 —
    #      "채워진다"고 적으면 검사 라벨이 없는 동작을 주장하게 된다(reviewer W-2).
    cols = {r[1]: r for r in con.execute("PRAGMA table_info(decisions)").fetchall()}
    fk_targets = {
        r[3]: r[2] for r in con.execute("PRAGMA foreign_key_list(decisions)").fetchall()
    }  # from-컬럼 → 참조 테이블
    required_cols = ("reason", "requested_by", "session_id")
    missing_cols = [c for c in required_cols if c not in cols]
    check(
        "⑲ decisions 신규 컬럼 3종 + requested_by FK (MQ-706 draft 계약)",
        not missing_cols and fk_targets.get("requested_by") == "users",
        f"누락={missing_cols or 0} · requested_by → {fk_targets.get('requested_by')!r}"
        f" · 부가 컬럼 decision_note={'decision_note' in cols}"
        f", created_at={'created_at' in cols}",
    )

    # ⑳ **두 CHECK 가 실제로 거부하는가.** 한 번도 실행되지 않는 CHECK 는 있는 셈 치기 쉽다
    #    (⑩ FK 프로브·⑰ D63 프로브와 같은 이유). 여기서는 **음성 2건 + 양성 1건**을 본다 —
    #    양성이 없으면 "전부 거부하는 CHECK" 도 통과해 버려 검사가 방어선이 아니게 된다.
    _BUNDLE = "{\"laws\":[],\"rules\":[],\"evaluated\":[],\"contracts\":[],\"facts\":{}}"

    def _decision_probe(label: str, cols_sql: str, values_sql: str) -> tuple[bool, str]:
        """SAVEPOINT 안에서 INSERT 를 실제로 시도하고 되돌린다. (거부됨?, 상세)"""
        con.execute("SAVEPOINT dec_probe")
        try:
            con.execute(
                f"INSERT INTO decisions (decision_id, asset_id, decision_type,"  # noqa: S608
                f" evidence_bundle, bundle_hash, {cols_sql})"
                f" VALUES ('DEC-CHK','AST-L3-CONV','DISPOSAL','{_BUNDLE}','sha256:x',{values_sql})"
            )
            return False, f"{label}: INSERT 가 통과해버림 (CHECK 미작동)"
        except sqlite3.IntegrityError as exc:
            return True, f"{label}: {exc}"
        finally:
            con.execute("ROLLBACK TO dec_probe")
            con.execute("RELEASE dec_probe")
            con.commit()

    # 음성 ⓐ — 서명 없는 확정: state='signed' 인데 signed_at·reviewed_by 가 NULL
    neg_a, det_a = _decision_probe(
        "ⓐ 서명 없는 signed",
        "verdict_at_signing, state",
        "'CLEAR','signed'",
    )
    # 음성 ⓑ — BLOCKING 우회: 서명 3요소는 갖췄지만 verdict=BLOCKED 인데 override=0
    neg_b, det_b = _decision_probe(
        "ⓑ override 없는 BLOCKED signed",
        "verdict_at_signing, state, signed_at, reviewed_by, override",
        "'BLOCKED','signed','2026-08-10 00:00:00','mgr-01',0",
    )
    # 양성 ⓒ — 정상 서명은 통과해야 한다 (거부되면 CHECK 가 과하게 잡는 것)
    pos_ok, det_c = _decision_probe(
        "ⓒ 정상 서명",
        "verdict_at_signing, state, signed_at, reviewed_by, override",
        "'CLEAR','signed','2026-08-10 00:00:00','mgr-01',0",
    )
    check(
        "⑳ 서명 없는 확정 / BLOCKING 우회 → CHECK 거부 (양성 대조 포함)",
        neg_a and neg_b and not pos_ok,
        f"{det_a} · {det_b} · ⓒ 정상 서명 통과={not pos_ok}",
    )

    # ㉑ CHECK 의 verdict 목록이 `engine.VERDICTS` 와 정합인가.
    #    DDL 은 리터럴이라 엔진이 어휘를 늘려도 조용히 낡는다. **방향을 정확히 적어 둔다** —
    #    CHECK 는 `verdict_at_signing IN ('CONDITIONAL','CLEAR')` **화이트리스트**라
    #    새 어휘는 override 를 요구하는 쪽(fail-closed)으로 떨어진다. 즉 위험은
    #    "새 차단 어휘가 우회된다"가 **아니라** "새 **비차단** 어휘가 부당하게 막힌다" 쪽이다.
    #    ⚠ 아래 `engine_blocking == set(BLOCKING_VERDICTS)` 는 양변이 같은 식으로 계산돼
    #      **항진명제**다. 실질 방어는 ⓐ DDL 문자열 파싱 대조(이 검사)와
    #      ⓑ `backend/services/decisions.py` 의 모듈 수준 assert(import 시점에 죽는다) 두 개다.
    from backend.services.decisions import BLOCKING_VERDICTS  # noqa: PLC0415
    from data.rules import engine  # noqa: PLC0415

    m = re.search(
        r"state <> 'signed' OR override = 1\s*OR verdict_at_signing IN \(([^)]*)\)", SCHEMA
    )
    ddl_non_blocking = set(re.findall(r"'([^']+)'", m.group(1))) if m else set()
    engine_blocking = set(engine.VERDICTS) - {"CONDITIONAL", "CLEAR"}
    check(
        "㉑ CHECK 의 비차단 verdict 목록 == engine.VERDICTS 파생 (D79)",
        bool(m)
        and ddl_non_blocking == set(engine.VERDICTS) - engine_blocking
        and engine_blocking == set(BLOCKING_VERDICTS),
        f"DDL 비차단={sorted(ddl_non_blocking)} · engine.VERDICTS={list(engine.VERDICTS)}"
        f" · BLOCKING_VERDICTS={list(BLOCKING_VERDICTS)}",
    )

    # ── Sprint 8 (MQ-804) — partner_links 4건 ────────────────────────────────────
    # ㉒ 시드 정합 · NOT_LINKED 대조군 존재 · 목업 고지 (D92·D95·D96)
    pl = con.execute(
        "SELECT partner, subject_type, subject_ref, link_state, external_ref, linked_at"
        " FROM partner_links ORDER BY partner, subject_type, subject_ref"
    ).fetchall()
    n_linked = sum(1 for r in pl if r[3] == "LINKED")
    n_not_linked = sum(1 for r in pl if r[3] == "NOT_LINKED")
    a22 = n_linked >= 1 and n_not_linked >= 1  # ⓐ 대조군이 없으면 D92 의 핵심이 사라진다

    # ⓑ 값 규약은 DDL CHECK 가 아니라 여기서 본다 (D96-ⓒ — 파트너가 늘 때마다 DDL 을 고치지 않는다)
    bad_partner = sorted({r[0] for r in pl} - {"finallq", "insuq"})
    bad_subject_type = sorted({r[1] for r in pl} - {"company", "building", "asset"})
    b22 = not bad_partner and not bad_subject_type

    # ⓒ **동적 대조** — 하드코딩 4종으로 적으면 자산이 늘 때 대장 누락을 못 잡는다 (검사 ⑬ 과 같은 논리)
    bld_rows = {
        r[0]
        for r in con.execute(
            "SELECT DISTINCT building_id FROM assets WHERE building_id IS NOT NULL"
        )
    }
    # ⚠ building 결만 대조한다. insuq 에 company 결 행이 늘면 `''` 때문에 집합이 어긋나는데,
    #    그 실패는 "대장 누락"이 아니라 "결이 섞였다"이고 메시지가 오독을 부른다 (Stage 3 reviewer 권고 ④)
    insuq_refs = {r[2] for r in pl if r[0] == "insuq" and r[1] == "building"}
    bld_null = q("SELECT count(*) FROM assets WHERE building_id IS NULL")[0]
    c22 = insuq_refs == bld_rows

    # ⓓ linked_at 은 LINKED 행만 non-null · 시·분·초 포함 · 현재 UTC 이전.
    #    ⛔ 비교도 반드시 UTC 다 — 로컬 시계와 섞으면 자정 근처에서 위양성 FAIL 한다 (D39·D96-ⓓ)
    now_utc_s = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    ts_pat = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
    ts_shape_bad = [r[2] for r in pl if r[5] is not None and not ts_pat.match(r[5])]
    ts_future = [r[2] for r in pl if r[5] is not None and r[5] > now_utc_s]
    ts_pairing_bad = [
        r[2] for r in pl if (r[5] is not None) != (r[3] == "LINKED")
    ]  # LINKED ↔ non-null 짝
    d22 = not ts_shape_bad and not ts_future and not ts_pairing_bad

    # ⓔ 회사 결은 '' (D96-ⓑ). NULL 이면 PK 가 무력화돼 매핑이 2행·3행으로 갈려도 아무도 모른다
    company_refs = [r[2] for r in pl if r[1] == "company"]
    e22 = bool(company_refs) and all(ref == "" for ref in company_refs)

    # ⓕ 목업 고지는 **상태에서 유도**된다 (D90 — 검사 ⑯ 의 source LIKE '%목업%' 선례)
    #    ⚠ 문구(부분문자열)와 **접두 기호** 두 축을 함께 잠근다 — `main()` 은 라벨을
    #    `startswith('✓')` 로 고르므로, 목업 문구가 실수로 `✓` 로 시작하면
    #    `[사람 확인] ⚠ … 목업 전제 …` 라는 **자기모순 라벨**이 나오는데 문구 축만 보면 통과한다.
    #    D90 이 기각한 ③(값은 "검수 완료"인데 이름에 unreviewed 가 남는다)과 같은 유형이다.
    #    (Stage 3 reviewer 권고 ②)
    pl_caveat = partner_links_caveat()
    f22_text = ("목업" in pl_caveat) if PARTNER_LINKS_MOCK else ("목업" not in pl_caveat)
    f22_mark = pl_caveat.startswith("⚠" if PARTNER_LINKS_MOCK else "✓")
    f22 = bool(pl_caveat.strip()) and f22_text and f22_mark
    check(
        "㉒ partner_links 시드 정합 · NOT_LINKED 대조군 · 목업 고지 (D92)",
        a22 and b22 and c22 and d22 and e22 and f22,
        f"ⓐ {len(pl)}행 LINKED={n_linked}/NOT_LINKED={n_not_linked}"
        f" · ⓑ partner 밖={bad_partner or 0}, subject_type 밖={bad_subject_type or 0}"
        f" · ⓒ insuq={sorted(insuq_refs)} vs assets.building_id={sorted(bld_rows)}"
        f" (building_id NULL 자산 {bld_null}건)"
        f" · ⓓ 형식위반={ts_shape_bad or 0}, 미래={ts_future or 0}, LINKED 짝 어긋남={ts_pairing_bad or 0}"
        f" (now_utc={now_utc_s})"
        f" · ⓔ company subject_ref={company_refs!r}"
        f" · ⓕ MOCK={PARTNER_LINKS_MOCK} 고지={f22}",
    )

    # ㉓ **두 CHECK 가 실제로 거부하는가** (⑩·⑰·⑳ 프로브와 같은 이유).
    #    음성 3 + **양성 2**. 양성이 없으면 "전부 거부하는 CHECK" 도 통과해 검사가 방어선이 아니게 된다.
    #    ⓑ 가 이 스프린트의 핵심이다 — `IS` 가 아니라 `=` 로 되돌아가면 여기서만 잡힌다 (D96-ⓐ).
    def _pl_probe(label: str, values_sql: str) -> tuple[bool, str]:
        """SAVEPOINT 안에서 INSERT 를 실제로 시도하고 되돌린다. (거부됨?, 상세)"""
        con.execute("SAVEPOINT pl_probe")
        try:
            con.execute(
                "INSERT INTO partner_links (partner, subject_type, subject_ref,"  # noqa: S608
                f" link_state, external_ref) VALUES ('probe','company',{values_sql})"
            )
            return False, f"{label}: 통과"
        except sqlite3.IntegrityError as exc:
            return True, f"{label}: 거부 ({exc})"
        finally:
            con.execute("ROLLBACK TO pl_probe")
            con.execute("RELEASE pl_probe")
            con.commit()  # 다음 검사가 다른 커넥션으로 읽으므로 트랜잭션을 남기지 않는다

    neg_a23, det_a23 = _pl_probe("음성ⓐ NOT_LINKED+식별자", "'P1','NOT_LINKED','X'")
    neg_b23, det_b23 = _pl_probe("음성ⓑ NULL+식별자", "'P2',NULL,'X'")
    neg_c23, det_c23 = _pl_probe("음성ⓒ 소문자 linked", "'P3','linked',NULL")
    pos_d23, det_d23 = _pl_probe("양성ⓓ NULL+NULL(모름)", "'P4',NULL,NULL")
    pos_e23, det_e23 = _pl_probe("양성ⓔ LINKED+식별자", "'P5','LINKED','CMP-X'")
    check(
        "㉓ partner_links CHECK 음성 3 + 양성 2 (D91·D96·D62)",
        neg_a23 and neg_b23 and neg_c23 and not pos_d23 and not pos_e23,
        f"{det_a23} · {det_b23} · {det_c23} · {det_d23} · {det_e23}",
    )

    # ㉔ **음성 검사** — partner_links 가 증권 식별자를 복제하지 않는다 (D95).
    #    ⛔ link_state 와 insured 를 엮지 않는다 — 연결 승인과 부보는 별개 축이고,
    #      엮으면 D78 이 분리한 두 사실을 되붙인다 (§A · BLD-D 를 대조군으로 고른 이유).
    insuq_ext = [(r[2], r[4]) for r in pl if r[0] == "insuq" and r[4] is not None]
    dup = q(
        "SELECT count(*) FROM partner_links WHERE external_ref IN"
        " (SELECT policy_id FROM assets WHERE policy_id IS NOT NULL)"
    )[0]
    finallq_ext = [r[4] for r in pl if r[0] == "finallq"]
    finallq_ok = bool(finallq_ext) and all(
        e is not None and e.startswith("CMP-") for e in finallq_ext
    )
    policies = con.execute(
        "SELECT policy_id, count(*) FROM assets WHERE policy_id IS NOT NULL"
        " GROUP BY policy_id ORDER BY 1"
    ).fetchall()
    # ⚠ `policies` 를 **판정에 넣는다** (Stage 3 reviewer 권고 ③). ⓑ 의 `IN (SELECT policy_id …)` 은
    #    우변이 공집합이면 **무조건 0** 이라, `assets.policy_id` 가 전부 NULL 이 되는 순간
    #    ⓑ 는 아무것도 지키지 않는다(공허참). 정본이 살아 있다는 사실이 이 검사의 전제이므로
    #    표시(detail)가 아니라 조건이어야 한다 — D95 의 "정본은 하나" 가 사라지면 복제 검사도 무의미하다.
    check(
        "㉔ partner_links 에 증권 식별자 복제 0건 (D95)",
        not insuq_ext and dup == 0 and finallq_ok and bool(policies),
        f"ⓐ insuq external_ref non-null={insuq_ext or 0}건"
        f" · ⓑ policy_id 값 복제={dup}건"
        f" · ⓒ finallq external_ref={finallq_ext!r}"
        f" · ⓓ [정본] assets.policy_id={[f'{p}×{n}' for p, n in policies] or 0}",
    )

    # ㉕ traces.request_chain_id 컬럼 존재·nullable (D94-ⓐ). 검사 ⑲ 의 PRAGMA 방식
    tr_cols = {r[1]: r for r in con.execute("PRAGMA table_info(traces)").fetchall()}
    rc_col = tr_cols.get("request_chain_id")
    check(
        "㉕ traces.request_chain_id 존재 · nullable (D94-ⓐ)",
        rc_col is not None and rc_col[3] == 0,
        f"존재={rc_col is not None}, notnull={rc_col[3] if rc_col else '-'}"
        " · **쓰는 쪽 = backend/a2a/trace.py**, 실측 계측 회귀는"
        " `spikes/a2a_identity_contract.py` 가 본다",
    )

    # ㉖ parts.mfr_part_no — 제조사 실품번 (D97).
    #
    # ⚠ 이 검사는 **"대부분 NULL"을 확인하는 검사가 아니다.** 그렇게 짜면 컬럼이 통째로
    #    비어도(적재 코드가 죽어도) 통과한다 — CLAUDE.md 부재검사 규칙이 금지하는 형태다.
    #    그래서 **양성 축**(정본 dict 와 DB 가 정확히 일치)과 **음성 축**(넣으면 안 되는 값이
    #    안 들어왔다)을 함께 걸고, detail 에 결론이 아니라 **두 축의 실측값**을 찍는다.
    p_cols = {r[1]: r for r in con.execute("PRAGMA table_info(parts)").fetchall()}
    mp_col = p_cols.get("mfr_part_no")
    total_parts = con.execute("SELECT count(*) FROM parts").fetchone()[0]
    filled = dict(
        con.execute("SELECT part_no, mfr_part_no FROM parts WHERE mfr_part_no IS NOT NULL")
    )
    # 음성 축 — 조사 중 실제로 헷갈렸던 두 종류가 들어왔는가
    bad = [
        f"{p}={v!r}"
        for p, v in filled.items()
        # ① 판매점 주문번호(숫자만) ② 완제품 형명(SV220iG5A-4 · LSLV0004G100-2EONN)
        if v.strip().isdigit()
        or (
            re.match(r"^(SV|LSLV)\d{3,4}(IG5A|G100|S100|IS7)", v.strip(), re.I)
            and not re.search(r"(FAN|PCB|ASSY|BOARD|KEYPAD|CAB\d)", v, re.I)
        )
    ]
    check(
        "㉖ parts.mfr_part_no 존재·nullable · 정본 일치 · 금지값 0건 (D97)",
        mp_col is not None
        and mp_col[3] == 0
        and total_parts > 0
        and filled == MFR_PART_NO
        and not bad,
        f"컬럼 존재={mp_col is not None}, notnull={mp_col[3] if mp_col else '-'}"
        f" · [양성] 적재 {len(filled)}/{total_parts}종, 정본(MFR_PART_NO {len(MFR_PART_NO)}종) 일치"
        f"={filled == MFR_PART_NO} {sorted(filled.items())}"
        f" · [음성] 금지값(주문번호·완제품형명) {len(bad)}건 {bad}"
        f" · NULL {total_parts - len(filled)}종은 **미조사가 아니라 미공개**"
        " (`data/analysis/part_number_sources.md`)",
    )

    # ㉗ repair_records 상태 불변식 (D98). "state='signed' ⇔ signed_at·record_hash·verified_by
    # 전부 non-null" 을 **양방향**(iff)으로 걸고, 어휘 밖 상태 0건 + 미서명 1행 존재까지 본다.
    # 미서명 1행이 사라지면 `get_maintenance_metrics.excluded[]` 검증이 공허해진다 (12 §11).
    signed_cnt = q("SELECT count(*) FROM repair_records WHERE state='signed'")[0]
    signed_complete = q(
        "SELECT count(*) FROM repair_records WHERE state='signed' AND signed_at IS NOT NULL"
        " AND record_hash IS NOT NULL AND verified_by IS NOT NULL"
    )[0]
    # 역방향 — 세 값이 다 차 있는데 state 가 signed 가 아닌 행(있으면 안 된다)
    complete_not_signed = q(
        "SELECT count(*) FROM repair_records WHERE state<>'signed' AND signed_at IS NOT NULL"
        " AND record_hash IS NOT NULL AND verified_by IS NOT NULL"
    )[0]
    bad_vocab = q(
        "SELECT count(*) FROM repair_records"
        " WHERE state NOT IN ('draft','pending','signed','rejected')"
    )[0]
    unsigned_cnt = q("SELECT count(*) FROM repair_records WHERE state<>'signed'")[0]
    check(
        "㉗ repair_records 상태 불변식 — signed⇔셋다non-null · 어휘·미서명 (D98)",
        signed_cnt == 11
        and signed_complete == signed_cnt
        and complete_not_signed == 0
        and bad_vocab == 0
        and unsigned_cnt == 1,
        f"[양성] state=signed {signed_cnt}건 중 셋다non-null {signed_complete}건"
        f" · [역방향] 셋다non-null인데 미서명={complete_not_signed}건"
        f" · [음성] 어휘 밖 상태={bad_vocab}건 · 미서명(state<>signed)={unsigned_cnt}건"
        " (기대 1건 = RPR-2403)",
    )

    # ㉘ error_codes 출처 컬럼 짝 불변식 (D100). DDL CHECK 가 이미 짝을 강제하므로 위반은
    # 구조적으로 0건이어야 한다 — 여기서는 그 사실과 게이트 상태(적재 여부)를 함께 실측한다.
    # `--with-error-codes` 없이 실행하면 0행이 정상이고 이때는 FAIL 이 아니라 통과시킨다.
    ec_mismatch = q(
        "SELECT count(*) FROM error_codes"
        " WHERE (actions_manual_id IS NULL) <> (actions_page IS NULL)"
    )[0]
    ec_total = q("SELECT count(*) FROM error_codes")[0]
    check(
        "㉘ error_codes 출처 컬럼 짝 불변식 (D100)",
        ec_mismatch == 0 and ((ec_total > 0) if with_codes else True),
        f"[음성] 짝 불일치={ec_mismatch}건 · [양성] error_codes 총 {ec_total}행"
        + (
            " (게이트: --with-error-codes 적재, 기대 70)"
            if with_codes
            else " (게이트: --with-error-codes 없음 — 0행이 정상, FAIL 아님)"
        ),
    )

    # ㉙ repair_records.record_hash 재계산 대조 (D84 태도). 시드가 저장한 해시와
    # `data/repair_hash.compute_record_hash()` 로 지금 다시 계산한 해시가 서명 11행 전건 일치해야 한다.
    sys.path.insert(0, str(ROOT.parent))
    from data.repair_hash import compute_record_hash  # noqa: PLC0415

    signed_rows = con.execute(
        "SELECT repair_id, equipment_id, model, error_code, part_class, work_type,"
        " expenditure_class, cost, downtime_hours, parts, performed_by, verified_by,"
        " signed_at, record_hash FROM repair_records WHERE state='signed' ORDER BY repair_id"
    ).fetchall()
    mismatches = []
    for (
        repair_id,
        equipment_id,
        model,
        error_code,
        part_class,
        work_type,
        expenditure_class,
        cost,
        downtime_hours,
        parts,
        performed_by,
        verified_by,
        signed_at,
        stored_hash,
    ) in signed_rows:
        recomputed = compute_record_hash(
            {
                "repair_id": repair_id,
                "equipment_id": equipment_id,
                "model": model,
                "error_code": error_code,
                "part_class": part_class,
                "work_type": work_type,
                "expenditure_class": expenditure_class,
                "cost": cost,
                "downtime_hours": downtime_hours,
                "parts": parts,
                "performed_by": performed_by,
                "verified_by": verified_by,
                "signed_at": signed_at,
            }
        )
        if recomputed != stored_hash:
            mismatches.append(repair_id)
    check(
        "㉙ repair_records.record_hash 재계산 대조 (D84)",
        len(signed_rows) == 11 and not mismatches,
        f"[양성] 서명 {len(signed_rows)}행 재계산 대조 일치"
        f" {len(signed_rows) - len(mismatches)}/{len(signed_rows)}건"
        f" · [음성] 불일치={mismatches}",
    )

    # ㉚ actions 병합 검증 (MQ-919, D99·D100). 승인 4건(iG5A RERR·ETB·NTC, S100 FANW)만
    #    actions_manual_id 가 채워져 있어야 하고(양성 축), 그 외 66건은 여전히 NULL 이어야
    #    한다(음성 축). 채워진 4건의 actions 내용도 후보 파일(병합 근거)과 대조한다.
    #    `--with-error-codes` 없이 실행하면 0행이 정상 — 이때는 FAIL 이 아니라 통과시킨다
    #    (㉘ 와 같은 태도).
    #    ⚠ `iG5A NTC` 는 2026-08-29 사람이 위임 반려를 뒤집어 승인한 건이다(기계 판정은
    #      여전히 STILL_AMBIGUOUS). 이 검사는 "승인된 것만 병합됐는가"를 보지 조치문이
    #      옳은지를 보지 않는다 — 근거의 한계는 후보 파일 override_note 에 남아 있다.
    expected_merged = {("iG5A", "RERR"), ("iG5A", "ETB"), ("S100", "FANW"), ("iG5A", "NTC")}
    merged_rows = con.execute(
        "SELECT model, code, actions, actions_manual_id, actions_page"
        " FROM error_codes WHERE actions_manual_id IS NOT NULL"
    ).fetchall()
    merged_keys = {(m, c) for m, c, *_ in merged_rows}
    null_count = q("SELECT count(*) FROM error_codes WHERE actions_manual_id IS NULL")[0]
    content_ok, content_detail = True, "n/a (게이트 미적재)"
    if with_codes:
        cand_path = EXTRACTED / "error_codes_actions.candidate.json"
        cand_by_key = {}
        if cand_path.exists():
            cand_doc = json.loads(cand_path.read_text(encoding="utf-8"))
            cand_by_key = {(e["model"], e["code"]): e for e in cand_doc.get("entries") or []}
        content_mismatches = []
        for m, c, actions_json, manual_id, page in merged_rows:
            cand = cand_by_key.get((m, c))
            if cand is None:
                content_mismatches.append((m, c, "후보 파일에 없음"))
                continue
            db_actions = json.loads(actions_json)
            if (
                db_actions != cand.get("actions")
                or manual_id != cand.get("actions_manual_id")
                or page != cand.get("actions_page")
            ):
                content_mismatches.append((m, c, "내용 불일치"))
        content_ok = not content_mismatches
        content_detail = (
            f"불일치={content_mismatches}"
            if content_mismatches
            else f"{len(merged_rows)}건 전부 후보값과 일치"
        )
    check(
        "㉚ error_codes.actions 병합 검증 (MQ-919)",
        (
            (merged_keys == expected_merged and null_count == 66 and content_ok)
            if with_codes
            else (len(merged_rows) == 0)
        ),
        f"[양성] 채워짐={sorted(merged_keys)} · [음성] NULL={null_count}건(기대 66)"
        f" · [내용대조] {content_detail}"
        + ("" if with_codes else " (게이트: --with-error-codes 없음 — 0행이 정상, FAIL 아님)"),
    )

    # ㉛ part_lifecycle_mock — 27행 · FK 정합(각 equipment 의 model 과 part_no 모델이 일치) (Sprint 10)
    rows_pl = con.execute(
        "SELECT p.equipment_id, e.model, p.part_no FROM part_lifecycle_mock p"
        " JOIN equipment e ON e.equipment_id = p.equipment_id"
    ).fetchall()
    mismatched = [
        (equipment_id, model, part_no)
        for equipment_id, model, part_no in rows_pl
        if (model == "iG5A" and "IG5" not in part_no) or (model == "S100" and "S100" not in part_no)
    ]
    check(
        "㉛ part_lifecycle_mock 27행 · 모델-부품 정합 (Sprint 10 브레인스토밍 D)",
        len(rows_pl) == 27 and not mismatched,
        f"행수={len(rows_pl)} (기대 27) · 모델 불일치 {len(mismatched)}건 {mismatched[:3]}",
    )

    # ㉜ deadlines — CHECK 프로브(음성: 잘못된 type INSERT 거부) + 0행 유지(양성) (Sprint 11, D10)
    #   MCP 쓰기 도구가 없어 정상 상태는 0행이다(flags 와 같은 이유) — "0행이라 통과"가 아니라,
    #   실제로 잘못된 INSERT 를 **시도**해 CHECK 가 실제로 막는지(양성 축: 시도 자체가 실행됨을
    #   sqlite3.IntegrityError 로 확인) 함께 잠근다.
    dl_before = q("SELECT count(*) FROM deadlines")[0]
    dl_rejected, dl_error = False, ""
    try:
        con.execute(
            "INSERT INTO deadlines (asset_id, type, due_date) VALUES (?,?,?)",
            ("AST-L3-LIFT", "NOT-A-TYPE", "2027-01-01"),
        )
    except sqlite3.IntegrityError as exc:
        dl_rejected, dl_error = True, str(exc)
    dl_after = q("SELECT count(*) FROM deadlines")[0]
    check(
        "㉜ deadlines CHECK 프로브 — 잘못된 type INSERT 거부 (D10)",
        dl_rejected and dl_before == 0 and dl_after == 0,
        "[음성] 잘못된 type INSERT 시도 → "
        + (f"거부됨 (IntegrityError: {dl_error})" if dl_rejected else "거부되지 않음 (FAIL)")
        + f" · [양성] 행수 before={dl_before} after={dl_after} (기대 0·0, 쓰기 경로 없음 D10)",
    )

    # ㉝ incidents — 2행 · FK 정합(asset_id ∈ assets, 고아 0건) · type enum 밖 0건 (Sprint 11, D68)
    inc_rows = con.execute("SELECT incident_id, asset_id, type FROM incidents").fetchall()
    inc_orphan = q(
        "SELECT count(*) FROM incidents i LEFT JOIN assets a ON a.asset_id = i.asset_id"
        " WHERE a.asset_id IS NULL"
    )[0]
    inc_enum_bad = [
        r[2] for r in inc_rows if r[2] not in ("COLLISION", "ALIGNMENT_LOSS", "FIRE", "FLOOD", "OTHER")
    ]
    inc_expected = {("AST-L2-SPDL", "COLLISION"), ("AST-L4-WRAP", "OTHER")}
    inc_actual = {(r[1], r[2]) for r in inc_rows}
    check(
        "㉝ incidents 2행 · FK 정합(고아 0건) · type enum (Sprint 11, D68)",
        len(inc_rows) == 2 and inc_orphan == 0 and not inc_enum_bad and inc_actual == inc_expected,
        f"행수={len(inc_rows)}(기대 2) · FK 고아={inc_orphan}건 · enum 밖={inc_enum_bad}"
        f" · 자산/유형={sorted(inc_actual)}",
    )

    # ㉞ ownership_checks — 행수 == verify_ownership(AST-L3-LIFT) 실측 항목 수 · either-or CHECK
    #    음성 검사 2건 (S18, D68). 실측은 하드코딩 38이 아니라 **판정기를 직접 호출**해서 댄다 —
    #    상수만 대조하면 판정기가 항목을 늘려도(또는 줄여도) 시드가 조용히 낡는다.
    sys.path.insert(0, str(ROOT.parent))
    from data.ownership import verify as own_verify  # noqa: PLC0415

    prev_factory = con.row_factory
    con.row_factory = DbRow
    try:
        live = own_verify(con, asset_id="AST-L3-LIFT")
    finally:
        con.row_factory = prev_factory
    live_item_count = (
        sum(len(c["items"]) for c in live["categories"]) if live.get("status") == "ok" else -1
    )
    oc_rows = q("SELECT count(*) FROM ownership_checks WHERE asset_id='AST-L3-LIFT'")[0]
    oc_neg1, oc_neg2 = False, False
    try:
        con.execute(
            "INSERT INTO ownership_checks (asset_id, category, check_item, state, evidence_ref,"
            " limit_note, checked_at) VALUES (?,?,?,?,?,?,?)",
            ("AST-L3-LIFT", "테스트", "음성검사①", "VERIFIED", None,
             "state=VERIFIED 인데 limit_note 채움 — 거부돼야 함", "2026-01-01 00:00:00"),
        )
    except sqlite3.IntegrityError:
        oc_neg1 = True
    try:
        con.execute(
            "INSERT INTO ownership_checks (asset_id, category, check_item, state, evidence_ref,"
            " limit_note, checked_at) VALUES (?,?,?,?,?,?,?)",
            ("AST-L3-LIFT", "테스트", "음성검사②",
             "UNVERIFIED", "state=UNVERIFIED 인데 evidence_ref 채움 — 거부돼야 함", None,
             "2026-01-01 00:00:00"),
        )
    except sqlite3.IntegrityError:
        oc_neg2 = True
    check(
        "㉞ ownership_checks 행수=verify_ownership 실측 · either-or CHECK 음성 (S18, D68)",
        oc_rows == live_item_count and oc_neg1 and oc_neg2,
        f"DB행수={oc_rows} · verify_ownership(AST-L3-LIFT) 실측 항목수={live_item_count}"
        f" · [음성①] VERIFIED+limit_note 동시 채움 → "
        + ("거부됨" if oc_neg1 else "거부 안 됨 (FAIL)")
        + " · [음성②] UNVERIFIED+evidence_ref 동시 채움 → "
        + ("거부됨" if oc_neg2 else "거부 안 됨 (FAIL)"),
    )

    # ㉟ risk_profile — 4행 · building_id 집합 == assets.building_id distinct (동적 대조) ·
    #    점수식 재계산이 시드 표(sprint-11.md §6)와 일치 (Sprint 11, self-check 전용 §_RISK_LEVEL_SCORE)
    rp_rows = con.execute(
        "SELECT building_id, fire_handling, hazmat_volume, power_capacity, risk_grade"
        " FROM risk_profile"
    ).fetchall()
    rp_bld = {r[0] for r in rp_rows}
    assets_bld = {
        r[0]
        for r in con.execute(
            "SELECT DISTINCT building_id FROM assets WHERE building_id IS NOT NULL"
        ).fetchall()
    }
    recompute_mismatch = []
    for building_id, fire, hazmat, power, stored_grade in rp_rows:
        score = _RISK_LEVEL_SCORE[fire] + _RISK_LEVEL_SCORE[hazmat] + _RISK_LEVEL_SCORE[power]
        computed = _risk_grade_from_score(score)
        expected_row = next(r for r in RISK_PROFILE if r["building_id"] == building_id)
        if computed != expected_row["stored_grade"] and building_id != "BLD-C":
            # BLD-C 는 의도적 불일치(데모) — 그 외 3건은 저장값과 재계산이 일치해야 한다
            recompute_mismatch.append((building_id, score, computed, stored_grade))
        if building_id == "BLD-C" and computed == stored_grade:
            # BLD-C 데모가 깨졌다면(우연히 일치) 그것도 실패로 잡는다
            recompute_mismatch.append((building_id, score, computed, stored_grade, "데모 불일치 소실"))
    check(
        "㉟ risk_profile 4행 · building_id 동적 대조 · 점수식 재계산 (Sprint 11, self-check)",
        len(rp_rows) == 4 and rp_bld == assets_bld and not recompute_mismatch,
        f"행수={len(rp_rows)}(기대 4) · building_id={sorted(rp_bld)} vs assets={sorted(assets_bld)}"
        f" · 재계산 불일치={recompute_mismatch}"
        f" · BLD-C stored=LOW/computed=HIGH 가 의도된 형태(데모)",
    )

    # ㊱ error_codes IE5 5건 병합 검증 (Sprint 15 MQ-1507). data/merge_ie5_codes.py 가
    #    IE5 트립 코드 5건을 정본 error_codes.json 에 병합했다(65→70). 여기서는 model='IE5'
    #    행이 정확히 5건이고(양성 축) 그중 causes/actions 가 빈 배열인 행이 없는지(음성 축)
    #    실측한다. `--with-error-codes` 없이 실행하면 0행이 정상 — 이때는 FAIL 이 아니라
    #    통과시킨다(㉘·㉚ 와 같은 태도).
    ie5_rows = q("SELECT count(*) FROM error_codes WHERE model='IE5'")[0]
    ie5_empty = q(
        "SELECT count(*) FROM error_codes WHERE model='IE5'"
        " AND (json_array_length(causes)=0 OR json_array_length(actions)=0)"
    )[0]
    check(
        "㊱ error_codes IE5 5건 병합 검증 (Sprint 15 MQ-1507)",
        (ie5_rows == 5 and ie5_empty == 0) if with_codes else (ie5_rows == 0),
        f"IE5 행수={ie5_rows}(기대 5) · causes/actions 빈 값={ie5_empty}건"
        + ("" if with_codes else " (게이트: --with-error-codes 없음 — 0행이 정상, FAIL 아님)"),
    )

    # ㊲ po_drafts.state CHECK 확장 — finance_approved/finance_rejected 허용, 임의 문자열 거부
    #    (Sprint 17 MQ-1702). 성공 케이스(2.의 INSERT 통과)는 count 로 확인하고, 실패 케이스는
    #    실제로 UPDATE 를 시도해 SAVEPOINT 안에서 되돌린다.
    finance_state_cnt = q(
        "SELECT count(*) FROM po_drafts WHERE state IN ('finance_approved','finance_rejected')"
    )[0]
    con.execute("SAVEPOINT check_state_bogus")
    bogus_detail = "UPDATE 가 통과해버림 (CHECK 미적용?)"
    try:
        con.execute("UPDATE po_drafts SET state='bogus_state' WHERE po_id='PO-0117'")
        bogus_rejected = False
    except sqlite3.IntegrityError as exc:
        bogus_rejected, bogus_detail = True, str(exc)
    finally:
        con.execute("ROLLBACK TO check_state_bogus")
        con.execute("RELEASE check_state_bogus")
        con.commit()
    check(
        "㊲ po_drafts.state CHECK 확장 — finance_* 허용·임의값 거부 (Sprint 17 MQ-1702)",
        finance_state_cnt == 2 and bogus_rejected,
        f"finance_* 상태 행수={finance_state_cnt}(기대 2) · bogus_state 거부={bogus_rejected} · {bogus_detail}",
    )

    # ㊳ decided_at 불변식 — approved/rejected/finance_approved/finance_rejected 인 행은
    #    decided_at 이 NULL 이면 안 된다 (Sprint 17 MQ-1702, 기존 gap 메움).
    decided_at_gap = q(
        "SELECT count(*) FROM po_drafts WHERE state IN"
        " ('approved','rejected','finance_approved','finance_rejected') AND decided_at IS NULL"
    )[0]
    check(
        "㊳ decided_at 불변식 — 결정된 발주는 decided_at NOT NULL (Sprint 17 MQ-1702)",
        decided_at_gap == 0,
        f"decided_at 누락 행수={decided_at_gap}(기대 0)",
    )

    # ㊴ PO-0118/PO-0119 재무 결정 표본 컬럼 완비 (Sprint 17 MQ-1702)
    finance_sample_rows = con.execute(
        "SELECT po_id, finance_decided_by, finance_decision_note, finance_decided_at"
        " FROM po_drafts WHERE po_id IN ('PO-0118','PO-0119') ORDER BY po_id"
    ).fetchall()
    finance_sample_ok = len(finance_sample_rows) == 2 and all(
        r[1] == "mgr-02" and r[2] and r[3] for r in finance_sample_rows
    )
    check(
        "㊴ PO-0118/PO-0119 finance_decided_by='mgr-02' + note·decided_at 완비 (Sprint 17 MQ-1702)",
        finance_sample_ok,
        f"표본={finance_sample_rows}",
    )

    # ㊵ finance_decided_by FK 무결성 probe — 유령 사용자 ID 거부 확인 (Sprint 17 MQ-1702,
    #    ⑩ fk_probe 와 같은 패턴, SAVEPOINT 이름만 분리)
    con.execute("SAVEPOINT fk_probe_finance")
    fin_fk_detail = "INSERT 가 통과해버림 (FK 미적용?)"
    try:
        con.execute(
            "INSERT INTO po_drafts (po_id, part_no, qty, supplier_id, unit_price, reason,"
            " requested_by, state, decided_by, decided_at, finance_decided_by) VALUES"
            " ('PO-FK01','FAN-IG5-01',1,'SUP-A',1000,'재무 FK 검증','tech-01','approved',"
            " 'mgr-01','2026-08-09 00:00:00','ghost-99')"
        )
        fin_fk_rejected = False
    except sqlite3.IntegrityError as exc:
        fin_fk_rejected, fin_fk_detail = True, str(exc)
    finally:
        con.execute("ROLLBACK TO fk_probe_finance")
        con.execute("RELEASE fk_probe_finance")
        con.commit()
    check(
        "㊵ 미등록 finance_decided_by → FK 거부 (Sprint 17 MQ-1702)",
        fin_fk_rejected,
        fin_fk_detail,
    )

    # ㊶ policy_id 는 InsuQ 발급 체계를 그대로 적는다 — 접두사가 **상품별로 2~3글자**다
    #    (SB 수퍼비즈니스 · DS 동산종합 · SBP 삼성비지니스패키지).
    #    ⚠ 부재 검사라 **양성 축을 함께 건다** (CLAUDE.md 규약) — `bad == 0` 만 보면
    #      쿼리가 0행을 돌려줘도 통과한다. 스캔된 행 수와 **접두사 종류 수**를 판정에 넣는다.
    #      접두사를 2글자로 가정해 짜면 SBP 하나만 빠지는데, 종류 수 축이 그걸 잡는다.
    pol_rows = con.execute(
        "SELECT asset_id, policy_id FROM assets WHERE policy_id IS NOT NULL"
    ).fetchall()
    pol_re = re.compile(r"^[A-Z]{2,3}-\d{4}-\d{4}$")
    pol_bad = [f"{r['asset_id']}={r['policy_id']}" for r in pol_rows if not pol_re.match(r["policy_id"])]
    pol_prefixes = {r["policy_id"].split("-")[0] for r in pol_rows}
    check(
        "㊶ policy_id 형식 [A-Z]{2,3}-NNNN-NNNN + 접두사 3종 생존 (InsuQ 발급 체계)",
        not pol_bad and len(pol_rows) == 8 and pol_prefixes == {"SB", "DS", "SBP"},
        f"스캔 {len(pol_rows)}행 · 위반 {len(pol_bad)}건{' ' + str(pol_bad) if pol_bad else ''}"
        f" · 접두사 {sorted(pol_prefixes)}",
    )

    # ㊷ 건물 ↔ 증권 매핑이 InsuQ 표와 **행 단위로** 일치하는가.
    #    InsuQ 쪽 해소는 2단계다(파트너 건물 매핑 → 사업장+증권 동시 조회). 둘 중 무엇이
    #    실패해도 응답은 똑같이 `policy_not_found` 라 **응답으로는 원인을 못 가른다** —
    #    그래서 우리 쪽에서 미리 고정한다. 출처: InsuQ 세션 회신 (2026-09-16).
    insuq_map = {
        "BLD-A": "SB-2023-0001",
        "BLD-B": "DS-2024-0002",
        "BLD-C": "SBP-2022-0003",
        "BLD-D": "SB-2024-0004",
    }
    pair_rows = con.execute(
        "SELECT building_id, policy_id, count(*) AS n FROM assets"
        " WHERE policy_id IS NOT NULL GROUP BY building_id, policy_id"
    ).fetchall()
    pair_bad = [
        f"{r['building_id']}→{r['policy_id']}"
        for r in pair_rows
        if insuq_map.get(r["building_id"]) != r["policy_id"]
    ]
    check(
        "㊷ 건물↔증권 매핑이 InsuQ 발급표와 일치 (엇갈리면 policy_not_found)",
        not pair_bad and len(pair_rows) == 4,
        f"짝 {len(pair_rows)}종 · 불일치 {len(pair_bad)}건{' ' + str(pair_bad) if pair_bad else ''}"
        f" · {[(r['building_id'], r['policy_id'], r['n']) for r in pair_rows]}",
    )

    return results


# ────────────────────────────────────────────────────────────── main


def main() -> None:
    # Windows 기본 콘솔은 cp949 — 한글·em dash 출력이 깨진다
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="MaintQ 목업 DB 시드")
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument(
        "--with-error-codes",
        action="store_true",
        help="error_codes 적재 (iG5A 매핑 사람 승인 후에만)",
    )
    ap.add_argument(
        "--today",
        type=date.fromisoformat,
        default=datetime.now(timezone.utc).date(),
        help="이력 생성 기준일 (YYYY-MM-DD, UTC). 재현용",
    )
    args = ap.parse_args()

    rng = random.Random(RNG_SEED)

    can_load, why = error_codes_gate()
    with_codes = args.with_error_codes and can_load
    if args.with_error_codes and not can_load:
        sys.exit(f"[중단] --with-error-codes 요청했지만 적재할 수 없습니다: {why}")

    if dbcompat.USE_POSTGRES:
        print(f"[대상] Postgres — {dbcompat.DATABASE_URL}")
    elif args.db.exists():
        backup = args.db.with_suffix(".db.bak")
        shutil.copy2(args.db, backup)
        args.db.unlink()
        print(f"[백업] 기존 DB → {backup.name}")

    # `allow_sqlite=True` 는 의도 표명이다 (D130) — `DATABASE_URL` 이 있으면 그쪽이
    # 우선이고 이 인자는 무시된다. 없을 때만 `args.db` 에 SQLite 파일을 만든다:
    # 시드 스크립트는 **픽스처 DB 를 만드는 것이 기능**이라 폴백이 정당한 유일한 자리다.
    con = dbcompat.connect(args.db, allow_sqlite=True)
    con.execute("PRAGMA foreign_keys=ON")  # 기본 OFF — 안 켜면 D33 FK가 무력화됨 (Postgres 는 무시됨)
    try:
        create_schema(con)
        seed_users(con)  # ← po_drafts·error_history 보다 먼저 (FK, D41)
        acquired = seed_assets(con, args.today)  # ← equipment.asset_id 보다 먼저 (FK, D68)
        # ← assets 직후. subject_ref 가 building_id 를 참조하는 결이라 자산이 먼저다 (D92).
        #   기준 시각은 `--today` 가 아니라 **실제 UTC 현재 시각** — seed_partner_links 독스트링 참조
        n_links = seed_partner_links(con, datetime.now(timezone.utc))
        # ← assets 직후. §21~§23 은 asset_id/building_id 를 참조하는 결이라 자산이 먼저다 (D68).
        n_incidents = seed_incidents(con, args.today)
        n_ownership_checks = seed_ownership_checks(con, args.today)
        n_risk_profile = seed_risk_profile(con, args.today)
        seed_masters(con)
        n_lifecycle = seed_part_lifecycle_mock(con, args.today)
        seed_inventory(con, rng)
        seed_supplier_parts(con, rng)
        seed_error_history(con, rng, args.today)

        # ── 근거 계층 (D60·D61). 파일이 정본, DB 는 사본이다
        try:
            n_laws, n_rules = seed_rule_catalog(con)
        except Exception as exc:  # RuleIntegrityError 포함 — 부분 적재 DB 를 남기지 않는다
            con.rollback()
            con.close()
            if not dbcompat.USE_POSTGRES:
                args.db.unlink(missing_ok=True)
            sys.exit(f"[중단] 룰 카탈로그 적재 실패 — {type(exc).__name__}: {exc}")
        print(f"[근거계층] law_refs {n_laws}행 · rules {n_rules}행 (load_rules 무결성 게이트 통과)")

        n_curve, curve_note = seed_residual_curve(con)
        if n_curve:
            print(f"[잔가곡선] residual_curve {n_curve}행 — {curve_note}")
        else:
            print(f"[잔가곡선] 적재 0행 ⚠ {curve_note}")

        print(f"[생애주기 목업] part_lifecycle_mock {n_lifecycle}행 (D — mock, 실 텔레메트리 아님)")

        if with_codes:
            total, mapped = load_error_codes(con)
            print(f"[error_codes] {total}건 적재 · related_parts 매핑 {mapped}건")
            print(f"  {related_parts_caveat()}")
        else:
            print(f"[error_codes] 적재 건너뜀 — {why}")
            print("  → 승인 후 실행: uv run python data/seed.py --with-error-codes")

        seed_po_drafts(con, with_codes)
        seed_repair_records(con, with_codes, args.today)
        con.commit()

        print(f"[파트너대장] partner_links {n_links}행 (D92 — 목업 전제, 표 뒤 고지 참조)")
        print(
            f"[자산 생애주기 확장] incidents {n_incidents}행 · ownership_checks {n_ownership_checks}행"
            f" · risk_profile {n_risk_profile}행 · deadlines 0행(쓰기 경로 없음) (Sprint 11, MQ-1101)"
        )

        print(f"\n[기준일] {args.today}  (반복 고장 3건 = 기준일 -22/-12/-4일)")
        print(f"[완료] {args.db}\n")

        print("자산 배치 (asset_id · category · acquired_at · age→bucket)")
        for a in ASSETS:
            probe = DISPOSAL_PROBE_MONTHS.get(a["asset_id"])
            hint = (
                f" · 처분 프로브 disposal_date={_shift_months(date.fromisoformat(acquired[a['asset_id']]), probe)}"
                f" (취득 후 {probe}개월)"
                if probe
                else ""
            )
            print(
                f"  {a['asset_id']:<13} {a['category']!r:<16} {acquired[a['asset_id']]}"
                f"  age={a['age_years']:>2}{hint}"
            )
        print()

        results = verify(con, with_codes, args.db)
        width = max(len(n) for n, _, _ in results)
        print("시드 케이스 맵 검증")
        print("─" * (width + 46))
        for name, ok, detail in results:
            print(f"  {'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail}")
        print("─" * (width + 46))

        failed = [n for n, ok, _ in results if not ok]
        if failed:
            sys.exit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
        print(f"\n전부 통과 ({len(results)}건)")
        # 사람 검수 항목은 통과 표 **뒤에** 찍는다 — PASS 로 덮이면 아무도 안 본다 (D12)
        # ⚠ 라벨도 상태에서 유도한다. 하드코딩하면 검수가 끝난 뒤 "[사람 검수 대기] ✓ 검수 완료"
        #   처럼 자기모순 문구가 나온다 — part_class_caveat() 독스트링이 경계한 그 함정이다.
        caveat = part_class_caveat()
        print(f"\n[{'사람 검수' if caveat.startswith('✓') else '사람 검수 대기'}] {caveat}")
        pl_caveat = partner_links_caveat()
        print(f"[{'사람 확인' if pl_caveat.startswith('✓') else '사람 확인 대기'}] {pl_caveat}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
