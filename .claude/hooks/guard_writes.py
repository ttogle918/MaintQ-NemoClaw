#!/usr/bin/env python3
"""PreToolUse 훅: 보호 경로 쓰기 차단 (크로스플랫폼).

차단 대상:
- data/raw/**        : 매뉴얼 원본은 읽기 전용 (CLAUDE.md 절대 규칙 5)
- eval/testset.json  : 기대 정답 변경은 사람 승인 사항 (run-eval 스킬 규칙)

exit 2  → 도구 호출 차단, stderr가 Claude에게 전달됨
exit 0  → 통과
"""
import json
import sys

PROTECTED = ("data/raw/", "data\\raw\\")
PROTECTED_FILES = ("eval/testset.json", "eval\\testset.json")
# manifest.json은 원본이 아니라 관리 대장 — 파이프라인이 sha256을 채우고(D19),
# 페이지 오프셋 등 메타데이터를 기록한다(D26). raw 보호에서 제외.
# INDEX.md도 같은 성격 — 원본이 아니라 "어느 디렉터리에 무엇이 있나"를 적는 문서다.
# ⛔ 예외는 **파일명 정확 일치**로만 준다. 원본(PDF·CSV·wav)은 그대로 차단된다.
ALLOWED_IN_PROTECTED = (
    "data/raw/manifest.json",
    "data\\raw\\manifest.json",
    "data/raw/index.md",
    "data\\raw\\index.md",
)

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)  # 파싱 실패 시 차단하지 않음 (훅이 개발을 막는 사고 방지)

tool_input = payload.get("tool_input", {}) or {}
path = str(tool_input.get("file_path") or tool_input.get("path") or "")
norm = path.replace("\\", "/").lower()

if any(norm.endswith(a.replace("\\", "/")) for a in ALLOWED_IN_PROTECTED):
    sys.exit(0)

if any(p.replace("\\", "/") in norm for p in PROTECTED):
    print(
        "차단: data/raw/ 는 읽기 전용입니다 (매뉴얼 원본). "
        "가공 결과는 data/extracted/ 에 저장하세요.",
        file=sys.stderr,
    )
    sys.exit(2)

if any(norm.endswith(f.replace("\\", "/")) for f in PROTECTED_FILES):
    print(
        "차단: eval/testset.json 의 기대 정답 변경은 사람 승인이 필요합니다. "
        "변경이 필요하면 이유를 보고하고 승인을 받으세요.",
        file=sys.stderr,
    )
    sys.exit(2)

sys.exit(0)
