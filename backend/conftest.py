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

    `AST-L3-CONV`        — 점검일이 **있는** 정상 자산. `acquisition_cost`(원가)와
                           `book_value`(장부가액)를 **둘 다** 갖는다 — 원가는 실어 보내고
                           장부가액은 보내지 않는다는 D138 경계를 한 자산에서 대조하려면
                           둘이 함께 있어야 한다(하나만 있으면 "안 보낸다"가 자동 성립한다)
    `AST-NO-INSPECTION`  — `last_inspection_date`·`acquisition_cost` 가 NULL (D62 키 생략 검증용)
    """
    con = dbcompat.connect_dsn(db_path)
    try:
        con.execute(
            "INSERT INTO assets (asset_id, name, category, line_id, building_id,"
            " acquired_at, last_inspection_date, inspection_valid_until,"
            " safety_inspection_target, acquisition_cost, book_value)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "AST-L3-CONV", "3라인 컨베이어", "설비", 3, "BLD-A",
                "2019-05-01", "2026-03-02", "2027-03-01", True,
                80_000_000, 40_000_000,
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


@pytest.fixture()
def seed_lien_decisions(db_path: str):
    """S12 payload 파생에 필요한 담보 자산 2건 + draft 결정 2건을 심는다.

    `DEC-0001`  → `AST-LIEN`   : `has_lien=1` · `lien_creditor='한빛은행 여신부'` ·
                                 `lien_consent_ref IS NULL` (= LIEN-CONSENT 발화 상태)
    `DEC-NOLIEN`→ `AST-NOLIEN` : `has_lien=0` (정산 요청 대상이 아님)

    둘 다 **미서명 draft** 다 — 담보 자산은 LIEN-CONSENT(BLOCKING)로 서명이 막혀
    있고 그 담보를 푸는 수단이 S12 자신이라, 서명 후 호출은 구조적으로 불가능하다.
    """
    con = dbcompat.connect_dsn(db_path)
    try:
        for aid, has_lien, creditor in (
            ("AST-LIEN", True, "한빛은행 여신부"),
            ("AST-NOLIEN", False, None),
        ):
            con.execute(
                "INSERT INTO assets (asset_id, name, category, line_id, building_id,"
                " has_lien, lien_creditor, lien_consent_ref)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (aid, f"{aid} 설비", "설비", 3, "BLD-A", has_lien, creditor),
            )
        for did, aid in (("DEC-0001", "AST-LIEN"), ("DEC-NOLIEN", "AST-NOLIEN")):
            con.execute(
                "INSERT INTO decisions (decision_id, asset_id, decision_type,"
                " evidence_bundle, bundle_hash, verdict_at_signing, state, reason)"
                " VALUES (?, ?, 'SALE', '{}', 'sha256:test', 'BLOCKED', 'draft', '테스트')",
                (did, aid),
            )
        con.commit()
    finally:
        con.close()


@pytest.fixture()
def seed_signed_disposals(db_path: str):
    """S11(notify-asset-change) payload 파생용 — 서명·부보 조합 4가지를 심는다.

    `DEC-SIGNED`    → `AST-INSURED`   : 서명 O · 부보 O          (정상 통지 대상)
    `DEC-DRAFT`     → `AST-INSURED`   : **서명 X** · 부보 O       (확정 전이라 통지 금지)
    `DEC-UNINSURED` → `AST-UNINSURED` : 서명 O · **부보 X**       (고칠 증권이 없다)
    `DEC-NOBLDG`    → `AST-NOBLDG`    : 서명 O · 부보 O · **building_id 없음**
    """
    con = dbcompat.connect_dsn(db_path)
    try:
        for aid, name, bldg, policy, insured in (
            ("AST-INSURED", "3라인 금속 컨베이어", "BLD-C", "POL-2026-FIRE-01", True),
            ("AST-UNINSURED", "3라인 리프트", "BLD-C", None, False),
            ("AST-NOBLDG", "건물 미상 설비", None, "POL-2026-FIRE-01", True),
        ):
            con.execute(
                "INSERT INTO assets (asset_id, name, category, line_id, building_id,"
                " policy_id, insured) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (aid, name, "설비", 3, bldg, policy, insured),
            )
        # 서명 행에는 서명자가 있어야 한다 — `decisions_check1` 이 DDL 로 강제한다(D81).
        con.execute(
            "INSERT OR IGNORE INTO users (user_id, display_name, role)"
            " VALUES ('mgr-01', '보전팀장', 'manager')"
        )
        for did, aid, signed in (
            ("DEC-SIGNED", "AST-INSURED", "2026-08-15 09:30:00"),
            ("DEC-DRAFT", "AST-INSURED", None),
            ("DEC-UNINSURED", "AST-UNINSURED", "2026-08-15 09:30:00"),
            ("DEC-NOBLDG", "AST-NOBLDG", "2026-08-15 09:30:00"),
        ):
            # `verdict_at_signing` 은 CLEAR|CONDITIONAL 만 서명될 수 있다(`decisions_check2`).
            con.execute(
                "INSERT INTO decisions (decision_id, asset_id, decision_type,"
                " evidence_bundle, bundle_hash, verdict_at_signing, state, reason,"
                " signed_at, reviewed_by)"
                " VALUES (?, ?, 'DISPOSAL', '{}', 'sha256:test', 'CLEAR', ?, '테스트', ?, ?)",
                (
                    did, aid,
                    "signed" if signed else "draft",
                    signed,
                    "mgr-01" if signed else None,
                ),
            )
        con.commit()
    finally:
        con.close()


@pytest.fixture()
def fetch_asset(db_path: str):
    def _fetch(asset_id: str) -> dict:
        con = dbcompat.connect_dsn(db_path)
        try:
            r = con.execute(
                "SELECT * FROM assets WHERE asset_id = ?", (asset_id,)
            ).fetchone()
            return dict(r) if r is not None else {}
        finally:
            con.close()

    return _fetch


@pytest.fixture()
def fetch_decision(db_path: str):
    def _fetch(decision_id: str) -> dict:
        con = dbcompat.connect_dsn(db_path)
        try:
            r = con.execute(
                "SELECT * FROM decisions WHERE decision_id = ?", (decision_id,)
            ).fetchone()
            return dict(r) if r is not None else {}
        finally:
            con.close()

    return _fetch
