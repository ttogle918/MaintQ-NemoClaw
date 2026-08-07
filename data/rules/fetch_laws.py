"""
법령 원문 수집 · 개정 감지

원칙:
  - 자동 덮어쓰기 금지. 해시가 달라지면 pending_revision을 만들고 사람에게 넘긴다.
  - 개정 감지 시 영향받는 룰을 역추적해 함께 보고한다.
  - 과거 스냅샷은 지우지 않는다 (append-only, D60).

사용:
    uv run python data/rules/fetch_laws.py --check      # 개정 감지만
    uv run python data/rules/fetch_laws.py --fetch ID   # 특정 조문 수집

⚠️ law.go.kr OPEN API는 이용 신청이 필요하며 응답 스키마가 바뀔 수 있다.
   실제 연동 전에 현행 API 문서를 확인할 것. 아래 fetch_from_api는 골격이다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from engine import load_laws, load_rules, text_hash  # noqa: E402

PENDING_DIR = Path(__file__).parent / "pending_revisions"
API_KEY = os.environ.get("LAW_API_KEY")


def fetch_from_api(law_ref_id: str) -> dict:
    """law.go.kr OPEN API 호출 지점.

    실제 구현 시 확인할 것:
      - 인증 방식 (OC 파라미터)
      - 조문 단위 조회 지원 여부 (미지원이면 전체 수신 후 조 단위 파싱)
      - 시행일·공포번호 필드명
    """
    if not API_KEY:
        raise RuntimeError(
            "LAW_API_KEY 미설정. law.go.kr에서 OPEN API 이용 신청 후 환경변수로 지정."
        )
    raise NotImplementedError("API 스키마 확인 후 구현")


def affected_rules(law_ref_id: str) -> list[str]:
    """개정된 조문을 참조하는 룰 역추적."""
    laws = load_laws()
    rules = load_rules(laws)
    return [r.rule_id for r in rules.values() if law_ref_id in r.law_refs]


def check_revisions() -> list[dict]:
    """해시 비교로 개정 감지. 변경분은 pending_revision으로만 남긴다."""
    laws = load_laws()
    reports = []

    for law_ref_id, law in laws.items():
        if not law.is_fetched:
            reports.append({
                "law_ref_id": law_ref_id,
                "status": "NOT_FETCHED",
                "citation": law.citation(),
                "affected_rules": affected_rules(law_ref_id),
                "note": law.verification_note,
            })
            continue

        try:
            fetched = fetch_from_api(law_ref_id)
        except (RuntimeError, NotImplementedError) as exc:
            reports.append({"law_ref_id": law_ref_id, "status": "FETCH_FAILED", "error": str(exc)})
            continue

        new_hash = text_hash(fetched["text"])
        if new_hash == law.text_hash:
            reports.append({"law_ref_id": law_ref_id, "status": "UNCHANGED"})
            continue

        # 자동 반영하지 않는다
        PENDING_DIR.mkdir(exist_ok=True)
        pending = {
            "law_ref_id": law_ref_id,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "old_hash": law.text_hash,
            "new_hash": new_hash,
            "old_text": law.text,
            "new_text": fetched["text"],
            "affected_rules": affected_rules(law_ref_id),
            "requires_signature": True,
        }
        (PENDING_DIR / f"{law_ref_id}.json").write_text(
            json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        reports.append({
            "law_ref_id": law_ref_id,
            "status": "REVISION_DETECTED",
            "affected_rules": pending["affected_rules"],
            "note": "pending_revisions에 기록됨. 담당자 검토·서명 전까지 반영되지 않는다.",
        })

    return reports


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="개정 감지")
    parser.add_argument("--fetch", metavar="LAW_REF_ID", help="특정 조문 수집")
    args = parser.parse_args()

    if args.check:
        for r in check_revisions():
            print(json.dumps(r, ensure_ascii=False))
    elif args.fetch:
        print(json.dumps(fetch_from_api(args.fetch), ensure_ascii=False, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
