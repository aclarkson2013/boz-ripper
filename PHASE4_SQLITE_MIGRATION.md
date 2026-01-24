# Phase 4: SQLite Database Migration

**Implementation Date:** January 23, 2026
**Status:** 🚧 Planning

## Overview

Migrate from in-memory storage to persistent SQLite database storage. This enables:
- Data persistence across server restarts
- Multi-disc TV season tracking that survives restarts
- Production-ready reliability
- Foundation for future features (worker failover, job recovery, etc.)

## Current Architecture

### In-Memory Storage
All data is currently stored in Python dictionaries:

1. **JobQueue Service:**
   - `_jobs: dict[str, Job]` - All jobs (rip/transcode)
   - `_discs: dict[str, Disc]` - Detected discs

2. **AgentManager Service:**
   - `_agents: dict[str, Agent]` - Registered agents

3. **WorkerManager Service:**
   - `_workers: dict[str, Worker]` - Registered workers

4. **PreviewGenerator Service:**
   - `_tv_seasons: dict[str, TVSeason]` - TV season state tracking

### Current Models (Pydantic)
- `Job`, `JobStatus`, `JobType`
- `Agent`, `AgentStatus`, `AgentCapabilities`
- `Worker`, `WorkerStatus`, `WorkerType`, `WorkerCapabilities`
- `Disc`, `Title`, `DiscType`, `MediaType`, `PreviewStatus`
- `TVSeason`, `TVEpisode`

## Migration Strategy

### Phase 4.1: Database Infrastructure
1. Add SQLAlchemy and Alembic to dependencies
2. Create database configuration and connection management
3. Set up Alembic for migrations
4. Design ORM models (parallel to Pydantic models initially)

### Phase 4.2: Database Schema Design
Design SQLAlchemy ORM models for:
- `jobs` table
- `agents` table
- `workers` table
- `discs` table
- `titles` table (one-to-many with discs)
- `tv_seasons` table
- `tv_episodes` table (one-to-many with tv_seasons)

### Phase 4.3: Service Layer Migration
Update services to use database instead of in-memory storage:
- JobQueue → Database queries
- AgentManager → Database queries
- WorkerManager → Database queries
- PreviewGenerator → Database queries for TV seasons

### Phase 4.4: Data Access Layer
Create repository pattern for database operations:
- `JobRepository`
- `AgentRepository`
- `WorkerRepository`
- `DiscRepository`
- `TVSeasonRepository`

## Database Schema Design

### Jobs Table
```sql
CREATE TABLE jobs (
    job_id VARCHAR(36) PRIMARY KEY,
    job_type VARCHAR(20) NOT NULL,  -- rip, transcode, organize
    status VARCHAR(20) NOT NULL,    -- pending, queued, assigned, running, completed, failed, cancelled
    priority INTEGER DEFAULT 0,

    -- Source info
    disc_id VARCHAR(36),
    title_index INTEGER,
    input_file VARCHAR(512),

    -- Output info
    output_name VARCHAR(255),
    output_file VARCHAR(512),
    preset VARCHAR(100),

    -- Assignment
    assigned_agent_id VARCHAR(100),
    assigned_at TIMESTAMP,

    -- Approval workflow
    requires_approval BOOLEAN DEFAULT FALSE,
    source_disc_name VARCHAR(255),
    input_file_size BIGINT,

    -- Progress tracking
    progress REAL DEFAULT 0.0,
    error TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    FOREIGN KEY (disc_id) REFERENCES discs(disc_id)
);

CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_agent ON jobs(assigned_agent_id);
CREATE INDEX idx_jobs_type ON jobs(job_type);
CREATE INDEX idx_jobs_approval ON jobs(requires_approval, status);
```

### Agents Table
```sql
CREATE TABLE agents (
    agent_id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    status VARCHAR(20) DEFAULT 'online',  -- online, offline, busy

    -- Capabilities (JSON)
    capabilities TEXT,  -- JSON: {can_rip, can_transcode, gpu_type}

    -- Current work
    current_job_id VARCHAR(36),

    -- Health tracking
    last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (current_job_id) REFERENCES jobs(job_id)
);

CREATE INDEX idx_agents_status ON agents(status);
```

