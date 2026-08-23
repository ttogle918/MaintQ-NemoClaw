# -*- coding: utf-8 -*-
"""A2A 호출 감사 이력 조회 (D114).

`traces` 에서 `tool LIKE 'a2a:%'` 인 행만 골라 `request_chain_id` 로 tool_call/tool_result
쌍을 묶어 반환한다. 기존 `read_trace`(D76-2 ⓑ, `tool_payload` 의도적 미포함)는 그대로 두고,
이 모듈만 A2A 전용으로 `tool_payload` 원문을 연다 — 대상이 `tool LIKE 'a2a:%'` 로 좁혀져 있어
일반 대화 trace 전체를 노출하지는 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.db import connect


def list_a2a_history(
    *,
    skill: str | None = None,
    po_id: str | None = None,
    building_id: str | None = None,
    chain_id: str | None = None,
    limit: int = 50,
    db_path: Path | None = None,
) -> dict:
    """A2A 호출 감사 이력. `tool LIKE 'a2a:%'` 인 traces 행을 request_chain_id 로 묶어 반환한다.

    반환: {"count": int, "items": [
      {"request_chain_id": str, "skill": str, "session_id": str,
       "status": str | None, "request": dict | None, "response": dict | None, "ts": str},
      ...
    ]}
    `status` 는 record_a2a_trace 가 기록한 값(ok|timeout|unavailable|error) — tool_result 행이
    아직 없으면 None. `response` 는 tool_result.tool_payload 원문, 파싱 실패 시 {"_parse_error": true}.
    정렬: ts desc. limit 은 필터링 후 적용.
    """
    if limit <= 0:
        return {"count": 0, "items": []}

    with connect(db_path) as con:
        rows = con.execute(
            "SELECT session_id, event_type, tool, payload, tool_payload,"
            " request_chain_id, ts FROM traces"
            " WHERE tool LIKE 'a2a:%' AND request_chain_id IS NOT NULL"
            " ORDER BY id ASC"
        ).fetchall()

    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for r in rows:
        cid = r["request_chain_id"]
        if cid not in groups:
            groups[cid] = {
                "request_chain_id": cid,
                "skill": (r["tool"] or "").removeprefix("a2a:"),
                "session_id": r["session_id"],
                "status": None,
                "request": None,
                "response": None,
                "ts": r["ts"],
            }
            order.append(cid)

        group = groups[cid]
        group["ts"] = r["ts"]  # tool_result 시각이 최종 시각 (ts desc 정렬 기준)

        try:
            payload = json.loads(r["payload"]) if r["payload"] else None
        except (TypeError, ValueError):
            payload = None

        if r["event_type"] == "tool_call":
            if isinstance(payload, dict) and isinstance(payload.get("input"), dict):
                group["request"] = payload["input"]
        elif r["event_type"] == "tool_result":
            if isinstance(payload, dict):
                group["status"] = payload.get("status")

            raw_response = r["tool_payload"]
            if raw_response is not None:
                try:
                    group["response"] = json.loads(raw_response)
                except (TypeError, ValueError):
                    group["response"] = {"_parse_error": True}

    items = [groups[cid] for cid in order]

    if skill is not None:
        items = [it for it in items if it["skill"] == skill]
    if po_id is not None:
        items = [
            it for it in items if isinstance(it["request"], dict) and it["request"].get("po_id") == po_id
        ]
    if building_id is not None:
        items = [
            it
            for it in items
            if isinstance(it["request"], dict) and it["request"].get("collateral_building_id") == building_id
        ]
    if chain_id is not None:
        items = [it for it in items if it["request_chain_id"] == chain_id]

    items.sort(key=lambda it: it["ts"] or "", reverse=True)
    items = items[:limit]

    return {"count": len(items), "items": items}
