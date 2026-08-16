# -*- coding: utf-8 -*-
"""assess_repair_value — 수리 / 교체 / 현상매각 3지 판단 (MQ-609, S1+ · `docs/12_MAINT_VALUE.md §1·§9·§11`).

**이 파일은 얇은 래퍼다.** 판정 로직·상수는 전부 `data/maint_value.py` 의 `repair_value()` 에
있다 (MQ-922, D101). 반복 고장 최우선 분기(D2)·시장가 미보간(D65·D74)·하위 판정 실패 전파
(`04 §13`)·"값을 어디서 읽는가" 규약(Stage 4 B-1 재발 방지)의 근거는 그 모듈 섹션 docstring에
있다.

여기 남는 것은 세 가지뿐이다:
  1. `DESCRIPTION`·`DEFAULT_REPAIR_SCOPE` — `04 §설계원칙 3` 이 **"코드 정본"으로 인용**하고,
     `mcp_server/server.py:183` 이 후자를 그대로 import 한다. 옮기지 않는다 — 옮기면
     `server.py` 를 고쳐야 하고, 같은 스테이지의 `create_repair_record` 태스크(=`server.py`
     소유)와 파일이 충돌한다 (MQ-922).
  2. 커넥션 수명 (`read_only` **1회**) — 읽기 전용이다 (D10). `data/maint_value.py` 는 DB
     경로를 모르므로 이 함수가 연 커넥션 하나를 판정(및 그 하위의 `part_criticality`·
     `maintenance_metrics`)이 그대로 재사용한다. 원본은 커넥션을 2회 열고 그 사이에서
     하위 도구 2종이 각자 또 열었다 — 이제 전부 이 한 번으로 합쳐진다 (MQ-922 본체).
  3. 예외를 `status` 로 닫는 바깥 껍데기 (D9·D46).

읽기 전용이다 (`read_only` 만, D10). 실패는 예외가 아니라 `status` 로 돌려준다 (D9·D46).
"""

from __future__ import annotations

from data import maint_value

from ..db import read_only

DEFAULT_REPAIR_SCOPE = "RESTORE"

DESCRIPTION = (
    "고장 난 설비를 수리할지, 교체할지, 수리 없이 현상 매각할지를 판단한다. "
    "수리비를 알고 있고 '고쳐 쓰는 게 나은가'를 물을 때 호출할 것. "
    "verdict 가 ROOT_CAUSE_FIRST 면 3지 선택지 자체가 없다 — 같은 고장이 반복되고 있다는 뜻이므로 "
    "수리·교체·매각 중 무엇도 권하지 말고 근본원인 점검을 먼저 안내하고 발주는 보류할 것. "
    "HOLD 는 '문제 없음'이 아니라 시장가를 산출할 원천이 없어 판단을 유보한 것이다 — "
    "금액을 추정해 메우지 말 것. "
    "market_value_before·market_value_after·value_recovery 는 목업 잔가곡선 기반 추정치이며 "
    "실거래가가 아니다(estimates 참조) — 사용자에게 확정 금액처럼 말하지 말 것. "
    "repair_cost 는 이 도구가 검증하지 않는다. 부품 단가·리드타임은 get_supplier_quotes, "
    "재고는 search_inventory, 지출의 세무 성격은 classify_expenditure 를 쓸 것. "
    "처분 가능 여부(법정 조건)는 이 도구가 아니라 check_disposal_blockers 소관이다."
)


def assess_repair_value(
    equipment_id: str,
    failed_part: str,
    repair_cost: int,
    repair_scope: str = DEFAULT_REPAIR_SCOPE,
) -> dict:
    """공개 진입점 — **얇은 래퍼**.

    ★ 필수 파라미터에 기본값을 두지 않는다 (D80) — 인자 누락은 MCP 스키마(pydantic)가
      본체 진입 전에 막는다. 기본값을 두면 "안 준 것"과 "빈 값을 준 것"이 구분되지 않는다.
      `repair_scope` 만 optional(기본 `DEFAULT_REPAIR_SCOPE`)이다.
    """
    try:
        with read_only() as con:
            return maint_value.repair_value(
                con,
                equipment_id=equipment_id,
                failed_part=failed_part,
                repair_cost=repair_cost,
                repair_scope=repair_scope,
            )
    except Exception as e:  # noqa: BLE001 — 도구는 예외를 던지지 않는다 (D9)
        return {"status": "error", "reason": "db_error", "message": str(e)}