### Workers Table
```sql
CREATE TABLE workers (
    worker_id VARCHAR(100) PRIMARY KEY,
    worker_type VARCHAR(20) NOT NULL,  -- agent, remote, server
    hostname VARCHAR(100) NOT NULL,
    agent_id VARCHAR(100),  -- Links worker to agent

    -- Capabilities (JSON)
    capabilities TEXT,  -- JSON: {nvenc, qsv, hevc, av1, cpu_threads, max_concurrent}

    -- Priority and status
    priority INTEGER DEFAULT 50,
    enabled BOOLEAN DEFAULT TRUE,
    status VARCHAR(20) DEFAULT 'available',  -- available, busy, offline

    -- Current work (JSON array)
    current_jobs TEXT,  -- JSON: ["job_id1", "job_id2"]

    -- Health tracking
    last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Stats
    total_jobs_completed INTEGER DEFAULT 0,
    avg_transcode_time_seconds REAL DEFAULT 0.0,

    -- Resource usage
    cpu_usage REAL,
    gpu_usage REAL,

    FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
);

CREATE INDEX idx_workers_status ON workers(status);
CREATE INDEX idx_workers_priority ON workers(priority);
CREATE INDEX idx_workers_agent ON workers(agent_id);
```

### Discs Table
```sql
CREATE TABLE discs (
    disc_id VARCHAR(36) PRIMARY KEY,
    agent_id VARCHAR(100) NOT NULL,
    drive VARCHAR(10) NOT NULL,
    disc_name VARCHAR(255) NOT NULL,
    disc_type VARCHAR(20) DEFAULT 'Unknown',  -- DVD, Blu-ray, Unknown
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'detected',  -- detected, ripping, completed, ejected

    -- Preview/approval fields
    media_type VARCHAR(20) DEFAULT 'unknown',  -- movie, tv_show, unknown
    preview_status VARCHAR(20) DEFAULT 'pending',  -- pending, approved, rejected

    -- TV show fields
    tv_show_name VARCHAR(255),
    tv_season_number INTEGER,
    tv_season_id VARCHAR(100),
    thetvdb_series_id INTEGER,
    starting_episode_number INTEGER,

    FOREIGN KEY (agent_id) REFERENCES agents(agent_id),
    FOREIGN KEY (tv_season_id) REFERENCES tv_seasons(season_id)
);

CREATE INDEX idx_discs_agent ON discs(agent_id);
CREATE INDEX idx_discs_status ON discs(status);
CREATE INDEX idx_discs_preview_status ON discs(preview_status);
CREATE INDEX idx_discs_tv_season ON discs(tv_season_id);
```

### Titles Table
```sql
CREATE TABLE titles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    disc_id VARCHAR(36) NOT NULL,
    title_index INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    duration_seconds INTEGER NOT NULL,
    size_bytes BIGINT NOT NULL,
    chapters INTEGER DEFAULT 0,
    selected BOOLEAN DEFAULT FALSE,

    -- Preview/approval fields
    is_extra BOOLEAN DEFAULT FALSE,
    proposed_filename VARCHAR(255),
    proposed_path VARCHAR(512),
    episode_number INTEGER,
    episode_title VARCHAR(255),
    confidence_score REAL DEFAULT 0.0,

    FOREIGN KEY (disc_id) REFERENCES discs(disc_id) ON DELETE CASCADE,
    UNIQUE (disc_id, title_index)
);

CREATE INDEX idx_titles_disc ON titles(disc_id);
CREATE INDEX idx_titles_selected ON titles(selected);
```

### TV Seasons Table
```sql
CREATE TABLE tv_seasons (
    season_id VARCHAR(100) PRIMARY KEY,
    show_name VARCHAR(255) NOT NULL,
    season_number INTEGER NOT NULL,
    thetvdb_series_id INTEGER,

    -- Episode tracking
    last_episode_assigned INTEGER DEFAULT 0,

    -- Multi-disc tracking
    disc_ids TEXT,  -- JSON: ["disc_id1", "disc_id2"]
    last_disc_name VARCHAR(255),

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (show_name, season_number)
);

CREATE INDEX idx_tv_seasons_show ON tv_seasons(show_name);
```

