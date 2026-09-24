# -*- coding: utf-8 -*-
"""HV600 매뉴얼 안전 문구 **후보** 추출 — 온보딩 승인 입력 (D147).

입력 : data/raw/TOEPC71061732.pdf (manifest `hv600-iopm`, 읽기 전용)
출력 : data/extracted/hv600_safety_candidates.json — `.gitignore` 대상(D144, 원문 인용이 들어 있다)

이 스크립트는 **결정적**이다 — LLM 을 부르지 않는다. 안전 문구는 사람이 원문과 대조해
승인해야 `SAFETY_BASELINE` 에 들어간다(D147) — 이 단계는 「후보 + 근거 페이지 + 원문 인용」
까지만 만든다. 번역은 하지 않는다(D147 원문 그대로 심사).

전략 (2026-09-25 실측, PDF 전 126페이지 직접 조사 후 확정) :
  ① `x_tolerance=1.5` — 기본값(3)은 이 PDF 의 좁은 자간을 붙인다(D107·`extract_hv600_codes.py`
     ②와 같은 이유, 이 PDF 는 코드 추출기와 같은 파일이다).
  ② 신호어는 **줄 시작**에서만 인정한다(`^(DANGER|WARNING)\\b`) — 실측 결과 이 매뉴얼의 모든
     안전 블록은 예외 없이 신호어로 줄이 시작한다(`DANGER Electrical Shock Hazard. ...`).
  ③ 블록은 다음 신호어(DANGER/WARNING) 또는 빈 줄 2개에서 끝난다(명세 그대로). **다만 실측으로
     명세보다 종료 조건을 넓혀야 했다** — 아래 ④.
  ④ ⛔ **명세와 다르게 만든 점 (실측 근거)**: 명세대로 DANGER/WARNING 만 블록 경계로 쓰면
     같은 DANGER 블록이 CAUTION·NOTICE·표 캡션·"Note:" 뒤에 이어지는 무관한 절차문·표
     전체를 그대로 삼킨다 — 실측: p.21 의 커버 분리 DANGER 블록이 "Remove the Terminal
     Cover" 이후 CAUTION 앞까지, p.91 의 방전 대기 WARNING 블록이 퓨즈 정격표
     (Table 13.3·13.4) 전체를 삼켜 후보 길이가 614자 → 1,500자로 부풀었다(같은 문장이
     p.7·19·23·28·39 에 5번 나오는데 이 오염 때문에 텍스트가 달라져 **중복 제거가 실패**했다
     — 페이지마다 뒤에 붙는 절차문이 다르므로). 그래서 **CAUTION·NOTICE·"Note:"(단독 줄)·
     "Table "·"Figure " 로 시작하는 줄도 블록을 조용히 끝낸다**(새 후보를 만들지 않고 그냥
     닫기만 한다 — `blocks_seen`·`electrical_blocks` 에 안 센다). 이 확장 후 위 5페이지 반복
     문장이 정확히 1건으로 합쳐지는 것으로 실증했다(`also_pages: [19, 23, 28, 39]`).
     완전하지는 않다 — 표제 없는 평문 소제목("Open the Front Door" 류, 글리프·전각 기호가
     없다)이 뒤따르면 여전히 일부 섞인다(p.21·26·33·91 잔존, 실측 길이로 확인). 이건
     `extract_hv600_codes.py` 의 엣지 케이스 문구와 같은 성격이다 — **추출기가 고치지 않고
     사람이 원문과 대조한다(H4)**. 과잉 포함이 누락보다 낫다는 명세 원칙을 그대로 따른다.
  ⑤ 반복되는 쪽 머리말/꼬리말("YASKAWA TOEPC71061732H HV600 DRIVE INSTALLATION & PRIMARY
     OPERATION", 페이지 번호 앞/뒤 어느 쪽에도 붙는다)은 매 페이지 텍스트에서 먼저 제거한다.
     제거하지 않으면 신호어 블록이 우연히 페이지 맨 끝에 오는 경우(p.19·23·28 등)에만 이
     꼬리말이 붙어 위와 같은 중복 제거 실패가 생긴다(실측으로 발견).
  ⑥ 신호어 직후 첫 마침표까지를 "위해 유형"으로 보고(`DANGER Electrical Shock Hazard.` →
     `Electrical Shock Hazard`), 그 안에 `Electrical Shock Hazard` 문자열이 있는 블록만 후보로
     본다(명세 그대로) — `Arc Flash Hazard`·`Fire Hazard`·`Crush Hazard`·`Sudden Movement
     Hazard`·`Burn Hazard` 는 후보에서 제외된다(`blocks_seen` 에는 센다).
  ⑦ `kind` 분류는 명세 순서 그대로 첫 매치 우선 — `capacitor|charge indicator|wait` →
     `discharge_wait` · `energized|power is (on|applied)|live` → `live_work` ·
     `qualified|authorized|trained` → `qualified_worker` · 그 외 `other`. 이 매뉴얼은
     "approved personnel" 이라는 표현만 쓰고 `qualified`·`authorized`·`trained` 어휘를 안
     써서(실측 — 전문 검색 0건) `qualified_worker` 후보가 하나도 없다. **추측해 패턴을
     넓히지 않는다** — 명세가 준 어휘 그대로 쓴다.
  ⑧ `wait_minutes_in_text`: `(\\d+)\\s*min(ute)?s?` 첫 매치. 이 매뉴얼의 방전 대기 문구는
     대부분 "wait for the time specified on the warning label at a minimum"(라벨 참조,
     숫자 없음) 이다 — `null` 이 대부분이고 정상이다. **실제 숫자가 있는 유일한 예**는 p.29
     "De-energize the drive and wait 5 minutes minimum until the Charge LED turns off." 뿐
     (전문 검색으로 확인 — 다른 분당 지시는 전부 라벨 참조형).
  ⑨ 공백 정규화(`" ".join(text.split())`)한 `quote_en` 이 완전히 같은 블록만 병합한다(대소문자
     구분 유지 — 이 매뉴얼은 대소문자 변형이 없다). 첫 발생 페이지를 `page`, 이후 발생 페이지를
     `also_pages`(오름차순, 중복 제거)로 둔다. 같은 페이지에 두 번 나오면(p.33) `also_pages` 에
     그 페이지를 또 넣지 않는다 — `deduped` 카운터에는 반영된다.

⛔ 쓰지 않는 것 (절대규칙 5): `data/raw/**` 에 쓰지 않는다.

실행:  uv run python data/extract_hv600_safety.py
종료코드: 0 성공 · 1 후보 0건 또는 discharge_wait 0건(추출기 사망 취급) · 2 PDF 없음/sha256 불일치
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.extract_hv600_codes import RAW, load_manifest_entry, sha256  # noqa: E402

OUT = ROOT / "data" / "extracted" / "hv600_safety_candidates.json"

#: 신호어 — 줄 시작에서만 인정한다(실측: 이 매뉴얼은 예외 없이 그렇다).
SIGNAL_RE = re.compile(r"^(DANGER|WARNING)\b")
#: 블록을 조용히 끝내지만 새 후보는 만들지 않는 경계(실측으로 추가 — docstring ④ 참고).
STOP_RE = re.compile(r"^(DANGER|WARNING|CAUTION|NOTICE|Note:?)$|^(DANGER|WARNING|CAUTION|NOTICE)\b|^(Table|Figure)\s")
#: 반복 쪽 머리말/꼬리말. 페이지 번호가 앞이나 뒤 어느 쪽에도 붙을 수 있다(실측).
FOOTER_RE = re.compile(r"^\d*\s*YASKAWA TOEPC71061732H HV600 DRIVE INSTALLATION & PRIMARY OPERATION\s*\d*$")

#: kind 분류 — 명세가 준 순서 그대로(첫 매치 우선). 어휘를 추측해 넓히지 않는다.
KIND_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("discharge_wait", re.compile(r"capacitor|charge indicator|wait", re.I)),
    ("live_work", re.compile(r"energized|power is (on|applied)|live", re.I)),
    ("qualified_worker", re.compile(r"qualified|authorized|trained", re.I)),
]
#: 원문에 명시된 숫자만 잡는다 — 추정하지 않는다(safety-guardrail 규칙 1·3).
WAIT_MINUTES_RE = re.compile(r"(\d+)\s*min(ute)?s?", re.I)
#: 후보 판정 기준 — 신호어 직후 첫 문장(마침표까지)에 이 문자열이 있어야 한다.
HAZARD_LABEL = "Electrical Shock Hazard"


def clean_block(lines: list[str]) -> str:
    """블록 줄들을 공백 정규화한 한 문단으로 합친다."""
    s = " ".join(line.strip() for line in lines if line.strip() != "")
    return re.sub(r"\s+", " ", s).strip()


def extract_blocks(text: str) -> list[list[str]]:
    """페이지 텍스트에서 DANGER/WARNING 로 시작하는 블록들을 뽑는다.

    CAUTION·NOTICE·"Note:"·"Table "·"Figure " 로 시작하는 줄은 현재 블록을 조용히
    끝내기만 한다(새 블록을 만들지 않음) — docstring ④ 실측 근거.
    """
    lines = [line for line in text.split("\n") if not FOOTER_RE.match(line.strip())]
    blocks: list[list[str]] = []
    current: list[str] | None = None
    blank_run = 0
    for line in lines:
        stripped = line.strip()
        if SIGNAL_RE.match(stripped):
            if current is not None:
                blocks.append(current)
            current = [line]
            blank_run = 0
            continue
        if STOP_RE.match(stripped):
            if current is not None:
                blocks.append(current)
                current = None
            continue
        if current is None:
            continue
        if stripped == "":
            blank_run += 1
            if blank_run >= 2:
                blocks.append(current)
                current = None
            continue
        blank_run = 0
        current.append(line)
    if current is not None:
        blocks.append(current)
    return blocks


def classify_kind(text: str) -> str:
    for kind, pattern in KIND_PATTERNS:
        if pattern.search(text):
            return kind
    return "other"


def find_wait_minutes(text: str) -> int | None:
    m = WAIT_MINUTES_RE.search(text)
    return int(m.group(1)) if m else None


def extract(pdf_path: Path) -> dict:
    blocks_seen = 0
    electrical: list[tuple[int, str, str, str]] = []  # (page, signal, hazard, text)

    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            text = page.extract_text(x_tolerance=1.5) or ""
            for raw_block in extract_blocks(text):
                blocks_seen += 1
                block_text = clean_block(raw_block)
                m = re.match(r"^(DANGER|WARNING)\s+([^.]+)\.", block_text)
                if not m:
                    continue
                signal, hazard = m.group(1), m.group(2).strip()
                if HAZARD_LABEL not in hazard:
                    continue
                electrical.append((pno, signal, hazard, block_text))

    # 공백 정규화 텍스트로 중복 제거 (docstring ⑨)
    merged: dict[str, dict] = {}
    order: list[str] = []
    for pno, signal, hazard, text in electrical:
        if text not in merged:
            merged[text] = {"page": pno, "signal": signal, "hazard": hazard, "text": text, "also_pages": []}
            order.append(text)
        else:
            entry = merged[text]
            if pno != entry["page"] and pno not in entry["also_pages"]:
                entry["also_pages"].append(pno)

    candidates = []
    by_kind: dict[str, int] = {}
    for ordinal, key in enumerate(order):
        e = merged[key]
        kind = classify_kind(e["text"])
        by_kind[kind] = by_kind.get(kind, 0) + 1
        candidates.append(
            {
                "ordinal": ordinal,
                "page": e["page"],
                "also_pages": sorted(e["also_pages"]),
                "signal": e["signal"],
                "hazard": e["hazard"],
                "kind": kind,
                "quote_en": e["text"],
                "wait_minutes_in_text": find_wait_minutes(e["text"]),
            }
        )

    deduped = len(electrical) - len(candidates)

    return {
        "candidates": candidates,
        "_stats": {
            "blocks_seen": blocks_seen,
            "electrical_blocks": len(electrical),
            "candidates": len(candidates),
            "by_kind": by_kind,
            "deduped": deduped,
        },
    }


def main() -> int:
    entry = load_manifest_entry()
    pdf_path = RAW / entry["file"]
    if not pdf_path.exists():
        print(f"[중단] {pdf_path.relative_to(ROOT)} 가 없다 — INDEX.md §7 을 보고 받아 둘 것", file=sys.stderr)
        return 2
    digest = sha256(pdf_path)
    if digest != entry["sha256"]:
        print(
            f"[중단] sha256 불일치 — manifest {entry['sha256'][:12]}… vs 파일 {digest[:12]}… "
            "(매뉴얼 개정본이면 manifest 에 새 항목을 추가하고 다시 돌린다)",
            file=sys.stderr,
        )
        return 2

    result = extract(pdf_path)
    out = {
        "_status": "초안 — 사람 승인 전 (HV600 안전 문구 후보, D147)",
        "_source": {
            "manifest_id": entry["id"],
            "file": entry["file"],
            "sha256": digest,
            "page_basis": "PDF 물리 페이지 (D26)",
        },
        "_generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **result,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    st = result["_stats"]
    print(f"HV600 안전 문구 후보 추출 — {pdf_path.name} → {OUT.relative_to(ROOT)}")
    print(f"  블록 {st['blocks_seen']} · 감전 위험 블록 {st['electrical_blocks']} · 중복 제거 {st['deduped']}")
    print(f"  후보 {st['candidates']} · kind 분포 {st['by_kind']}")

    # 양성 축: 0건이면 "안전 문구 없음"이 아니라 추출기가 죽은 것이다
    if st["candidates"] == 0:
        print("[실패] 후보 0건 — 추출기가 안전 블록을 하나도 못 읽었다", file=sys.stderr)
        return 1
    if st["by_kind"].get("discharge_wait", 0) == 0:
        print("[실패] discharge_wait 후보 0건 — HV600 안전 승인 경로가 막힌다", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
