# -*- coding: utf-8 -*-
"""보전지표·부품 등급·지출 판정·수리가치 판단 REST 어댑터 (MQ-908, D73·D101).

**판정을 어디서 가져오는가.** 도구 서버 패키지를 import 하지 않는다(D15 — 두 런타임
프로세스의 상호 import 금지). 산식은 전부 `data/maint_value.py` 에 한 벌만 있고 MCP 도구
(`get_maintenance_metrics`·`classify_part_criticality`·`classify_expenditure`·
`assess_repair_value`)와 이 서비스가 **같은 함수**를 부른다 — `services/ownership.py` 와
같은 구조다. 복제본을 두면 같은 자산이 채팅(도구)과 화면(REST)에서 다르게 보인다.

`core` 프로파일(D69 기본값)에서는 확장 도구가 등록조차 되지 않지만, 이 서비스는 도구를
경유하지 않으므로 **`core` 에서도 5경로 전부 200(또는 정의된 4xx)** 이다(D73) — 사람용
REST 가 에이전트 도구 노출 설정에 종속되면 안 된다.

**읽기 전용이다.** `services/disposal.read_only`(`mode=ro` URI)만 쓴다. ⛔ 세 번째
`mode=ro` 헬퍼를 만들지 않는다 — `services/ownership.py` 가 같은 이유로 이미 재사용하고
있다. `data/maint_value.py` 는 DB 경로를 모르므로(호출자가 커넥션을 열어 넘기는 규약,
그 모듈 docstring 참조) 이 서비스가 커넥션 수명을 쥔다.

**아무것도 저장하지 않는다.** 라우터의 두 POST(`repair-value`·`expenditure/classify`)도
입력이 본문이라 POST 일 뿐이다.

**에러를 재포장하지 않는다.** `data.maint_value` 의 4개 함수(D9)는 이미 `status`/`reason`
으로 실패를 닫아 준다 — 이 파일은 그 dict 를 그대로 돌려준다. HTTP 매핑은
`routers/maint_value.py` 가 `status`/`reason` 을 보고 한다. 다만 **커넥션을 여는 시점**의
예외(파일 없음·DB 오류)는 `data.maint_value` 가 알지 못하는 영역이므로(커넥션을 받아서만
동작한다) 여기서 `services/ownership.verify()` 와 같은 어휘로 닫는다.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from data import maint_value

from backend.services.disposal import read_only


def _open_error(exc: Exception) -> dict:
    """`read_only()` 진입 자체에서 난 예외를 `data.maint_value` 와 같은 status 어휘로 닫는다."""
    if isinstance(exc, FileNotFoundError):
        return {"status": "error", "reason": "db_missing", "message": str(exc)}
    if isinstance(exc, sqlite3.Error):
        return {"status": "error", "reason": "db_error", "message": str(exc)}
    return {
        "status": "error",
        "reason": "internal_error",
        "message": f"{type(exc).__name__}: {exc}",
    }


def metrics(
    *,
    asset_id: str,
    window_months: int | str | None = None,
    db_path: Path | None = None,
) -> dict:
    """`GET /api/assets/{asset_id}/metrics` — `data.maint_value.maintenance_metrics` 위임.

    `window_months` 가 `None` 이면 그 함수의 기본값(`DEFAULT_WINDOW_MONTHS`, 24개월)을
    그대로 쓴다 — 여기서 리터럴로 다시 적지 않는다(정본은 `data/maint_value.py`).
    """
    kwargs = {} if window_months is None else {"window_months": window_months}
    try:
        with read_only(db_path) as con:
            return maint_value.maintenance_metrics(con, asset_id=asset_id, **kwargs)
    except Exception as e:  # noqa: BLE001 — 커넥션을 여는 시점의 예외까지 status 로 닫는다 (D9)
        return _open_error(e)


def repair_value(
    *,
    equipment_id: str,
    failed_part: str,
    repair_cost: int | str,
    repair_scope: str | None = None,
    db_path: Path | None = None,
) -> dict:
    """`POST /api/equipment/{equipment_id}/repair-value` — 무저장. `data.maint_value.repair_value` 위임.

    `repair_scope` 가 `None` 이면 그 함수의 계약 기본값(`"RESTORE"`)을 그대로 쓴다.
    """
    kwargs = {} if repair_scope is None else {"repair_scope": repair_scope}
    try:
        with read_only(db_path) as con:
            return maint_value.repair_value(
                con,
                equipment_id=equipment_id,
                failed_part=failed_part,
                repair_cost=repair_cost,
                **kwargs,
            )
    except Exception as e:  # noqa: BLE001
        return _open_error(e)


def part_criticality(*, part_no: str, db_path: Path | None = None) -> dict:
    """`GET /api/parts/{part_no}/criticality` — `data.maint_value.part_criticality` 위임."""
    try:
        with read_only(db_path) as con:
            return maint_value.part_criticality(con, part_no=part_no)
    except Exception as e:  # noqa: BLE001
        return _open_error(e)


def expenditure(
    *,
    part_no: str | None = None,
    part_class: str | None = None,
    repair_scope: str,
    amount: int | str,
    db_path: Path | None = None,
) -> dict:
    """`POST /api/expenditure/classify` — 무저장.

    `part_no`·`part_class` 는 **either-or** 다(엣지케이스 표). 둘 다 오면 어느 쪽이 이겼는지
    아무도 모르게 되므로 `invalid_input`, 둘 다 없어도 `expenditure()` 가 요구하는
    `part_class` 를 채울 길이 없으므로 같은 `invalid_input` 이다.

    `part_no` 만 오면 이 함수가 `classify_part_criticality` 로 등급을 채운다 — "④ 입력
    의존을 서버가 해소한다"(엣지케이스 표). 하위 판정 실패는 그대로 전파한다(재포장 금지) —
    `unknown_part`·`part_class_not_set` 등이 그대로 나갈 수 있다.

    ⚠ 원 REST 인터페이스(`docs/sprints/sprint-9.md` MQ-908)에는 `asset_id` 필드가 없다 —
    이 판정은 항상 `asset_id=None`(취득원가 대비 지출 비율 = `NOT_EVALUATED`)으로 호출된다.
    """
    has_no = bool(part_no and part_no.strip())
    has_class = bool(part_class and part_class.strip())
    if has_no and has_class:
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": "part_no 와 part_class 를 동시에 지정할 수 없습니다(either-or) — "
            "둘이 어긋나면 어느 쪽이 이겼는지 알 수 없습니다.",
        }
    if not has_no and not has_class:
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": "part_no 또는 part_class 중 하나는 필요합니다.",
        }
    try:
        with read_only(db_path) as con:
            resolved_class = part_class
            if has_no:
                part_result = maint_value.part_criticality(con, part_no=part_no)
                if part_result.get("status") != "ok":
                    return part_result
                resolved_class = part_result["part_class"]
            return maint_value.expenditure(
                con,
                part_class=resolved_class,
                repair_scope=repair_scope,
                amount=amount,
                asset_id=None,
            )
    except Exception as e:  # noqa: BLE001
        return _open_error(e)
