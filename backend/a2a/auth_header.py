# -*- coding: utf-8 -*-
"""MaintQ A2A Authorization 헤더 생성 층.

credentials.load(partner)로 얻은 값을 Authorization 헤더로 만든다.

M1 목업: 실제 토큰 교환 엔드포인트가 아직 없어 client_id:client_secret을
HTTP Basic으로 그대로 실어 보낸다. 어댑터가 검사하지 않으므로 지금은
효과가 없지만, 나중에 어댑터 쪽에 토큰 교환이 붙으면 이 함수 내부만
바뀐다 — 호출부(client.py)는 "헤더 dict를 받아 붙인다"는 계약만 안다.
"""

from __future__ import annotations

import base64

from backend.a2a import credentials


def build_auth_header(partner: str) -> dict[str, str]:
    """credentials.load(partner)로 얻은 값을 Authorization 헤더로 만든다.

    cred.usable이 아니면 (not_configured, incomplete 등) 빈 dict {}를 반환한다.
    """
    cred = credentials.load(partner)
    if not cred.usable:
        return {}
    token = base64.b64encode(f"{cred.client_id}:{cred.client_secret}".encode("utf-8")).decode("utf-8")
    return {"Authorization": f"Basic {token}"}
