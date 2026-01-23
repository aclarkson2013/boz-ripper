# Boz Ripper - Requirements Tracking

Extracted from PRD v2.1 (January 18, 2026)

## Status Legend
- [ ] Not started
- [x] Complete
- [~] Partial/In Progress

---

## 1. Agent Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| A1 | Detect disc insertion within 5 seconds | P0 | [x] |
| A2 | Identify disc type (DVD/Blu-ray) | P0 | [x] |
| A3 | Extract disc name/label | P0 | [x] |
| A4 | Call MakeMKV for track analysis | P0 | [x] |
| A5 | Send track list to server | P0 | [x] |
| A6 | Wait for server approval before ripping | P0 | [ ] |
| A7 | Support multiple disc drives | P1 | [x] |
| A8 | Query server for worker assignment before transcoding | P0 | [ ] |
| A9 | Support "local" mode: transcode then upload final | P0 | [ ] |
| A10 | Support "remote" mode: upload raw for remote transcoding | P0 | [ ] |
| A11 | Act as transcoding worker if configured | P0 | [ ] |
| A12 | Register worker capabilities with server on startup | P0 | [ ] |
| A13 | Send heartbeat to server every 30 seconds | P1 | [x] |
| A14 | Call MakeMKV to rip approved tracks | P0 | [x] |
| A15 | Monitor progress and report to user | P1 | [~] |
| A16 | Upload files via chunked transfer | P0 | [x] |
| A17 | Delete staging files after upload | P0 | [ ] |
| A18 | Auto-eject disc on completion | P1 | [ ] |

---

## 2. Server Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| S1 | Receive track analysis from agent | P0 | [x] |
| S2 | Detect TV show vs movie from disc name | P0 | [ ] |
| S3 | Query TheTVDB for TV show metadata | P0 | [ ] |
| S4 | Query OMDb for movie metadata | P1 | [ ] |
| S5 | Generate preview with proposed filenames | P0 | [ ] |
| S6 | Track multi-disc TV seasons (episode continuation) | P0 | [ ] |
| S7 | Filter extras/bloopers from episodes | P0 | [ ] |
| S8 | Allow user approval/modification of preview | P0 | [ ] |
| S9 | Maintain registry of all workers | P0 | [ ] |
| S10 | Monitor worker health via heartbeats | P0 | [ ] |
| S11 | Assign transcode jobs based on strategy (priority/round-robin/load-balance) | P0 | [ ] |
| S12 | Support worker priorities (1-99) | P0 | [ ] |
| S13 | Handle worker failover automatically | P1 | [ ] |
| S14 | Provide worker management UI | P1 | [ ] |
| S15 | Queue jobs in SQLite database | P0 | [ ] |
| S16 | Process jobs sequentially or parallel (configurable) | P0 | [~] |
| S17 | Receive transcoded files from workers | P0 | [x] |
| S18 | Organize files to network shares | P0 | [~] |
| S19 | Trigger Plex library scan | P1 | [ ] |
| S20 | Send Discord notifications | P1 | [ ] |
| S21 | Web UI dashboard (jobs, workers, previews) | P0 | [x] |

---

## 3. Worker Requirements (NEW in v2.1)

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| W1 | Register with server on startup | P0 | [x] |
| W2 | Report capabilities (NVENC, QSV, CPU, etc.) | P0 | [x] |
| W3 | Poll server for transcode jobs | P0 | [~] |
| W4 | Download raw MKV from server (if remote worker) | P0 | [ ] |
| W5 | Transcode with HandBrake using assigned preset | P0 | [ ] |
| W6 | Upload final file to server (if remote worker) | P0 | [ ] |
| W7 | Report progress to server | P1 | [ ] |
| W8 | Send heartbeat every 30 seconds | P0 | [x] |
| W9 | Handle job cancellation gracefully | P1 | [ ] |
| W10 | Support concurrent jobs (configurable max) | P1 | [x] |

---

