"""
법령 원문 수집 · 적용 · 개정 감지

원칙:
  - 자동 덮어쓰기 금지. 해시가 달라지면 pending_revision을 만들고 사람에게 넘긴다.
  - 개정 감지 시 영향받는 룰을 역추적해 함께 보고한다.
  - 과거 스냅샷은 지우지 않는다 (append-only, D60).
  - 조문번호·제목이 어긋나면 파일을 고치지 않고 중단한다 (각 파일의 verification_note 요구사항).

**수집기(fetch_from_api)와 적용기(apply_fetch)를 분리한다.**
전자는 네트워크·인증키가 있어야 하지만 후자는 파일 조작뿐이라 합성 픽스처로 검증할 수 있다.
회귀는 `spikes/law_fetch_contract.py` (**네트워크 미사용** — 응답 정규화까지 합성 픽스처로 덮는다).

사용:
    uv run python data/rules/fetch_laws.py --check       # 개정 감지만
    uv run python data/rules/fetch_laws.py --fetch ID    # 특정 조문 수집
    uv run python data/rules/fetch_laws.py --fetch-all   # 등록 7건 순회 + 결과표
    uv run python data/rules/fetch_laws.py --pending     # pending_revisions 열람

────────────────────────────────────────────────────────────────────────────────
★ 실호출로 확정된 형식 (추측 금지 — 근거는 `data/analysis/law_fetch.md`)
────────────────────────────────────────────────────────────────────────────────
    lawSearch.do?OC=..&target=law&type=JSON&query=<법령명>&display=100&search=1
        display 기본값 20 → `상법`(동명 부분일치 56건)이 exact match 를 못 찾는다.
        search=2 는 **본문 검색**이라 법령명 exact match 가 전 법령에서 실패한다.
    lawService.do?OC=..&target=law&MST=<법령일련번호>&type=JSON&JO=<6자리>
        JO = 조번호 4자리 + 가지번호 2자리. `제24조` → `002400`.
        `24`·`002400000` 은 **HTTP 200 인데 조문단위가 0건**으로 조용히 실패한다.

★ `조문내용` 은 본문이 아니라 **제목인 경우가 있다** — 여기가 이 파일의 급소다
────────────────────────────────────────────────────────────────────────────────
    조문내용           = '제32조(세금계산서 등)'               ← 15자, 이게 전부
    항[0].항내용       = '① 사업자가 재화 또는 용역을 공급…'    ← 본문은 여기
    항[0].호[0].호내용 = '1. 공급하는 사업자의 등록번호와…'
    항[0].목[i].목내용 = '가. 기계장치 등 사업용 유형자산…'     ← 중첩 리스트로도 온다

`text = 조문내용` 으로 매핑하면 `apply_fetch` 의 비어있지 않음 검사를 **통과**하고
15자짜리 제목이 계층 1 "조문 원문"으로 해시되어 서명 번들에 실린다.
`11 §2` 가 막으려던 것("조문 원문을 손으로 타이핑하지 않는다")과 **같은 실패**가
자동 수집 경로에서 일어난다. 그래서 `flatten_article()` 이 조문내용·항내용·호내용·목내용을
계층 순서대로 평탄화하고, 평탄화 결과가 **제목 한 줄뿐이면 수집 실패로 중단**한다.

⚠️ law.go.kr OPEN API는 이용 신청이 필요하며 응답 스키마가 바뀔 수 있다.
   인증값(OC)은 **저장소에 남기지 않는다** — 로그·문서·주석·source_url 어디에도.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from engine import load_laws, load_rules, normalize, text_hash  # noqa: E402

LAWS_DIR = Path(__file__).parent / "laws"
PENDING_DIR = Path(__file__).parent / "pending_revisions"
REPO_ROOT = Path(__file__).resolve().parents[2]

# CLI 로 직접 실행하면 `.env` 가 자동으로 로드되지 않는다(backend 만 로드한다).
# `override=False` 라 이미 있는 환경변수를 덮지 않는다 — CI 는 env 로 주입하면 된다.
try:  # pragma: no cover — 의존성 부재 시에도 적용기·개정감지는 동작해야 한다
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env", override=False)
except ImportError:
    pass

# ⚠ 인증값은 API 키가 아니라 **신청한 이메일 ID 앞부분**이다 (hong@gmail.com → hong).
#    변수명이 사실과 어긋나 있어 개명했다. 뒤쪽은 개명 전 이름 — 폴백으로만 남긴다.
#    ⛔ 이 값을 출력·기록하지 않는다. 요청 URL 을 로그에 남길 때도 반드시 가린다.
API_OC = os.environ.get("LAW_API_OC") or os.environ.get("LAW_API_KEY")

SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"
DEFAULT_TIMEOUT = 10.0

# 부분 실패 시의 수집 우선순위. `VAT-INVOICE` 가 모든 SALE precheck 에서 발화하므로
# `KR-VAT-32` 없이는 어떤 매각 자산도 번들을 만들지 못한다(D78 부수 확정).
# `KR-CITA-ENF-31` 은 처분 룰이 참조하지 않아 S10 에 무관하다 — 그래서 맨 뒤다.
FETCH_PRIORITY = (
    "KR-VAT-32",
    "KR-STTC-24",
    "KR-STTC-146",
    "KR-OSHA-93",
    "KR-KCC-652",
    "KR-CIVIL-388",
    "KR-CITA-ENF-31",
)

# 적용 결과 3종. 그 밖의 상황(조문번호·제목 불일치, 미등록 참조)은 반환하지 않고 예외로 중단한다.
FILLED = "FILLED"
UNCHANGED = "UNCHANGED"
REVISION_PENDING = "REVISION_PENDING"

# 정체성 대조 키 — 값이 어긋나도, **아예 없어도** 중단한다. 선택적 필드는 여기 넣지 말 것.
IDENTITY_KEYS = ("article", "title")

# pending_revisions 레코드의 반영 상태.
#   None       반영 시도 없음 (force=False) — 사람 검토·서명 대기
#   "intent"   파일 기입 **직전** 기록. 기입 성공이 확인되지 않았다는 뜻
#   "confirmed" 기입 성공을 확인한 뒤 승격됨
# 기입 도중 죽으면 "intent" 로 남는다 — 기록이 사라지지도, 거짓말을 하지도 않는다.
APPLY_INTENT = "intent"
APPLY_CONFIRMED = "confirmed"


class LawMismatchError(Exception):
    """수집 응답이 등록된 조문과 어긋난다 — 파일을 고치지 않고 사람에게 넘긴다."""


class LawFetchError(Exception):
    """수집 자체가 실패했다 — 네트워크·인증·응답 형식·조문 부재.

    `LawMismatchError` 와 구분하는 이유: 저쪽은 **응답은 왔는데 다른 조문**이라
    사람의 판단(law_ref_id 정정 여부)이 필요하고, 이쪽은 **아직 아무것도 못 받은**
    상태라 재시도가 답이다. 한 예외로 뭉치면 결과표가 두 상황을 구분하지 못한다.
    """


# ---------------------------------------------------------------- 수집기


def _require_oc() -> str:
    """인증값 확인. **네트워크로 나가기 전에** 막는다."""
    if not API_OC:
        raise RuntimeError(
            "LAW_API_OC 미설정. law.go.kr에서 OPEN API 이용 신청 후 환경변수로 지정. "
            "값은 API 키가 아니라 신청한 이메일 ID 앞부분이다. "
            "키가 비어 있으면 응답이 '필수입력요소 검증에 실패하였습니다' 로 돌아온다."
        )
    return API_OC


def _redact(params: dict) -> str:
    """로그·예외 메시지용 파라미터 요약. **OC 는 절대 싣지 않는다.**"""
    return "&".join(f"{k}={v}" for k, v in params.items() if k != "OC")


def _get_json(url: str, params: dict, timeout: float) -> dict:
    """법제처 GET → JSON. 실패는 전부 `LawFetchError`.

    ⚠ **키가 틀려도 HTTP 200 이 온다.** 본문이 `{"result": "...검증에 실패하였습니다."}` 라
    `json.loads` 성공을 수집 성공으로 읽으면 조용히 넘어간다. 그래서 `result` 키를 직접 본다.
    """
    import httpx  # noqa: PLC0415 — 적용기·개정감지는 httpx 없이도 import 되어야 한다

    try:
        response = httpx.get(url, params=params, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise LawFetchError(f"{url} 호출 실패 ({_redact(params)}): {type(exc).__name__}") from None

    try:
        data = response.json()
    except ValueError:
        raise LawFetchError(
            f"{url} 응답이 JSON 이 아니다 ({_redact(params)}, "
            f"content-type={response.headers.get('content-type')})"
        ) from None

    if not isinstance(data, dict):
        raise LawFetchError(f"{url} 응답 최상위가 dict 가 아니다: {type(data).__name__}")

    # 인증·필수값 실패는 200 + result 로 온다. 실측 2종:
    #   OC 공백  → "필수입력요소 검증에 실패하였습니다."
    #   OC 오류  → "사용자 정보 검증에 실패하였습니다."
    if "result" in data:
        raise LawFetchError(
            f"법제처가 요청을 거부했다: {data.get('result')} / {data.get('msg')} "
            f"({_redact(params)}). 인증값(LAW_API_OC)과 등록 IP·도메인을 확인할 것."
        )
    return data


def resolve_mst(law_name: str, *, timeout: float = DEFAULT_TIMEOUT) -> str:
    """법령명 **exact match** 로 MST(법령일련번호) 확보.

    `display=100` 이 필수다 — 기본값 20 이면 `상법`처럼 부분일치가 많은 이름에서
    exact match 가 페이지 밖으로 밀려난다(실측: totalCnt 56, 상위 20건에 상법 없음).
    `search=1`(법령명 검색) 이 필수다 — `search=2` 는 본문 검색이라 전 법령에서 실패한다.

    동명이 2건 이상이면 **고르지 않고 예외**다 (D50 태도 — 임의 선택 금지).
    """
    params = {
        "OC": _require_oc(),
        "target": "law",
        "type": "JSON",
        "query": law_name,
        "display": 100,
        "search": 1,
    }
    data = _get_json(SEARCH_URL, params, timeout)
    payload = data.get("LawSearch")
    if not isinstance(payload, dict):
        raise LawFetchError(f"{law_name}: 응답에 LawSearch 가 없다 (키={sorted(data)[:5]})")

    candidates = _as_list(payload.get("law"))
    wanted = normalize(law_name)
    exact = [
        item
        for item in candidates
        if isinstance(item, dict) and normalize(str(item.get("법령명한글") or "")) == wanted
    ]
    if not exact:
        raise LawFetchError(
            f"{law_name}: 법령명 exact match 0건 (totalCnt={payload.get('totalCnt')}, "
            f"수신 {len(candidates)}건). 유사 법령을 임의로 고르지 않는다."
        )
    if len(exact) > 1:
        raise LawFetchError(
            f"{law_name}: 동명 법령 {len(exact)}건 — 사람이 고를 것 "
            f"(MST 후보={[str(item.get('법령일련번호')) for item in exact]})"
        )

    mst = str(exact[0].get("법령일련번호") or "").strip()
    if not mst:
        raise LawFetchError(f"{law_name}: 법령일련번호가 비어 있다")
    return mst


_ARTICLE_RE = re.compile(r"^\s*(\d+)\s*(?:의\s*(\d+))?\s*$")


def _jo_param(article: str, clause: str | None = None) -> str:
    """`JO` 파라미터. **조번호 4자리 + 가지번호 2자리 = 6자리** (실호출 확정).

        제24조    → '002400'
        제24조의2 → '002402'

    자리수를 틀리면(`24`·`002400000`) **HTTP 200 인데 조문단위가 0건**으로 돌아온다.
    응답이 비었다고 조문이 없는 게 아니라 파라미터가 틀린 것이다 — 이 함수가 유일한 조립점이다.

    `clause`(항)는 JO 로 표현되지 않는다. 조 단위로 받아 항·호·목을 평탄화하는 것이
    인용 앵커의 전제이므로(`11 §2`), 값이 들어오면 조용히 무시하지 않고 중단한다.
    """
    if clause not in (None, ""):
        raise ValueError(
            f"JO 는 조 단위만 지정한다 — 항({clause!r})은 API 파라미터로 표현되지 않는다. "
            "조 단위로 받아 항·호·목을 평탄화할 것."
        )
    matched = _ARTICLE_RE.match(str(article))
    if not matched:
        raise ValueError(f"조문번호 형식을 해석할 수 없다: {article!r} (예: '24', '24의2')")
    return f"{int(matched.group(1)):04d}{int(matched.group(2) or 0):02d}"


def _as_list(value: Any) -> list:
    """법제처는 항목이 1건이면 **리스트가 아니라 dict** 로 준다."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _lines(value: Any) -> list[str]:
    """문자열 | (중첩) 리스트 → 공백 아닌 줄 목록.

    `목내용` 은 문자열일 때도 있고 **리스트의 리스트**일 때도 있다(조특법 제24조 실측).
    타입 분기를 빼먹으면 그 조문의 본문 절반이 조용히 사라진다.
    """
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        return [line for item in value for line in _lines(item)]
    return []


