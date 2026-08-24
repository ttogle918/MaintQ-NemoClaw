# -*- coding: utf-8 -*-
"""자금집행 내부통제 판정 — 전부 목업 상수/규칙이다. 실제 재무 정책이 아니다."""

BUDGET_LIMIT = 5_000_000       # 건당 예산 한도 (원) — 목업 상수
DAILY_LIMIT = 15_000_000       # 부서 1일 누적 한도 (원) — 목업 상수
FDS_WARNING_RATIO = 0.5        # 예산한도 대비 이 비율 초과 시 "주의" — 목업 규칙


def budget_check(amount: int) -> tuple[bool, str]:
    ok = amount <= BUDGET_LIMIT
    return ok, f"{amount:,}원 / 한도 {BUDGET_LIMIT:,}원 ({'이내' if ok else '초과'})"


def daily_limit_check(amount: int, today_total_before: int) -> tuple[bool, str]:
    total = today_total_before + amount
    ok = total <= DAILY_LIMIT
    return ok, f"금일 누적 {total:,}원 / 한도 {DAILY_LIMIT:,}원 ({'이내' if ok else '초과'})"


def fds_verdict(amount: int) -> tuple[str, str]:
    ratio = amount / BUDGET_LIMIT
    verdict = "주의" if ratio > FDS_WARNING_RATIO else "정상"
    return verdict, f"예산한도 대비 {ratio:.0%} — 목업 규칙(FDS_WARNING_RATIO={FDS_WARNING_RATIO})"


def sod_check(requested_by: str, decided_by: str, finance_decided_by: str) -> tuple[bool, str]:
    ids = {requested_by, decided_by, finance_decided_by}
    ok = len(ids) == 3
    return ok, f"요청자·팀장·재무 3인 {'전원 상이' if ok else '중복 있음'} ({sorted(ids)})"
