# -*- coding: utf-8 -*-
"""안전 게이트 런타임 원천 (D157).

`iG5A`·`S100` 은 `prompts.SAFETY_BASELINE` 정적 상수 그대로다(`source="static"`) —
이 파일은 그 둘의 출력 바이트를 **하나도 바꾸지 않는다**. 그 밖의 `prompts.MODELS`
기종(HV600 등)은 `/app` 이 읽기 전용이라 배포 후 `prompts.py` 를 코드로 고칠 수
없으므로(D147), 사람이 승인한 문구를 `onboarding_safety_candidates` 테이블에서
런타임에 읽는다.

**fail closed (D157)** — 승인 행이 정확히 1건일 때만 값을 돌려준다. 0건·2건 이상·
DB 조회 예외는 전부 `None`이다. `None`을 받은 `backend/agent/loop.py` 는 새 분기를
타지 않고 기존 차단 로직(`:433-436` 부근 — 안전 블록도 절차 서술도 내지 않는다)을
그대로 재사용한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from backend import db
from backend.agent import prompts

logger = logging.getLogger(__name__)

#: 시드 3기종은 파일이 정본(D148) — 온보딩 승격·안전 문구 승인 대상이 아니다.
#: `backend.services.onboarding` 이 이 상수를 재수출한다(정의는 여기 한 곳 — 그쪽이
#: 이 모듈을 import 하므로 반대 방향으로 두면 순환 import 가 된다).
SEED_MODELS: frozenset[str] = frozenset({"iG5A", "S100", "IE5"})


@dataclass(frozen=True)
class SafetyEntry:
    model: str
    title: str
    text: str
    page: int
    source: Literal["static", "onboarding"]
    approved_at: str | None
    text_reviewed_at: str | None


def _static_entry(model: str) -> SafetyEntry | None:
    """`SAFETY_BASELINE` 에서 조회 — iG5A·S100 전용, 무변경 경로."""
    pages = prompts.SAFETY_BASELINE.get("pages")
    if not isinstance(pages, dict) or model not in pages:
        return None
    page = pages.get(model)
    if not isinstance(page, int):
        return None
    approved_at = prompts.SAFETY_BASELINE.get("approved_at")
    text_reviewed_at = prompts.SAFETY_BASELINE.get("text_reviewed_at")
    return SafetyEntry(
        model=model,
        title=str(prompts.SAFETY_BASELINE["title"]),
        text=str(prompts.SAFETY_BASELINE["text"]),
        page=page,
        source="static",
        approved_at=str(approved_at) if approved_at else None,
        text_reviewed_at=str(text_reviewed_at) if text_reviewed_at else None,
    )


def _onboarding_entry(model: str) -> SafetyEntry | None:
    """`onboarding_safety_candidates` 에서 조회 — HV600 등, D157 fail-closed."""
    try:
        with db.connect() as con:
            rows = con.execute(
                "SELECT approved_text, page, approved_at, text_reviewed_at"
                " FROM onboarding_safety_candidates"
                " WHERE model = ? AND kind = 'discharge_wait' AND state = 'approved'",
                (model,),
            ).fetchall()
    except Exception as e:  # noqa: BLE001 — DB 예외는 fail closed(D157), 턴을 죽이지 않는다
        logger.warning("safety_source.resolve(%s): DB 조회 실패 — None 반환: %s", model, e)
        return None

    if len(rows) != 1:
        if len(rows) > 1:
            logger.warning(
                "safety_source.resolve(%s): 승인 행이 %d건 — 데이터 오류, None 반환",
                model,
                len(rows),
            )
        return None

    row = rows[0]
    page = row["page"]
    if not isinstance(page, int):
        return None
    approved_text = row["approved_text"]
    approved_at = row["approved_at"]
    text_reviewed_at = row["text_reviewed_at"]
    return SafetyEntry(
        model=model,
        title=str(prompts.SAFETY_BASELINE["title"]),  # UI 라벨 — 검수 대상 아님(D157)
        text=str(approved_text),
        page=page,
        source="onboarding",
        approved_at=str(approved_at) if approved_at is not None else None,
        text_reviewed_at=str(text_reviewed_at) if text_reviewed_at is not None else None,
    )


def resolve(model: str | None) -> SafetyEntry | None:
    """안전 문구 런타임 원천. 모델을 모르면 `None`.

    iG5A·S100 → 정적 상수(`source="static"`, 바이트 동일). 그 밖의 `prompts.MODELS`
    기종 → DB 승인 행 정확히 1건일 때만(`source="onboarding"`). 그 외 전부 `None`.
    시드 기종인데 정적 상수에 없는 IE5 는 DB 를 보지 않고 `None` (D109 ⓐ).
    """
    if not model:
        return None

    static = _static_entry(model)
    if static is not None:
        return static

    if model not in prompts.MODELS:
        return None

    # 방어 이중화 (D109 ⓐ) — 정적 상수에 없는 시드 기종(IE5)은 안전 문구를 확장하지 않는다.
    # 승인 서비스가 시드 기종 후보를 422 로 막지만(`seed_model_not_onboardable`), DB 에
    # 어떤 경로로든 IE5 승인 행이 생겨도 여기서는 **DB 를 조회하지 않고** None 이다.
    if model in SEED_MODELS:
        return None

    return _onboarding_entry(model)