# 하위 단위 컨테이너 → 그 단위의 본문 필드. 순서가 곧 출력 순서다.
_SUBUNITS: tuple[tuple[str, str], ...] = (("항", "항내용"), ("호", "호내용"), ("목", "목내용"))


def _subunit_lines(node: dict) -> list[str]:
    """항 → 호 → 목 순으로 하위 단위 본문을 계층 순서대로 모은다."""
    out: list[str] = []
    for container, content_key in _SUBUNITS:
        for child in _as_list(node.get(container)):
            if isinstance(child, dict):
                out.extend(_lines(child.get(content_key)))
                out.extend(_subunit_lines(child))
            else:
                out.extend(_lines(child))
    return out


def flatten_article(unit: dict) -> str:
    """조문단위 → 조문 **원문**. `조문내용 + 항내용 + 호내용 + 목내용` 평탄화.

    ⛔ `조문내용` 단독으로 쓰지 않는다. 조문에 따라 그 값이 본문 전체이기도 하고
    (`민법 제388조`, `조특법 제146조`) **제목 한 줄뿐**이기도 하다(`부가가치세법 제32조`).
    후자를 그대로 실으면 15자짜리 제목이 "조문 원문"으로 해시된다.
    """
    return "\n".join(_lines(unit.get("조문내용")) + _subunit_lines(unit))


