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
SOURCE_DB = ROOT / "data" / "maintq.db"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


TECH = {"X-Role": "technician", "X-User": "tech-01"}
MGR = {"X-Role": "manager", "X-User": "mgr-01"}


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


def seed_trace_fixture(db: Path) -> None:
    """traces 5행을 무작위 seq 순서로 직접 INSERT (백엔드 코드를 거치지 않는다)."""
    con = sqlite3.connect(db)
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
        "① 승인 큐 조회 (긴급 우선 정렬)",
        r.status_code == 200 and len(items) == 3 and items[0]["urgency"] == "urgent",
        f"{len(items)}건, 첫 항목 {items[0]['po_id']}({items[0]['urgency']})",
    )

    # ── 상세: 근거 카드·공급사 비교에 필요한 것이 한 번에 오는가
    d = client.get("/api/po/PO-0117", headers=MGR).json()
    check(
        "② 상세 — evidence·재고·견적·trace 링크",
        d["evidence"]["symptoms"]
        and d["inventory"]["qty"] == 1
        and len(d["quotes"]) == 2
        and d["trace_url"] == "/api/chat/S1/trace",
        f"quotes={len(d['quotes'])}, 재고={d['inventory']['qty']}, trace={d['trace_url']}",
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
        "㉔ D57 print_page — iG5A(offset 0): 202 → 202",
        po["evidence"]["basis"][0].get("print_page") == 202,
        f"{po['evidence']['basis'][0]}",
    )

    # ㉕ S100(offset 16) — 실제 환산이 걸리는 케이스 (★ 음성: 202 그대로면 오프셋 미적용)
    po = {"model": "S100", "evidence": {"basis": [{"tool": "lookup_error_code", "manual_page": 202}]}}
    _attach_print_pages(po)
    check(
        "㉕ D57 print_page — S100(offset 16): 202 → 186 (★ 음성: 202 면 오프셋 미적용)",
        po["evidence"]["basis"][0].get("print_page") == 186,
        f"{po['evidence']['basis'][0]}",
    )

    # ㉖ model 없음 → 필드 자체를 안 붙인다 (지어낸 값 금지)
    po = {"model": None, "evidence": {"basis": [{"tool": "lookup_error_code", "manual_page": 202}]}}
    _attach_print_pages(po)
    check(
        "㉖ D57 print_page — model 없음 → 필드 없음",
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
        "㉗ D57 print_page — manual_page 없는 basis 항목은 무영향",
        "print_page" not in po["evidence"]["basis"][0],
        f"{po['evidence']['basis'][0]}",
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("REST API 계약 검증 — 상태 전이 = 권한 (임시 DB 사본)\n")
    if not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    with tempfile.TemporaryDirectory() as td:
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

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 40))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 40))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(f"\n통과 ({len(results)}건) — 권한 403·전이 409·D29 기록·GET /trace(D43) 확인")


if __name__ == "__main__":
    main()
