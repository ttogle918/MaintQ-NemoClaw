# -*- coding: utf-8 -*-
"""`actions` 부재 주장 3자 대조 엔진 + 검수 패키지 렌더러 (MQ-1309, Sprint 13 Stage 3).

저장소는 같은 결측 34건(S100 25 / iG5A 9)에 대해 **서로 충돌하는 진단 셋**을 갖고 있다
(파서 주장 `_pending_review` · triage 라벨 · 백로그 P31). 셋 다 Sprint 9 산출물인데 서로를
참조하지 않는다. 이 모듈은 그 불일치를 **독립 2차 판독기**(Elice DocVision, D105)로 해소한다.

⛔ **목표는 "회수"가 아니라 "불일치 해소"다.** 부재가 사실로 확정되는 것(`CONFIRMED_ABSENT`)도
똑같이 유효한 산출이다. 회수 건수를 성공 지표로 삼으면 없는 조치문을 만들어내는 압력이 생기고,
그것은 **절대규칙 3**(안전 문구는 매뉴얼 근거 없이 생성 금지) 위반으로 직결된다.

## 이 모듈이 지키는 것

1. **정본을 쓰지 않는다 (D99).** 입력 3종(`error_codes.json` · `error_codes_actions.candidate.json`
   · `extract_triage.json`)은 전부 **읽기 전용**이고, 실행 전후 sha256 을 재서 리포트에 인쇄한다.
   출력은 `data/analysis/actions_absence_verification.md` · `data/extracted/*.json` 둘뿐이다.
2. **기본은 dry-run — 네트워크 0 · 지출 0.** 인자 없이 실행하면 `extract_page(...,
   allow_purchase=False)` 만 부르므로 캐시가 없으면 그대로 `UNREAD` 다. 캐시 0건에서도 완주하며
   전건 `INCONCLUSIVE` + `NOT_READ` 경고 + **exit 0**.
3. **지출은 이중 게이트.** `--allow-purchase` 는 `--confirm-won <총액>` 이
   `cost_estimate()["won_total"]` 과 **정확히 일치**할 때만 진행한다.
4. **부재 주장에는 양성 축을 건다 (P30 · D65).** `control_codes()` 가 판독 범위 안에서
   *`actions` 가 이미 있는* 코드를 **같은 알고리즘으로** 찾고, 그 결과를 **정본 `actions`
   문장과 대조**한다(`action_text_match`). 대조 통과가 0건이면 `READER_BLIND` 경고와 함께
   그 모델 스코프의 **모든 `CONFIRMED_ABSENT` 를 `INCONCLUSIVE` 로 강등**한다 —
   *"조치문이 실재하는 코드조차 못 찾는 판독기의 '없다'는 근거가 아니다."*
   ⛔ 생존 축을 *"`ACTION_FOUND` 가 1건이라도 나왔는가"* 로 재면 안 된다 — 판독 범위의 1차
   표(트립·보호기능표)에는 항상 긴 설명 셀이 있어 **자명하게 참**이 되고 양성 축이 죽는다.
5. **"못 봤다"를 "없다"로 바꾸지 않는다 (D62).** 한 코드의 판독 대상 중 하나라도 미판독이면
   `unread_in_scope` 로 `CONFIRMED_ABSENT` 를 강등한다. `UNREAD` 는 축 우선순위가 0 이라
   여러 대상 결합(`max()`)에서 조용히 밀리기 때문에 별도 축이 필요하다.
6. **DB 를 열지 않는다.** 재시드도 하지 않는다.
7. 페이지는 전부 **PDF 물리 페이지**(D26). 인쇄 페이지 환산을 여기서 하지 않는다(D32).

## 급소 4가지 (이게 틀리면 1,530원이 전건 `INCONCLUSIVE` 로 끝난다)

① **앵커는 `error_name` 이 1차 축이다.** S100 9.2 조치사항표(p.420~421)의 항목 열은
  `Over Load`·`Out Phase Open` 같은 **LCD 영문명뿐이고 코드 토큰이 0개**다. iG5A p.202 도
  `code_tokens_found=0` 인데 6개 코드가 조치문을 갖는다(triage `ANCHOR_CONFLICT`). 코드 토큰으로
  앵커를 잡으면 대조군이 전멸하고 `READER_BLIND` 가 상시 발화해 판독 전액이 무효가 된다.
  → 앵커 = {`error_name`, `display_code`, `code`} 정규화(대소문자·공백 무시) **부분일치**.
② **축의 정의역은 페이지가 아니라 "읽은 페이지 union(대상 문서 범위)"다.** 앵커는 9.1(416~419)에,
  조치문은 9.2(420~421)에 있다. 페이지 단위로 재면 전부 `ANCHOR_ONLY` 가 된다.
③ **`{AMBIGUOUS, NOT_FOUND_ON_PAGE, UNCLASSIFIED, NO_CLAIM} × ACTION_FOUND` 는 `rowspan`
  귀속이 1:1 로 풀렸을 때만 `RECOVERABLE`**, 아니면 `STILL_AMBIGUOUS`(MQ-1310). 파서가 멈춘
  이유가 *"조치문이 5개 항목과 공유"* = 귀속 불가인데, Elice 가 그 셀을 읽어도 귀속이 안 되면
  회수 후보가 아니다(지어내기 압력 차단). iG5A `NTC` 가 실증 사례다 — 근거가 `text_window`
  폴백(귀속행 0)인데 파서 내부 분류가 `NOT_FOUND_ON_PAGE`(≠ `AMBIGUOUS`)라는 이유만으로
  예전엔 `RECOVERABLE` 이 났다. 같은 공유 조치문의 `HWT`·`EEP`·`ERR`·`COM`(`AMBIGUOUS`)은
  `STILL_AMBIGUOUS` 로 남았으니 데이터가 같은데 파서의 내부 분류 차이만으로 결론이 갈린
  것 — 네 칸 전부에 같은 귀속 조건을 걸어 통일했다.
④ **`_pending_review` 는 dict 가 아니라 문자열 35개**이고 그중 S100 `FANW` 1건은 **이미 회수돼
  정본에 있다**. 그래서 조인 대상은 34건이고 그 사실을 리포트에 인쇄한다.

## 공개 인터페이스 (`spikes/external_store_contract.py` ⓛ·ⓜ 가 임포트한다)

    READ_PLAN · VERDICTS · PARSER_CLAIMS · ELICE_AXES · ReadTarget
    cost_estimate() · classify_pending() · decide() · control_codes() · verify() · main()
    action_text_match() · is_action_text() · action_columns() · parse_tables() · axis_for()

임포트 형식은 공통 규약을 따른다 — `sys.path.insert(0, str(REPO_ROOT))` 후
`from data.external... import ...`. `__init__.py` 는 두지 않는다(암시적 네임스페이스).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Final

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data.external.elice_docvision import (  # noqa: E402
    PRICE_PER_PAGE_WON,
    EliceError,
    PageExtraction,
    extract_page,
)

# ──────────────────────────────────────────────── 경로 (전부 읽기 전용 입력 + 출력 2종)
DATA = REPO_ROOT / "data"
RAW = DATA / "raw"
EXTRACTED = DATA / "extracted"
ANALYSIS = DATA / "analysis"

ERROR_CODES = EXTRACTED / "error_codes.json"  # ★ 정본 — 읽기 전용 (D99)
CANDIDATE = EXTRACTED / "error_codes_actions.candidate.json"  # ★ 후보 — 읽기 전용 (D99)
TRIAGE = EXTRACTED / "extract_triage.json"  # ★ 라벨 — 읽기 전용
MANIFEST = RAW / "manifest.json"

REPORT_MD = ANALYSIS / "actions_absence_verification.md"
REPORT_JSON = EXTRACTED / "actions_absence_verification.json"

# 실행 전후로 해시를 재서 "쓰지 않았다"를 실측으로 증명하는 대상 (D99 DoD).
IMMUTABLE_INPUTS: Final[tuple[Path, ...]] = (ERROR_CODES, CANDIDATE)


# ──────────────────────────────────────────────── 판독 계획 · 판정 어휘
@dataclass(frozen=True)
class ReadTarget:
    """판독 대상 = (문서 슬러그, 물리 페이지 구간, 근거). 슬러그는 manifest `id` 다."""

    doc_slug: str
    pages: range
    note: str

    @property
    def page_numbers(self) -> tuple[int, ...]:
        return tuple(self.pages)


READ_PLAN: Final[tuple[ReadTarget, ...]] = (
    ReadTarget("s100-manual", range(412, 426), "§9.1+§9.2+여유 (결측 25건)"),
    ReadTarget("ig5a-troubleshooting", range(20, 32), "트러블슈팅 조치 구간+여유 (결측 9건)"),
    ReadTarget("ig5a-manual", range(200, 208), "보호기능표+여유 (p.202 ANCHOR_CONFLICT)"),
)  # 14+12+8 = 34p

VERDICTS: Final[tuple[str, ...]] = (
    "CONFIRMED_ABSENT",
    "RECOVERABLE",
    "STILL_AMBIGUOUS",
    "DISAGREE",
    "INCONCLUSIVE",
)
PARSER_CLAIMS: Final[tuple[str, ...]] = (
    "ABSENT_IN_MANUAL",
    "AMBIGUOUS",
    "NOT_FOUND_ON_PAGE",
    "UNCLASSIFIED",
    "NO_CLAIM",
)
# `ROW_TEXT_ONLY` = "앵커 행에 긴 이웃 셀이 있을 뿐, 그게 조치문이라는 근거는 없다".
# 판독 범위의 1차 표는 조치표가 아니라 트립/보호기능표이고 그 행에는 **항상** 긴 설명 셀이
# 있다(S100 `NMT` p.416 설명 53자 · `ALOR` p.418 설명 92자 — 둘 다 `actions` 는 0건). 이걸
# `ACTION_FOUND` 로 세면 ① 대조군이 자명 충족돼 `READER_BLIND` 가 원리적으로 발화하지 못하고
# ② 결측 코드가 자기 설명 셀로 전건 `DISAGREE` 가 된다. 판정상으로는 `ANCHOR_ONLY` 와 같게
# 다루고(아래 `_MATRIX`), 축으로만 분리해 리포트에서 구분해 보이게 한다.
ELICE_AXES: Final[tuple[str, ...]] = (
    "ACTION_FOUND",
    "ROW_TEXT_ONLY",
    "ANCHOR_ONLY",
    "NO_ANCHOR",
    "UNREAD",
)

# `_pending_review` 문자열 중 **이미 회수된 해소분**. 판정 매트릭스에 들어가지 않는다 —
# 그래서 `PARSER_CLAIMS` 의 원소가 아니다 (35 vs 34 의 정체가 이것이다, 급소 ④).
RESOLVED_CLAIM: Final[str] = "RESOLVED"

# ── 재량 문턱 (임의값이다. 정본에 닿지 않아 느슨해도 안전하지만 **실측과 함께 인쇄**한다).
ACTION_MIN_CHARS: Final[int] = 12  # 조치문으로 인정하는 최소 길이
MIN_ANCHOR_TOKEN_LEN: Final[int] = 2  # 이보다 짧은 앵커 토큰은 쓰지 않는다
# 앵커 토큰이 이보다 짧으면 약한 앵커로 표시한다. **출처와 무관하게** 적용한다 —
# 예전에는 `source != "error_name"` 조건이 붙어 있어서 S100 `BX`(`error_name` 자체가 2자)가
# 약한 앵커로 표시되지 않았다. 짧은 토큰의 오탐 위험은 출처가 아니라 길이에서 온다.
WEAK_ANCHOR_LEN: Final[int] = 4
TEXT_WINDOW_CHARS: Final[int] = 240  # 표 밖 폴백에서 앵커 뒤로 보는 문자 수
# "조치문처럼 보인다"를 판단하는 표지. **표 경로와 텍스트 폴백에 똑같이 적용한다** —
# 예전에는 폴백(느슨하다고 스스로 표시한 경로)에만 게이트가 있고 1차(표) 경로에는 없어서
# 엄격도가 역전돼 있었다(리뷰 C1). 표지가 판정을 *만들지는* 않는다 — 근거 종류를
# `evidence_kind` 로 인쇄하고 `rowspan` 귀속은 표 구조가 있을 때만 주장한다.
ACTION_MARKERS: Final[tuple[str, ...]] = (
    "조치",
    "점검",
    "교체",
    "제거",
    "확인하십시오",
    "확인하여",
    "Check",
    "Replace",
    "Inspect",
)
# 표의 **머리행**에 이 말이 있으면 그 열은 조치 열로 본다(ⓐ). 정규화(공백 제거·소문자) 후 비교.
ACTION_HEADER_MARKERS: Final[tuple[str, ...]] = (
    "조치",
    "대책",
    "처치",
    "action",
    "remedy",
    "correctiveaction",
)
# 대조군 생존 축 — 정본 `actions` 문장이 판독 근거 안에 나오는지 볼 때 쓰는 최소 대조 길이.
# 이보다 짧은 정본 문장은 우연 일치 위험이 커서 대조에 쓰지 않는다.
ACTION_MATCH_MIN_CHARS: Final[int] = 12

# ── `_pending_review` 문자열 분류 정규식 4종 (실측 분포: ABSENT 28 · AMBIGUOUS 5 ·
#    NOT_FOUND 1 = 34 · RESOLVED 1 = 합계 35). 순서가 계약이다 — RESOLVED 를 먼저 본다.
_CLAIM_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (RESOLVED_CLAIM, re.compile(r"공유\s*회수|명시\s*병기")),
    ("AMBIGUOUS", re.compile(r"자동\s*매칭\s*보류|ambiguous", re.IGNORECASE)),
    ("NOT_FOUND_ON_PAGE", re.compile(r"찾지\s*못")),
    (
        "ABSENT_IN_MANUAL",
        re.compile(r"해당\s*항목이\s*없음|실제\s*조치\s*내용이\s*없다|대응\s*페이지가\s*없음"),
    ),
)
_PENDING_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?P<model>iG5A|S100)\s+(?P<code>[A-Za-z0-9_]+)\s*:\s*(?P<reason>.+)$", re.DOTALL
)

# ── 판정 매트릭스 (이 표가 계약이다). `× ACTION_FOUND` 네 칸(`AMBIGUOUS`·`NOT_FOUND_ON_PAGE`·
# `UNCLASSIFIED`·`NO_CLAIM`) 은 전부 rowspan 귀속을 본다 — `decide()` 가 값을 채운다.
# 급소(MQ-1310, NTC 사례): `NOT_FOUND_ON_PAGE`/`UNCLASSIFIED`/`NO_CLAIM` 도 예전엔 이 축에서
# 무조건 `RECOVERABLE` 이었다. iG5A `NTC` 는 근거가 `text_window`(표 밖 폴백)라 귀속행이 0인데도
# `NOT_FOUND_ON_PAGE` 로 분류됐다는 이유만으로 회수됐다 — 같은 공유 조치문을 두고 `HWT`·`EEP`·
# `ERR`·`COM` 은 `AMBIGUOUS` 라서 `STILL_AMBIGUOUS` 로 남았는데 `NTC` 만 다른 결론이 났다.
# 파서의 내부 분류(왜 멈췄는가)가 아니라 **데이터 상황**(귀속이 풀렸는가)이 판정을 갈라야 한다.
_MATRIX: Final[dict[tuple[str, str], str]] = {
    ("ABSENT_IN_MANUAL", "ACTION_FOUND"): "DISAGREE",
    ("ABSENT_IN_MANUAL", "ROW_TEXT_ONLY"): "CONFIRMED_ABSENT",
    ("ABSENT_IN_MANUAL", "ANCHOR_ONLY"): "CONFIRMED_ABSENT",
    ("ABSENT_IN_MANUAL", "NO_ANCHOR"): "INCONCLUSIVE",
    ("ABSENT_IN_MANUAL", "UNREAD"): "INCONCLUSIVE",
    ("AMBIGUOUS", "ACTION_FOUND"): "",  # rowspan 귀속이 가른다 (decide 참조)
    ("AMBIGUOUS", "ROW_TEXT_ONLY"): "DISAGREE",
    ("AMBIGUOUS", "ANCHOR_ONLY"): "DISAGREE",
    ("AMBIGUOUS", "NO_ANCHOR"): "INCONCLUSIVE",
    ("AMBIGUOUS", "UNREAD"): "INCONCLUSIVE",
    ("NOT_FOUND_ON_PAGE", "ACTION_FOUND"): "",  # rowspan 귀속이 가른다 (decide 참조)
    ("NOT_FOUND_ON_PAGE", "ROW_TEXT_ONLY"): "DISAGREE",
    ("NOT_FOUND_ON_PAGE", "ANCHOR_ONLY"): "DISAGREE",
    ("NOT_FOUND_ON_PAGE", "NO_ANCHOR"): "INCONCLUSIVE",
    ("NOT_FOUND_ON_PAGE", "UNREAD"): "INCONCLUSIVE",
    ("UNCLASSIFIED", "ACTION_FOUND"): "",  # rowspan 귀속이 가른다 (decide 참조)
    ("UNCLASSIFIED", "ROW_TEXT_ONLY"): "INCONCLUSIVE",
    ("UNCLASSIFIED", "ANCHOR_ONLY"): "INCONCLUSIVE",
    ("UNCLASSIFIED", "NO_ANCHOR"): "INCONCLUSIVE",
    ("UNCLASSIFIED", "UNREAD"): "INCONCLUSIVE",
    ("NO_CLAIM", "ACTION_FOUND"): "",  # rowspan 귀속이 가른다 (decide 참조)
    ("NO_CLAIM", "ROW_TEXT_ONLY"): "INCONCLUSIVE",
    ("NO_CLAIM", "ANCHOR_ONLY"): "INCONCLUSIVE",
    ("NO_CLAIM", "NO_ANCHOR"): "INCONCLUSIVE",
    ("NO_CLAIM", "UNREAD"): "INCONCLUSIVE",
}

# `× ACTION_FOUND` 에서 귀속(`rowspan_resolved`) 조건을 거는 파서 주장 전체. `ABSENT_IN_MANUAL`
# 은 제외한다 — "부재"라는 주장 자체와 조치문 발견이 정면 충돌하므로 귀속 여부와 무관하게
# `DISAGREE`(사람이 볼 곳)가 맞다.
_ATTRIBUTION_GATED_CLAIMS: Final[frozenset[str]] = frozenset(
    {"AMBIGUOUS", "NOT_FOUND_ON_PAGE", "UNCLASSIFIED", "NO_CLAIM"}
)

# 축 우선순위 — 한 코드가 여러 대상(iG5A 는 표준본+트러블슈팅본)에 걸릴 때 결합 규칙.
_AXIS_RANK: Final[dict[str, int]] = {
    "ACTION_FOUND": 4,
    "ROW_TEXT_ONLY": 3,
    "ANCHOR_ONLY": 2,
    "NO_ANCHOR": 1,
    "UNREAD": 0,
}


def decide(
    claim: str,
    axis: str,
    *,
    rowspan_resolved: bool = False,
    reader_blind: bool = False,
    unread_in_scope: bool = False,
) -> str:
    """판정 매트릭스 오라클. **순수 함수** — 파일도 네트워크도 건드리지 않는다.

    - `{AMBIGUOUS, NOT_FOUND_ON_PAGE, UNCLASSIFIED, NO_CLAIM} × ACTION_FOUND` 는
      `rowspan_resolved=True`(귀속이 1:1 로 풀림)일 때만 `RECOVERABLE`, 아니면
      `STILL_AMBIGUOUS`. **파서가 왜 멈췄는지(내부 분류)가 아니라 귀속이 풀렸는지(데이터
      상황)가 판정을 가른다** — 네 칸 모두 같은 원칙이다. `NOT_FOUND_ON_PAGE`·`UNCLASSIFIED`
      가 예전엔 무조건 `RECOVERABLE` 이었는데, iG5A `NTC` 가 `text_window` 폴백(귀속행 0,
      `rowspan_resolved=False`)에서 `NOT_FOUND_ON_PAGE` 로 분류됐다는 이유만으로 회수됐다.
      같은 공유 조치문을 두고 `AMBIGUOUS` 로 분류된 `HWT`·`EEP`·`ERR`·`COM` 은 `STILL_AMBIGUOUS`
      로 남았으니 데이터가 같은데 결론만 갈린 것 — 지어내기 압력이라 통일했다.
      `ABSENT_IN_MANUAL` 은 여기 포함하지 않는다 — "부재" 주장과 조치문 발견이 정면 충돌하므로
      귀속 여부와 무관하게 `DISAGREE`(사람이 볼 곳)다.
    - `NO_ANCHOR` 는 **절대** `CONFIRMED_ABSENT` 가 되지 않는다 — 양성 축이 죽은 상태에서
      부재를 주장할 수 없다 (P30 · D65).
    - `ROW_TEXT_ONLY` 는 판정상 `ANCHOR_ONLY` 와 같다 — "긴 이웃 셀이 있다"는 조치문의
      근거가 아니다. 축으로만 분리해 리포트에서 구분한다.
    - `reader_blind=True` **또는** `unread_in_scope=True` 면 `CONFIRMED_ABSENT` 를
      `INCONCLUSIVE` 로 강등한다. 후자는 *"이 코드의 판독 대상 중 하나를 아직 못 읽었다"* —
      **"못 봤다"를 "없다"로 바꾸지 않는다** (D62).
    """
    if claim not in PARSER_CLAIMS:
        raise ValueError(f"모르는 파서 주장: {claim!r} (허용 {PARSER_CLAIMS})")
    if axis not in ELICE_AXES:
        raise ValueError(f"모르는 Elice 축: {axis!r} (허용 {ELICE_AXES})")
    if claim in _ATTRIBUTION_GATED_CLAIMS and axis == "ACTION_FOUND":
        verdict = "RECOVERABLE" if rowspan_resolved else "STILL_AMBIGUOUS"
    else:
        verdict = _MATRIX[(claim, axis)]
    if (reader_blind or unread_in_scope) and verdict == "CONFIRMED_ABSENT":
        return "INCONCLUSIVE"
    return verdict


# ──────────────────────────────────────────────── 입력 (읽기 전용)
def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_manuals() -> dict[str, dict]:
    """manifest `id` → 매뉴얼 항목. PDF 경로는 `RAW / entry["file"]`."""
    return {m["id"]: m for m in _read_json(MANIFEST).get("manuals", [])}


def _pdf_path(doc_slug: str) -> Path | None:
    entry = _manifest_manuals().get(doc_slug)
    if entry is None:
        return None
    path = RAW / entry["file"]
    return path if path.exists() else None


def _model_of(doc_slug: str) -> str:
    entry = _manifest_manuals().get(doc_slug) or {}
    return str(entry.get("model") or "")


def canonical_entries() -> list[dict]:
    """정본 65건. **읽기 전용** (D99)."""
    return list(_read_json(ERROR_CODES).get("entries") or [])


def missing_entries() -> list[dict]:
    """`actions` 결측 34건 (S100 25 / iG5A 9). 실측이며 상수로 박지 않는다."""
    return [e for e in canonical_entries() if not (e.get("actions") or [])]


def candidate_entries() -> list[dict]:
    """후보 파일의 회수 성공분(`entries`) 3건. **읽기 전용** (D99)."""
    return list(_read_json(CANDIDATE).get("entries") or [])


def pending_lines() -> list[str]:
    """`_pending_review` — **dict 가 아니라 문자열 35개**다 (급소 ④)."""
    return [str(s) for s in (_read_json(CANDIDATE).get("_pending_review") or [])]


def triage_labels() -> dict[tuple[str, int], dict]:
    """(manual_id, 물리 페이지) → triage 판정 1행.

    ⚠ 이 라벨은 **표시용**이다. `ANCHOR_CONFLICT` 가 붙은 행의 라벨은 triage 스스로 근거가
    없다고 표시한 것이라 판정의 입력으로 쓰지 않는다 (설계 스펙 §8).
    """
    if not TRIAGE.exists():
        return {}
    out: dict[tuple[str, int], dict] = {}
    for row in _read_json(TRIAGE).get("verdicts") or []:
        out[(str(row.get("manual_id")), int(row.get("page") or 0))] = row
    return out


# ──────────────────────────────────────────────── 파서 주장 분류 · 조인
def classify_pending(reason: str) -> str:
    """`_pending_review` 사유 문자열 1건 → 파서 주장 라벨.

    반환값은 `PARSER_CLAIMS` 중 하나이거나 `RESOLVED_CLAIM`(이미 회수된 해소분)이다.
    어느 정규식에도 안 걸리면 `"UNCLASSIFIED"` — **조용히 버리지 않는다.**
    """
    text = str(reason or "")
    for label, pattern in _CLAIM_PATTERNS:
        if pattern.search(text):
            return label
    return "UNCLASSIFIED"


def parse_pending() -> list[dict]:
    """`_pending_review` 35건을 (model, code, reason, claim) 으로 푼다. 파싱 실패도 남긴다."""
    out: list[dict] = []
    for index, line in enumerate(pending_lines(), start=1):
        match = _PENDING_LINE_RE.match(line)
        if match is None:
            out.append(
                {
                    "index": index,
                    "model": None,
                    "code": None,
                    "reason": line,
                    "claim": "UNCLASSIFIED",
                    "parse_ok": False,
                }
            )
            continue
        reason = match.group("reason").strip()
        out.append(
            {
                "index": index,
                "model": match.group("model"),
                "code": match.group("code"),
                "reason": reason,
                "claim": classify_pending(reason),
                "parse_ok": True,
            }
        )
    return out


def join_pending() -> dict:
    """결측 34건 ↔ `_pending_review` 35건 조인 무결성.

    - 제외 대상은 **정본에 `actions` 가 이미 있는** 코드다(= 결측 집합 밖). 정규식
      `RESOLVED` 판정은 그 사실의 **교차 확인**으로만 쓰고, 둘이 어긋나면 경고를 낸다.
    - 조인 실패분은 `NO_CLAIM` 으로 표에 **그대로 싣는다**(조용히 버리지 않는다).
    """
    parsed = parse_pending()
    missing = missing_entries()
    missing_keys = {(str(e["model"]), str(e["code"])) for e in missing}

    by_key: dict[tuple[str, str], dict] = {}
    excluded: list[dict] = []
    unjoined_pending: list[dict] = []
    for row in parsed:
        key = (str(row["model"]), str(row["code"]))
        if key in missing_keys:
            by_key[key] = row
        elif row["parse_ok"]:
            excluded.append(row)  # 결측이 아닌 코드 = 해소분
        else:
            unjoined_pending.append(row)

    joined = sorted(key for key in missing_keys if key in by_key)
    unjoined_missing = sorted(key for key in missing_keys if key not in by_key)

    mismatched = [
        {"model": row["model"], "code": row["code"], "claim": row["claim"]}
        for row in excluded
        if row["claim"] != RESOLVED_CLAIM
    ]
    by_claim: dict[str, int] = {}
    for key in joined:
        by_claim[by_key[key]["claim"]] = by_claim.get(by_key[key]["claim"], 0) + 1

    return {
        "pending_total": len(parsed),
        "pending_parse_failed": sum(1 for row in parsed if not row["parse_ok"]),
        "missing_total": len(missing),
        "joined": len(joined),
        "join_ratio": f"{len(joined)}/{len(missing)}",
        "unjoined_missing": [f"{m} {c}" for m, c in unjoined_missing],
        "unjoined_pending": [row["reason"][:60] for row in unjoined_pending],
        "excluded_resolved": [
            {"model": row["model"], "code": row["code"], "claim": row["claim"]}
            for row in excluded
        ],
        "excluded_claim_mismatch": mismatched,
        "by_claim": by_claim,
        "claims_by_key": {f"{m} {c}": by_key[(m, c)] for (m, c) in joined},
    }


# ──────────────────────────────────────────────── 앵커 (급소 ①)
def normalize_anchor(value: Any) -> str:
    """대소문자·공백 무시 정규화. **부분일치**를 쓰기 때문에 그 밖의 문자는 지우지 않는다.

    `FANW` 의 실제 셀은 `FAN Trip / FAN Warning` 병합이라 `Fan Warning` 이 부분문자열로
    걸려야 한다.
    """
    return re.sub(r"[\s ​]+", "", str(value or "")).lower()


def anchor_tokens(entry: dict) -> list[tuple[str, str]]:
    """(축 이름, 정규화 토큰) 목록. **`error_name` 이 1차 축**이고 코드 토큰은 보조다.

    S100 9.2 조치표 항목 열에는 코드 토큰이 **한 개도 없다** — 코드로 앵커를 잡으면 대조군이
    전멸하고 `READER_BLIND` 가 상시 발화해 판독 전액이 무효가 된다(급소 ①).
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for source in ("error_name", "display_code", "code"):
        token = normalize_anchor(entry.get(source))
        if len(token) < MIN_ANCHOR_TOKEN_LEN or token in seen:
            continue
        seen.add(token)
        out.append((source, token))
    return out


