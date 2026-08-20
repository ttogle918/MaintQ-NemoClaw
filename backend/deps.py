# -*- coding: utf-8 -*-
"""요청 컨텍스트 — 역할·신원 헤더 (docs/06_REPO_API.md §2).

목업 수준이지만 **권한 검사 로직은 실제로 구현한다.** "정비사가 approve 를 호출하면 403"
은 평가 지표(권한 위반 차단 100%)라 동작하는 코드여야 한다.

🔴 **`department`(소속)는 `role`(권한)과 직교다 (D108, P41 ③).** `require()` 는 `role` 만 본다 —
재무부 소속이어도 role 이 없으면 승인할 수 없다. 그리고 **`department` 는 헤더로 받지 않는다** —
`X-Dept` 같은 헤더를 두면 클라이언트가 자기 부서를 참칭할 수 있다. 그래서 `role`(헤더 시뮬레이션)과
달리 `department` 는 서버가 `users` 테이블에서 `user_id` 로 조회해 주입한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import Header, HTTPException

from backend.db import connect

Role = Literal["technician", "manager"]
VALID_ROLES = ("technician", "manager")


@dataclass(frozen=True)
class Caller:
    role: Role
    user_id: str
    department: str | None = None


def _department_of(user_id: str) -> str | None:
    """`users.department` 조회. 헤더가 아니라 DB 가 유일한 원천이다 (D108).

    미등록 `user_id` 는 400 이 아니라 `None`(미배정)으로 흘려보낸다 — `department` 는
    권한이 아니라 소속 표시일 뿐이라, 모르는 사용자를 거부할 이유가 없다. 기존 `role`
    검사(400)와 태도가 다른 것은 의도적이다: `role` 은 요청을 검증하는 값이고
    `department` 는 조회해서 붙이는 부가 정보다.
    """
    with connect() as con:
        row = con.execute(
            "SELECT department FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row["department"] if row else None


def caller(
    x_role: str = Header(default="technician", alias="X-Role"),
    # ASCII 사용자 ID. 한글 표시명은 헤더에 실을 수 없다 (D36)
    x_user: str = Header(default="tech-01", alias="X-User"),
) -> Caller:
    if x_role not in VALID_ROLES:
        raise HTTPException(400, f"X-Role 은 technician|manager 이어야 합니다: {x_role!r}")
    if not x_user.isascii():
        raise HTTPException(400, "X-User 는 ASCII 사용자 ID 여야 합니다 (D36)")
    return Caller(role=x_role, user_id=x_user, department=_department_of(x_user))  # type: ignore[arg-type]


def require(c: Caller, role: Role, action: str) -> None:
    """역할이 다르면 403. 상태 전이의 주체를 UI 가 아니라 서버가 강제한다.

    ⛔ `c.department` 를 보지 않는다 — 그 순간 "부서는 권한이 아니다"(D108)가 깨진다.
    """
    if c.role != role:
        raise HTTPException(
            403,
            f"{action} 은(는) {role} 만 수행할 수 있습니다 (요청자 역할: {c.role})",
        )
