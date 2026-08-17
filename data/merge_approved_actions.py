# -*- coding: utf-8 -*-
"""승인된 `actions` 3건을 정본에 병합한다 (M1, MQ-919) — 멱등 재실행 가능.

입력 : data/extracted/error_codes.json (정본, 65 entries)
       data/extracted/error_codes_actions.candidate.json (후보, 사람 승인 완료 — TODO_직접할일.md)
출력 : data/extracted/error_codes.json — `actions`·`actions_manual_id`·`actions_page`
       **3필드만** 갱신한다. 다른 필드는 절대 건드리지 않는다(아래 해시 대조가 그것을 증명한다).
       data/extracted/ig5a_action_map.json — `_status` 를 mappings/pending_review 건수에서
       동적으로 유도해 갱신한다(D19 태도 — 손으로 문자열을 쓰지 않는다).

🔴 이 스크립트는 `extract_error_codes.write_canonical()` 을 재사용하지 않는다 — 그 함수는
   "정본 내용이 달라지면 무조건 쓰지 않고 exit 1(사람이 판단)" 이 설계 의도라, **의도적으로
   승인된 변경을 실제로 기록하는 것**은 그 함수의 책임이 아니다(D99). `is_draft_status()`
   와 `canonical_payload()` 는 재구현하지 않고 그대로 가져와 쓴다.

승인 목록은 후보 파일 전체가 아니라 **TODO_직접할일.md `## actions 검수` 절의 사람 승인
기록**을 정본으로 삼아 `APPROVED` 상수에 하드코딩한다 — 후보 파일에 더 많은 항목이 들어와도
승인되지 않은 항목은 병합하지 않는다(엣지케이스: 일부만 승인).

병합 전후 안전장치 (핵심):
  1. 병합 **전** 65건 전체에서 `actions`·`actions_manual_id`·`actions_page` **3필드를
     제외한** 나머지 전부를 정준 직렬화해 sha256 해시를 65건 계산해 둔다.
  2. `APPROVED` 의 3건만 그 3필드를 후보 값으로 덮어쓴다.
  3. 병합 **후** 같은 방식으로 65건 해시를 다시 계산해 **전건 대조**한다.
     하나라도 다르면 (버그로 다른 필드가 건드려졌다는 뜻이므로) **파일을 쓰지 않고 중단**한다.

재실행 안전성: 승인된 3건의 3필드가 이미 후보값과 같으면 "변경 없음"으로 안전하게 종료하고
정본을 다시 쓰지 않는다.

사용:
    uv run python data/merge_approved_actions.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent  # data/
sys.path.insert(0, str(ROOT.parent))

from data.extract_error_codes import canonical_payload, diff_summary, is_draft_status  # noqa: E402

EXTRACTED = ROOT / "extracted"
CANONICAL = EXTRACTED / "error_codes.json"
CANDIDATE = EXTRACTED / "error_codes_actions.candidate.json"
ACTION_MAP = EXTRACTED / "ig5a_action_map.json"

# 사람 승인 기록 (TODO_직접할일.md `## actions 검수` 절, 2026-08-17 사용자 최종 승인 G1·G2).
# 후보 파일 전체를 무조건 병합하지 않는다 — 이 목록에 있는 것만 병합한다.
APPROVED: list[tuple[str, str]] = [
    ("iG5A", "RERR"),
    ("iG5A", "ETB"),
    ("S100", "FANW"),
]

ACTION_FIELDS = ("actions", "actions_manual_id", "actions_page")
MERGE_MARKER = "actions 3건 병합"


def _entry_hash(entry: dict) -> str:
    """`actions`·`actions_manual_id`·`actions_page` 를 제외한 필드의 정준 해시."""
    body = {k: v for k, v in entry.items() if k not in ACTION_FIELDS}
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _by_key(entries: list[dict]) -> dict[tuple[str, str], dict]:
    return {(e["model"], e["code"]): e for e in entries}


def merge_error_codes() -> bool:
    """정본에 승인 3건을 병합한다. 실제로 파일을 썼으면 True, 변경이 없어 생략했으면 False."""
    if not CANONICAL.exists():
        raise SystemExit(f"[중단] 정본이 없습니다 — {CANONICAL}")
    if not CANDIDATE.exists():
        raise SystemExit(f"[중단] 후보 파일이 없습니다 — {CANDIDATE}")

    cand = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    cand_status = str(cand.get("_status", ""))
    if not cand_status.startswith("승인 완료"):
        raise SystemExit(
            f"[중단] 후보 파일 _status 가 '승인 완료' 로 시작하지 않습니다 — 병합하지 않았다"
            f" (_status={cand_status!r})"
        )

    raw_text = CANONICAL.read_text(encoding="utf-8")
    prev = json.loads(raw_text)  # 병합 전 스냅샷 — 절대 mutate 하지 않는다 (비교용)
    out = json.loads(raw_text)  # 작업 사본 — 이것만 고친다

    prev_entries = prev.get("entries") or []
    out_entries = out.get("entries") or []
    if len(prev_entries) != 65 or len(out_entries) != 65:
        raise SystemExit(
            f"[중단] 정본 entries 가 65건이 아닙니다 (실측 {len(out_entries)}) — 병합하지 않았다"
        )

    cand_by_key = _by_key(cand.get("entries") or [])
    for key in APPROVED:
        if key not in cand_by_key:
            raise SystemExit(f"[중단] 승인 목록 {key} 가 후보 파일에 없습니다 — 방어적 중단")

    # 🔴 병합 전 해시 (65건 전체, 비-actions 필드)
    before_hashes = {key: _entry_hash(e) for key, e in _by_key(prev_entries).items()}
    if len(before_hashes) != 65:
        raise SystemExit(
            "[중단] (model,code) 키 중복 의심 — "
            f"entries {len(prev_entries)}건인데 고유 키 {len(before_hashes)}건"
        )
    for key in APPROVED:
        if key not in before_hashes:
            raise SystemExit(f"[중단] 승인 목록 {key} 가 정본에 없습니다 — 방어적 중단")

    # 병합 적용 — 승인된 3건의 3필드만 덮어쓴다. 다른 필드·다른 엔트리는 건드리지 않는다.
    out_by_key = _by_key(out_entries)
    changed_keys: list[tuple[str, str]] = []
    for key in APPROVED:
        target = out_by_key[key]
        source = cand_by_key[key]
        before_vals = tuple(target.get(f) for f in ACTION_FIELDS)
        after_vals = tuple(source.get(f) for f in ACTION_FIELDS)
        if before_vals != after_vals:
            changed_keys.append(key)
        for f in ACTION_FIELDS:
            target[f] = source.get(f)

    # 🔴 병합 후 해시 재계산 — 65건 전체가 병합 전과 동일해야 한다(actions 3필드는 제외했으므로
    #    구조적으로 항상 같아야 정상이다 — 다르면 위 로직이 다른 필드를 건드렸다는 뜻이다).
    after_hashes = {key: _entry_hash(e) for key, e in _by_key(out_entries).items()}
    mismatched = [k for k in before_hashes if before_hashes[k] != after_hashes.get(k)]
    matched = len(before_hashes) - len(mismatched)
    print(f"[해시 대조] 비-actions 필드 65건 중 {matched}건 일치 · 불일치 {len(mismatched)}건")
    if mismatched:
        print(f"[중단] 해시 불일치 {mismatched} — 정본을 쓰지 않았다.")
        raise SystemExit(1)

    if changed_keys:
        print(f"[병합 대상] {len(changed_keys)}건 필드 변경 예정: {changed_keys}")
        for key in changed_keys:
            e = out_by_key[key]
            print(
                f"  {key[0]} {key[1]}: actions_manual_id={e['actions_manual_id']!r}"
                f" actions_page={e['actions_page']!r} actions={e['actions']!r}"
            )
    else:
        print("[병합 대상 없음] 승인된 3건이 이미 후보값과 같습니다.")

    # _status 갱신 — 마커가 이미 있으면 중복 추가하지 않는다 (멱등)
    prev_status = str(prev.get("_status", ""))
    if MERGE_MARKER in prev_status:
        new_status = prev_status
    else:
        new_status = f"{prev_status} · {MERGE_MARKER} (2026-08-17, MQ-919, TODO_직접할일.md 승인 완료)"
    out["_status"] = new_status
    out["generated_at"] = str(date.today())

    if is_draft_status(out["_status"]):
        raise SystemExit(
            f"[중단] 신규 _status 가 초안 마커를 포함합니다 — 정본을 쓰지 않았다: {out['_status']!r}"
        )

    if canonical_payload(prev) == canonical_payload(out):
        print(f"[변경 없음] 기록 생략 — {CANONICAL}")
        print(
            f"  generated_at {prev.get('generated_at')!r} → {out.get('generated_at')!r} "
            "만 다르다. 내용이 같으면 쓰지 않는다 (D99 태도)"
        )
        return False

    print("[변경 요약]")
    for line in diff_summary(prev, out):
        print(line)

    CANONICAL.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[기록] {CANONICAL} — actions {len(changed_keys)}건 병합 완료 (entries 65건 불변)")
    return True


def update_action_map() -> None:
    """`ig5a_action_map.json` 의 `_status` 를 mappings/pending_review 실측에서 동적으로 유도한다.

    무작정 "승인 완료" 로 바꾸지 않는다 — `pending_review` 가 남아 있는 한 "부분 반영"이다
    (D19 태도: `ig5a_approval_status()` 와 같은 패턴, 하드코딩 낙관 문구 금지).
    """
    if not ACTION_MAP.exists():
        print(f"[경고] {ACTION_MAP} 가 없습니다 — _status 갱신을 건너뜁니다")
        return

    doc = json.loads(ACTION_MAP.read_text(encoding="utf-8"))
    n_mappings = len(doc.get("mappings") or [])
    n_pending = len(doc.get("pending_review") or [])
    today = str(date.today())

    new_status = (
        f"부분 반영 ({today}) — mappings {n_mappings}건 정본 병합 완료(MQ-919) · "
        f"pending_review {n_pending}건 미해결 — 전부 해결돼야 완전 승인"
    )
    prev_status = str(doc.get("_status", ""))
    if prev_status == new_status:
        print(f"[변경 없음] {ACTION_MAP} _status 동일 — 기록 생략")
        return

    doc["_status"] = new_status
    ACTION_MAP.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[기록] {ACTION_MAP} _status → {new_status!r}")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    print(f"승인 목록 (TODO_직접할일.md 2026-08-17 승인): {APPROVED}\n")
    merge_error_codes()
    print()
    update_action_map()


if __name__ == "__main__":
    main()
