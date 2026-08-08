"""잔가곡선(residual_curve) 산출 — D74 (D72 supersede). M4/Sprint6 MQ-603.

두 부분으로 나뉜다.

  (A) 곡선 생성 — 법정 기준내용연수 기반 **정률 감가 목업 공식**.
      `data/extracted/residual_curve.json` 을 만든다. **외부 파일에 의존하지 않는다.**
  (B) 한계 실증 — 중소벤처기업진흥공단 자산거래중개장터 호가 데이터 분석.
      `data/analysis/residual_curve.md` 의 "왜 실데이터를 쓰지 못하는가" 절만 만든다.
      **JSON 에는 들어가지 않는다.** 원본 CSV 가 없으면 이 부분만 건너뛴다.

왜 (B) 를 값 원천으로 쓰지 않는가 (D74)
  실측 곡선이 5종 카테고리 전부 우상향했다. `카테고리2`(세부분류)로 층화해도 사라지지 않았고,
  동일 `모델명` 내 연차-가격 상관은 사실상 0 이었다. 중고 매물 호가는 연차가 아니라
  **기계 규격이 지배**한다 — 이 데이터로는 감가를 식별할 수 없다.
  실데이터를 버리는 게 아니라 **실데이터가 무엇을 말할 수 없는지를 근거로 남긴다.**

유지되는 D72 규격
  연차 버킷 6종 격자 · 평활 금지 · D65 추정치 고지 강제 · 카테고리 문자열은 원본 바이트 그대로

주의
  - `data/raw/` 는 읽기 전용 (D19). 이 스크립트는 원본을 열기만 한다.
  - 회귀 스위트에 넣지 않는다 — (B) 의 원본 CSV 가 git 제외라 CI 재현이 불가능하다.
  - CSV 부재 시 md 는 **갱신하지 않고 보존**한다(한계 실증 절을 잃지 않기 위해).
"""

from __future__ import annotations

import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent  # data/
JSON_OUT = ROOT / "extracted" / "residual_curve.json"
MD_OUT = ROOT / "analysis" / "residual_curve.md"

# ══════════════════════════════════════════════ (A) 목업 곡선 파라미터
# 근거는 residual_curve.md §2 에 전부 기록한다. 상수를 손으로 박지 말고 여기서 유도한다.

STATUTORY_LIFE_YEARS = 8  # 법정 기준내용연수 N — 제조업 기계장치 (⚠ 미검증 가정, md §2-2)
RESIDUAL_AT_LIFE_END = 0.50  # 목업 가정: N 년 시점 잔가율. 세법 관행(0.05)이 아니다 (md §2-3)
FLOOR = 0.10  # 잔존율 하한 — 고철·중고부품 회수가치 자리표시자 (md §2-4)
TAX_RESIDUAL_AT_N = 0.05  # 세법 정률법 상각률 유도 관행. **참고 곡선 계산에만** 쓴다

# 버킷 대표연차 = 버킷 중앙값 (D74)
BUCKETS: list[tuple[str, int, int]] = [
    ("0-2", 0, 2),
    ("3-5", 3, 5),
    ("6-10", 6, 10),
    ("11-15", 11, 15),
    ("16-20", 16, 20),
    ("21-30", 21, 30),
]
BUCKET_REP_AGE: dict[str, int] = {
    "0-2": 1,
    "3-5": 4,
    "6-10": 8,
    "11-15": 13,
    "16-20": 18,
    "21-30": 25,
}

# 곡선 대상 카테고리 — MQ-601a 의 `assets.category` 후보.
# **원본 CSV 의 `카테고리1` 바이트 그대로.** '환경  설비' 는 공백 2칸이다(문서 표기 오류 주의).
# CSV 가 있으면 아래 상수가 원본에 실재하는지 대조하고, 불일치 시 경고한다.
CURVE_CATEGORIES: list[str] = [
    "공작 기계",
    "가공기계",
    "기타",
    "일반산업",
    "전기전자계측",
    "환경  설비",
]

# ══════════════════════════════════════════════ (B) 실데이터 분석 파라미터
CSV_NAME = "중소벤처기업진흥공단_자산거래중개장터 매물정보_20251231.csv"
CSV_PATH = ROOT / "raw" / "external" / CSV_NAME
CSV_ENCODING = "cp949"
BASIS_DATE = "2025-12-31"  # 파일명 접미 _20251231
REFERENCE_YEAR = 2026  # age = 2026 - 제조연도
MISSING_TOKEN = "확인불가"
MIN_PRICE = 10_000
EXPECTED_FINAL_N = 5_475  # 실측(2026-08 원본 기준). 다르면 경고 — 원본 갱신 감지용
CLIP_Q = 0.995  # 상위 0.5% 클리핑(캡)
CONTAMINATION_RATIO = 0.01  # 단일 제조년월 일자가 카테고리 표본의 1% 이상 → 오염
MIN_BUCKET_N = 10
MIN_BASE_N = 30
BASE_MAX_AGE = 5
STRATA = ["머시닝센터", "프레스", "절단절곡기"]  # 카테고리2 층화 대상 (표본 상위 세부분류)

CSV_HINT = f"""  원본 CSV 미검출: {CSV_PATH}
  data/raw/ 는 git 에서 제외된다(D19). 한계 실증 절이 필요하면 아래에서 내려받을 것.
    공공데이터포털 — 중소벤처기업진흥공단_자산거래중개장터 매물정보
    https://www.data.go.kr/data/15044251/fileData.do
    파일명 유지 필수 (인코딩 cp949, 16,011행)"""


# ══════════════════════════════════════════════ (A) 곡선 생성 — 외부 의존 없음
def declining_rate(life_years: int, residual_at_end: float) -> float:
    """정률법 상각률 유도.

    `residual(N) = (1 - r) ** N = residual_at_end`  →  `r = 1 - residual_at_end ** (1/N)`

    이 식은 세법 정률법 상각률표의 유도식과 같다.
    residual_at_end=0.05 를 넣으면 N=8 → 0.3124, N=10 → 0.2589 로 표의 0.313 / 0.259 와 일치한다.
    목업 곡선은 여기에 0.05 가 아니라 RESIDUAL_AT_LIFE_END 를 넣는다(md §2-3).
    """
    if life_years <= 0 or not (0.0 < residual_at_end < 1.0):
        raise ValueError("life_years > 0, 0 < residual_at_end < 1")
    return 1.0 - residual_at_end ** (1.0 / life_years)


