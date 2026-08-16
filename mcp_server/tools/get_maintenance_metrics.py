# -*- coding: utf-8 -*-
"""get_maintenance_metrics — 자산 보전지표 (MQ-607, `docs/12_MAINT_VALUE.md §2·§10`).

**이 파일은 얇은 래퍼다.** 산출 로직·상수는 전부 `data/maint_value.py` 에 있다 (MQ-903, D101).
이 도구가 지키는 결정(D70·D64·D68ⓑ·D2·D29)의 근거는 그 모듈 docstring 에 있다.

여기 남는 것은 세 가지뿐이다:
  1. `DESCRIPTION`·`DEFAULT_WINDOW_MONTHS` — `04 §설계원칙 3` 이 **"코드 정본"으로 인용**한다.
     옮기지 않는다(`server.py` 도 여기서 `DEFAULT_WINDOW_MONTHS` 를 그대로 가져간다).
  2. 커넥션 수명 (`read_only()`) — 읽기 전용이다 (D10). `data/maint_value.py` 는 DB 경로를 모른다.
  3. 반복 고장 문턱(D2·D29) 드리프트 방지 assert — 아래 참조.
"""

from __future__ import annotations

from data import maint_value

from ..db import read_only

# 반복 고장 문턱의 **정본은 이 파일 옆의 `get_error_history`** 다 (D2·D29). `data/maint_value.py`
# 는 `mcp_server` 를 import 할 수 없어(D15) `data/ownership.py` 의 기존 상수를 재사용하는데,
# 그 복제를 규율이 아니라 **import 시점 단언**으로 잠근다 — 어긋나면 MCP 서버가 기동하다 죽는다.
# `mcp_server/tools/verify_ownership.py:34` 와 같은 형태다.
from .get_error_history import REPEAT_THRESHOLD, REPEAT_WINDOW_DAYS

assert (maint_value.REPEAT_WINDOW_DAYS, maint_value.REPEAT_THRESHOLD) == (
    REPEAT_WINDOW_DAYS,
    REPEAT_THRESHOLD,
), (
    "반복 고장 문턱이 get_error_history 와 data/maint_value.py(data/ownership.py 재사용) 사이에서 "
    f"어긋났다 (D2·D29) — tools={(REPEAT_WINDOW_DAYS, REPEAT_THRESHOLD)} / "
    f"data={(maint_value.REPEAT_WINDOW_DAYS, maint_value.REPEAT_THRESHOLD)}"
)

DEFAULT_WINDOW_MONTHS = maint_value.DEFAULT_WINDOW_MONTHS

DESCRIPTION = (
    "설비 자산의 보전지표(MTBF·MTBF 추세·MTTR·가용도·예방보전 비율·누적 수리비·반복 고장 여부)를 "
    "조회한다. 수리할지 교체할지, 매각 시점인지 판단하기 전에 호출할 것. "
    "MTBF 는 가동시간이 아니라 달력 기준 평균 고장 간격(일)이며(mtbf_basis 확인), "
    "값이 null 이거나 mtbf_trend 가 insufficient_data 면 **데이터가 부족한 것**이지 "
    "'문제 없음'이 아니다 — 그 상태로 좋다/나쁘다를 단정하지 말 것. "
    "repeat_failure=true 면 지표 비교보다 근본원인 점검이 먼저다. "
    "OEE 는 이 도구가 제공하지 않으며 거래·처분 판정에 쓰지 말 것. "
    "부품 등급은 classify_part_criticality, 개별 에러 이력은 get_error_history 를 쓸 것."
)


def get_maintenance_metrics(
    asset_id: str | None = None,
    equipment_id: str | None = None,
    window_months: int | str = DEFAULT_WINDOW_MONTHS,
) -> dict:
    try:
        with read_only() as con:
            return maint_value.maintenance_metrics(
                con,
                asset_id=asset_id,
                equipment_id=equipment_id,
                window_months=window_months,
            )
    except Exception as e:  # noqa: BLE001 — 예외를 status 로 바꿔 반환 (D9)
        return {"status": "error", "reason": "db_error", "message": str(e)}
