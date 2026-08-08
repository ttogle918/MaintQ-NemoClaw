# -*- coding: utf-8 -*-
"""apply_fetch 계약 검증 — 법령 수집 결과의 파일 적용 (MQ-602L).

검증 대상: D60(append-only · 자동 덮어쓰기 금지) · D61(불변식 2 — 미등록 법령 참조 거부) ·
          verification_note 요구(조문번호·제목 대조) · D59(룩업이지 RAG 아님 — 인덱싱 없음)

**네트워크를 쓰지 않는다.** `fetch_from_api` 는 호출하지 않으며(키 미발급 · Sprint 7),
수집기와 적용기를 분리해 둔 덕에 적용기만 합성 픽스처로 지금 검증한다.

**정본을 건드리지 않는다.** `data/rules/laws/*.json` 은 tmp 로 복사해서 쓰고,
마지막에 정본 디렉토리의 mtime·바이트를 대조한다.

실행:  uv run python spikes/law_fetch_contract.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
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


def run(tmp: Path) -> None:
    laws, pending = sandbox(tmp)
    target = "KR-CITA-ENF-31"
    path = laws / f"{target}.json"

    # ── ⓪ 전제: 등록된 7건이 전부 PENDING (수집 전 상태)
    files = sorted(laws.glob("*.json"))
    raws = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in files}
    check(
        "⓪ laws/ 7건 · 전부 PENDING · text=null",
        len(files) == 7
        and all(r["fetch_status"] == "PENDING" for r in raws.values())
        and all(r["text"] is None for r in raws.values())
        and target in raws,
        f"{len(files)}건, {target} 등록={target in raws}",
    )

    # ── ⓐ 최초 수집: PENDING → FETCHED. text_hash 가 파일에 기입된다
    before = digest(path)
    outcome = fl.apply_fetch(
        target,
        {"article": "31", "title": "즉시상각의제", "text": SYNTHETIC_TEXT,
         "effective_from": "2026-01-01"},
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
            {"article": "24의2", "title": "통합투자세액공제", "text": SYNTHETIC_TEXT},
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

    # ⓑ-2 제목 불일치도 같은 경로
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
    vat_raw = json.loads((laws / "KR-VAT-32.json").read_text(encoding="utf-8"))
    check(
        "ⓑ-2 제목 불일치 → 중단 · PENDING 유지",
        raised2 == "LawMismatchError" and vat_raw["fetch_status"] == "PENDING",
        f"{raised2 or 'no-raise'} / status={vat_raw['fetch_status']}",
    )

    # ⓑ-W5-a article 키 자체가 없으면 → 중단. **누락은 통과가 아니다**
    #   Sprint 7 에서 법제처 응답의 `조문번호` 매핑을 빠뜨리면 정체성 게이트가 조용히
    #   무력화되고 대조 없이 원문이 기입된다 — D50·D62 가 막아 온 실패 유형과 같다.
    kcc = laws / "KR-KCC-652.json"
    k_before = kcc.read_bytes()
    try:
        fl.apply_fetch(
            "KR-KCC-652",
            {"title": "위험변경증가의 통지와 계약해지", "text": SYNTHETIC_TEXT},
            laws_dir=laws,
            pending_dir=pending,
        )
        raised_a, msg_a = None, ""
    except fl.LawMismatchError as exc:
        raised_a, msg_a = "LawMismatchError", str(exc)
    kcc_raw = json.loads(kcc.read_text(encoding="utf-8"))
    check(
        "ⓑ-W5-a article 키 누락 → 중단 · 파일 바이트 불변",
        raised_a == "LawMismatchError"
        and "article" in msg_a
        and kcc.read_bytes() == k_before
        and kcc_raw["fetch_status"] == "PENDING",
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

    # ⓑ-W5-c 선택적 필드는 필수가 아니다 — 정체성 키만 대상 (과잉 게이트 방지)
    optional_ok = fl.apply_fetch(
        "KR-STTC-146",
        {"article": "146", "title": "세액공제액의 추징", "text": SYNTHETIC_TEXT},
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
        {"article": "31", "title": "즉시상각의제", "text": SYNTHETIC_TEXT_V2},
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
        {"article": "31", "title": "즉시상각의제", "text": SYNTHETIC_TEXT_V2},
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
        {"article": "31", "title": "즉시상각의제", "text": SYNTHETIC_TEXT},
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
        {"article": "31", "title": "즉시상각의제", "text": SYNTHETIC_TEXT_V2},
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
            {"article": "31", "title": "즉시상각의제", "text": SYNTHETIC_TEXT_V3},
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
    try:
        fl.apply_fetch(
            "KR-OSHA-93",
            {"article": "93", "title": "안전검사", "text": "   "},
            laws_dir=laws,
            pending_dir=pending,
        )
        raised5 = None
    except ValueError:
        raised5 = "ValueError"
    osha = json.loads((laws / "KR-OSHA-93.json").read_text(encoding="utf-8"))
    check(
        "ⓔ 빈 원문 거부 · PENDING 유지",
        raised5 == "ValueError" and osha["fetch_status"] == "PENDING",
        f"{raised5 or 'no-raise'} / status={osha['fetch_status']}",
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

    # ⓕ-2 키가 있어도 아직 미구현 — 추측한 URL 형식을 박아두지 않았다
    fl.API_OC = "dummy-oc-not-used"
    try:
        fl.fetch_from_api("KR-CITA-ENF-31")
        raised7, msg7 = None, ""
    except NotImplementedError as exc:
        raised7, msg7 = "NotImplementedError", str(exc)
    finally:
        fl.API_OC = saved
    check(
        "ⓕ-2 fetch_from_api 미구현 유지 (Sprint 7)",
        raised7 == "NotImplementedError" and "Sprint 7" in msg7 and "MST" in msg7,
        f"{raised7}: {msg7[:44]}…",
    )

    # ── ⓖ D59: 법령은 룩업이다. 벡터 인덱싱 흔적이 없어야 한다
    src = (ROOT / "data" / "rules" / "fetch_laws.py").read_text(encoding="utf-8")
    banned = [w for w in ("embed", "vector", "faiss", "chroma", "index_law") if w in src.lower()]
    check(
        "ⓖ D59 벡터 인덱싱 흔적 없음",
        not banned,
        f"금지어 검출={banned or '없음'}",
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("apply_fetch 계약 검증 — tmp 사본 + 합성 픽스처 (네트워크·정본 파일 미사용)\n")
    before_real = dir_digest(REAL_LAWS)
    real_pending = ROOT / "data" / "rules" / "pending_revisions"
    pending_existed = real_pending.exists()

    with tempfile.TemporaryDirectory() as td:
        run(Path(td))

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
        f"\n통과 ({len(results)}건) — D59·D60·D61 준수. "
        "법제처 API 미호출(키 미발급) · 실수집은 Sprint 7. "
        "적용기를 수집기에서 분리했기에 키 없이도 계약이 검증된다."
    )


if __name__ == "__main__":
    main()
