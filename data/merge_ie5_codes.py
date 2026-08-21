# -*- coding: utf-8 -*-
"""IE5 트립 코드 5건을 정본에 병합한다 (M1, Sprint 15 MQ-1507) — 멱등 재실행 가능.

입력 : data/extracted/error_codes.json (정본, 65 entries)
       data/extracted/ie5_code_candidates.json (후보, 사람 승인 완료 — 2026-08-20)
출력 : data/extracted/error_codes.json — `entries` 에 IE5 5건을 **추가**한다
       (65 → 70). 기존 65건은 어떤 필드도 건드리지 않는다 — `merge_approved_actions.py`
       가 "3필드만 덮어쓰기"를 해시로 증명하는 것과 달리, 이 스크립트는 **행 추가**라
       기존 65건을 새 오브젝트로 다시 파싱해(`prev`/`out` 이중 로드) 참조를 섞지 않는다.
       data/extracted/ie5_code_candidates.json — `_status` 에 병합 완료 사실을 덧붙이고
       (기존 문구는 지우지 않는다), `_source.manifest_registered` 를 true 로 갱신한다.
       이 두 필드 외에는 후보 파일의 어떤 키도 건드리지 않는다.

🔴 이 스크립트는 `extract_error_codes.write_canonical()` 을 재사용하지 않는다 — 그 함수는
   "정본 내용이 달라지면 무조건 쓰지 않고 exit 1(사람이 판단)" 이 설계 의도라, 신규 행
   추가라는 **의도된 변경**을 실제로 기록하는 것은 그 함수의 책임이 아니다(D99).
   `is_draft_status()`·`canonical_payload()`·`diff_summary()` 는 재구현하지 않고
   그대로 가져와 쓴다.

병합 대상은 후보 파일 전체가 아니라 `codes` 배열 5건(사람이 이미 검수 완료, `_status`
가 '승인 완료' 로 시작하는지로 확인)이다 — `_unmatched.codes`·`_unmatched.names`·
`_unmatched.codes_excluded_by_shape`·`_unmatched.codes_without_name` 은 검수 대상이
아니었으므로 병합하지 않는다(엣지케이스: 일부만 승인).

매핑 (data/extracted/ie5_code_candidates.json `codes[]` → 정본 신규 행, D25·D100):
  model              = "IE5"
  code               = canonical_code (대문자, D25)
  display_code       = display_code (원표기 그대로)
  error_name         = name_ko
  severity           = "fault" (표에 상태 마커 없음 — iG5A 관행과 동일하게 고정)
  causes             = cause 그대로
  actions            = action 그대로
  related_parts      = [] (IE5 부품 매핑 데이터 없음 — 지어내지 않는다, D12)
  manual_page        = manual_page (125 또는 126)
  actions_manual_id  = null (원인·조치가 같은 표·같은 페이지 — 별도 출처 추적 불필요, D100)
  actions_page       = null
  source             = "IE5 표준판 13장 이상 대책 및 점검표(p125-126) + 본문 괄호 코드(D107)"

병합 전후 안전장치:
  1. 병합 **전** 정본 entries 가 정확히 65건이어야 진행한다(사전 조건 ①). 신규 5건이
     이미 전부 동일 내용으로 들어가 있으면(재실행) 65+5=70건 상태를 별도로 인식해
     "변경 없음" 으로 안전 종료한다 — 65 도 아니고 이 정확한 70 도 아니면(부분 병합·
     다른 변경 혼입 의심) **추측하지 않고 중단**한다.
  2. (model, code) 키 중복 검사 — 신규 5건 내부 중복 + 기존 65건과의 중복을
     방어적으로 assert 한다(모두 model="IE5" 라 구조적으로 안 겹치지만 확인은 한다).
  3. `_status` 되돌림(초안 마커 유입) 을 `is_draft_status()` 로 막는다 — 정본·후보
     양쪽 모두. 걸리면 **쓰지 않고** exit 2 (D99, 65→0행 사고 재발 방지와 같은 계열).
  4. 내용이 이미 같으면(`canonical_payload` 동등) 정본을 다시 쓰지 않는다.

사용:
    uv run python data/merge_ie5_codes.py

⚠ 이 스크립트는 `data/seed.py`·스파이크 회귀를 실행하지 않는다 — 다음 태스크(MQ-1508)가
  이 결과의 정확한 개수를 실측해서 그 태스크에서 처리한다.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent  # data/
sys.path.insert(0, str(ROOT.parent))

from data.extract_error_codes import canonical_payload, diff_summary, is_draft_status  # noqa: E402

EXTRACTED = ROOT / "extracted"
CANONICAL = EXTRACTED / "error_codes.json"
CANDIDATE = EXTRACTED / "ie5_code_candidates.json"

SOURCE_TEXT = "IE5 표준판 13장 이상 대책 및 점검표(p125-126) + 본문 괄호 코드(D107)"
CANON_MERGE_MARKER = "IE5 5건 정본 병합 완료"
CAND_MERGE_MARKER = "IE5 5건 정본 병합 완료"
MERGE_DATE_TAG = "2026-08-21, MQ-1507"
N_EXPECTED = 5


def build_ie5_entries(cand_codes: list[dict]) -> list[dict]:
    """후보 파일 `codes[]` → 정본 신규 행. 필드명·값은 모듈 docstring의 매핑표와 정확히 같다."""
    out = []
    for c in cand_codes:
        out.append(
            {
                "model": "IE5",
                "code": c["canonical_code"],
                "display_code": c["display_code"],
                "error_name": c["name_ko"],
                "severity": "fault",
                "causes": c["cause"],
                "actions": c["action"],
                "related_parts": [],
                "manual_page": c["manual_page"],
                "actions_manual_id": None,
                "actions_page": None,
                "source": SOURCE_TEXT,
            }
        )
    return out


def _by_key(entries: list[dict]) -> dict[tuple, dict]:
    return {(e.get("model"), e.get("code")): e for e in entries}


def merge_error_codes() -> bool:
    """정본에 IE5 5건을 병합한다. 실제로 파일을 썼으면 True, 이미 반영돼 생략했으면 False."""
    if not CANONICAL.exists():
        raise SystemExit(f"[중단] 정본이 없습니다 — {CANONICAL}")
    if not CANDIDATE.exists():
        raise SystemExit(f"[중단] 후보 파일이 없습니다 — {CANDIDATE}")

    cand = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    cand_status = str(cand.get("_status", ""))
    if not cand_status.startswith("승인 완료"):
        print(
            f"[중단] 후보 파일 _status 가 '승인 완료' 로 시작하지 않습니다 — 병합하지 않았다"
            f" (_status={cand_status!r})"
        )
        raise SystemExit(1)

    cand_codes = cand.get("codes") or []
    if len(cand_codes) != N_EXPECTED:
        print(
            f"[중단] 후보 codes 배열이 {N_EXPECTED}건이 아닙니다 "
            f"(실측 {len(cand_codes)}) — 병합하지 않았다"
        )
        raise SystemExit(1)

    new_entries = build_ie5_entries(cand_codes)
    new_keys = [(e["model"], e["code"]) for e in new_entries]
    if len(set(new_keys)) != N_EXPECTED:
        print(f"[중단] 신규 {N_EXPECTED}건 내부에 (model,code) 중복이 있습니다 — {new_keys}")
        raise SystemExit(1)

    raw_text = CANONICAL.read_text(encoding="utf-8")
    prev = json.loads(raw_text)  # 병합 전 스냅샷 — 절대 mutate 하지 않는다 (비교용)
    out = json.loads(raw_text)  # 작업 사본 — 이것만 고친다 (별도 파싱이라 참조가 안 섞인다)

    prev_entries = prev.get("entries") or []
    existing_keys = {(e.get("model"), e.get("code")) for e in prev_entries}
    new_key_set = set(new_keys)
    overlap = new_key_set & existing_keys

    if overlap == new_key_set:
        # 재실행 — IE5 5건이 이미 전부 정본에 있다. 개수·내용이 정확히 일치해야
        # "변경 없음" 이다. 대충 넘어가면 부분 손상·다른 변경 혼입을 놓친다.
        if len(prev_entries) != 65 + N_EXPECTED:
            print(
                f"[중단] IE5 {N_EXPECTED}건이 이미 존재하지만 entries 총합이 "
                f"{65 + N_EXPECTED}건이 아닙니다 (실측 {len(prev_entries)}) — "
                "추측하지 않고 중단한다"
            )
            raise SystemExit(1)
        by_key = _by_key(prev_entries)
        mismatched = [k for k in new_keys if by_key.get(k) != _by_key(new_entries).get(k)]
        if mismatched:
            print(
                f"[중단] IE5 코드가 이미 존재하나 내용이 후보와 다릅니다 — {mismatched} "
                "— 방어적 중단(수기 편집 의심)"
            )
            raise SystemExit(1)
        print(f"[변경 없음] IE5 {N_EXPECTED}건이 이미 정본에 동일하게 존재합니다 — 기록 생략")
        return False

    if overlap:
        print(
            f"[중단] IE5 코드가 일부만 이미 정본에 존재합니다(부분 상태) — {sorted(overlap)} "
            "— 방어적 중단"
        )
        raise SystemExit(1)

    # 부분 겹침도 아니고 전부 겹침도 아니다 = 신규 병합. 사전 조건 ①: 정확히 65건.
    if len(prev_entries) != 65:
        print(
            f"[중단] 정본 entries 가 65건이 아닙니다 (실측 {len(prev_entries)}) — "
            "병합하지 않았다(다른 변경이 먼저 들어간 것일 수 있음 — 추측하지 않는다)"
        )
        raise SystemExit(1)

    out_entries = list(out.get("entries") or [])
    out_entries.extend(new_entries)
    out["entries"] = out_entries

    counts = dict(out.get("counts") or {})
    counts["IE5"] = N_EXPECTED
    out["counts"] = counts

    prev_status = str(prev.get("_status", ""))
    if CANON_MERGE_MARKER in prev_status:
        new_status = prev_status
    else:
        new_status = f"{prev_status} · {CANON_MERGE_MARKER} (OCT·IOL·OHT·OVT·LVT, {MERGE_DATE_TAG})"
    out["_status"] = new_status
    out["generated_at"] = str(date.today())

    if is_draft_status(out["_status"]):
        print(f"[중단] 신규 _status 가 초안 마커를 포함합니다 — 정본을 쓰지 않았다: {out['_status']!r}")
        raise SystemExit(2)

    if canonical_payload(prev) == canonical_payload(out):
        print(f"[변경 없음] 기록 생략 — {CANONICAL}")
        return False

    print("[변경 요약]")
    for line in diff_summary(prev, out):
        print(line)

    CANONICAL.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[기록] {CANONICAL} — IE5 {N_EXPECTED}건 병합 완료 (entries {len(prev_entries)} → {len(out_entries)})")
    return True


def update_candidate_after_merge() -> None:
    """후보 파일의 `_status`·`_source.manifest_registered` 만 갱신한다 (그 외 키는 손대지 않는다).

    두 필드 모두 이미 반영돼 있으면 아무것도 쓰지 않는다(멱등). 병합 성공 여부와
    무관하게 호출한다 — 이전 실행이 정본만 쓰고 이 갱신 전에 중단됐던 경우에도
    다음 실행에서 스스로 따라잡는다.
    """
    if not CANDIDATE.exists():
        print(f"[경고] {CANDIDATE} 가 없습니다 — 후보 파일 갱신을 건너뜁니다")
        return

    doc = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    changed = False

    prev_status = str(doc.get("_status", ""))
    if CAND_MERGE_MARKER not in prev_status:
        new_status = f"{prev_status} · {CAND_MERGE_MARKER} ({MERGE_DATE_TAG})"
        if is_draft_status(new_status):
            print(f"[중단] 후보 파일 신규 _status 가 초안 마커를 포함합니다 — 쓰지 않았다: {new_status!r}")
            raise SystemExit(2)
        doc["_status"] = new_status
        changed = True

    source = dict(doc.get("_source") or {})
    if source.get("manifest_registered") is not True:
        source["manifest_registered"] = True
        doc["_source"] = source
        changed = True

    if not changed:
        print(f"[변경 없음] {CANDIDATE} — _status·manifest_registered 이미 갱신됨")
        return

    CANDIDATE.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[기록] {CANDIDATE} — _status 갱신 · _source.manifest_registered=True")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    print(f"IE5 트립 코드 병합 대상: {N_EXPECTED}건 (OCT·IOL·OHT·OVT·LVT, MQ-1507)\n")
    merge_error_codes()
    print()
    update_candidate_after_merge()


if __name__ == "__main__":
    main()
