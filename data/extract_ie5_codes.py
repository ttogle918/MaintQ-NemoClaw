# -*- coding: utf-8 -*-
"""IE5 표준 매뉴얼 에러코드 **후보** 추출 (P29 · Sprint 14 MQ-1402~1404).

입력 : data/raw/IE5_User Manual(Standard)_Kor_V1.0_200526.pdf (151p, 읽기 전용)
출력 : data/extracted/ie5_code_candidates.json      — 후보 파일 (`_status` 는 **한국어 초안 마커**.
       `data/seed.py error_codes_gate()` 가 *"초안"·"승인 전"* 으로 판정하므로 같은 어휘를 쓴다 —
       `"pending"` 으로 두면 그 게이트를 재사용하는 쪽에서 **승인으로 읽힌다**)
       spikes/fixtures/ie5_p125_geometry.json       — PDF 없이 도는 회귀 픽스처 (MQ-1405)

전략 :
  ① 원인·대책 표(물리 p125·p126, 13.3 "고장 대책")에는 **괘선이 없다**(`page.lines` 세로선 0개).
     기본 `lines` 전략은 빈 셀만 낸다. 그러나 셀 배경 rect 에서 유래한 **세로 edge 는 있으므로**
     `page.edges` 의 `orientation=='v'` x 좌표를 **클러스터링해 열 경계를 유도**하고
     `extract_tables({"vertical_strategy":"explicit", ...})` 로 3열을 얻는다.
     ⛔ 좌표 하드코딩 금지 — p125 는 84.98/160.98/314.39/474.36, p126 은 99.64/175.38/332.50/488.49
        으로 **페이지마다 다르다**(홀·짝 여백 미러링). 실측값은 주석의 예시일 뿐 상수가 아니다.
        🔴 위 값은 **클램프 전** 원계산값이다(마지막 경계가 페이지 단어 범위를 벗어난 원본 edge
        좌표) — `column_bounds()` 가 글자 범위로 클램프한 **최종** 산출값(D107 결정문 예시,
        p125 우측 466.89 · p126 우측 487.26)과 다르다. 같은 표를 가리키는 두 값이라 나란히
        읽으면 "코드와 결정문이 어긋났다"로 오독하기 쉽다 — 오독이 아니라 클램프 전/후 차이다
        (sprint-14 §9 이월 ②).
  ② 가로 경계도 같은 `page.edges` 에서 유도한다. `horizontal_strategy:"text"` 는 **글자 줄 단위**로
     행을 끊어 "이 줄이 어느 보호기능의 것인가"를 다시 추론해야 하는데, 그 추론이 바로
     `extract_error_codes.span_key()` 가 금지한 "가장 가까운 항목으로 흘려보내기"다.
     셀 배경 rect 의 가로 edge 가 **병합 셀 경계를 그대로** 알려주므로 그걸 쓴다.
  ③ 본문에서 `한글명(코드)` 괄호 표기를 정규식으로 뽑아 `코드 ↔ 한글명` 사전을 만들고
     ①의 표 명칭과 조인한다.
  ④ 조인 실패는 **버리지 않고** `_unmatched` 에 남긴다 (양방향).
  ⑤ **잘라낸 것도 남긴다** — `_unmatched` 는 버킷 **4종**이다:
       `codes`                    조인 실패 (코드는 있는데 표 명칭에 못 붙였다)
       `codes_excluded_by_shape`  코드 **형상**이 좁아 파이프라인에 안 들어온 것 (③의 정규식 밖)
       `codes_without_name`       본문에 코드 리터럴은 있으나 **괄호 표기가 없어** 못 들어온 것
     뒤의 두 버킷이 **리콜(recall) 축**이다. 이것들이 없으면 검수자가
     `codes_found` 를 보고 *"본문에 이만큼밖에 없구나"* 라고 **틀리게** 결론 낸다.
  ⑥ 코드 집계·차집합은 **대문자 canonical** 로 접는다 (D25). 원표기는 버리지 않고
     `display_code`·`display_variants` 에 보존한다 — D25 는 canonical 매칭이지 원표기 폐기가 아니다.

주의 (실측으로 확인한 함정) :
  🔴 `보호 기능` 열의 코드는 **텍스트가 아니라 7-세그먼트 이미지**다 (OCt·GFt·GCt…).
     텍스트로 남는 것은 이미지 아래의 한글 캡션뿐이라 **표만으로는 코드를 알 수 없다** — ③의 조인이
     필요한 이유가 이것이다.
  🔴 캡션이 열 경계를 **넘어 흐르는 밴드가 있다** (p126 마지막: `파라미터 저장 이상`·`하드웨어 이상`
     두 캡션이 나란히 놓여 `이상 원인` 열 안까지 들어온다). `extract_tables()` 는 이를 조용히
     잘라 `파라미터 저장` 만 준다 — 그래서 명칭 열은 **단어 좌표로 읽고 넘침을 탐지**한다.
     넘친 밴드는 추측으로 복원하지 않고 `name_clipped` 로 표시해 `_unmatched.names` 로 보낸다.
  🔴 `이상 원인`·`대 책` 셀이 **두 보호기능에 걸쳐 병합된 밴드**가 있다
     (p125 `인버터 과부하`+`과부하 트립`, p126 `A접점`+`B접점`). 원문이 한 셀로 묶은 것이므로
     두 명칭에 같은 원인·대책을 준다 — 다만 **추측이 아님을 남기려고** `merged_with` 로 기록한다.
  🔴 캡션이 아예 없는 밴드가 있다 (p126 `- - - L` 7-세그 이미지, 지령 관련). 이름을 지어내지 않고
     빈 문자열로 두고 `_unmatched.names` 에 밴드 좌표와 함께 남긴다.
  🔴 같은 코드가 **대소문자만 다르게** 인쇄된다 (`Ovt`/`OVt` · `Lvt`/`LVt` · `RPM`/`rPM`/`rPm`/`rpm`).
     접지 않고 세면 `_unmatched.codes` 가 부풀어 **사람 검수 우선순위가 왜곡된다**
     (실측: 접기 전 35종 → 접은 뒤 24종, 약 46% 과대보고였다). D25 가 정확히 이 사고를
     막으려는 결정이다.

⛔ 이 스크립트가 **쓰지 않는** 것 (D99 · CLAUDE.md 절대규칙 5) :
  - `data/extracted/error_codes.json` (사람이 승인한 정본) — **읽기만** 한다(중복 코드 확인용)
  - `data/raw/**` 전부 — manifest.json 포함. IE5 를 manifest 에 등재하면
    `spikes/citation_render.py ⑨` 가 `validate_model("IE5")` 에서 ValueError 로 죽는다.
    등재·model enum 확장은 P11 의 일이고 그 앞에 사람 검수가 있다 (sprint-14 §0-5·§7-1).

D9 : 실패는 예외가 아니라 상태로 돌려준다 — 열 경계를 못 찾거나 3열이 아니면 그 페이지를
     **스킵 + 경고**하고 그 사실을 후보 파일 `_warnings` 에 남긴다. 추측으로 채우지 않는다.
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
REPO = ROOT.parent
RAW = ROOT / "raw"
EXTRACTED = ROOT / "extracted"
FIXTURES = REPO / "spikes" / "fixtures"

PDF_NAME = "IE5_User Manual(Standard)_Kor_V1.0_200526.pdf"
MANUAL_ID = "ie5-standard"  # ⚠ manifest.json 미등재 (P11 소관) — 후보 파일 안에서만 쓰는 식별자
TABLE_PAGES = (125, 126)  # 13.3 고장 대책 (PDF 물리 페이지, D26)

CANDIDATE = EXTRACTED / "ie5_code_candidates.json"
CANONICAL = EXTRACTED / "error_codes.json"  # 읽기 전용 (D99)
GEOMETRY_FIXTURE = FIXTURES / "ie5_p125_geometry.json"

BULLET = ""  # 매뉴얼 불릿 글리프 (PUA) — `extract_error_codes.split_bullets()` 와 동일
X_TOL = 3.0  # 세로 edge x 클러스터 허용 간격 (pt)
Y_TOL = 1.5  # 가로 경계 y 클러스터 허용 간격 (pt) — 테두리 두께가 0.2~0.9pt 라 그보다 크게
MIN_LEN_RATIO = 0.25  # 표 열 경계로 인정할 최소 누적 길이 (최장 클러스터 대비)
MAX_NAME_TOKENS = 4  # 본문 괄호 앞 명칭 후보의 최대 어절 수 ("인버터 냉각 핀 과열" = 4)
MIN_NAME_LEN = 3  # 정규화 후 3자 미만 명칭은 조인 후보로 쓰지 않는다 (오탐 방지)

# 본문 `한글명(코드)` — 괄호 안에 다른 괄호가 없어야 한다.
#
# 🔴 코드를 **영문자 3자**로 좁힌 이유 (판단이 개입한 유일한 지점이라 근거를 남긴다):
#    좁히지 않고 `[A-Za-z][A-Za-z0-9]{1,3}` 로 두면 이 매뉴얼이 괄호로 쓰는 **파라미터 코드**가
#    전부 딸려 온다 — 실측 1회 실행에서 `P25`·`P43`·`P77`·`FDT-1`·`V1`·`SHFT`·`Push` 등
#    **90종 이상**이 잡혀 `_unmatched.codes` 가 의미를 잃었다.
#    IE5 의 트립 표시는 7-세그 3자리이고, §0-2 가 실측으로 확인한 12종
#    (OCt·Ovt·OHt·GCt·CoL·Lvt·HWt·IOL·EtA·EtB·Err·nOn)이 **전부 이 조건을 만족**한다.
#    숫자를 배제하면 `P25` 형 파라미터가 구조적으로 들어올 자리가 없어진다.
#    ⚠ 그래도 3자 영문 키패드 라벨(`RUN`·`SET`·`drv`·`vOL` 등)은 남는다 —
#      **지우지 않고** `_unmatched.codes` 에 그대로 둔다. 사람이 보고 거르는 것이 맞고,
#      임의로 제외하면 진짜 코드를 같이 지울 위험이 생긴다(절대규칙 6).
#    🔴 **그래서 잘라낸 쪽도 산출물에 남긴다.** 사람이 승인한 정본 `error_codes.json` 65종 중
#      **16종이 이 형상 밖**이다 (ALOR·BX·EFAN·ERRC·FANW·FIDL·FLTL·HOLD·IOLW·LV2·OC2·OLOR·
#      PTCT·RERR·TRER·__L). 즉 스펙 형상 `[A-Za-z][A-Za-z0-9]{1,3}` 이 **정본이 실제로 쓰는
#      분포**였다. 좁힌 것은 유지하되(파라미터 90종 혼입은 실측된 사실이다) **차집합을 제3
#      버킷 `_unmatched.codes_excluded_by_shape` 로 내보낸다** — `_unmatched.names` 에서
#      이미 택한 태도(*"못 붙인 것을 지우지 않는다"*)와 같게 만든다.
BODY_CODE_RE = re.compile(r"([가-힣][가-힣A-Za-z0-9 :]{0,20}?)\s*[(（]\s*([A-Za-z]{3})\s*[)）]")
# 스펙 형상 — 이름 부분은 `BODY_CODE_RE` 와 **글자 하나까지 같고** 코드 부분만 넓다.
# 두 정규식을 각각 돌린 뒤 코드 형상으로 갈라 두 버킷을 만든다. 갈라진 합이 스펙 스캔 총수와
# 다르면 그 전제가 깨진 것이므로 `_warnings` 로 보고한다(조용히 넘기지 않는다).
SPEC_CODE_RE = re.compile(
    r"([가-힣][가-힣A-Za-z0-9 :]{0,20}?)\s*[(（]\s*([A-Za-z][A-Za-z0-9]{1,3})\s*[)）]"
)
NARROW_SHAPE_RE = re.compile(r"[A-Za-z]{3}")
HEADER_KEYS = ("보호기능", "이상원인", "대책")

# sprint-14 §0-2 가 실측으로 확인한 IE5 트립 코드 12종 (물리 페이지까지 확인됨).
# ⛔ 이 목록은 **리콜 측정용**이지 정답지가 아니다 — 여기 있는 코드에 이름을 지어 붙이지 않는다.
#    괄호 표기가 없어 파이프라인에 못 들어온 것은 `_unmatched.codes_without_name` 으로 낸다.
CONFIRMED_CODES = (
    "OCt",
    "Ovt",
    "OHt",
    "GCt",
    "CoL",
    "Lvt",
    "HWt",
    "IOL",
    "EtA",
    "EtB",
    "Err",
    "nOn",
)


# ──────────────────────────────────────────────── 공통 유틸
def sha256_of(path: Path) -> str:
    """`extract_error_codes.sha256_of()` 와 동일 방식 (1MB 스트리밍)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\n", " ")).strip()


