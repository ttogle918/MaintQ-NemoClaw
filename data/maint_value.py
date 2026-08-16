# -*- coding: utf-8 -*-
"""maint_value — 보전지표·부품 등급·지출 판정·수리가치 판단 **공유 데이터 계층** (MQ-903·MQ-922, D101).

`mcp_server/tools/{get_maintenance_metrics,classify_part_criticality,classify_expenditure,
assess_repair_value}.py` 가 이 모듈로 얇게 위임한다 — `data/ownership.py`(MQ-707b)와 같은
형태다. 소비자가 늘면(예: 향후 REST 노출) 판정 로직을 두 곳에 복제하지 않기 위해 여기 한 곳에
둔다 (D73).

⚠ **범위** — 이 모듈은 4종을 다룬다: `maintenance_metrics`·`part_criticality`·`expenditure`
(MQ-903)·`repair_value`(MQ-922, `assess_repair_value` 위임).

⛔ 이 모듈은 `mcp_server` 를 import 하지 않는다(D15 — 두 런타임 프로세스의 상호 import 금지).
   커넥션은 호출자가 **읽기 전용**으로 열어 넘긴다(`data/ownership.py` 와 같은 규약) —
   `mcp_server.db.read_only()` 도 import 하지 않는다. 이 모듈은 DB 경로를 모른다.
   `repair_value()` 는 하위 판정(`part_criticality`·`maintenance_metrics`)을 **같은 커넥션으로
   함수 호출**한다 — 원본 도구가 열던 `read_only()` 2회 + 하위 도구가 각자 열던 커넥션은
   호출자(`mcp_server/tools/assess_repair_value.py`)가 여는 **하나**로 합쳐진다 (MQ-922).

★ 반복 고장 문턱(30일 3회, D2·D29)의 **정본은 `mcp_server/tools/get_error_history.py`** 다.
   이 모듈은 `mcp_server` 를 import 할 수 없어(D15) 값을 여기서 다시 정의하지 않고
   **`data/ownership.py:70~71` 의 기존 상수를 그대로 재사용**한다(새 사본을 만들지 않는다 —
   `verify_ownership.py` 가 이미 같은 이유로 같은 상수를 재사용하고 있다). 드리프트 방지는
   규율이 아니라 **import 시점 단언**으로 잠근다 — `mcp_server/tools/get_maintenance_metrics.py`
   가 `verify_ownership.py:34` 와 같은 형태의 assert 를 건다.

실패는 예외가 아니라 `status` 필드로 반환한다(D9) — 다만 예외를 `status` 로 닫는 **바깥
껍데기**는 각 함수 안에 있다(원본 도구 파일의 try/except 경계를 그대로 옮겼다). 이 파일의
목표는 리팩터이지 기능 변경이 아니다 — **출력 dict 를 한 글자도 바꾸지 않는다.**
"""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, date, timedelta
from fractions import Fraction

# ★ 새 사본을 만들지 않는다 — data/ownership.py:70~71 의 기존 상수를 그대로 재사용한다.
from data.ownership import REPEAT_THRESHOLD, REPEAT_WINDOW_DAYS
from data.rules.engine import ASSET_FACT_COLUMNS, build_facts, get_law_as_of, load_laws_from_db

__all__ = [
    "REPEAT_THRESHOLD",
    "REPEAT_WINDOW_DAYS",
    "DEFAULT_WINDOW_MONTHS",
    "maintenance_metrics",
    "part_criticality",
    "expenditure",
    "repair_value",
]


def _fail(reason: str, message: str, status: str = "error") -> dict:
    return {"status": status, "reason": reason, "message": message}


# ══════════════════════════════════════════════════════════════════════════
# maintenance_metrics — 원본: mcp_server/tools/get_maintenance_metrics.py (MQ-607)
# ══════════════════════════════════════════════════════════════════════════

DEFAULT_WINDOW_MONTHS = 24

# 추세 비교 창 — window_months 와 무관하게 12+12 로 고정한다 (계약 문언: "최근 12개월 vs 이전 12개월").
TREND_WINDOW_MONTHS = 12
# 추세 판정 밴드. 최근 MTBF 가 직전 대비 10% 이상 짧아지면 악화(declining), 10% 이상 길어지면 개선.
TREND_BAND = 0.10

HOURS_PER_DAY = 24.0  # 가용도 계산의 단위 환산 상수 (MTTR[시간] → 일)

MTBF_BASIS = "calendar_days"

_METRICS_NOT_CONSIDERED_BASE = [
    "가동시간·스핀들 시간(원천 없음 — 달력 기준 MTBF 로 대체, D70)",
    "OEE(거래 판정 사용 금지 — D64)",
    "생산량·부하율·작업자 숙련도 등 설비 외 요인",
    f"mtbf_trend 는 window_months 와 무관하게 최근 {TREND_WINDOW_MONTHS}개월 대 "
    f"직전 {TREND_WINDOW_MONTHS}개월 고정 비교다",
]

_METRICS_DISCLAIMER = (
    "MTBF 는 가동시간이 아니라 달력 기준 평균 고장 간격이다(D70). "
    "가동률이 다른 기간·설비 사이의 직접 비교에는 쓸 수 없다. "
    "null 과 insufficient_data 는 '양호'가 아니라 '판단 근거 부족'이다."
)

_METRICS_DT_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d")


