# -*- coding: utf-8 -*-
"""IE5 추출 경로 계약 검증 (MQ-1405 · Sprint 14 Stage 1 · P29).

검증 대상 (`data/extract_ie5_codes.py` + 그 산출물 2종):
  A. **기하 픽스처** — 괘선 없는 표에서 유도한 열/행 경계가 3열로 떨어졌는가 (sprint-14 §0-3).
     ⑭⑮ 는 저장된 결과를 보는 데 그치지 않고 **픽스처 좌표로 가짜 page 를 만들어
     `column_bounds()` 를 다시 실행**한다 — §0-3 이 지목한 가장 위험한 로직(열 경계 유도)이
     PDF 없이도 회귀에 걸리게 하려는 것이다. ⑮ 는 D9 실패 경로(예외 아님)를 함께 본다.
  B. **조인 로직 재현** — 픽스처의 `code_name_pairs` 로 `join()` 을 다시 돌려 실측과 일치하는가.
     ⑧ 은 `codes[].cause`/`action` 이 **올바른 밴드의 그리드 셀**에서 왔는지까지 본다
     (병합 셀 복제 `merged_with` 가 엉뚱한 밴드를 복제해도 개수 검사는 통과한다).
  C. **후보 파일 계약** — `_status` 초안 마커(D33) · `_unmatched` **3버킷** 비공백 ·
     `_stats` 자기무결성 · `manual_page` 가 물리 페이지(D26) · **리콜**(§0-2 확정 12종 전건 등장) ·
     **대문자 canonical 접기**(D25) + 원표기 보존
  D. **부재 주장** — 정본 미기록(D99) · `data/raw/` 미기록 · `extract_text()` 폴백 부재
  E. **PDF 대조** — PDF 가 있을 때만 도는 축 (없으면 `SKIP`, **건수와 함께 인쇄**)
  F. **메타 오라클** — 불량 픽스처를 메모리에서 만들어 A·B·C 판정식이 실제로 **발화**하는지

⛔ **PDF 를 열지 않는 것이 기본이다.** `.gitignore:2` 가 `data/raw/*` 라 IE5 PDF 는 git 에 없다
   (sprint-14 §7-2). 새 클론·CI 에서도 A~D·F 는 전부 돈다 — E 만 `SKIP` 으로 빠진다.
   그 `SKIP` 은 **숨기지 않고 표와 마지막 줄에 숫자로 인쇄**한다. 조용한 0건 통과 금지.

⚠ **부재 검사에는 liveness 앵커를 함께 건다** (CLAUDE.md 회귀 절 · P30 선례). D 의 세 검사는
   전부 `not bad and anchors > 0` 형태이고, detail 에는 결론 문구가 아니라 **두 축의 실측값**을
   찍는다. D③ 은 한 발 더 나가 **양성 대조**를 쓴다 — 같은 스캐너가 `body_code_names()` 안의
   진짜 `extract_text()` 호출을 잡아내는지 확인한다(못 잡으면 "없다"는 판정이 무의미하다).
   F⑨ 는 그 스캐너를 합성 소스로 한 번 더 검증하는 독립 오라클이다.

⚠ **모든 probe 에 `guard` 를 건다.** guard 가 A 에만 걸려 있으면 B·C·D·F 의 직접 인덱싱이
   회귀 시 **FAIL 이 아니라 트레이스백**으로 터져 뒤 검사가 통째로 안 돈다 — 표에서 검사가
   사라지는 것이 실패보다 나쁘다(건수 기준선이 조용히 줄어든다).

실행:  uv run python spikes/ie5_extract_contract.py
       MAINTQ_IE5_PDF=/nonexistent uv run python spikes/ie5_extract_contract.py   # E 축 SKIP 확인
"""

from __future__ import annotations

import ast
import copy
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data import extract_ie5_codes as ie5  # noqa: E402 — sys.path 주입 후여야 한다

FIXTURE = ROOT / "spikes" / "fixtures" / "ie5_p125_geometry.json"
CANDIDATE = ROOT / "data" / "extracted" / "ie5_code_candidates.json"
CANONICAL = ROOT / "data" / "extracted" / "error_codes.json"
SRC_PATH = ROOT / "data" / "extract_ie5_codes.py"
SEED_PATH = ROOT / "data" / "seed.py"

PAGES = (125, 126)  # 물리 페이지 (D26)
TOP_KEYS = (
    "_source",
    "_generated_by",
    "_generated_at",
    "pages",
    "code_name_pairs",
    "shape_excluded_pairs",
    "expected",
)
PAGE_KEYS = (
    "page",
    "v_edge_x",
    "column_bounds",
    "table_y_range",
    "text_extent",
    "v_edges",
    "row_bounds",
    "name_row_bounds",
    "rows",
)
POLITE = re.compile(r"(십시오|합니다|하세요)")  # 대책 열의 종결 어미 — 원인 열에는 없어야 한다
NARROW = re.compile(r"[A-Za-z]{3}")  # 좁힌 코드 형상
SPEC = re.compile(r"[A-Za-z][A-Za-z0-9]{1,3}")  # 스펙 코드 형상 (정본 65종 중 64종이 이 안)
GEO_TOL = 0.05  # 픽스처 좌표가 소수 2자리로 반올림돼 있어 재유도값과 이만큼 어긋날 수 있다

results: list[tuple[str, str, str]] = []  # (제목, PASS|FAIL|SKIP, detail)


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, "PASS" if ok else "FAIL", detail))


def skip(name: str, detail: str) -> None:
    results.append((name, "SKIP", detail))


def guard(fn):
    """probe 래퍼 — 뮤턴트·회귀가 예외를 내도 '판정 실패'로 환원한다.

    A 뿐 아니라 **B·C·D·E·F 전부**에 건다. 안 걸면 `doc["_stats"]` 같은 직접 인덱싱 하나가
    스파이크를 통째로 죽여, 표에서 검사가 **사라진다** — FAIL 보다 나쁜 실패 양식이다.
    """

    def wrapped(*args: Any, **kwargs: Any) -> tuple[bool, str]:
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 — 예외도 FAIL 로 본다
            return False, f"예외 {type(e).__name__}: {e}"

    wrapped.__name__ = fn.__name__
    return wrapped


# ──────────────────────────────────────────────── A. 픽스처 probe (메타에서 재사용)
@guard
def probe_top_keys(fx: dict) -> tuple[bool, str]:
    missing = [k for k in TOP_KEYS if k not in fx]
    src = fx.get("_source") or {}
    src_ok = bool(src.get("sha256")) and bool(src.get("file"))
    return (
        not missing and src_ok,
        f"최상위 키 {len(fx)}개 · 누락 {missing or '없음'} · _source.sha256 "
        f"{'있음' if src.get('sha256') else '없음'}",
    )


@guard
def probe_pages(fx: dict) -> tuple[bool, str]:
    pages = fx.get("pages") or []
    nums = [p.get("page") for p in pages]
    missing = {p.get("page"): [k for k in PAGE_KEYS if k not in p] for p in pages}
    bad = {k: v for k, v in missing.items() if v}
    return (
        tuple(nums) == PAGES and not bad,
        f"페이지 {nums} (기대 {list(PAGES)}) · 페이지 키 누락 {bad or '없음'}",
    )


@guard
def probe_col_count(fx: dict) -> tuple[bool, str]:
    got = {p["page"]: len(p["column_bounds"]) for p in fx["pages"]}
    return (
        bool(got) and all(n == 4 for n in got.values()) and len(got) == len(PAGES),
        f"열 경계 개수 {got} (3열 = 경계 4개) · 페이지 {len(got)}장",
    )


