# -*- coding: utf-8 -*-
"""backend/a2a/circuit.py 테스트 (P35 차단기).

시간은 `FakeClock` 으로 주입한다 — `time.sleep` 으로 쿨다운을 재현하면 느리고 흔들린다.
네트워크는 타지 않는다(순수 상태 기계).
"""

from __future__ import annotations

import pytest

from backend.a2a.circuit import (
    CLOSED,
    HALF_OPEN,
    OPEN,
    CircuitOpen,
    CircuitRegistry,
)


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def reg(clock: FakeClock) -> CircuitRegistry:
    return CircuitRegistry(now=clock, threshold=3, cooldown=30.0)


def _trip(reg: CircuitRegistry, partner: str = "finallq", times: int = 3) -> None:
    """차단기를 여는 데 필요한 만큼 «도달 불가»를 먹인다."""
    for _ in range(times):
        reg.before_call(partner)
        reg.on_unreachable(partner)


# --- ① 닫힌 상태: 통과시킨다 -------------------------------------------------


def test_closed_by_default_passes_through(reg: CircuitRegistry) -> None:
    reg.before_call("finallq")  # 예외 없음
    assert reg.snapshot("finallq")["state"] == CLOSED


def test_success_keeps_it_closed(reg: CircuitRegistry) -> None:
    for _ in range(10):
        reg.before_call("finallq")
        reg.on_reachable("finallq")
    assert reg.snapshot("finallq")["state"] == CLOSED
    assert reg.snapshot("finallq")["failure_count"] == 0


# --- ② 임계치까지는 열지 않는다 ----------------------------------------------


def test_below_threshold_stays_closed(reg: CircuitRegistry) -> None:
    _trip(reg, times=2)  # threshold=3 이므로 아직
    assert reg.snapshot("finallq")["state"] == CLOSED
    reg.before_call("finallq")  # 여전히 통과


def test_opens_exactly_at_threshold(reg: CircuitRegistry) -> None:
    _trip(reg, times=3)
    assert reg.snapshot("finallq")["state"] == OPEN
    with pytest.raises(CircuitOpen):
        reg.before_call("finallq")


def test_success_resets_the_counter(reg: CircuitRegistry) -> None:
    """연속이 끊기면 처음부터 다시 센다 — 누적 실패가 아니라 연속 실패다."""
    _trip(reg, times=2)
    reg.before_call("finallq")
    reg.on_reachable("finallq")
    _trip(reg, times=2)
    assert reg.snapshot("finallq")["state"] == CLOSED


# --- ③ 열린 상태: 네트워크를 타지 않는다 -------------------------------------


def test_open_raises_with_retry_after(reg: CircuitRegistry, clock: FakeClock) -> None:
    _trip(reg)
    clock.advance(10.0)
    with pytest.raises(CircuitOpen) as exc:
        reg.before_call("finallq")
    assert exc.value.partner == "finallq"
    assert exc.value.failure_count == 3
    assert exc.value.retry_after == pytest.approx(20.0)  # 30 - 10


def test_open_does_not_count_further_failures(reg: CircuitRegistry) -> None:
    """열린 뒤에는 호출 자체가 없으므로 실패도 늘지 않는다."""
    _trip(reg)
    for _ in range(5):
        with pytest.raises(CircuitOpen):
            reg.before_call("finallq")
    assert reg.snapshot("finallq")["failure_count"] == 3


# --- ④ 파트너 격리 — 이 차단기의 존재 이유 ------------------------------------


def test_one_partner_outage_does_not_block_the_other(reg: CircuitRegistry) -> None:
    """finallq 가 죽어도 insuq 약관 조회는 계속돼야 한다."""
    _trip(reg, "finallq")
    with pytest.raises(CircuitOpen):
        reg.before_call("finallq")
    reg.before_call("insuq")  # 예외 없음
    assert reg.snapshot("insuq")["state"] == CLOSED


# --- ⑤ 쿨다운 → 시험 호출(HALF_OPEN) ------------------------------------------


def test_cooldown_elapsed_allows_one_probe(reg: CircuitRegistry, clock: FakeClock) -> None:
    _trip(reg)
    clock.advance(30.0)
    reg.before_call("finallq")  # 시험 호출 통과
    assert reg.snapshot("finallq")["state"] == HALF_OPEN


def test_half_open_admits_only_one_probe(reg: CircuitRegistry, clock: FakeClock) -> None:
    """두 번째 호출은 막는다 — 아직 죽어 있을 상대에게 몰려가면 복구를 방해한다."""
    _trip(reg)
    clock.advance(31.0)
    reg.before_call("finallq")
    with pytest.raises(CircuitOpen):
        reg.before_call("finallq")


def test_probe_success_closes_the_circuit(reg: CircuitRegistry, clock: FakeClock) -> None:
    _trip(reg)
    clock.advance(31.0)
    reg.before_call("finallq")
    reg.on_reachable("finallq")
    assert reg.snapshot("finallq")["state"] == CLOSED
    assert reg.snapshot("finallq")["failure_count"] == 0
    reg.before_call("finallq")  # 다시 정상 통과


def test_probe_failure_reopens_immediately(reg: CircuitRegistry, clock: FakeClock) -> None:
    """시험 호출이 실패하면 임계치를 다시 채우지 않고 곧바로 다시 연다."""
    _trip(reg)
    clock.advance(31.0)
    reg.before_call("finallq")
    reg.on_unreachable("finallq")
    assert reg.snapshot("finallq")["state"] == OPEN
    with pytest.raises(CircuitOpen):
        reg.before_call("finallq")


def test_probe_failure_restarts_the_cooldown(reg: CircuitRegistry, clock: FakeClock) -> None:
    _trip(reg)
    clock.advance(31.0)
    reg.before_call("finallq")
    reg.on_unreachable("finallq")  # 여기서 쿨다운이 다시 시작된다
    clock.advance(29.0)
    with pytest.raises(CircuitOpen):
        reg.before_call("finallq")
    clock.advance(2.0)
    reg.before_call("finallq")  # 31초 지났으니 다시 시험 호출


# --- ⑥ 리셋 --------------------------------------------------------------------


def test_reset_one_partner(reg: CircuitRegistry) -> None:
    _trip(reg, "finallq")
    _trip(reg, "insuq")
    reg.reset("finallq")
    reg.before_call("finallq")
    with pytest.raises(CircuitOpen):
        reg.before_call("insuq")


def test_reset_all(reg: CircuitRegistry) -> None:
    _trip(reg, "finallq")
    _trip(reg, "insuq")
    reg.reset()
    reg.before_call("finallq")
    reg.before_call("insuq")


# --- ⑦ 설정 --------------------------------------------------------------------


def test_threshold_is_configurable(clock: FakeClock) -> None:
    reg = CircuitRegistry(now=clock, threshold=1, cooldown=5.0)
    reg.before_call("finallq")
    reg.on_unreachable("finallq")
    assert reg.snapshot("finallq")["state"] == OPEN


def test_snapshot_does_not_mutate_state(reg: CircuitRegistry, clock: FakeClock) -> None:
    """관측이 상태를 바꾸면 로그를 켜는 것만으로 동작이 달라진다."""
    _trip(reg)
    clock.advance(31.0)
    before = reg.snapshot("finallq")
    after = reg.snapshot("finallq")
    assert before == after
    assert before["state"] == OPEN  # snapshot 이 HALF_OPEN 으로 넘기지 않는다
