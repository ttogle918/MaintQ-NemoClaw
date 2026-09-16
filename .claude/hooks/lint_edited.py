#!/usr/bin/env python3
"""PostToolUse 훅: **방금 편집한 파일 하나만** ruff 로 점검하고 안전한 것만 자동 수정한다.

## 왜 `ruff format` 이 아닌가 (2026-09-09 실측으로 결정)

이 훅은 오래 `python -m ruff format . --silent || exit 0` 이었는데 **한 번도 돈 적이 없다** —
시스템 파이썬에 ruff 가 없어서 매번 `No module named ruff` 로 죽었고 `|| exit 0` 이 그걸 삼켰다.
(그동안 포맷이 유지된 건 훅이 아니라 사람이 `uv run ruff check` 를 돌렸기 때문이다.)

고치면서 재 보니 **`ruff format` 은 189개 중 110개 파일을 재포맷한다.** 이 코드베이스는
`ruff format` 으로 포맷된 적이 없다 — 규약은 사실상 **린터**(`ruff check`)였다. 그대로 켜면
다음에 누가 큰 파일 한 줄을 고치는 순간 **기능 변경 3줄에 스타일 500줄이 섞인 diff** 가 나온다.
이 저장소가 리뷰 가능한 diff 를 중시하는 것과 정면으로 어긋나므로 **켜지 않았다.**

대신 `ruff check --fix` 로 **안전한 자동 수정만** 한다(미사용 import 정리 등). 전면 스타일
적용을 원하면 그건 훅이 아니라 **의도된 단독 커밋**으로 해야 한다.

## 두 번째 교훈 — 조용히 실패하지 않는다

원래 훅의 진짜 결함은 ruff 가 없는 것이 아니라 **없다는 사실이 아무 데도 안 보인 것**이다.
CLAUDE.md 는 *"부재 검사에는 liveness 앵커를 함께 건다"* 고 적어 뒀는데 훅에는 그 원칙이
적용되지 않았다. 그래서 여기서는 **도구를 못 찾으면 stderr 로 알린다**(단, 종료코드는 0 —
훅이 개발을 막는 사고는 여전히 피한다. `guard_writes.py` 와 같은 태도다).
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # 파싱 실패로 개발을 막지 않는다

    tool_input = payload.get("tool_input", {}) or {}
    raw = str(tool_input.get("file_path") or tool_input.get("path") or "")
    if not raw:
        return 0

    path = Path(raw)
    if path.suffix != ".py":
        return 0  # 파이썬 파일만 대상
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.exists():
        return 0

    if shutil.which("uv") is None:
        # ⚠ 조용히 넘어가지 않는다 — 이 훅이 3주 동안 죽어 있던 이유가 바로 이 침묵이었다.
        print("[lint_edited] uv 를 찾지 못해 ruff 점검을 건너뜁니다.", file=sys.stderr)
        return 0

    try:
        proc = subprocess.run(
            ["uv", "run", "ruff", "check", "--fix", str(path)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"[lint_edited] ruff 실행 실패: {exc}", file=sys.stderr)
        return 0

    # 자동 수정으로 끝나지 않은 위반은 보여 준다 — 고칠지는 사람·에이전트가 정한다.
    out = (proc.stdout or "").strip()
    if proc.returncode != 0 and out:
        print(f"[lint_edited] {path.name}\n{out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
