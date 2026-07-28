# -*- coding: utf-8 -*-
"""에러코드 추출 파이프라인 (M1) — 멱등 재실행 가능 (D19, D24).

입력 : data/raw/*.pdf + data/raw/manifest.json + data/extracted/ig5a_code_map.json
출력 : data/extracted/error_codes.json
전략 : pdfplumber extract_text() 행 단위 규칙 파싱, extract_tables()는 보조 (D24)
규칙 : code는 대문자 canonical, display_code에 키패드 원표기 보존 (D25)
       manual_page는 PDF 물리 페이지 (D26)
주의 : 승인 여부는 `ig5a_code_map.json` 에서 **유도**한다(하드코딩하지 않는다, D19) —
       pending_review 가 남아 있거나 confidence 가 "high" 아닌 항목이 있으면 초안,
       둘 다 해소되면 승인. 재실행할 때마다 사람이 `_status` 를 다시 손으로 칠 필요가 없다.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent  # data/
RAW = ROOT / "raw"
EXTRACTED = ROOT / "extracted"
MANIFEST = RAW / "manifest.json"
IG5A_MAP = EXTRACTED / "ig5a_code_map.json"
OUTPUT = EXTRACTED / "error_codes.json"

# S100 파싱 구간 (PDF 물리 페이지)
S100_TRIP_PAGES = range(416, 422)  # 9.x 트립 표: 키패드/LCD/상태/내용
S100_REMEDY_PAGES = range(417, 422)  # 항목|진단|조치 표
S100_WARNING_PAGES = (309, 310)  # 6.3 일람표 (경보 섹션 → warning 시드)

SEVERITY_BY_STATE = {"latch": "fault", "level": "fault", "fatal": "critical", "warning": "warning"}


# ──────────────────────────────────────────────── manifest (D19)
def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_manifest() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    changed = False
    for m in manifest["manuals"]:
        f = RAW / m["file"]
        if not f.exists():
            sys.exit(f"[중단] 매뉴얼 파일 없음: {f}")
        digest = sha256_of(f)
        if m.get("sha256") is None:
            m["sha256"] = digest
            changed = True
            print(f"[manifest] sha256 기록: {m['id']} = {digest[:12]}…")
        elif m["sha256"] != digest:
            sys.exit(
                f"[중단] {m['id']} 해시 불일치 — 매뉴얼이 바뀌었습니다. "
                "manifest 갱신 절차(update_policy)를 따르세요."
            )
    if changed:
        MANIFEST.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return manifest


# ──────────────────────────────────────────────── 공통 유틸
def norm_key(s: str) -> str:
    """한글 명칭 매칭 키: 공백·개행 제거"""
    return re.sub(r"\s+", "", s or "")


def split_bullets(cell: str) -> list[str]:
    """'' 불릿 셀 → 문장 리스트 (개행은 문장 내 이어붙임)"""
    if not cell:
        return []
    parts = [p.strip().replace("\n", " ") for p in cell.split("")]
    parts = [re.sub(r"\s+", " ", p) for p in parts if p.strip()]
    return parts


# ──────────────────────────────────────────────── S100
def grid_text(page, table) -> list[list[str | None]]:
    """find_tables() 셀 bbox를 crop해 병합 셀 원문 복원.
    세로 병합 셀은 원점 행에 전체 텍스트, 스팬 행은 None."""
    grid = []
    for row in table.rows:
        cells = []
        for bbox in row.cells:
            if bbox is None:
                cells.append(None)
            else:
                txt = (page.crop(bbox).extract_text() or "").strip()
                cells.append(txt)
        grid.append(cells)
    return grid


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\n", " ")).strip()


def rk(s: str) -> str:
    """remedy 매칭 키: 소문자 영숫자만"""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def parse_s100(pdf_path: Path) -> tuple[list[dict], list[str]]:
    entries: list[dict] = []
    unparsed: list[str] = []
    remedies: dict[str, dict[str, list[str]]] = {}
    pairs: list[tuple[str, str, str, int]] = []  # (keypad, lcd, state, page)
    last_lcd: tuple[str, str] | None = None  # 페이지 경계에서 병합이 끊긴 경우 상속
    last_item: str | None = None  # remedy 표의 페이지 경계 carry

    with pdfplumber.open(pdf_path) as pdf:
        for pno in S100_TRIP_PAGES:
            page = pdf.pages[pno - 1]
            for table in page.find_tables():
                grid = grid_text(page, table)
                if not grid:
                    continue
                header = clean(" ".join(c or "" for c in grid[0]))

                is_warning_tbl = (
                    "키패드" in header and "LCD" in header and "고장 상태" not in header
                )
                is_trip_tbl = "키패드" in header and "고장 상태" in header

                if is_warning_tbl or is_trip_tbl:
                    # 컬럼별 병합-원점 셀을 (텍스트, y구간)으로 수집 → 세로 겹침으로 페어링
                    desc_col = 2 if is_warning_tbl else 3
                    # '내용' 열은 우측 괘선이 없어 셀 검출이 안 됨 → 헤더 x좌표 기반 스트립 크롭
                    desc_x0 = None
                    hdr_cells = table.rows[0].cells
                    if len(hdr_cells) > desc_col and hdr_cells[desc_col]:
                        desc_x0 = hdr_cells[desc_col][0]
                    kp_cells, lcd_cells, st_cells, desc_cells = [], [], [], []
                    for row in table.rows[1:]:
                        for ci, bbox in enumerate(row.cells[: desc_col + 1]):
                            if bbox is None:
                                continue
                            txt = clean(page.crop(bbox).extract_text() or "")
                            if not txt:
                                continue
                            yr = (bbox[1], bbox[3])
                            if ci == 0:
                                tok = txt.split()[0]
                                if re.fullmatch(r"[a-z][a-z0-9\-]{1,7}", tok):
                                    kp_cells.append((tok, yr))
                            elif ci == 1 and re.match(r"[A-Z]", txt):
                                name = re.sub(r"[*]+\s*$", "", txt).strip()
                                lcd_cells.append((name, yr))
                            elif ci == 2 and is_trip_tbl:
                                st_cells.append((txt.lower(), yr))
                            elif ci == desc_col:
                                desc_cells.append((txt, yr))
                    for kp, kyr in kp_cells:
                        lcd = max(lcd_cells, key=lambda c: overlap(kyr, c[1]), default=None)
                        if lcd and overlap(kyr, lcd[1]) > 0:
                            if is_trip_tbl:
                                st = max(
                                    st_cells, key=lambda c: overlap(lcd[1], c[1]), default=None
                                )
                                state = st[0] if st and overlap(lcd[1], st[1]) > 0 else ""
                            else:
                                state = "warning"
                            dc = max(desc_cells, key=lambda c: overlap(lcd[1], c[1]), default=None)
                            desc = dc[0] if dc and overlap(lcd[1], dc[1]) > 0 else ""
                            if not desc and desc_x0 is not None:
                                strip = (desc_x0, lcd[1][0], table.bbox[2], lcd[1][1])
                                try:
                                    desc = clean(page.crop(strip).extract_text() or "")
                                except ValueError:
                                    desc = ""
                            last_lcd = (lcd[0], state, desc)
                            pairs.append((kp, lcd[0], state, desc, pno))
                        elif last_lcd:
                            # 겹치는 LCD 없음 = 페이지 경계/N코드 1명칭 병합 → 직전 명칭 상속
                            pairs.append((kp, last_lcd[0], last_lcd[1], last_lcd[2], pno))
                        else:
                            unparsed.append(f"S100 키패드 '{kp}' (p.{pno}): 대응 LCD 없음")

                elif "항목" in header and "진단" in header:
                    # 항목 셀 병합 bbox와의 세로 겹침으로 진단/조치를 배정.
                    # 겹치는 항목이 없으면 직전 항목 carry (페이지 경계에서 병합이 끊긴 경우)
                    item_cells: list[tuple[str, tuple[float, float]]] = []
                    body: list[tuple[int, tuple[float, float], str]] = []  # (col, y구간, 텍스트)
                    for row in table.rows[1:]:
                        for ci, bbox in enumerate(row.cells[:3]):
                            if bbox is None:
                                continue
                            txt = clean(page.crop(bbox).extract_text() or "")
                            if not txt:
                                continue
                            yr = (bbox[1], bbox[3])
                            if ci == 0:
                                # 한글 항목 = 9.3 증상 기반 표 → 트립 remedy 아님
                                if not re.search(r"[가-힣]", txt) and rk(txt):
                                    item_cells.append((rk(txt), yr))
                            else:
                                body.append((ci, yr, txt))
                    for key, _ in item_cells:
                        remedies.setdefault(key, {"causes": [], "actions": []})
                    for ci, yr, txt in body:
                        hit = max(item_cells, key=lambda c: overlap(yr, c[1]), default=None)
                        key = hit[0] if hit and overlap(yr, hit[1]) > 0 else last_item
                        if key is None:
                            continue
                        remedies.setdefault(key, {"causes": [], "actions": []})
                        remedies[key]["causes" if ci == 1 else "actions"].append(txt)
                        last_item = key
                    if item_cells:
                        last_item = item_cells[-1][0]

    seen = set()
    for kp, lcd, state, desc, pno in pairs:
        code = kp.replace("-", "").upper()
        if code in seen:
            continue
        seen.add(code)
        lcd = "".join(ch for ch in lcd if ord(ch) < 0xE000)  # 각주 기호(PUA 글리프) 제거
        rem = remedies.get(rk(lcd), {"causes": [], "actions": []})
        causes = rem["causes"][:6] or ([desc] if desc else [])
        entry = {
            "model": "S100",
            "code": code,
            "display_code": kp,
            "error_name": lcd.strip(),
            "severity": SEVERITY_BY_STATE.get(state.split()[0] if state else "", "fault"),
            "causes": causes,
            "actions": rem["actions"][:6],
            "description": desc,
            "manual_page": pno,
            "source": "S100 9장 문제 해결(트립 표+진단/조치 표)",
        }
        if not causes:
            unparsed.append(f"S100 {code}: 원인/조치·내용 모두 미확보 (LCD='{lcd}')")
        entries.append(entry)
    return entries, unparsed


# ──────────────────────────────────────────────── iG5A
def parse_ig5a(pdf_path: Path) -> tuple[list[dict], list[str], list[dict], dict]:
    mapping = json.loads(IG5A_MAP.read_text(encoding="utf-8"))
    unparsed: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        # 12.1 보호기능 표 (p.202~204): 한글명 → 내용
        desc_by_key: dict[str, tuple[str, int]] = {}
        for pno in (202, 203, 204):
            for tb in pdf.pages[pno - 1].extract_tables():
                for r in tb:
                    cells = [(c or "").strip() for c in r]
                    named = [c for c in cells if c]
                    if len(named) < 2 or "보호" in named[0][:4] or named[0] == "주 의":
                        continue
                    key = norm_key(named[0])
                    if 2 <= len(key) <= 12:
                        desc_by_key[key] = (re.sub(r"\s+", " ", named[1].replace("\n", " ")), pno)
        # 12.2 고장 대책 표 (p.204~206): 한글명 → 원인/대책
        remedy_by_key: dict[str, dict[str, list[str]]] = {}
        current = None
        for pno in (204, 205, 206):
            for tb in pdf.pages[pno - 1].extract_tables():
                header = norm_key("".join(c or "" for c in tb[0]))
                if "이상원인" not in header and "대책" not in header:
                    continue
                for r in tb[1:]:
                    cells = [(c or "").strip() for c in r]
                    name = cells[0] if cells else ""
                    nk = norm_key(name)
                    if nk and nk != "주의" and not name.startswith(""):
                        current = nk
                        remedy_by_key.setdefault(current, {"causes": [], "actions": []})
                    if current is None:
                        continue
                    texty = [c for c in cells[1:] if c]
                    if len(texty) >= 2:
                        remedy_by_key[current]["causes"] += split_bullets(texty[0])
                        remedy_by_key[current]["actions"] += split_bullets(texty[-1])
                    elif len(texty) == 1 and texty[0].startswith(""):
                        remedy_by_key[current]["causes"] += split_bullets(texty[0])
    entries: list[dict] = []
    for m in mapping["mappings"]:
        desc, page = None, m["manual_page"]
        rem = {"causes": [], "actions": []}
        for k in m["match_keys"]:
            nk = norm_key(k)
            if nk in desc_by_key:
                desc, page = desc_by_key[nk]
            for rk, rv in remedy_by_key.items():
                if rk.startswith(nk[:4]) and (rv["causes"] or rv["actions"]):
                    rem = rv
                    break
        entry = {
            "model": "iG5A",
            "code": m["code"],
            "display_code": m["display_code"],  # null = 7-세그 원표기 미확정 (검수 시 기입)
            "error_name": m["name_kr"],
            "severity": "fault",
            "causes": rem["causes"][:6] or ([desc] if desc else []),
            "actions": rem["actions"][:6],
            "manual_page": page,
            "mapping_confidence": m["confidence"],
            "source": "iG5A 표준본 12.1/12.2 + 통신 챕터 비트명 매핑(검수 대기)",
        }
        if not entry["causes"]:
            unparsed.append(f"iG5A {m['code']}: 12.1/12.2 매칭 실패 (keys={m['match_keys']})")
        entries.append(entry)
    return entries, unparsed, mapping.get("pending_review", []), mapping


def ig5a_approval_status(mapping: dict, pending: list) -> str:
    """승인 여부를 `ig5a_code_map.json` 에서 유도한다 — 하드코딩하지 않는다 (D19).

    사람이 검수를 마치면 그 파일의 `pending_review` 를 비우고 모든 매핑의
    `confidence` 를 "high" 로 승격한다(`data/analysis/ig5a_code_mapping.md` 절차).
    이 함수는 그 두 조건만 보고 판정한다 — 재실행할 때마다 `error_codes.json` 의
    `_status` 를 사람이 다시 손으로 칠 필요가 없다.
    """
    if pending:
        return (
            f"초안 — 미결 항목 {len(pending)}건 "
            "(data/analysis/ig5a_code_mapping.md ③). DB 적재 금지"
        )
    not_high = [m["code"] for m in mapping["mappings"] if m.get("confidence") != "high"]
    if not_high:
        return (
            f"초안 — 확인 대기 항목 {len(not_high)}건({', '.join(not_high)}) "
            "(data/analysis/ig5a_code_mapping.md ②). DB 적재 금지"
        )
    return mapping.get(
        "_status", "승인 완료 — data/analysis/ig5a_code_mapping.md 참조"
    )


# ──────────────────────────────────────────────── main
def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 대응
    manifest = check_manifest()
    files = {m["id"]: RAW / m["file"] for m in manifest["manuals"]}

    s100_entries, s100_unparsed = parse_s100(files["s100-manual"])
    ig5a_entries, ig5a_unparsed, pending, ig5a_mapping = parse_ig5a(files["ig5a-manual"])

    out = {
        "_status": ig5a_approval_status(ig5a_mapping, pending),
        "generated_at": str(date.today()),
        "citation_basis": "PDF 물리 페이지 (D26)",
        "code_policy": "code=대문자 canonical, display_code=키패드 원표기 (D25)",
        "counts": {"iG5A": len(ig5a_entries), "S100": len(s100_entries)},
        "entries": ig5a_entries + s100_entries,
        "_pending_review": pending,
        "_unparsed": ig5a_unparsed + s100_unparsed,
    }
    EXTRACTED.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n_visual = sum(1 for e in ig5a_entries if e.get("mapping_confidence") == "visual")
    print(f"[완료] {OUTPUT}")
    print(
        f"  iG5A {len(ig5a_entries)}건 (high {len(ig5a_entries) - n_visual} + "
        f"visual·확인대기 {n_visual}) + S100 {len(s100_entries)}건"
    )
    print(
        f"  보류(pending_review) {len(pending)}건, 파싱 미완(_unparsed) {len(out['_unparsed'])}건"
    )
    for u in out["_unparsed"]:
        print(f"    - {u}")


if __name__ == "__main__":
    main()
