# -*- coding: utf-8 -*-
"""backend/a2a/credentials.py 테스트.

D9(예외 대신 status)·D56(캐시 없음, 매 호출 os.environ 재조회)·비밀값 미노출을
회귀로 고정한다.
"""

from __future__ import annotations

from backend.a2a import credentials as cr


def test_env_names_builds_prefixed_pair():
    assert cr.env_names("finallq") == (
        "MAINTQ_A2A_FINALLQ_CLIENT_ID",
        "MAINTQ_A2A_FINALLQ_CLIENT_SECRET",
    )


def test_env_names_uppercases_and_strips():
    assert cr.env_names("  InsuQ ") == (
        "MAINTQ_A2A_INSUQ_CLIENT_ID",
        "MAINTQ_A2A_INSUQ_CLIENT_SECRET",
    )


def test_load_unknown_partner_does_not_read_env(monkeypatch):
    # 존재하지 않는 파트너 이름으로 env 를 지어내 조회하면 오타가 조용히 통과한다 —
    # 그래서 env 를 아예 읽지 않는지까지 확인한다.
    monkeypatch.setenv("MAINTQ_A2A_STRIPE_CLIENT_ID", "x")
    monkeypatch.setenv("MAINTQ_A2A_STRIPE_CLIENT_SECRET", "y")
    cred = cr.load("stripe")
    assert cred.status == "unknown_partner"
    assert cred.client_id == ""
    assert cred.usable is False


def test_load_not_configured_when_both_absent(monkeypatch):
    monkeypatch.delenv("MAINTQ_A2A_FINALLQ_CLIENT_ID", raising=False)
    monkeypatch.delenv("MAINTQ_A2A_FINALLQ_CLIENT_SECRET", raising=False)
    cred = cr.load("finallq")
    assert cred.status == "not_configured"
    assert cred.usable is False


def test_load_not_configured_when_both_blank(monkeypatch):
    # `.env` 의 빈 값(KEY=)·공백뿐인 값도 미설정과 같게 취급한다.
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_CLIENT_ID", "   ")
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_CLIENT_SECRET", "")
    cred = cr.load("finallq")
    assert cred.status == "not_configured"


def test_load_incomplete_when_only_id_set(monkeypatch):
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_CLIENT_ID", "id-only")
    monkeypatch.delenv("MAINTQ_A2A_FINALLQ_CLIENT_SECRET", raising=False)
    cred = cr.load("finallq")
    assert cred.status == "incomplete"
    assert cred.usable is False  # 한쪽만으로 호출을 시도할 수 있는 상태를 만들지 않는다


def test_load_incomplete_when_only_secret_set(monkeypatch):
    monkeypatch.delenv("MAINTQ_A2A_FINALLQ_CLIENT_ID", raising=False)
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_CLIENT_SECRET", "secret-only")
    cred = cr.load("finallq")
    assert cred.status == "incomplete"


def test_load_configured_when_both_set(monkeypatch):
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_CLIENT_ID", "cid")
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_CLIENT_SECRET", "csecret")
    cred = cr.load("finallq")
    assert cred.status == "configured"
    assert cred.usable is True
    assert cred.client_id == "cid"
    assert cred.client_secret == "csecret"


def test_load_strips_whitespace_and_lowercases_partner(monkeypatch):
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_CLIENT_ID", "  cid  ")
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_CLIENT_SECRET", "  csecret  ")
    cred = cr.load("  FinAllQ  ")
    assert cred.partner == "finallq"
    assert cred.client_id == "cid"
    assert cred.client_secret == "csecret"


def test_load_has_no_module_level_cache(monkeypatch):
    """매 호출 os.environ 을 다시 읽는다 (D56) — 첫 호출 값이 굳지 않아야 한다."""
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_CLIENT_ID", "cid")
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_CLIENT_SECRET", "csecret")
    assert cr.load("finallq").status == "configured"

    monkeypatch.delenv("MAINTQ_A2A_FINALLQ_CLIENT_SECRET", raising=False)
    assert cr.load("finallq").status == "incomplete"


def test_partner_credential_repr_masks_secret():
    cred = cr.PartnerCredential(
        partner="finallq", status="configured", client_id="cid", client_secret="super-secret"
    )
    rendered = repr(cred)
    assert "super-secret" not in rendered
    assert "secret_len=12" in rendered
    assert "cid" in rendered  # client_id 는 비밀이 아니므로 그대로 노출돼도 된다


def test_partner_credential_str_matches_repr():
    cred = cr.PartnerCredential(partner="insuq", status="not_configured")
    assert str(cred) == repr(cred)


def test_status_report_covers_all_partners(monkeypatch):
    for partner in cr.PARTNERS:
        id_name, secret_name = cr.env_names(partner)
        monkeypatch.delenv(id_name, raising=False)
        monkeypatch.delenv(secret_name, raising=False)

    report = cr.status_report()
    assert set(report.keys()) == set(cr.PARTNERS)
    assert all(status == "not_configured" for status in report.values())