## 4. TV Show Handling Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| TV1 | Detect TV show from disc name patterns | P0 | [ ] |
| TV2 | Parse season number from disc name | P0 | [ ] |
| TV3 | Query TheTVDB for episode list | P0 | [ ] |
| TV4 | Match tracks to episodes by duration | P0 | [ ] |
| TV5 | Track disc sequence within season | P0 | [ ] |
| TV6 | Continue episode numbering across discs | P0 | [ ] |
| TV7 | Filter extras using duration + naming patterns | P0 | [ ] |
| TV8 | Generate Plex-compatible filenames | P0 | [ ] |
| TV9 | Support manual episode override | P1 | [ ] |

### Extras Detection Patterns
Tracks matching these patterns should be flagged as extras:
- Duration < 10 minutes (configurable)
- Name contains: "bonus", "extra", "behind", "blooper", "gag", "deleted", "feature", "interview", "trailer", "preview", "promo"
- Significantly different duration from other tracks

---

## 5. Preview/Approval Workflow

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| P1 | Generate preview after disc analysis | P0 | [ ] |
| P2 | Show all tracks with proposed names | P0 | [ ] |
| P3 | Show destination paths | P0 | [ ] |
| P4 | Allow track selection (include/exclude) | P0 | [ ] |
| P5 | Allow filename editing | P1 | [ ] |
| P6 | Allow media type override (movie/TV) | P1 | [ ] |
| P7 | Require explicit approval before ripping | P0 | [ ] |
| P8 | Support auto-approve mode (optional) | P2 | [ ] |

---

## 6. API Endpoints

### 6.1 Worker Management Endpoints (NEW - Not Implemented)

| Endpoint | Method | Status |
|----------|--------|--------|
| `/api/workers/register` | POST | [ ] |
| `/api/workers/{worker_id}/heartbeat` | POST | [ ] |
| `/api/workers` | GET | [ ] |
| `/api/workers/{worker_id}` | GET | [ ] |
| `/api/workers/{worker_id}/update-priority` | POST | [ ] |
| `/api/workers/{worker_id}` | DELETE | [ ] |

### 6.2 Job Assignment Endpoints (NEW - Not Implemented)

| Endpoint | Method | Status |
|----------|--------|--------|
| `/api/jobs/{job_id}/request-worker` | POST | [ ] |
| `/api/workers/{worker_id}/jobs/poll` | POST | [ ] |

### 6.3 Existing Endpoints

| Endpoint | Method | Status |
|----------|--------|--------|
| `/api/agents/register` | POST | [x] |
| `/api/agents/{agent_id}/heartbeat` | POST | [x] |
| `/api/agents` | GET | [x] |
| `/api/discs/detected` | POST | [x] |
| `/api/discs/ejected` | POST | [x] |
| `/api/discs` | GET | [x] |
| `/api/discs/{disc_id}/rip` | POST | [x] |
| `/api/jobs` | GET/POST | [x] |
| `/api/jobs/{job_id}` | GET/PATCH | [x] |
| `/api/jobs/{job_id}/assign` | POST | [x] |
| `/api/jobs/{job_id}/cancel` | POST | [x] |
| `/api/files/upload` | POST | [x] |
| `/api/files/organize/{filename}` | POST | [x] |

---

## 7. Data Models

### 7.1 Worker Schema (NEW - Not Implemented)

```python
class Worker:
    worker_id: str              # "DESKTOP-MAIN-4080"
    worker_type: str            # "agent", "remote", "server"
    hostname: str
    capabilities: {
        "nvenc": bool,
        "nvenc_generation": int,
        "qsv": bool,
        "vaapi": bool,
        "hevc": bool,
        "av1": bool,
        "cpu_threads": int,
        "max_concurrent": int
    }
    priority: int               # 1-99 (1 = highest)
    enabled: bool
    status: str                 # "available", "busy", "offline"
    current_jobs: list[str]
    last_seen: datetime
    total_jobs_completed: int
    avg_transcode_time_seconds: float
```

### 7.2 Job Schema Updates Needed

