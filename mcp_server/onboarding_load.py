# -*- coding: utf-8 -*-
"""mcp_server.onboarding_load — 온보딩 후보 JSON 적재기 (D154, Sprint 19 MQ-1905).

결정적 추출기(`data/extract_hv600_codes.py`·`data/extract_hv600_safety.py`)의 산출물을
온보딩 스테이징 테이블(`onboarding_batches`·`onboarding_code_rows`·
`onboarding_safety_candidates`)에 적재한다. 이 스크립트 자체는 LLM 을 부르지 않는다 —
결정적 파일 읽기 + `onboarding_guard.row_source_flags()` 판정 + INSERT 뿐이다.

`(manual_id, candidates_sha256)` 유니크가 멱등 키다 — 같은 후보 파일을 두 번 적재하면
두 번째는 아무것도 쓰지 않고 종료코드 3을 낸다.

실행:
  uv run python -m mcp_server.onboarding_load --codes data/extracted/hv600_code_candidates.json \
      [--safety data/extracted/hv600_safety_candidates.json] [--model HV600] \
      [--loaded-by onboarding-loader]

종료코드: 0 적재 성공 / 2 입력 오류 / 3 이미 적재됨(멱등, 아무것도 쓰지 않음).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from . import onboarding_guard
from .db import onboarding_writer, read_only

DEFAULT_MODEL = "HV600"
DEFAULT_LOADED_BY = "onboarding-loader"

# D155 — error_codes.code / onboarding_code_rows.code 와 완전히 같은 정규식.
_CODE_RE = re.compile(r"^[A-Z0-9_-]+$")


def _valid_code_shape(code: str) -> bool:
    return bool(code) and 2 <= len(code) <= 5 and code == code.upper() and bool(_CODE_RE.match(code))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="온보딩 후보 JSON 적재기")
    parser.add_argument("--codes", required=True, help="고장 표 후보 JSON 경로")
    parser.add_argument("--safety", default=None, help="안전 문구 후보 JSON 경로 (선택)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"기종 (기본 {DEFAULT_MODEL})")
    parser.add_argument("--loaded-by", default=DEFAULT_LOADED_BY, help="감사 라벨")
    return parser.parse_args(argv)


def _already_loaded(manual_id: str, candidates_sha256: str) -> int | None:
    with read_only() as con:
        row = con.execute(
            "SELECT batch_id FROM onboarding_batches WHERE manual_id = ? AND candidates_sha256 = ?",
            (manual_id, candidates_sha256),
        ).fetchone()
    return row["batch_id"] if row else None


def load(argv: list[str]) -> int:
    args = _parse_args(argv)
    codes_path = Path(args.codes)
    if not codes_path.is_file():
        print(f"입력 오류: --codes 파일이 없습니다: {codes_path}", file=sys.stderr)
        return 2

    try:
        codes_doc = _load_json(codes_path)
    except (ValueError, OSError) as e:
        print(f"입력 오류: --codes JSON 파싱 실패: {e}", file=sys.stderr)
        return 2

    source = codes_doc.get("_source") or {}
    manual_id = source.get("manifest_id")
    pdf_sha256 = source.get("sha256")
    codes = codes_doc.get("codes")
    if not manual_id or not pdf_sha256 or not isinstance(codes, list):
        print(
            "입력 오류: _source.manifest_id · _source.sha256 · codes[] 가 모두 있어야 합니다",
            file=sys.stderr,
        )
        return 2

    safety_doc: dict | None = None
    safety_candidates: list[dict] = []
    if args.safety:
        safety_path = Path(args.safety)
        if not safety_path.is_file():
            print(f"입력 오류: --safety 파일이 없습니다: {safety_path}", file=sys.stderr)
            return 2
        try:
            safety_doc = _load_json(safety_path)
        except (ValueError, OSError) as e:
            print(f"입력 오류: --safety JSON 파싱 실패: {e}", file=sys.stderr)
            return 2
        safety_candidates = safety_doc.get("candidates") or []
        if not isinstance(safety_candidates, list):
            print("입력 오류: --safety 의 candidates 는 배열이어야 합니다", file=sys.stderr)
            return 2

    candidates_sha256 = _sha256_file(codes_path)

    existing_batch = _already_loaded(manual_id, candidates_sha256)
    if existing_batch is not None:
        print(
            json.dumps(
                {
                    "status": "already_loaded",
                    "batch_id": existing_batch,
                    "manual_id": manual_id,
                    "candidates_sha256": candidates_sha256,
                },
                ensure_ascii=False,
            )
        )
        return 3

    model = args.model
    loaded_by = args.loaded_by

    by_section: dict[str, int] = defaultdict(int)
    flagged_rows = 0
    skipped_shape: list[dict] = []
    display_variants: dict[str, set[str]] = defaultdict(set)
    inserted_rows = 0

    try:
        with onboarding_writer() as con:
            batch = con.execute(
                "INSERT INTO onboarding_batches"
                " (model, manual_id, pdf_sha256, candidates_sha256, loaded_by)"
                " VALUES (?, ?, ?, ?, ?) RETURNING batch_id",
                (model, manual_id, pdf_sha256, candidates_sha256, loaded_by),
            ).fetchone()
            batch_id = batch["batch_id"]

            for ordinal, item in enumerate(codes):
                code = str(item.get("code", ""))
                if not _valid_code_shape(code):
                    skipped_shape.append({"code": code, "reason": "invalid_code_shape"})
                    continue
                display_code = item.get("display_code", code)
                section_en = item.get("section", "")
                name_en = item.get("name", "")
                causes_en = item.get("causes", [])
                pages = item.get("pages", [])
                expanded_from = item.get("expanded_from")
                source_flags = onboarding_guard.row_source_flags(name_en, causes_en)

                con.execute(
                    "INSERT INTO onboarding_code_rows"
                    " (batch_id, ordinal, model, code, display_code, section_en, name_en,"
                    "  causes_en, pages, expanded_from, source_flags)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        batch_id,
                        ordinal,
                        model,
                        code,
                        display_code,
                        section_en,
                        name_en,
                        json.dumps(causes_en, ensure_ascii=False),
                        json.dumps(pages),
                        expanded_from,
                        json.dumps(source_flags),
                    ),
                )
                inserted_rows += 1
                by_section[section_en] += 1
                if source_flags:
                    flagged_rows += 1
                display_variants[code].add(display_code)

            for ordinal, cand in enumerate(safety_candidates):
                con.execute(
                    "INSERT INTO onboarding_safety_candidates"
                    " (batch_id, ordinal, model, page, also_pages, kind, quote_en,"
                    "  wait_minutes_in_text)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        batch_id,
                        ordinal,
                        model,
                        cand.get("page"),
                        json.dumps(cand.get("also_pages") or []),
                        cand.get("kind"),
                        cand.get("quote_en", ""),
                        cand.get("wait_minutes_in_text"),
                    ),
                )
    except Exception as e:  # noqa: BLE001
        print(f"적재 실패: {e}", file=sys.stderr)
        return 2

    conflicts = [
        {"code": code, "display_codes": sorted(variants)}
        for code, variants in display_variants.items()
        if len(variants) > 1
    ]

    summary = {
        "status": "loaded",
        "batch_id": batch_id,
        "model": model,
        "manual_id": manual_id,
        "rows": inserted_rows,
        "by_section": dict(by_section),
        "flagged_rows": flagged_rows,
        "skipped_shape": skipped_shape,
        "display_variant_conflicts": conflicts,
        "safety_candidates": len(safety_candidates),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


def main() -> None:
    sys.exit(load(sys.argv[1:]))


if __name__ == "__main__":
    main()
