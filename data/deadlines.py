# -*- coding: utf-8 -*-
"""deadlines — 법정 기한 추적 산출 로직 (MQ-1102, S9).

두 갈래를 스캔한다.

  1. **TAX-CREDIT-2Y** — `assets.tax_credit_applied=1` 인 자산의 투자세액공제 사후관리 기한
     (취득 후 24개월). 경계 구간(`review_band`)은 이 파일이 하드코딩하지 않는다 —
     `data.rules.engine.load_laws()`→`load_rules()` 로 `TAX-CREDIT-2Y` 룰 파일을 읽어
     `boundary.review_band` 를 그대로 쓴다. 룰이 바뀌면(D60) 이 파일도 손대지 않고 따라간다.
  2. **SAFETY-INSPECTION** — `assets.safety_inspection_target=1 AND inspection_valid_until
     IS NOT NULL` 인 자산의 안전검사 유효기한.

읽기 전용 산출 로직이다 — 아무것도 쓰지 않는다. 쓰기 도구는 `create_po_draft`·
`generate_disposal_document`·`create_repair_record` 3종뿐이고(D10), 이 모듈은 그중 어느 것도
아니다.

⛔ 이 모듈은 `mcp_server` 를 import 하지 않는다(D15 — 두 런타임 프로세스의 상호 import 금지).
   커넥션은 호출자가 **읽기 전용**으로 열어 넘긴다(`data/hotspot_status.py`·`data/maint_value.py`
   와 같은 규약) — 이 모듈은 DB 경로를 모른다.
   `data.rules.engine` 을 import 하는 것은 D15 위반이 아니다 — 그 모듈은 데이터 계층이다(D73).

`today` 는 주입 가능하다(`date | None`, 기본 `date.today()`) — `data/hotspot_status.py` 의
`hotspot_status(..., today: date)` 선례를 따른다. 회귀 테스트가 벽시계에 의존하지 않고
결정론적으로 경계 구간·임박 상태를 재현할 수 있어야 하기 때문이다.

실패는 예외가 아니라 `status` 필드로 반환한다(D9). 룰 카탈로그가 비어 있거나 필요한 룰이
빠져 있으면 `not_found` 가 아니라 `error`/`rule_catalog_not_loaded` 다(D50 어휘 재사용) —
"기한 없음"과 "판정 근거 자체가 없음"은 다르다.

NULL·판독 불가한 날짜는 건너뛰고 `not_considered` 에 사유를 남긴다(D62 — 모름과 없음의 구분).
0건이 나오는 것 자체는 실패가 아니다 — 9자산 전부가 취득 후 24개월을 이미 넘긴 시드 구조에서는
기본 호출이 TAX-CREDIT-2Y 경로에서 정직하게 0건인 것이 정상이다.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from data.rules import engine

__all__ = ["DEFAULT_WINDOW_DAYS", "track_deadlines"]

DEFAULT_WINDOW_DAYS = 180

TAX_CREDIT_RULE_ID = "TAX-CREDIT-2Y"
SAFETY_INSPECTION_RULE_ID = "SAFETY-INSPECTION"
TAX_CREDIT_MONTHS = 24  # 취득 후 사후관리 기한(개월) — 룰 message·interpretation 과 같은 통상값

STATE_UPCOMING = "UPCOMING"
STATE_IN_REVIEW_BAND = "IN_REVIEW_BAND"
STATE_OVERDUE = "OVERDUE"

_DISCLAIMER = (
    "TAX-CREDIT-2Y 는 취득일 기준 통상 24개월 사후관리 기간의 해석이며, 경계 구간"
    "(review_band)에 든 자산은 IN_REVIEW_BAND 로만 표시하고 임박/경과를 단정하지 않는다"
    "(D62 — 기산일 해석에 따라 달라질 수 있어 사람 검토가 필요하다). SAFETY-INSPECTION 은 "
    "assets.safety_inspection_target·inspection_valid_until 사실값에만 의존하며, 안전검사 "
    "대상 기계 목록 자체의 법적 정확성(시행령 제78조 고시)은 검증하지 않는다. 두 경로 모두 "
    "목업 데이터 기준이며 실제 적용에는 전문가 검토가 필요하다."
)


def _fail(reason: str, message: str, status: str = "error") -> dict:
    return {"status": status, "reason": reason, "message": message}


def _as_int(value: object) -> int | None:
    """정수로 해석되면 int, 아니면 None. 추정하지 않는다 (data/maint_value.py 와 같은 태도)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _as_date(value: object) -> date | None:
    """ISO 날짜로 읽히지 않으면 None. 판독 실패를 오늘/0 으로 메우지 않는다 (D62)."""
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _add_months(d: date, months: int) -> date:
    """달력 기준 N개월 뒤. 말일 보정은 그 달의 마지막 날로 자른다(1/31 → 2/28).

    `data/maint_value.py` 의 `_months_ago`(역방향)와 같은 보정 방식이다.
    """
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = d.day
    while day > 0:
        try:
            return d.replace(year=year, month=month, day=day)
        except ValueError:
            day -= 1
    return d.replace(year=year, month=month, day=1)