@guard
def probe_monotonic(fx: dict) -> tuple[bool, str]:
    detail = {}
    ok = bool(fx["pages"])
    for p in fx["pages"]:
        cb = p["column_bounds"]
        mono = all(a < b for a, b in zip(cb, cb[1:], strict=False)) and len(cb) > 1
        detail[p["page"]] = f"{[round(v, 2) for v in cb]}{'↑' if mono else '✗'}"
        ok = ok and mono
    return ok, f"열 경계 {detail}"


@guard
def probe_not_hardcoded(fx: dict) -> tuple[bool, str]:
    sets = [tuple(p["column_bounds"]) for p in fx["pages"]]
    deltas = [round(b - a, 2) for a, b in zip(sets[0], sets[1], strict=True)]
    return (
        len(set(sets)) == len(sets) and all(d != 0 for d in deltas),
        f"p125↔p126 경계 차 {deltas} (전부 0 이면 하드코딩 의심 · §0-3 '페이지마다 다르다')",
    )


@guard
def probe_clamp(fx: dict) -> tuple[bool, str]:
    detail = {}
    ok = bool(fx["pages"])
    for p in fx["pages"]:
        cb, (lo, hi) = p["column_bounds"], p["text_extent"]
        inside = lo <= cb[0] and cb[-1] <= hi + 1e-6 and all(lo <= b <= hi for b in cb[1:-1])
        detail[p["page"]] = f"글자범위[{lo},{hi}] 경계[{cb[0]},{cb[-1]}] 우측일치={cb[-1] == hi}"
        ok = ok and inside
    return ok, f"{detail}"


@guard
def probe_row_bounds(fx: dict) -> tuple[bool, str]:
    detail = {}
    ok = bool(fx["pages"])
    for p in fx["pages"]:
        rb, rows = p["row_bounds"], p["rows"]
        mono = all(a < b for a, b in zip(rb, rb[1:], strict=False))
        shape = len(rows) == len(rb) - 1
        detail[p["page"]] = f"경계{len(rb)}개{'↑' if mono else '✗'} 그리드{len(rows)}행"
        ok = ok and mono and shape and len(rb) >= 3
    return ok, f"{detail} (그리드 행 = 경계-1)"


@guard
def probe_name_bounds(fx: dict) -> tuple[bool, str]:
    detail = {}
    ok = bool(fx["pages"])
    for p in fx["pages"]:
        rb, nrb = p["row_bounds"], p["name_row_bounds"]
        extra = [y for y in nrb if y not in rb]
        superset = set(rb) <= set(nrb)
        detail[p["page"]] = f"본문{len(rb)} ⊂ 명칭{len(nrb)} 추가경계{extra}"
        ok = ok and superset and len(extra) >= 1
    return ok, f"{detail} (추가 경계 = 세로 병합 밴드)"


@guard
def probe_header(fx: dict) -> tuple[bool, str]:
    detail = {}
    ok = bool(fx["pages"])
    for p in fx["pages"]:
        head = p["rows"][0]
        hit = len(head) == 3 and all(
            k in ie5.norm_key(c) for k, c in zip(ie5.HEADER_KEYS, head, strict=True)
        )
        detail[p["page"]] = f"{head}{'✓' if hit else '✗'}"
        ok = ok and hit
    return ok, f"{detail}"


@guard
def probe_row_width(fx: dict) -> tuple[bool, str]:
    widths: dict[int, set[int]] = {}
    n = 0
    for p in fx["pages"]:
        widths[p["page"]] = {len(r) for r in p["rows"]}
        n += len(p["rows"])
    return (
        n > 0 and all(w == {3} for w in widths.values()),
        f"행 {n}개 · 페이지별 셀 폭 { ({k: sorted(v) for k, v in widths.items()}) }",
    )


@guard
def probe_no_column_bleed(fx: dict) -> tuple[bool, str]:
    """원인 열에 대책 문장이 섞이지 않았는가 (§0-3 의 조용한 오작동).

    두 축으로 판정한다 — 원인 열에 존댓말 종결이 **없고**(부재), 대책 열에는 **있다**(앵커).
    앵커가 없으면 정규식이 죽어도 조용히 통과한다.
    """
    bleed, anchored, total = [], 0, 0
    for p in fx["pages"]:
        for row in p["rows"][1:]:
            total += 1
            if POLITE.search(row[1]):
                bleed.append((p["page"], row[0][:10], POLITE.search(row[1]).group()))
            if POLITE.search(row[2]):
                anchored += 1
    return (
        not bleed and anchored > 0 and total > 0,
        f"본문 {total}행 · 원인 열 존댓말 종결 {len(bleed)}건{bleed if bleed else ''} · "
        f"대책 열 존댓말 종결 {anchored}건(앵커)",
    )


@guard
def probe_bullets(fx: dict) -> tuple[bool, str]:
    cells = [row[1] for p in fx["pages"] for row in p["rows"][1:]]
    parts = [ie5.split_bullets(c) for c in cells]
    multi = sum(1 for x in parts if len(x) >= 2)
    return (
        bool(cells) and all(parts) and multi > 0,
        f"원인 셀 {len(cells)}개 → 문장 {sum(len(x) for x in parts)}건 · 2문장 이상 {multi}행",
    )


@guard
def probe_band_arith(fx: dict) -> tuple[bool, str]:
    """명칭 열 경계에서 유도한 밴드 총수 == `_stats.table_rows` (기하 ↔ 통계 자기무결성)."""
    per = {p["page"]: len(p["name_row_bounds"]) - 2 for p in fx["pages"]}  # 머리행 제외
    derived = sum(per.values())
    stated = fx["expected"]["stats"]["table_rows"]
    return derived == stated and derived > 0, f"기하 유도 {per} 합 {derived} · expected {stated}"


# ── A⑭⑮ 추출기 **재실행** 축 (PDF-free)
class FakePage:
    """픽스처 좌표만으로 만든 최소 page 대역.

    `column_bounds()` → `vertical_clusters()` + `text_extent()` 가 쓰는 인터페이스는
    `page.edges` 와 `page.extract_words()` 둘뿐이다. 픽스처가 `v_edges`(=[x0, top, bottom])와
    `text_extent` 를 이미 들고 있으므로 **PDF 없이 유도 로직을 그대로 태울 수 있다.**
    이 축이 없으면 §0-3 이 지목한 가장 위험한 로직이 기본 실행에서 한 줄도 안 돈다.
    """

    def __init__(self, v_edges: list[list[float]], extent: list[float]) -> None:
        self.edges = [
            {
                "orientation": "v",
                "x0": float(x),
                "x1": float(x),
                "top": float(t),
                "bottom": float(b),
            }
            for x, t, b in v_edges
        ]
        self._extent = (float(extent[0]), float(extent[1]))

    def extract_words(self) -> list[dict]:
        lo, hi = self._extent
        return [
            {"text": "L", "x0": lo, "x1": lo + 1.0, "top": 100.0, "bottom": 110.0},
            {"text": "R", "x0": hi - 1.0, "x1": hi, "top": 100.0, "bottom": 110.0},
        ]


def near(a: list[float] | None, b: list[float] | None, tol: float = GEO_TOL) -> bool:
    if a is None or b is None or len(a) != len(b):
        return False
    return all(abs(x - y) <= tol for x, y in zip(a, b, strict=True))


@guard
def probe_recolumn(fx: dict) -> tuple[bool, str]:
    """픽스처 기하로 `column_bounds()` 를 **재유도**해 저장값과 대조한다."""
    detail: dict[int, str] = {}
    ok = bool(fx["pages"])
    for p in fx["pages"]:
        page = FakePage(p["v_edges"], p["text_extent"])
        bounds, y_range, why = ie5.column_bounds(page)
        hit_b = near(bounds, p["column_bounds"])
        hit_y = near(list(y_range) if y_range else None, p["table_y_range"])
        detail[p["page"]] = (
            f"재유도 {bounds} vs 저장 {p['column_bounds']} → 경계일치={hit_b} · "
            f"y범위 {list(y_range) if y_range else None} vs {p['table_y_range']} → {hit_y}"
            f"{' · 사유=' + why if why else ''}"
        )
        ok = ok and hit_b and hit_y
    return ok, f"(tol {GEO_TOL}pt — 픽스처는 소수 2자리 반올림) {detail}"


