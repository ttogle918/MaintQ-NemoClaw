# -*- coding: utf-8 -*-
"""매뉴얼 manifest 로더 + 인쇄 페이지 환산 (D19 · D26 · D32 · D49).

`data/raw/manifest.json` 이 오프셋의 **단일 원천**이다 (D19). 여기서 읽은
`print_page_offset` 을 적용하는 곳은 `backend/sse.py:citation_for()` 하나뿐이고
(D32), 저장·평가는 계속 PDF 물리 페이지만 본다 (D26).

경계 조건 (D49): `page - offset` 이 1 미만이면 오프셋을 적용하지 않는다.
S100 안전 지침은 물리 p.2 인데 offset 16 을 빼면 인쇄 p.-14 가 된다 —
표지·안전지침은 본문 쪽번호 체계 밖이라 환산 대상이 아니다.

모델 키(`print_page_offset`)는 `role="primary"` 를 우선하므로 같은 기종의 보충
매뉴얼을 가리키지 못한다. 근거를 `manual_id` 로 들고 다니는 경로는 `manual_offset()`
/ `to_print_page_for_manual()` 을 쓴다 — 산술과 D49 경계는 동일하다 (MQ-920).

manifest 가 없거나 모델이 목록에 없으면 offset 0 으로 폴백하고 경고만 남긴다.
인용을 아예 못 내는 것보다 물리 페이지라도 보여주는 편이 낫고, 인용률 판정은
`page`(물리) 로 이뤄지므로 지표에는 영향이 없다 (D26).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

#: model enum — 기종은 2개로 고정 (D6 · D13)
MODELS: tuple[str, ...] = ("iG5A", "S100")

MANIFEST_PATH: Path = Path(__file__).resolve().parent.parent / "data" / "raw" / "manifest.json"

DEFAULT_OFFSET = 0

# 1회 캐시 — manifest 는 연 단위로만 바뀌는 정적 파일이다 (D19).
_cache: dict | None = None
_cache_path: Path | None = None
_warned_models: set[str] = set()
_warned_manuals: set[str] = set()


def reset_cache() -> None:
    """캐시 초기화. 테스트에서 MANIFEST_PATH 를 바꿔 폴백 경로를 볼 때 쓴다."""
    global _cache, _cache_path
    _cache = None
    _cache_path = None
    _warned_models.clear()
    _warned_manuals.clear()


def validate_model(model: str) -> str:
    """model enum 강제 (D6 · D13). 미지 기종은 조용히 넘기지 않는다."""
    if model not in MODELS:
        raise ValueError(f"model 은 {MODELS} 중 하나여야 합니다 (받은 값: {model!r})")
    return model


def load_manifest(path: str | Path | None = None) -> dict:
    """manifest.json 을 읽어 dict 로 반환. 같은 경로면 1회만 읽는다.

    파일이 없거나 JSON 이 깨져도 예외를 올리지 않고 빈 목록으로 폴백한다 —
    manifest 하나 때문에 인용 자체가 끊기면 안 된다.
    """
    global _cache, _cache_path

    target = Path(path) if path is not None else MANIFEST_PATH
    if _cache is not None and _cache_path == target:
        return _cache

    data: dict
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("manuals"), list):
            logger.warning("manifest 구조가 예상과 다릅니다 (%s) — offset 0 으로 폴백", target)
            data = {"manuals": []}
    except FileNotFoundError:
        logger.warning("manifest 를 찾을 수 없습니다 (%s) — offset 0 으로 폴백", target)
        data = {"manuals": []}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("manifest 를 읽지 못했습니다 (%s): %s — offset 0 으로 폴백", target, exc)
        data = {"manuals": []}

    _cache = data
    _cache_path = target
    _warned_models.clear()
    _warned_manuals.clear()
    return data


def manual_entry(model: str) -> dict | None:
    """모델의 대표 매뉴얼 항목. role='primary' 를 우선한다 (보충 자료는 오프셋 원천이 아님)."""
    validate_model(model)
    entries = [m for m in load_manifest().get("manuals", []) if m.get("model") == model]
    if not entries:
        return None
    for entry in entries:
        if entry.get("role") == "primary":
            return entry
    return entries[0]


def manual_label(model: str) -> str:
    """인용 라벨의 매뉴얼 이름. 예: `iG5A 매뉴얼`."""
    validate_model(model)
    return f"{model} 매뉴얼"


def print_page_offset(model: str) -> int:
    """manifest 의 `print_page_offset` (물리 = 인쇄 + offset). 미등록이면 0 (D19)."""
    entry = manual_entry(model)
    if entry is None:
        if model not in _warned_models:
            _warned_models.add(model)
            logger.warning(
                "manifest 에 %s 항목이 없습니다 — offset %d 로 폴백", model, DEFAULT_OFFSET
            )
        return DEFAULT_OFFSET

    offset = entry.get("print_page_offset", DEFAULT_OFFSET)
    if not isinstance(offset, int) or isinstance(offset, bool):
        if model not in _warned_models:
            _warned_models.add(model)
            logger.warning(
                "%s 의 print_page_offset 이 정수가 아닙니다 (%r) — offset %d 로 폴백",
                model,
                offset,
                DEFAULT_OFFSET,
            )
        return DEFAULT_OFFSET
    return offset


def to_print_page(model: str, page: int) -> int:
    """PDF 물리 페이지 → 인쇄(본문) 페이지.

    `p = page - offset` 이고 **`p < 1` 이면 `page` 를 그대로 반환한다** (D49).
    표지·안전지침처럼 본문 쪽번호 체계 밖의 면에서 음수가 나오는 것을 막는다.

    반환값은 **표시 전용**이다. 저장·검증에는 물리 `page` 만 쓴다 (D26).
    """
    validate_model(model)
    if isinstance(page, bool) or not isinstance(page, int):
        raise ValueError(f"page 는 정수여야 합니다 (받은 값: {page!r})")
    if page < 1:
        raise ValueError(f"page 는 1 이상의 PDF 물리 페이지여야 합니다 (받은 값: {page})")

    printed = page - print_page_offset(model)
    return page if printed < 1 else printed


# ── manual_id 키 조회 (MQ-920) ────────────────────────────────────────────────
# `print_page_offset(model)` 은 model 키 + `role="primary"` 우선 규약이라
# 같은 기종의 supplement 매뉴얼(`ig5a-troubleshooting` 등)을 절대 찾지 못한다.
# ⛔ 여기에 오프셋 **값**을 적지 않는다 — manifest 가 단일 원천이고(D19) 주석 사본은 조용히 낡는다.
# 근거가 어느 문서의 몇 쪽인지를 `manual_id` 로 들고 다니는 경로(조치문 추출 등)는
# 아래 두 함수를 쓴다. 산술 규약·경계 조건은 위 함수들과 동일하다 (D19·D32·D49).


def manual_entry_by_id(manual_id: str) -> dict | None:
    """`id` 로 매뉴얼 항목을 찾는다. model 필터도 role 우선순위도 적용하지 않는다."""
    if not isinstance(manual_id, str) or not manual_id:
        raise ValueError(
            f"manual_id 는 비어 있지 않은 문자열이어야 합니다 (받은 값: {manual_id!r})"
        )
    for entry in load_manifest().get("manuals", []):
        if entry.get("id") == manual_id:
            return entry
    return None


def manual_offset(manual_id: str) -> int:
    """manifest 의 `print_page_offset` 을 **manual_id 키**로 조회 (물리 = 인쇄 + offset).

    미등록 id 는 `print_page_offset(model)` 과 같은 태도 — 예외를 던지지 않고
    `DEFAULT_OFFSET` 으로 폴백하며 id 당 1회만 경고한다 (D19).
    """
    entry = manual_entry_by_id(manual_id)
    if entry is None:
        if manual_id not in _warned_manuals:
            _warned_manuals.add(manual_id)
            logger.warning(
                "manifest 에 매뉴얼 id %r 항목이 없습니다 — offset %d 로 폴백",
                manual_id,
                DEFAULT_OFFSET,
            )
        return DEFAULT_OFFSET

    offset = entry.get("print_page_offset", DEFAULT_OFFSET)
    if not isinstance(offset, int) or isinstance(offset, bool):
        if manual_id not in _warned_manuals:
            _warned_manuals.add(manual_id)
            logger.warning(
                "%s 의 print_page_offset 이 정수가 아닙니다 (%r) — offset %d 로 폴백",
                manual_id,
                offset,
                DEFAULT_OFFSET,
            )
        return DEFAULT_OFFSET
    return offset


def to_print_page_for_manual(manual_id: str, page: int) -> int:
    """PDF 물리 페이지 → 인쇄(본문) 페이지, **manual_id 기준**.

    `to_print_page(model, page)` 와 같은 D49 경계 조건을 쓴다 — `page - offset` 이
    1 미만이면 오프셋을 적용하지 않고 물리 페이지를 그대로 돌려준다.
    반환값은 **표시 전용**이며 저장·검증에는 물리 `page` 만 쓴다 (D26).
    """
    if isinstance(page, bool) or not isinstance(page, int):
        raise ValueError(f"page 는 정수여야 합니다 (받은 값: {page!r})")
    if page < 1:
        raise ValueError(f"page 는 1 이상의 PDF 물리 페이지여야 합니다 (받은 값: {page})")

    printed = page - manual_offset(manual_id)
    return page if printed < 1 else printed
