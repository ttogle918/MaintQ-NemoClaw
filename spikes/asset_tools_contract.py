# -*- coding: utf-8 -*-
"""Stage 4 확장 읽기 도구 5종 계약 검증 (MQ-604·605·606·607·608).

Stage 4 에는 전용 회귀가 없어서 **도구 안의 오배선이 MQ-612 까지 살아남는 구조**였다.
실제로 그런 결함이 하나 잡혔다 — `verify_ownership` 이 `assets.last_overhaul_at` 을
`build_facts()` 산출물에서 읽는 바람에(그 컬럼은 `ASSET_FACT_COLUMNS` 에 없다) **DB 에 값이
있는 자산까지 "기록 없음"으로 서술**했다(B-1). D62 방향으로는 안전하지만 반대편 위반이다 —
**있는 근거를 없다고 말하는 것**도 이 프로젝트가 막으려는 것이다. ⑳㉑㉒ 가 그 회귀다.

검증 대상:
  ⓐ 5도구 × (정상 / 잘못된 입력 / 없는 대상) — **전부 예외 없이 `status` 반환** (D9·D46)
  ⓑ `verify_ownership` 이 `VERIFIED` 를 내지 않는다 (`11 §6` — PARTIAL 은 승격 불가).
     ⑰ 이 **상수 방어선**(`FIXED_UNVERIFIED`)을, ⑱ 이 **동적 방어선**(항상 UNVERIFIED 인 항목)을
     각각 잠근다 — 둘 중 하나만 잠그면 나머지 하나를 지울 때 조용히 통과한다
  ⓒ B-1 회귀 — 오버홀 값이 있는 자산은 `VERIFIED`, 없는 자산만 `UNVERIFIED`
  ⓓ `check_disposal_blockers` 5종 verdict (D79) + `SALE`/`SCRAP` 대조 (D78 부수 확정)
  ⓔ `get_maintenance_metrics` 에 `oee` 키 부재 (D64) · `classify_part_criticality` 의 `reviewed`
  ⓕ `classify_expenditure` 판정 3종 (`12 §3`)

**실 DB 를 읽기만 한다** — 5도구 전부 읽기 전용이고(D10), 실행 전후 mtime·size 불변을
마지막 검사가 직접 확인한다 (`s4_smoke.py` 선례).

**표는 어떤 경우에도 살아남는다.** 도구가 `error` 를 내거나 시드 자산명이 바뀌어도
KeyError 트레이스백으로 죽지 않고 **FAIL 행**으로 기록한다 — 진단 정보가 가장 필요한
순간에 사라지면 회귀의 값어치가 없다.

실행:  uv run python spikes/asset_tools_contract.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mcp_server.tools.verify_ownership as vo_mod  # noqa: E402

# 처분 프로브(`disposal_date`)는 **시드 컬럼이 아니라 도구 파라미터**다 (`seed.py:696`).
# 기대 verdict 를 재현하려면 시드가 정한 개월수를 그대로 써야 하므로 값을 베끼지 않고 import 한다 —
# 여기에 숫자를 하드코딩하면 시드가 바뀔 때 이 회귀가 조용히 어긋난다.
from data.seed import DISPOSAL_PROBE_MONTHS, _shift_months  # noqa: E402
from mcp_server.db import DB_PATH, read_only  # noqa: E402
from mcp_server.tools.check_disposal_blockers import check_disposal_blockers  # noqa: E402
from mcp_server.tools.classify_expenditure import classify_expenditure  # noqa: E402
from mcp_server.tools.classify_part_criticality import classify_part_criticality  # noqa: E402
from mcp_server.tools.get_maintenance_metrics import get_maintenance_metrics  # noqa: E402
from mcp_server.tools.verify_ownership import (  # noqa: E402
    _fact as fact_of,
    _knows as knows,
    verify_ownership,
)

results: list[tuple[str, bool, str]] = []

STATUSES = ("ok", "not_found", "empty", "error")

# 번호는 **자동 부여**한다 — 손으로 인덱스를 박으면 검사를 하나 끼워 넣을 때마다
# 뒤 번호가 전부 밀려 어긋난다(실제로 한 번 어긋났다).
MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛㉜㉝㉞㉟㊱㊲㊳㊴㊵"


def check(name: str, ok: bool, detail: str) -> None:
    mark = MARKS[len(results)] if len(results) < len(MARKS) else f"[{len(results) + 1}]"
    results.append((f"{mark} {name}", ok, detail))


def call(fn, **kwargs) -> dict:
    """도구 호출. **예외가 새어나오면 그 자체가 계약 위반**이라 실패 dict 로 바꿔 기록한다."""
    try:
        out = fn(**kwargs)
    except Exception as exc:  # noqa: BLE001
        return {"status": f"!!예외누출 {type(exc).__name__}: {exc}"}
    if not isinstance(out, dict):
        return {"status": f"!!dict 아님 {type(out).__name__}"}
    return out


def item_of(res: dict, name: str) -> dict:
    """항목 1건. 없으면 **빈 dict** — 호출부가 인덱싱으로 죽지 않게 한다."""
    for cat in res.get("categories") or []:
        for item in (cat or {}).get("items") or []:
            if (item or {}).get("item") == name:
                return item
    return {}


def risk_of(res: dict) -> str:
    return res.get("residual_risk") or ""


# ── 픽스처 ────────────────────────────────────────────────────────────────────
# 5도구 × 3케이스 + 퍼징 대상 추가 키.
# `good` 에 없는 optional 파라미터(`equipment_id`·`window_months`·`disposal_mode`·
# `disposal_date`)는 퍼징에서 통째로 빠져 있었다 — 파싱 경로가 있는 곳일수록 값어치가 크다.
CASES: tuple[tuple[str, object, dict, dict, dict, tuple[str, ...]], ...] = (
    (
        "check_disposal_blockers",
        check_disposal_blockers,
        {"asset_id": "AST-L3-CONV"},
        {"asset_id": "AST-L3-CONV", "disposal_mode": "SELL"},  # enum 밖 — 폴백 금지
        {"asset_id": "AST-NOPE"},
        ("equipment_id", "disposal_mode", "disposal_date"),
    ),
    (
        "verify_ownership",
        verify_ownership,
        {"asset_id": "AST-L3-CONV"},
        {"asset_id": 123},  # 문자열이 아님
        {"asset_id": "AST-NOPE"},
        ("equipment_id",),
    ),
    (
        "classify_part_criticality",
        classify_part_criticality,
        {"part_no": "FAN-IG5-01"},
        {"part_no": ""},
        {"part_no": "NOPE-999"},
        (),
    ),
    (
        "get_maintenance_metrics",
        get_maintenance_metrics,
        {"asset_id": "AST-L3-CONV"},
        {"asset_id": 123},
        {"asset_id": "AST-NOPE"},
        ("equipment_id", "window_months"),  # window_months 는 파싱 경로가 있다
    ),
    (
        "classify_expenditure",
        classify_expenditure,
        {"part_class": "CONSUMABLE", "repair_scope": "RESTORE", "amount": 100_000},
        {"part_class": "CONSUMABLE", "repair_scope": "FIX", "amount": 100_000},  # enum 밖
        {
            "part_class": "CONSUMABLE",
            "repair_scope": "RESTORE",
            "amount": 100_000,
            "asset_id": "AST-NOPE",
        },
        ("asset_id",),
    ),
)

# 어떤 입력에도 예외가 새어나오지 않는지 — 타입이 통째로 어긋난 값들
JUNK = (None, 123, 4.2, True, "", "   ", [], {}, ("a",))

# `FIXED_UNVERIFIED` 실측 핀 (2026-08-09). 줄이려면 **이 숫자도 함께 내려야** 하고,
# 그때 사람이 "왜 미확인 항목을 줄이는가"에 답하게 된다 — 조용한 축소를 막는 게 목적이다.
EXPECTED_FIXED_CATEGORIES = frozenset(
    {
        "물리적 상태",
        "가동 이력",
        "기술적 진부화",
        "권리관계",
        "법정 요건",
        "재무·회계",
        "시장·가격",
        "이전 비용",
    }
)
EXPECTED_FIXED_TOTAL = 26


def main() -> None:
    # 기존 spike 전부가 갖는 보일러플레이트 — 없으면 stdout 이 파이프일 때
    # 콘솔 코드페이지(cp949)로 인코딩돼 '—' 같은 문자에서 UnicodeEncodeError 로 죽는다.
    # 회귀 러너는 출력을 캡처하므로 이게 빠지면 CI 에서만 실패한다.
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    if not DB_PATH.exists():
        raise SystemExit(f"목업 DB 가 없습니다: {DB_PATH} — data/seed.py 를 먼저 실행하세요")
    before = (DB_PATH.stat().st_mtime_ns, DB_PATH.stat().st_size)

    with read_only() as con:
        assets = [r[0] for r in con.execute("SELECT asset_id FROM assets ORDER BY asset_id")]
        acquired = {
            r[0]: r[1]
            for r in con.execute("SELECT asset_id, acquired_at FROM assets")
            if r[1] is not None
        }
        # B-1 기대값의 원천은 시드 하드코딩이 아니라 **DB 실측**이다 —
        # 시드가 바뀌면 기대값도 같이 움직여야 회귀가 거짓 신호를 내지 않는다
        with_overhaul = [
            r[0]
            for r in con.execute(
                "SELECT asset_id FROM assets WHERE last_overhaul_at IS NOT NULL ORDER BY asset_id"
            )
        ]

    # ─ ①~⑮ 5도구 × 3케이스 ─────────────────────────────────────────────────
    for label, fn, good, bad, missing, _extra in CASES:
        for kind, kwargs, expect in (
            ("정상", good, "ok"),
            ("잘못된 입력", bad, "error"),
            ("없는 대상", missing, "not_found"),
        ):
            res = call(fn, **kwargs)
            got = res.get("status")
            detail = f"status={got} reason={res.get('reason', '-')}"
            if got not in STATUSES:
                detail += "  ← status 4종(D9) 밖"
            check(f"{label} — {kind}", got == expect, detail)

    # ─ ⑯ verify_ownership 은 VERIFIED 를 내지 않는다 ────────────────────────
    vo = {a: call(verify_ownership, asset_id=a) for a in assets}
    bad_status = [a for a, r in vo.items() if r.get("status") != "ok"]
    verdicts = {a: r.get("verdict") for a, r in vo.items()}
    check(
        f"verify_ownership — 시드 {len(assets)}자산 전부 PARTIAL 이하",
        not bad_status and all(v in ("PARTIAL", "UNVERIFIED") for v in verdicts.values()),
        f"{sorted({str(v) for v in verdicts.values()})}"
        + (f" · status 비정상 {bad_status}" if bad_status else ""),
    )

    # ─ ⑰ 상수 방어선 — `FIXED_UNVERIFIED` 를 실측치에 핀 고정 ────────────────
    # 이건 **유일한 방어선이 아니다**(⑱ 이 동적 방어선을 따로 잠근다). 다만 이 상수가
    # 조용히 줄면 "확인 못 한 것"이 화면에서 사라지므로 카테고리 집합·항목 총량을 함께 박는다.
    fixed = vo_mod.FIXED_UNVERIFIED
    fixed_total = sum(len(v) for v in fixed.values())
    empty_cats = sorted(c for c, v in fixed.items() if not v)
    check(
        "verify_ownership — FIXED_UNVERIFIED 카테고리 집합·항목 총량 핀 고정",
        set(fixed) == EXPECTED_FIXED_CATEGORIES
        and not empty_cats
        and fixed_total >= EXPECTED_FIXED_TOTAL,
        f"카테고리 {len(fixed)}종(기대 {len(EXPECTED_FIXED_CATEGORIES)}) · "
        f"항목 {fixed_total}개(기대 ≥{EXPECTED_FIXED_TOTAL})"
        + (f" · 빈 카테고리 {empty_cats}" if empty_cats else "")
        + (
            f" · 차집합 {sorted(set(fixed) ^ EXPECTED_FIXED_CATEGORIES)}"
            if set(fixed) != EXPECTED_FIXED_CATEGORIES
            else ""
        ),
    )

    # ─ ⑱ 동적 방어선 — 상수를 통째로 비워도 VERIFIED 에 도달하지 못한다 ──────
    # `_market_items` 가 "동일 기종 거래가"를 **무조건** UNVERIFIED 로 낸다는 사실 자체를 잠근다.
    # 상수(⑰)와 동적(⑱)을 따로 잠가야 한 쪽을 지울 때 다른 쪽이 가려주지 못한다.
    saved = vo_mod.FIXED_UNVERIFIED
    try:
        vo_mod.FIXED_UNVERIFIED = {}
        stripped = {a: call(verify_ownership, asset_id=a) for a in assets}
    finally:
        vo_mod.FIXED_UNVERIFIED = saved
    slipped = [a for a, r in stripped.items() if r.get("verdict") == "VERIFIED"]
    survivors = sorted(
        {
            (i or {}).get("item")
            for r in stripped.values()
            for c in r.get("categories") or []
            for i in (c or {}).get("items") or []
            if (i or {}).get("state") == "UNVERIFIED"
        }
    )
    check(
        "verify_ownership — 상수를 비워도 무조건 UNVERIFIED 인 동적 항목이 남는다",
        not slipped and bool(survivors),
        f"VERIFIED 누출 {slipped} · 잔존 동적 미확인 {survivors[:4]}",
    )

    # ─ ⑲ 9카테고리 · 전 항목 state · UNVERIFIED 는 limit ────────────────────
    broken: list[str] = []
    for a, r in vo.items():
        if r.get("status") != "ok":
            broken.append(f"{a}:status={r.get('status')}")
            continue
        cats = [(c or {}).get("category") for c in r.get("categories") or []]
        if len(cats) != 9 or len(set(cats)) != 9:
            broken.append(f"{a}:카테고리 {len(cats)}종")
        for c in r.get("categories") or []:
            for i in (c or {}).get("items") or []:
                if (i or {}).get("state") not in ("VERIFIED", "UNVERIFIED"):
                    broken.append(f"{a}/{(i or {}).get('item')}:state={(i or {}).get('state')}")
                elif i["state"] == "UNVERIFIED" and not i.get("limit"):
                    broken.append(f"{a}/{i.get('item')}:limit 없음")
        if not r.get("not_considered") or not r.get("disclaimer"):
            broken.append(f"{a}:not_considered/disclaimer 누락")
    check(
        "verify_ownership — 9카테고리·전 항목 state·UNVERIFIED limit",
        not broken,
        f"결함 {len(broken)}건 {broken[:3]}",
    )

    # ─ ⑳㉑㉒ B-1 회귀 — 있는 근거를 없다고 말하지 않는가 ─────────────────────
    hit = {a: item_of(vo.get(a) or {}, "오버홀") for a in assets}
    wrong_present = [a for a in with_overhaul if hit.get(a, {}).get("state") != "VERIFIED"]
    check(
        "B-1 — last_overhaul_at 값이 있는 자산은 오버홀 VERIFIED",
        bool(with_overhaul) and not wrong_present,
        f"대상 {with_overhaul} · 어긋남 {wrong_present}",
    )
    without = [a for a in assets if a not in with_overhaul]
    wrong_absent = [a for a in without if hit.get(a, {}).get("state") != "UNVERIFIED"]
    check(
        "B-1 — 값이 없는 자산만 오버홀 UNVERIFIED(빈 값을 '실시함'으로 읽지 않는다)",
        not wrong_absent,
        f"대상 {len(without)}자산 · 어긋남 {wrong_absent}",
    )
    leaked = [a for a in with_overhaul if "오버홀 실시 여부 미확인" in risk_of(vo.get(a) or {})]
    # `status != ok` 면 residual_risk 가 비어 이 검사가 **공허하게 통과**한다 — 그 상태를 통과로 세지 않는다
    risk_readable = all((vo.get(a) or {}).get("status") == "ok" for a in with_overhaul)
    check(
        "B-1 — 오버홀 기록이 있는 자산의 residual_risk 에 '오버홀 미확인'이 없다",
        risk_readable and not leaked,
        f"잔존 {leaked}" + ("" if risk_readable else " · status 비정상이라 판정 불가"),
    )

    # ─ ㉓ insured 3상태가 그대로 드러나는가 (D78) ────────────────────────────
    missing_assets = [a for a in ("AST-L3-LIFT", "AST-L2-SPDL") if a not in vo]
    lift_res, spdl_res = vo.get("AST-L3-LIFT") or {}, vo.get("AST-L2-SPDL") or {}
    lift, spdl = item_of(lift_res, "부보 여부"), item_of(spdl_res, "부보 여부")
    insured_ok = (
        not missing_assets
        and lift.get("state") == "VERIFIED"
        and spdl.get("state") == "VERIFIED"
        and lift.get("evidence") != spdl.get("evidence")
        and "미부보" in risk_of(lift_res)
        and "미부보" not in risk_of(spdl_res)
    )
    check(
        "verify_ownership — insured=0(확인된 미부보)과 =1 이 다르게 표시",
        insured_ok,
        (f"자산 없음 {missing_assets} · " if missing_assets else "")
        + f"LIFT={str(lift.get('evidence'))[:24]}… / SPDL={str(spdl.get('evidence'))[:24]}…",
    )

    # ─ ㉔~㉙ check_disposal_blockers 5종 verdict (D79) ───────────────────────
    probe_date = {
        a: _shift_months(date.fromisoformat(acquired[a]), m)
        for a, m in DISPOSAL_PROBE_MONTHS.items()
        if a in acquired
    }
    expected = (
        ("AST-L3-CONV", "SALE", "BLOCKED", 2),
        ("AST-L4-WRAP", "SALE", "HOLD", None),
        ("AST-L4-DUST", "SALE", "INSUFFICIENT_FACTS", None),
        ("AST-L2-SPDL", "SALE", "CONDITIONAL", None),
        ("AST-L3-LIFT", "SALE", "CONDITIONAL", None),  # VAT-INVOICE — 매각은 최소 CONDITIONAL
        ("AST-L3-LIFT", "SCRAP", "CLEAR", None),  # CLEAR 는 SCRAP·TRANSFER 에서만 (D78)
    )
    for asset, mode, want, n_blockers in expected:
        probe = probe_date.get(asset)
        if probe is None:
            # 시드에서 자산·취득일이 사라지면 여기서 **FAIL 행**으로 보고한다 (KeyError 금지)
            check(
                f"처분 판정 — {asset}/{mode} → {want}",
                False,
                f"프로브 날짜 없음 — DISPOSAL_PROBE_MONTHS/acquired_at 에 {asset} 이 없다",
            )
            continue
        res = call(check_disposal_blockers, asset_id=asset, disposal_mode=mode, disposal_date=probe)
        got = res.get("verdict")
        ok = got == want
        detail = f"verdict={got}"
        if n_blockers is not None:
            ok = ok and len(res.get("blockers") or []) == n_blockers
            detail += f" blockers={len(res.get('blockers') or [])}(기대 {n_blockers})"
        check(f"처분 판정 — {asset}/{mode} → {want}", ok, detail)

    # ─ ㉚ OEE 는 계산도 출력도 하지 않는다 (D64) ─────────────────────────────
    oee = [a for a in assets if "oee" in call(get_maintenance_metrics, asset_id=a)]
    check("get_maintenance_metrics — 출력에 oee 키 부재 (D64)", not oee, f"검출 {oee}")

    # ─ ㉛ 부품 등급은 조회이지 추론이 아니다 (D12) ───────────────────────────
    part = call(classify_part_criticality, part_no="FAN-IG5-01")
    check(
        "classify_part_criticality — FAN-IG5-01 CRITICAL · reviewed 필드 존재",
        part.get("part_class") == "CRITICAL" and "reviewed" in part,
        f"part_class={part.get('part_class')} reviewed={part.get('reviewed')}",
    )

    # ─ ㉜ 지출 판정 3종 ──────────────────────────────────────────────────────
    exp = (
        ("CRITICAL", "UPGRADE", "CAPITAL"),
        ("CONSUMABLE", "RESTORE", "REVENUE"),
        ("CRITICAL", "RESTORE", "HOLD"),  # 원상 회복인지 내용연수 연장인지가 최대 논쟁 지점
    )
    got_exp = [
        call(classify_expenditure, part_class=pc, repair_scope=rs, amount=100_000).get("verdict")
        for pc, rs, _ in exp
    ]
    check(
        "classify_expenditure — CAPITAL/REVENUE/HOLD 판정",
        got_exp == [w for _, _, w in exp],
        f"{got_exp} (기대 {[w for _, _, w in exp]})",
    )

    # ─ ㉝ 어떤 입력에도 예외가 새어나오지 않는다 ─────────────────────────────
    leaks: list[str] = []
    calls = 0
    for label, fn, good, _bad, _missing, extra in CASES:
        for key in (*good, *extra):
            for junk in JUNK:
                calls += 1
                res = call(fn, **{**good, key: junk})
                if str(res.get("status", "")).startswith("!!"):
                    leaks.append(f"{label}({key}={junk!r}) {res['status']}")
                elif res.get("status") not in STATUSES:
                    leaks.append(f"{label}({key}={junk!r}) status={res.get('status')!r}")
    check(
        "예외 무누출 — 도구 5종 × 타입 오류 입력(optional 파라미터 포함)",
        not leaks,
        f"호출 {calls}회 · 누출 {len(leaks)}건 {leaks[:2]}",
    )

    # ─ ㉞ B-1 을 구조로 닫았는가 — 규약이 주석이 아니라 코드인가 ──────────────
    # 허용 집합은 `ASSET_FACT_COLUMNS ∪ 엔진 파생 키`다. 목록 밖 컬럼은 거부하고,
    # 파생 키(`vat_invoice_issued` 등)는 **허용**해야 한다 — 좁히면 정당한 코드를 거짓 차단한다.
    outside_rejected = True
    try:
        fact_of({}, "last_overhaul_at")
        outside_rejected = False  # 예외가 안 났다 = 규약이 다시 주석으로 돌아갔다
    except KeyError:
        pass
    derived_allowed = True
    try:
        knows({}, "vat_invoice_issued")
    except KeyError:
        derived_allowed = False
    inside_ok = knows({"insured": True}, "insured") and not knows({}, "insured")
    check(
        "verify_ownership — facts 접근자: 목록 밖 거부 · 사실 키/파생 키 허용 (B-1 구조 방어)",
        outside_rejected and derived_allowed and inside_ok,
        f"밖 거부={outside_rejected} · 파생 허용={derived_allowed} · 안 정상={inside_ok}",
    )

    # ─ ㉟ 실 DB 불변 ─────────────────────────────────────────────────────────
    after = (DB_PATH.stat().st_mtime_ns, DB_PATH.stat().st_size)
    check(
        "실 DB 불변 (mtime·size) — 읽기 전용 커넥션만 (D10)",
        before == after,
        f"{DB_PATH.name} size={after[1]}",
    )

    width = max(len(name) for name, _, _ in results)
    print("─" * (width + 52))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 52))

    failed = [name for name, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건:\n  - " + "\n  - ".join(failed))
    print(
        f"\n통과 ({len(results)}건) — D9·D46(status 반환)·D62(모른다≠통과)·"
        "D64(OEE 금지)·D78·D79 준수 · B-1 회귀 포함"
    )


if __name__ == "__main__":
    main()
