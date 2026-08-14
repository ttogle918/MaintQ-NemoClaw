# -*- coding: utf-8 -*-
"""추출 품질 triage — **계측기** (MQ-902, Sprint 9 Stage 1).

목적 : MQ-905·907 이 파서를 고치기 **전에** `error_codes.json` 의 결측 상태를 고정한다.
       파서를 먼저 바꾸면 좋아졌는지 잴 방법이 없다.
입력 : data/extracted/error_codes.json (**읽기 전용**) + data/raw/*.pdf + manifest.json
출력 : data/analysis/extract_triage.md · data/extracted/extract_triage.json

경계 (지키는 것)
  - 정본 `error_codes.json` 을 **쓰지 않는다** (D99 격리). 읽은 파일의 sha256 을 스냅샷에 남긴다.
  - DB(`data/maintq.db`)를 열지 않는다.
  - 외부 호출 0 — `estimate_ocr_cost()` 는 **페이지 수 × 원** 산술만 한다.
  - 매뉴얼 해시 게이트는 `extract_error_codes.check_manifest()` 를 **재사용**한다 (D19).
  - 페이지는 전부 **PDF 물리 페이지** (D26). 인쇄 페이지 환산을 여기서 하지 않는다 (D32).

판정 태도 (CLAUDE.md 부재검사 규칙 · D65)
  "조치문이 없다" 는 **부재 주장**이라 *사실이 참* 인 경우와 *스캐너가 눈이 멀었다* 를 구분하지
  못한다. 그래서 페이지마다 **양성 축** `code_tokens_found` 를 함께 재고, 두 축의 실측값을
  리포트에 그대로 찍는다. 결론 문구("소스 없음")를 하드코딩하지 않는다 — FAIL 일 때도 그대로
  인쇄돼 표를 읽는 사람이 정반대로 이해한다.

  ⚠ 양성 축 자체도 눈이 멀 수 있다. 그래서 **두 번째 양성 축**(`codes_with_actions` = 그 페이지에서
  실제로 조치문 추출에 성공한 코드 수)을 함께 재고, `codes_with_actions > 0` 인데 코드 토큰이
  0 이면 `anchor_conflict` 로 표시한다. 그 페이지의 `SOURCE_MISSING` 라벨은 신뢰할 수 없다는 뜻이다.

기대값은 **assert 로 죽이지 않는다.** 계측기가 입력을 검열하면 계측기가 아니다 — 다르면 경고를
찍고 실측값을 그대로 리포트한다 (계획이 데이터를 이기지 않는다).
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
import sys
from dataclasses import asdict, dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import pdfplumber

ROOT = Path(__file__).resolve().parent  # data/
RAW = ROOT / "raw"
EXTRACTED = ROOT / "extracted"
ANALYSIS = ROOT / "analysis"

ERROR_CODES = EXTRACTED / "error_codes.json"  # ★ 읽기 전용
REPORT_MD = ANALYSIS / "extract_triage.md"
REPORT_JSON = EXTRACTED / "extract_triage.json"

SIGNALS: Final[tuple[str, ...]] = ("field_missing", "length_outlier", "table_collapse")
LABELS: Final[tuple[str, ...]] = (
    "SOURCE_MISSING",
    "CELL_SPLIT",
    "RE_OCR_CANDIDATE",
    "OK",
    # ★ "재 보지 못했다" 는 "없다" 와 다르다. 스캔 불가를 SOURCE_MISSING 으로 접으면
    #   재지 못한 축을 결론으로 바꾸는 것이다 (D65 — 모르는 것을 0 으로 메우지 않는다).
    "UNSCANNED",
)

# ── 신호는 2종만 쓴다 (+ field_missing 은 결측 그 자체다).
#    ⛔ 문자 깨짐 계열을 넣지 않는다 — P31 실측에서 코퍼스 전체 0건이었고 한국어 나열 구분자()를
#    고립 자모로 오탐한 전례가 있다. 없는 신호는 오탐만 늘린다.
Z_OUTLIER: Final[float] = 2.0  # 셀 길이 z-score 절대값 문턱
OUTLIER_RATE: Final[float] = 0.10  # 페이지 내 이상치 셀 비율이 이 값 이상이면 신호 발화
COLLAPSE_DROP: Final[float] = 0.35  # 행당 유효 셀 수가 매뉴얼 평균 대비 이만큼 줄면 발화

# 코드 토큰 — 명세 그대로 대문자 canonical 을 1차 축으로 쓴다 (D25: 내부는 대문자).
# 보조로 키패드 원표기(S100 은 소문자 'oct')까지 세는 축을 따로 둔다. 라벨 판정은 1차 축만 쓴다.
CODE_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[A-Z0-9]{2,4}")
CODE_TOKEN_CI_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9]{2,4}")

# 브리핑 실측 (2026-08-14). ⛔ assert 아님 — 다르면 경고를 찍고 실측을 리포트한다.
EXPECTED: Final[dict[str, Any]] = {
    "by_model": {
        "S100": {"total": 41, "missing_actions": 26, "missing_causes": 0},
        "iG5A": {"total": 24, "missing_actions": 11, "missing_causes": 0},
    },
    "_unparsed": 0,
    "_pending_review": 0,
}

# 보충 소스 탐침 대상 — iG5A 트러블슈팅본 물리 페이지 (D26).
# 조치문이 이쪽에 실재하는지 **읽어서 확인**만 한다. 여기서 추출하지 않는다 (MQ-905 소관).
SUPPLEMENT_MANUAL_ID: Final[str] = "ig5a-troubleshooting"
SUPPLEMENT_PAGES: Final[tuple[int, ...]] = tuple(range(20, 30))


@dataclass(frozen=True)
class PageVerdict:
    manual_id: str  # 'ig5a-manual' | 'ig5a-troubleshooting' | 's100-manual'
    page: int  # PDF 물리 페이지 (D26)
    label: str  # LABELS
    codes_total: int
    codes_missing_actions: int
    code_tokens_found: int  # ★ 양성 축 — 이 페이지 텍스트에서 실제로 발견된 코드 토큰 수
    signals: dict[str, float] = field(default_factory=dict)
    note: str = ""
    # ── ★ 기계 판독용 축 2종 (MQ-902 / Stage 1 reviewer 권고 1·2).
    #    산문(note)에만 경고를 적으면 `label` 로 필터링하는 소비자(MQ-905)에게 통째로 증발한다.
    scanned: bool = True  # False = PDF 범위 밖이라 재지 못했다 (label 은 UNSCANNED)
    anchor_conflict: bool = False  # True = 양성 축 2개가 모순 → 이 행의 label 을 믿지 마라


# ──────────────────────────────────────────────── 입력 (읽기 전용)
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@lru_cache(maxsize=1)
def _error_codes() -> dict:
    """정본 스냅샷을 읽는다. **쓰지 않는다** (D99)."""
    if not ERROR_CODES.exists():
        sys.exit(
            f"[중단] {ERROR_CODES} 가 없습니다 — 추출이 아직 돌지 않았습니다.\n"
            "        먼저 `uv run python data/extract_error_codes.py` 를 실행하세요."
        )
    return json.loads(ERROR_CODES.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _manifest() -> dict:
    """D19 해시 게이트를 `extract_error_codes` 에서 그대로 재사용한다.

    같은 게이트를 두 벌로 두면 한쪽만 통과하는 실행이 생긴다.
    """
    sys.path.insert(0, str(ROOT.parent))
    from data.extract_error_codes import check_manifest  # noqa: PLC0415

    return check_manifest()


@lru_cache(maxsize=1)
def _primary_manual_by_model() -> dict[str, tuple[str, Path]]:
    """model → (manual_id, pdf 경로). `error_codes.manual_page` 는 primary 본 기준이다."""
    out: dict[str, tuple[str, Path]] = {}
    for m in _manifest()["manuals"]:
        if m.get("role") == "primary":
            out.setdefault(m["model"], (m["id"], RAW / m["file"]))
    return out


def _manual_entry(manual_id: str) -> dict | None:
    for m in _manifest()["manuals"]:
        if m["id"] == manual_id:
            return m
    return None


# ──────────────────────────────────────────────── 페이지 프로파일
def _page_profile(page) -> tuple[str, list[int], list[int]]:
    """(페이지 텍스트, 셀 텍스트 길이들, 행별 유효 셀 수)."""
    text = page.extract_text() or ""
    lengths: list[int] = []
    rows_valid: list[int] = []
    try:
        tables = page.extract_tables()
    except Exception:  # pdfplumber 내부 파싱 실패 — 계측기는 멈추지 않는다
        tables = []
    for tb in tables:
        for row in tb:
            vals = [(c or "").strip() for c in row]
            rows_valid.append(sum(1 for v in vals if v))
            lengths.extend(len(v) for v in vals if v)
    return text, lengths, rows_valid


def _count_code_tokens(
    text: str, canonical: set[str], keypad: set[str]
) -> tuple[int, int, list[str]]:
    """(1차 축: 대문자 canonical 토큰 수, 보조 축: 키패드 원표기 포함 토큰 수, 발견 토큰 목록)."""
    hits = [t for t in CODE_TOKEN_RE.findall(text) if t in canonical]
    loose = sum(1 for t in CODE_TOKEN_CI_RE.findall(text) if t.upper() in canonical | keypad)
    return len(hits), loose, sorted(set(hits))


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


# ──────────────────────────────────────────────── scan
def scan() -> list[PageVerdict]:
    """`error_codes.json` 이 인용한 모든 (매뉴얼, 물리 페이지)를 훑어 판정한다."""
    data = _error_codes()
    entries = data.get("entries", [])
    by_model = _primary_manual_by_model()

    # (manual_id, page) → 코드 집계
    buckets: dict[tuple[str, int], dict[str, list[str]]] = {}
    canon: dict[str, set[str]] = {}
    keypad: dict[str, set[str]] = {}
    for e in entries:
        model = e.get("model") or ""
        canon.setdefault(model, set()).add(str(e.get("code") or "").upper())
        dc = re.sub(r"[^A-Za-z0-9]", "", str(e.get("display_code") or "")).upper()
        if dc:
            keypad.setdefault(model, set()).add(dc)
        ref = by_model.get(model)
        if ref is None:
            continue
        page = e.get("manual_page")
        if not isinstance(page, int):
            continue  # 페이지를 모르는 항목은 페이지 판정에 넣지 않는다 (0 으로 메우지 않는다, D65)
        b = buckets.setdefault((ref[0], page), {"missing": [], "ok": []})
        b["missing" if not e.get("actions") else "ok"].append(str(e.get("code")))

    # 매뉴얼별로 PDF 를 한 번만 연다
    raw: dict[tuple[str, int], dict[str, Any]] = {}
    for model, (manual_id, pdf_path) in by_model.items():
        pages = sorted({p for (mid, p) in buckets if mid == manual_id})
        if not pages:
            continue
        with pdfplumber.open(pdf_path) as pdf:
            for pno in pages:
                if pno < 1 or pno > len(pdf.pages):
                    raw[(manual_id, pno)] = {"out_of_range": True}
                    continue
                text, lengths, rows_valid = _page_profile(pdf.pages[pno - 1])
                strict, loose, hits = _count_code_tokens(
                    text, canon.get(model, set()), keypad.get(model, set())
                )
                raw[(manual_id, pno)] = {
                    "lengths": lengths,
                    "rows_valid": rows_valid,
                    "strict": strict,
                    "loose": loose,
                    "hits": hits,
                    "out_of_range": False,
                }

    # 신호는 **같은 매뉴얼 안의 분포**를 기준으로 잰다 (매뉴얼마다 표 조판이 다르다)
    per_manual_cells: dict[str, list[int]] = {}
    per_manual_rows: dict[str, list[int]] = {}
    for (manual_id, _), r in raw.items():
        if r.get("out_of_range"):
            continue
        per_manual_cells.setdefault(manual_id, []).extend(r["lengths"])
        per_manual_rows.setdefault(manual_id, []).extend(r["rows_valid"])

    verdicts: list[PageVerdict] = []
    for (manual_id, pno), b in sorted(buckets.items()):
        r = raw.get((manual_id, pno), {"out_of_range": True})
        n_miss, n_ok = len(b["missing"]), len(b["ok"])
        n_tot = n_miss + n_ok

        if r.get("out_of_range"):
            verdicts.append(
                PageVerdict(
                    manual_id=manual_id,
                    page=pno,
                    label="UNSCANNED",
                    codes_total=n_tot,
                    codes_missing_actions=n_miss,
                    code_tokens_found=0,
                    signals={s: 0.0 for s in SIGNALS},
                    note=(
                        f"페이지가 PDF 범위 밖 — 스캔 불가 (codes {n_tot} / missing {n_miss}). "
                        "⛔ 이 0 들은 실측이 아니라 '재지 못함' 이다 — 신호로 읽지 마라"
                    ),
                    scanned=False,
                )
            )
            continue

        # ① field_missing — 결측 그 자체
        field_missing = round(n_miss / n_tot, 3) if n_tot else 0.0

        # ② length_outlier — 셀 텍스트 길이 z-score 이상치 비율
        pop = per_manual_cells.get(manual_id, [])
        mu = statistics.fmean(pop) if pop else 0.0
        sd = statistics.pstdev(pop) if len(pop) > 1 else 0.0
        if sd > 0 and r["lengths"]:
            n_out = sum(1 for v in r["lengths"] if abs((v - mu) / sd) >= Z_OUTLIER)
            length_outlier = round(n_out / len(r["lengths"]), 3)
        else:
            length_outlier = 0.0

        # ③ table_collapse — 행당 유효 셀 수가 매뉴얼 평균 대비 얼마나 줄었나
        rows_pop = per_manual_rows.get(manual_id, [])
        rows_mu = statistics.fmean(rows_pop) if rows_pop else 0.0
        if not r["rows_valid"]:
            table_collapse = 1.0  # 표 자체가 검출되지 않았다 = 완전 붕괴
        elif rows_mu > 0:
            page_mu = statistics.fmean(r["rows_valid"])
            table_collapse = round(max(0.0, 1.0 - page_mu / rows_mu), 3)
        else:
            table_collapse = 0.0

        signals = {
            "field_missing": field_missing,
            "length_outlier": length_outlier,
            "table_collapse": table_collapse,
        }

        # ── 라벨: 결측이 있으면 **양성 축이 가른다**
        if n_miss > 0 and r["strict"] == 0:
            label = "SOURCE_MISSING"
        elif n_miss > 0:
            label = "CELL_SPLIT"
        elif length_outlier >= OUTLIER_RATE or table_collapse >= COLLAPSE_DROP:
            label = "RE_OCR_CANDIDATE"
        else:
            label = "OK"

        note = (
            f"codes {n_tot} / with_actions {n_ok} / missing {n_miss} / "
            f"code_tokens {r['strict']}{'=' + ','.join(r['hits'][:8]) if r['hits'] else ''} "
            f"(키패드표기 포함 {r['loose']}) / "
            f"cells {len(r['lengths'])} / rows {len(r['rows_valid'])}"
        )
        anchor_conflict = n_ok > 0 and r["strict"] == 0
        if anchor_conflict:
            # 두 번째 양성 축이 첫 번째 양성 축과 모순한다 — 토큰 스캐너가 이 페이지에서 눈이 멀었다.
            note += (
                " ⚠ anchor_conflict: 조치문 추출에 성공한 코드가 있는데 코드 토큰 0 "
                "— 이 페이지에서 토큰 축은 눈이 멀었다"
            )
            if label == "SOURCE_MISSING":
                note += " (따라서 이 SOURCE_MISSING 은 근거 없는 라벨이다)"
        if label == "RE_OCR_CANDIDATE":
            note += " · 결측 0 — 조판 신호만 발화한 **점검 후보**이며 알려진 결함이 아니다"
        verdicts.append(
            PageVerdict(
                manual_id=manual_id,
                page=pno,
                label=label,
                codes_total=n_tot,
                codes_missing_actions=n_miss,
                code_tokens_found=r["strict"],
                signals=signals,
                note=note,
                anchor_conflict=anchor_conflict,
            )
        )
    return verdicts


# ──────────────────────────────────────────────── summarize
def summarize(verdicts: list[PageVerdict]) -> dict:
    """항목 축(결측)과 페이지 축(라벨·양성 축)을 함께 집계한다."""
    data = _error_codes()
    entries = data.get("entries", [])

    by_model: dict[str, dict[str, int]] = {}
    for e in entries:
        m = str(e.get("model") or "?")
        row = by_model.setdefault(m, {"total": 0, "missing_actions": 0, "missing_causes": 0})
        row["total"] += 1
        if not e.get("actions"):
            row["missing_actions"] += 1
        if not e.get("causes"):
            row["missing_causes"] += 1

    warnings: list[str] = []

    # 기대값 대조 — 죽이지 않는다. 다르면 입력이 이미 바뀐 것이므로 알려만 준다.
    diffs: list[str] = []
    for model, exp in EXPECTED["by_model"].items():
        act = by_model.get(model)
        if act is None:
            diffs.append(f"{model}: 기대 {exp} / 실측 없음")
            continue
        for k, v in exp.items():
            if act.get(k) != v:
                diffs.append(f"{model}.{k}: 기대 {v} / 실측 {act.get(k)}")
    n_unparsed = len(data.get("_unparsed") or [])
    n_pending = len(data.get("_pending_review") or [])
    if n_unparsed != EXPECTED["_unparsed"]:
        diffs.append(f"_unparsed: 기대 {EXPECTED['_unparsed']} / 실측 {n_unparsed}")
    if n_pending != EXPECTED["_pending_review"]:
        diffs.append(f"_pending_review: 기대 {EXPECTED['_pending_review']} / 실측 {n_pending}")
    if diffs:
        warnings.append(
            "INPUT_DRIFT — 브리핑 실측과 다릅니다. 입력이 이미 바뀐 것이므로 "
            "아래 표의 **실측값**을 기준으로 읽으세요: " + " · ".join(diffs)
        )

    by_label = {lab: sum(1 for v in verdicts if v.label == lab) for lab in LABELS}
    tokens_by_manual: dict[str, int] = {}
    for v in verdicts:
        tokens_by_manual[v.manual_id] = tokens_by_manual.get(v.manual_id, 0) + v.code_tokens_found
    tokens_total = sum(tokens_by_manual.values())

    # 양성 축 자체의 건강 진단
    blind_manuals = sorted(mid for mid, n in tokens_by_manual.items() if n == 0)
    conflicts = [
        f"{v.manual_id} p.{v.page}({v.label})"
        for v in verdicts
        if v.codes_total - v.codes_missing_actions > 0 and v.code_tokens_found == 0
    ]
    conflict_source_missing = [c for c in conflicts if "(SOURCE_MISSING)" in c]
    if tokens_total == 0:
        warnings.append(
            "SCANNER_BLIND — 스캔한 전 페이지에서 코드 토큰이 0건입니다. 양성 축이 죽었으므로 "
            "SOURCE_MISSING 라벨은 '소스가 없다'가 아니라 '스캐너가 못 봤다'일 수 있습니다."
        )
    elif blind_manuals:
        warnings.append(
            "SCANNER_BLIND(부분) — 코드 토큰이 0건인 매뉴얼: "
            + ", ".join(blind_manuals)
            + ". 해당 매뉴얼의 SOURCE_MISSING 라벨은 근거가 없습니다."
        )
    if conflicts:
        msg = (
            "ANCHOR_CONFLICT — 조치문 추출에 성공한 코드가 있는데 코드 토큰이 0인 페이지: "
            + ", ".join(conflicts)
            + ". 이 페이지들에서 토큰 축은 눈이 멀었다(추출은 코드 토큰이 아니라 한글 명칭으로 조인한다)."
        )
        if conflict_source_missing:
            msg += (
                " 그중 SOURCE_MISSING 라벨이 붙은 "
                + ", ".join(conflict_source_missing)
                + " 은 근거가 없는 라벨이므로 '소스를 바꿔야 풀린다'로 읽지 마세요."
            )
        else:
            msg += " 다만 이 페이지들에 SOURCE_MISSING 라벨은 없어 라벨이 오염되지는 않았습니다."
        warnings.append(msg)
    if not verdicts:
        warnings.append("스캔한 페이지가 0개입니다 — 입력 또는 페이지 매핑을 확인하세요.")

    return {
        "generated_at": str(date.today()),
        "input": {
            "path": str(ERROR_CODES.relative_to(ROOT.parent)).replace("\\", "/"),
            "sha256": _sha256(ERROR_CODES),
            "generated_at": data.get("generated_at"),
            "_status": data.get("_status"),
        },
        "entries": {
            "total": len(entries),
            "by_model": by_model,
            "_unparsed": n_unparsed,
            "_pending_review": n_pending,
        },
        "expected": EXPECTED,
        "expected_diffs": diffs,
        "pages": {
            "scanned": len(verdicts),
            "by_label": by_label,
            "by_manual": sorted({v.manual_id for v in verdicts}),
        },
        "liveness": {
            "code_tokens_total": tokens_total,
            "code_tokens_by_manual": tokens_by_manual,
            "blind_manuals": blind_manuals,
            "anchor_conflicts": conflicts,
        },
        "thresholds": {
            "z_outlier": Z_OUTLIER,
            "outlier_rate": OUTLIER_RATE,
            "collapse_drop": COLLAPSE_DROP,
        },
        "warnings": warnings,
    }


# ──────────────────────────────────────────────── 비용 (산술만)
def estimate_ocr_cost(verdicts: list[PageVerdict], won_per_page: int = 45) -> dict:
    """재-OCR 후보 페이지 수 × 단가. **외부 호출 없이 곱셈만 한다.**

    ⛔ SOURCE_MISSING·CELL_SPLIT 은 대상이 아니다 — 전자는 소스를 바꿔야 풀리고 후자는 파서
    결함이라 같은 이미지를 다시 읽어도 값이 바뀌지 않는다. 무엇을 살지 고르는 것까지가 경계다.
    """
    targets = [v for v in verdicts if v.label == "RE_OCR_CANDIDATE"]
    return {
        "won_per_page": won_per_page,
        "target_label": "RE_OCR_CANDIDATE",
        "n_pages": len(targets),
        "won_total": len(targets) * won_per_page,
        "target_pages": [{"manual_id": v.manual_id, "page": v.page} for v in targets],
        "excluded": {
            "SOURCE_MISSING": sum(1 for v in verdicts if v.label == "SOURCE_MISSING"),
            "CELL_SPLIT": sum(1 for v in verdicts if v.label == "CELL_SPLIT"),
            "OK": sum(1 for v in verdicts if v.label == "OK"),
        },
        "note": "산술 추정치다. 실제 구매·집행은 사람 승인 사안이며 이 모듈은 호출하지 않는다.",
    }


# ──────────────────────────────────────────────── 보충 소스 탐침 (참고)
def probe_supplement() -> dict:
    """iG5A 조치 결측 코드의 조치문이 **트러블슈팅본에 실재하는가**를 읽어서 확인만 한다.

    라벨에 영향을 주지 않는다. 1차 양성 축(코드 토큰)이 iG5A 표준본에서 약할 수 있으므로,
    "소스를 바꾸면 풀리는가"를 **독립된 실측**으로 남긴다 (MQ-905 의 입력).
    """
    m = _manual_entry(SUPPLEMENT_MANUAL_ID)
    if m is None:
        return {"status": "manual_not_registered", "manual_id": SUPPLEMENT_MANUAL_ID}
    pdf_path = RAW / m["file"]
    if not pdf_path.exists():
        return {"status": "file_missing", "manual_id": SUPPLEMENT_MANUAL_ID}

    data = _error_codes()
    missing = [
        e for e in data.get("entries", []) if e.get("model") == "iG5A" and not e.get("actions")
    ]
    names = {str(e.get("code")): _norm(str(e.get("error_name") or "")) for e in missing}

    per_page: list[dict] = []
    blob: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for pno in SUPPLEMENT_PAGES:
            if pno < 1 or pno > len(pdf.pages):
                continue
            text = pdf.pages[pno - 1].extract_text() or ""
            blob.append(text)
            per_page.append(
                {
                    "page": pno,
                    "chars": len(text),
                    "has_action_header": ("조치" in text),
                    "has_cause_header": ("원인" in text),
                }
            )
    joined = _norm("\n".join(blob))
    hits = sorted(c for c, nk in names.items() if nk and nk in joined)
    return {
        "status": "ok",
        "manual_id": SUPPLEMENT_MANUAL_ID,
        "pages_scanned": [p["page"] for p in per_page],
        "chars_scanned": sum(p["chars"] for p in per_page),
        "pages_with_action_header": [p["page"] for p in per_page if p["has_action_header"]],
        "missing_codes_probed": len(names),
        "name_hits": hits,
        "n_name_hits": len(hits),
        "name_misses": sorted(set(names) - set(hits)),
        "note": (
            "명칭(error_name) 문자열이 트러블슈팅본 텍스트에 실재하는지만 본다. "
            "여기서 조치문을 추출하지 않는다 (MQ-905 소관)."
        ),
    }


# ──────────────────────────────────────────────── 리포트
def _md_table(rows: list[list[str]], header: list[str]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def render_markdown(verdicts: list[PageVerdict], summary: dict, cost: dict, probe: dict) -> str:
    L: list[str] = []
    L.append("# 추출 품질 triage — before 스냅샷 (MQ-902)")
    L.append("")
    L.append(
        f"**생성**: {summary['generated_at']} · **자동 생성 파일** — 손으로 고치지 말고 "
        "`uv run python data/extract_triage.py` 를 다시 돌릴 것."
    )
    L.append("")
    L.append(
        f"입력: `{summary['input']['path']}` "
        f"(sha256 `{summary['input']['sha256'][:16]}…`, generated_at "
        f"{summary['input']['generated_at']}) — **읽기 전용**. 이 스크립트는 정본을 쓰지 않는다 (D99)."
    )
    L.append("")
    L.append(
        "이 문서는 MQ-905·907 이 파서를 고치기 **전**의 상태다. 개선을 주장하려면 이 숫자와 "
        "대조해야 한다."
    )
    L.append("")

    L.append("## 0. 경고")
    L.append("")
    if summary["warnings"]:
        for w in summary["warnings"]:
            L.append(f"- 🔴 {w}")
    else:
        L.append(
            f"- 경고 없음. 스캔한 페이지 {summary['pages']['scanned']}개 · 코드 토큰 "
            f"{summary['liveness']['code_tokens_total']}건 (양성 축 생존)."
        )
    L.append("")

    L.append("## 1. 항목 축 — 필드 결측 (65건 전수)")
    L.append("")
    rows = []
    for model, row in sorted(summary["entries"]["by_model"].items()):
        exp = EXPECTED["by_model"].get(model, {})
        rows.append(
            [
                model,
                str(row["total"]),
                str(row["missing_actions"]),
                str(row["missing_causes"]),
                f"{exp.get('total', '-')} / {exp.get('missing_actions', '-')} / "
                f"{exp.get('missing_causes', '-')}",
            ]
        )
    L.append(
        _md_table(
            rows, ["model", "codes", "actions 결측", "causes 결측", "브리핑 기대 (건/조치/원인)"]
        )
    )
    L.append("")
    L.append(
        f"- 합계 **{summary['entries']['total']}건** · `_unparsed` "
        f"**{summary['entries']['_unparsed']}** · `_pending_review` "
        f"**{summary['entries']['_pending_review']}**"
    )
    if summary["expected_diffs"]:
        L.append("- ⚠ 기대값과 다른 항목: " + " · ".join(summary["expected_diffs"]))
    else:
        L.append("- 기대값과 실측이 일치한다.")
    L.append("")

    L.append("## 2. 페이지 축 — 판정")
    L.append("")
    L.append(
        "판정 규칙 (양성 축이 가른다): `missing>0 & tokens==0 → SOURCE_MISSING` · "
        "`missing>0 & tokens>0 → CELL_SPLIT` · `missing==0 & 신호 발화 → RE_OCR_CANDIDATE` · "
        "그 밖 `OK`."
    )
    L.append("")
    rows = []
    for v in verdicts:
        rows.append(
            [
                v.manual_id,
                f"p.{v.page}",
                f"**{v.label}**",
                str(v.codes_total),
                str(v.codes_total - v.codes_missing_actions),
                str(v.codes_missing_actions),
                str(v.code_tokens_found),
                f"{v.signals.get('field_missing', 0.0):.3f}",
                f"{v.signals.get('length_outlier', 0.0):.3f}",
                f"{v.signals.get('table_collapse', 0.0):.3f}",
            ]
        )
    L.append(
        _md_table(
            rows,
            [
                "manual_id",
                "page(물리)",
                "label",
                "codes",
                "with_actions",
                "missing",
                "code_tokens ★",
                "field_missing",
                "length_outlier",
                "table_collapse",
            ],
        )
    )
    L.append("")
    L.append("### 두 축 실측 한 줄 요약")
    L.append("")
    L.append("```")
    for v in verdicts:
        L.append(
            f"{v.manual_id} p.{v.page}: missing {v.codes_missing_actions} / "
            f"code_tokens {v.code_tokens_found} -> {v.label}"
        )
    L.append("```")
    L.append("")
    L.append("### 페이지별 실측 상세")
    L.append("")
    for v in verdicts:
        L.append(f"- `{v.manual_id} p.{v.page}` **{v.label}** — {v.note}")
    L.append("")
    L.append(
        "- 라벨 분포: "
        + " · ".join(f"{k} {n}" for k, n in summary["pages"]["by_label"].items())
        + f" (스캔 {summary['pages']['scanned']}페이지)"
    )
    L.append("")
    L.append("### 계획 기대 라벨과의 대조 — 다르면 실측을 적는다")
    L.append("")
    L.append(
        "Sprint 9 §6 MQ-902 DoD 는 *iG5A 조치 결측 = `SOURCE_MISSING` · S100 결측 페이지 = "
        "`CELL_SPLIT`* 을 기대했다. 실측은 다음과 같다 (결측 **코드 수**를 라벨별로 갈라 센 것):"
    )
    L.append("")
    per_manual_label: dict[str, dict[str, int]] = {}
    for v in verdicts:
        if v.codes_missing_actions:
            per_manual_label.setdefault(v.manual_id, {})
            per_manual_label[v.manual_id][v.label] = (
                per_manual_label[v.manual_id].get(v.label, 0) + v.codes_missing_actions
            )
    for mid, row in sorted(per_manual_label.items()):
        L.append(
            f"- `{mid}` 결측 {sum(row.values())}건 → "
            + " · ".join(f"{k} {n}건" for k, n in sorted(row.items()))
        )
    # ⛔ 결론 문구를 하드코딩하지 않는다 — 실측에서 유도한다 (FAIL 일 때도 그대로 인쇄되면 안 된다).
    for mid, want in (("s100-manual", "CELL_SPLIT"), ("ig5a-manual", "SOURCE_MISSING")):
        row = per_manual_label.get(mid, {})
        hit = row.get(want, 0)
        tot = sum(row.values())
        state = "기대대로" if tot and hit == tot else "기대와 다름"
        L.append(f"- `{mid}`: 기대 라벨 `{want}` — 결측 {tot}건 중 {hit}건 일치 → **{state}**")
    if per_manual_label.get("ig5a-manual", {}).get("SOURCE_MISSING", 0) < sum(
        per_manual_label.get("ig5a-manual", {}).values()
    ):
        L.append(
            "- iG5A 불일치의 원인은 라벨 규칙이 아니라 **양성 축의 적용 범위**다. iG5A 추출은 코드 "
            "토큰이 아니라 **한글 명칭**으로 조인하므로 표준본 본문에 코드 토큰이 거의 없다"
            "(§0 ANCHOR_CONFLICT). 즉 iG5A 에서 `code_tokens` 는 *소스 유무*를 재는 축이 아니다."
        )
    L.append(
        "- iG5A 의 *소스를 바꾸면 풀리는가* 는 §3 보충 소스 탐침이 **독립적으로** 답한다. "
        "그 결과를 라벨보다 우선해 읽을 것."
    )
    L.append("")
    L.append(
        "- 양성 축 합계: 코드 토큰 "
        f"{summary['liveness']['code_tokens_total']}건 "
        + " · ".join(
            f"{k} {n}" for k, n in sorted(summary["liveness"]["code_tokens_by_manual"].items())
        )
    )
    L.append("")

    L.append("## 3. 보충 소스 탐침 (참고 — 라벨에 반영하지 않음)")
    L.append("")
    if probe.get("status") != "ok":
        L.append(f"- 탐침 불가: `{probe.get('status')}` (`{probe.get('manual_id')}`)")
    else:
        L.append(
            f"- `{probe['manual_id']}` 물리 p.{probe['pages_scanned'][0]}~"
            f"{probe['pages_scanned'][-1]} · 텍스트 {probe['chars_scanned']}자 스캔"
        )
        L.append(
            f"- '조치' 머리글이 나타난 페이지: {probe['pages_with_action_header']} "
            "(양성 축 — 비어 있으면 이 탐침 자체가 눈이 먼 것)"
        )
        L.append(
            f"- iG5A 조치 결측 코드 {probe['missing_codes_probed']}건 중 "
            f"**명칭이 이 문서에 실재하는 것 {probe['n_name_hits']}건**: {probe['name_hits']}"
        )
        L.append(f"- 명칭 미발견: {probe['name_misses']}")
    L.append("")

    L.append("## 4. 재-OCR 비용 추정 (산술만)")
    L.append("")
    L.append(
        f"- 대상 `{cost['target_label']}` **{cost['n_pages']}페이지** × "
        f"{cost['won_per_page']}원 = **{cost['won_total']}원**"
    )
    L.append(
        "- 제외: "
        + " · ".join(f"{k} {n}페이지" for k, n in cost["excluded"].items())
        + " — SOURCE_MISSING 은 소스 교체, CELL_SPLIT 은 파서 수정 대상이라 재-OCR 로 풀리지 않는다."
    )
    L.append(f"- {cost['note']}")
    L.append("")

    L.append("## 5. 이 계측기의 한계")
    L.append("")
    L.append(
        "- 코드 토큰 축은 **정규식이 실패하면 조용히 0** 이 된다. 그래서 두 번째 양성 축"
        "(`with_actions` = 같은 페이지에서 조치문 추출에 성공한 코드 수)을 함께 싣고, "
        "둘이 모순하면 `anchor_conflict` 로 표시한다. 모순 표시가 붙은 줄의 `SOURCE_MISSING` 은 "
        "**근거가 없는 라벨**이다."
    )
    L.append(
        f"- 신호 문턱: 셀 길이 |z| ≥ {Z_OUTLIER} 인 셀 비율 ≥ {OUTLIER_RATE} · "
        f"행당 유효 셀 수 감소율 ≥ {COLLAPSE_DROP}. 임의 문턱이며 "
        "판정을 뒤집을 힘은 없다(결측이 있는 페이지는 두 축이 먼저 라벨을 정한다)."
    )
    L.append(
        "- 문자 깨짐 계열 신호는 **의도적으로 넣지 않았다** — P31 실측에서 코퍼스 전체 0건이었고 "
        "한국어 나열 구분자를 고립 자모로 오탐한 전례가 있다."
    )
    L.append("- 페이지는 전부 PDF 물리 페이지다 (D26). 인쇄 페이지 환산은 하지 않는다 (D32).")
    L.append("")
    return "\n".join(L) + "\n"


# ──────────────────────────────────────────────── main
def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 대응

    verdicts = scan()
    summary = summarize(verdicts)
    cost = estimate_ocr_cost(verdicts)
    probe = probe_supplement()

    ANALYSIS.mkdir(exist_ok=True)
    EXTRACTED.mkdir(exist_ok=True)
    REPORT_MD.write_text(render_markdown(verdicts, summary, cost, probe), encoding="utf-8")
    REPORT_JSON.write_text(
        json.dumps(
            {
                "summary": summary,
                "verdicts": [asdict(v) for v in verdicts],
                "ocr_cost": cost,
                "supplement_probe": probe,
                "labels": list(LABELS),
                "signals": list(SIGNALS),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    for w in summary["warnings"]:
        print(f"[경고] {w}")
    print(f"[완료] {REPORT_MD}")
    print(f"[완료] {REPORT_JSON}")
    for model, row in sorted(summary["entries"]["by_model"].items()):
        print(
            f"  {model}: {row['total']}건 / actions 결측 {row['missing_actions']} / "
            f"causes 결측 {row['missing_causes']}"
        )
    print(
        f"  _unparsed {summary['entries']['_unparsed']} · "
        f"_pending_review {summary['entries']['_pending_review']}"
    )
    for v in verdicts:
        print(
            f"  {v.manual_id} p.{v.page}: missing {v.codes_missing_actions} / "
            f"code_tokens {v.code_tokens_found} -> {v.label}"
        )
    print(f"  재-OCR 후보 {cost['n_pages']}페이지 = {cost['won_total']}원")


if __name__ == "__main__":
    main()
