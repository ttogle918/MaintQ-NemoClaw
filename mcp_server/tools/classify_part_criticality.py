# -*- coding: utf-8 -*-
"""classify_part_criticality — 부품 등급 조회 (MQ-606, `docs/12_MAINT_VALUE.md §10`).

**추론하지 않는다.** `parts.part_class` 를 그대로 읽어 돌려주는 단순 조회다.
등급이 비어 있으면 `status:"error"` 로 닫는다 — 도구가 등급을 추측하면
`assess_repair_value` 의 3지 판단(수리/교체/현상매각)이 근거를 잃는다.
D12 가 `related_parts` 에서 세운 태도("부품 특정을 LLM 추측에 위임하지 않는다")를
등급 판정에도 그대로 적용한 것이다.

`reviewed:false` 는 장식이 아니다 — `part_class` 는 `related_parts.seed.json` 과 같은
**미검수 초안**이고(`05_DB_SCHEMA` parts DDL 주석), 이 값이 하류 verdict 를 가른다.
실패는 예외가 아니라 status 로 반환한다 (D9·D46).
"""

from __future__ import annotations

from ..db import read_only

# parts.part_class 에 허용된 값 (`12 §9`). 이 밖의 값은 "모른다"이지 새 등급이 아니다.
PART_CLASSES = ("CONSUMABLE", "CRITICAL")

# `related_parts.seed.json` 의 reviewed 플래그와 같은 성격 — 사람 검수 전이다.
REVIEWED = False
REVIEW_NOTE = "part_class 는 미검수 초안"

DESCRIPTION = (
    "부품이 핵심 부품(CRITICAL)인지 소모품(CONSUMABLE)인지 조회한다. 수리 여부·지출 성격"
    "(자본적/수익적)·잔존가치 판단의 입력이 필요할 때 사용할 것. "
    "이 도구는 등록된 등급을 읽어올 뿐 추론하지 않는다 — 등급이 지정되지 않은 부품은 "
    "error(part_class_not_set)를 돌려주며, 이때 부품 이름이나 용도로 등급을 추측하지 말 것. "
    "재고 수량·단가 조회에는 사용 금지(search_inventory·get_supplier_quotes 를 쓸 것). "
    "반환되는 등급은 사람 검수 전 초안(reviewed=false)이므로 단정적으로 서술하지 말 것."
)

NOT_CONSIDERED = [
    "부품 이름·카테고리로부터의 등급 추론 (금지 — 등록된 값만 사용, D12)",
    "설비별 중요도 차이 (같은 부품이라도 라인 위치에 따라 다를 수 있으나 원천 없음)",
    "재고 수량·리드타임 (search_inventory·get_supplier_quotes 소관)",
]

DISCLAIMER = (
    "part_class 는 사람 검수를 거치지 않은 초안이다(reviewed=false). "
    "수리/교체/처분 판단에 쓸 때는 등급 자체를 정비 담당자가 확인한 뒤 확정할 것."
)


def _fail(reason: str, message: str, status: str = "error") -> dict:
    return {"status": status, "reason": reason, "message": message}


def classify_part_criticality(part_no: str) -> dict:
    """공개 진입점 — **얇은 래퍼**.

    본체를 통째로 감싸 입력 파싱·응답 조립에서 난 예외까지 status 로 닫는다 (D9·D46).
    DB 블록만 try 로 감싸면 "어떤 입력에도 예외가 새지 않음"이 코드 위치에 의존하게 되고,
    나중에 조립부에 한 줄이 추가되는 순간 조용히 깨진다 — Stage 4 다른 도구와 같은 형태다.
    반환 계약(status·reason 문자열 집합)은 이 래퍼로 바뀌지 않는다. MQ-609 가 그대로 전파한다.
    """
    try:
        return _classify(part_no)
    except Exception as e:  # noqa: BLE001 — 도구는 예외를 던지지 않는다
        return _fail("internal_error", f"부품 등급 조회 중 처리 오류: {e}")


def _classify(part_no: str) -> dict:
    if not isinstance(part_no, str) or not part_no.strip():
        return _fail(
            "invalid_input",
            f"part_no 는 비어 있지 않은 부품 번호 문자열입니다: {part_no!r}",
        )
    part_no = part_no.strip()

    try:
        with read_only() as con:
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
        "reviewed": REVIEWED,
        "note": REVIEW_NOTE,
        "not_considered": list(NOT_CONSIDERED),
        "disclaimer": DISCLAIMER,
    }
