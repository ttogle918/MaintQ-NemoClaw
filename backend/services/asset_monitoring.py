# -*- coding: utf-8 -*-
"""기한 추적 · 위험등급 산출 REST 어댑터 (MQ-1105, D73·D101).

**판정을 어디서 가져오는가.** 도구 서버 패키지를 import 하지 않는다(D15 — 두 런타임
프로세스의 상호 import 금지). 산식은 전부 `data/deadlines.py`·`data/risk_grade.py` 에
한 벌만 있고 MCP 도구(`track_deadlines`·`assess_risk_grade`)와 이 서비스가 **같은 함수**를
부른다 — `services/maint_value.py`·`services/ownership.py` 와 같은 구조다.

`core` 프로파일(D69 기본값)에서는 확장 도구가 등록조차 되지 않지만, 이 서비스는 도구를
경유하지 않으므로 **`core` 에서도 두 경로 전부 200(또는 정의된 4xx)** 이다(D73) — 사람용
REST 가 에이전트 도구 노출 설정에 종속되면 안 된다.

**읽기 전용이다.** `services/disposal.read_only`(`mode=ro` URI)만 쓴다. ⛔ 세 번째
`mode=ro` 헬퍼를 만들지 않는다 — `services/maint_value.py`·`services/ownership.py` 가 같은
이유로 이미 재사용하고 있다. `data/deadlines.py`·`data/risk_grade.py` 는 DB 경로를 모르므로
(호출자가 커넥션을 열어 넘기는 규약, 그 모듈 docstring 참조) 이 서비스가 커넥션 수명을 쥔다.

**아무것도 저장하지 않는다.** `deadlines`·`ownership_checks` 에 쓸 수 있는 MCP 도구는
없다(절대 규칙 1) — 이 서비스도 조회만 한다.

**에러를 재포장하지 않는다.** `data.deadlines.track_deadlines`·`data.risk_grade.risk_grade`
(둘 다 D9)는 이미 `status`/`reason` 으로 실패를 닫아 준다 — 이 파일은 그 dict 를 그대로
돌려준다. HTTP 매핑은 `routers/asset_monitoring.py` 가 `status`/`reason` 을 보고 한다. 다만
**커넥션을 여는 시점**의 예외(파일 없음·DB 오류)는 두 데이터 모듈이 알지 못하는 영역이므로
(커넥션을 받아서만 동작한다) 여기서 `services/maint_value._open_error()` 와 같은 어휘로
닫는다.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from data import deadlines as deadlines_data
from data import risk_grade as risk_grade_data

from backend.services.disposal import read_only


def _open_error(exc: Exception) -> dict:
    """`read_only()` 진입 자체에서 난 예외를 두 데이터 모듈과 같은 status 어휘로 닫는다."""
    if isinstance(exc, FileNotFoundError):
        return {"status": "error", "reason": "db_missing", "message": str(exc)}
    if isinstance(exc, sqlite3.Error):
        return {"status": "error", "reason": "db_error", "message": str(exc)}
    return {
        "status": "error",
        "reason": "internal_error",
        "message": f"{type(exc).__name__}: {exc}",
    }


def deadlines(
    *,
    asset_id: str | None = None,
    window_days: int | str | None = None,
    db_path: Path | None = None,
) -> dict:
    """`GET /api/deadlines` — `data.deadlines.track_deadlines` 위임.

    `window_days` 가 `None` 이면 그 함수의 기본값(`DEFAULT_WINDOW_DAYS`, 180일)을 그대로
    쓴다 — 여기서 리터럴로 다시 적지 않는다(정본은 `data/deadlines.py`).
    """
    kwargs: dict = {} if window_days is None else {"window_days": window_days}
    if asset_id is not None:
        kwargs["asset_id"] = asset_id
    try:
        with read_only(db_path) as con:
            return deadlines_data.track_deadlines(con, **kwargs)
    except Exception as e:  # noqa: BLE001 — 커넥션을 여는 시점의 예외까지 status 로 닫는다 (D9)
        return _open_error(e)


def risk_grade(
    *,
    building_id: str | None = None,
    asset_id: str | None = None,
    db_path: Path | None = None,
) -> dict:
    """`GET /api/buildings/{building_id}/risk-grade`·`GET /api/assets/{asset_id}/risk-grade`
    — `data.risk_grade.risk_grade` 위임. `building_id`·`asset_id` 는 either-or 다 — 위반
    시 `data.risk_grade` 가 이미 `invalid_input` 으로 닫아 준다(재검증하지 않는다).
    """
    try:
        with read_only(db_path) as con:
            return risk_grade_data.risk_grade(con, building_id=building_id, asset_id=asset_id)
    except Exception as e:  # noqa: BLE001
        return _open_error(e)
