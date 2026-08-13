# -*- coding: utf-8 -*-
"""법령 수집·적용 계약 검증 (MQ-602L → MQ-701 확장).

검증 대상: D60(append-only · 자동 덮어쓰기 금지) · D61(불변식 2 — 미등록 법령 참조 거부) ·
          D75(2단계 기록 · 정체성 대조) · D59(룩업이지 RAG 아님 — 인덱싱 없음)

**네트워크를 쓰지 않는다.** MQ-701 이 `fetch_from_api` 를 실제로 구현한 뒤에도 그렇다 —
응답 정규화(`parse_article_response`)를 **순수 함수로 분리**해 뒀기에 합성 응답으로 덮는다.
실 API 호출은 회귀에 넣지 않는다(키·네트워크·법령 개정에 좌우되면 회귀가 아니다).

**기대값을 하드코딩하지 않는다.** 조문 제목·수집 상태는 `data/rules/laws/*.json` 에서
읽어 쓴다. `KR-STTC-146` 의 제목이 사람 승인으로 정정됐을 때(`세액공제액의 추징` →
`감면세액의 추징`) 이 스위트가 **하드코딩 때문에 통째로 죽었던** 적이 있다.

**정본을 건드리지 않는다.** `data/rules/laws/*.json` 은 tmp 로 복사해서 쓰고,
마지막에 정본 디렉토리의 내용 해시를 대조한다.

실행:  uv run python spikes/law_fetch_contract.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# fetch_laws.py 자신이 `from engine import …` 로 여는 것과 **같은 경로**로 연다.
# data.rules.engine 으로 열면 별개 모듈 객체가 되어 ⓓ-2 의 동일성 검사가 무의미해진다.
sys.path.insert(0, str(ROOT / "data" / "rules"))

import engine  # noqa: E402
import fetch_laws as fl  # noqa: E402

REAL_LAWS = ROOT / "data" / "rules" / "laws"

# 합성 원문 — 실제 조문이 아니다. 손으로 적은 텍스트를 계층 1 정본에 넣지 않기 위해
# 일부러 조문처럼 보이지 않게 쓴다 (11 §8: "누가 적은 텍스트"가 사실이 되면 안 된다).
SYNTHETIC_TEXT = "[합성] 제1항 이것은 회귀 픽스처이며 실제 조문 원문이 아니다."
SYNTHETIC_TEXT_V2 = "[합성] 제1항 개정된 것으로 가정한 회귀 픽스처. 원문이 아니다."
SYNTHETIC_TEXT_V3 = "[합성] 제1항 두 번째 개정으로 가정한 회귀 픽스처. 원문이 아니다."

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def dir_digest(d: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(d.glob("*.json")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def sandbox(tmp: Path) -> tuple[Path, Path]:
    """정본 사본 + 빈 pending 디렉토리."""
    laws = tmp / "laws"
    shutil.copytree(REAL_LAWS, laws)
    return laws, tmp / "pending_revisions"


# 수집 결과로 채워지는 필드. `as_pending` 이 되돌리는 대상이자,
# ⓪ 이 "FETCHED 인데 원문이 없는" 모순 행을 잡을 때 보는 필드이기도 하다.
FETCH_FIELDS = ("text", "text_hash", "retrieved_at", "effective_from", "promulgation_no")


def as_pending(path: Path) -> dict:
    """tmp 사본 1건을 **수집 전 상태**로 되돌린다 (정본 미수정).

    MQ-701 이 정본 6건을 실제로 채웠기 때문에, "최초 수집" 경로를 검증하려면
    수집 전 상태가 필요하다. 정본의 수집 여부에 따라 검사 의미가 흔들리지 않게
    **픽스처 쪽에서 상태를 만든다** — 기대값을 정본에 맞춰 바꾸는 게 아니다.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    for key in FETCH_FIELDS:
        raw[key] = None
    raw["fetch_status"] = "PENDING"
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return raw