```python
# NEW fields to add to Job model:
assigned_worker_id: str | None
worker_assigned_at: datetime | None
transcode_mode: str | None      # "local", "remote", "server"
transcode_started_at: datetime | None
transcode_completed_at: datetime | None
transcode_duration_seconds: float | None
```

---

## 8. Configuration Updates Needed

### 8.1 Agent Config - Worker Section (NEW)

```yaml
worker:
  enabled: true
  worker_id: "DESKTOP-MAIN-4080"
  priority: 1
  handbrake:
    path: "C:\\Program Files\\HandBrake\\HandBrakeCLI.exe"
  hardware:
    nvenc: true
    nvenc_device: 0
    qsv: false
    hevc: true
    av1: true
  max_concurrent_jobs: 2
  heartbeat_interval_seconds: 30
```

### 8.2 Server Config - Worker Management (NEW)

```yaml
workers:
  assignment_strategy: "priority"  # priority, round-robin, load-balance
  fallback:
    mode: "next_priority"          # next_priority, queue_and_wait, fail_job
    timeout_seconds: 300
  health_check:
    heartbeat_timeout_seconds: 90
    mark_offline_after_missed: 3
  server_worker:
    enabled: true
    worker_id: "server-cpu-fallback"
    priority: 99
    max_concurrent: 1
```

---

## 9. Implementation Phases

### Phase 1: Web UI Dashboard [COMPLETE]
- [x] Flask dashboard application
- [x] Dashboard home page with stats
- [x] Jobs listing and details
- [x] Agents/Workers status page
- [x] Discs page with title selection
- [x] Docker integration

### Phase 2: Worker System [NEXT]
- [ ] Worker model and database schema
- [ ] Worker registration endpoint
- [ ] Worker heartbeat endpoint
- [ ] Worker capabilities detection (GPU)
- [ ] Worker assignment logic (priority-based)
- [ ] Update agent to register as worker
- [ ] HandBrake integration for transcoding
- [ ] Local vs remote transcode modes

### Phase 3: Preview/Approval Workflow
- [ ] Preview model and generation
- [ ] TV show detection logic
- [ ] TheTVDB integration
- [ ] Extras filtering
- [ ] Preview UI in dashboard
- [ ] Approval API endpoints
- [ ] Agent waits for approval

### Phase 4: TV Show Intelligence
- [ ] Multi-disc season tracking
- [ ] Episode number continuation
- [ ] Duration-based episode matching
- [ ] Season/episode filename generation

### Phase 5: Windows Service
- [ ] Agent as Windows Service
- [ ] Auto-start on boot
- [ ] System tray UI
- [ ] Service management commands

---

## 10. Success Metrics (from PRD)

| Metric | Target | Status |
|--------|--------|--------|
| Transcoding speed (DVD with NVENC) | < 10 min | [ ] |
| Transcoding speed (Blu-ray with NVENC) | < 30 min | [ ] |
| Worker failover time | < 30 seconds | [ ] |
| TV show accuracy | 100% correct numbering | [ ] |
| Agent setup time | < 30 minutes | [ ] |
| Add new worker time | < 10 minutes | [ ] |
| Concurrent ripping stations | 5+ supported | [ ] |

---

## 11. Current Architecture Gap Analysis

### What Exists:
- FastAPI server with basic job queue (in-memory)
- Agent with disc detection and MakeMKV ripping
- Basic dashboard (Flask, separate service)

### What's Missing for PRD Compliance:
1. **Worker System** - Separate from agents, handles transcoding
2. **SQLite Database** - PRD requires persistent storage (S15)
3. **Preview/Approval** - No workflow exists yet
4. **TV Show Intelligence** - No metadata integration
5. **HandBrake Integration** - Agent has stub, not functional
6. **Worker Assignment** - No priority/failover logic

### Key Architectural Decision:
PRD specifies **Agents** (ripping) and **Workers** (transcoding) as separate concepts:
- An agent CAN also be a worker (if GPU available)
- Workers can exist without being agents (remote Proxmox)
- Server can be a fallback worker (CPU only)

---

*Last Updated: January 22, 2026*
