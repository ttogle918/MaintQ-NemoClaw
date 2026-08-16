# -*- coding: utf-8 -*-
"""classify_expenditure — 수선 지출의 자본적/수익적 분류 (sprint-6 MQ-608, `12 §3`).

**이 파일은 얇은 래퍼다.** 판정 로직·규칙표·상수는 전부 `data/maint_value.py` 에 있다
(MQ-903, D101). 근거 검증이 판정보다 먼저인 이유(D61)·경계를 유보하는 이유(D62)는 그
모듈 docstring 에 있다.

⛔ 판정 규칙을 `data/rules/rules/` 에 두지 않는다 — 그 디렉토리는 **처분 플래그 전용**이고
(`disposal_type` 필수) `check_disposal_blockers` 가 디렉토리 전체를 로드하므로 지출 판정 룰을
넣으면 처분 판정에 섞여 들어간다. 그래서 규칙표가 `data/maint_value.py` 안에 있다(이 파일은
아니다).

여기 남는 것은 두 가지뿐이다:
  1. `DESCRIPTION` — `04 §설계원칙 3` 이 **"코드 정본"으로 인용**한다. 옮기지 않는다.
  2. 커넥션 수명 (`read_only()`) — 읽기 전용이다 (D10). `data/maint_value.py` 는 DB 경로를 모른다.
"""

from __future__ import annotations

from data import maint_value

from ..db import read_only

DESCRIPTION = (
    "수선·개조 지출을 자본적 지출(CAPITAL)과 수익적 지출(REVENUE)로 분류한다. "
    "수리비를 자산으로 올릴지 당기 비용으로 처리할지, 회계·세무 처리를 물을 때 사용할 것. "
    "part_class 는 추측하지 말고 classify_part_criticality 로 먼저 확인해 넣을 것. "
    "HOLD 는 실패가 아니라 '경계 사안이라 단정하지 않는다'는 판정이다 — "
    "CAPITAL·REVENUE 중 하나로 임의 해석하지 말고 세무 전문가 확인 필요를 그대로 전달할 것. "
    "부품 재고 조회·발주에는 사용 금지(search_inventory·create_po_draft). "
    "이 도구는 판정만 하며 전표 기표·세무 신고를 대신하지 않는다."
)


def classify_expenditure(
    part_class: str,
    repair_scope: str,
    amount: int,
    asset_id: str | None = None,
) -> dict:
    """지출을 CAPITAL | REVENUE | HOLD 로 분류한다.

    **필수 파라미터에 기본값을 두지 않는다 (D80).** 인자 누락은 도구 코드가 아니라 MCP 스키마
    검증이 앞단에서 막는다 — 기본값을 두면 FastMCP 가 `required` 를 빼서 optional 로 노출하고,
    LLM 이 인자 없이 호출 → `invalid_input` → 재시도하는 낭비 루프가 생긴다. D9 는 **도구 로직의
    실패**에 대한 규칙이지 호출 규약 위반에 대한 규칙이 아니다. 선택적인 `asset_id` 만 기본값을
    갖는다.
    """
    try:
        with read_only() as con:
            return maint_value.expenditure(
                con,
                part_class=part_class,
                repair_scope=repair_scope,
                amount=amount,
                asset_id=asset_id,
            )
    except Exception as e:  # noqa: BLE001 — 도구는 예외를 던지지 않는다 (D9)
        return {"status": "error", "reason": "db_error", "message": str(e)}