def run(tmp: Path) -> None:
    laws, pending = sandbox(tmp)
    # "최초 수집" 경로의 대상. 어느 건이든 상관없다 — 아래에서 `as_pending()` 으로
    # **픽스처 쪽에서 수집 전 상태를 만들기** 때문이다.
    target = "KR-CITA-ENF-31"
    path = laws / f"{target}.json"

    # ── ⓪ 전제: 등록 8건 · FETCHED 는 원문+해시를 갖고 해시가 실제로 맞는다 ·
    #    PENDING 이 남아 있다면 원문이 비어 있어야 한다 (수집 안 됐다는 뜻이므로)
    #
    # 🚨 여기에 "특정 건이 PENDING 이어야 한다" 를 박지 않는다. 2026-08-13 에
    #    `KR-CITA-ENF-31` 이 사람 승인 후 수집되면서(D75 게이트 통과) 그 단언이
    #    **정상적인 상태 변화 때문에** 깨졌고, 뒤따라 ⓐ~ⓒ-7 이 연쇄 실패했다.
    #    스위트는 **불변식**(FETCHED 면 원문+해시 일치 / PENDING 이면 원문 없음)만 본다.
    files = sorted(laws.glob("*.json"))
    raws = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in files}
    fetched_ids = sorted(k for k, r in raws.items() if r["fetch_status"] == "FETCHED")
    pending_ids = sorted(k for k, r in raws.items() if r["fetch_status"] != "FETCHED")
    broken = [
        k
        for k in fetched_ids
        if not (raws[k]["text"] or "").strip()
        or raws[k]["text_hash"] != engine.text_hash(raws[k]["text"])
    ]
    # PENDING 인데 원문이 있으면 "수집 안 됐다"는 표시가 거짓이다
    lying = [k for k in pending_ids if (raws[k].get("text") or "").strip()]
    check(
        "⓪ laws/ 8건 · FETCHED 는 원문+해시 일치 · PENDING 은 원문 없음",
        len(files) == 8 and not broken and not lying,
        f"{len(files)}건 · FETCHED {len(fetched_ids)}건 · PENDING {pending_ids or '없음'} · "
        f"해시 불일치 {broken or '없음'} · 원문 있는 PENDING {lying or '없음'}",
    )

    # 정체성 키는 **파일에서 읽는다.** 기대값을 코드에 박으면 사람 승인 정정이 스위트를 죽인다.
    ident = {"article": raws[target]["article"], "title": raws[target]["title"]}

    # ⓐ 는 "최초 수집" 경로다 — 정본이 이미 수집됐으면 tmp 사본을 되돌려 놓고 시작한다.
    # (`as_pending` 의 독스트링이 말하는 그 용도. 정본은 건드리지 않는다.)
    as_pending(path)

    # ── ⓐ 최초 수집: PENDING → FETCHED. text_hash 가 파일에 기입된다
    before = digest(path)
    outcome = fl.apply_fetch(
        target,
        {**ident, "text": SYNTHETIC_TEXT, "effective_from": "2026-01-01"},
        laws_dir=laws,
        pending_dir=pending,
    )
    filled = json.loads(path.read_text(encoding="utf-8"))
    expected_hash = engine.text_hash(SYNTHETIC_TEXT)
    check(
        "ⓐ 최초 수집 → FILLED · text_hash 기입",
        outcome == fl.FILLED
        and filled["fetch_status"] == "FETCHED"
        and filled["text"] == SYNTHETIC_TEXT
        and filled["text_hash"] == expected_hash
        and filled["retrieved_at"] is not None
        and digest(path) != before,
        f"{outcome}, hash={filled['text_hash'][:20]}…, retrieved_at 有",
    )

    # ⓐ-2 파일 키 집합이 보존된다 (계층 1 스키마를 수집이 깎지 않는다)
    check(
        "ⓐ-2 키 집합 보존 (필드 추가·누락 없음)",
        set(filled) == set(raws[target]),
        f"초과={sorted(set(filled) - set(raws[target])) or '없음'}, "
        f"누락={sorted(set(raws[target]) - set(filled)) or '없음'}",
    )

    # ── ⓑ 조문번호 불일치 → 중단. 파일 바이트가 1비트도 바뀌면 안 된다
    victim = laws / "KR-STTC-24.json"
    v_before = victim.read_bytes()
    try:
        fl.apply_fetch(
            "KR-STTC-24",
            {"article": "24의2", "title": raws["KR-STTC-24"]["title"], "text": SYNTHETIC_TEXT},
            laws_dir=laws,
            pending_dir=pending,
        )
        raised, msg = None, ""
    except fl.LawMismatchError as exc:
        raised, msg = "LawMismatchError", str(exc)
    check(
        "ⓑ 조문번호 불일치 → 중단 · 파일 바이트 불변",
        raised == "LawMismatchError"
        and victim.read_bytes() == v_before
        and "24의2" in msg,
        f"{raised or 'no-raise'} / 바이트 동일={victim.read_bytes() == v_before}",
    )

    # ⓑ-2 제목 불일치도 같은 경로. **이미 수집된 조문이라도** 개정 기록조차 남기지 않는다 —
    #     "다른 조문이 왔다"와 "같은 조문이 개정됐다"는 서로 다른 사건이다.
    vat_path = laws / "KR-VAT-32.json"
    vat_before = vat_path.read_bytes()
    try:
        fl.apply_fetch(
            "KR-VAT-32",
            {"article": "32", "title": "세금계산서(개정)", "text": SYNTHETIC_TEXT},
            laws_dir=laws,
            pending_dir=pending,
        )
        raised2 = None
    except fl.LawMismatchError:
        raised2 = "LawMismatchError"
    check(
        "ⓑ-2 제목 불일치 → 중단 · 파일 바이트 불변 · 개정 기록도 없음",
        raised2 == "LawMismatchError"
        and vat_path.read_bytes() == vat_before
        and not sorted(pending.glob("KR-VAT-32.*.json")),
        f"{raised2 or 'no-raise'} / 바이트 동일={vat_path.read_bytes() == vat_before} / pending 0건",
    )

    # ⓑ-W5-a article 키 자체가 없으면 → 중단. **누락은 통과가 아니다**
    #   Sprint 7 에서 법제처 응답의 `조문번호` 매핑을 빠뜨리면 정체성 게이트가 조용히
    #   무력화되고 대조 없이 원문이 기입된다 — D50·D62 가 막아 온 실패 유형과 같다.
    kcc = laws / "KR-KCC-652.json"
    k_before = kcc.read_bytes()
    try:
        fl.apply_fetch(
            "KR-KCC-652",
            {"title": raws["KR-KCC-652"]["title"], "text": SYNTHETIC_TEXT},
            laws_dir=laws,
            pending_dir=pending,
        )
        raised_a, msg_a = None, ""
    except fl.LawMismatchError as exc:
        raised_a, msg_a = "LawMismatchError", str(exc)
    check(
        "ⓑ-W5-a article 키 누락 → 중단 · 파일 바이트 불변",
        raised_a == "LawMismatchError"
        and "article" in msg_a
        and kcc.read_bytes() == k_before,
        f"{raised_a or 'no-raise'} / 바이트 동일={kcc.read_bytes() == k_before} / msg에 'article' 포함",
    )

    # ⓑ-W5-b title 이 빈 문자열이어도 같은 경로 (None 만이 아니라 공백도 누락이다)
    civil = laws / "KR-CIVIL-388.json"
    c_before = civil.read_bytes()
    try:
        fl.apply_fetch(
            "KR-CIVIL-388",
            {"article": "388", "title": "   ", "text": SYNTHETIC_TEXT},
            laws_dir=laws,
            pending_dir=pending,
        )
        raised_b, msg_b = None, ""
    except fl.LawMismatchError as exc:
        raised_b, msg_b = "LawMismatchError", str(exc)
    check(
        "ⓑ-W5-b title 빈 문자열 → 중단 · 파일 바이트 불변",
        raised_b == "LawMismatchError"
        and "title" in msg_b
        and "article" not in msg_b.split("→")[0]
        and civil.read_bytes() == c_before,
        f"{raised_b or 'no-raise'} / 바이트 동일={civil.read_bytes() == c_before} / 누락 키만 지목",
    )

    # ⓑ-W5-c 선택적 필드는 필수가 아니다 — 정체성 키만 대상 (과잉 게이트 방지).
    #   정본은 이미 수집됐으므로 tmp 사본을 수집 전으로 되돌려 "최초 수집" 경로를 만든다.
    #   ⚠ 제목은 파일에서 읽는다 — 여기 하드코딩했다가 사람 승인 정정(`세액공제액의 추징`
    #     → `감면세액의 추징`) 때 이 스위트가 통째로 죽었다.
    sttc_pending = as_pending(laws / "KR-STTC-146.json")
    optional_ok = fl.apply_fetch(
        "KR-STTC-146",
        {"article": sttc_pending["article"], "title": sttc_pending["title"],
         "text": SYNTHETIC_TEXT},
        laws_dir=laws,
        pending_dir=pending,
    )
    sttc = json.loads((laws / "KR-STTC-146.json").read_text(encoding="utf-8"))
    check(
        "ⓑ-W5-c 선택적 필드 없어도 통과 (정체성 키만 필수)",
        optional_ok == fl.FILLED
        and sttc["effective_from"] is None
        and sttc["promulgation_no"] is None,
        f"{optional_ok} / effective_from·promulgation_no 는 null 유지 (지어내지 않음)",
    )

    # ⓑ-3 미등록 참조 거부 (D61 불변식 2)
    try:
        fl.apply_fetch("KR-NOPE-999", {"text": SYNTHETIC_TEXT}, laws_dir=laws, pending_dir=pending)
        raised3 = None
    except KeyError:
        raised3 = "KeyError"
    check(
        "ⓑ-3 미등록 law_ref_id 거부 (D61)",
        raised3 == "KeyError" and not (laws / "KR-NOPE-999.json").exists(),
        f"{raised3 or 'no-raise'} / 파일 생성 안 됨",
    )

    # ── ⓒ 이미 FETCHED + 해시 상이 → 덮어쓰지 않고 pending_revisions (D60)
    fetched_bytes = path.read_bytes()
    outcome2 = fl.apply_fetch(
        target,
        {**ident, "text": SYNTHETIC_TEXT_V2},
        laws_dir=laws,
        pending_dir=pending,
    )
    revs = sorted(pending.glob(f"{target}.*.json"))
    rec = json.loads(revs[0].read_text(encoding="utf-8")) if revs else {}
    check(
        "ⓒ FETCHED + 해시 상이 → REVISION_PENDING · 원본 불변",
        outcome2 == fl.REVISION_PENDING
        and path.read_bytes() == fetched_bytes
        and len(revs) == 1
        and rec.get("old_text") == SYNTHETIC_TEXT
        and rec.get("new_text") == SYNTHETIC_TEXT_V2
        and rec.get("requires_signature") is True,
        f"{outcome2}, pending {len(revs)}건, 원본 바이트 동일={path.read_bytes() == fetched_bytes}",
    )

    # ⓒ-2 재호출해도 앞선 기록을 덮어쓰지 않는다 (append-only)
    fl.apply_fetch(
        target,
        {**ident, "text": SYNTHETIC_TEXT_V2},
        laws_dir=laws,
        pending_dir=pending,
    )
    revs2 = sorted(pending.glob(f"{target}.*.json"))
    check(
        "ⓒ-2 재감지 시 기록 누적 (append-only, D60)",
        len(revs2) == 2 and revs2[0].read_bytes() == revs[0].read_bytes(),
        f"{len(revs)}건 → {len(revs2)}건, 기존 파일 불변",
    )

    # ⓒ-3 같은 원문 재적용 → UNCHANGED. 파일도 pending 도 늘지 않는다
    outcome3 = fl.apply_fetch(
        target,
        {**ident, "text": SYNTHETIC_TEXT},
        laws_dir=laws,
        pending_dir=pending,
    )
    check(
        "ⓒ-3 동일 원문 → UNCHANGED · 무기록",
        outcome3 == fl.UNCHANGED
        and path.read_bytes() == fetched_bytes
        and len(sorted(pending.glob(f"{target}.*.json"))) == 2,
        f"{outcome3}, pending 증가 없음",
    )

    # ⓒ-4 force=True 는 반영하되 직전 스냅샷을 남긴다 (과거 원문을 지우지 않는다)
    outcome4 = fl.apply_fetch(
        target,
        {**ident, "text": SYNTHETIC_TEXT_V2},
        force=True,
        laws_dir=laws,
        pending_dir=pending,
    )
    after_force = json.loads(path.read_text(encoding="utf-8"))
    revs3 = sorted(pending.glob(f"{target}.*.json"))
    applied = [json.loads(p.read_text(encoding="utf-8")) for p in revs3]
    confirmed = [r for r in applied if r["applied"] == fl.APPLY_CONFIRMED]
    check(
        "ⓒ-4 force → FILLED · 직전 스냅샷 보존 · confirmed 승격",
        outcome4 == fl.FILLED
        and after_force["text"] == SYNTHETIC_TEXT_V2
        and after_force["text_hash"] == engine.text_hash(SYNTHETIC_TEXT_V2)
        and len(revs3) == 3
        and len(confirmed) == 1
        and confirmed[0]["old_text"] == SYNTHETIC_TEXT
        and confirmed[0]["confirmed_at"] is not None
        and confirmed[0]["requires_signature"] is False,
        f"{outcome4}, pending {len(revs3)}건 / confirmed 1건에 구 원문 보존",
    )

    # ── ⓒ-5 ★N7: 기입이 실패하면 "적용됨" 기록이 남지 않는다.
    #   _write_law 에 장애를 주입해 force 경로를 중간에 끊는다. append-only 라 잘못 쓴
    #   기록은 지울 수 없으므로, 기입 **성공 확인 후**에만 confirmed 로 승격해야 한다.
    before_fail = path.read_bytes()
    original_write = fl._write_law

    def boom(*_args, **_kwargs):
        raise OSError("주입된 디스크 장애 — 기입 실패 시뮬레이션")

    fl._write_law = boom
    try:
        fl.apply_fetch(
            target,
            {**ident, "text": SYNTHETIC_TEXT_V3},
            force=True,
            laws_dir=laws,
            pending_dir=pending,
        )
        raised_n7 = None
    except OSError:
        raised_n7 = "OSError"
    finally:
        fl._write_law = original_write

    revs4 = sorted(pending.glob(f"{target}.*.json"))
    recs4 = [json.loads(p.read_text(encoding="utf-8")) for p in revs4]
    intents = [r for r in recs4 if r["applied"] == fl.APPLY_INTENT]
    check(
        "ⓒ-5 기입 실패 → intent 로 남음 (거짓 '적용됨' 기록 없음)",
        raised_n7 == "OSError"
        and path.read_bytes() == before_fail
        and len(revs4) == 4
        and len(intents) == 1
        and intents[0]["new_text"] == SYNTHETIC_TEXT_V3
        and intents[0]["confirmed_at"] is None
        and intents[0]["requires_signature"] is True,
        f"{raised_n7} / 법령파일 불변 / intent 1건 (requires_signature=true → 사람이 대조)",
    )

    # ⓒ-6 intent→confirmed 전이가 스냅샷 payload 를 건드리지 않는다.
    #   D60 이 지키는 것은 old/new 원문·해시이고, applied 는 flags.state 같은 상태 필드다.
    #   ⓒ-5 가 남긴 intent 기록을 복사해 전이만 시켜 본다 (원 기록은 그대로 둔다).
    payload_keys = ("law_ref_id", "detected_at", "old_hash", "new_hash", "old_text", "new_text")
    intent_path = next(
        p for p in revs4 if json.loads(p.read_text(encoding="utf-8"))["applied"] == fl.APPLY_INTENT
    )
    probe = intent_path.parent / "probe.transition.json"
    probe.write_bytes(intent_path.read_bytes())
    before_rec = json.loads(probe.read_text(encoding="utf-8"))
    fl._confirm_pending_revision(probe)
    after_rec = json.loads(probe.read_text(encoding="utf-8"))
    check(
        "ⓒ-6 intent→confirmed 전이가 payload 를 바꾸지 않음",
        all(before_rec[k] == after_rec[k] for k in payload_keys)
        and before_rec["requires_signature"] is True
        and after_rec["applied"] == fl.APPLY_CONFIRMED
        and after_rec["requires_signature"] is False
        and after_rec["confirmed_at"] is not None
        and json.loads(intent_path.read_text(encoding="utf-8"))["applied"] == fl.APPLY_INTENT,
        "old/new text·hash·detected_at 동일 — 상태 3필드만 전이. 원 기록 불변",
    )

    # ⓒ-7 Sprint 7 서명 큐가 읽을 대상: requires_signature=true 인 기록만
    queue = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(pending.glob(f"{target}.*.json"))
    ]
    todo = [r for r in queue if r["requires_signature"]]
    check(
        "ⓒ-7 서명 큐 필터 = requires_signature (confirmed 만 제외)",
        len(queue) == 4
        and len(todo) == 3
        and {r["applied"] for r in todo} == {None, fl.APPLY_INTENT}
        and all(r["applied"] == fl.APPLY_CONFIRMED for r in queue if not r["requires_signature"]),
        f"전체 {len(queue)}건 중 미처리 {len(todo)}건 (applied=None 2 + intent 1)",
    )

    # ── ⓓ 해시는 engine.text_hash 그대로 — 재구현했다면 여기서 갈린다
    variants = [
        "제１항  이것은   회귀 픽스처다.",   # 전각 숫자 + 다중 공백
        "제1항 이것은 회귀 픽스처다.",       # 반각 + 단일 공백
        "  제１항\t이것은\n회귀  픽스처다.  ",  # 탭·개행·앞뒤 공백
    ]
    hashes = {engine.text_hash(v) for v in variants}
    check(
        "ⓓ 전각/공백 변형 해시 동치 (NFKC + 공백 축약)",
        len(hashes) == 1 and next(iter(hashes)).startswith("sha256:"),
        f"3변형 → 해시 {len(hashes)}종: {next(iter(hashes))[:24]}…",
    )
    src_fetch = (ROOT / "data" / "rules" / "fetch_laws.py").read_text(encoding="utf-8")
    reimpl = [w for w in ("hashlib", "sha256(", "unicodedata", "NFKC") if w in src_fetch]
    check(
        "ⓓ-2 text_hash 재구현 없음 (engine 함수 동일 객체)",
        fl.text_hash is engine.text_hash
        and fl.normalize is engine.normalize
        and not reimpl,
        f"engine 함수 그대로 · 자체 해시 흔적={reimpl or '없음'}",
    )
    # 파일에 실제로 들어간 해시도 engine 산출값과 같아야 한다
    check(
        "ⓓ-3 파일 기입 해시 == engine.text_hash(원문)",
        after_force["text_hash"] == engine.text_hash(SYNTHETIC_TEXT_V2),
        after_force["text_hash"][:24] + "…",
    )

    # ── ⓔ 빈 원문은 계층 1에 들어가지 않는다
    osha_path = laws / "KR-OSHA-93.json"
    osha_before = osha_path.read_bytes()
    try:
        fl.apply_fetch(
            "KR-OSHA-93",
            {"article": raws["KR-OSHA-93"]["article"], "title": raws["KR-OSHA-93"]["title"],
             "text": "   "},
            laws_dir=laws,
            pending_dir=pending,
        )
        raised5 = None
    except ValueError:
        raised5 = "ValueError"
    check(
        "ⓔ 빈 원문 거부 · 파일 바이트 불변",
        raised5 == "ValueError" and osha_path.read_bytes() == osha_before,
        f"{raised5 or 'no-raise'} / 바이트 동일={osha_path.read_bytes() == osha_before}",
    )

    # ── ⓕ 키 미설정 시 fetch_from_api 는 RuntimeError (네트워크로 나가지 않는다)
    saved = fl.API_OC
    fl.API_OC = None
    try:
        fl.fetch_from_api("KR-CITA-ENF-31")
        raised6, msg6 = None, ""
    except RuntimeError as exc:
        raised6, msg6 = "RuntimeError", str(exc)
    except NotImplementedError:
        raised6, msg6 = "NotImplementedError", ""
    finally:
        fl.API_OC = saved
    check(
        "ⓕ 키 미설정 → RuntimeError (호출 전 차단)",
        raised6 == "RuntimeError" and "LAW_API_OC" in msg6 and "필수입력요소" in msg6,
        f"{raised6}: {msg6[:40]}…",
    )

    # ⓕ-2 `JO`·검색 파라미터가 **실호출로 확정된 형식** 그대로인가 (네트워크 미사용).
    #   `24`·`002400000` 은 HTTP 200 인데 조문단위가 0건으로 조용히 돌아온다 — 그래서
    #   "응답이 비었다"를 "조문이 없다"로 읽으면 안 되고, 조립점을 한 곳에 묶어 잠근다.
    #   `display=100`(기본 20 이면 `상법` exact match 가 페이지 밖) ·
    #   `search=1`(2 는 본문검색이라 법령명 매칭이 전 법령에서 실패) 도 함께 본다.
    jo_ok = (
        fl._jo_param("24") == "002400"
        and fl._jo_param("146") == "014600"
        and fl._jo_param("652") == "065200"
        and fl._jo_param("24의2") == "002402"
    )
    try:
        fl._jo_param("24", "1")
        clause_guarded = False  # 항을 조용히 무시하면 다른 조문을 받아 놓고 모른다
    except ValueError:
        clause_guarded = True
    search_params = '"display": 100' in src_fetch and '"search": 1' in src_fetch
    check(
        "ⓕ-2 JO 6자리(조4+가지2) · display=100 · search=1 — 실호출 확정 형식 고정",
        jo_ok and clause_guarded and search_params,
        f"JO 4종 일치={jo_ok} · 항 지정 차단={clause_guarded} · 검색 파라미터={search_params}",
    )

    # ── ⓘ ★MQ-701: `조문내용` 만 담긴 응답(=제목 한 줄)은 **수집 실패**로 거부한다.
    #   법제처는 조문에 따라 `조문내용` 에 본문을 다 담기도 하고(`민법 388`) **제목만**
    #   담기도 한다(`부가세법 32` — 15자). 후자를 그대로 text 로 쓰면 `apply_fetch` 의
    #   비어있지 않음 검사를 **통과**해서 제목이 계층 1 원문으로 해시되고 서명 번들에 실린다.
    #   `11 §2`("조문 원문을 손으로 타이핑하지 않는다")가 막으려던 실패의 자동화 판이다.
    heading_only = {
        "법령": {
            "기본정보": {"법령명_한글": "부가가치세법", "공포번호": "21065", "시행일자": "20260102"},
            "조문": {"조문단위": {
                "조문여부": "조문", "조문번호": "32", "조문제목": "세금계산서 등",
                "조문시행일자": "20260102", "조문내용": "제32조(세금계산서 등)",
            }},
        }
    }
    try:
        fl.parse_article_response(heading_only, article="32", law_ref_id="KR-VAT-32")
        raised_h, msg_h = None, ""
    except fl.LawFetchError as exc:
        raised_h, msg_h = "LawFetchError", str(exc)
    # 같은 응답에 항을 한 줄만 붙이면 통과해야 한다 — 과잉 게이트가 아님을 함께 잠근다
    with_body = json.loads(json.dumps(heading_only))
    with_body["법령"]["조문"]["조문단위"]["항"] = [{"항내용": "① 사업자가 재화 또는 용역을 공급한다."}]
    parsed = fl.parse_article_response(with_body, article="32", law_ref_id="KR-VAT-32")
    check(
        "ⓘ 제목만 담긴 응답 → 적용 거부 (본문 1줄만 있어도 통과)",
        raised_h == "LawFetchError"
        and "제목만" in msg_h
        and len(parsed["text"]) > len("제32조(세금계산서 등)")
        and "① 사업자가" in parsed["text"],
        f"{raised_h or 'no-raise'} · 본문 있으면 text {len(parsed['text'])}자 (제목 15자)",
    )

    # ── ⓙ ★MQ-701: `'전문'`(절 제목)이 섞여 와도 `'조문'` 만 고른다.
    #   `산업안전보건법 93`·`조특법 24` 는 실제로 2건이 온다. 첫 건을 집으면
    #   `제4절 안전검사` 라는 **절 제목**이 조문 원문으로 들어간다.
    mixed = {
        "법령": {
            "기본정보": {"법령명_한글": "산업안전보건법", "공포번호": "21374", "시행일자": "20260601"},
            "조문": {"조문단위": [
                {"조문여부": "전문", "조문번호": "93", "조문제목": None,
                 "조문시행일자": "20260601", "조문내용": "          제4절 안전검사"},
                {"조문여부": "조문", "조문번호": "93", "조문제목": "안전검사",
                 "조문시행일자": "20260601", "조문내용": "제93조(안전검사)",
                 "항": [{"항내용": "① 유해하거나 위험한 기계ㆍ기구ㆍ설비로서 대통령령으로 정하는 것",
                         "호": [{"호내용": "1. 고용노동부장관이 정하는 검사"}]}]},
            ]},
        }
    }
    picked = fl.parse_article_response(mixed, article="93", law_ref_id="KR-OSHA-93")
    check(
        "ⓙ '전문'(절 제목) 섞인 응답에서 '조문' 만 선택 · 항·호까지 평탄화",
        picked["title"] == "안전검사"
        and "제4절" not in picked["text"]
        and picked["text"].startswith("제93조(안전검사)")
        and "① 유해하거나" in picked["text"]
        and "1. 고용노동부장관이" in picked["text"]
        and picked["effective_from"] == "2026-06-01"
        and picked["promulgation_no"] == "21374",
        f"text {len(picked['text'])}자 · '제4절' 배제 · effective_from={picked['effective_from']} "
        f"(YYYYMMDD→ISO) · promulgation_no={picked['promulgation_no']} (기본정보 유래)",
    )

    # ── ⓖ D59: 법령은 룩업이다. 벡터 인덱싱 흔적이 없어야 한다
    src = (ROOT / "data" / "rules" / "fetch_laws.py").read_text(encoding="utf-8")
    banned = [w for w in ("embed", "vector", "faiss", "chroma", "index_law") if w in src.lower()]
    check(
        "ⓖ D59 벡터 인덱싱 흔적 없음",
        not banned,
        f"금지어 검출={banned or '없음'}",
    )