def _as_int(value: object) -> int | None:
    """정수로 해석되면 int, 아니면 None. 추정하지 않는다 (get_error_history 와 같은 태도)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in _METRICS_DT_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _mean_gap_days(moments: list[datetime]) -> float | None:
    """인접 발생 간격(일)의 평균 = 달력 기준 MTBF (D70).

    이벤트가 2건 미만이면 간격 자체가 없으므로 **None**. 0 으로 채우면
    "고장 간격 0일"이라는 최악의 신호가 되고, 큰 수로 채우면 없는 안정성이 생긴다.
    """
    if len(moments) < 2:
        return None
    gaps = [
        (later - earlier).total_seconds() / 86400.0
        for earlier, later in zip(moments, moments[1:], strict=False)
    ]
    return sum(gaps) / len(gaps)


def _months_ago(anchor: datetime, months: int) -> datetime:
    """달력 기준 N개월 전. 말일 보정은 그 달의 마지막 날로 자른다(1/31 → 2/28)."""
    total = anchor.year * 12 + (anchor.month - 1) - months
    year, month = divmod(total, 12)
    month += 1
    # 해당 월에 존재하지 않는 일자(31일 등)는 말일로 내린다
    day = anchor.day
    while day > 0:
        try:
            return anchor.replace(year=year, month=month, day=day)
        except ValueError:
            day -= 1
    return anchor.replace(year=year, month=month, day=1)


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def _resolve_metrics_asset(
    con: sqlite3.Connection, asset_id: str | None, equipment_id: str | None
) -> tuple[str | None, dict | None]:
    """(asset_id, 실패 응답) — 실패 응답이 None 이 아니면 그대로 반환한다."""
    if asset_id:
        row = con.execute("SELECT asset_id FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
        if row is None:
            return None, _fail(
                "unknown_asset",
                f"등록되지 않은 자산입니다: {asset_id}",
                status="not_found",
            )
        return row["asset_id"], None

    row = con.execute(
        "SELECT asset_id FROM equipment WHERE equipment_id = ?", (equipment_id,)
    ).fetchone()
    if row is None:
        return None, _fail(
            "unknown_equipment",
            f"등록되지 않은 설비입니다: {equipment_id}",
            status="not_found",
        )
    if not row["asset_id"]:
        # 호스트 자산이 없는 인버터(분전반 등) — 자산 단위 지표를 산출할 대상이 없다 (D68)
        return None, _fail(
            "no_host_asset",
            f"{equipment_id} 에는 연결된 호스트 자산이 없습니다. 자산 단위 보전지표를 산출할 수 없습니다.",
            status="not_found",
        )
    return row["asset_id"], None


def _fetch_metrics_data(
    con: sqlite3.Connection, asset_id: str | None, equipment_id: str | None
) -> dict | tuple:
    """DB 조회 구간 — 원본의 `with read_only() as con: ... except Exception: db_error` 경계와
    동일한 보호 범위를 유지한다. 실패 dict 또는 조회 결과 튜플을 반환한다."""
    try:
        resolved, failure = _resolve_metrics_asset(con, asset_id, equipment_id)
        if failure is not None:
            return failure

        asset = con.execute(
            "SELECT acquisition_cost, cumulative_repair_cost FROM assets WHERE asset_id = ?",
            (resolved,),
        ).fetchone()

        equipment_ids = [
            r["equipment_id"]
            for r in con.execute(
                "SELECT equipment_id FROM equipment WHERE asset_id = ? ORDER BY equipment_id",
                (resolved,),
            ).fetchall()
        ]

        # SQLite 의 'now' 를 기준 시각으로 삼는다 — get_error_history 의 datetime('now') 와
        # 같은 기준이어야 repeat_failure 판정이 두 도구 사이에서 어긋나지 않는다 (D2·D29).
        now = _parse_dt(con.execute("SELECT datetime('now')").fetchone()[0])
        if now is None:
            return _fail("db_error", "기준 시각(datetime('now')) 을 해석하지 못했습니다")

        events: list[tuple[str, datetime]] = []
        unparsed_events = 0
        repairs: list[dict] = []
        if equipment_ids:
            marks = ",".join("?" * len(equipment_ids))
            for r in con.execute(
                f"SELECT equipment_id, occurred_at FROM error_history "  # noqa: S608 — 자리표시자만 삽입
                f"WHERE equipment_id IN ({marks}) ORDER BY occurred_at ASC",
                equipment_ids,
            ).fetchall():
                moment = _parse_dt(r["occurred_at"])
                if moment is None:
                    unparsed_events += 1
                    continue
                events.append((r["equipment_id"], moment))

            repairs = [
                dict(r)
                for r in con.execute(
                    f"SELECT work_type, downtime_hours, signed_at FROM repair_records "  # noqa: S608
                    f"WHERE equipment_id IN ({marks})",
                    equipment_ids,
                ).fetchall()
            ]
    except Exception as e:  # noqa: BLE001 — 예외를 status 로 바꿔 반환 (D9)
        return _fail("db_error", str(e))

    return resolved, asset, equipment_ids, now, events, unparsed_events, repairs


def maintenance_metrics(
    con: sqlite3.Connection,
    *,
    asset_id: str | None = None,
    equipment_id: str | None = None,
    window_months: int | str = DEFAULT_WINDOW_MONTHS,
) -> dict:
    # 타입이 어긋난 식별자를 그대로 조회하면 "등록되지 않은 자산"(not_found)이 되어
    # 입력 오류가 데이터 부재로 둔갑한다 — 에이전트가 자산이 없다고 서술하게 되므로 분리한다.
    for label, value in (("asset_id", asset_id), ("equipment_id", equipment_id)):
        if value is not None and not isinstance(value, str):
            return _fail("invalid_input", f"{label} 는 문자열 식별자입니다: {value!r}")
    asset_id = asset_id.strip() if asset_id else None
    equipment_id = equipment_id.strip() if equipment_id else None

    if not asset_id and not equipment_id:
        return _fail("invalid_input", "asset_id 또는 equipment_id 중 하나는 필요합니다")

    months = _as_int(window_months)
    if months is None or months <= 0:
        return _fail(
            "invalid_input",
            f"window_months 는 양의 정수(조회 개월 수)입니다: {window_months!r}",
        )

    fetched = _fetch_metrics_data(con, asset_id, equipment_id)
    if isinstance(fetched, dict):
        return fetched
    resolved, asset, equipment_ids, now, events, unparsed_events, repairs = fetched

    excluded: list[str] = []
    not_considered = list(_METRICS_NOT_CONSIDERED_BASE)

    # ── 1) MTBF (D70): window_months 안의 이벤트, 인접 간격(일)의 평균 ──────────────
    window_start = _months_ago(now, months)
    windowed = sorted(m for _, m in events if m >= window_start)
    mtbf_days = _mean_gap_days(windowed)

    # ── 2) 추세: 최근 12개월 MTBF vs 직전 12개월 MTBF ────────────────────────────
    recent_start = _months_ago(now, TREND_WINDOW_MONTHS)
    prior_start = _months_ago(now, TREND_WINDOW_MONTHS * 2)
    recent = sorted(m for _, m in events if m >= recent_start)
    prior = sorted(m for _, m in events if prior_start <= m < recent_start)
    recent_mtbf = _mean_gap_days(recent)
    prior_mtbf = _mean_gap_days(prior)
    if recent_mtbf is None or prior_mtbf is None or prior_mtbf == 0:
        # 어느 한쪽이라도 이벤트 <2건이면 비교 자체가 성립하지 않는다.
        # ⛔ "stable" 로 대체하지 않는다 — 모른다를 안정으로 바꾸는 순간 지표가 거짓말을 한다.
        mtbf_trend = "insufficient_data"
    else:
        ratio = recent_mtbf / prior_mtbf
        if ratio <= 1 - TREND_BAND:
            mtbf_trend = "declining"  # 고장 간격이 짧아짐 = 악화
        elif ratio >= 1 + TREND_BAND:
            mtbf_trend = "improving"
        else:
            mtbf_trend = "stable"

    # ── 3) MTTR: 서명된 수리 레코드의 downtime_hours 평균 (12 §11) ────────────────
    signed = [r for r in repairs if r["signed_at"]]
    unsigned_n = len(repairs) - len(signed)
    downtimes = [float(r["downtime_hours"]) for r in signed if r["downtime_hours"] is not None]
    mttr_hours = sum(downtimes) / len(downtimes) if downtimes else None

    if unsigned_n:
        excluded.append(
            f"서명되지 않은 수리 레코드 {unsigned_n}건은 지표에서 제외했다 "
            "(MTTR·예방보전 비율 분모 모두 — 12 §11)"
        )
    if signed and not downtimes:
        excluded.append(
            "서명된 수리 레코드에 downtime_hours 가 하나도 없어 MTTR 을 산출하지 못했다"
        )
    if unparsed_events:
        excluded.append(
            f"occurred_at 을 해석하지 못한 에러 이력 {unparsed_events}건은 집계에서 제외했다"
        )
    # repair_records 에는 시각 컬럼이 없다(DDL 은 계약이므로 컬럼을 추가하지 않는다).
    # signed_at 은 '서명 시각'이지 '수리 시각'이 아니라 기간 절단 근거로 쓸 수 없다.
    excluded.append(
        "repair_records 에 수리 시각 컬럼이 없어 window_months 로 자를 수 없다 — "
        "MTTR·예방보전 비율·누적 수리비는 전 기간 집계다"
    )

    # ── 4) 가용도 ────────────────────────────────────────────────────────────────
    # ⚠ 단위가 다르다: mtbf_days 는 **일(day)**, mttr_hours 는 **시간(hour)**.
    #   그대로 더하면 수리 시간이 24배로 부풀어 가용도가 조용히 낮아진다.
    #   그래서 MTTR 을 일로 환산(hours / 24)한 뒤 같은 단위끼리 계산한다.
    #   availability = MTBF[일] / (MTBF[일] + MTTR[일])
    if mtbf_days is None or mttr_hours is None:
        # 둘 중 하나라도 없으면 null. MTTR 을 0 으로 두면 "무중단"이라는 없는 사실이 생긴다.
        availability = None
        if mtbf_days is None:
            not_considered.append("가용도(MTBF 미산출 — 고장 이벤트 2건 미만)")
        else:
            not_considered.append("가용도(MTTR 미산출 — 서명된 수리 레코드의 downtime 없음)")
    else:
        mttr_days = mttr_hours / HOURS_PER_DAY  # 시간 → 일
        availability = mtbf_days / (mtbf_days + mttr_days)

    # ── 5) 예방보전 비율: PLANNED / (PLANNED + UNPLANNED), 서명분만 (12 §11) ──────
    planned = sum(1 for r in signed if r["work_type"] == "PLANNED")
    unplanned = sum(1 for r in signed if r["work_type"] == "UNPLANNED")
    denominator = planned + unplanned
    planned_ratio = planned / denominator if denominator else None
    if planned_ratio is None:
        excluded.append("서명된 수리 레코드가 없어 예방보전 비율을 산출하지 못했다")

    # ── 6) 반복 고장: 판정은 **인버터 단위**(D68 ⓑ), 상수는 get_error_history 재사용 ──
    repeat_since = now - timedelta(days=REPEAT_WINDOW_DAYS)
    per_equipment: dict[str, int] = {}
    for eq, moment in events:
        if moment >= repeat_since:
            per_equipment[eq] = per_equipment.get(eq, 0) + 1
    repeat_failure = any(n >= REPEAT_THRESHOLD for n in per_equipment.values())

    # ── 7) 누적 수리비 ───────────────────────────────────────────────────────────
    acquisition_cost = asset["acquisition_cost"] if asset else None
    cumulative_repair_cost = (asset["cumulative_repair_cost"] if asset else None) or 0
    if acquisition_cost:
        cumulative_repair_ratio = cumulative_repair_cost / acquisition_cost
    else:
        # 취득원가가 없으면 비율을 만들지 않는다 (분모를 지어내지 않는다)
        cumulative_repair_ratio = None
        not_considered.append("누적 수리비 비율(acquisition_cost 없음)")

    if not equipment_ids:
        excluded.append(
            f"{resolved} 에 연결된 설비(equipment)가 없어 이력 기반 지표를 산출하지 못했다"
        )

    return {
        "status": "ok",  # 값이 null·insufficient_data 여도 도구는 성공이다 (데이터 부족 ≠ 실패)
        "asset_id": resolved,
        "window_months": months,
        "mtbf_days": _round(mtbf_days, 1),
        "mtbf_basis": MTBF_BASIS,  # D70 — 가동시간 기준이 아님을 계약 수준에서 고지
        "mtbf_trend": mtbf_trend,
        "mttr_hours": _round(mttr_hours, 2),
        "availability": _round(availability, 4),
        "planned_ratio": _round(planned_ratio, 3),
        "n_repairs_signed": len(signed),
        "n_repairs_unsigned": unsigned_n,
        "cumulative_repair_cost": cumulative_repair_cost,
        "acquisition_cost": acquisition_cost,
        "cumulative_repair_ratio": _round(cumulative_repair_ratio, 3),
        "repeat_failure": repeat_failure,
        "excluded": excluded,
        "not_considered": not_considered,
        "disclaimer": _METRICS_DISCLAIMER,
    }


# ══════════════════════════════════════════════════════════════════════════
# part_criticality — 원본: mcp_server/tools/classify_part_criticality.py (MQ-606)
# ══════════════════════════════════════════════════════════════════════════

# parts.part_class 에 허용된 값 (`12 §9`). 이 밖의 값은 "모른다"이지 새 등급이 아니다.
# (classify_expenditure 도 같은 값을 쓴다 — 두 도구가 같은 등급 어휘를 공유하므로 여기 한 곳에 둔다.)
PART_CLASSES = ("CONSUMABLE", "CRITICAL")

# `related_parts.seed.json` 의 reviewed 플래그와 같은 성격 — 사람 검수 전이다.
CRITICALITY_REVIEWED = False
CRITICALITY_REVIEW_NOTE = "part_class 는 미검수 초안"

CRITICALITY_NOT_CONSIDERED = [
    "부품 이름·카테고리로부터의 등급 추론 (금지 — 등록된 값만 사용, D12)",
    "설비별 중요도 차이 (같은 부품이라도 라인 위치에 따라 다를 수 있으나 원천 없음)",
    "재고 수량·리드타임 (search_inventory·get_supplier_quotes 소관)",
]

CRITICALITY_DISCLAIMER = (
    "part_class 는 사람 검수를 거치지 않은 초안이다(reviewed=false). "
    "수리/교체/처분 판단에 쓸 때는 등급 자체를 정비 담당자가 확인한 뒤 확정할 것."
)


def part_criticality(con: sqlite3.Connection, *, part_no: str) -> dict:
    """공개 진입점 — **얇은 래퍼**.

    본체를 통째로 감싸 입력 파싱·응답 조립에서 난 예외까지 status 로 닫는다 (D9·D46).
    DB 블록만 try 로 감싸면 "어떤 입력에도 예외가 새지 않음"이 코드 위치에 의존하게 되고,
    나중에 조립부에 한 줄이 추가되는 순간 조용히 깨진다.
    """
    try:
        return _part_criticality(con, part_no)
    except Exception as e:  # noqa: BLE001 — 도구는 예외를 던지지 않는다
        return _fail("internal_error", f"부품 등급 조회 중 처리 오류: {e}")


def _part_criticality(con: sqlite3.Connection, part_no: str) -> dict:
    if not isinstance(part_no, str) or not part_no.strip():
        return _fail(
            "invalid_input",
            f"part_no 는 비어 있지 않은 부품 번호 문자열입니다: {part_no!r}",
        )
    part_no = part_no.strip()

    try:
        row = con.execute(
            "SELECT part_no, name, category, part_class, discontinued "
            "FROM parts WHERE part_no = ?",
            (part_no,),
        ).fetchone()
    except Exception as e:  # noqa: BLE001 — 예외를 status 로 바꿔 반환 (D9)
        return _fail("db_error", str(e))

    if row is None:
        # 유사 부품번호를 추측해 돌려주지 않는다 (미지 에러코드 규칙과 같은 태도)
        return _fail(
            "unknown_part",
            f"등록되지 않은 부품 번호입니다: {part_no}. 부품 번호를 확인하거나 이름으로 검색하세요.",
            status="not_found",
        )

    part_class = (row["part_class"] or "").strip().upper()
    if not part_class:
        # ★ 여기서 추측하면 assess_repair_value 의 3지 판단이 근거를 잃는다 (D12)
        return _fail(
            "part_class_not_set",
            f"{part_no} 의 부품 등급(part_class)이 등록돼 있지 않습니다. "
            "등급을 추정하지 않으니 자재 담당자가 등급을 등록한 뒤 다시 조회하세요.",
        )
    if part_class not in PART_CLASSES:
        return _fail(
            "part_class_invalid",
            f"{part_no} 의 part_class 가 허용 값({' | '.join(PART_CLASSES)}) 밖입니다: "
            f"{row['part_class']!r}. 데이터를 바로잡기 전에는 등급 없이 진행하세요.",
        )

    return {
        "status": "ok",
        "part_no": row["part_no"],
        "part_class": part_class,
        "basis": "parts.part_class (데이터 조회)",
        "name": row["name"],
        "category": row["category"],
        "discontinued": bool(row["discontinued"]),  # D20 — 단종 분기 판단 근거
        "reviewed": CRITICALITY_REVIEWED,
        "note": CRITICALITY_REVIEW_NOTE,
        "not_considered": list(CRITICALITY_NOT_CONSIDERED),
        "disclaimer": CRITICALITY_DISCLAIMER,
    }


# ══════════════════════════════════════════════════════════════════════════
# expenditure — 원본: mcp_server/tools/classify_expenditure.py (MQ-608)
# ══════════════════════════════════════════════════════════════════════════

EXPENDITURE_LAW_REF_ID = "KR-CITA-ENF-31"  # 법인세법 시행령 제31조 (즉시상각의제)

REPAIR_SCOPES = ("RESTORE", "UPGRADE", "OVERHAUL", "REPLACE_UNIT")
EXPENDITURE_VERDICTS = ("CAPITAL", "REVENUE", "HOLD")

# 취득원가 대비 지출 비율 문턱. Fraction 으로 두는 이유는 아래 `_materiality` 주석 참조.
MATERIALITY_THRESHOLD = Fraction(1, 5)  # 0.20

# (repair_scope, part_class) 8조합을 전부 명시한다. `if` 로 접으면 "어느 조합이 어디로 가는지"가
# 코드를 읽어야만 보이고, 나중에 조합이 늘 때 조용히 빠지는 칸이 생긴다.
_EXPENDITURE_RULE_TABLE: dict[tuple[str, str], tuple[str, str]] = {
    ("UPGRADE", "CONSUMABLE"): ("CAPITAL", "UPGRADE"),
    ("UPGRADE", "CRITICAL"): ("CAPITAL", "UPGRADE"),
    ("OVERHAUL", "CONSUMABLE"): ("CAPITAL", "OVERHAUL"),
    ("OVERHAUL", "CRITICAL"): ("CAPITAL", "OVERHAUL"),
    ("RESTORE", "CONSUMABLE"): ("REVENUE", "RESTORE_CONSUMABLE"),
    ("RESTORE", "CRITICAL"): ("HOLD", "RESTORE_CRITICAL_BOUNDARY"),
    ("REPLACE_UNIT", "CONSUMABLE"): ("HOLD", "REPLACE_UNIT_BOUNDARY"),
    ("REPLACE_UNIT", "CRITICAL"): ("HOLD", "REPLACE_UNIT_BOUNDARY"),
}

_EXPENDITURE_RULE_REASONING = {
    "UPGRADE": "성능 향상을 수반하는 개조 지출이므로 자본적 지출로 본다.",
    "OVERHAUL": "오버홀은 통상 내용연수를 연장하는 지출이므로 자본적 지출로 본다.",
    "RESTORE_CONSUMABLE": (
        "소모품 교체를 통한 원상 회복 수준의 수선이므로 수익적 지출(당기 비용)로 본다."
    ),
    "RESTORE_CRITICAL_BOUNDARY": (
        "핵심부품(CRITICAL) 원상 회복은 '원상 회복'인지 '내용연수 연장'인지가 실무에서 가장 "
        "논쟁이 잦은 경계 사안이라 단정하지 않는다 (12 §3)."
    ),
    "REPLACE_UNIT_BOUNDARY": (
        "설비 단위 교체는 기존 자산의 수선이 아니라 자산 대체(신규 취득 + 기존 자산 처분)로 "
        "볼 여지가 있는 경계 사안이라 단정하지 않는다."
    ),
}

_EXPENDITURE_ESCALATION_REASONING = {
    "MATERIALITY_AT_OR_ABOVE_THRESHOLD": (
        "취득원가 대비 지출 비율이 문턱(20%) 이상이라 소액 수선으로 볼 수 없다 — "
        "기본 판정({base})을 유보(HOLD)로 격상했다."
    ),
    "MATERIALITY_UNKNOWN": (
        "취득원가를 알 수 없어 지출 비율(20% 기준)을 계산하지 못했다 — "
        "'모른다'를 '문턱 미만'으로 처리하지 않고 기본 판정({base})을 유보(HOLD)로 격상했다 (D62)."
    ),
}

_EXPENDITURE_BASE_NOT_CONSIDERED = (
    "회사 내부 자본화 기준·소액수선비 특례 적용 여부 (사내 회계정책은 원천이 없다)",
    "같은 자산에 대한 사업연도 누적 지출액 — 이 판정은 지출 건별이다",
    "부가가치세 매입세액 공제·세금계산서 요건",
    "자본화 시 감가상각 재계산(내용연수 연장분)과 장부가액 영향",
    "수선 내용의 사실관계 (현장 증빙·수리 명세서 확인 전)",
)

_EXPENDITURE_DISCLAIMER = (
    "통상 사례 기준 목업 판정이다. 세무 신고·회계 기표의 근거로 그대로 사용할 수 없으며 "
    "실제 적용에는 전문가 검토가 필요하다."
)
_EXPENDITURE_DISCLAIMER_LAW_PENDING = (
    " 인용한 조문의 원문은 아직 수집되지 않았으며(fetch_status=PENDING), 인용은 조문 번호·제목 "
    "기준이다."
)


def _as_amount(value: object) -> int | None:
    """금액으로 해석되면 int, 아니면 None. **추정하지 않는다.**

    bool 을 먼저 걸러낸다 — 파이썬에서 `True` 는 `int` 라 `isinstance` 로는 통과해 금액 1원이 된다.
    inf·nan 은 `is_integer()` 가 False 라 자동으로 걸린다.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if cleaned.lstrip("-").isdigit():
            return int(cleaned)
    return None


