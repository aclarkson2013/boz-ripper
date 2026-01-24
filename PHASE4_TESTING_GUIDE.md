# Phase 4 SQLite Migration - Testing Guide

**Purpose:** Verify that database persistence works correctly

## Prerequisites

1. Server with Phase 4 code deployed
2. Agent connected
3. Access to server logs
4. Access to database file: `/data/database/boz_ripper.db`

## Quick Start Testing

### Test 1: Database Creation (2 minutes)

**Verify database was created on server startup:**

```bash
# SSH to server
ssh user@10.0.0.60

# Check database exists
ls -lh /data/database/boz_ripper.db

# Should see file with size > 0 bytes
```

**Check server logs:**
```
Starting Boz Ripper Server v0.x.x
Initializing database...
Database initialized successfully
Server ready on 0.0.0.0:8000
```

**✅ Pass:** Database file exists and initialization logged
**❌ Fail:** No database file or initialization errors in logs

---

### Test 2: Agent Registration Persistence (3 minutes)

**Step 1: Register Agent**
- Start agent on 192.168.0.61
- Wait for registration to complete

**Step 2: Verify Registration**
```bash
# Check agent appears in dashboard
curl http://10.0.0.60:8000/api/agents

# Should see your agent with status "online"
```

**Step 3: Restart Server**
```bash
# On server
docker restart boz-ripper-server
# OR if running directly:
# pkill -f boz_server
# python -m boz_server.main
```

**Step 4: Agent Re-registers**
- Agent should automatically detect server restart
- Agent re-registers on next heartbeat

**Step 5: Verify Persistence**
```bash
# Check agent still exists
curl http://10.0.0.60:8000/api/agents

# Should show agent (may be "offline" until heartbeat)
```

**✅ Pass:** Agent persists across restart
**❌ Fail:** Agent disappears after restart

---

### Test 3: TV Season Multi-Disc Persistence (10 minutes)

**THIS IS THE CRITICAL TEST - Phase 3 Limitation Fix**

**Step 1: Insert Disc 1**
1. Insert TV show disc (e.g., "Breaking Bad S01 Disc 1")
2. Wait for detection
3. Check dashboard - preview should generate
4. Note the episode numbers assigned (e.g., S01E01-S01E07)