@guard
def probe_recolumn_d9(fx: dict) -> tuple[bool, str]:
    """열 경계 유도 **실패 경로**가 예외가 아니라 (None, None, 사유) 인가 (D9)."""
    empty = ie5.column_bounds(FakePage([], fx["pages"][0]["text_extent"]))
    p = fx["pages"][0]
    drop = p["column_bounds"][1]
    thinned = [e for e in p["v_edges"] if abs(e[0] - drop) > ie5.X_TOL]
    missing = ie5.column_bounds(FakePage(thinned, p["text_extent"]))
    both_none = empty[0] is None and empty[1] is None and missing[0] is None and missing[1] is None
    reasons = bool(empty[2]) and bool(missing[2])
    removed = len(p["v_edges"]) - len(thinned)
    return (
        both_none and reasons and removed > 0,
        f"edge 0개 → {empty[0]} 사유={empty[2][:40]!r} · x≈{drop} edge {removed}개 제거 → "
        f"{missing[0]} 사유={missing[2][:60]!r} (예외 없이 상태로 반환 = D9)",
    )


# ──────────────────────────────────────────────── B. 조인 재현
def synth_row(name: str, page: int = 125) -> dict:
    """`join()` 이 먹는 최소 행 — 정규화 규칙을 **고립**해 검사할 때 쓰는 합성 입력."""
    return {
        "보호기능": name,
        "이상원인": [],
        "대책": [],
        "manual_page": page,
        "band": [0.0, 1.0],
        "name_band": [0.0, 1.0],
        "name_clipped": False,
        "name_band_raw": name,
        "merged_with": [],
    }


def rebuild_rows(fx: dict) -> tuple[list[dict], list[str], dict]:
    """픽스처 그리드 + 명칭 인벤토리 → `join()` 이 먹는 행 목록을 재구성한다.

    명칭 인벤토리(13종)는 `expected` 에서 오지만 **분할·귀속은 그리드 col0 와 명칭 행 경계에서
    유도**한다 — 즉 입력은 기하, 출력은 조인 결과다. 병합 밴드(`인버터 과부하 과부하 트립`)가
    두 명칭으로 쪼개지는지까지 여기서 드러난다.
    """
    exp = fx["expected"]
    inventory = [m["name_ko"] for m in exp["matched"]] + list(exp["unmatched_names"])
    index = {ie5.norm_key(n): n for n in inventory if n}
    rows: list[dict] = []
    used: list[str] = []
    bands: dict[str, int] = {}
    for p in fx["pages"]:
        for gi, grid in enumerate(p["rows"][1:], start=1):
            rest = ie5.norm_key(grid[0])
            names = [""] if not rest else []
            while rest:
                cands = [k for k in index if rest.startswith(k)]
                if not cands:
                    names.append(f"!!미해결:{rest}")
                    break
                key = max(cands, key=len)
                names.append(index[key])
                rest = rest[len(key) :]
            top, bottom = p["row_bounds"][gi], p["row_bounds"][gi + 1]
            inner = [y for y in p["name_row_bounds"] if top + ie5.Y_TOL < y < bottom - ie5.Y_TOL]
            bands[f"p{p['page']}r{gi}"] = len(inner) + 1
            for name in names:
                used.append(name)
                rows.append(
                    {
                        "보호기능": name,
                        "이상원인": ie5.split_bullets(grid[1]),
                        "대책": ie5.split_bullets(grid[2]),
                        "manual_page": p["page"],
                        "band": [top, bottom],
                        "name_band": [top, bottom],
                        "name_clipped": False,
                        "name_band_raw": grid[0],
                        "merged_with": [n for n in names if n != name],
                    }
                )
    stats = {
        "inventory": len(inventory),
        "rows": len(rows),
        "소비일치": sorted(used) == sorted(inventory),
        "밴드합": sum(bands.values()),
        "미해결": [n for n in used if n.startswith("!!")],
    }
    return rows, used, stats


@guard
def probe_body_shape(fx: dict) -> tuple[bool, str]:
    """두 버킷의 괄호 표기가 각자의 **형상**을 지키는가 + 둘이 서로소인가."""
    occ = fx["code_name_pairs"]
    shape_occ = fx["shape_excluded_pairs"]
    bad_shape = [
        o
        for o in occ
        if not (
            {"code", "name_raw", "page"} <= set(o)
            and NARROW.fullmatch(str(o["code"]))
            and isinstance(o["page"], int)
        )
    ]
    bad_excl = [
        o
        for o in shape_occ
        if not (
            {"code", "name_raw", "page"} <= set(o)
            and SPEC.fullmatch(str(o["code"]))
            and not NARROW.fullmatch(str(o["code"]))
        )
    ]
    overlap = {o["code"] for o in occ} & {o["code"] for o in shape_occ}
    return (
        bool(occ) and bool(shape_occ) and not bad_shape and not bad_excl and not overlap,
        f"좁은 형상 {len(occ)}건(코드 {len({o['code'] for o in occ})}종) · 형상 제외 "
        f"{len(shape_occ)}건(코드 {len({o['code'] for o in shape_occ})}종) · 형식 위반 "
        f"{len(bad_shape)}/{len(bad_excl)}건 · 표기 겹침 {sorted(overlap)}",
    )


@guard
def probe_rebuild(fx: dict) -> tuple[bool, str]:
    _rows, _used, stats = rebuild_rows(fx)
    return (
        stats["소비일치"] and not stats["미해결"] and stats["rows"] == stats["밴드합"],
        f"인벤토리 {stats['inventory']}종 → 행 {stats['rows']}개 · 기하 밴드합 {stats['밴드합']} · "
        f"명칭 1:1 소비={stats['소비일치']} · 미해결 {stats['미해결']}",
    )


@guard
def probe_join_matched(fx: dict) -> tuple[bool, str]:
    rows, _u, _s = rebuild_rows(fx)
    matched, _uc, _un = ie5.join(rows, fx["code_name_pairs"])
    got = sorted(
        (m["code"], m["canonical_code"], rows[m["row"]]["보호기능"], m["join_variant"])
        for m in matched
    )
    want = sorted(
        (m["code"], m["canonical_code"], m["name_ko"], m["join_variant"])
        for m in fx["expected"]["matched"]
    )
    return (
        got == want and len(got) > 0,
        f"재현 {len(got)}건 {[(c, k, v) for c, k, _n, v in got]} · 기대 {len(want)}건 "
        f"(일치={got == want})",
    )


@guard
def probe_join_unmatched(fx: dict) -> tuple[bool, str]:
    rows, _u, _s = rebuild_rows(fx)
    matched, un_codes, un_names = ie5.join(rows, fx["code_name_pairs"])
    exp = fx["expected"]
    got_uc = sorted(u["canonical_code"] for u in un_codes)
    got_un = sorted(u["name"] for u in un_names)
    hit_rows = len({m["row"] for m in matched})
    # 🔴 올바른 항등식: `matched` 는 **(코드, 행) 쌍 수**라 행 수와 다를 수 있다.
    #    버려진 행이 0 임을 주장하려면 **행 축**으로 세야 한다.
    closed = hit_rows + len(got_un) == len(rows)
    return (
        got_uc == sorted(exp["unmatched_codes"])
        and got_un == sorted(exp["unmatched_names"])
        and closed,
        f"코드 {len(got_uc)}/{len(exp['unmatched_codes'])} · 명칭 {len(got_un)}/"
        f"{len(exp['unmatched_names'])} · 행 폐포 {hit_rows}(코드 붙은 행)+{len(got_un)}(미매칭 행)"
        f"={hit_rows + len(got_un)} vs 전체 {len(rows)}행 → 버려진 행 없음={closed} "
        f"(matched 쌍 {len(matched)}건 ≠ 행 수일 수 있다)",
    )


