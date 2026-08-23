# -*- coding: utf-8 -*-
"""backend/a2a/auth_header.py 테스트.

M1 목업(HTTP Basic, client_id:client_secret) 계약과 usable=False 폴백을 고정한다.
"""

from __future__ import annotations

import base64

from backend.a2a import auth_header as ah


def test_returns_empty_dict_when_not_configured(monkeypatch):
    monkeypatch.delenv("MAINTQ_A2A_FINALLQ_CLIENT_ID", raising=False)
    monkeypatch.delenv("MAINTQ_A2A_FINALLQ_CLIENT_SECRET", raising=False)
    assert ah.build_auth_header("finallq") == {}


def test_returns_empty_dict_when_incomplete(monkeypatch):
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_CLIENT_ID", "cid")
    monkeypatch.delenv("MAINTQ_A2A_FINALLQ_CLIENT_SECRET", raising=False)
    assert ah.build_auth_header("finallq") == {}


def test_returns_empty_dict_for_unknown_partner():
    assert ah.build_auth_header("unknown-partner") == {}


def test_builds_basic_auth_header_when_configured(monkeypatch):
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_CLIENT_ID", "cid")
    monkeypatch.setenv("MAINTQ_A2A_FINALLQ_CLIENT_SECRET", "csecret")

    header = ah.build_auth_header("finallq")

    assert list(header.keys()) == ["Authorization"]
    scheme, _, token = header["Authorization"].partition(" ")
    assert scheme == "Basic"
    decoded = base64.b64decode(token).decode("utf-8")
    assert decoded == "cid:csecret"


def test_header_reflects_credential_changes_without_caching(monkeypatch):
    monkeypatch.setenv("MAINTQ_A2A_INSUQ_CLIENT_ID", "a")
    monkeypatch.setenv("MAINTQ_A2A_INSUQ_CLIENT_SECRET", "b")
    first = ah.build_auth_header("insuq")

    monkeypatch.setenv("MAINTQ_A2A_INSUQ_CLIENT_ID", "c")
    monkeypatch.setenv("MAINTQ_A2A_INSUQ_CLIENT_SECRET", "d")
    second = ah.build_auth_header("insuq")

    assert first != second
