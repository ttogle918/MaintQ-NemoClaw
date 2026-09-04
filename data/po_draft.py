# -*- coding: utf-8 -*-
"""po_draft — 발주 초안 산출 로직 공유 계층 (D73·D101 패턴, P39 축소판 — 발주서만).

`mcp_server/tools/create_po_draft.py`·`backend/services/po.py`가 이 모듈로 위임한다 —
`data/maint_value.py`와 같은 구조다. 소비자가 늘어도(채팅 MCP 도구 + 화면 REST) 판정
로직을 두 곳에 복제하지 않기 위해 여기 한 곳에 둔다.

⛔ 이 모듈은 `mcp_server`도 `backend`도 import하지 않는다(D15 — 두 런타임 프로세스의
상호 import 금지). 커넥션은 호출자가 열어서 넘긴다 — 이 모듈은 DB 경로를 모른다
(`data/maint_value.py`와 같은 규약).

★ `data/` 아래 첫 INSERT 수행 모듈이다 — 기존 `data/maint_value.py`류는 전부 읽기 전용
판정이었다. 이 모듈 자체는 "쓰기 권한"을 갖지 않는다 — 권한은 호출자가 여는 **커넥션의
종류**로 결정된다(MCP는 `mcp_server/db.py`의 TEMP TRIGGER로 INSERT만 허용된
`draft_writer()`, 백엔드는 이미 UPDATE 권한이 있는 일반 커넥션). 이 모듈은 그 커넥션에
SQL을 실행할 뿐이다.

스키마 경계 검증(필수값 존재·urgency enum·model/error_code 쌍·model enum)은 이 모듈에
없다 — `mcp_server/tools/create_po_draft.py`와 `backend/services/po.py`가 각자
진입점에서 한다(둘 다 같은 체크를 하지만 "산출 로직"이 아니라 "이 진입점이 받은 입력이
말이 되는가"라 의도적으로 두 곳에 둔다 — 2026-08-21 설계 §3).

실패는 예외가 아니라 status 필드로 반환한다(D9).
"""

from __future__ import annotations

from data.dbcompat import DbConnection


from data import txn


def next_po_id(con: DbConnection) -> str:
    """`PO-%04d` 채번. 경쟁 없는 발급은 `data/txn.py` 가 소유한다 (D126) —
    같은 규약을 쓰는 `repair_record.next_repair_id` 와 한 곳에서 갈린다."""
    return txn.next_sequential_id(con, "po_drafts", "po_id", "PO")


def validate_and_price(
    con: DbConnection,
    *,
    part_no: str,
    qty: int,
    supplier_id: str,
    model: str | None,
    error_code: str | None,
) -> dict:
    """단가·MOQ 조회(D31) + 에러코드 FK 검증(D33). `error_code`는 이미 대문자 canonical(D25)
    이라고 가정한다 — 호출자가 대문자화한다."""
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

    if error_code is not None:
        known = con.execute(
            "SELECT 1 FROM error_codes WHERE model=? AND code=?", (model, error_code)
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

    return {"status": "ok", "unit_price": quote["unit_price"], "moq": moq}


def insert_draft(
    con: DbConnection,
    *,
    po_id: str,
    part_no: str,
    qty: int,
    supplier_id: str,
    model: str | None,
    error_code: str | None,
    evidence_json: str | None,
    unit_price: int,
    reason: str,
    urgency: str,
    requested_by: str | None = None,
    session_id: str | None = None,
) -> None:
    """`po_drafts`에 draft 한 건을 INSERT. `requested_by`/`session_id`를 None으로 부르면
    기존 MCP 경로(사후 stamp, D37)와 동일하게 NULL로 들어간다 — 백엔드 경로는 생성
    즉시 `requested_by`를 채워 넘긴다(2026-08-21 설계 §4)."""
    con.execute(
        "INSERT INTO po_drafts (po_id, part_no, qty, supplier_id, model, error_code,"
        " evidence, unit_price, reason, urgency, state, requested_by, session_id)"
        " VALUES (?,?,?,?,?,?,?,?,?,?, 'draft', ?, ?)",
        (
            po_id, part_no, qty, supplier_id, model, error_code,
            evidence_json, unit_price, reason, urgency, requested_by, session_id,
        ),
    )


def update_draft(
    con: DbConnection,
    *,
    po_id: str,
    part_no: str,
    qty: int,
    supplier_id: str,
    model: str | None,
    error_code: str | None,
    evidence_json: str | None,
    unit_price: int,
    reason: str,
    urgency: str,
) -> None:
    """draft 상태 발주 한 건을 UPDATE. 호출자가 `state == 'draft'`를 이미 확인했다고
    가정한다 — `WHERE ... AND state='draft'`는 방어적 이중 잠금이지 이 함수의 유일한
    가드는 아니다(호출자가 별도로 404/409를 판단해야 한다)."""
    con.execute(
        "UPDATE po_drafts SET part_no=?, qty=?, supplier_id=?, model=?, error_code=?,"
        " evidence=?, unit_price=?, reason=?, urgency=? WHERE po_id=? AND state='draft'",
        (
            part_no, qty, supplier_id, model, error_code,
            evidence_json, unit_price, reason, urgency, po_id,
        ),
    )


def list_quotes(con: DbConnection, *, part_no: str) -> list[dict]:
    """부품의 공급사별 견적(리드타임·단가·MOQ). `backend/services/po.py`의 `get_po()`
    (상세의 `quotes` 필드)와 `quotes_for_part()`(화면이 발주 전 공급사를 고르기 위한
    사전 조회, `GET /api/po/quotes/{part_no}`)가 같은 쿼리를 쓴다 — 세 번째 사본을
    만들지 않는다."""
    rows = con.execute(
        "SELECT sp.supplier_id, s.name, sp.lead_days, sp.unit_price, sp.moq"
        " FROM supplier_parts sp JOIN suppliers s ON s.supplier_id = sp.supplier_id"
        " WHERE sp.part_no = ? ORDER BY sp.lead_days",
        (part_no,),
    ).fetchall()
    return [dict(r) for r in rows]
