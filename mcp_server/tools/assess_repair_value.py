# -*- coding: utf-8 -*-
"""assess_repair_value — 수리 / 교체 / 현상매각 3지 판단 (MQ-609, S1+ · `docs/12_MAINT_VALUE.md §1·§9·§11`).

이 도구가 지키는 순서와 태도는 전부 "지어내지 않기" 하나에서 나온다.

★ 최우선 분기 — 반복 고장이면 3지 판단을 **하지 않는다** (D2 · `12 §11`)
  `repeat_failure == true` 면 다른 계산을 하기 전에 즉시 `ROOT_CAUSE_FIRST` 로 닫고
  `alternatives` 를 **빈 배열**로 돌려준다. 3지 선택지를 함께 주면 에이전트가 그중 하나를
  고르기 때문이다 — 그게 이 분기의 존재 이유다. S3 발주 보류(`po_card` variant `hold`, D35)가
  그대로 적용돼야 한다.

★ 시장가는 없으면 없다고 한다 (D65 · D74)
  `residual_curve` 는 **목업 정률법 산출물**이고 실거래 데이터가 아니다. 연차가 격자 밖이거나
  행이 없거나 `acquisition_cost` 가 NULL 이면 `market_value_before = None` 이고 판정은 `HOLD` 다.
  ⛔ **인접 버킷으로 보간하지 않는다.** 값이 없는데 판단하면 지어내는 것이다.
  ⚠ 목업 곡선은 전 카테고리 값이 동일하다 — 즉 `category` 는 조인 키일 뿐 **판정에 영향을 주지 않는다**.
     이 사실을 `not_considered` 와 `disclaimer` 에 드러낸다(데모에서 카테고리별 잔가 차이는 보여줄 수 없다).

★ 하위 도구 실패를 삼키지 않는다
  `classify_part_criticality` · `get_maintenance_metrics` 중 하나라도 `status != "ok"` 면
  그 `status`·`reason` 을 **그대로 전파**한다. 기본값으로 진행하면 **없는 근거로 판단**하게 된다.

────────────────────────────────────────────────────────────────────────────────
★ 값을 어디서 읽는가 — 이 규약을 어기면 판정이 조용히 틀린다 (Stage 4 B-1 재발 방지)

  **룰 사실 키**(`engine.ASSET_FACT_COLUMNS` ∪ 엔진 파생 키) → `facts[...]` (키 부재 = 모른다, D62)
  그 **밖**의 컬럼                                        → `row[...]`

`build_facts` 는 `ASSET_FACT_COLUMNS` 의 컬럼과 판정 시점 파생 키만 만든다. 이 도구가 쓰는
`category`·`acquisition_cost`·`book_value`·`parts_eol_flag` 는 **전부 목록 밖**이라 `facts` 에서
읽으면 DB 에 값이 있어도 항상 None 이 나온다 — Stage 4 에서 실제로 그 결함(B-1)이 났다.
`_fact()` 접근자가 목록 밖 컬럼을 `facts` 에서 읽으려 하면 즉시 실패시킨다.
`acquired_at` 만 사실 키이고, `build_facts` 를 경유하는 덕에 **판독 불가한 날짜가 자동으로
"모른다"로 떨어진다**(→ 시장가 null → HOLD). 직접 `row["acquired_at"]` 을 파싱하면 그 보호가 사라진다.
────────────────────────────────────────────────────────────────────────────────

읽기 전용이다 (`read_only` 만, D10). 실패는 예외가 아니라 `status` 로 돌려준다 (D9·D46).
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

# D73 — `data/` 는 두 프로세스가 공유해도 되는 데이터 계층이다(`backend` ↔ `mcp_server`
# 상호 import 만 금지). `server.py:28` 이 레포 루트를 sys.path 에 넣는다.
from data.rules.engine import ASSET_FACT_COLUMNS, build_facts

from ..db import read_only

# 하위 도구를 **모듈 import 해서 호출**한다 (MCP 왕복을 한 번 더 돌지 않는다).
from .classify_part_criticality import classify_part_criticality

# 반복 고장 기준(30일 3회)의 단일 출처는 `get_error_history` 다 (D2·D29).
# 여기서 숫자를 다시 적으면 한쪽만 바뀌었을 때 S3 판정과 이 도구의 사유 문장이 어긋난다.
from .get_error_history import REPEAT_THRESHOLD, REPEAT_WINDOW_DAYS
from .get_maintenance_metrics import get_maintenance_metrics

# ---------------------------------------------------------------- 상수

REPAIR_RECOMMENDED = "REPAIR_RECOMMENDED"
REPLACE_RECOMMENDED = "REPLACE_RECOMMENDED"
SELL_AS_IS = "SELL_AS_IS"
ROOT_CAUSE_FIRST = "ROOT_CAUSE_FIRST"
HOLD = "HOLD"

VERDICTS = (REPAIR_RECOMMENDED, REPLACE_RECOMMENDED, SELL_AS_IS, ROOT_CAUSE_FIRST, HOLD)

# `classify_expenditure`(MQ-608)와 같은 enum. 폴백하지 않는다 — 오타를 그대로 흘리면
# 회복 계수가 조용히 바뀌어 verdict 가 달라진다.
REPAIR_SCOPES = ("RESTORE", "UPGRADE", "OVERHAUL", "REPLACE_UNIT")
DEFAULT_REPAIR_SCOPE = "RESTORE"

# 잔가 격자 (MQ-603/D74 산출물과 동일). 격자 밖 연차는 행이 없으므로 조회 자체를 하지 않는다.
AGE_BUCKETS: tuple[tuple[int, int, str], ...] = (
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
LIFE_RECOVERY_BY_SCOPE: dict[str, float] = {
    "RESTORE": 0.10,
    "REPLACE_UNIT": 0.15,
    "UPGRADE": 0.20,
    "OVERHAUL": 0.25,
}

# verdict 문턱 — 전부 결정론적이다(같은 입력이면 같은 판정).
RECOVERY_RATIO_THRESHOLD = 1.0  # 회복액 ≥ 수리비 → 수리가 경제적으로 회수된다
REPLACE_REPAIR_RATIO_THRESHOLD = 0.5  # 누적 수리비가 취득원가의 절반 → 교체 검토 구간

DESCRIPTION = (
    "고장 난 설비를 수리할지, 교체할지, 수리 없이 현상 매각할지를 판단한다. "
    "수리비를 알고 있고 '고쳐 쓰는 게 나은가'를 물을 때 호출할 것. "
    "verdict 가 ROOT_CAUSE_FIRST 면 3지 선택지 자체가 없다 — 같은 고장이 반복되고 있다는 뜻이므로 "
    "수리·교체·매각 중 무엇도 권하지 말고 근본원인 점검을 먼저 안내하고 발주는 보류할 것. "
    "HOLD 는 '문제 없음'이 아니라 시장가를 산출할 원천이 없어 판단을 유보한 것이다 — "
    "금액을 추정해 메우지 말 것. "
    "market_value_before·market_value_after·value_recovery 는 목업 잔가곡선 기반 추정치이며 "
    "실거래가가 아니다(estimates 참조) — 사용자에게 확정 금액처럼 말하지 말 것. "
    "repair_cost 는 이 도구가 검증하지 않는다. 부품 단가·리드타임은 get_supplier_quotes, "
    "재고는 search_inventory, 지출의 세무 성격은 classify_expenditure 를 쓸 것. "
    "처분 가능 여부(법정 조건)는 이 도구가 아니라 check_disposal_blockers 소관이다."
)

NOT_CONSIDERED_BASE = (
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

DISCLAIMER = (
    "시장가는 법정 기준내용연수 기반 목업 잔가곡선(D74) 추정치이며 실거래가가 아니다. "
    "수리 후 회복분의 계수도 계측이 아니라 코드 상수다 — estimates[] 에 나열된 필드는 전부 "
    "추정치이므로 확정 금액처럼 제시하지 말 것 (D65). "
    "목업 곡선은 전 카테고리 값이 같아 category 는 판정에 영향을 주지 않는다. "
    "HOLD 는 '문제 없음'이 아니라 '판단 근거 부족'이다."
)

# `build_facts` 가 `ASSET_FACT_COLUMNS` 밖에서 추가로 만드는 **판정 시점 파생 키**
# (`data/rules/engine.py:389-396`). 이 도구는 `build_facts(row)` 를 인자 없이 부르므로
# 실제로는 앞의 둘만 존재하지만, 가드가 정당한 접근까지 거짓 차단하지 않도록 4종을 전부 넣는다.
# ⚠ `engine` 의 공개 상수로 승격하지 않는다 — `engine.py` 는 MQ-601b 소유다.
ENGINE_DERIVED_FACT_KEYS = frozenset(
    {"disposal_mode", "vat_invoice_issued", "disposal_date", "months_since_acquisition"}
)
FACT_KEYS = frozenset(ASSET_FACT_COLUMNS) | ENGINE_DERIVED_FACT_KEYS


# ---------------------------------------------------------------- 헬퍼


def _fail(reason: str, message: str, status: str = "error") -> dict:
    return {"status": status, "reason": reason, "message": message}


def _assert_fact_column(col: str) -> None:
    """ "값을 어디서 읽는가" 규약을 **주석이 아니라 코드로** 강제한다 (Stage 4 B-1).

    목록 밖 컬럼을 `facts` 에서 읽으면 DB 에 값이 있어도 조용히 None 이 나와
    "취득원가 없음 → HOLD" 같은 **거짓 판정**이 된다. 여기서 시끄럽게 실패시키고,
    공개 진입점이 그것을 `status:"error"` 로 닫는다 — 거짓 판정을 내보내는 것보다 낫다.
    """
    if col not in FACT_KEYS:
        raise KeyError(
            f"{col!r} 은 룰 사실 키가 아니다 (ASSET_FACT_COLUMNS ∪ 엔진 파생 키 밖) — "
            "facts 에 절대 들어오지 않으므로 row[...] 에서 읽어야 한다 (모듈 docstring 규약 · B-1)"
        )


def _fact(facts: dict, col: str) -> Any:
    _assert_fact_column(col)
    return facts.get(col)


def _as_amount(value: object) -> int | None:
    """금액으로 읽히면 int, 아니면 None. **추정하지 않는다.**

    bool 은 거부한다(`True` 가 1원이 되면 안 된다). NaN·inf 도 거부한다 —
    그대로 비교 연산에 들어가면 verdict 가 조용히 뒤집힌다.
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


