# -*- coding: utf-8 -*-
"""요청 컨텍스트 — 역할·신원 헤더 (docs/06_REPO_API.md §2).

목업 수준이지만 **권한 검사 로직은 실제로 구현한다.** "정비사가 approve 를 호출하면 403"
은 평가 지표(권한 위반 차단 100%)라 동작하는 코드여야 한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import Header, HTTPException

Role = Literal["technician", "manager"]
VALID_ROLES = ("technician", "manager")


@dataclass(frozen=True)
class Caller:
    role: Role
    user_id: str


def caller(
    x_role: str = Header(default="technician", alias="X-Role"),
    # ASCII 사용자 ID. 한글 표시명은 헤더에 실을 수 없다 (D36)
    x_user: str = Header(default="tech-01", alias="X-User"),
) -> Caller:
    if x_role not in VALID_ROLES:
        raise HTTPException(400, f"X-Role 은 technician|manager 이어야 합니다: {x_role!r}")
    if not x_user.isascii():
        raise HTTPException(400, "X-User 는 ASCII 사용자 ID 여야 합니다 (D36)")
    return Caller(role=x_role, user_id=x_user)  # type: ignore[arg-type]


def require(c: Caller, role: Role, action: str) -> None:
    """역할이 다르면 403. 상태 전이의 주체를 UI 가 아니라 서버가 강제한다."""
    if c.role != role:
        raise HTTPException(
            403,
            f"{action} 은(는) {role} 만 수행할 수 있습니다 (요청자 역할: {c.role})",
        )
