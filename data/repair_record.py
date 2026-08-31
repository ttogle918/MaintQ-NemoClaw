# -*- coding: utf-8 -*-
"""repair_record — 수리 증빙 초안 산출 로직 공유 계층 (D73·D101 패턴, P39 수리증빙편).

`mcp_server/tools/create_repair_record.py`(채팅 MCP 도구)·`backend/services/repairs.py`
(화면 REST)가 이 모듈로 위임한다 — `data/po_draft.py`와 같은 구조다. 소비자가 둘이어도
**부품 등급·지출 성격 산출을 두 곳에 복제하지 않기 위해** 여기 한 곳에 둔다.

⛔ 이 모듈은 `mcp_server`도 `backend`도 import하지 않는다(D15 — 두 런타임 프로세스의
상호 import 금지). 커넥션은 호출자가 열어서 넘긴다 — 이 모듈은 DB 경로를 모른다
(`data/maint_value.py`·`data/po_draft.py`와 같은 규약).

**권한은 이 모듈이 갖지 않는다.** `update_draft()`가 여기 있지만, 그것을 실행할 수 있는지는
호출자가 여는 **커넥션의 종류**가 결정한다 — MCP는 `mcp_server/db.py`의 TEMP TRIGGER로
INSERT만 허용된 `repair_writer()`라 `update_draft()`를 부르면 그 자리에서 막히고(D10·D98),
백엔드는 처음부터 UPDATE 권한이 있는 일반 커넥션이다(D111이 정리한 경계).
⛔ **MCP 도구는 `update_draft()`를 부르지 않는다** — 부를 수 없는 게 아니라 부르지 않는다.

스키마 경계 검증 중 **입력 형식 검증은 여기 있고**(`validate_input` — 두 진입점이 같은
9필드를 받으므로 복제할 이유가 없다), **진입점 고유 검증**(HTTP 권한·상태 전이)은 각
호출자에 남는다.

실패는 예외가 아니라 status 필드로 반환한다(D9).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from data import maint_value

#: `work_type` 허용값. 미기재는 거부한다(12 §7) — 폴백으로 PLANNED를 고르지 않는다.
WORK_TYPES: tuple[str, ...] = ("PLANNED", "UNPLANNED")

#: `model` enum (D6·D13·D109). IE5는 정의 조회 경로만이지만 수리 이력에는 남을 수 있다.
VALID_MODELS: tuple[str, ...] = ("iG5A", "S100", "IE5")


def fail(reason: str, message: str, *, status: str = "error", **extra: Any) -> dict:
    """D9 실패 표현. 두 진입점이 같은 모양의 실패를 돌려주게 한다."""
    return {"status": status, "reason": reason, "message": message, **extra}


def _as_positive_int(v: object) -> int | None:
    """`"3"`·`3.0`도 받는다 — D9 타입 폭. `True`는 int이지만 수량이 아니므로 거부한다."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if v.is_integer() else None
    if isinstance(v, str):
        try:
            return int(v.strip())
        except ValueError:
            return None
    return None


def _as_float(v: object) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def validate_parts(parts: object) -> tuple[list[dict] | None, dict | None]:
    """`parts`를 검증하고 정규화한다. 1건 이상, 각 항목은 `part_no` 필수(문자열).

    `serial`·`qty`는 있으면 형식을 검증하고, **없으면 담지 않는다** — 없는 값을 지어내
    채우지 않는다(D62).
    """
    if not isinstance(parts, list) or not parts:
        return None, fail(
            "invalid_input",
            "parts 는 1건 이상의 배열입니다 — 부품 없는 수리 증빙은 근거 패키지에서 쓸모가 없습니다.",
        )
    cleaned: list[dict] = []
    for i, item in enumerate(parts):
        if not isinstance(item, dict):
            return None, fail("invalid_input", f"parts[{i}] 는 객체여야 합니다: {item!r}")
        part_no = item.get("part_no")
        if not isinstance(part_no, str) or not part_no.strip():
            return None, fail(
                "invalid_input", f"parts[{i}].part_no 는 비어 있지 않은 문자열입니다: {part_no!r}"
            )
        entry: dict[str, Any] = {"part_no": part_no.strip()}
        serial = item.get("serial")
        if serial is not None:
            if not isinstance(serial, str):
                return None, fail(
                    "invalid_input", f"parts[{i}].serial 은 문자열입니다: {serial!r}"
                )
            entry["serial"] = serial
        if "qty" in item and item["qty"] is not None:
            qty = _as_positive_int(item["qty"])
            if qty is None or qty <= 0:
                return None, fail(
                    "invalid_input", f"parts[{i}].qty 는 1 이상의 정수입니다: {item['qty']!r}"
                )
            entry["qty"] = qty
        cleaned.append(entry)
    return cleaned, None


