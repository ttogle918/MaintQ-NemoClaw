# -*- coding: utf-8 -*-
"""목업 DB 시드 (M1) — docs/05_DB_SCHEMA.md의 스키마와 시드 케이스 맵 7종을 구현한다.

출력 : data/maintq.db (기존 파일은 .bak 으로 백업 후 재생성)
검증 : 실행 끝에 케이스 맵 7종(①~⑧) + D41 스키마 보강(⑨~⑪)을 SQL로 자가 검증하고
       통과/실패 표를 출력

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
import shutil
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent  # data/
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
  PRIMARY KEY (model, code),
  CHECK (severity IN ('warning','fault','critical')),
  -- code 형식 (D33): 대문자·숫자·언더스코어 2~4자
  CHECK (length(code) BETWEEN 2 AND 4
         AND code = upper(code)
         AND code NOT GLOB '*[^A-Z0-9_]*')
);

-- 사용자 (D41·D52) — X-User 헤더 값의 원천이자 표시명 매핑 소스.
-- 표시명이 backend/services/po.py 에 하드코딩돼 있던 것을 여기로 옮겼다 (D36→D41).
-- 행을 지우지 않는다: 퇴사자는 active=0. decided_by 가 끊기면 감사 추적(P5)이 무너진다.
CREATE TABLE users (
  user_id       TEXT PRIMARY KEY,         -- 'tech-01' — 헤더로 오가는 ASCII ID (D36)
  email         TEXT UNIQUE,              -- 회사 이메일. 향후 IdP 매칭 키 (D52)
  display_name  TEXT NOT NULL,            -- '김OO' — 화면 표시용
  role          TEXT NOT NULL,            -- 회사가 사전 부여. OAuth 가 정하지 않는다 (D52)
  auth_provider TEXT NOT NULL DEFAULT 'local',
  external_id   TEXT,                     -- IdP 의 sub/oid. 연동 전 NULL
  active        BOOLEAN NOT NULL DEFAULT 1,
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  CHECK (role IN ('technician','manager')),
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
  policy_id                TEXT,
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
  part_class   TEXT                       -- 'CONSUMABLE' | 'CRITICAL' (12 §9). ⚠ 미검수 초안 (D12)
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
  supplier_id  TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  contact      TEXT
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
  FOREIGN KEY (model, error_code) REFERENCES error_codes(model, code),
  CHECK (state IN ('draft','pending','approved','rejected')),
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
  -- 도구 결과 **원본** JSON (D77-2). `tool_result` 행에만 들어가므로 nullable.
  -- ⛔ payload 를 재사용하지 않는 이유: payload 는 **SSE data 와 바이트 동일**이 계약이고
  --    (D30) trace_persist ② · sp3_sse_events ⑬ 이 바이트 단위로 대조한다. 여기에 원본을
  --    섞으면 평가의 두 소스 대조가 조용히 깨진다.
  -- ⚠ 이 스프린트는 **컬럼만** 만든다. 값을 쓰는 쪽(backend/agent/trace.py)은 D77-2 담당.
  tool_payload TEXT,
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

-- §14 decisions — 계층 3 서명. **쓰기 경로는 Sprint 7** (D10 태도 유지: 도구는 못 쓴다)
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
  FOREIGN KEY (model, error_code) REFERENCES error_codes(model, code),  -- D13·D33
  CHECK (work_type IN ('PLANNED','UNPLANNED')),
  CHECK ((model IS NULL) = (error_code IS NULL)),
  CHECK (parts IS NULL OR json_valid(parts)),
  CHECK (expenditure_class IS NULL OR expenditure_class IN ('CAPITAL','REVENUE','HOLD'))
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
"""

# ────────────────────────────────────────────────────────────── 마스터 데이터

# (user_id, email, display_name, role, auth_provider) — D41·D52
# auth_provider 는 전부 'local' : 회사 IdP 연동(google)은 백로그 P21 이고, 개인 소셜은 넣지 않는다.
# 이메일은 회사 도메인 형식 예시 (.example 은 RFC 2606 예약 도메인 — 실제로 발송되지 않는다)
USERS = [
    ("tech-01", "kim@maintq.example", "김OO", "technician", "local"),
    ("tech-02", "lee@maintq.example", "이OO", "technician", "local"),
    ("mgr-01", "park@maintq.example", "박OO", "manager", "local"),
]

