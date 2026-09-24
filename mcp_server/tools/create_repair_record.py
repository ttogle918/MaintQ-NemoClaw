# -*- coding: utf-8 -*-
"""create_repair_record — 수리 증빙 초안 생성 ⚠️ **세 번째 쓰기 도구** (`docs/04_MCP_TOOLS.md §16`).

`create_po_draft`(§7)·`generate_disposal_document`(§15) 와 **같은 패턴**이다: draft 만
INSERT 하고, 확정(서명)은 사람 전용 API 소관이며, 신원은 백엔드가 stamp 한다.

이 도구가 지키는 경계 (D98):
  D10   `repair_records` 에 `state='draft'` **INSERT 만**. UPDATE/DELETE 권한 자체가 없다 —
        규율이 아니라 `db.repair_writer()` 의 TEMP TRIGGER 2개로 잠근다.
        ⛔ `draft_writer()`·`decision_writer()` 를 재사용하지 않는다 — 그건 각각
          `po_drafts`·`decisions` 전용 트리거만 걸린 커넥션이라, 그걸로 `repair_records` 를
          만지면 **잠금이 없는 채로 쓰는 것**이 된다 (`mcp_server/db.py` 기존 주석과 같은 이유).
  D80   `equipment_id`·`work_type`·`repair_scope`·`cost`·`parts` 에는 기본값을 두지 않는다.
  D23·D37  `performed_by`·`verified_by`·`signed_at`·`record_hash`·`requested_by`·`session_id`
        는 **파라미터가 아니다.** 서명·신원은 사람 전용 API 가 stamp 한다.
  D33·D13  `(model, error_code)` 는 짝이거나 둘 다 NULL. FK(`(model, error_code)
        REFERENCES error_codes(model, code)`)가 실재하지 않는 코드를 거부한다 — 여기서는
        `create_po_draft` 와 달리 **사전 조회를 하지 않고** INSERT 시점의 FK 위반을
        `status:"error", reason:"integrity"` 로 그대로 드러낸다 (엣지 케이스 표).
  D12   `part_class` 는 등급을 추측하지 않는다 — `parts` 테이블에 등록된 값만 읽는다.
  D101  `expenditure_class`·`expenditure_reason` 은 `data/maint_value.expenditure()` 산출을
        그대로 옮긴다 — 회계 판정을 LLM 이 지어내는 경로를 막는다 (D31·D81 과 같은 이유).
  D65   `expenditure_class` 는 회계·세무 판단의 **참고값**이다 — `disclaimer` 로 고지한다.
  D9    실패는 예외가 아니라 `status` 로 돌려준다.

입력 검증 → 조회 → 산출 → INSERT 순서. 거부할 입력으로 DB 를 열지 않는다.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from data import repair_record

from ..db import read_only, repair_writer

DESCRIPTION = (
    "수리 작업의 증빙 '초안'을 생성한다. 확정이 아니다. 수리가 끝난 뒤 무엇을 어떻게 "
    "고쳤는지(작업유형·수리범위·비용·교체 부품)를 기록할 때 호출할 것. 이 초안은 팀장이 "
    "서명해야 정식 증빙이 되며, 서명 전에는 get_maintenance_metrics 의 보전지표에 들어가지 "
    "않는다. 교체한 부품 품번을 정확히 넣을 것 — 등록되지 않은 품번은 거부된다(unknown_part). "
    "지출의 자본적/수익적 분류(expenditure_class)는 시스템이 자동 산출한다 — 파라미터로 받지 "
    "않으며 네가 추측하거나 지어내지 말 것. 에러코드로부터 시작된 수리이면 model·error_code 를 "
    "함께 넣을 것 — 매뉴얼에 없는 코드는 거부된다."
)

VALID_MODELS = ("iG5A", "S100", "IE5", "HV600")
WORK_TYPES = ("PLANNED", "UNPLANNED")

NEXT_STEP = "이 기록은 확정이 아니다. 제출 후 팀장이 서명해야 증빙이 된다."

DISCLAIMER = (
    "expenditure_class 는 회계·세무 판단의 참고값이며 확정이 아니다 — 세무 전문가 확인이 "
    "필요할 수 있다(classify_expenditure 참조). record_hash 는 서명 시 백엔드가 계산한다(D84 태도). "
    "이 기록은 팀장 서명 전까지 보전지표(n_repairs_signed 등)에 반영되지 않는다."
)


def _fail(reason: str, message: str, status: str = "error", **extra: Any) -> dict:
    return {"status": status, "reason": reason, "message": message, **extra}


def _as_positive_int(value: object) -> int | None:
    """정수로 해석되면 int, 아니면 None. **추정하지 않는다** (`data/maint_value._as_amount` 와 같은 태도)."""
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


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _validate_parts(parts: object) -> tuple[list[dict] | None, dict | None]:
    """`parts` 를 검증하고 정규화한다. 1건 이상, 각 항목은 `part_no` 필수(문자열).

    `serial`·`qty` 는 있으면 형식을 검증하고, 없으면 담지 않는다 — 없는 값을 지어내 채우지 않는다.
    """
    if not isinstance(parts, list) or not parts:
        return None, _fail(
            "invalid_input",
            "parts 는 1건 이상의 배열입니다 — 부품 없는 수리 증빙은 근거 패키지에서 쓸모가 없습니다.",
        )
    cleaned: list[dict] = []
    for i, item in enumerate(parts):
        if not isinstance(item, dict):
            return None, _fail("invalid_input", f"parts[{i}] 는 객체여야 합니다: {item!r}")
        part_no = item.get("part_no")
        if not isinstance(part_no, str) or not part_no.strip():
            return None, _fail(
                "invalid_input", f"parts[{i}].part_no 는 비어 있지 않은 문자열입니다: {part_no!r}"
            )
        entry: dict[str, Any] = {"part_no": part_no.strip()}
        serial = item.get("serial")
        if serial is not None:
            if not isinstance(serial, str):
                return None, _fail(
                    "invalid_input", f"parts[{i}].serial 은 문자열입니다: {serial!r}"
                )
            entry["serial"] = serial
        if "qty" in item and item["qty"] is not None:
            qty = _as_positive_int(item["qty"])
            if qty is None or qty <= 0:
                return None, _fail(
                    "invalid_input", f"parts[{i}].qty 는 1 이상의 정수입니다: {item['qty']!r}"
                )
            entry["qty"] = qty
        cleaned.append(entry)
    return cleaned, None


def create_repair_record(
    equipment_id: str,
    work_type: str,
    repair_scope: str,
    cost: int,
    parts: list,
    downtime_hours: float | None = None,
    model: str | None = None,
    error_code: str | None = None,
    note: str | None = None,
) -> dict:
    """`repair_records` 에 draft 한 건을 INSERT 한다 (D10 — INSERT 만, D98).

    실패는 예외가 아니라 `status` 로 돌려준다 (D9).
    """
    # ── ① 입력 검증 (DB 를 열기 전) — 거부할 입력으로 DB 를 열지 않는다 ────────────
    #    산출 로직은 `data/repair_record.py` 공유 계층이 갖는다 (P39 — 화면 REST 와
    #    같은 판정을 두 곳에 복제하지 않는다). 이 파일에 남는 것은 **MCP 진입점의 책임**
    #    뿐이다: 커넥션 종류 선택(D10 — `repair_writer()` 의 TEMP TRIGGER)·D9 실패 표현.
    vals, err = repair_record.validate_input(
        equipment_id=equipment_id,
        work_type=work_type,
        repair_scope=repair_scope,
        cost=cost,
        parts=parts,
        downtime_hours=downtime_hours,
        model=model,
        error_code=error_code,
        note=note,
    )
    if err is not None:
        return err

    # ── ② 조회 — 설비·부품 실재 확인 + 지출 산출 ─────────────────────────────────
    try:
        with read_only() as con:
            calc, calc_err = repair_record.classify(
                con,
                equipment_id=vals["equipment_id"],
                parts_list=vals["parts_list"],
                repair_scope=vals["repair_scope"],
                cost=vals["cost"],
            )
            if calc_err is not None:
                return calc_err
    except sqlite3.Error as e:
        return _fail("db_error", str(e))
    except FileNotFoundError as e:
        return _fail("db_missing", str(e))
    except Exception as e:  # noqa: BLE001 — 예외를 밖으로 던지지 않는다 (D9)
        return _fail("internal_error", f"{type(e).__name__}: {e}")

    # ── ③ INSERT — draft 만. 서명·신원 필드는 전부 NULL (D23·D37·D80) ──────────────
    #    ⛔ `repair_writer()` 는 TEMP TRIGGER 로 INSERT 만 허용된 커넥션이다 (D10·D98).
    #      공유 계층의 `update_draft()` 를 여기서 부르지 않는다 — 부를 수 없어서가 아니라
    #      **도구는 draft INSERT 만 한다**는 계약이기 때문이다.
    try:
        with repair_writer() as con:
            repair_id = repair_record.next_repair_id(con)
            repair_record.insert_draft(
                con,
                repair_id=repair_id,
                equipment_id=vals["equipment_id"],
                model=vals["model"],
                error_code=vals["error_code"],
                part_class=calc["part_class"],
                work_type=vals["work_type"],
                expenditure_class=calc["expenditure_class"],
                cost=vals["cost"],
                downtime_hours=vals["downtime_hours"],
                parts_list=vals["parts_list"],
                note=vals["note"],
            )
    except sqlite3.IntegrityError as e:
        # FK((model,error_code))·CHECK 위반은 계약 위반이므로 그대로 드러낸다.
        # 매뉴얼에 없는 error_code 로 부르면 여기서 걸린다 (사전 조회 없이 FK 가 막는다).
        return _fail("integrity", str(e))
    except sqlite3.Error as e:
        return _fail("db_error", str(e))
    except FileNotFoundError as e:
        return _fail("db_missing", str(e))
    except Exception as e:  # noqa: BLE001 — 예외를 밖으로 던지지 않는다 (D9)
        return _fail("internal_error", f"{type(e).__name__}: {e}")

    return {
        "status": "ok",
        "repair_id": repair_id,
        "state": "draft",
        "equipment_id": vals["equipment_id"],
        "work_type": vals["work_type"],
        "part_class": calc["part_class"],
        "expenditure_class": calc["expenditure_class"],
        "expenditure_reason": calc["expenditure_reason"],
        "cost": vals["cost"],
        "downtime_hours": vals["downtime_hours"],
        "record_hash": None,
        "next_step": NEXT_STEP,
        "disclaimer": DISCLAIMER,
    }
