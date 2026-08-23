# -*- coding: utf-8 -*-
"""NVIDIA API 임베딩 클라이언트 — Qwen3-Embedding (D117).

**로컬 캐시, git 미추적.** `data/external/store.py`(D103)를 쓰지 않는다 — 그건 저빈도·
사람이 감사할 가치가 있는 응답(법령 조문·Elice 판독)을 git 이력으로 남기는 용도다. 여기서
다루는 건 매뉴얼 청크 1,000여 건의 기계적 임베딩 벡터라 성격이 다르다 — `backend/agent/
llm_cache.py`(D104)와 같은 부류: **재현성 있는 결정론적 캐시**(같은 모델·같은 텍스트 =
같은 벡터)이지 감사 대상 원본이 아니다. 저장은 `data/cache/embeddings/<key>.json` 이고
언제 지워도 된다 — 지우면 다음 호출이 그냥 다시 산다.

## 지출 가드 (D105 와 같은 순서)

  ① 캐시 확인이 **가장 먼저** — `allow_purchase` 와 무관하게 캐시가 있으면 네트워크 0.
  ② 캐시 미스인데 `allow_purchase=False` 면 예외 — 실수로 돈이 나가지 않게 호출부가
     **명시적으로** 구매를 허용해야 한다. 질의(query) 임베딩은 매 검색마다 필요하므로
     `mcp_server/dense_scorer.py` 가 기본으로 켜 둔다(비용이 텍스트 1건이라 미미함).
     코퍼스(passage) 일괄 임베딩은 `scripts/embed_manual_chunks.py` 가 명시적으로 켠다.
  ③ `NVIDIA_API_KEY` 부재 확인을 **지출(네트워크 제출) 전에** 끝낸다.

## 모델 선정 경위 (2026-08-24 실측, D117)

원래 요청은 Qwen3-Embedding(1B 이상, 다국어)이었으나 **이 NVIDIA API 키의 카탈로그
(`GET /v1/models`, 102개 모델)에 Qwen 임베딩이 0건**이었다 — build.nvidia.com 웹에는
Qwen 계열이 보이지만 이 카탈로그 API 로는 접근 불가. 실제 호출 가능한 1B급 후보 중
한국어 관련/무관 문장 판별 테스트(코사인 유사도 차)로 비교:
`nvidia/llama-nemotron-embed-1b-v2`(차 0.444) vs `nvidia/nemotron-3-embed-1b`(차 0.598,
채택) — `input`/`model`/`input_type`/`encoding_format` 요청 필드와 OpenAI 호환
`/v1/embeddings` 엔드포인트는 이 두 모델 호출로 실측 확인됐다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_ROOT = REPO_ROOT / "data" / "cache" / "embeddings"

DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
EMBEDDINGS_PATH = "/embeddings"
REQUEST_TIMEOUT_S = 60.0

#: 이 상수는 dense_scorer·embed_manual_chunks 둘 다 참조한다 — 모델을 바꾸면 이 값도
#: 같이 바꾸고, Postgres manual_chunks.embedding 컬럼 차원(scripts/postgres_schema.sql)도
#: 다시 맞춰야 한다.
#: ⚠ Qwen3-Embedding 은 이 NVIDIA API 키의 카탈로그(`/v1/models`)에 없었다(2026-08-24
#: 실측 — 102개 모델 중 임베딩 계열에 qwen 이 0건). 대신 실제로 호출해 확인한 1B급 2종
#: (`nvidia/llama-nemotron-embed-1b-v2` 유사도 차 0.444 · `nvidia/nemotron-3-embed-1b`
#: 유사도 차 0.598, 한국어 관련/무관 문장 판별 테스트) 중 변별력이 더 강한 후자를 D117 로
#: 확정했다. **차원은 2,048** — Qwen3-Embedding-4B(2,560)와 다르니 헷갈리지 말 것.
EMBEDDING_DIM = 2048

InputType = Literal["query", "passage"]


class NvidiaEmbedError(RuntimeError):
    """API 호출 실패 또는 응답 스키마 불일치. 원문 응답을 메시지에 담아 원인 파악을 돕는다."""


def _cache_key(model: str, input_type: InputType, text: str) -> str:
    """모델·용도·본문 내용 전부가 키에 들어간다 — 셋 중 하나만 달라도 다른 벡터가 나와야 한다."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]
    slug = model.replace("/", "_")
    return f"{slug}_{input_type}_{digest}"


def _cache_path(key: str) -> Path:
    return CACHE_ROOT / f"{key}.json"


