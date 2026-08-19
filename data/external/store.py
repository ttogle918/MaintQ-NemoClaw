"""외부 API 응답 원본 보관 (D103 · 백로그 P28 ⓐ 규약 구현체).

**이 모듈은 저장만 한다 — 네트워크를 타지 않는다.**
HTTP 클라이언트 라이브러리를 하나도 임포트하지 않으며 그 부재 자체가 회귀 검사 대상이다
(⛔ 그 라이브러리 이름을 주석·독스트링에도 적지 않는다 — 부분문자열 스캐너가 주석만 보고 FAIL 한다.
`spikes/law_fetch_contract.py ⓓ-2` 가 `sha256` 문자열로 같은 함정을 기록해 뒀다)
(`spikes/external_store_contract.py`, MQ-1310). 수집은 소비자 쪽 두 함수
(`data/rules/fetch_laws.py::_get_json` · `data/external/elice_docvision.py::_submit_and_wait`)
밖으로 나가지 않는다.

이 모듈이 지키는 것 6가지:

  ① **source·key 검증** — `SOURCES` 집합 + `KEY_RE` 로 경로 이탈(`..`·`/`·절대경로)을 막는다.
     검증 후 경로 포함 관계를 한 번 더 확인한다(정규식이 뚫려도 파일이 store 밖에 안 생긴다).
  ② **메타 allowlist (denylist 아님)** — `ALLOWED_META` 밖의 키는 거부하고 값은 스칼라만 받는다.
     요청 파라미터(`OC`·`MST`·`JO`)·헤더를 넣을 자리가 **구조적으로 없다.**
     2026-08-13 이 저장소는 평문 자격증명이 추적 파일로 새어 `git filter-repo` 로 히스토리를
     재작성했다(커밋 10개). denylist 는 "빠뜨리면 유출"이라 같은 사고가 반복된다.
  ③ **환경 자격증명 값 스캔** — 기입 직전 페이로드에 `CREDENTIAL_ENV_VARS` 의 *값* 이 들어
     있으면 거부한다. ⛔ 예외 메시지에는 **변수 이름만** 싣는다(값·본문 미포함).
     `MIN_CREDENTIAL_LEN` 미만은 스킵한다 — `LAW_API_OC` 는 이메일 ID 앞부분(4~8자)이라
     짧은 값이 본문에 우연히 걸리면 `fetch_laws` 저장이 **조용히** 죽는다(MQ-1305 가 예외를
     삼킨다). 스킵 여부는 `credential_scan_status()` 로 값 없이 조회해 리포트에 인쇄한다.
  ④ **`retrieved_at` 은 UTC 기본** (D39). naive datetime 은 거부한다.
  ⑤ **내용 주소 멱등** — 동일 내용 재저장은 무동작, 상이 내용은 거부(append-only, D60).
     비교 대상은 `body`(+`_meta`)의 canonical JSON 뿐이고 `_store.retrieved_at` 은 **제외**한다.
     봉투 전체를 비교하면 재저장이 매번 "상이 → 거부"가 된다.
  ⑥ **원자적 기입** — tmp + `os.replace`. `data/rules/fetch_laws.py::_atomic_write` 와 같은
     형태·같은 이유다. `write_text` 는 열자마자 원본을 0바이트로 만들어, 도중에 죽으면
     append-only(D60)가 지키려던 원본이 빈 파일로 남는다. tmp 는 같은 디렉터리에 둔다 —
     `os.replace` 의 원자성은 같은 볼륨에서만 보장된다.

⚠ **`STORE_ROOT` 파생 모듈 상수를 만들지 말 것.** `ELICE_DIR = STORE_ROOT / "elice"` 처럼
로드 시점에 파생시키면 테스트의 `monkeypatch.setattr(store, "STORE_ROOT", tmp_path)` 가
무효가 되어 **실 캐시를 보다 캐시 미스 → 유료 API 구매 경로**로 갈 수 있다(MQ-1308).
`store_path()` 는 반드시 **호출 시점에** 모듈 전역 `STORE_ROOT` 를 읽는다.

깨진 JSON·모르는 스키마는 `None` 이 아니라 **예외**다 (D62 — 모름을 통과로 바꾸지 않는다).
`None` 은 "파일이 없다" 한 가지 뜻으로만 쓴다.

봉투 구조:

    {
      "_store": {"schema": "maintq.external.v1", "source": ..., "key": ..., "retrieved_at": ...},
      "_meta":  {...allowlist 키만...},
      "body":   <응답 본문 원본>
    }

임포트 형식(공통 규약): `sys.path.insert(0, str(REPO_ROOT))` 후
`from data.external.store import ...`. ⛔ `data/external` 을 path 에 넣고 `import store` 하는
형식과 섞지 말 것 — 별개 모듈 객체가 되어 `monkeypatch` 와 동일성 검사가 무의미해진다
(`spikes/law_fetch_contract.py:33~34` 가 같은 함정을 기록해 뒀다).
`__init__.py` 는 두지 않는다(암시적 네임스페이스 패키지, `data/extract_triage.py:135` 선례).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final, Iterator

__all__ = [
    "ALLOWED_META",
    "CREDENTIAL_ENV_VARS",
    "ExternalStoreError",
    "KEY_RE",
    "MIN_CREDENTIAL_LEN",
    "SCHEMA",
    "SOURCES",
    "STORE_ROOT",
    "body_of",
    "content_key",
    "credential_scan_status",
    "iter_stored",
    "load_response",
    "store_path",
    "store_response",
]

# ⚠ 이 값을 파생시킨 모듈 상수를 만들지 말 것(모듈 독스트링 참조).
#    소비자·테스트는 `store.STORE_ROOT` 를 갈아끼우고, 모든 경로는 호출 시점에 여기서 나온다.
STORE_ROOT: Final[Path] = Path(__file__).resolve().parents[1] / "raw" / "external"

SCHEMA: Final[str] = "maintq.external.v1"

SOURCES: Final[frozenset[str]] = frozenset({"elice", "law"})

# 파일명이 되는 값이라 ASCII 로 제한한다. 첫 글자는 영숫자 — `.`/`-` 로 시작하는 이름
# (`..`·숨김파일·옵션처럼 보이는 이름)을 원천 차단한다. 총 120자 상한.
KEY_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
# 진단 전용 — 문자 하나가 허용 집합에 드는지만 본다. KEY_RE 는 "영숫자로 시작"까지
#   요구해서 단일 문자에 그대로 쓰면 허용 문자인 `-`·`.` 도 위반으로 찍힌다.
_KEY_CHAR_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9._-]")

# 🔴 allowlist 다. 여기 없는 키는 저장되지 않는다 — 요청 파라미터·헤더를 담을 자리가 없다.
ALLOWED_META: Final[dict[str, frozenset[str]]] = {
    "law": frozenset({"law_ref_id", "article"}),
    "elice": frozenset({"source_pdf", "page", "doc_slug", "manual_id", "price_won"}),
}

# 메타 값으로 허용하는 타입. dict/list 를 막아 "허용된 키 밑에 헤더 뭉치"를 못 넣게 한다.
_META_VALUE_TYPES: Final[tuple[type, ...]] = (str, int, float, bool, type(None))

# 기입 직전 페이로드에서 값을 찾아볼 환경변수 이름. **이름만** 코드에 남는다.
CREDENTIAL_ENV_VARS: Final[tuple[str, ...]] = (
    "LAW_API_OC",
    "LAW_API_KEY",
    "ELICE_API_KEY",
    "ELICE_DOCVISION_URL",
    "DATA_GO_KR_SERVICE_KEY",
    "IROS_API_KEY_APPLY_CASES",
    "IROS_API_KEY_APPLY_BY_AMOUNT",
    "IROS_API_KEY_STATUS_BY_GRANTOR",
    "IROS_API_KEY_DEBT_BY_GRANTOR",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "MAINTQ_A2A_FINALLQ_CLIENT_SECRET",
    "MAINTQ_A2A_INSUQ_CLIENT_SECRET",
)

# 이보다 짧은 값은 스캔하지 않는다(모듈 독스트링 ③). 문턱을 낮추면 4~8자짜리 `LAW_API_OC`
# 가 본문 어딘가에 우연히 포함돼 정상 수집이 조용히 죽는다.
MIN_CREDENTIAL_LEN: Final[int] = 8


class ExternalStoreError(RuntimeError):
    """보관 규약 위반. ⛔ 메시지에 본문·자격증명 값을 싣지 않는다(변수 이름까지만)."""


def store_path(source: str, key: str) -> Path:
    """`<STORE_ROOT>/<source>/<key>.json`. **호출 시점에** `STORE_ROOT` 를 읽는다.

    ⛔ 이 함수의 결과를 모듈 상수로 캐시하지 말 것 — 테스트의 monkeypatch 가 무효가 되고
    실 캐시를 보게 되어 유료 API 구매 경로가 열린다.
    """
    _check_source(source)
    _check_key(key)
    root = Path(STORE_ROOT)
    base = (root / source).resolve()
    path = (base / f"{key}.json").resolve()
    # KEY_RE 가 이미 구분자를 막지만, 정규식이 완화돼도 파일이 store 밖에 안 생기게 한 번 더 본다.
    if path.parent != base:
        raise ExternalStoreError(f"경로 이탈 거부 — key={key!r} 가 {source} 디렉터리를 벗어난다")
    return path


def store_response(
    source: str,
    key: str,
    body: Any,
    *,
    meta: dict[str, Any] | None = None,
    retrieved_at: datetime | str | None = None,
) -> Path:
    """응답 본문을 봉투에 담아 보관하고 경로를 돌려준다.

    - 같은 경로에 **내용이 같은** 봉투가 이미 있으면 아무것도 쓰지 않고 경로만 반환한다.
      비교는 `body` + `_meta` 의 canonical JSON 이며 `_store.retrieved_at` 은 제외한다.
    - 같은 경로에 **내용이 다른** 봉투가 있으면 `ExternalStoreError` — 덮어쓰지 않는다(D60).
    - `meta` 는 `ALLOWED_META[source]` 안의 키만, 값은 스칼라만 허용한다(요청 파라미터 차단).
    - `retrieved_at` 기본값은 현재 UTC(D39). naive datetime 은 거부한다.
    """
    path = store_path(source, key)
    envelope = {
        "_store": {
            "schema": SCHEMA,
            "source": source,
            "key": key,
            "retrieved_at": _normalize_retrieved_at(retrieved_at),
        },
        "_meta": _check_meta(source, meta),
        "body": body,
    }

    fingerprint = _fingerprint(envelope)
    if path.exists():
        existing = _read_envelope(path)
        if _fingerprint(existing) == fingerprint:
            return path  # 멱등 — 같은 응답 재수집이면 파일도 mtime 도 건드리지 않는다
        raise ExternalStoreError(
            f"append-only 위반 거부 — {source}/{key} 에 내용이 다른 원본이 이미 있다(D60). "
            "개정·재판독이면 새 key(content_key)로 저장할 것"
        )

    payload = json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    _scan_credentials(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, payload)
    return path


def load_response(source: str, key: str) -> dict | None:
    """보관된 봉투를 읽는다. **파일이 없을 때만** `None`.

    깨진 JSON·봉투가 아닌 구조·모르는 스키마는 `None` 이 아니라 예외다 (D62) —
    "모른다"를 "없다"로 바꾸면 캐시 미스로 오인돼 **유료 재판독**으로 이어진다.
    """
    path = store_path(source, key)
    if not path.exists():
        return None
    return _read_envelope(path)


def body_of(envelope: dict) -> Any:
    """봉투에서 응답 본문만 꺼낸다. 봉투가 아니면 예외(조용히 원본 취급하지 않는다, D62)."""
    if not isinstance(envelope, dict) or "body" not in envelope:
        raise ExternalStoreError("봉투 구조가 아니다 — 'body' 키가 없다")
    return envelope["body"]


def iter_stored(source: str | None = None) -> Iterator[Path]:
    """보관된 봉투 경로를 순회한다(source 별 이름순). `.json` 만 — tmp 조각은 제외된다."""
    if source is not None:
        _check_source(source)
        targets = [source]
    else:
        targets = sorted(SOURCES)
    root = Path(STORE_ROOT)
    for name in targets:
        directory = root / name
        if not directory.is_dir():
            continue
        yield from sorted(directory.glob("*.json"))


def content_key(prefix: str, body: Any) -> str:
    """`f"{prefix}.{sha256(canonical(body))[:12]}"` — 내용 주소 키.

    같은 응답을 다시 받으면 같은 key 라 파일이 늘지 않고, 내용이 바뀌면(개정·재판독) **새 파일**이
    는다. 이 해시는 여기 한 곳에만 둔다 — `fetch_laws.py` 본문에 `sha256` 문자열이 생기면
    `spikes/law_fetch_contract.py ⓓ-2` 가 FAIL 한다.
    """
    if not isinstance(prefix, str) or not prefix:
        raise ExternalStoreError("content_key prefix 가 비어 있다")
    digest = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()[:12]
    key = f"{prefix}.{digest}"
    _check_key(key)
    return key


def credential_scan_status() -> dict[str, str]:
    """자격증명 스캔 대상의 **상태만** 돌려준다 — 값은 절대 싣지 않는다.

    상태: `"scanned"`(스캔함) · `"skipped_short"`(`MIN_CREDENTIAL_LEN` 미만이라 스킵) ·
    `"unset"`(환경변수 없음). 리포트가 "무엇이 스킵됐는지"를 실측 인쇄하는 데 쓴다 —
    스킵을 모르면 `LAW_API_OC` 같은 짧은 값이 검사 밖에 있다는 사실이 감춰진다.
    """
    return {var: _scannable(var)[0] for var in CREDENTIAL_ENV_VARS}


def _scannable(var: str) -> tuple[str, str]:
    """(상태, 값). **양성 축과 실제 검사가 같은 로직을 쓰게 하는 단일 지점**이다 (P30).

    두 벌로 나뉘어 있으면 한쪽만 바뀌었을 때 리포트의 `"scanned"` 가 아무것도 보증하지
    않는 문구가 된다 — 이 저장소가 P30 에서 고친 결함과 같은 계열이다.
    """
    value = (os.environ.get(var) or "").strip()
    if not value:
        return "unset", value
    if len(value) < MIN_CREDENTIAL_LEN:
        return "skipped_short", value
    return "scanned", value


# ────────────────────────────── 내부 헬퍼 ──────────────────────────────


def _check_source(source: str) -> None:
    if source not in SOURCES:
        raise ExternalStoreError(f"미등록 source={source!r} — 허용: {sorted(SOURCES)}")


def _check_key(key: str) -> None:
    if not isinstance(key, str) or not KEY_RE.match(key):
        # ⛔ key 원문을 메시지에 싣지 않는다 — 조립 실수로 인증값이 섞이면 그대로 로그·리포트로
        #    흘러나간다. MQ-1305 는 이 예외를 삼켜 경고로 인쇄하므로 그 경로가 실제로 열려 있다.
        bad = "".join(sorted({c for c in str(key) if not _KEY_CHAR_RE.match(c)}))[:12] if key else ""
        raise ExternalStoreError(
            f"key 형식 위반 (길이 {len(str(key))}, 위반문자 {bad!r}) — "
            "영숫자로 시작하는 ASCII `[A-Za-z0-9._-]` 120자 이내"
        )


def _check_meta(source: str, meta: dict[str, Any] | None) -> dict[str, Any]:
    """allowlist 검증. 밖의 키는 거부 — 요청 파라미터·헤더가 들어올 자리를 없앤다."""
    if meta is None:
        return {}
    if not isinstance(meta, dict):
        raise ExternalStoreError("meta 는 dict 여야 한다")
    allowed = ALLOWED_META[source]
    rejected = sorted(k for k in meta if k not in allowed)
    if rejected:
        raise ExternalStoreError(
            f"허용되지 않은 메타 키 {rejected} (source={source}) — "
            f"허용: {sorted(allowed)}. 요청 파라미터·헤더·인증값은 보관 대상이 아니다(D103)"
        )
    for name, value in meta.items():
        if not isinstance(value, _META_VALUE_TYPES):
            raise ExternalStoreError(
                f"메타 값 타입 위반: {name} — 스칼라만 허용(중첩 구조로 요청 정보를 담을 수 없다)"
            )
    return {k: meta[k] for k in sorted(meta)}


def _normalize_retrieved_at(value: datetime | str | None) -> str:
    """UTC ISO-8601 문자열로 정규화한다 (D39).

    문자열도 받되 **타임존이 명시된 것만** 인정한다 — naive 값을 그대로 통과시키면
    "언제 받은 원본인지"가 로컬시간과 섞여 증거 가치가 떨어진다.
    포맷은 `data/rules/fetch_laws.py:677` 의 `retrieved_at` 과 같은 `isoformat()`(`+00:00`)이다.
    """
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ExternalStoreError("retrieved_at 은 타임존이 있어야 한다 (UTC, D39)")
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ExternalStoreError(f"retrieved_at 파싱 실패: {value!r}") from exc
        if parsed.tzinfo is None:
            raise ExternalStoreError("retrieved_at 은 타임존이 있어야 한다 (UTC, D39)")
        return parsed.astimezone(timezone.utc).isoformat()
    raise ExternalStoreError("retrieved_at 은 datetime 또는 ISO-8601 문자열이어야 한다")


def _canonical(value: Any) -> str:
    """비교용 정규 직렬화. 키 순서·공백에 흔들리지 않는다."""
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        # ⛔ 값을 메시지에 싣지 않는다 — 실패 대상은 타입까지만 밝힌다.
        raise ExternalStoreError(f"JSON 직렬화 불가 — type={type(value).__name__}") from exc


def _fingerprint(envelope: dict) -> str:
    """멱등 비교 지문 — `body` + `_meta` 만. `_store.retrieved_at` 은 **제외**한다.

    봉투 전체를 비교하면 수집 시각이 매번 달라 재저장이 늘 "상이 → 거부"가 된다.
    """
    return _canonical({"_meta": envelope.get("_meta") or {}, "body": envelope.get("body")})


def _read_envelope(path: Path) -> dict:
    """봉투 1개를 읽고 구조를 검증한다. 깨졌으면 예외 — `None` 으로 뭉개지 않는다(D62)."""
    raw = path.read_text(encoding="utf-8")
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExternalStoreError(f"보관 파일이 깨졌다: {path.name} — {exc.msg}") from exc
    if not isinstance(envelope, dict) or not isinstance(envelope.get("_store"), dict):
        raise ExternalStoreError(f"봉투 구조가 아니다: {path.name} — '_store' 없음")
    if "body" not in envelope:
        raise ExternalStoreError(f"봉투 구조가 아니다: {path.name} — 'body' 없음")
    schema = envelope["_store"].get("schema")
    if schema != SCHEMA:
        raise ExternalStoreError(f"모르는 스키마: {path.name} — schema={schema!r} (기대 {SCHEMA})")
    return envelope


def _scan_credentials(payload: str) -> None:
    """기입 직전 페이로드에 환경 자격증명 **값** 이 있으면 거부한다.

    ⛔ 예외 메시지에 값을 싣지 않는다 — 변수 이름까지만. 메시지 자체가 로그·리포트로 흘러
    나가는 경로가 있어(2026-08-13 사고) 값을 넣는 순간 같은 유출이 재발한다.
    `MIN_CREDENTIAL_LEN` 미만은 스킵한다(`credential_scan_status()` 로 확인 가능).
    """
    for var in CREDENTIAL_ENV_VARS:
        state, value = _scannable(var)
        if state != "scanned":
            continue
        # 원문과 **직렬화형** 둘 다 본다 — 값에 `"`·`\`·제어문자가 있으면 JSON 이스케이프로
        # 원문이 페이로드에 그대로 나타나지 않아 원문만 보는 검사는 조용히 우회된다.
        needles = {value, json.dumps(value)[1:-1]}
        if any(n and n in payload for n in needles):
            raise ExternalStoreError(
                f"저장 거부 — 페이로드에 환경변수 {var} 의 값이 포함돼 있다. "
                "요청 파라미터·헤더·인증값은 보관하지 않는다 (D103)"
            )


def _atomic_write(path: Path, payload: str) -> None:
    """임시 파일에 다 쓴 뒤 `os.replace` 로 갈아끼운다.

    `data/rules/fetch_laws.py::_atomic_write` 와 같은 형태·같은 이유다 — `write_text` 는
    열자마자 원본을 0바이트로 만들어, 도중에 죽으면 append-only(D60)가 지키려던 원본이
    빈 파일로 남는다. tmp 를 같은 디렉터리에 두는 이유: `os.replace` 의 원자성은 같은
    볼륨에서만 보장된다. tmp 는 `*.json` 이 아니라 git 추적 패턴에도 걸리지 않는다.
    """
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