def _as_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _age_bucket(acquired: date, today: date) -> tuple[int, str | None]:
    """`age = 오늘연도 - 취득연도` → 버킷 라벨. 격자 밖이면 라벨이 None 이다.

    ⛔ 격자 밖(음수·31년 이상)을 인접 버킷으로 **보간하지 않는다** (D65).
       31년 된 설비에 21-30 버킷 잔가율을 쓰면 없는 정확도를 만드는 것이다.
    """
    age = today.year - acquired.year
    for low, high, label in AGE_BUCKETS:
        if low <= age <= high:
            return age, label
    return age, None


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


# ---------------------------------------------------------------- 공개 진입점


def assess_repair_value(
    equipment_id: str,
    failed_part: str,
    repair_cost: int,
    repair_scope: str = DEFAULT_REPAIR_SCOPE,
) -> dict:
    """공개 진입점 — **얇은 래퍼**.

    본체를 통째로 감싸 입력 파싱·응답 조립·엔진 호출에서 난 예외까지 status 로 닫는다 (D9·D46).
    `engine` 은 예외를 던지므로(`RuleIntegrityError`·`KeyError`·`TypeError` 등) 특정 예외만
    잡으면 "어떤 입력에도 예외가 새지 않음"이 코드 위치에 의존하게 된다.

    ★ 필수 파라미터에 기본값을 두지 않는다 (D80) — 인자 누락은 MCP 스키마(pydantic)가
      본체 진입 전에 막는다. 기본값을 두면 "안 준 것"과 "빈 값을 준 것"이 구분되지 않는다.
    """
    try:
        return _assess(equipment_id, failed_part, repair_cost, repair_scope)
    except Exception as e:  # noqa: BLE001 — 도구는 예외를 던지지 않는다 (D9)
        return _fail("internal_error", f"수리가치 판단 중 처리 오류: {e}")


