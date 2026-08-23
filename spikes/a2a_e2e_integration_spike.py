# -*- coding: utf-8 -*-
"""MaintQ A2A E2E 통합 실통신 검증 스파이크.

검증 시나리오:
  1. S5: MaintQ -> FinAllQ 출금 요청 E2E 왕복
     - 실제 발주서(PO-0117) 및 공급사(에이스산전 계좌 110-384-928103) 실측 데이터 사용
     - dispatch_a2a_withdrawal_request() 호출 -> FinAllQ 어댑터 수신 -> input-required(승인 대기) 회신
     - traces 테이블에 request_chain_id 및 원본 페이로드 불변 기록 검증
  2. InsuQ 약관 근거 조회 (lookup-clause) E2E 왕복
     - POST /api/a2a/lookup-clause 호출 -> InsuQ 어댑터 수신 -> completed 및 evidence 인용 회신
     - traces 테이블에 request_chain_id 및 응답 원문 기록 검증

Postgres 이식 (Sprint 16 MQ-1614 뒤처리): 실 시드(PO-0117·partner_links 등)가 필요해
`data/pg_isolation.py::create_isolated_schema(clone_data=True)` 로 `public` 을 복제한
새 스키마에서 돈다. **`backend.db.DB_PATH` 를 그 DSN 으로 override 하고, 아래에서 호출하는
모든 함수(`get_po`·`transition`·`dispatch_a2a_withdrawal_request`·`record_a2a_trace`)에
`db_path` 를 명시적으로 넘기지 않는다** — `dispatch_a2a_withdrawal_request` 내부가
`backend/a2a/payloads.py::get_finallq_company_id(db_path)` 를 그대로 전달하는데, 그 함수는
`Path(db_path) if db_path else None` 로 감싸서 DSN 문자열을 넘기면 `isinstance(db_path, str)`
분기를 벗어나 격리가 깨진다(이 실사고로 세션 전에 실 Postgres 의 PO-0117 이 이미
approved 로, traces 에 잔여 2행이 남아 있던 것을 이 작업 착수 전 발견해 `data/seed.py
--with-error-codes` 로 정리했다 — 아래 "발견한 문제" 참고). `db_path` 를 아예 안 넘기고
전역 override 하나로 통일하면 `backend/services/po.py`(감싸지 않음)·`backend/a2a/payloads.py`
(감쌈) 양쪽 모두 `connect(None)` 경로로 일관되게 격리 스키마를 본다.

## 이 작업에서 발견한 문제 (보고용, 코드는 고치지 않음)

`backend/a2a/payloads.py` 의 `get_finallq_company_id`·`build_request_withdrawal_payload`·
`build_lookup_clause_payload`·`build_assess_loan_payload` 는 전부 `connect(Path(db_path)
if db_path else None)` 패턴이다 — `db_path` 가 이미 Postgres DSN 문자열이어도 `Path()` 로
감싸는 순간 `backend/db.py::connect()` 의 `isinstance(db_path, str)` 검사를 벗어나 그
값이 조용히 무시되고 전역 `DATABASE_URL`(또는 `backend.db.DB_PATH` override)로 떨어진다.
`backend/services/po.py` 는 같은 인자를 감싸지 않고 그대로 넘겨 DSN 문자열이 정상 작동한다 —
두 모듈의 관례가 어긋나 있다. 이 스파이크·`a2a_outbound_contract.py` 는 `db_path` 인자를
아예 안 넘기고 전역 `bdb.DB_PATH` override 로 우회했다(정상 동작 확인됨). `backend/a2a/
payloads.py` 자체는 `backend/a2a/test_payloads.py`(SQLite 파일 경로를 그대로 쓰는 pytest
스위트)와의 호환을 위해 그 래핑이 필요해 보여 이번 작업에서는 손대지 않았다 — 이 함수들에
DSN 문자열을 **명시적으로** 넘겨야 하는 다른 호출부가 생기면 그때 `Path(db_path) if
isinstance(db_path, Path) or (db_path and not str(db_path).startswith("postgresql://"))
else db_path` 식으로 분기를 넣어야 한다.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import asyncio  # noqa: E402

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import backend.db as bdb  # noqa: E402
from backend.main import app  # noqa: E402
from backend.services.po import dispatch_a2a_withdrawal_request, get_po, transition  # noqa: E402
from data import dbcompat, pg_isolation  # noqa: E402


def run_e2e_tests():
    print("\n" + "═" * 90)
    print("MaintQ A2A 3사 연계 E2E 실통신 통합 검증 (S5 출금 요청 & InsuQ 약관 조회)")
    print("═" * 90 + "\n")

    schema, dsn = pg_isolation.create_isolated_schema("a2a_e2e", clone_data=True)
    saved_db_path = bdb.DB_PATH
    bdb.DB_PATH = dsn

    # ── 1. Mock Transport for FinAllQ & InsuQ Adapters
    def mock_adapter_handler(request: httpx.Request) -> httpx.Response:
        chain_id = request.headers.get("X-Request-Chain-Id")
        body = json.loads(request.content.decode("utf-8"))

        assert chain_id, "X-Request-Chain-Id header must be present"

        # Scenario A: FinAllQ request-withdrawal
        if request.url.path.endswith("/request-withdrawal"):
            assert body["po_id"] == "PO-0117"
            assert body["amount"] == 76000
            assert body["supplier"] == "에이스산전"
            assert body["to_account_number"] == "110-384-928103"
            assert body["to_bank_code"] == "088"
            assert body["requester"]["finallq_company_id"] == "CMP-MAINTQ-001"

            return httpx.Response(
                202,
                json={
                    "status": "input-required",
                    "task_id": "TSK-FINALLQ-20260821-001",
                    "request_chain_id": chain_id,
                    "detail": "출금 요청이 접수되었습니다. 재무 승인권자의 2단 결재가 대기 중입니다.",
                },
            )

        # Scenario B: InsuQ lookup-clause
        if request.url.path.endswith("/lookup-clause"):
            assert "과열" in body["question"] or "약관" in body["question"]
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "verdict": "covered",
                    "answer": "삼성화재 수퍼비즈니스보험 보통약관 제4조에 의거, 기계 장치의 전기적/기계적 원인으로 인한 과열 소손 손해는 구내폭발위험 특별약관에 가입된 경우 보장 대상에 포함됩니다.",
                    "evidence": [
                        "삼성화재 수퍼비즈니스보험 보통약관 제4조 ①, p.13",
                        "삼성화재 수퍼비즈니스보험 구내폭발위험 특별약관 제1조, p.36",
                    ],
                    "request_chain_id": chain_id,
                },
            )

        return httpx.Response(404, text="Not Found")

    orig_async_client = httpx.AsyncClient
    httpx.AsyncClient = lambda **kwargs: orig_async_client(
        transport=httpx.MockTransport(mock_adapter_handler), **kwargs
    )

    prev_finallq_url = os.environ.get("MAINTQ_A2A_FINALLQ_BASE_URL")
    prev_insuq_url = os.environ.get("MAINTQ_A2A_INSUQ_BASE_URL")

    try:
        # ── [시나리오 1] S5: MaintQ -> FinAllQ 출금 요청 E2E
        os.environ["MAINTQ_A2A_FINALLQ_BASE_URL"] = "http://localhost:9101"

        # Step 1-1: PO 상태 전이 (pending -> approved) — db_path 를 넘기지 않는다
        # (bdb.DB_PATH override 를 탄다, 아래 모듈 docstring 참고)
        po_before = get_po("PO-0117")
        assert po_before["state"] == "pending"
        po_approved = transition("PO-0117", "approved", decided_by="mgr-01", note="승인 완료")
        assert po_approved["state"] == "approved"

        # Step 1-2: A2A 출금 요청 디스패치
        res_s5 = asyncio.run(dispatch_a2a_withdrawal_request("PO-0117"))

        assert res_s5 is not None
        assert res_s5["status"] == "input-required"
        assert res_s5["task_id"] == "TSK-FINALLQ-20260821-001"

        # Step 1-3: traces 테이블 영속화 검증
        con = dbcompat.connect_dsn(dsn)
        try:
            rows = con.execute(
                "SELECT event_type, tool, payload, tool_payload, request_chain_id"
                " FROM traces WHERE session_id = 'S1' ORDER BY seq"
            ).fetchall()
        finally:
            con.close()

        a2a_traces = [r for r in rows if r["tool"] == "a2a:request-withdrawal"]
        assert len(a2a_traces) == 2, f"Expected 2 a2a traces (tool_call + tool_result), got {len(a2a_traces)}"
        assert a2a_traces[0]["event_type"] == "tool_call"
        assert a2a_traces[0]["request_chain_id"].startswith("CHAIN-PO-0117-")
        assert a2a_traces[1]["event_type"] == "tool_result"
        assert a2a_traces[1]["request_chain_id"] == a2a_traces[0]["request_chain_id"]

        raw_res = json.loads(a2a_traces[1]["tool_payload"])
        assert raw_res["task_id"] == "TSK-FINALLQ-20260821-001"

        print("  PASS  ① S5 출금 요청 E2E (MaintQ PO-0117 승인 -> FinAllQ 수취계좌 110-384-928103 -> input-required -> trace 영속화)")

        # ── [시나리오 2] InsuQ 약관 근거 조회 (lookup-clause) E2E
        os.environ["MAINTQ_A2A_INSUQ_BASE_URL"] = "http://localhost:9102"

        with TestClient(app) as client:
            resp = client.post(
                "/api/a2a/lookup-clause",
                json={
                    "question": "인버터 과전압 및 냉각팬 과열 손해에 대해 약관 보장 여부 문의",
                    "session_id": "S1",
                },
                headers={"X-Role": "technician", "X-User": "tech-01"},
            )

            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert data["status"] == "completed"
            assert data["verdict"] == "covered"
            assert len(data["evidence"]) == 2
            assert "삼성화재 수퍼비즈니스보험 보통약관 제4조 ①, p.13" in data["evidence"]

        # Step 2-2: traces 테이블 영속화 검증
        con = dbcompat.connect_dsn(dsn)
        try:
            clause_traces = con.execute(
                "SELECT event_type, tool, payload, tool_payload, request_chain_id"
                " FROM traces WHERE session_id = 'S1' AND tool = 'a2a:lookup-clause' ORDER BY seq"
            ).fetchall()
        finally:
            con.close()

        assert len(clause_traces) == 2, f"Expected 2 clause traces, got {len(clause_traces)}"
        assert clause_traces[0]["event_type"] == "tool_call"
        assert clause_traces[1]["event_type"] == "tool_result"
        assert "삼성화재" in clause_traces[1]["tool_payload"]

        print("  PASS  ② InsuQ 약관 조회 E2E (POST /api/a2a/lookup-clause -> InsuQ RAG -> evidence 조항 인용 -> trace 영속화)")

    finally:
        httpx.AsyncClient = orig_async_client
        if prev_finallq_url is None:
            os.environ.pop("MAINTQ_A2A_FINALLQ_BASE_URL", None)
        else:
            os.environ["MAINTQ_A2A_FINALLQ_BASE_URL"] = prev_finallq_url
        if prev_insuq_url is None:
            os.environ.pop("MAINTQ_A2A_INSUQ_BASE_URL", None)
        else:
            os.environ["MAINTQ_A2A_INSUQ_BASE_URL"] = prev_insuq_url
        bdb.DB_PATH = saved_db_path
        pg_isolation.drop_isolated_schema(schema)

    print("\n" + "─" * 90)
    print("전체 E2E 통합 시나리오 통과 (2건) — MaintQ 아웃바운드 통신 및 Trace 실계측 완비!")
    print("─" * 90 + "\n")


if __name__ == "__main__":
    run_e2e_tests()
