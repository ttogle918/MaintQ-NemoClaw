# -*- coding: utf-8 -*-
"""사업장 → 구역 → 설비 위치 (D158, Sprint 19 MQ-1914 — docs/06_REPO_API.md §2.12).

**읽기 전용 · 역할 무관.** 평면도(SVG)를 그릴 재료만 준다 — 설비 상태(하이라이트)·기종
온보딩 상태는 여기서 판정하지 않는다. 화면이 기존 API(`GET /api/assets/{id}/hotspot-status`·
`GET /api/onboarding/status`)를 그대로 불러 조합한다: 판정 로직을 두 벌 만들면 두 화면이
같은 설비를 다른 색으로 칠하는 날이 온다.

커넥션은 `read_only()`(세션 `default_transaction_read_only=on`)다 — "SELECT 만 썼으니
안전하다"는 규율이 아니라 구조로 무저장을 보증한다(`backend/services/disposal.py` 주석).
⛔ 이 라우터에 쓰기 엔드포인트를 추가하지 않는다 — 배치 변경은 시드·멱등 마이그레이션
(`scripts/migrate_d158_sites.py`)의 몫이다(D158).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.deps import Caller, caller
from backend.services.disposal import read_only

router = APIRouter(prefix="/api/sites", tags=["sites"])


def _site_dict(r) -> dict:
    return {
        "site_id": r["site_id"],
        "name": r["name"],
        "is_mock": bool(r["is_mock"]),
        "width": r["width"],
        "height": r["height"],
    }


@router.get("")
def list_sites(c: Caller = Depends(caller)) -> dict:
    """사업장 목록 (역할 무관). 헤더 검증은 `caller()` 가 한다(다른 라우터와 같다)."""
    with read_only() as con:
        rows = con.execute(
            "SELECT site_id, name, is_mock, width, height FROM sites ORDER BY site_id"
        ).fetchall()
    return {"items": [_site_dict(r) for r in rows]}


@router.get("/{site_id}/floorplan")
def floorplan(site_id: str, c: Caller = Depends(caller)) -> dict:
    """평면도 재료 — 사업장 · 구역 사각형 · 설비 점.

    `asset_name` 은 호스트 자산(`assets.name`)이 있을 때만 채운다. HV600 2행·분전반처럼
    `asset_id` 가 NULL 이면 **null** 이다 — 지어낸 이름으로 메우지 않는다(D68·D87).
    위치가 없는 설비는 응답에 넣지 않는다(좌표를 지어내지 않는다) — 시드·마이그레이션은
    12대 전부에 위치를 준다(`spikes/site_floorplan_contract.py` 가 검사).
    """
    with read_only() as con:
        site = con.execute(
            "SELECT site_id, name, is_mock, width, height FROM sites WHERE site_id = ?",
            (site_id,),
        ).fetchone()
        if site is None:
            raise HTTPException(404, f"사업장을 찾을 수 없습니다: {site_id}")
        zones = con.execute(
            "SELECT zone_id, name, kind, x, y, w, h FROM zones WHERE site_id = ?"
            " ORDER BY y, x, zone_id",  # 읽는 순서(위→아래, 왼→오른)
            (site_id,),
        ).fetchall()
        equipment = con.execute(
            "SELECT l.equipment_id, e.model, l.zone_id, l.x, l.y, e.location, e.asset_id,"
            " a.name AS asset_name"
            " FROM equipment_locations l"
            " JOIN zones z ON z.zone_id = l.zone_id"
            " JOIN equipment e ON e.equipment_id = l.equipment_id"
            " LEFT JOIN assets a ON a.asset_id = e.asset_id"
            " WHERE z.site_id = ?"
            " ORDER BY l.equipment_id",
            (site_id,),
        ).fetchall()
    return {
        "site": _site_dict(site),
        "zones": [
            {k: z[k] for k in ("zone_id", "name", "kind", "x", "y", "w", "h")} for z in zones
        ],
        "equipment": [
            {
                k: e[k]
                for k in (
                    "equipment_id", "model", "zone_id", "x", "y", "location", "asset_id",
                    "asset_name",
                )
            }
            for e in equipment
        ],
    }
