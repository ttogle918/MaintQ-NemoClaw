# -*- coding: utf-8 -*-
"""재고 조회 서비스 — `data.inventory` 위임 (D101·D73).

`mcp_server` 를 import하지 않는다(D15) — REST 와 MCP 도구가 `data/inventory.py`
하나만 공유한다(`backend/services/maint_value.py`·`backend/services/ownership.py` 와
같은 구조).

**읽기 전용이다.** `services/disposal.read_only`(`mode=ro` URI)만 쓴다. ⛔ 세 번째
`mode=ro` 헬퍼를 만들지 않는다.

**에러를 재포장하지 않는다.** `data.inventory.search` 는 이미 `status`/`reason` 으로
실패를 닫아 준다(D9) — 이 파일은 그 dict 를 그대로 돌려준다. 다만 **커넥션을 여는
시점**의 예외(파일 없음·DB 오류)는 `data.inventory` 가 알지 못하는 영역이므로
(커넥션을 받아서만 동작한다) `services/maint_value.py`·`services/ownership.py` 와
같은 어휘로 여기서 닫는다.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from data import inventory as data_inventory

from backend.services.disposal import read_only


def _open_error(exc: Exception) -> dict:
    """`read_only()` 진입 자체에서 난 예외를 `data.inventory` 와 같은 status 어휘로 닫는다."""
    if isinstance(exc, FileNotFoundError):
        return {"status": "error", "reason": "db_missing", "message": str(exc)}
    if isinstance(exc, sqlite3.Error):
        return {"status": "error", "reason": "db_error", "message": str(exc)}
    return {
        "status": "error",
        "reason": "internal_error",
        "message": f"{type(exc).__name__}: {exc}",
    }


def search(
    *,
    part_no: str | None = None,
    part_name: str | None = None,
    model: str | None = None,
    db_path: Path | None = None,
) -> dict:
    """`GET /api/inventory` — `data.inventory.search` 위임."""
    try:
        with read_only(db_path) as con:
            return data_inventory.search(con, part_no=part_no, part_name=part_name, model=model)
    except Exception as e:  # noqa: BLE001 — 커넥션을 여는 시점의 예외까지 status 로 닫는다 (D9)
        return _open_error(e)