### TV Episodes Table
```sql
CREATE TABLE tv_episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id VARCHAR(100) NOT NULL,
    episode_number INTEGER NOT NULL,
    episode_name VARCHAR(255) NOT NULL,
    season_number INTEGER NOT NULL,
    runtime INTEGER,  -- minutes
    overview TEXT,

    FOREIGN KEY (season_id) REFERENCES tv_seasons(season_id) ON DELETE CASCADE,
    UNIQUE (season_id, episode_number)
);

CREATE INDEX idx_tv_episodes_season ON tv_episodes(season_id);
```

## Implementation Plan

### Step 1: Add Dependencies
Update `server/requirements.txt`:
```
sqlalchemy>=2.0.0
alembic>=1.13.0
aiosqlite>=0.19.0  # Async SQLite support
```

### Step 2: Create Database Module
New files:
- `server/src/boz_server/database/__init__.py`
- `server/src/boz_server/database/config.py` - Database configuration
- `server/src/boz_server/database/session.py` - Session management
- `server/src/boz_server/database/base.py` - Base ORM class

### Step 3: Create ORM Models
New files in `server/src/boz_server/database/models/`:
- `job.py` - Job ORM model
- `agent.py` - Agent ORM model
- `worker.py` - Worker ORM model
- `disc.py` - Disc and Title ORM models
- `tv_show.py` - TVSeason and TVEpisode ORM models

### Step 4: Set Up Alembic
```bash
cd server
alembic init alembic
```

Configure `alembic.ini` and create initial migration.

### Step 5: Create Repository Layer
New files in `server/src/boz_server/repositories/`:
- `base.py` - Base repository with common operations
- `job_repository.py`
- `agent_repository.py`
- `worker_repository.py`
- `disc_repository.py`
- `tv_season_repository.py`

### Step 6: Update Services
Modify existing services to use repositories:
- `job_queue.py` - Use JobRepository
- `agent_manager.py` - Use AgentRepository
- `worker_manager.py` - Use WorkerRepository
- `preview_generator.py` - Use TVSeasonRepository
- Update API endpoints to use database sessions

### Step 7: Migration Testing
Test scenarios:
1. Create job → Restart server → Job persists
2. Register agent → Restart server → Agent still registered
3. TV season disc 1 → Restart server → Insert disc 2 → Episodes continue
4. Worker assignment → Restart server → Worker stats preserved

## Architectural Decisions

### 1. Hybrid Pydantic + SQLAlchemy Approach
- Keep Pydantic models for API validation
- Add SQLAlchemy ORM models for database
- Create conversion utilities between Pydantic ↔ ORM

**Why:** Minimal disruption to existing API contracts and validation logic.

### 2. Repository Pattern
- Isolate database operations in repository classes
- Services depend on repositories, not direct ORM access

**Why:** Clean separation of concerns, easier testing, flexibility for future database changes.

### 3. JSON Fields for Complex Types
- Store `capabilities`, `current_jobs`, `disc_ids` as JSON strings
- Parse to Python objects when loading

**Why:** SQLite doesn't have native array/object types. JSON is simple and works well for our use case.

### 4. Async Database Operations
- Use `aiosqlite` for async SQLite support
- All repository methods are async

**Why:** Maintain consistency with FastAPI async patterns, prevent blocking.

### 5. Cascade Deletes
- Titles deleted when Disc is deleted
- Episodes deleted when TVSeason is deleted

**Why:** Data integrity, automatic cleanup.

### 6. Database Location
Default: `/data/database/boz_ripper.db`
Configurable via environment: `BOZ_DATABASE_URL`

**Why:** Persistent storage in Docker volumes, easy backups.

## Breaking Changes

### None Expected
Migration is designed to be transparent to:
- Agent API contracts
- Dashboard API contracts
- Existing functionality

## Configuration

New environment variables:
```bash
# Database URL (SQLite by default)
BOZ_DATABASE_URL=sqlite+aiosqlite:////data/database/boz_ripper.db

# Database pool settings (optional)
BOZ_DATABASE_POOL_SIZE=5
BOZ_DATABASE_MAX_OVERFLOW=10

# Enable SQL query logging (debug)
BOZ_DATABASE_ECHO=false
```

