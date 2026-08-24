# -*- coding: utf-8 -*-
"""backend/a2a/credentials.py 테스트.

D9(예외 대신 status)·D56(캐시 없음, 매 호출 os.environ 재조회)·비밀값 미노출·
D120(SERVICE_TOKEN 단일값 스킴)을 회귀로 고정한다.
"""

from __future__ import annotations

from backend.a2a import credentials as cr


def test_env_name_builds_suffixed_name():
    assert cr.env_name("finallq") == "FINALLQ_SERVICE_TOKEN"


def test_env_name_uppercases_and_strips():
    assert cr.env_name("  InsuQ ") == "INSUQ_SERVICE_TOKEN"


def test_load_unknown_partner_does_not_read_env(monkeypatch):
    # 존재하지 않는 파트너 이름으로 env 를 지어내 조회하면 오타가 조용히 통과한다 —
    # 그래서 env 를 아예 읽지 않는지까지 확인한다.
    monkeypatch.setenv("STRIPE_SERVICE_TOKEN", "x")
    cred = cr.load("stripe")
    assert cred.status == "unknown_partner"
    assert cred.token == ""
    assert cred.usable is False


def test_load_not_configured_when_absent(monkeypatch):
    monkeypatch.delenv("FINALLQ_SERVICE_TOKEN", raising=False)
    cred = cr.load("finallq")
    assert cred.status == "not_configured"
    assert cred.usable is False


def test_load_not_configured_when_blank(monkeypatch):
    # `.env` 의 빈 값(KEY=)·공백뿐인 값도 미설정과 같게 취급한다.
    monkeypatch.setenv("FINALLQ_SERVICE_TOKEN", "   ")
    cred = cr.load("finallq")
    assert cred.status == "not_configured"


def test_load_configured_when_set(monkeypatch):
    monkeypatch.setenv("FINALLQ_SERVICE_TOKEN", "tok-value")
    cred = cr.load("finallq")
    assert cred.status == "configured"
    assert cred.usable is True
    assert cred.token == "tok-value"


def test_load_strips_whitespace_and_lowercases_partner(monkeypatch):
    monkeypatch.setenv("FINALLQ_SERVICE_TOKEN", "  tok  ")
    cred = cr.load("  FinAllQ  ")
    assert cred.partner == "finallq"
    assert cred.token == "tok"


def test_load_has_no_module_level_cache(monkeypatch):
    """매 호출 os.environ 을 다시 읽는다 (D56) — 첫 호출 값이 굳지 않아야 한다."""
    monkeypatch.setenv("FINALLQ_SERVICE_TOKEN", "tok")
    assert cr.load("finallq").status == "configured"

    monkeypatch.delenv("FINALLQ_SERVICE_TOKEN", raising=False)
    assert cr.load("finallq").status == "not_configured"


def test_partner_credential_repr_masks_token():
    cred = cr.PartnerCredential(partner="finallq", status="configured", token="super-secret")
    rendered = repr(cred)
    assert "super-secret" not in rendered
    assert "token_len=12" in rendered


def test_partner_credential_str_matches_repr():
    cred = cr.PartnerCredential(partner="insuq", status="not_configured")
    assert str(cred) == repr(cred)


def test_status_report_covers_all_partners(monkeypatch):
    for partner in cr.PARTNERS:
        monkeypatch.delenv(cr.env_name(partner), raising=False)

    report = cr.status_report()
    assert set(report.keys()) == set(cr.PARTNERS)
    assert all(status == "not_configured" for status in report.values())


def test_self_partner_id_matches_insuq_seed():
    """InsuQ CustomerSeeder.java 의 PARTNER_ID_MAINTQ_AGENT 시드값과 일치해야
    partner_grant 조회가 통과한다(값이 다르면 401/403) — 실측으로 고정."""
    assert cr.SELF_PARTNER_ID == "maintq-agent"
