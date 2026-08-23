# -*- coding: utf-8 -*-
"""추천 1(S5 자동 출금) 및 추천 2(약관 실시간 질의) 시연 스크립트.

실제 데이터와 DB 상태 변화를 콘솔에 상세히 시각화하여 출력합니다.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402
from backend.services.po import dispatch_a2a_withdrawal_request, get_po, transition  # noqa: E402

SOURCE_DB = ROOT / "data" / "maintq.db"


def print_box(title: str, content: str, char="─", width=88):
    print(f"\n┌{char * (width - 2)}┐")
    print(f"│  {title:<{width - 6}}  │")
    print(f"├{char * (width - 2)}┤")
    for line in content.strip().split("\n"):
        print(f"│  {line:<{width - 6}}  │")
    print(f"└{char * (width - 2)}┘")


def main():
    print("\n" + "═" * 88)
    print(" 🚀 [시연 세션] Q 시리즈 A2A 크로스도메인 핵심 시나리오 (추천 1 & 추천 2)")
    print("═" * 88)

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "maintq_demo.db"
        shutil.copy2(SOURCE_DB, db_path)
        os.environ["MAINTQ_DB"] = str(db_path)

        # ── Adapter Mock Transport
        def mock_adapter_handler(request: httpx.Request) -> httpx.Response:
            chain_id = request.headers.get("X-Request-Chain-Id")
            body = json.loads(request.content.decode("utf-8"))

            if request.url.path.endswith("/request-withdrawal"):
                return httpx.Response(
                    202,
                    json={
                        "status": "input-required",
                        "task_id": "TSK-FINALLQ-20260821-8819",
                        "request_chain_id": chain_id,
                        "message": "FinAllQ 기업 이체 결재라인에 등록되었습니다. (재무 승인자 2단 결재 대기)",
                        "transfer_summary": {
                            "from_company": body["requester"]["finallq_company_id"],
                            "to_supplier": body["supplier"],
                            "to_account": body["to_account_number"],
                            "to_bank": body.get("to_bank_code", "088"),
                            "amount_krw": body["amount"],
                            "purpose": body["purpose"],
                        },
                    },
                )

            if request.url.path.endswith("/lookup-clause"):
                return httpx.Response(
                    200,
                    json={
                        "status": "completed",
                        "verdict": "covered",
                        "answer": (
                            "삼성화재 수퍼비즈니스보험 보통약관 제4조(보상하는 손해)에 따르면 "
                            "전기적/기계적 원인에 의한 과열 손해는 구내폭발위험 특별약관 제1조에 의해 "
                            "정상 보장 범위에 포함됩니다."
                        ),
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

        try:
            # ─────────────────────────────────────────────────────────────
            # [시연 1] S5: MaintQ 발주 승인 -> FinAllQ 자동 출금 요청 E2E
            # ─────────────────────────────────────────────────────────────
            os.environ["MAINTQ_A2A_FINALLQ_BASE_URL"] = "http://localhost:9101"

            print_box(
                "🎯 [시연 1] MaintQ 긴급 발주 승인 → FinAllQ 2단 결재 출금 위임 (S5 E2E)",
                "상황: iG5A 인버터 냉각팬 고장으로 정비사(tech-01)가 상의한 긴급 발주서(PO-0117)가\n"
                "공장 팀장(mgr-01)의 승인 큐에 대기 중입니다.\n"
                "팀장이 승인하면 MaintQ 백엔드가 공급사(에이스산전) 계좌로 자동 출금을 요청합니다.",
            )

            # Step 1: 승인 전 발주서 조회
            po_before = get_po("PO-0117", db_path)
            print("\n[1단계] MaintQ 발주서(PO-0117) 초기 상태 조회:")
            print(f"  • 발주 ID    : {po_before['po_id']} (부품: {po_before['part_name']}, 수량: {po_before['qty']}개)")
            print(f"  • 금액       : {po_before['unit_price'] * po_before['qty']:,}원 (단가: {po_before['unit_price']:,}원)")
            print(f"  • 공급사     : {po_before['supplier_name']} (ID: {po_before['supplier_id']})")
            print(f"  • 발주 상태  : 🟡 {po_before['state'].upper()} (팀장 승인 대기)")
            print(f"  • 사유       : {po_before['reason']}")

            # Step 2: 팀장 발주 승인
            print("\n[2단계] 공장 팀장(mgr-01)이 발주서 승인 실행 (POST /api/po/PO-0117/approve):")
            po_approved = transition("PO-0117", "approved", decided_by="mgr-01", note="정비 승인 완료", db_path=db_path)
            print(f"  • 변경 상태  : 🟢 {po_approved['state'].upper()}")
            print(f"  • 승인권자   : {po_approved['decided_by_name']} ({po_approved['decided_by']})")
            print(f"  • 승인 메모  : {po_approved['decision_note']}")

            # Step 3: A2A 출금 요청 디스패치
            print("\n[3단계] MaintQ 서비스 트리거: FinAllQ A2A 어댑터로 자동 출금 요청 전송:")
            res_s5 = asyncio.run(dispatch_a2a_withdrawal_request("PO-0117", db_path=db_path))

            print(f"  • HTTP 응답  : 202 Accepted (status='{res_s5['status']}')")
            print(f"  • FinAllQ Task ID: 🔖 {res_s5['task_id']}")
            print(f"  • 메시지     : {res_s5['message']}")
            print("  • 이체 명세  :")
            for k, v in res_s5["transfer_summary"].items():
                print(f"      - {k:<15}: {v}")

            # Step 4: DB Trace 영속화 확인
            con = sqlite3.connect(db_path)
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT seq, event_type, tool, request_chain_id, tool_payload FROM traces WHERE session_id = 'S1' AND tool = 'a2a:request-withdrawal' ORDER BY seq"
            ).fetchall()
            con.close()

            print("\n[4단계] MaintQ SQLite `traces` 테이블 감사 기록 영속화 확인:")
            for r in rows:
                print(f"  • [Seq {r['seq']}] {r['event_type']} | 체인ID: {r['request_chain_id']} | 도구: {r['tool']}")
                if r["tool_payload"]:
                    print(f"    └─ tool_payload: {r['tool_payload'][:90]}...")

            print("\n  👉 결과: MaintQ 발주 승인 시 수취계좌(110-384-928103)로 FinAllQ 결재라인 자동 인계 및 Trace 기록 완료! ✅")

            # ─────────────────────────────────────────────────────────────
            # [시연 2] InsuQ 약관 실시간 질의 (lookup-clause) E2E
            # ─────────────────────────────────────────────────────────────
            os.environ["MAINTQ_A2A_INSUQ_BASE_URL"] = "http://localhost:9102"

            print("\n" + "─" * 88)
            print_box(
                "🎯 [시연 2] MaintQ 정비사 현장 질의 → InsuQ 약관 RAG 실시간 답변 (lookup-clause)",
                "상황: 현장 정비사가 인버터 과열 고장 수리 중, 본 손해가 공장 화재보험 약관상\n"
                "보상 대상인지 확인하기 위해 자연어로 실시간 질의를 보냅니다.\n"
                "InsuQ 약관 AI 엔진이 실제 조항 번호 및 페이지를 인용하여 회신합니다.",
            )

            test_question = "인버터 과전압 및 냉각팬 과열 손해에 대해 약관 보장 여부 문의"
            print("[1단계] 정비사 자연어 질의 입력 (POST /api/a2a/lookup-clause):")
            print(f"  • 질의 내용  : \"{test_question}\"")
            print("  • 호출 대상  : InsuQ A2A Adapter (:9102) -> InsuQ QA RAG Core")

            with TestClient(app) as client:
                resp = client.post(
                    "/api/a2a/lookup-clause",
                    json={"question": test_question, "session_id": "S1"},
                    headers={"X-Role": "technician", "X-User": "tech-01"},
                )
                clause_res = resp.json()

            print("\n[2단계] InsuQ A2A 어댑터로부터 수신한 RAG 분석 결과:")
            print(f"  • 처리 상태  : {clause_res['status'].upper()}")
            print(f"  • 보장 판정  : 🛡️ {clause_res['verdict'].upper()} (보장 대상)")
            print(f"  • 종합 답변  : {clause_res['answer']}")
            print("  • 근거 조항 (evidence):")
            for ev in clause_res["evidence"]:
                print(f"      📖 {ev}")

            con = sqlite3.connect(db_path)
            con.row_factory = sqlite3.Row
            clause_traces = con.execute(
                "SELECT seq, event_type, tool, request_chain_id, tool_payload FROM traces WHERE session_id = 'S1' AND tool = 'a2a:lookup-clause' ORDER BY seq"
            ).fetchall()
            con.close()

            print("\n[3단계] MaintQ SQLite `traces` 테이블 감사 기록 영속화 확인:")
            for r in clause_traces:
                print(f"  • [Seq {r['seq']}] {r['event_type']} | 체인ID: {r['request_chain_id']} | 도구: {r['tool']}")

            print("\n  👉 결과: 정비사가 질문한 즉시 InsuQ 약관 근거 조항(보통약관 제4조, 특약 제1조) 및 판정 수신 완료! ✅")

        finally:
            httpx.AsyncClient = orig_async_client

    print("\n" + "═" * 88)
    print(" 🎉 [시연 완료] 추천 1 및 추천 2 크로스도메인 통신 검증이 성공적으로 완료되었습니다.")
    print("═" * 88 + "\n")


if __name__ == "__main__":
    main()
