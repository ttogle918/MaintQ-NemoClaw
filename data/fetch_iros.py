# -*- coding: utf-8 -*-
"""등기정보광장(IROS) 동산·채권담보등기 통계 수집 (A6) — 멱등 재실행 가능.

**왜 지금 받는가.** 이 API 는 **최근 3년치만** 제공한다(`APIERROR-0014`). 지금은
2023-08 부터 받히지만 1년 뒤엔 2024-08 부터만 받힌다 — **오늘 받아 둔 스냅샷은
영구 보존되고, 안 받으면 영영 사라진다.** 소비처(기능 12 · S18 `residual_risk`)가
아직 없어도 수집을 먼저 하는 이유가 이것이다.

**저장 구조는 법령과 같다 (D60).** 파일이 정본이고 DB 는 조회용 사본이다 —
`data/iros/<slug>.json` 이 커밋되는 스냅샷이고, DB 적재는 소비처가 생길 때 붙인다.
`data_list.md` 원칙 1 도 같은 말이다: 수집은 개발 시점 작업이고 런타임 서버는
커밋된 스냅샷만 읽는다. 요청마다 외부 기관을 호출하면 재현이 깨진다.

⚠ **실호출로 확정한 것 (2026-08-12) — 기관 명세와 다르다.**
  1. `0000000239` 에는 명세에 없는 **`bondAmtSectName`**(채권최고액 구간)이 있다.
     이게 없으면 "금액 구간별" 이라는 서비스 자체가 성립하지 않는다.
  2. **`tot` 의 의미가 서비스마다 다르다.** `0000000212` 는 266(건수),
     `0000000242` 는 26417625864986(원)이다. 같은 필드명이 다른 것을 담는다 —
     그래서 스냅샷에 `tot_unit` 을 박아 둔다. 이걸 안 적으면 다음 사람이 26조를
     건수로 읽는다.
  3. 🔴 **`0000000239`(채권최고액별)는 값이 통째로 비어서 온다.** 첫 레코드만 그런 게
     아니었다 — `totalCount: 34` · `returnCode: APIINFO-0001`(정상)인데 **34행 전부**
     `{"resDate":"", "srprsCls":"", "bondAmtSectName":"", "tot":""}` 다.
     ⛔ **"정상 응답 + totalCount > 0" 을 데이터가 있다는 뜻으로 읽으면 안 된다.**
     기관측 결함으로 보이며 우리가 파싱으로 고칠 수 있는 게 아니다. 빈 행을 거르면
     0행이 남는 것이 정직한 결과다 — 빈 문자열을 0 으로 채우면 없는 사실이 생긴다.
     `data_list.md §A6` 이 이 서비스를 ⭐2순위로 뒀는데, **현재로선 쓸 수 없다.**

⛔ **인용 금지선** — 6종 전부 "동산·채권 **합산**" 이고 동산 중 기계설비 비중은
   공개되지 않는다(재고자산·원자재·농축산물이 함께 들어감).
     ❌ "기계설비 담보가 연 N건"
     ✅ "동산담보 등기가 연 N건 규모이며, 이 중 기계설비 비중은 공개 통계로 확인되지 않는다"
   이 문장을 스냅샷 메타에도 넣어 둔다 — 파일만 보고 인용하는 경우를 막는다.

실행:
    uv run --with httpx python data/fetch_iros.py --dry-run   # 계획만, 호출 0회
    uv run --with httpx python data/fetch_iros.py             # 실수집
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=ROOT / ".env", override=False)

OUT_DIR = ROOT / "data" / "iros"
URL = "https://data.iros.go.kr/openapi/cr/rs/selectCrRsRgsCsOpenApi.rest"

#: 하루 1,000회 한도. 서비스 4 × 연도 4 = 16회면 충분히 여유롭다.
DAILY_LIMIT_NOTE = "일 1,000회 · 1회 최대 1,000건"

CITATION_GUARD = (
    "동산·채권 합산 통계다. 동산 중 기계설비 비중은 공개되지 않는다 — "
    "'기계설비 담보가 연 N건' 으로 인용하면 사실 왜곡이다."
)

#: (서비스ID, .env 키, slug, 라벨, tot 단위)
#: ⚠ tot_unit 은 실호출로 확인한 값이다. 명세에는 넷 다 "결과 건수" 로 적혀 있었다.
SERVICES = [
    ("0000000212", "IROS_API_KEY_APPLY_CASES", "apply_cases", "신청사건 현황", "건"),
    ("0000000239", "IROS_API_KEY_APPLY_BY_AMOUNT", "apply_by_amount", "신청현황(채권최고액별)", "건"),
    ("0000000213", "IROS_API_KEY_STATUS_BY_GRANTOR", "status_by_grantor", "현황(담보권설정자 유형별)", "건"),
    ("0000000242", "IROS_API_KEY_DEBT_BY_GRANTOR", "debt_by_grantor", "누적채권액 현황(설정자 유형별)", "원"),
]

OK_CODES = {"APIINFO-0001"}
EMPTY_CODE = "APIINFO-0003"  # ⛔ "0건" 이 아니라 "조회 결과가 없다" 다


def month_windows(today: date, years: int = 3) -> list[tuple[str, str]]:
    """연 단위 창으로 쪼갠다 — 3년을 한 번에 요청하면 `APIERROR-0010`(출력 과다)이 난다."""
    start_y, start_m = today.year - years, today.month
    end_y, end_m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    out: list[tuple[str, str]] = []
    for y in range(start_y, end_y + 1):
        lo_m = start_m if y == start_y else 1
        hi_m = end_m if y == end_y else 12
        if lo_m > hi_m:
            continue
        out.append((f"{y}{lo_m:02d}", f"{y}{hi_m:02d}"))
    return out


def _records(payload: object) -> list[dict]:
    """응답 어디에 있든 레코드 리스트를 찾아낸다 (래핑 구조에 의존하지 않는다)."""
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for v in payload.values():
            got = _records(v)
            if got:
                return got
    return []


def _code(payload: object) -> str | None:
    if isinstance(payload, dict):
        for k, v in payload.items():
            if isinstance(v, str) and v.startswith("API"):
                return v
            got = _code(v)
            if got:
                return got
    elif isinstance(payload, list):
        for v in payload[:3]:
            got = _code(v)
            if got:
                return got
    return None


def fetch_window(svc_id: str, key: str, lo: str, hi: str, timeout: float) -> tuple[list[dict], str]:
    params = {
        "id": svc_id,
        "key": key,
        "reqtype": "json",
        "search_type_api": "02",  # 월별 — 4종 모두 지원하는 유일한 공통 구분
        "search_start_date_api": lo,
        "search_end_date_api": hi,
    }
    r = httpx.get(URL, params=params, timeout=timeout)
    r.raise_for_status()
    payload = r.json()
    code = _code(payload) or "?"
    if code == EMPTY_CODE:
        return [], code
    if code not in OK_CODES:
        raise RuntimeError(f"{code}: {json.dumps(payload, ensure_ascii=False)[:160]}")
    # ⚠ 239 는 첫 레코드가 전 필드 빈 문자열로 온다 — 거른다.
    return [r for r in _records(payload) if any((v or "").strip() for v in r.values())], code


def collect(svc, windows, timeout: float) -> dict:
    svc_id, env_key, slug, label, unit = svc
    key = os.environ.get(env_key)
    if not key:
        raise RuntimeError(f"{env_key} 미설정")
    rows: list[dict] = []
    empty_windows: list[str] = []
    for lo, hi in windows:
        got, code = fetch_window(svc_id, key, lo, hi, timeout)
        if code == EMPTY_CODE:
            empty_windows.append(f"{lo}~{hi}")
        rows.extend(got)
    return {
        "service_id": svc_id,
        "service_label": label,
        "slug": slug,
        "source_url": URL,
        "search_type_api": "02 (월별)",
        "windows": [f"{lo}~{hi}" for lo, hi in windows],
        # ⛔ "조회 결과 없음" 은 0건이 아니다. 어느 창이 비었는지 남긴다.
        "empty_windows": empty_windows,
        "tot_unit": unit,
        "tot_note": (
            "tot 의 단위는 서비스마다 다르다 — 실호출로 확인한 값이 tot_unit 이다. "
            "기관 명세에는 4종 모두 '결과 건수' 로 적혀 있었으나 누적채권액은 원이다."
        ),
        "citation_guard": CITATION_GUARD,
        "rate_limit": DAILY_LIMIT_NOTE,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "record_count": len(rows),
        "fields": sorted({k for r in rows for k in r}),
        "records": rows,
    }


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="IROS 동산·채권담보등기 통계 수집 (A6)")
    ap.add_argument("--dry-run", action="store_true", help="계획만 출력 — 호출 0회")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--years", type=int, default=3, help="소급 연수 (API 상한 3년)")
    args = ap.parse_args()

    windows = month_windows(date.today(), args.years)
    print(f"수집 창 {len(windows)}개: {[f'{a}~{b}' for a, b in windows]}")
    print(f"서비스 {len(SERVICES)}종 × 창 {len(windows)}개 = 호출 {len(SERVICES) * len(windows)}회 ({DAILY_LIMIT_NOTE})")

    if args.dry_run:
        for svc_id, env_key, slug, label, unit in SERVICES:
            has = "OK" if os.environ.get(env_key) else "❌ 키 없음"
            print(f"  {svc_id}  {label:<28} → iros/{slug}.json  tot 단위={unit}  {has}")
        print("[--dry-run] 호출하지 않았습니다.")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print()
    for svc in SERVICES:
        slug, label = svc[2], svc[3]
        path = OUT_DIR / f"{slug}.json"
        try:
            snap = collect(svc, windows, args.timeout)
        except Exception as exc:  # noqa: BLE001 — 한 서비스 실패가 나머지를 막지 않는다
            print(f"  ❌ {label}: {type(exc).__name__}: {exc}")
            continue
        # 멱등 — records 가 같으면 retrieved_at 만 바뀌므로 파일을 다시 쓰지 않는다.
        prev = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        if prev and prev.get("records") == snap["records"]:
            print(f"  = {label}: UNCHANGED ({snap['record_count']}행)")
            continue
        path.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        mark = "갱신" if prev else "신규"
        print(f"  ✓ {label}: {mark} {snap['record_count']}행 · 필드 {snap['fields']}")
        if snap["empty_windows"]:
            print(f"      ⚠ 조회 결과 없음(0건 아님): {snap['empty_windows']}")


if __name__ == "__main__":
    main()