def _heading_forms(unit: dict) -> set[str]:
    """`제32조(세금계산서 등)` 같은 **제목 한 줄** 표기 후보 (정규화된 형태)."""
    number = str(unit.get("조문번호") or "").strip()
    branch = str(unit.get("조문가지번호") or "").strip()
    label = f"제{number}조" + (f"의{branch}" if branch and branch != "0" else "")
    title = str(unit.get("조문제목") or "").strip()
    forms = {normalize(label)}
    if title:
        forms.add(normalize(f"{label}({title})"))
    return forms


def _article_id(unit: dict) -> str:
    """`조문번호`(+`조문가지번호`) → laws/*.json 의 `article` 표기."""
    number = str(unit.get("조문번호") or "").strip()
    branch = str(unit.get("조문가지번호") or "").strip()
    return f"{number}의{branch}" if branch and branch != "0" else number


def _iso_date(value: Any) -> str | None:
    """`YYYYMMDD` → `YYYY-MM-DD`. 형식이 다르면 **지어내지 않고** None."""
    digits = str(value or "").strip()
    if len(digits) != 8 or not digits.isdigit():
        return None
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"


def _source_url(law_name: str, article: str) -> str:
    """인용 앵커용 조문 단위 URL. **OC 를 포함하지 않는다** (키 유출 금지).

    법제처 본문 페이지 규약(`/법령/<법령명>/제<조>조`) — 실호출로 200 확인.
    """
    return f"https://www.law.go.kr/법령/{law_name}/제{article}조"


