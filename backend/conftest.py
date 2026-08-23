# -*- coding: utf-8 -*-
"""backend 테스트 공통 fixture.

`backend/agent/test_llm_cache.py` 는 각 테스트 파일이 스스로 sys.path 를 손봤다 —
여기서는 conftest.py 한 곳에서 루트를 얹어, backend 아래 새 테스트들이 매번 반복하지
않게 한다. pytest 는 테스트 모듈을 임포트하기 전에 conftest.py 를 먼저 읽는다.

A2A 관련 테스트(`backend/a2a/`, `backend/services/`, `backend/routers/`)가 공유하는
최소 SQLite 스키마도 여기 둔다 — `data/seed.py` 의 관련 테이블(parts·users·suppliers·
supplier_parts·inventory·po_drafts·traces·partner_links)에서 A2A 경로가 실제로 건드리는
컬럼만 발췌했다. **정본이 아니다** — data/seed.py 가 스키마를 바꾸면 이 발췌본도 손으로
맞춰야 한다는 뜻이지만, 매 테스트가 프로덕션 DDL 전체(assets·equipment·law_refs 등 20여
테이블)를 끌어오게 하는 것보다는 이 편이 유지비가 적다.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_SCHEMA = """
CREATE TABLE parts (
  part_no      TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  compatible_models TEXT NOT NULL
);

CREATE TABLE users (
  user_id      TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  role         TEXT NOT NULL,
  department   TEXT,
  CHECK (role IN ('technician','manager'))
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

CREATE TABLE inventory (
  part_no      TEXT PRIMARY KEY REFERENCES parts,
  qty          INTEGER NOT NULL,
  safety_stock INTEGER NOT NULL DEFAULT 0,
  location     TEXT
);

CREATE TABLE po_drafts (
  po_id        TEXT PRIMARY KEY,
  part_no      TEXT NOT NULL REFERENCES parts,
  qty          INTEGER NOT NULL,
  supplier_id  TEXT NOT NULL REFERENCES suppliers,
  model        TEXT,
  error_code   TEXT,
  evidence     TEXT,
  unit_price   INTEGER NOT NULL,
  reason       TEXT NOT NULL,
  urgency      TEXT DEFAULT 'normal',
  state        TEXT DEFAULT 'draft',
  requested_by TEXT REFERENCES users,
  decided_by   TEXT REFERENCES users,
  decision_note TEXT,
  session_id   TEXT,
  created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
  CHECK (state IN ('draft','pending','approved','rejected')),
  CHECK (urgency IN ('urgent','normal'))
);

CREATE TABLE traces (
  id           INTEGER PRIMARY KEY,
  session_id   TEXT NOT NULL,
  seq          INTEGER NOT NULL,
  event_type   TEXT NOT NULL,
  tool         TEXT,
  payload      TEXT NOT NULL,
  tool_payload TEXT,
  request_chain_id TEXT,
  ts           DATETIME DEFAULT CURRENT_TIMESTAMP,
  CHECK (event_type IN ('tool_call','tool_result','block')),
  UNIQUE (session_id, seq)
);

CREATE TABLE partner_links (
  partner      TEXT NOT NULL,
  subject_type TEXT NOT NULL,
  subject_ref  TEXT NOT NULL,
  link_state   TEXT,
  external_ref TEXT,
  linked_at    DATETIME,
  PRIMARY KEY (partner, subject_type, subject_ref),
  CHECK (link_state IN ('NOT_LINKED','LINKED')),
  CHECK (external_ref IS NULL OR link_state IS 'LINKED')
);
"""


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """A2A 테스트용 최소 스키마 SQLite 파일 (parts~partner_links, data/seed.py 발췌)."""
    path = tmp_path / "test_maintq.db"
    con = sqlite3.connect(path)
    con.executescript(_SCHEMA)
    con.commit()
    con.close()
    return path


@pytest.fixture()
def seed_po(db_path: Path):
    """발주서 1건 + 부품·공급사 픽스처를 심는 헬퍼를 반환한다 (호출부가 필드를 고른다)."""

    def _seed(
        *,
        po_id: str = "PO-001",
        part_no: str = "PART-001",
        supplier_id: str = "SUP-001",
        qty: int = 2,
        unit_price: int = 10000,
        account_number: str | None = "110-123-456789",
        bank_code: str | None = "004",
        reason: str = "테스트 발주",
        state: str = "approved",
        decided_by: str | None = "mgr-01",
        session_id: str = "sess-001",
    ) -> None:
        con = sqlite3.connect(db_path)
        con.execute("PRAGMA foreign_keys=ON")
        con.execute(
            "INSERT INTO parts (part_no, name, compatible_models) VALUES (?, ?, ?)",
            (part_no, "테스트 부품", "[]"),
        )
        con.execute(
            "INSERT INTO suppliers (supplier_id, name, account_number, bank_code) VALUES (?, ?, ?, ?)",
            (supplier_id, "테스트 거래처", account_number, bank_code),
        )
        if decided_by is not None:
            con.execute(
                "INSERT OR IGNORE INTO users (user_id, display_name, role) VALUES (?, ?, 'manager')",
                (decided_by, decided_by),
            )
        con.execute(
            "INSERT INTO po_drafts (po_id, part_no, qty, supplier_id, unit_price, reason, state,"
            " decided_by, session_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (po_id, part_no, qty, supplier_id, unit_price, reason, state, decided_by, session_id),
        )
        con.commit()
        con.close()

    return _seed


@pytest.fixture()
def link_finallq(db_path: Path):
    """`partner_links` 에 finallq 회사 결(subject_ref='') 을 심는 헬퍼."""

    def _link(external_ref: str = "CMP-MAINTQ-001", link_state: str = "LINKED") -> None:
        con = sqlite3.connect(db_path)
        con.execute(
            "INSERT INTO partner_links (partner, subject_type, subject_ref, link_state, external_ref)"
            " VALUES ('finallq', 'company', '', ?, ?)",
            (link_state, external_ref if link_state == "LINKED" else None),
        )
        con.commit()
        con.close()

    return _link