def _display_ratio(numerator: int, denominator: int) -> float | None:
    """표시용 비율. **판정은 이 값으로 하지 않는다** (아래 `_materiality` 참조).

    반올림된 값이라 문턱 근처에서는 `state` 와 눈으로 어긋나 보일 수 있다 —
    판정의 근거는 언제나 `state` 이고 이 필드는 사람이 읽는 용도다.
    거대 정수를 float 로 나누면 `OverflowError` 가 난다 — 예외를 새어나가게 두면 D9 가 깨진다.
    """
    try:
        return round(numerator / denominator, 6)
    except (ZeroDivisionError, OverflowError):
        return None


def _materiality(amount: int, acquisition_cost: object, asset_found: bool) -> dict:
    """취득원가 대비 지출 비율 판정.

    비교를 `amount / cost >= 0.20` 로 하지 않는 이유: 거대 정수에서 float 변환이 터지고
    (`OverflowError`), 0.2 의 이진 부동소수 오차가 문턱 정확히 20% 인 입력의 판정을 흔든다.
    `Fraction` 은 정수 교차곱 비교라 둘 다 없다.

    state 4종:
      NOT_EVALUATED     asset_id 미제공 — 호출자가 자산을 지정하지 않았다
      UNKNOWN           자산은 있으나 취득원가가 NULL/비정상 — **모른다**
      BELOW_THRESHOLD / AT_OR_ABOVE_THRESHOLD
    """
    if not asset_found:
        return {
            "state": "NOT_EVALUATED",
            "acquisition_cost": None,
            "ratio": None,
            "threshold": float(MATERIALITY_THRESHOLD),
        }
    cost = acquisition_cost if isinstance(acquisition_cost, int) else None
    if isinstance(acquisition_cost, float) and acquisition_cost.is_integer():
        cost = int(acquisition_cost)
    if cost is None or cost <= 0:
        return {
            "state": "UNKNOWN",
            "acquisition_cost": None,
            "ratio": None,
            "threshold": float(MATERIALITY_THRESHOLD),
        }
    at_or_above = Fraction(amount, cost) >= MATERIALITY_THRESHOLD
    return {
        "state": "AT_OR_ABOVE_THRESHOLD" if at_or_above else "BELOW_THRESHOLD",
        "acquisition_cost": cost,
        "ratio": _display_ratio(amount, cost),
        "threshold": float(MATERIALITY_THRESHOLD),
    }


