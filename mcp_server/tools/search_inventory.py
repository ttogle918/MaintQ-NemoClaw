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
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": "part_no 또는 part_name 중 하나는 필요합니다",
        }
    if model is not None and model not in ("iG5A", "S100"):
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
        # 양쪽의 공백을 지우고 비교한다 — LLM 은 부품명을 자연스럽게 띄어 쓰는데
        # ("냉각 팬", "전원 모듈") 시드의 name 은 붙여쓰기라 LIKE 가 통째로 빗나갔다.
        # 2026-08-05 평가에서 T04·T15 가 이 경로로 not_found 를 받았다. 에러코드 없이
        # 부품명만 말하는 S2 진입은 이름 조회가 유일한 경로라 여기서 막히면 분기 자체가
        # 성립하지 않는다. `prompts.needs_safety_block` 의 공백 정규화와 같은 이유다.
        sql.append("AND REPLACE(p.name, ' ', '') LIKE ?")
        args.append(f"%{part_name.replace(' ', '')}%")

    try:
        with read_only() as con:
            rows = con.execute(" ".join(sql), args).fetchall()
    except Exception as e:  # noqa: BLE001 — 예외를 status로 바꿔 반환 (D9)
        return {"status": "error", "reason": "db_error", "message": str(e)}

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
