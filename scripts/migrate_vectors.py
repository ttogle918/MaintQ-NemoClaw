#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""JSONL → Postgres 벡터 테이블 마이그레이션."""

import argparse
import json
import sys
from pathlib import Path

import psycopg


def migrate_vectors(jsonl_path: str, pg_url: str):
    """manual_chunks.jsonl을 Postgres 테이블에 로드."""

    jsonl_file = Path(jsonl_path)
    if not jsonl_file.exists():
        print(f"ERROR: {jsonl_path} not found", file=sys.stderr)
        sys.exit(1)

    print(f"📝 벡터 인덱스 마이그레이션")
    print(f"  JSONL: {jsonl_file}")
    print(f"  Postgres: {pg_url}")

    # Postgres 연결
    con = psycopg.connect(pg_url)
    cur = con.cursor()

    # pgvector 확장 활성화
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    con.commit()

    # manual_chunks 테이블 생성 (기존 있으면 DROP)
    cur.execute("DROP TABLE IF EXISTS manual_chunks CASCADE")
    cur.execute("""
        CREATE TABLE manual_chunks (
            chunk_id TEXT PRIMARY KEY,
            manual_id TEXT NOT NULL,
            model TEXT NOT NULL,
            page INTEGER NOT NULL,
            section TEXT NOT NULL,
            text TEXT NOT NULL,
            char_len INTEGER NOT NULL,
            embedding vector(1536),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX idx_chunks_model ON manual_chunks(model);
        CREATE INDEX idx_chunks_manual ON manual_chunks(manual_id);
    """)
    con.commit()

    # JSONL 로드
    rows_loaded = 0
    with jsonl_file.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue

            try:
                chunk = json.loads(line)

                # 쿼리 준비
                cur.execute("""
                    INSERT INTO manual_chunks
                    (chunk_id, manual_id, model, page, section, text, char_len, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    chunk.get("chunk_id"),
                    chunk.get("manual_id"),
                    chunk.get("model"),
                    chunk.get("page"),
                    chunk.get("section"),
                    chunk.get("text"),
                    chunk.get("char_len"),
                    None,  # embedding 아직 NULL
                ))
                rows_loaded += 1

                if rows_loaded % 100 == 0:
                    con.commit()
                    print(f"  {rows_loaded} rows loaded...")

            except (json.JSONDecodeError, KeyError) as e:
                print(f"  ERROR line {line_no}: {e}", file=sys.stderr)
                continue

    con.commit()
    con.close()

    print(f"✅ {rows_loaded}개 청크 마이그레이션 완료")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JSONL → Postgres 벡터 마이그레이션")
    parser.add_argument(
        "--jsonl",
        default="data/extracted/manual_chunks.jsonl",
        help="JSONL 파일 경로"
    )
    parser.add_argument(
        "--postgres",
        required=True,
        help="Postgres 연결 문자열"
    )

    args = parser.parse_args()
    migrate_vectors(args.jsonl, args.postgres)