SUPPLIERS = [
    ("SUP-A", "에이스산전", "02-555-0101 / sales@acesanjeon.example"),
    ("SUP-B", "비전파츠", "031-777-0202 / order@visionparts.example"),
    ("SUP-C", "대한전기자재", "051-333-0303 / cs@daehan-elec.example"),
    ("SUP-D", "한빛오토메이션", "032-999-0404 / help@hanbit-auto.example"),
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
PART_CLASS_REVIEWED = False

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
        "policy_id": "POL-2026-FIRE-01",
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
        "policy_id": "POL-2026-FIRE-01",
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
        "policy_id": "POL-2026-FIRE-01",
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
        "policy_id": "POL-2026-FIRE-01",
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
        "policy_id": "POL-2026-FIRE-01",
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
        # 처분 시나리오: 전 사실 채움·무해당 → CLEAR 기대
        "tax_credit_applied": 0,
        "has_lien": 0,
        "policy_id": "POL-2026-FIRE-01",
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
        "policy_id": "POL-2026-FIRE-01",
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
        "policy_id": "POL-2026-FIRE-01",
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
        "policy_id": "POL-2026-FIRE-01",
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
        ["BRG-6205", "CPL-JAW-01"],
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


# ────────────────────────────────────────────────────────────── 적재


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)


def seed_users(con: sqlite3.Connection) -> None:
    """**가장 먼저** 적재한다 — po_drafts.requested_by/decided_by 와 error_history.recorded_by 가
    FK 로 이 테이블을 참조한다 (D41). `PRAGMA foreign_keys=ON` 상태라 순서가 틀리면 즉시 실패한다.
    """
    con.executemany(
        "INSERT INTO users (user_id, email, display_name, role, auth_provider) VALUES (?,?,?,?,?)",
        USERS,
    )


def seed_masters(con: sqlite3.Connection) -> None:
    """⚠ `seed_assets` 보다 **뒤에** 호출한다 — equipment.asset_id 가 assets 를 참조한다 (D68)."""
    missing = [p for p, *_ in PARTS if p not in PART_CLASS]
    if missing:
        # 부품 등급을 도구가 추측하면 3지 판단이 근거를 잃는다 (D12). 누락은 조용히 넘기지 않는다
        sys.exit(f"[중단] parts.part_class 미지정: {missing}")

    con.executemany("INSERT INTO suppliers VALUES (?,?,?)", SUPPLIERS)
    con.executemany(
        "INSERT INTO parts VALUES (?,?,?,?,?,?)",
        [(p, n, c, json.dumps(m, ensure_ascii=False), d, PART_CLASS[p]) for p, n, c, m, d in PARTS],
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


def seed_assets(con: sqlite3.Connection, today: date) -> dict[str, str]:
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
        " lien_consent_ref, policy_id, safety_inspection_target, last_inspection_date,"
        " inspection_valid_until, cumulative_repair_cost, last_overhaul_at,"
        " controller_generation, parts_eol_flag)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    return acquired


def seed_repair_records(con: sqlite3.Connection, with_codes: bool, today: date) -> None:
    """수리 증빙 12건. 쓰기 경로는 Sprint 7 이고 여기서는 시드만 넣는다.

    `--with-error-codes` 없이 실행하면 `error_codes` 가 0행이라 `(model, error_code)`
    복합 FK 를 만족시킬 수 없다 → 둘 다 NULL (`seed_po_drafts` 선례 그대로).
    DDL 의 `CHECK ((model IS NULL) = (error_code IS NULL))` 이 짝을 강제한다.

    `record_hash` 는 전 행 NULL 이다 — 서명 해시 규약(정렬·구분자 고정)은 Sprint 7 의
    서명 API 와 `build_evidence_bundle` 이 함께 정한다. 지금 임의 규약을 심으면
    나중에 검증이 조용히 어긋난다.
    """
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
        # 서명 시각은 실행일 기준 상대값 (UTC, D39)
        signed_at = (
            datetime.combine(today - timedelta(days=20 + i * 17), datetime.min.time())
            .replace(tzinfo=timezone.utc)
            .strftime("%Y-%m-%d %H:%M:%S")
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
                json.dumps(parts, ensure_ascii=False),
                performed_by,
                verified_by,
                signed_at,
                None,
                "signed" if signed else "draft",
            )
        )
    con.executemany(
        "INSERT INTO repair_records (repair_id, equipment_id, model, error_code, part_class,"
        " work_type, expenditure_class, cost, downtime_hours, parts, performed_by, verified_by,"
        " signed_at, record_hash, state) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )


def seed_rule_catalog(con: sqlite3.Connection) -> tuple[int, int]:
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


def seed_residual_curve(con: sqlite3.Connection) -> tuple[int, str]:
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


def seed_inventory(con: sqlite3.Connection, rng: random.Random) -> None:
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


def seed_supplier_parts(con: sqlite3.Connection, rng: random.Random) -> None:
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


def seed_error_history(con: sqlite3.Connection, rng: random.Random, today: date) -> None:
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


def seed_po_drafts(con: sqlite3.Connection, with_codes: bool) -> None:
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
    #  reason, urgency, state, requested_by, decided_by, decision_note, session_id)
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
        ),
    ]
    if not with_codes:
        # error_codes 가 비어 있으면 FK를 만족할 수 없다 → 코드 필드를 비운다
        rows = [r[:4] + (None, None) + r[6:] for r in rows]

    con.executemany(
        "INSERT INTO po_drafts (po_id, part_no, qty, supplier_id, model, error_code,"
        " evidence, unit_price, reason, urgency, state, requested_by, decided_by,"
        " decision_note, session_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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


def load_error_codes(con: sqlite3.Connection) -> tuple[int, int]:
    """추출 JSON → error_codes. related_parts 는 임시 매핑 파일로 덧씌운다 (검수 전)."""
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
            )
        )
    con.executemany("INSERT INTO error_codes VALUES (?,?,?,?,?,?,?,?,?)", rows)
    return len(rows), mapped


