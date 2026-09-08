# -*- coding: utf-8 -*-
"""MaintQ A2A 나가는 호출의 차단기(circuit breaker) — P35.

목적은 **상대 에이전트의 장애가 MaintQ 의 진단·발주까지 끌고 내려가지 않게** 하는 것이다
(`docs/07_BACKLOG.md` P35). FinAllQ 가 죽어 있으면 발주 승인마다 10초 타임아웃을 무는데,
예외를 삼켜도(`routers/po.py`) **기다리는 시간 자체는 사라지지 않는다** —
*실패를 삼키는 것*과 *빨리 실패하는 것*은 다르다.

## 세 가지 경계

1. **파트너 단위로 연다.** finallq 가 죽어도 insuq 호출은 계속돼야 한다.
   스킬 단위로 쪼개면 같은 서버가 죽었는데 스킬마다 따로 임계치를 채워야 해 늦게 열린다.

2. **«도달 불가»만 차단기를 연다.** 타임아웃·연결 실패·502/503/504 만 실패로 센다.
   400·422 같은 **비즈니스/계약 실패는 열지 않는다** — 그건 상대가 살아 있다는 증거이고
   (우리 payload 가 틀렸거나 그쪽 검증에 걸린 것), 그걸로 차단하면 **한 스킬의 계약 오류가
   그 파트너의 멀쩡한 다른 스킬까지 막는다.** 실제로 assess-loan 계약 드리프트(2026-08-24)
   때 400 이 반복해서 났는데, 그때 request-withdrawal 은 정상 동작해야 했다.

3. **상태는 프로세스 안에만 둔다.** DB 에 쓰지 않는다 — 차단기는 *지금 이 프로세스가 상대를
   어떻게 보고 있는가*이지 업무 사실이 아니다. D10 쓰기 가드와도 무관해진다.

## 상태 전이

    CLOSED ──(도달 불가 연속 threshold회)──> OPEN
      ^                                        │
      │                                   (cooldown 경과)
      │                                        v
      └────────(시험 호출 성공)──────────── HALF_OPEN ──(시험 호출 실패)──> OPEN

HALF_OPEN 에서는 **시험 호출을 한 건만** 통과시킨다. 여러 건을 흘려보내면 아직 죽어 있는
상대에게 몰려가 복구를 방해한다.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"

#: 연속 «도달 불가» 몇 번에 열 것인가.
DEFAULT_THRESHOLD = 3
#: OPEN 이 유지되는 시간(초). 지나면 시험 호출 한 건을 허용한다.
DEFAULT_COOLDOWN = 30.0


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


class CircuitOpen(Exception):
    """차단기가 열려 있어 호출을 시도조차 하지 않았다.

    `retry_after` 는 다음 시험 호출까지 남은 초다 — 호출부가 `Retry-After` 로 그대로 쓴다.
    """

    def __init__(self, partner: str, retry_after: float, failure_count: int):
        super().__init__(
            f"A2A circuit for partner '{partner}' is open "
            f"(연속 실패 {failure_count}회, {retry_after:.1f}s 후 재시도)"
        )
        self.partner = partner
        self.retry_after = retry_after
        self.failure_count = failure_count


@dataclass
class _Breaker:
    """파트너 하나의 차단기 상태. 직접 만들지 말고 `registry()` 를 통해 얻는다."""

    partner: str
    threshold: int = DEFAULT_THRESHOLD
    cooldown: float = DEFAULT_COOLDOWN
    state: str = CLOSED
    failure_count: int = 0
    opened_at: float = 0.0
    #: HALF_OPEN 에서 시험 호출이 이미 나갔는가 (동시 진입 방지)
    probe_in_flight: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class CircuitRegistry:
    """파트너별 차단기 보관소.

    ⚠ 테스트는 `now` 를 주입해 시간을 통제한다 — `time.sleep` 으로 재현하면 느리고 흔들린다.
    """

    def __init__(self, now=time.monotonic, threshold: int | None = None, cooldown: float | None = None):
        self._now = now
        self._threshold = threshold if threshold is not None else _env_int(
            "MAINTQ_A2A_BREAKER_THRESHOLD", DEFAULT_THRESHOLD
        )
        self._cooldown = cooldown if cooldown is not None else _env_float(
            "MAINTQ_A2A_BREAKER_COOLDOWN", DEFAULT_COOLDOWN
        )
        self._breakers: dict[str, _Breaker] = {}
        self._registry_lock = threading.Lock()

    def _get(self, partner: str) -> _Breaker:
        with self._registry_lock:
            b = self._breakers.get(partner)
            if b is None:
                b = _Breaker(partner=partner, threshold=self._threshold, cooldown=self._cooldown)
                self._breakers[partner] = b
            return b

    def before_call(self, partner: str) -> None:
        """호출 직전 관문. 열려 있으면 `CircuitOpen` 을 던진다(네트워크를 타지 않는다)."""
        b = self._get(partner)
        with b._lock:
            if b.state == CLOSED:
                return

            elapsed = self._now() - b.opened_at
            remaining = b.cooldown - elapsed

            if b.state == OPEN:
                if remaining > 0:
                    raise CircuitOpen(partner, retry_after=remaining, failure_count=b.failure_count)
                # 쿨다운이 지났다 — 시험 호출 한 건만 통과시킨다
                b.state = HALF_OPEN
                b.probe_in_flight = True
                return

            # HALF_OPEN: 시험 호출이 이미 나가 있으면 나머지는 계속 막는다.
            # 여기서 흘려보내면 아직 죽어 있을 수 있는 상대에게 몰려간다.
            if b.probe_in_flight:
                raise CircuitOpen(partner, retry_after=max(remaining, 0.0), failure_count=b.failure_count)
            b.probe_in_flight = True

    def on_reachable(self, partner: str) -> None:
        """상대에 **도달**했다 — 완전히 닫는다.

        비즈니스 실패(400·422)도 여기로 온다. 응답을 돌려줬다는 것 자체가 살아 있다는 증거다.
        """
        b = self._get(partner)
        with b._lock:
            b.state = CLOSED
            b.failure_count = 0
            b.opened_at = 0.0
            b.probe_in_flight = False

    def on_unreachable(self, partner: str) -> None:
        """«도달 불가»를 셌다. 임계치를 채우면 연다.

        ⛔ 비즈니스 실패(400·422 등)로는 이 메서드를 부르지 않는다 — 모듈 docstring 경계 2.
        """
        b = self._get(partner)
        with b._lock:
            b.failure_count += 1
            was_probe = b.state == HALF_OPEN
            b.probe_in_flight = False
            # HALF_OPEN 의 시험 호출이 실패하면 임계치와 무관하게 즉시 다시 연다 —
            # 이미 threshold 만큼 실패해서 열렸던 상대다.
            if was_probe or b.failure_count >= b.threshold:
                b.state = OPEN
                b.opened_at = self._now()

    def snapshot(self, partner: str) -> dict:
        """관측용 상태 사본 (로그·디버깅). 상태를 바꾸지 않는다."""
        b = self._get(partner)
        with b._lock:
            return {
                "partner": b.partner,
                "state": b.state,
                "failure_count": b.failure_count,
                "threshold": b.threshold,
                "cooldown": b.cooldown,
            }

    def reset(self, partner: str | None = None) -> None:
        """테스트·운영 수동 복구용. partner 가 없으면 전부 지운다."""
        with self._registry_lock:
            if partner is None:
                self._breakers.clear()
            else:
                self._breakers.pop(partner, None)


#: 프로세스 전역 레지스트리. `call_skill` 이 이것을 쓴다.
_REGISTRY = CircuitRegistry()


def registry() -> CircuitRegistry:
    return _REGISTRY
