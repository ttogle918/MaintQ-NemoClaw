# -*- coding: utf-8 -*-
"""classify_expenditure — 수선 지출의 자본적/수익적 분류 (sprint-6 MQ-608, `12 §3`).

**근거 검증이 판정보다 먼저다.** `KR-CITA-ENF-31`(법인세법 시행령 제31조 즉시상각의제)이
`law_refs` 에 없으면 판정 자체를 하지 않고 `status:"error", reason:"law_ref_missing"` 을 돌려준다.
근거 없는 판정이 생성될 경로를 도구 안에서 직접 막는 것이다 (D61 · `11 §4` 불변식 2).

조문 **원문**은 아직 수집 전이다(`fetch_status:"PENDING"`, `text:null` — 법령 API 키 미발급).
그래도 판정은 진행하되 `evidence_completeness:"LAW_TEXT_PENDING"` 로 그 사실을 드러낸다 —
인용은 조문 번호·제목 기준이고, **근거 참조 무결성은 참조 대상의 존재로 이미 보장**되기 때문이다.

경계는 유보한다 (D62). `RESTORE` + `CRITICAL` 은 원상 회복인지 내용연수 연장인지가 실무 최대
논쟁 지점이라 `CAPITAL`/`REVENUE` 로 반올림하지 않고 `HOLD` + 전문가 확인 안내로 닫는다.

⛔ 판정 규칙을 `data/rules/rules/` 에 두지 않는다 — 그 디렉토리는 **처분 플래그 전용**이고
(`disposal_type` 필수) `check_disposal_blockers` 가 디렉토리 전체를 로드하므로 지출 판정 룰을
넣으면 처분 판정에 섞여 들어간다. 그래서 규칙표가 이 파일 안에 있다.
"""

from __future__ import annotations

from datetime import date
from fractions import Fraction

# D73 — `data/` 는 두 프로세스가 공유하는 데이터 계층이다. 인용 문자열 서식(`LawRef.citation`)과
# 시점 조회 규칙(불변식 5)을 여기서 다시 구현하면 룰 개정 시 조용히 어긋난다.
from data.rules.engine import get_law_as_of, load_laws_from_db

from ..db import read_only

DESCRIPTION = (
    "수선·개조 지출을 자본적 지출(CAPITAL)과 수익적 지출(REVENUE)로 분류한다. "
    "수리비를 자산으로 올릴지 당기 비용으로 처리할지, 회계·세무 처리를 물을 때 사용할 것. "
    "part_class 는 추측하지 말고 classify_part_criticality 로 먼저 확인해 넣을 것. "
    "HOLD 는 실패가 아니라 '경계 사안이라 단정하지 않는다'는 판정이다 — "
    "CAPITAL·REVENUE 중 하나로 임의 해석하지 말고 세무 전문가 확인 필요를 그대로 전달할 것. "
    "부품 재고 조회·발주에는 사용 금지(search_inventory·create_po_draft). "
    "이 도구는 판정만 하며 전표 기표·세무 신고를 대신하지 않는다."
)

# ── 계약 상수 ────────────────────────────────────────────────────────────────
LAW_REF_ID = "KR-CITA-ENF-31"  # 법인세법 시행령 제31조 (즉시상각의제)

PART_CLASSES = ("CONSUMABLE", "CRITICAL")
REPAIR_SCOPES = ("RESTORE", "UPGRADE", "OVERHAUL", "REPLACE_UNIT")
VERDICTS = ("CAPITAL", "REVENUE", "HOLD")

# 취득원가 대비 지출 비율 문턱. Fraction 으로 두는 이유는 아래 `_materiality` 주석 참조.
MATERIALITY_THRESHOLD = Fraction(1, 5)  # 0.20

