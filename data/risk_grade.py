# -*- coding: utf-8 -*-
"""건물 단위 위험 프로파일 등급 산출 — **공유 데이터 계층** (S18, `11 §10-2`, D101·D102).

`화기 취급`·`위험물 보관량`·`수전 용량` 3속성을 점수화해 위험등급을 산출하고, 마지막으로
`risk_profile.risk_grade`에 저장된 등급과 달라졌는지(`changed`)를 알려준다. `mcp_server` 도
`backend` 도 여기서 import하지 않는다(D15) — 커넥션은 호출자가 읽기 전용으로 열어 넘긴다
(`data/ownership.py`·`data/maint_value.py`와 같은 규약).

⛔ **이 모듈은 아무것도 쓰지 않는다.** `risk_profile.risk_grade`·`risk_grade_updated_at`을
   갱신하는 코드를 여기 두지 않는다 — 절대 규칙 1(MCP 쓰기 도구는 `create_po_draft`·
   `generate_disposal_document`·`create_repair_record` 3종뿐)이 `risk_profile`을 포함하지
   않으므로, "변동 감지"는 알림 정보일 뿐 자동 반영이 아니다(D10). 이 함수는 순수 조회+계산이다.

실패는 예외가 아니라 `status` 필드로 반환한다(D9) — 공개 진입점 `risk_grade()`가 예외를
전부 삼켜 `internal_error`로 닫는다(`data/maint_value.py`의 얇은 래퍼 관행과 동일).

★ `<=4 LOW / 5~6 MEDIUM / >=7 HIGH` 임계값은 **이 모듈이 정본이다** — 다른 곳에 사본을 두지
   않는다. `data/seed.py`의 `_risk_grade_from_score()`는 시드 자가검증(㉟) 전용 역산일 뿐
   정본이 아니다(seed.py 주석 참조).
"""

from __future__ import annotations

from data.dbcompat import DbConnection


# LOW=1 / MEDIUM=2 / HIGH=3. 이 모듈의 정본 상수 — 다른 모듈이 사본을 두지 않는다.
GRADE_ORDER: dict[str, int] = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
GRADE_SCALE: tuple[str, ...] = ("LOW", "MEDIUM", "HIGH")

# 점수화 대상 3속성 — 순서가 rationale 문장 조립에도 그대로 쓰인다.
_SCORED_ATTRS: tuple[tuple[str, str], ...] = (
    ("fire_handling", "화기 취급"),
    ("hazmat_volume", "위험물 보관량"),
    ("power_capacity", "수전용량"),
)

DISCLAIMER = (
    "이 등급은 통상 기준 목업 산식이다. 실제 화재·환경 규제상 위험평가를 대체하지 않는다."
)


def _fail(reason: str, message: str | None = None, status: str = "error") -> dict:
    d: dict = {"status": status, "reason": reason}
    if message:
        d["message"] = message
    return d


def _grade_from_score(score: int) -> str:
    """이 모듈의 정본 임계값. `<=4 LOW / 5~6 MEDIUM / >=7 HIGH`."""
    if score <= 4:
        return "LOW"
    if score <= 6:
        return "MEDIUM"
    return "HIGH"


def _as_date_str(value: object) -> str | None:
    """`YYYY-MM-DD HH:MM:SS` 저장값에서 날짜만 잘라 낸다. 값이 없으면 None."""
    if not value:
        return None
    return str(value)[:10]


def risk_grade(
    con: DbConnection,
    *,
    building_id: str | None = None,
    asset_id: str | None = None,
) -> dict:
    """건물 위험등급을 산출한다. 공개 진입점 — **얇은 래퍼**.

    본체를 통째로 감싸 입력 파싱·조회·응답 조립에서 난 예외까지 status로 닫는다(D9).
    """
    try:
        return _risk_grade(con, building_id, asset_id)
    except Exception as e:  # noqa: BLE001 — 도구는 예외를 던지지 않는다 (D9)
        return _fail("internal_error", f"위험등급 산출 중 처리 오류: {e}")