@guard
def probe_cause_action(fx: dict, doc: dict) -> tuple[bool, str]:
    """`codes[].cause`/`action` 이 **그 밴드의 그리드 셀**에서 왔는가.

    개수 검사(C③)나 (code, name) 비교(B③)는 병합 셀 복제가 **엉뚱한 밴드**를 복제해도
    전부 통과한다. 픽스처 그리드에서 원인·대책을 다시 유도해 값 자체를 대조한다.
    """
    rows, _u, _s = rebuild_rows(fx)
    matched, _uc, _un = ie5.join(rows, fx["code_name_pairs"])
    got = {
        m["canonical_code"]: (rows[m["row"]]["이상원인"], rows[m["row"]]["대책"]) for m in matched
    }
    want = {c["canonical_code"]: (c["cause"], c["action"]) for c in doc["codes"]}
    diff = sorted(k for k in set(got) | set(want) if got.get(k) != want.get(k))
    # 병합 밴드 앵커 — 복제가 실제로 일어났고, 복제된 쪽이 **같은 밴드**의 셀을 들고 있다
    merged = [c for c in doc["codes"] if c["merged_with"]]
    merged_ok = all(
        got.get(c["canonical_code"]) == (c["cause"], c["action"]) and c["cause"] and c["action"]
        for c in merged
    )
    nonempty = sum(1 for v in want.values() if v[0] and v[1])
    return (
        not diff and bool(want) and merged_ok and len(merged) > 0 and nonempty == len(want),
        f"코드 {len(want)}종 대조 · 불일치 {diff or '없음'} · 병합 밴드 {len(merged)}건"
        f"{[(c['code'], c['merged_with']) for c in merged]} 셀 일치={merged_ok} · "
        f"원인·대책 둘 다 비지 않은 코드 {nonempty}/{len(want)}",
    )


@guard
def probe_norm_a() -> tuple[bool, str]:
    n1, n2 = ie5.norm_key("냉각 핀 과열"), ie5.norm_key("과전압 (Ovt)")
    return (
        n1 == "냉각핀과열" and n2 == "과전압" and ie5.norm_key("") == "",
        f"'냉각 핀 과열'→{n1!r} · '과전압 (Ovt)'→{n2!r}",
    )


@guard
def probe_norm_b(fx: dict) -> tuple[bool, str]:
    """정규화 ⓑ — `인버터` 접두어 제거.

    ⚠ **실측 정정**: 이 데이터셋에서 ⓑ 를 차단해도 매칭 **건수는 5로 그대로**다 —
       본문에 `인버터 과부하(IOL)` 라는 **접두어 포함 표기가 따로 존재**해 ⓐ 경로로도 붙기
       때문이다. 즉 ⓑ 는 이 표본에서 **중복 경로**다. 그래서 두 축으로 나눠 검사한다:
       ① 합성 입력으로 ⓑ 경로를 **고립**시켜 실제로 매칭을 만드는지 (차단하면 떨어진다)
       ② 실 픽스처에서는 IOL 의 `join_variant` 가 ⓑ 산물(`과부하`)임을 관측으로 고정
    """
    rows, _u, _s = rebuild_rows(fx)
    occ = fx["code_name_pairs"]
    s1, s2 = ie5.strip_inverter("인버터과부하"), ie5.strip_inverter("과부하")
    iso_rows = [synth_row("인버터 과부하")]
    iso_occ = [{"code": "ZZa", "name_raw": "과부하", "page": 1}]
    iso_on = {m["canonical_code"] for m in ie5.join(iso_rows, iso_occ)[0]}
    orig = ie5.strip_inverter
    try:
        ie5.strip_inverter = lambda s: s  # ⓑ 경로 차단
        iso_off = {m["canonical_code"] for m in ie5.join(iso_rows, iso_occ)[0]}
        var_off = {m["canonical_code"]: m["join_variant"] for m in ie5.join(rows, occ)[0]}
    finally:
        ie5.strip_inverter = orig
    var_on = {m["canonical_code"]: m["join_variant"] for m in ie5.join(rows, occ)[0]}
    return (
        s1 == "과부하"
        and s2 == "과부하"
        and iso_on == {"ZZA"}
        and iso_off == set()
        and var_on.get("IOL") == "과부하"
        and var_off.get("IOL") == "인버터 과부하",
        f"'인버터과부하'→{s1!r} · 고립 입력 매칭 ON {sorted(iso_on)} / OFF {sorted(iso_off)} · "
        f"실 픽스처 IOL variant ON {var_on.get('IOL')!r} → OFF {var_off.get('IOL')!r} "
        f"(건수는 5로 불변 — 본문에 접두어 포함 표기가 따로 있어 ⓐ 로도 붙는다)",
    )


@guard
def probe_name_variants() -> tuple[bool, str]:
    v1 = ie5.name_variants("동시 과전류")
    v2 = ie5.name_variants("전압")
    return (
        "과전류" in v1 and "동시 과전류" in v1 and len(v1) <= ie5.MAX_NAME_TOKENS and v2 == [],
        f"'동시 과전류'→{v1} · '전압'(2자)→{v2} · MIN_NAME_LEN={ie5.MIN_NAME_LEN} "
        f"MAX_NAME_TOKENS={ie5.MAX_NAME_TOKENS}",
    )


# ──────────────────────────────────────────────── C. 후보 파일 계약
def seed_draft_markers() -> list[str]:
    """`data/seed.py` 의 `error_codes_gate()` 가 초안으로 판정하는 문자열 리터럴.

    후보 파일 `_status` 어휘를 여기에 **묶어 둔다** — 게이트 선례가 한국어인데 후보 파일만
    `"pending"` 이면, P11 이 같은 게이트를 재사용하는 순간 그 값이 **승인으로 읽힌다**.

    ⚠ 함수 안 문자열을 통째로 긁으면 `''`·`'utf-8'` 까지 마커로 잡히고, **`'' in status` 는
      언제나 참**이라 판정이 무의미해진다. 그래서 `<리터럴> in status` **비교식의 좌변만**
      뽑는다 — 게이트가 판정에 실제로 쓰는 어휘 그것이다.
    """
    if not SEED_PATH.exists():
        return []
    for node in ast.walk(ast.parse(SEED_PATH.read_text(encoding="utf-8"))):
        if not (isinstance(node, ast.FunctionDef) and node.name == "error_codes_gate"):
            continue
        out: set[str] = set()
        for cmp_node in ast.walk(node):
            if not isinstance(cmp_node, ast.Compare) or len(cmp_node.ops) != 1:
                continue
            right = cmp_node.comparators[0]
            hits_status = isinstance(right, ast.Name) and right.id == "status"
            left = cmp_node.left
            if (
                isinstance(cmp_node.ops[0], ast.In)
                and hits_status
                and isinstance(left, ast.Constant)
                and isinstance(left.value, str)
                and left.value
            ):
                out.add(left.value)
        return sorted(out)
    return []


@guard
def probe_status(doc: dict) -> tuple[bool, str]:
    status = str(doc.get("_status", ""))
    markers = seed_draft_markers()
    hits = [m for m in markers if m in status]
    return (
        bool(markers) and bool(hits) and "pending" not in status,
        f"_status={status!r} · seed.error_codes_gate() 마커 {markers} · 적중 {hits} "
        f"(마커 0개면 스캐너가 눈먼 것이라 판정 불가)",
    )


