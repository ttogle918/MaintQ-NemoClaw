# -*- coding: utf-8 -*-
"""search_inventory — 재고 조회 (docs/04_MCP_TOOLS.md §4).

실패는 예외가 아니라 status 로 반환한다 (D9) — 에이전트가 S2 분기를 판단해야 하므로.
"""

from __future__ import annotations

import json

from ..db import read_only

DESCRIPTION = (
    "부품의 재고·안전재고·단종 여부를 조회한다. part_no를 알면 part_no로, 사용자가 부품을 "
    "이름으로만 말했으면 part_name으로 조회할 것. part_name으로 조회할 때는 model을 반드시 "
    "함께 지정할 것 — 지정하지 않으면 다른 기종 부품이 섞여 나온다."
)


def search_inventory(
    part_no: str | None = None,
    part_name: str | None = None,
    model: str | None = None,
) -> dict:
    if not part_no and not part_name:
        return {"status": "error", "message": "part_no 또는 part_name 중 하나는 필요합니다"}
    if model is not None and model not in ("iG5A", "S100"):
        return {"status": "error", "message": f"model은 iG5A|S100 이어야 합니다: {model!r}"}

    sql = [
        "SELECT p.part_no, p.name, p.compatible_models, p.discontinued,",
        "       i.qty, i.safety_stock, i.location",
        "FROM parts p JOIN inventory i ON i.part_no = p.part_no",
        "WHERE 1=1",
    ]
    args: list[object] = []
    if part_no:
        sql.append("AND p.part_no = ?")
        args.append(part_no)
    if part_name:
        sql.append("AND p.name LIKE ?")
        args.append(f"%{part_name}%")

    try:
        with read_only() as con:
            rows = con.execute(" ".join(sql), args).fetchall()
    except Exception as e:  # noqa: BLE001 — 예외를 status로 바꿔 반환 (D9)
        return {"status": "error", "message": str(e)}

    items = []
    for r in rows:
        models = json.loads(r["compatible_models"])
        # D28 — model 지정 시 호환 기종이 아닌 부품은 제외 (기종 교차 오염 차단)
        if model and model not in models:
            continue
        items.append(
            {
                "part_no": r["part_no"],
                "name": r["name"],
                "qty": r["qty"],
                "safety_stock": r["safety_stock"],
                "location": r["location"],
                "compatible_models": models,
                "discontinued": bool(r["discontinued"]),
            }
        )

    if not items:
        return {"status": "not_found", "items": []}
    return {"status": "ok", "items": items}
