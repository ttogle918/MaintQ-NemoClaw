# -*- coding: utf-8 -*-
"""온보딩 스테이징 순수 함수 — 프롬프트 주입 판정 (D154).

업로드된 매뉴얼 원문(`onboarding_code_rows.causes_en` 등)과 에이전트가 만든 번역
(`stage_code_normalization` 의 `name_ko`·`causes_ko`)은 둘 다 **신뢰할 수 없는 입력**이다
(D144·D145). 이 모듈은 그 위에서 서버가 **결정적으로** 내리는 판정만 담는다 —
외부 의존성이 없고(DB·네트워크·LLM 미접촉), 같은 입력에는 항상 같은 출력을 낸다.

- `suspect_reasons()` — 문자열 하나에서 주입/지시 문구 패턴을 찾는다.
- `row_source_flags()` — 적재 시점, 매뉴얼 원문 자체에 그 패턴이 있는지(`onboarding_load.py`).
- `preserved_tokens()` — 파라미터 ID·숫자처럼 번역 중에도 그대로 남아야 하는 토큰.
- `shape_matches()` — 번역이 원문과 같은 개수·모양을 유지했는지.
- `finalize()` — `stage_code_normalization` 이 INSERT 하기 직전 최종 confidence·flags 를 정한다.
  에이전트가 보낸 값을 그대로 믿지 않고 서버가 덮어쓸 수 있다 — 무엇을 덮었는지는
  `forced_by_server` 로 숨기지 않고 알려준다.
"""

from __future__ import annotations

import json
import re
from typing import Any

# ── suspect_reasons() 패턴 (대소문자 무시) ──────────────────────────────
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        # 2026-09-25 Stage 2 리뷰 반영: 옛 패턴은 한정사 하나만 허용해 "ignore THE PREVIOUS
        # instructions"(둘 다) · "ignore YOUR instructions"("your" 미포함) · "FORGET previous
        # instructions"(동사 "ignore" 고정)를 놓쳤다. 동사 3종(ignore|disregard|forget) +
        # 한정사 0개 이상 반복 + 시점어 선택으로 넓힌다. `data/extracted/hv600_code_candidates.json`
        # 전 249행 원문에 대해 오탐 0건 실측 확인(양성 4종은 전부 매칭).
        "ignore_instructions",
        re.compile(
            r"(ignore|disregard|forget)\s+(all\s+|any\s+|the\s+|your\s+|my\s+)*"
            r"(previous|prior|above|earlier)?\s*(instructions?|prompts?|rules?)",
            re.IGNORECASE,
        ),
    ),
    ("disregard", re.compile(r"disregard", re.IGNORECASE)),
    (
        "role_marker",
        re.compile(r"system prompt|developer message|assistant:", re.IGNORECASE),
    ),
    ("persona", re.compile(r"you are (now )?(an?|the) ", re.IGNORECASE)),
    (
        "ignore_instructions_ko",
        re.compile(r"이전\s*(지시|명령|규칙)|(지시|명령|규칙)\S*\s*무시"),
    ),
    (
        "tool_or_action_mention",
        re.compile(
            r"stage_code_normalization|list_onboarding_rows|create_po_draft|"
            r"lookup_error_code|promote|approve|승인하",
            re.IGNORECASE,
        ),
    ),
    ("url", re.compile(r"https?://", re.IGNORECASE)),
    (
        "markup",
        re.compile(r"```|<\s*/?\s*(system|tool|instructions?)", re.IGNORECASE),
    ),
)

#: 허용된 에이전트 플래그(D154) — 이 밖은 버리고 `unknown_flag_dropped` 를 추가한다.
ALLOWED_AGENT_FLAGS = frozenset(
    {
        "injection_suspect",
        "output_suspect",
        "token_dropped",
        "untranslated_term",
        "ambiguous_source",
        "agent_low_confidence",
    }
)

# 파라미터 ID: "H5-34" · "A-12" 류(문자 + 선택 숫자 1개 + 하이픈 + 숫자 2자리),
# "H5-4" 류(문자 + 숫자 1개 필수 + 하이픈 + 숫자 1~2자리).
# 경계는 ASCII 로 판정한다 — `\b` 는 유니코드라 한글을 단어 문자로 보고 "A1-03을" 의 토큰을 놓쳐
# `token_dropped` 로 떨어뜨렸다(2026-09-25 MQ-1908 실측, HV600 row 40).
_PARAM_ID_RE1 = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]\d?-\d{2}(?![A-Za-z0-9])")
_PARAM_ID_RE2 = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]\d-\d{1,2}(?![A-Za-z0-9])")
_NUMBER_RUN_RE = re.compile(r"\d+(?:\.\d+)?")


