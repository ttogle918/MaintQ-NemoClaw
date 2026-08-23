# Postgres Setup Guide

Complete setup guide for migrating MaintQ from SQLite to Postgres (Supabase, Neon, or local Docker).

## Quick Start

### Option A: Supabase (Cloud - Recommended)

**Time: ~5 minutes**

1. **Create project**
   ```
   Visit https://supabase.com
   Sign up (free tier available)
   Create new project
   ```

2. **Apply schema**
   ```
   1. Open project → SQL Editor → New Query
   2. Copy contents of: scripts/postgres_schema.sql
   3. Paste into SQL Editor
   4. Click "Run"
   5. Verify: "Query succeeded" message
   ```

3. **Get connection string**
   ```
   Project Settings → Database → Connection string
   Copy the full "URI" (postgresql://...)
   ```

4. **Update .env**
   ```bash
   cp .env.postgres.example .env.postgres
   # Edit .env.postgres, set DATABASE_URL to your connection string
   # DATABASE_URL=postgresql://postgres:[PASSWORD]@[PROJECT_ID].supabase.co:5432/postgres
   ```

5. **Verify**
   ```sql
   -- In Supabase SQL Editor:
   SELECT COUNT(*) as table_count FROM information_schema.tables 
   WHERE table_schema = 'public';
   -- Expected: 24
   ```

### Option B: Docker Compose (Local - Development)

**Time: ~10 minutes** (includes Docker startup)

1. **Create docker-compose.yml** (see section below)

2. **Start Postgres**
   ```bash
   docker-compose up postgres -d
   docker-compose logs postgres  # Wait for "ready to accept connections"
   ```

3. **Apply schema**
   ```bash
   psql postgresql://postgres:postgres@localhost:5432/maintq \
     < scripts/postgres_schema.sql
   ```

4. **Update .env**
   ```bash
   cp .env.postgres.example .env.postgres
   # Edit: DATABASE_URL=postgresql://postgres:postgres@localhost:5432/maintq
   ```

5. **Verify**
   ```bash
   psql postgresql://postgres:postgres@localhost:5432/maintq \
     -c "SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema='public';"
   # Expected: table_count = 24
   ```

## Detailed Setup Instructions

### Supabase (Cloud)

#### Prerequisites
- Email address
- Credit card (for paid usage, though free tier has generous limits)
- Web browser

#### Steps

1. **Sign up at Supabase**
   ```
   https://supabase.com/sign-up
   ```

2. **Create organization** (if first time)
   - Enter organization name: e.g., "MaintQ Dev"
   - Click "Create organization"

3. **Create project**
   - Click "New project"
   - Name: `maintq` or `maintq-dev`
   - Database password: Generate or set your own (save securely)
   - Region: Select closest to your location
   - Click "Create new project"
   - Wait for initialization (~2-3 minutes)

4. **Open SQL Editor**
   - Left sidebar → "SQL Editor" → "New query"
   - Or: Top menu → "SQL" → "New query"

5. **Apply schema**
   ```
   1. Open scripts/postgres_schema.sql in text editor
   2. Select all (Ctrl+A)
   3. Copy (Ctrl+C)
   4. Click in Supabase SQL Editor query area
   5. Paste (Ctrl+V)
   6. Click blue "Run" button
   7. Wait for completion
   ```

6. **Verify successful**
   - Look for: "Query succeeded" message
   - No error messages in red
   - Scroll down: should see "CREATE TABLE" confirmations

7. **Verify table count**
   ```sql
   -- Paste this into SQL Editor:
   SELECT COUNT(*) as table_count FROM information_schema.tables 
   WHERE table_schema = 'public';
   ```
   Expected result: `table_count = 24`

8. **Get connection details**
   - Top-left → Project settings → Database
   - Find "Connection string" section
   - Copy "URI" (looks like: `postgresql://postgres:xxx@xxx.supabase.co:5432/postgres`)

9. **Configure .env**
   ```bash
   # In MaintQ root:
   cp .env.postgres.example .env.postgres
   
   # Edit .env.postgres with your editor:
   # Find line: DATABASE_URL=
   # Replace with: DATABASE_URL=postgresql://postgres:[PASSWORD]@[PROJECT_ID].supabase.co:5432/postgres
   ```

10. **Test connection** (optional but recommended)
    ```bash
    # From MaintQ root:
    uv run python -c "import psycopg; con = psycopg.connect('YOUR_DATABASE_URL'); print(f'✅ Connected to Postgres'); con.close()"
    ```