def parse_article_response(payload: dict, *, article: str, law_ref_id: str = "") -> dict:
    """lawService 응답 → `apply_fetch` 가 먹는 dict. **네트워크를 쓰지 않는 순수 함수.**

    여기서 하는 판단 세 가지:
      1. `조문여부 == '조문'` 인 단위만 고른다. `'전문'` 은 절 제목 줄이라 본문이 아니다
         (`제4절 안전검사`). 산업안전보건법 제93조·조특법 제24조는 **2건이 온다.**
      2. 요청한 조번호와 같은 단위만 남긴다. 2건 이상 남으면 고르지 않고 중단한다.
      3. 평탄화 결과가 **제목 한 줄뿐이면 수집 실패**로 중단한다 — 그대로 두면
         `apply_fetch` 의 비어있지 않음 검사를 통과해 제목이 원문으로 해시된다.
    """
    tag = law_ref_id or f"제{article}조"
    law = payload.get("법령")
    if not isinstance(law, dict):
        raise LawFetchError(f"{tag}: 응답에 '법령' 이 없다 (키={sorted(payload)[:5]})")

    basic = law.get("기본정보") if isinstance(law.get("기본정보"), dict) else {}
    units = [u for u in _as_list((law.get("조문") or {}).get("조문단위")) if isinstance(u, dict)]
    if not units:
        raise LawFetchError(
            f"{tag}: 조문단위 0건 — JO 파라미터 자리수를 확인할 것 "
            "(6자리가 아니면 HTTP 200 인데 조문이 비어 돌아온다)"
        )

    wanted = _jo_param(article)
    body_units = [
        u
        for u in units
        if str(u.get("조문여부") or "").strip() == "조문"
        and _jo_param(_article_id(u)) == wanted
    ]
    if not body_units:
        kinds = sorted({str(u.get("조문여부")) for u in units})
        raise LawFetchError(
            f"{tag}: 조문여부='조문' 인 제{article}조 단위가 없다 "
            f"(수신 {len(units)}건, 조문여부={kinds}). '전문'(절 제목)은 본문이 아니다."
        )
    if len(body_units) > 1:
        raise LawFetchError(f"{tag}: 같은 조번호의 '조문' 단위가 {len(body_units)}건 — 사람이 고를 것")

    unit = body_units[0]
    text = flatten_article(unit)
    if not text.strip():
        raise LawFetchError(f"{tag}: 평탄화 결과가 비었다 (조문내용·항·호·목 모두 공백)")
    if normalize(text) in _heading_forms(unit):
        raise LawFetchError(
            f"{tag}: 응답에 조문 **제목만** 있고 본문(항·호·목)이 없다: {text!r}. "
            "이 값을 원문으로 실으면 제목이 계층 1 해시가 된다 — 수집 실패로 처리한다."
        )

    law_name = str(basic.get("법령명_한글") or "").strip()
    article_id = _article_id(unit)
    return {
        "article": article_id,
        "title": str(unit.get("조문제목") or "").strip(),
        "text": text,
        # 조 단위로 받아 통합했으므로 항 단위 지정은 없다. 없는 값을 지어내지 않는다.
        "clause": None,
        # 조문 단위 시행일이 먼저다. 같은 법령이라도 조문별로 시행일이 다르다.
        "effective_from": _iso_date(unit.get("조문시행일자")) or _iso_date(basic.get("시행일자")),
        # ⚠ 공포번호는 조문 단위가 아니라 응답 `기본정보` 에 있다.
        "promulgation_no": str(basic.get("공포번호") or "").strip() or None,
        "source_url": _source_url(law_name, article_id) if law_name else "",
    }