**Step 2: Approve and Rip**
1. Approve preview
2. Start ripping (or just approve - don't need to wait for rip)

**Step 3: Verify Season Tracking**
```bash
# Check TV season exists in database
curl http://10.0.0.60:8000/api/tv-seasons/{season_id}

# season_id format: "breakingbad:s1"
# Should show:
# - last_episode_assigned: 7 (or whatever last episode was)
# - disc_ids: ["disc-uuid"]
```

**Step 4: RESTART SERVER** ⚠️
```bash
docker restart boz-ripper-server
```

**Step 5: Insert Disc 2**
1. Insert next disc (e.g., "Breaking Bad S01 Disc 2")
2. Wait for detection
3. Check dashboard - preview should generate

**Step 6: Verify Episode Continuation** ✨
- Episodes should start from where Disc 1 left off
- If Disc 1 had E01-E07, Disc 2 should have E08+

**✅ Pass:** Episodes continue correctly after server restart
**❌ Fail:** Episodes restart from E01 on Disc 2

**Query database to verify:**
```bash
sqlite3 /data/database/boz_ripper.db

SELECT * FROM tv_seasons;
-- Should show last_episode_assigned = 7 (or last episode from Disc 1)

SELECT * FROM discs WHERE tv_season_id IS NOT NULL ORDER BY detected_at;
-- Should show both discs linked to same season

.exit
```

---

### Test 4: Job Persistence (5 minutes)

**Step 1: Create Jobs**
1. Approve a disc for ripping (creates rip jobs)
2. Let rip complete (creates transcode jobs)
3. Note job IDs from dashboard

**Step 2: Check Job Status**
```bash
curl http://10.0.0.60:8000/api/jobs

# Note:
# - Total number of jobs
# - Job statuses (pending, running, completed)
# - Job IDs
```

**Step 3: Restart Server**
```bash
docker restart boz-ripper-server
```

**Step 4: Verify Jobs Persist**
```bash
curl http://10.0.0.60:8000/api/jobs

# Should show:
# - Same number of jobs
# - Same job statuses
# - Same job IDs
```

**✅ Pass:** All jobs persist with correct status
**❌ Fail:** Jobs disappear or status resets

---

### Test 5: Worker Stats Persistence (3 minutes)

**Step 1: Complete Some Jobs**
- Let worker complete at least 2 transcode jobs
- Note worker stats:
  ```bash
  curl http://10.0.0.60:8000/api/workers/{worker_id}

  # Note: total_jobs_completed
  ```

**Step 2: Restart Server**
```bash
docker restart boz-ripper-server
```

**Step 3: Worker Re-registers**
- Wait for worker heartbeat

**Step 4: Verify Stats Persist**
```bash
curl http://10.0.0.60:8000/api/workers/{worker_id}

# total_jobs_completed should match pre-restart value
```

**✅ Pass:** Worker stats persist
**❌ Fail:** total_jobs_completed resets to 0

---

## Database Inspection

### Connect to Database
```bash
sqlite3 /data/database/boz_ripper.db
```

### Useful Queries

**Show all tables:**
```sql
.tables
```

**Check TV seasons:**
```sql
SELECT
    season_id,
    show_name,
    season_number,
    last_episode_assigned,
    disc_ids
FROM tv_seasons;
```

**Check jobs:**
```sql
SELECT
    job_id,
    job_type,
    status,
    output_name,
    created_at
FROM jobs
ORDER BY created_at DESC
LIMIT 10;
```

**Check agents:**
```sql
SELECT
    agent_id,
    name,
    status,
    last_heartbeat
FROM agents;
```

**Check discs:**
```sql
SELECT
    disc_id,
    disc_name,
    media_type,
    preview_status,
    tv_season_id
FROM discs
ORDER BY detected_at DESC;
```

**Check worker performance:**
```sql
SELECT
    worker_id,
    hostname,
    total_jobs_completed,
    avg_transcode_time_seconds,
    status
FROM workers;
```

### Database Size
```bash
ls -lh /data/database/boz_ripper.db

# Should start small (~100KB)
# Will grow with data (expect ~1MB per 100 jobs)
```

---

## Performance Testing

### Response Time Comparison

**Before restart (in-memory):**
```bash
time curl http://10.0.0.60:8000/api/jobs
```

**After restart (database):**
```bash
time curl http://10.0.0.60:8000/api/jobs
```

**Expected:** Similar response times (< 100ms for normal queries)

### Load Testing

**Create many jobs:**
```bash
# Insert multiple discs rapidly
# Check dashboard remains responsive
```

**Expected:** No significant slowdown with 100+ jobs in database

---

## Troubleshooting

### Database File Not Created

**Check:**
```bash
# Directory exists?
ls -ld /data/database/

# Permissions correct?
ls -l /data/database/
```

**Fix:**
```bash
mkdir -p /data/database
chmod 755 /data/database
```

### "No such table" Errors

**Cause:** Database initialization failed

**Check logs:**
```
grep -i "database" /path/to/server/logs
```

**Fix:**
```bash
# Delete corrupted database
rm /data/database/boz_ripper.db

# Restart server (will recreate)
docker restart boz-ripper-server
```

### Episodes Don't Continue After Restart

**Diagnose:**
```sql
sqlite3 /data/database/boz_ripper.db

-- Check season exists
SELECT * FROM tv_seasons WHERE season_id = 'yourshow:s1';

-- Check last_episode_assigned value
-- Should be > 0 after first disc

-- Check disc linkage
SELECT disc_id, tv_season_id FROM discs
WHERE tv_season_id = 'yourshow:s1';
```

**Possible causes:**
- Season ID mismatch (check show name normalization)
- last_episode_assigned not updated
- New disc detected as different season

### Slow Queries

**Enable SQL logging:**
```bash
# Set environment variable
export BOZ_DATABASE_ECHO=true

# Restart server
```

**Check logs for slow queries**
```
grep "SELECT" /path/to/logs
```

---

## Success Checklist

After running all tests, verify:

- [x] Database file exists and grows
- [ ] Agents persist across restart
- [ ] Workers persist across restart
- [ ] Jobs persist across restart
- [ ] **TV seasons persist and episodes continue** ⭐
- [ ] Disc previews persist
- [ ] Worker stats persist (total_jobs_completed)
- [ ] No significant performance degradation
- [ ] No errors in server logs
- [ ] Dashboard fully functional

## Known Issues

### 1. First Heartbeat After Restart

**Symptom:** Agent/worker shows "offline" briefly after server restart

**Expected Behavior:** Status updates to "online" on first heartbeat (within 30s)

**Not a bug:** This is normal behavior

### 2. Database Locks

**Symptom:** "database is locked" errors under heavy load

**Cause:** SQLite has limited write concurrency

**Mitigation:** Phase 4 uses async operations to minimize lock contention

**Future:** Migrate to PostgreSQL for high concurrency

---

## Next Steps After Testing

If all tests pass:
1. ✅ Mark Phase 4 as production-ready
2. ⬜ Set up database backups
3. ⬜ Monitor database growth
4. ⬜ Plan Phase 4.1 (Alembic migrations)

If tests fail:
1. Document failure scenarios
2. Check server logs for errors
3. Inspect database with sqlite3
4. Report issues for debugging

---

*Testing Guide Version 1.0*
*Last Updated: January 23, 2026*
