# -*- coding: utf-8 -*-
"""수리 증빙(`repair_records`) 서명 해시 규약 — **단일 출처** (D73·D84·D98).

`docs/05_DB_SCHEMA.md §16` 이 "해시 규약은 나중에 정한다"고 미뤄 둔 자리를 여기서 정한다.
`data/seed.py`(시드 11행 채움 · 자가검증 ㉙)와 `backend/services/repairs.py`(서명 API, MQ-909)가
**이 모듈 하나를 함께 import** 한다 — 규약이 두 곳에 따로 있으면 조용히 어긋난다.

`canonical_json` 은 `backend/services/decisions.py:canonical_json` 과 **동일 규약**이다
(`sort_keys=True` · `separators=(",",":")` · `ensure_ascii=False`) — "같은 사실 → 같은 해시"가
성립하려면 두 모듈이 같은 직렬화 규칙을 써야 한다. `decisions.compute_bundle_hash` 와 달리
`data/rules/engine.text_hash` 의 NFKC·공백정규화는 **거치지 않는다** — 그건 법령 원문처럼
공백/전각 표기가 흔들리는 텍스트를 위한 처리이고, 여기 해시 대상은 이미 구조화된 값(정수·문자열
리터럴·JSON 배열 문자열)이라 정규화가 오히려 실제 값 차이(예: 콤마 뒤 공백)를 지워 버릴 위험이
있다.

호출부 주의: `row["parts"]` 는 **DB 에 저장되는 그대로의 JSON 문자열**을 넣는다(파싱한 list 를
넣지 않는다). 시드가 넣는 값과 서명 API 가 DB 에서 읽어 재계산하는 값이 같은 표현이어야
"같은 사실 → 같은 해시"가 실제로 성립한다.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final

# 해시에 포함되는 컬럼 — 이 순서·구성이 바뀌면 기존 서명 해시가 전부 무효가 된다.
# performed_by·verified_by·signed_at 을 포함해 "누가 언제 무엇을 서명했는가"까지 고정한다.
HASHED_KEYS: Final[tuple[str, ...]] = (
    "repair_id",
    "equipment_id",
    "model",
    "error_code",
    "part_class",
    "work_type",
    "expenditure_class",
    "cost",
    "downtime_hours",
    "parts",
    "performed_by",
    "verified_by",
    "signed_at",
)


def canonical_json(obj: Any) -> str:
    """정준 직렬화. `backend/services/decisions.py:canonical_json` 과 **동일 규약**."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_record_hash(row: Mapping[str, Any]) -> str:
    """`row` 에서 `HASHED_KEYS` 만 뽑아 정준 직렬화한 뒤 sha256 — `"sha256:…"` 형태로 반환.

    `row` 에 `HASHED_KEYS` 밖의 키가 더 있어도(예: DB 조회 결과 전체 dict) 무시한다.
    없는 키는 `None` 으로 취급한다.
    """
    subset = {k: row.get(k) for k in HASHED_KEYS}
    return "sha256:" + hashlib.sha256(canonical_json(subset).encode()).hexdigest()