@guard
def probe_unmatched_buckets(doc: dict) -> tuple[bool, str]:
    un = doc["_unmatched"]
    need = ("codes", "names", "codes_excluded_by_shape", "codes_without_name")
    empty = [k for k in need if not un.get(k)]
    return (
        not empty and len(un) == len(need),
        f"버킷 {len(un)}종 "
        + " · ".join(f"{k}={len(un.get(k, []))}" for k in need)
        + f" · 비어 있는 버킷 {empty or '없음'} (조인 실패도 형상 제외도 숨기지 않는다)",
    )


@guard
def probe_stats(doc: dict) -> tuple[bool, str]:
    st, un, codes = doc["_stats"], doc["_unmatched"], doc["codes"]
    rows_covered = len({c["table_row"] for c in codes})
    checks = {
        "matched=len(codes)": st["matched"] == len(codes),
        "matched_rows": st["matched_rows"] == rows_covered,
        "uc": st["unmatched_codes"] == len(un["codes"]),
        "un": st["unmatched_names"] == len(un["names"]),
        "shape": st["codes_excluded_by_shape"] == len(un["codes_excluded_by_shape"]),
        "noname": st["codes_without_name"] == len(un["codes_without_name"]),
        # 🔴 올바른 항등식 — `matched` 는 (코드,행) 쌍 수라 행 수와 다를 수 있다.
        #    행 축으로 세야 "버려진 행 0" 을 주장할 수 있다.
        "행 폐포": st["table_rows"] == st["matched_rows"] + st["unmatched_names"],
        "접기 단조": st["codes_found"] <= st["codes_found_display_variants"],
    }
    bad = [k for k, v in checks.items() if not v]
    return (
        not bad and bool(codes),
        f"rows {st['table_rows']} = matched_rows {st['matched_rows']} + un {st['unmatched_names']} · "
        f"matched 쌍 {st['matched']} · canonical {st['codes_found']}종/원표기 "
        f"{st['codes_found_display_variants']}종 · 위반 {bad or '없음'}",
    )


@guard
def probe_manual_page(doc: dict) -> tuple[bool, str]:
    codes, un = doc["codes"], doc["_unmatched"]
    bad_pages = [c["code"] for c in codes if c.get("manual_page") not in PAGES]
    bad_un_pages = [u["name"] for u in un["names"] if u.get("manual_page") not in PAGES]
    return (
        bool(codes) and not bad_pages and not bad_un_pages,
        f"codes {len(codes)}건 · 페이지 {sorted({c['manual_page'] for c in codes})} · "
        f"범위 밖 {bad_pages + bad_un_pages} · _source.pages={doc['_source']['pages']} · "
        f"citation_basis={doc['_source']['citation_basis']!r}",
    )


@guard
def probe_code_keys(doc: dict) -> tuple[bool, str]:
    codes = doc["codes"]
    need = {
        "code",
        "display_code",
        "display_variants",
        "canonical_code",
        "table_row",
        "name_ko",
        "cause",
        "action",
        "manual_page",
    }
    missing = [c.get("code") for c in codes if not need <= set(c)]
    model_leak = [c.get("code") for c in codes if "model" in c] + (
        ["_source"] if "model" in doc["_source"] else []
    )
    return (
        bool(codes) and not missing and not model_leak,
        f"검사 {len(codes)}건 · 키 누락 {missing} · model 필드 {model_leak} (§0-5 — enum 확장은 P11)",
    )


@guard
def probe_same_run(doc: dict, fx: dict) -> tuple[bool, str]:
    st, un, codes = doc["_stats"], doc["_unmatched"], doc["codes"]
    exp = fx["expected"]
    same = {
        "sha256": doc["_source"]["sha256"] == fx["_source"]["sha256"],
        "stats": st == exp["stats"],
        "codes": [c["code"] for c in codes] == [m["code"] for m in exp["matched"]],
        "uc": [u["canonical_code"] for u in un["codes"]] == list(exp["unmatched_codes"]),
        "shape": [u["canonical_code"] for u in un["codes_excluded_by_shape"]]
        == list(exp["codes_excluded_by_shape"]),
        "noname": [u["canonical_code"] for u in un["codes_without_name"]]
        == list(exp["codes_without_name"]),
    }
    bad = [k for k, v in same.items() if not v]
    return not bad, f"동일 실행 대조 {same} · 불일치 {bad or '없음'}"


@guard
def probe_manifest(doc: dict) -> tuple[bool, str]:
    return (
        doc["_source"].get("manifest_registered") is False,
        f"manifest_registered={doc['_source'].get('manifest_registered')} · "
        f"manual_id={doc['_source']['manual_id']!r} (등재는 P11 소관)",
    )


@guard
def probe_recall(doc: dict) -> tuple[bool, str]:
    """§0-2 확정 12종이 **전건** 산출물 어딘가에 등장하는가 (리콜 축).

    `codes` ∪ `_unmatched` 3버킷 = 파이프라인이 본 것 전부. 하나라도 여기 없으면 그 코드는
    **아무 흔적 없이 사라진 것**이고, 검수자는 `codes_found` 를 보고 틀린 결론을 낸다
    (블로커 ② 의 실제 사고: `CoL`·`nOn` 이 후보·픽스처 양쪽에서 0회였다).
    """
    un = doc["_unmatched"]
    buckets = {
        "codes": {c["canonical_code"] for c in doc["codes"]},
        "_unmatched.codes": {u["canonical_code"] for u in un["codes"]},
        "codes_excluded_by_shape": {u["canonical_code"] for u in un["codes_excluded_by_shape"]},
        "codes_without_name": {u["canonical_code"] for u in un["codes_without_name"]},
    }
    everywhere: set[str] = set().union(*buckets.values())
    want = {ie5.canon(c) for c in ie5.CONFIRMED_CODES}
    missing = sorted(want - everywhere)
    where = {c: [k for k, v in buckets.items() if c in v] for c in sorted(want)}
    # 이름을 지어내지 않았는가 — `codes_without_name` 항목에 명칭 필드가 없어야 한다
    invented = [u for u in un["codes_without_name"] if {"name", "name_ko"} & set(u)]
    return (
        not missing and not invented and len(want) == 12 and len(everywhere) > 0,
        f"확정 {len(want)}종 중 미등장 {missing or '없음'} · 산출물 canonical 총 {len(everywhere)}종 · "
        f"이름 지어냄 {len(invented)}건 · 소재 {where}",
    )


@guard
def probe_fold(doc: dict, fx: dict) -> tuple[bool, str]:
    """대문자 canonical 접기(D25) + 원표기 보존.

    부재 축(중복 canonical 없음)에 **양성 앵커**를 함께 건다 — 실제로 접힌 항목(변형 2개 이상)이
    최소 1건 있어야 한다. 없으면 접기 코드가 통째로 죽어도 조용히 통과한다.
    """
    un = doc["_unmatched"]
    entries = doc["codes"] + un["codes"] + un["codes_excluded_by_shape"]
    canons = [e["canonical_code"] for e in entries]
    dup = sorted({c for c in canons if canons.count(c) > 1})
    bad_case = [e["canonical_code"] for e in entries if e["canonical_code"] != e["code"].upper()]
    lost = [e["code"] for e in entries if e["code"] not in e["display_variants"]]
    folded = [e for e in entries if len(e["display_variants"]) > 1]
    raw = len({o["code"] for o in fx["code_name_pairs"]})
    return (
        not dup and not bad_case and not lost and len(folded) > 0,
        f"항목 {len(entries)}종 · canonical 중복 {dup or '없음'} · 대문자 위반 {bad_case or '없음'} · "
        f"원표기 유실 {lost or '없음'} · **접힌 항목 {len(folded)}건**(앵커) "
        f"{[(e['canonical_code'], e['display_variants']) for e in folded[:4]]} · "
        f"원표기 {raw}종 → canonical {doc['_stats']['codes_found']}종",
    )


