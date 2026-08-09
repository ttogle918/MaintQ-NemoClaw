# -*- coding: utf-8 -*-
"""get_maintenance_metrics — 자산 보전지표 (MQ-607, `docs/12_MAINT_VALUE.md §2·§10`).

**없는 정밀도를 만들지 않는다.** 데이터가 부족하면 도구가 실패하는 게 아니라
그 사실이 **필드로 드러난다** — `null` · `"insufficient_data"` · `excluded[]`.
0 으로 채우거나 `"stable"` 로 뭉개면, 지어낸 숫자가 매각 증빙(S10)까지 흘러간다.

이 파일이 지키는 결정:
  D70  MTBF 는 **달력 기준** 평균 고장 간격(일). 가동시간 원천이 저장소에 없으므로
       가동시간 기반 산식은 쓰지 않고, 그 사실을 `mtbf_basis` 로 강제 고지한다.
  D64  OEE 는 **계산도 출력도 하지 않는다**. `not_considered` 에 금지 사유만 남긴다.
  D68ⓑ 집계 단위는 asset(하위 equipment 전부 합산), **판정 단위는 인버터**.
       `repeat_failure` 는 인버터 단위로 판정한 뒤 OR 로 모은다.
  D2·D29 반복 고장 기준(30일 3회)은 `get_error_history` 의 상수를 **재사용**한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..db import read_only

# ★ 상수를 재정의하지 않는다 — 반복 고장 기준의 단일 출처는 get_error_history 다 (D2·D29).
#   여기서 30/3 을 다시 적으면 한쪽만 바뀌었을 때 S3 판정과 지표가 조용히 어긋난다.
from .get_error_history import REPEAT_THRESHOLD, REPEAT_WINDOW_DAYS

DEFAULT_WINDOW_MONTHS = 24

# 추세 비교 창 — window_months 와 무관하게 12+12 로 고정한다 (계약 문언: "최근 12개월 vs 이전 12개월").
TREND_WINDOW_MONTHS = 12
# 추세 판정 밴드. 최근 MTBF 가 직전 대비 10% 이상 짧아지면 악화(declining), 10% 이상 길어지면 개선.
TREND_BAND = 0.10

HOURS_PER_DAY = 24.0  # 가용도 계산의 단위 환산 상수 (MTTR[시간] → 일)

MTBF_BASIS = "calendar_days"

DESCRIPTION = (
    "설비 자산의 보전지표(MTBF·MTBF 추세·MTTR·가용도·예방보전 비율·누적 수리비·반복 고장 여부)를 "
    "조회한다. 수리할지 교체할지, 매각 시점인지 판단하기 전에 호출할 것. "
    "MTBF 는 가동시간이 아니라 달력 기준 평균 고장 간격(일)이며(mtbf_basis 확인), "
    "값이 null 이거나 mtbf_trend 가 insufficient_data 면 **데이터가 부족한 것**이지 "
    "'문제 없음'이 아니다 — 그 상태로 좋다/나쁘다를 단정하지 말 것. "
    "repeat_failure=true 면 지표 비교보다 근본원인 점검이 먼저다. "
    "OEE 는 이 도구가 제공하지 않으며 거래·처분 판정에 쓰지 말 것. "
    "부품 등급은 classify_part_criticality, 개별 에러 이력은 get_error_history 를 쓸 것."
)

_NOT_CONSIDERED_BASE = [
    "가동시간·스핀들 시간(원천 없음 — 달력 기준 MTBF 로 대체, D70)",
    "OEE(거래 판정 사용 금지 — D64)",
    "생산량·부하율·작업자 숙련도 등 설비 외 요인",
    f"mtbf_trend 는 window_months 와 무관하게 최근 {TREND_WINDOW_MONTHS}개월 대 "
    f"직전 {TREND_WINDOW_MONTHS}개월 고정 비교다",
]

_DISCLAIMER = (
    "MTBF 는 가동시간이 아니라 달력 기준 평균 고장 간격이다(D70). "
    "가동률이 다른 기간·설비 사이의 직접 비교에는 쓸 수 없다. "
    "null 과 insufficient_data 는 '양호'가 아니라 '판단 근거 부족'이다."
)

_DT_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d")


def _fail(reason: str, message: str, status: str = "error") -> dict:
    return {"status": status, "reason": reason, "message": message}


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
    for fmt in _DT_FORMATS:
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


def _resolve_asset(
    con, asset_id: str | None, equipment_id: str | None
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


def get_maintenance_metrics(
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

    try:
        with read_only() as con:
            resolved, failure = _resolve_asset(con, asset_id, equipment_id)
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

    excluded: list[str] = []
    not_considered = list(_NOT_CONSIDERED_BASE)

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
        "disclaimer": _DISCLAIMER,
    }
