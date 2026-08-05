# -*- coding: utf-8 -*-
"""get_error_history — 에러 이력 조회 (확정 기능 ①, docs/04_MCP_TOOLS.md §3).

`repeated=true` 면 에이전트는 근본원인 모드로 전환해야 한다 (S3).
이 테이블에 쓰는 경로는 백엔드의 명시적 기록 API 하나뿐이다 (D29) — 도구는 읽기만.
"""

from __future__ import annotations

from ..db import read_only

# 계약에 고정된 상수 (docs/04_MCP_TOOLS.md §3)
REPEAT_WINDOW_DAYS = 30
REPEAT_THRESHOLD = 3

DESCRIPTION = (
    "설비·라인·에러코드 기준으로 과거 발생 이력을 조회한다. 같은 에러가 반복되는지 "
    f"판단하는 게 목적이며, {REPEAT_WINDOW_DAYS}일 내 {REPEAT_THRESHOLD}회 이상이면 "
    "repeated=true 로 반환한다. repeated면 단순 조치 대신 근본원인 점검으로 전환할 것."
)


def _as_int(value: object) -> int | None:
    """정수로 해석되면 int, 아니면 None. **추정하지 않는다.**

    LLM 은 `line_id` 에 라인 **이름**을 넣곤 한다 ("2번 가공라인", "L1"). 시그니처를
    `int` 로 좁혀 두면 MCP 계층의 스키마 검증이 예외를 던져 도구가 status 로 실패를
    돌려주지 못하고(D9 위반) 원문 예외가 그대로 새어 나간다 — 에이전트에겐 조치할 수
    없는 메시지이고 턴당 도구 호출 상한(8회)만 축낸다. 그래서 넓게 받아 여기서 판정한다.
    "2번 가공라인" 에서 2 를 뽑아내는 식의 추정은 하지 않는다 — 라인 번호를 잘못 짚으면
    남의 설비 이력으로 `repeated` 를 판정하게 된다.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def get_error_history(
    equipment_id: str | None = None,
    line_id: int | str | None = None,
    code: str | None = None,
    days: int | str = REPEAT_WINDOW_DAYS,
) -> dict:
    if line_id is not None:
        parsed = _as_int(line_id)
        if parsed is None:
            return {
                "status": "error",
                "reason": "invalid_line_id",
                "message": (
                    f"line_id 는 라인 번호(정수)입니다: {line_id!r}. 라인 이름을 넣지 말고, "
                    "설비를 알면 equipment_id 로 조회하세요."
                ),
            }
        line_id = parsed

    parsed_days = _as_int(days)
    if parsed_days is None or parsed_days <= 0:
        return {
            "status": "error",
            "reason": "invalid_days",
            "message": f"days 는 양의 정수(조회 기간)입니다: {days!r}",
        }
    days = parsed_days

    if equipment_id is None and line_id is None and code is None:
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": "equipment_id · line_id · code 중 최소 하나는 필요합니다",
        }

    # line_id 는 error_history 에 없는 컬럼 — equipment 조인으로 해석한다
    sql = [
        "SELECT h.equipment_id, h.code, h.occurred_at, h.action_taken, h.part_replaced",
        "FROM error_history h JOIN equipment e ON e.equipment_id = h.equipment_id",
        "WHERE h.occurred_at >= datetime('now', ?)",
    ]
    args: list[object] = [f"-{days} day"]
    if equipment_id:
        sql.append("AND h.equipment_id = ?")
        args.append(equipment_id)
    if line_id is not None:
        sql.append("AND e.line_id = ?")
        args.append(line_id)
    if code:
        # 저장은 대문자 canonical, 사용자 입력은 혼재 (D25) → case-insensitive 매칭
        sql.append("AND upper(h.code) = upper(?)")
        args.append(code)
    sql.append("ORDER BY h.occurred_at DESC")

    try:
        with read_only() as con:
            rows = con.execute(" ".join(sql), args).fetchall()
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "reason": "db_error", "message": str(e)}

    events = [
        {
            "date": r["occurred_at"][:10],
            "code": r["code"],
            "action_taken": r["action_taken"],
            "part_replaced": r["part_replaced"],
        }
        for r in rows
    ]
    return {
        "status": "ok",
        "count": len(events),
        "repeated": len(events) >= REPEAT_THRESHOLD,
        "events": events,
    }