def _months_between(start: date, end: date) -> int:
    """`data/rules/engine.py:_months_between` 과 **완전히 같은 정의**를 쓴다 — TAX-CREDIT-2Y 의
    `months_since_acquisition` 판정(처분 precheck)과 이 기한 추적이 같은 자산에 대해 다른 개월
    수를 말하면 안 되기 때문이다. `engine` 은 이 함수를 공개하지 않으므로(비공개 헬퍼) 값 하나
    짜리 순수 함수를 그대로 옮겨 적었다 — import 하지 않는 이유는 私(private) 이름이라서다.
    """
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return months


class _CatalogError(Exception):
    """룰 카탈로그 로드·정합 실패 — `_load_catalog` 안에서만 던지고 즉시 status 로 닫는다."""

    def __init__(self, response: dict) -> None:
        super().__init__(response.get("message", ""))
        self.response = response


def _load_catalog() -> tuple[engine.Rule, engine.Rule, list]:
    """TAX-CREDIT-2Y·SAFETY-INSPECTION 룰과 전자의 `review_band` 를 파일에서 로드한다.

    review_band 를 하드코딩하지 않는다 — 이 함수가 실패하면 호출자는 `rule_catalog_not_loaded`
    로 닫는다(D50 어휘 재사용). "기한 없음"과 "판정 근거 자체가 없음"을 구분하기 위함이다.
    """
    try:
        laws = engine.load_laws()
        rules = engine.load_rules(laws)
    except engine.RuleIntegrityError as e:
        raise _CatalogError(
            _fail("rule_catalog_not_loaded", f"룰 카탈로그 무결성 위반: {e}")
        ) from e
    except (OSError, ValueError) as e:
        raise _CatalogError(
            _fail("rule_catalog_not_loaded", f"룰 카탈로그를 불러오지 못했습니다: {e}")
        ) from e

    missing = [
        rule_id
        for rule_id in (TAX_CREDIT_RULE_ID, SAFETY_INSPECTION_RULE_ID)
        if rule_id not in rules
    ]
    if missing:
        raise _CatalogError(
            _fail(
                "rule_catalog_not_loaded",
                f"필요한 룰이 카탈로그에 없습니다: {', '.join(missing)}",
            )
        )

    tax_rule = rules[TAX_CREDIT_RULE_ID]
    review_band = (tax_rule.boundary or {}).get("review_band")
    if not isinstance(review_band, (list, tuple)) or len(review_band) != 2:
        raise _CatalogError(
            _fail(
                "rule_catalog_not_loaded",
                f"{TAX_CREDIT_RULE_ID} 에 boundary.review_band 가 없거나 형식이 올바르지 "
                f"않습니다: {review_band!r}",
            )
        )

    return tax_rule, rules[SAFETY_INSPECTION_RULE_ID], list(review_band)


def _scan_tax_credit(
    con: sqlite3.Connection,
    *,
    asset_id: str | None,
    today: date,
    window_days: int,
    rule: engine.Rule,
    review_band: list,
) -> tuple[list[dict], list[str]]:
    lo, hi = review_band
    sql = "SELECT asset_id, acquired_at FROM assets WHERE tax_credit_applied = 1"
    params: list = []
    if asset_id is not None:
        sql += " AND asset_id = ?"
        params.append(asset_id)
    sql += " ORDER BY asset_id"

    items: list[dict] = []
    not_considered: list[str] = []
    for row in con.execute(sql, params).fetchall():
        acquired = _as_date(row["acquired_at"])
        if acquired is None:
            not_considered.append(
                f"{row['asset_id']}: acquired_at 판독 불가 — TAX-CREDIT-2Y 판정에서 제외했다"
            )
            continue

        months_since = _months_between(acquired, today)
        due_date = _add_months(acquired, TAX_CREDIT_MONTHS)
        days_remaining = (due_date - today).days

        if months_since >= hi:
            continue  # 사후관리 기간을 이미 넘겼다 — 정직한 제외 (D62)
        elif lo <= months_since < hi:
            state = STATE_IN_REVIEW_BAND
        elif months_since < lo and days_remaining <= window_days:
            state = STATE_UPCOMING
        else:
            continue

        items.append(
            {
                "asset_id": row["asset_id"],
                "type": TAX_CREDIT_RULE_ID,
                "law_refs": list(rule.law_refs),
                "due_date": due_date.isoformat(),
                "days_remaining": days_remaining,
                "state": state,
                "message": rule.message,
                "resolve_options": list(rule.resolve_options),
            }
        )
    return items, not_considered