## Rollout Plan

### Development Phase
1. Implement on development branch
2. Test with sample data
3. Verify all existing features work
4. Performance testing

### Production Rollout
1. **Backup:** No data to backup (currently in-memory)
2. **Deploy:** New version with SQLite
3. **Verify:** Check logs for database initialization
4. **Test:** Full end-to-end workflow test

## Success Criteria

- [ ] All jobs persist across server restart
- [ ] Workers/agents re-register and reconnect seamlessly
- [ ] Discs persist and can be queried after restart
- [ ] TV season tracking persists across multi-disc inserts with server restart in between
- [ ] No degradation in API response times
- [ ] All existing tests pass
- [ ] Database migrations run successfully

## Future Enhancements (Post Phase 4)

1. **Database Backups:**
   - Automatic daily backups
   - Backup before major operations

2. **Data Retention Policies:**
   - Auto-delete completed jobs after 30 days
   - Archive old disc records

3. **Advanced Queries:**
   - Job history analytics
   - Worker performance metrics
   - Disc collection browsing

4. **Multi-Server Support:**
   - Migrate to PostgreSQL for distributed architecture
   - Shared database across multiple server instances

## File Checklist

### New Files
- [ ] `server/src/boz_server/database/__init__.py`
- [ ] `server/src/boz_server/database/config.py`
- [ ] `server/src/boz_server/database/session.py`
- [ ] `server/src/boz_server/database/base.py`
- [ ] `server/src/boz_server/database/models/__init__.py`
- [ ] `server/src/boz_server/database/models/job.py`
- [ ] `server/src/boz_server/database/models/agent.py`
- [ ] `server/src/boz_server/database/models/worker.py`
- [ ] `server/src/boz_server/database/models/disc.py`
- [ ] `server/src/boz_server/database/models/tv_show.py`
- [ ] `server/src/boz_server/repositories/__init__.py`
- [ ] `server/src/boz_server/repositories/base.py`
- [ ] `server/src/boz_server/repositories/job_repository.py`
- [ ] `server/src/boz_server/repositories/agent_repository.py`
- [ ] `server/src/boz_server/repositories/worker_repository.py`
- [ ] `server/src/boz_server/repositories/disc_repository.py`
- [ ] `server/src/boz_server/repositories/tv_season_repository.py`
- [ ] `server/alembic/env.py`
- [ ] `server/alembic/versions/001_initial_schema.py`

### Modified Files
- [ ] `server/requirements.txt`
- [ ] `server/src/boz_server/core/config.py`
- [ ] `server/src/boz_server/services/job_queue.py`
- [ ] `server/src/boz_server/services/agent_manager.py`
- [ ] `server/src/boz_server/services/worker_manager.py`
- [ ] `server/src/boz_server/services/preview_generator.py`
- [ ] `server/src/boz_server/api/*.py` (dependency injection)

## Risks and Mitigation

### Risk: Data Loss During Migration
**Mitigation:** Since currently in-memory, no existing data to lose. Fresh start.

### Risk: Performance Degradation
**Mitigation:** SQLite is fast for single-server workloads. Add indexes for common queries.

### Risk: Database Corruption
**Mitigation:**
- Use WAL mode for SQLite
- Implement health checks
- Regular backups

### Risk: Complex Queries
**Mitigation:** Start simple, optimize as needed. Repository pattern allows easy query tuning.

## Timeline Estimate

- **Step 1-2 (Infrastructure):** 2-3 hours
- **Step 3-4 (ORM Models + Alembic):** 4-5 hours
- **Step 5 (Repositories):** 3-4 hours
- **Step 6 (Service Migration):** 6-8 hours
- **Step 7 (Testing):** 3-4 hours

**Total:** ~20-25 hours of development

## References

- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [FastAPI with SQLAlchemy](https://fastapi.tiangolo.com/tutorial/sql-databases/)
- [aiosqlite Documentation](https://aiosqlite.omnilib.dev/)

---

*Created: January 23, 2026*
*Status: Planning Complete - Ready for Implementation*