def canon(code: str) -> str:
    """코드 canonical 키 — **대문자 접기** (D25).

    D25 는 *"저장은 대문자 canonical, `display_code` 에 원표기 보존, lookup 은 case-insensitive"*
    이고 근거가 *"통일 없으면 정상 코드가 not_found 로 새어 S4 오탐"* 이다. 이 스크립트에서
    통일하지 않으면 같은 사고의 축소판이 난다 — `Ovt` 는 조인 성공인데 `OVt` 가 미매칭으로
    남아 검수 대기열이 부푼다.
    """
    return (code or "").upper()


def fold_occurrences(occ_list: list[dict]) -> list[dict]:
    """괄호 표기 발생 목록 → canonical 로 접은 버킷 항목 (canonical 오름차순).

    원표기는 **버리지 않는다** — 대표 표기는 문서 등장 순 첫 것을 `code` 로 두고,
    관측된 표기 전부를 `display_variants` 로 남긴다.
    """
    by: dict[str, dict] = {}
    for o in occ_list:
        key = canon(o["code"])
        entry = by.setdefault(
            key,
            {
                "code": o["code"],
                "canonical_code": key,
                "display_variants": [],
                "name_candidates": [],
                "pages": [],
            },
        )
        for field, value in (
            ("display_variants", o["code"]),
            ("name_candidates", o["name_raw"]),
            ("pages", o["page"]),
        ):
            if value not in entry[field]:
                entry[field].append(value)
    return [by[k] for k in sorted(by)]


