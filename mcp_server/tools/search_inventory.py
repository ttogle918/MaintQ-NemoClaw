# -*- coding: utf-8 -*-
"""search_inventory — 재고 조회 (docs/04_MCP_TOOLS.md §4).

산출 로직은 `data/inventory.py`(D101) — 이 파일은 얇은 위임이다.
실패는 예외가 아니라 status 로 반환한다 (D9) — 에이전트가 S2 분기를 판단해야 하므로.
"""

from __future__ import annotations

from data import inventory as data_inventory

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
    try:
        with read_only() as con:
            return data_inventory.search(con, part_no=part_no, part_name=part_name, model=model)
    except Exception as e:  # noqa: BLE001 — 예외를 status로 바꿔 반환 (D9)
        return {"status": "error", "reason": "db_error", "message": str(e)}
