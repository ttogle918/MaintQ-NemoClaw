# -*- coding: utf-8 -*-
"""목업 DB 시드 (M1) — docs/05_DB_SCHEMA.md의 스키마와 시드 케이스 맵 7종을 구현한다.

출력 : data/maintq.db (기존 파일은 .bak 으로 백업 후 재생성)
검증 : 실행 끝에 케이스 맵 7종을 SQL로 자가 검증하고 통과/실패 표를 출력

원칙
  - `PRAGMA foreign_keys=ON` 필수 (기본 OFF, 안 켜면 D33의 FK 보증이 조용히 사라짐)
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
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent  # data/
EXTRACTED = ROOT / "extracted"
ERROR_CODES_JSON = EXTRACTED / "error_codes.json"
RELATED_PARTS_JSON = ROOT / "related_parts.seed.json"
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

CREATE TABLE equipment (
  equipment_id TEXT PRIMARY KEY,
  line_id      INTEGER NOT NULL,
  model        TEXT NOT NULL,
  installed_at DATE,
  location     TEXT,
  CHECK (model IN ('iG5A','S100'))
);

CREATE TABLE error_history (
  id           INTEGER PRIMARY KEY,
  equipment_id TEXT NOT NULL REFERENCES equipment,
  code         TEXT NOT NULL,             -- 대문자 canonical (D25)
  occurred_at  DATETIME NOT NULL,
  action_taken TEXT,
  part_replaced TEXT,
  resolved     BOOLEAN DEFAULT 1
);
CREATE INDEX idx_history_eq_code ON error_history(equipment_id, code, occurred_at);

CREATE TABLE parts (
  part_no      TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  category     TEXT,
  compatible_models TEXT NOT NULL,        -- JSON array
  discontinued BOOLEAN DEFAULT 0
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
  requested_by TEXT,
  decided_by   TEXT,
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
  ts           DATETIME DEFAULT CURRENT_TIMESTAMP,
  CHECK (event_type IN ('tool_call','tool_result','block'))
);
CREATE INDEX idx_traces_session ON traces(session_id, seq);
"""

# ────────────────────────────────────────────────────────────── 마스터 데이터

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

EQUIPMENT = [
    ("INV-L1-01", 1, "iG5A", "2021-04-12", "1번 조립라인 분전반"),
    ("INV-L1-02", 1, "iG5A", "2021-04-12", "1번 조립라인 컨베이어"),
    ("INV-L2-01", 2, "S100", "2022-09-30", "2번 가공라인 주축"),
    ("INV-L2-02", 2, "S100", "2022-09-30", "2번 가공라인 절삭유 펌프"),
    ("INV-L3-01", 3, "iG5A", "2020-11-05", "3번 조립라인 반송 컨베이어"),
    ("INV-L3-02", 3, "iG5A", "2020-11-05", "3번 조립라인 배기팬"),
    ("INV-L3-03", 3, "S100", "2023-02-17", "3번 조립라인 리프터"),
    ("INV-L4-01", 4, "S100", "2023-06-01", "4번 포장라인 컨베이어"),
    ("INV-L4-02", 4, "S100", "2023-06-01", "4번 포장라인 랩핑기"),
    ("INV-L4-03", 4, "iG5A", "2019-08-22", "4번 포장라인 집진기"),
]

# 이력 생성에 쓰는 코드 (추출 결과에 실재하는 코드만 — 대문자 canonical, D25)
CODES_BY_MODEL = {
    "iG5A": ["OCT", "OHT", "OLT", "LVT", "GFT", "FAN"],
    "S100": ["OCT", "OHT", "LVT", "OVT", "FAN", "NTC"],
}

# 고장 유형 분포 참고: AI허브 「기계시설물 고장 예지 센서」 4종 분포 (D16)
ACTIONS = ["리셋", "냉각팬 청소", "단자 재조임", "부품 교체", "파라미터 재설정", "배선 점검"]

PART_BY_ACTION = {
    "부품 교체": ["FAN-IG5-01", "FUSE-30A", "CAP-DC-450", "BRG-6205", "BLT-V-A50"],
}


# ────────────────────────────────────────────────────────────── 적재


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)


