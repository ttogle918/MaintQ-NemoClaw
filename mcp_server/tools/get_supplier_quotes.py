# -*- coding: utf-8 -*-
"""get_supplier_quotes — 공급사 견적 (리드타임+단가+MOQ 통합, D8)."""

from __future__ import annotations

from ..db import read_only

DESCRIPTION = (
    "부품의 공급사별 리드타임·단가·MOQ를 조회한다. 2개 이상이면 비교해 제시하고 사용자가 "
    "고르게 할 것(단독 결정 금지). 요청 수량이 어떤 공급사의 moq에 미달하면 그 사실을 견적 "
    "제시 단계에서 먼저 알릴 것 — MOQ 미달 상태로 발주 초안을 만들면 도구가 거부한다."
)


def get_supplier_quotes(part_no: str, qty: int = 1) -> dict:
    if not part_no:
        return {"status": "error", "message": "part_no는 필수입니다"}
    if qty < 1:
        return {"status": "error", "message": f"qty는 1 이상이어야 합니다: {qty}"}

    try:
        with read_only() as con:
            rows = con.execute(
                "SELECT sp.supplier_id, s.name, sp.lead_days, sp.unit_price, sp.moq"
                " FROM supplier_parts sp JOIN suppliers s ON s.supplier_id = sp.supplier_id"
                " WHERE sp.part_no = ?"
                " ORDER BY sp.lead_days, sp.unit_price",
                (part_no,),
            ).fetchall()
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "message": str(e)}

    if not rows:
        return {"status": "empty", "suppliers": []}

    return {
        "status": "ok",
        "suppliers": [
            {
                "supplier_id": r["supplier_id"],
                "name": r["name"],
                "lead_days": r["lead_days"],
                "unit_price": r["unit_price"],
                "moq": r["moq"],
            }
            for r in rows
        ],
    }
