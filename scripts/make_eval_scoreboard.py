# -*- coding: utf-8 -*-
"""`eval/results/` 의 **점수만** 뽑아 스코어보드 1장으로 남긴다 (D144).

평가 결과 원본(`eval/results/*.json`·`*.traces.jsonl`)에는 에이전트 응답이 통째로 실려
있고 그 안에 매뉴얼의 원인·조치 문구가 그대로 들어간다 — 그래서 git 추적에서 뺀다.
대신 **"실제로 돌렸다"는 증거인 지표는 사라지면 안 되므로** 여기로 옮긴다.

남기는 것 : 실행일시 · 제공자/모델 · 도구 프로파일 · 반복 수 · 5지표 수치
버리는 것 : `response_text` · `judge` 근거문 · trace 본문 (전부 매뉴얼 문구를 실어 나른다)

실행: uv run python scripts/make_eval_scoreboard.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "results"
OUT = ROOT / "eval" / "SCOREBOARD.md"

METRICS = ("part", "citation", "safety", "sequence", "hallucination")


def _rate(m: dict, name: str) -> str:
    v = m.get(name)
    if not isinstance(v, dict):
        return "—"
    rate = v.get("rate")
    total = v.get("total")
    if rate is None or not total:
        return "—"
    return f"{rate * 100:.0f}% ({v.get('passed', v.get('hallucinated', '?'))}/{total})"


def main() -> int:
    rows: list[tuple] = []
    for path in sorted(RESULTS.rglob("*.json")):
        if path.name.endswith(".traces.jsonl"):
            continue
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        agg = d.get("aggregate")
        if not isinstance(agg, dict):
            continue
        meta = d.get("meta") or {}
        m = agg.get("metrics") or {}
        rows.append(
            (
                d.get("generated_at", path.stem),
                str(path.relative_to(ROOT)),
                f"{meta.get('llm_provider', '?')} / {meta.get('llm_model', '?')}",
                f"{meta.get('tools_profile', '?')}({meta.get('tools', '?')})",
                d.get("repeat", 1),
                agg.get("n_kept", "?"),
                *[_rate(m, k) for k in METRICS],
            )
        )

    if not rows:
        print("⚠ eval/results 에 집계가 있는 결과 파일이 없다 — 스코어보드를 쓰지 않았다")
        return 1

    lines = [
        "# 평가 스코어보드 — 지표만 (D144)",
        "",
        f"`eval/results/` 결과 파일 **{len(rows)}건**에서 지표만 뽑았다.",
        "원본에는 에이전트 응답 전문이 실려 있고 그 안에 매뉴얼 원인·조치 문구가 그대로",
        "들어가므로 git 추적에서 제외했다(D144). 재생성: `uv run python scripts/make_eval_scoreboard.py`",
        "",
        "5지표는 `eval/score.py` 정의를 따른다. `—` 는 그 실행에서 해당 지표의 분모가 0.",
        "",
        "| 실행 | 파일 | 제공자/모델 | 프로파일 | 반복 | 채점 | 부품특정 | 인용 | 안전 | 순서 | 환각 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(rows):
        lines.append("| " + " | ".join(f"`{c}`" if i == 1 else str(c) for i, c in enumerate(r)) + " |")
    lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)} — 실행 {len(rows)}건 기록")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
