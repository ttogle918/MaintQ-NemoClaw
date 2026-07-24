# -*- coding: utf-8 -*-
"""eval/score.py 계약 검증 (MQ-310) — **전부 합성 traces, DB·API 불필요**.

`score_session(events, expected)` 는 traces DB 를 읽지 않고 event 리스트를 인자로 받는다.
그래서 이 스파이크는 event 를 손으로 지어 넣어 4지표(부품 특정·인용·안전·시퀀스)를 검증한다.
event 형태는 `backend.agent.trace.read_trace` 스키마 `{seq, event, tool, data}` 를 따른다.

이 프로젝트는 "검사는 통과하는데 대상은 깨진" 사례가 4건 나왔다. 그래서 **되돌리면 실제로
fail 하는지**(음성 검증)를 citation·safety·sequence·S4 4개 지표에서 스크립트 안에서 확인하고
결과를 주석(★ 음성)으로 남긴다.

실행:  uv run python spikes/eval_score_contract.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.score import metric_rate, score_session  # noqa: E402

DB = ROOT / "data" / "maintq.db"
DB_MTIME_BEFORE = DB.stat().st_mtime_ns if DB.exists() else None

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


# ────────────────────────────────────────────── event 팩토리 (read_trace 형태)


def tc(tool: str, **inp) -> dict:
    return {"event": "tool_call", "tool": tool, "data": {"tool": tool, "input": inp, "ts": "Z"}}


def tr(tool: str, status: str, **extra) -> dict:
    """tool_result. 기본은 실 traces 처럼 **요약본**(page 없음). extra 로 manual_page/chunks 를
    실으면 더 풍부한 trace 를 흉내낸다 — 그때만 인용 값 일치가 strict 하게 걸린다."""
    data = {"tool": tool, "status": status, "summary": f"{tool} {status}", "elapsed": 0.2}
    data.update(extra)
    return {"event": "tool_result", "tool": tool, "data": data}


def cite(page: int) -> dict:
    inner = {"page": page, "print_page": page, "label": f"iG5A 매뉴얼 p.{page}"}
    return {"event": "block", "tool": None, "data": {"type": "citation", "data": inner}}


def safety(text: str, page: int | None) -> dict:
    inner: dict = {"title": "안전", "text": text}
    if page is not None:
        inner["citation"] = {"page": page, "print_page": page, "label": f"iG5A 매뉴얼 p.{page}"}
    return {"event": "block", "tool": None, "data": {"type": "safety", "data": inner}}


def po_card(variant: str, **kw) -> dict:
    inner = {"variant": variant, **kw}
    return {"event": "block", "tool": None, "data": {"type": "po_card", "data": inner}}


def verdict(vs, metric):
    return next(v for v in vs if v.metric == metric)


# ────────────────────────────────────────────── 시나리오


# S1 정상 — lookup(rich manual_page) → rag → search_inventory → create_po_draft → citation
S1_OK = [
    tc("lookup_error_code", model="iG5A", code="OHt"),
    tr("lookup_error_code", "ok", manual_page=202),
    tc("rag_search_manual", model="iG5A", query="냉각팬 점검"),
    tr("rag_search_manual", "ok", chunks=[{"page": 204, "section": "12.2"}]),
    tc("search_inventory", part_no="FAN-IG5-01", model="iG5A"),
    tr("search_inventory", "ok"),
    tc("create_po_draft", part_no="FAN-IG5-01", qty=2, supplier_id="SUP-A", reason="x"),
    tr("create_po_draft", "ok"),
    safety("작업 전 방전 대기 10분 이상 유지하십시오.", 4),
    cite(202),
    po_card("draft", po_id="PO-0117", part_no="FAN-IG5-01"),
]
S1_EXPECT = {
    "part_no": "FAN-IG5-01",
    "safety_required": True,
    "safety_page": 4,
}


def run() -> None:
    # ── ① 정상 케이스 전 지표 pass ─────────────────────────────
    vs = score_session(S1_OK, S1_EXPECT)
    check(
        "① 정상 S1 — 4지표 전부 pass",
        all(v.passed for v in vs),
        "; ".join(f"{v.metric}:{'P' if v.passed else 'F'}" for v in vs),
    )

    # ── ② citation page 불일치 → fail (근거 202 인데 인용 999) ──
    # **주의: 이 검사는 "합성 rich payload 한정" 이다.** S1_OK 의 tool_result 는
    # `manual_page=202`·`chunks=[…]` 를 실은 풍부한 형태인데, **실 loop.py 는 tool_result 에
    # 이 필드를 절대 싣지 않는다**(요약본만 — 06_REPO_API §tool_result). 즉 이 검사가 증명하는 건
    # "근거 소스가 주어졌을 때 union+strict 로직이 지어낸 페이지를 잡는다"이지,
    # "실 파이프라인이 지어낸 페이지를 잡는다"가 아니다. 실 형태(요약본)에서 어떻게 되는지는
    # ⑪ 이 본다 — 거기선 소스가 빈 집합이라 발행=근거 degraded 로 내려간다.
    # 이 둘을 한 검사로 뭉뚱그리면 "citation 지표가 실전에서 환각 페이지를 막는다"는 과신이 된다.
    bad = [e for e in S1_OK if e.get("data", {}).get("type") != "citation"] + [cite(999)]
    v_bad = verdict(score_session(bad, S1_EXPECT), "citation")
    v_ok = verdict(vs, "citation")
    check(
        "② citation page 불일치 → fail [합성 rich payload 한정] (★ 음성: 202→pass, 999→fail)",
        v_bad.passed is False and v_ok.passed is True,
        f"999:{v_bad.passed} / 202:{v_ok.passed}",
    )

    # ── ③ safety '5분'(기대 '10분') → fail ─────────────────────
    ev5 = [e for e in S1_OK if e.get("data", {}).get("type") != "safety"] + [
        safety("작업 전 방전 대기 5분 유지.", 4)
    ]
    v5 = verdict(score_session(ev5, S1_EXPECT), "safety")
    v10 = verdict(vs, "safety")
    check(
        "③ safety 기준값 완화('5분') → fail (★ 음성: 10분→pass, 5분→fail)",
        v5.passed is False and v10.passed is True,
        f"5분:{v5.passed} / 10분:{v10.passed}",
    )

    # ── ④ S3 에서 create_po_draft 호출 → sequence fail ─────────
    s3_events = [
        tc("lookup_error_code", model="iG5A", code="OCt"),
        tr("lookup_error_code", "ok", manual_page=204),
        tc("get_error_history", equipment_id="INV-L3-01", days=30),
        tr("get_error_history", "ok"),
        tc("rag_search_manual", model="iG5A", query="근본원인"),
        tr("rag_search_manual", "ok", chunks=[{"page": 206, "section": "12.3"}]),
        po_card("hold", reason="반복 고장", checklist=[], repeated={"count": 3, "window_days": 30}),
    ]
    s3_expect = {"expect_hold": True}
    v_hold_ok = verdict(score_session(s3_events, s3_expect), "sequence")
    s3_with_po = s3_events + [
        tc("create_po_draft", part_no="FAN-IG5-01", qty=2, supplier_id="SUP-A", reason="x"),
        tr("create_po_draft", "ok"),
    ]
    v_hold_bad = verdict(score_session(s3_with_po, s3_expect), "sequence")
    check(
        "④ S3 에서 create_po_draft → sequence fail (★ 음성: 미호출→pass, 호출→fail)",
        v_hold_bad.passed is False and v_hold_ok.passed is True,
        f"호출:{v_hold_bad.passed} / 미호출:{v_hold_ok.passed}",
    )

    # ── ⑤ catalog_not_loaded 를 S4 로 → fail (미적재는 S4 성공 아님, D50) ──
    s4_bad = [
        tc("lookup_error_code", model="iG5A", code="XY9"),
        tr("lookup_error_code", "error", reason="catalog_not_loaded"),
    ]
    s4_expect = {"expect_not_found": True}
    v_cnl = verdict(score_session(s4_bad, s4_expect), "citation")
    check(
        "⑤ catalog_not_loaded 를 S4 로 → citation fail 이고 분모 포함 (D50)",
        v_cnl.passed is False and v_cnl.applicable is True,
        f"passed={v_cnl.passed}, applicable={v_cnl.applicable}",
    )

    # ── ⑥ S4 정답(not_found) → 인용 분모 제외 (applicable=False) ──
    s4_ok = [
        tc("lookup_error_code", model="iG5A", code="XY9"),
        tr("lookup_error_code", "not_found"),
    ]
    v_nf = verdict(score_session(s4_ok, s4_expect), "citation")
    check(
        "⑥ S4 정답(not_found) → citation applicable=False (★ 음성: catalog→fail/포함)",
        v_nf.applicable is False and v_nf.passed is True and v_cnl.applicable is True,
        f"not_found.applicable={v_nf.applicable} / catalog.applicable={v_cnl.applicable}",
    )

    # ── ⑦ S4 정답이 인용률 분모를 흔들지 않는다 ────────────────
    # 정상 1건(pass) + S4 정답 1건 → 인용 분모는 1(정상만), 비율 100%.
    passed_n, denom = metric_rate([vs, score_session(s4_ok, s4_expect)], "citation")
    # S4 를 빼기 전이라면 분모가 2가 됐을 것 — 실제로 1인지 확인
    check(
        "⑦ S4 정답 → 인용 분모 제외로 인용률 불변 (통과 1 / 분모 1 = 100%)",
        (passed_n, denom) == (1, 1),
        f"통과 {passed_n} / 분모 {denom}",
    )

    # ── ⑧ 부품 특정 불일치 → part fail (★ 음성) ────────────────
    wrong_part = [e for e in S1_OK if _po_name(e) != "create_po_draft"] + [
        tc("create_po_draft", part_no="WRONG-01", qty=1, supplier_id="SUP-A", reason="x"),
        tr("create_po_draft", "ok"),
    ]
    v_pw = verdict(score_session(wrong_part, S1_EXPECT), "part")
    v_pok = verdict(vs, "part")
    check(
        "⑧ 부품 특정 불일치 → part fail (★ 음성: 정답→pass, 오답→fail)",
        v_pw.passed is False and v_pok.passed is True,
        f"오답:{v_pw.passed} / 정답:{v_pok.passed}",
    )

    # ── ⑨ 안전 근거 page 없음 → safety fail (절대규칙 3) ────────
    no_page = [e for e in S1_OK if e.get("data", {}).get("type") != "safety"] + [
        safety("작업 전 방전 대기 10분 이상 유지.", None)
    ]
    v_np = verdict(score_session(no_page, S1_EXPECT), "safety")
    check(
        "⑨ 안전 블록에 근거 page 없음 → safety fail",
        v_np.passed is False,
        v_np.detail,
    )

    # ── ⑩ 진단 응답인데 citation 블록 없음 → citation fail ─────
    no_cite = [e for e in S1_OK if e.get("data", {}).get("type") != "citation"]
    v_nc = verdict(score_session(no_cite, S1_EXPECT), "citation")
    check("⑩ citation 블록 미발행 → fail", v_nc.passed is False, v_nc.detail)

    # ── ⑪ tool_result 요약본(page 없음) → 발행=근거 degraded pass ──
    # 실 traces 의 기본 형태: tool_result 가 summary 만 담아 manual_page·chunks 가 없다.
    # 이때 근거 소스가 빈 집합이라 값 일치를 검사할 수 없으므로, 시스템이 도구 결과에서
    # 생성한 citation 을 **발행=근거**로 인정한다(degraded). 인용 블록 자체가 없으면(⑩) 여전히 fail.
    summary_only = [
        tc("lookup_error_code", model="iG5A", code="OHt"),
        tr("lookup_error_code", "ok"),  # ← manual_page 없음 (요약본)
        cite(202),
    ]
    v_deg = verdict(score_session(summary_only, {"part_no": None}), "citation")
    check(
        "⑪ tool_result 요약본(page 없음) → 발행=근거로 citation pass (degraded)",
        v_deg.passed is True and "degraded" in v_deg.detail,
        v_deg.detail,
    )

    # ── ⑫ 부품 특정 — create_po_draft 없으면 마지막 search_inventory 로 폴백 ──
    inv_only = [
        tc("search_inventory", part_no="FAN-IG5-01", model="iG5A"),
        tr("search_inventory", "ok"),
    ]
    v_inv = verdict(score_session(inv_only, {"part_no": "FAN-IG5-01"}), "part")
    check("⑫ create_po_draft 없으면 search_inventory 인자로 부품 특정", v_inv.passed, v_inv.detail)

    # ── ⑬ 위험 절차 아님 → safety applicable=False (분모 제외) ──
    v_nsr = verdict(score_session(S1_OK, {"part_no": "FAN-IG5-01"}), "safety")
    check(
        "⑬ safety_required 아님 → applicable=False (분모 제외)",
        v_nsr.applicable is False and v_nsr.passed is True,
        f"applicable={v_nsr.applicable}",
    )

    # ── ⑭ score_session 은 항상 4지표를 순서대로 반환 ──────────
    check(
        "⑭ score_session → [part, citation, safety, sequence] 4지표 고정",
        [v.metric for v in vs] == ["part", "citation", "safety", "sequence"],
        str([v.metric for v in vs]),
    )


def _po_name(ev: dict) -> str | None:
    return ev.get("tool")


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("eval/score.py 계약 검증 (합성 traces — DB·API 불필요)\n")
    if DB_MTIME_BEFORE is None:
        print("[주의] data/maintq.db 없음 — DB 를 열지 않으므로 판정에는 무관")

    run()

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 44))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 44))

    # data/maintq.db mtime 불변 — 이 판정기는 DB 를 절대 열지 않는다
    after = DB.stat().st_mtime_ns if DB.exists() else None
    db_unchanged = after == DB_MTIME_BEFORE
    print(f"\ndata/maintq.db mtime 불변: {db_unchanged} (before={DB_MTIME_BEFORE}, after={after})")
    if not db_unchanged:
        raise SystemExit("[실패] DB mtime 이 바뀌었다 — score 는 DB 를 열면 안 된다")

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(f"\n통과 ({len(results)}건) — 4지표 · D30 분모 · D50 S4 · 발행=근거 폴백 확인")


if __name__ == "__main__":
    main()
