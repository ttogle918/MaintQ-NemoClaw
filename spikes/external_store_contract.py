# -*- coding: utf-8 -*-
"""외부 응답 원본 보관·소비자 계약 검증 (MQ-1310, Sprint 13 Stage 3 페이즈 2).

검증 대상:
  - `data/external/store.py` — 저장 경로·경로 이탈 차단·메타 allowlist·자격증명 스캔·
    멱등/append-only(D60)·원자적 기입(D103·D39·D62)
  - `data/rules/fetch_laws.py::_store_payload` — 소급 보관 지점의 호출 순서·지연 import·
    금칙 식별자(D103·D75)
  - `data/external/elice_docvision.py` — 지출 가드 순서(D105) · 가격 상수
  - `data/verify_actions_absence.py` — 판독 계획 산술 · 판정 매트릭스 오라클 `decide()`
    (MQ-1309, D65 · P30)
  - `.env.example` · `.gitignore` — 자격증명 값 부재 · git 추적 경계(D103 이 만든 절대규칙 5 예외)

**네트워크 0 · 지출 0.** 실 Elice·법제처 호출을 하지 않는다. `store.STORE_ROOT` 는 매 검사마다
tmp 디렉터리로 격리해서 실 캐시(`data/raw/external/`)를 오염시키지 않는다 — 오염되면 최악의
경우 캐시 미스를 유발해 유료 API 구매 경로로 이어질 수 있다(`data/external/test_elice_docvision.py`
와 같은 방어). 실행 전후로 `data/verify_actions_absence.py::IMMUTABLE_INPUTS`(정본) 의 sha256 을
재서 "쓰지 않았다"를 실측으로 증명한다 (D99).

**ⓖ 의 양성 축 (P30).** "자격증명이 없다"는 주장은 스캐너가 눈이 멀어도 참으로 보인다 —
그래서 축을 셋으로 나눈다: ① 실제 추적 파일에서 환경값을 찾는 `leaks_real`
② 일부러 심은 합성 픽스처가 반드시 검출되는지 보는 `scanner_alive`
③ 스캔한 파일 수 `scanned_total`. 판정은 `not leaks_real and scanner_alive and scanned_total > 0`.
스캔은 순수 함수 `scan(paths, needles)` 하나로 두 축에 **동일하게** 적용한다 — 두 벌로 나뉘면
한쪽만 바뀌었을 때 "검사했다"는 문구가 아무것도 보증하지 않게 된다(이 스위트가 반복해서
경계하는 결함 계열, `data/external/store.py::_scannable` 독스트링 참조).

실행:  uv run python spikes/external_store_contract.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data import verify_actions_absence as verify_mod  # noqa: E402
from data.external import elice_docvision, store  # noqa: E402
from data.verify_actions_absence import (  # noqa: E402
    ELICE_AXES,
    IMMUTABLE_INPUTS,
    PARSER_CLAIMS,
    READ_PLAN,
    action_text_match,
    cost_estimate,
    decide,
)

RAW = ROOT / "data" / "raw"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan(paths: list[Path], needles: list[str]) -> list[str]:
    """`paths` 중 `needles` 어느 하나라도 포함된 파일의 이름 목록. **순수 함수** — 읽기만 한다.

    원문과 JSON 이스케이프 형태 둘 다 본다 — `store.py::_scan_credentials` 와 같은 이유다.
    ⓖ 의 실제 축(git 추적 파일)과 생존 축(합성 픽스처)이 **같은 이 함수**를 통과한다(P30).
    """
    hits: list[str] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for needle in needles:
            if not needle:
                continue
            escaped = json.dumps(needle)[1:-1]
            if needle in text or escaped in text:
                hits.append(path.name)
                break
    return hits


def _git_ls_files(rel: str) -> tuple[bool, int | None, list[str]]:
    """(성공여부, rc, 파일목록). git 부재·rc 이상은 실패로 취급 — 통과로 읽지 않는다."""
    try:
        result = subprocess.run(  # noqa: S603
            ["git", "ls-files", rel],  # noqa: S607
            cwd=ROOT,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False, None, []
    if result.returncode != 0:
        return False, result.returncode, []
    return True, 0, [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]


def _check_ignore(rel_path: str) -> tuple[str, int | None]:
    """`git check-ignore` 1건 판정. rc 0=제외됨(ignored) · 1=추적대상(tracked) · 그 밖=오류."""
    try:
        result = subprocess.run(  # noqa: S603
            ["git", "check-ignore", rel_path],  # noqa: S607
            cwd=ROOT,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return "error", None
    if result.returncode == 0:
        return "ignored", 0
    if result.returncode == 1:
        return "tracked", 1
    return "error", result.returncode


class _FakeOS:
    """`store.os` 하나만 갈아끼우는 프록시 — **전역 `os` 모듈은 건드리지 않는다.**

    `store.os.replace = boom` 처럼 실제 `os` 모듈 속성을 바꾸면 프로세스 전체의
    `os.replace` 가 오염된다. 이 프록시는 `store` 모듈의 이름공간 안에서만 `replace` 를
    가로채고 나머지(`os.environ` 등)는 진짜 `os` 로 위임한다.
    """

    def __init__(self, real: Any) -> None:
        self._real = real

    def replace(self, *_args: Any, **_kwargs: Any) -> None:
        raise OSError("주입된 기입 실패 시뮬레이션 (spikes/external_store_contract.py)")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


@contextmanager
def _isolated_cache():
    """`store.STORE_ROOT` 를 tmp 디렉터리로 격리한다 — 실 캐시(`data/raw/external/`) 오염 방지.

    `store_path()` 가 **호출 시점에** 모듈 전역을 읽으므로(모듈 독스트링), 이 갈아끼우기가
    `store.*` 뿐 아니라 그 함수를 참조로 가져다 쓰는 `elice_docvision.py` 에도 그대로 적용된다.
    """
    original = store.STORE_ROOT
    tmp_dir = Path(tempfile.mkdtemp(prefix="ext_store_contract_"))
    store.STORE_ROOT = tmp_dir
    try:
        yield tmp_dir
    finally:
        store.STORE_ROOT = original
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _check_a() -> None:
    probe = store.store_path("elice", "x_p1_probe_never_written")
    expected_tail = ("data", "raw", "external", "elice", "x_p1_probe_never_written.json")
    check(
        "ⓐ 저장 경로 규약: store_path('elice', key) → data/raw/external/elice/<key>.json",
        probe.parts[-5:] == expected_tail
        and store.STORE_ROOT == ROOT / "data" / "raw" / "external"
        and not probe.exists(),
        f"path={probe} · STORE_ROOT={store.STORE_ROOT} · 파일 미생성={not probe.exists()}",
    )


def _check_b() -> None:
    cases: list[tuple[str, bool]] = []
    for label, source, key in (
        ("미등록 source", "s3_unregistered_source", "probe"),
        ("상위 디렉터리 이탈 ..", "elice", ".."),
        ("경로 구분자 /", "elice", "a/b"),
        ("숨김파일형 선행 .", "elice", ".hidden"),
    ):
        try:
            store.store_path(source, key)
            cases.append((label, False))
        except store.ExternalStoreError:
            cases.append((label, True))
    check(
        "ⓑ 미등록 source·경로 이탈 key 거부 (4종)",
        all(ok for _, ok in cases),
        f"{dict(cases)}",
    )


def _check_c(tmp_cache: Path) -> None:
    body = {"result": {"pages": [{"elements": [{"label": "table", "content": "<t/>"}]}]}}
    path = store.store_response(
        "elice", "roundtrip_probe_p1", body, meta={"doc_slug": "s100-manual", "page": 1}
    )
    loaded = store.load_response("elice", "roundtrip_probe_p1")
    match = loaded is not None and store.body_of(loaded) == body
    check(
        "ⓒ 봉투 round-trip: store_response → load_response → body_of",
        match and path.exists() and path.parent == tmp_cache / "elice",
        f"path={path.name} · body 일치={match} · iter_stored 포함="
        f"{path in list(store.iter_stored('elice'))}",
    )
    unstored = store.load_response("elice", "never_stored_probe")
    check(
        "ⓒ-2 load_response: 미보관 key → None",
        unstored is None,
        f"반환값={unstored!r} (type={type(unstored).__name__})",
    )


def _check_d() -> None:
    cases: list[tuple[str, bool]] = []
    for label, meta in (
        ("params", {"params": {"a": 1}}),
        ("headers", {"headers": {"Authorization": "x"}}),
        ("Authorization", {"Authorization": "Bearer x"}),
        ("OC", {"OC": "abcd1234"}),
    ):
        try:
            store.store_response(
                "law", f"meta_probe_{label.lower()}", {"x": 1}, meta=meta
            )
            cases.append((label, False))
        except store.ExternalStoreError:
            cases.append((label, True))
    check(
        "ⓓ 메타 allowlist: params·headers·Authorization·OC 4종 거부",
        all(ok for _, ok in cases),
        f"{dict(cases)}",
    )


def _check_e() -> None:
    same_body = {"result": "idempotent_probe_body"}
    meta = {"law_ref_id": "X", "article": "1"}
    p1 = store.store_response("law", "idem_probe", same_body, meta=meta)
    mtime1 = p1.stat().st_mtime_ns
    p2 = store.store_response("law", "idem_probe", same_body, meta=meta)
    mtime2 = p2.stat().st_mtime_ns
    check(
        "ⓔ 멱등: 동일 내용 재저장은 무동작 (경로·mtime 불변)",
        p1 == p2 and mtime1 == mtime2,
        f"path 동일={p1 == p2} · mtime 동일={mtime1 == mtime2}",
    )

    try:
        store.store_response(
            "law", "idem_probe", {"result": "different_probe_body"}, meta=meta
        )
        raised_diff = None
    except store.ExternalStoreError:
        raised_diff = "ExternalStoreError"
    after_body = store.body_of(store.load_response("law", "idem_probe"))
    check(
        "ⓔ-2 상이 내용 재저장 거부 (append-only, D60) · 원본 보존",
        raised_diff == "ExternalStoreError" and after_body == same_body,
        f"{raised_diff or 'no-raise'} · 원본 보존={after_body == same_body}",
    )


def _check_f(tmp_cache: Path) -> None:
    before = list(tmp_cache.rglob("*.tmp"))
    original_os = store.os
    store.os = _FakeOS(original_os)
    try:
        try:
            store.store_response(
                "law", "fail_probe", {"x": "fail_probe_body"}, meta={"law_ref_id": "Y", "article": "1"}
            )
            raised_fail = None
        except OSError:
            raised_fail = "OSError"
    finally:
        store.os = original_os
    after = list(tmp_cache.rglob("*.tmp"))
    check(
        "ⓕ 기입 실패 주입 후 .tmp 잔여 0건 (원자적 기입)",
        raised_fail == "OSError" and not after,
        f"{raised_fail or 'no-raise'} · 잔여 .tmp={len(after)}건 (주입 전 {len(before)}건)",
    )


def _check_g() -> None:
    git_ok, rc, tracked_names = _git_ls_files("data/raw/external")
    tracked_paths = [ROOT / n for n in tracked_names]

    real_needles = [
        os.environ[var]
        for var in store.CREDENTIAL_ENV_VARS
        if store.credential_scan_status().get(var) == "scanned"
    ]
    leaked_files = scan(tracked_paths, real_needles) if real_needles else []
    leaks_real = bool(leaked_files)

    synthetic_secret = "spike-synthetic-credential-9f8e7d6c5b4a"  # 실값 아님, 픽스처 전용
    fixture_dir = Path(tempfile.mkdtemp(prefix="ext_store_contract_fixture_"))
    fixture = fixture_dir / "synthetic_leak.json"
    fixture.write_text(json.dumps({"token": synthetic_secret}), encoding="utf-8")
    try:
        scanner_alive = bool(scan([fixture], [synthetic_secret]))
    finally:
        shutil.rmtree(fixture_dir, ignore_errors=True)

    scanned_total = len(tracked_paths)
    check(
        "ⓖ 평문 자격증명 부재 + 양성 축 (P30) — leaks_real·scanner_alive·scanned_total",
        git_ok and not leaks_real and scanner_alive and scanned_total > 0,
        f"git_ok={git_ok}(rc={rc}) · leaks_real={leaks_real}"
        f"(대상 {len(real_needles)}종 — {'미검증(환경값 없음)' if not real_needles else f'검출파일{leaked_files}'}) "
        f"· scanner_alive={scanner_alive}(합성 픽스처 탐지) · scanned_total={scanned_total}",
    )


def _check_h() -> None:
    env_path = ROOT / ".env.example"
    text = env_path.read_text(encoding="utf-8")
    keys = ("LAW_API_OC", "ELICE_API_KEY", "ELICE_DOCVISION_URL")
    missing = [k for k in keys if not re.search(rf"^{k}\s*=", text, re.MULTILINE)]
    filled = []
    for k in keys:
        m = re.search(rf"^{k}\s*=(.*)$", text, re.MULTILINE)
        if m:
            value = m.group(1).split("#", 1)[0].strip()
            if value:
                filled.append(k)
    check(
        "ⓗ .env.example: 키 이름 3종 존재 · 실값 없음",
        not missing and not filled,
        f"누락={missing or '없음'} · 값 채워짐={filled or '없음'}",
    )


def _check_i() -> None:
    state, rc = _check_ignore("data/raw/external/elice/__probe_never_written__.json")
    check(
        "ⓘ-1 신규 elice 응답 JSON → git 추적 대상 (rc=1)",
        state == "tracked",
        f"state={state} rc={rc}",
    )

    state, rc = _check_ignore("data/raw/external/elice/_tmp_probe_never_written.pdf")
    check(
        "ⓘ-2 임시 페이지 PDF 조각 → 제외 (rc=0)",
        state == "ignored",
        f"state={state} rc={rc}",
    )

    manifest = json.loads((RAW / "manifest.json").read_text(encoding="utf-8"))
    s100_file = next(
        m["file"] for m in manifest.get("manuals", []) if m.get("id") == "s100-manual"
    )
    state, rc = _check_ignore(f"data/raw/{s100_file}")
    check(
        "ⓘ-3 매뉴얼 PDF 원본 → 제외 (rc=0, 절대규칙 5 유지)",
        state == "ignored",
        f"state={state} rc={rc} · file={s100_file}",
    )


def _function_body(source: str, name: str) -> str:
    """`source` 안에서 최상위 함수 `def name(...)` 의 본문 텍스트. 없으면 빈 문자열.

    다음 최상위 `def ` (컬럼 0) 직전까지를 자른다 — 클래스 메서드는 들여쓰기가 있어
    `^def ` 에 걸리지 않으므로 경계로 안전하게 쓸 수 있다.
    """
    match = re.search(rf"^def {re.escape(name)}\(.*?\n(?=^def |\Z)", source, re.MULTILINE | re.DOTALL)
    return match.group(0) if match else ""


def _check_j() -> None:
    src = (ROOT / "data" / "rules" / "fetch_laws.py").read_text(encoding="utf-8")

    idx_get = src.find("payload = _get_json(")
    idx_store = src.find("_store_payload(law_ref_id, article, payload)")
    idx_parse = src.find("fetched = parse_article_response(")
    check(
        "ⓙ-1 소급 보관 지점 순서: _get_json → _store_payload → parse_article_response",
        idx_get != -1 and idx_store != -1 and idx_parse != -1 and idx_get < idx_store < idx_parse,
        f"인덱스 {idx_get} < {idx_store} < {idx_parse}",
    )

    body = _function_body(src, "_store_payload")
    bad_idents = [w for w in ("params", "headers") if re.search(rf"\b{w}\b", body)]
    lazy_import = bool(re.search(r"^\s+from data\.external\.store import", body, re.MULTILINE))
    check(
        "ⓙ-2 _store_payload 본문: params·headers 식별자 0건 · 지연 import",
        bool(body) and not bad_idents and lazy_import,
        f"본문확보={bool(body)} · 금칙식별자={bad_idents or '없음'} · 지연import={lazy_import}",
    )

    reimpl = [w for w in ("hashlib", "sha256(", "unicodedata", "NFKC") if w in src]
    check(
        "ⓙ-3 fetch_laws.py 본문에 해시 재구현 흔적 0건 (content_key 는 store.py 단일 소유)",
        not reimpl,
        f"검출={reimpl or '없음'}",
    )


def _check_k_static() -> None:
    src = (ROOT / "data" / "external" / "elice_docvision.py").read_text(encoding="utf-8")
    no_requests = "import requests" not in src and "requests." not in src
    check(
        "ⓚ-1 elice_docvision.py: requests import 0건 (httpx 만 지연 import)",
        no_requests,
        f"requests 참조={'없음' if no_requests else '검출'}",
    )

    body = _function_body(src, "extract_page")
    idx_cache = body.find("load_response(")
    idx_submit = body.find("_submit_and_wait(")
    check(
        "ⓚ-2 extract_page: 캐시 확인이 _submit_and_wait 호출보다 앞 (문자열 인덱스)",
        bool(body) and idx_cache != -1 and idx_submit != -1 and idx_cache < idx_submit,
        f"본문확보={bool(body)} · load_response idx={idx_cache} < _submit_and_wait idx={idx_submit}",
    )

    check(
        "ⓚ-3 PRICE_PER_PAGE_WON == 45",
        elice_docvision.PRICE_PER_PAGE_WON == 45,
        f"실측 {elice_docvision.PRICE_PER_PAGE_WON}",
    )


def _check_k_actual(tmp_cache: Path) -> None:
    calls = {"n": 0}

    def _boom_submit(*_args: Any, **_kwargs: Any) -> Any:
        calls["n"] += 1
        raise AssertionError("이 스파이크에서 _submit_and_wait 는 절대 호출되면 안 된다")

    original_submit = elice_docvision._submit_and_wait
    elice_docvision._submit_and_wait = _boom_submit
    try:
        try:
            elice_docvision.extract_page(
                Path("nonexistent_probe.pdf"), 1, doc_slug="s100-manual", allow_purchase=False
            )
            raised_a = None
        except elice_docvision.EliceError:
            raised_a = "EliceError"
        check(
            "ⓚ-4 캐시 미스 + allow_purchase=False → 예외 · 네트워크 0회",
            raised_a == "EliceError" and calls["n"] == 0,
            f"{raised_a or 'no-raise'} · _submit_and_wait 호출 {calls['n']}회",
        )

        saved_key = os.environ.pop("ELICE_API_KEY", None)
        saved_url = os.environ.pop("ELICE_DOCVISION_URL", None)
        try:
            try:
                elice_docvision.extract_page(
                    Path("nonexistent_probe.pdf"), 2, doc_slug="s100-manual", allow_purchase=True
                )
                raised_b = None
            except elice_docvision.EliceError:
                raised_b = "EliceError"
        finally:
            if saved_key is not None:
                os.environ["ELICE_API_KEY"] = saved_key
            if saved_url is not None:
                os.environ["ELICE_DOCVISION_URL"] = saved_url
        check(
            "ⓚ-5 캐시 미스 + allow_purchase=True 인데 키/URL 없음 → 지출 전 예외 · 네트워크 0회",
            raised_b == "EliceError" and calls["n"] == 0,
            f"{raised_b or 'no-raise'} · _submit_and_wait 호출 {calls['n']}회",
        )
    finally:
        elice_docvision._submit_and_wait = original_submit
    # tmp_cache 는 컨텍스트가 소유 — 여기서는 격리 확인만.
    check(
        "ⓚ-6 실측 중 실 캐시 디렉터리 미생성 (격리 확인)",
        not (ROOT / "data" / "raw" / "external" / "elice" / "s100-manual_p1.json").exists()
        and not (ROOT / "data" / "raw" / "external" / "elice" / "s100-manual_p2.json").exists(),
        f"tmp_cache={tmp_cache.name} (실 캐시 경로 미접촉)",
    )


def _check_l() -> None:
    n_pages = sum(len(t.page_numbers) for t in READ_PLAN)
    cost = cost_estimate()
    check(
        "ⓛ 판독 계획 산술: 34p / 1530원",
        n_pages == 34
        and cost["n_pages"] == 34
        and cost["won_per_page"] == elice_docvision.PRICE_PER_PAGE_WON
        and cost["won_total"] == 34 * elice_docvision.PRICE_PER_PAGE_WON == 1530,
        f"n_pages={cost['n_pages']} · won_per_page={cost['won_per_page']} · won_total={cost['won_total']}",
    )


def _check_m() -> None:
    no_anchor_ok = all(decide(c, "NO_ANCHOR") != "CONFIRMED_ABSENT" for c in PARSER_CLAIMS)
    check(
        "ⓜ-1 NO_ANCHOR 는 어떤 claim 과도 CONFIRMED_ABSENT 가 되지 않는다 (양성 축 사수, P30)",
        no_anchor_ok,
        f"{[decide(c, 'NO_ANCHOR') for c in PARSER_CLAIMS]}",
    )
    check(
        "ⓜ-2 ABSENT_IN_MANUAL × ANCHOR_ONLY → CONFIRMED_ABSENT",
        decide("ABSENT_IN_MANUAL", "ANCHOR_ONLY") == "CONFIRMED_ABSENT",
        decide("ABSENT_IN_MANUAL", "ANCHOR_ONLY"),
    )
    check(
        "ⓜ-3 AMBIGUOUS × ACTION_FOUND (rowspan 1:1 해소) → RECOVERABLE",
        decide("AMBIGUOUS", "ACTION_FOUND", rowspan_resolved=True) == "RECOVERABLE",
        decide("AMBIGUOUS", "ACTION_FOUND", rowspan_resolved=True),
    )
    check(
        "ⓜ-4 AMBIGUOUS × ACTION_FOUND (rowspan 미해소) → STILL_AMBIGUOUS",
        decide("AMBIGUOUS", "ACTION_FOUND", rowspan_resolved=False) == "STILL_AMBIGUOUS",
        decide("AMBIGUOUS", "ACTION_FOUND", rowspan_resolved=False),
    )
    check(
        "ⓜ-5 reader_blind=True 는 CONFIRMED_ABSENT 를 INCONCLUSIVE 로 강등",
        decide("ABSENT_IN_MANUAL", "ANCHOR_ONLY", reader_blind=True) == "INCONCLUSIVE",
        decide("ABSENT_IN_MANUAL", "ANCHOR_ONLY", reader_blind=True),
    )
    check(
        "ⓜ-6 ABSENT_IN_MANUAL × ACTION_FOUND → DISAGREE",
        decide("ABSENT_IN_MANUAL", "ACTION_FOUND") == "DISAGREE",
        decide("ABSENT_IN_MANUAL", "ACTION_FOUND"),
    )
    check(
        "ⓜ-7 NOT_FOUND_ON_PAGE × ACTION_FOUND → RECOVERABLE",
        decide("NOT_FOUND_ON_PAGE", "ACTION_FOUND") == "RECOVERABLE",
        decide("NOT_FOUND_ON_PAGE", "ACTION_FOUND"),
    )
    try:
        decide("NOT_A_CLAIM", "ACTION_FOUND")
        raised_claim = None
    except ValueError:
        raised_claim = "ValueError"
    try:
        decide("ABSENT_IN_MANUAL", "NOT_AN_AXIS")
        raised_axis = None
    except ValueError:
        raised_axis = "ValueError"
    check(
        "ⓜ-8 미지 claim·axis → ValueError (순수 오라클, D9 미적용 — MCP 도구가 아니다)",
        raised_claim == "ValueError" and raised_axis == "ValueError",
        f"claim={raised_claim or 'no-raise'} · axis={raised_axis or 'no-raise'}",
    )
    same = {c: (decide(c, "ROW_TEXT_ONLY"), decide(c, "ANCHOR_ONLY")) for c in PARSER_CLAIMS}
    check(
        "ⓜ-9 ROW_TEXT_ONLY 는 ANCHOR_ONLY 와 같은 판정 (축만 분리, 판정은 동일) · 축 5종",
        all(a == b for a, b in same.values()) and "ROW_TEXT_ONLY" in ELICE_AXES,
        f"{ {c: a for c, (a, b) in same.items()} } · ELICE_AXES={list(ELICE_AXES)}",
    )
    demoted = decide("ABSENT_IN_MANUAL", "ANCHOR_ONLY", unread_in_scope=True)
    kept = decide("ABSENT_IN_MANUAL", "ANCHOR_ONLY")
    check(
        "ⓜ-10 unread_in_scope=True 는 CONFIRMED_ABSENT 를 INCONCLUSIVE 로 강등 (D62)",
        demoted == "INCONCLUSIVE" and kept == "CONFIRMED_ABSENT",
        f"unread_in_scope=True → {demoted} · False → {kept}",
    )


def _check_n() -> None:
    store_src = (ROOT / "data" / "external" / "store.py").read_text(encoding="utf-8")
    verify_src = (ROOT / "data" / "verify_actions_absence.py").read_text(encoding="utf-8")
    net_words = ("httpx", "requests", "urllib")
    store_hits = [w for w in net_words if w in store_src]
    verify_hits = [w for w in net_words if w in verify_src]
    check(
        "ⓝ store.py·verify_actions_absence.py 네트워크 라이브러리 참조 0건(주석 포함)",
        not store_hits and not verify_hits,
        f"store.py 검출={store_hits or '없음'} · verify_actions_absence.py 검출={verify_hits or '없음'}",
    )


# ──────────────────────────────────────────── ⓟ 합성 봉투 통합 검사 (네트워크 0 · 지출 0)
#
# `decide()` 단위 오라클(ⓜ)만으로는 `control_codes() → blind_slugs → verdict` 배선이 한 번도
# 실행되지 않는다. dry-run 은 전건 `UNREAD` 라 그 경로를 지나가지 않으므로, 배선의 첫 실행이
# **1,530원 지출 이후**가 된다. 여기서는 격리된 `store.STORE_ROOT` 에 합성 봉투를 심어
# `verify()` 전 구간을 네트워크 0 으로 태운다.
#
# 픽스처는 원칙적으로 정본/후보에서 그대로 가져온 실제 문자열이다 — S100 `OCT`·`NMT` 의
# 설명/조치문, iG5A `RERR`·`ETB` 의 조치문(후보 파일 `evidence_excerpt` 원문). 문장을
# 지어내면 검사가 자기 자신을 검증하게 되므로 원칙은 지킨다.
#
# ⚠ 예외 2건은 의도적으로 합성이다 — "지어낸 문장 0건"이 아니다:
#   ① `_IG5A_SHARED_ACTION_TABLE` 의 조치문 — `EEP`·`HWT`·`NTC`·`ERR`·`COM` 은 전부
#      `_pending_review` 상 `AMBIGUOUS`(귀속 미해소)라 **정본/후보 어디에도 회수된 실제
#      문장이 없다**. rowspan 셀 정체성 판정(ⓟ-6)을 태우려면 구조만 갖춘 합성 조치문이
#      불가피하다 — 대체할 실제 문장 자체가 존재하지 않는 경우.
#   ② `_IG5A_CAUSE_TABLE` 의 설명 — 이건 다르다. `COL` 은 실제 cause 문장이 정본에
#      **있다**(`3상 입력 전원 중 1상이 결상되거나, ... 콘덴서를 교체할 시기가 되면 ...`).
#      그 실제 문장을 심으면 `교체`(`ACTION_MARKERS`)가 걸려 `is_action_text()` 가 참이
#      되고 축이 `ROW_TEXT_ONLY` 가 아니라 `ACTION_FOUND` 로 바뀐다 — 원인문이 표지어
#      하나로 조치문처럼 오인되는 C1 계열 위양성이다. 리뷰(Sprint 13 재리뷰 Important 1)가
#      지적한 대로 **이 실제 문장으로 교체하고, 그 귀결(`DISAGREE`)을 아래 ⓟ-7 에서 의도된
#      계약으로 명시 검사한다** — 안전 방향(`DISAGREE`=사람이 볼 곳)이라 은폐하지 않는다.

_S100_TRIP_TABLE = (  # 9.1 트립표 — 머리행이 `기능`/`설명` 이라 조치 열이 아니다
    "<table>"
    "<tr><th>기능</th><th>설명</th></tr>"
    "<tr><td>Over Current1</td>"
    "<td>인버터 출력 전류가 정격 전류의 200% 이상일 때 발생합니다.</td></tr>"
    "<tr><td>No Motor Trip</td>"
    "<td>인버터 운전 시 모터가 연결되지 않으면 발생합니다. Pr.31 코드를 1로 설정해야 "
    "작동합니다.</td></tr>"
    "</table>"
)
_S100_ACTION_TABLE = (  # 9.2 조치사항표 — 머리행 `조치 사항` 이 조치 열을 만든다
    "<table>"
    "<tr><th>항목</th><th>조치 사항</th></tr>"
    "<tr><td>Over Current1</td>"
    "<td>모터가 정지한 후에 운전하거나 속도 검색 기능(Cn.60)을 사용하십시오.</td></tr>"
    "</table>"
)
_IG5A_ACTION_TABLE = (  # 대조군 RERR·ETB 의 조치문 (후보 파일 `evidence_excerpt` 원문)
    "<table>"
    "<tr><th>항목</th><th>조치 사항</th></tr>"
    "<tr><td>리모트 통신 에러</td>"
    "<td>통신선 연결 커넥터에 통신 선이 올바르게 부착되어 있는지 확인하십시오.</td></tr>"
    "<tr><td>B 접점 고장 신호</td>"
    "<td>외부 고장 단자에 연결된 회로 이상 및 외부 고장의 원인을 제거합니다.</td></tr>"
    "</table>"
)
# 조치 셀이 **0행이 아니라 1행에서 시작해 5행을 span** 한다. 마지막 항목행(`로더 이상` = COM)
# 에서 앵커가 걸리면 옛 오프셋 계산은 격자 밖을 짚어 covers=0 → `or 1` → **가짜 1:1 귀속**을
# 만들었다(리뷰 C2). 셀 정체성으로 세면 covers=4 다.
# ⚠ 이 조치문 자체는 **합성이다**(위 헤더 주석 ① 참조) — 걸려 있는 5개 항목(`EEP`·`HWT`·
# `NTC`·`ERR`·`COM`) 은 전부 `AMBIGUOUS`(귀속 미해소)라 대체할 실제 회수 문장이 없다.
_IG5A_SHARED_ACTION_TABLE = (
    "<table>"
    "<tr><th>항목</th><th>조치 사항</th></tr>"
    "<tr><td>파라미터 저장 이상</td>"
    '<td rowspan="5">인버터 주변의 노이즈원을 제거하고 접지 상태를 점검하십시오.</td></tr>'
    "<tr><td>하드웨어 이상</td></tr>"
    "<tr><td>NTC 이상</td></tr>"
    "<tr><td>로더와 인버터간 통신 에러</td></tr>"
    "<tr><td>로더 이상</td></tr>"
    "</table>"
)
_IG5A_CAUSE_TABLE = (  # `COL` 실제 cause 원문(정본 error_codes.json) — 조치표가 아닌
    # 원인표라 머리행은 `설명`이지만, 문장 안의 `교체` 표지어가 `is_action_text()` 를
    # 참으로 만들어 축이 `ACTION_FOUND` 로 뒤집힌다(C1 계열 위양성, ⓟ-7 이 이걸 검사한다).
    "<table>"
    "<tr><th>항목</th><th>설명</th></tr>"
    "<tr><td>입력결상</td>"
    "<td>3상 입력 전원 중 1상이 결상되거나, 인버터 내부에 있는 평활용 콘덴서를 교체할 "
    "시기가 되면 인버터 출력을 차단합니다.</td></tr>"
    "</table>"
)


def _elice_body(tables: list[str]) -> dict:
    """Elice helpy-document-vision 응답 형태의 최소 본문 (`result.pages[0].elements`)."""
    return {
        "result": {
            "pages": [{"elements": [{"label": "table", "content": html} for html in tables]}]
        }
    }


@contextmanager
def _synthetic_read(pages: dict[tuple[str, int], list[str]]):
    """합성 봉투를 심고 `verify()` 를 한 번 돌린다. **네트워크 0 · 지출 0 · 정본 쓰기 0.**

    - `store.STORE_ROOT` 를 tmp 로 격리 (실 캐시 미접촉)
    - `_pdf_path` 를 가짜 경로로 갈아끼워 `data/raw/*.pdf` 존재에 의존하지 않게 한다
      (캐시 히트 경로는 PDF 를 열지 않는다 — `source_pdf.name` 만 쓴다)
    - `_submit_and_wait` 를 폭탄으로 갈아끼워 네트워크 호출 0회를 **실측**한다
    """
    calls = {"n": 0}

    def _boom(*_args: Any, **_kwargs: Any) -> Any:
        calls["n"] += 1
        raise AssertionError("ⓟ 에서 _submit_and_wait 는 절대 호출되면 안 된다")

    original_pdf_path = verify_mod._pdf_path
    original_submit = elice_docvision._submit_and_wait
    with _isolated_cache():
        for (slug, page), tables in pages.items():
            store.store_response(
                "elice",
                f"{slug}_p{page}",
                _elice_body(tables),
                meta={"doc_slug": slug, "page": page},
            )
        verify_mod._pdf_path = lambda slug: Path(f"synthetic_{slug}.pdf")
        elice_docvision._submit_and_wait = _boom
        try:
            yield verify_mod.verify(allow_purchase=False, measure_page_chars=False), calls
        finally:
            verify_mod._pdf_path = original_pdf_path
            elice_docvision._submit_and_wait = original_submit


def _row(result: dict, model: str, code: str) -> dict:
    return next(
        (r for r in result["rows"] if r["model"] == model and r["code"] == code), {}
    )


def _control_row(result: dict, slug: str, code: str) -> dict:
    report = next((r for r in result["control"] if r["doc_slug"] == slug), {"rows": []})
    return next((r for r in report["rows"] if r["code"] == code), {})


def _control(result: dict, slug: str) -> dict:
    return next((r for r in result["control"] if r["doc_slug"] == slug), {})


def _check_p() -> None:
    # ── 픽스처 A: S100 트립표만. 조치표가 없으니 판독기는 조치문을 **찾지 못한 것**이 맞다.
    with _synthetic_read({("s100-manual", 416): [_S100_TRIP_TABLE]}) as (result_a, calls_a):
        s100_a = _control(result_a, "s100-manual")
        oct_a = _control_row(result_a, "s100-manual", "OCT")
        nmt_a = _row(result_a, "S100", "NMT")
        check(
            "ⓟ-1 트립표만 심으면 대조군이 자명 충족되지 않는다 → state=blind (READER_BLIND 발화 가능)",
            s100_a.get("state") == "blind"
            and s100_a.get("action_verified") == 0
            and s100_a.get("action_found") == 0
            and s100_a.get("row_text_only", 0) > 0
            and oct_a.get("axis") == "ROW_TEXT_ONLY",
            f"state={s100_a.get('state')} · 대조통과={s100_a.get('action_verified')} · "
            f"ACTION_FOUND={s100_a.get('action_found')} · "
            f"ROW_TEXT_ONLY={s100_a.get('row_text_only')} · OCT축={oct_a.get('axis')} "
            f"(발견 p={oct_a.get('found_page')})",
        )
        check(
            "ⓟ-2 결측 코드의 자기 설명 셀은 조치문이 아니다 — S100 NMT 가 DISAGREE 로 가지 않는다",
            nmt_a.get("elice_axis") == "ROW_TEXT_ONLY"
            and nmt_a.get("verdict") == "INCONCLUSIVE"
            and nmt_a.get("reader_blind") is True
            and sum(1 for r in result_a["rows"] if r["verdict"] == "DISAGREE") == 0,
            f"NMT 축={nmt_a.get('elice_axis')} 판정={nmt_a.get('verdict')} "
            f"blind={nmt_a.get('reader_blind')} · 전체 DISAGREE="
            f"{sum(1 for r in result_a['rows'] if r['verdict'] == 'DISAGREE')}건 · "
            f"근거={nmt_a.get('evidence', '')[:40]!r}",
        )
        check(
            "ⓟ-3 픽스처 A: 네트워크 0회 · 판독은 캐시에서만",
            calls_a["n"] == 0 and result_a["pages_read"] == 1,
            f"_submit_and_wait {calls_a['n']}회 · pages_read={result_a['pages_read']}",
        )

    # ── 픽스처 B: 트립표 + 조치표(+ iG5A 트러블슈팅본). 여기서 생존 축이 **진짜로** 선다.
    fixture_b = {
        ("s100-manual", 416): [_S100_TRIP_TABLE],
        ("s100-manual", 420): [_S100_ACTION_TABLE],
        ("ig5a-troubleshooting", 27): [_IG5A_ACTION_TABLE],
        ("ig5a-troubleshooting", 28): [_IG5A_SHARED_ACTION_TABLE],
        ("ig5a-troubleshooting", 29): [_IG5A_CAUSE_TABLE],
    }
    with _synthetic_read(fixture_b) as (result_b, calls_b):
        s100_b = _control(result_b, "s100-manual")
        oct_b = _control_row(result_b, "s100-manual", "OCT")
        nmt_b = _row(result_b, "S100", "NMT")
        com_b = _row(result_b, "iG5A", "COM")
        col_b = _row(result_b, "iG5A", "COL")
        ts_b = _control(result_b, "ig5a-troubleshooting")

        check(
            "ⓟ-4 생존 축은 정본 actions 문장 대조다 — OCT 가 조치표(p.420)에서 대조 통과",
            s100_b.get("state") == "ok"
            and s100_b.get("action_verified", 0) >= 1
            and oct_b.get("axis") == "ACTION_FOUND"
            and oct_b.get("found_page") == 420
            and oct_b.get("action_text_matched") is True,
            f"state={s100_b.get('state')} · 대조통과={s100_b.get('action_verified')} · "
            f"OCT 축={oct_b.get('axis')} 발견p={oct_b.get('found_page')} "
            f"대조={oct_b.get('action_match_kind')!r} 근거={oct_b.get('evidence', '')[:36]!r}",
        )
        check(
            "ⓟ-5 생존 확인 후에는 결측 코드가 진짜 판정을 받는다 — S100 NMT → CONFIRMED_ABSENT",
            nmt_b.get("elice_axis") == "ROW_TEXT_ONLY"
            and nmt_b.get("verdict") == "CONFIRMED_ABSENT"
            and nmt_b.get("reader_blind") is False
            and nmt_b.get("unread_in_scope") is False,
            f"NMT 축={nmt_b.get('elice_axis')} 판정={nmt_b.get('verdict')} "
            f"blind={nmt_b.get('reader_blind')} unread={nmt_b.get('unread_in_scope')}",
        )
        check(
            "ⓟ-6 rowspan 귀속을 셀 정체성으로 센다 — iG5A COM 은 가짜 1:1 이 아니라 STILL_AMBIGUOUS",
            com_b.get("parser_claim") == "AMBIGUOUS"
            and com_b.get("elice_axis") == "ACTION_FOUND"
            and com_b.get("covers_item_rows", 0) >= 2
            and com_b.get("rowspan_resolved") is False
            and com_b.get("verdict") == "STILL_AMBIGUOUS",
            f"claim={com_b.get('parser_claim')} 축={com_b.get('elice_axis')} "
            f"rowspan={com_b.get('rowspan')} covers={com_b.get('covers_item_rows')} "
            f"resolved={com_b.get('rowspan_resolved')} 판정={com_b.get('verdict')}",
        )
        check(
            "ⓟ-7 원인문의 표지어(`교체`)가 조치문으로 오인된다 — iG5A COL 실제 cause → "
            "ACTION_FOUND·DISAGREE (안전 방향, C1 계열 위양성을 은폐하지 않고 계약으로 검사)",
            col_b.get("elice_axis") == "ACTION_FOUND"
            and col_b.get("verdict_before_blind_demotion") == "DISAGREE"
            and col_b.get("verdict") == "DISAGREE"
            # 미판독(ig5a-manual)은 여전히 참이다 — 단지 이 코드의 verdict 가
            # CONFIRMED_ABSENT 가 아니라서(위 DISAGREE) D62 강등이 여기서는 발동하지
            # 않을 뿐이다. `unread_in_scope` 가 CONFIRMED_ABSENT 를 INCONCLUSIVE 로
            # 강등하는 그 경로 자체는 순수 오라클 ⓜ-10 이 이미 계약으로 검사한다.
            and col_b.get("unread_in_scope") is True
            and "ig5a-manual" in (col_b.get("unread_targets") or []),
            f"축={col_b.get('elice_axis')} 미판독={col_b.get('unread_targets')} "
            f"강등전={col_b.get('verdict_before_blind_demotion')} 판정={col_b.get('verdict')}",
        )
        check(
            "ⓟ-8 픽스처 B: 네트워크 0회 · 5p 캐시 판독 · ig5a-troubleshooting 대조군도 생존",
            calls_b["n"] == 0
            and result_b["pages_read"] == 5
            and ts_b.get("action_verified", 0) >= 1
            and ts_b.get("state") == "ok",
            f"_submit_and_wait {calls_b['n']}회 · pages_read={result_b['pages_read']} · "
            f"ig5a-troubleshooting 대조통과={ts_b.get('action_verified')}"
            f"/{ts_b.get('controls_total')} state={ts_b.get('state')}",
        )

    # ── 대조 함수 자체의 양성/음성 축 (P30) — 자명 충족이 사라졌는지 직접 잰다.
    desc = "인버터 출력 전류가 정격 전류의 200% 이상일 때 발생합니다."
    action = "모터가 정지한 후에 운전하거나 속도 검색 기능(Cn.60)을 사용하십시오."
    neg = action_text_match(desc, [action])
    pos = action_text_match(action, [action])
    check(
        "ⓟ-9 action_text_match: 설명 셀은 불일치 · 조치문 원문은 일치 (음성·양성 양축)",
        neg[0] is False and pos[0] is True and pos[1] == "full",
        f"설명셀={neg} · 조치문={pos}",
    )


def run_checks() -> list[tuple[str, bool, str]]:
    """전체 검사를 실행하고 새 결과 목록을 돌려준다. 뮤턴트 실증을 위해 반복 호출 가능하다."""
    results.clear()
    before = {p.name: _sha256(p) for p in IMMUTABLE_INPUTS if p.exists()}

    _check_a()
    _check_b()
    with _isolated_cache() as tmp_cache:
        _check_c(tmp_cache)
        _check_d()
        _check_e()
        _check_f(tmp_cache)
        _check_k_actual(tmp_cache)
    _check_g()
    _check_h()
    _check_i()
    _check_j()
    _check_k_static()
    _check_l()
    _check_m()
    _check_n()
    _check_p()

    after = {p.name: _sha256(p) for p in IMMUTABLE_INPUTS if p.exists()}
    check(
        "ⓞ 정본 불변 (D99) — error_codes.json · candidate 후보 파일 sha256 실행 전후 동일",
        bool(before) and after == before,
        f"대상={list(before)} · sha256 동일={after == before}",
    )
    return list(results)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    print("외부 응답 원본 보관·소비자 계약 검증 (D103·D105·D60·D39·D62·D99, P30) — 네트워크·지출 0\n")
    outcomes = run_checks()

    width = max(len(n) for n, _, _ in outcomes)
    print("─" * (width + 52))
    for name, ok, detail in outcomes:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 52))

    failed = [n for n, ok, _ in outcomes if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(
        f"\n통과 ({len(outcomes)}건) — D103·D105·D60·D39·D62·D99 준수. "
        "실 Elice·법제처 호출은 하지 않는다 — 캐시는 매 검사마다 tmp 로 격리했다."
    )


if __name__ == "__main__":
    main()
