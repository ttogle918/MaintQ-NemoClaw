# -*- coding: utf-8 -*-
"""발주 서비스 — 신원 stamp 와 상태 전이.

**신원이 도구 파라미터가 아닌 이유 (D23·D37).**
MCP 도구 스키마에 `requested_by` 가 있으면 LLM 이 그 값을 채울 수 있다 = 위조 경로다.
그래서 도구는 신원 없이 INSERT 하고, 백엔드가 같은 요청 안에서 X-User 값으로 stamp 한다.
백엔드는 사람 쪽 코드라 UPDATE 권한이 있어도 되고(D10 은 MCP 도구만 제약),
LLM 은 이 경로에 개입할 수 없다.

**상태 전이 (docs/06_REPO_API.md §2.4)**
    draft ──submit(정비사)──▶ pending ──approve(팀장)──▶ approved
                                 └──────reject(팀장)──▶ rejected
전이의 주체(역할)는 라우터가, 전이의 순서(현재 상태)는 여기서 강제한다.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from backend.db import connect

# 전이 규칙: 목표 상태 → 허용되는 현재 상태
ALLOWED_FROM: dict[str, str] = {
    "pending": "draft",
    "approved": "pending",
    "rejected": "pending",
}


class TransitionError(Exception):
    """현재 상태에서 할 수 없는 전이."""

    def __init__(self, po_id: str, current: str, target: str) -> None:
        self.po_id, self.current, self.target = po_id, current, target
        super().__init__(
            f"{po_id} 는 지금 '{current}' 상태라 '{target}' 로 전이할 수 없습니다 "
            f"('{ALLOWED_FROM[target]}' 에서만 가능)"
        )


def display_name(user_id: str | None, db_path: Path | None = None) -> str:
    """ASCII 사용자 ID → 화면 표시명 (D36 매핑을 D41 로 `users` 테이블 이관).

    하드코딩 딕셔너리였던 것을 DB 조회로 바꿨다 — 표시명이 코드에 박혀 있으면 사용자가
    늘 때마다 배포가 필요하고, `requested_by`/`decided_by` 의 FK 대상도 생기지 않는다.

    **미등록 ID 는 예외가 아니라 ID 를 그대로 돌려준다.** 표시명이 없다고 화면이 비면
    승인 큐에서 "누가 요청했는지"가 사라진다 — 삭제된 계정이어도 감사 추적은 남아야 한다.
    """
    if not user_id:
        return user_id or ""
    with connect(db_path) as con:
        r = con.execute("SELECT display_name FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return r["display_name"] if r else user_id


def iso_utc(ts: str | None) -> str | None:
    """DB 의 naive 문자열 → 타임존이 명시된 ISO-8601.

    SQLite 의 `CURRENT_TIMESTAMP` 는 **UTC** 인데 'YYYY-MM-DD HH:MM:SS' 로만 저장돼
    타임존 표기가 없다. 그대로 내보내면 브라우저가 로컬 시각으로 해석해
    KST 기준 9시간이 어긋난다 (실제로 "방금"이 "9시간 전"으로 보였다).
    저장은 UTC, 전송은 UTC 명시, 표시는 클라이언트가 로컬로 — 경계를 여기서 긋는다.
    """
    if not ts:
        return ts
    return ts.replace(" ", "T") + ("" if ts.endswith("Z") or "+" in ts else "Z")


# 표시명은 users 조인으로 붙인다 (D41) — 행마다 display_name() 을 부르면 N+1 이 된다.
# LEFT JOIN 인 이유: requested_by 는 stamp 전 NULL 이고, 미등록 ID 여도 행이 사라지면 안 된다
_PO_SELECT = (
    "SELECT p.*, pt.name AS part_name, s.name AS supplier_name,"
    " ru.display_name AS requested_by_name, du.display_name AS decided_by_name"
    " FROM po_drafts p"
    " JOIN parts pt ON pt.part_no = p.part_no"
    " JOIN suppliers s ON s.supplier_id = p.supplier_id"
    " LEFT JOIN users ru ON ru.user_id = p.requested_by"
    " LEFT JOIN users du ON du.user_id = p.decided_by"
)


def _row_to_po(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["evidence"] = json.loads(d["evidence"]) if d.get("evidence") else None
    # 미등록·NULL 이면 ID 를 그대로 (display_name() 과 같은 규칙)
    d["requested_by_name"] = d.get("requested_by_name") or d.get("requested_by") or ""
    d["decided_by_name"] = d.get("decided_by_name") or d.get("decided_by") or ""
    d["created_at"] = iso_utc(d.get("created_at"))
    return d


def stamp_identity(
    po_id: str,
    requested_by: str,
    session_id: str | None = None,
    db_path: Path | None = None,
) -> bool:
    """도구가 만든 draft 에 신원·세션을 새긴다 (D37).

    draft 상태에서 아직 비어 있을 때만 1회 — 이미 stamp 된 발주의 요청자를
    나중에 바꿀 수 있으면 감사 추적이 무너진다.
    """
    with connect(db_path) as con:
        cur = con.execute(
            "UPDATE po_drafts SET requested_by = ?, session_id = ?"
            " WHERE po_id = ? AND state = 'draft' AND requested_by IS NULL",
            (requested_by, session_id, po_id),
        )
        return cur.rowcount == 1


def list_pos(state: str | None = None, db_path: Path | None = None) -> list[dict]:
    sql = _PO_SELECT
    args: list[object] = []
    if state:
        sql += " WHERE p.state = ?"
        args.append(state)
    sql += " ORDER BY p.urgency = 'urgent' DESC, p.created_at DESC, p.po_id DESC"
    with connect(db_path) as con:
        return [_row_to_po(r) for r in con.execute(sql, args).fetchall()]


def get_po(po_id: str, db_path: Path | None = None) -> dict | None:
    """상세 — 근거 카드와 공급사 비교에 필요한 것을 한 번에 준다 (화면 B)."""
    with connect(db_path) as con:
        r = con.execute(_PO_SELECT + " WHERE p.po_id = ?", (po_id,)).fetchone()
        if r is None:
            return None
        po = _row_to_po(r)

        po["quotes"] = [
            dict(q)
            for q in con.execute(
                "SELECT sp.supplier_id, s.name, sp.lead_days, sp.unit_price, sp.moq"
                " FROM supplier_parts sp JOIN suppliers s ON s.supplier_id = sp.supplier_id"
                " WHERE sp.part_no = ? ORDER BY sp.lead_days",
                (po["part_no"],),
            ).fetchall()
        ]
        po["inventory"] = (
            dict(inv)
            if (
                inv := con.execute(
                    "SELECT qty, safety_stock, location FROM inventory WHERE part_no = ?",
                    (po["part_no"],),
                ).fetchone()
            )
            else None
        )
        # 화면 B "실행 로그 전체 보기" 링크 (D21)
        po["trace_url"] = f"/api/chat/{po['session_id']}/trace" if po["session_id"] else None
        return po


def transition(
    po_id: str,
    target: str,
    decided_by: str | None = None,
    note: str | None = None,
    db_path: Path | None = None,
) -> dict:
    """상태 전이. 현재 상태가 맞지 않으면 TransitionError."""
    with connect(db_path) as con:
        r = con.execute("SELECT state FROM po_drafts WHERE po_id = ?", (po_id,)).fetchone()
        if r is None:
            raise KeyError(po_id)
        if r["state"] != ALLOWED_FROM[target]:
            raise TransitionError(po_id, r["state"], target)

        if target == "pending":
            con.execute("UPDATE po_drafts SET state = ? WHERE po_id = ?", (target, po_id))
        else:
            con.execute(
                "UPDATE po_drafts SET state = ?, decided_by = ?, decision_note = ? WHERE po_id = ?",
                (target, decided_by, note, po_id),
            )
    return get_po(po_id, db_path) or {}
