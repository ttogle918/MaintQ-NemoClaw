# -*- coding: utf-8 -*-
"""track_deadlines — 법정 기한(세액공제 사후관리·안전검사) 사전 경보 (MQ-1104, S9, D102).

**이 파일은 얇은 래퍼다.** 판정 로직·상수는 전부 `data/deadlines.py` 에 있다 (D101).
여기 남는 것은 두 가지뿐이다:
  1. `DESCRIPTION` — `04 §17` 이 정본으로 인용한다. 옮기지 않는다.
  2. 커넥션 수명 (`read_only()`) — 읽기 전용이다 (D10). `data/deadlines.py` 는 DB 경로를 모른다.
"""

from __future__ import annotations

from data import deadlines

from ..db import read_only

DEFAULT_WINDOW_DAYS = deadlines.DEFAULT_WINDOW_DAYS

DESCRIPTION = (
    "자산의 법정 기한(투자세액공제 사후관리 24개월·안전검사 유효기한)이 임박했거나 이미 지났는지 "
    "조회한다. 처분·매각을 검토하기 전에 먼저 호출할 것 — 세액공제 사후관리 기간 안에 처분하면 "
    "추징 리스크가 있고, 안전검사가 만료된 자산은 가동 자체가 제한될 수 있다. window_days 안에 "
    "들어오는 항목만 UPCOMING 으로 표시하며, 안전검사는 만료 후에도 OVERDUE 로 항상 포함한다. "
    "기본 호출(window_days=180)에서 0건이 나올 수 있다 — 이는 실패가 아니라 그 기간 안에 임박한 "
    "기한이 없다는 뜻이다(추측으로 채우지 말 것, D62). 처분 차단 여부 자체는 이 도구가 아니라 "
    "check_disposal_blockers 를 쓸 것."
)


def track_deadlines(asset_id: str | None = None, window_days: int | str = DEFAULT_WINDOW_DAYS) -> dict:
    try:
        with read_only() as con:
            return deadlines.track_deadlines(con, asset_id=asset_id, window_days=window_days)
    except FileNotFoundError as e:
        return {"status": "error", "reason": "db_missing", "message": str(e)}
    except Exception as e:  # noqa: BLE001 — 도구는 예외를 던지지 않는다 (D9)
        return {"status": "error", "reason": "db_error", "message": str(e)}
