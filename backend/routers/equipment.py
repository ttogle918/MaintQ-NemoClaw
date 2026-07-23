# -*- coding: utf-8 -*-
"""라인/장비 컨텍스트 + 에러 이력 (docs/06_REPO_API.md §2.3)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.db import connect
from backend.deps import Caller, caller, require

router = APIRouter(prefix="/api/equipment", tags=["equipment"])


class ErrorRecord(BaseModel):
    """에러 발생 기록 — 정비사의 명시적 액션만 (D29·A7)."""

    code: str = Field(min_length=2, max_length=4)
    occurred_at: str | None = None
    action_taken: str | None = None
    part_replaced: str | None = None


@router.get("")
def list_equipment(c: Caller = Depends(caller)) -> dict:
    with connect() as con:
        rows = con.execute(
            "SELECT equipment_id, line_id, model, installed_at, location"
            " FROM equipment ORDER BY line_id, equipment_id"
        ).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.get("/{equipment_id}/history")
def history(equipment_id: str, days: int = 180, c: Caller = Depends(caller)) -> dict:
    with connect() as con:
        if (
            con.execute(
                "SELECT 1 FROM equipment WHERE equipment_id = ?", (equipment_id,)
            ).fetchone()
            is None
        ):
            raise HTTPException(404, f"설비를 찾을 수 없습니다: {equipment_id}")
        rows = con.execute(
            "SELECT code, occurred_at, action_taken, part_replaced, resolved"
            " FROM error_history WHERE equipment_id = ?"
            " AND occurred_at >= datetime('now', ?)"
            " ORDER BY occurred_at DESC",
            (equipment_id, f"-{int(days)} day"),
        ).fetchall()
    return {"equipment_id": equipment_id, "count": len(rows), "events": [dict(r) for r in rows]}


@router.post("/{equipment_id}/errors", status_code=201)
def record_error(equipment_id: str, body: ErrorRecord, c: Caller = Depends(caller)) -> dict:
    """에러 발생을 이력에 기록한다.

    **에이전트 루프가 자동으로 부르지 않는다 (D29).** 채팅 진입만으로 기록하면
    `get_error_history` 의 count 가 실제 고장 횟수가 아니라 질문 횟수가 되어,
    같은 에러를 세 번 물어본 것만으로 repeated=true 가 잘못 켜진다.
    """
    require(c, "technician", "고장 이력 기록")

    code = body.code.upper()  # 저장은 대문자 canonical (D25)
    if not code.isascii() or not all(ch.isalnum() or ch == "_" for ch in code):
        raise HTTPException(400, f"코드 형식이 올바르지 않습니다: {body.code!r}")

    occurred = body.occurred_at or datetime.now().isoformat(sep=" ", timespec="seconds")

    with connect() as con:
        if (
            con.execute(
                "SELECT 1 FROM equipment WHERE equipment_id = ?", (equipment_id,)
            ).fetchone()
            is None
        ):
            raise HTTPException(404, f"설비를 찾을 수 없습니다: {equipment_id}")
        cur = con.execute(
            "INSERT INTO error_history (equipment_id, code, occurred_at, action_taken,"
            " part_replaced, resolved) VALUES (?,?,?,?,?,0)",
            (equipment_id, code, occurred, body.action_taken, body.part_replaced),
        )
        row_id = cur.lastrowid

    return {
        "status": "ok",
        "id": row_id,
        "equipment_id": equipment_id,
        "code": code,
        "occurred_at": occurred,
        "recorded_by": c.user_id,
    }