def norm_key(s: str) -> str:
    """조인 키 ⓐ — 괄호 내용 제거 후 **공백 전부 제거**."""
    s = re.sub(r"[(（][^)）]*[)）]", "", s or "")
    return re.sub(r"\s+", "", s)


def strip_inverter(s: str) -> str:
    """조인 키 ⓑ — 접두어 `인버터` 제거 (본문 '인버터 냉각 핀 과열' vs 표 '냉각핀 과열')."""
    return s[len("인버터") :] if s.startswith("인버터") else s


def cluster(values: list[float], tol: float) -> list[list[float]]:
    """정렬 후 인접 간격이 `tol` 이하인 것들을 한 덩어리로 묶는다."""
    out: list[list[float]] = []
    for v in sorted(values):
        if out and v - out[-1][-1] <= tol:
            out[-1].append(v)
        else:
            out.append([v])
    return out


def split_bullets(cell: str) -> list[str]:
    """불릿 셀 → 문장 리스트. 셀 안의 개행은 문장 내 이어붙임."""
    if not cell:
        return []
    parts = [clean(p) for p in cell.split(BULLET)]
    return [p for p in parts if p]


# ──────────────────────────────────────────────── MQ-1402 ① 열 경계 유도
def text_extent(page) -> tuple[float, float] | None:
    """`horizontal_strategy:"text"`/`"explicit"` 가 만드는 가로선의 x 범위.

    pdfplumber 는 글자에서 유도한 가로선을 **페이지 전체 단어의 min x0 ~ max x1** 로 긋는다
    (`pdfplumber.table.words_to_edges_h`). 이 범위를 벗어난 세로 경계는 가로선과 교차하지 못해
    **조용히 버려진다** — 실측: p125 의 우측 경계 474.36 은 단어 최대 x1(466.89)보다 커서
    3열이 아니라 **2열**로 떨어졌다. 그래서 바깥쪽 두 경계는 이 범위 안으로 클램프한다.
    """
    words = page.extract_words()
    if not words:
        return None
    try:  # 실제 사용 함수를 그대로 부르는 것이 정확하다
        from pdfplumber.table import words_to_edges_h

        edges = words_to_edges_h(words)
        if edges:
            return min(e["x0"] for e in edges), max(e["x1"] for e in edges)
    except Exception:  # noqa: BLE001 — 내부 API 이므로 사라지면 단어 범위로 근사한다
        pass
    return min(w["x0"] for w in words), max(w["x1"] for w in words)


def vertical_clusters(page) -> list[dict]:
    """`page.edges` 의 세로 edge 를 x 로 클러스터링 → [{x, sumlen, top, bottom, n}] (x 오름차순).

    누적 길이(`sumlen`)로 무게를 준다 — 표의 열 경계는 표 높이만큼 이어지지만 머리말 밑줄·
    주의 상자 테두리 같은 것은 짧다.
    """
    by_x: dict[float, list] = {}
    for e in page.edges:
        if e["orientation"] == "v":
            by_x.setdefault(round(e["x0"], 1), []).append(e)
    out: list[dict] = []
    for group in cluster(list(by_x), X_TOL):
        es = [e for k in group for e in by_x[k]]
        out.append(
            {
                "x": sum(e["x0"] for e in es) / len(es),
                "sumlen": sum(e["bottom"] - e["top"] for e in es),
                "top": min(e["top"] for e in es),
                "bottom": max(e["bottom"] for e in es),
                "n": len(es),
            }
        )
    return out


def column_bounds(page) -> tuple[list[float] | None, tuple[float, float] | None, str]:
    """세로 edge 클러스터 → (열 경계 4개, 표의 y 범위, 사유).

    실패하면 `(None, None, 사유)` — 예외를 던지지 않는다 (D9).
    y 범위는 **안쪽 경계 두 개의 세로 스팬 합집합**이다. 이것이 없으면 머리말 밑줄·주의 상자
    테두리·꼬리말 선까지 행 경계로 딸려 온다 (실측: 그대로 두면 p125 의 행 경계가 7개가 아니라
    **12개**가 되고 머리행 판정이 `['고장 대책','','']` 로 어긋난다).
    """
    clusters = vertical_clusters(page)
    if not clusters:
        return None, None, "세로 edge 가 0개 — 이 페이지에는 표 배경 rect 가 없다"
    longest = max(c["sumlen"] for c in clusters)
    keep = [c for c in clusters if c["sumlen"] >= MIN_LEN_RATIO * longest]
    bounds = [c["x"] for c in keep]
    if len(bounds) != 4:
        found = ", ".join(f"{c['x']:.1f}(len {c['sumlen']:.0f})" for c in keep)
        return None, None, f"열 경계가 4개가 아니다 — {len(bounds)}개 [{found}]"

    extent = text_extent(page)
    if extent is None:
        return None, None, "페이지에 단어가 없어 가로선 범위를 구할 수 없다"
    lo, hi = extent
    if not (lo <= bounds[1] <= hi and lo <= bounds[2] <= hi):
        return None, None, f"안쪽 경계가 글자 범위 [{lo:.1f}, {hi:.1f}] 밖이다 — {bounds}"
    bounds[0] = max(bounds[0], lo)
    bounds[-1] = min(bounds[-1], hi)

    inner = keep[1:-1]
    y_range = (
        round(min(c["top"] for c in inner), 2),
        round(max(c["bottom"] for c in inner), 2),
    )
    return [round(b, 2) for b in bounds], y_range, ""


