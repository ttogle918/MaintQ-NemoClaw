# -*- coding: utf-8 -*-
"""eval/score.py 계약 검증 (MQ-310) — **전부 합성 traces, DB·API 불필요**.

`score_session(events, expected)` 는 traces DB 를 읽지 않고 event 리스트를 인자로 받는다.
그래서 이 스파이크는 event 를 손으로 지어 넣어 4지표(부품 특정·인용·안전·시퀀스)를 검증한다.
event 형태는 `backend.agent.trace.read_trace` 스키마 `{seq, event, tool, data}` 를 따른다.

이 프로젝트는 "검사는 통과하는데 대상은 깨진" 사례가 4건 나왔다. 그래서 **되돌리면 실제로
fail 하는지**(음성 검증)를 citation·safety·sequence·S4 4개 지표에서 스크립트 안에서 확인하고
결과를 주석(★ 음성)으로 남긴다.

⑱⑲ 는 `eval/run_eval.py` 의 **D88 프로파일 가드**(MQ-703)다. 합성 `/health` dict 를 가드
함수에 직접 먹여 `SystemExit.code` 를 본다 — 서버·서브프로세스를 띄우지 않으므로 이 파일의
"DB·API 불필요" 성질이 유지된다(다른 스위트와 포트·DB 를 다투지 않는다).

실행:  uv run python spikes/eval_score_contract.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.agent.loop import format_llm_end  # noqa: E402
from eval.judge import JudgeVerdict  # noqa: E402
from eval.run_eval import (  # noqa: E402
    _EXEC_FAILED_PREFIX,
    ItemResult,
    _flip_lines,
    _free_port,
    _llm_end_lines,
    _run_stage,
    build_meta,
    enforce_profile_guard,
    estimate_cost,
    flip_analysis,
    item_outcomes,
    parse_llm_end,
    profile_violations,
    summarize_llm_end,
)
from eval.score import has_replay, metric_rate, score_session  # noqa: E402

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

    # ── ⑧-b D66 S2 — 부품이 도구 **결과**에만 있어도 특정으로 인정 ────
    #
    # S2 는 에러코드가 없어 related_parts 가 없고 부품명으로 조회한다 — input 에 part_no 가
    # 없다. 실측(2026-08-05 T13)에서 단종 감지→대체품 제시까지 완주하고도 판정이 None 이었다.
    s2_alt = [
        tc("search_inventory", model="S100", part_name="제어보드"),
        tr("search_inventory", "ok", parts=["PCB-S100-CTRL", "PCB-S100-CTRL-R2"]),
        tc("find_alternative_parts", part_no="PCB-S100-CTRL"),
        tr("find_alternative_parts", "ok", parts=["PCB-S100-CTRL-R2"]),
        cite(417),
    ]
    s2_expect = {
        "branch": "s2_alternative",
        "part_no": "PCB-S100-CTRL-R2",
        "safety_required": False,
        "expect_not_found": False,
        "expect_hold": False,
    }
    v_s2 = verdict(score_session(s2_alt, s2_expect), "part")
    check(
        "⑧-b D66 대체품 결과로 부품 특정 인정 (원부품 아닌 대체품)",
        v_s2.passed is True,
        v_s2.detail,
    )

    # 다건 결과는 채택하지 않는다 — 고르지도 않은 부품에 점수를 주면 완화가 아니라 오판이다
    s2_ambiguous = [
        tc("search_inventory", model="iG5A", part_name="냉각팬"),
        tr("search_inventory", "ok", parts=["FAN-IG5-01", "FAN-GEN-40", "FAN-IG5-02"]),
    ]
    v_amb = verdict(
        score_session(s2_ambiguous, {**s2_expect, "part_no": "FAN-IG5-01"}), "part"
    )
    check(
        "⑧-c D66 결과 다건이면 특정 실패 (★ 첫 항목을 정답으로 세지 않음)",
        v_amb.passed is False and "None" in v_amb.detail,
        v_amb.detail,
    )

    # 미확인 호환품은 애초에 parts 에 실리지 않는다 — 실려도 정답으로 세면 안 되는 부품이다
    v_pref = verdict(
        score_session(
            [
                tc("search_inventory", model="iG5A", part_no="FAN-IG5-01"),
                tr("search_inventory", "ok", parts=["FAN-IG5-01"]),
            ],
            {**s2_expect, "part_no": "FAN-IG5-01"},
        ),
        "part",
    )
    check(
        "⑧-d 인자 part_no 가 결과보다 우선 (기존 판정 경로 불변)",
        v_pref.passed is True,
        v_pref.detail,
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

    # ── ⑮ D54 — tool_result.pages 로 strict 판정 (실 루프 형태) ──
    # 실 loop.py 는 tool_result 에 pages 를 항상 싣는다. 근거 안이면 pass, 밖이면 fail.
    with_pages_ok = [
        tc("lookup_error_code", model="iG5A", code="OHt"),
        tr("lookup_error_code", "ok", pages=[202]),
        cite(202),
    ]
    with_pages_bad = [
        tc("lookup_error_code", model="iG5A", code="OHt"),
        tr("lookup_error_code", "ok", pages=[202]),
        cite(999),
    ]
    v_pg_ok = verdict(score_session(with_pages_ok, {"part_no": None}), "citation")
    v_pg_bad = verdict(score_session(with_pages_bad, {"part_no": None}), "citation")
    check(
        "⑮ D54 pages 로 strict — 근거 안 pass / 밖 fail (★ 음성: 202→pass, 999→fail)",
        v_pg_ok.passed is True and v_pg_bad.passed is False,
        f"202:{v_pg_ok.passed} / 999:{v_pg_bad.passed}",
    )

    # ── ⑯ D54 — pages 생산자가 있으면 degraded 로 안 내려간다 ──
    # 같은 "근거 소스 빈 집합"이라도: pages 키가 있으면(생산자 존재) 지어낸 페이지 → fail,
    # 키가 아예 없으면(구 trace·합성 요약본, ⑪) 발행=근거 degraded → pass. 이 경계가 D54 다.
    empty_pages = [
        tc("lookup_error_code", model="iG5A", code="OHt"),
        tr("lookup_error_code", "ok", pages=[]),  # 생산자는 있는데 근거가 없다
        cite(202),
    ]
    v_ep = verdict(score_session(empty_pages, {"part_no": None}), "citation")
    check(
        "⑯ D54 pages=[] (생산자 존재·근거 없음) → fail (★ 음성: 키 없으면 ⑪ degraded pass)",
        v_ep.passed is False and "지어낸" in v_ep.detail,
        v_ep.detail,
    )

    # ── ⑰ D55 — 재생 표식 감지 (has_replay) ────────────────────
    replayed = [
        tc("lookup_error_code", model="iG5A", code="OHt"),
        {
            "event": "tool_result",
            "tool": "lookup_error_code",
            "data": {"tool": "lookup_error_code", "status": "ok", "summary": "x",
                     "elapsed": 0.4, "replay": True},
        },
    ]
    check(
        "⑰ D55 has_replay — replay:true 섞인 세션 감지 (★ 음성: 없으면 False)",
        has_replay(replayed) is True and has_replay(S1_OK) is False,
        f"replay={has_replay(replayed)} / live={has_replay(S1_OK)}",
    )

    # ── ⑱ D88 이중 게이트 — core 아님 → SystemExit(2) ───────────
    #
    # `run_eval.py --dry-run` 을 서브프로세스로 돌려 종료코드를 보는 대신 **가드 함수를 직접**
    # 부른다. 이 스파이크의 불변식이 "DB·API 불필요"라 서버를 띄우면 그 성질이 깨지고, 다른
    # 스위트와 포트·DB 를 다투는 플래키 원인이 된다. 종료코드는 `SystemExit.code` 로 같은 값을
    # 본다 — main() 은 이 예외를 잡지 않으므로 프로세스 종료코드와 동치다.
    #
    # ★ 두 팔을 **따로** 건다. 한쪽만 검사하면 "이중 게이트"라는 이름만 남는다:
    #   (가) env 에코만 full  (나) 에코는 core 인데 실측 tools 가 7 초과  (다) 둘 다
    def _guard_code(health: dict, *, allow: bool = False) -> object:
        try:
            enforce_profile_guard(health, allow_full_profile=allow)
        except SystemExit as e:
            return e.code
        return 0

    echo_only = _guard_code({"status": "ok", "mcp": True, "tools": 7, "tools_profile": "full"})
    tools_only = _guard_code({"status": "ok", "mcp": True, "tools": 14, "tools_profile": "core"})
    both = _guard_code({"status": "ok", "mcp": True, "tools": 14, "tools_profile": "full"})
    unknown = _guard_code({})  # health 조회 실패 → 모르는 상태를 통과로 세지 않는다
    core_ok = _guard_code({"status": "ok", "mcp": True, "tools": 7, "tools_profile": "core"})
    check(
        "⑱ D88 이중 게이트 — 에코만 full·실측만 14·둘 다·health 불명 → 전부 exit 2 "
        "(★ 음성: core/7 → 0)",
        (echo_only, tools_only, both, unknown, core_ok) == (2, 2, 2, 2, 0),
        f"에코만:{echo_only} / 실측만:{tools_only} / 둘다:{both} / 불명:{unknown} / core:{core_ok}",
    )

    # ── ⑲ --allow-full-profile → 우회 (exit 0) ─────────────────
    allowed = _guard_code(
        {"status": "ok", "mcp": True, "tools": 14, "tools_profile": "full"}, allow=True
    )
    reasons = profile_violations({"status": "ok", "mcp": True, "tools": 14, "tools_profile": "full"})
    check(
        "⑲ D88 --allow-full-profile → 우회해 exit 0 (★ 위반 사유 자체는 2건 그대로 보고)",
        allowed == 0 and len(reasons) == 2,
        f"exit={allowed} / 사유 {len(reasons)}건: {reasons}",
    )


    # ── ⑳ MQ-713a ② — meta.llm_model. 없으면 `null`, **지어내지 않는다** ──
    #
    # `llm_provider` 는 미설정 시 'gemini' 로 떨어지는데(D56, get_client 의 실동작),
    # 모델명에는 그런 폴백이 없다. 같은 자리에 기본값을 두면 회차 비교의 근거가 거짓이 된다.
    saved = os.environ.get("MAINTQ_LLM_MODEL")
    try:
        os.environ["MAINTQ_LLM_MODEL"] = "gemini-2.5-flash"
        set_meta = build_meta({"tools_profile": "core", "tools": 7})
        os.environ["MAINTQ_LLM_MODEL"] = "   "  # .env 의 빈 값 = 미설정 (D56 과 같은 근거)
        blank_meta = build_meta({"tools_profile": "core", "tools": 7})
        del os.environ["MAINTQ_LLM_MODEL"]
        unset_meta = build_meta({"tools_profile": "core", "tools": 7})
    finally:
        if saved is None:
            os.environ.pop("MAINTQ_LLM_MODEL", None)
        else:
            os.environ["MAINTQ_LLM_MODEL"] = saved
    check(
        "⑳ D88 확장 — meta.llm_model 은 env 그대로, 없으면 null (★ 음성: 빈 값도 null)",
        set_meta["llm_model"] == "gemini-2.5-flash"
        and blank_meta["llm_model"] is None
        and unset_meta["llm_model"] is None
        and set(set_meta) == {"tools_profile", "tools", "llm_provider", "llm_model"},
        f"설정={set_meta['llm_model']!r} / 빈값={blank_meta['llm_model']!r} / "
        f"미설정={unset_meta['llm_model']!r}",
    )

    # ── ㉑ MQ-713a ③ — 잘림 계측의 **생산자↔소비자**를 한 검사로 묶는다 ──
    #
    # 형식 문자열은 `backend/agent/loop.py:format_llm_end` 가 만들고 `run_eval.parse_llm_end`
    # 가 읽는다. 두 곳이 조용히 갈리면 4차 평가에서 "잘림 0건"이 **파싱 실패의 0건**이 된다.
    # 그래서 파서에 지어낸 샘플을 먹이지 않고 **생산자가 만든 실제 줄**을 먹인다.
    stderr_sample = "\n".join(
        [
            "INFO:     Started server process",
            format_llm_end("EVAL-T01", 1, "STOP"),
            "WARNING  traces seq 충돌 ...",
            format_llm_end("EVAL-T08", 2, "FinishReason.MAX_TOKENS"),
            format_llm_end("EVAL-T08", 3, "max_tokens"),
            format_llm_end("EVAL-T13", 1, "stream_error"),
        ]
    )
    parsed = parse_llm_end(stderr_sample)
    summary = summarize_llm_end(parsed)
    check(
        "㉑ [LLM_END] 생산자(loop) → 소비자(run_eval) 라운드트립 · 잡음 줄 무시",
        len(parsed) == 4
        and summary["llm_calls"] == 4
        and summary["truncated_calls"] == 2
        and summary["truncated_by_session"] == {"EVAL-T08": 2}
        and summary["mismatched"] == 0,
        f"파싱 {len(parsed)}줄 · 잘림 {summary['truncated_calls']} · {summary['reasons']}",
    )

    # ★ 음성 — 정상 종료만 있는 stderr 는 잘림 0건이어야 한다. 무엇을 넣어도 잘림으로
    #   세는 계측이면 4차 결과의 "N건"이 아무 의미가 없다.
    clean = summarize_llm_end(
        parse_llm_end("\n".join([format_llm_end("EVAL-T01", i, "STOP") for i in (1, 2)]))
    )
    check(
        "㉑-b ★ 음성: 정상 종료만 → 잘림 0건 (measured=True 는 유지)",
        clean["truncated_calls"] == 0
        and clean["measured"] is True
        and clean["truncated_by_session"] == {},
        f"measured={clean['measured']} / 잘림={clean['truncated_calls']}",
    )

    # ── ㉒ "0건"과 "계측 실패"를 결과 MD 가 다른 문장으로 쓰는가 ──
    #
    # 3차 분석의 결론이 "개선과 요동을 구분할 수 없다"였다. 마커가 하나도 없는데 0건이라고
    # 적으면 "잘림은 원인이 아니다"가 근거 없이 서게 된다 — 같은 종류의 실패다.
    none_lines = " ".join(_llm_end_lines(summarize_llm_end([])))
    zero_lines = " ".join(_llm_end_lines(clean))
    check(
        "㉒ 미계측(마커 0건)과 잘림 0건을 다른 문장으로 보고",
        "계측 실패" in none_lines
        and "0건이라는 뜻이 아니다" in none_lines
        and "계측 실패" not in zero_lines
        and "**0건**" in zero_lines,
        f"미계측={none_lines[:52]}… / 0건={zero_lines[:52]}…",
    )

    # ── ㉓~㉗ MQ-713b — 회차 간 흔들림(flip) 계측 ──
    #
    # 후보 3 이 존재하는 이유는 `eval_gap_3rd.md §4` 다: 같은 코드에서 2·3차 판정이 뒤집힌
    # 문항이 7개였다. 그 위에서 프롬프트를 고치고 단일 실행으로 4차를 돌리면 증감이
    # 수정 효과인지 요동인지 구분되지 않는다. 여기서는 **합성 ItemResult** 로 그 집계가
    # 실제로 뒤집힘을 잡는지, 그리고 **재지 않은 것을 안정으로 읽지 않는지**를 본다.
    exp = {
        "branch": "s1_pipeline",
        "part_no": "FAN-IG5-01",
        "safety_required": False,
        "expect_not_found": False,
        "expect_hold": False,
    }

    def _fake(item_id: str, *, part: bool, failed: bool = False, judged: bool | None = None):
        """`score_session` 이 만든 진짜 Verdict 를 part 만 갈아끼운다 (Verdict 는 frozen)."""
        verdicts = [
            replace(v, passed=part, applicable=True) if v.metric == "part" else v
            for v in score_session([], exp)
        ]
        return ItemResult(
            item_id=item_id,
            branch="s1_pipeline",
            expected=exp,
            events=[],
            response_text=(_EXEC_FAILED_PREFIX + "boom") if failed else "ok",
            verdicts=verdicts,
            judge=(
                None
                if judged is None
                else JudgeVerdict(hallucinated=judged, rationale="-", raw="-")
            ),
            elapsed_s=1.0,
            session_id=f"EVAL-{item_id}",
        )

    # T01 = 3회 전부 통과 / T02 = 2/3 (뒤집힘) / T03 = 3회 전부 실패
    rounds3 = [
        [_fake("T01", part=True), _fake("T02", part=True), _fake("T03", part=False)],
        [_fake("T01", part=True), _fake("T02", part=False), _fake("T03", part=False)],
        [_fake("T01", part=True), _fake("T02", part=True), _fake("T03", part=False)],
    ]
    f3 = flip_analysis(rounds3)
    check(
        "㉓ 3회차 — 뒤집힌 문항만 flipped, 나머지는 안정 통과/안정 실패",
        f3["measurable"] is True
        and f3["by_metric"]["part"] == {
            "stable_pass": 1,
            "stable_fail": 1,
            "flipped": 1,
            "undetermined": 0,
        }
        and f3["flipped_items"] == ["T02"]
        and f3["items"]["T02"]["part"] == {"passed": 2, "measured": 3, "state": "flipped"},
        f"flipped={f3['flipped_items']} · part={f3['by_metric']['part']}",
    )

    # ★ 음성 — 3회 모두 같은 판정이면 흔들림이 0이어야 한다. 무엇을 넣어도 flipped 로
    #   세는 집계면 4차의 "흔들림 N건"이 아무 의미가 없다.
    stable = flip_analysis([[_fake("T01", part=True)] for _ in range(3)])
    check(
        "㉓-b ★ 음성: 3회 동일 판정 → 흔들림 0칸",
        stable["n_flipped_cells"] == 0 and stable["by_metric"]["part"]["stable_pass"] == 1,
        f"flipped={stable['n_flipped_cells']} · part={stable['by_metric']['part']}",
    )

    # ⛔ 1회차에서 "흔들림 0건"이라고 쓰면 3차 분석이 지적한 그 실패를 리포트가 되풀이한다.
    f1 = flip_analysis([rounds3[0]])
    one_round_md = " ".join(_flip_lines(f1))
    check(
        "㉔ 1회차 — measurable=False 이고 MD 가 '측정 불가'라고 쓴다(0건이 아니다)",
        f1["measurable"] is False
        and f1["n_flipped_cells"] == 0
        and "측정 불가" in one_round_md
        and "흔들림이 없다는 뜻이 아니다" in one_round_md,
        f"measurable={f1['measurable']} / md={one_round_md[:60]}…",
    )

    # 실행 실패 회차를 fail 로 접으면 흔들림이 부풀려진다 — 분모에서 빠져야 한다(aggregate 와 동일 기준).
    mixed = flip_analysis(
        [
            [_fake("T05", part=True)],
            [_fake("T05", part=True)],
            [_fake("T05", part=False, failed=True)],
        ]
    )
    check(
        "㉕ 실행 실패 회차는 분모 제외 — 통과 2/측정 2 로 '안정 통과'(흔들림 아님)",
        mixed["items"]["T05"]["part"] == {"passed": 2, "measured": 2, "state": "stable_pass"}
        and mixed["n_flipped_cells"] == 0,
        f"T05={mixed['items']['T05']['part']}",
    )

    # 측정 1회뿐인 칸은 안정도 흔들림도 아니다 — `undetermined` 로 따로 센다.
    thin = flip_analysis([[_fake("T06", part=True)], [_fake("T06", part=True, failed=True)]])
    check(
        "㉖ 측정 회차 <2 인 칸은 undetermined (안정으로 읽지 않는다)",
        thin["items"]["T06"]["part"]["state"] == "undetermined"
        and thin["by_metric"]["part"]["undetermined"] == 1
        and thin["by_metric"]["part"]["stable_pass"] == 0,
        f"T06={thin['items']['T06']['part']}",
    )

    # judge 방향 정규화 — hallucinated=True 가 '나쁨'이라 통과 축을 뒤집어 담는다.
    # 뒤집지 않으면 같은 표에서 환각만 의미가 반대로 읽힌다.
    hallu = flip_analysis(
        [
            [_fake("T07", part=True, judged=False)],
            [_fake("T07", part=True, judged=False)],
            [_fake("T07", part=True, judged=True)],
        ]
    )
    outcomes_clean = item_outcomes(_fake("T07", part=True, judged=False))
    outcomes_bad = item_outcomes(_fake("T07", part=True, judged=True))
    check(
        "㉗ hallucination 은 통과 축으로 정규화(hallucinated=True → passed=False)",
        outcomes_clean["hallucination"] is True
        and outcomes_bad["hallucination"] is False
        and hallu["items"]["T07"]["hallucination"]
        == {"passed": 2, "measured": 3, "state": "flipped"},
        f"clean={outcomes_clean['hallucination']} / bad={outcomes_bad['hallucination']} / "
        f"T07={hallu['items']['T07']['hallucination']}",
    )

    # ── ㉙ 403 점검 실패가 이미 끝난 문항 결과를 날리지 않는가 ──
    #
    # 2026-08-11 실측 사고: 20문항을 다 돌린 뒤 `GET /api/po` 가 httpx.ReadTimeout 을 냈고,
    # 그 예외가 `main` 까지 올라가 **리포트가 하나도 생성되지 않았다**(traces 덤프만 살아남음).
    # 여기서는 **아무도 듣지 않는 포트**로 `_run_stage` 를 불러 같은 상황을 만든다 —
    # 연결 거부는 즉시 나므로 네트워크 대기가 없다(items=[] 라 LLM 호출도 0회).
    dead_url = f"http://127.0.0.1:{_free_port()}"
    stage_results, stage_perm = asyncio.run(_run_stage(dead_url, []))
    check(
        "㉙ 403 점검이 죽어도 실행은 계속 — 결과를 반환하고 사유를 싣는다 (N문항 폐기 금지)",
        stage_results == []
        and stage_perm[0] is False
        and "점검 실패" in stage_perm[1]
        # ⛔ "N/A"(점검할 pending 건 없음)로 접으면 못 잰 것과 잴 게 없던 것이 뭉개진다
        and stage_perm[1] != "N/A",
        f"perm={stage_perm}",
    )

    # 비용 문구가 회차를 곱하지 않으면 사람이 1회분에 동의하고 N회분을 쓰게 된다.
    one = estimate_cost([{"id": "T01"}] * 20, 1)
    three = estimate_cost([{"id": "T01"}] * 20, 3)
    check(
        "㉘ --repeat 비용 추정이 회차를 곱한다 (200 → 600회)",
        "200회" in one and "600회" in three and "3회차" in three,
        f"1회차={one[:60]}… / 3회차={three[:64]}…",
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
    print(
        f"\n통과 ({len(results)}건) — 4지표 · D30 분모 · D50 S4 · 발행=근거 폴백 · "
        "D88 프로파일 가드 확인"
    )


if __name__ == "__main__":
    main()
