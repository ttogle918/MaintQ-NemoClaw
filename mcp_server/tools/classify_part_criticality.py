# -*- coding: utf-8 -*-
"""classify_part_criticality — 부품 등급 조회 (MQ-606, `docs/12_MAINT_VALUE.md §10`).

**이 파일은 얇은 래퍼다.** 판정 로직·상수는 전부 `data/maint_value.py` 에 있다 (MQ-903, D101).
`reviewed:false` 가 왜 장식이 아닌지, 등급을 추측하지 않는 이유(D12)는 그 모듈 docstring 에 있다.

여기 남는 것은 두 가지뿐이다:
  1. `DESCRIPTION` — `04 §설계원칙 3` 이 **"코드 정본"으로 인용**한다. 옮기지 않는다.
  2. 커넥션 수명 (`read_only()`) — 읽기 전용이다 (D10). `data/maint_value.py` 는 DB 경로를 모른다.
"""

from __future__ import annotations

from data import maint_value

from ..db import read_only

DESCRIPTION = (
    "부품이 핵심 부품(CRITICAL)인지 소모품(CONSUMABLE)인지 조회한다. 수리 여부·지출 성격"
    "(자본적/수익적)·잔존가치 판단의 입력이 필요할 때 사용할 것. "
    "이 도구는 등록된 등급을 읽어올 뿐 추론하지 않는다 — 등급이 지정되지 않은 부품은 "
    "error(part_class_not_set)를 돌려주며, 이때 부품 이름이나 용도로 등급을 추측하지 말 것. "
    "재고 수량·단가 조회에는 사용 금지(search_inventory·get_supplier_quotes 를 쓸 것). "
    "반환되는 등급은 사람 검수 전 초안(reviewed=false)이므로 단정적으로 서술하지 말 것."
)


def classify_part_criticality(part_no: str) -> dict:
    try:
        with read_only() as con:
            return maint_value.part_criticality(con, part_no=part_no)
    except Exception as e:  # noqa: BLE001 — 도구는 예외를 던지지 않는다 (D9)
        return {"status": "error", "reason": "db_error", "message": str(e)}
