# -*- coding: utf-8 -*-
"""설비 하이라이트 색 판정 — 공유 데이터 계층 (D101·D73, spec §4-5·§4-6).

색 우선순위(부품 단위): 🔴 이상탐지 > 🔵 최근 수리 > 🟠 곧 점검 > 없음.
"이상탐지"는 새 탐지 로직(센서·임계치)이 아니라 기존 `error_history`+`error_codes.related_parts`+
`repair_records` 를 재해석하는 것뿐이다 — 이 프로젝트에 실시간 텔레메트리가 없다(spec §4-5).

커넥션은 호출자가 `mode=ro`로 열어 넘긴다 — `mcp_server`를 import하지 않는다(D15).
"""

from __future__ import annotations

from data.dbcompat import DbConnection

import json
from datetime import date

# 최근 수리로 볼 기간(일) · 곧 점검으로 볼 기간(일). spec §4-5 제안값.
N_RECENT_REPAIR_DAYS = 90
M_UPCOMING_DAYS = 60

# frontend/lib/hotspots.ts 의 partNo 와 짝이어야 한다 — 한쪽만 바뀌면 조용히 어긋난다.
MODEL_HOTSPOT_PARTS: dict[str, list[str]] = {
    "iG5A": ["FAN-IG5-01", "KPD-IG5-01", "PCB-IG5-CTRL"],
    "S100": ["FAN-S100-01", "KPD-S100-01", "PCB-S100-CTRL"],
}


def hotspot_status(con: DbConnection, *, asset_id: str, today: date) -> dict:
    eq = con.execute(
        "SELECT equipment_id, model FROM equipment WHERE asset_id = ? ORDER BY equipment_id",
        (asset_id,),
    ).fetchone()
    if eq is None:
        return {"status": "not_found", "reason": "no_equipment_for_asset"}

    equipment_id, model = eq["equipment_id"], eq["model"]
    part_nos = MODEL_HOTSPOT_PARTS.get(model)
    if part_nos is None:
        return {"status": "error", "reason": "unknown_model", "message": f"model={model!r}"}

    diagnoses = _latest_diagnosis_by_part(con, equipment_id, model, part_nos)
    repairs = _latest_signed_repair_by_part(con, equipment_id, part_nos)
    due = _lifecycle_due_by_part(con, equipment_id, part_nos)

    parts_status = []
    for part_no in part_nos:
        diag = diagnoses.get(part_no)
        repair = repairs.get(part_no)
        diag_at = diag["occurred_at"] if diag else None
        repair_at = repair["signed_at"] if repair else None

        if diag_at and (repair_at is None or diag_at > repair_at):
            color, basis = "red", diag
        elif repair_at and _within_days(repair_at, today, N_RECENT_REPAIR_DAYS):
            color, basis = "blue", repair
        elif part_no in due and (due[part_no] - today).days <= M_UPCOMING_DAYS:
            color, basis = "orange", {"next_maintenance_due": due[part_no].isoformat()}
        else:
            color, basis = None, {}

        parts_status.append({"part_no": part_no, "color": color, "basis": basis})

    return {"status": "ok", "equipment_id": equipment_id, "model": model, "parts": parts_status}


def _latest_diagnosis_by_part(
    con: DbConnection, equipment_id: str, model: str, part_nos: list[str]
) -> dict[str, dict]:
    """부품별 마지막 진단 이벤트. `occurred_at` 오름차순으로 훑어 마지막 값이 남게 한다."""
    rows = con.execute(
        "SELECT h.code, h.occurred_at, e.related_parts, e.causes, e.actions, e.manual_page"
        " FROM error_history h JOIN error_codes e ON e.model = ? AND e.code = h.code"
        " WHERE h.equipment_id = ? ORDER BY h.occurred_at",
        (model, equipment_id),
    ).fetchall()
    latest: dict[str, dict] = {}
    for row in rows:
        related = json.loads(row["related_parts"] or "[]")
        for part_no in part_nos:
            if part_no in related:
                latest[part_no] = {
                    "code": row["code"],
                    "occurred_at": row["occurred_at"],
                    "causes": json.loads(row["causes"]),
                    "actions": json.loads(row["actions"]),
                    "manual_page": row["manual_page"],
                }
    return latest


def _latest_signed_repair_by_part(
    con: DbConnection, equipment_id: str, part_nos: list[str]
) -> dict[str, dict]:
    """부품별 마지막 **서명된** 수리 기록. draft/pending 은 세지 않는다(spec §4-5 — "서명된")."""
    rows = con.execute(
        "SELECT r.repair_id, r.parts, r.signed_at, u.display_name AS performed_by_name"
        " FROM repair_records r LEFT JOIN users u ON u.user_id = r.performed_by"
        " WHERE r.equipment_id = ? AND r.state = 'signed' AND r.signed_at IS NOT NULL"
        " ORDER BY r.signed_at",
        (equipment_id,),
    ).fetchall()
    latest: dict[str, dict] = {}
    for row in rows:
        parts_in_record = json.loads(row["parts"] or "[]")
        for part_no in part_nos:
            if part_no in parts_in_record:
                latest[part_no] = {
                    "repair_id": row["repair_id"],
                    "signed_at": row["signed_at"],
                    "performed_by_name": row["performed_by_name"],
                }
    return latest


def _lifecycle_due_by_part(
    con: DbConnection, equipment_id: str, part_nos: list[str]
) -> dict[str, date]:
    rows = con.execute(
        "SELECT part_no, next_maintenance_due FROM part_lifecycle_mock WHERE equipment_id = ?",
        (equipment_id,),
    ).fetchall()
    return {
        row["part_no"]: date.fromisoformat(row["next_maintenance_due"])
        for row in rows
        if row["part_no"] in part_nos
    }


def _within_days(iso_datetime: str, today: date, days: int) -> bool:
    d = date.fromisoformat(iso_datetime[:10])
    return (today - d).days <= days
