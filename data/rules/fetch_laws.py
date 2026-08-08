"""
법령 원문 수집 · 적용 · 개정 감지

원칙:
  - 자동 덮어쓰기 금지. 해시가 달라지면 pending_revision을 만들고 사람에게 넘긴다.
  - 개정 감지 시 영향받는 룰을 역추적해 함께 보고한다.
  - 과거 스냅샷은 지우지 않는다 (append-only, D60).
  - 조문번호·제목이 어긋나면 파일을 고치지 않고 중단한다 (각 파일의 verification_note 요구사항).

**수집기(fetch_from_api)와 적용기(apply_fetch)를 분리한다.**
전자는 네트워크·인증키가 있어야 하지만 후자는 파일 조작뿐이라 합성 픽스처로 지금 검증할 수 있다.
회귀는 `spikes/law_fetch_contract.py` (네트워크 미사용).

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
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from engine import load_laws, load_rules, normalize, text_hash  # noqa: E402

LAWS_DIR = Path(__file__).parent / "laws"
PENDING_DIR = Path(__file__).parent / "pending_revisions"

# ⚠ 인증값은 API 키가 아니라 **신청한 이메일 ID 앞부분**이다 (hong@gmail.com → hong).
#    변수명이 사실과 어긋나 있어 개명했다. 뒤쪽은 개명 전 이름 — 폴백으로만 남긴다.
API_OC = os.environ.get("LAW_API_OC") or os.environ.get("LAW_API_KEY")

# 적용 결과 3종. 그 밖의 상황(조문번호·제목 불일치, 미등록 참조)은 반환하지 않고 예외로 중단한다.
FILLED = "FILLED"
UNCHANGED = "UNCHANGED"
REVISION_PENDING = "REVISION_PENDING"

# 정체성 대조 키 — 값이 어긋나도, **아예 없어도** 중단한다. 선택적 필드는 여기 넣지 말 것.
IDENTITY_KEYS = ("article", "title")

# pending_revisions 레코드의 반영 상태.
#   None       반영 시도 없음 (force=False) — 사람 검토·서명 대기
#   "intent"   파일 기입 **직전** 기록. 기입 성공이 확인되지 않았다는 뜻
#   "confirmed" 기입 성공을 확인한 뒤 승격됨
# 기입 도중 죽으면 "intent" 로 남는다 — 기록이 사라지지도, 거짓말을 하지도 않는다.
APPLY_INTENT = "intent"
APPLY_CONFIRMED = "confirmed"


class LawMismatchError(Exception):
    """수집 응답이 등록된 조문과 어긋난다 — 파일을 고치지 않고 사람에게 넘긴다."""


def fetch_from_api(law_ref_id: str) -> dict:
    """law.go.kr OPEN API 호출 지점. **아직 구현하지 않는다.**

    URL 파라미터 형식을 추측해서 박아두지 않는 이유: 틀린 형식이 코드에 남으면
    나중에 "구현돼 있는데 안 되는" 상태가 되어 원인 추적이 더 어려워진다.

    Sprint 7 구현 순서:
      1. `MST`(법령 마스터 번호) 조회 — 법령명으로 lawSearch 해서 MST 확보
      2. `JO` 형식 실호출 확인 — 조번호 자리수·가지번호 표기는 실호출로만 확정된다
      3. 응답의 조문번호·제목을 laws/*.json 과 대조 (apply_fetch 가 강제한다)
    """
    if not API_OC:
        raise RuntimeError(
            "LAW_API_OC 미설정. law.go.kr에서 OPEN API 이용 신청 후 환경변수로 지정. "
            "값은 API 키가 아니라 신청한 이메일 ID 앞부분이다. "
            "키가 비어 있으면 응답이 '필수입력요소 검증에 실패하였습니다' 로 돌아온다."
        )
    raise NotImplementedError(
        "키 발급 후 Sprint 7 에서 구현. "
        "MST 조회 → JO 형식 실호출 확인 → 조문번호·제목 대조 순서."
    )


# ---------------------------------------------------------------- 적용기


def _law_path(law_ref_id: str, laws_dir: Path) -> Path:
    path = laws_dir / f"{law_ref_id}.json"
    if not path.exists():
        # 불변식 2 (D61) — 등록되지 않은 조문에 원문을 붙이지 않는다.
        raise KeyError(f"미등록 법령 참조: {law_ref_id} ({path})")
    return path


def _verify_identity(law_ref_id: str, raw: dict, fetched: dict) -> None:
    """조문번호·제목 대조. 어긋나거나 **대조할 값 자체가 없으면** 파일을 손대기 전에 중단한다.

    누락을 통과시키지 않는 이유: 법제처 응답 필드명은 `조문번호`·`조문제목` 이라
    매핑을 빠뜨리기 쉽고, 그때 이 게이트가 조용히 무력화되면 대조 없이 원문이 기입된다.
    **"확인할 값이 없다"를 "확인했고 문제없다"로 처리하지 않는다** (D50·D62와 같은 태도).
    선택적 필드(effective_from·promulgation_no 등)는 대상이 아니다 — 정체성 키만 본다.
    """
    missing = [
        key
        for key in IDENTITY_KEYS
        if fetched.get(key) is None or not str(fetched[key]).strip()
    ]
    if missing:
        raise LawMismatchError(
            f"{law_ref_id}: 대조 키 누락/공백 {missing} → 파일 미수정. "
            f"응답에서 {', '.join(IDENTITY_KEYS)} 를 채운 뒤 다시 적용할 것 "
            "(법제처 응답 필드명은 조문번호·조문제목). "
            "대조할 값이 없는 것은 대조를 통과한 것이 아니다."
        )

    diffs = [
        f"{key}: 등록={raw.get(key)!r} / 응답={fetched[key]!r}"
        for key in IDENTITY_KEYS
        if normalize(str(fetched[key])) != normalize(str(raw.get(key, "")))
    ]
    if diffs:
        raise LawMismatchError(
            f"{law_ref_id}: 수집 응답이 등록 조문과 불일치 → 파일 미수정. "
            + " | ".join(diffs)
            + ". 개정으로 조문이 이동했을 수 있다 — law_ref_id 정정 여부를 사람이 판단할 것."
        )


def affected_rules(law_ref_id: str) -> list[str]:
    """개정된 조문을 참조하는 룰 역추적."""
    laws = load_laws()
    rules = load_rules(laws)
    return [r.rule_id for r in rules.values() if law_ref_id in r.law_refs]


def _write_pending_revision(
    law_ref_id: str,
    *,
    old_hash: str | None,
    new_hash: str,
    old_text: str | None,
    new_text: str,
    applied: str | None,
    pending_dir: Path,
) -> Path:
    """개정분 기록. **덮어쓰지 않는다** — 파일명에 타임스탬프를 붙여 누적한다 (D60).

    `applied` 는 None | APPLY_INTENT. APPLY_CONFIRMED 로의 승격은
    기입 성공을 확인한 뒤 `_confirm_pending_revision` 이 한다.
    """
    pending_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%S%f")
    path = pending_dir / f"{law_ref_id}.{stamp}.json"
    seq = 0
    while path.exists():
        seq += 1
        path = pending_dir / f"{law_ref_id}.{stamp}-{seq}.json"

    try:
        affected = affected_rules(law_ref_id)
    except Exception as exc:  # noqa: BLE001 — 역추적 실패가 개정 기록을 막으면 안 된다
        affected = [f"<역추적 실패: {exc}>"]

    record = {
        "law_ref_id": law_ref_id,
        "detected_at": now.isoformat(),
        "old_hash": old_hash,
        "new_hash": new_hash,
        "old_text": old_text,
        "new_text": new_text,
        "affected_rules": affected,
        "applied": applied,
        "confirmed_at": None,
        # confirmed 가 아닌 모든 상태는 사람이 봐야 한다 —
        # intent 는 "기입했다고 주장하지만 확인은 안 된 상태"다.
        "requires_signature": applied != APPLY_CONFIRMED,
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _confirm_pending_revision(path: Path) -> None:
    """기입 성공 확인 후 intent → confirmed 승격.

    append-only(D60)가 지키는 것은 **스냅샷 payload**(old/new text·hash)다.
    그 값들은 여기서 건드리지 않고 상태 필드만 전이한다 — flags.state 와 같은 성격.
    """
    record = json.loads(path.read_text(encoding="utf-8"))
    record["applied"] = APPLY_CONFIRMED
    record["confirmed_at"] = datetime.now(timezone.utc).isoformat()
    record["requires_signature"] = False
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_law(path: Path, raw: dict) -> None:
    """계층 1 파일 기입. 키 순서·포맷을 원본 그대로 유지한다."""
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def apply_fetch(
    law_ref_id: str,
    fetched: dict[str, Any],
    *,
    force: bool = False,
    laws_dir: Path | None = None,
    pending_dir: Path | None = None,
) -> str:
    """수집 결과를 계층 1 파일에 적용한다.

    반환: 'FILLED' | 'UNCHANGED' | 'REVISION_PENDING'

      FILLED           최초 수집(PENDING→FETCHED) 또는 force 재적용 — 파일에 in-place 기입
      UNCHANGED        이미 FETCHED 이고 해시 동일 — 파일을 열지도 쓰지도 않는다
      REVISION_PENDING 이미 FETCHED 인데 해시 상이 — **덮어쓰지 않고** pending_revisions 에 기록

    중단(예외):
      KeyError          laws/ 에 없는 law_ref_id (불변식 2, D61)
      LawMismatchError  응답의 조문번호·제목이 등록값과 **불일치하거나 아예 없음** → 파일 미수정
      ValueError        응답에 text 가 없거나 비어 있음

    force=True 는 사람이 개정분을 검토한 뒤의 반영 경로다. 이 경우에도 직전 스냅샷을
    pending_revisions 에 남긴 뒤에 덮어쓴다 — 과거 원문을 지우지 않는다 (D60).
    기록은 `applied:"intent"` 로 먼저 쓰고 **기입 성공을 확인한 뒤** `"confirmed"` 로 승격한다 —
    기입이 실패하면 "적용됨"이라고 거짓말하는 기록이 남지 않는다.

    laws_dir·pending_dir 는 테스트에서 정본을 오염시키지 않기 위한 주입점이다.
    """
    laws_dir = laws_dir or LAWS_DIR
    pending_dir = pending_dir or PENDING_DIR

    path = _law_path(law_ref_id, laws_dir)
    raw = json.loads(path.read_text(encoding="utf-8"))

    new_text = fetched.get("text")
    if not isinstance(new_text, str) or not new_text.strip():
        raise ValueError(f"{law_ref_id}: 수집 응답에 text 가 없다 — 빈 원문을 계층 1에 넣지 않는다")

    # 파일을 손대기 전에 정체성부터 대조한다
    _verify_identity(law_ref_id, raw, fetched)

    new_hash = text_hash(new_text)
    already_fetched = raw.get("fetch_status") == "FETCHED" and raw.get("text") is not None

    if already_fetched and raw.get("text_hash") == new_hash:
        return UNCHANGED

    if already_fetched and not force:
        _write_pending_revision(
            law_ref_id,
            old_hash=raw.get("text_hash"),
            new_hash=new_hash,
            old_text=raw.get("text"),
            new_text=new_text,
            applied=None,
            pending_dir=pending_dir,
        )
        return REVISION_PENDING

    revision_path = None
    if already_fetched:  # force — 덮어쓰기 전에 직전 스냅샷을 남긴다
        revision_path = _write_pending_revision(
            law_ref_id,
            old_hash=raw.get("text_hash"),
            new_hash=new_hash,
            old_text=raw.get("text"),
            new_text=new_text,
            applied=APPLY_INTENT,
            pending_dir=pending_dir,
        )

    raw["text"] = new_text
    raw["text_hash"] = new_hash
    raw["fetch_status"] = "FETCHED"
    raw["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    # 응답이 준 것만 채운다. 없는 필드를 지어내지 않는다.
    for key in ("clause", "effective_from", "effective_to", "promulgation_no", "source_url"):
        if fetched.get(key) is not None:
            raw[key] = fetched[key]

    _write_law(path, raw)
    if revision_path is not None:
        # 기입이 실제로 끝난 뒤에만 "적용됨"이라고 말한다 (N7)
        _confirm_pending_revision(revision_path)
    return FILLED


# ---------------------------------------------------------------- 개정 감지


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

        try:
            outcome = apply_fetch(law_ref_id, fetched)
        except (KeyError, ValueError, LawMismatchError) as exc:
            reports.append({"law_ref_id": law_ref_id, "status": "MISMATCH", "error": str(exc)})
            continue

        if outcome == UNCHANGED:
            reports.append({"law_ref_id": law_ref_id, "status": "UNCHANGED"})
            continue

        reports.append({
            "law_ref_id": law_ref_id,
            "status": "REVISION_DETECTED",
            "affected_rules": affected_rules(law_ref_id),
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
        try:
            fetched = fetch_from_api(args.fetch)
        except (RuntimeError, NotImplementedError) as exc:
            raise SystemExit(f"[수집 불가] {args.fetch}: {exc}") from None
        try:
            print(f"{args.fetch}: {apply_fetch(args.fetch, fetched)}")
        except (KeyError, ValueError, LawMismatchError) as exc:
            raise SystemExit(f"[적용 중단] {exc}") from None
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
