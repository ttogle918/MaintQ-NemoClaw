# -*- coding: utf-8 -*-
"""rag_search_manual — 매뉴얼 본문 검색 (docs/04_MCP_TOOLS.md §2).

절차·배경 등 **서술형** 정보만 담당한다. 에러코드 정의는 `lookup_error_code` 다 (D1).

이 파일은 **계약 어댑터**다 — 검색 알고리즘은 `mcp_server/rag.py` (D47·D48) 에 있고,
여기서는 입력 검증 · 계약 형태로의 변환 · status 매핑만 한다.

계약에서 특히 조심할 것:
  - 출력 청크는 `text`/`page`/`section` **3키뿐**. `rag.py` 가 내부적으로 붙이는 `score`·
    `chunk_id` 등은 여기서 **떨어낸다** (04 §2 계약을 임의로 넓히지 않는다).
  - `text` 를 절단하지 않는다 (D53). 길이 상한은 청킹 단계에 이미 있다.
  - `page` 를 가공하지 않는다 (D26). 인용률 판정이 이 값을 traces 와 대조한다.
  - 인덱스 미구축은 `empty` 가 아니라 `error` 다 — 아래 참조.
"""

from __future__ import annotations

from .. import dense_scorer
from ..rag import DEFAULT_TOP_K, MODELS, IndexNotBuilt, search

DESCRIPTION = (
    "매뉴얼 본문에서 점검 절차, 배선, 설치 조건 등 서술형 정보를 검색한다. "
    "에러코드 정의 자체는 lookup_error_code를 사용할 것. model 필터 필수. "
    "결과가 없으면 empty를 반환하며, 이때 절차를 지어내지 말고 "
    "'매뉴얼에서 해당 절차를 찾지 못했다'고 말할 것."
)

# 계약(04 §2)이 정한 청크 키. rag.py 가 무엇을 더 붙이든 여기서 이 3개만 통과시킨다.
_CHUNK_KEYS = ("text", "page", "section")


def rag_search_manual(model: str, query: str, top_k: int = DEFAULT_TOP_K) -> dict:
    if model not in MODELS:
        return {
            "status": "error",
            "reason": "invalid_model",
            "message": f"model 은 {'|'.join(MODELS)} 이어야 합니다: {model!r}",
        }
    if not query or not query.strip():
        return {
            "status": "error",
            "reason": "query_required",
            "message": "query 는 필수입니다",
        }

    try:
        hits = search(model=model, query=query, top_k=top_k, dense=dense_scorer.score)
    except IndexNotBuilt as e:
        # empty 로 주면 "매뉴얼에 그런 내용이 없다"는 신호가 되어 에이전트가 절차를
        # 지어낼 여지가 생긴다. 미구축은 미구축이라고 정직하게 실패한다 (D9, 09_RUNTIME §3).
        return {
            "status": "error",
            "reason": "index_not_built",
            "message": (
                f"매뉴얼 검색 인덱스가 준비되지 않았습니다 ({e}). "
                "uv run python data/chunk_manual.py 를 먼저 실행하세요."
            ),
        }
    except Exception as e:  # noqa: BLE001 — 예외를 status 로 바꿔 반환 (D9)
        return {"status": "error", "reason": "search_failed", "message": str(e)}

    if not hits:
        # 매칭 0건 — 인덱스는 정상이고 정말로 못 찾은 것 (S2 의 empty 와 같은 성격)
        return {"status": "empty", "chunks": []}

    return {
        "status": "ok",
        "chunks": [{k: h.get(k) for k in _CHUNK_KEYS} for h in hits],
    }