def validate_input(
    *,
    equipment_id: object,
    work_type: object,
    repair_scope: object,
    cost: object,
    parts: object,
    downtime_hours: object = None,
    model: object = None,
    error_code: object = None,
    note: object = None,
) -> tuple[dict | None, dict | None]:
    """9필드 입력 검증. `(정규화된 값, None)` 또는 `(None, 실패 dict)`.

    **DB를 열기 전에 부른다** — 거부할 입력으로 DB를 열지 않는다.
    `error_code`는 대문자 canonical로 정규화한다(D25 — 저장 표기는 하나뿐이다).
    """
    if not isinstance(equipment_id, str) or not equipment_id.strip():
        return None, fail(
            "invalid_input", f"equipment_id 는 비어 있지 않은 문자열입니다: {equipment_id!r}"
        )

    if work_type not in WORK_TYPES:
        return None, fail(
            "invalid_input",
            f"work_type 은 {' | '.join(WORK_TYPES)} 중 하나여야 합니다 (미기재 거부, 12 §7): {work_type!r}",
        )

    if repair_scope not in maint_value.REPAIR_SCOPES:
        return None, fail(
            "invalid_input",
            f"repair_scope 는 {' | '.join(maint_value.REPAIR_SCOPES)} 중 하나여야 합니다"
            f" (폴백 금지): {repair_scope!r}",
        )

    cost_int = _as_positive_int(cost)
    if cost_int is None or cost_int <= 0:
        return None, fail("invalid_input", f"cost 는 0보다 큰 정수(원)입니다: {cost!r}")

    downtime: float | None = None
    if downtime_hours is not None:
        downtime = _as_float(downtime_hours)
        if downtime is None or downtime < 0:
            return None, fail(
                "invalid_input", f"downtime_hours 는 0 이상의 숫자입니다: {downtime_hours!r}"
            )

    parts_list, parts_err = validate_parts(parts)
    if parts_err is not None:
        return None, parts_err

    if (model is None) != (error_code is None):
        return None, fail(
            "model_code_pair", "model 과 error_code 는 둘 다 있거나 둘 다 없어야 합니다 (D33)."
        )
    if model is not None and model not in VALID_MODELS:
        return None, fail(
            "invalid_model", f"model 은 {' | '.join(VALID_MODELS)} 이어야 합니다: {model!r}"
        )
    code = error_code.strip().upper() if isinstance(error_code, str) else None

    if note is not None and not isinstance(note, str):
        return None, fail("invalid_input", f"note 는 문자열입니다: {note!r}")
    note_text = note.strip() if isinstance(note, str) and note.strip() else None

    return {
        "equipment_id": equipment_id.strip(),
        "work_type": work_type,
        "repair_scope": repair_scope,
        "cost": cost_int,
        "downtime_hours": downtime,
        "parts_list": parts_list,
        "model": model,
        "error_code": code,
        "note": note_text,
    }, None


def classify(
    con: sqlite3.Connection,
    *,
    equipment_id: str,
    parts_list: list[dict],
    repair_scope: str,
    cost: int,
) -> tuple[dict | None, dict | None]:
    """설비·부품 실재 확인 + `part_class`·`expenditure_class` 산출.

    `part_class` 합성 규칙: 하나라도 CRITICAL이면 CRITICAL · 등급 미상이 섞이면 **NULL** ·
    전부 CONSUMABLE이면 CONSUMABLE. ⛔ 0·임의값으로 메우지 않는다(D12 — 등급을 추정하지
    않는다). `part_class`가 NULL이면 `expenditure_class`도 NULL이고, 그 사유를 문장으로 남긴다.
    """
    eq = con.execute(
        "SELECT equipment_id FROM equipment WHERE equipment_id = ?", (equipment_id,)
    ).fetchone()
    if eq is None:
        return None, fail(
            "unknown_equipment",
            f"등록되지 않은 설비입니다: {equipment_id}",
            status="not_found",
        )

    distinct_part_nos = {item["part_no"] for item in parts_list}
    found_class: dict[str, str | None] = {}
    for part_no in distinct_part_nos:
        row = con.execute(
            "SELECT part_class FROM parts WHERE part_no = ?", (part_no,)
        ).fetchone()
        if row is not None:
            found_class[part_no] = row["part_class"]
    missing = sorted(distinct_part_nos - set(found_class))
    if missing:
        # 지어낸 품번이 정비 이력에 남을 경로를 막는다 — D33이 에러코드에 건 방어를 부품에도.
        return None, fail(
            "unknown_part",
            f"등록되지 않은 부품 번호가 있습니다: {', '.join(missing)}",
            status="not_found",
            missing=missing,
        )

    classes: set[str] = set()
    unset_parts: list[str] = []
    for part_no in sorted(distinct_part_nos):
        raw = (found_class.get(part_no) or "").strip().upper()
        if raw in maint_value.PART_CLASSES:
            classes.add(raw)
        else:
            unset_parts.append(part_no)

    if "CRITICAL" in classes:
        part_class: str | None = "CRITICAL"
    elif unset_parts:
        part_class = None
    else:
        part_class = "CONSUMABLE"

    expenditure_class: str | None = None
    if part_class is None:
        expenditure_reason = (
            "일부 부품의 등급(part_class)이 등록돼 있지 않아 지출 성격(자본적/수익적)을 "
            f"판정하지 않았다 — 등급 미상 부품: {', '.join(unset_parts)}. "
            "등급을 추정하지 않는다 (D12)."
        )
    else:
        exp = maint_value.expenditure(
            con, part_class=part_class, repair_scope=repair_scope, amount=cost
        )
        if exp.get("status") != "ok":
            # 하위 산출 실패를 삼키지 않는다 — 없는 근거로 회계 판정을 지어내지 않는다.
            return None, exp
        expenditure_class = exp["verdict"]  # HOLD도 실패가 아니라 판정이다
        expenditure_reason = exp["reasoning"]

    return {
        "part_class": part_class,
        "expenditure_class": expenditure_class,
        "expenditure_reason": expenditure_reason,
    }, None