def residual_at(age: int, rate: float, floor: float = FLOOR) -> float:
    """정률 감가 + 하한. 격자 밖(age > 30)에서도 floor 아래로 내려가지 않는다."""
    return max((1.0 - rate) ** age, floor)


def build_curve() -> tuple[list[dict], dict]:
    """(A) 목업 곡선. CSV 없이도 항상 동작한다."""
    rate = declining_rate(STATUTORY_LIFE_YEARS, RESIDUAL_AT_LIFE_END)
    tax_rate = declining_rate(STATUTORY_LIFE_YEARS, TAX_RESIDUAL_AT_N)
    source = (
        f"법정 기준내용연수 {STATUTORY_LIFE_YEARS}년 기반 정률법 추정 (목업) — 실거래 데이터 아님 "
        f"[r={rate:.4f}, floor={FLOOR}, D74]"
    )
    rows: list[dict] = []
    for cat in CURVE_CATEGORIES:
        for name, _, _ in BUCKETS:
            rows.append(
                {
                    "category": cat,
                    "age_bucket": name,
                    "residual_ratio": round(residual_at(BUCKET_REP_AGE[name], rate), 4),
                    # 표본에서 나온 값이 아니다. 채우면 거짓말이므로 null (D74)
                    "n_samples": None,
                    "p25_ratio": None,
                    "p75_ratio": None,
                    "base_n": None,
                    "source": source,
                }
            )
    meta = {
        "rate": rate,
        "tax_rate": tax_rate,
        "source": source,
        # 하한이 실제로 구속하기 시작하는 연차 (log 로 역산)
        "floor_binds_from_age": math.ceil(math.log(FLOOR) / math.log(1.0 - rate)),
    }
    return rows, meta


# ══════════════════════════════════════════════ (B) 실데이터 분석 — CSV 있을 때만
def parse_year(raw: str) -> int | None:
    """'2013-05-01' / '2022' → 연도. '확인불가'·비정형 → None."""
    s = (raw or "").strip()
    if not s or s == MISSING_TOKEN:
        return None
    m = re.match(r"^(\d{4})", s)
    return int(m.group(1)) if m else None