def suspect_reasons(text: str) -> list[str]:
    """`text` 안에서 지시·주입 문구 패턴을 찾아 정렬된 사유 코드 목록을 돌려준다.
    없으면 빈 리스트."""
    if not text:
        return []
    hits = {name for name, pattern in _PATTERNS if pattern.search(text)}
    return sorted(hits)


def _causes_text(causes: Any) -> str:
    """`causes_en`/`causes_ko` (list[dict] 또는 이미 직렬화된 JSON 문자열)를 검사 가능한
    단일 문자열로 만든다."""
    if isinstance(causes, str):
        try:
            causes = json.loads(causes) if causes else []
        except (ValueError, TypeError):
            return causes
    return json.dumps(causes, ensure_ascii=False)


def row_source_flags(name_en: str, causes_en: list[dict] | str) -> list[str]:
    """적재 시 원문 전체(이름 + 원인·조치)를 판정한다. `["injection_suspect"]` 또는 `[]`."""
    text = f"{name_en or ''} {_causes_text(causes_en)}"
    return ["injection_suspect"] if suspect_reasons(text) else []


def preserved_tokens(text: str) -> set[str]:
    """번역 중에도 그대로 남아야 하는 토큰(파라미터 ID·숫자) 집합."""
    if not text:
        return set()
    tokens: set[str] = set()
    for pattern in (_PARAM_ID_RE1, _PARAM_ID_RE2, _NUMBER_RUN_RE):
        tokens.update(m.group(0) for m in pattern.finditer(text))
    return tokens


def shape_matches(causes_en: list[dict] | str, causes_ko: object) -> bool:
    """`causes_ko` 가 `causes_en` 과 같은 모양(길이·각 solutions 개수·문자열 타입)인지."""
    if isinstance(causes_en, str):
        try:
            causes_en = json.loads(causes_en) if causes_en else []
        except (ValueError, TypeError):
            return False
    if isinstance(causes_ko, str):
        try:
            causes_ko = json.loads(causes_ko) if causes_ko else []
        except (ValueError, TypeError):
            return False
    if not isinstance(causes_en, list) or not isinstance(causes_ko, list):
        return False
    if len(causes_en) != len(causes_ko):
        return False
    for en_item, ko_item in zip(causes_en, causes_ko):
        if not isinstance(en_item, dict) or not isinstance(ko_item, dict):
            return False
        if not isinstance(ko_item.get("cause"), str):
            return False
        en_solutions = en_item.get("solutions") or []
        ko_solutions = ko_item.get("solutions") or []
        if not isinstance(en_solutions, list) or not isinstance(ko_solutions, list):
            return False
        if len(en_solutions) != len(ko_solutions):
            return False
        if not all(isinstance(s, str) for s in ko_solutions):
            return False
    return True


def finalize(
    row: dict,
    name_ko: str,
    causes_ko: list[dict],
    confidence: str,
    flags: list[str] | None,
) -> tuple[str, list[str], list[str]]:
    """서버 최종 판정. `row` 는 스테이징 행(적어도 `name_en`·`causes_en`·`source_flags` 를
    담고 있어야 한다). 반환: (최종 confidence, 최종 flags(정렬·중복 제거), 서버가 강제한
    사유 목록)."""
    forced: list[str] = []
    sanitized: set[str] = set()
    unknown_dropped = False
    for f in flags or []:
        if f in ALLOWED_AGENT_FLAGS:
            sanitized.add(f)
        else:
            unknown_dropped = True

    final_confidence = confidence

    source_flags = row.get("source_flags") or []
    if isinstance(source_flags, str):
        try:
            source_flags = json.loads(source_flags) if source_flags else []
        except (ValueError, TypeError):
            source_flags = []
    if source_flags:
        final_confidence = "low"
        sanitized.add("injection_suspect")
        forced.append("injection_suspect")

    output_text = f"{name_ko or ''} {_causes_text(causes_ko)}"
    if suspect_reasons(output_text):
        final_confidence = "low"
        sanitized.add("output_suspect")
        forced.append("output_suspect")

    orig_text = f"{row.get('name_en', '') or ''} {_causes_text(row.get('causes_en', []))}"
    orig_tokens = preserved_tokens(orig_text)
    translated_tokens = preserved_tokens(output_text)
    if orig_tokens - translated_tokens:
        final_confidence = "low"
        sanitized.add("token_dropped")
        forced.append("token_dropped")

    if unknown_dropped:
        sanitized.add("unknown_flag_dropped")
        forced.append("unknown_flag_dropped")

    return final_confidence, sorted(sanitized), forced
