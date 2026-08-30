# -*- coding: utf-8 -*-
"""backend 테스트 공통 fixture.

`backend/agent/test_llm_cache.py` 는 각 테스트 파일이 스스로 sys.path 를 손봤다 —
여기서는 conftest.py 한 곳에서 루트를 얹어, backend 아래 새 테스트들이 매번 반복하지
않게 한다. pytest 는 테스트 모듈을 임포트하기 전에 conftest.py 를 먼저 읽는다.

A2A 관련 테스트(`backend/a2a/`, `backend/services/`, `backend/routers/`)가 공유하는
`db_path` 픽스처도 여기 둔다. Sprint 16(MQ-1614) 이전엔 이게 SQLite 파일이었다 —
`backend/db.py` 가 Postgres 전용으로 바뀐 뒤에도 그대로 남아 있어서, `connect()` 가
`db_path`(Path 객체)를 조건 불일치로 무시하고 **항상 실 `DATABASE_URL`(공유 public
스키마)에 접속**해 왔다. 즉 이 스키마로 만든 "격리 DB"는 아무도 읽지 않았고, 테스트는
매번 진짜 공유 DB를 보면서 우연히 맞거나(빈 경우) 실패해 왔다(발견 경위:
`docs/sprints/sprint-16-wip.md` "4차 체크포인트" 참고). 이제 `data/pg_isolation.py` 로
실제 격리된 Postgres 스키마를 만들고 DSN 문자열을 반환한다 — 프로덕션 전체 스키마이므로
발췌본을 손으로 맞출 필요도 없어졌다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data import dbcompat  # noqa: E402
from data.pg_isolation import create_isolated_schema, drop_isolated_schema  # noqa: E402


@pytest.fixture()
def db_path() -> str:
    """A2A 테스트용 격리 Postgres 스키마 DSN (프로덕션 전체 스키마, 데이터는 비어 있음)."""
    schema, dsn = create_isolated_schema(label="a2a_test", clone_data=False)
    try:
        yield dsn
    finally:
        drop_isolated_schema(schema)


@pytest.fixture()
def seed_po(db_path: str):
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
        con = dbcompat.connect_dsn(db_path)
        try:
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
        finally:
            con.close()

    return _seed


@pytest.fixture()
def link_finallq(db_path: str):
    """`partner_links` 에 finallq 회사 결(subject_ref='') 을 심는 헬퍼."""

    def _link(external_ref: str = "CMP-MAINTQ-001", link_state: str = "LINKED") -> None:
        con = dbcompat.connect_dsn(db_path)
        try:
            con.execute(
                "INSERT INTO partner_links (partner, subject_type, subject_ref, link_state, external_ref)"
                " VALUES ('finallq', 'company', '', ?, ?)",
                (link_state, external_ref if link_state == "LINKED" else None),
            )
            con.commit()
        finally:
            con.close()

    return _link


@pytest.fixture()
def seed_assets(db_path: str):
    """S13 payload 파생에 필요한 자산 2건 + 소유권 점검 2행을 심는다.

    `AST-L3-CONV`        — 점검일이 **있는** 정상 자산
    `AST-NO-INSPECTION`  — `last_inspection_date` 가 NULL (D62 키 생략 검증용)
    """
    con = dbcompat.connect_dsn(db_path)
    try:
        con.execute(
            "INSERT INTO assets (asset_id, name, category, line_id, building_id,"
            " acquired_at, last_inspection_date, inspection_valid_until,"
            " safety_inspection_target)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "AST-L3-CONV", "3라인 컨베이어", "설비", 3, "BLD-A",
                "2019-05-01", "2026-03-02", "2027-03-01", True,
            ),
        )
        con.execute(
            "INSERT INTO assets (asset_id, name, category, line_id, building_id,"
            " acquired_at, last_inspection_date, inspection_valid_until,"
            " safety_inspection_target)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "AST-NO-INSPECTION", "점검이력 없는 설비", "설비", 3, "BLD-A",
                "2021-01-01", None, None, None,
            ),
        )
        for cat, item, state in (
            ("소유", "취득 증빙", "VERIFIED"),
            ("담보", "근저당 설정 여부", "UNVERIFIED"),
        ):
            con.execute(
                "INSERT INTO ownership_checks (asset_id, category, check_item, state,"
                " checked_at) VALUES (?, ?, ?, ?, ?)",
                ("AST-L3-CONV", cat, item, state, "2026-08-01 00:00:00"),
            )
        con.commit()
    finally:
        con.close()