def seed_masters(con: sqlite3.Connection) -> None:
    con.executemany("INSERT INTO suppliers VALUES (?,?,?)", SUPPLIERS)
    con.executemany(
        "INSERT INTO parts VALUES (?,?,?,?,?)",
        [(p, n, c, json.dumps(m, ensure_ascii=False), d) for p, n, c, m, d in PARTS],
    )
    con.executemany("INSERT INTO equipment VALUES (?,?,?,?,?)", EQUIPMENT)
    con.executemany("INSERT INTO part_alternatives VALUES (?,?,?,?)", ALTERNATIVES)


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
    """6개월치 이력 ~200건. 대부분 단발, INV-L3-01의 OCT만 30일 내 3건 (S3 트리거)."""
    rows: list[tuple] = []

    # ── S3 케이스: 실행일 기준 상대 날짜 (하드코딩 금지)
    #    today=2026-07-23 이면 07-01 / 07-11 / 07-19 — 문서·UI의 예시와 일치
    for days_ago in (22, 12, 4):
        occurred = datetime.combine(today - timedelta(days=days_ago), datetime.min.time())
        occurred += timedelta(hours=rng.randint(8, 18), minutes=rng.randint(0, 59))
        rows.append(("INV-L3-01", "OCT", occurred.isoformat(sep=" "), "리셋", None, 1))

    # ── 나머지: 6개월치 잡음. S3 케이스를 오염시키지 않도록 제약을 건다
    target = 200
    while len(rows) < target:
        eq_id, _line, model, *_ = rng.choice(EQUIPMENT)
        code = rng.choice(CODES_BY_MODEL[model])
        days_ago = rng.randint(4, 180)
        # INV-L3-01 + OCT 조합은 최근 30일 안에 추가로 만들지 않는다 (count 정확히 3)
        if eq_id == "INV-L3-01" and code == "OCT" and days_ago <= 30:
            continue
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
    """화면 B 승인 큐용. 에러코드 FK는 error_codes 적재 여부에 따라 채운다 (D33)."""
    evidence_0117 = {
        "symptoms": ["냉각팬 소음 증가", "3번 라인 2회 정지"],
        "basis": [
            {"tool": "lookup_error_code", "code": "OHT", "manual_page": 202},
            {"tool": "search_inventory", "part_no": "FAN-IG5-01", "qty": 1, "safety_stock": 3},
        ],
        "notes": "야간조 정비사 육안 확인 — 팬 회전 불량",
    }
    # (po_id, part_no, qty, supplier_id, model, code, evidence, unit_price,
    #  reason, urgency, state, requested_by, decided_by, session_id)
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
            "김OO",
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
            "이OO",
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
            "김OO",
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
            "김OO",
            "박OO",
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
            "이OO",
            "박OO",
            None,
        ),
    ]
    if not with_codes:
        # error_codes 가 비어 있으면 FK를 만족할 수 없다 → 코드 필드를 비운다
        rows = [r[:4] + (None, None) + r[6:] for r in rows]

    con.executemany(
        "INSERT INTO po_drafts (po_id, part_no, qty, supplier_id, model, error_code,"
        " evidence, unit_price, reason, urgency, state, requested_by, decided_by,"
        " session_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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


def verify(con: sqlite3.Connection, with_codes: bool) -> list[tuple[str, bool, str]]:
    """docs/05_DB_SCHEMA.md 시드 케이스 맵 7종 자가 검증."""
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
        default=date.today(),
        help="이력 생성 기준일 (YYYY-MM-DD). 재현용",
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
        seed_masters(con)
        seed_inventory(con, rng)
        seed_supplier_parts(con, rng)
        seed_error_history(con, rng, args.today)

        if with_codes:
            total, mapped = load_error_codes(con)
            print(f"[error_codes] {total}건 적재 · related_parts 임시 매핑 {mapped}건")
            print("  ⚠ related_parts 는 사람 검수 전 임시값 — 평가 결과를 실적으로 인용하지 말 것")
        else:
            print(f"[error_codes] 적재 건너뜀 — {why}")
            print("  → 승인 후 실행: uv run python data/seed.py --with-error-codes")

        seed_po_drafts(con, with_codes)
        con.commit()

        print(f"\n[기준일] {args.today}  (반복 고장 3건 = 기준일 -22/-12/-4일)")
        print(f"[완료] {args.db}\n")

        results = verify(con, with_codes)
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
    finally:
        con.close()


if __name__ == "__main__":
    main()
