# -*- coding: utf-8 -*-
"""MQ-1308 — Elice 클라이언트 유닛테스트 이식. **네트워크를 절대 타지 않는다.**

원본: `../InsuQ/ai-engine/tests/ingest/test_elice_docvision.py` (134줄). 그 서두를 계승한다:

이 모듈은 **호출당 45원이 나가는** 유료 API 를 다룬다. 그래서 테스트의 최우선 목적은
"기능이 되는가"가 아니라 **"실수로 돈이 나가지 않는가"** 다.

## 원본과 달라진 두 지점

1. `extract_page(..., cache_dir=...)` 파라미터가 사라졌다 — 캐시 위치는 이제
   `data/external/store.py` 의 `STORE_ROOT` 가 소유한다. 그래서 이 파일은
   `monkeypatch.setattr(store, "STORE_ROOT", tmp_path)` 로 매 테스트를 격리한다
   (autouse fixture `_isolated_store`). 이걸 빠뜨리면 실 캐시 디렉터리를 오염시키고,
   최악의 경우 캐시 미스 → 실제 구매 경로로 간다.
2. 원본 슬러그 `"sf실손2607"` 은 `store.KEY_RE` (ASCII 전용)를 통과하지 못한다.
   manifest id(`s100-manual` 등)로 바꿨다.

추가로 이 파일은 `_submit_and_wait` 를 **모든** 테스트에서 폭파 스텁으로 monkeypatch 한다
(autouse fixture `_no_network`) — 이 파일에는 실 구매 경로를 실행하는 테스트가 하나도
없어야 하므로, 개별 테스트가 patch 를 깜빡해도 네트워크 0회가 구조적으로 보장된다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data.external import elice_docvision, store  # noqa: E402
from data.external.elice_docvision import (  # noqa: E402
    DEFAULT_BASE,
    PRICE_PER_PAGE_WON,
    EliceError,
    PageExtraction,
    extract_page,
    normalize_base_url,
)


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """캐시 위치를 `tmp_path` 로 격리한다 — 실 `data/raw/external/elice/` 오염 방지."""
    monkeypatch.setattr(store, "STORE_ROOT", tmp_path)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """이 파일 전체에서 네트워크 0회를 구조적으로 강제하는 폭파 스텁."""

    def _boom(*args, **kwargs):
        raise AssertionError("이 파일의 테스트는 네트워크(_submit_and_wait)를 타면 안 된다")

    monkeypatch.setattr(elice_docvision, "_submit_and_wait", _boom)


def _seed_cache(doc_slug: str, page: int, body: dict) -> None:
    """`store.py` 를 경유해 캐시 히트를 만든다 (봉투는 store 가 조립한다)."""
    key = elice_docvision._cache_key(doc_slug, page)
    store.store_response("elice", key, body, meta={"doc_slug": doc_slug, "page": page})


# --- URL 정규화 ---------------------------------------------------------------
# 실패 이력(InsuQ, 2026-08-10): 규격서에 URL·모델 ID·콘솔 UUID 세 값이 섞여 있어 3회 실패했다.


def test_normalize_passes_full_url_through():
    url = "https://mlapi.run/3886be6c-3e1b-4c4b-be28-0f7cafbee0ef"
    assert normalize_base_url(url) == url


def test_normalize_strips_trailing_slash():
    assert normalize_base_url("https://mlapi.run/abc/") == "https://mlapi.run/abc"


def test_normalize_prepends_host_for_bare_api_id():
    assert normalize_base_url("3886be6c-3e1b-4c4b-be28-0f7cafbee0ef") == (
        f"{DEFAULT_BASE}/3886be6c-3e1b-4c4b-be28-0f7cafbee0ef"
    )


def test_normalize_rejects_model_id_shaped_value():
    """모델 ID 를 URL 자리에 넣는 것이 실제로 겪은 1차 실패다 — 예외로 잡는다."""
    with pytest.raises(EliceError, match="모델 ID"):
        normalize_base_url("eliceai/helpy-document-vision")


def test_normalize_rejects_empty():
    with pytest.raises(EliceError):
        normalize_base_url("")


# --- 지출 가드 (이 파일의 존재 이유) -------------------------------------------


def test_cache_miss_without_permission_raises_instead_of_buying(tmp_path):
    """`allow_purchase` 를 명시하지 않으면 **네트워크를 타지 않고 즉시 예외**."""
    with pytest.raises(EliceError, match="캐시에 없다"):
        extract_page(tmp_path / "any.pdf", 50, doc_slug="s100-manual", allow_purchase=False)


def test_cache_hit_does_not_touch_network(tmp_path):
    """캐시가 있으면 구매 허용 여부와 무관하게 네트워크를 안 탄다 — 재구매 방지.

    `_no_network` autouse fixture 가 이미 `_submit_and_wait` 를 폭파 스텁으로 바꿔 두었다 —
    `allow_purchase=True` 로 불러도 캐시 히트라 그 스텁까지 도달하지 않아야 통과한다.
    """
    payload = {
        "result": {
            "pages": [
                {
                    "elements": [
                        {"label": "table", "content": "<table><tr><td>a</td></tr></table>"},
                        {"label": "text", "content": "본문"},
                    ]
                }
            ]
        }
    }
    _seed_cache("s100-manual", 50, payload)

    result = extract_page(
        tmp_path / "any.pdf", 50, doc_slug="s100-manual", allow_purchase=True
    )
    assert result.from_cache is True
    assert len(result.elements) == 2


def test_missing_api_key_raises_before_spending(tmp_path, monkeypatch):
    monkeypatch.setenv("ELICE_DOCVISION_URL", "https://mlapi.run/abc")
    monkeypatch.delenv("ELICE_API_KEY", raising=False)
    with pytest.raises(EliceError, match="ELICE_API_KEY"):
        extract_page(tmp_path / "any.pdf", 50, doc_slug="s100-manual", allow_purchase=True)


def test_price_constant_is_explicit():
    """가격이 코드에 상수로 박혀 있어야 비용 산정이 리포트와 어긋나지 않는다."""
    assert PRICE_PER_PAGE_WON == 45


# --- 결과 파싱 -----------------------------------------------------------------


def _extraction(elements) -> PageExtraction:
    return PageExtraction(source_pdf="x.pdf", page=50, elements=elements, from_cache=True)


def test_tables_html_selects_only_table_elements():
    result = _extraction(
        [
            {"label": "table", "content": "<table>T1</table>"},
            {"label": "text", "content": "본문"},
            {"label": "table", "content": "<table>T2</table>"},
        ]
    )
    assert result.tables_html == ["<table>T1</table>", "<table>T2</table>"]


def test_text_excludes_tables():
    """표는 별도 청크가 된다(`rag.md`) — 본문 텍스트에 섞이면 항이 오염된다."""
    result = _extraction(
        [
            {"label": "paragraph_title", "content": "제1조 (보장종목)"},
            {"label": "table", "content": "<table>표</table>"},
            {"label": "text", "content": "① 회사는…"},
        ]
    )
    assert "표" not in result.text
    assert "제1조 (보장종목)" in result.text
    assert "① 회사는…" in result.text


def test_text_prefers_compact_content():
    result = _extraction([{"label": "text", "content": "긴 것", "content_compact": "짧은 것"}])
    assert result.text == "짧은 것"


def test_empty_result_yields_no_elements(tmp_path):
    _seed_cache("s100-manual", 1, {"result": {"pages": []}})
    result = extract_page(
        tmp_path / "x.pdf", 1, doc_slug="s100-manual", allow_purchase=False
    )
    assert result.elements == []