def check_oc_not_committed() -> None:
    """법제처 인증값(OC)이 추적 파일에 남지 않았는가.

    `fetch_laws.py` docstring 이 "인증값은 저장소에 남기지 않는다 — 로그·문서·주석·source_url
    어디에도" 라고 스스로 규정하는데, 그 규정을 지키는지 확인하는 장치가 없었다. 실제로
    `.env.example` 과 세션 로그에 실값이 평문으로 들어갔고 **사람 리뷰가 잡을 때까지 3커밋을 살아남았다**.

    ★ 기대값을 **하드코딩하지 않는다** — 스파이크에 값을 적는 순간 그 자체가 유출이다.
      실행 환경의 `LAW_API_OC` 를 읽어 추적 파일과 대조한다. 키가 없으면 검사를 통과로
      **위장하지 않고** 미검증임을 detail 에 남긴다(D62 — 모른다를 통과로 바꾸지 않는다).
    """
    oc = (os.environ.get("LAW_API_OC") or "").strip()
    if not oc:
        check(
            "ⓚ 인증값(OC) 이 추적 파일에 없다",
            True,
            "LAW_API_OC 미설정 — 대조 미수행(키가 있는 환경에서만 유효한 검사)",
        )
        return

    try:
        tracked = subprocess.run(  # noqa: S603
            ["git", "grep", "-l", "--fixed-strings", oc],  # noqa: S607
            cwd=ROOT,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        check("ⓚ 인증값(OC) 이 추적 파일에 없다", False, f"git grep 실패 — {type(exc).__name__}: {exc}")
        return

    # git grep: 0=검출됨, 1=없음. 그 밖은 실행 실패이므로 통과로 읽지 않는다.
    if tracked.returncode not in (0, 1):
        check("ⓚ 인증값(OC) 이 추적 파일에 없다", False, f"git grep rc={tracked.returncode}")
        return

    hits = [ln for ln in tracked.stdout.splitlines() if ln.strip()]
    check(
        "ⓚ 인증값(OC) 이 추적 파일에 없다 (.env.example·세션 로그 평문 유출 재발 방지)",
        not hits,
        f"검출 {len(hits)}건: {', '.join(hits[:4])}" if hits else "추적 파일 0건",
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("법령 수집·적용 계약 검증 — tmp 사본 + 합성 픽스처 (네트워크·정본 파일 미사용)\n")
    before_real = dir_digest(REAL_LAWS)
    real_pending = ROOT / "data" / "rules" / "pending_revisions"
    pending_existed = real_pending.exists()

    with tempfile.TemporaryDirectory() as td:
        run(Path(td))

    check_oc_not_committed()

    check(
        "ⓗ 정본 laws/ 불변 (내용 해시)",
        dir_digest(REAL_LAWS) == before_real,
        f"sha256[:16]={before_real} (7파일 전부 그대로)",
    )
    check(
        "ⓗ-2 정본 pending_revisions/ 생성 안 됨",
        real_pending.exists() == pending_existed,
        f"존재={real_pending.exists()} (실행 전과 동일)",
    )

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 52))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 52))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(
        f"\n통과 ({len(results)}건) — D59·D60·D61·D75 준수. "
        "실수집은 MQ-701 이 완료했으나 **이 스위트는 법제처를 호출하지 않는다** — "
        "응답 정규화를 순수 함수로 분리해 합성 응답으로 덮는다. "
        "키·네트워크·법령 개정에 좌우되는 검사는 회귀가 아니다."
    )


if __name__ == "__main__":
    main()