# ── 판정표 (결정론적) ────────────────────────────────────────────────────────
# (repair_scope, part_class) 8조합을 전부 명시한다. `if` 로 접으면 "어느 조합이 어디로 가는지"가
# 코드를 읽어야만 보이고, 나중에 조합이 늘 때 조용히 빠지는 칸이 생긴다.
_RULE_TABLE: dict[tuple[str, str], tuple[str, str]] = {
    ("UPGRADE", "CONSUMABLE"): ("CAPITAL", "UPGRADE"),
    ("UPGRADE", "CRITICAL"): ("CAPITAL", "UPGRADE"),
    ("OVERHAUL", "CONSUMABLE"): ("CAPITAL", "OVERHAUL"),
    ("OVERHAUL", "CRITICAL"): ("CAPITAL", "OVERHAUL"),
    ("RESTORE", "CONSUMABLE"): ("REVENUE", "RESTORE_CONSUMABLE"),
    ("RESTORE", "CRITICAL"): ("HOLD", "RESTORE_CRITICAL_BOUNDARY"),
    ("REPLACE_UNIT", "CONSUMABLE"): ("HOLD", "REPLACE_UNIT_BOUNDARY"),
    ("REPLACE_UNIT", "CRITICAL"): ("HOLD", "REPLACE_UNIT_BOUNDARY"),
}

