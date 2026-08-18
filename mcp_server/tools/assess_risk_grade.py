# -*- coding: utf-8 -*-
"""assess_risk_grade — 건물 단위 위험 프로파일 등급 산출 (MQ-1104, S18, D102).

**이 파일은 얇은 래퍼다.** 판정 로직·상수는 전부 `data/risk_grade.py` 에 있다 (D101).
여기 남는 것은 두 가지뿐이다:
  1. `DESCRIPTION` — `04 §18` 이 정본으로 인용한다. 옮기지 않는다.
  2. 커넥션 수명 (`read_only()`) — 읽기 전용이다 (D10). `data/risk_grade.py` 는 DB 경로를 모른다.

⛔ 아무것도 쓰지 않는다 — `risk_profile.risk_grade` 를 갱신하는 경로는 이 도구를 포함한
어떤 MCP 도구에도 없다(절대 규칙 1). `changed:true` 는 알림 정보일 뿐 자동 반영이 아니다.
"""

from __future__ import annotations

from data import risk_grade

from ..db import read_only

DESCRIPTION = (
    "건물(building_id) 단위의 위험 프로파일(화기 취급·위험물 보관량·수전용량)로 위험등급을 "
    "산출하고, 마지막으로 저장된 등급과 달라졌는지(changed) 알려준다. 중고 취득 실사·처분 리스크 "
    "판단 시 building_id 또는 asset_id 중 하나로 호출할 것(asset_id 는 자산의 building_id 로 "
    "자동 해석된다). 3속성 중 하나라도 미확인이면 current_grade 는 null 이다 — 이때 등급을 "
    "추측해 채우지 말 것(D62). changed:true 는 재산정이 필요하다는 신호일 뿐 이 도구가 "
    "risk_profile 을 갱신하지는 않는다. 산출 등급은 통상 기준 목업 산식이며 실제 화재·환경 규제상 "
    "위험평가를 대체하지 않는다(disclaimer 참조)."
)


def assess_risk_grade(building_id: str | None = None, asset_id: str | None = None) -> dict:
    try:
        with read_only() as con:
            return risk_grade.risk_grade(con, building_id=building_id, asset_id=asset_id)
    except FileNotFoundError as e:
        return {"status": "error", "reason": "db_missing", "message": str(e)}
    except Exception as e:  # noqa: BLE001 — 도구는 예외를 던지지 않는다 (D9)
        return {"status": "error", "reason": "db_error", "message": str(e)}
