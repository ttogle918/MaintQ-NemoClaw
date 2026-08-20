# -*- coding: utf-8 -*-
"""create_po_draft — 발주서 초안 생성 ⚠️ **유일한 쓰기 도구** (docs/04_MCP_TOOLS.md §7).

이 도구가 지키는 경계:
  D10  state='draft' 로 INSERT만. UPDATE/DELETE 권한 자체가 없다 (db.py 트리거로도 잠금)
  D23  requested_by·session_id 는 파라미터가 아니다 — 스키마에 없으므로 LLM 이 위조할 수 없다.
       INSERT 직후 백엔드가 stamp 한다 (D37)
  D31  unit_price 도 파라미터가 아니다 — supplier_parts 에서 조회한 스냅샷.
       MOQ 미달 수량은 자동 상향하지 않고 거부한다
  D33  (model, error_code) 는 둘 다 있거나 둘 다 없거나. 매뉴얼에 없는 코드는 FK 가 거부
  D34  evidence 로 "어떤 현상을 보고 판단했는지"를 구조화해 남긴다
"""

from __future__ import annotations

import json
import sqlite3

from ..db import draft_writer, read_only

DESCRIPTION = (
    "발주서 '초안'을 생성한다. 확정이 아니다. 반드시 사용자가 부품·공급사를 확인한 후에만 "
    "호출할 것. reason에는 진단 근거를 한 줄로 요약하고, evidence에는 어떤 현상을 보고 "
    "고장으로 판단했는지(symptoms)와 근거가 된 도구 결과(basis), 기타 비고(notes)를 "
    "구조화해 남길 것. 에러코드로부터 시작된 진단이면 model·error_code를 함께 넣을 것 — "
    "매뉴얼에 없는 코드는 거부된다. 단가는 파라미터가 아니다(서버가 조회해 채움). "
    "수량이 공급사 MOQ에 미달하면 거부되므로 미달이면 먼저 사용자에게 수량 조정을 확인할 것."
)

VALID_MODELS = ("iG5A", "S100", "IE5")


def _next_po_id(con: sqlite3.Connection) -> str:
    row = con.execute(
        "SELECT po_id FROM po_drafts WHERE po_id LIKE 'PO-%' ORDER BY po_id DESC LIMIT 1"
    ).fetchone()
    n = int(row["po_id"].split("-")[1]) + 1 if row else 1
    return f"PO-{n:04d}"


def create_po_draft(
    part_no: str,
    qty: int,
    supplier_id: str,
    reason: str,
    urgency: str = "normal",
    model: str | None = None,
    error_code: str | None = None,
    evidence: dict | None = None,
) -> dict:
    # ── 입력 검증 (실패는 전부 status 로, D9)
    if not part_no or not supplier_id:
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": "part_no·supplier_id 는 필수입니다",
        }
    if not reason or not reason.strip():
        return {
            "status": "error",
            "reason": "reason_required",
            "message": "reason 은 필수입니다 — 승인자가 판단 근거를 추적할 수 있어야 합니다 (D5)",
        }
    if qty < 1:
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": f"qty 는 1 이상이어야 합니다: {qty}",
        }
    if urgency not in ("urgent", "normal"):
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": f"urgency 는 urgent|normal 이어야 합니다: {urgency!r}",
        }
    if (model is None) != (error_code is None):
        return {
            "status": "error",
            "reason": "model_code_pair",
            "message": "model 과 error_code 는 둘 다 있거나 둘 다 없어야 합니다 (D33)",
        }
    if model is not None and model not in VALID_MODELS:
        return {
            "status": "error",
            "reason": "invalid_model",
            "message": f"model 은 {' | '.join(VALID_MODELS)} 이어야 합니다: {model!r}",
        }

    code = error_code.upper() if error_code else None  # 저장은 대문자 canonical (D25)

    try:
        with read_only() as con:
            # 단가·MOQ 는 서버가 조회한다 — LLM 이 가격을 지어낼 경로를 없앤다 (D31)
            quote = con.execute(
                "SELECT unit_price, moq FROM supplier_parts WHERE supplier_id=? AND part_no=?",
                (supplier_id, part_no),
            ).fetchone()
            if quote is None:
                return {
                    "status": "not_found",
                    "reason": "no_quote",
                    "message": f"{supplier_id} 는 {part_no} 를 공급하지 않습니다",
                }

            if code is not None:
                known = con.execute(
                    "SELECT 1 FROM error_codes WHERE model=? AND code=?", (model, code)
                ).fetchone()
                if known is None:
                    return {
                        "status": "error",
                        "reason": "unknown_error_code",
                        "message": (
                            f"{model} 매뉴얼에서 확인되지 않는 코드입니다 ({error_code}). "
                            "코드 없이 발주하거나 표시부를 재확인하세요."
                        ),
                    }

        moq = quote["moq"] or 1
        if qty < moq:
            # 자동 상향 금지 — 사람 승인 없이 발주 금액을 키우지 않는다 (D31)
            return {
                "status": "error",
                "reason": "moq_not_met",
                "message": (
                    f"{supplier_id} 의 최소 발주 수량은 {moq}개입니다 (요청 {qty}개). "
                    "수량을 조정하거나 다른 공급사를 선택하세요."
                ),
                "moq": moq,
                "requested_qty": qty,
            }

        unit_price = quote["unit_price"]

        with draft_writer() as con:
            po_id = _next_po_id(con)
            con.execute(
                "INSERT INTO po_drafts (po_id, part_no, qty, supplier_id, model, error_code,"
                " evidence, unit_price, reason, urgency, state)"
                " VALUES (?,?,?,?,?,?,?,?,?,?, 'draft')",
                (
                    po_id,
                    part_no,
                    qty,
                    supplier_id,
                    model,
                    code,
                    json.dumps(evidence, ensure_ascii=False) if evidence else None,
                    unit_price,
                    reason.strip(),
                    urgency,
                ),
            )
    except sqlite3.IntegrityError as e:
        # FK·CHECK 위반은 계약 위반이므로 그대로 드러낸다 (조용히 넘기지 않는다)
        return {"status": "error", "reason": "integrity", "message": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "reason": "db_error", "message": str(e)}

    return {
        "status": "ok",
        "po_id": po_id,
        "state": "draft",
        "unit_price": unit_price,
        "total": unit_price * qty,
    }
