# Task 7: pgvector Setup and Vector Table Migration — Report

**Status:** DONE

**Commit:** `4c2c6c2` — [M4] scripts: 벡터 인덱스 JSONL→Postgres 마이그레이션 스크립트

## Summary

Created `scripts/migrate_vectors.py` to migrate JSONL chunks to Postgres with pgvector support. Script verified for syntax and argument parsing.

## Implementation Details

### File Created
- **`scripts/migrate_vectors.py`** (108 lines)
  - Enables pgvector extension: `CREATE EXTENSION IF NOT EXISTS vector`
  - Creates `manual_chunks` table with 8 columns:
    - `chunk_id` (TEXT PRIMARY KEY)
    - `manual_id` (TEXT NOT NULL)
    - `model` (TEXT NOT NULL — iG5A, S100, IE5)
    - `page` (INTEGER NOT NULL)
    - `section` (TEXT NOT NULL)
    - `text` (TEXT NOT NULL)
    - `char_len` (INTEGER NOT NULL)
    - `embedding` (vector(1536), nullable — will be populated by D51 later)
    - `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
  
  - Creates two indexes:
    - `idx_chunks_model` on `model`
    - `idx_chunks_manual` on `manual_id`
  
  - Loads JSONL records from `data/extracted/manual_chunks.jsonl`
  - Sets `embedding` to NULL for all records (D51 handles actual embedding)
  - Commits in batches of 100 rows
  - Reports progress and final count

### Command Signature

```bash
uv run python scripts/migrate_vectors.py \
    --jsonl data/extracted/manual_chunks.jsonl \
    --postgres postgresql://user:password@host:5432/maintq
```

### Verification

- ✅ Syntax validated: `python -m py_compile scripts/migrate_vectors.py`
- ✅ Help output works: `uv run python scripts/migrate_vectors.py --help`
- ✅ JSONL file verified:
  - Location: `data/extracted/manual_chunks.jsonl`
  - Chunk count: **1,229 records** (note: plan spec stated 1,035, but actual file has 1,229)
  - All records parse successfully as valid JSON
  - All records have required fields: chunk_id, manual_id, model, page, section, text, char_len
- ✅ Dependencies present in `pyproject.toml`:
  - `psycopg[binary,pool]>=3.1.0`
  - `pgvector>=0.2.1`

## Test Status

**Current:** Syntax and argument parsing verified. Ready for execution pending Postgres database availability.

**When Postgres is available, run:**
```bash
uv run python scripts/migrate_vectors.py \
    --jsonl data/extracted/manual_chunks.jsonl \
    --postgres postgresql://user:password@host:5432/maintq
```

**Expected output:**
```
📝 벡터 인덱스 마이그레이션
  JSONL: .../data/extracted/manual_chunks.jsonl
  Postgres: postgresql://...
  100 rows loaded...
  ...
✅ 1229개 청크 마이그레이션 완료
```

## Design Decisions Respected

- **D51** — Embedding column created as NULL; actual embeddings will be populated in a separate sprint
- Pgvector extension properly isolated: only enabled when running migration, not baked into schema
- No vector indexes created yet (Task 8 reserved for optimization)
- UTF-8 encoding properly handled for Korean manual content

## Dependencies

- `psycopg[binary,pool]>=3.1.0` (already in pyproject.toml)
- `pgvector>=0.2.1` (already in pyproject.toml)

## Files Modified/Created

| File | Action | Lines |
|------|--------|-------|
| `scripts/migrate_vectors.py` | Created | 108 |

## Next Steps (Task 8+)

1. **When Postgres available:** Execute script to populate `manual_chunks` table
2. **Task 8 (Vector Search Layer):** Currently on hold — will migrate JSONL-based search to Postgres when needed
3. **Vector Index Optimization:** After vectors are embedded (D51), create IVFFlat index for cosine similarity search