def parse_price(raw: str) -> int | None:
    s = (raw or "").strip().replace(",", "")
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def quantile(sorted_vals: list[float], q: float) -> float:
    """선형보간 분위수. q=0.5 는 median 과 동일."""
    n = len(sorted_vals)
    if n == 0:
        raise ValueError("empty")
    if n == 1:
        return float(sorted_vals[0])
    pos = (n - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return float(sorted_vals[lo])
    return float(sorted_vals[lo]) + (float(sorted_vals[hi]) - float(sorted_vals[lo])) * (pos - lo)


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


def analyze_market() -> dict | None:
    """(B) 호가 데이터 분석. CSV 가 없으면 None — 곡선 생성은 이것과 무관하게 진행된다."""
    if not CSV_PATH.exists():
        return None
    with open(CSV_PATH, encoding=CSV_ENCODING, newline="") as f:
        rows = list(csv.DictReader(f))
    total = len(rows)

    cat_counts = Counter(r["카테고리1"] for r in rows)
    blank = sum(1 for r in rows if not r["제조년월"].strip())
    unknown = sum(1 for r in rows if r["제조년월"].strip() == MISSING_TOKEN)

    s1 = [r for r in rows if parse_year(r["제조년월"]) is not None]
    s2 = [r for r in s1 if (parse_price(r["희망가격"]) or 0) > 0]
    s3 = [r for r in s2 if (parse_price(r["희망가격"]) or 0) >= MIN_PRICE]

    samples = [
        {
            "category": r["카테고리1"],
            "sub": r["카테고리2"].strip(),
            "model": r["모델명"].strip(),
            "mfg_raw": r["제조년월"].strip(),
            "age": REFERENCE_YEAR - parse_year(r["제조년월"]),
            "price": float(parse_price(r["희망가격"])),
        }
        for r in s3
    ]

    # 상위 0.5% 캡 (표본 수 불변)
    prices_sorted = sorted(s["price"] for s in samples)
    cap = quantile(prices_sorted, CLIP_Q)
    clipped = sum(1 for s in samples if s["price"] > cap)
    for s in samples:
        s["price"] = min(s["price"], cap)

    # 오염 제거 — 카테고리별 단일 제조년월 일자 1% 이상
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for s in samples:
        by_cat[s["category"]].append(s)
    contamination: dict[str, list[tuple[str, int]]] = {}
    kept_by_cat: dict[str, list[dict]] = {}
    for cat, rs in by_cat.items():
        threshold = len(rs) * CONTAMINATION_RATIO
        dates = Counter(s["mfg_raw"] for s in rs)
        bad = sorted(
            ((d, c) for d, c in dates.items() if c >= threshold), key=lambda dc: (-dc[1], dc[0])
        )
        bad_dates = {d for d, _ in bad}
        contamination[cat] = bad
        kept_by_cat[cat] = [s for s in rs if s["mfg_raw"] not in bad_dates]
    kept_all = [s for rs in kept_by_cat.values() for s in rs]

    # ① 카테고리1 격자 (D72 방식 — 우상향 증거)
    grid: dict[str, dict[str, dict]] = {}
    base_info: dict[str, dict] = {}
    age_hist: dict[str, Counter] = {}
    for cat, rs in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        kept = kept_by_cat[cat]
        age_hist[cat] = Counter(s["age"] for s in rs)
        base_prices = sorted(s["price"] for s in kept if s["age"] <= BASE_MAX_AGE)
        base_info[cat] = {
            "n_filtered": len(rs),
            "n_kept": len(kept),
            "base_n": len(base_prices),
            "base": None,
        }
        if len(base_prices) < MIN_BASE_N:
            continue
        base = quantile(base_prices, 0.5)
        base_info[cat]["base"] = base
        grid[cat] = {}
        for name, lo, hi in BUCKETS:
            vals = sorted(s["price"] for s in kept if lo <= s["age"] <= hi)
            cell = {"n": len(vals)}
            if len(vals) >= MIN_BUCKET_N:
                cell["median_price"] = quantile(vals, 0.5)
                cell["ratio"] = round(quantile(vals, 0.5) / base, 4)
            grid[cat][name] = cell

    # ② 카테고리2 층화 — 구성 편향 가설 검정
    strata: dict[str, dict] = {}
    for sub in STRATA:
        rs = [s for s in kept_all if s["sub"] == sub]
        cells = {}
        for name, lo, hi in BUCKETS:
            vals = sorted(s["price"] for s in rs if lo <= s["age"] <= hi)
            cells[name] = {"n": len(vals)}
            if len(vals) >= MIN_BUCKET_N:
                cells[name]["median_price"] = quantile(vals, 0.5)
        strata[sub] = {"total": len(rs), "cells": cells}

    # ③ 동일 모델명 내 연차-가격 상관 (모델 내 평균 제거 = 규격 고정효과 근사)
    correl: dict[str, dict] = {}
    for sub in STRATA:
        rs = [s for s in kept_all if s["sub"] == sub]
        groups: dict[str, list[dict]] = defaultdict(list)
        for s in rs:
            if s["model"]:
                groups[s["model"]].append(s)
        xs: list[float] = []
        ys: list[float] = []
        used = 0
        for items in groups.values():
            if len(items) < 2 or len({i["age"] for i in items}) < 2:
                continue
            used += 1
            ma = sum(i["age"] for i in items) / len(items)
            mp = sum(i["price"] for i in items) / len(items)
            xs += [i["age"] - ma for i in items]
            ys += [i["price"] - mp for i in items]
        pooled = [s for s in rs if s["model"]]
        correl[sub] = {
            "groups": used,
            "obs": len(xs),
            "r_within": pearson(xs, ys),
            "r_pooled": pearson([s["age"] for s in pooled], [s["price"] for s in pooled]),
            "n_pooled": len(pooled),
        }

    return {
        "total": total,
        "cat_counts": cat_counts,
        "blank": blank,
        "unknown": unknown,
        "n1": len(s1),
        "n2": len(s2),
        "n3": len(s3),
        "cap": cap,
        "clipped": clipped,
        "max_price": prices_sorted[-1],
        "contamination": contamination,
        "base_info": base_info,
        "grid": grid,
        "age_hist": age_hist,
        "strata": strata,
        "correl": correl,
        "kept_all": len(kept_all),
    }


# ══════════════════════════════════════════════ 문서 렌더
def render_md(curve: list[dict], meta: dict, mkt: dict) -> str:
    lines: list[str] = []
    a = lines.append
    rate = meta["rate"]
    bucket_names = [b for b, _, _ in BUCKETS]
    grid = mkt["grid"]

    a("# 잔가곡선 (residual_curve) — 목업 공식과 한계 실증")
    a("")
    a("- 생성: `data/build_residual_curve.py` (자동 생성 문서 — 직접 편집하지 말 것)")
    a(f"- 생성일: {date.today().isoformat()}")
    a(
        "- 결정: **D74**(목업 정률 공식 · D72 supersede) · D65(추정치 고지 강제) · D19(원본 읽기 전용)"
    )
    a(
        "- D72 에서 유지되는 것: **연차 버킷 6종 격자 · 평활 금지 · 카테고리 원본 바이트 · D65 고지**"
    )
    a("")
    a("> **이 곡선은 목업이다.** 실거래·호가 어느 쪽에서도 값을 가져오지 않았다.")
    a("> 법정 기준내용연수를 앵커로 한 **명시적 가정의 정률 감가 공식**이며, 시장 시세가 아니다.")
    a("> 이 값을 인용하는 모든 출력은 D65 의 추정치 고지를 함께 실어야 한다.")
    a(">")
    a("> **호가 데이터(중진공 장터)를 값 원천으로 쓰지 않는 이유는 §4 에 실측으로 남겼다.**")
    a("> 요약: 호가는 연차가 아니라 기계 규격이 지배해서 감가를 식별할 수 없다.")
    a("")

    # ── §1 곡선
    a("## 1. 곡선 (목업) — `residual_curve.json` 의 값")
    a("")
    a("전 카테고리 동일 값이다. 카테고리 축은 **조인 키로만 존재**한다(이유 §2-5).")
    a("")
    a("| age_bucket | 대표연차 | 취득연도 범위 | residual_ratio |")
    a("|---|---:|---|---:|")
    first = {r["age_bucket"]: r for r in curve if r["category"] == CURVE_CATEGORIES[0]}
    for b, lo, hi in BUCKETS:
        a(
            f"| `{b}` | {BUCKET_REP_AGE[b]} | {REFERENCE_YEAR - hi} ~ {REFERENCE_YEAR - lo} | "
            f"**{first[b]['residual_ratio']:.4f}** |"
        )
    a("")
    a(f"- 카테고리 {len(CURVE_CATEGORIES)}종 × 버킷 {len(BUCKETS)}종 = **{len(curve)}행**")
    a(
        "- 취득연도 범위는 기준연도 2026 기준. 격자 밖(`age > 30`)은 행이 없다 — 소비 측은 `21-30` 로 "
        f"클램프하거나 하한 {FLOOR} 를 쓸 것."
    )
    a("")

    # ── §2 파라미터와 근거
    a("## 2. 공식과 파라미터 — **왜 이 값인가**")
    a("")
    a("```")
    a("residual(age) = max( (1 - r) ** age , FLOOR )")
    a("r             = 1 - RESIDUAL_AT_LIFE_END ** (1 / N)")
    a("```")
    a("")
    a("| 기호 | 값 | 무엇인가 | 성격 |")
    a("|---|---:|---|---|")
    a(f"| `N` | {STATUTORY_LIFE_YEARS} | 법정 기준내용연수(제조업 기계장치) | **법령 — 미검증** |")
    a(f"| `RESIDUAL_AT_LIFE_END` | {RESIDUAL_AT_LIFE_END} | N 년 시점 잔가율 | **가정** |")
    a(f"| `r` | {rate:.4f} | 연 정률 상각률 (유도값) | 유도 |")
    a(f"| `FLOOR` | {FLOOR} | 잔존율 하한 | **가정** |")
    a(f"| (참고) 세법 잔존율 | {TAX_RESIDUAL_AT_N} | 세법 상각률표 유도 관행 | 참고 곡선 전용 |")
    a("")
    a("### 2-1. 상수를 박지 않고 유도한다")
    a("")
    a("`declining_rate(N, residual_at_end)` 가 `r` 을 계산한다. 이 유도식은 세법 정률법 상각률표의")
    a("유도식과 같다 — `residual_at_end=0.05` 를 넣으면")
    a(f"N=8 → {declining_rate(8, 0.05):.4f}, N=10 → {declining_rate(10, 0.05):.4f} 로")
    a("상각률표의 **0.313 / 0.259 와 일치**한다. 즉 식 자체는 검증 가능하다.")
    a("")
    a("### 2-2. `N = 8` — 법정 기준내용연수 ⚠ 미검증")
    a("")
    a("제조업 기계장치의 기준내용연수를 8년으로 두었다(내용연수범위 6~10년의 중앙).")
    a("**이 값은 법령 원문과 대조되지 않았다.** 근거 문서(`법인세법 시행규칙` 별표)는")
    a('`data/rules/laws/` 수집 파이프라인이 `fetch_status:"PENDING"` 상태이므로,')
    a("원문이 확보되면 **가장 먼저 재검증해야 할 파라미터**다. 값이 바뀌면 곡선 전체가 바뀐다.")
    a("")
    a("### 2-3. `RESIDUAL_AT_LIFE_END = 0.50` — 세법 0.05 를 그대로 쓰지 않은 이유")
    a("")
    a("세법 관행(N 년 시점 잔존율 5%)을 그대로 넣으면 곡선이 이렇게 된다.")
    a("")
    a("| age | 세법 정률 (r={:.4f}) | 목업 (r={:.4f}) |".format(meta["tax_rate"], rate))
    a("|---:|---:|---:|")
    for age in (1, 4, 8, 13, 18, 25):
        tax = (1 - meta["tax_rate"]) ** age
        a(f"| {age} | {tax:.4f} | {residual_at(age, rate):.4f} |")
    a("")
    n2130 = sum(mkt["age_hist"][c][x] for c in grid for x in range(21, 31))
    a(
        f"**age 20 에서 세법 곡선은 {(1 - meta['tax_rate']) ** 20:.4f} 다.** "
        "그런데 실데이터는 20~30년 설비가 여전히 시장에"
    )
    a(f"올라오고 호가된다는 것을 보여준다 — 집계 5종에서 `age 21-30` 매물이 {n2130:,}건 이고,")
    a(
        "`'머시닝센터'` 의 `21-30` 호가 중앙값은 "
        f"{mkt['strata']['머시닝센터']['cells']['21-30'].get('median_price', 0) / 10000:,.0f}만원이다(§4-2)."
    )
    a('**"20년이면 사실상 0"은 과세 목적의 조기 상각 유인이지 시장 사실이 아니다.**')
    a("")
    a("그래서 목업은 법정 내용연수를 **가치가 0 이 되는 시점이 아니라 절반이 되는 시점**으로")
    a("재해석한다. 이것은 **검증된 시장 사실이 아니라 명시적 가정**이다. 다만 두 가지를 만족한다.")
    a("")
    a('1. **존재 사실과 모순되지 않는다** — 위 실측이 지지하는 것은 "오래된 설비도 무시 못 할 값에')
    a('   호가된다"는 **존재** 명제뿐이다. 기울기(감가율)는 실측이 말해주지 못한다(§4).')
    a("2. **격자 전 구간에서 판정력이 남는다** — 세법 곡선을 쓰면 `6-10` 이후가 전부 하한에 붙어")
    a("   `assess_repair_value` 의 verdict 가 연차를 구분하지 못한다. 이건 데이터 주장이 아니라")
    a("   **도구 요구사항**이다.")
    a("")
    a("### 2-4. `FLOOR = 0.10`")
    a("")
    a("설비가 고철·중고부품으로서 갖는 최소 회수가치의 자리표시자다. 과거 기업회계 관행의")
    a("잔존가액 10% 를 차용했다(**가정 — 근거 문서 미확보**).")
    a(
        f"현재 파라미터에서 하한이 실제로 구속하는 구간은 **age >= {meta['floor_binds_from_age']}** 이므로"
    )
    a("격자 대표연차(최대 25)에는 적용되지 않는다. 즉 격자 값은 전부 정률식 원값이다.")
    a("하한은 **격자 밖 연차를 조회하는 소비 측을 위한 방어선**으로만 존재한다.")
    a("")
    a("### 2-5. 카테고리별 `N` 을 두지 않은 이유 — 카테고리 축의 정보량은 0")
    a("")
    a("**단일 `N` 을 쓴다. 따라서 전 카테고리의 `residual_ratio` 가 동일하다.**")
    a("")
    a(
        "- 법정 기준내용연수는 **업종별**로 정해지는데, 이 카테고리는 중고 장터의 **매물 분류축**이라"
    )
    a(
        "  업종 코드로 매핑되지 않는다. 카테고리별로 다른 `N` 을 주면 그 차이 자체가 근거 없는 가정이 된다."
    )
    a("- 실데이터로 카테고리 차이를 추정할 수도 없다 — 그게 §4 의 결론이다.")
    a(
        "- 그래서 카테고리 축은 **`(category, age_bucket)` PK 와 조인을 성립시키기 위해서만** 존재한다."
    )
    a("  카테고리별 차등이 필요해지면 그것은 **새 근거와 새 결정**이 필요한 일이다.")
    a("")
    a("### 2-6. 대상 카테고리 — 원본 바이트 그대로")
    a("")
    a("| # | repr(category) | 원본 CSV 실재 |")
    a("|---:|---|---|")
    for i, cat in enumerate(CURVE_CATEGORIES, 1):
        a(
            f"| {i} | `{cat!r}` | {'✅ ' + format(mkt['cat_counts'][cat], ',') + '건' if cat in mkt['cat_counts'] else '❌ 없음'} |"
        )
    a("")
    a(
        "- **`'환경  설비'` 는 공백 2칸이다.** `data/data_list.md §6-1` 이 `환경설비` 로 잘못 옮겼다 —"
    )
    a("  문서를 베끼지 말고 이 표의 바이트를 쓸 것. 스크립트가 매 실행마다 원본 CSV 와 대조한다.")
    a("- 호가 데이터에서 `base_n >= 30` 을 넘긴 5종에 **`'환경  설비'` 를 더해 6종**으로 했다.")
    a(
        "  목업 공식은 표본 문턱과 무관하므로 표본 부족을 이유로 뺄 근거가 없고, MQ-601a 의 자산 배치가"
    )
    a("  넓어진다. 동시에 **공백 2칸 문자열이 시드→조인 경로에서 실제로 검증**된다.")
    a(
        "- 표기 변종(`'환경 / 설비'`, `'고무 / 플라스틱'` 등)은 **넣지 않았다** — 같은 뜻의 두 문자열을"
    )
    a("  둘 다 조인 키로 두면 시드에서 어느 쪽을 쓰는지가 우연에 맡겨진다.")
    a("")

    # ── §3 한계
    a("## 3. 한계")
    a("")
    a("1. **목업 공식이며 실거래가와 무관하다.** 값의 출처는 데이터가 아니라 §2 의 가정 3개")
    a(
        "   (`N`, `RESIDUAL_AT_LIFE_END`, `FLOOR`)다. 그중 `N` 만 법령 근거를 가지며 그마저 미검증이다."
    )
    a("2. **호가지 실거래가 아니다.** 유일하게 참조한 실데이터(중진공 장터)조차 매도 희망가이며")
    a("   성사가가 아니다. 그마저 값 원천이 아니라 한계 실증으로만 쓴다(§4).")
    a("3. **연 1회 스냅샷.** 원본 파일이 연말 1회 공개되므로 시세 변동을 추적할 수 없다.")
    a("4. **신품가 분모가 아니다.** `residual_ratio` 는 **취득원가 대비 비율**로 정의된다")
    a(
        "   (`book_value ≈ acquisition_cost × residual_ratio`). 취득원가를 모르는 자산에는 쓸 수 없다."
    )
    a("5. **age 2~4 구간은 실측 표본이 아예 없다**(§4-1). 목업 공식은 이 구간에도 값을 내지만,")
    a("   그 값은 **공식의 외삽이지 관측이 아니다.**")
    a("")

    # ── §4 한계 실증
    a("## 4. 한계 실증 — 왜 실데이터를 값 원천으로 쓰지 못하는가")
    a("")
    a(f"원천: `data/raw/external/{CSV_NAME}` (cp949, {mkt['total']:,}행, 기준일 {BASIS_DATE})")
    a("")
    a("근거는 3단이다. **① 카테고리1 집계에서 곡선이 우상향한다 → ② 세부분류로 층화해도 사라지지")
    a("않는다 → ③ 동일 모델 안에서 연차-가격 상관이 사실상 0 이다.**")
    a("")

    a("### 4-1. 1단 — 카테고리1 집계 (D72 방식) 결과가 우상향")
    a("")
    a(
        "`제조년월` 결측은 빈칸이 아니라 **`'확인불가'` 문자열**이다. "
        f"빈 문자열 {mkt['blank']:,}건 / `'확인불가'` **{mkt['unknown']:,}건**"
        f"({mkt['unknown'] / mkt['total']:.1%}). "
        f"결측 처리하지 않으면 분모가 {mkt['total']:,} 이 되어 집계가 통째로 틀어진다."
    )
    a("")
    a("| 단계 | 조건 | 잔여 | 감소 |")
    a("|---|---|---:|---:|")
    a(f"| ① | 전체 | {mkt['total']:,} | — |")
    a(f"| ② | 제조년월 연도 파싱 성공 | {mkt['n1']:,} | -{mkt['total'] - mkt['n1']:,} |")
    a(f"| ③ | + 희망가격 > 0 | {mkt['n2']:,} | -{mkt['n1'] - mkt['n2']:,} |")
    a(
        f"| ④ | + 희망가격 >= {MIN_PRICE:,} **(유효 표본)** | **{mkt['n3']:,}** | -{mkt['n2'] - mkt['n3']:,} |"
    )
    a("")
    a(
        f"- D68 이 인용한 5,396 은 재현되지 않는다. 필터를 `연도 파싱 성공 ∧ 희망가격 >= {MIN_PRICE:,}` 으로 고정했다."
    )
    a(
        f"- 클리핑: 상위 {(1 - CLIP_Q):.1%} 캡. 최대 {mkt['max_price']:,.0f}원 → 상한 {mkt['cap']:,.0f}원, "
        f"{mkt['clipped']}건 캡(표본 수 불변)."
    )
    a("")
    a(
        f"**호가 기준 상대 잔가율** (`base = median(가격 | age <= {BASE_MAX_AGE})`, 버킷 표본 <{MIN_BUCKET_N} 은 `—`):"
    )
    a("")
    a("| 카테고리 | " + " | ".join(f"`{b}`" for b in bucket_names) + " | base_n |")
    a("|---|" + "---|" * (len(bucket_names) + 1))
    for cat in grid:
        cells = []
        for b in bucket_names:
            g = grid[cat][b]
            cells.append(f"**{g['ratio']:.3f}** ({g['n']})" if "ratio" in g else f"— ({g['n']})")
        a(f"| `{cat!r}` | " + " | ".join(cells) + f" | {mkt['base_info'][cat]['base_n']} |")
    a("")
    rising = [
        c
        for c in grid
        if "ratio" in grid[c]["0-2"]
        and any(
            "ratio" in grid[c][b] and grid[c][b]["ratio"] > grid[c]["0-2"]["ratio"]
            for b in ("11-15", "16-20", "21-30")
        )
    ]
    a(
        f"**{len(grid)}종 중 {len(rising)}종에서 11년 이상 버킷이 `0-2` 버킷보다 크다.** "
        "감가곡선이라면 나올 수 없는 모양이다."
    )
    a("")
    a("절대 중앙값(원)으로 보면 더 분명하다.")
    a("")
    a("| 카테고리 | base median | " + " | ".join(f"`{b}`" for b in bucket_names) + " |")
    a("|---|---:|" + "---:|" * len(bucket_names))
    for cat in grid:
        cells = [
            f"{grid[cat][b]['median_price']:,.0f}" if "median_price" in grid[cat][b] else "—"
            for b in bucket_names
        ]
        a(f"| `{cat!r}` | {mkt['base_info'][cat]['base']:,.0f} | " + " | ".join(cells) + " |")
    a("")

    a("#### 카테고리1 유일값 — 원본 바이트 전량")
    a("")
    a("| # | repr(카테고리1) | 원본 건수 | 곡선 대상 |")
    a("|---:|---|---:|---|")
    for i, (cat, n) in enumerate(mkt["cat_counts"].most_common(), 1):
        a(f"| {i} | `{cat!r}` | {n:,} | {'✅' if cat in CURVE_CATEGORIES else '—'} |")
    a("")
    a(
        "표기 변종이 병존한다 — `'환경  설비'` vs `'환경 / 설비'`, `'고무  플라스틱'` vs `'고무 / 플라스틱'`,"
    )
    a("`'전기전자계측'` vs `'전기/전자/계측'`, `'공조냉각유공압'` vs `'공조/냉각/유공압'`,")
    a(
        "`'물류운반하역'` vs `'물류운반/하역'`, `'정보통신보안'` vs `'정보통신/보안'`. 집계에서는 병합하지 않았다."
    )
    a("")

    a("#### 연차 원자료 분포 — `age 2~4` 공백 (오염 제거 전)")
    a("")
    ages = list(range(0, 11))
    a("| 카테고리 | " + " | ".join(f"age {x}" for x in ages) + " |")
    a("|---|" + "---:|" * len(ages))
    for cat in grid:
        h = mkt["age_hist"][cat]
        a(f"| `{cat!r}` | " + " | ".join(str(h.get(x, 0)) for x in ages) + " |")
    a("")
    age34 = [mkt["age_hist"][c].get(x, 0) for c in grid for x in (3, 4)]
    a(
        f"- **`age=2` 는 전 카테고리 0건**, `age=3·4` 도 카테고리당 {min(age34)}~{max(age34)}건뿐이다."
    )
    a("- `age=0·1` 에 표본이 몰려 있고 그중 상당수가 **제조일이 아닌 등록일**이다(아래 오염 제거).")
    a("- 이것이 D72 가 `age<=2` 대신 `age<=5` 를 base 로 삼은 이유였다.")
    a("")

    a("#### 오염 제거 기록 — 카테고리별 단일 `제조년월` 일자 1% 이상")
    a("")
    a(
        "`2025-01-13` 처럼 제조일이 아니라 **등록일이 들어간 정황**이 있어, 한 카테고리 안에서 단일 일자가"
    )
    a(
        "그 카테고리 표본의 1% 이상이면 그 일자 행을 통째로 제외했다. 월 단위 표기(`1989-10-01` 등)도"
    )
    a("같은 규칙에 걸린다 — **규칙을 예외 없이 적용한 결과이며 제외 건수를 아래에 남긴다.**")
    a("")
    a("| 카테고리 | 유효 표본 | 임계(1%) | 제외 일자 수 | 제외 행 | 잔여 | base_n |")
    a("|---|---:|---:|---:|---:|---:|---:|")
    for cat, info in sorted(mkt["base_info"].items(), key=lambda kv: -kv[1]["n_filtered"]):
        n = info["n_filtered"]
        a(
            f"| `{cat!r}` | {n:,} | {n * CONTAMINATION_RATIO:.2f} | {len(mkt['contamination'][cat])} | "
            f"{n - info['n_kept']:,} | {info['n_kept']:,} | {info['base_n']} |"
        )
    a("")
    a("제외된 일자 상세 (집계에 반영된 카테고리):")
    a("")
    for cat in grid:
        items = mkt["contamination"][cat]
        a(f"- `{cat!r}` ({len(items)}일자, {sum(c for _, c in items):,}행)")
        a("  " + ", ".join(f"`{d}`×{c}" for d, c in items))
    a("")
    a("제외된 일자 상세 (집계 미반영 카테고리, 상위 10일자):")
    a("")
    for cat, info in sorted(mkt["base_info"].items(), key=lambda kv: -kv[1]["n_filtered"]):
        if cat in grid:
            continue
        items = mkt["contamination"][cat]
        head = ", ".join(f"`{d}`×{c}" for d, c in items[:10])
        more = f" … 외 {len(items) - 10}일자" if len(items) > 10 else ""
        a(f"- `{cat!r}` ({len(items)}일자, {sum(c for _, c in items):,}행) {head}{more}")
    a("")
    a("> 소표본 카테고리는 1% 임계가 1건 미만이 되어 사실상 전량이 제외된다. 이들은 어차피")
    a("> `base_n < 30` 으로 집계에서 빠진다.")
    a("")

    a("### 4-2. 2단 — `카테고리2` 층화로도 우상향이 사라지지 않는다")
    a("")
    a('"신형 매물은 소형기기, 구형은 대형기계"라는 구성 편향 가설을 검정했다.')
    a(
        f"세부분류를 고정하면(오염 제거 후 표본 {mkt['kept_all']:,}건 기준) 사라져야 하는데, 사라지지 않는다."
    )
    a("")
    a("| 카테고리2 | 표본 | " + " | ".join(f"`{b}`" for b in bucket_names) + " |")
    a("|---|---:|" + "---:|" * len(bucket_names))
    for sub, d in mkt["strata"].items():
        cells = []
        for b in bucket_names:
            c = d["cells"][b]
            cells.append(
                f"{c['median_price'] / 10000:,.0f}만 ({c['n']})"
                if "median_price" in c
                else f"— ({c['n']})"
            )
        a(f"| `{sub}` | {d['total']:,} | " + " | ".join(cells) + " |")
    a("")
    a("- `'머시닝센터'` 는 `11-15`·`16-20` 이 `0-2` 보다 **높다**.")
    a("- `'프레스'` 는 `21-30` 이 `0-2` 의 3배 이상이다.")
    a("- 단위는 만원, 괄호는 표본 수. 표본 <10 은 `—`.")
    a("")

    a("### 4-3. 3단 — 동일 `모델명` 안에서 연차-가격 상관이 사실상 0")
    a("")
    a("규격을 가장 강하게 고정하는 방법은 **같은 모델끼리 비교**하는 것이다.")
    a("모델명별로 age·가격의 평균을 뺀 뒤(모델 고정효과 근사) 상관을 구했다.")
    a("")
    a("| 카테고리2 | 모델 그룹 | 관측 | **모델 내 상관 r** | (참고) 단순 상관 r | n |")
    a("|---|---:|---:|---:|---:|---:|")
    for sub, d in mkt["correl"].items():
        a(
            f"| `{sub}` | {d['groups']} | {d['obs']} | **{d['r_within']:+.2f}** | "
            f"{d['r_pooled']:+.2f} | {d['n_pooled']:,} |"
        )
    a("")
    max_within = max(abs(d["r_within"]) for d in mkt["correl"].values())
    a(
        f"- 감가가 존재한다면 **강한 음의 상관**이 나와야 한다. 실제 모델 내 상관은 `|r| <= {max_within:.2f}` 로"
    )
    a("  사실상 무상관이고, 모델을 고정하지 않은 단순 상관은 오히려 **양수**다(규격 효과).")
    a("- 조건: 같은 모델명이 2건 이상이고 연차가 서로 다른 그룹만 사용.")
    a("")
    a("### 4-4. 결론")
    a("")
    a(
        "**중고 매물 호가는 연차가 아니라 기계 규격(용량·크기)이 지배한다.** 규격 대리변수가 데이터에"
    )
    a(
        "없어 층화로도 회귀로도 감가를 식별할 수 없다. 억지로 단조 감소를 만들면 그것이 바로 D65·D72 가"
    )
    a(
        '금지한 "없는 정확도"다. 그래서 **값 원천을 목업 공식으로 바꾸고(D74), 이 분석은 근거로 남긴다.**'
    )
    a("")
    a("실데이터를 버린 게 아니다 — **실데이터가 무엇을 말할 수 없는지를 기록한 것**이다.")
    a("")

    # ── §5 스키마
    a("## 5. 산출물 스키마 — `data/extracted/residual_curve.json`")
    a("")
    a("```jsonc")
    a("{")
    a('  "_status": "...", "generated_at": "...", "method": "...",')
    a('  "parameters": { "statutory_life_years": 8, "declining_rate": 0.083, ... },')
    a('  "disclosure": "...",     // D65 고지 문구')
    a('  "rows": [                // ← DB §17 residual_curve 시드 입력')
    a("    {")
    a('      "category": "환경  설비",  // 원본 바이트 그대로 (공백 2칸)')
    a('      "age_bucket": "11-15",     // 0-2|3-5|6-10|11-15|16-20|21-30')
    a('      "residual_ratio": 0.3242,  // max((1-r)**대표연차, FLOOR)')
    a('      "n_samples": null, "p25_ratio": null, "p75_ratio": null, "base_n": null,')
    a('      "source": "법정 기준내용연수 8년 기반 정률법 추정 (목업) — 실거래 데이터 아님 [...]"')
    a("    }")
    a("  ]")
    a("}")
    a("```")
    a("")
    a(
        "- ⚠ **`n_samples`·`base_n`·`p25_ratio`·`p75_ratio` 는 전부 `null` 이다.** 목업 공식에는 표본이"
    )
    a("  없으므로 숫자를 채우면 거짓말이 된다(D74).")
    a("  → **`05_DB_SCHEMA.md` §17 의 `n_samples INTEGER NOT NULL`·`base_n INTEGER NOT NULL` 은")
    a("  nullable 로 바꿔야 한다.** MQ-601a 의 DDL 변경 필요 사항이다.")
    a(
        "- PK 는 `(category, age_bucket)`. 전 카테고리 × 전 버킷이 채워져 있어 **격자 공백이 없다** —"
    )
    a(
        "  MQ-601a 는 `acquired_at` 을 자유롭게 배치해도 조인이 비지 않는다(1996년 이후로만 두면 된다)."
    )
    a(
        "- 회귀 스위트에 넣지 않는다 — §4 의 원본 CSV 가 git 제외라 CI 재현이 불가능하다. **JSON 만 커밋한다.**"
    )
    a("- 단, **곡선 생성(§1·§2)은 CSV 없이도 재현된다.** CSV 가 없으면 §4 만 갱신되지 않는다.")
    a("")
    return "\n".join(lines)


# ══════════════════════════════════════════════ main
def rel(path: Path) -> str:
    """저장소 상대경로 표시. 저장소 밖이면 절대경로 그대로 (표시용이라 실패하면 안 된다)."""
    try:
        return str(path.relative_to(ROOT.parent))
    except ValueError:
        return str(path)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):  # Windows 콘솔 cp949/437 방어
        sys.stdout.reconfigure(encoding="utf-8")

    # ── (A) 곡선 — 외부 파일 의존 없음
    curve, meta = build_curve()
    print("[A] 목업 곡선 (D74) — 법정 기준내용연수 기반 정률법")
    print(
        f"  N={STATUTORY_LIFE_YEARS}년  잔가@N={RESIDUAL_AT_LIFE_END}  "
        f"→ r={meta['rate']:.4f}  FLOOR={FLOOR} (age>={meta['floor_binds_from_age']} 에서 구속)"
    )
    print(
        f"  (참고) 세법 잔존율 {TAX_RESIDUAL_AT_N} 유도 시 r={meta['tax_rate']:.4f} → age 20 에서 "
        f"{(1 - meta['tax_rate']) ** 20:.4f}"
    )
    print("  버킷 대표연차 → residual_ratio")
    first = {r["age_bucket"]: r for r in curve if r["category"] == CURVE_CATEGORIES[0]}
    for b, _, _ in BUCKETS:
        print(f"    {b:>6} (age {BUCKET_REP_AGE[b]:>2}) : {first[b]['residual_ratio']:.4f}")
    print("  대상 카테고리 (원본 바이트) —")
    for cat in CURVE_CATEGORIES:
        print(f"    {cat!r}")
    print(f"  행 수: {len(CURVE_CATEGORIES)} × {len(BUCKETS)} = {len(curve)}")

    # ── (B) 한계 실증 — CSV 있을 때만
    print(
        f"\n[B] 한계 실증 — 중진공 호가 데이터 분석  (CSV: {'있음' if CSV_PATH.exists() else '없음'})"
    )
    mkt = analyze_market()
    if mkt is None:
        print(CSV_HINT)
        print("  → (B) 를 건너뛴다. (A) 는 정상 산출된다.")
    else:
        print(f"  ① 표본 감소: {mkt['total']:,} → {mkt['n1']:,} → {mkt['n2']:,} → {mkt['n3']:,}")
        if mkt["n3"] != EXPECTED_FINAL_N:
            print(
                f"  ⚠ 경고: 유효 표본 {mkt['n3']:,} != 실측 기준 {EXPECTED_FINAL_N:,} — 원본 갱신 가능성"
            )
        missing = [c for c in CURVE_CATEGORIES if c not in mkt["cat_counts"]]
        if missing:
            print(f"  ⚠ 경고: 곡선 카테고리 상수가 원본 CSV 에 없다 → {[repr(c) for c in missing]}")
        else:
            print(f"  ② 곡선 카테고리 {len(CURVE_CATEGORIES)}종 전부 원본 `카테고리1` 에 실재 확인")
        for cat in mkt["grid"]:
            g = mkt["grid"][cat]
            cells = " ".join(
                f"{b}={g[b]['ratio']:.2f}" if "ratio" in g[b] else f"{b}=—" for b, _, _ in BUCKETS
            )
            print(f"    {cat!r} 호가비율 {cells}")
        for sub, d in mkt["correl"].items():
            print(
                f"  ③ {sub!r} 모델 내 연차-가격 상관 r={d['r_within']:+.2f} (그룹 {d['groups']}, 관측 {d['obs']})"
            )

    # ── 산출물
    payload = {
        "_status": "D74 목업 공식 산출 — 실거래 데이터 아님. 값 원천은 §2 의 가정 3개",
        "generated_at": date.today().isoformat(),
        "method": "declining_balance_mock_from_statutory_life",
        "parameters": {
            "statutory_life_years": STATUTORY_LIFE_YEARS,
            "residual_at_life_end": RESIDUAL_AT_LIFE_END,
            "declining_rate": round(meta["rate"], 6),
            "floor": FLOOR,
            "floor_binds_from_age": meta["floor_binds_from_age"],
            "bucket_rep_age": BUCKET_REP_AGE,
            "reference_year": REFERENCE_YEAR,
            "smoothing": "none",
            "formula": "residual(age) = max((1 - r) ** age, floor); r = 1 - residual_at_life_end ** (1/N)",
        },
        "disclosure": (
            "법정 기준내용연수 기반 정률법 목업 추정치이며 실거래가·시세가 아니다. "
            "취득원가 대비 비율이며, 표본 통계가 아니므로 n_samples/base_n/p25/p75 는 null 이다 (D65·D74)."
        ),
        "empirical_note": (
            "중진공 자산거래중개장터 호가 데이터는 값 원천이 아니라 한계 실증으로만 쓴다 — "
            "호가는 연차가 아니라 기계 규격이 지배해 감가를 식별할 수 없다. "
            "근거: data/analysis/residual_curve.md §4"
        ),
        "counts": {
            "categories": len(CURVE_CATEGORIES),
            "buckets": len(BUCKETS),
            "rows": len(curve),
        },
        "rows": curve,
    }
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n[출력] {rel(JSON_OUT)}  rows={len(curve)}")

    if mkt is not None:
        MD_OUT.parent.mkdir(parents=True, exist_ok=True)
        MD_OUT.write_text(render_md(curve, meta, mkt), encoding="utf-8")
        print(f"[출력] {rel(MD_OUT)}")
    else:
        print(f"[보존] {rel(MD_OUT)} — CSV 부재로 한계 실증 절을 재생성할 수 없어")
        print("       기존 파일을 덮어쓰지 않았다. 파라미터를 바꿨다면 CSV 를 두고 다시 실행할 것.")

    # 자가검증
    assert len(curve) == len(CURVE_CATEGORIES) * len(BUCKETS)
    assert all(FLOOR <= r["residual_ratio"] <= 1.0 for r in curve)
    ratios = [first[b]["residual_ratio"] for b, _, _ in BUCKETS]
    assert ratios == sorted(ratios, reverse=True), "곡선이 단조 감소하지 않는다"
    assert all(r["n_samples"] is None and r["base_n"] is None for r in curve), (
        "목업에 표본 수를 채우면 안 된다"
    )
    print("[자가검증] 36행 · 단조 감소 · FLOOR<=ratio<=1 · 표본 필드 전부 null ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
