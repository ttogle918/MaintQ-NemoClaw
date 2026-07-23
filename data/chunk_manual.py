# -*- coding: utf-8 -*-
"""매뉴얼 청킹 파이프라인 (M2 / MQ-305) — 멱등 재실행 가능 (D19, D24).

입력 : data/raw/*.pdf + data/raw/manifest.json  (둘 다 읽기 전용)
출력 : data/extracted/manual_chunks.jsonl
전략 : pdfplumber extract_text() 페이지 단위 → 러닝헤더/쪽번호 제거 → 줄 단위 균등 분할 (D24)

계약 (MQ-314 `rag_search_manual` 의 입력) — 각 줄의 키는 **정확히 7개**:
    chunk_id / manual_id / model / page / section / text / char_len

불변식
  1. **청크는 페이지 경계를 넘지 않는다.** 넘으면 인용 페이지가 모호해져 D30 인용률 판정이 흔들린다.
     main() 의 자가 검증이 "청크 text 가 해당 페이지 정제 텍스트의 부분 문자열인가"로 실제 확인한다.
  2. `page` 는 **PDF 물리 페이지**만 저장한다 (D26). `print_page` 를 넣지 않는다 (D32) —
     인쇄 페이지 환산 지점은 backend/manifest.py 한 곳뿐이어야 한다 (MQ-312).
  3. `chunk_id` 는 결정론적(`{manual_id}-p{page:04d}-{idx:02d}`)이고 출력은 chunk_id 정렬 —
     같은 PDF 면 몇 번을 돌려도 바이트 동일한 파일이 나온다 (D19).
  4. manifest sha256 을 실제로 계산해 대조하고 불일치면 중단한다 (D19). 매뉴얼이 바뀌면
     페이지가 밀려 기존 인용이 전부 어긋나므로 조용히 재생성해서는 안 된다.

검색 구현체는 mcp_server/rag.py 가 소유한다. `backend/rag/` 는 만들지 않는다 (D48).
임베딩 모델·벡터스토어·하이브리드 가중치는 이 스크립트가 정하지 않는다 —
data/analysis/rag_sizing.md 수치를 보고 사람이 결정한다 (D51).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import unicodedata
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent  # data/
RAW = ROOT / "raw"
EXTRACTED = ROOT / "extracted"
MANIFEST = RAW / "manifest.json"
OUTPUT = EXTRACTED / "manual_chunks.jsonl"

# 청크 크기 (문자 수). 페이지 평균이 ~900자라 대부분의 페이지는 1~2청크가 된다.
MAX_CHARS = 900  # 청크 상한 — 이 값을 넘으면 페이지 안에서 균등 분할
MIN_CHARS = (
    60  # 이보다 짧은 청크는 만들지 않는다 (꼬리는 직전 청크에 병합, 페이지 전체가 짧으면 제외)
)

CHUNK_ID_RE = re.compile(r"^[a-z0-9-]+-p\d{4}-\d{2}$")
# 절 제목: 점이 최소 1개 있고(6.1 / 8.14.1), 장 번호가 현재 장과 일치하는 줄만 인정.
# 장 번호 일치 조건이 "1.5 kW", "23 Spd Limit" 같은 표 행 오검출을 걸러 준다.
HEADING_RE = re.compile(r"^(\d{1,2})((?:\.\d{1,2}){1,2})\s+(\S.{0,38})$")
CHAPTER_RE = re.compile(r"^(\d{1,2})\.?\s+(\S.{0,38})$")
PAGE_NO_RE = re.compile(r"^(?:\d{1,4}|\d{1,2}-\d{1,3})$")  # 쪽번호 단독 줄 ("293", "12-3")
DOT_LEADER_RE = re.compile(r"^.*[.·]{4,}\s*\d{1,4}$")  # 목차의 점선 줄
LETTER_RE = re.compile(r"[가-힣A-Za-z]")
RUNNING_HEADER_MIN_PAGES = 3  # 같은 첫 줄이 N쪽 이상 반복되면 러닝헤더로 본다


# ──────────────────────────────────────────────── manifest (D19)
def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_manifest() -> dict:
    """manifest 의 sha256 을 실제 계산값과 대조. 불일치·미기록이면 중단 (D19).

    extract_error_codes.py 와 달리 이 스크립트는 manifest 를 **쓰지 않는다** —
    청킹은 소비자일 뿐이고, 해시 기록은 추출 파이프라인의 책임이다.
    """
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for m in manifest["manuals"]:
        f = RAW / m["file"]
        if not f.exists():
            sys.exit(f"[중단] 매뉴얼 파일 없음: {f}")
        if m.get("sha256") is None:
            sys.exit(
                f"[중단] {m['id']} sha256 미기록 — 먼저 extract_error_codes.py 로 해시를 기록하세요."
            )
        digest = sha256_of(f)
        if m["sha256"] != digest:
            sys.exit(
                f"[중단] {m['id']} 해시 불일치 — 매뉴얼이 바뀌었습니다.\n"
                f"  manifest={m['sha256'][:12]}… 실제={digest[:12]}…\n"
                "  페이지가 밀리면 기존 인용이 전부 어긋납니다. "
                "manifest 갱신 절차(update_policy)를 따르세요."
            )
    return manifest


# ──────────────────────────────────────────────── 텍스트 정제
def normalize(text: str) -> str:
    """PUA 글리프(불릿 등)·NBSP 정리. 원문 의미는 바꾸지 않는다."""
    out = []
    for ch in text:
        o = ord(ch)
        if 0xE000 <= o <= 0xF8FF:  # 사용자 정의 영역 = 폰트 전용 불릿/각주 기호
            out.append("•")
        elif ch == " ":
            out.append(" ")
        elif unicodedata.category(ch) == "Cc" and ch != "\n":
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def page_lines(raw: str, header_keys: set[str]) -> list[str]:
    """페이지 원문 → 정제된 줄 목록. 러닝헤더·쪽번호·목차 점선을 제거한다.

    쪽번호 줄을 지우는 건 위생 문제만이 아니다 — 본문에 인쇄 쪽번호가 남으면
    LLM 이 그 숫자를 인용할 여지가 생기고, 그러면 D32 의 "환산은 한 곳"이 깨진다.
    """
    lines = [ln.strip() for ln in normalize(raw).split("\n")]
    lines = [re.sub(r"[ \t]+", " ", ln) for ln in lines if ln.strip()]
    if lines and norm_key(lines[0]) in header_keys:
        lines = lines[1:]
    if lines and PAGE_NO_RE.match(lines[-1]):
        lines = lines[:-1]
    return [ln for ln in lines if not DOT_LEADER_RE.match(ln) and not PAGE_NO_RE.match(ln)]


def norm_key(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def running_headers(pages_raw: list[str]) -> tuple[set[str], dict[str, str]]:
    """첫 줄이 여러 쪽에 반복되면 러닝헤더로 판정. (키 집합, 키→표시문자열)"""
    counts: dict[str, int] = {}
    label: dict[str, str] = {}
    for raw in pages_raw:
        lines = [ln.strip() for ln in normalize(raw).split("\n") if ln.strip()]
        if not lines:
            continue
        k = norm_key(lines[0])
        if len(k) < 2 or len(k) > 40:
            continue
        counts[k] = counts.get(k, 0) + 1
        label.setdefault(k, lines[0])
    keys = {k for k, n in counts.items() if n >= RUNNING_HEADER_MIN_PAGES}
    return keys, {k: label[k] for k in keys}


# ──────────────────────────────────────────────── 섹션 추적
def looks_like_title(title: str) -> bool:
    """제목다운가? 숫자만 늘어선 표 행("5.5 12.1 4.1 1.50 …")을 절 제목으로 오인하지 않게."""
    letters = len(LETTER_RE.findall(title))
    return letters >= 2 and letters / len(title) >= 0.3


class SectionTracker:
    """장(chapter) 번호를 러닝헤더 전환으로 관리하고, 그 장에 속한 절 제목만 인정한다."""

    def __init__(self) -> None:
        self.chapter_no: str | None = None
        self.chapter_title: str | None = None
        self.section: str | None = None

    def enter_page(self, header_label: str | None) -> None:
        if header_label is not None and header_label != self.chapter_title:
            self.chapter_title = header_label
            m = CHAPTER_RE.match(header_label)
            self.chapter_no = m.group(1) if m else None
            self.section = None  # 장이 바뀌면 절 carry 를 끊는다

    def feed(self, line: str) -> None:
        m = CHAPTER_RE.match(line)
        if (
            m
            and self.chapter_title
            and norm_key(m.group(2)) == norm_key(re.sub(r"^\d{1,2}\.?\s*", "", self.chapter_title))
        ):
            self.chapter_no = m.group(1)
            self.section = line
            return
        h = HEADING_RE.match(line)
        if h and self.chapter_no is not None and h.group(1) == self.chapter_no:
            if looks_like_title(h.group(3)):
                self.section = line

    def current(self, fallback: str) -> str:
        return self.section or self.chapter_title or fallback


# ──────────────────────────────────────────────── 청킹
def split_page(lines: list[str]) -> list[list[str]]:
    """페이지 줄 목록을 MAX_CHARS 이하 덩어리로 균등 분할. 페이지 밖으로 절대 나가지 않는다."""
    total = sum(len(ln) for ln in lines) + max(0, len(lines) - 1)
    if total < MIN_CHARS:
        return []
    parts = max(1, math.ceil(total / MAX_CHARS))
    target = math.ceil(total / parts)
    chunks: list[list[str]] = []
    buf: list[str] = []
    size = 0
    for ln in lines:
        add = len(ln) + (1 if buf else 0)
        if buf and size + add > target:
            chunks.append(buf)
            buf, size = [], 0
            add = len(ln)
        buf.append(ln)
        size += add
    if buf:
        chunks.append(buf)
    # 꼬리가 MIN_CHARS 미만이면 직전 청크에 병합 — 모든 청크가 MIN_CHARS 를 만족해야 한다.
    # pop 을 먼저 하고 새 리스트를 만든다. `chunks[-2] += chunks.pop()` 로 쓰면 pop 이 길이를
    # 줄인 뒤에 -2 가 다시 계산돼 엉뚱한 슬롯에 쓰이고 두 청크가 같은 객체가 된다.
    if len(chunks) >= 2 and len("\n".join(chunks[-1])) < MIN_CHARS:
        tail = chunks.pop()
        chunks[-1] = chunks[-1] + tail
    return chunks


def chunk_manual(pdf_path: Path, manual_id: str, model: str) -> tuple[list[dict], dict]:
    with pdfplumber.open(pdf_path) as pdf:
        pages_raw = [(p.extract_text() or "") for p in pdf.pages]
    header_keys, header_label = running_headers(pages_raw)

    tracker = SectionTracker()
    records: list[dict] = []
    page_texts: dict[int, str] = {}
    empty_pages = 0
    for pno, raw in enumerate(pages_raw, start=1):
        first = norm_key(raw.strip().split("\n")[0]) if raw.strip() else ""
        tracker.enter_page(header_label.get(first))
        lines = page_lines(raw, header_keys)
        page_texts[pno] = "\n".join(lines)
        groups = split_page(lines)
        if not groups:
            empty_pages += 1
            continue
        for idx, group in enumerate(groups):
            # 첫 줄이 절 제목이면 그 청크부터 새 섹션에 속한다 → 첫 줄만 먼저 먹이고 확정
            tracker.feed(group[0])
            section = tracker.current(header_label.get(first, "") or lines[0][:40])
            for ln in group[1:]:
                tracker.feed(ln)
            text = "\n".join(group)
            records.append(
                {
                    "chunk_id": f"{manual_id}-p{pno:04d}-{idx:02d}",
                    "manual_id": manual_id,
                    "model": model,
                    "page": pno,
                    "section": section,
                    "text": text,
                    "char_len": len(text),
                }
            )
    stats = {
        "manual_id": manual_id,
        "model": model,
        "pages_total": len(pages_raw),
        "pages_indexed": len(pages_raw) - empty_pages,
        "chunks": len(records),
        "chars": sum(r["char_len"] for r in records),
    }
    return records, {"stats": stats, "page_texts": page_texts}


# ──────────────────────────────────────────────── 자가 검증
KEYS = ("chunk_id", "manual_id", "model", "page", "section", "text", "char_len")


def verify(records: list[dict], page_texts: dict[str, dict[int, str]]) -> None:
    seen: set[str] = set()
    for r in records:
        assert tuple(r.keys()) == KEYS, f"키 불일치: {list(r.keys())}"
        assert isinstance(r["page"], int) and r["page"] >= 1, f"page 이상: {r['chunk_id']}"
        assert r["model"] in ("iG5A", "S100"), f"model enum 위반: {r['model']}"  # D6·D13
        assert r["char_len"] == len(r["text"]) >= MIN_CHARS, f"char_len 위반: {r['chunk_id']}"
        assert isinstance(r["section"], str), f"section 타입 위반: {r['chunk_id']}"
        assert CHUNK_ID_RE.match(r["chunk_id"]), f"chunk_id 형식 위반: {r['chunk_id']}"
        assert r["chunk_id"] not in seen, f"chunk_id 중복: {r['chunk_id']}"
        seen.add(r["chunk_id"])
        # 페이지 경계 불변식 ①: 청크 본문은 그 페이지 정제 텍스트의 부분 문자열이어야 한다
        assert r["text"] in page_texts[r["manual_id"]][r["page"]], (
            f"페이지 경계 초과: {r['chunk_id']}"
        )
    assert records == sorted(records, key=lambda r: r["chunk_id"]), "출력 정렬 위반 (D19 멱등)"

    # 페이지 경계 불변식 ②: 한 페이지의 청크를 idx 순으로 이으면 그 페이지 정제 텍스트와
    # 정확히 같아야 한다. 부분 문자열 검사만으로는 못 잡는 유실·중복(같은 구간을 두 청크가
    # 나눠 갖는 병합 버그)까지 여기서 걸린다.
    by_page: dict[tuple[str, int], list[dict]] = {}
    for r in records:
        by_page.setdefault((r["manual_id"], r["page"]), []).append(r)
    for (mid, page), rs in by_page.items():
        joined = "\n".join(x["text"] for x in sorted(rs, key=lambda x: x["chunk_id"]))
        assert joined == page_texts[mid][page], f"페이지 재구성 불일치: {mid} p.{page}"


# ──────────────────────────────────────────────── 통계 출력
def percentile(xs: list[int], q: float) -> int:
    if not xs:
        return 0
    s = sorted(xs)
    return s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))]


def report(all_stats: list[dict], records: list[dict]) -> None:
    print()
    print("| 매뉴얼 | model | 전체 쪽 | 색인 쪽 | 청크 | 총 문자 | 평균 | p50 | p90 | 최대 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    rows = all_stats + [
        {
            "manual_id": "**합계**",
            "model": "—",
            "pages_total": sum(s["pages_total"] for s in all_stats),
            "pages_indexed": sum(s["pages_indexed"] for s in all_stats),
            "chunks": len(records),
            "chars": sum(r["char_len"] for r in records),
        }
    ]
    for s in rows:
        lens = [
            r["char_len"]
            for r in records
            if s["manual_id"].startswith("**") or r["manual_id"] == s["manual_id"]
        ]
        avg = round(s["chars"] / s["chunks"]) if s["chunks"] else 0
        print(
            f"| {s['manual_id']} | {s['model']} | {s['pages_total']} | {s['pages_indexed']} | "
            f"{s['chunks']} | {s['chars']:,} | {avg} | {percentile(lens, 0.5)} | "
            f"{percentile(lens, 0.9)} | {max(lens) if lens else 0} |"
        )


# ──────────────────────────────────────────────── main
def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 대응
    manifest = check_manifest()

    records: list[dict] = []
    page_texts: dict[str, dict[int, str]] = {}
    all_stats: list[dict] = []
    for m in manifest["manuals"]:
        recs, aux = chunk_manual(RAW / m["file"], m["id"], m["model"])
        records += recs
        page_texts[m["id"]] = aux["page_texts"]
        all_stats.append(aux["stats"])
        print(f"[청킹] {m['id']}: {aux['stats']['chunks']}청크")

    records.sort(key=lambda r: r["chunk_id"])
    verify(records, page_texts)

    EXTRACTED.mkdir(exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"[완료] {OUTPUT}  sha256={sha256_of(OUTPUT)[:16]}…")
    report(all_stats, records)


if __name__ == "__main__":
    main()