#### Supabase Billing Notes

- **Free tier:** 500 MB database storage, sufficient for development
- **Paid tier:** $15/month for production features
- **Auto-pause:** Free tier databases pause after 7 days of inactivity (resume anytime)
- **Backup:** Daily backups included (14-day retention)

---

### Docker Compose (Local Development)

#### Prerequisites
- Docker Desktop installed (macOS/Windows) or Docker + Docker Compose (Linux)
- ~1 GB disk space for Postgres image
- Port 5432 available (Postgres default)

#### Docker Compose Configuration

Create `docker-compose.yml` in MaintQ root:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    container_name: maintq_postgres
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: maintq
      TZ: UTC
    ports:
      - "5432:5432"
    volumes:
      # Named volume for data persistence
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    networks:
      - maintq
    command: 
      - "postgres"
      - "-c"
      - "log_statement=all"
      - "-c"
      - "log_duration=on"

  # Optional: pgAdmin for visual database management
  pgadmin:
    image: dpage/pgadmin4:latest
    container_name: maintq_pgadmin
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@localhost
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5050:80"
    depends_on:
      - postgres
    networks:
      - maintq

volumes:
  postgres_data:

networks:
  maintq:
```

#### Docker Setup Steps

1. **Create docker-compose.yml**
   - Copy YAML above into `docker-compose.yml` in MaintQ root
   - Or: `cp docs/docker-compose.example.yml docker-compose.yml`

2. **Start Postgres**
   ```bash
   docker-compose up postgres -d
   ```

3. **Wait for health check**
   ```bash
   # Watch logs until you see: "database system is ready to accept connections"
   docker-compose logs postgres
   ```
   Should see something like:
   ```
   postgres_1  | 2026-08-23 12:34:56.789 UTC [1] LOG:  database system is ready to accept connections
   ```

4. **Apply schema**
   ```bash
   # One of these methods:
   
   # Method A: Using psql from host
   psql postgresql://postgres:postgres@localhost:5432/maintq < scripts/postgres_schema.sql
   
   # Method B: Using psql from Docker container
   docker exec -i maintq_postgres psql -U postgres -d maintq < scripts/postgres_schema.sql
   
   # Method C: Using psql interactively
   psql postgresql://postgres:postgres@localhost:5432/maintq
   # Then in psql: \i scripts/postgres_schema.sql
   ```

5. **Verify tables created**
   ```bash
   psql postgresql://postgres:postgres@localhost:5432/maintq \
     -c "SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema='public';"
   ```
   Expected: `table_count = 24`

6. **Update .env**
   ```bash
   cp .env.postgres.example .env.postgres
   
   # Edit .env.postgres:
   # DATABASE_URL=postgresql://postgres:postgres@localhost:5432/maintq
   ```

#### Docker Management Commands

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# View logs
docker-compose logs postgres
docker-compose logs postgres -f  # Follow live logs

# Access psql directly
docker exec -it maintq_postgres psql -U postgres -d maintq

# Reset database (careful!)
docker-compose down
docker volume rm maintq_postgres_data
docker-compose up postgres -d

# Open pgAdmin UI
# Go to: http://localhost:5050
# Login: admin@localhost / admin
# Add server: host=postgres, port=5432, user=postgres, password=postgres
```

#### pgAdmin UI (Optional)

pgAdmin is included in docker-compose.yml for visual database management.

1. **Open pgAdmin**
   ```
   http://localhost:5050
   ```

2. **Login**
   - Email: `admin@localhost`
   - Password: `admin`

3. **Add Postgres server**
   - Right-click "Servers" → "Create" → "Server"
   - General tab → Name: `maintq`
   - Connection tab:
     - Host: `postgres` (Docker service name)
     - Port: `5432`
     - Username: `postgres`
     - Password: `postgres`
   - Click "Save"

4. **Browse database**
   - Left panel → Servers → maintq → Databases → maintq → Schemas → public → Tables
   - Should see all 24 tables

---

### Neon (Cloud Alternative)

**Similar to Supabase but different provider**

1. **Sign up**
   ```
   https://neon.tech/sign-up
   ```

2. **Create project**
   - Free tier includes: 10 projects, 3 GB storage
   - Select Postgres version (14+)

3. **Get connection string**
   - Copy "Connection string" from Dashboard
   - Looks like: `postgresql://user:password@host/dbname?sslmode=require`