# ────────────────────────────────────────────────────────────── 검증


def verify(con: sqlite3.Connection, with_codes: bool, db_path: Path) -> list[tuple[str, bool, str]]:
    """docs/05_DB_SCHEMA.md 시드 케이스 맵 7종(⑧까지) + D41 스키마 보강(⑨~⑪) 자가 검증."""
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
    users = con.execute("SELECT user_id, display_name, role FROM users ORDER BY user_id").fetchall()
    check(
        "⑨ users 3행 적재 (D41)",
        users
        == [
            ("mgr-01", "박OO", "manager"),
            ("tech-01", "김OO", "technician"),
            ("tech-02", "이OO", "technician"),
        ],
        f"{len(users)}행 {[u[0] for u in users]}",
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

    dn = display_name("tech-01", db_path=db_path)
    unknown = display_name("ghost-99", db_path=db_path)
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

    if args.db.exists():
        backup = args.db.with_suffix(".db.bak")
        shutil.copy2(args.db, backup)
        args.db.unlink()
        print(f"[백업] 기존 DB → {backup.name}")

    con = sqlite3.connect(args.db)
    con.execute("PRAGMA foreign_keys=ON")  # 기본 OFF — 안 켜면 D33 FK가 무력화됨
    try:
        create_schema(con)
        seed_users(con)  # ← po_drafts·error_history 보다 먼저 (FK, D41)
        acquired = seed_assets(con, args.today)  # ← equipment.asset_id 보다 먼저 (FK, D68)
        seed_masters(con)
        seed_inventory(con, rng)
        seed_supplier_parts(con, rng)
        seed_error_history(con, rng, args.today)

        # ── 근거 계층 (D60·D61). 파일이 정본, DB 는 사본이다
        try:
            n_laws, n_rules = seed_rule_catalog(con)
        except Exception as exc:  # RuleIntegrityError 포함 — 부분 적재 DB 를 남기지 않는다
            con.rollback()
            con.close()
            args.db.unlink(missing_ok=True)
            sys.exit(f"[중단] 룰 카탈로그 적재 실패 — {type(exc).__name__}: {exc}")
        print(f"[근거계층] law_refs {n_laws}행 · rules {n_rules}행 (load_rules 무결성 게이트 통과)")

        n_curve, curve_note = seed_residual_curve(con)
        if n_curve:
            print(f"[잔가곡선] residual_curve {n_curve}행 — {curve_note}")
        else:
            print(f"[잔가곡선] 적재 0행 ⚠ {curve_note}")

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
        # 사람 검수 대기 항목은 통과 표 **뒤에** 찍는다 — PASS 로 덮이면 아무도 안 본다 (D12)
        print(f"\n[사람 검수 대기] {part_class_caveat()}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