def _assess(equipment_id: str, failed_part: str, repair_cost: object, repair_scope: object) -> dict:
    # ── 0) 입력 검증 ─────────────────────────────────────────────────────────────
    for label, value in (("equipment_id", equipment_id), ("failed_part", failed_part)):
        if not isinstance(value, str) or not value.strip():
            return _fail(
                "invalid_input", f"{label} 는 비어 있지 않은 문자열 식별자입니다: {value!r}"
            )
    equipment_id = equipment_id.strip()
    failed_part = failed_part.strip()

    cost = _as_amount(repair_cost)
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
        with read_only() as con:
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
            today = _as_date(con.execute("SELECT date('now')").fetchone()[0])
            if today is None:
                return _fail("db_error", "기준 일자(date('now')) 를 해석하지 못했습니다")
    except Exception as e:  # noqa: BLE001 — 예외를 status 로 바꿔 반환 (D9)
        return _fail("db_error", str(e))

    # ── 2) 하위 도구 — 실패는 **그대로 전파**한다 ────────────────────────────────
    #     기본값으로 진행하면 없는 근거로 3지 판단을 하게 된다.
    part = classify_part_criticality(failed_part)
    if part.get("status") != "ok":
        return dict(part)

    metrics = get_maintenance_metrics(asset_id=asset_id)
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
                *NOT_CONSIDERED_BASE,
                "시장가·회복분 — 반복 고장 분기에서는 계산하지 않는다 "
                "(근본원인 규명 전의 3지 판단은 근거가 없다)",
            ],
            "disclaimer": DISCLAIMER,
        }

    # ── 4) 시장가 — 없는 정밀도를 만들지 않는다 (D65 · D74) ─────────────────────
    #   `acquired_at` 만 룰 사실 키다. `build_facts` 경유 덕에 판독 불가한 날짜가
    #   자동으로 "모른다"(키 부재)로 떨어진다 — 직접 파싱하면 그 보호가 사라진다 (D62).
    facts = build_facts(asset_row)
    acquired = _as_date(_fact(facts, "acquired_at"))
    # 아래 3종은 ASSET_FACT_COLUMNS **밖**이므로 반드시 row 에서 읽는다 (B-1)
    category = asset.get("category")
    acquisition_cost = _as_amount(asset.get("acquisition_cost"))
    parts_eol = bool(asset.get("parts_eol_flag"))

    hold_reasons: list[str] = []
    age: int | None = None
    bucket: str | None = None
    residual_ratio: float | None = None

    if acquired is None:
        hold_reasons.append("acquired_at 이 없거나 날짜로 읽히지 않아 연차를 산출할 수 없다")
    else:
        age, bucket = _age_bucket(acquired, today)
        if bucket is None:
            hold_reasons.append(
                f"취득 후 {age}년은 잔가곡선 격자(0-30년) 밖이다 — "
                "인접 버킷으로 보간하지 않는다 (D65)"
            )
    if acquisition_cost is None or acquisition_cost <= 0:
        hold_reasons.append("acquisition_cost 가 없어 잔가율을 금액으로 환산할 수 없다")

    if bucket is not None:
        try:
            with read_only() as con:
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
    recovery_coefficient = LIFE_RECOVERY_BY_SCOPE[scope] if part_class == "CRITICAL" else 0.0
    market_value_after: int | None = None
    value_recovery: int | None = None
    recovery_ratio: float | None = None
    if market_value_before is not None:
        market_value_after = int(round(market_value_before * (1.0 + recovery_coefficient)))
        value_recovery = market_value_after - market_value_before
        recovery_ratio = value_recovery / cost

    # ── 5) verdict — 결정론적. 순서 자체가 계약이다 ─────────────────────────────
    verdict, reasoning = _decide(
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
        "alternatives": _alternatives(market_value_before),
        "estimates": estimates,
        "assumptions": assumptions,
        "not_considered": list(NOT_CONSIDERED_BASE),
        "disclaimer": DISCLAIMER,
    }


