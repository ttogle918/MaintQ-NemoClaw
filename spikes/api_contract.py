# -*- coding: utf-8 -*-
"""REST API 계약 검증 — 상태 전이 = 권한 (docs/06_REPO_API.md §2.2·§2.3).

핵심: **정비사가 approve 를 호출하면 403.** 완료 기준의 "권한 위반 차단 100%" 가
프롬프트 지시가 아니라 서버 코드로 강제되는지를 본다.

임시 DB 사본에서 돌린다 — 상태를 실제로 바꾸는 테스트라 원본을 오염시키면 안 된다.

실행:  uv run python spikes/api_contract.py
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from data import dbcompat, pg_isolation  # noqa: E402

SOURCE_DB = ROOT / "data" / "maintq.db"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


TECH = {"X-Role": "technician", "X-User": "tech-01"}
MGR = {"X-Role": "manager", "X-User": "mgr-01"}
MGR_FIN = {"X-Role": "manager", "X-User": "mgr-02"}

# ── `/api/po` 응답 **키 집합** 기준선 (D85) ──────────────────────────────────────
# D85 가 `/api/po` 의 "경로·응답 형태 불변"을 조건으로 `GET /api/approvals` 신설을 허용했다.
# 그런데 값만 단언하는 검사는 **키가 늘거나 사라져도 통과한다** — Stage 1 에서 계약 드리프트가
# 키집합 단언이 없어 그대로 지나간 전례가 있다. 그래서 형태를 여기에 못박고,
# `spikes/approvals_contract.py` ⑱ 이 **이 상수를 import 해** 통합 큐 도입 후에도 대조한다
# (기준선을 두 곳에 적으면 한쪽만 고쳐도 조용히 어긋난다).
PO_LIST_ITEM_KEYS = frozenset(
    {
        "created_at", "decided_at", "decided_by", "decided_by_name", "decision_note",
        "error_code", "evidence", "finance_decided_at", "finance_decided_by",
        "finance_decided_by_name", "finance_decision_note", "model", "part_name", "part_no",
        "po_id", "qty", "reason", "requested_by", "requested_by_name",
        "requested_by_department", "session_id", "state", "supplier_id", "supplier_name",
        "unit_price", "urgency",
    }
)
# 상세는 목록 + 화면 B 재료 3종 + D118(01·02 렌더) 가산 3종
PO_DETAIL_KEYS = PO_LIST_ITEM_KEYS | {
    "quotes", "inventory", "trace_url", "alternatives", "error_code_def", "documents_preview",
}


#: seq 를 **일부러 뒤섞어** INSERT 한다 — 저장 순서가 아니라 `ORDER BY seq` 가
#: 응답 순서를 정하는지 봐야 화면 B 타임라인(MQ-309)이 믿을 수 있다.
TRACE_FIXTURE_SESSION = "S-TRACE-FIX"
TRACE_FIXTURE_ROWS = [
    (3, "tool_result", "lookup_error_code", {"tool": "lookup_error_code", "status": "ok"}),
    (1, "tool_call", "lookup_error_code", {"tool": "lookup_error_code", "input": {"code": "OHt"}}),
    (5, "block", None, {"type": "citation", "data": {"page": 202}}),
    (2, "block", None, {"type": "safety", "data": {"text": "10분 이상 대기"}}),
    (4, "tool_call", "search_inventory", {"tool": "search_inventory", "input": {"qty": 2}}),
]


def seed_trace_fixture(db) -> None:
    """traces 5행을 무작위 seq 순서로 직접 INSERT (백엔드 코드를 거치지 않는다)."""
    con = dbcompat.connect_dsn(db) if dbcompat.USE_POSTGRES else sqlite3.connect(db)
    try:
        con.executemany(
            "INSERT INTO traces (session_id, seq, event_type, tool, payload, ts)"
            " VALUES (?,?,?,?,?,?)",
            [
                (
                    TRACE_FIXTURE_SESSION,
                    seq,
                    event_type,
                    tool,
                    json.dumps(payload, ensure_ascii=False),
                    "2026-07-23 04:05:06.000",
                )
                for seq, event_type, tool, payload in TRACE_FIXTURE_ROWS
            ],
        )
        con.commit()
    finally:
        con.close()


def run(client) -> None:
    # ── 큐 조회
    r = client.get("/api/po", params={"state": "pending"}, headers=MGR)
    items = r.json()["items"]
    check(
        "① 승인 큐 조회 (긴급 우선 정렬) + 항목 키집합 불변 (D85)",
        r.status_code == 200
        and len(items) == 3
        and items[0]["urgency"] == "urgent"
        and all(set(i) == PO_LIST_ITEM_KEYS for i in items),
        f"{len(items)}건, 첫 항목 {items[0]['po_id']}({items[0]['urgency']})"
        f", 키차이={set(items[0]) ^ PO_LIST_ITEM_KEYS or '없음'}",
    )

    # ── 상세: 근거 카드·공급사 비교에 필요한 것이 한 번에 오는가
    d = client.get("/api/po/PO-0117", headers=MGR).json()
    check(
        "② 상세 — evidence·재고·견적·trace 링크 + 키집합 불변 (D85)",
        d["evidence"]["symptoms"]
        and d["inventory"]["qty"] == 1
        and len(d["quotes"]) == 2
        and d["trace_url"] == "/api/chat/S1/trace"
        and set(d) == PO_DETAIL_KEYS,
        f"quotes={len(d['quotes'])}, 재고={d['inventory']['qty']}, trace={d['trace_url']}"
        f", 키차이={set(d) ^ PO_DETAIL_KEYS or '없음'}",
    )
    check(
        "②-b D57 — model 확정(iG5A, 2026-07-28 승인 후) → print_page 실측 202(offset 0)",
        next((b.get("print_page") for b in d["evidence"]["basis"] if b.get("manual_page") == 202), None)
        == 202,
        f"model={d['model']}, basis={d['evidence']['basis']}",
    )
    check(
        "③ D36 표시명은 서버가 매핑",
        d["requested_by"] == "tech-01" and d["requested_by_name"] == "김OO",
        f"{d['requested_by']} → {d['requested_by_name']}",
    )
    check(
        "③-b PO-0117 pending(재무 결정 전, 진단 있음) — documents_preview.fund_execution"
        " 은 None (아직 팀장 승인 전이라 자금집행요청서 자체가 성립하지 않음, MQ-1710)."
        " ★ 이 체크는 반드시 ⑧(PO-0117 approve)보다 앞에서 실행돼야 한다 — PO-0117 은"
        " 이 스크립트에서 그 뒤로 되돌릴 수 없이 approved 로 소비된다.",
        d["documents_preview"]["fund_execution"] is None,
        f"state={d['state']}, fund_execution={d['documents_preview'].get('fund_execution')!r}",
    )

    # ── ★ 403 규칙 — 평가 지표
    r = client.post("/api/po/PO-0117/approve", headers=TECH)
    check(
        "④ 정비사 approve → 403 (평가 지표)",
        r.status_code == 403,
        f"{r.status_code} {r.json().get('detail', '')[:40]}",
    )
    r = client.post("/api/po/PO-0117/reject", json={"reason": "x"}, headers=TECH)
    check("⑤ 정비사 reject → 403", r.status_code == 403, f"{r.status_code}")
    r = client.post("/api/po/PO-0117/submit", headers=MGR)
    check("⑥ 팀장 submit → 403 (역할 분리는 양방향)", r.status_code == 403, f"{r.status_code}")

    # ── 상태 전이 순서 강제
    r = client.post("/api/po/PO-0117/submit", headers=TECH)
    check(
        "⑦ pending 을 다시 submit → 409 (403 과 구분)",
        r.status_code == 409,
        f"{r.status_code} {r.json().get('detail', '')[:46]}",
    )

    # ── 정상 승인
    r = client.post("/api/po/PO-0117/approve", json={"note": "긴급 승인"}, headers=MGR)
    body = r.json()
    check(
        "⑧ 팀장 approve → approved + decided_by stamp",
        r.status_code == 200
        and body["state"] == "approved"
        and body["decided_by"] == "mgr-01"
        and body["decided_by_name"] == "박OO",
        f"state={body['state']}, decided_by={body['decided_by']}",
    )
    r = client.post("/api/po/PO-0117/approve", headers=MGR)
    check("⑨ 이미 승인된 건 재승인 → 409", r.status_code == 409, f"{r.status_code}")

    d116 = client.get("/api/po/PO-0116", headers=MGR).json()
    check(
        "⑨-b PO-0116 pending(model/error_code 없는 S2 표본, 진단서도 이미 None) —"
        " documents_preview.fund_execution 도 마찬가지로 None (MQ-1710)."
        " ★ 이 체크는 반드시 ⑩(PO-0116 reject)보다 앞에서 실행돼야 한다.",
        d116["documents_preview"]["fund_execution"] is None,
        f"state={d116['state']}, fund_execution={d116['documents_preview'].get('fund_execution')!r}",
    )

    # ── 반려는 사유 필수 (D38)
    r = client.post("/api/po/PO-0116/reject", json={}, headers=MGR)
    check("⑩ D38 사유 없는 반려 → 422", r.status_code == 422, f"{r.status_code}")
    r = client.post("/api/po/PO-0116/reject", json={"reason": "예산 초과"}, headers=MGR)
    body = r.json()
    check(
        "⑪ 반려 → rejected + 사유 저장",
        body["state"] == "rejected" and body["decision_note"] == "예산 초과",
        f"state={body['state']}, note={body['decision_note']!r}",
    )

    # ── 없는 발주
    check("⑫ 없는 발주 → 404", client.get("/api/po/PO-9999", headers=MGR).status_code == 404, "404")

    # ── 장비 컨텍스트
    eq = client.get("/api/equipment", headers=TECH).json()["items"]
    check("⑬ 장비 목록", len(eq) == 10, f"{len(eq)}대")

    h = client.get("/api/equipment/INV-L3-01/history", params={"days": 30}, headers=TECH).json()
    oct_before = sum(1 for e in h["events"] if e["code"] == "OCT")
    check("⑭ 이력 조회 (30일 OCT 3건)", oct_before == 3, f"OCT {oct_before}건")

    # ── D29 이력 기록
    r = client.post(
        "/api/equipment/INV-L3-01/errors",
        json={"code": "OCt", "action_taken": "리셋"},
        headers=TECH,
    )
    check(
        "⑮ D29 이력 기록 (정비사) + D25 대문자 저장",
        r.status_code == 201 and r.json()["code"] == "OCT",
        f"{r.status_code}, code={r.json().get('code')}",
    )
    h2 = client.get("/api/equipment/INV-L3-01/history", params={"days": 30}, headers=TECH).json()
    oct_after = sum(1 for e in h2["events"] if e["code"] == "OCT")
    check(
        "⑯ 기록이 반복 감지 모수에 반영",
        oct_after == oct_before + 1,
        f"{oct_before} → {oct_after}건",
    )

    r = client.post("/api/equipment/INV-L3-01/errors", json={"code": "OCT"}, headers=MGR)
    check("⑰ 팀장은 이력 기록 불가 → 403", r.status_code == 403, f"{r.status_code}")

    r = client.post("/api/equipment/NO-SUCH/errors", json={"code": "OCT"}, headers=TECH)
    check("⑱ 없는 설비에 기록 → 404", r.status_code == 404, f"{r.status_code}")

    # ── D36: 한글 표시명을 헤더에 넣으려는 시도
    r = client.get("/api/equipment", headers={"X-Role": "technician", "X-User": "tech-01"})
    check("⑲ ASCII 사용자 ID 는 통과", r.status_code == 200, f"{r.status_code}")

    # ── GET /trace (D43) — 화면 B 링크이자 SSE 끊김 폴백
    # trace_url 은 서버가 만든 링크다. 문자열을 다시 조립하지 않고 **그대로** 따라가야
    # "링크가 항상 유효하다"는 D43 의 전제가 실제로 검증된다.
    trace_url = client.get("/api/po/PO-0117", headers=MGR).json()["trace_url"]
    r = client.get(trace_url, headers=MGR)
    body = r.json()
    check(
        "⑳ trace_url 을 그대로 GET → 200 + D43 스키마",
        r.status_code == 200 and set(body) == {"session_id", "count", "events"},
        f"{r.status_code} {trace_url} keys={sorted(body)}",
    )

    r = client.get("/api/chat/NO-SUCH-SESSION/trace", headers=MGR)
    body = r.json()
    check(
        "㉑ 없는 세션 → 404 가 아니라 200 + count 0 (D43)",
        r.status_code == 200 and body["count"] == 0 and body["events"] == [],
        f"{r.status_code}, count={body.get('count')}",
    )

    body = client.get(f"/api/chat/{TRACE_FIXTURE_SESSION}/trace", headers=MGR).json()
    seqs = [e["seq"] for e in body["events"]]
    check(
        "㉒ 무작위 순서 INSERT → seq 오름차순 · data 는 dict · ts 는 ...Z (D39)",
        body["count"] == 5
        and seqs == sorted(seqs)
        and all(isinstance(e["data"], dict) for e in body["events"])
        and all(e["ts"].endswith("Z") for e in body["events"]),
        f"seq={seqs}, ts={body['events'][0]['ts']}",
    )

    r = client.get(f"/api/chat/{TRACE_FIXTURE_SESSION}/trace", headers=TECH)
    check(
        "㉓ 역할 제한 없음 — technician 헤더로도 200 (D43)",
        r.status_code == 200 and r.json()["count"] == 5,
        f"{r.status_code}, count={r.json().get('count')}",
    )

    # ── D108 — department 는 권한이 아니고 헤더가 아니라 DB 조회로만 온다 ──────────────
    body = client.get("/api/whoami", headers=MGR).json()
    body2 = client.get("/api/whoami", headers={"X-Role": "manager", "X-User": "mgr-02"}).json()
    body3 = client.get("/api/whoami", headers=TECH).json()
    check(
        "㉔ GET /api/whoami — department 는 user_id 별로 DB 값 그대로 (D108)",
        body["department"] == "maintenance"
        and body2["department"] == "finance"
        and body3["department"] == "maintenance",
        f"mgr-01={body['department']!r} mgr-02={body2['department']!r} tech-01={body3['department']!r}",
    )

    # X-Dept 헤더는 애초에 정의돼 있지 않다 — 보내도 서버가 읽지 않고 DB 값이 그대로 나와야 한다
    spoofed = client.get(
        "/api/whoami", headers={**MGR, "X-Dept": "finance"}
    ).json()
    check(
        "㉕ X-Dept 헤더 스푸핑 무시 — mgr-01(maintenance)에 X-Dept:finance 를 실어도 무시 (D108)",
        spoofed["department"] == "maintenance",
        f"department={spoofed['department']!r} (기대: 'maintenance', 헤더값 'finance' 는 무시돼야 함)",
    )

    unknown = client.get(
        "/api/whoami", headers={"X-Role": "manager", "X-User": "ghost-99"}
    ).json()
    check(
        "㉖ 미등록 user_id → department:None, 400 아님 (D108)",
        unknown["department"] is None and "role" in unknown and "user_id" in unknown,
        f"{unknown}",
    )

    # ── ㉗~㊱ P39 축소판 — 화면 직접 생성 (POST /api/po, D111)
    quote_part = "BLT-V-A50"
    r = client.get(f"/api/po/quotes/{quote_part}", headers=TECH)
    quotes = r.json()["quotes"] if r.status_code == 200 else None
    check(
        "㉗ 부품 견적 사전 조회 (발주 화면이 공급사를 고르기 전)",
        r.status_code == 200 and isinstance(quotes, list) and len(quotes) >= 1,
        f"{r.status_code}, {len(quotes) if quotes is not None else 'N/A'}건",
    )

    supplier_id = quotes[0]["supplier_id"] if quotes else None
    r = client.post(
        "/api/po",
        json={
            "part_no": quote_part,
            "qty": quotes[0]["moq"] if quotes else 1,
            "supplier_id": supplier_id,
            "reason": "화면 직접 생성 테스트",
        },
        headers=TECH,
    )
    body = r.json()
    check(
        "㉘ 정비사 화면 직접 생성 → 200 + draft + requested_by 즉시 stamp",
        r.status_code == 200
        and body.get("state") == "draft"
        and body.get("requested_by") == "tech-01"
        and body.get("session_id") is None
        and set(body) == PO_DETAIL_KEYS,
        f"{r.status_code}, state={body.get('state')}, requested_by={body.get('requested_by')}"
        f", 키차이={set(body) ^ PO_DETAIL_KEYS or '없음'}",
    )
    new_po_id = body.get("po_id")

    r = client.post(
        "/api/po",
        json={"part_no": quote_part, "qty": 1, "supplier_id": supplier_id, "reason": "x"},
        headers=MGR,
    )
    check("㉙ 팀장이 화면 생성 호출 → 403", r.status_code == 403, f"{r.status_code}")

    r = client.post(
        "/api/po",
        json={"part_no": quote_part, "qty": 1, "supplier_id": "NO-SUCH-SUP", "reason": "x"},
        headers=TECH,
    )
    check("㉚ 없는 공급사 → 404(no_quote)", r.status_code == 404, f"{r.status_code}")

    moq_supplier = next((q for q in (quotes or []) if q["moq"] > 1), None)
    if moq_supplier:
        r = client.post(
            "/api/po",
            json={
                "part_no": quote_part,
                "qty": moq_supplier["moq"] - 1,
                "supplier_id": moq_supplier["supplier_id"],
                "reason": "x",
            },
            headers=TECH,
        )
        check(
            "㉛ MOQ 미달 → 422(moq_not_met)",
            r.status_code == 422 and r.json().get("reason") == "moq_not_met",
            f"{r.status_code}, reason={r.json().get('reason')}",
        )
    else:
        check("㉛ MOQ 미달 → 422(moq_not_met)", False, "시드에 moq>1 공급사가 없어 이 경로를 검증 못 함")

    # ── ㉜~㊱ PATCH — draft 수정
    r = client.patch(
        f"/api/po/{new_po_id}",
        json={
            "part_no": quote_part,
            "qty": (quotes[0]["moq"] if quotes else 1) + 1,
            "supplier_id": supplier_id,
            "reason": "수량 정정",
        },
        headers=TECH,
    )
    body2 = r.json()
    check(
        "㉜ draft 수정 → 200 + qty·reason 반영",
        r.status_code == 200
        and body2.get("qty") == (quotes[0]["moq"] if quotes else 1) + 1
        and body2.get("reason") == "수량 정정",
        f"{r.status_code}, qty={body2.get('qty')}, reason={body2.get('reason')!r}",
    )
    r = client.patch(
        f"/api/po/{new_po_id}",
        json={"part_no": quote_part, "qty": 1, "supplier_id": supplier_id, "reason": "x"},
        headers=MGR,
    )
    check("㉝ 팀장이 PATCH 호출 → 403", r.status_code == 403, f"{r.status_code}")

    r = client.post(f"/api/po/{new_po_id}/submit", headers=TECH)
    check("㉞ 제출(submit) 성공 — 이후 PATCH 는 409 여야 한다", r.status_code == 200, f"{r.status_code}")
    r = client.patch(
        f"/api/po/{new_po_id}",
        json={"part_no": quote_part, "qty": 1, "supplier_id": supplier_id, "reason": "x"},
        headers=TECH,
    )
    check("㉟ pending 상태를 PATCH → 409(draft 아님)", r.status_code == 409, f"{r.status_code}")

    r = client.patch(
        "/api/po/PO-9999",
        json={"part_no": quote_part, "qty": 1, "supplier_id": supplier_id, "reason": "x"},
        headers=TECH,
    )
    check("㊱ 없는 발주 PATCH → 404", r.status_code == 404, f"{r.status_code}")

    # ── ㊲~㊶ D119 — 자금집행 승인(SoD): role → department → state 순서로 문지기 3중
    r = client.post("/api/po/PO-0114/finance-approve", headers=TECH)
    check(
        "㊲ 정비사 finance-approve → 403 (role 사유, D119)",
        r.status_code == 403 and "자금집행 승인" in r.json().get("detail", ""),
        f"{r.status_code} {r.json().get('detail', '')[:60]}",
    )

    r = client.post("/api/po/PO-0114/finance-approve", headers=MGR)
    check(
        "㊳ mgr-01(maintenance) finance-approve → 403 (department 사유 — 재무부, D119)",
        r.status_code == 403 and "재무부" in r.json().get("detail", ""),
        f"{r.status_code} {r.json().get('detail', '')[:60]}",
    )

    # PO-0117 은 이 스크립트 앞부분(체크 ⑧)에서 이미 approved 로 소비됐다 — 여전히
    # pending 인 PO-0115(시드 3건 중 PO-0116⑪ 반려, PO-0117⑧ 승인 후 유일하게 남는 건)로 검증한다.
    r = client.post("/api/po/PO-0115/finance-approve", headers=MGR_FIN)
    check(
        "㊴ mgr-02 finance-approve on pending(PO-0115) → 409 (state 순서 위반, D38 과 구분)",
        r.status_code == 409,
        f"{r.status_code} {r.json().get('detail', '')[:60]}",
    )

    # ㊴-b MQ-1710 — PO-0114 는 ㊵ 에서 finance_approved 로 소비되므로, "재무 결정 전
    # approved 표본" 검증은 반드시 ㊵ 의 POST 이전인 여기서 끼워 넣는다(스프린트 문서
    # 엣지 케이스 절이 명시한 조율 지점).
    d114 = client.get("/api/po/PO-0114", headers=MGR).json()
    fund114 = d114["documents_preview"]["fund_execution"]
    check(
        "㊴-b PO-0114 approved(재무 결정 전) — documents_preview.fund_execution non-null"
        " + SOD 미확정 문구('확인 전') (MQ-1710)",
        fund114 is not None and "확인 전" in fund114,
        f"state={d114['state']}, fund_execution 일부={(fund114[:80] if fund114 else None)!r}",
    )

    r = client.post("/api/po/PO-0114/finance-approve", headers=MGR_FIN)
    body = r.json()
    check(
        "㊵ mgr-02 finance-approve on approved(PO-0114) → 200 + finance_approved stamp",
        r.status_code == 200
        and body.get("state") == "finance_approved"
        and body.get("finance_decided_by") == "mgr-02"
        and body.get("finance_decided_at") is not None,
        f"{r.status_code}, state={body.get('state')}, finance_decided_by={body.get('finance_decided_by')}"
        f", finance_decided_at={body.get('finance_decided_at')}",
    )

    r = client.post(
        "/api/po/PO-0120/finance-reject", json={"reason": "일일 한도 초과"}, headers=MGR_FIN
    )
    body = r.json()
    check(
        "㊶ mgr-02 finance-reject on approved(PO-0120) → 200 + finance_rejected + 사유 저장",
        r.status_code == 200
        and body.get("state") == "finance_rejected"
        and body.get("finance_decision_note") == "일일 한도 초과",
        f"{r.status_code}, state={body.get('state')}, note={body.get('finance_decision_note')!r}",
    )

    r = client.post(
        "/api/po/PO-0114/finance-reject", json={"reason": "재검토"}, headers=MGR_FIN
    )
    check(
        "㊷ mgr-02 finance-reject on 이미 finance_approved 된 건(PO-0114) 재호출 → 409",
        r.status_code == 409,
        f"{r.status_code} {r.json().get('detail', '')[:60]}",
    )

    # ── ㊸~㊹ MQ-1710 — 자금집행요청서(03) 렌더 계약: 재무 결정 확정 표본 (D118·D119)
    d118 = client.get("/api/po/PO-0118", headers=MGR).json()
    fund118 = d118["documents_preview"]["fund_execution"]
    budget_line_118 = next((ln for ln in (fund118 or "").splitlines() if "예산 한도" in ln), "")
    check(
        "㊸ PO-0118(finance_approved) — fund_execution non-null + '자금집행 요청서' 헤더"
        " + budget_check 통과('통과')",
        fund118 is not None and "자금집행 요청서" in fund118 and "통과" in budget_line_118,
        f"state={d118['state']}, budget_line={budget_line_118!r}",
    )

    d119 = client.get("/api/po/PO-0119", headers=MGR).json()
    fund119 = d119["documents_preview"]["fund_execution"]
    budget_line_119 = next((ln for ln in (fund119 or "").splitlines() if "예산 한도" in ln), "")
    check(
        "㊹ PO-0119(finance_rejected, 예산 초과 표본) — fund_execution 텍스트 예산 한도"
        " 줄에 '초과' 문구 (budget_check ok=False 실증)",
        fund119 is not None and "초과" in budget_line_119,
        f"state={d119['state']}, budget_line={budget_line_119!r}",
    )


def run_print_page_checks() -> None:
    """`_attach_print_pages` (D57) 순수 함수 검증 — DB·HTTP 없이 딕셔너리로만.

    ②-b 가 실 DB(PO-0117, model=iG5A 확정 후)로 "값이 있을 때 offset 0 정합"을 이미
    실측했으니, 여기서는 **S100(offset 16) 실환산·model 없음·manual_page 없음** 등
    실 시드에는 없는 분기를 DB 를 mutate하지 않고 함수 직접 호출로 커버한다.
    """
    from backend.services.po import _attach_print_pages  # noqa: PLC0415

    # ㉔ iG5A(offset 0) — 물리=인쇄 이므로 값이 그대로
    po = {"model": "iG5A", "evidence": {"basis": [{"tool": "lookup_error_code", "manual_page": 202}]}}
    _attach_print_pages(po)
    check(
        "㉗ D57 print_page — iG5A(offset 0): 202 → 202",
        po["evidence"]["basis"][0].get("print_page") == 202,
        f"{po['evidence']['basis'][0]}",
    )

    # ㉕ S100(offset 16) — 실제 환산이 걸리는 케이스 (★ 음성: 202 그대로면 오프셋 미적용)
    po = {"model": "S100", "evidence": {"basis": [{"tool": "lookup_error_code", "manual_page": 202}]}}
    _attach_print_pages(po)
    check(
        "㉘ D57 print_page — S100(offset 16): 202 → 186 (★ 음성: 202 면 오프셋 미적용)",
        po["evidence"]["basis"][0].get("print_page") == 186,
        f"{po['evidence']['basis'][0]}",
    )

    # ㉖ model 없음 → 필드 자체를 안 붙인다 (지어낸 값 금지)
    po = {"model": None, "evidence": {"basis": [{"tool": "lookup_error_code", "manual_page": 202}]}}
    _attach_print_pages(po)
    check(
        "㉙ D57 print_page — model 없음 → 필드 없음",
        "print_page" not in po["evidence"]["basis"][0],
        f"{po['evidence']['basis'][0]}",
    )

    # ㉗ basis 항목에 manual_page 자체가 없으면(예: search_inventory) 그 항목은 그대로
    po = {
        "model": "iG5A",
        "evidence": {"basis": [{"tool": "search_inventory", "part_no": "FAN-IG5-01"}]},
    }
    _attach_print_pages(po)
    check(
        "㉚ D57 print_page — manual_page 없는 basis 항목은 무영향",
        "print_page" not in po["evidence"]["basis"][0],
        f"{po['evidence']['basis'][0]}",
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("REST API 계약 검증 — 상태 전이 = 권한 (임시 DB 사본)\n")
    if not dbcompat.USE_POSTGRES and not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    schema = None
    try:
        with tempfile.TemporaryDirectory() as td:
            if dbcompat.USE_POSTGRES:
                import backend.db as bdb  # noqa: PLC0415

                schema, db = pg_isolation.create_isolated_schema("api_contract")
                bdb.DB_PATH = db  # TestClient 는 같은 프로세스 안이라 이걸로 충분하다
            else:
                db = Path(td) / "api.db"
                shutil.copy2(SOURCE_DB, db)
                os.environ["MAINTQ_DB"] = str(db)
            seed_trace_fixture(db)

            sys.path.insert(0, str(ROOT))
            from fastapi.testclient import TestClient  # noqa: PLC0415

            from backend.main import app  # noqa: PLC0415

            with TestClient(app) as client:
                run(client)
            run_print_page_checks()
    finally:
        if schema:
            pg_isolation.drop_isolated_schema(schema)

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 40))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 40))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(
        f"\n통과 ({len(results)}건) — 권한 403·전이 409·D29 기록·GET /trace(D43)·"
        "department 는 헤더 스푸핑 불가·DB 조회만(D108) 확인"
    )


if __name__ == "__main__":
    main()