def horizontal_bounds(page, x0: float, x1: float, y_range: tuple[float, float]) -> list[float]:
    """`[x0, x1]` 를 **가로지르는** 가로 edge 의 y → 행 경계 (클러스터 대표값, 오름차순).

    같은 열의 셀 배경 rect 들이 위·아래 테두리를 그리므로, 그 y 목록이 곧 그 열의 **병합 셀 경계**다.
    열마다 다르게 나오는 것이 정상이고, 그 차이가 곧 세로 병합 정보다 —
    실측: p125 의 `보호 기능` 열에는 y≈373.7 경계가 있으나 `이상 원인`·`대 책` 열에는 없다
    (= `인버터 과부하`·`과부하 트립` 이 원인·대책 셀을 공유한다).
    """
    top, bottom = y_range
    tops = [
        e["top"]
        for e in page.edges
        if e["orientation"] == "h"
        and e["x0"] <= x0 + 2
        and e["x1"] >= x1 - 2
        and top - Y_TOL <= e["top"] <= bottom + Y_TOL
    ]
    return [round(sum(g) / len(g), 2) for g in cluster(tops, Y_TOL)]


# ──────────────────────────────────────────────── MQ-1402 ② 표 추출
def _lines_text(words: list[dict]) -> str:
    """단어 목록 → 줄(top) 단위로 묶어 좌→우로 이어붙인 텍스트."""
    lines: dict[int, list] = {}
    for w in words:
        lines.setdefault(round(w["top"]), []).append(w)
    return clean(
        " ".join(
            " ".join(w["text"] for w in sorted(lines[t], key=lambda w: w["x0"]))
            for t in sorted(lines)
        )
    )


def band_name(
    page, x0: float, x1: float, x_raw: float, top: float, bottom: float
) -> tuple[str, bool, str]:
    """명칭 밴드의 캡션 텍스트 → (명칭, 열 경계를 넘쳤는가, 넘침 확인용 원문).

    ⚠ `extract_tables()` 를 쓰지 않는 이유: 이 열의 캡션은 열 경계를 **넘어 흐르는 경우가 있고**
    (p126 `파라미터 저장 이상`·`하드웨어 이상`) 표 추출은 그것을 조용히 잘라 낸다. 잘린 명칭을
    그대로 조인하면 "없는 이름"이 만들어진다. 단어 좌표로 읽어 **넘침을 사실로 탐지**하고,
    복원은 하지 않는다(추측 금지, 절대규칙 6) — 넘친 밴드는 `_unmatched.names` 로 보낸다.

    `x_raw` 는 원문 채취 우측 한계(= `대 책` 열 시작). 캡션이 넘쳐 봐야 `이상 원인` 열까지이므로
    거기까지만 담는다 — 사람이 볼 증거를 주되 밴드 전체를 통째로 옮겨 적지는 않는다.
    """
    words = [w for w in page.extract_words() if top - 1 <= w["top"] < bottom - 1]
    own = [w for w in words if x0 - 1 <= w["x0"] < x1]
    name = _lines_text(own)
    clipped = any(w["x1"] > x1 for w in own)
    raw = _lines_text([w for w in words if x0 - 1 <= w["x0"] < x_raw])
    return name, clipped, raw


def parse_table_page(page, pno: int) -> tuple[list[dict], dict, str]:
    """물리 페이지 1장 → (행 목록, 기하 정보, 경고). 실패는 경고 문자열로 돌려준다 (D9).

    행 = `{"보호기능": str, "이상원인": [str], "대책": [str], "manual_page": int, ...}`
    """
    bounds, y_range, why = column_bounds(page)
    geo: dict = {
        "page": pno,
        "v_edge_x": sorted({round(e["x0"], 2) for e in page.edges if e["orientation"] == "v"}),
        # D107 의 핵심 전제("괘선이 없다")를 회귀로 잠근다. `page.lines` 는 명시적 선 객체만
        # 센다 — `page.edges`(v_edge_x 의 출처)는 배경 rect 에서도 유래해 이미 0이 아니다.
        # 이 값이 0이어야 "왜 explicit 유도가 필요한가"가 산출물 자신에서 증명된다
        # (sprint-14 §9 이월 1 — 픽스처가 이 전제를 잠그지 못했던 갭).
        "v_line_count": sum(
            1 for ln in page.lines if abs(ln.get("x0", 0) - ln.get("x1", 1)) < 0.01
        ),
    }
    if bounds is None or y_range is None:
        return [], geo, f"p{pno}: 열 경계 유도 실패 — {why} (스킵)"

    geo["column_bounds"] = bounds
    geo["table_y_range"] = list(y_range)
    geo["text_extent"] = [round(v, 2) for v in (text_extent(page) or (0.0, 0.0))]
    geo["v_edges"] = sorted(
        [round(e["x0"], 2), round(e["top"], 2), round(e["bottom"], 2)]
        for e in page.edges
        if e["orientation"] == "v"
    )

    body_y = horizontal_bounds(page, bounds[1], bounds[2], y_range)
    name_y = horizontal_bounds(page, bounds[0], bounds[1], y_range)
    geo["row_bounds"] = body_y
    geo["name_row_bounds"] = name_y
    if len(body_y) < 3:  # 머리행 + 본문 1행 이상
        return [], geo, f"p{pno}: 가로 경계가 {len(body_y)}개뿐 — 행을 나눌 수 없다 (스킵)"

    tables = page.extract_tables(
        {
            "vertical_strategy": "explicit",
            "explicit_vertical_lines": bounds,
            "horizontal_strategy": "explicit",
            "explicit_horizontal_lines": body_y,
        }
    )
    if len(tables) != 1:
        return [], geo, f"p{pno}: 표가 {len(tables)}개 검출됨 — 1개여야 한다 (스킵)"
    grid = [[(c or "") for c in row] for row in tables[0]]
    geo["rows"] = [[clean(c) for c in row] for row in grid]
    widths = {len(row) for row in grid}
    if widths != {3}:
        return [], geo, f"p{pno}: 열 개수가 3이 아니다 — {sorted(widths)} (스킵)"

    header = [norm_key(c) for c in grid[0]]
    if not all(k in h for k, h in zip(HEADER_KEYS, header, strict=True)):
        return [], geo, f"p{pno}: 머리행이 '보호기능|이상원인|대책' 이 아니다 — {grid[0]} (스킵)"

    rows: list[dict] = []
    for i, cells in enumerate(grid[1:], start=1):
        top, bottom = body_y[i], body_y[i + 1]
        # 이 밴드 안에 있는 `보호 기능` 열의 세로 병합 경계 = 밴드가 품은 명칭 수
        inner = [y for y in name_y if top + Y_TOL < y < bottom - Y_TOL]
        edges_y = [top, *inner, bottom]
        names = [
            (
                *band_name(page, bounds[0], bounds[1], bounds[2], edges_y[j], edges_y[j + 1]),
                [round(edges_y[j], 2), round(edges_y[j + 1], 2)],
            )
            for j in range(len(edges_y) - 1)
        ]
        cause, action = split_bullets(cells[1]), split_bullets(cells[2])
        for name, clipped, raw, name_band in names:
            rows.append(
                {
                    "보호기능": name,
                    "이상원인": cause,
                    "대책": action,
                    "manual_page": pno,
                    # band = 원인·대책 셀의 y 구간(= 이 원인·대책이 실제로 놓인 칸),
                    # name_band = 그 안에서 이 명칭이 차지한 구간. 둘이 다르면 세로 병합이다.
                    "band": [round(top, 2), round(bottom, 2)],
                    "name_band": name_band,
                    "name_clipped": clipped,
                    "name_band_raw": raw,
                    "merged_with": [n for n, _, _, _ in names if n != name],
                }
            )
    return rows, geo, ""


