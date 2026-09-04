# -*- coding: utf-8 -*-
"""dense 스코어러 — `mcp_server/rag.py` 의 `DenseScorer` 계약 구현체 (D47·D117).

`rag.py` 는 어떤 임베딩도 고르지 않는다는 원칙을 지킨다(그 모듈 독스트링 참고) — 그래서
실제 임베딩 모델(Qwen3-Embedding-4B, NVIDIA API)을 고르는 이 배선은 별도 모듈에 둔다.
`mcp_server/tools/rag_search_manual.py` 가 이 모듈의 `score` 를 `search(..., dense=score)`
로 주입한다.

## 코퍼스 임베딩은 Postgres 에서, 질의 임베딩은 매 호출마다 API로

- **코퍼스(passage) 임베딩**은 `scripts/migrate_vectors.py` 가 미리 계산해
  `manual_chunks.embedding` 에 저장해 둔 것을 읽기만 한다 — 이 모듈은 임베딩을 계산하지 않는다.
- **질의(query) 임베딩**은 검색할 때마다 필요해서 매번 NVIDIA API 를 부른다(캐시는
  `data/external/nvidia_embed.py` 가 처리 — 같은 질의를 반복하면 네트워크가 안 탄다).

## 실패 방식

`NVIDIA_API_KEY`·`NVIDIA_EMBED_MODEL` 미설정이거나 API 호출이 실패하면 **예외를 던지지
않는다** — `rag.py::search()` 의 `dense=None` 과 동등하게(키워드 점수만) 동작하도록
`None` 을 반환한다. D40 이 말하는 "조용한 폴백 금지"는 **거짓 응답을 진짜처럼 위장**하는
것을 막는 규칙이지, 이 경우와는 다르다 — dense 미활성은 D47 이 이미 정의해 둔 정상
상태(`dense=None`)이고, 여기서 예외를 던지면 임베딩 설정 하나 때문에 매뉴얼 검색
전체(키워드만으로도 동작 가능한 기능)가 죽는다. 실패는 warning 으로 로그만 남긴다.
"""

from __future__ import annotations

import json
import logging
import os

from data.external.nvidia_embed import EMBEDDING_DIM, NvidiaEmbedError, embed_text
from mcp_server.db import read_only

logger = logging.getLogger(__name__)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _fetch_corpus_embeddings(model: str) -> dict[str, list[float]]:
    """`manual_chunks` 에서 이 기종의 임베딩을 chunk_id → 벡터로 읽는다.

    `embedding::text` 로 캐스팅해 pgvector 어댑터 등록 없이 파싱한다 — pgvector 텍스트
    표현이 `[0.1,0.2,...]` 라 `json.loads` 로 바로 읽힌다(psycopg 커넥션에 커스텀
    CompatCursor/row_factory 가 이미 얹혀 있어, 별도 어댑터를 등록하면 그 조합과 상호작용을
    새로 검증해야 한다 — 이 편이 더 단순하고 안전하다).
    """
    with read_only() as con:
        rows = con.execute(
            "SELECT chunk_id, embedding::text AS embedding_text FROM manual_chunks"
            " WHERE model = ? AND embedding IS NOT NULL",
            (model,),
        ).fetchall()
    return {r["chunk_id"]: json.loads(r["embedding_text"]) for r in rows}


def score(query: str, chunks: list[dict]) -> list[float]:
    """`DenseScorer` 계약: chunks 와 같은 길이·같은 순서의 점수열을 돌려준다.

    실패 시 전부 0.0 — `rag.py::_normalize` 가 전부 0인 벡터를 그대로 통과시키므로
    최종 순위는 키워드 점수만으로 결정된다(= dense=None 과 동일한 결과).
    """
    if not chunks:
        return []

    zeros = [0.0] * len(chunks)

    if not (os.environ.get("NVIDIA_API_KEY") or "").strip():
        return zeros  # 미설정 — 조용히 키워드 전용으로 (D47 이 정의한 정상 상태)

    model = chunks[0].get("model")
    try:
        query_vec = embed_text(query, input_type="query", allow_purchase=True)
        corpus = _fetch_corpus_embeddings(model)
    except NvidiaEmbedError as e:
        logger.warning("dense 스코어러 비활성 — 질의 임베딩 실패: %s", e)
        return zeros
    except Exception as e:  # noqa: BLE001 — DB 오류 등도 dense 만 죽이고 키워드는 살린다
        logger.warning("dense 스코어러 비활성 — 코퍼스 임베딩 조회 실패: %s", e)
        return zeros

    if len(query_vec) != EMBEDDING_DIM:
        logger.warning(
            "dense 스코어러 비활성 — 질의 벡터 차원 불일치(%d != %d, 모델 설정 확인 필요)",
            len(query_vec), EMBEDDING_DIM,
        )
        return zeros

    return [
        _cosine(query_vec, corpus[c["chunk_id"]]) if c.get("chunk_id") in corpus else 0.0
        for c in chunks
    ]
