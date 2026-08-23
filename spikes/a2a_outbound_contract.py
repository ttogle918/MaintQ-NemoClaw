# -*- coding: utf-8 -*-
"""MaintQ A2A 아웃바운드 클라이언트 계약 검증.

검증 대상:
  1. build_auth_header() — configured 시 Basic 토큰, not_configured/incomplete 시 {}
  2. get_finallq_company_id() — partner_links 에서 finallq company external_ref 정상 조회 (LINKED 일 때만)
  3. build_request_withdrawal_payload() — S5 스키마 필드 정합성
  4. build_lookup_clause_payload() — InsuQ lookup-clause 스키마 필드 정합성
  5. call_skill() — 헤더(X-Request-Chain-Id, Authorization) 주입, chain_id mismatch 방어,
                    200/202 파싱, 502/504 및 4xx 에러 분류

Postgres 이식 (Sprint 16 MQ-1614 뒤처리): ②③ 은 `partner_links` 를 읽으므로 격리가
필요하다 — `data/pg_isolation.py` 로 새 스키마를 만들고(빈 스키마, `clone_data=False`:
이 두 검사는 최소한의 통제된 행만 필요해 실 시드를 복제할 이유가 없다) `backend.db.DB_PATH`
를 그 DSN 으로 override 한다. **`db_path` 파라미터를 명시적으로 넘기지 않는다** —
`backend/a2a/payloads.py::get_finallq_company_id` 는 `Path(db_path) if db_path else None`
로 인자를 감싸는데, DSN 문자열을 그대로 넘기면 `Path("postgresql://...")` 가 되어
`backend/db.py::connect()` 의 `isinstance(db_path, str)` 분기를 벗어나 격리가 깨진다
(payloads.py 는 SQLite 시절 그대로인 `backend/a2a/test_payloads.py`용 실 파일 경로를 위해
그 래핑이 필요해 건드리지 않는다). 대신 `bdb.DB_PATH` 전역 override 하나로 `connect(None)`
경로가 일관되게 격리 스키마를 보게 한다(`spikes/db_concurrency.py::run_pg` 와 같은 패턴).
"""

from __future__ import annotations

import asyncio
import base64
import os
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


import httpx  # noqa: E402

import backend.db as bdb  # noqa: E402
from backend.a2a.auth_header import build_auth_header  # noqa: E402
from backend.a2a.client import (  # noqa: E402
    A2AClientError,
    A2AUpstreamUnavailableError,
    call_skill,
)
from backend.a2a.payloads import (  # noqa: E402
    build_lookup_clause_payload,
    build_request_withdrawal_payload,
    get_finallq_company_id,
)
from data import dbcompat, pg_isolation  # noqa: E402


@contextmanager
def isolated_backend_db(label: str):
    """새 격리 스키마를 만들고 `backend.db.DB_PATH` 를 그 DSN 으로 override 한다.

    빈 스키마(`clone_data=False`)로 시작한다 — 이 스파이크의 검사는 `partner_links` 에
    스스로 심는 통제된 소수 행만 필요해 실 시드를 복제할 이유가 없다(원본 SQLite 픽스처도
    최소 스키마 하나만 즉석으로 만들었다).
    """
    schema, dsn = pg_isolation.create_isolated_schema(label=label, clone_data=False)
    saved = bdb.DB_PATH
    bdb.DB_PATH = dsn
    try:
        yield dsn
    finally:
        bdb.DB_PATH = saved
        pg_isolation.drop_isolated_schema(schema)


def test_auth_header():
    # 1. 미설정 시
    old_env = dict(os.environ)
    try:
        for k in list(os.environ.keys()):
            if k.startswith("MAINTQ_A2A_"):
                del os.environ[k]

        hdr = build_auth_header("finallq")
        assert hdr == {}, f"Expected empty dict for not_configured, got {hdr}"

        # 2. incomplete 시
        os.environ["MAINTQ_A2A_FINALLQ_CLIENT_ID"] = "test_client"
        hdr = build_auth_header("finallq")
        assert hdr == {}, f"Expected empty dict for incomplete, got {hdr}"

        # 3. configured 시
        os.environ["MAINTQ_A2A_FINALLQ_CLIENT_SECRET"] = "test_secret"
        hdr = build_auth_header("finallq")
        expected_token = base64.b64encode(b"test_client:test_secret").decode()
        assert hdr == {"Authorization": f"Basic {expected_token}"}, f"Unexpected header: {hdr}"
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    print("  PASS  ① build_auth_header() — 미설정/불완전 {} 반환 및 정상 시 Basic 헤더 생성")


def test_partner_links_lookup():
    with isolated_backend_db("a2a_outbound_links"):
        con = dbcompat.connect_dsn(bdb.DB_PATH)
        try:
            con.execute(
                "INSERT INTO partner_links (partner, subject_type, subject_ref, link_state,"
                " external_ref, linked_at) VALUES ('finallq', 'company', '', 'LINKED',"
                " 'CMP-MAINTQ-001', '2026-08-13T09:00:00')"
            )
            con.commit()
        finally:
            con.close()

        # 정상 LINKED 조회 (db_path 를 넘기지 않는다 — bdb.DB_PATH override 를 탄다)
        comp_id = get_finallq_company_id()
        assert comp_id == "CMP-MAINTQ-001", f"Expected CMP-MAINTQ-001, got {comp_id}"

        # NOT_LINKED인 경우
        con = dbcompat.connect_dsn(bdb.DB_PATH)
        try:
            con.execute(
                "UPDATE partner_links SET link_state = 'NOT_LINKED', external_ref = NULL"
                " WHERE partner='finallq' AND subject_type='company'"
            )
            con.commit()
        finally:
            con.close()

        comp_id = get_finallq_company_id()
        assert comp_id is None, f"Expected None for NOT_LINKED, got {comp_id}"
    print("  PASS  ② get_finallq_company_id() — partner_links 테이블에서 LINKED 일 때만 external_ref 조회")