# ──────────────────────────────────────────────── 표 HTML 파싱 (급소 ③ rowspan)
class _TableCollector(HTMLParser):
    """`<table>` 을 (행 × 셀) 로 푼다. `rowspan`·`colspan` 을 보존한다 — 급소 ③ 의 입력이다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[dict]]] = []
        self._rows: list[list[dict]] | None = None
        self._row: list[dict] | None = None
        self._cell: dict | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._rows = []
        elif tag == "tr" and self._rows is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            values = dict(attrs)
            self._cell = {
                "text": "",
                "rowspan": _positive_int(values.get("rowspan"), 1),
                "colspan": _positive_int(values.get("colspan"), 1),
            }

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._cell["text"] = re.sub(r"\s+", " ", self._cell["text"]).strip()
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._rows is not None and self._row is not None:
            self._rows.append(self._row)
            self._row = None
        elif tag == "table" and self._rows is not None:
            self.tables.append(self._rows)
            self._rows = None


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 1 else default


def parse_tables(html_fragments: list[str]) -> list[list[list[dict | None]]]:
    """표 HTML 조각들 → `rowspan/colspan` 을 펼친 격자 목록.

    격자의 각 칸은 **원본 셀 dict 를 그대로 가리킨다**(동일 객체). 그래서 "이 조치 셀이 몇 개
    항목 행에 걸쳐 있는가"를 셀 정체성으로 셀 수 있다.
    """
    grids: list[list[list[dict | None]]] = []
    for fragment in html_fragments:
        collector = _TableCollector()
        try:
            collector.feed(str(fragment or ""))
            collector.close()
        except Exception:  # 판독기 응답의 표가 깨져도 엔진은 멈추지 않는다
            continue
        for rows in collector.tables:
            grid = _expand_grid(rows)
            if grid:
                grids.append(grid)
    return grids


def _expand_grid(rows: list[list[dict]]) -> list[list[dict | None]]:
    occupied: dict[tuple[int, int], dict] = {}
    for row_index, row in enumerate(rows):
        column = 0
        for cell in row:
            while (row_index, column) in occupied:
                column += 1
            for d_row in range(cell["rowspan"]):
                for d_col in range(cell["colspan"]):
                    occupied[(row_index + d_row, column + d_col)] = cell
            column += cell["colspan"]
    if not occupied:
        return []
    max_row = max(r for r, _ in occupied)
    max_col = max(c for _, c in occupied)
    return [[occupied.get((r, c)) for c in range(max_col + 1)] for r in range(max_row + 1)]


# ──────────────────────────────────────────────── 판독 결과에서 축 계산 (급소 ②)
@dataclass(frozen=True)
class AxisResult:
    """한 코드 × 한 판독 대상(=읽은 페이지 union)의 축 계산 결과."""

    axis: str
    doc_slug: str
    page: int | None  # 근거가 나온 물리 페이지 (D26). 없으면 None
    anchor_source: str  # "error_name" | "display_code" | "code" | ""
    matched_token: str
    evidence_kind: str  # "table_row" | "text_window" | ""
    evidence: str
    rowspan: int
    covers_item_rows: int
    rowspan_resolved: bool
    weak_anchor: bool


_EMPTY_AXIS = AxisResult("UNREAD", "", None, "", "", "", "", 0, 0, False, False)


def _flex_pattern(token_source: str) -> re.Pattern[str]:
    """공백을 무시하는 부분일치 정규식. 원문 위치를 알아야 하는 텍스트 폴백에서 쓴다."""
    chars = [ch for ch in str(token_source) if not ch.isspace()]
    return re.compile(r"\s*".join(re.escape(ch) for ch in chars), re.IGNORECASE)


def _page_text_blob(extraction: PageExtraction, grids: list[list[list[dict | None]]]) -> str:
    parts = [extraction.text]
    for grid in grids:
        seen: set[int] = set()
        for row in grid:
            for cell in row:
                if cell is None or id(cell) in seen:
                    continue
                seen.add(id(cell))
                parts.append(cell["text"])
    return "\n".join(p for p in parts if p)


def is_action_text(text: str) -> bool:
    """이 문자열이 **조치문처럼** 보이는가 — `ACTION_MARKERS` 표지 1개 이상.

    표 경로와 텍스트 폴백이 **같은 이 함수**를 쓴다. 두 벌로 나뉘면 한쪽만 느슨해져
    "가장 느슨한 경로"가 경고에도 안 잡힌다(리뷰 C1 이 지적한 엄격도 역전).
    """
    body = str(text or "")
    return any(marker in body for marker in ACTION_MARKERS)


def action_columns(grid: list[list[dict | None]]) -> set[int]:
    """머리행(격자 0행)에 `ACTION_HEADER_MARKERS` 가 있는 열 번호 집합.

    S100 9.2 조치사항표·iG5A 12.2 고장 대책표는 머리행에 `조치`/`대책` 이 있다. 반대로
    9.1 트립표(p.416~419)·iG5A 보호기능표(p.202)는 `기능`/`설명` 이라 여기 걸리지 않는다 —
    그 차이가 `ACTION_FOUND` 와 `ROW_TEXT_ONLY` 를 가른다.
    """
    if not grid:
        return set()
    out: set[int] = set()
    for column, cell in enumerate(grid[0]):
        if cell is None:
            continue
        header = normalize_anchor(cell["text"])
        if any(marker in header for marker in ACTION_HEADER_MARKERS):
            out.add(column)
    return out


def _covered_anchor_rows(
    grid: list[list[dict | None]], cell: dict, row_has_anchor: list[bool]
) -> int:
    """`cell` 이 실제로 놓인 격자 행들 중 앵커를 가진 행의 수. **셀 정체성으로 센다.**

    ⛔ `앵커 행 + range(rowspan)` 오프셋으로 세면 안 된다 — `_expand_grid` 가 span 된 칸에
    **같은 셀 객체**를 채우므로, rowspan=3 셀이 0행에서 시작하고 앵커가 2행에서 걸리면
    오프셋 방식은 2·3·4행(격자 밖)을 세어 표 끝에서 0 → `or 1` 폴백으로 **가짜 1:1 귀속**이
    만들어진다(리뷰 C2). 0 이면 "귀속 미확인"으로 그대로 둔다 — 폴백하지 않는다.
    """
    rows = [
        index
        for index, grid_row in enumerate(grid)
        if any(other is cell for other in grid_row)
    ]
    return sum(1 for index in rows if index < len(row_has_anchor) and row_has_anchor[index])


def _find_in_tables(
    grids: list[list[list[dict | None]]],
    tokens: list[tuple[str, str]],
    all_anchor_tokens: list[str],
) -> tuple[str, str, str, dict, int] | None:
    """표에서 (축, 앵커 축, 앵커 토큰, 근거 셀, 그 셀이 걸친 항목 행 수) 를 찾는다.

    축은 둘 중 하나다:
      - `ACTION_FOUND` — 근거 셀이 **조치성**을 통과했다. 조치 열(머리행 `조치`/`대책`/`Action`)
        이거나 `ACTION_MARKERS` 표지를 가진 셀이다.
      - `ROW_TEXT_ONLY` — 같은 행에 `ACTION_MIN_CHARS` 이상의 이웃 셀이 있을 뿐이다.
        판독 범위의 1차 표는 조치표가 아니라 트립/보호기능표라 **항상** 긴 설명 셀이 있다 —
        이걸 조치문으로 세면 대조군이 자명 충족돼 `READER_BLIND` 가 죽는다(리뷰 C1).

    `ACTION_FOUND` 를 찾으면 즉시 반환하고, 없으면 첫 `ROW_TEXT_ONLY` 를 돌려준다.
    `covers_item_rows` = 그 셀이 걸친 행들 중 *어떤 코드의 앵커라도* 들어 있는 행의 수 —
    2 이상이면 조치문이 여러 항목과 공유된 것이라 **귀속이 1:1 로 풀리지 않았다**(급소 ③).
    """
    fallback: tuple[str, str, str, dict, int] | None = None
    for grid in grids:
        row_has_anchor = [
            any(
                cell is not None
                and any(t in normalize_anchor(cell["text"]) for t in all_anchor_tokens)
                for cell in row
            )
            for row in grid
        ]
        action_cols = action_columns(grid)
        for row in grid:
            hit = None
            for cell in row:
                if cell is None:
                    continue
                normalized = normalize_anchor(cell["text"])
                for source, token in tokens:
                    if token and token in normalized:
                        hit = (source, token, cell)
                        break
                if hit:
                    break
            if hit is None:
                continue
            anchor_cell = hit[2]
            others: list[tuple[dict, bool]] = []
            seen_ids: set[int] = set()
            for column, cell in enumerate(row):
                if cell is None or cell is anchor_cell or id(cell) in seen_ids:
                    continue
                if len(cell["text"]) < ACTION_MIN_CHARS:
                    continue
                seen_ids.add(id(cell))
                others.append((cell, column in action_cols or is_action_text(cell["text"])))
            if not others:
                continue
            actionable = [cell for cell, is_action in others if is_action]
            if actionable:
                action_cell = max(actionable, key=lambda c: len(c["text"]))
                covers = _covered_anchor_rows(grid, action_cell, row_has_anchor)
                return "ACTION_FOUND", hit[0], hit[1], action_cell, covers
            if fallback is None:
                text_cell = max((cell for cell, _ in others), key=lambda c: len(c["text"]))
                covers = _covered_anchor_rows(grid, text_cell, row_has_anchor)
                fallback = ("ROW_TEXT_ONLY", hit[0], hit[1], text_cell, covers)
    return fallback


def _find_in_text(
    text: str, entry: dict, tokens: list[tuple[str, str]]
) -> tuple[str, str, str] | None:
    """표 밖 폴백 — 앵커 뒤 창에서 조치문 표지를 찾는다.

    ⚠ 느슨하다. 그래서 결과를 `evidence_kind="text_window"` 로 **표시**하고 `rowspan` 귀속은
    항상 미해소로 둔다(→ `AMBIGUOUS` 는 `STILL_AMBIGUOUS`, `ABSENT_IN_MANUAL` 은 `DISAGREE`
    = 사람이 볼 곳). 리더 생존 검사에서 이 축이 몇 건을 만들었는지도 따로 인쇄한다.
    """
    for source in ("error_name", "display_code", "code"):
        raw = str(entry.get(source) or "")
        if len(normalize_anchor(raw)) < MIN_ANCHOR_TOKEN_LEN:
            continue
        match = _flex_pattern(raw).search(text)
        if match is None:
            continue
        window = text[match.end() : match.end() + TEXT_WINDOW_CHARS].strip()
        if len(window) >= ACTION_MIN_CHARS and is_action_text(window):
            token = next((t for s, t in tokens if s == source), normalize_anchor(raw))
            return source, token, window
    return None


def axis_for(
    entry: dict,
    doc_slug: str,
    pages: dict[int, PageExtraction],
    all_anchor_tokens: list[str],
) -> AxisResult:
    """한 코드의 축을 **읽은 페이지 union(대상 문서 범위) 단위**로 계산한다 (급소 ②).

    앵커는 9.1 에, 조치문은 9.2 에 있다 — 페이지 단위로 재면 전부 `ANCHOR_ONLY` 가 되고
    대조군도 `ACTION_FOUND=0` 이 되어 `READER_BLIND` 가 상시 발화한다.
    """
    if not pages:
        return _EMPTY_AXIS
    tokens = anchor_tokens(entry)
    if not tokens:
        return AxisResult("NO_ANCHOR", doc_slug, None, "", "", "", "", 0, 0, False, False)

    anchor_hit: tuple[int, str, str] | None = None
    row_text_hit: AxisResult | None = None
    for page_no in sorted(pages):
        extraction = pages[page_no]
        grids = parse_tables(extraction.tables_html)
        blob = normalize_anchor(_page_text_blob(extraction, grids))
        found = _find_in_tables(grids, tokens, all_anchor_tokens)
        if found is not None:
            kind, source, token, cell, covers = found
            result = AxisResult(
                axis=kind,
                doc_slug=doc_slug,
                page=page_no,
                anchor_source=source,
                matched_token=token,
                evidence_kind="table_row" if kind == "ACTION_FOUND" else "row_text_only",
                evidence=cell["text"][:400],
                rowspan=int(cell["rowspan"]),
                covers_item_rows=covers,
                # 귀속은 조치문으로 인정된 셀에 대해서만 주장한다. covers==0 은 "귀속 미확인".
                rowspan_resolved=kind == "ACTION_FOUND" and covers == 1,
                weak_anchor=len(token) < WEAK_ANCHOR_LEN,
            )
            if kind == "ACTION_FOUND":
                return result
            if row_text_hit is None:
                row_text_hit = result
        if anchor_hit is None:
            for source, token in tokens:
                if token and token in blob:
                    anchor_hit = (page_no, source, token)
                    break

    for page_no in sorted(pages):
        extraction = pages[page_no]
        window = _find_in_text(_page_text_blob(extraction, parse_tables(extraction.tables_html)),
                               entry, tokens)
        if window is not None:
            source, token, evidence = window
            return AxisResult(
                axis="ACTION_FOUND",
                doc_slug=doc_slug,
                page=page_no,
                anchor_source=source,
                matched_token=token,
                evidence_kind="text_window",
                evidence=evidence[:400],
                rowspan=0,
                covers_item_rows=0,
                rowspan_resolved=False,  # 표 구조가 없으면 귀속을 주장할 수 없다
                weak_anchor=len(token) < WEAK_ANCHOR_LEN,
            )

    if row_text_hit is not None:
        return row_text_hit
    if anchor_hit is not None:
        page_no, source, token = anchor_hit
        return AxisResult(
            axis="ANCHOR_ONLY",
            doc_slug=doc_slug,
            page=page_no,
            anchor_source=source,
            matched_token=token,
            evidence_kind="",
            evidence="",
            rowspan=0,
            covers_item_rows=0,
            rowspan_resolved=False,
            weak_anchor=len(token) < WEAK_ANCHOR_LEN,
        )
    return AxisResult("NO_ANCHOR", doc_slug, None, "", "", "", "", 0, 0, False, False)


# ──────────────────────────────────────────────── 대조군 (리더 생존 검사)
def action_text_match(evidence: str, actions: list[str]) -> tuple[bool, str, str]:
    """판독 근거 안에 **정본 `actions` 문장**이 나오는가 → (일치, 일치 방식, 일치한 정본 문장).

    🔴 이게 대조군 생존 축의 급소다. 예전 생존 축은 *"대조군에서 `ACTION_FOUND` 가 1건이라도
    나왔는가"* 였는데, 조치성 판정이 없던 시절에는 **앵커 행에 긴 이웃 셀이 있기만 하면**
    참이 되어 `READER_BLIND` 가 원리적으로 발화하지 못했다(리뷰 C1). 대조군은 조치문 원문을
    **이미 갖고 있으므로**, "판독 결과에 그 문장이 나오는가"로 재면 자명 충족이 사라진다.

    비교는 `normalize_anchor`(공백 제거·소문자) 후 부분일치다. 판독기가 문장을 자르거나
    앞뒤를 붙여 오는 경우를 받아들이려고 세 방향을 본다 — 완전 포함 / 앞부분 포함 /
    근거가 정본 문장 안에 포함. `ACTION_MATCH_MIN_CHARS` 미만의 정본 문장은 쓰지 않는다.
    """
    haystack = normalize_anchor(evidence)
    if not haystack:
        return False, "", ""
    for action in actions or []:
        needle = normalize_anchor(action)
        if len(needle) < ACTION_MATCH_MIN_CHARS:
            continue
        if needle in haystack:
            return True, "full", str(action)
        if needle[:ACTION_MATCH_MIN_CHARS] in haystack:
            return True, "prefix", str(action)
        if len(haystack) >= ACTION_MATCH_MIN_CHARS and haystack in needle:
            return True, "contained", str(action)
    return False, "", ""


def control_codes() -> dict[str, list[dict]]:
    """판독 범위 안에 있으면서 **`actions` 가 이미 있는** 코드 = 대조군.

    선정 규칙 두 갈래(`actions_page` 는 31건 중 3건만 채워져 있다 — D100: null = "출처 미기록"):
      ⓐ 정본에 `actions` 가 있고 `manual_page` 가 그 모델 primary 본의 판독 범위 안
      ⓑ 후보 파일 `entries` 의 `actions_manual_id`/`actions_page` 가 판독 범위 안
        (`ig5a-troubleshooting` 은 ⓑ 로만 잡힌다 — 그래서 대조군이 **2건뿐**이다)

    ⚠ 실제 발견 페이지는 판독 후에 리포트가 따로 인쇄한다. 여기서는 **앵커 페이지**만 안다.
    """
    by_slug: dict[str, list[dict]] = {t.doc_slug: [] for t in READ_PLAN}
    primary_of_model = {
        _model_of(t.doc_slug): t.doc_slug
        for t in READ_PLAN
        if (_manifest_manuals().get(t.doc_slug) or {}).get("role") == "primary"
    }
    ranges = {t.doc_slug: set(t.page_numbers) for t in READ_PLAN}
    seen: set[tuple[str, str, str]] = set()

    for entry in canonical_entries():
        if not (entry.get("actions") or []):
            continue
        slug = primary_of_model.get(str(entry.get("model")))
        page = entry.get("manual_page")
        if slug is None or not isinstance(page, int) or page not in ranges.get(slug, set()):
            continue
        key = (slug, str(entry.get("model")), str(entry.get("code")))
        if key in seen:
            continue
        seen.add(key)
        by_slug[slug].append(
            {
                "model": entry.get("model"),
                "code": entry.get("code"),
                "error_name": entry.get("error_name"),
                "anchor_page": page,
                "selected_by": "canonical.manual_page",
                # 생존 축의 대조 기준 — 이 문장이 판독 결과에 나와야 "판독기가 살아 있다".
                "expected_actions": list(entry.get("actions") or []),
            }
        )

    canonical_by_key = {
        (str(e.get("model")), str(e.get("code"))): e for e in canonical_entries()
    }
    for candidate in candidate_entries():
        slug = str(candidate.get("actions_manual_id") or "")
        page = candidate.get("actions_page")
        if slug not in ranges or not isinstance(page, int) or page not in ranges[slug]:
            continue
        key = (slug, str(candidate.get("model")), str(candidate.get("code")))
        if key in seen:
            continue
        seen.add(key)
        source_entry = canonical_by_key.get(
            (str(candidate.get("model")), str(candidate.get("code")))
        )
        by_slug[slug].append(
            {
                "model": candidate.get("model"),
                "code": candidate.get("code"),
                "error_name": (source_entry or {}).get("error_name"),
                "anchor_page": page,
                "selected_by": "candidate.actions_page",
                "expected_actions": list(
                    (source_entry or {}).get("actions") or candidate.get("actions") or []
                ),
            }
        )
    return by_slug


# ──────────────────────────────────────────────── 판독 (기본은 캐시만 — 네트워크 0)
def read_target(
    target: ReadTarget, *, allow_purchase: bool = False
) -> tuple[dict[int, PageExtraction], list[dict]]:
    """대상 1개의 페이지들을 읽는다. **캐시 우선** — 미스면 `EliceError` 를 받아 `UNREAD` 로 남긴다.

    `allow_purchase=False`(기본)면 `extract_page` 가 네트워크를 타기 전에 예외를 던진다.

    ⚠ `EliceError` 만 잡으면 **구매 성공 직후** 보관 단계(`store_response`)가 던지는
    `ExternalStoreError` 에 verify 전체가 중단된다 — 이미 결제된 45원이 캐시에도 남지 않은 채
    증발하고 나머지 페이지도 못 읽는다. 그래서 넓게 잡아 `store_failed` 로 남기고 **계속 간다**.
    """
    pdf = _pdf_path(target.doc_slug)
    pages: dict[int, PageExtraction] = {}
    status: list[dict] = []
    for page_no in target.page_numbers:
        if pdf is None:
            status.append({"doc_slug": target.doc_slug, "page": page_no, "state": "pdf_missing"})
            continue
        try:
            extraction = extract_page(
                pdf, page_no, doc_slug=target.doc_slug, allow_purchase=allow_purchase
            )
        except EliceError as exc:
            status.append(
                {
                    "doc_slug": target.doc_slug,
                    "page": page_no,
                    "state": "unread",
                    "detail": str(exc)[:160],
                }
            )
            continue
        except Exception as exc:  # 구매 직후 보관 실패 등 — 여기서 멈추면 결제분이 증발한다
            status.append(
                {
                    "doc_slug": target.doc_slug,
                    "page": page_no,
                    "state": "store_failed",
                    "detail": f"{type(exc).__name__}: {str(exc)[:140]}",
                }
            )
            continue
        pages[page_no] = extraction
        status.append(
            {
                "doc_slug": target.doc_slug,
                "page": page_no,
                "state": "cache" if extraction.from_cache else "purchased",
                "elements": len(extraction.elements),
                "tables": len(extraction.tables_html),
                "chars": len(extraction.text),
            }
        )
    return pages, status


# ──────────────────────────────────────────────── 비용 (산술만 — 외부 호출 0)
def cost_estimate() -> dict:
    """판독 계획의 페이지 수 × 단가. `--confirm-won` 이 이 값과 정확히 일치해야 지출이 열린다."""
    by_target = [
        {
            "doc_slug": t.doc_slug,
            "first_page": t.page_numbers[0],
            "last_page": t.page_numbers[-1],
            "n_pages": len(t.page_numbers),
            "won": len(t.page_numbers) * PRICE_PER_PAGE_WON,
            "note": t.note,
        }
        for t in READ_PLAN
    ]
    n_pages = sum(row["n_pages"] for row in by_target)
    return {
        "won_per_page": PRICE_PER_PAGE_WON,
        "n_pages": n_pages,
        "won_total": n_pages * PRICE_PER_PAGE_WON,
        "by_target": by_target,
        "note": "산술 추정치다. 실제 집행은 사람 승인 사안이며 기본 실행은 네트워크를 타지 않는다.",
    }


# ──────────────────────────────────────────────── 페이지별 문자 수 실측 (판독 범위 재확정 근거)
def page_char_counts() -> list[dict]:
    """판독 계획 34페이지의 **pdfplumber 문자 수**를 실측한다 (계획서 §6-2).

    감축 후보(S100 p.412~414 · p.422~425 · iG5A-TS p.29~31)를 사람이 판단할 근거다.
    ⛔ 이 값으로 계획을 자동 축소하지 않는다 — 범위 확정은 사람 몫이다.
    """
    import pdfplumber  # noqa: PLC0415 — 계산 경로에서만 필요하다

    rows: list[dict] = []
    for target in READ_PLAN:
        pdf_path = _pdf_path(target.doc_slug)
        if pdf_path is None:
            for page_no in target.page_numbers:
                rows.append(
                    {"doc_slug": target.doc_slug, "page": page_no, "chars": None,
                     "tables": None, "state": "pdf_missing"}
                )
            continue
        with pdfplumber.open(pdf_path) as pdf:
            for page_no in target.page_numbers:
                if page_no < 1 or page_no > len(pdf.pages):
                    rows.append(
                        {"doc_slug": target.doc_slug, "page": page_no, "chars": None,
                         "tables": None, "state": "out_of_range"}
                    )
                    continue
                page = pdf.pages[page_no - 1]
                text = page.extract_text() or ""
                try:
                    tables = page.extract_tables()
                except Exception:  # 계측기는 멈추지 않는다
                    tables = []
                rows.append(
                    {
                        "doc_slug": target.doc_slug,
                        "page": page_no,
                        "chars": len(text),
                        "tables": len(tables),
                        "state": "ok",
                    }
                )
    return rows


# ──────────────────────────────────────────────── 3자 대조 본체
def verify(*, allow_purchase: bool = False, measure_page_chars: bool = True) -> dict:
    """3자 대조를 수행하고 검수 패키지용 결과 dict 를 돌려준다. **정본을 쓰지 않는다** (D99)."""
    before = {p.name: _sha256(p) for p in IMMUTABLE_INPUTS if p.exists()}
    cost = cost_estimate()
    join = join_pending()
    controls = control_codes()
    labels = triage_labels()
    missing = missing_entries()

    # 모델별 전체 앵커 토큰 — "이 조치 셀이 몇 개 항목 행에 걸쳐 있나"를 세는 데 쓴다(급소 ③).
    anchors_by_model: dict[str, list[str]] = {}
    for entry in canonical_entries():
        model = str(entry.get("model"))
        anchors_by_model.setdefault(model, []).extend(t for _, t in anchor_tokens(entry))

    read_pages: dict[str, dict[int, PageExtraction]] = {}
    read_status: list[dict] = []
    for target in READ_PLAN:
        pages, status = read_target(target, allow_purchase=allow_purchase)
        read_pages[target.doc_slug] = pages
        read_status.extend(status)

    # ── 리더 생존 검사 (대상별). 대조군에 같은 알고리즘을 그대로 적용한다.
    control_report: list[dict] = []
    blind_slugs: set[str] = set()
    canonical_by_key = {(str(e["model"]), str(e["code"])): e for e in canonical_entries()}
    for target in READ_PLAN:
        slug = target.doc_slug
        pages = read_pages.get(slug) or {}
        rows: list[dict] = []
        for item in controls.get(slug, []):
            entry = canonical_by_key.get((str(item["model"]), str(item["code"]))) or item
            result = axis_for(entry, slug, pages, anchors_by_model.get(str(item["model"]), []))
            expected = list(item.get("expected_actions") or entry.get("actions") or [])
            matched, match_kind, matched_action = action_text_match(result.evidence, expected)
            rows.append(
                {
                    **item,
                    "axis": result.axis,
                    "found_page": result.page,
                    "anchor_source": result.anchor_source,
                    "evidence_kind": result.evidence_kind,
                    "evidence": result.evidence,
                    # 🔴 진짜 양성 축 — 정본 조치문이 판독 근거 안에 나왔는가(리뷰 C1 ⓑ).
                    "action_text_matched": bool(matched and result.axis == "ACTION_FOUND"),
                    "action_match_kind": match_kind if matched else "",
                    "expected_action_sample": (expected[0] if expected else ""),
                    "matched_action": matched_action,
                }
            )
        n_action = sum(1 for r in rows if r["axis"] == "ACTION_FOUND")
        n_verified = sum(1 for r in rows if r["action_text_matched"])
        n_table = sum(
            1 for r in rows if r["axis"] == "ACTION_FOUND" and r["evidence_kind"] == "table_row"
        )
        n_row_text = sum(1 for r in rows if r["axis"] == "ROW_TEXT_ONLY")
        if not pages:
            state = "unread"
        elif not rows:
            state = "no_controls"
        elif n_verified == 0:
            # 생존 축은 `ACTION_FOUND` 건수가 아니라 **정본 조치문 대조 통과 건수**다.
            state = "blind"
        else:
            state = "ok"
        if state in ("blind", "no_controls"):
            blind_slugs.add(slug)
        control_report.append(
            {
                "doc_slug": slug,
                "state": state,
                "controls_total": len(rows),
                "action_found": n_action,
                "action_verified": n_verified,
                "action_found_table_row": n_table,
                "action_found_text_window": n_action - n_table,
                "row_text_only": n_row_text,
                "pages_read": len(pages),
                "rows": rows,
            }
        )

    # ── 코드별 3자 대조. iG5A 는 표준본·트러블슈팅본 두 대상에 모두 걸린다.
    rows: list[dict] = []
    for entry in sorted(missing, key=lambda e: (str(e["model"]), str(e["code"]))):
        model = str(entry["model"])
        key = f"{model} {entry['code']}"
        claim_row = join["claims_by_key"].get(key)
        claim = claim_row["claim"] if claim_row else "NO_CLAIM"
        if claim == RESOLVED_CLAIM:  # 해소분은 결측 집합에 없으므로 여기 올 수 없다
            claim = "UNCLASSIFIED"

        scope = [t for t in READ_PLAN if _model_of(t.doc_slug) == model]
        per_target: list[AxisResult] = [
            axis_for(entry, t.doc_slug, read_pages.get(t.doc_slug) or {},
                     anchors_by_model.get(model, []))
            for t in scope
        ]
        best = max(per_target, key=lambda r: _AXIS_RANK[r.axis]) if per_target else _EMPTY_AXIS

        # 강등 판단은 **대상별**로 계산한 blind 를 코드 범위에서 보수적으로 합친다.
        # 조치문이 다른 대상에 있을 수 있으므로 "읽은 대상 중 하나라도 눈이 멀었으면" 강등한다.
        read_slugs = [t.doc_slug for t in scope if read_pages.get(t.doc_slug)]
        blind = any(slug in blind_slugs for slug in read_slugs) if read_slugs else False
        # 같은 보수 규칙을 **미판독 대상**에도 적용한다 — `UNREAD` 는 `_AXIS_RANK` 0 이라
        # `max()` 에서 조용히 밀린다. 그대로 두면 iG5A 두 대상 중 하나만 읽혀도 나머지
        # 하나의 `ANCHOR_ONLY` 만으로 부재가 확정된다 = "못 봤다"를 "없다"로 바꾸는 경로(D62).
        unread_slugs = [t.doc_slug for t in scope if not read_pages.get(t.doc_slug)]
        unread_in_scope = bool(unread_slugs)

        verdict = decide(
            claim,
            best.axis,
            rowspan_resolved=best.rowspan_resolved,
            reader_blind=blind,
            unread_in_scope=unread_in_scope,
        )
        undemoted = decide(claim, best.axis, rowspan_resolved=best.rowspan_resolved)
        page = entry.get("manual_page")
        primary_slug = next(
            (t.doc_slug for t in scope
             if (_manifest_manuals().get(t.doc_slug) or {}).get("role") == "primary"),
            "",
        )
        label_row = labels.get((primary_slug, page)) if isinstance(page, int) else None
        rows.append(
            {
                "model": model,
                "code": entry.get("code"),
                "display_code": entry.get("display_code"),
                "error_name": entry.get("error_name"),
                "anchor_page": page,
                "parser_claim": claim,
                "parser_reason": (claim_row or {}).get("reason", ""),
                "triage_label": (label_row or {}).get("label"),
                "triage_anchor_conflict": bool((label_row or {}).get("anchor_conflict")),
                "elice_axis": best.axis,
                "axis_by_target": [
                    {"doc_slug": r.doc_slug or t.doc_slug, "axis": r.axis, "page": r.page}
                    for r, t in zip(per_target, scope)
                ],
                "evidence_kind": best.evidence_kind,
                "evidence_page": best.page,
                "evidence": best.evidence,
                "anchor_source": best.anchor_source,
                "matched_token": best.matched_token,
                "weak_anchor": best.weak_anchor,
                "rowspan": best.rowspan,
                "covers_item_rows": best.covers_item_rows,
                "rowspan_resolved": best.rowspan_resolved,
                "reader_blind": blind,
                "unread_in_scope": unread_in_scope,
                "unread_targets": unread_slugs,
                "verdict": verdict,
                "verdict_before_blind_demotion": undemoted,
            }
        )

    counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in VERDICTS}
    axis_counts = {a: sum(1 for r in rows if r["elice_axis"] == a) for a in ELICE_AXES}
    pages_read = sum(len(p) for p in read_pages.values())
    page_chars = page_char_counts() if measure_page_chars else []

    warnings = _warnings(
        pages_read=pages_read,
        cost=cost,
        join=join,
        control_report=control_report,
        rows=rows,
        read_status=read_status,
        page_chars=page_chars,
    )
    after = {p.name: _sha256(p) for p in IMMUTABLE_INPUTS if p.exists()}
    if before != after:
        warnings.insert(
            0,
            "CANONICAL_CHANGED — 🔴 실행 중 정본/후보 파일 해시가 바뀌었다. 이 모듈은 "
            "어느 정본에도 쓰지 않는다(D99) — 다른 프로세스를 확인할 것.",
        )

    return {
        "generated_at": str(date.today()),
        "allow_purchase": allow_purchase,
        "inputs": {
            "error_codes": {
                "path": _rel(ERROR_CODES),
                "sha256_before": before.get(ERROR_CODES.name),
                "sha256_after": after.get(ERROR_CODES.name),
            },
            "candidate": {"path": _rel(CANDIDATE), "sha256_before": before.get(CANDIDATE.name),
                          "sha256_after": after.get(CANDIDATE.name)},
            "triage": {"path": _rel(TRIAGE), "exists": TRIAGE.exists()},
        },
        "canonical_unchanged": before == after,
        "cost": cost,
        "read_plan": [
            {"doc_slug": t.doc_slug, "pages": [t.page_numbers[0], t.page_numbers[-1]],
             "n_pages": len(t.page_numbers), "note": t.note}
            for t in READ_PLAN
        ],
        "read_status": read_status,
        "pages_read": pages_read,
        "page_chars": page_chars,
        "pending_join": {k: v for k, v in join.items() if k != "claims_by_key"},
        "control": control_report,
        "rows": rows,
        "verdict_counts": counts,
        "axis_counts": axis_counts,
        "thresholds": {
            "action_min_chars": ACTION_MIN_CHARS,
            "min_anchor_token_len": MIN_ANCHOR_TOKEN_LEN,
            "weak_anchor_len": WEAK_ANCHOR_LEN,
            "text_window_chars": TEXT_WINDOW_CHARS,
            "action_match_min_chars": ACTION_MATCH_MIN_CHARS,
            "action_markers": list(ACTION_MARKERS),
            "action_header_markers": list(ACTION_HEADER_MARKERS),
        },
        "vocabulary": {
            "verdicts": list(VERDICTS),
            "parser_claims": list(PARSER_CLAIMS),
            "elice_axes": list(ELICE_AXES),
            "resolved_claim": RESOLVED_CLAIM,
        },
        "warnings": warnings,
    }


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _warnings(
    *,
    pages_read: int,
    cost: dict,
    join: dict,
    control_report: list[dict],
    rows: list[dict],
    read_status: list[dict],
    page_chars: list[dict],
) -> list[str]:
    out: list[str] = []
    if pages_read == 0:
        out.append(
            f"NOT_READ — 판독 결과가 **0페이지**다(계획 {cost['n_pages']}p). 캐시가 비어 있고 "
            "구매가 허용되지 않았다. 이 실행의 모든 판정은 `INCONCLUSIVE` 이며, 그것은 "
            "'부재가 확인됐다'가 **아니라** '아직 안 읽었다'는 뜻이다."
        )
    elif pages_read < cost["n_pages"]:
        out.append(
            f"PARTIAL_READ — 계획 {cost['n_pages']}p 중 {pages_read}p 만 읽혔다. "
            "덜 읽은 대상의 판정은 부재 근거로 쓰지 말 것."
        )
    if join["joined"] != join["missing_total"]:
        out.append(
            f"JOIN_MISMATCH — 결측 {join['missing_total']}건 중 "
            f"{join['joined']}건만 `_pending_review` 와 조인됐다. 나머지는 `NO_CLAIM` 으로 "
            "표에 그대로 실린다(조용히 버리지 않는다)."
        )
    if join["excluded_claim_mismatch"]:
        out.append(
            "RESOLVED_MISMATCH — 결측 집합 밖인데 해소분 정규식에 안 걸린 항목: "
            + ", ".join(f"{r['model']} {r['code']}({r['claim']})"
                        for r in join["excluded_claim_mismatch"])
        )
    for report in control_report:
        if report["state"] == "blind":
            out.append(
                f"READER_BLIND — `{report['doc_slug']}`: 대조군 {report['controls_total']}건 중 "
                f"**정본 `actions` 문장이 판독 근거에서 확인된 건수가 0건**이다"
                f"(`ACTION_FOUND` 자체는 {report['action_found']}건 · "
                f"`ROW_TEXT_ONLY` {report['row_text_only']}건). 조치문이 실재하는 코드조차 못 "
                "찾는 판독기의 '없다'는 근거가 아니다 — **이 대상이 속한 모델의 판독 스코프 "
                "전체**에서 `CONFIRMED_ABSENT` 를 `INCONCLUSIVE` 로 강등했다(이 대상 한 곳이 "
                "아니라 그 모델의 코드 전부다)."
            )
        elif report["state"] == "no_controls" and report["pages_read"]:
            out.append(
                f"NO_CONTROLS — `{report['doc_slug']}`: 판독 범위 안에 대조군이 0건이라 "
                "판독기 생존을 **잴 수 없다**. 강등을 적용했다(못 잰 것을 통과로 바꾸지 않는다). "
                "강등 범위는 이 대상이 속한 모델의 판독 스코프 전체다."
            )
        if 0 < report["controls_total"] <= 2:
            out.append(
                f"CONTROL_WEAK — `{report['doc_slug']}`: 대조군이 "
                f"{report['controls_total']}건뿐이라 **통계적으로 약하다.** 이 대상의 "
                "`READER_BLIND` 발화/미발화 어느 쪽도 강한 근거가 아니다."
            )
        if report["action_found_text_window"]:
            out.append(
                f"LOOSE_LIVENESS — `{report['doc_slug']}`: `ACTION_FOUND` 판정 "
                f"{report['action_found']}건 중 {report['action_found_text_window']}건이 표가 "
                "아니라 **텍스트 창 폴백**에서 나왔다. 생존 축은 이 건수가 아니라 정본 대조 "
                "통과 건수(`action_verified`)이지만, 폴백 비중이 클수록 그 대조 근거 자체가 "
                "느슨하게 잡혔다는 뜻이라 함께 표시한다."
            )
        if report["action_found"] > report["action_verified"]:
            out.append(
                f"UNVERIFIED_ACTION — `{report['doc_slug']}`: `ACTION_FOUND` "
                f"{report['action_found']}건 중 "
                f"{report['action_found'] - report['action_verified']}건은 **정본 `actions` "
                "문장과 대조되지 않았다**(판독기가 다른 문장을 조치문으로 인정했거나 문장이 "
                "잘렸다). 생존 축은 대조 통과 건수로만 센다 — 근거 열을 직접 볼 것."
            )
    if any(r["weak_anchor"] for r in rows):
        weak = [f"{r['model']} {r['code']}" for r in rows if r["weak_anchor"]]
        out.append(
            f"WEAK_ANCHOR — 앵커 토큰이 {WEAK_ANCHOR_LEN}자 미만으로 짧은 항목(**출처와 무관하게** "
            f"적용 — `error_name` 자체가 짧아도 걸린다): "
            + ", ".join(weak)
            + ". 오탐 가능성이 있으니 근거 열을 직접 볼 것."
        )
    demoted_unread = sorted(
        {f"{r['model']} {r['code']}" for r in rows
         if r["unread_in_scope"] and r["verdict_before_blind_demotion"] == "CONFIRMED_ABSENT"}
    )
    if demoted_unread:
        out.append(
            "UNREAD_IN_SCOPE — 판독 대상 중 일부를 아직 못 읽어 부재 확정을 보류한 항목 "
            f"{len(demoted_unread)}건: " + ", ".join(demoted_unread)
            + ". **'못 봤다'를 '없다'로 바꾸지 않는다**(D62)."
        )
    missing_pdf = sorted({s["doc_slug"] for s in read_status if s["state"] == "pdf_missing"})
    if missing_pdf:
        out.append("PDF_MISSING — 원본 PDF 를 찾지 못한 대상: " + ", ".join(missing_pdf))
    store_failed = [s for s in read_status if s["state"] == "store_failed"]
    if store_failed:
        out.append(
            f"STORE_FAILED — 판독은 됐는데 **보관에 실패한 페이지 {len(store_failed)}건**: "
            + ", ".join(f"{s['doc_slug']} p.{s['page']}" for s in store_failed)
            + ". 구매를 허용한 실행이었다면 **지출이 캐시에 남지 않았다** — 재실행 시 다시 "
            "결제된다. 원인을 먼저 고칠 것."
        )
    unmeasured = [p for p in page_chars if p["state"] != "ok"]
    if unmeasured:
        out.append(
            f"PAGE_CHARS_INCOMPLETE — 문자 수를 재지 못한 페이지 {len(unmeasured)}건 "
            "(상태 열을 볼 것). ⛔ 0 이 아니라 '재지 못함'이다."
        )
    return out


# ──────────────────────────────────────────────── 리포트 렌더러
def _md_table(header: list[str], body: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def _cell(value: Any, limit: int = 60) -> str:
    text = re.sub(r"\s+", " ", str(value if value not in (None, "") else "—")).strip()
    text = text.replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _attribution_cell(row: dict) -> str:
    """`rowspan` 귀속 열. **`covers_item_rows == 0` 을 `1:1` 로 인쇄하지 않는다.**

    0 은 "이 셀이 어느 항목 행에 걸리는지 확인하지 못했다"이지 "1:1 로 풀렸다"가 아니다.
    예전 구현은 오프셋 계산이 격자 밖을 짚어 0 이 되면 `or 1` 로 1 을 만들어 리포트에 `1:1`
    을 찍었다 — 검수자가 오히려 신뢰하게 되는 인쇄였다(리뷰 C2).
    """
    if row["elice_axis"] != "ACTION_FOUND":
        return "—"
    if row["evidence_kind"] != "table_row":
        return "표밖"
    if row["rowspan_resolved"]:
        return "1:1"
    if row["covers_item_rows"]:
        return f"공유{row['covers_item_rows']}"
    return "미확인"


def render_markdown(result: dict) -> str:
    L: list[str] = []
    cost = result["cost"]
    join = result["pending_join"]
    L.append("# `actions` 부재 주장 3자 대조 — 검수 패키지 (MQ-1309)")
    L.append("")
    L.append(
        f"**생성**: {result['generated_at']} · **기계 생성 파일** — 손으로 표를 고치지 말고 "
        "`uv run python data/verify_actions_absence.py` 를 다시 돌릴 것."
    )
    L.append("")
    L.append(
        "⛔ **이 문서의 목적은 '회수'가 아니라 '불일치 해소'다.** `CONFIRMED_ABSENT` 다수는 "
        "**성공**이다 — 부재가 사실로 확정된 것이다. 회수 건수를 성공 지표로 삼으면 없는 "
        "조치문을 만들어내는 압력이 생기고 그것은 절대규칙 3 위반으로 직결된다."
    )
    L.append("")

    L.append("## 0. 경고")
    L.append("")
    if result["warnings"]:
        L.extend(f"- 🔴 {w}" for w in result["warnings"])
    else:
        L.append(
            f"- 경고 없음. 판독 {result['pages_read']}/{cost['n_pages']}페이지 · "
            f"조인 {join['join_ratio']}."
        )
    L.append("")

    L.append("## 1. 입력 — 전부 읽기 전용 (D99)")
    L.append("")
    inputs = result["inputs"]
    L.append(
        _md_table(
            ["파일", "sha256 (실행 전)", "sha256 (실행 후)", "동일?"],
            [
                [
                    f"`{inputs[name]['path']}`",
                    f"`{str(inputs[name]['sha256_before'])[:16]}…`",
                    f"`{str(inputs[name]['sha256_after'])[:16]}…`",
                    "✅" if inputs[name]["sha256_before"] == inputs[name]["sha256_after"] else "🔴",
                ]
                for name in ("error_codes", "candidate")
            ],
        )
    )
    L.append("")
    L.append(
        f"- triage 라벨: `{inputs['triage']['path']}` (존재 {inputs['triage']['exists']}) — "
        "**표시용**이다. `ANCHOR_CONFLICT` 가 붙은 행의 라벨은 triage 스스로 근거가 없다고 "
        "표시한 것이라 판정의 입력으로 쓰지 않는다."
    )
    L.append(
        f"- 이 스크립트는 어떤 정본에도 쓰지 않는다. 정본 불변 실측: "
        f"**{'동일' if result['canonical_unchanged'] else '변경됨 🔴'}**."
    )
    L.append("")

    L.append("## 2. 판독 계획 · 비용")
    L.append("")
    L.append(
        _md_table(
            ["대상(manifest id)", "물리 페이지", "쪽수", "원", "근거"],
            [
                [
                    f"`{row['doc_slug']}`",
                    f"p.{row['first_page']}~{row['last_page']}",
                    str(row["n_pages"]),
                    f"{row['won']:,}",
                    _cell(row["note"], 40),
                ]
                for row in cost["by_target"]
            ],
        )
    )
    L.append("")
    L.append(
        f"**합계 {cost['n_pages']}페이지 × {cost['won_per_page']}원 = "
        f"{cost['won_total']:,}원.** `--allow-purchase` 는 `--confirm-won "
        f"{cost['won_total']}` 이 정확히 일치할 때만 진행한다. 이번 실행의 구매 허용 = "
        f"**{result['allow_purchase']}**."
    )
    L.append("")
    L.append(
        "⚠ **위양성 위험 — 전액 지출 전에 반드시 읽을 것.** 이 대조 엔진의 조치성 판정은 "
        "표 머리행 표지(`조치`/`대책`/`Action` 등)와 셀 안의 표지어(`교체`·`제거`·`확인하십시오` "
        "등)에 의존한다(§9 문턱 참조). **실제 PDF 의 머리행이 계획과 다르면**(예: 조치사항표가 "
        "다른 절 번호로 이동했거나 열 이름이 바뀌었으면) `READER_BLIND` 가 **위양성**으로 발화할 "
        "수 있다 — 대조군이 진짜로 조치문을 갖고 있는데도 판독기가 그걸 못 찾은 것처럼 보여, "
        f"이 실행의 판독 {cost['n_pages']}페이지 · {cost['won_total']:,}원 **전액이 무조건 "
        "`INCONCLUSIVE` 로 끝난다.** 원인문에 표지어가 우연히 섞여 있으면 반대로 **위양성 "
        "`DISAGREE`** 가 뜬다(안전 방향이지만 사람이 볼 곳이 늘어난다 — "
        "`spikes/external_store_contract.py::_check_p` ⓟ-7 이 이 경로를 실제 사례(iG5A "
        "`COL`)로 계약 검사한다)."
    )
    L.append("")
    L.append(
        "**그래서 지출은 2단계로 나눈다** — 전액을 한 번에 태우지 않고, 소규모 실측으로 "
        "표 구조·조치성 문턱이 실제 응답에서 살아 있는지 먼저 확인한다:"
    )
    L.append("")
    L.append("```bash")
    L.append("# 1단계 — 소규모(예: 2p × 45원 = 90원)로 표 구조·조치성 문턱을 실제 응답에서 검증")
    L.append(
        "python -m data.external.elice_docvision --pdf <원본 PDF 경로> "
        "--pages 416 420 --doc-slug s100-manual --buy"
    )
    L.append("uv run python data/verify_actions_absence.py   # 캐시만 읽어 대조군 생존 재확인")
    L.append("")
    L.append("# 2단계 — 1단계에서 대조군이 살아 있는 것(state=ok)이 확인된 뒤에만 나머지를 태운다")
    L.append(
        f"uv run python data/verify_actions_absence.py --allow-purchase "
        f"--confirm-won {cost['won_total']}"
    )
    L.append("```")
    L.append(
        "⚠ `--pages` 는 범위가 아니라 **개별 페이지 나열**이다(`elice_docvision.py::main` "
        "`nargs=\"+\"`) — 위 예시는 416·420 두 페이지만 사고 416~420 전체를 사지 않는다. "
        "실제 CLI 인자는 소스에서 재확인할 것."
    )
    L.append("")

    L.append("### 2-1. 페이지별 pdfplumber 문자 수 (판독 범위 재확정 근거, 계획서 §6-2)")
    L.append("")
    if not result["page_chars"]:
        L.append(
            "- 이번 실행에서 측정하지 않았다(`--no-page-chars`). ⛔ 0 이 아니라 '재지 않음'이다."
        )
    else:
        by_slug: dict[str, list[dict]] = {}
        for row in result["page_chars"]:
            by_slug.setdefault(row["doc_slug"], []).append(row)
        for slug, page_rows in by_slug.items():
            L.append(f"**`{slug}`**")
            L.append("")
            L.append(
                _md_table(
                    ["물리 p.", "문자 수", "표 수", "상태"],
                    [
                        [
                            str(r["page"]),
                            "재지 못함" if r["chars"] is None else f"{r['chars']:,}",
                            "—" if r["tables"] is None else str(r["tables"]),
                            r["state"],
                        ]
                        for r in page_rows
                    ],
                )
            )
            measured = [r["chars"] for r in page_rows if r["chars"] is not None]
            L.append("")
            L.append(
                f"- 측정 {len(measured)}/{len(page_rows)}p · 합계 {sum(measured):,}자 · "
                f"0자 페이지 {sum(1 for c in measured if c == 0)}건"
            )
            L.append("")
        L.append(
            "⛔ 이 표로 계획을 **자동 축소하지 않는다.** 범위 확정은 사람 몫이다 — 앞뒤 여유 "
            "페이지는 *\"표가 구간 밖으로 이어지는가\"* 를 보기 위한 것이라 감축은 그 목적을 "
            "일부 포기하는 선택이다. 특히 `ig5a-manual p.201` 은 pdfplumber 로 0자라 "
            "**이 계획에서 값이 가장 큰 페이지**다(파서가 못 읽는 지점 = 2차 판독기를 쓰는 이유)."
        )
    L.append("")

    L.append("## 3. 판독 상태")
    L.append("")
    states: dict[str, int] = {}
    for row in result["read_status"]:
        states[row["state"]] = states.get(row["state"], 0) + 1
    L.append(
        "- " + " · ".join(f"`{k}` {v}건" for k, v in sorted(states.items()))
        + f" (총 {len(result['read_status'])}p)"
    )
    L.append(f"- 실제로 읽힌 페이지: **{result['pages_read']}p**")
    L.append("")

    L.append("## 4. 조인 무결성 — `_pending_review` ↔ 결측")
    L.append("")
    L.append(
        _md_table(
            ["항목", "실측"],
            [
                ["`_pending_review` 문자열", f"{join['pending_total']}건"],
                ["파싱 실패", f"{join['pending_parse_failed']}건"],
                ["정본 `actions` 결측", f"{join['missing_total']}건"],
                ["**조인 성공**", f"**{join['join_ratio']}**"],
                ["해소분 제외", f"{len(join['excluded_resolved'])}건"],
                ["조인 실패(→ `NO_CLAIM`)", f"{len(join['unjoined_missing'])}건"],
            ],
        )
    )
    L.append("")
    for row in join["excluded_resolved"]:
        L.append(
            f"- **제외**: `{row['model']} {row['code']}` — 정본에 `actions` 가 이미 있는 "
            f"**해소분**이다(분류 `{row['claim']}`). 그래서 `_pending_review` 는 35건인데 "
            "조인 대상은 34건이다."
        )
    if join["unjoined_missing"]:
        L.append(
            "- 조인 실패(표에 `NO_CLAIM` 으로 그대로 싣는다): "
            + ", ".join(join["unjoined_missing"])
        )
    L.append("")
    L.append("**파서 주장 분포(조인된 34건)**: " + " · ".join(
        f"`{k}` {v}" for k, v in sorted(join["by_claim"].items())
    ))
    L.append("")

    L.append("## 5. 대조군 · 리더 생존 검사 (양성 축 — P30 · D65)")
    L.append("")
    L.append(
        "*\"조치문이 실재하는 코드조차 못 찾는 판독기의 '없다'는 근거가 아니다.\"* "
        "대조군 = 판독 범위 안에 있으면서 **`actions` 가 이미 있는** 코드. 결측 코드와 "
        "**같은 알고리즘**으로 찾는다."
    )
    L.append("")
    L.append(
        "🔴 **생존 축은 `ACTION_FOUND` 건수가 아니라 `대조 통과` 건수다.** 대조군은 조치문 "
        "원문(정본 `actions`)을 **이미 갖고 있으므로**, *\"판독 결과에 그 문장이 정규화 "
        "부분일치로 나오는가\"* 로 잰다. 예전처럼 *\"앵커 행에 긴 이웃 셀이 있는가\"* 로 재면 "
        "판독 범위의 1차 표(트립·보호기능표)에는 **항상** 긴 설명 셀이 있어 대조군이 자명하게 "
        "충족되고 `READER_BLIND` 가 원리적으로 발화하지 못한다 — 양성 축이 검사 대상과 무관하게 "
        "참이 되는 P30 결함이다."
    )
    L.append("")
    L.append(
        _md_table(
            ["대상", "대조군", "**대조 통과**", "ACTION_FOUND", "ROW_TEXT_ONLY", "표 근거",
             "텍스트창 근거", "읽은 p", "상태"],
            [
                [
                    f"`{r['doc_slug']}`",
                    str(r["controls_total"]),
                    f"**{r['action_verified']}**",
                    str(r["action_found"]),
                    str(r["row_text_only"]),
                    str(r["action_found_table_row"]),
                    str(r["action_found_text_window"]),
                    str(r["pages_read"]),
                    r["state"],
                ]
                for r in result["control"]
            ],
        )
    )
    L.append("")
    L.append(
        "- 상태 `ok` = 생존 확인(**대조 통과 ≥ 1**) · `blind` = **강등 발동** · "
        "`no_controls` = 잴 수 없어 **강등 적용** · `unread` = 아직 안 읽음."
    )
    L.append(
        "- 강등 범위는 그 대상 하나가 아니라 **그 대상이 속한 모델의 판독 스코프 전체**다 "
        "(iG5A 는 표준본+트러블슈팅본 두 대상에 함께 걸린다)."
    )
    L.append("")
    L.append(
        "> **각주 — 대조군 수가 계획서와 다르다.** `sprint-13.md` 의 대조군 표는 `ig5a-manual` "
        "을 **13건**으로 적었으나 이 스크립트의 실측은 **15건**이다. 계획서가 열거하지 않은 "
        "`OC2`·`RERR`·`ETB`·`__L` 이 같은 규칙(*정본에 `actions` 가 있고 `manual_page` 가 그 "
        "모델 primary 본의 판독 범위 안*)에 걸린다. 계획서 표는 **손으로 고른 예시**이고 여기 "
        "숫자가 실측이다 — 선정 규칙은 두 갈래로, ⓐ `canonical.manual_page` 가 판독 범위 안 "
        "ⓑ 후보 파일의 `actions_manual_id`/`actions_page` 가 판독 범위 안(`selected_by` 열)."
    )
    L.append("")
    for report in result["control"]:
        if not report["rows"]:
            L.append(f"**`{report['doc_slug']}`** — 대조군 0건.")
            L.append("")
            continue
        L.append(f"**`{report['doc_slug']}`** — 대조군 {report['controls_total']}건")
        L.append("")
        L.append(
            _md_table(
                ["model", "code", "error_name", "앵커 p(계획)", "선정 근거", "축",
                 "발견 p(실측)", "대조", "판독 근거 원문", "정본 `actions`"],
                [
                    [
                        _cell(r["model"], 8),
                        _cell(r["code"], 8),
                        _cell(r["error_name"], 24),
                        str(r["anchor_page"]),
                        f"`{r['selected_by']}`",
                        r["axis"],
                        "—" if r["found_page"] is None else str(r["found_page"]),
                        (f"✅ {r['action_match_kind']}" if r["action_text_matched"] else "—"),
                        _cell(r["evidence"], 70),
                        _cell(r["expected_action_sample"], 70),
                    ]
                    for r in report["rows"]
                ],
            )
        )
        L.append("")

    L.append("## 6. 코드별 3자 대조표")
    L.append("")
    L.append(
        _md_table(
            ["model", "code", "error_name", "파서 주장", "triage 라벨", "Elice 축", "근거",
             "귀속", "판정"],
            [
                [
                    _cell(r["model"], 8),
                    _cell(r["code"], 8),
                    _cell(r["error_name"], 22),
                    f"`{r['parser_claim']}`",
                    (f"`{r['triage_label']}`" if r["triage_label"] else "—")
                    + (" ⚠충돌" if r["triage_anchor_conflict"] else ""),
                    f"`{r['elice_axis']}`",
                    _cell(r["evidence"] or r["evidence_kind"], 34),
                    _attribution_cell(r),
                    f"**{r['verdict']}**",
                ]
                for r in result["rows"]
            ],
        )
    )
    L.append("")
    L.append(f"행 수 = {len(result['rows'])} (정본 `actions` 결측 수와 일치 — 기계 생성 증명).")
    L.append("")
    demoted = [r for r in result["rows"]
               if r["verdict"] != r["verdict_before_blind_demotion"]]
    if demoted:
        L.append(
            f"⚠ **강등된 항목 {len(demoted)}건** (`CONFIRMED_ABSENT` → `INCONCLUSIVE`): "
            + ", ".join(
                f"{r['model']} {r['code']}"
                + ("(생존)" if r["reader_blind"] else "")
                + ("(미판독)" if r["unread_in_scope"] else "")
                for r in demoted
            )
            + ". `(생존)` = 리더 생존 검사 실패 · `(미판독)` = 이 코드의 판독 대상 중 "
            "아직 안 읽은 것이 있다."
        )
        L.append("")

    L.append("## 7. 판정 분포")
    L.append("")
    L.append(
        _md_table(
            ["판정", "건수", "뜻"],
            [
                ["`CONFIRMED_ABSENT`", str(result["verdict_counts"]["CONFIRMED_ABSENT"]),
                 "두 판독기가 모두 '없다' — **부재가 사실로 확정**(유효한 산출이다)"],
                ["`RECOVERABLE`", str(result["verdict_counts"]["RECOVERABLE"]),
                 "회수 후보 → ⛔ 정본에 쓰지 않는다. D99 게이트 경유"],
                ["`STILL_AMBIGUOUS`", str(result["verdict_counts"]["STILL_AMBIGUOUS"]),
                 "조치문은 읽혔으나 `rowspan` 귀속이 1:1 로 안 풀렸다"],
                ["`DISAGREE`", str(result["verdict_counts"]["DISAGREE"]),
                 "파서와 판독기가 어긋난다 — **사람이 볼 곳**"],
                ["`INCONCLUSIVE`", str(result["verdict_counts"]["INCONCLUSIVE"]),
                 "판독 실패·앵커 부재·강등 — '없다'가 **아니다**"],
            ],
        )
    )
    L.append("")
    L.append("**Elice 축 분포**: " + " · ".join(
        f"`{k}` {v}" for k, v in result["axis_counts"].items()
    ))
    L.append("")

    L.append("## 8. 판정 매트릭스 (계약)")
    L.append("")
    L.append(
        _md_table(
            ["파서 \\ Elice", "ACTION_FOUND", "ROW_TEXT_ONLY", "ANCHOR_ONLY", "NO_ANCHOR",
             "UNREAD"],
            [
                ["`ABSENT_IN_MANUAL`", "DISAGREE", "**CONFIRMED_ABSENT**",
                 "**CONFIRMED_ABSENT**", "INCONCLUSIVE", "INCONCLUSIVE"],
                ["`AMBIGUOUS`", "RECOVERABLE(1:1) / STILL_AMBIGUOUS", "DISAGREE", "DISAGREE",
                 "INCONCLUSIVE", "INCONCLUSIVE"],
                ["`NOT_FOUND_ON_PAGE`", "RECOVERABLE", "DISAGREE", "DISAGREE", "INCONCLUSIVE",
                 "INCONCLUSIVE"],
                ["`UNCLASSIFIED`·`NO_CLAIM`", "RECOVERABLE", "INCONCLUSIVE", "INCONCLUSIVE",
                 "INCONCLUSIVE", "INCONCLUSIVE"],
            ],
        )
    )
    L.append("")
    L.append(
        "- `NO_ANCHOR` 는 **절대** `CONFIRMED_ABSENT` 가 되지 않는다 — 양성 축이 죽은 상태에서 "
        "부재를 주장할 수 없다(P30 · D65)."
    )
    L.append(
        "- `ROW_TEXT_ONLY` = *\"앵커 행에 `ACTION_MIN_CHARS` 이상의 이웃 셀이 있을 뿐, 그게 "
        "조치문이라는 근거는 없다\"*. 판정상 `ANCHOR_ONLY` 와 **같게** 다루고 축으로만 분리해 "
        "인쇄한다 — 판독 범위의 1차 표는 조치표가 아니라 트립/보호기능표라 항상 긴 설명 셀이 "
        "있기 때문이다(S100 `NMT` p.416 설명 53자 · `ALOR` p.418 설명 92자, 둘 다 `actions` 0건)."
    )
    L.append(
        "- 강등은 두 갈래다 — `reader_blind`(대조군 생존 실패) **와** `unread_in_scope`(이 "
        "코드의 판독 대상 중 아직 안 읽은 것이 있음). 둘 다 `CONFIRMED_ABSENT` 만 "
        "`INCONCLUSIVE` 로 내린다. `UNREAD` 는 축 우선순위가 0 이라 `max()` 에서 조용히 밀리므로, "
        "이 별도 축이 없으면 **\"못 봤다\"가 \"없다\"로 바뀐다**(D62)."
    )
    L.append(
        "- 축은 **읽은 페이지 union(대상 문서 범위)** 단위다. 앵커는 9.1(p.416~419)에, 조치문은 "
        "9.2(p.420~421)에 있어 페이지 단위로 재면 전부 `ANCHOR_ONLY` 가 된다."
    )
    L.append("")

    L.append("## 9. 문턱과 한계 (전부 재량값 — 실측과 함께 인쇄한다)")
    L.append("")
    th = result["thresholds"]
    L.append(f"- 조치문 인정 최소 길이 **{th['action_min_chars']}자** — 임의값이다. 정본에 닿지 "
             "않아 느슨해도 안전하지만 값을 숨기지 않는다.")
    L.append(f"- 앵커 토큰 최소 길이 {th['min_anchor_token_len']}자 · 약한 앵커 표시 문턱 "
             f"{th['weak_anchor_len']}자(**출처와 무관하게** 적용 — `error_name` 자체가 2자인 "
             f"S100 `BX` 도 약한 앵커로 표시된다) · 텍스트 창 {th['text_window_chars']}자")
    L.append("- 앵커는 {`error_name`, `display_code`, `code`} 정규화(대소문자·공백 무시) "
             "**부분일치**이고 `error_name` 이 1차 축이다. S100 9.2 조치표 항목 열은 LCD "
             "영문명뿐이라 코드 토큰으로 잡으면 대조군이 전멸한다.")
    L.append("- 조치문 탐지는 **표 행 연관**이 1차다. **표에서 조치성 셀을 못 찾았을 때** "
             "(표가 아예 없을 때뿐 아니라 표는 있는데 조치 셀이 없을 때도) 텍스트 창 폴백을 "
             "쓰고 `evidence_kind` 로 구분해 인쇄한다 — 폴백 근거는 `rowspan` 귀속을 주장하지 "
             "않으므로 `AMBIGUOUS` 는 `STILL_AMBIGUOUS` 로 떨어진다.")
    L.append(f"- **조치성 판정은 표 경로와 텍스트 폴백에 똑같이 건다.** 조치 열(머리행에 "
             f"{' · '.join('`' + m + '`' for m in th['action_header_markers'])} 중 하나 — "
             "정규화(공백 제거·소문자) 후 비교) 이거나 "
             f"셀/창 본문에 표지({' · '.join('`' + m + '`' for m in th['action_markers'])})가 "
             "있어야 `ACTION_FOUND` 다. 아니면 `ROW_TEXT_ONLY` — 예전에는 폴백에만 게이트가 "
             "있고 1차(표) 경로에는 없어 **엄격도가 역전**돼 있었다.")
    L.append(f"- 대조군 생존 축은 정본 `actions` 문장과의 정규화 부분일치다(최소 대조 길이 "
             f"{th['action_match_min_chars']}자). `ACTION_FOUND` 건수로 재지 않는다 — 그러면 "
             "양성 축이 검사 대상과 무관하게 참이 된다(P30).")
    L.append("- `rowspan` 귀속은 **셀 정체성**으로 센다(격자에서 같은 셀 객체가 놓인 행 중 앵커 "
             "보유 행 수). 오프셋으로 세면 span 시작 행과 앵커 행이 다를 때 엉뚱한 행을 세고, "
             "표 끝에서 0 이 되어 가짜 `1:1` 이 만들어진다. 0 은 `미확인`으로 인쇄하며 "
             "`RECOVERABLE` 이 되지 않는다.")
    L.append("- Elice 를 **정답지로 취급하지 않는다**(D105). 독립 2차 판독기이며 실측 오탈자 "
             "사례가 있다. 두 판독기가 같은 답이면 강한 근거, 어긋나면 사람이 볼 지점이다.")
    L.append("- 페이지는 전부 PDF 물리 페이지다(D26). 인쇄 페이지 환산은 하지 않는다(D32).")
    L.append("- `RECOVERABLE` 은 ⛔ 정본·후보에 **쓰지 않는다**. D99 게이트(사람 승인)를 거친다.")
    L.append("")
    return "\n".join(L) + "\n"


# ──────────────────────────────────────────────── CLI
def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 대응

    parser = argparse.ArgumentParser(
        description="`actions` 부재 주장 3자 대조 (기본: 캐시만 — 네트워크 0 · 지출 0)"
    )
    parser.add_argument(
        "--allow-purchase",
        action="store_true",
        help="캐시 미스 페이지의 유료 판독을 허용한다. --confirm-won 이 함께 있어야 한다.",
    )
    parser.add_argument(
        "--confirm-won",
        type=int,
        default=None,
        help="지출 총액 확인값. cost_estimate()['won_total'] 과 정확히 일치해야 진행한다.",
    )
    parser.add_argument(
        "--no-page-chars",
        action="store_true",
        help="pdfplumber 페이지 문자 수 실측을 건너뛴다(리포트에서 그 절이 비게 된다).",
    )
    args = parser.parse_args()

    cost = cost_estimate()
    if args.allow_purchase:
        # 지출 이중 게이트 — 총액을 손으로 다시 적어야만 열린다.
        if args.confirm_won is None or args.confirm_won != cost["won_total"]:
            print(
                f"[중단] 지출 확인 불일치 — --confirm-won {args.confirm_won} != "
                f"{cost['won_total']} (계획 {cost['n_pages']}p × {cost['won_per_page']}원). "
                "네트워크를 타지 않았고 지출은 0원이다."
            )
            return 2
        print(
            f"[고지] 구매 허용 — 캐시 미스 페이지를 최대 {cost['n_pages']}p 까지 "
            f"{cost['won_per_page']}원/p 로 구매한다 (최대 {cost['won_total']:,}원). "
            "이미 캐시에 있는 페이지는 다시 사지 않는다."
        )
    elif args.confirm_won is not None:
        print("[안내] --confirm-won 은 --allow-purchase 와 함께일 때만 의미가 있다. 무시한다.")

    result = verify(
        allow_purchase=args.allow_purchase,
        measure_page_chars=not args.no_page_chars,
    )

    ANALYSIS.mkdir(parents=True, exist_ok=True)
    EXTRACTED.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text(render_markdown(result), encoding="utf-8")
    REPORT_JSON.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for warning in result["warnings"]:
        print(f"[경고] {warning}")
    print(f"[완료] {_rel(REPORT_MD)}")
    print(f"[완료] {_rel(REPORT_JSON)}")
    join = result["pending_join"]
    print(
        f"  판독 {result['pages_read']}/{cost['n_pages']}p · 계획 비용 {cost['won_total']:,}원 · "
        f"이번 실행 구매 허용 {result['allow_purchase']}"
    )
    print(
        f"  조인 무결성 {join['join_ratio']} (`_pending_review` {join['pending_total']}건 중 "
        f"해소분 {len(join['excluded_resolved'])}건 제외)"
    )
    print("  파서 주장: " + " · ".join(f"{k} {v}" for k, v in sorted(join["by_claim"].items())))
    print("  Elice 축: " + " · ".join(f"{k} {v}" for k, v in result["axis_counts"].items()))
    print("  판정: " + " · ".join(f"{k} {v}" for k, v in result["verdict_counts"].items()))
    for report in result["control"]:
        print(
            f"  대조군 {report['doc_slug']}: {report['controls_total']}건 / "
            f"정본 actions 대조 통과 {report['action_verified']} "
            f"(ACTION_FOUND {report['action_found']} · "
            f"ROW_TEXT_ONLY {report['row_text_only']}) -> {report['state']}"
        )
    print(
        f"  정본 불변(D99): {'동일' if result['canonical_unchanged'] else '🔴 변경됨'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
