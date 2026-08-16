# -*- coding: utf-8 -*-
"""통합 승인 큐 · 처분 서명 REST 계약 회귀 (MQ-707 — S10 계층 3).

이 스위트가 지키는 두 문장은 사용자 요청의 헤드라인이다:

    **"BLOCKING 우회 처분 0건"** · **"서명 없는 처분 확정 0건"**

그 증명은 4층이고, 여기서는 **3층(REST 순서 강제)과 4층(DB CHECK)** 을 본다.
1·2층(도구에 UPDATE 권한 없음 / 도구 스키마에 override 없음)은 `write_tool_contract` 소관이다.

★ **깨지지 않는 검사는 방어선이 아니다.** ㉑ 은 CHECK 를 제거한 **뮤턴트 테이블**에서
  같은 SQL 이 **통과**하는 것까지 확인한다 — 거부의 원인이 CHECK 임을 실증하지 않으면
  "막힌다"는 관찰은 우연일 수 있다.

★ **순서가 계약이다** (D84). ⑮ 는 *근거 변경*과 *BLOCKED* 를 **동시에** 만든 케이스에서
  `evidence_changed` 가 나오는지 본다. `override_required` 가 나오면 FAIL 이다 —
  근거가 바뀐 상태에서 override 를 받으면 "사람이 본 것과 다른 근거에 서명"이 된다.

★ **실 DB 는 읽기만 한다.** 전부 임시 폴더의 사본에서 돌린다.

실행:  uv run python spikes/approvals_contract.py
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DB = ROOT / "data" / "maintq.db"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "spikes"))

# MCP 서브프로세스는 필요 없다 — 이 스위트는 사람 전용 REST 만 본다.
os.environ["MAINTQ_MCP_AUTOSTART"] = "0"

TECH = {"X-Role": "technician", "X-User": "tech-01"}
MGR = {"X-Role": "manager", "X-User": "mgr-01"}

# 처분일을 고정한다 — 오늘 날짜를 쓰면 `months_since_acquisition` 이 매일 달라져 기대 verdict
# 가 흔들린다 (`bundle_integrity.PROBE_DATE` 와 같은 이유).
PROBE_DATE = "2026-09-01"

MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    """번호는 자동 부여 — 손으로 박으면 검사를 끼워 넣을 때마다 뒤가 전부 밀린다."""
    mark = MARKS[len(results)] if len(results) < len(MARKS) else f"[{len(results) + 1}]"
    results.append((f"{mark} {name}", ok, detail))


# ── 픽스처 ──────────────────────────────────────────────────────────────────────
# MQ-706(`generate_disposal_document`)과 **병렬**로 개발되므로 도구에 의존하지 않는다.
# 대신 그 도구의 **draft INSERT 계약**(sprint-7 §MQ-706 표)을 여기서 그대로 재현한다 —
# `override=0` · `override_reason NULL` · `reviewed_by/signed_at NULL` · `state='draft'` ·
# `evidence_bundle` 은 **번들의 정준 직렬화 그대로**.
FIXTURES = [
    # (decision_id, asset_id, disposal_mode, state, 기대 verdict, 용도)
    ("DEC-Q001", "AST-L3-LIFT", "SALE", "pending", "CONDITIONAL", "큐 조회 · 반려"),
    ("DEC-S001", "AST-L3-LIFT", "SCRAP", "draft", "CLEAR", "submit → sign 정상 경로"),
    ("DEC-B001", "AST-L3-CONV", "SALE", "pending", "BLOCKED", "override_required · 422 · override 서명"),
    ("DEC-X001", "AST-L3-CONV", "SALE", "pending", "BLOCKED", "직접 SQL 뚫기 대상(BLOCKED)"),
    ("DEC-E001", "AST-L2-SPDL", "SALE", "pending", "CONDITIONAL", "evidence_changed · 직접 SQL 뚫기(서명요소)"),
    ("DEC-O001", "AST-L3-LIFT", "SCRAP", "pending", "CLEAR", "순서 잠금(근거변경 + BLOCKED)"),
]


def seed_decisions(db: Path) -> dict[str, dict]:
    """MCP 도구로 **실제 번들**을 만들고 draft 계약대로 INSERT 한다.

    도구를 부르는 이유: 번들 조립 규약(정준 직렬화·정렬·`rule_hash`)이 backend 재산출과
    **바이트 수준으로 같은지**가 이 스위트의 핵심 대조(⑲)이기 때문이다. 픽스처를 backend
    자신으로 만들면 그 대조가 동어반복이 된다.
    """
    import mcp_server.db as mcp_db  # noqa: PLC0415

    saved = mcp_db.DB_PATH
    mcp_db.DB_PATH = db
    try:
        from mcp_server.tools.build_evidence_bundle import (  # noqa: PLC0415
            build_evidence_bundle,
            canonical_json,
        )

        built: dict[str, dict] = {}
        con = sqlite3.connect(db)
        try:
            for decision_id, asset_id, mode, state, expected, _use in FIXTURES:
                res = build_evidence_bundle(
                    asset_id=asset_id, disposal_mode=mode, disposal_date=PROBE_DATE
                )
                if res.get("status") != "ok":
                    raise SystemExit(f"[중단] 번들 생성 실패 {decision_id}: {res}")
                if res["verdict"] != expected:
                    raise SystemExit(
                        f"[중단] {decision_id} 기대 verdict {expected} ≠ 실측 {res['verdict']}"
                        " — 시드가 바뀌었다. 픽스처를 고칠 것"
                    )
                con.execute(
                    "INSERT INTO decisions (decision_id, asset_id, decision_type,"
                    " evidence_bundle, bundle_hash, verdict_at_signing, override,"
                    " override_reason, reviewed_by, signed_at, state, reason, requested_by)"
                    " VALUES (?,?,'DISPOSAL',?,?,?,0,NULL,NULL,NULL,?,?,?)",
                    (
                        decision_id,
                        asset_id,
                        canonical_json(res["evidence_bundle"]),
                        res["bundle_hash"],
                        res["verdict"],
                        state,
                        f"{asset_id} {mode} 처분 요청 (회귀 픽스처)",
                        "tech-01" if state != "draft" else None,
                    ),
                )
                built[decision_id] = res
            con.commit()
        finally:
            con.close()
        return built
    finally:
        mcp_db.DB_PATH = saved


def mutate(db: Path, sql: str, args: tuple = ()) -> None:
    con = sqlite3.connect(db)
    try:
        con.execute(sql, args)
        con.commit()
    finally:
        con.close()


def query_one(db: Path, sql: str, args: tuple = ()) -> tuple:
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, args).fetchone()
    finally:
        con.close()


# ── 검사 본체 ───────────────────────────────────────────────────────────────────
def run(client, db: Path, built: dict[str, dict]) -> None:
    from api_contract import PO_DETAIL_KEYS, PO_LIST_ITEM_KEYS  # noqa: PLC0415

    # ① 통합 큐가 po·disposal 양쪽을 담는다 (D85)
    r = client.get("/api/approvals", params={"state": "pending"}, headers=MGR)
    body = r.json()
    kinds = [i["kind"] for i in body["items"]]
    check(
        "/api/approvals?state=pending 이 po·disposal 양쪽을 담는다",
        r.status_code == 200 and "po" in kinds and "disposal" in kinds,
        f"{r.status_code} · {len(kinds)}건 · kind 분포="
        f"{ {k: kinds.count(k) for k in set(kinds)} }",
    )

    # ② kind 필터
    only_po = client.get("/api/approvals", params={"kind": "po"}, headers=MGR).json()["items"]
    only_dec = client.get(
        "/api/approvals", params={"kind": "disposal"}, headers=MGR
    ).json()["items"]
    check(
        "kind 필터 동작 (po / disposal)",
        only_po and only_dec
        and {i["kind"] for i in only_po} == {"po"}
        and {i["kind"] for i in only_dec} == {"disposal"},
        f"po={len(only_po)}건 · disposal={len(only_dec)}건",
    )

    # ③ repair 는 MQ-909(Stage 5) 이후 REST 로 실제 노출된다 — 통합 큐 3종째.
    #    **양성 축**: `repair_records` 실측 건수(사본 DB 직접 조회)와 REST 응답 건수가
    #    **정확히 일치**해야 한다(0건이면 스캐너가 눈이 먼 것과 "정말 없다"를 구분 못 하므로
    #    CLAUDE.md 부재검사 규칙에 따라 이 대조가 필요하다). **음성 축**: kind 밖 값은 422.
    repair_total = query_one(db, "SELECT count(*) FROM repair_records")[0]
    con = sqlite3.connect(db)
    try:
        repair_by_state = dict(
            con.execute("SELECT state, count(*) FROM repair_records GROUP BY state").fetchall()
        )
    finally:
        con.close()
    rr = client.get("/api/approvals", params={"kind": "repair"}, headers=MGR)
    r_nope = client.get("/api/approvals", params={"kind": "nope"}, headers=MGR)
    rr_items = rr.json().get("items", []) if rr.status_code == 200 else []
    check(
        "kind=repair → 200·REST 건수 == repair_records 실측 건수 (양성 축) "
        "· kind 밖 값 → 422 (음성 축)",
        rr.status_code == 200
        and repair_total > 0
        and len(rr_items) == repair_total
        and all(i["kind"] == "repair" for i in rr_items)
        and rr.json()["kinds"] == ["po", "disposal", "repair"]
        and r_nope.status_code == 422,
        f"repair={repair_total}(분포={repair_by_state}) · REST={len(rr_items)}건 · "
        f"kinds=3 · kind=nope→{r_nope.status_code}",
    )

    # ④ state 는 **각 종류의 원 어휘 그대로** — 공통 어휘로 정규화 금지
    all_items = client.get("/api/approvals", headers=MGR).json()["items"]
    po_states = {i["state"] for i in all_items if i["kind"] == "po"}
    dec_states = {i["state"] for i in all_items if i["kind"] == "disposal"}
    check(
        "state 가 원 어휘 그대로 (approved ≠ signed, 정규화 금지)",
        po_states <= {"draft", "pending", "approved", "rejected"}
        and dec_states <= {"draft", "pending", "signed", "rejected"}
        and "draft" in dec_states,  # 픽스처 DEC-S001
        f"po={sorted(po_states)} · disposal={sorted(dec_states)}",
    )

    # ⑤ 처분서에는 긴급도가 없다 → null. 발주에는 판정이 없다 → null (양쪽 다 지어내지 않는다)
    dec_sample = next(i for i in all_items if i["kind"] == "disposal")
    po_sample = next(i for i in all_items if i["kind"] == "po")
    check(
        "urgency 가 처분서에서 null · verdict 가 발주에서 null (지어내지 않는다)",
        dec_sample["urgency"] is None
        and dec_sample["verdict"] in ("BLOCKED", "CONDITIONAL", "CLEAR", "HOLD", "INSUFFICIENT_FACTS")
        and po_sample["verdict"] is None
        and po_sample["requires_override"] is None,
        f"disposal.urgency={dec_sample['urgency']!r}/verdict={dec_sample['verdict']!r} · "
        f"po.verdict={po_sample['verdict']!r}/requires_override={po_sample['requires_override']!r}",
    )

    # ⑥ detail_path 는 서버가 만든 링크다 — **그대로** 따라가야 링크 유효성이 실제로 검증된다
    codes = {i["detail_path"]: client.get(i["detail_path"], headers=MGR).status_code
             for i in all_items}
    check(
        "모든 detail_path 가 실제 200",
        all(v == 200 for v in codes.values()),
        f"{len(codes)}개 경로 · 비200={[k for k, v in codes.items() if v != 200] or '없음'}",
    )

    # ⑦ submit — 정비사만
    r = client.post("/api/decisions/DEC-S001/submit", headers=TECH)
    check(
        "정비사 submit → 200 · draft→pending · requested_by stamp (D23·D37)",
        r.status_code == 200
        and r.json()["state"] == "pending"
        and r.json()["requested_by"] == "tech-01",
        f"{r.status_code} state={r.json().get('state')} requested_by={r.json().get('requested_by')}",
    )

    # ⑧ 403 **양방향** — 한쪽만 보면 반쪽이다
    r_mgr_submit = client.post("/api/decisions/DEC-B001/submit", headers=MGR)
    r_tech_sign = client.post("/api/decisions/DEC-B001/sign", json={}, headers=TECH)
    check(
        "403 대칭 — 팀장 submit → 403 · 정비사 sign → 403",
        r_mgr_submit.status_code == 403 and r_tech_sign.status_code == 403,
        f"manager submit={r_mgr_submit.status_code} · technician sign={r_tech_sign.status_code}",
    )

    # ⑨ sign 정상 경로 (CLEAR 자산 — override 불필요)
    r = client.post("/api/decisions/DEC-S001/sign", json={"note": "정상 서명"}, headers=MGR)
    signed = r.json()
    check(
        "팀장 sign → 200 · signed · verdict_at_signing 이 재산출 값",
        r.status_code == 200
        and signed["state"] == "signed"
        and signed["verdict_at_signing"] == "CLEAR"
        and signed["override"] is False,
        f"{r.status_code} state={signed.get('state')} verdict={signed.get('verdict_at_signing')}",
    )

    # ⑩ 이미 signed 인 건 재서명 → 409 (403 과 구분)
    r = client.post("/api/decisions/DEC-S001/sign", json={}, headers=MGR)
    r404 = client.post("/api/decisions/DEC-NOPE/sign", json={}, headers=MGR)
    r_draft_sign = client.post("/api/decisions/DEC-Q001/submit", headers=TECH)
    check(
        "재서명 → 409 · 없는 decision_id → 404 · pending 재submit → 409",
        r.status_code == 409
        and r.json()["reason"] == "invalid_transition"
        and r404.status_code == 404
        and r_draft_sign.status_code == 409,
        f"재서명={r.status_code}({r.json().get('reason')}) · 404={r404.status_code}"
        f" · 재submit={r_draft_sign.status_code}",
    )

    # ⑪ reject — 사유 필수 (D38)
    r_noreason = client.post("/api/decisions/DEC-Q001/reject", json={}, headers=MGR)
    r_rej = client.post(
        "/api/decisions/DEC-Q001/reject", json={"reason": "매각 시점 재검토"}, headers=MGR
    )
    check(
        "반려 — 사유 없으면 422 · 사유 있으면 rejected + 사유 저장",
        r_noreason.status_code == 422
        and r_rej.status_code == 200
        and r_rej.json()["state"] == "rejected"
        and r_rej.json()["decision_note"] == "매각 시점 재검토",
        f"사유없음={r_noreason.status_code} · 반려={r_rej.status_code}"
        f" note={r_rej.json().get('decision_note')!r}",
    )

    # ⑫ 정비사 reject → 403 (403 대칭 보강)
    r = client.post("/api/decisions/DEC-B001/reject", json={"reason": "x"}, headers=TECH)
    check(
        "정비사 reject → 403",
        r.status_code == 403,
        f"{r.status_code} {r.json().get('detail', '')[:40]}",
    )

    # ⑬ BLOCKED + override 미지정 → 409 override_required (S4 태도: 무엇이 막고 무엇을 하면 풀리는지)
    r = client.post("/api/decisions/DEC-B001/sign", json={}, headers=MGR)
    b = r.json()
    check(
        "BLOCKED + override 없음 → 409 override_required + blockers·resolve_options",
        r.status_code == 409
        and b["reason"] == "override_required"
        and b["verdict"] == "BLOCKED"
        and len(b["blockers"]) >= 1
        and len(b["resolve_options"]) >= 1,
        f"{r.status_code} {b.get('reason')} verdict={b.get('verdict')}"
        f" blockers={[x['rule_id'] for x in b.get('blockers', [])]}"
        f" resolve={len(b.get('resolve_options', []))}건",
    )

    # ⑭ override=true + 사유 공백 → 422 (DB CHECK 는 2차 방어선)
    r_blank = client.post(
        "/api/decisions/DEC-B001/sign",
        json={"override": True, "override_reason": "   "},
        headers=MGR,
    )
    r_none = client.post(
        "/api/decisions/DEC-B001/sign", json={"override": True}, headers=MGR
    )
    check(
        "override=true + 사유 공백/누락 → 422 (D63)",
        r_blank.status_code == 422 and r_none.status_code == 422,
        f"공백={r_blank.status_code} · 누락={r_none.status_code}",
    )

    # override 정상 서명 — ⑯ 에서 판정한다 (⑮ 의 자산 변조보다 **먼저** 실행해야 한다)
    r_ovr = client.post(
        "/api/decisions/DEC-B001/sign",
        json={"override": True, "override_reason": "법무 검토 완료 — 담보권자 동의 별건 확보"},
        headers=MGR,
    )

    # ⑮ evidence_changed — 자산 UPDATE 를 **실제로 주입**한다
    #    ⓐ 판정은 그대로인데 사실만 바뀐 경우(policy_id) → evidence_changed
    #    ⓑ 근거 변경 **과** BLOCKED 를 동시에 만든 경우 → **evidence_changed 가 이겨야 한다**
    #       (`override_required` 가 나오면 "사람이 본 것과 다른 근거에 override" 가 된다 — D84)
    mutate(db, "UPDATE assets SET policy_id='CHANGED-BY-SPIKE' WHERE asset_id='AST-L2-SPDL'")
    r_ec = client.post("/api/decisions/DEC-E001/sign", json={}, headers=MGR)
    mutate(
        db,
        "UPDATE assets SET has_lien=1, lien_creditor='스파이크은행', lien_consent_ref=NULL"
        " WHERE asset_id='AST-L3-LIFT'",
    )
    r_order = client.post("/api/decisions/DEC-O001/sign", json={}, headers=MGR)
    r_order_ovr = client.post(
        "/api/decisions/DEC-O001/sign",
        json={"override": True, "override_reason": "우회 시도"},
        headers=MGR,
    )
    check(
        "자산 UPDATE 주입 → 409 evidence_changed · **순서 잠금**(근거변경+BLOCKED → override_required 아님)",
        r_ec.status_code == 409
        and r_ec.json()["reason"] == "evidence_changed"
        and r_ec.json()["bundle_hash"] != r_ec.json()["recomputed_hash"]
        and r_order.status_code == 409
        and r_order.json()["reason"] == "evidence_changed"
        and r_order_ovr.status_code == 409
        and r_order_ovr.json()["reason"] == "evidence_changed",
        f"ⓐ policy_id 변경={r_ec.status_code}/{r_ec.json().get('reason')} · "
        f"ⓑ 담보 주입(CLEAR→BLOCKED)={r_order.status_code}/{r_order.json().get('reason')} · "
        f"ⓑ+override={r_order_ovr.status_code}/{r_order_ovr.json().get('reason')}",
    )

    # ⑯ 서명 후 signed_at·reviewed_by non-null (DB 행을 직접 읽는다 — 응답만 보면 UPDATE 를 못 본다)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = {
        r["decision_id"]: dict(r)
        for r in con.execute(
            "SELECT * FROM decisions WHERE decision_id IN ('DEC-S001','DEC-B001')"
        )
    }
    con.close()
    s, bl = rows["DEC-S001"], rows["DEC-B001"]
    check(
        "서명 후 signed_at·reviewed_by non-null · override 서명은 사유와 함께 기록",
        r_ovr.status_code == 200
        and s["signed_at"] and s["reviewed_by"] == "mgr-01" and s["override"] == 0
        and bl["state"] == "signed" and bl["signed_at"] and bl["reviewed_by"] == "mgr-01"
        and bl["override"] == 1 and (bl["override_reason"] or "").strip()
        and bl["verdict_at_signing"] == "BLOCKED",
        f"override 서명={r_ovr.status_code} · DEC-S001(signed_at={bool(s['signed_at'])},"
        f" override={s['override']}) · DEC-B001(override={bl['override']},"
        f" reason={(bl['override_reason'] or '')[:20]!r}, verdict={bl['verdict_at_signing']})",
    )

    # ⑰ GET /api/decisions/{id} — D86 강제 고지 2종 + `12 §8` 3종 렌더 + `12 §11` 서명분만
    #    DEC-B001(AST-L3-CONV) 을 쓰는 이유: BLOCKED 라 **인용 조문이 실제로 있고**,
    #    이 자산에만 서명된 `repair_records` 가 붙어 있어 증빙 3종이 전부 비지 않는다.
    #    빈 문서로 통과하는 검사는 렌더 경로를 검증하지 못한다.
    d = client.get("/api/decisions/DEC-B001", headers=TECH).json()
    docs = d["documents"]
    pkg = docs["evidence_package"]
    unsigned_leak = [h for h in pkg["maintenance_history"] if not h["signed_at"]]
    check(
        "상세에 missing_sections·hash_fixed:false · 증빙 3종 · 서명분만 (D86·12 §11)",
        docs["hash_fixed"] is False
        and docs["missing_sections"] == ["감가상각 명세 — 상각 스케줄 원천 없음"]
        and "서명 해시로 고정되지 않는다" in docs["hash_fixed_note"]
        and {"approval", "representation_warranty", "evidence_package"} <= set(docs)
        and docs["approval"]["law_footnotes"]
        and all(f["citation"] for f in docs["approval"]["law_footnotes"])
        and docs["approval"]["blockers"]
        and docs["representation_warranty"]["statements"]
        and pkg["maintenance_history"]
        and not unsigned_leak,
        f"hash_fixed={docs['hash_fixed']} · missing={docs['missing_sections']} · "
        f"이력 {len(pkg['maintenance_history'])}건(미서명 누출 {len(unsigned_leak)}) · "
        f"각주 {len(docs['approval']['law_footnotes'])}건 · "
        f"핵심부품 {len(pkg['critical_parts_renewal'])}건",
    )

    # ⑱ `/api/po` 응답 **키 집합** 불변 (D85). 값이 아니라 키집합이다 —
    #    값만 보는 검사는 키가 늘거나 사라져도 통과한다
    po_items = client.get("/api/po", headers=MGR).json()["items"]
    po_detail = client.get(f"/api/po/{po_items[0]['po_id']}", headers=MGR).json()
    bad = [i["po_id"] for i in po_items if set(i) != PO_LIST_ITEM_KEYS]
    check(
        "/api/po 응답 키집합 불변 — 통합 큐 도입 무회귀 (D85)",
        not bad and set(po_detail) == PO_DETAIL_KEYS,
        f"목록 {len(po_items)}건 · 키 어긋난 항목={bad or '없음'} · "
        f"상세 키차이={set(po_detail) ^ PO_DETAIL_KEYS or '없음'}",
    )

    # ── 보강 3건 (명세 18건 밖 — 드리프트·뮤턴트) ────────────────────────────────
    # ⑲ backend 재산출 == MCP 도구 산출. backend 는 `mcp_server` 를 import 할 수 없어(D15)
    #    번들 조립 규약을 **한 벌 더** 갖는다. 어긋나면 모든 서명이 evidence_changed 로 막힌다.
    import backend.services.decisions as dec_svc  # noqa: PLC0415
    from backend.services.disposal import read_only  # noqa: PLC0415

    tool_res = built["DEC-B001"]  # 변조되지 않은 자산(AST-L3-CONV)의 도구 산출물
    with read_only(db) as con:
        rb, rb_hash, judgment = dec_svc.rebuild_bundle(con, "AST-L3-CONV", "SALE", PROBE_DATE)
    check(
        "backend 번들 재산출 == MCP 도구 산출 (해시·본문 동일 — 규약 드리프트 방어)",
        rb_hash == tool_res["bundle_hash"]
        and rb == tool_res["evidence_bundle"]
        and judgment["verdict"] == tool_res["verdict"],
        f"도구={tool_res['bundle_hash'][:24]} · backend={rb_hash[:24]} · "
        f"verdict={judgment['verdict']}",
    )

    # ⑳ 증빙 패키지의 보전지표가 `get_maintenance_metrics` 와 **같은 산식**인가 (12 §2·D70)
    import mcp_server.db as mcp_db  # noqa: PLC0415

    saved_path = mcp_db.DB_PATH
    mcp_db.DB_PATH = db
    try:
        from mcp_server.tools.get_maintenance_metrics import (  # noqa: PLC0415
            get_maintenance_metrics,
        )

        tool_m = get_maintenance_metrics(asset_id="AST-L3-CONV")
    finally:
        mcp_db.DB_PATH = saved_path
    with read_only(db) as con:
        mine = dec_svc._metrics(con, "AST-L3-CONV")
    # ★ 숫자 11필드만 보면 **고지가 갈린 것을 못 잡는다.** 산식이 같아도 "무엇을 제외했는가"
    #   가 다르면 증빙 패키지는 *확인 안 된 항목을 확인된 것처럼* 보이게 된다 (D65).
    #   그래서 `excluded`(순서까지) 와 `disclaimer` 를 대조 범위에 넣는다.
    shared = (
        "mtbf_days", "mtbf_basis", "mttr_hours", "availability", "planned_ratio",
        "n_repairs_signed", "n_repairs_unsigned", "acquisition_cost",
        "cumulative_repair_cost", "cumulative_repair_ratio", "window_months",
        "excluded", "disclaimer",
    )
    diff = {k: (tool_m.get(k), mine.get(k)) for k in shared if tool_m.get(k) != mine.get(k)}
    check(
        "증빙 패키지 보전지표 == get_maintenance_metrics (숫자 11 + excluded·disclaimer)",
        not diff
        and bool(mine.get("excluded"))
        and "판단 근거 부족" in (mine.get("disclaimer") or ""),
        f"대조 {len(shared)}필드 · 불일치={ {k: v for k, v in diff.items()} or '없음'} · "
        f"mtbf={mine['mtbf_days']}일/{mine['mtbf_basis']}, mttr={mine['mttr_hours']}h · "
        f"excluded {len(mine.get('excluded') or [])}건",
    )

    # ⑳-b `disclaimer` 가 **응답에 실제로 실리는가** — `_metrics()` 직접 호출만 보면
    #     `render_documents` 가 필드를 떨어뜨려도 통과한다. HTTP 응답을 다시 읽는다.
    pkg_metrics = client.get("/api/decisions/DEC-B001", headers=TECH).json()["documents"][
        "evidence_package"
    ]["metrics"]
    check(
        "evidence_package.metrics 에 disclaimer·excluded 가 실려 나간다 (D65·D86)",
        pkg_metrics.get("disclaimer") == tool_m["disclaimer"]
        and pkg_metrics.get("excluded") == tool_m["excluded"],
        f"disclaimer={(pkg_metrics.get('disclaimer') or '')[:34]!r}… · "
        f"excluded={len(pkg_metrics.get('excluded') or [])}건",
    )

    # ⑳-c **파싱 실패 고지** — 깨진 `occurred_at` 을 주입해 두 구현이 *같은 문장으로* 고지하는지.
    #     ⑳ 는 정상 데이터만 보므로 이 분기를 통과시킨다: backend 가 조용히 버려도 안 걸린다.
    eq_id = query_one(db, "SELECT equipment_id FROM equipment WHERE asset_id='AST-L3-CONV'")[0]
    mutate(
        db,
        "INSERT INTO error_history (equipment_id, code, occurred_at, resolved)"
        " VALUES (?, 'E-SPIKE', '깨진-시각-값', 1)",
        (eq_id,),
    )
    try:
        mcp_db.DB_PATH = db
        try:
            tool_bad = get_maintenance_metrics(asset_id="AST-L3-CONV")
        finally:
            mcp_db.DB_PATH = saved_path
        with read_only(db) as con:
            mine_bad = dec_svc._metrics(con, "AST-L3-CONV")
        notice = "occurred_at 을 해석하지 못한 에러 이력 1건은 집계에서 제외했다"
        check(
            "occurred_at 파싱 실패가 excluded 에 고지된다 (조용히 버리지 않는다 — D65)",
            notice in tool_bad["excluded"]
            and notice in mine_bad["excluded"]
            and tool_bad["excluded"] == mine_bad["excluded"],
            f"도구={notice in tool_bad['excluded']} · backend={notice in mine_bad['excluded']} · "
            f"excluded 동일={tool_bad['excluded'] == mine_bad['excluded']} "
            f"(backend {len(mine_bad['excluded'])}건)",
        )
    finally:
        mutate(db, "DELETE FROM error_history WHERE code='E-SPIKE'")

    # ㉑ **직접 SQL 로 뚫기 2건** + 뮤턴트 대조.
    #    "막힌다"만으로는 부족하다 — CHECK 를 제거한 테이블에서 **같은 SQL 이 통과**해야
    #    거부의 원인이 CHECK 임이 증명된다.
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=ON")
    try:
        bypass = []
        for label, sql in (
            (
                "ⓐ signed_at 없이 signed",
                "UPDATE decisions SET state='signed' WHERE decision_id='DEC-E001'",
            ),
            (
                "ⓑ BLOCKED 를 override=0 으로 signed",
                "UPDATE decisions SET state='signed', signed_at='2026-08-10 00:00:00',"
                " reviewed_by='mgr-01' WHERE decision_id='DEC-X001'",
            ),
        ):
            con.execute("SAVEPOINT bypass")
            try:
                con.execute(sql)
                bypass.append((label, False, "통과해버림"))
            except sqlite3.IntegrityError as exc:
                bypass.append((label, True, str(exc).splitlines()[0]))
            finally:
                con.execute("ROLLBACK TO bypass")
                con.execute("RELEASE bypass")

        # 뮤턴트 — 두 CHECK 만 제거한 사본 테이블
        ddl = con.execute("SELECT sql FROM sqlite_master WHERE name='decisions'").fetchone()[0]
        # ⚠ 저장된 DDL 에는 주석이 그대로 남는다 — `,\s*CHECK` 는 콤마와 CHECK 사이의
        #   `-- …` 줄을 건너뛰지 못한다. 주석을 먼저 지우지 않으면 뮤턴트가 조용히
        #   **원본과 같아져** "뮤턴트에서도 거부됨" = 위양성 FAIL 이 난다 (실측).
        mutant = re.sub(r"--[^\n]*", "", ddl)
        mutant = mutant.replace("CREATE TABLE decisions", "CREATE TABLE decisions_mutant", 1)
        mutant = re.sub(
            r",\s*CHECK \(state <> 'signed' OR \(signed_at.*?length\(trim\(bundle_hash\)\) > 0\)\)",
            "",
            mutant,
            flags=re.S,
        )
        mutant = re.sub(
            r",\s*CHECK \(state <> 'signed' OR override = 1\s*OR verdict_at_signing IN \([^)]*\)\)",
            "",
            mutant,
            flags=re.S,
        )
        stripped = "bundle_hash)) > 0" not in mutant and "verdict_at_signing IN (" not in mutant
        con.execute("SAVEPOINT mutant")
        con.execute(mutant)
        con.execute(
            "INSERT INTO decisions_mutant (decision_id, asset_id, decision_type,"
            " evidence_bundle, bundle_hash, verdict_at_signing, override, state)"
            " SELECT decision_id, asset_id, decision_type, evidence_bundle, bundle_hash,"
            " verdict_at_signing, override, state FROM decisions WHERE decision_id IN"
            " ('DEC-E001','DEC-X001')"
        )
        mutant_passed = []
        for label, sql in (
            ("ⓐ", "UPDATE decisions_mutant SET state='signed' WHERE decision_id='DEC-E001'"),
            (
                "ⓑ",
                "UPDATE decisions_mutant SET state='signed', signed_at='2026-08-10 00:00:00',"
                " reviewed_by='mgr-01' WHERE decision_id='DEC-X001'",
            ),
        ):
            try:
                con.execute(sql)
                mutant_passed.append(label)
            except sqlite3.IntegrityError:
                pass
        con.execute("ROLLBACK TO mutant")
        con.execute("RELEASE mutant")
    finally:
        con.close()

    check(
        "직접 SQL 뚫기 2건 → CHECK 거부 · **CHECK 제거 뮤턴트에서는 통과**(방어선 실증)",
        all(ok for _, ok, _ in bypass) and stripped and mutant_passed == ["ⓐ", "ⓑ"],
        " · ".join(f"{lbl}: {'거부' if ok else '통과'}({msg[:60]})" for lbl, ok, msg in bypass)
        + f" · 뮤턴트 통과={mutant_passed}",
    )

    # ── 룰 카탈로그 장애 2종은 **같은 코드로 뭉치지 않는다** (W-11 · D38) ─────────────
    # 503 = "재시도하라". 그러니 재시도로 풀리는 것만 503 이어야 한다.
    #   ㉔ 인용 룰 소실  → 근거가 바뀐 것 = 사람의 재검토 → **409**
    #   ㉕ 카탈로그 0행 → 적재 미완 = 재시도·관리자 문의 → **503**
    # 두 경로를 **각각** 잠근다 — 한 검사로 뭉치면 분리한 의미가 없다.

    # ㉔ DEC-X001(AST-L3-CONV, BLOCKED, pending)은 변조되지 않았으므로 정상이면
    #    `override_required` 가 난다. 판정이 카탈로그에 없는 룰을 인용하도록 주입하면
    #    그보다 **먼저** cited_rule_missing 으로 막혀야 한다 (근거 무결성이 권한보다 앞선다).
    real_check = dec_svc.engine.check_disposal_blockers

    def _ghost_citation(facts, at=None, *, laws=None, rules=None):
        j = real_check(facts, at, laws=laws, rules=rules)
        j["blockers"] = list(j.get("blockers") or []) + [
            {"rule_id": "RULE-GHOST-999", "rule_version": 1, "law_refs": []}
        ]
        return j

    dec_svc.engine.check_disposal_blockers = _ghost_citation
    try:
        r_ghost = client.post("/api/decisions/DEC-X001/sign", json={}, headers=MGR)
    finally:
        dec_svc.engine.check_disposal_blockers = real_check
    gb = r_ghost.json()
    check(
        "인용 룰 소실 → **409** cited_rule_missing (503 `rule_catalog_invalid` 와 어휘까지 구분)",
        r_ghost.status_code == 409
        and gb.get("reason") == "cited_rule_missing"
        and "RULE-GHOST-999 v1" in (gb.get("missing_rules") or []),
        f"{r_ghost.status_code} reason={gb.get('reason')} missing_rules={gb.get('missing_rules')}",
    )

    # ㉕ 진짜 미적재(rules 0행)는 503 그대로 — 여기까지 409 로 내리면 "적재하세요"가 사라진다
    con = sqlite3.connect(db)
    try:
        cols = [d[0] for d in con.execute("SELECT * FROM rules LIMIT 1").description]
        backup = con.execute("SELECT * FROM rules").fetchall()
        con.execute("DELETE FROM rules")
        con.commit()
        r_empty = client.post("/api/decisions/DEC-X001/sign", json={}, headers=MGR)
    finally:
        con.executemany(
            f"INSERT INTO rules ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",  # noqa: S608
            backup,
        )
        con.commit()
        con.close()
    detail = r_empty.json().get("detail")
    check(
        "룰 카탈로그 0행 → **503** rule_catalog_not_loaded (적재 미완은 재시도 대상)",
        r_empty.status_code == 503
        and isinstance(detail, dict)
        and detail.get("reason") == "rule_catalog_not_loaded",
        f"{r_empty.status_code} reason={detail.get('reason') if isinstance(detail, dict) else detail} "
        f"· rules 복원={len(backup)}행",
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("통합 승인 큐 · 처분 서명 REST 계약 (임시 DB 사본)\n")
    if not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    before = (SOURCE_DB.stat().st_mtime_ns, SOURCE_DB.stat().st_size)

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "approvals.db"
        shutil.copy2(SOURCE_DB, db)
        for side in ("-wal", "-shm"):
            src = SOURCE_DB.with_name(SOURCE_DB.name + side)
            if src.exists():
                shutil.copy2(src, db.with_name(db.name + side))
        os.environ["MAINTQ_DB"] = str(db)

        built = seed_decisions(db)

        from fastapi.testclient import TestClient  # noqa: PLC0415

        from backend.main import app  # noqa: PLC0415

        with TestClient(app) as client:
            run(client, db, built)

    after = (SOURCE_DB.stat().st_mtime_ns, SOURCE_DB.stat().st_size)
    check(
        "실 DB mtime·size 불변 (사본만 썼다는 증거)",
        before == after,
        f"{'불변' if before == after else f'{before} → {after}'}",
    )

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 40))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 40))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(
        f"\n통과 ({len(results)}건) — BLOCKING 우회 0건·서명 없는 확정 0건이 "
        "REST 순서(D84)와 DB CHECK 양쪽에서 막힌다"
    )


if __name__ == "__main__":
    main()