_RULE_REASONING = {
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

_ESCALATION_REASONING = {
    "MATERIALITY_AT_OR_ABOVE_THRESHOLD": (
        "취득원가 대비 지출 비율이 문턱(20%) 이상이라 소액 수선으로 볼 수 없다 — "
        "기본 판정({base})을 유보(HOLD)로 격상했다."
    ),
    "MATERIALITY_UNKNOWN": (
        "취득원가를 알 수 없어 지출 비율(20% 기준)을 계산하지 못했다 — "
        "'모른다'를 '문턱 미만'으로 처리하지 않고 기본 판정({base})을 유보(HOLD)로 격상했다 (D62)."
    ),
}

_BASE_NOT_CONSIDERED = (
    "회사 내부 자본화 기준·소액수선비 특례 적용 여부 (사내 회계정책은 원천이 없다)",
    "같은 자산에 대한 사업연도 누적 지출액 — 이 판정은 지출 건별이다",
    "부가가치세 매입세액 공제·세금계산서 요건",
    "자본화 시 감가상각 재계산(내용연수 연장분)과 장부가액 영향",
    "수선 내용의 사실관계 (현장 증빙·수리 명세서 확인 전)",
)

_DISCLAIMER = (
    "통상 사례 기준 목업 판정이다. 세무 신고·회계 기표의 근거로 그대로 사용할 수 없으며 "
    "실제 적용에는 전문가 검토가 필요하다."
)
_DISCLAIMER_LAW_PENDING = (
    " 인용한 조문의 원문은 아직 수집되지 않았으며(fetch_status=PENDING), 인용은 조문 번호·제목 "
    "기준이다."
)


# ── 입력 해석 ────────────────────────────────────────────────────────────────
def _error(reason: str, message: str) -> dict:
    """실패는 예외가 아니라 status 로 돌려준다 (D9·D46)."""
    return {"status": "error", "reason": reason, "message": message}


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


# ── 본체 ─────────────────────────────────────────────────────────────────────
def classify_expenditure(
    part_class: str,
    repair_scope: str,
    amount: int,
    asset_id: str | None = None,
) -> dict:
    """지출을 CAPITAL | REVENUE | HOLD 로 분류한다.

    **필수 파라미터에 기본값을 두지 않는다 (D80).** 인자 누락은 도구 코드가 아니라 MCP 스키마
    검증이 앞단에서 막는다 — 기본값을 두면 FastMCP 가 `required` 를 빼서 optional 로 노출하고,
    LLM 이 인자 없이 호출 → `invalid_input` → 재시도하는 낭비 루프가 생긴다. D9 는 **도구 로직의
    실패**에 대한 규칙이지 호출 규약 위반에 대한 규칙이 아니다. 선택적인 `asset_id` 만 기본값을
    갖는다.

    **값이 잘못된 경우**(enum 밖·`amount <= 0`·타입 불일치)는 여전히 D9 대상이라
    `status:"error", reason:"invalid_input"` 으로 돌려준다 — 호출 규약은 지켜졌고 판정이 실패한 것이다.
    """
    try:
        return _classify(part_class, repair_scope, amount, asset_id)
    except Exception as exc:  # noqa: BLE001 — 도구는 예외를 던지지 않는다 (D9)
        return _error("internal_error", f"판정 중 오류가 발생했습니다: {exc}")


def _classify(
    part_class: object,
    repair_scope: object,
    amount: object,
    asset_id: object,
) -> dict:
    # ── 1. 입력 검증 — enum 밖 값은 폴백하지 않는다 -------------------------
    if part_class not in PART_CLASSES:
        return _error(
            "invalid_input",
            f"part_class 는 {' | '.join(PART_CLASSES)} 중 하나여야 합니다: {part_class!r}. "
            "부품 등급은 classify_part_criticality 로 확인하세요.",
        )
    if repair_scope not in REPAIR_SCOPES:
        return _error(
            "invalid_input",
            f"repair_scope 는 {' | '.join(REPAIR_SCOPES)} 중 하나여야 합니다: {repair_scope!r}",
        )
    parsed_amount = _as_amount(amount)
    if parsed_amount is None:
        return _error("invalid_input", f"amount 는 지출 금액(정수, 원)입니다: {amount!r}")
    if parsed_amount <= 0:
        return _error("invalid_input", f"amount 는 0보다 커야 합니다: {parsed_amount}")
    if asset_id is not None and (not isinstance(asset_id, str) or not asset_id.strip()):
        return _error("invalid_input", f"asset_id 는 비어있지 않은 문자열입니다: {asset_id!r}")

    # ── 2. 조회 -----------------------------------------------------------
    try:
        with read_only() as con:
            laws = load_laws_from_db(con)
            asset_row = None
            if asset_id is not None:
                asset_row = con.execute(
                    "SELECT asset_id, name, acquisition_cost FROM assets WHERE asset_id = ?",
                    (asset_id,),
                ).fetchone()
    except Exception as exc:  # noqa: BLE001
        return _error("db_error", str(exc))

    # ── 3. 근거 검증이 판정보다 먼저다 (D61 · 불변식 2) ---------------------
    today = date.today()
    try:
        law = get_law_as_of(laws, LAW_REF_ID, today)
    except KeyError:
        return _error(
            "law_ref_missing",
            f"근거 조문 {LAW_REF_ID} 이 law_refs 에 등록돼 있지 않습니다. "
            "근거 없는 지출 판정은 하지 않습니다 (D61).",
        )
    except ValueError as exc:  # 시점 밖 조문 — 조용히 최신본으로 대체하지 않는다 (불변식 5)
        return _error("law_not_effective", str(exc))

    # ── 4. 자산 해석 (asset_id 를 준 경우에만) ------------------------------
    if asset_id is not None and asset_row is None:
        return {
            "status": "not_found",
            "reason": "unknown_asset",
            "message": f"등록되지 않은 자산입니다: {asset_id!r}",
        }

    # ── 5. 판정 ------------------------------------------------------------
    verdict, basis = _RULE_TABLE[(repair_scope, part_class)]
    reasons = [_RULE_REASONING[basis]]

    materiality = _materiality(
        parsed_amount,
        asset_row["acquisition_cost"] if asset_row is not None else None,
        asset_found=asset_row is not None,
    )
    escalation = None
    if materiality["state"] in ("AT_OR_ABOVE_THRESHOLD", "UNKNOWN"):
        escalation = f"MATERIALITY_{materiality['state']}"
        reasons.append(_ESCALATION_REASONING[escalation].format(base=verdict))
        verdict = "HOLD"  # 결과와 무관하게 격상
    materiality["escalated"] = escalation is not None

    not_considered = list(_BASE_NOT_CONSIDERED)
    if materiality["state"] == "NOT_EVALUATED":
        not_considered.insert(
            0, "취득원가 대비 지출 비율(20% 기준) — asset_id 미제공으로 평가하지 않았다"
        )

    requires_expert_review = verdict == "HOLD"
    if requires_expert_review:
        reasons.append("세무 전문가 확인이 필요하다.")

    # 조문 원문이 없으면 그 사실을 판정에 실어 보낸다 (판정 자체는 막지 않는다)
    law_text_pending = not law.is_fetched
    disclaimer = _DISCLAIMER + (_DISCLAIMER_LAW_PENDING if law_text_pending else "")

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