def _decide(
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
        and cumulative_repair_ratio >= REPLACE_REPAIR_RATIO_THRESHOLD
    ):
        return REPLACE_RECOMMENDED, (
            f"누적 수리비가 취득원가의 {cumulative_repair_ratio:.0%}로 "
            f"문턱({REPLACE_REPAIR_RATIO_THRESHOLD:.0%})을 넘었다. 개별 수리의 회수 여부와 무관하게 "
            "교체를 검토할 구간이다."
        )

    if mtbf_trend == "declining" and market_value_after is not None:
        if repair_cost > market_value_after:
            return SELL_AS_IS, (
                f"고장 간격이 짧아지는 추세(mtbf_trend=declining)인데 수리비 {repair_cost:,}원이 "
                f"수리 후 추정 시장가 {market_value_after:,}원을 넘는다. 수리비를 들여도 자산가치를 "
                "회수하지 못하므로 현상 매각을 검토할 것 (매각 전 처분 법정 조건은 "
                "check_disposal_blockers 로 별도 확인)."
            )

    if recovery_ratio is not None and recovery_ratio >= RECOVERY_RATIO_THRESHOLD:
        return REPAIR_RECOMMENDED, (
            f"수리로 회복되는 추정 잔존가치가 수리비의 {recovery_ratio:.2f}배로 "
            f"문턱({RECOVERY_RATIO_THRESHOLD:.1f})을 넘는다. 수리가 경제적으로 회수되는 구간이다. "
            "회복분은 목업 잔가곡선·목업 계수 기반 추정치이므로 금액 자체를 확정으로 쓰지 말 것."
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


def _alternatives(market_value_before: int | None) -> list[dict]:
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
