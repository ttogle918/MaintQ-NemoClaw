# -*- coding: utf-8 -*-
"""find_alternative_parts — 호환 대체품 검색 (docs/04_MCP_TOOLS.md §5)."""

from __future__ import annotations

from ..db import read_only

DESCRIPTION = (
    "재고가 없거나 단종된 부품의 호환 대체품을 조회한다. "
    "compat_confirmed가 false인 부품은 사용자에게 제안하지 말 것."
)


def find_alternative_parts(part_no: str) -> dict:
    if not part_no:
        return {"status": "error", "reason": "invalid_input", "message": "part_no는 필수입니다"}

    try:
        with read_only() as con:
            rows = con.execute(
                "SELECT a.alt_part_no, a.compat_confirmed, a.note"
                " FROM part_alternatives a"
                " WHERE a.part_no = ?"
                " ORDER BY a.compat_confirmed DESC, a.alt_part_no",
                (part_no,),
            ).fetchall()
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "reason": "db_error", "message": str(e)}

    if not rows:
        # S2 서브 분기 — 긴급 견적 + 에스컬레이션
        return {"status": "empty", "alternatives": []}

    return {
        "status": "ok",
        "alternatives": [
            {
                "part_no": r["alt_part_no"],
                "compat_confirmed": bool(r["compat_confirmed"]),
                "note": r["note"],
            }
            for r in rows
        ],
    }