@guard
def probe_shape_bucket(doc: dict, fx: dict) -> tuple[bool, str]:
    """제3 버킷(형상 제외)이 **차집합**으로 성립하는가.

    이 버킷이 없으면 `BODY_CODE_RE` 축소가 잃은 것을 산출물이 말하지 않는다 — 정본 65종 중
    16종이 좁힌 형상 밖이라는 실측이 그 위험의 근거다.
    """
    un = doc["_unmatched"]
    bucket = un["codes_excluded_by_shape"]
    in_pipeline = {c["canonical_code"] for c in doc["codes"]} | {
        u["canonical_code"] for u in un["codes"]
    }
    bucket_canons = {u["canonical_code"] for u in bucket}
    overlap = sorted(bucket_canons & in_pipeline)
    narrow_leak = sorted(c for c in bucket_canons if NARROW.fullmatch(c))
    shape_bad = sorted(c for c in bucket_canons if not SPEC.fullmatch(c))
    evidence = [u for u in bucket if not (u["pages"] and u["name_candidates"])]
    # 픽스처 원본 발생과의 산술 — 접기 전 표기 종류 수가 버킷 canonical 수 이상이어야 한다
    raw_codes = {o["code"] for o in fx["shape_excluded_pairs"]}
    return (
        bool(bucket)
        and not overlap
        and not narrow_leak
        and not shape_bad
        and not evidence
        and len(raw_codes) >= len(bucket_canons),
        f"형상 제외 {len(bucket_canons)}종(원표기 {len(raw_codes)}종) · 파이프라인과 겹침 "
        f"{overlap or '없음'} · 좁은 형상 누수 {narrow_leak or '없음'} · 스펙 형상 밖 "
        f"{shape_bad or '없음'} · 근거(페이지+주변텍스트) 누락 {len(evidence)}건 · "
        f"예: {[u['canonical_code'] for u in bucket[:6]]}",
    )


# ──────────────────────────────────────────────── D. 소스 정적 스캔 (부재 주장 + 앵커)
SRC = SRC_PATH.read_text(encoding="utf-8") if SRC_PATH.exists() else ""
TREE = ast.parse(SRC) if SRC else ast.parse("")

WRITE_ATTRS = {"write_text", "write_bytes", "mkdir", "touch", "unlink", "rename", "replace"}
READ_ATTRS = {"read_text", "read_bytes", "exists", "is_file", "stat"}


def _seg(src: str, node: ast.AST) -> str:
    return (ast.get_source_segment(src, node) or "").strip()


def io_calls(
    src: str, tree: ast.AST, attrs: set[str], names: set[str]
) -> list[tuple[str, str, int]]:
    """(호출명, 대상 표현식 소스, 줄번호) — 대상은 `X.write_text()` 의 `X`, `f(Y)` 의 `Y`."""
    out: list[tuple[str, str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Attribute) and fn.attr in attrs:
            out.append((fn.attr, _seg(src, fn.value), node.lineno))
        elif isinstance(fn, ast.Name) and fn.id in names:
            arg = _seg(src, node.args[0]) if node.args else ""
            out.append((fn.id, arg, node.lineno))
        elif isinstance(fn, ast.Name) and fn.id == "open":
            mode = (
                node.args[1].value
                if len(node.args) > 1 and isinstance(node.args[1], ast.Constant)
                else "r"
            )
            if isinstance(mode, str) and any(c in mode for c in "wa+"):
                out.append(("open", _seg(src, node.args[0]), node.lineno))
    return out


def func_attr_calls(src: str) -> dict[str, set[str]]:
    """함수명 → 그 안에서 호출한 속성명 집합. (`page.extract_text()` → {'extract_text', …})"""
    out: dict[str, set[str]] = {}
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef):
            calls = {
                n.func.attr
                for n in ast.walk(node)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            }
            out[node.name] = calls
    return out


TABLE_FUNCS = (
    "text_extent",
    "vertical_clusters",
    "column_bounds",
    "horizontal_bounds",
    "_lines_text",
    "band_name",
    "parse_table_page",
    "parse_tables",
)


@guard
def probe_no_canonical_write() -> tuple[bool, str]:
    writes = io_calls(SRC, TREE, WRITE_ATTRS, {"write_json"})
    reads = io_calls(SRC, TREE, READ_ATTRS, {"sha256_of"})
    w_canon = [w for w in writes if "CANONICAL" in w[1] or "error_codes.json" in w[1]]
    r_canon = [r for r in reads if "CANONICAL" in r[1]]
    canon_codes = ie5.known_canonical_codes()  # 읽기 경로를 실제로 태운다
    indirect = [f for f, calls in func_attr_calls(SRC).items() if "write_text" in calls]
    return (
        not w_canon and len(r_canon) > 0 and len(canon_codes) > 0 and indirect == ["write_json"],
        f"쓰기 호출 {len(writes)}건 대상={sorted({w[1] for w in writes})} · CANONICAL 향함 "
        f"{len(w_canon)}건 · CANONICAL 읽기 {len(r_canon)}건 · 정본 실측 {len(canon_codes)}종 · "
        f"write_text 보유 함수 {indirect}",
    )


@guard
def probe_no_raw_write() -> tuple[bool, str]:
    writes = io_calls(SRC, TREE, WRITE_ATTRS, {"write_json"})
    w_raw = [w for w in writes if re.search(r"\bRAW\b|data/raw|manifest", w[1])]
    raw_refs = [
        n.lineno for n in ast.walk(TREE) if isinstance(n, ast.Name) and n.id in {"RAW", "PDF_NAME"}
    ]
    out_dirs = sorted(
        {str(p.parent.relative_to(ROOT)) for p in (ie5.CANDIDATE, ie5.GEOMETRY_FIXTURE)}
    )
    return (
        not w_raw
        and len(raw_refs) > 0
        and len(writes) >= 3
        and all("raw" not in d for d in out_dirs),
        f"쓰기 호출 {len(writes)}건 · RAW 향함 {len(w_raw)}건 · RAW/PDF_NAME 참조 "
        f"{len(raw_refs)}회(줄 {raw_refs}) · 산출 디렉터리 {out_dirs} · RAW 실재={ie5.RAW.exists()}",
    )


@guard
def probe_no_text_fallback() -> tuple[bool, str]:
    fcalls = func_attr_calls(SRC)
    scanned = [f for f in TABLE_FUNCS if f in fcalls]
    bleeders = [f for f in scanned if "extract_text" in fcalls[f]]
    tbl_anchor = [f for f in scanned if "extract_tables" in fcalls[f]]
    strings = {
        n.value for n in ast.walk(TREE) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }
    explicit = sorted(
        s
        for s in {"explicit", "explicit_vertical_lines", "explicit_horizontal_lines"}
        if s in strings
    )
    positive = "extract_text" in fcalls.get("body_code_names", set())  # 양성 대조: 스캐너 생존
    return (
        not bleeders
        and len(scanned) == len(TABLE_FUNCS)
        and len(tbl_anchor) > 0
        and len(explicit) == 3
        and positive,
        f"표 함수 {len(scanned)}/{len(TABLE_FUNCS)}개 스캔 · extract_text 보유 {bleeders} · "
        f"extract_tables 앵커 {tbl_anchor} · explicit 문자열 {explicit} · "
        f"양성대조(body_code_names 의 extract_text 탐지)={positive}",
    )