def parse_tables(pdf) -> tuple[list[dict], list[dict], list[str]]:
    rows: list[dict] = []
    geos: list[dict] = []
    warnings: list[str] = []
    for pno in TABLE_PAGES:
        page_rows, geo, warn = parse_table_page(pdf.pages[pno - 1], pno)
        geos.append(geo)
        if warn:
            warnings.append(warn)
        rows += page_rows
    return rows, geos, warnings


# ──────────────────────────────────────────────── MQ-1403 ③ 본문 괄호 코드
def body_code_names(
    pdf,
) -> tuple[list[dict], list[dict], dict[str, list[int]], dict[str, list[int]], list[dict], str]:
    """본문 전체 스캔 → (occurrences, 형상 제외분, {canonical: exact 페이지}, {canonical: case_folded 추가 페이지}, 이름 없는 확정코드, 경고).

    등장 페이지는 괄호 표기와 별개로 **코드 리터럴 전수 스캔**으로 잡는다 — 괄호 밖에서만
    언급되는 페이지가 있기 때문이다(예: p63 "OHt, Lvt, ESt, HWt 등의 보호기능"). 앞뒤가
    영숫자면 제외한다(`IOLt` 안의 `IOL`·`OLt` 를 세지 않기 위해서다).
    리터럴 스캔은 **대소문자 무시**다 (D25) — `Ovt` 와 `OVt` 는 같은 코드이고, 접지 않으면
    같은 코드의 등장 페이지가 표기별로 쪼개진다(실측: `Ovt` 는 p67·p141 을 case-sensitive
    스캔에서 놓친다).

    🔴 **리콜 축 2개**를 함께 낸다 — 산출물이 *"무엇을 잃었는지"* 를 스스로 말하게 하려는 것이다:
      ⓐ `shape_excluded` : 스펙 형상(`[A-Za-z][A-Za-z0-9]{1,3}`)에는 맞지만 좁힌 형상
         (`[A-Za-z]{3}`)에 걸려 파이프라인에 못 들어온 괄호 표기 (`BODY_CODE_RE` 주석 참조)
      ⓑ `without_name` : §0-2 확정 12종 중 본문에 **코드 리터럴은 있으나 괄호 표기가 없어**
         `occ` 에 한 번도 들어오지 못한 코드. ⛔ 이름을 지어내지 않는다 — 코드와 페이지만 남긴다.
         (실측: `CoL`·`nOn` 2종. 이게 없으면 검수자가 `codes_found` 를 보고 "12종 중 10종만
          본문에 있다"고 **틀리게** 결론 낸다.)
    """
    occ: list[dict] = []
    shape_excluded: list[dict] = []
    n_spec = 0
    texts: list[str] = []
    for pno, page in enumerate(pdf.pages, start=1):
        flat = (page.extract_text() or "").replace("\n", " ")
        texts.append(flat)
        for m in BODY_CODE_RE.finditer(flat):
            occ.append({"code": m.group(2), "name_raw": clean(m.group(1)), "page": pno})
        for m in SPEC_CODE_RE.finditer(flat):
            n_spec += 1
            if not NARROW_SHAPE_RE.fullmatch(m.group(2)):
                shape_excluded.append(
                    {"code": m.group(2), "name_raw": clean(m.group(1)), "page": pno}
                )

    warn = ""
    if len(occ) + len(shape_excluded) != n_spec:
        warn = (
            f"형상 분할 전제 붕괴 — 좁은 스캔 {len(occ)}건 + 형상 제외 {len(shape_excluded)}건 "
            f"≠ 스펙 스캔 {n_spec}건. 두 정규식의 이름 부분이 어긋났다는 뜻이므로 "
            f"codes_excluded_by_shape 를 차집합으로 읽으면 안 된다"
        )

    wanted = (
        {canon(o["code"]) for o in occ}
        | {canon(c) for c in CONFIRMED_CODES}
        | {canon(o["code"]) for o in shape_excluded}
    )
    # 원표기(대소문자 그대로) 인벤토리 — canonical 하나에 실제로 관측된 표기들.
    known_variants: dict[str, set[str]] = {}
    for o in occ:
        known_variants.setdefault(canon(o["code"]), set()).add(o["code"])
    for o in shape_excluded:
        known_variants.setdefault(canon(o["code"]), set()).add(o["code"])

    pages_exact: dict[str, list[int]] = {}
    pages_case_folded: dict[str, list[int]] = {}
    for code in sorted(wanted):
        # "exact" = canonical 표기 자체 또는 본문에서 실제 관측된 원표기 그대로 리터럴 매치된
        # 페이지. "case_folded" = 대소문자를 무시했을 때만 추가로 걸리는 페이지 — 알려진 어느
        # 표기와도 대소문자가 다르다는 뜻이라 사람이 한 번 더 볼 값이다. D25 는 매칭을
        # case-insensitive 로 하라는 것이지 **증거에서 표기 차이를 지우라는 것이 아니다**
        # (sprint-14 §8 이월 ②, reviewer 권고 "높음").
        known = known_variants.get(code, set()) | {code}
        exact_pages: set[int] = set()
        for v in known:
            rx = re.compile(rf"(?<![A-Za-z0-9]){re.escape(v)}(?![A-Za-z0-9])")
            exact_pages |= {pno for pno, t in enumerate(texts, start=1) if rx.search(t)}
        rx_ci = re.compile(rf"(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])", re.IGNORECASE)
        all_hits = {pno for pno, t in enumerate(texts, start=1) if rx_ci.search(t)}
        pages_exact[code] = sorted(exact_pages)
        pages_case_folded[code] = sorted(all_hits - exact_pages)

    seen = {canon(o["code"]) for o in occ}
    without_name = [
        {
            "code": c,
            "canonical_code": canon(c),
            "pages": sorted(
                set(pages_exact.get(canon(c), [])) | set(pages_case_folded.get(canon(c), []))
            ),
            # 필드명은 `_unmatched.codes`·`codes_excluded_by_shape`·매칭 `codes` 와 **동일하게**
            # `code_pages_exact`/`code_pages_case_folded` 로 맞춘다 — 버킷마다 다른 이름을 쓰면
            # 지금 고치는 "pages 의미가 버킷마다 다르다"는 문제를 필드명 축에서 그대로 재현한다
            # (sprint-14 §8 이월 ①).
            "code_pages_exact": pages_exact.get(canon(c), []),
            "code_pages_case_folded": pages_case_folded.get(canon(c), []),
            "reason": (
                "본문에 코드 리터럴은 있으나 `한글명(코드)` 괄호 표기가 없어 조인 후보에 못 들어왔다 "
                "— 이름은 지어내지 않는다 (절대규칙 6)"
                if pages_exact.get(canon(c)) or pages_case_folded.get(canon(c))
                else "본문 전수 스캔에서 코드 리터럴 자체를 찾지 못했다 — §0-2 실측과 어긋난다"
            ),
        }
        for c in CONFIRMED_CODES
        if canon(c) not in seen
    ]
    return occ, shape_excluded, pages_exact, pages_case_folded, without_name, warn


