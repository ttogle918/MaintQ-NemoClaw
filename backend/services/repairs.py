# -*- coding: utf-8 -*-
"""수리 증빙(`repair_records`) 서비스 — 제출·서명·반려 (MQ-909, D85·D98).

`services/po.py`·`services/decisions.py` 와 **같은 3원칙**을 따른다:
  1. 상태 전이는 `ALLOWED_FROM` 한 곳을 지난다. 불가 전이는 `RepairTransitionError` → 409.
  2. 신원은 도구가 아니라 백엔드가 stamp 한다 (D23·D37) — `create_repair_record`(§16) 는
     `performed_by`·`verified_by`·`signed_at`·`record_hash`·`requested_by`·`session_id` 를
     전부 NULL 로 INSERT 하고, 이 모듈이 상태 전이와 함께 채운다.
  3. **append-only** — `signed` 이후 어떤 경로로도 UPDATE 하지 않는다(이 모듈에 그런 경로가
     없다). 정정은 새 레코드(`docs/12_MAINT_VALUE.md §7`)이며, **이번 스프린트 범위 밖**이다.

`verified_by` 컬럼은 서명자뿐 아니라 **반려자도 함께 쓴다** — DDL 에 별도 `reviewed_by`
컬럼이 없고(`data/seed.py §16`), 반려도 서명과 같은 "manager 가 그 증빙을 검토했다"는 사건이라
같은 신원 컬럼이 그 사실을 담는다. CHECK 는 `state='signed'` 일 때만 `verified_by` non-null 을
강제하므로(신설 ②) `state='rejected'` 에 `verified_by` 를 채우는 것은 스키마와 어긋나지 않는다.

해시 규약은 `data/repair_hash.py` 가 **단일 출처**다(D73·D84) — 여기서 재구현하지 않는다.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from backend.db import connect
from backend.services.decisions import now_utc_sql
from backend.services.po import iso_utc
from data.repair_hash import HASHED_KEYS, compute_record_hash

# 전이 규칙: 목표 상태 → 허용되는 현재 상태 (`services/po.ALLOWED_FROM`·
# `services/decisions.ALLOWED_FROM` 과 같은 형태)
ALLOWED_FROM: dict[str, str] = {"pending": "draft", "signed": "pending", "rejected": "pending"}

# 승인 큐 카드 제목에 쓰는 표시 라벨. `services/decisions.DISPOSAL_MODE_LABELS` 와 같은 패턴.
WORK_TYPE_LABELS: dict[str, str] = {"PLANNED": "계획", "UNPLANNED": "비계획"}


class RepairTransitionError(Exception):
    """현재 상태에서 할 수 없는 전이 → 409 `invalid_transition`."""

    def __init__(self, repair_id: str, current: str, target: str) -> None:
        self.repair_id, self.current, self.target = repair_id, current, target
        super().__init__(
            f"{repair_id} 는 지금 '{current}' 상태라 '{target}' 로 전이할 수 없습니다 "
            f"('{ALLOWED_FROM[target]}' 에서만 가능)"
        )


class SelfSignError(Exception):
    """`performed_by == verified_by` → 409 `self_sign` (D4 — 진단자/승인자 분리)."""

    reason = "self_sign"

    def __init__(self, repair_id: str, user_id: str) -> None:
        self.repair_id, self.user_id = repair_id, user_id
        super().__init__(
            f"{repair_id}: 작업을 수행한 사람({user_id})이 스스로 서명할 수 없습니다 (D4)"
        )


# 표시명은 users 조인으로 붙인다 (`services/po._PO_SELECT` 와 같은 이유 — N+1 방지)
_REPAIR_SELECT = (
    "SELECT r.*, pu.display_name AS performed_by_name, vu.display_name AS verified_by_name,"
    " ru.display_name AS requested_by_name"
    " FROM repair_records r"
    " LEFT JOIN users pu ON pu.user_id = r.performed_by"
    " LEFT JOIN users vu ON vu.user_id = r.verified_by"
    " LEFT JOIN users ru ON ru.user_id = r.requested_by"
)


def _row_to_repair(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["parts"] = json.loads(d["parts"]) if d.get("parts") else []
    # 미등록·NULL 이면 ID 를 그대로 (`services/po._row_to_po` 와 같은 규칙)
    d["performed_by_name"] = d.get("performed_by_name") or d.get("performed_by") or ""
    d["verified_by_name"] = d.get("verified_by_name") or d.get("verified_by") or ""
    d["requested_by_name"] = d.get("requested_by_name") or d.get("requested_by") or ""
    d["created_at"] = iso_utc(d.get("created_at"))
    d["signed_at"] = iso_utc(d.get("signed_at"))
    return d


def list_repairs(state: str | None = None, db_path: Path | None = None) -> list[dict]:
    sql = _REPAIR_SELECT
    args: list[object] = []
    if state:
        sql += " WHERE r.state = ?"
        args.append(state)
    sql += " ORDER BY r.created_at DESC, r.repair_id DESC"
    with connect(db_path) as con:
        return [_row_to_repair(r) for r in con.execute(sql, args).fetchall()]


def get_repair(repair_id: str, db_path: Path | None = None) -> dict | None:
    """상세. `hash_verified` 는 저장된 `record_hash` 를 `data.repair_hash` 규약으로
    재계산해 대조한 결과다(D84 태도) — 서명되지 않은 레코드는 `record_hash` 가 NULL 이라
    항상 `false` 다(값이 없으니 "일치"가 성립할 수 없다 — `null` 이 아니라 `false` 로 고정하는
    이유는 계약이 `true/false` 둘로만 나뉘게 정했기 때문이다, MQ-909 DoD)."""
    with connect(db_path) as con:
        r = con.execute(_REPAIR_SELECT + " WHERE r.repair_id = ?", (repair_id,)).fetchone()
        if r is None:
            return None
        raw = dict(r)  # HASHED_KEYS 는 DB 원본 표현(가공 전 signed_at·parts 문자열)을 요구한다
        recomputed = compute_record_hash({k: raw.get(k) for k in HASHED_KEYS})
        d = _row_to_repair(r)
        d["hash_verified"] = raw.get("record_hash") is not None and raw["record_hash"] == recomputed
        return d


def _locked_row(con: sqlite3.Connection, repair_id: str) -> sqlite3.Row:
    r = con.execute("SELECT * FROM repair_records WHERE repair_id = ?", (repair_id,)).fetchone()
    if r is None:
        raise KeyError(repair_id)
    return r


def submit(
    repair_id: str,
    *,
    requested_by: str,
    session_id: str | None = None,
    db_path: Path | None = None,
) -> dict:
    """draft → pending. 정비사의 '팀장 서명 요청' (A3 — 에이전트 루프 밖).

    `requested_by`·`performed_by` 를 `X-User` 로 stamp(D23·D37) — 이미 stamp 돼 있으면
    (`create_repair_record` 는 항상 NULL 로 INSERT 하지만, 시드 데이터처럼 `performed_by` 가
    이미 채워진 행도 있을 수 있다) 덮지 않는다. `session_id` 도 같은 규칙으로 최초 1회만
    (현재 REST 경로는 세션 문맥이 없어 항상 `None` 을 넘긴다 — 호출자가 언젠가 세션 문맥과
    함께 부르게 되어도 계약이 바뀌지 않도록 파라미터를 미리 둔다).
    """
    with connect(db_path) as con:
        row = _locked_row(con, repair_id)
        if row["state"] != ALLOWED_FROM["pending"]:
            raise RepairTransitionError(repair_id, row["state"], "pending")
        con.execute(
            "UPDATE repair_records SET state='pending',"
            " requested_by = COALESCE(requested_by, ?),"
            " performed_by = COALESCE(performed_by, ?),"
            " session_id = COALESCE(session_id, ?)"
            " WHERE repair_id = ?",
            (requested_by, requested_by, session_id, repair_id),
        )
    return get_repair(repair_id, db_path) or {}


def sign(repair_id: str, *, verified_by: str, db_path: Path | None = None) -> dict:
    """pending → signed. **manager 전용** (라우터가 역할을 강제한다).

    ⓐ `verified_by = X-User` ⓑ `signed_at = UTC now`(D39) ⓒ `record_hash =
    data.repair_hash.compute_record_hash(row)` — **세 값을 같은 UPDATE 에서** 쓴다.
    DDL CHECK(신설 ②)가 하나라도 빠지면 거부한다. ⓓ `performed_by == verified_by` 면
    `SelfSignError` → 409 `self_sign` (D4).
    """
    with connect(db_path) as con:
        row = _locked_row(con, repair_id)
        if row["state"] != ALLOWED_FROM["signed"]:
            raise RepairTransitionError(repair_id, row["state"], "signed")
        if row["performed_by"] is not None and row["performed_by"] == verified_by:
            raise SelfSignError(repair_id, verified_by)

        signed_at = now_utc_sql()
        raw = dict(row)
        raw["verified_by"] = verified_by
        raw["signed_at"] = signed_at
        record_hash = compute_record_hash({k: raw.get(k) for k in HASHED_KEYS})

        con.execute(
            "UPDATE repair_records SET state='signed', verified_by=?, signed_at=?, record_hash=?"
            " WHERE repair_id = ?",
            (verified_by, signed_at, record_hash, repair_id),
        )
    return get_repair(repair_id, db_path) or {}


def reject(repair_id: str, *, verified_by: str, reason: str, db_path: Path | None = None) -> dict:
    """pending → rejected. 사유 필수(D38) → `note` 에 저장. `rejected` 는 종착역(P15 백로그).

    라우터의 pydantic 이 공백을 먼저 막는다(422) — 여기서는 값을 그대로 받아 저장한다.
    """
    with connect(db_path) as con:
        row = _locked_row(con, repair_id)
        if row["state"] != ALLOWED_FROM["rejected"]:
            raise RepairTransitionError(repair_id, row["state"], "rejected")
        con.execute(
            "UPDATE repair_records SET state='rejected', verified_by=?, note=?"
            " WHERE repair_id = ?",
            (verified_by, reason, repair_id),
        )
    return get_repair(repair_id, db_path) or {}
