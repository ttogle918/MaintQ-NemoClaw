# -*- coding: utf-8 -*-
"""공개 레포에 남길 **구조 샘플**을 만든다 (D144).

매뉴얼 본문·에러코드 표 문구는 원본 매뉴얼의 표현이라 재배포하지 않는다 —
실데이터는 `.gitignore` 로 빼고, **형태를 사람이 확인할 수 있을 만큼만** 여기로 뽑는다.

규칙
  1. 키 구조는 원본 그대로 남긴다 — 필드가 몇 개이고 어떤 타입인지 보여야 한다.
  2. 매뉴얼에서 온 문자열은 `MAX_CHARS` 로 자르고 `…` 를 붙인다 (인용 수준).
  3. 리스트는 앞 `MAX_ITEMS` 개만 남기고 `_omitted` 로 몇 개를 뺐는지 밝힌다.
  4. 결정론적이다 — 같은 입력이면 같은 출력(D19 와 같은 발상).

실행: uv run python scripts/make_data_samples.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "extracted" / "samples"

MAX_CHARS = 40  # 매뉴얼 유래 문자열을 자르는 길이
MAX_ITEMS = 2  # 리스트에서 남길 원소 수
MAX_ENTRIES = 2  # entries 류 최상위 리스트에서 남길 행 수

# 매뉴얼 본문이 실리는 필드 — 이 키의 문자열만 자른다.
# (설명·상태 메타는 우리가 쓴 글이라 그대로 둔다.)
MANUAL_TEXT_KEYS = frozenset(
    {"text", "causes", "actions", "error_name", "quote", "section", "name", "raw"}
)


def _clip(s: str) -> str:
    return s if len(s) <= MAX_CHARS else s[:MAX_CHARS] + "…"


def redact(value, *, manual: bool):
    """manual=True 면 이 가지의 문자열은 매뉴얼 유래로 보고 자른다."""
    if isinstance(value, str):
        return _clip(value) if manual else value
    if isinstance(value, list):
        kept = [redact(v, manual=manual) for v in value[:MAX_ITEMS]]
        if len(value) > MAX_ITEMS:
            kept.append(f"…({len(value) - MAX_ITEMS}건 생략)")
        return kept
    if isinstance(value, dict):
        return {k: redact(v, manual=manual or k in MANUAL_TEXT_KEYS) for k, v in value.items()}
    return value


def sample_json(src: Path, list_key: str | None) -> dict:
    data = json.loads(src.read_text(encoding="utf-8"))
    out = {}
    for k, v in data.items():
        if k == list_key and isinstance(v, list):
            out[f"_{k}_전체건수"] = len(v)
            out[k] = [redact(e, manual=False) for e in v[:MAX_ENTRIES]]
        else:
            out[k] = redact(v, manual=False)
    return out


def sample_jsonl(src: Path, n: int = 3) -> list[dict]:
    rows = []
    with src.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i >= n:
                break
            rows.append(redact(json.loads(line), manual=False))
    return rows


# (원본, 결과 파일명, entries 역할을 하는 키)
TARGETS: tuple[tuple[str, str, str | None], ...] = (
    ("data/extracted/error_codes.json", "error_codes.sample.json", "entries"),
    (
        "data/extracted/error_codes_actions.candidate.json",
        "error_codes_actions.candidate.sample.json",
        "entries",
    ),
    ("data/extracted/ie5_code_candidates.json", "ie5_code_candidates.sample.json", "candidates"),
    ("data/extracted/ig5a_code_map.json", "ig5a_code_map.sample.json", "mappings"),
    ("data/extracted/ig5a_action_map.json", "ig5a_action_map.sample.json", "mappings"),
    (
        "data/extracted/actions_absence_verification.json",
        "actions_absence_verification.sample.json",
        None,
    ),
)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    made: list[str] = []
    missing: list[str] = []

    for rel, name, key in TARGETS:
        src = ROOT / rel
        if not src.exists():
            missing.append(rel)
            continue
        (OUT / name).write_text(
            json.dumps(sample_json(src, key), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        made.append(name)

    chunks = ROOT / "data/extracted/manual_chunks.jsonl"
    if chunks.exists():
        total = sum(1 for _ in chunks.open(encoding="utf-8"))
        rows = sample_jsonl(chunks)
        body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        header = f"// 전체 {total}청크 중 앞 {len(rows)}건. text 는 {MAX_CHARS}자로 잘랐다.\n"
        (OUT / "manual_chunks.sample.jsonl").write_text(header + body, encoding="utf-8")
        made.append("manual_chunks.sample.jsonl")
    else:
        missing.append("data/extracted/manual_chunks.jsonl")

    # ── 양성 축 (CLAUDE.md 의 liveness 앵커 규칙) ─────────────────────────────
    # "잘렸다" 만 확인하면 입력이 비었을 때도 통과한다. 실제로 뭔가 읽었는지 같이 본다.
    print(f"생성 {len(made)}건: {', '.join(made)}")
    if missing:
        print(f"⚠ 원본 없음 {len(missing)}건 (실데이터는 .gitignore 대상): {', '.join(missing)}")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