# ──────────────────────────────────────────────── 본문
def run_fixture_checks(fx: dict) -> None:
    check("A① 픽스처 최상위 키", *probe_top_keys(fx))
    check("A② 대상 페이지·페이지 키", *probe_pages(fx))
    check("A③ 열 경계 4개 = 3열", *probe_col_count(fx))
    check("A④ 열 경계 단조 증가", *probe_monotonic(fx))
    check("A⑤ 경계가 페이지마다 다르다", *probe_not_hardcoded(fx))
    check("A⑥ 바깥 경계 글자범위 클램프", *probe_clamp(fx))
    check("A⑦ 행 경계 ↔ 그리드 행수", *probe_row_bounds(fx))
    check("A⑧ 명칭 열 경계 ⊃ 본문 경계", *probe_name_bounds(fx))
    check("A⑨ 머리행 3열", *probe_header(fx))
    check("A⑩ 모든 행이 3셀", *probe_row_width(fx))
    check("A⑪ 원인·대책 열 혼입 없음", *probe_no_column_bleed(fx))
    check("A⑫ 불릿 분해", *probe_bullets(fx))
    check("A⑬ 밴드 산술 = table_rows", *probe_band_arith(fx))
    check("A⑭ 열 경계 재유도 (PDF-free 실행)", *probe_recolumn(fx))
    check("A⑮ 열 경계 실패 경로 = 상태 반환 (D9)", *probe_recolumn_d9(fx))


def run_join_checks(fx: dict, doc: dict) -> None:
    check("B① 괄호 표기 형상 · 두 버킷 서로소", *probe_body_shape(fx))
    check("B② 밴드 재구성 (병합 밴드 분할)", *probe_rebuild(fx))
    check("B③ 조인 재현 — 매칭", *probe_join_matched(fx))
    check("B④ 조인 재현 — 미매칭 양방향 · 행 폐포", *probe_join_unmatched(fx))
    check("B⑤ 정규화 ⓐ 공백·괄호 제거", *probe_norm_a())
    check("B⑥ 정규화 ⓑ 인버터 접두어 (고립 + 관측)", *probe_norm_b(fx))
    check("B⑦ 명칭 후보 = 접미 어절 · 최소 길이", *probe_name_variants())
    check("B⑧ cause·action ↔ 그리드 셀 (병합 복제 포함)", *probe_cause_action(fx, doc))


def run_candidate_checks(fx: dict, doc: dict) -> None:
    check("C① _status 초안 마커 (D33 · seed 게이트 어휘)", *probe_status(doc))
    check("C② _unmatched 3버킷 실재·비공백", *probe_unmatched_buckets(doc))
    check("C③ _stats 자기무결성 (행 폐포)", *probe_stats(doc))
    check("C④ manual_page = 물리 페이지 (D26)", *probe_manual_page(doc))
    check("C⑤ codes 필수 키 · model enum 미확장", *probe_code_keys(doc))
    check("C⑥ 후보 ↔ 픽스처 동일 실행 산출물", *probe_same_run(doc, fx))
    check("C⑦ manifest 미등재 표기 (§7-1)", *probe_manifest(doc))
    check("C⑧ 리콜 — 확정 12종 전건 등장", *probe_recall(doc))
    check("C⑨ 형상 제외 버킷 = 차집합 (블로커 ①)", *probe_shape_bucket(doc, fx))
    check("C⑩ canonical 접기 + 원표기 보존 (D25)", *probe_fold(doc, fx))


def run_absence_checks() -> None:
    check("D① 정본 error_codes.json 미기록 (D99)", *probe_no_canonical_write())
    check("D② data/raw/ 미기록 (절대규칙 5)", *probe_no_raw_write())
    check("D③ 표 파싱 경로에 extract_text 폴백 없음", *probe_no_text_fallback())


@guard
def _reextract(pdf_path: Path) -> tuple[bool, str]:
    """E 축 재추출 — guard 로 감싸 예외를 FAIL 로 환원한다."""
    import pdfplumber  # noqa: PLC0415 — PDF 가 있을 때만 필요

    geos: dict[int, dict] = {}
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        for pno in PAGES:
            _rows, geo, _warn = ie5.parse_table_page(pdf.pages[pno - 1], pno)
            geos[pno] = geo
    return True, json.dumps({"total": total, "geos": geos}, ensure_ascii=False)


def run_pdf_axis(fx: dict) -> int:
    """PDF 가 있을 때만 도는 축. 없으면 SKIP 3건 — 조용히 넘어가지 않는다."""
    pdf_path = Path(os.environ.get("MAINTQ_IE5_PDF") or (ie5.RAW / ie5.PDF_NAME))
    titles = (
        "E① PDF sha256 ↔ 픽스처",
        "E② 재추출 열 경계 == 픽스처",
        "E③ 재추출 그리드 텍스트 == 픽스처",
    )
    if not pdf_path.exists():
        for t in titles:
            skip(t, f"PDF 없음 ({pdf_path.name}) — .gitignore data/raw/* · 픽스처 축은 전부 실행됨")
        return len(titles)

    ok, payload = _reextract(pdf_path)
    if not ok:
        for t in titles:
            check(t, False, f"재추출 실패 — {payload}")
        return 0

    blob = json.loads(payload)
    total = blob["total"]
    geos = {int(k): v for k, v in blob["geos"].items()}
    sha = ie5.sha256_of(pdf_path)

    check(
        titles[0],
        sha == fx["_source"]["sha256"] and total == fx["_source"]["total_pages"],
        f"sha256 {sha[:12]}… (픽스처 {fx['_source']['sha256'][:12]}…) · {total}p "
        f"(픽스처 {fx['_source']['total_pages']}p) · 경로 {pdf_path.name}",
    )
    fx_by_page = {p["page"]: p for p in fx["pages"]}
    cb_diff = {
        pno: (geos[pno].get("column_bounds"), fx_by_page[pno]["column_bounds"])
        for pno in PAGES
        if geos[pno].get("column_bounds") != fx_by_page[pno]["column_bounds"]
    }
    check(
        titles[1],
        not cb_diff and all(len(geos[p].get("column_bounds") or []) == 4 for p in PAGES),
        f"재추출 {[geos[p].get('column_bounds') for p in PAGES]} · 불일치 {cb_diff or '없음'}",
    )
    row_diff = {
        pno: (len(geos[pno].get("rows") or []), len(fx_by_page[pno]["rows"]))
        for pno in PAGES
        if geos[pno].get("rows") != fx_by_page[pno]["rows"]
    }
    check(
        titles[2],
        not row_diff and all(geos[p].get("rows") for p in PAGES),
        f"재추출 행수 {[len(geos[p].get('rows') or []) for p in PAGES]} · 셀 텍스트 불일치 "
        f"{row_diff or '없음'}",
    )
    return 0


