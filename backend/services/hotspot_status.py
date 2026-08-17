# -*- coding: utf-8 -*-
"""설비 하이라이트 상태 서비스 — `data.hotspot_status` 위임 (D101·D73).

`mcp_server`를 import하지 않는다(D15) — REST 와 MCP 도구가 `data/hotspot_status.py`
하나만 공유한다(`backend/services/inventory.py`·`backend/services/maint_value.py` 와
같은 구조). `print_page` 부착은 이 파일의 유일한 책임이다(D32 — 오프셋 산술 자체는
`backend.manifest.to_print_page()` 에 위임하고 재구현하지 않는다).

**읽기 전용이다.** `services/disposal.read_only`(`mode=ro` URI)만 쓴다. ⛔ 세 번째
`mode=ro` 헬퍼를 만들지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timezone

from data import hotspot_status as data_hotspot

from backend.manifest import to_print_page
from backend.services.disposal import read_only


def get(asset_id: str) -> dict:
    """`GET /api/assets/{asset_id}/hotspot-status` — `data.hotspot_status.hotspot_status` 위임.

    `red` 로 판정된 부품의 `basis.manual_page`(물리 페이지)에만 `print_page`(인쇄 페이지)를
    붙인다. 오프셋 산술은 `backend.manifest.to_print_page()` 한 곳에만 위임한다 —
    `backend/services/po.py` 의 `_attach_print_pages` 와 같은 태도.
    """
    today = datetime.now(timezone.utc).date()
    with read_only() as con:
        result = data_hotspot.hotspot_status(con, asset_id=asset_id, today=today)
    if result.get("status") == "ok":
        model = result["model"]
        for part in result["parts"]:
            page = part.get("basis", {}).get("manual_page")
            if part["color"] == "red" and isinstance(page, int):
                part["basis"]["print_page"] = to_print_page(model, page)
    return result