def _store_payload(law_ref_id: str, article: str, payload: dict) -> None:
    """법제처 원본 응답을 `data/raw/external/law/` 에 소급 보관한다 (D103 · P28 ⓐ).

    ⛔ **지연 import + ROOT 부트스트랩** — `spikes/law_fetch_contract.py` 는 30개 스파이크 중
    유일하게 `sys.path` 에 REPO_ROOT 를 넣지 않는다(`data/rules` 만 넣는다). 이 함수를
    최상단에서 import 하면 그 스파이크가 `ModuleNotFoundError` 로 전멸한다.
    `_get_json` 의 `import httpx  # noqa: PLC0415` 지연 import 와 같은 형태다.

    key 는 내용 주소(`content_key`) — 같은 응답을 다시 받아도 파일이 늘지 않고,
    개정되면 새 파일이 는다. meta 는 allowlist 가 정확히 받는 2개(law_ref_id·article)만
    넘긴다 — 요청 파라미터(OC·MST·JO)·헤더는 넘기지 않는다(D103).

    실패해도 수집을 막지 않는다 — 예외를 삼키고 경고만 남긴다. 원본 보관은
    수집의 부수효과이지 필수조건이 아니다(D75, 기존 동작 불변).
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from data.external.store import ExternalStoreError, content_key, store_response  # noqa: PLC0415

    try:
        key = content_key(law_ref_id, payload)
        store_response("law", key, payload, meta={"law_ref_id": law_ref_id, "article": article})
    except (ExternalStoreError, OSError) as exc:
        print(f"[경고] 원본 보관 실패({law_ref_id}): {type(exc).__name__}", file=sys.stderr)
        return None


def _fetch_with_meta(law_ref_id: str, *, timeout: float = DEFAULT_TIMEOUT) -> tuple[dict, dict]:
    """`fetch_from_api` 의 본체. 결과표·검증용 계측치를 함께 돌려준다.

    계측치를 `fetch_from_api` 반환 dict 에 섞지 않는 이유: 그 dict 는 `apply_fetch` 의
    입력 계약이라 키가 늘면 계약이 흐려진다. **보고용 값은 별도 채널로 뺀다.**
    """
    _require_oc()
    path = _law_path(law_ref_id, LAWS_DIR)
    raw = json.loads(path.read_text(encoding="utf-8"))

    # 요청 주소를 만드는 데 필요한 것만 등록값에서 가져온다 —
    # `title` 은 **가져오지 않는다.** 등록 제목을 요청에 섞으면 정체성 대조가 자기 자신을 본다.
    law_name = str(raw.get("law_name") or "").strip()
    article = str(raw.get("article") or "").strip()
    if not law_name or not article:
        raise LawFetchError(f"{law_ref_id}: 등록 파일에 law_name·article 이 없다")

    mst = resolve_mst(law_name, timeout=timeout)
    jo = _jo_param(article, raw.get("clause"))
    params = {
        "OC": _require_oc(),
        "target": "law",
        "MST": mst,
        "type": "JSON",
        "JO": jo,
    }
    payload = _get_json(SERVICE_URL, params, timeout)
    _store_payload(law_ref_id, article, payload)
    fetched = parse_article_response(payload, article=article, law_ref_id=law_ref_id)

    units = [
        u
        for u in _as_list(((payload.get("법령") or {}).get("조문") or {}).get("조문단위"))
        if isinstance(u, dict)
    ]
    unit = next(
        u
        for u in units
        if str(u.get("조문여부") or "").strip() == "조문" and _jo_param(_article_id(u)) == jo
    )
    hangs = [h for h in _as_list(unit.get("항")) if isinstance(h, dict)]
    hang_heads = [head for h in hangs for head in _lines(h.get("항내용"))]
    meta = {
        "mst": mst,
        "jo": jo,
        "unit_count": len(units),
        "hang_count": len(hangs),
        "article_text_len": len(str(unit.get("조문내용") or "")),
        "text_len": len(fetched["text"]),
        "first_hang_head": hang_heads[0][:40] if hang_heads else None,
        "heading_only_len": len(next(iter(sorted(_heading_forms(unit), key=len, reverse=True)))),
    }
    return fetched, meta


def fetch_from_api(law_ref_id: str, *, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """law.go.kr OPEN API 로 조문 원문을 수집한다.

    반환: {"article", "title", "text", "clause", "effective_from",
           "promulgation_no", "source_url"} — `apply_fetch` 입력 계약과 동일.
    예외: RuntimeError(키 미설정) · LawFetchError(네트워크·응답 형식·조문 부재·제목뿐)

    ⛔ 여기서 파일을 쓰지 않는다. 정체성 대조·2단계 기록은 전부 `apply_fetch` 에 있다(D75).
    """
    fetched, _meta = _fetch_with_meta(law_ref_id, timeout=timeout)
    return fetched


# ---------------------------------------------------------------- 적용기


def _law_path(law_ref_id: str, laws_dir: Path) -> Path:
    path = laws_dir / f"{law_ref_id}.json"
    if not path.exists():
        # 불변식 2 (D61) — 등록되지 않은 조문에 원문을 붙이지 않는다.
        raise KeyError(f"미등록 법령 참조: {law_ref_id} ({path})")
    return path


def _verify_identity(law_ref_id: str, raw: dict, fetched: dict) -> None:
    """조문번호·제목 대조. 어긋나거나 **대조할 값 자체가 없으면** 파일을 손대기 전에 중단한다.

    누락을 통과시키지 않는 이유: 법제처 응답 필드명은 `조문번호`·`조문제목` 이라
    매핑을 빠뜨리기 쉽고, 그때 이 게이트가 조용히 무력화되면 대조 없이 원문이 기입된다.
    **"확인할 값이 없다"를 "확인했고 문제없다"로 처리하지 않는다** (D50·D62와 같은 태도).
    선택적 필드(effective_from·promulgation_no 등)는 대상이 아니다 — 정체성 키만 본다.
    """
    missing = [
        key
        for key in IDENTITY_KEYS
        if fetched.get(key) is None or not str(fetched[key]).strip()
    ]
    if missing:
        raise LawMismatchError(
            f"{law_ref_id}: 대조 키 누락/공백 {missing} → 파일 미수정. "
            f"응답에서 {', '.join(IDENTITY_KEYS)} 를 채운 뒤 다시 적용할 것 "
            "(법제처 응답 필드명은 조문번호·조문제목). "
            "대조할 값이 없는 것은 대조를 통과한 것이 아니다."
        )

    diffs = [
        f"{key}: 등록={raw.get(key)!r} / 응답={fetched[key]!r}"
        for key in IDENTITY_KEYS
        if normalize(str(fetched[key])) != normalize(str(raw.get(key, "")))
    ]
    if diffs:
        raise LawMismatchError(
            f"{law_ref_id}: 수집 응답이 등록 조문과 불일치 → 파일 미수정. "
            + " | ".join(diffs)
            + ". 개정으로 조문이 이동했을 수 있다 — law_ref_id 정정 여부를 사람이 판단할 것."
        )


def affected_rules(law_ref_id: str) -> list[str]:
    """개정된 조문을 참조하는 룰 역추적."""
    laws = load_laws()
    rules = load_rules(laws)
    return [r.rule_id for r in rules.values() if law_ref_id in r.law_refs]


def _write_pending_revision(
    law_ref_id: str,
    *,
    old_hash: str | None,
    new_hash: str,
    old_text: str | None,
    new_text: str,
    applied: str | None,
    pending_dir: Path,
) -> Path:
    """개정분 기록. **덮어쓰지 않는다** — 파일명에 타임스탬프를 붙여 누적한다 (D60).

    `applied` 는 None | APPLY_INTENT. APPLY_CONFIRMED 로의 승격은
    기입 성공을 확인한 뒤 `_confirm_pending_revision` 이 한다.
    """
    pending_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%S%f")
    path = pending_dir / f"{law_ref_id}.{stamp}.json"
    seq = 0
    while path.exists():
        seq += 1
        path = pending_dir / f"{law_ref_id}.{stamp}-{seq}.json"

    try:
        affected = affected_rules(law_ref_id)
    except Exception as exc:  # noqa: BLE001 — 역추적 실패가 개정 기록을 막으면 안 된다
        affected = [f"<역추적 실패: {exc}>"]

    record = {
        "law_ref_id": law_ref_id,
        "detected_at": now.isoformat(),
        "old_hash": old_hash,
        "new_hash": new_hash,
        "old_text": old_text,
        "new_text": new_text,
        "affected_rules": affected,
        "applied": applied,
        "confirmed_at": None,
        # confirmed 가 아닌 모든 상태는 사람이 봐야 한다 —
        # intent 는 "기입했다고 주장하지만 확인은 안 된 상태"다.
        "requires_signature": applied != APPLY_CONFIRMED,
    }
    _atomic_write(path, json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return path


def _atomic_write(path: Path, payload: str) -> None:
    """임시 파일에 다 쓴 뒤 `os.replace` 로 갈아끼운다 (N-6 이월).

    `write_text` 는 열자마자 원본을 0바이트로 만든다 — 도중에 죽으면 **계층 1 정본이
    빈 파일로 남는다.** append-only(D60)는 "지우지 않는다"는 약속인데 그 사고가 나면
    지운 것과 같아진다. 같은 디렉토리에 tmp 를 두는 이유: `os.replace` 의 원자성은
    같은 볼륨에서만 보장된다.
    """
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _confirm_pending_revision(path: Path) -> None:
    """기입 성공 확인 후 intent → confirmed 승격.

    append-only(D60)가 지키는 것은 **스냅샷 payload**(old/new text·hash)다.
    그 값들은 여기서 건드리지 않고 상태 필드만 전이한다 — flags.state 와 같은 성격.
    """
    record = json.loads(path.read_text(encoding="utf-8"))
    record["applied"] = APPLY_CONFIRMED
    record["confirmed_at"] = datetime.now(timezone.utc).isoformat()
    record["requires_signature"] = False
    _atomic_write(path, json.dumps(record, ensure_ascii=False, indent=2) + "\n")


def _write_law(path: Path, raw: dict) -> None:
    """계층 1 파일 기입. 키 순서·포맷을 원본 그대로 유지한다 (tmp + os.replace)."""
    _atomic_write(path, json.dumps(raw, ensure_ascii=False, indent=2) + "\n")


def apply_fetch(
    law_ref_id: str,
    fetched: dict[str, Any],
    *,
    force: bool = False,
    laws_dir: Path | None = None,
    pending_dir: Path | None = None,
) -> str:
    """수집 결과를 계층 1 파일에 적용한다.

    반환: 'FILLED' | 'UNCHANGED' | 'REVISION_PENDING'

      FILLED           최초 수집(PENDING→FETCHED) 또는 force 재적용 — 파일에 in-place 기입
      UNCHANGED        이미 FETCHED 이고 해시 동일 — 파일을 열지도 쓰지도 않는다
      REVISION_PENDING 이미 FETCHED 인데 해시 상이 — **덮어쓰지 않고** pending_revisions 에 기록

    중단(예외):
      KeyError          laws/ 에 없는 law_ref_id (불변식 2, D61)
      LawMismatchError  응답의 조문번호·제목이 등록값과 **불일치하거나 아예 없음** → 파일 미수정
      ValueError        응답에 text 가 없거나 비어 있음

    force=True 는 사람이 개정분을 검토한 뒤의 반영 경로다. 이 경우에도 직전 스냅샷을
    pending_revisions 에 남긴 뒤에 덮어쓴다 — 과거 원문을 지우지 않는다 (D60).
    기록은 `applied:"intent"` 로 먼저 쓰고 **기입 성공을 확인한 뒤** `"confirmed"` 로 승격한다 —
    기입이 실패하면 "적용됨"이라고 거짓말하는 기록이 남지 않는다.

    laws_dir·pending_dir 는 테스트에서 정본을 오염시키지 않기 위한 주입점이다.
    """
    laws_dir = laws_dir or LAWS_DIR
    pending_dir = pending_dir or PENDING_DIR

    path = _law_path(law_ref_id, laws_dir)
    raw = json.loads(path.read_text(encoding="utf-8"))

    new_text = fetched.get("text")
    if not isinstance(new_text, str) or not new_text.strip():
        raise ValueError(f"{law_ref_id}: 수집 응답에 text 가 없다 — 빈 원문을 계층 1에 넣지 않는다")

    # 파일을 손대기 전에 정체성부터 대조한다
    _verify_identity(law_ref_id, raw, fetched)

    new_hash = text_hash(new_text)
    already_fetched = raw.get("fetch_status") == "FETCHED" and raw.get("text") is not None

    if already_fetched and raw.get("text_hash") == new_hash:
        return UNCHANGED

    if already_fetched and not force:
        _write_pending_revision(
            law_ref_id,
            old_hash=raw.get("text_hash"),
            new_hash=new_hash,
            old_text=raw.get("text"),
            new_text=new_text,
            applied=None,
            pending_dir=pending_dir,
        )
        return REVISION_PENDING

    revision_path = None
    if already_fetched:  # force — 덮어쓰기 전에 직전 스냅샷을 남긴다
        revision_path = _write_pending_revision(
            law_ref_id,
            old_hash=raw.get("text_hash"),
            new_hash=new_hash,
            old_text=raw.get("text"),
            new_text=new_text,
            applied=APPLY_INTENT,
            pending_dir=pending_dir,
        )

    raw["text"] = new_text
    raw["text_hash"] = new_hash
    raw["fetch_status"] = "FETCHED"
    raw["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    # 응답이 준 것만 채운다. 없는 필드를 지어내지 않는다.
    for key in ("clause", "effective_from", "effective_to", "promulgation_no", "source_url"):
        if fetched.get(key) is not None:
            raw[key] = fetched[key]

    _write_law(path, raw)
    if revision_path is not None:
        # 기입이 실제로 끝난 뒤에만 "적용됨"이라고 말한다 (N7)
        _confirm_pending_revision(revision_path)
    return FILLED


# ---------------------------------------------------------------- 개정 감지


def check_revisions() -> list[dict]:
    """해시 비교로 개정 감지. 변경분은 pending_revision으로만 남긴다."""
    laws = load_laws()
    reports = []

    for law_ref_id, law in laws.items():
        if not law.is_fetched:
            reports.append({
                "law_ref_id": law_ref_id,
                "status": "NOT_FETCHED",
                "citation": law.citation(),
                "affected_rules": affected_rules(law_ref_id),
                "note": law.verification_note,
            })
            continue

        try:
            fetched = fetch_from_api(law_ref_id)
        # OSError 를 더한 이유(N-7 이월): 파일 1건의 입출력 실패가 **전체 스캔을 중단**시키면
        # 나머지 조문의 개정 여부를 영영 모르게 된다. 실패는 행으로 남기고 순회는 완주한다.
        except (RuntimeError, NotImplementedError, LawFetchError, OSError) as exc:
            reports.append({"law_ref_id": law_ref_id, "status": "FETCH_FAILED", "error": str(exc)})
            continue

        try:
            outcome = apply_fetch(law_ref_id, fetched)
        except (KeyError, ValueError, LawMismatchError) as exc:
            reports.append({"law_ref_id": law_ref_id, "status": "MISMATCH", "error": str(exc)})
            continue
        except OSError as exc:
            # 기입 실패는 불일치가 아니다 — 두 상황을 한 라벨로 뭉개지 않는다.
            reports.append({"law_ref_id": law_ref_id, "status": "APPLY_FAILED", "error": str(exc)})
            continue

        if outcome == UNCHANGED:
            reports.append({"law_ref_id": law_ref_id, "status": "UNCHANGED"})
            continue

        reports.append({
            "law_ref_id": law_ref_id,
            "status": "REVISION_DETECTED",
            "affected_rules": affected_rules(law_ref_id),
            "note": "pending_revisions에 기록됨. 담당자 검토·서명 전까지 반영되지 않는다.",
        })

    return reports


# ---------------------------------------------------------------- CLI

# 결과표의 판정 라벨. **FETCHED 는 "원문이 파일에 들어 있다"** 는 뜻이라
# 최초 기입(FILLED)과 재실행(UNCHANGED)을 함께 센다 — 그래야 재실행해도 같은 수가 나온다.
_ROW_FETCHED = "FETCHED"
_ROW_MISMATCH = "MISMATCH"
_ROW_FAILED = "FAILED"
_ROW_REVISION = "REVISION_PENDING"


def fetch_one(law_ref_id: str, *, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """수집 → 적용 1건. **예외를 밖으로 내지 않는다** — 결과표 1행을 돌려준다.

    한 건 실패로 순회를 멈추지 않기 위한 경계다. 그 대신 실패 사유를 행에 싣는다 —
    "몇 건 실패"만 남고 왜인지가 사라지면 다음 사람이 다시 조사해야 한다.
    """
    row: dict[str, Any] = {"law_ref_id": law_ref_id, "outcome": None, "note": ""}
    try:
        fetched, meta = _fetch_with_meta(law_ref_id, timeout=timeout)
    except (RuntimeError, LawFetchError, ValueError, KeyError, OSError) as exc:
        row["result"] = _ROW_FAILED
        row["note"] = f"{type(exc).__name__}: {exc}"
        return row

    row["meta"] = meta
    row["title"] = fetched["title"]
    row["effective_from"] = fetched["effective_from"]
    try:
        outcome = apply_fetch(law_ref_id, fetched)
    except LawMismatchError as exc:
        row["result"] = _ROW_MISMATCH
        row["note"] = str(exc)
        return row
    except (KeyError, ValueError, OSError) as exc:
        row["result"] = _ROW_FAILED
        row["note"] = f"{type(exc).__name__}: {exc}"
        return row

    row["outcome"] = outcome
    row["result"] = _ROW_REVISION if outcome == REVISION_PENDING else _ROW_FETCHED
    if outcome == REVISION_PENDING:
        row["note"] = "해시 상이 — 덮어쓰지 않고 pending_revisions 에 기록 (D60)"
    return row


def fetch_all(*, timeout: float = DEFAULT_TIMEOUT) -> list[dict]:
    """등록 전 건 순회. **한 건 실패로 중단하지 않는다.**

    순서는 `FETCH_PRIORITY` — 부분 수집으로 끝날 때 S10 이 살아남는 순서다.
    목록에 없는 신규 등록분은 뒤에 정렬해 붙인다(빠뜨리지 않기 위해).
    """
    registered = sorted(p.stem for p in LAWS_DIR.glob("*.json"))
    ordered = [rid for rid in FETCH_PRIORITY if rid in registered]
    ordered += [rid for rid in registered if rid not in FETCH_PRIORITY]
    return [fetch_one(rid, timeout=timeout) for rid in ordered]


def _print_fetch_table(rows: list[dict]) -> None:
    header = (
        f"  {'law_ref_id':<16} {'결과':<16} {'조문내용':>8} {'제목만':>7} "
        f"{'text':>7} {'항':>3}  비고"
    )
    print(header)
    print("  " + "─" * (len(header) + 12))
    for row in rows:
        meta = row.get("meta") or {}
        outcome = f"{row['result']}"
        if row.get("outcome") and row["result"] == _ROW_FETCHED:
            outcome += f"({row['outcome'][:2]})"
        note = (row.get("note") or "").splitlines()[0] if row.get("note") else ""
        print(
            f"  {row['law_ref_id']:<16} {outcome:<16} "
            f"{meta.get('article_text_len', '-'):>8} {meta.get('heading_only_len', '-'):>7} "
            f"{meta.get('text_len', '-'):>7} {meta.get('hang_count', '-'):>3}  {note[:60]}"
        )
    counts = {
        _ROW_FETCHED: sum(r["result"] == _ROW_FETCHED for r in rows),
        _ROW_MISMATCH: sum(r["result"] == _ROW_MISMATCH for r in rows),
        _ROW_FAILED: sum(r["result"] == _ROW_FAILED for r in rows),
    }
    revisions = sum(r["result"] == _ROW_REVISION for r in rows)
    line = (
        f"\n결과: FETCHED {counts[_ROW_FETCHED]} / MISMATCH {counts[_ROW_MISMATCH]} "
        f"/ FAILED {counts[_ROW_FAILED]}"
    )
    if revisions:
        line += f" / REVISION_PENDING {revisions}"
    print(line)
    print(
        "  MISMATCH 는 결함이 아니라 설계된 중단이다 — 파일을 손대지 않고 사람 승인으로 넘긴다 (D75).\n"
        "  '조문내용' 은 조문에 따라 본문 전체이기도, 제목 한 줄뿐이기도 하다. "
        "'제목만' 열과 비교할 것."
    )


def _print_pending() -> None:
    """`pending_revisions/` 열람 (N-7 이월). 서명 대기분을 먼저 보여준다."""
    if not PENDING_DIR.exists():
        print(f"pending_revisions 없음: {PENDING_DIR}")
        return
    records = []
    for path in sorted(PENDING_DIR.glob("*.json")):
        try:
            records.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError) as exc:  # 1건이 깨져도 나머지는 보여준다
            print(f"  [읽기 실패] {path.name}: {exc}")
    if not records:
        print("pending_revisions 비어 있음 — 감지된 개정분 없음")
        return
    todo = [r for r in records if r[1].get("requires_signature")]
    print(f"pending_revisions {len(records)}건 (서명 대기 {len(todo)}건)\n")
    for path, rec in records:
        print(
            f"  {'[서명대기]' if rec.get('requires_signature') else '[반영완료]'} {path.name}\n"
            f"      law_ref_id={rec.get('law_ref_id')} applied={rec.get('applied')} "
            f"detected_at={rec.get('detected_at')}\n"
            f"      affected_rules={rec.get('affected_rules')}\n"
            f"      old_hash={str(rec.get('old_hash'))[:24]}… "
            f"new_hash={str(rec.get('new_hash'))[:24]}…"
        )


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="개정 감지")
    parser.add_argument("--fetch", metavar="LAW_REF_ID", help="특정 조문 수집")
    parser.add_argument("--fetch-all", action="store_true", help="등록 전 건 순회 + 결과표")
    parser.add_argument("--pending", action="store_true", help="pending_revisions 열람")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="요청 타임아웃(초)")
    args = parser.parse_args()

    if args.check:
        for r in check_revisions():
            print(json.dumps(r, ensure_ascii=False))
    elif args.fetch_all:
        # 한 건 실패로 중단하지 않고 전 행을 출력한 뒤 exit 0 —
        # 부분 수집 상태를 사람이 보고 S10 진행 방식을 정한다 (`data/analysis/law_fetch.md`).
        _print_fetch_table(fetch_all(timeout=args.timeout))
    elif args.pending:
        _print_pending()
    elif args.fetch:
        row = fetch_one(args.fetch, timeout=args.timeout)
        print(json.dumps(row, ensure_ascii=False, indent=2))
        if row["result"] == _ROW_FAILED:
            raise SystemExit(f"[수집 불가] {args.fetch}: {row['note']}")
        if row["result"] == _ROW_MISMATCH:
            raise SystemExit(f"[적용 중단] {row['note']}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