def name_variants(phrase: str) -> list[str]:
    """괄호 앞 어구 → 조인 후보 명칭들 (뒤에서부터 1~4어절 접미 조합).

    본문 표기는 문장 안에 박혀 있어 앞쪽에 군더더기가 붙는다
    (예: `"…여러 종류의 트립이 발생한 경우 동시 과전류(OCt)"`). 후보를 어절 접미로 한정하고
    **정규화 후 완전 일치**만 채택한다 — 유사도 매칭이 아니다(절대규칙 6).
    정규화 후 3자 미만은 버린다(짧은 조각이 엉뚱한 표 명칭과 우연히 같아지는 것을 막는다).
    """
    tokens = [t for t in re.split(r"\s+", phrase.strip()) if t]
    out: list[str] = []
    for k in range(1, min(MAX_NAME_TOKENS, len(tokens)) + 1):
        cand = " ".join(tokens[-k:])
        if len(norm_key(cand)) >= MIN_NAME_LEN:
            out.append(cand)
    return out


def join(rows: list[dict], occ: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """표 명칭 ↔ 본문 코드 조인 → (매칭, 미매칭 코드, 미매칭 명칭).

    ⛔ 유사 명칭 추측 금지 — 정규화(공백 제거 → 실패 시 `인버터` 접두어 제거) **후 완전 일치**만
       채택한다. 실패한 쪽은 양방향 모두 남긴다(D99 의 "버리지 않는다" 태도).

    🔴 코드 축은 **대문자 canonical 로 접는다** (D25). 접기 전에는 `Ovt` 가 매칭인데 `OVt` 가
       미매칭으로 따로 남았다 — D25 가 *"통일 없으면 정상 코드가 not_found 로 샌다"* 고
       기각한 바로 그 상태다. 원표기는 `display_variants` 로 전량 보존한다.
    """
    # 표 명칭 인덱스: 정규화 키 → 행 인덱스들
    by_key: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        key = norm_key(r["보호기능"])
        if not key:
            continue
        by_key.setdefault(key, []).append(i)
        by_key.setdefault(strip_inverter(key), []).append(i)

    # 원표기 보존 — canonical 하나에 붙은 모든 표기 (문서 등장 순)
    variants: dict[str, list[str]] = {}
    for o in occ:
        vs = variants.setdefault(canon(o["code"]), [])
        if o["code"] not in vs:
            vs.append(o["code"])

    hit_rows: set[int] = set()
    matched_by_code: dict[tuple[str, int], dict] = {}  # (canonical, 표 행 인덱스) → 매칭 기록
    failed: list[dict] = []

    for o in occ:
        code = canon(o["code"])
        found: list[int] = []
        used_variant = ""
        for variant in name_variants(o["name_raw"]):
            key = norm_key(variant)
            idxs = by_key.get(key) or by_key.get(strip_inverter(key))
            if idxs:
                found, used_variant = idxs, variant
                break
        if not found:
            failed.append(o)
            continue
        for i in dict.fromkeys(found):
            hit_rows.add(i)
            key = (code, i)
            prev = matched_by_code.get(key)
            if prev is None:
                matched_by_code[key] = {
                    "code": o["code"],  # 조인을 만든 **원표기** (D25 — 원표기 폐기 아님)
                    "canonical_code": code,
                    "display_variants": variants[code],
                    "row": i,
                    "join_variant": used_variant,
                    "join_pages": [o["page"]],
                }
            elif o["page"] not in prev["join_pages"]:
                prev["join_pages"].append(o["page"])

    matched = sorted(matched_by_code.values(), key=lambda m: (m["row"], m["canonical_code"]))
    # 조인에 성공한 코드는 미매칭에서 뺀다 — **canonical 기준**이라 `OVt` 는 `Ovt` 성공에 흡수된다
    ok = {m["canonical_code"] for m in matched}
    unmatched_code_list = [e for e in fold_occurrences(failed) if e["canonical_code"] not in ok]
    unmatched_names = [
        {
            "name": rows[i]["보호기능"],
            "manual_page": rows[i]["manual_page"],
            "band": rows[i]["band"],
            "name_band": rows[i]["name_band"],
            "name_clipped": rows[i]["name_clipped"],
            "name_band_raw": rows[i]["name_band_raw"],
            "reason": (
                "명칭 텍스트 없음 — 7-세그 이미지만 있는 밴드"
                if not rows[i]["보호기능"]
                else (
                    "명칭이 열 경계를 넘쳐 잘렸다 — name_band_raw 로 사람이 판단"
                    if rows[i]["name_clipped"]
                    else "본문 괄호 표기에서 같은 명칭을 찾지 못함"
                )
            ),
        }
        for i in range(len(rows))
        if i not in hit_rows
    ]
    return matched, unmatched_code_list, unmatched_names


def detect_name_collisions(codes: list[dict], shape_excluded: list[dict]) -> None:
    """매칭 코드 ↔ 형상 제외 코드의 명칭 충돌을 **상호 참조**한다 (제자리에서 딕셔너리를 수정).

    실측 사례: `IOL`(매칭, 원인·대책까지 붙음, p110·p113)과 `IOLt`(형상 제외, p67)가
    **같은 명칭** "인버터 과부하"를 공유한다 — 매뉴얼 자신의 표기가 절 사이에서 갈린 것이다
    (12.6·11.5절은 `IOL`, 7절 기능 일람표는 `IOLt`). 이 충돌이 산출물에 안 보이면 사람이
    원인·대책까지 붙은 `IOL` 만 보고 확정으로 오독하기 쉽다
    (sprint-14 §8 Stage 1 reviewer 권고 — 우선순위 "가장 높음").

    ⛔ 정규화 후 **완전 일치**만 인정한다 — 유사 명칭 추측 금지 (절대규칙 6). 매칭 코드의
    표기·개수는 바꾸지 않는다 — 충돌 사실만 양방향으로 드러낸다.
    """
    matched_by_key: dict[str, list[str]] = {}
    for c in codes:
        matched_by_key.setdefault(norm_key(c["name_ko"]), []).append(c["canonical_code"])
    excluded_by_key: dict[str, list[str]] = {}
    for e in shape_excluded:
        for name in e.get("name_candidates", []):
            excluded_by_key.setdefault(norm_key(name), []).append(e["canonical_code"])

    for entry in shape_excluded:
        keys = {norm_key(n) for n in entry.get("name_candidates", [])}
        hits = sorted({code for k in keys for code in matched_by_key.get(k, [])})
        if hits:
            entry["name_collision_with"] = hits
    for c in codes:
        hits = sorted(set(excluded_by_key.get(norm_key(c["name_ko"]), [])))
        if hits:
            c["name_collision_with"] = hits


# ──────────────────────────────────────────────── MQ-1404 후보 파일
def known_canonical_codes() -> set[str]:
    """정본 `error_codes.json` 을 **읽기만** 해 이미 등재된 코드를 확인한다 (D99).

    IE5 는 model enum 밖이라 겹칠 일이 없지만, 코드 문자열이 같은 것이 있으면
    사람 검수 때 "같은 코드인가 다른 기종의 동명이인인가"를 먼저 봐야 한다(D13 복합키).
    """
    if not CANONICAL.exists():
        return set()
    try:
        doc = json.loads(CANONICAL.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {str(e.get("code", "")).upper() for e in doc.get("entries") or []}


def build_candidate(
    pdf_path: Path,
    rows: list[dict],
    matched: list[dict],
    unmatched_codes: list[dict],
    unmatched_names: list[dict],
    shape_excluded: list[dict],
    without_name: list[dict],
    code_pages_exact: dict[str, list[int]],
    code_pages_case_folded: dict[str, list[int]],
    n_codes: int,
    n_display: int,
    total_pages: int,
    warnings: list[str],
) -> dict:
    canonical = known_canonical_codes()
    codes: list[dict] = []
    for m in matched:
        r = rows[m["row"]]
        cp_exact = code_pages_exact.get(m["canonical_code"], [])
        cp_folded = code_pages_case_folded.get(m["canonical_code"], [])
        codes.append(
            {
                "code": m["code"],
                "display_code": m["code"],
                "display_variants": m["display_variants"],
                "canonical_code": m["canonical_code"],
                "table_row": m["row"],
                "name_ko": r["보호기능"],
                "cause": r["이상원인"],
                "action": r["대책"],
                "manual_page": r["manual_page"],
                "code_pages": sorted(set(cp_exact) | set(cp_folded)),
                "code_pages_exact": cp_exact,
                "code_pages_case_folded": cp_folded,
                "join_variant": m["join_variant"],
                "join_pages": sorted(m["join_pages"]),
                "merged_with": r["merged_with"],
                "collides_with_canonical_code": m["canonical_code"] in canonical,
            }
        )
    detect_name_collisions(codes, shape_excluded)
    return {
        "_status": "초안 — 사람 검수 전이라 DB 에 적재되지 않는다 (승인 전, D33·D99)",
        "_설명": (
            "IE5 표준 매뉴얼 추출 **후보** — 사람 검수 전이며 DB 에 적재되지 않는다 (D33·D99). "
            "정본 data/extracted/error_codes.json 은 이 스크립트가 읽기만 한다. "
            "model enum·manifest 등재는 P11 소관이라 여기서 건드리지 않는다. "
            "🔴 **P11 정본 병합 시 `code` 를 그대로 넣지 말 것** — 이 파일의 `code`/`display_code` 는 "
            "매뉴얼 **원표기**(`OHt`·`Ovt`)다. 정본 error_codes.json 과 DB 는 D25 에 따라 "
            "**대문자 canonical** 로 저장하고 원표기는 `display_code` 에 남긴다. 병합할 때 "
            "`canonical_code` 를 `code` 로, `display_code` 를 그대로 쓰면 된다 — 이 파일 안의 "
            "집계·차집합은 이미 `canonical_code` 기준으로 접혀 있다. "
            "⚠ `_stats.codes_found` 는 '본문에서 `한글명(영문 3자)` 로 표기된 토큰의 canonical 종류 수'이지 "
            "'에러코드 수'가 아니다 — 키패드 라벨(RUN·SET·drv 등)이 섞여 있고, 그것들은 "
            "`_unmatched.codes` 에 그대로 남는다(임의 제외하지 않는다, 절대규칙 6). "
            "🔴 `_unmatched` 는 버킷 **3종**이고 뒤의 둘이 **리콜(recall) 축**이다: "
            "`codes`= 조인 실패 · `codes_excluded_by_shape`= 코드 형상이 좁아 애초에 파이프라인에 "
            "못 들어온 것(스펙 형상 `[A-Za-z][A-Za-z0-9]{1,3}` 과의 차집합. 정본 65종 중 16종이 "
            "이 형상 밖이므로 무시하면 안 된다) · `codes_without_name`= §0-2 확정 12종 중 본문에 "
            "리터럴은 있으나 괄호 표기가 없어 못 들어온 것(이름 미상 — 지어내지 않는다). "
            "실제 검수 대상은 `codes`(조인 성공분) + `_unmatched` 3버킷 + "
            "`_unmatched.names`(표에 있으나 코드를 못 붙인 행)다."
        ),
        "_source": {
            "manual_id": MANUAL_ID,
            "manifest_registered": False,
            "file": pdf_path.name,
            "sha256": sha256_of(pdf_path),
            "pages": list(TABLE_PAGES),
            "total_pages": total_pages,
            "citation_basis": "PDF 물리 페이지 (D26)",
        },
        "_generated_at": str(date.today()),
        "_stats": {
            # canonical(대문자 접기, D25) 기준. `_display_variants` 는 접기 전 원표기 종류 수로,
            # 둘의 차이가 곧 "대소문자만 다른 중복이 몇 개였나"다.
            "codes_found": n_codes,
            "codes_found_display_variants": n_display,
            "table_rows": len(rows),
            "matched": len(codes),
            "matched_rows": len({c["table_row"] for c in codes}),
            "unmatched_codes": len(unmatched_codes),
            "unmatched_names": len(unmatched_names),
            "codes_excluded_by_shape": len(shape_excluded),
            "codes_without_name": len(without_name),
        },
        "_warnings": warnings,
        "_unmatched": {
            "codes": unmatched_codes,
            "names": unmatched_names,
            "codes_excluded_by_shape": shape_excluded,
            "codes_without_name": without_name,
        },
        "codes": codes,
    }


def build_fixture(
    pdf_path: Path,
    geos: list[dict],
    occ: list[dict],
    shape_excluded: list[dict],
    candidate: dict,
    total_pages: int,
) -> dict:
    """PDF 없이 도는 회귀 픽스처 (MQ-1405). 텍스트 조각·좌표만 담는다 — 원본 재배포가 아니다."""
    un = candidate["_unmatched"]
    return {
        "_설명": (
            "IE5 p125·p126 기하 픽스처 — spikes 가 PDF 없이 열 경계 유도·조인 로직을 검증한다. "
            "data/raw/*.pdf 는 git 에 없다(.gitignore). "
            "v_edges=[x0, top, bottom], column_bounds=유도된 4경계, rows=추출된 3열 텍스트. "
            "code_name_pairs=좁힌 형상(`[A-Za-z]{3}`)의 괄호 표기, "
            "shape_excluded_pairs=스펙 형상에는 맞지만 좁힌 형상 밖이라 제외된 괄호 표기 "
            "(둘의 합이 스펙 스캔 전량이다 — 스파이크가 차집합 무결성을 이걸로 검증한다)."
        ),
        "_source": {
            "manual_id": MANUAL_ID,
            "file": pdf_path.name,
            "sha256": candidate["_source"]["sha256"],
            "total_pages": total_pages,
        },
        "_generated_by": "data/extract_ie5_codes.py",
        "_generated_at": candidate["_generated_at"],
        "pages": geos,
        "code_name_pairs": occ,
        "shape_excluded_pairs": shape_excluded,
        "expected": {
            "stats": candidate["_stats"],
            "matched": [
                {
                    "code": c["code"],
                    "canonical_code": c["canonical_code"],
                    "display_variants": c["display_variants"],
                    "name_ko": c["name_ko"],
                    "join_variant": c["join_variant"],
                    "cause": c["cause"],
                    "action": c["action"],
                }
                for c in candidate["codes"]
            ],
            "unmatched_codes": [u["canonical_code"] for u in un["codes"]],
            "unmatched_names": [u["name"] for u in un["names"]],
            "codes_excluded_by_shape": [u["canonical_code"] for u in un["codes_excluded_by_shape"]],
            "codes_without_name": [u["canonical_code"] for u in un["codes_without_name"]],
        },
    }


def write_json(path: Path, doc: dict) -> None:
    """멱등 기록 — 내용이 같으면 다시 쓰지 않는다. (후보 파일이라 정본 가드는 두지 않는다)"""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        prev = path.read_text(encoding="utf-8")
        volatile = re.compile(r'"_generated_at": "[^"]*"')
        if volatile.sub("", prev) == volatile.sub("", text):
            print(f"[변경 없음] 기록 생략 — {path}")
            return
    path.write_text(text, encoding="utf-8")
    print(f"[기록] {path}")


# ──────────────────────────────────────────────── main
def run(pdf_path: Path) -> int:
    if not pdf_path.exists():
        print(f"[중단] 매뉴얼 파일 없음: {pdf_path}")
        return 1

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        rows, geos, warnings = parse_tables(pdf)
        occ, shape_occ, code_pages_exact, code_pages_case_folded, without_name, scan_warn = (
            body_code_names(pdf)
        )
    if scan_warn:
        warnings.append(scan_warn)

    n_codes = len({canon(o["code"]) for o in occ})
    n_display = len({o["code"] for o in occ})
    matched, unmatched_codes, unmatched_names = join(rows, occ)
    shape_excluded = fold_occurrences(shape_occ)

    # 조인 실패·형상 제외 버킷도 매칭 버킷과 **같은 방식**(exact/case_folded)의 code_pages 를
    # 받는다 — 이전에는 `pages`(괄호 표기 등장분)만 있어 GCt 처럼 리터럴로만 등장하는 페이지
    # (예: p117 의 `[GCt]` 표시)가 누락됐다 (sprint-14 §8 이월 ①, reviewer 권고).
    for bucket in (unmatched_codes, shape_excluded):
        for entry in bucket:
            code = entry["canonical_code"]
            entry["code_pages_exact"] = code_pages_exact.get(code, [])
            entry["code_pages_case_folded"] = code_pages_case_folded.get(code, [])

    candidate = build_candidate(
        pdf_path,
        rows,
        matched,
        unmatched_codes,
        unmatched_names,
        shape_excluded,
        without_name,
        code_pages_exact,
        code_pages_case_folded,
        n_codes,
        n_display,
        total_pages,
        warnings,
    )
    fixture = build_fixture(pdf_path, geos, occ, shape_occ, candidate, total_pages)

    print(f"[IE5 추출] {pdf_path.name} · {total_pages}p · 표 페이지 {list(TABLE_PAGES)}")
    for g in geos:
        bounds = g.get("column_bounds")
        state = f"열 경계 {bounds}" if bounds else "열 경계 유도 실패"
        print(f"  p{g['page']}: {state} · 행 경계 {len(g.get('row_bounds', []))}개")
    for w in warnings:
        print(f"  ⚠ {w}")
    st = candidate["_stats"]
    print(
        f"  코드 {st['codes_found']}종(canonical · 원표기 {st['codes_found_display_variants']}종) · "
        f"표 행 {st['table_rows']}건 → 조인 성공 {st['matched']}건({st['matched_rows']}행) · "
        f"미매칭 코드 {st['unmatched_codes']}종 · 미매칭 명칭 {st['unmatched_names']}건"
    )
    print(
        f"  ↳ 리콜 축 — 형상 제외 {st['codes_excluded_by_shape']}종 · "
        f"괄호 표기 없는 확정코드 {st['codes_without_name']}종"
    )
    for u in candidate["_unmatched"]["codes"]:
        print(
            f"    - [코드 미매칭] {u['canonical_code']} 표기={u['display_variants']} "
            f"p{u['pages']} 명칭후보={u['name_candidates']}"
        )
    for u in candidate["_unmatched"]["names"]:
        print(f"    - [명칭 미매칭] p{u['manual_page']} {u['name']!r} — {u['reason']}")
    for u in candidate["_unmatched"]["codes_without_name"]:
        print(f"    - [이름 없음] {u['canonical_code']}({u['code']}) p{u['pages']} — {u['reason']}")
    excluded = candidate["_unmatched"]["codes_excluded_by_shape"]
    print(
        f"    - [형상 제외] {len(excluded)}종: {', '.join(u['canonical_code'] for u in excluded)}"
    )

    write_json(CANDIDATE, candidate)
    write_json(GEOMETRY_FIXTURE, fixture)
    return 0


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 대응

    ap = argparse.ArgumentParser(
        description="IE5 표준 매뉴얼 에러코드 후보 추출 (P29) — 정본·manifest 를 쓰지 않는다"
    )
    ap.add_argument(
        "--pdf",
        default=str(RAW / PDF_NAME),
        help="입력 PDF 경로 (기본: data/raw/ 의 IE5 표준판, 읽기 전용)",
    )
    args = ap.parse_args()
    raise SystemExit(run(Path(args.pdf)))


if __name__ == "__main__":
    main()