def _risk_grade(con: DbConnection, building_id: object, asset_id: object) -> dict:
    # ── 0) 입력 검증 — either-or (D80 예외 패턴) ──────────────────────────────
    for label, value in (("building_id", building_id), ("asset_id", asset_id)):
        if value is not None and not isinstance(value, str):
            return _fail("invalid_input", f"{label} 는 문자열 식별자입니다: {value!r}")
    building_id = building_id.strip() if building_id else None
    asset_id = asset_id.strip() if asset_id else None

    if bool(building_id) == bool(asset_id):
        # 둘 다 없거나(둘 다 falsy) 둘 다 있으면(둘 다 truthy) 거부한다
        return _fail("invalid_input", "building_id 또는 asset_id 중 하나만 지정해야 합니다")

    # ── 1) asset_id 경로 — assets.building_id 로 해석한다 ────────────────────
    if asset_id:
        asset_row = con.execute(
            "SELECT asset_id, building_id FROM assets WHERE asset_id = ?", (asset_id,)
        ).fetchone()
        if asset_row is None:
            return {
                "status": "not_found",
                "reason": "unknown_asset",
                "message": f"등록되지 않은 자산입니다: {asset_id}",
            }
        building_id = asset_row["building_id"]
        if not building_id:
            return {
                "status": "not_found",
                "reason": "no_building",
                "message": f"{asset_id} 에 building_id 가 등록돼 있지 않습니다",
            }

    # ── 2) risk_profile 조회 ──────────────────────────────────────────────
    profile = con.execute(
        "SELECT building_id, fire_handling, hazmat_volume, power_capacity, product_type,"
        " risk_grade, risk_grade_updated_at FROM risk_profile WHERE building_id = ?",
        (building_id,),
    ).fetchone()
    if profile is None:
        return {
            "status": "not_found",
            "reason": "unknown_building",
            "message": f"위험 프로파일이 등록되지 않은 건물입니다: {building_id}",
        }

    facts = {
        "fire_handling": profile["fire_handling"],
        "hazmat_volume": profile["hazmat_volume"],
        "power_capacity": profile["power_capacity"],
        "product_type": profile["product_type"],  # 점수화 안 함 — 정보성 필드로만 노출
    }

    # ── 3) 점수화 — 하나라도 NULL 이면 추측하지 않는다 (D62) ──────────────────
    not_considered: list[str] = []
    missing = [label for col, label in _SCORED_ATTRS if facts[col] is None]
    if missing:
        current_grade = None
        rationale = f"{'·'.join(missing)} 미확인으로 등급 산출 보류 (D62)"
        not_considered.append(f"미확인 속성({', '.join(missing)})으로 등급 산출 보류")
    else:
        score = sum(GRADE_ORDER[facts[col]] for col, _label in _SCORED_ATTRS)
        current_grade = _grade_from_score(score)
        parts = "·".join(f"{label} {facts[col]}" for col, label in _SCORED_ATTRS)
        rationale = f"{parts} → 점수 {score} → {current_grade}"

    # ── 4) 변동 감지 — 저장만, 반영은 하지 않는다 ──────────────────────────────
    stored_grade = profile["risk_grade"]
    if stored_grade is None:
        changed = False
        rationale += " (최초 산출 — 저장된 등급 이력 없음)"
    else:
        changed = current_grade is not None and current_grade != stored_grade

    return {
        "status": "ok",
        "building_id": building_id,
        "facts": facts,
        "current_grade": current_grade,
        "stored_grade": stored_grade,
        "stored_grade_updated_at": _as_date_str(profile["risk_grade_updated_at"]),
        "changed": changed,
        "grade_scale": list(GRADE_SCALE),
        "rationale": rationale,
        "not_considered": not_considered,
        "disclaimer": DISCLAIMER,
    }
