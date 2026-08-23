#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""manual_chunks.jsonl → Postgres manual_chunks 테이블, 실제 임베딩 포함 (D117).

이전 버전은 이름과 달리 임베딩을 전혀 계산하지 않고 `embedding=NULL` 인 행만 넣었다 —
`data/external/nvidia_embed.py` 가 생기기 전이라 계산할 방법이 없었다. 이제 NVIDIA
API(`nvidia/nemotron-3-embed-1b`, D117)로 실제 벡터를 채운다.

**API 호출이다(현재 무료 티어로 확인됨).** 캐시가 있으면(`data/cache/embeddings/`) 네트워크를
안 타지만, 최초 실행이나 캐시 삭제 후에는 코퍼스 전체(현재 1,229청크)를 임베딩한다 — 실행 전
`--dry-run` 으로 건수만 먼저 확인할 것을 권장한다.

**멱등 — DROP TABLE 하지 않는다.** `chunk_id` 기준 UPSERT 라 재실행해도 안전하고,
텍스트가 안 바뀐 청크는 캐시 히트라 재과금도 없다. 텍스트가 바뀐 청크만 새로 임베딩된다
(캐시 키가 텍스트 내용 해시를 포함하므로, D117).

**저장소는 Postgres(pgvector) 다 — 나중에 Qdrant Cloud 로 옮길 계획이 있다면, 바뀌는
지점은 이 스크립트의 INSERT 문 하나와 `mcp_server/dense_scorer.py::_fetch_corpus_embeddings`
하나뿐이다. 임베딩 자체(`data/external/nvidia_embed.py`)·검색 로직(`mcp_server/rag.py`)은
저장소가 뭐든 그대로다 — 지금 별도 추상화 계층을 미리 만들지는 않는다(코퍼스가 1,229건이라
브루트포스로 충분하다는 rag_sizing.md §4 결론과 같은 이유로, 쓰지도 않을 인터페이스를
먼저 설계하지 않는다).

**속도 제한(`--sleep-s`, 기본 0.3초)**: 무료 티어 rate limit 을 조심스럽게 다루기 위해
청크마다 이 시간만큼 쉰다(캐시 히트는 API 를 안 타므로 쉬지 않는다).

실행:
    uv run python scripts/migrate_vectors.py --postgres "$DATABASE_URL"
    uv run python scripts/migrate_vectors.py --postgres "$DATABASE_URL" --dry-run
    uv run python scripts/migrate_vectors.py --postgres "$DATABASE_URL" --sleep-s 0.5
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402

from data.external.nvidia_embed import (  # noqa: E402
    EMBEDDING_DIM,
    NvidiaEmbedError,
    embed_text,
    is_cached,
)


def migrate_vectors(
    jsonl_path: str, pg_url: str, *, dry_run: bool = False, sleep_s: float = 0.3
) -> None:
    jsonl_file = Path(jsonl_path)
    if not jsonl_file.exists():
        print(f"ERROR: {jsonl_path} not found", file=sys.stderr)
        sys.exit(1)

    chunks = []
    with jsonl_file.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                chunks.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  ERROR line {line_no}: {e}", file=sys.stderr)

    print(f"청크 {len(chunks)}건 (파일: {jsonl_file})")
    if dry_run:
        print("--dry-run — API 호출·DB 쓰기 없이 종료")
        return

    con = psycopg.connect(pg_url)
    cur = con.cursor()
    embedded = 0
    cache_hits = 0
    failed: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        chunk_id = chunk.get("chunk_id", "")
        was_cached = is_cached(chunk["text"], input_type="passage")
        try:
            vec = embed_text(chunk["text"], input_type="passage", allow_purchase=True)
        except NvidiaEmbedError as e:
            print(f"  임베딩 실패 {chunk_id}: {e}", file=sys.stderr)
            failed.append(chunk_id)
            continue
        if was_cached:
            cache_hits += 1
        else:
            time.sleep(sleep_s)  # 캐시 히트는 네트워크가 안 갔으니 쉴 필요 없음
        if len(vec) != EMBEDDING_DIM:
            print(
                f"  차원 불일치 {chunk_id}: {len(vec)} != {EMBEDDING_DIM} (스킵)",
                file=sys.stderr,
            )
            failed.append(chunk_id)
            continue

        vec_literal = "[" + ",".join(repr(float(x)) for x in vec) + "]"
        cur.execute(
            """
            INSERT INTO manual_chunks
                (chunk_id, manual_id, model, page, section, text, char_len, embedding, embedded_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector, now())
            ON CONFLICT (chunk_id) DO UPDATE SET
                manual_id = EXCLUDED.manual_id, model = EXCLUDED.model, page = EXCLUDED.page,
                section = EXCLUDED.section, text = EXCLUDED.text, char_len = EXCLUDED.char_len,
                embedding = EXCLUDED.embedding, embedded_at = EXCLUDED.embedded_at
            """,
            (
                chunk_id, chunk.get("manual_id"), chunk.get("model"), chunk.get("page"),
                chunk.get("section"), chunk.get("text"), chunk.get("char_len"), vec_literal,
            ),
        )
        embedded += 1
        if embedded % 20 == 0:
            con.commit()
            print(f"  {embedded}/{len(chunks)} 완료 (캐시 히트 {cache_hits}건)...")

    con.commit()
    con.close()
    print(f"완료 — {embedded}건 임베딩(캐시 히트 {cache_hits}건 포함), {len(failed)}건 실패")
    if failed:
        print(f"  실패 chunk_id: {failed}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="manual_chunks.jsonl → Postgres 임베딩 색인")
    parser.add_argument("--jsonl", default="data/extracted/manual_chunks.jsonl")
    parser.add_argument("--postgres", required=True, help="Postgres 연결 문자열")
    parser.add_argument("--dry-run", action="store_true", help="건수만 확인, API/DB 호출 없음")
    parser.add_argument(
        "--sleep-s", type=float, default=0.3, help="청크마다 API 호출 뒤 대기 시간(초, 기본 0.3)"
    )
    args = parser.parse_args()
    migrate_vectors(args.jsonl, args.postgres, dry_run=args.dry_run, sleep_s=args.sleep_s)