def next_repair_id(con: sqlite3.Connection) -> str:
    row = con.execute(
        "SELECT repair_id FROM repair_records WHERE repair_id LIKE 'RPR-%'"
        " ORDER BY repair_id DESC LIMIT 1"
    ).fetchone()
    n = int(row["repair_id"].split("-")[1]) + 1 if row else 1
    return f"RPR-{n:04d}"


def insert_draft(
    con: sqlite3.Connection,
    *,
    repair_id: str,
    equipment_id: str,
    model: str | None,
    error_code: str | None,
    part_class: str | None,
    work_type: str,
    expenditure_class: str | None,
    cost: int,
    downtime_hours: float | None,
    parts_list: list[dict],
    note: str | None,
    performed_by: str | None = None,
    session_id: str | None = None,
) -> None:
    """`repair_records`에 draft 한 건을 INSERT.

    서명 필드(`verified_by`·`signed_at`·`record_hash`)는 **항상 NULL 리터럴**이다 —
    파라미터로도 받지 않는다(D23·D98). `performed_by`를 None으로 부르면 기존 MCP 경로
    (사후 stamp, D37)와 같고, 백엔드 경로는 생성 즉시 채워 넘긴다(D111 선례).
    """
    con.execute(
        "INSERT INTO repair_records (repair_id, equipment_id, model, error_code,"
        " part_class, work_type, expenditure_class, cost, downtime_hours, parts,"
        " performed_by, verified_by, signed_at, record_hash, state,"
        " requested_by, session_id, note)"
        " VALUES (?,?,?,?,?,?,?,?,?,?, ?, NULL, NULL, NULL, 'draft', NULL, ?, ?)",
        (
            repair_id, equipment_id, model, error_code, part_class, work_type,
            expenditure_class, cost, downtime_hours,
            json.dumps(parts_list, ensure_ascii=False),
            performed_by, session_id, note,
        ),
    )


def update_draft(
    con: sqlite3.Connection,
    *,
    repair_id: str,
    equipment_id: str,
    model: str | None,
    error_code: str | None,
    part_class: str | None,
    work_type: str,
    expenditure_class: str | None,
    cost: int,
    downtime_hours: float | None,
    parts_list: list[dict],
    note: str | None,
) -> None:
    """draft 상태 수리 증빙 한 건을 UPDATE.

    ⛔ **MCP 도구는 이 함수를 부르지 않는다** (D10·D98 — 도구는 draft INSERT만).
    호출자가 `state == 'draft'`를 이미 확인했다고 가정한다 — `WHERE ... AND state='draft'`
    는 방어적 이중 잠금이지 유일한 가드가 아니다(호출자가 404/409를 별도로 판단한다).

    서명 필드는 **건드리지 않는다** — SET 절에 아예 없다. 수정으로 서명이 지워지거나
    채워지는 경로를 만들지 않는다.
    """
    con.execute(
        "UPDATE repair_records SET equipment_id=?, model=?, error_code=?, part_class=?,"
        " work_type=?, expenditure_class=?, cost=?, downtime_hours=?, parts=?, note=?"
        " WHERE repair_id=? AND state='draft'",
        (
            equipment_id, model, error_code, part_class, work_type,
            expenditure_class, cost, downtime_hours,
            json.dumps(parts_list, ensure_ascii=False),
            note, repair_id,
        ),
    )
