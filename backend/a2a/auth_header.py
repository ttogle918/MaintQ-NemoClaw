# -*- coding: utf-8 -*-
"""MaintQ A2A 인증 헤더 생성 층 (D120).

credentials.load(partner)로 얻은 값을 Authorization + X-A2A-Partner-Id 헤더로 만든다.

InsuQ 의 실 인증 필터(`ServiceTokenFilter.java`)가 검증하는 그대로다 —
`Authorization: Bearer <token>` 한 값 비교 + `X-A2A-Partner-Id` 자기신고 헤더로
actor(partner_grant)를 식별한다. FinAllQ→InsuQ 2차 홉(`insuq_client.py`)이 이미
이 스킴으로 실 E2E 성공을 냈다 — 여기서도 같은 스킴을 쓴다(더는 "어댑터가 검사하지
않는 M1 목업"이 아니다, D93 시절 문서와 달리 InsuQ 쪽은 실제로 검사한다).
FinAllQ 는 아직 인바운드 인증 자체가 없어(2026-08-24 실측) 이 헤더가 지금 당장은
무해하게 무시되지만, 나중에 검사가 붙어도 호출부(client.py)는 바뀌지 않는다.
"""

from __future__ import annotations

from backend.a2a import credentials


def build_auth_header(partner: str) -> dict[str, str]:
    """credentials.load(partner)로 얻은 값을 인증 헤더로 만든다.

    cred.usable이 아니면(not_configured, unknown_partner) 빈 dict {}를 반환한다.
    """
    cred = credentials.load(partner)
    if not cred.usable:
        return {}
    return {
        "Authorization": f"Bearer {cred.token}",
        "X-A2A-Partner-Id": credentials.SELF_PARTNER_ID,
    }
