# -*- coding: utf-8 -*-
"""backend/a2a/auth_header.py 테스트.

D120 계약(Bearer <token> + X-A2A-Partner-Id)과 usable=False 폴백을 고정한다.
"""

from __future__ import annotations

from backend.a2a import auth_header as ah
from backend.a2a import credentials as cr


def test_returns_empty_dict_when_not_configured(monkeypatch):
    monkeypatch.delenv("FINALLQ_SERVICE_TOKEN", raising=False)
    assert ah.build_auth_header("finallq") == {}


def test_returns_empty_dict_for_unknown_partner():
    assert ah.build_auth_header("unknown-partner") == {}


def test_builds_bearer_auth_header_when_configured(monkeypatch):
    monkeypatch.setenv("FINALLQ_SERVICE_TOKEN", "tok-value")

    header = ah.build_auth_header("finallq")

    assert header["Authorization"] == "Bearer tok-value"


def test_includes_self_partner_id_header(monkeypatch):
    monkeypatch.setenv("FINALLQ_SERVICE_TOKEN", "tok-value")

    header = ah.build_auth_header("finallq")

    assert header["X-A2A-Partner-Id"] == cr.SELF_PARTNER_ID
    assert set(header.keys()) == {"Authorization", "X-A2A-Partner-Id"}


def test_header_reflects_credential_changes_without_caching(monkeypatch):
    monkeypatch.setenv("INSUQ_SERVICE_TOKEN", "a")
    first = ah.build_auth_header("insuq")

    monkeypatch.setenv("INSUQ_SERVICE_TOKEN", "b")
    second = ah.build_auth_header("insuq")

    assert first != second
