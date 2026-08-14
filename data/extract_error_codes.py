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

🔴 정본 쓰기 가드 (D99, MQ-921)
       `data/extracted/error_codes.json` 은 **사람이 승인한 정본**이고 `seed.error_codes_gate()`
       가 `_status` 만 보고 65행 전량 적재/미적재를 가른다. 그래서 이 스크립트는 정본을
       **무조건 덮어쓰지 않는다**:
         - 내용 동일(`generated_at` 제외) → **쓰지 않고** "변경 없음 — 기록 생략"
         - 내용 상이                     → **쓰지 않고** diff 요약 + exit 1 (사람이 판단)
         - `_status` 승인 → 초안 되돌림  → **쓰지 않고** 즉시 중단 + exit 2 (65→0행 사고 차단)
         - 정본 없음(최초 추출)          → 그대로 기록 (가드는 회귀 방지지 최초 생성 금지가 아니다)
       후보 추출은 `--candidates-only` 로 돌린다 — 이 모드는 정본을 열지도 쓰지도 않는다.
"""

from __future__ import annotations

import argparse
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


def assign_key(yr, item_cells, fallback):
    """세로 겹침이 가장 큰 항목 키. 겹치는 항목이 없으면 직전 항목을 잇는다."""
    hit = max(item_cells, key=lambda c: overlap(yr, c[1]), default=None)
    return hit[0] if hit and overlap(yr, hit[1]) > 0 else fallback


def span_key(y: float, parts: list[tuple[float, float, str]]) -> str | None:
    """분할 구간에서 y 가 속한 항목 키. **어디에도 안 들어가면 버린다.**

    가장 가까운 항목으로 흘려보내면 남의 조치문이 붙는다 — 실측에서 Out Phase Open 이
    이웃 항목들의 조치까지 6건 흡수했다. 엉뚱한 에러코드에 붙은 조치는 누락보다 나쁘다.
    에이전트가 그대로 정비사에게 전달하기 때문이다. 못 고르면 비운다.
    """
    for lo, hi, key in parts:
        if lo <= y <= hi:
            return key
    return None


def column_sentences(page, bbox) -> list[tuple[float, str]]:
    """컬럼 bbox 를 단어로 읽어 줄로 묶고 문장으로 재구성 → [(문장 시작 y, 문장)].

    `extract_text()` 로 통째 읽으면 줄바꿈 위치를 잃어 문장의 y 를 알 수 없고,
    행 단위로 크롭하면 문장이 끊긴다 (D53 — 잘린 절차문은 뒷부분을 지어낼 여지를 만든다).
    """
    try:
        words = page.crop(bbox).extract_words()
    except ValueError:  # 크롭 영역이 페이지 밖
        return []

    lines: dict[int, list] = {}
    for w in words:
        lines.setdefault(round(w["top"]), []).append(w)

    out: list[tuple[float, str]] = []
    cur_y: float | None = None
    cur: list[str] = []
    for top in sorted(lines):
        row = sorted(lines[top], key=lambda w: w["x0"])
        text = clean(" ".join(w["text"] for w in row))
        if not text:
            continue
        if cur_y is None:
            cur_y = float(top)
        cur.append(text)
        # 마침표로 끝나면 문장 종료 — 다음 줄은 새 문장
        if text.endswith("."):
            joined = clean(" ".join(cur))
            if len(joined) > 3:
                out.append((cur_y, joined))
            cur, cur_y = [], None
    if cur and cur_y is not None:
        joined = clean(" ".join(cur))
        if len(joined) > 3:
            out.append((cur_y, joined))
    return out


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

                    # '조치 사항' 컬럼은 **본문 행에서 cells[2] 가 항상 None** 이다 —
                    # 괘선이 닫힌 셀을 만들지 않아 pdfplumber 가 bbox 를 못 낸다.
                    # bbox is None 을 건너뛰면 actions 가 통째로 비고(S100 41/41 결측,
                    # 2026-08-05 확인), 진단 결과에 조치가 없어 에이전트가 절차를 서술하지
                    # 못한다. 헤더 행에서 컬럼 x 범위를 얻어 **항목 병합 셀의 y 구간 전체**를
                    # 한 번에 crop 한다 (iG5A 12.1 의 desc 크롭과 같은 기법).
                    #
                    # 행 단위로 자르지 않는 이유: 진단 행과 조치 셀의 y 경계가 어긋나 문장이
                    # 조각나고("있는지 확인하십시오.") 다음 항목으로 번진다. **잘린 절차문은
                    # 에이전트가 뒷부분을 지어낼 여지를 만든다 (D53)** — 항목 단위로 통째
                    # 크롭한 뒤 문장으로 나누면 원문이 온전히 보존된다.
                    head_cells = table.rows[0].cells if table.rows else []
                    act_x = None
                    if len(head_cells) >= 3 and head_cells[2] is not None:
                        act_x = (head_cells[2][0], head_cells[2][2])

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
                        key = assign_key(yr, item_cells, last_item)
                        if key is None:
                            continue
                        remedies.setdefault(key, {"causes": [], "actions": []})
                        remedies[key]["causes" if ci == 1 else "actions"].append(txt)
                        last_item = key

                    # 조치 사항 — 컬럼 전체를 단어로 읽어 줄→문장으로 재구성한 뒤 y 로 배정.
                    #
                    # 행 단위 크롭이 안 되는 이유: 조치 문장이 같은 행의 진단보다 길어
                    # 아래로 더 흐르기 때문에 진단 행 y 로 자르면 문장이 끊긴다
                    # ("…속도 검색 기능(Cn.60)을"). 반대로 항목 셀 y 는 병합 스팬이 아니라
                    # 텍스트가 놓인 한 행이라 그것도 못 쓴다. 그래서 **컬럼을 통째로 읽고
                    # 문장으로 나눈 뒤**, 각 문장의 y 를 원인 행 스팬과 맞춰 항목에 준다.
                    if act_x and body:
                        spans: dict[str, tuple[float, float]] = {}
                        for ci_b, yr_b, _ in body:
                            if ci_b != 1:
                                continue
                            # 스팬은 **항목 셀과 실제로 겹치는 행만** 정의한다.
                            # last_item 으로 흘려보내면 겹치지 않는 행까지 흡수돼
                            # 그 항목의 y 범위가 페이지 전체로 부풀고, nearest_span 이
                            # 다른 항목의 조치까지 전부 그쪽으로 몰아준다 (실측: 41문장이
                            # ETH·OLW 두 항목에만 배정됨).
                            k = assign_key(yr_b, item_cells, None)
                            if k is None:
                                continue
                            lo, hi = spans.get(k, (yr_b[0], yr_b[1]))
                            spans[k] = (min(lo, yr_b[0]), max(hi, yr_b[1]))

                        if spans:
                            # 표 본문 전체를 훑는다 — 스팬 합집합으로 자르면 원인 행이
                            # 덜 잡힌 항목의 조치문이 크롭 밖으로 떨어진다.
                            top = min(v[0] for v in spans.values())
                            bot = max(v[1] for v in spans.values())
                            parts = [(lo, hi, k) for k, (lo, hi) in spans.items()]
                            for y_mid, sent in column_sentences(
                                page, (act_x[0], top, act_x[1], bot)
                            ):
                                k = span_key(y_mid, parts)
                                if k is None:
                                    continue
                                remedies.setdefault(k, {"causes": [], "actions": []})
                                bucket = remedies[k]["actions"]
                                if sent not in bucket:
                                    bucket.append(sent)

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
    return mapping.get("_status", "승인 완료 — data/analysis/ig5a_code_mapping.md 참조")


# ──────────────────────────────────────────────── 정본 쓰기 가드 (D99 · MQ-921)
SEED_PY = ROOT / "seed.py"
VOLATILE_KEYS = ("generated_at",)  # 내용이 같아도 매 실행 바뀐다 — 동등성 비교에서 뺀다
DRAFT_MARKERS = ("초안", "승인 전")  # data/seed.py `error_codes_gate()` 와 같아야 한다


def is_draft_status(status: str) -> bool:
    """`seed.error_codes_gate()` 가 미적재로 떨어뜨리는 상태인가."""
    return any(marker in str(status) for marker in DRAFT_MARKERS)


def gate_marker_drift() -> str | None:
    """`DRAFT_MARKERS` 가 `seed.error_codes_gate()` 와 어긋났는지 **정적으로** 대조한다.

    seed 모듈을 import 하지 않는 이유: 이 스크립트는 DB 를 건드리지 않는데 시드 모듈을
    끌어오면 그 자체가 사고 경로가 된다. 소스를 읽어 그 함수 본문만 본다.
    ⚠ 양성 축 — **함수를 실제로 찾았을 때만** 판정한다. 못 찾으면 "드리프트 없음"이
    아니라 *확인 불가*로 돌려준다(CLAUDE.md 부재 검사 규칙).
    """
    try:
        src = SEED_PY.read_text(encoding="utf-8")
    except OSError as e:  # 경로가 바뀌었거나 읽기 실패
        return f"확인 불가 — {SEED_PY} 를 읽지 못했다 ({e.__class__.__name__})"
    m = re.search(r"def error_codes_gate\(.*?(?=\ndef |\Z)", src, re.S)
    if not m:
        return "확인 불가 — seed.error_codes_gate() 를 찾지 못했다"
    body = m.group(0)
    missing = [k for k in DRAFT_MARKERS if f'"{k}"' not in body]
    if missing:
        return f"드리프트 — 게이트 본문({len(body)}자)에 없는 마커 {missing}"
    return None


def canonical_payload(doc: dict) -> str:
    """`generated_at` 을 제외한 정준 직렬화 — 내용 동등성 판정용."""
    body = {k: v for k, v in doc.items() if k not in VOLATILE_KEYS}
    return json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True)


def _by_code(doc: dict) -> dict[tuple[str, str], dict]:
    return {(str(e.get("model")), str(e.get("code"))): e for e in (doc.get("entries") or [])}


def diff_summary(prev: dict, new: dict, limit: int = 10) -> list[str]:
    """사람이 판단할 수 있을 만큼의 변경 요약 (전체 diff 가 아니다)."""
    p, n = _by_code(prev), _by_code(new)
    removed, added = sorted(set(p) - set(n)), sorted(set(n) - set(p))
    changed = sorted(k for k in set(p) & set(n) if p[k] != n[k])
    lines = [
        f"  entries {len(p)} → {len(n)} "
        f"(추가 {len(added)} · 삭제 {len(removed)} · 변경 {len(changed)})"
    ]
    for key in sorted(set(prev) | set(new)):
        if key in VOLATILE_KEYS or key == "entries" or prev.get(key) == new.get(key):
            continue
        before = json.dumps(prev.get(key), ensure_ascii=False)[:70]
        after = json.dumps(new.get(key), ensure_ascii=False)[:70]
        lines.append(f"  [최상위] {key}: {before} → {after}")
    for model, code in added[:limit]:
        lines.append(f"  [추가] {model} {code}")
    for model, code in removed[:limit]:
        lines.append(f"  [삭제] {model} {code}")
    for k in changed[:limit]:
        fields = sorted(f for f in set(p[k]) | set(n[k]) if p[k].get(f) != n[k].get(f))
        lines.append(f"  [변경] {k[0]} {k[1]}: {', '.join(fields)}")
    return lines


def write_canonical(out: dict) -> None:
    """정본 기록 — 가드를 통과할 때만 쓴다. 통과 못 하면 **쓰지 않고 중단**한다 (D99).

    exit 1 = 내용이 실제로 달라졌다(사람이 판단) · exit 2 = `_status` 승인→초안 되돌림.
    """
    EXTRACTED.mkdir(exist_ok=True)
    text = json.dumps(out, ensure_ascii=False, indent=2) + "\n"

    if not OUTPUT.exists():
        # 최초 추출 — 가드는 회귀 방지지 최초 생성 금지가 아니다
        OUTPUT.write_text(text, encoding="utf-8")
        print(f"[기록] {OUTPUT} — 정본 신규 생성(최초 추출)")
        return

    try:
        prev = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        # 기존 정본을 못 읽으면 **덮어쓰지 않는다** — 읽기 실패는 "빈 파일"이 아니다
        print(f"[중단] 기존 정본을 읽지 못했다 ({e.__class__.__name__}: {e}) — 쓰지 않았다")
        print(f"  → {OUTPUT} 를 사람이 확인하라(git 이력에 정상본이 있다).")
        raise SystemExit(1) from None

    prev_entries = prev.get("entries") or []
    prev_status, new_status = str(prev.get("_status", "")), str(out.get("_status", ""))
    prev_draft, new_draft = is_draft_status(prev_status), is_draft_status(new_status)

    drift = gate_marker_drift()
    if drift:
        print(f"[경고] 초안 마커 대조 {drift} — seed 게이트와 판정이 어긋날 수 있다")

    # 🔴 `_status` 되돌림 차단. 판정에 양성 축(기존 entries 수)을 함께 건다 —
    #    이것이 `error_codes` 65 → 0행 사고(MQ-708·MQ-713a)의 정확한 조건이다.
    if len(prev_entries) > 0 and not prev_draft and new_draft:
        print(f"[중단] `_status` 되돌림 감지 — 정본을 쓰지 않았다 ({OUTPUT})")
        print(f"  기존 entries {len(prev_entries)}건 · 기존 초안 여부 {prev_draft}")
        print(f"  기존 _status: {prev_status!r}")
        print(f"  신규 _status: {new_status!r} (초안 여부 {new_draft})")
        print("  → 그대로 기록하면 seed.error_codes_gate() 가 전량 미적재로 떨어뜨린다.")
        print(
            "  → data/extracted/ig5a_code_map.json 의 pending_review·confidence 를 먼저 확인하라."
        )
        raise SystemExit(2)

    if canonical_payload(prev) == canonical_payload(out):
        print(f"[변경 없음] 기록 생략 — {OUTPUT}")
        print(
            f"  generated_at {prev.get('generated_at')!r} → {out.get('generated_at')!r} "
            "만 다르다. 내용이 같으면 쓰지 않는다 (D99 — 해시 불변)"
        )
        return

    print(f"[중단] 내용이 달라졌다 — 정본을 쓰지 않았다 ({OUTPUT})")
    for line in diff_summary(prev, out):
        print(line)
    print("  → 사람이 판단한다. 의도한 갱신이면 검토 후 직접 반영하라(D99·D33 승인 절차).")
    raise SystemExit(1)


def extract_candidates() -> None:
    """후보 추출 모드 — 정본(`error_codes.json`)을 **열지도 쓰지도 않는다** (D99).

    ⚠ 후보 추출 로직 자체는 아직 없다. MQ-905·907 이 트러블슈팅 조인 결과를
    후보 파일에 쓰는 코드를 이 함수 안에 채운다. 지금 이 모드의 계약은 하나다 —
    **정본 미접촉으로 정상 종료**.
    """
    print("[후보 모드] 후보 추출 로직 미구현 (MQ-905·907 이 채운다)")
    print(f"  정본 미접촉: {OUTPUT} 를 열지도 쓰지도 않았다 (D99)")


# ──────────────────────────────────────────────── main
def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 대응

    ap = argparse.ArgumentParser(description="에러코드 추출 (M1) — 정본 쓰기 가드 포함 (D99)")
    ap.add_argument(
        "--candidates-only",
        action="store_true",
        help="후보 파일만 생성한다. 정본(data/extracted/error_codes.json)을 열지도 쓰지도 않는다",
    )
    args = ap.parse_args()

    if args.candidates_only:
        extract_candidates()
        return

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
    n_visual = sum(1 for e in ig5a_entries if e.get("mapping_confidence") == "visual")
    print(f"[추출 완료] {len(out['entries'])}건 — 정본 반영 여부는 아래 가드 판정을 따른다")
    print(
        f"  iG5A {len(ig5a_entries)}건 (high {len(ig5a_entries) - n_visual} + "
        f"visual·확인대기 {n_visual}) + S100 {len(s100_entries)}건"
    )
    print(
        f"  보류(pending_review) {len(pending)}건, 파싱 미완(_unparsed) {len(out['_unparsed'])}건"
    )
    for u in out["_unparsed"]:
        print(f"    - {u}")

    write_canonical(out)  # 🔴 정본은 가드를 통과할 때만 기록된다 (D99)


if __name__ == "__main__":
    main()
