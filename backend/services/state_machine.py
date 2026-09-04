# -*- coding: utf-8 -*-
"""state_machine — 결재 상태 전이의 **골격** 공유 계층 (D126).

`po_drafts` · `decisions` · `repair_records` 세 결재 흐름의 전이 함수 8개는 앞부분
네 단계가 **글자까지 같았다**:

    ① 커넥션을 연다
    ② 대상 행을 **잠근 채** 읽는다        → 없으면 KeyError (라우터가 404)
    ③ 목표 상태로 갈 수 있는 상태인가     → 아니면 <흐름>TransitionError (라우터가 409)
    ④ (흐름마다 다른 일)

①~③ 이 이 모듈의 전부다. **④ 는 각 서비스에 그대로 남는다** — 합치지 않는다.
`decisions.sign()` 의 6단계 순서 계약(D84 — 근거 재산출·해시 대조·override 게이트)과
`repairs.sign()` 의 `record_hash` 산출은 **의도적으로 다른 로직**이라, 하나의 추상
아래로 밀어 넣으면 읽기 어려워지고 계약이 흐려진다. 골격만 공통화한다.

**왜 `data/` 가 아니라 여기인가.** 이 골격은 `backend.db.connect()` 로 커넥션을 여는
것까지 포함한다 — `data/` 는 DB 경로를 모르는 계층이라(D15, 커넥션은 호출자가 연다)
그 책임을 가질 수 없다. 잠금 원시 자체(`FOR UPDATE`)는 `data/txn.py` 가 소유하고
MCP 도구와 공유하며, 이 모듈은 그 위에 백엔드 전용 골격을 얹는다.

사용:

    FLOW = state_machine.Flow("po_drafts", "po_id", ALLOWED_FROM, TransitionError)

    def reject(po_id, *, decided_by, note, db_path=None):
        with FLOW.transition(po_id, "rejected", db_path=db_path) as (con, row):
            con.execute("UPDATE po_drafts SET ... WHERE po_id = ?", (...))
        return get_po(po_id, db_path) or {}

`with` 블록을 정상적으로 빠져나오면 `backend.db.connect()` 가 커밋한다. 블록 안에서
예외가 나면 롤백된다 — 즉 ④ 에서 올린 예외(`SelfSignError`·`EvidenceChanged` 등)는
**부분 변경을 남기지 않는다.**
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from backend.db import connect
from data import txn


class TransitionErrorFactory(Protocol):
    """`(entity_id, current_state, target_state)` 로 예외를 만드는 호출체.

    세 서비스의 `TransitionError`·`DecisionTransitionError`·`RepairTransitionError` 가
    모두 이 시그니처다. 예외 **클래스 자체는 합치지 않는다** — 라우터가 흐름별로
    `except` 를 걸어 서로 다른 409 응답 본문을 만들기 때문이다.
    """

    def __call__(self, entity_id: str, current: str, target: str) -> Exception: ...


@dataclass(frozen=True)
class Flow:
    """한 결재 흐름의 전이 규칙.

    `table`·`pk` 는 SQL 식별자로 직접 들어간다 — **호출자가 주는 상수만** 넣을 것
    (사용자 입력을 흘리면 인젝션 경로가 된다). 세 서비스 모두 모듈 상수로 고정한다.
    """

    table: str
    pk: str
    allowed_from: Mapping[str, str]
    error: TransitionErrorFactory | Callable[..., Exception]

    @contextmanager
    def transition(
        self, entity_id: str, target: str, *, db_path: str | None = None
    ) -> Iterator[tuple[Any, Any]]:
        """전이 골격 ①~③. `(con, row)` 를 넘겨주고 나머지는 호출부가 한다.

        `row` 는 **잠긴 상태**의 전체 행이다 — `repairs.sign()` 의 `performed_by`
        자기서명 검사나 `decisions.sign()` 의 `evidence_bundle` 처럼, ④ 가 다른
        컬럼을 봐야 하는 경우가 있어 `state` 만 주지 않는다.

        ⚠ `con` 을 블록 밖으로 들고 나가지 말 것. 잠금은 이 `with` 가 끝나며 함께
        풀린다 — 밖에서 UPDATE 하면 아무것도 막지 못한다(D126 이 고친 그 버그다).
        """
        with connect(db_path) as con:
            row = txn.locked_row(con, self.table, self.pk, entity_id)
            # `allowed_from[target]` 은 행 확인 **뒤에** 평가한다 — 순서를 바꾸면
            # 없는 ID + 잘못된 target 조합에서 404 대신 다른 예외가 나간다.
            if row["state"] != self.allowed_from[target]:
                raise self.error(entity_id, row["state"], target)
            yield con, row
