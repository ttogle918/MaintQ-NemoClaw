"""Elice helpy-document-vision 클라이언트 — triage 가 고른 페이지만 유료 재추출 (D105).

**페이지당 45원이다.** 전수 파싱 경로가 아니라, 파서가 못 읽거나 잘못 읽은 페이지만 다시
읽는 **독립 2차 판독기**다. 정답지로 취급하지 않는다(D105) — 정본 반영은 D99 게이트를 거친다.

## 이 모듈이 지키는 것

1. **지출 가드(D105) — 순서가 계약이다.**
   ① 캐시 확인이 **가장 먼저** — `allow_purchase` 값과 무관하게 캐시가 있으면 네트워크 0.
   ② 캐시 미스인데 `allow_purchase=False` 면 예외 — 실수로 돈이 나가지 않게 호출부가
      **명시적으로** 구매를 허용해야 한다.
   ③ `ELICE_DOCVISION_URL` 정규화 + `ELICE_API_KEY` 부재 확인을 **지출(네트워크 제출) 전에** 끝낸다.
   ④ 단일 페이지만 잘라 제출 → 폴링 → 성공 payload 를 `store_response` 로 기록(D103).
2. **원본 보관은 `data/external/store.py` 한 곳을 경유한다(D103).** 캐시 위치·형식을
   이 모듈이 소유하지 않는다 — `load_response("elice", key)` / `store_response("elice", key, …)`.
3. **토큰·`Authorization` 헤더를 로그·예외 메시지에 싣지 않는다.**
4. **URL 정규화** — 규격서에 URL·모델 ID·콘솔 UUID 세 값이 섞여 있어 InsuQ 에서 실제로 3회
   실패한 이력이 있다. `http` 로 시작하지 않으면 `https://mlapi.run/` 를 붙인다.
5. **네트워크는 `_submit_and_wait` 밖으로 나가지 않는다** — `httpx` 는 그 함수 안에서만
   지연 import 한다. 캐시 경로만 타는 호출은 `httpx` 없이도 동작해야 한다.
6. **단일 페이지 임시 PDF 는 `tempfile.mkdtemp()` 로 store 밖에** 쓴다 — 캐시 디렉터리에
   매뉴얼 조각을 남기지 않는다.

## 사용

    python -m data.external.elice_docvision --pdf <원본.pdf> --pages 412 413 --doc-slug s100-manual
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data.external.store import store_response, load_response  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_BASE = "https://mlapi.run"
SUBMIT_PATH = "/v1/documents"
JOB_PATH = "/v1/jobs"
POLL_INTERVAL_S = 5.0
POLL_TIMEOUT_S = 300.0
SUBMIT_TIMEOUT_S = 120.0
PRICE_PER_PAGE_WON = 45
# 문서 AI 가 표를 HTML 로 주게 한다 — 뭉개진 표를 되살리는 게 이 폴백의 주 목적이다.
DEFAULT_CONFIGS = {"do_image_description": False, "do_chart_conversion": True}


class EliceError(RuntimeError):
    """API 호출 실패. 개별 페이지 실패가 배치를 죽이지 않도록 호출부가 잡는다."""


@dataclass(frozen=True)
class PageExtraction:
    """한 페이지 재추출 결과."""

    source_pdf: str
    page: int  # 원본 PDF 의 1-based 물리 페이지 (D26)
    elements: list[dict[str, Any]]
    from_cache: bool

    @property
    def tables_html(self) -> list[str]:
        return [str(e.get("content") or "") for e in self.elements if e.get("label") == "table"]

    @property
    def text(self) -> str:
        parts = []
        for element in self.elements:
            if element.get("label") == "table":
                continue
            content = element.get("content_compact") or element.get("content") or ""
            if content:
                parts.append(str(content))
        return "\n".join(parts)


def normalize_base_url(raw: str) -> str:
    """`http` 로 시작하지 않으면 api-id 로 보고 호스트를 붙인다.

    실패 이력(InsuQ, 2026-08-10): 모델 ID(`eliceai/helpy-document-vision`)를 URL 자리에 넣어
    `MissingSchema`, 콘솔 UUID 를 api-id 로 착각해 `404 api_not_found`.
    """
    value = (raw or "").strip().rstrip("/")
    if not value:
        raise EliceError("ELICE_DOCVISION_URL 이 비어 있다")
    if value.startswith(("http://", "https://")):
        return value
    if "/" in value:
        raise EliceError(
            f"ELICE_DOCVISION_URL 이 모델 ID 처럼 보인다({value!r}). "
            f"api-id(UUID) 또는 완전 URL({DEFAULT_BASE}/<api-id>) 을 넣어라."
        )
    return f"{DEFAULT_BASE}/{value}"


def _cache_key(doc_slug: str, page: int) -> str:
    """캐시(=보관) key. `store.py` 의 `KEY_RE` 를 만족해야 하므로 슬러그는 ASCII 여야 한다
    (manifest `id`: `s100-manual`·`ig5a-manual`·`ig5a-troubleshooting`)."""
    return f"{doc_slug}_p{page}"


def _single_page_pdf(source_pdf: Path, page: int, out_path: Path) -> Path:
    """원본에서 한 페이지만 잘라낸 PDF. **페이지 단위로 사기 때문에** 통째로 올리지 않는다."""
    import pypdfium2 as pdfium  # noqa: PLC0415

    src = pdfium.PdfDocument(str(source_pdf))
    dst = pdfium.PdfDocument.new()
    dst.import_pages(src, [page - 1])
    dst.save(str(out_path))
    dst.close()
    src.close()
    return out_path


def _submit_and_wait(pdf_path: Path, base: str, key: str) -> dict[str, Any]:
    """실제 유료 호출. **이 함수 밖으로 네트워크가 나가지 않는다.**"""
    import httpx  # noqa: PLC0415 — 캐시 경로는 httpx 없이도 동작해야 한다

    headers = {"Authorization": f"Bearer {key}"}
    try:
        with pdf_path.open("rb") as handle:
            response = httpx.post(
                f"{base}{SUBMIT_PATH}",
                headers=headers,
                files={"document": (pdf_path.name, handle, "application/pdf")},
                data={"configs": json.dumps(DEFAULT_CONFIGS)},
                timeout=SUBMIT_TIMEOUT_S,
            )
    except httpx.HTTPError as exc:
        raise EliceError(f"제출 실패: {type(exc).__name__}") from exc

    if response.status_code >= 400:
        raise EliceError(f"제출 거부 {response.status_code}: {response.text[:200]}")

    job_id = response.json().get("job_id")
    if not job_id:
        raise EliceError(f"job_id 없음: {response.text[:200]}")
    logger.info("제출 완료 job_id=%s", job_id)

    started = time.time()
    while time.time() - started < POLL_TIMEOUT_S:
        time.sleep(POLL_INTERVAL_S)
        try:
            payload = httpx.get(f"{base}{JOB_PATH}/{job_id}", headers=headers, timeout=60).json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EliceError(f"폴링 실패: {type(exc).__name__}") from exc
        status = payload.get("status")
        if status == "succeeded":
            logger.info("완료 (%.0f초)", time.time() - started)
            return payload
        # 규격의 종료 상태는 "failure" 다("failed" 아님 — 오타로 무한 폴링에 빠지지 않게 고정).
        if status in {"failure", "failed", "cancelled"}:
            raise EliceError(f"작업 실패 status={status}: {str(payload)[:200]}")
    raise EliceError(f"타임아웃({POLL_TIMEOUT_S:.0f}초)")


def extract_page(
    source_pdf: Path,
    page: int,
    *,
    doc_slug: str,
    allow_purchase: bool = False,
) -> PageExtraction:
    """한 페이지를 재추출한다. **캐시에 있으면 `allow_purchase` 와 무관하게 네트워크를 타지 않는다.**

    `allow_purchase=False` 면 캐시 미스 시 예외를 던진다 — 실수로 돈이 나가지 않게
    호출부가 **명시적으로** 구매를 허용해야 한다.
    """
    key = _cache_key(doc_slug, page)

    # ① 캐시 확인 — 항상 가장 먼저, allow_purchase 와 무관.
    cached = load_response("elice", key)
    if cached is not None:
        logger.info("캐시 사용 p%d (%s)", page, key)
        return PageExtraction(
            source_pdf=source_pdf.name,
            page=page,
            elements=_elements_of(cached),
            from_cache=True,
        )

    # ② 캐시 미스인데 구매 미허용 — 네트워크 0.
    if not allow_purchase:
        raise EliceError(
            f"캐시에 없다({key}). 구매하려면 allow_purchase=True 로 호출하라 "
            f"(페이지당 {PRICE_PER_PAGE_WON}원)."
        )

    # ③ URL 정규화 + 자격증명 확인 — 지출(네트워크 제출) 전에 끝낸다.
    base = normalize_base_url(os.environ.get("ELICE_DOCVISION_URL", ""))
    api_key = os.environ.get("ELICE_API_KEY", "")
    if not api_key:
        raise EliceError("ELICE_API_KEY 가 없다")

    # ④ 단일 페이지 분할 → 제출 → 폴링. 임시 PDF 는 store 밖(tempfile.mkdtemp)에 둔다.
    tmp_dir = Path(tempfile.mkdtemp(prefix="elice_docvision_"))
    tmp_pdf = tmp_dir / f"_tmp_{doc_slug}_p{page}.pdf"
    try:
        _single_page_pdf(source_pdf, page, tmp_pdf)
        payload = _submit_and_wait(tmp_pdf, base, api_key)
    finally:
        tmp_pdf.unlink(missing_ok=True)
        try:
            tmp_dir.rmdir()
        except OSError:
            pass

    # ⑤ 원본 보관 (D103) — 저장은 store.py 한 곳만 경유한다.
    store_response(
        "elice",
        key,
        payload,
        meta={
            "source_pdf": source_pdf.name,
            "page": page,
            "doc_slug": doc_slug,
            "price_won": PRICE_PER_PAGE_WON,
        },
    )
    logger.info("구매 완료 %s (%d원 지출)", key, PRICE_PER_PAGE_WON)
    return PageExtraction(
        source_pdf=source_pdf.name, page=page, elements=_elements_of(payload), from_cache=False
    )


def _elements_of(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """응답에서 첫 페이지의 요소 목록. **봉투(store 의 `{"body": ...}`)와 생응답 둘 다 수용한다**
    — 캐시 히트 경로는 봉투를, 구매 직후 경로는 생응답을 넘긴다. 한 페이지만 올리므로 `pages[0]`."""
    body = payload.get("body", payload) if isinstance(payload, dict) else payload
    if not isinstance(body, dict):
        return []
    pages = (body.get("result") or {}).get("pages") or []
    if not pages:
        return []
    return pages[0].get("elements") or []


def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Elice 문서 AI 로 지정 페이지만 재추출")
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--pages", type=int, nargs="+", required=True)
    parser.add_argument("--doc-slug", required=True)
    parser.add_argument(
        "--buy",
        action="store_true",
        help=f"캐시 미스 시 실제 구매를 허용한다 (페이지당 {PRICE_PER_PAGE_WON}원)",
    )
    args = parser.parse_args()

    spent = 0
    for page in args.pages:
        try:
            result = extract_page(
                args.pdf, page, doc_slug=args.doc_slug, allow_purchase=args.buy
            )
        except EliceError as exc:
            logger.warning("p%d 실패: %s", page, exc)  # 개별 실패로 배치를 죽이지 않는다
            continue
        if not result.from_cache:
            spent += PRICE_PER_PAGE_WON
        print(
            f"p{page}: 요소 {len(result.elements)} · 표 {len(result.tables_html)} "
            f"· {'캐시' if result.from_cache else '구매'}"
        )
    print(f"이번 실행 지출: {spent}원")


if __name__ == "__main__":
    main()