def _scan_safety_inspection(
    con: sqlite3.Connection,
    *,
    asset_id: str | None,
    today: date,
    window_days: int,
    rule: engine.Rule,
) -> tuple[list[dict], list[str]]:
    sql = (
        "SELECT asset_id, inspection_valid_until FROM assets "
        "WHERE safety_inspection_target = 1 AND inspection_valid_until IS NOT NULL"
    )
    params: list = []
    if asset_id is not None:
        sql += " AND asset_id = ?"
        params.append(asset_id)
    sql += " ORDER BY asset_id"

    items: list[dict] = []
    not_considered: list[str] = []
    for row in con.execute(sql, params).fetchall():
        due_date = _as_date(row["inspection_valid_until"])
        if due_date is None:
            not_considered.append(
                f"{row['asset_id']}: inspection_valid_until 판독 불가 — SAFETY-INSPECTION "
                "판정에서 제외했다"
            )
            continue

        days_remaining = (due_date - today).days
        if due_date < today:
            state = STATE_OVERDUE  # window 무관 — 만료 후가 더 위험하다
        elif days_remaining <= window_days:
            state = STATE_UPCOMING
        else:
            continue

        items.append(
            {
                "asset_id": row["asset_id"],
                "type": SAFETY_INSPECTION_RULE_ID,
                "law_refs": list(rule.law_refs),
                "due_date": due_date.isoformat(),
                "days_remaining": days_remaining,
                "state": state,
                "message": rule.message,
                "resolve_options": list(rule.resolve_options),
            }
        )
    return items, not_considered


def track_deadlines(
    con: sqlite3.Connection,
    *,
    asset_id: str | None = None,
    window_days: int | str = DEFAULT_WINDOW_DAYS,
    today: date | None = None,
) -> dict:
    """공개 진입점 — **얇은 래퍼**. 입력 파싱·조회·조립 어디서 난 예외든 status 로 닫는다 (D9)."""
    try:
        return _track_deadlines(con, asset_id=asset_id, window_days=window_days, today=today)
    except Exception as e:  # noqa: BLE001 — 도구는 예외를 던지지 않는다 (D9)
        return _fail("internal_error", f"기한 추적 중 처리 오류: {e}")


def _track_deadlines(
    con: sqlite3.Connection,
    *,
    asset_id: object,
    window_days: object,
    today: object,
) -> dict:
    # ── 1) 입력 검증 ────────────────────────────────────────────────────────
    if asset_id is not None and (not isinstance(asset_id, str) or not asset_id.strip()):
        return _fail("invalid_input", f"asset_id 는 비어있지 않은 문자열입니다: {asset_id!r}")
    asset_id = asset_id.strip() if asset_id else None

    if today is not None and not isinstance(today, date):
        return _fail("invalid_input", f"today 는 date 타입입니다: {today!r}")
    today = today or date.today()

    days = _as_int(window_days)
    if days is None or days < 0:
        return _fail(
            "invalid_input",
            f"window_days 는 0 이상의 정수입니다: {window_days!r}",
        )

    # ── 2) 룰 카탈로그 로드 (D50 — 미적재는 not_found 가 아니라 error) ────────
    try:
        tax_rule, safety_rule, review_band = _load_catalog()
    except _CatalogError as e:
        return e.response

    # ── 3) 자산 필터 해석 ──────────────────────────────────────────────────
    if asset_id is not None:
        row = con.execute("SELECT asset_id FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
        if row is None:
            return _fail(
                "unknown_asset",
                f"등록되지 않은 자산입니다: {asset_id}",
                status="not_found",
            )

    # ── 4) 두 경로 스캔 ────────────────────────────────────────────────────
    tax_items, tax_skipped = _scan_tax_credit(
        con,
        asset_id=asset_id,
        today=today,
        window_days=days,
        rule=tax_rule,
        review_band=review_band,
    )
    safety_items, safety_skipped = _scan_safety_inspection(
        con,
        asset_id=asset_id,
        today=today,
        window_days=days,
        rule=safety_rule,
    )

    items = tax_items + safety_items
    items.sort(key=lambda it: it["days_remaining"])

    return {
        "status": "ok",
        "evaluated_at": today.isoformat(),
        "window_days": days,
        "items": items,
        "not_considered": tax_skipped + safety_skipped,
        "disclaimer": _DISCLAIMER,
    }
