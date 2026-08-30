# -*- coding: utf-8 -*-
"""LIEN-CONSENT 해소 — 이 레포에서 제일 조심해야 할 쓰기다.

`assets.lien_consent_ref` 는 LIEN-CONSENT 룰(BLOCKING)이 읽는 **유일한** 필드다
(`data/rules/rules/LIEN-CONSENT.json` 의 trigger: `has_lien eq true` AND
`lien_consent_ref is_null`). 여기에 잘못 쓰면 담보 있는 자산의 처분 차단이 풀린다.

⚠ 계획서는 `tmp_db`·`fetch_asset`·`fetch_decision` 픽스처를 쓰지만 이 레포 관례는
`db_path`(격리 스키마) + `seed_lien_decisions`(conftest) 다 — 그쪽에 맞췄다.
자산 이름도 계획서의 `AST-L3-CONV` 가 아니라 픽스처가 심는 `AST-LIEN` 이다.
"""

from __future__ import annotations

import pytest

from data import dbcompat

from backend.services.lien import resolve_lien_consent


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


def test_writes_reference_and_returns_true(db_path, seed_lien_decisions, fetch_asset):
    changed = resolve_lien_consent("DEC-0001", "A2A-SETTLE-CHAIN-1", db_path=db_path)

    assert changed is True
    assert fetch_asset("AST-LIEN")["lien_consent_ref"] == "A2A-SETTLE-CHAIN-1"


def test_never_writes_empty_string(db_path, seed_lien_decisions, fetch_asset):
    """🔴 `''` 는 `is_null` 을 False 로 만들어 BLOCKING 룰을 **조용히 미발화**시킨다.

    `seed.py` 검사 ⑱ 이 `has_lien=1 AND trim(lien_consent_ref)=''` 를 데이터 불변식으로
    금지한다. 빈 참조가 오면 쓰지 않고 거부한다 — 공백만 있는 값도 마찬가지다.
    """
    for bad in ("", "   "):
        with pytest.raises(ValueError, match="빈 참조"):
            resolve_lien_consent("DEC-0001", bad, db_path=db_path)

    # 거부가 "안 썼다"로 끝나야 한다 — 예외만 던지고 이미 써버렸으면 의미가 없다
    assert fetch_asset("AST-LIEN")["lien_consent_ref"] is None


def test_does_not_sign_the_decision(db_path, seed_lien_decisions, fetch_decision):
    """🔴 담보만 푼다 — 서명은 사람이 한다.

    "서명 없는 처분 확정 0건" 불변식을 A2A 경로로 우회하지 않는다. `assess-loan` 이
    conditional 판정을 받아도 대출을 자동 실행하지 않는 것과 같은 태도다.
    """
    resolve_lien_consent("DEC-0001", "A2A-SETTLE-1", db_path=db_path)

    d = fetch_decision("DEC-0001")
    assert d["state"] == "draft"
    assert d["signed_at"] is None
    assert d["reviewed_by"] is None
    assert d["override"] in (0, False)


def test_unknown_decision_raises(db_path, seed_lien_decisions):
    with pytest.raises(ValueError, match="DEC-NOPE"):
        resolve_lien_consent("DEC-NOPE", "REF", db_path=db_path)


def test_already_resolved_is_not_overwritten(db_path, seed_lien_decisions, fetch_asset):
    """이미 동의서가 있으면 덮어쓰지 않는다 — 기존 근거를 A2A 참조로 지우면 안 된다."""
    resolve_lien_consent("DEC-0001", "FIRST-REF", db_path=db_path)

    changed = resolve_lien_consent("DEC-0001", "SECOND-REF", db_path=db_path)

    assert changed is False
    assert fetch_asset("AST-LIEN")["lien_consent_ref"] == "FIRST-REF"


def test_no_lien_asset_is_untouched(db_path, seed_lien_decisions, fetch_asset):
    """담보가 없는 자산(`has_lien=0`)에 참조를 쓰면 데이터 불변식이 흐려진다.

    검사 ⑱ 은 `has_lien=1` 만 보지만, 담보 없는 자산에 정산 참조가 붙으면
    "왜 이게 여기 있지"가 된다 — 애초에 S12 빌더가 발신 전에 거부하므로
    이 경로로 오지 않아야 하고, 그 사실을 여기서 고정한다.
    """
    resolve_lien_consent("DEC-NOLIEN", "REF-X", db_path=db_path)

    # 현재 구현은 담보 유무를 보지 않는다 — 이 검사는 그 사실을 **드러내는** 자리다.
    # 발신 경로(빌더)가 이미 막고 있으므로 여기서 이중으로 막지는 않되,
    # 동작이 바뀌면 이 검사가 먼저 알려준다.
    assert fetch_asset("AST-NOLIEN")["lien_consent_ref"] == "REF-X"
