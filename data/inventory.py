# -*- coding: utf-8 -*-
"""재고 조회 — 공유 데이터 계층 (D101·D73).

`mcp_server/tools/search_inventory.py`(MCP 도구)와 `backend/services/inventory.py`
(REST) 둘 다 이 모듈을 부른다 — 산식이 두 벌 존재하는 것을 막는다(Stage 2
`data/maint_value.py` 선례와 같은 이유).

커넥션은 호출자가 `mode=ro`로 열어 넘긴다 — 이 모듈은 `mcp_server`를 import하지
않는다(D15).
"""

from __future__ import annotations

import json
import sqlite3

VALID_MODELS = ("iG5A", "S100")


def search(
    con: sqlite3.Connection,
    *,
    part_no: str | None = None,
    part_name: str | None = None,
    model: str | None = None,
) -> dict:
    if not part_no and not part_name:
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": "part_no 또는 part_name 중 하나는 필요합니다",
        }
    if model is not None and model not in VALID_MODELS:
        return {
            "status": "error",
            "reason": "invalid_model",
            "message": f"model은 iG5A|S100 이어야 합니다: {model!r}",
        }

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
        # 양쪽의 공백을 지우고 비교한다 — search_inventory.py 원본 주석 그대로 유지
        sql.append("AND REPLACE(p.name, ' ', '') LIKE ?")
        args.append(f"%{part_name.replace(' ', '')}%")

    try:
        rows = con.execute(" ".join(sql), args).fetchall()
    except sqlite3.Error as e:
        return {"status": "error", "reason": "db_error", "message": str(e)}

    items = []
    for r in rows:
        models = json.loads(r["compatible_models"])
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
