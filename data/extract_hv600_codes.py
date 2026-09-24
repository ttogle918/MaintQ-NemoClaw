# -*- coding: utf-8 -*-
"""HV600 매뉴얼 고장 표 **후보** 추출 — 온보딩 스테이징 입력 (D145·D146).

입력 : data/raw/TOEPC71061732.pdf (manifest `hv600-iopm`, 읽기 전용)
출력 : data/extracted/hv600_code_candidates.json — `.gitignore` 대상(D144, 원문 표현이 들어 있다)

이 스크립트는 **결정적**이다 — LLM 을 부르지 않는다. 코드·페이지·원문은 사실이라 추출은
코드가 하고, 한국어 정규화(D145)는 이 산출물을 입력으로 받는 **다음 단계**의 일이다.
`_status` 는 한국어 초안 마커 — `data/seed.py error_codes_gate()` 가 *"초안"·"승인 전"* 으로
판정하므로 같은 어휘를 쓴다(IE5 추출기와 같은 이유).

전략 (2026-09-24 실측) :
  ① 고장 표는 **괘선 4열**(`Code | Name | Causes | Possible Solutions`)이라 D107 의 기하 유도가
     필요 없다 — 기본 `lines` 전략으로 잡힌다. 판별은 **헤더 행**으로 한다: 헤더가 정확히 그 4개가
     아닌 표(p107 빈 3열 표, p123 `Keypad Display` 메시지 표)는 버리지 않고 `_skipped_tables` 에 남긴다.
  ② `text_x_tolerance=1.5` — 기본값(3)은 이 PDF 의 좁은 자간을 붙여 `Thecurrentflowing…` 가 된다.
  ③ 구역(Fault / Minor Faults/Alarms / Parameter Setting Errors / Auto-Tuning Errors / Backup …)은
     `�` 글리프(14pt) 옆 13pt 제목으로 **탐지**한다. 좌표·쪽 하드코딩 없음. 표는 자기보다 앞선
     마지막 제목의 구역에 속한다 — 같은 코드라도 고장이냐 알람이냐가 다르다.
  ④ `Code` 칸이 빈 행은 **이어지는 행**이다(쪽 경계 포함). 앞 코드에 원인·조치를 덧붙인다.
     `Causes` 가 빈 행은 앞 원인의 조치가 이어진 것이다(원문이 한 원인에 조치를 여러 줄로 쓴다).
  ⑤ 범위 표기(`EF1 to EF7`, `CPF00 to CPF03, CPF07 to CPF08, …, and CPF26 to CPF39`)는 펼친다.
     접두·자릿수가 같을 때만 펼치고, 아니면 **추측하지 않고** `_unmatched` 로 보낸다.
     펼친 코드는 `expanded_from` 에 원표기를 남긴다 — 검수자가 원문과 대조할 수 있어야 한다.
  ⑥ 같은 코드가 여러 구역에 나오면(고장이자 알람) **합치지 않는다** — 구역별로 따로 둔다.
     D25 canonical(대문자)로는 **세기만** 하고 원표기는 `display_code` 에 보존한다.

⛔ 쓰지 않는 것 (절대규칙 5·D99): `data/raw/**`, `data/extracted/error_codes.json`(사람 승인 정본).

실행:  uv run python data/extract_hv600_codes.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "extracted" / "hv600_code_candidates.json"
MANIFEST_ID = "hv600-iopm"

#: 20장 Troubleshooting 의 고장 표 범위 (INDEX.md §7 · manifest page_note). 물리 = 인쇄 (offset 0).
PAGE_FROM, PAGE_TO = 107, 124
FAULT_HEADER = ["Code", "Name", "Causes", "Possible Solutions"]
TABLE_SETTINGS = {"text_x_tolerance": 1.5}
#: 코드 형상 — 영문자로 시작, 영숫자·하이픈 8자 이내 (`CPF06`·`oFA30`·`Bu-Fb`·`EP24v`)
CODE_SHAPE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{0,7}")
HEADING_GLYPH = "�"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest_entry() -> dict:
    manifest = json.loads((RAW / "manifest.json").read_text(encoding="utf-8"))
    for m in manifest["manuals"]:
        if m["id"] == MANIFEST_ID:
            return m
    raise SystemExit(f"[중단] manifest 에 {MANIFEST_ID} 가 없다 — data/raw/manifest.json 확인")


def clean(cell: str | None) -> str:
    """셀 텍스트 정리. 줄 끝 하이픈(`b3-\\n24`)은 붙이고, 나머지 줄바꿈은 공백으로."""
    if not cell:
        return ""
    s = re.sub(r"-\n(?=\S)", "-", cell)
    s = re.sub(r"\s*\n\s*", " ", s)
    return re.sub(r"[ \t]+", " ", s).strip()


def headings(page) -> list[tuple[float, str]]:
    """`�`(14pt) 글리프와 같은 줄의 13pt 이상 단어를 구역 제목으로 읽는다."""
    words = page.extract_words(x_tolerance=1.5, extra_attrs=["size"])
    out = []
    for g in (w for w in words if w["text"] == HEADING_GLYPH and w["size"] >= 13):
        line = [
            w["text"]
            for w in words
            if abs(w["top"] - g["top"]) <= 2.5 and w["size"] >= 12.5 and w["text"] != HEADING_GLYPH
        ]
        if line:
            out.append((g["top"], " ".join(line)))
    return out


def expand_codes(raw: str) -> tuple[list[str], str | None]:
    """범위 표기를 펼친다. (코드들, 실패 사유) — 실패하면 추측하지 않고 사유를 돌려준다."""
    parts = [p.strip() for p in re.split(r",|\band\b", raw) if p.strip()]
    codes: list[str] = []
    for part in parts:
        m = re.fullmatch(r"(\S+)\s+to\s+(\S+)", part)
        if not m:
            if not CODE_SHAPE.fullmatch(part):
                return [], f"코드 형상 아님: {part!r}"
            codes.append(part)
            continue
        a, b = m.groups()
        ma, mb = re.fullmatch(r"([A-Za-z]+)(\d+)", a), re.fullmatch(r"([A-Za-z]+)(\d+)", b)
        if not (ma and mb) or ma.group(1) != mb.group(1) or len(ma.group(2)) != len(mb.group(2)):
            return [], f"범위 접두·자릿수 불일치: {part!r}"
        lo, hi, width = int(ma.group(2)), int(mb.group(2)), len(ma.group(2))
        if hi < lo:
            return [], f"역순 범위: {part!r}"
        codes += [f"{ma.group(1)}{n:0{width}d}" for n in range(lo, hi + 1)]
    return codes, None


def extract(pdf_path: Path) -> dict:
    records: list[dict] = []
    skipped: list[dict] = []
    unmatched: list[dict] = []
    warnings: list[str] = []
    section = None  # 첫 제목 전의 표는 None → 경고
    current: list[dict] = []  # 지금 원인·조치를 받는 레코드들(범위면 여러 개)

    with pdfplumber.open(pdf_path) as pdf:
        for pno in range(PAGE_FROM, PAGE_TO + 1):
            page = pdf.pages[pno - 1]
            heads = headings(page)
            tables = sorted(page.find_tables(TABLE_SETTINGS), key=lambda t: t.bbox[1])
            events = [("h", top, text) for top, text in heads] + [("t", t.bbox[1], t) for t in tables]
            for kind, _top, obj in sorted(events, key=lambda e: e[1]):
                if kind == "h":
                    section = obj
                    current = []  # 구역이 바뀌면 이어지는 행이 앞 구역으로 새지 않는다
                    continue
                rows = obj.extract(x_tolerance=TABLE_SETTINGS["text_x_tolerance"])
                header = [clean(c) for c in rows[0]] if rows else []
                if header != FAULT_HEADER:
                    skipped.append({"page": pno, "section": section, "header": header, "rows": len(rows)})
                    continue
                if section is None:
                    warnings.append(f"p{pno}: 구역 제목 전에 고장 표가 있다")
                for row in rows[1:]:
                    code_raw, name, cause, sol = (clean(c) for c in (row + [None] * 4)[:4])
                    if code_raw:
                        codes, why = expand_codes(code_raw)
                        if why:
                            unmatched.append({"page": pno, "section": section, "raw": code_raw, "reason": why})
                            current = []
                            continue
                        current = []
                        for c in codes:
                            rec = {
                                "code": c.upper(),
                                "display_code": c,
                                "name": name,
                                "section": section,
                                "pages": [pno],
                                "causes": [],
                            }
                            if len(codes) > 1 or code_raw != c:
                                rec["expanded_from"] = code_raw
                            records.append(rec)
                            current.append(rec)
                    elif not current:
                        if cause or sol:
                            warnings.append(f"p{pno}: 이어지는 행인데 받을 코드가 없다 — {cause[:40]!r}")
                        continue
                    elif name:
                        warnings.append(f"p{pno}: 코드 없이 이름만 있는 행 {name!r} — 앞 코드에 붙이지 않음")
                        continue
                    for rec in current:
                        if pno not in rec["pages"]:
                            rec["pages"].append(pno)
                        if cause:
                            rec["causes"].append({"cause": cause, "solutions": [sol] if sol else []})
                        elif sol and rec["causes"]:
                            rec["causes"][-1]["solutions"].append(sol)
                        elif sol:
                            rec["causes"].append({"cause": "", "solutions": [sol]})

    for rec in records:
        if not rec["causes"]:
            warnings.append(f"{rec['display_code']}({rec['section']}): 원인·조치 0건")

    by_code: dict[str, list[str]] = {}
    for rec in records:
        by_code.setdefault(rec["code"], []).append(rec["section"])
    multi = {c: s for c, s in by_code.items() if len(s) > 1}
    sections: dict[str, int] = {}
    for rec in records:
        sections[rec["section"] or "(없음)"] = sections.get(rec["section"] or "(없음)", 0) + 1

    return {
        "codes": records,
        "_skipped_tables": skipped,
        "_unmatched": unmatched,
        "_warnings": warnings,
        "_stats": {
            "records": len(records),
            "distinct_codes": len(by_code),
            "expanded_records": sum(1 for r in records if "expanded_from" in r),
            "codes_in_multiple_sections": multi,
            "by_section": sections,
            "skipped_tables": len(skipped),
            "unmatched": len(unmatched),
            "warnings": len(warnings),
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
        "_status": "초안 — 사람 승인 전 (HV600 온보딩 스테이징 입력, D145·D146)",
        "_source": {
            "manifest_id": MANIFEST_ID,
            "file": entry["file"],
            "sha256": digest,
            "pages": [PAGE_FROM, PAGE_TO],
            "page_basis": "PDF 물리 페이지 (D26) — print_page_offset 0",
        },
        "_generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **result,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    st = result["_stats"]
    print(f"HV600 고장 표 추출 — p{PAGE_FROM}~{PAGE_TO} → {OUT.relative_to(ROOT)}")
    print(f"  레코드 {st['records']} · 고유 코드 {st['distinct_codes']} · 범위에서 펼친 것 {st['expanded_records']}")
    for sec, n in st["by_section"].items():
        print(f"    {sec}: {n}")
    print(
        f"  여러 구역에 나온 코드 {len(st['codes_in_multiple_sections'])} · 건너뛴 표 {st['skipped_tables']} · "
        f"미처리 {st['unmatched']} · 경고 {st['warnings']}"
    )
    # 양성 축: 0건이면 "문제 없음" 이 아니라 추출기가 죽은 것이다
    if st["records"] == 0:
        print("[실패] 레코드 0건 — 추출기가 표를 하나도 못 읽었다", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
