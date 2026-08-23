# -*- coding: utf-8 -*-
"""정수 금액 → 한글 금액 표기 (D73 공유 계층 — backend·mcp_server 양쪽에서 쓸 수 있다).

결재 문서(발주요청서·자금집행요청서 등)의 "일금 ○○○원整" 표기에 쓴다.
소수점·음수는 이 문서들의 도메인에 없으므로 다루지 않는다 — 들어오면 예외를 던진다
(D9 는 도구 실패에 대한 규칙이지 이 순수 함수의 계약은 아니다. 호출부가 try/except 로 감싼다).
"""

from __future__ import annotations

_DIGITS = "일이삼사오육칠팔구"
_SMALL_UNITS = ("", "십", "백", "천")
_BIG_UNITS = ("", "만", "억", "조", "경")


def _four_digit_group(n: int) -> str:
    """0~9999 를 한글로. 0이면 빈 문자열(자릿수 단위와 결합할 때 생략된다)."""
    if n == 0:
        return ""
    out = []
    for i, unit in enumerate(_SMALL_UNITS):
        place = (n // (10**i)) % 10
        if place == 0:
            continue
        # '일십'이 아니라 '십' — 단, 단독 자리(예: 15 → '십오')에서만 앞자리 '일' 생략
        digit = "" if (place == 1 and i > 0) else _DIGITS[place - 1]
        out.append(digit + unit)
    return "".join(reversed(out))


def amount_to_korean(amount: int) -> str:
    """248400 → '이십사만팔천사백원'. 0 → '영원'."""
    if not isinstance(amount, int) or isinstance(amount, bool):
        raise TypeError(f"amount_to_korean expects int, got {type(amount).__name__}")
    if amount < 0:
        raise ValueError("amount_to_korean does not support negative amounts")
    if amount == 0:
        return "영원"

    groups = []
    n = amount
    while n > 0:
        groups.append(n % 10000)
        n //= 10000

    parts = []
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if g == 0:
            continue
        parts.append(_four_digit_group(g) + _BIG_UNITS[i])
    return "".join(parts) + "원"