def run_meta_checks(fx: dict, doc: dict) -> None:
    """오라클 — 알려진 불량 입력에서 A·B·C 판정식이 **발화**하는지. (P30 방식)"""

    def broke(probe, mutate, *extra) -> tuple[bool, str]:
        m = copy.deepcopy(fx if not extra else extra[0])
        mutate(m)
        ok, detail = probe(m) if not extra else probe(m)
        return (not ok), detail

    def m_empty(m):
        m.clear()

    fired, d = broke(probe_top_keys, m_empty)
    check(
        "F① 뮤턴트: 빈 픽스처 → A① 발화",
        fired,
        f"판정={'FAIL(기대)' if fired else 'PASS(결함)'} · {d}",
    )

    def m_no_pages(m):
        m["pages"] = []

    fired, d = broke(probe_pages, m_no_pages)
    check(
        "F② 뮤턴트: pages 제거 → A② 발화",
        fired,
        f"판정={'FAIL(기대)' if fired else 'PASS(결함)'} · {d}",
    )

    def m_three_cols(m):
        m["pages"][0]["column_bounds"] = m["pages"][0]["column_bounds"][:3]

    fired, d = broke(probe_col_count, m_three_cols)
    check(
        "F③ 뮤턴트: 열 경계 3개 → A③ 발화",
        fired,
        f"판정={'FAIL(기대)' if fired else 'PASS(결함)'} · {d}",
    )

    def m_unsorted(m):
        cb = m["pages"][1]["column_bounds"]
        cb[1], cb[2] = cb[2], cb[1]

    fired, d = broke(probe_monotonic, m_unsorted)
    check(
        "F④ 뮤턴트: 경계 뒤섞음 → A④ 발화",
        fired,
        f"판정={'FAIL(기대)' if fired else 'PASS(결함)'} · {d}",
    )

    def m_header(m):
        m["pages"][0]["rows"][0] = ["고장 대책", "", ""]

    fired, d = broke(probe_header, m_header)
    check(
        "F⑤ 뮤턴트: 머리행 훼손 → A⑨ 발화",
        fired,
        f"판정={'FAIL(기대)' if fired else 'PASS(결함)'} · {d}",
    )

    def m_bleed(m):
        row = m["pages"][0]["rows"][4]
        row[1] = row[1] + " 이물질이 있는지 확인합니다."  # §0-3 의 열 혼입 재현

    fired, d = broke(probe_no_column_bleed, m_bleed)
    check(
        "F⑥ 뮤턴트: 대책 문장 혼입 → A⑪ 발화",
        fired,
        f"판정={'FAIL(기대)' if fired else 'PASS(결함)'} · {d}",
    )

    def m_band(m):
        m["expected"]["stats"]["table_rows"] = 99

    fired, d = broke(probe_band_arith, m_band)
    check(
        "F⑦ 뮤턴트: table_rows 위조 → A⑬ 발화",
        fired,
        f"판정={'FAIL(기대)' if fired else 'PASS(결함)'} · {d}",
    )

    # 정규화 ⓐ(공백 제거)가 실제로 매칭을 만드는가 — **고립 입력**으로 본다.
    # ⚠ 실 픽스처로는 이 뮤턴트가 발화하지 않는다: 본문에 `인버터 냉각핀 과열`(붙임)·
    #   `인버터 냉각 핀 과열`(띄움) 두 표기가 **모두** 있어 정규화 없이도 붙는다(실측).
    #   그 사실을 숨기지 않고 detail 에 함께 찍는다 — 표본이 우연히 관대했던 것이지
    #   규칙이 불필요하다는 뜻이 아니다.
    @guard
    def norm_a_isolation(_fx: dict) -> tuple[bool, str]:
        iso_rows = [synth_row("냉각 핀 과열")]  # 표 표기(띄움)
        iso_occ = [
            {"code": "ZZb", "name_raw": "인버터 냉각핀 과열", "page": 125}
        ]  # 본문 표기(붙임)
        on = {m["canonical_code"] for m in ie5.join(iso_rows, iso_occ)[0]}
        orig = ie5.norm_key
        try:
            ie5.norm_key = lambda s: s or ""  # 공백 제거 차단
            off = {m["canonical_code"] for m in ie5.join(iso_rows, iso_occ)[0]}
            real_off = ie5.join(rebuild_rows(_fx)[0], _fx["code_name_pairs"])[0]
        finally:
            ie5.norm_key = orig
        return (
            on == {"ZZB"} and off == set(),
            f"고립 입력('냉각 핀 과열' ↔ '인버터 냉각핀 과열') ON {sorted(on)} / OFF {sorted(off)} · "
            f"실 픽스처에서는 OFF 여도 {len(real_off)}건 유지(본문에 두 표기가 모두 존재 — "
            f"이 표본에서 ⓐ 는 중복 경로다)",
        )

    check("F⑧ 뮤턴트: 공백 정규화 차단 → 고립 매칭 붕괴", *norm_a_isolation(fx))

    # 스캐너 오라클 — 표 함수 안의 extract_text 를 정말 잡는가 (D③ 판정식의 눈)
    @guard
    def scanner_oracle() -> tuple[bool, str]:
        fake = "def parse_table_page(page, pno):\n    return page.extract_text()\n"
        seen = func_attr_calls(fake)
        caught = "extract_text" in seen.get("parse_table_page", set())
        fake2 = "def parse_table_page(page, pno):\n    return page.extract_tables({})\n"
        clean = "extract_text" not in func_attr_calls(fake2).get("parse_table_page", set())
        return (
            caught and clean,
            f"합성 소스(폴백 있음) 탐지={caught} · 합성 소스(폴백 없음) 오탐={not clean} · "
            f"스캔 함수 {sorted(seen)}",
        )

    check("F⑨ 오라클: extract_text 스캐너 생존", *scanner_oracle())

    # 🔴 블로커 ② 재발 오라클 — 확정 코드를 산출물에서 지우면 C⑧ 이 발화하는가.
    #    (실제 사고 형태가 "CoL·nOn 이 어느 버킷에도 없다" 였다)
    mut_doc = copy.deepcopy(doc)
    mut_doc["_unmatched"]["codes_without_name"] = []
    ok8, d8 = probe_recall(mut_doc)
    check(
        "F⑩ 뮤턴트: codes_without_name 제거 → C⑧ 발화",
        not ok8,
        f"판정={'FAIL(기대)' if not ok8 else 'PASS(결함)'} · {d8}",
    )

    # 🔴 추출기 유도 로직 오라클 — 세로 edge 를 옮기면 A⑭ 가 발화하는가.
    #    F 뮤턴트가 픽스처만 흔들면 probe 만 검증되고 **추출기는 검증되지 않는다.**
    #    여기서는 재유도 입력(v_edges)을 흔들어 `column_bounds()` 실행 경로를 태운다.
    def m_shift(m):
        p = m["pages"][0]
        target = p["column_bounds"][1]
        for e in p["v_edges"]:
            if abs(e[0] - target) <= ie5.X_TOL:
                e[0] += 50.0

    fired, d = broke(probe_recolumn, m_shift)
    check(
        "F⑪ 뮤턴트: v_edge 이동 → A⑭ 발화 (추출기 실행)",
        fired,
        f"판정={'FAIL(기대)' if fired else 'PASS(결함)'} · {d}",
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("IE5 추출 경로 계약 — 픽스처 기반 (PDF 비의존, sprint-14 §2 MQ-1405)\n")
    if not FIXTURE.exists():
        raise SystemExit(f"[실패] 픽스처 없음: {FIXTURE} — data/extract_ie5_codes.py 를 먼저 실행")
    if not CANDIDATE.exists():
        raise SystemExit(f"[실패] 후보 파일 없음: {CANDIDATE}")

    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    doc = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    run_fixture_checks(fx)
    run_join_checks(fx, doc)
    run_candidate_checks(fx, doc)
    run_absence_checks()
    n_skipped = run_pdf_axis(fx)
    run_meta_checks(fx, doc)

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 60))
    for name, status, detail in results:
        print(f"  {status:<4}  {name:<{width}}  {detail}")
    print("─" * (width + 60))

    failed = [n for n, s, _ in results if s == "FAIL"]
    passed = [n for n, s, _ in results if s == "PASS"]
    skipped = [n for n, s, _ in results if s == "SKIP"]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    assert n_skipped == len(skipped), "SKIP 집계 불일치"
    print(
        f"\n통과 (전체 {len(results)}건 = PASS {len(passed)} · SKIPPED {len(skipped)}) — "
        f"D9·D25·D26·D33·D99 · sprint-14 §0-3(괘선 없는 표) 준수."
    )
    if skipped:
        print(
            f"  ⚠ SKIPPED {len(skipped)}건: {', '.join(skipped)}\n"
            "    PDF 는 git 에 없다(.gitignore data/raw/*). 대조하려면 "
            "MAINTQ_IE5_PDF=<경로> 로 지정하거나 data/raw/ 에 두고 재실행한다."
        )
    else:
        print("  · E 축(PDF 대조) 실행됨 — SKIPPED 0건")


if __name__ == "__main__":
    main()