def _load_cached(key: str) -> list[float] | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise NvidiaEmbedError(f"임베딩 캐시 {path} 를 읽을 수 없습니다: {e}") from e
    vec = data.get("embedding")
    if not isinstance(vec, list) or not vec:
        raise NvidiaEmbedError(f"임베딩 캐시 {path} 형식이 올바르지 않습니다: {sorted(data)}")
    return vec


def _store_cached(key: str, *, model: str, input_type: InputType, embedding: list[float]) -> None:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    path = _cache_path(key)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {"model": model, "input_type": input_type, "dim": len(embedding), "embedding": embedding},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    os.replace(tmp, path)  # 원자적 쓰기 — data/external/store.py 와 같은 이유(D103 ⑥)


def is_cached(text: str, *, input_type: InputType = "passage", model: str | None = None) -> bool:
    """네트워크 없이 캐시 적중 여부만 본다 — 일괄 색인 스크립트가 속도 제한(sleep)을
    캐시 히트에는 안 걸고 싶을 때 쓴다."""
    model_id = model or os.environ.get("NVIDIA_EMBED_MODEL", "").strip()
    if not model_id or not text:
        return False
    return _load_cached(_cache_key(model_id, input_type, text)) is not None


def embed_text(
    text: str,
    *,
    input_type: InputType = "query",
    model: str | None = None,
    allow_purchase: bool = True,
) -> list[float]:
    """텍스트 1건을 임베딩한다. 캐시 우선 — 같은 (모델, 용도, 텍스트) 는 네트워크를 안 탄다.

    `allow_purchase=False` 면 캐시 미스일 때 예외를 던진다(D105 식 안전장치) — 일괄 색인
    스크립트처럼 "많이 부를 걸 알고 있으니 명시적으로 허용" 하는 자리에서 기본을 뒤집어 쓴다.
    """
    if not text or not text.strip():
        raise NvidiaEmbedError("embed_text: text 가 비어 있습니다")

    model_id = model or os.environ.get("NVIDIA_EMBED_MODEL", "").strip()
    if not model_id:
        raise NvidiaEmbedError(
            "NVIDIA_EMBED_MODEL 이 설정되지 않았습니다 — .env 에 실제 카탈로그 모델 ID를 넣으세요"
            " (기본값을 두지 않는 이유: 임의 모델로 과금되는 사고를 막기 위해, MAINTQ_LLM_MODEL 과 같은 관례)"
        )

    key = _cache_key(model_id, input_type, text)
    cached = _load_cached(key)
    if cached is not None:
        logger.debug("임베딩 캐시 사용 (%s)", key)
        return cached

    if not allow_purchase:
        raise NvidiaEmbedError(
            f"임베딩 캐시 미스이고 allow_purchase=False 입니다 (key={key}) — "
            "의도한 호출이면 allow_purchase=True 로 명시하세요"
        )

    api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not api_key:
        raise NvidiaEmbedError("NVIDIA_API_KEY 가 설정되지 않았습니다")

    embedding = _call_api(text, model_id=model_id, input_type=input_type, api_key=api_key)
    _store_cached(key, model=model_id, input_type=input_type, embedding=embedding)
    return embedding


def _call_api(text: str, *, model_id: str, input_type: InputType, api_key: str) -> list[float]:
    """네트워크는 이 함수 밖으로 나가지 않는다 — httpx 는 여기서만 지연 import 한다."""
    import httpx  # noqa: PLC0415

    base_url = (os.environ.get("NVIDIA_EMBED_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    payload = {
        "input": [text],
        "model": model_id,
        "input_type": input_type,
        "encoding_format": "float",
    }
    try:
        resp = httpx.post(
            f"{base_url}{EMBEDDINGS_PATH}",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=REQUEST_TIMEOUT_S,
        )
    except httpx.HTTPError as e:
        raise NvidiaEmbedError(f"NVIDIA 임베딩 API 요청 실패: {e}") from e

    if resp.status_code != 200:
        raise NvidiaEmbedError(
            f"NVIDIA 임베딩 API status={resp.status_code}: {resp.text[:500]}"
        )
    try:
        body = resp.json()
        vec = body["data"][0]["embedding"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
        raise NvidiaEmbedError(
            f"NVIDIA 임베딩 API 응답 스키마가 예상과 다릅니다 ({e}): {resp.text[:500]}"
        ) from e
    if not isinstance(vec, list) or not vec:
        raise NvidiaEmbedError(f"NVIDIA 임베딩 API 가 빈 벡터를 반환했습니다: {resp.text[:500]}")
    return vec
