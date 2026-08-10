# -*- coding: utf-8 -*-
"""확장 읽기 도구 **7종** 계약 검증 (MQ-604~610, MQ-612 확장).

Stage 4 에는 전용 회귀가 없어서 **도구 안의 오배선이 MQ-612 까지 살아남는 구조**였다.
실제로 그런 결함이 하나 잡혔다 — `verify_ownership` 이 `assets.last_overhaul_at` 을
`build_facts()` 산출물에서 읽는 바람에(그 컬럼은 `ASSET_FACT_COLUMNS` 에 없다) **DB 에 값이
있는 자산까지 "기록 없음"으로 서술**했다(B-1). D62 방향으로는 안전하지만 반대편 위반이다 —
**있는 근거를 없다고 말하는 것**도 이 프로젝트가 막으려는 것이다. "B-1 —" 로 시작하는 3건이
그 회귀다(번호는 검사를 끼워 넣을 때마다 자동 재부여되므로 **이름으로** 가리킨다).

MQ-612 확장분 (Stage 5 reviewer 지정 3건):
  1. `assess_repair_value`·`build_evidence_bundle` 을 더해 **7종**을 덮는다 — 5종짜리로 두면
     MQ-612 의 DoD("7종 × 3케이스")가 **거짓 통과**한다
  2. **MCP verdict ↔ REST verdict 직접 대조** — 지금까지는 각자 파일 정본과 **간접** 대조만 했다.
     두 소비자가 같은 프로브에서 갈리면 여기서 잡힌다
  3. **⑳(REST ↔ 파일 대조) 방어선 생존 확인** — DB 룰 1행을 일부러 어긋나게 한 픽스처로
     그 대조가 **실제로 FAIL 하는지**. reviewer 평: *"지금 ⑳ 은 '항상 통과하는 검사'일
     가능성이 검증되지 않았다"* (Stage 4 W-a 의 공허한 PASS 와 같은 유형)

검증 대상:
  ⓐ 7도구 × (정상 / 잘못된 입력 / 없는 대상) — **전부 예외 없이 `status` 반환** (D9·D46)
  ⓑ `verify_ownership` 이 `VERIFIED` 를 내지 않는다 (`11 §6` — PARTIAL 은 승격 불가).
     **상수 방어선**(`FIXED_UNVERIFIED`)과 **동적 방어선**(항상 UNVERIFIED 인 항목)을
     각각 잠근다 — 둘 중 하나만 잠그면 나머지 하나를 지울 때 조용히 통과한다
  ⓒ B-1 회귀 — 오버홀 값이 있는 자산은 `VERIFIED`, 없는 자산만 `UNVERIFIED`
  ⓓ `check_disposal_blockers` 5종 verdict (D79) + `SALE`/`SCRAP` 대조 (D78 부수 확정)
  ⓔ `get_maintenance_metrics` 에 `oee` 키 부재 (D64) · `classify_part_criticality` 의 `reviewed`
  ⓕ `classify_expenditure` 판정 3종 (`12 §3`)
  ⓖ `assess_repair_value` 의 `estimates[]`(D65) · `ROOT_CAUSE_FIRST` 는 3지 선택지를 내지 않는다
  ⓗ `build_evidence_bundle` — 정상 케이스 기대값을 **`data/rules/laws/*.json` 의 수집 상태와
     그 자산이 실제로 인용한 조문**에서 파생시킨다(하드코딩 0건). 해시 안정성은 인용 조문이
     전부 채워진 **임시 DB 사본**에서 본다. 같은 사실 → 같은 해시.
     MQ-705 이후 번들은 **5키**(D83)이며, 무결성 축(`rule_hash`·주입·N1·N2·뮤턴트 생존)은
     `spikes/bundle_integrity.py` 가 전담한다 — 여기서는 계약의 겉면만 확인한다

**실 DB 를 읽기만 한다** — 7도구 전부 읽기 전용이고(D10), 실행 전후 mtime·size 불변을
마지막 검사가 직접 확인한다 (`s4_smoke.py` 선례). 픽스처는 전부 **임시 폴더의 사본**에
만들고 원본 경로는 즉시 되돌린다.

**표는 어떤 경우에도 살아남는다.** 도구가 `error` 를 내거나 시드 자산명이 바뀌어도
KeyError 트레이스백으로 죽지 않고 **FAIL 행**으로 기록한다 — 진단 정보가 가장 필요한
순간에 사라지면 회귀의 값어치가 없다.

실행:  uv run python spikes/asset_tools_contract.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mcp_server.db as mcp_db  # noqa: E402
import mcp_server.tools.verify_ownership as vo_mod  # noqa: E402

# 처분 프로브(`disposal_date`)는 **시드 컬럼이 아니라 도구 파라미터**다 (`seed.py:696`).
# 기대 verdict 를 재현하려면 시드가 정한 개월수를 그대로 써야 하므로 값을 베끼지 않고 import 한다 —
# 여기에 숫자를 하드코딩하면 시드가 바뀔 때 이 회귀가 조용히 어긋난다.
from data.rules import engine  # noqa: E402
from data.seed import DISPOSAL_PROBE_MONTHS, _shift_months  # noqa: E402
from mcp_server.db import DB_PATH, read_only  # noqa: E402
from mcp_server.tools.assess_repair_value import assess_repair_value  # noqa: E402
from mcp_server.tools.build_evidence_bundle import build_evidence_bundle  # noqa: E402
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
MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛㉜㉝㉞㉟㊱㊲㊳㊴㊵㊶㊷㊸㊹㊺㊻㊼㊽㊾㊿"


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
    (
        "assess_repair_value",
        assess_repair_value,
        {"equipment_id": "INV-L2-01", "failed_part": "FAN-IG5-01", "repair_cost": 300_000},
        {
            "equipment_id": "INV-L2-01",
            "failed_part": "FAN-IG5-01",
            "repair_cost": -1,  # 음수 수리비 — 폴백 금지
        },
        {"equipment_id": "INV-NOPE", "failed_part": "FAN-IG5-01", "repair_cost": 300_000},
        ("repair_scope",),
    ),
    (
        "build_evidence_bundle",
        build_evidence_bundle,
        {"asset_id": "AST-L3-CONV", "disposal_date": "2026-08-09"},
        {"asset_id": "AST-L3-CONV", "disposal_mode": "SELL"},  # enum 밖
        {"asset_id": "AST-NOPE"},
        ("equipment_id", "disposal_mode", "disposal_date"),
    ),
)

# 정상 케이스의 기대 status. 기본은 `ok` 이고, **실 DB 에서 정상적으로 실패하는** 도구만 예외다.
#
# `build_evidence_bundle` 은 인용 조문의 원문이 하나라도 미수집이면 `law_text_unavailable`
# 로 거부한다. 그래서 기대값은 **수집 상태에 따라 달라진다** — 여기 상수로 박으면
# MQ-701 이 조문을 채우는 순간 회귀가 "수집하지 말 것"을 강요하고,
# 반대로 `ok` 로 박으면 수집이 되돌아갔을 때 조용히 통과한다.
# → `data/rules/laws/*.json` 의 `fetch_status` + **그 자산이 실제로 인용한 조문**에서 파생시킨다.
LAWS_DIR = ROOT / "data" / "rules" / "laws"
_JUDGMENT_BUCKETS = ("blockers", "preconditions", "holds", "insufficient")


def unhashable_law_refs() -> set[str]:
    """계층 1 **정본 파일** 기준으로 해시할 원문이 없는 조문 (D60 — 파일이 정본)."""
    out: set[str] = set()
    for path in sorted(LAWS_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("fetch_status") != "FETCHED" or not raw.get("text") or not raw.get("text_hash"):
            out.add(raw["law_ref_id"])
    return out


def cited_law_refs(judgment: dict) -> set[str]:
    """판정 4버킷이 인용한 조문 합집합. 어떤 조문이 필요한지는 **판정이 정한다.**"""
    return {
        ref
        for bucket in _JUDGMENT_BUCKETS
        for item in judgment.get(bucket) or []
        for ref in item.get("law_refs") or []
    }


def derive_good_expect() -> tuple[dict[str, tuple[str, str | None]], str]:
    """정상 케이스 기대값 + 그 근거 문장."""
    args = GOOD_ARGS["build_evidence_bundle"]
    judgment = call(check_disposal_blockers, **args)
    needed = cited_law_refs(judgment)
    missing = sorted(needed & unhashable_law_refs())
    if missing:
        return (
            {"build_evidence_bundle": ("error", "law_text_unavailable")},
            f"미수집 조문 {missing} 인용 → 번들 거부가 정상",
        )
    return {}, f"인용 조문 {len(needed)}건 전부 수집됨 → 번들 성공이 정상"

# 케이스 인자를 **이름으로** 꺼낸다. `CASES[5][2]` 처럼 인덱스를 박으면 케이스를 하나
# 끼워 넣는 순간 조용히 다른 도구를 검사하게 된다 — MARKS 번호를 자동 부여한 것과 같은 이유다.
GOOD_ARGS: dict[str, dict] = {label: good for label, _fn, good, *_rest in CASES}

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

    # ─ ①~㉑ 7도구 × 3케이스 ─────────────────────────────────────────────────
    #   `build_evidence_bundle` 의 기대값만 계층 1 수집 상태에서 파생된다 (하드코딩 0건).
    good_expect, expect_why = derive_good_expect()
    print(f"[기대값 파생] build_evidence_bundle 정상 케이스 — {expect_why}\n")
    for label, fn, good, bad, missing, _extra in CASES:
        good_status, good_reason = good_expect.get(label, ("ok", None))
        for kind, kwargs, expect, want_reason in (
            ("정상", good, good_status, good_reason),
            ("잘못된 입력", bad, "error", None),
            ("없는 대상", missing, "not_found", None),
        ):
            res = call(fn, **kwargs)
            got = res.get("status")
            detail = f"status={got} reason={res.get('reason', '-')}"
            if got not in STATUSES:
                detail += "  ← status 4종(D9) 밖"
            ok = got == expect and (want_reason is None or res.get("reason") == want_reason)
            label_kind = kind if want_reason is None else f"{kind}({want_reason})"
            check(f"{label} — {label_kind}", ok, detail)

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

    # ─ ㉙-b 출력 키집합 전수 대조 (`04 §8`) ──────────────────────────────────
    #   ★ 이 검사가 없어서 `facts_used`·`laws_used`(D82) 가 엔진 → `**result` 스프레드를 타고
    #     계약에 없는 키로 조용히 승격됐다. 개별 키 존재만 보면 **늘어난 키를 영원히 못 잡는다.**
    #     계약을 넓히는 변경은 `04 §8` 을 먼저 고치라는 신호로 여기서 FAIL 시킨다.
    contract_keys = {
        "status",
        "asset_id",
        "evaluated_at",
        "verdict",
        "blockers",
        "preconditions",
        "holds",
        "insufficient",
        "disposal_mode",
        "disposal_date",
        "evidence_completeness",
        "not_considered",
        "disclaimer",
    }
    probe = probe_date.get("AST-L3-CONV")
    keyset = set(call(check_disposal_blockers, asset_id="AST-L3-CONV", disposal_mode="SALE",
                      disposal_date=probe))
    check(
        "check_disposal_blockers — 출력 키집합이 04 §8 과 정확히 일치 (초과 키 = 계약 드리프트)",
        keyset == contract_keys,
        f"초과={sorted(keyset - contract_keys) or '없음'} 누락={sorted(contract_keys - keyset) or '없음'}",
    )

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

    # ─ assess_repair_value — 추정치는 추정치로 (D65) · 반복 고장은 3지 판단 앞이다 (D2·S3)
    arv = call(assess_repair_value, **GOOD_ARGS["assess_repair_value"])
    estimates = arv.get("estimates") or []
    check(
        "assess_repair_value — estimates[] 에 시장가·회복액이 나열된다 (D65 추정치 고지)",
        arv.get("status") == "ok"
        and {"market_value_before", "market_value_after", "value_recovery"} <= set(estimates)
        and bool(str(arv.get("disclaimer") or "").strip()),
        f"verdict={arv.get('verdict')} estimates={estimates}",
    )
    # `INV-L3-01` 은 시드에서 OHt 반복 고장 자산이다 — 반복이면 3지 선택지 자체가 없다.
    root = call(
        assess_repair_value,
        equipment_id="INV-L3-01",
        failed_part="FAN-IG5-01",
        repair_cost=300_000,
    )
    check(
        "assess_repair_value — ROOT_CAUSE_FIRST 는 수리/교체/매각 선택지를 내지 않는다 (규칙 14)",
        root.get("verdict") == "ROOT_CAUSE_FIRST"
        and not root.get("alternatives")
        and not root.get("estimates")
        and root.get("market_value_before") is None,
        f"verdict={root.get('verdict')} alternatives={root.get('alternatives')} "
        f"estimates={root.get('estimates')}",
    )

    # ─ build_evidence_bundle — 합성 픽스처로만 해시가 나온다 (MQ-610 픽스처 흡수) ─────
    #   처분일은 위 verdict 프로브와 **같은 값**을 쓴다 — 여기서 오늘 날짜를 쓰면 판정이
    #   달라져 "무엇을 근거로 묶었는가"가 위 검사와 어긋난다 (D62).
    probe_iso = probe_date.get("AST-L3-CONV")
    #   해시 안정성은 **인용 조문이 전부 채워진 DB** 에서만 검증할 수 있다. MQ-701 이 실 DB 를
    #   채운 뒤에도 이 사본을 쓰는 이유: 미수집 조문이 1건이라도 남으면(예: 사람 승인 대기 중인
    #   `KR-CITA-ENF-31`) 이 검사가 수집 상태에 따라 켜졌다 꺼졌다 한다. 원본은 건드리지 않는다.
    with tempfile.TemporaryDirectory() as td:
        fetched_db = Path(td) / "law_fetched.db"
        shutil.copy2(DB_PATH, fetched_db)
        con = sqlite3.connect(fetched_db)
        try:
            for (rid,) in con.execute("SELECT law_ref_id FROM law_refs").fetchall():
                text = f"[합성 픽스처] {rid} 조문 원문"
                con.execute(
                    "UPDATE law_refs SET text=?, text_hash=?, fetch_status='FETCHED' "
                    "WHERE law_ref_id=?",
                    (text, hashlib.sha256(text.encode()).hexdigest(), rid),
                )
            con.commit()
        finally:
            con.close()

        saved_db = mcp_db.DB_PATH
        try:
            mcp_db.DB_PATH = fetched_db
            b1 = call(build_evidence_bundle, asset_id="AST-L3-CONV", disposal_date=probe_iso)
            b2 = call(build_evidence_bundle, asset_id="AST-L3-CONV", disposal_date=probe_iso)
            clear = call(
                build_evidence_bundle,
                asset_id="AST-L3-LIFT",
                disposal_mode="SCRAP",
                # 처분일을 빼면 `TAX-CREDIT-2Y` 가 사실 부족으로 남아 CLEAR 가 아니다 (D62).
                # 이 도구를 `disposal_date` 없이 부르면 안 되는 이유가 여기서도 드러난다.
                disposal_date=probe_date.get("AST-L3-LIFT"),
            )
        finally:
            mcp_db.DB_PATH = saved_db

    # ★ 번들 스키마는 MQ-705 에서 3키 → **5키**가 됐다 (D83). 여기서는 계약의 겉면만
    #   확인하고, 무결성 축(rule_hash·주입·N1·N2·뮤턴트 생존)은 `spikes/bundle_integrity.py`
    #   가 전담한다 — 두 스위트가 같은 것을 검사하면 한쪽을 고칠 때 다른 쪽이 가려 준다.
    bundle_keys = {"laws", "rules", "evaluated", "contracts", "facts"}
    check(
        "build_evidence_bundle — 원문이 있으면 해시 산출 · 같은 사실이면 2회 동일 (built_at 은 해시 밖)",
        b1.get("status") == "ok"
        and b2.get("status") == "ok"
        and b1.get("bundle_hash") == b2.get("bundle_hash")
        and str(b1.get("bundle_hash") or "").startswith("sha256:")
        and set(b1.get("evidence_bundle") or {}) == bundle_keys
        and b1.get("hash_spec")  # N1 — 해시 규약의 이름은 번들 **밖**에 붙는다
        and "hash_spec" not in (b1.get("evidence_bundle") or {})
        and b1.get("built_at") is not None
        and b1.get("not_considered"),
        f"status={b1.get('status')} hash={str(b1.get('bundle_hash'))[:24]}… "
        f"동일={b1.get('bundle_hash') == b2.get('bundle_hash')} "
        f"번들키={sorted(b1.get('evidence_bundle') or {})}",
    )
    check(
        "build_evidence_bundle — CLEAR 자산은 laws·rules 가 비어도 evaluated[] 는 비지 않는다 (W7)",
        clear.get("status") == "ok"
        and clear.get("verdict") == "CLEAR"
        and (clear.get("evidence_bundle") or {}).get("laws") == []
        and (clear.get("evidence_bundle") or {}).get("rules") == []
        # 빈 근거도 사실이라 해시는 나온다. 다만 **무엇을 평가했는지**는 남아야 한다 —
        # 이게 없으면 "조회 결과 해당 없음"과 "아예 안 봤다"가 번들에서 구분되지 않는다.
        and bool((clear.get("evidence_bundle") or {}).get("evaluated"))
        and bool(clear.get("bundle_hash")),
        f"verdict={clear.get('verdict')} "
        f"evaluated={len((clear.get('evidence_bundle') or {}).get('evaluated') or [])}건 "
        f"hash={str(clear.get('bundle_hash'))[:24]}…",
    )

    # ─ MCP ↔ REST 직접 대조 (Stage 5 reviewer 지정 2) ───────────────────────
    #   지금까지 두 소비자는 **각자 파일 정본과 간접 대조**만 했다. 둘이 서로 갈리는 조합은
    #   어느 쪽 회귀에도 잡히지 않는다 — 같은 프로브로 직접 맞대 본다.
    #   MCP 도구는 파일 정본(`engine.check_disposal_blockers`)을, REST 서비스는 DB 사본
    #   (`load_rules_from_db` + `evaluate_rule`)을 쓴다. 즉 이 대조는 **두 벌 판정의 대조**다.
    from backend.services.disposal import precheck  # noqa: PLC0415

    rest_probes = (
        ("AST-L3-CONV", "SALE"),
        ("AST-L4-WRAP", "SALE"),
        ("AST-L4-DUST", "SALE"),
        ("AST-L2-SPDL", "SALE"),
        ("AST-L3-LIFT", "SALE"),
        ("AST-L3-LIFT", "SCRAP"),
    )

    def _mcp_vs_rest(db: Path) -> list[str]:
        """(MCP verdict, REST verdict) 가 갈리는 조합. **비교 로직은 한 벌뿐**이라
        아래 '방어선 생존' 검사가 이 함수를 그대로 재사용해 검사력을 증명한다."""
        gaps = []
        for asset, mode in rest_probes:
            when = probe_date.get(asset)
            mcp_out = call(check_disposal_blockers, asset_id=asset, disposal_mode=mode, disposal_date=when)
            try:
                rest_out = precheck(asset, disposal_mode=mode, disposal_date=when, db_path=db)
            except Exception as exc:  # noqa: BLE001 — 예외도 불일치로 기록한다
                gaps.append(f"{asset}/{mode}: REST 예외 {type(exc).__name__}")
                continue
            if mcp_out.get("verdict") != rest_out.get("verdict"):
                gaps.append(
                    f"{asset}/{mode}: MCP={mcp_out.get('verdict')} vs REST={rest_out.get('verdict')}"
                )
        return gaps

    mismatch = _mcp_vs_rest(DB_PATH)
    check(
        "MCP(파일 정본) verdict == REST(DB 사본) verdict — 같은 프로브 6조합 직접 대조",
        not mismatch,
        "; ".join(mismatch) or f"{len(rest_probes)}조합 일치",
    )

    # ─ 방어선 생존 확인 — 위 대조가 '항상 통과하는 검사'가 아님을 증명한다 ──────
    #   Stage 4 W-a 와 같은 유형(공허한 PASS)을 막는다. DB 룰 **1행만** 어긋나게 한
    #   사본으로 같은 대조를 돌려, 실제로 **불일치가 검출되는지** 확인한다.
    #   ⚠ 여기서 기대하는 것은 "실패"다 — 불일치가 안 잡히면 그게 결함이다.
    with tempfile.TemporaryDirectory() as td:
        drifted = Path(td) / "rule_drift.db"
        shutil.copy2(DB_PATH, drifted)
        con = sqlite3.connect(drifted)
        try:
            # `required_facts` 에 원천 없는 필드를 하나 끼운다 — 조문 참조·트리거는 그대로라
            # 로드 게이트(D61·무결성 검사)에 걸리지 않고 **판정만 조용히 바뀐다**(D77 이 다룬
            # 바로 그 유형). DB 사본에서만 이 룰이 항상 `INSUFFICIENT_FACTS` 가 된다.
            #
            # ⚠ 처음에는 `disposal_type` 을 BLOCKING→PRECONDITION 으로 바꿔 봤는데
            #   **불일치가 잡히지 않았다** — `AST-L3-CONV` 는 blocker 가 2건이라 하나를 내려도
            #   verdict 가 `BLOCKED` 로 남고, 다른 자산은 이 룰을 발화시키지 않는다.
            #   즉 "룰 1행을 바꿨다"가 곧 "판정이 달라진다"는 아니다. 픽스처가 **verdict 로
            #   드러나는 드리프트**여야 이 검사가 검사력을 갖는다.
            changed = con.execute(
                "UPDATE rules SET required_facts = ? WHERE rule_id = 'LIEN-CONSENT'",
                (json.dumps(["has_lien", "lien_creditor", "drifted_ghost_fact"]),),
            ).rowcount
            con.commit()
        finally:
            con.close()
        drift_gaps = _mcp_vs_rest(drifted)

    check(
        "방어선 생존 — DB 룰 1행을 어긋나게 하면 MCP↔REST 대조가 **실제로 FAIL** 한다",
        changed == 1 and bool(drift_gaps),
        f"변경 {changed}행 · 검출된 불일치 {len(drift_gaps)}건 {drift_gaps[:2]}",
    )

    # ─ W2 이월 — REST 가 복제한 엔진 문구가 드리프트하지 않았는가 ────────────
    #   `backend/services/disposal.py` 가 `not_considered`·`disclaimer` 를 **문자열로 복제**한다.
    #   엔진이 바꾸면 REST 만 조용히 옛 문구를 낸다(D73 이 기각한 복제 유형).
    with read_only() as con:
        conv_row = con.execute(
            "SELECT * FROM assets WHERE asset_id = 'AST-L3-CONV'"
        ).fetchone()
    engine_out = engine.check_disposal_blockers(
        engine.build_facts(conv_row, disposal_mode="SALE", disposal_date=probe_iso)
    )
    rest_out = precheck("AST-L3-CONV", disposal_mode="SALE", disposal_date=probe_iso)
    check(
        "REST 가 복제한 not_considered·disclaimer 가 엔진과 동일 (W2 드리프트 감시)",
        rest_out.get("not_considered") == engine_out.get("not_considered")
        and rest_out.get("disclaimer") == engine_out.get("disclaimer"),
        f"not_considered 일치={rest_out.get('not_considered') == engine_out.get('not_considered')} "
        f"disclaimer 일치={rest_out.get('disclaimer') == engine_out.get('disclaimer')}",
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
        "예외 무누출 — 도구 7종 × 타입 오류 입력(optional 파라미터 포함)",
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
        f"\n통과 ({len(results)}건) — 도구 7종 · D9·D46(status 반환)·D62(모른다≠통과)·"
        "D64(OEE 금지)·D65·D78·D79 준수 · B-1 회귀 · MCP↔REST 대조와 그 방어선 생존 확인 포함"
    )


if __name__ == "__main__":
    main()
