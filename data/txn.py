# -*- coding: utf-8 -*-
"""txn — 결재 흐름의 **동시성 원시(primitive)** 공유 계층 (D126).

`po_drafts` · `decisions` · `repair_records` 세 결재 흐름은 상태 기계의 **모양이 같다**:

    ① 행을 읽어 현재 상태를 확인한다
    ② 목표 상태로 갈 수 있는 상태인지 판정한다 (아니면 409)
    ③ UPDATE 로 상태를 옮긴다

세 서비스가 이 모양을 각자 손으로 구현하면서 ①과 ③ 사이가 **원자적이지 않았다** —
두 결재자가 같은 순간에 승인/반려를 누르면 둘 다 ②를 통과하고 둘 다 200 을 받는다
(lost update). `docs/14_CONCURRENCY.md` 에 재현 로그와 근본 원인이 있다.

⛔ 이 모듈은 `backend` 도 `mcp_server` 도 import 하지 않는다 (D15) — `data/po_draft.py`·
`data/repair_record.py` 와 같은 규약이다. 커넥션은 호출자가 열어서 넘긴다. 그래서
백엔드(사람 REST)와 MCP 도구(채번만) **양쪽이 같은 원시를 쓴다** — 채번 규약이
프로세스 경계를 넘어 갈라지지 않는다.

실패는 예외로 올린다(`KeyError`) — 이 모듈의 소비자는 사람용 REST 서비스 계층이고,
거기서는 예외를 라우터가 HTTP 로 옮기는 것이 기존 관행이다. D9(도구는 status 로 반환)는
`mcp_server/tools/*` 의 규칙이라 여기 해당하지 않는다.
"""

from __future__ import annotations

from data.dbcompat import DbConnection


# ── ① 행 잠금 ────────────────────────────────────────────────────────────────

def locked_row(con: DbConnection, table: str, pk_col: str, pk_value: str):
    """상태 전이의 대상 행을 **잠근 채** 읽는다.

    `SELECT ... FOR UPDATE` 가 이 함수의 존재 이유 전부다. 잠금이 없으면 Postgres 기본
    격리수준(READ COMMITTED)에서 두 트랜잭션이 같은 `state` 를 읽고 둘 다 전이 판정을
    통과한다 — 뒤에 커밋한 쪽이 앞선 결재를 조용히 덮어쓴다.

    `FOR UPDATE` 는 두 번째 트랜잭션을 첫 번째의 COMMIT 까지 **대기**시키고, 대기가
    풀린 뒤 `state` 를 **다시 읽게** 한다. 그래서 두 번째는 이미 바뀐 상태를 보고
    호출부의 전이 판정에서 정상적으로 409 로 떨어진다.

    ⚠ 반드시 **UPDATE 와 같은 트랜잭션 안**에서 불러야 한다. 잠금은 트랜잭션 종료 시
    풀리므로, 여기서 읽고 커넥션을 닫은 뒤 다른 커넥션에서 UPDATE 하면 아무것도
    막지 못한다(그게 정확히 이 함수가 고치려는 버그다).

    ⚠ 이름을 믿을 수 있게 유지할 것. 이전 구현들은 `_locked_row` 라는 이름을 달고
    잠그지 않았다 — 이름이 거짓이면 호출부는 안전하다고 **믿고** 검토를 건너뛴다.

    없는 행이면 `KeyError` (라우터가 404 로 옮긴다).
    """
    r = con.execute(
        f"SELECT * FROM {table} WHERE {pk_col} = ? FOR UPDATE", (pk_value,)
    ).fetchone()
    if r is None:
        raise KeyError(pk_value)
    return r


# ── ② 순번 채번 ──────────────────────────────────────────────────────────────

def next_sequential_id(con: DbConnection, table: str, col: str, prefix: str) -> str:
    """`PO-0042` 형태의 다음 식별자를 **경쟁 없이** 발급한다.

    기존 구현은 세 곳(`po_draft`·`repair_record`·`decisions`)에 복제된 `MAX+1` 이었고,
    읽기와 INSERT 사이에 잠금이 없어 동시 생성 시 두 요청이 같은 번호를 받았다 —
    PK 제약이 데이터는 지켜주지만 한쪽 사용자는 500 을 받는다.

    **왜 시퀀스(`SERIAL`)가 아닌가.** `PO-%04d` 는 화면·문서·감사 로그에 그대로 찍히는
    표시 규약이고 스파이크가 이 형식을 문자열로 대조한다. 시퀀스로 바꾸면 스키마
    마이그레이션 + 그 계약 전부를 건드려야 한다 — 이 함수는 형식을 그대로 두고
    **경쟁만** 없앤다.

    **왜 자문 잠금(advisory lock)인가.** 잠글 대상 행이 아직 **존재하지 않으므로**
    `FOR UPDATE` 를 걸 행이 없다. `pg_advisory_xact_lock` 은 임의의 키에 잠금을 걸고
    **트랜잭션 종료 시 자동 해제**된다(`_xact_` 접미가 그 뜻) — 명시적 해제를 잊어
    잠금이 새는 경로가 없다. 테이블 전체를 `LOCK TABLE` 하는 것보다 좁다: 같은 테이블에
    대한 **채번끼리만** 직렬화되고 일반 읽기·수정은 막지 않는다.

    같은 테이블을 부르는 호출자는 전부 이 함수를 거쳐야 의미가 있다 — 한 곳이라도
    옛 `MAX+1` 을 그대로 쓰면 그쪽이 잠금 밖에서 같은 번호를 발급한다.
    """
    # 키를 테이블 이름에서 유도한다 — 호출자가 상수를 각자 고르면 같은 테이블에 서로
    # 다른 잠금이 걸려 직렬화가 성립하지 않는다.
    con.execute("SELECT pg_advisory_xact_lock(hashtext(?))", (f"maintq.seq.{table}",))

    # 정렬은 **문자열이 아니라 수치**로 한다. `LIKE 'PO-%' ORDER BY po_id DESC` 는
    # 자릿수가 고정일 때만 맞다 — `PO-9999` 다음이 `PO-10000` 이 되는 순간 사전순
    # 내림차순은 `PO-9999` 를 위로 올리고, 채번이 `PO-10000` 으로 되돌아가 PK 충돌을
    # 영구 반복한다.
    #
    # 필터도 `LIKE` 가 아니라 정규식이다. `LIKE '{prefix}-%'` 는 접미가 숫자가 아닌 행
    # (마이그레이션 잔재·수동 보정·테스트 찌꺼기 `PO-V1` 등)까지 잡고, 그 행이 한 건이라도
    # 있으면 `int()` 가 ValueError 로 죽어 **그 테이블의 채번 전체가 영구 마비**된다.
    # 형식에 맞는 행만 후보로 본다 — 이물질은 무시하고 계속 발급한다.
    row = con.execute(
        f"SELECT {col} AS v FROM {table} WHERE {col} ~ ?"
        f" ORDER BY (substring({col} from '[0-9]+$'))::bigint DESC LIMIT 1",
        (f"^{prefix}-[0-9]+$",),
    ).fetchone()
    n = int(row["v"].rsplit("-", 1)[1]) + 1 if row else 1
    # 5자리 이상으로 넘어가면 폭을 자연스럽게 넓힌다(자르지 않는다) — 위 수치 정렬이
    # 그 상태에서도 계속 맞는다.
    return f"{prefix}-{n:04d}"
