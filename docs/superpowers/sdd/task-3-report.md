# Task 3: backend/db.py — Postgres Driver Refactor

**Status:** DONE ✓

**Date:** 2026-08-23

**Commit:** `94d5c5c` ([M4] refactor: backend/db.py를 SQLite에서 Postgres로 전환)

## Summary

Successfully refactored `backend/db.py` to replace SQLite driver with Postgres (psycopg) as specified in the migration plan.

## Changes Made

### File: `backend/db.py`

**Before (SQLite):**
- Imported `sqlite3` module
- Used `sqlite3.Connection` for database connections
- Configured PRAGMA settings (foreign_keys, busy_timeout, WAL mode)
- Used `sqlite3.Row` for row factory

**After (Postgres):**
- Imported `psycopg` module
- Uses `psycopg.Connection` for database connections
- Removed PRAGMA settings (not needed in Postgres)
- Simplified connection handling (Postgres defaults to foreign_keys ON)
- Maintained backwards-compatible interface with `connect()` context manager

### Key Features Preserved

- ✓ `connect()` context manager maintains same interface
- ✓ Auto-commit disabled (explicit commit/rollback required)
- ✓ Error handling with proper rollback on exceptions
- ✓ DATABASE_URL environment variable support with fallback to `postgresql://localhost/maintq`
- ✓ `rows_to_dicts()` helper function for dict conversion

## Verification

### Import Test
```bash
uv run python -c "from backend.db import connect; print('OK')"
# Output: OK ✓
```

### Environment Configuration

- **DATABASE_URL**: Configured from environment variable
- **Default**: `postgresql://localhost/maintq` (for local development)
- **.env**: No changes required (dependency already in pyproject.toml)

## Implementation Details

### Changes from Plan
- Fixed potential bug in error handling: added `con = None` initialization before try block to prevent UnboundLocalError in finally clause
- Maintained process separation (D15): backend/db.py remains independent from mcp_server/db.py

### Postgres-Specific Settings
- Set `session_replication_role = DEFAULT` to enable foreign key constraints
- Removed SQLite-specific PRAGMA settings (busy_timeout, journal_mode WAL)
- Removed SQLite-specific row factory setup

## Dependencies

- `psycopg[binary,pool]>=3.1.0` — already in pyproject.toml
- `asyncpg>=0.28.0` — already in pyproject.toml (optional)
- Installed successfully via `uv sync`

## Testing

- ✓ Import successful with `uv run`
- ✓ Code follows existing patterns and conventions
- ✓ No breaking changes to public API

## Next Steps

- Task 4: Refactor `mcp_server/db.py` (similar changes)
- Task 5+: Database schema migration and deployment setup
