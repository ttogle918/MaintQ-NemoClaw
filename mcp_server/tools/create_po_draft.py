# -*- coding: utf-8 -*-
"""create_po_draft — 발주서 초안 생성 ⚠️ **유일한 쓰기 도구** (docs/04_MCP_TOOLS.md §7).

**이 파일은 얇은 래퍼다.** 단가 조회·MOQ 검증·에러코드 FK 검증·INSERT는 전부
`data/po_draft.py`에 있다(P39 축소판, D73·D101 패턴). 화면 쪽 `POST /api/po`
(`backend/services/po.py`)가 같은 함수를 부른다 — 복제본을 두면 채팅과 화면에서
같은 입력이 다르게 거부될 수 있다.

이 파일에 남는 것:
  D10  read_only()로 조회 → draft_writer()로 INSERT. 두 커넥션을 분리해 MCP 프로세스가
       INSERT 밖의 어떤 것도 못 하게 만든다(트리거는 `mcp_server/db.py`).
  D23  requested_by·session_id 는 **MCP 스키마의** 파라미터가 아니다 — LLM 이 위조할 수 없다.
       stdio 경로는 INSERT 시점엔 None(백엔드가 사후 stamp, D37). MCP-HTTP 경로는 서버가
       `X-User` 헤더에서 읽어(`mcp_server/identity.py`) 아래 `requested_by` 로 넘긴다 (D152).
       ⚠ 이 함수의 `requested_by` 는 server.py 가 채우는 **서버 측 인자**다 — server.py 의
       `@mcp.tool` 시그니처에 올리면 그 순간 D23 이 깨진다.
  D80  필수 파라미터에 기본값을 두지 않는다 — 인자 누락은 MCP 스키마가 앞단에서 막는다.
       urgency만 optional(기본 "normal").
  스키마 경계 검증(필수값·enum·model/error_code 쌍)은 "산출 로직"이 아니라 이 진입점의
  몫이라 여기 남는다(`data/po_draft.py`에 옮기지 않는다).
"""

from __future__ import annotations

import json
import sqlite3

from data import po_draft

from ..db import draft_writer, read_only

DESCRIPTION = (
    "발주서 '초안'을 생성한다. 확정이 아니다. 반드시 사용자가 부품·공급사를 확인한 후에만 "
    "호출할 것. reason에는 진단 근거를 한 줄로 요약하고, evidence에는 어떤 현상을 보고 "
    "고장으로 판단했는지(symptoms)와 근거가 된 도구 결과(basis), 기타 비고(notes)를 "
    "구조화해 남길 것. 에러코드로부터 시작된 진단이면 model·error_code를 함께 넣을 것 — "
    "매뉴얼에 없는 코드는 거부된다. 단가는 파라미터가 아니다(서버가 조회해 채움). "
    "수량이 공급사 MOQ에 미달하면 거부되므로 미달이면 먼저 사용자에게 수량 조정을 확인할 것."
)

VALID_MODELS = ("iG5A", "S100", "IE5", "HV600")


def create_po_draft(
    part_no: str,
    qty: int,
    supplier_id: str,
    reason: str,
    urgency: str = "normal",
    model: str | None = None,
    error_code: str | None = None,
    evidence: dict | None = None,
    *,
    requested_by: str | None = None,
    session_id: str | None = None,
) -> dict:
    # ── 입력 검증 (실패는 전부 status 로, D9) — 스키마 경계이지 산출 로직이 아니다
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
            result = po_draft.validate_and_price(
                con,
                part_no=part_no,
                qty=qty,
                supplier_id=supplier_id,
                model=model,
                error_code=code,
            )
            if result["status"] == "ok" and requested_by is not None:
                # 헤더 형식만으로는 부족하다 — 발주 귀속이라 **등록된 사용자**여야 한다 (D152).
                # 백엔드 `deps.caller()` 가 미등록 ID 를 department=None 으로 흘리는 것과 다른
                # 태도는 의도적이다: 거기는 소속 표시, 여기는 쓰기의 주체다.
                known = con.execute(
                    "SELECT 1 FROM users WHERE user_id = ?", (requested_by,)
                ).fetchone()
                if not known:
                    return {
                        "status": "error",
                        "reason": "unknown_user",
                        "message": "요청자 ID 가 등록된 사용자가 아닙니다 — 초안을 만들지 않았습니다 (D152)",
                    }
        if result["status"] != "ok":
            return result

        with draft_writer() as con:
            po_id = po_draft.next_po_id(con)
            po_draft.insert_draft(
                con,
                po_id=po_id,
                part_no=part_no,
                qty=qty,
                supplier_id=supplier_id,
                model=model,
                error_code=code,
                evidence_json=json.dumps(evidence, ensure_ascii=False) if evidence else None,
                unit_price=result["unit_price"],
                reason=reason.strip(),
                urgency=urgency,
                requested_by=requested_by,
                session_id=session_id,
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
        "unit_price": result["unit_price"],
        "total": result["unit_price"] * qty,
    }
