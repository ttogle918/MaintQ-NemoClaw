# -*- coding: utf-8 -*-
"""`eval/run_eval.py` 의 `aggregate()` 분모 제외 배선 회귀 (MQ-504) — **전부 합성 `ItemResult`,
API·서버·DB 호출 없음**.

무엇을 확인하는가:

  A. 정상 세션 — `aggregate([A])` 의 지표가 A 의 판정 그대로 반영된다.
  B. 재생 오염 세션(D55, `replay:true`) — 일부러 fail 조합으로 구성해서 `aggregate([A, B])`
     가 B 를 분모에서 제외하면 `aggregate([A])` 와 지표가 **완전히 동일**해야 한다(포함됐다면
     B 의 fail 이 rate 를 끌어내려 달라졌을 것 — 이 동치 비교 자체가 검출 장치다).
     `excluded_replay` 가 정확히 1(A 는 0, B 만 1)인지도 확인한다.
  C. 빈 리스트 — `aggregate([])` 가 예외 없이 안전하게(0분모 → rate=None) 반환하는지 확인.
  D. 실행 실패 문항(Stage 2 신규, `_EXEC_FAILED_PREFIX`) — `aggregate([A, D])` 도 B 와 같은
     논리로 `aggregate([A])` 와 지표가 동일해야 하고 `excluded_failed` 가 정확히 1이어야 한다.
     D 의 `sequence` 판정은 이벤트가 비어 `create_po_draft` 미호출로 **공허하게 PASS** 가
     나오는데(Stage 2 reviewer 가 잡은 결함), 그게 분모에 안 들어가는지가 핵심 회귀 지점이다.
  E. `has_replay()` 위치 무관성 — 표식이 이벤트 리스트의 첫 위치든 마지막이든 세션 전체가
     걸리는지 확인(부분 오염도 전체 배제, D55).

관련 결정: D55(재생 표식 분모 제외) · D21 · D30.
Stage 2 인계: `excluded_failed` 필드가 `aggregate()` 반환에 새로 추가됐다 — 아래 D 픽스처가
그 필드를 직접 검증한다.

실행:  uv run python spikes/eval_replay_guard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval import score  # noqa: E402 — sys.path 설정 후여야 한다
from eval.run_eval import (  # noqa: E402
    _EXEC_FAILED_PREFIX,
    ItemResult,
    aggregate,
    item_outcomes,
    mark_stream_failures,
    stream_failed_sessions,
)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


# ────────────────────────────────────────────── event 팩토리 (eval_score_contract.py 관례)


def tc(tool: str, **inp) -> dict:
    return {"event": "tool_call", "tool": tool, "data": {"tool": tool, "input": inp, "ts": "Z"}}


def tr(tool: str, status: str, **extra) -> dict:
    data = {"tool": tool, "status": status, "summary": f"{tool} {status}", "elapsed": 0.2}
    data.update(extra)
    return {"event": "tool_result", "tool": tool, "data": data}


def tr_replay(tool: str) -> dict:
    """D55 재생 표식이 실린 tool_result — 실 서버가 채운 적 없는 합성 payload."""
    data = {
        "tool": tool,
        "status": "ok",
        "summary": f"{tool} ok",
        "elapsed": 0.1,
        "replay": True,
    }
    return {"event": "tool_result", "tool": tool, "data": data}


def cite(page: int) -> dict:
    inner = {"page": page, "print_page": page, "label": f"iG5A 매뉴얼 p.{page}"}
    return {"event": "block", "tool": None, "data": {"type": "citation", "data": inner}}


# ────────────────────────────────────────────── 픽스처 A — 정상 세션 (전 지표 pass 조합)

EXPECT_A = {"part_no": "FAN-IG5-01", "safety_required": False}
EVENTS_A = [
    tc("lookup_error_code", model="iG5A", code="OHt"),
    tr("lookup_error_code", "ok", manual_page=202),
    tc("search_inventory", part_no="FAN-IG5-01", model="iG5A"),
    tr("search_inventory", "ok"),
    tc("create_po_draft", part_no="FAN-IG5-01", qty=2, supplier_id="SUP-A", reason="x"),
    tr("create_po_draft", "ok"),
    cite(202),
]  # tool_result 3건 — 명세의 "3~4개" 충족


def make_item_a() -> ItemResult:
    return ItemResult(
        item_id="A1",
        branch="s1_pipeline",
        expected=EXPECT_A,
        events=EVENTS_A,
        response_text="정상 응답입니다.",
        verdicts=score.score_session(EVENTS_A, EXPECT_A),
        judge=None,
        elapsed_s=1.2,
    )


# ────────────────────────────────────────────── 픽스처 B — 재생 오염 세션 (일부러 fail 조합)

EXPECT_B = {"part_no": "FAN-IG5-01", "safety_required": False}


def make_item_b(*, replay_at: str) -> ItemResult:
    """`replay_at` = "first" | "last" — 재생 표식 위치를 바꿔가며 검증한다(부분 오염도 전체 배제)."""
    fail_events = [
        tc("create_po_draft", part_no="WRONG-PART", qty=1, supplier_id="SUP-X", reason="y"),
        tr("create_po_draft", "ok"),
    ]
    marker = tr_replay("lookup_error_code")
    events = [marker, *fail_events] if replay_at == "first" else [*fail_events, marker]
    return ItemResult(
        item_id=f"B-{replay_at}",
        branch="s1_pipeline",
        expected=EXPECT_B,
        events=events,
        response_text="재생 오염 세션 — 분모에서 제외돼야 한다.",
        verdicts=score.score_session(events, EXPECT_B),
        judge=None,
        elapsed_s=0.5,
    )


# ────────────────────────────────────────────── 픽스처 D — 실행 실패 문항 (Stage 2 신규)

EXPECT_D = {"part_no": None, "expect_hold": True}  # S3 형 — sequence 지표가 적용되게(applicable)


def make_item_d() -> ItemResult:
    empty_events: list[dict] = []
    return ItemResult(
        item_id="D1",
        branch="s3_root_cause",
        expected=EXPECT_D,
        events=empty_events,
        response_text=f"{_EXEC_FAILED_PREFIX}RuntimeError: 서버 타임아웃",
        # 실행 실패 문항의 실제 배선(run_eval._run_all)과 동일하게 score_session([], expected)
        # 로 생성 — sequence 는 create_po_draft 미호출 근거로 공허하게 PASS 가 나온다.
        verdicts=score.score_session(empty_events, EXPECT_D),
        judge=None,
        elapsed_s=180.0,
    )


# ─────────────────────── 픽스처 E — LLM 스트림 실패 문항 (2026-09-05 신설)
#
# 🔴 **이 축이 없어서 2026-09-05 실행이 통째로 오독됐다.** NVIDIA 가 모델을 EOL
#    시키고 폴백 OpenAI 는 크레딧이 소진돼 20문항 전부 빈 응답이 됐는데, 예외가
#    러너까지 올라온 2건만 "실행 실패"로 빠지고 **나머지 18건은 실질 오답으로 채점**돼
#    리포트가 `part 53.3% → 0.0% (-53.3pt)` 라는 가짜 회귀를 인쇄했다.
#
# 실행 실패(픽스처 D)와 **다른 점이 핵심이다**: 스트림 실패는 HTTP 200 에 빈 본문으로
# 오므로 `response_text` 에 `_EXEC_FAILED_PREFIX` 가 없다. 러너는 "응답을 받은" 것과
# 구분하지 못하고, 서버가 남긴 `[LLM_END] reason=` 만이 그 구분을 갖고 있다.

EXPECT_E = {"part_no": None, "expect_hold": True}  # D 와 같은 S3 형


def make_item_e() -> ItemResult:
    empty_events: list[dict] = []
    return ItemResult(
        item_id="E1",
        branch="s3_root_cause",
        expected=EXPECT_E,
        events=empty_events,
        # ⚠ 실행 실패와 달리 **접두어가 없다** — 응답을 0바이트로 받았을 뿐이다.
        response_text="",
        verdicts=score.score_session(empty_events, EXPECT_E),
        judge=None,
        elapsed_s=2.4,
        session_id="EVAL-E1",
    )


def _end(session: str, call: int, reason: str) -> dict:
    """`parse_llm_end()` 가 돌려주는 레코드 모양."""
    return {"session_id": session, "call": call, "reason": reason,
            "truncated": False, "mismatch": False}


def run() -> None:
    item_a = make_item_a()

    # ── 사전 확인: A 자체가 설계대로 pass 조합인가 ──────────────
    applicable_a = [v for v in item_a.verdicts if v.applicable]
    check(
        "사전 A — 적용 가능한 지표 전부 pass (설계 의도 확인)",
        all(v.passed for v in applicable_a) and len(applicable_a) >= 1,
        "; ".join(f"{v.metric}:{'P' if v.passed else 'F'}/{v.applicable}" for v in item_a.verdicts),
    )

    agg_a_only = aggregate([item_a])

    # ── ① 픽스처 B(first) — aggregate([A,B]) 가 aggregate([A]) 와 지표 완전 동일 ──
    item_b_first = make_item_b(replay_at="first")
    applicable_b = [v for v in item_b_first.verdicts if v.applicable]
    check(
        "사전 B — 일부러 fail 조합인가 (분모에 잘못 섞이면 rate 가 떨어져야 함)",
        any(not v.passed for v in applicable_b),
        "; ".join(f"{v.metric}:{'P' if v.passed else 'F'}/{v.applicable}" for v in item_b_first.verdicts),
    )
    agg_ab_first = aggregate([item_a, item_b_first])
    check(
        "① aggregate([A,B(first)]) 의 metrics == aggregate([A]) (B 완전 배제)",
        agg_ab_first["metrics"] == agg_a_only["metrics"],
        f"AB={agg_ab_first['metrics']} / A={agg_a_only['metrics']}",
    )
    check(
        "① excluded_replay == 1 (B 하나만 재생 오염)",
        agg_ab_first["excluded_replay"] == 1 and agg_a_only["excluded_replay"] == 0,
        f"AB.excluded_replay={agg_ab_first['excluded_replay']} / A.excluded_replay={agg_a_only['excluded_replay']}",
    )
    check(
        "① n_kept == 1 (A 만 kept, B 제외)",
        agg_ab_first["n_kept"] == 1 and agg_ab_first["n_items"] == 2,
        f"n_kept={agg_ab_first['n_kept']}, n_items={agg_ab_first['n_items']}",
    )

    # ── ② 표식 위치 무관 — 재생 표식이 리스트 마지막이어도 동일하게 배제 ──
    item_b_last = make_item_b(replay_at="last")
    check(
        "② has_replay — 표식이 리스트 마지막이어도 True",
        score.has_replay(item_b_last.events) is True,
        f"events[0]={item_b_last.events[0].get('data', {}).get('replay')!r}, "
        f"events[-1]={item_b_last.events[-1].get('data', {}).get('replay')!r}",
    )
    agg_ab_last = aggregate([item_a, item_b_last])
    check(
        "② aggregate([A,B(last)]) 도 aggregate([A]) 와 지표 동일 (위치 무관)",
        agg_ab_last["metrics"] == agg_a_only["metrics"] and agg_ab_last["excluded_replay"] == 1,
        f"metrics 동일={agg_ab_last['metrics'] == agg_a_only['metrics']}, "
        f"excluded_replay={agg_ab_last['excluded_replay']}",
    )

    # ── ③ 픽스처 C — aggregate([]) 안전 반환 (0분모 방어) ──────
    try:
        agg_empty = aggregate([])
        raised = False
    except ZeroDivisionError:
        agg_empty = {}
        raised = True
    check(
        "③ aggregate([]) 이 ZeroDivisionError 없이 반환",
        raised is False,
        "예외 발생" if raised else "정상 반환",
    )
    all_total_zero = all(m["total"] == 0 and m["rate"] is None for m in agg_empty.get("metrics", {}).values())
    check(
        "③ aggregate([]) 의 모든 지표 total==0, rate=None",
        all_total_zero,
        str(agg_empty.get("metrics")),
    )
    check(
        "③ aggregate([]) 의 n_items/n_kept/excluded_* 전부 0, failed_items 빈 리스트",
        agg_empty.get("n_items") == 0
        and agg_empty.get("n_kept") == 0
        and agg_empty.get("excluded_replay") == 0
        and agg_empty.get("excluded_failed") == 0
        and agg_empty.get("failed_items") == [],
        str(agg_empty),
    )

    # ── ④ 픽스처 D — 실행 실패 문항이 분모에서 제외 (excluded_failed, Stage 2 회귀) ──
    item_d = make_item_d()
    seq_verdict_d = next(v for v in item_d.verdicts if v.metric == "sequence")
    check(
        "사전 D — sequence 가 공허하게 PASS (create_po_draft 미호출, applicable=True)",
        seq_verdict_d.passed is True and seq_verdict_d.applicable is True,
        f"passed={seq_verdict_d.passed}, applicable={seq_verdict_d.applicable}, detail={seq_verdict_d.detail}",
    )
    agg_ad = aggregate([item_a, item_d])
    check(
        "④ aggregate([A,D]) 의 metrics == aggregate([A]) (D 완전 배제, Stage 2 회귀)",
        agg_ad["metrics"] == agg_a_only["metrics"],
        f"AD={agg_ad['metrics']} / A={agg_a_only['metrics']}",
    )
    check(
        "④ excluded_failed == 1 (D 하나만 실행 실패, excluded_replay 는 0)",
        agg_ad["excluded_failed"] == 1 and agg_ad["excluded_replay"] == 0,
        f"excluded_failed={agg_ad['excluded_failed']}, excluded_replay={agg_ad['excluded_replay']}",
    )
    check(
        "④ D 의 공허한 sequence PASS 가 sequence 분모에 안 들어감",
        agg_ad["metrics"]["sequence"]["total"] == agg_a_only["metrics"]["sequence"]["total"],
        f"AD.sequence.total={agg_ad['metrics']['sequence']['total']}, "
        f"A.sequence.total={agg_a_only['metrics']['sequence']['total']}",
    )
    check(
        "④ failed_items 에 D1 이 기록됨(집계에서는 빠지되 실패 사실은 노출)",
        agg_ad["failed_items"] == ["D1"],
        str(agg_ad["failed_items"]),
    )

    # ── ⑤ B 와 D 를 함께 넣어도 A 만 반영 (복합 배제) ──────────
    agg_all = aggregate([item_a, item_b_first, item_d])
    check(
        "⑤ aggregate([A,B,D]) 도 aggregate([A]) 와 지표 동일 + excluded_replay=1 · excluded_failed=1",
        agg_all["metrics"] == agg_a_only["metrics"]
        and agg_all["excluded_replay"] == 1
        and agg_all["excluded_failed"] == 1
        and agg_all["n_kept"] == 1,
        f"metrics 동일={agg_all['metrics'] == agg_a_only['metrics']}, "
        f"excluded_replay={agg_all['excluded_replay']}, excluded_failed={agg_all['excluded_failed']}, "
        f"n_kept={agg_all['n_kept']}",
    )
    # ── ⑥ LLM 스트림 실패 축 (2026-09-05) ───────────────────────────────────
    #
    # ⑥-a 가 이 축의 **정의**다. `all` 을 `any` 로 느슨하게 바꾸면 부분 실패 세션까지
    # 분모에서 빠져 **지표가 부풀려진다** — 제외는 정직해지는 방향으로만 써야 한다.
    partial = [_end("EVAL-P1", 1, "TOOL_CALLS"), _end("EVAL-P1", 2, "STREAM_ERROR")]
    total = [_end("EVAL-E1", 1, "STREAM_ERROR"), _end("EVAL-E1", 2, "STREAM_ERROR")]
    verdict = stream_failed_sessions([*partial, *total])
    check(
        "⑥-a 전 호출 실패만 잡는다 (all 규칙 — 부분 실패는 제외 대상 아님)",
        verdict == {"EVAL-E1"},
        f"판정={sorted(verdict)} (기대 ['EVAL-E1'] · P1 은 1회 정상 종료라 제외 아님)",
    )
    check(
        "⑥-b 레코드 0건이면 빈 집합 (계측 불능을 '전부 실패'로 오인하지 않는다)",
        stream_failed_sessions([]) == set(),
        f"판정={stream_failed_sessions([])}",
    )

    item_e = make_item_e()
    n_marked = mark_stream_failures([item_e], total)
    agg_ae = aggregate([item_a, item_e])
    check(
        "⑥-c mark_stream_failures 로 찍힌 문항은 전 지표 분모에서 빠진다",
        n_marked == 1 and item_e.llm_stream_failed
        and agg_ae["metrics"] == agg_a_only["metrics"],
        f"찍힘={n_marked} · 플래그={item_e.llm_stream_failed} · "
        f"metrics 동일={agg_ae['metrics'] == agg_a_only['metrics']}",
    )
    check(
        "⑥-d excluded_stream 으로 따로 세고 stream_failed_items 로 노출한다 (감추지 않는다)",
        agg_ae["excluded_stream"] == 1
        and agg_ae["excluded_failed"] == 0
        and agg_ae["stream_failed_items"] == ["E1"]
        and agg_ae["n_kept"] == 1,
        f"excluded_stream={agg_ae['excluded_stream']} · "
        f"excluded_failed={agg_ae['excluded_failed']} · "
        f"items={agg_ae['stream_failed_items']} · n_kept={agg_ae['n_kept']}",
    )
    # `item_outcomes()` 는 흔들림(flip) 집계의 분모다. 여기가 aggregate() 와 갈리면
    # 같은 문항이 지표에서는 빠지고 흔들림에서는 '실패'로 세어져 수치가 어긋난다 —
    # 그 함수의 docstring 이 "aggregate() 와 같은 근거로 맞춘다"고 약속하고 있다.
    outs = item_outcomes(item_e)
    check(
        "⑥-e item_outcomes 도 같은 규칙 — 전 지표 None (흔들림이 부풀지 않게)",
        all(v is None for v in outs.values()),
        f"outcomes={outs}",
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("eval/run_eval.py aggregate() 분모 제외 배선 회귀 (합성 ItemResult — API·서버·DB 불필요)\n")

    run()

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 44))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 44))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(f"\n통과 ({len(results)}건) — replay/실행실패/LLM 스트림 실패 분모 제외 · 0분모 방어 · 표식 위치 무관 확인")


if __name__ == "__main__":
    main()