def expenditure(
    con: sqlite3.Connection,
    *,
    part_class: str,
    repair_scope: str,
    amount: int | str,
    asset_id: str | None = None,
) -> dict:
    """지출을 CAPITAL | REVENUE | HOLD 로 분류한다. 공개 진입점 — **얇은 래퍼**."""
    try:
        return _expenditure(con, part_class, repair_scope, amount, asset_id)
    except Exception as exc:  # noqa: BLE001 — 도구는 예외를 던지지 않는다 (D9)
        return _fail("internal_error", f"판정 중 오류가 발생했습니다: {exc}")


def _expenditure(
    con: sqlite3.Connection,
    part_class: object,
    repair_scope: object,
    amount: object,
    asset_id: object,
) -> dict:
    # ── 1. 입력 검증 — enum 밖 값은 폴백하지 않는다 -------------------------
    if part_class not in PART_CLASSES:
        return _fail(
            "invalid_input",
            f"part_class 는 {' | '.join(PART_CLASSES)} 중 하나여야 합니다: {part_class!r}. "
            "부품 등급은 classify_part_criticality 로 확인하세요.",
        )
    if repair_scope not in REPAIR_SCOPES:
        return _fail(
            "invalid_input",
            f"repair_scope 는 {' | '.join(REPAIR_SCOPES)} 중 하나여야 합니다: {repair_scope!r}",
        )
    parsed_amount = _as_amount(amount)
    if parsed_amount is None:
        return _fail("invalid_input", f"amount 는 지출 금액(정수, 원)입니다: {amount!r}")
    if parsed_amount <= 0:
        return _fail("invalid_input", f"amount 는 0보다 커야 합니다: {parsed_amount}")
    if asset_id is not None and (not isinstance(asset_id, str) or not asset_id.strip()):
        return _fail("invalid_input", f"asset_id 는 비어있지 않은 문자열입니다: {asset_id!r}")

    # ── 2. 조회 -----------------------------------------------------------
    try:
        laws = load_laws_from_db(con)
        asset_row = None
        if asset_id is not None:
            asset_row = con.execute(
                "SELECT asset_id, name, acquisition_cost FROM assets WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
    except Exception as exc:  # noqa: BLE001
        return _fail("db_error", str(exc))

    # ── 3. 근거 검증이 판정보다 먼저다 (D61 · 불변식 2) ---------------------
    today = date.today()
    try:
        law = get_law_as_of(laws, EXPENDITURE_LAW_REF_ID, today)
    except KeyError:
        return _fail(
            "law_ref_missing",
            f"근거 조문 {EXPENDITURE_LAW_REF_ID} 이 law_refs 에 등록돼 있지 않습니다. "
            "근거 없는 지출 판정은 하지 않습니다 (D61).",
        )
    except ValueError as exc:  # 시점 밖 조문 — 조용히 최신본으로 대체하지 않는다 (불변식 5)
        return _fail("law_not_effective", str(exc))

    # ── 4. 자산 해석 (asset_id 를 준 경우에만) ------------------------------
    if asset_id is not None and asset_row is None:
        return {
            "status": "not_found",
            "reason": "unknown_asset",
            "message": f"등록되지 않은 자산입니다: {asset_id!r}",
        }

    # ── 5. 판정 ------------------------------------------------------------
    verdict, basis = _EXPENDITURE_RULE_TABLE[(repair_scope, part_class)]
    reasons = [_EXPENDITURE_RULE_REASONING[basis]]

    materiality = _materiality(
        parsed_amount,
        asset_row["acquisition_cost"] if asset_row is not None else None,
        asset_found=asset_row is not None,
    )
    escalation = None
    if materiality["state"] in ("AT_OR_ABOVE_THRESHOLD", "UNKNOWN"):
        escalation = f"MATERIALITY_{materiality['state']}"
        reasons.append(_EXPENDITURE_ESCALATION_REASONING[escalation].format(base=verdict))
        verdict = "HOLD"  # 결과와 무관하게 격상
    materiality["escalated"] = escalation is not None

    not_considered = list(_EXPENDITURE_BASE_NOT_CONSIDERED)
    if materiality["state"] == "NOT_EVALUATED":
        not_considered.insert(
            0, "취득원가 대비 지출 비율(20% 기준) — asset_id 미제공으로 평가하지 않았다"
        )

    requires_expert_review = verdict == "HOLD"
    if requires_expert_review:
        reasons.append("세무 전문가 확인이 필요하다.")

    # 조문 원문이 없으면 그 사실을 판정에 실어 보낸다 (판정 자체는 막지 않는다)
    law_text_pending = not law.is_fetched
    disclaimer = _EXPENDITURE_DISCLAIMER + (
        _EXPENDITURE_DISCLAIMER_LAW_PENDING if law_text_pending else ""
    )

    return {
        "status": "ok",
        "verdict": verdict,
        "asset_id": asset_row["asset_id"] if asset_row is not None else None,
        "part_class": part_class,
        "repair_scope": repair_scope,
        "amount": parsed_amount,
        "basis": basis,
        "law_refs": [law.law_ref_id],
        "citations": [law.citation()],
        "reasoning": " ".join(reasons),
        "requires_expert_review": requires_expert_review,
        "evidence_completeness": "LAW_TEXT_PENDING" if law_text_pending else "COMPLETE",
        "materiality": materiality,
        "evaluated_at": today.isoformat(),
        "not_considered": not_considered,
        "disclaimer": disclaimer,
    }


# ══════════════════════════════════════════════════════════════════════════
# repair_value — 원본: mcp_server/tools/assess_repair_value.py (MQ-609, MQ-922 위임)
# ══════════════════════════════════════════════════════════════════════════
#
# 이 판정이 지키는 순서와 태도는 전부 "지어내지 않기" 하나에서 나온다.
#
# ★ 최우선 분기 — 반복 고장이면 3지 판단을 **하지 않는다** (D2 · `12 §11`)
#   `repeat_failure == true` 면 다른 계산을 하기 전에 즉시 `ROOT_CAUSE_FIRST` 로 닫고
#   `alternatives` 를 **빈 배열**로 돌려준다. 3지 선택지를 함께 주면 에이전트가 그중 하나를
#   고르기 때문이다 — 그게 이 분기의 존재 이유다. S3 발주 보류(`po_card` variant `hold`, D35)가
#   그대로 적용돼야 한다.
#
# ★ 시장가는 없으면 없다고 한다 (D65 · D74)
#   `residual_curve` 는 **목업 정률법 산출물**이고 실거래 데이터가 아니다. 연차가 격자 밖이거나
#   행이 없거나 `acquisition_cost` 가 NULL 이면 `market_value_before = None` 이고 판정은 `HOLD` 다.
#   ⛔ **인접 버킷으로 보간하지 않는다.** 값이 없는데 판단하면 지어내는 것이다.
#   ⚠ 목업 곡선은 전 카테고리 값이 동일하다 — 즉 `category` 는 조인 키일 뿐 **판정에 영향을
#   주지 않는다**. 이 사실을 `not_considered` 와 `disclaimer` 에 드러낸다.
#
# ★ 하위 판정 실패를 삼키지 않는다
#   `part_criticality` · `maintenance_metrics` 중 하나라도 `status != "ok"` 면
#   그 `status`·`reason` 을 **그대로 전파**한다 (04 §13). 기본값으로 진행하면 없는 근거로
#   판단하게 된다.
#
# ────────────────────────────────────────────────────────────────────────────────
# ★ 값을 어디서 읽는가 — 이 규약을 어기면 판정이 조용히 틀린다 (Stage 4 B-1 재발 방지)
#
#   **룰 사실 키**(`ASSET_FACT_COLUMNS` ∪ 엔진 파생 키) → `facts[...]` (키 부재 = 모른다, D62)
#   그 **밖**의 컬럼                                    → `row[...]`
#
# `build_facts` 는 `ASSET_FACT_COLUMNS` 의 컬럼과 판정 시점 파생 키만 만든다. 이 판정이 쓰는
# `category`·`acquisition_cost`·`book_value`·`parts_eol_flag` 는 **전부 목록 밖**이라 `facts` 에서
# 읽으면 DB 에 값이 있어도 항상 None 이 나온다 — Stage 4 에서 실제로 그 결함(B-1)이 났다.
# `_rv_assert_fact_column()` 접근자가 목록 밖 컬럼을 `facts` 에서 읽으려 하면 즉시 실패시킨다.
# `acquired_at` 만 사실 키이고, `build_facts` 를 경유하는 덕에 **판독 불가한 날짜가 자동으로
# "모른다"로 떨어진다**(→ 시장가 null → HOLD). 직접 `row["acquired_at"]` 을 파싱하면 그 보호가
# 사라진다.
# ────────────────────────────────────────────────────────────────────────────────

REPAIR_RECOMMENDED = "REPAIR_RECOMMENDED"
REPLACE_RECOMMENDED = "REPLACE_RECOMMENDED"
SELL_AS_IS = "SELL_AS_IS"
ROOT_CAUSE_FIRST = "ROOT_CAUSE_FIRST"
HOLD = "HOLD"

VERDICTS = (REPAIR_RECOMMENDED, REPLACE_RECOMMENDED, SELL_AS_IS, ROOT_CAUSE_FIRST, HOLD)

# `repair_scope` enum — `expenditure()` 와 값이 같으므로 위에서 이미 정의한 `REPAIR_SCOPES` 를
# 그대로 재사용한다(새 사본을 만들지 않는다). 폴백하지 않는다 — 오타를 그대로 흘리면
# 회복 계수가 조용히 바뀌어 verdict 가 달라진다.

# 잔가 격자 (MQ-603/D74 산출물과 동일). 격자 밖 연차는 행이 없으므로 조회 자체를 하지 않는다.
_REPAIR_VALUE_AGE_BUCKETS: tuple[tuple[int, int, str], ...] = (
    (0, 2, "0-2"),
    (3, 5, "3-5"),
    (6, 10, "6-10"),
    (11, 15, "11-15"),
    (16, 20, "16-20"),
    (21, 30, "21-30"),
)

# ★ CRITICAL 부품 교체가 회복시키는 잔존가치 비율 — **목업 상수**다.
#   저장소에 "수리 후 실제 거래가"를 담은 원천이 하나도 없어 계측으로 낼 수 없다.
#   잔가곡선 자체가 목업(D74)이므로 그 위에 얹는 계수도 목업임을 숨기지 않는다:
#   값은 `assumptions` 로 출력에 실리고, 파생 금액은 전부 `estimates[]` 에 나열된다 (D65).
#   범위(원상회복 < 유닛교체 < 성능개선 < 오버홀)의 근거도 실측이 아니라 순서 가정일 뿐이다.
_REPAIR_VALUE_LIFE_RECOVERY_BY_SCOPE: dict[str, float] = {
    "RESTORE": 0.10,
    "REPLACE_UNIT": 0.15,
    "UPGRADE": 0.20,
    "OVERHAUL": 0.25,
}

# verdict 문턱 — 전부 결정론적이다(같은 입력이면 같은 판정).
_REPAIR_VALUE_RECOVERY_RATIO_THRESHOLD = 1.0  # 회복액 ≥ 수리비 → 수리가 경제적으로 회수된다
_REPAIR_VALUE_REPLACE_REPAIR_RATIO_THRESHOLD = 0.5  # 누적 수리비가 취득원가의 절반 → 교체 검토

_REPAIR_VALUE_NOT_CONSIDERED_BASE = (
    "신규 취득 단가 — 저장소에 신품 가격 원천이 없어 교체 대안의 비용을 산출하지 못한다",
    "수리 후 실제 잔존수명 — 계측 원천이 없어 회복 계수는 목업 상수다 (assumptions 참조)",
    "부품 재고·조달 리드타임 (search_inventory·get_supplier_quotes 소관)",
    "repair_cost 의 적정성 — 호출자가 준 값이며 이 도구는 견적으로 검증하지 않는다 "
    "(단가 조회는 get_supplier_quotes 소관, D31)",
    "OEE·가동률 — 거래·처분 판정에 사용 금지 (D64)",
    "지출의 세무 성격(자본적/수익적) — classify_expenditure 소관",
    "처분 법정 조건(담보·세액공제·안전검사) — check_disposal_blockers 소관",
    "설비 카테고리별 잔가 차이 — 목업 곡선(D74)은 전 카테고리 값이 동일하다. "
    "category 는 잔가곡선 조인 키일 뿐 판정에 영향을 주지 않는다",
)

_REPAIR_VALUE_DISCLAIMER = (
    "시장가는 법정 기준내용연수 기반 목업 잔가곡선(D74) 추정치이며 실거래가가 아니다. "
    "수리 후 회복분의 계수도 계측이 아니라 코드 상수다 — estimates[] 에 나열된 필드는 전부 "
    "추정치이므로 확정 금액처럼 제시하지 말 것 (D65). "
    "목업 곡선은 전 카테고리 값이 같아 category 는 판정에 영향을 주지 않는다. "
    "HOLD 는 '문제 없음'이 아니라 '판단 근거 부족'이다."
)

# `build_facts` 가 `ASSET_FACT_COLUMNS` 밖에서 추가로 만드는 **판정 시점 파생 키**
# (`data/rules/engine.py:389-396`). 이 판정은 `build_facts(row)` 를 인자 없이 부르므로
# 실제로는 앞의 둘만 존재하지만, 가드가 정당한 접근까지 거짓 차단하지 않도록 4종을 전부 넣는다.
# ⚠ `engine` 의 공개 상수로 승격하지 않는다 — `engine.py` 는 MQ-601b 소유다.
_REPAIR_VALUE_ENGINE_DERIVED_FACT_KEYS = frozenset(
    {"disposal_mode", "vat_invoice_issued", "disposal_date", "months_since_acquisition"}
)
_REPAIR_VALUE_FACT_KEYS = frozenset(ASSET_FACT_COLUMNS) | _REPAIR_VALUE_ENGINE_DERIVED_FACT_KEYS


def _rv_assert_fact_column(col: str) -> None:
    """ "값을 어디서 읽는가" 규약을 **주석이 아니라 코드로** 강제한다 (Stage 4 B-1).

    목록 밖 컬럼을 `facts` 에서 읽으면 DB 에 값이 있어도 조용히 None 이 나와
    "취득원가 없음 → HOLD" 같은 **거짓 판정**이 된다. 여기서 시끄럽게 실패시키고,
    공개 진입점이 그것을 `status:"error"` 로 닫는다 — 거짓 판정을 내보내는 것보다 낫다.
    """
    if col not in _REPAIR_VALUE_FACT_KEYS:
        raise KeyError(
            f"{col!r} 은 룰 사실 키가 아니다 (ASSET_FACT_COLUMNS ∪ 엔진 파생 키 밖) — "
            "facts 에 절대 들어오지 않으므로 row[...] 에서 읽어야 한다 (모듈 섹션 docstring 규약 · B-1)"
        )


def _rv_fact(facts: dict, col: str) -> object:
    _rv_assert_fact_column(col)
    return facts.get(col)


def _rv_as_amount(value: object) -> int | None:
    """금액으로 읽히면 int, 아니면 None. **추정하지 않는다.**

    bool 은 거부한다(`True` 가 1원이 되면 안 된다). NaN·inf 도 거부한다 —
    그대로 비교 연산에 들어가면 verdict 가 조용히 뒤집힌다.

    ⚠ `expenditure()` 의 `_as_amount` 와 이름만 같지 규칙이 다르다(부동소수 반올림 허용) —
    한 이름으로 합치면 어느 한쪽 판정이 조용히 달라진다.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value)) if math.isfinite(value) else None
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)
        except ValueError:
            pass
        try:
            number = float(text)
        except ValueError:
            return None
        return int(round(number)) if math.isfinite(number) else None
    return None


def _rv_as_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _rv_age_bucket(acquired: date, today: date) -> tuple[int, str | None]:
    """`age = 오늘연도 - 취득연도` → 버킷 라벨. 격자 밖이면 라벨이 None 이다.

    ⛔ 격자 밖(음수·31년 이상)을 인접 버킷으로 **보간하지 않는다** (D65).
       31년 된 설비에 21-30 버킷 잔가율을 쓰면 없는 정확도를 만드는 것이다.
    """
    age = today.year - acquired.year
    for low, high, label in _REPAIR_VALUE_AGE_BUCKETS:
        if low <= age <= high:
            return age, label
    return age, None


def repair_value(
    con: sqlite3.Connection,
    *,
    equipment_id: str,
    failed_part: str,
    repair_cost: int | str,
    repair_scope: str = "RESTORE",
) -> dict:
    """공개 진입점 — **얇은 래퍼**.

    본체를 통째로 감싸 입력 파싱·응답 조립·엔진 호출에서 난 예외까지 status 로 닫는다 (D9·D46).
    `engine` 은 예외를 던지므로(`RuleIntegrityError`·`KeyError`·`TypeError` 등) 특정 예외만
    잡으면 "어떤 입력에도 예외가 새지 않음"이 코드 위치에 의존하게 된다.

    호출자(`mcp_server/tools/assess_repair_value.py`)가 **읽기 전용 커넥션 하나**를 열어
    넘긴다 — 이 함수와 하위 판정(`part_criticality`·`maintenance_metrics`)이 그 커넥션 하나만
    쓴다 (MQ-922, D73). `repair_scope` 기본값 `"RESTORE"` 는 이 함수의 계약값이다 — MCP 노출용
    `DEFAULT_REPAIR_SCOPE` 상수의 정본은 `mcp_server/tools/assess_repair_value.py` 다(D80 — 필수
    파라미터에 기본값을 두지 않는다는 규칙은 도구의 공개 시그니처에 대한 것이고, 이 값은 그
    시그니처가 실제로 넘길 값과 같아야 한다).
    """
    try:
        return _repair_value(con, equipment_id, failed_part, repair_cost, repair_scope)
    except Exception as e:  # noqa: BLE001 — 도구는 예외를 던지지 않는다 (D9)
        return _fail("internal_error", f"수리가치 판단 중 처리 오류: {e}")


def _repair_value(
    con: sqlite3.Connection,
    equipment_id: object,
    failed_part: object,
    repair_cost: object,
    repair_scope: object,
) -> dict:
    # ── 0) 입력 검증 ─────────────────────────────────────────────────────────────
    for label, value in (("equipment_id", equipment_id), ("failed_part", failed_part)):
        if not isinstance(value, str) or not value.strip():
            return _fail(
                "invalid_input", f"{label} 는 비어 있지 않은 문자열 식별자입니다: {value!r}"
            )
    equipment_id = equipment_id.strip()
    failed_part = failed_part.strip()

    cost = _rv_as_amount(repair_cost)
    if cost is None or cost <= 0:
        return _fail("invalid_input", f"repair_cost 는 0보다 큰 금액(원)입니다: {repair_cost!r}")

    if not isinstance(repair_scope, str) or repair_scope.strip().upper() not in REPAIR_SCOPES:
        # 폴백하지 않는다 — 모르는 scope 를 RESTORE 로 접으면 회복 계수가 조용히 바뀐다
        return _fail(
            "invalid_input",
            f"repair_scope 는 {' | '.join(REPAIR_SCOPES)} 중 하나입니다: {repair_scope!r}",
        )
    scope = repair_scope.strip().upper()

    # ── 1) equipment → asset 해석 (D68) ─────────────────────────────────────────
    try:
        equipment = con.execute(
            "SELECT equipment_id, asset_id FROM equipment WHERE equipment_id = ?",
            (equipment_id,),
        ).fetchone()
        if equipment is None:
            return _fail(
                "unknown_equipment",
                f"등록되지 않은 설비입니다: {equipment_id}",
                status="not_found",
            )
        asset_id = equipment["asset_id"]
        if not asset_id:
            return _fail(
                "no_host_asset",
                f"{equipment_id} 에는 연결된 호스트 자산이 없습니다. "
                "자산 단위 잔존가치를 산출할 수 없습니다.",
                status="not_found",
            )
        asset_row = con.execute(
            "SELECT * FROM assets WHERE asset_id = ?", (asset_id,)
        ).fetchone()
        if asset_row is None:
            return _fail(
                "unknown_asset",
                f"{equipment_id} 가 가리키는 자산이 없습니다: {asset_id}",
                status="not_found",
            )
        asset = dict(asset_row)
        today = _rv_as_date(con.execute("SELECT date('now')").fetchone()[0])
        if today is None:
            return _fail("db_error", "기준 일자(date('now')) 를 해석하지 못했습니다")
    except Exception as e:  # noqa: BLE001 — 예외를 status 로 바꿔 반환 (D9)
        return _fail("db_error", str(e))

    # ── 2) 하위 판정 — **함수 호출**로 바뀐다(같은 커넥션을 그대로 넘긴다). 실패는
    #     그대로 전파한다 — 기본값으로 진행하면 없는 근거로 3지 판단을 하게 된다 (04 §13) ──
    part = part_criticality(con, part_no=failed_part)
    if part.get("status") != "ok":
        return dict(part)

    metrics = maintenance_metrics(con, asset_id=asset_id)
    if metrics.get("status") != "ok":
        return dict(metrics)

    part_class = part["part_class"]
    mtbf_trend = metrics["mtbf_trend"]
    repeat_failure = bool(metrics["repeat_failure"])
    cumulative_repair_ratio = metrics["cumulative_repair_ratio"]

    base = {
        "status": "ok",
        "asset_id": asset_id,
        "equipment_id": equipment_id,
        "failed_part": failed_part,
        "part_class": part_class,
        "repair_cost": cost,
        "repair_scope": scope,
        "evaluated_at": today.isoformat(),
        "book_value": asset.get("book_value"),  # ASSET_FACT_COLUMNS 밖 → row 에서 읽는다
        "mtbf_trend": mtbf_trend,
        "repeat_failure": repeat_failure,
        "cumulative_repair_ratio": cumulative_repair_ratio,
        "parts_eol_flag": bool(asset.get("parts_eol_flag")),  # 목록 밖 → row
    }

    # ── 3) ★ 최우선 분기 — 반복 고장이면 3지 판단을 하지 않는다 (D2 · D35 · `12 §11`) ──
    #     시장가·회복분을 **계산하지 않고** 즉시 닫는다. 선택지를 함께 주면 에이전트가
    #     그중 하나를 고른다 — 그게 이 분기의 존재 이유다.
    if repeat_failure:
        return {
            **base,
            "market_value_before": None,
            "market_value_after": None,
            "value_recovery": None,
            "recovery_ratio": None,
            "verdict": ROOT_CAUSE_FIRST,
            "reasoning": (
                f"직전 {REPEAT_WINDOW_DAYS}일 안에 같은 설비에서 고장이 {REPEAT_THRESHOLD}회 이상 "
                "반복됐다. 반복 고장은 부품 수명이 아니라 다른 원인(냉각·부하·설치 조건 등)의 "
                "신호이므로, 수리·교체·현상매각 3지 판단보다 근본원인 규명이 먼저다 (D2 · 12 §11). "
                "부품 발주는 보류하고 근본원인 점검 절차를 먼저 안내할 것 (S3)."
            ),
            "alternatives": [],  # ⛔ 비운다 — 선택지를 주면 그중 하나가 골라진다
            "estimates": [],  # 시장가를 계산하지 않았으므로 추정한 값이 없다
            "assumptions": [],
            "not_considered": [
                *_REPAIR_VALUE_NOT_CONSIDERED_BASE,
                "시장가·회복분 — 반복 고장 분기에서는 계산하지 않는다 "
                "(근본원인 규명 전의 3지 판단은 근거가 없다)",
            ],
            "disclaimer": _REPAIR_VALUE_DISCLAIMER,
        }

    # ── 4) 시장가 — 없는 정밀도를 만들지 않는다 (D65 · D74) ─────────────────────
    #   `acquired_at` 만 룰 사실 키다. `build_facts` 경유 덕에 판독 불가한 날짜가
    #   자동으로 "모른다"(키 부재)로 떨어진다 — 직접 파싱하면 그 보호가 사라진다 (D62).
    facts = build_facts(asset_row)
    acquired = _rv_as_date(_rv_fact(facts, "acquired_at"))
    # 아래 3종은 ASSET_FACT_COLUMNS **밖**이므로 반드시 row 에서 읽는다 (B-1)
    category = asset.get("category")
    acquisition_cost = _rv_as_amount(asset.get("acquisition_cost"))
    parts_eol = bool(asset.get("parts_eol_flag"))

    hold_reasons: list[str] = []
    age: int | None = None
    bucket: str | None = None
    residual_ratio: float | None = None

    if acquired is None:
        hold_reasons.append("acquired_at 이 없거나 날짜로 읽히지 않아 연차를 산출할 수 없다")
    else:
        age, bucket = _rv_age_bucket(acquired, today)
        if bucket is None:
            hold_reasons.append(
                f"취득 후 {age}년은 잔가곡선 격자(0-30년) 밖이다 — "
                "인접 버킷으로 보간하지 않는다 (D65)"
            )
    if acquisition_cost is None or acquisition_cost <= 0:
        hold_reasons.append("acquisition_cost 가 없어 잔가율을 금액으로 환산할 수 없다")

    if bucket is not None:
        try:
            curve = con.execute(
                "SELECT residual_ratio, source FROM residual_curve "
                "WHERE category = ? AND age_bucket = ?",
                (category, bucket),
            ).fetchone()
        except Exception as e:  # noqa: BLE001
            return _fail("db_error", str(e))
        if curve is None:
            hold_reasons.append(
                f"잔가곡선에 (category={category!r}, age_bucket={bucket!r}) 행이 없다 — "
                "다른 버킷 값을 끌어다 쓰지 않는다 (D65)"
            )
        else:
            residual_ratio = curve["residual_ratio"]

    market_value_before: int | None = None
    if residual_ratio is not None and acquisition_cost is not None and acquisition_cost > 0:
        market_value_before = int(round(acquisition_cost * residual_ratio))

    # 회복분: CRITICAL 부품 교체만 잔존수명 회복으로 본다.
    # CONSUMABLE 은 `market_value_after = market_value_before` — 소모품 교체는 가격에
    # 직접 반영되지 않는다 (`12 §1`). 계수는 목업 상수이며 estimates·assumptions 로 고지한다.
    recovery_coefficient = (
        _REPAIR_VALUE_LIFE_RECOVERY_BY_SCOPE[scope] if part_class == "CRITICAL" else 0.0
    )
    market_value_after: int | None = None
    value_recovery: int | None = None
    recovery_ratio: float | None = None
    if market_value_before is not None:
        market_value_after = int(round(market_value_before * (1.0 + recovery_coefficient)))
        value_recovery = market_value_after - market_value_before
        recovery_ratio = value_recovery / cost

    # ── 5) verdict — 결정론적. 순서 자체가 계약이다 ─────────────────────────────
    verdict, reasoning = _rv_decide(
        market_value_before=market_value_before,
        market_value_after=market_value_after,
        recovery_ratio=recovery_ratio,
        cumulative_repair_ratio=cumulative_repair_ratio,
        parts_eol=parts_eol,
        mtbf_trend=mtbf_trend,
        repair_cost=cost,
        part_class=part_class,
        hold_reasons=hold_reasons,
    )

    # ── 6) 추정치 고지 — 문장이 아니라 **필드**로 (D65) ─────────────────────────
    #   UI·평가가 기계적으로 확인할 수 있어야 한다. 값이 없으면 추정한 것도 없으므로
    #   목록에서 뺀다(빈 배열은 "추정치가 없다"는 정직한 신호다).
    estimates = [
        name
        for name, value in (
            ("market_value_before", market_value_before),
            ("market_value_after", market_value_after),
            ("value_recovery", value_recovery),
            ("recovery_ratio", recovery_ratio),
        )
        if value is not None
    ]

    assumptions: list[str] = []
    if residual_ratio is not None:
        assumptions.append(
            f"잔가율 {residual_ratio} = residual_curve(category={category!r}, "
            f"age_bucket={bucket!r}) · 목업 정률법 산출물이며 실거래 데이터가 아니다 (D74)"
        )
    if market_value_before is not None:
        if part_class == "CRITICAL":
            assumptions.append(
                f"수리 후 잔존가치 회복 계수 {recovery_coefficient} "
                f"(repair_scope={scope}, part_class=CRITICAL) — 계측이 아닌 코드 상수다. "
                "저장소에 '수리 후 실거래가' 원천이 없어 측정할 수 없다"
            )
        else:
            assumptions.append(
                "CONSUMABLE 교체는 시장가에 직접 반영하지 않는다 "
                "(market_value_after = market_value_before, 12 §1)"
            )

    return {
        **base,
        "age_years": age,
        "age_bucket": bucket,
        "residual_ratio": residual_ratio,
        "market_value_before": market_value_before,
        "market_value_after": market_value_after,
        "value_recovery": value_recovery,
        "recovery_ratio": _round(recovery_ratio, 3),
        "verdict": verdict,
        "reasoning": reasoning,
        "alternatives": _rv_alternatives(market_value_before),
        "estimates": estimates,
        "assumptions": assumptions,
        "not_considered": list(_REPAIR_VALUE_NOT_CONSIDERED_BASE),
        "disclaimer": _REPAIR_VALUE_DISCLAIMER,
    }


def _rv_decide(
    *,
    market_value_before: int | None,
    market_value_after: int | None,
    recovery_ratio: float | None,
    cumulative_repair_ratio: float | None,
    parts_eol: bool,
    mtbf_trend: str,
    repair_cost: int,
    part_class: str,
    hold_reasons: list[str],
) -> tuple[str, str]:
    """3지 판단 — **순서가 계약이다.**

    1. `market_value_before` 가 null → **HOLD**. 시장가 없이 3지 판단을 하면 지어내는 것이다.
       ⚠ `parts_eol_flag=1` 보다 **앞**에 둔다: 잔가 원천이 없는 상태에서 "교체하라"고
         권하는 것도 근거 없는 판단이고, 이 순서 덕에 "`residual_curve` 를 비우면 전 자산 HOLD"
         가 성립한다(값을 지어내지 않음의 증명).
    2. 교체 신호(누적 수리비 비율 ≥ 0.5 · 부품 단종) → **REPLACE_RECOMMENDED**.
       회복 계산보다 앞이다 — 부품이 EOL 이면 이번 수리가 회수돼도 다음 수리를 못 한다.
    3. MTBF 악화 + 수리비 > 회복 후 시장가 → **SELL_AS_IS**.
    4. 회복액 ≥ 수리비 → **REPAIR_RECOMMENDED**.
       3과 4는 상호배타다(회복분 ≥ 수리비 이면 수리비는 회복 후 시장가를 넘을 수 없다).
    5. 어느 규칙도 발화하지 않으면 **HOLD**. 새 verdict 를 만들거나 가까운 쪽으로
       반올림하지 않는다 — 규칙이 침묵한 것을 결론으로 바꾸면 그게 지어내기다.
    """
    if market_value_before is None:
        why = " / ".join(hold_reasons) if hold_reasons else "시장가를 산출할 원천이 없다"
        return HOLD, (
            f"시장가를 산출하지 못해 수리·교체·현상매각을 비교할 수 없다: {why}. "
            "금액을 추정해 메우지 않는다 (D65). 취득원가·취득일을 자산대장에서 보완하거나 "
            "감정평가·복수 딜러 호가로 시장가 근거를 확보한 뒤 다시 판단할 것."
            + (" 참고: 이 자산은 부품 단종(parts_eol_flag) 상태다." if parts_eol else "")
        )

    if parts_eol:
        return REPLACE_RECOMMENDED, (
            "핵심 부품이 단종(parts_eol_flag=1)이라 이번 수리가 회수되더라도 다음 고장에서 "
            "부품을 구할 수 없다. 수리보다 교체(또는 대체품 확보 계획)를 먼저 검토할 것. "
            "신규 취득 단가 원천이 없으므로 교체 비용은 견적으로 확인해야 한다."
        )
    if (
        cumulative_repair_ratio is not None
        and cumulative_repair_ratio >= _REPAIR_VALUE_REPLACE_REPAIR_RATIO_THRESHOLD
    ):
        return REPLACE_RECOMMENDED, (
            f"누적 수리비가 취득원가의 {cumulative_repair_ratio:.0%}로 "
            f"문턱({_REPAIR_VALUE_REPLACE_REPAIR_RATIO_THRESHOLD:.0%})을 넘었다. "
            "개별 수리의 회수 여부와 무관하게 교체를 검토할 구간이다."
        )

    if mtbf_trend == "declining" and market_value_after is not None:
        if repair_cost > market_value_after:
            return SELL_AS_IS, (
                f"고장 간격이 짧아지는 추세(mtbf_trend=declining)인데 수리비 {repair_cost:,}원이 "
                f"수리 후 추정 시장가 {market_value_after:,}원을 넘는다. 수리비를 들여도 자산가치를 "
                "회수하지 못하므로 현상 매각을 검토할 것 (매각 전 처분 법정 조건은 "
                "check_disposal_blockers 로 별도 확인)."
            )

    if recovery_ratio is not None and recovery_ratio >= _REPAIR_VALUE_RECOVERY_RATIO_THRESHOLD:
        return REPAIR_RECOMMENDED, (
            f"수리로 회복되는 추정 잔존가치가 수리비의 {recovery_ratio:.2f}배로 "
            f"문턱({_REPAIR_VALUE_RECOVERY_RATIO_THRESHOLD:.1f})을 넘는다. 수리가 경제적으로 "
            "회수되는 구간이다. 회복분은 목업 잔가곡선·목업 계수 기반 추정치이므로 금액 자체를 "
            "확정으로 쓰지 말 것."
        )

    detail = (
        f"recovery_ratio={recovery_ratio if recovery_ratio is None else round(recovery_ratio, 3)}"
        f" · mtbf_trend={mtbf_trend} · part_class={part_class}"
        f" · cumulative_repair_ratio={cumulative_repair_ratio}"
    )
    return HOLD, (
        f"결정론적 규칙 어느 것도 발화하지 않았다 ({detail}). 수리가 회수되지도, 교체·매각 신호가 "
        "잡히지도 않은 경계 구간이므로 가까운 쪽으로 반올림하지 않고 판단을 유보한다. "
        "정비 담당자가 가동 계획·대체 설비 가용성을 함께 보고 결정할 것."
    )


def _rv_alternatives(market_value_before: int | None) -> list[dict]:
    """수리 이외의 선택지. **ROOT_CAUSE_FIRST 에서는 호출하지 않는다**(빈 배열이 계약)."""
    if market_value_before is None:
        sell_note = "잔가 원천이 없어 매각 대금을 추정할 수 없다 — 감정평가·호가 수집 필요 (D65)"
    else:
        sell_note = "수리 없이 현상 매각했을 때의 추정 대금 (목업 잔가곡선 기반, 실거래가 아님)"
    return [
        {
            "option": "REPLACE",
            "cost": None,
            "note": "신규 취득 단가 원천 없음 — 교체 비용은 견적으로 확인할 것",
        },
        {
            "option": "SELL_AS_IS",
            "proceeds": market_value_before,
            "note": sell_note,
        },
    ]