4. **Apply schema**
   ```bash
   # Via psql:
   psql 'postgresql://user:password@host/dbname?sslmode=require' < scripts/postgres_schema.sql
   ```

5. **Update .env**
   ```bash
   DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
   ```

---

## Verification Checklist

### Universal Verification (any Postgres)

```sql
-- Connect to database, then run:

-- 1. Table count
SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema='public';
-- Expected: 24

-- 2. Table names
SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;
-- Should include: error_codes, users, assets, equipment, parts, suppliers, etc.

-- 3. Constraint count
SELECT COUNT(*) as constraint_count FROM information_schema.constraint_column_usage WHERE table_schema='public';
-- Expected: > 100 (many CHECK constraints)

-- 4. Foreign key count
SELECT COUNT(*) as fk_count FROM information_schema.table_constraints WHERE constraint_type='FOREIGN KEY' AND table_schema='public';
-- Expected: > 10
```

### Supabase-specific Verification

In SQL Editor:
```sql
-- Check extensions
SELECT * FROM pg_extension WHERE extname = 'pgvector';
-- Should be empty (added in Task 7)

-- Check for errors
SELECT * FROM information_schema.tables WHERE table_schema='public' LIMIT 1;
-- Should return error_codes table
```

### Docker-specific Verification

```bash
# List tables
docker exec maintq_postgres psql -U postgres -d maintq -c "\dt public.*"

# Full schema dump (for backup)
docker exec maintq_postgres pg_dump -U postgres maintq > backup.sql

# Check disk usage
docker exec maintq_postgres psql -U postgres -d maintq -c "SELECT pg_size_pretty(pg_database_size('maintq'));"
```

---

## Troubleshooting

### Connection Issues

**Error: "could not translate host name"**
- Postgres server not running
- **Supabase:** Check internet connection, project status
- **Docker:** Run `docker-compose up postgres -d`

**Error: "password authentication failed"**
- Wrong password in connection string
- Check .env, credentials in docker-compose.yml

**Error: "database does not exist"**
- **Supabase:** Use `postgres` as database name (not `maintq`)
- **Docker:** Database created automatically; verify with `docker-compose logs postgres`

### Schema Application Issues

**Error: "permission denied"**
- Postgres user lacks schema creation rights
- **Supabase:** Use default account, should have rights
- **Docker:** Use `postgres` user with password `postgres`

**Error: "table already exists"**
- Schema already applied once
- Drop and re-create: `DROP SCHEMA public CASCADE; CREATE SCHEMA public;`
- Re-apply schema

**Error: "CREATE TEMP TRIGGER failed"**
- Temporary trigger syntax issue (shouldn't occur with provided SQL)
- Verify scripts/postgres_schema.sql is unchanged

### Performance Issues

**Queries running slowly after migration:**
- Indexes not created: Check `scripts/postgres_schema.sql` includes CREATE INDEX
- Statistics stale: Run `ANALYZE;` in database
- **Supabase:** May be auto-paused (free tier); wake up by accessing

**Vector index errors (Task 7):**
- pgvector extension not installed
- **Supabase:** Enabled by default
- **Docker:** Install in docker-compose.yml or after startup

---

## Environment Configuration

### .env.postgres Template

```bash
# Copy from .env.postgres.example
cp .env.postgres.example .env.postgres

# Edit with your connection string:

# Local Docker:
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/maintq

# Supabase:
DATABASE_URL=postgresql://postgres:[PASSWORD]@[PROJECT_ID].supabase.co:5432/postgres

# Neon:
DATABASE_URL=postgresql://[user]:[password]@[host]/maintq?sslmode=require
```

### Backend Code Configuration

Ensure backend reads from environment:

```python
# backend/db.py
import os
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")
con = psycopg.connect(DATABASE_URL)
```

---

## Next Steps

1. ✅ **Task 6 (this):** Postgres schema applied, verified 24 tables
2. **Task 7:** Vector index migration (pgvector setup)
3. **Task 8:** Data migration (sqlite → postgres data)
4. **Task 9:** Backend code updates (driver migration)
5. **Task 10:** Testing & verification

---

## Reference

- **Postgres 14+ Documentation:** https://www.postgresql.org/docs/14/
- **Supabase Docs:** https://supabase.com/docs
- **Docker Compose Reference:** https://docs.docker.com/compose/
- **pgvector Extension:** https://github.com/pgvector/pgvector
- **psycopg (Python driver):** https://www.psycopg.org/psycopg3/

---

**Last updated:** 2026-08-23
**Plan reference:** Task 6, lines 713-779