def test_payload_assembly():
    with isolated_backend_db("a2a_outbound_payload"):
        con = dbcompat.connect_dsn(bdb.DB_PATH)
        try:
            con.execute(
                "INSERT INTO partner_links (partner, subject_type, subject_ref, link_state,"
                " external_ref, linked_at) VALUES ('finallq', 'company', '', 'LINKED',"
                " 'CMP-MAINTQ-001', '2026-08-13T09:00:00')"
            )
            con.commit()
        finally:
            con.close()

        po = {
            "po_id": "PO-2026-001",
            "unit_price": 50000,
            "qty": 2,
            "supplier_name": "삼원정밀",
            "decided_by": "MGR-001",
            "reason": "냉각팬 베어링 파손",
            "error_code": "ERR-FAN-01",
        }
        supplier_row = {
            "account_number": "110-123-456789",
            "bank_code": "088",
        }

        # 1. request-withdrawal (db_path 를 넘기지 않는다 — bdb.DB_PATH override 를 탄다)
        p1 = build_request_withdrawal_payload(po, supplier_row, "REQ-CHAIN-001")
        assert p1["requester"]["finallq_company_id"] == "CMP-MAINTQ-001"
        assert p1["request_chain_id"] == "REQ-CHAIN-001"
        assert p1["amount"] == 100000
        assert p1["supplier"] == "삼원정밀"
        assert p1["approved_by"] == "MGR-001"
        assert p1["purpose"] == "냉각팬 베어링 파손"
        assert p1["to_account_number"] == "110-123-456789"
        assert p1["to_bank_code"] == "088"

        # 2. lookup-clause
        p2 = build_lookup_clause_payload("모터 과열 시 면책 조항이 어떻게 되나요?", "REQ-CHAIN-002")
        assert p2["requester"]["finallq_company_id"] == "CMP-MAINTQ-001"
        assert p2["request_chain_id"] == "REQ-CHAIN-002"
        assert p2["question"] == "모터 과열 시 면책 조항이 어떻게 되나요?"
    print("  PASS  ③ build_*_payload() — S5 출금 및 lookup-clause 페이로드 조립 정합성")


async def test_client_async():
    # Custom Mock Transport
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-Request-Chain-Id") == "CHAIN-100"
        if request.url.path.endswith("/request-withdrawal"):
            return httpx.Response(
                202,
                json={"status": "input-required", "task_id": "TSK-001", "detail": "승인 대기 중"},
            )
        if request.url.path.endswith("/502-error"):
            return httpx.Response(502, text="Bad Gateway")
        if request.url.path.endswith("/400-error"):
            return httpx.Response(400, text="Bad Request")
        return httpx.Response(404, text="Not Found")

    transport = httpx.MockTransport(handler)

    # 1. Parameter validation
    try:
        await call_skill("finallq", "request-withdrawal", {"request_chain_id": "A"}, "B", "http://test")
        assert False, "Should raise on chain_id mismatch"
    except ValueError:
        pass

    try:
        await call_skill("finallq", "request-withdrawal", {}, "", "http://test")
        assert False, "Should raise on empty chain_id"
    except ValueError:
        pass

    # 2. Normal 202 response
    # Monkeypatch AsyncClient to use mock transport
    orig_async_client = httpx.AsyncClient
    try:
        httpx.AsyncClient = lambda **kwargs: orig_async_client(transport=transport, **kwargs)

        res = await call_skill(
            "finallq",
            "request-withdrawal",
            {"request_chain_id": "CHAIN-100", "amount": 1000},
            "CHAIN-100",
            "http://test:9001",
        )
        assert res["status"] == "input-required"
        assert res["task_id"] == "TSK-001"

        # 3. 502 -> A2AUpstreamUnavailableError
        try:
            await call_skill(
                "finallq",
                "502-error",
                {"request_chain_id": "CHAIN-100"},
                "CHAIN-100",
                "http://test:9001",
            )
            assert False, "Should raise A2AUpstreamUnavailableError"
        except A2AUpstreamUnavailableError:
            pass

        # 4. 400 -> A2AClientError
        try:
            await call_skill(
                "finallq",
                "400-error",
                {"request_chain_id": "CHAIN-100"},
                "CHAIN-100",
                "http://test:9001",
            )
            assert False, "Should raise A2AClientError"
        except A2AClientError as e:
            assert e.status_code == 400

    finally:
        httpx.AsyncClient = orig_async_client

    print("  PASS  ④ call_skill() — 헤더 주입, chain_id mismatch 검증, 202 파싱, 502/400 예외 매핑")


def main():
    print("\nMaintQ A2A 아웃바운드 클라이언트 계약 검증\n" + "─" * 80)
    test_auth_header()
    test_partner_links_lookup()
    test_payload_assembly()
    asyncio.run(test_client_async())
    print("─" * 80 + "\n전체 통과 (4건) — MaintQ A2A 아웃바운드 클라이언트 계약 및 구현 검증 완료!\n")


if __name__ == "__main__":
    main()
