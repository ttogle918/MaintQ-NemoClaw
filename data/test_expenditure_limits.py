# -*- coding: utf-8 -*-
"""
자금집행 내부통제 판정 로직(`data/expenditure_limits.py`) 테스트.

실행:  uv run --with pytest python -m pytest data/test_expenditure_limits.py -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from expenditure_limits import (  # noqa: E402
    BUDGET_LIMIT,
    DAILY_LIMIT,
    FDS_WARNING_RATIO,
    budget_check,
    daily_limit_check,
    fds_verdict,
    sod_check,
)


# ---------------------------------------------------------------------------
# budget_check
# ---------------------------------------------------------------------------


def test_budget_check_exactly_at_limit_is_ok():
    ok, msg = budget_check(BUDGET_LIMIT)
    assert ok is True
    assert "이내" in msg
    assert f"{BUDGET_LIMIT:,}원" in msg


def test_budget_check_one_won_over_limit_is_not_ok():
    ok, msg = budget_check(BUDGET_LIMIT + 1)
    assert ok is False
    assert "초과" in msg


def test_budget_check_well_under_limit_is_ok():
    ok, msg = budget_check(1_000_000)
    assert ok is True
    assert "이내" in msg


def test_budget_check_zero_is_ok():
    ok, msg = budget_check(0)
    assert ok is True


# ---------------------------------------------------------------------------
# daily_limit_check
# ---------------------------------------------------------------------------


def test_daily_limit_check_exactly_at_limit_is_ok():
    ok, msg = daily_limit_check(amount=DAILY_LIMIT, today_total_before=0)
    assert ok is True
    assert "이내" in msg
    assert f"{DAILY_LIMIT:,}원" in msg


def test_daily_limit_check_one_won_over_limit_is_not_ok():
    ok, msg = daily_limit_check(amount=DAILY_LIMIT + 1, today_total_before=0)
    assert ok is False
    assert "초과" in msg


def test_daily_limit_check_cumulative_pushes_over_limit():
    # 이미 오늘 14,999,999원을 썼고 2원을 추가하면 15,000,001원으로 한도 초과.
    ok, msg = daily_limit_check(amount=2, today_total_before=DAILY_LIMIT - 1)
    assert ok is False
    assert "초과" in msg


def test_daily_limit_check_cumulative_within_limit():
    ok, msg = daily_limit_check(amount=1, today_total_before=DAILY_LIMIT - 1)
    assert ok is True
    assert "이내" in msg


# ---------------------------------------------------------------------------
# fds_verdict
# ---------------------------------------------------------------------------


def test_fds_verdict_exactly_half_ratio_is_normal():
    amount = int(BUDGET_LIMIT * FDS_WARNING_RATIO)
    verdict, msg = fds_verdict(amount)
    assert verdict == "정상"
    assert "50%" in msg


def test_fds_verdict_over_half_ratio_is_warning():
    amount = int(BUDGET_LIMIT * FDS_WARNING_RATIO) + 1
    verdict, msg = fds_verdict(amount)
    assert verdict == "주의"


def test_fds_verdict_low_ratio_is_normal():
    verdict, msg = fds_verdict(0)
    assert verdict == "정상"


def test_fds_verdict_full_budget_is_warning():
    verdict, msg = fds_verdict(BUDGET_LIMIT)
    assert verdict == "주의"
    assert "100%" in msg


# ---------------------------------------------------------------------------
# sod_check
# ---------------------------------------------------------------------------


def test_sod_check_three_distinct_people_is_ok():
    ok, msg = sod_check(
        requested_by="user_a", decided_by="user_b", finance_decided_by="user_c"
    )
    assert ok is True
    assert "전원 상이" in msg


def test_sod_check_requester_equals_decider_is_not_ok():
    ok, msg = sod_check(
        requested_by="user_a", decided_by="user_a", finance_decided_by="user_c"
    )
    assert ok is False
    assert "중복 있음" in msg


def test_sod_check_decider_equals_finance_is_not_ok():
    ok, msg = sod_check(
        requested_by="user_a", decided_by="user_b", finance_decided_by="user_b"
    )
    assert ok is False
    assert "중복 있음" in msg


def test_sod_check_all_same_person_is_not_ok():
    ok, msg = sod_check(
        requested_by="user_a", decided_by="user_a", finance_decided_by="user_a"
    )
    assert ok is False
    assert "중복 있음" in msg
