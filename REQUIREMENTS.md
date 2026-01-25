# Boz Ripper - Requirements Tracking

Extracted from PRD v2.1 (January 18, 2026)

## Status Legend
- [ ] Not started
- [x] Complete
- [~] Partial/In Progress

---

## 🚨 CRITICAL ISSUES (P0 - Must Fix First)

| ID | Issue | Description | Status |
|----|-------|-------------|--------|
| C1 | Movie Detection & Title Matching | Movies have poor detection/naming. Disc labels are often vague ("MOVIE", studio codes). Need OMDb/TMDb integration to match disc names to actual movie titles and generate proper filenames like "The Dark Knight (2008).mkv". Improve TV vs Movie heuristics using track count, duration patterns, and disc structure. | [x] |
| C2 | Video Preview/Verification | Two-stage preview system: Stage 2 (post-rip FFmpeg thumbnails from MKV files) is critical for verifying episode-to-title mapping before transcoding. Stage 1 (pre-rip VLC thumbnails from encrypted disc) is a future enhancement. | [x] |

### C1 - Movie Detection Implementation Plan [COMPLETE ✅]
- [x] Improve TV vs Movie heuristics (track count, duration patterns, disc structure)
- [x] Add OMDb API integration (API key configured)
- [x] Implement fuzzy search for disc names that don't match exactly
- [x] Fall back to user confirmation if confidence < 80%
- [x] Generate proper movie filenames: "Movie Title (Year).mkv"

### C2 - Video Preview Implementation Plan (Two-Stage System)

**Problem:** FFmpeg cannot read encrypted DVDs directly (error code 4294967294). Only MakeMKV can decrypt protected content.

**Solution:** Two-stage preview system that provides visual verification at both pre-rip and pre-transcode stages.

#### Stage 2: Post-Rip Preview (PRIORITY - Implement First) [COMPLETE]
**When:** After ripping completes, before user approves transcode
**Goal:** Detailed visual verification with episode name matching
**Method:** FFmpeg extracts 4 thumbnails per ripped MKV file

- [x] Extract thumbnails from ripped MKV files in staging directory
- [x] Send thumbnails to server with rip completion notification
- [x] Display 2x2 thumbnail grid in transcode approval modal
- [x] Add file renaming capability if episode detection was wrong
- [x] Add episode number adjustment UI for TV shows
- [x] Clean up thumbnails after transcode approval/rejection

**FFmpeg Command:**
```bash
ffmpeg -ss <timestamp> -i <ripped_mkv_file> -frames:v 1 -q:v 2 -vf scale=320:-1 -y thumb.jpg
```

**Timestamps:** 0:30, 2:00, 5:00, 50% through

#### Stage 1: Initial Preview (FUTURE ENHANCEMENT)
**When:** During disc detection, before user approves rip
**Goal:** Quick visual confirmation to help user select which titles to rip
**Method:** VLC headless mode extracts 1 thumbnail per title from encrypted DVD

- [ ] Use VLC to extract single frame at 30 seconds per title
- [ ] Display thumbnail in initial preview page
- [ ] Fallback gracefully if VLC not available

**VLC Command (Windows):**
```bash
vlc dvd:///I:/#<title_index> --video-filter=scene --scene-format=jpg --scene-ratio=1 --run-time=30 --play-and-exit
```

#### Why Two Stages?
| Stage | Purpose | Thumbnails | Works On |
|-------|---------|------------|----------|
| Stage 1 (Pre-Rip) | Quick title selection | 1 per title | Encrypted DVD (VLC) |
| Stage 2 (Post-Rip) | Episode verification | 4 per title | Ripped MKV (FFmpeg) |

Stage 2 is critical because:
- Prevents wasting 20+ minute transcode on mismatched content
- Works perfectly with unencrypted MKV files
- Allows user to fix episode names/numbers before committing

### VLC1 - Full Video Preview Feature [COMPLETE]

**Purpose:** Allow users to preview full video files with VLC Media Player before approving transcodes. This addresses the limitation of thumbnail-only previews for verifying content (especially for 40GB+ Blu-ray files).

**Architecture:** Command Relay via Polling
- Dashboard requests VLC preview via server API
- Server queues command for the target agent
- Agent picks up command on next poll cycle (within 5 seconds)
- Agent launches VLC with the file path as a detached process
- Agent reports completion to server

**Implementation:**
- [x] VLC detector service (checks Windows registry and common paths)
- [x] VLC launcher service (launches VLC as detached process)
- [x] VLC config in agent settings (enabled, executable path, fullscreen)
- [x] Worker capabilities extended with vlc_installed, vlc_path, vlc_version
- [x] VLC command database model (vlc_commands table)
- [x] Server VLC API endpoints (/api/vlc/preview, /api/vlc/commands)
- [x] Agent polls for VLC commands in job runner loop
- [x] Dashboard "Preview with VLC" button in transcode approval modal

**Agent Config:**
```yaml
vlc:
  enabled: true                    # Enable VLC preview feature
  executable: null                 # Auto-detected, or specify path
  fullscreen: true                 # Open VLC in fullscreen mode
```

**Dashboard UI:**
- VLC preview button appears in transcode approval modal
- If VLC is installed on agent: Shows "Preview with VLC" button
- If VLC is not installed: Shows disabled button + "Get VLC" download link

---

## 1. Agent Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| A1 | Detect disc insertion within 5 seconds | P0 | [x] |
| A2 | Identify disc type (DVD/Blu-ray) | P0 | [x] |
| A3 | Extract disc name/label | P0 | [x] |
| A4 | Call MakeMKV for track analysis | P0 | [x] |
| A5 | Send track list to server | P0 | [x] |
| A6 | Wait for server approval before ripping | P0 | [x] |
| A7 | Support multiple disc drives | P1 | [x] |
| A8 | Query server for worker assignment before transcoding | P0 | [x] |
| A9 | Support "local" mode: transcode then upload final | P0 | [x] |
| A10 | Support "remote" mode: upload raw for remote transcoding | P0 | [ ] |
| A11 | Act as transcoding worker if configured | P0 | [x] |
| A12 | Register worker capabilities with server on startup | P0 | [x] |
| A13 | Send heartbeat to server every 30 seconds | P1 | [x] |
| A14 | Call MakeMKV to rip approved tracks | P0 | [x] |
| A15 | Monitor progress and report to user | P1 | [x] |
| A16 | Upload files via chunked transfer | P0 | [x] |
| A17 | Delete staging files after upload | P0 | [x] |
| A18 | Auto-eject disc on completion | P1 | [x] |

---

## 2. Server Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| S1 | Receive track analysis from agent | P0 | [x] |
| S2 | Detect TV show vs movie from disc name | P0 | [x] |
| S3 | Query TheTVDB for TV show metadata | P0 | [x] |
| S4 | Query OMDb for movie metadata | P1 | [x] |
| S5 | Generate preview with proposed filenames | P0 | [x] |
| S6 | Track multi-disc TV seasons (episode continuation) | P0 | [x] |
| S7 | Filter extras/bloopers from episodes | P0 | [x] |
| S8 | Allow user approval/modification of preview | P0 | [x] |
| S9 | Maintain registry of all workers | P0 | [x] |
| S10 | Monitor worker health via heartbeats | P0 | [x] |
| S11 | Assign transcode jobs based on strategy (priority/round-robin/load-balance) | P0 | [x] |
| S12 | Support worker priorities (1-99) | P0 | [x] |
| S13 | Handle worker failover automatically | P1 | [x] |
| S14 | Provide worker management UI | P1 | [x] |
| S15 | Queue jobs in SQLite database | P0 | [x] |
| S16 | Process jobs sequentially or parallel (configurable) | P0 | [x] |
| S17 | Receive transcoded files from workers | P0 | [x] |
| S18 | Organize files to network shares | P0 | [x] |
| S19 | Trigger Plex library scan | P1 | [x] |
| S20 | Send Discord notifications | P1 | [x] |
| S21 | Web UI dashboard (jobs, workers, previews) | P0 | [x] |

---

## 3. Worker Requirements (NEW in v2.1)

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| W1 | Register with server on startup | P0 | [x] |
| W2 | Report capabilities (NVENC, QSV, CPU, etc.) | P0 | [x] |
| W3 | Poll server for transcode jobs | P0 | [x] |
| W4 | Download raw MKV from server (if remote worker) | P0 | [ ] |
| W5 | Transcode with HandBrake using assigned preset | P0 | [x] |
| W6 | Upload final file to server (if remote worker) | P0 | [~] |
| W7 | Report progress to server | P1 | [x] |
| W8 | Send heartbeat every 30 seconds | P0 | [x] |
| W9 | Handle job cancellation gracefully | P1 | [x] |
| W10 | Support concurrent jobs (configurable max) | P1 | [x] |

---

## 4. TV Show Handling Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| TV1 | Detect TV show from disc name patterns | P0 | [x] |
| TV2 | Parse season number from disc name | P0 | [x] |
| TV3 | Query TheTVDB for episode list | P0 | [x] |
| TV4 | Match tracks to episodes by duration | P0 | [x] |
| TV5 | Track disc sequence within season | P0 | [x] |
| TV6 | Continue episode numbering across discs | P0 | [x] |
| TV7 | Filter extras using duration + naming patterns | P0 | [x] |
| TV8 | Generate Plex-compatible filenames | P0 | [x] |
| TV9 | Support manual episode override | P1 | [x] |

### Extras Detection Patterns
Tracks matching these patterns should be flagged as extras:
- Duration < 10 minutes (configurable)
- Name contains: "bonus", "extra", "behind", "blooper", "gag", "deleted", "feature", "interview", "trailer", "preview", "promo"
- Significantly different duration from other tracks

---

## 5. Preview/Approval Workflow [IMPLEMENTED - Phase 3]

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| P1 | Generate preview after disc analysis | P0 | [x] |
| P2 | Show all tracks with proposed names | P0 | [x] |
| P3 | Show destination paths | P0 | [x] |
| P4 | Allow track selection (include/exclude) | P0 | [x] |
| P5 | Allow filename editing | P1 | [x] |
| P6 | Allow media type override (movie/TV) | P1 | [x] |
| P7 | Require explicit approval before ripping | P0 | [x] |
| P8 | Support auto-approve mode (optional) | P2 | [x] |

### 5.1 Transcode Approval Workflow [IMPLEMENTED]

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| TA1 | Transcode jobs wait for user approval | P0 | [x] |
| TA2 | User selects worker for transcoding | P0 | [x] |
| TA3 | User selects preset for transcoding | P0 | [x] |
| TA4 | Dashboard shows "Awaiting Approval" section | P0 | [x] |
| TA5 | Approval modal with worker/preset selection | P0 | [x] |
| TA6 | Show file size and source disc name | P1 | [x] |
| TA7 | Show upload errors for manual retry | P1 | [x] |
| TA8 | Display 2x2 thumbnail grid per job (Stage 2 preview) | P0 | [x] |
| TA9 | Allow file renaming before transcode | P1 | [x] |
| TA10 | Allow episode number adjustment (TV shows) | P1 | [x] |

---

## 6. API Endpoints

### 6.1 Worker Management Endpoints

| Endpoint | Method | Status |
|----------|--------|--------|
| `/api/workers/register` | POST | [x] |
| `/api/workers/{worker_id}/heartbeat` | POST | [x] |
| `/api/workers` | GET | [x] |
| `/api/workers/{worker_id}` | GET | [x] |
| `/api/workers/stats` | GET | [x] |
| `/api/workers/{worker_id}/update-priority` | POST | [ ] |
| `/api/workers/{worker_id}` | DELETE | [ ] |

### 6.2 Job Assignment/Approval Endpoints

| Endpoint | Method | Status |
|----------|--------|--------|
| `/api/jobs/{job_id}/approve` | POST | [x] |
| `/api/jobs/awaiting-approval` | GET | [x] |
| `/api/jobs/presets` | GET | [x] |
| `/api/jobs/upload-errors` | GET | [x] |
| `/api/jobs/stats` | GET | [x] |
| `/api/jobs/pending` | GET | [x] |

### 6.3 VLC Preview Endpoints (NEW)

| Endpoint | Method | Status |
|----------|--------|--------|
| `/api/vlc/preview` | POST | [x] |
| `/api/vlc/commands/{agent_id}` | GET | [x] |
| `/api/vlc/commands/{command_id}/complete` | POST | [x] |
| `/api/vlc/commands/{command_id}/status` | GET | [x] |

### 6.4 Existing Endpoints

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

### 7.1 Worker Schema [IMPLEMENTED]

```python
class Worker:
    worker_id: str              # "DESKTOP-MAIN-4080"
    worker_type: WorkerType     # "agent", "remote", "server"
    hostname: str
    capabilities: WorkerCapabilities  # nvenc, qsv, hevc, av1, cpu_threads, max_concurrent
    priority: int               # 1-99 (1 = highest)
    enabled: bool
    status: WorkerStatus        # "available", "busy", "offline"
    current_jobs: list[str]
    last_seen: datetime
    total_jobs_completed: int
    agent_id: str | None        # Links worker to agent for job assignment
```

### 7.2 Job Schema Updates [PARTIALLY IMPLEMENTED]

```python
# Implemented fields:
requires_approval: bool = False     # [x] Transcode jobs wait for approval
source_disc_name: str | None        # [x] Original disc name for display
input_file_size: int | None         # [x] File size for display
assigned_agent_id: str | None       # [x] Agent assigned to execute job
preset: str | None                  # [x] Transcoding preset selected by user

# NOT YET implemented:
transcode_mode: str | None          # [ ] "local", "remote", "server"
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

### Phase 2: Worker System [MOSTLY COMPLETE]
- [x] Worker model and database schema
- [x] Worker registration endpoint
- [x] Worker heartbeat endpoint
- [x] Worker capabilities detection (GPU)
- [x] Worker assignment logic (priority-based via approval)
- [x] Update agent to register as worker
- [x] HandBrake integration for transcoding
- [x] Local transcode mode (agent transcodes locally, uploads result)
- [ ] Remote transcode mode (A10, W4, W6) - upload raw, remote worker downloads/transcodes/uploads

### Phase 2.5: Transcode Approval Workflow [COMPLETE]
- [x] Jobs require user approval before transcoding
- [x] User selects worker and preset via dashboard
- [x] Approval modal with worker/preset dropdowns
- [x] Jobs awaiting approval section in dashboard
- [x] Approve endpoint assigns job to selected worker
- [x] Upload error visibility and retry mechanism
- [x] Agent links worker to agent_id for job assignment

### Phase 3: Preview/Approval Workflow [COMPLETE ✅]
- [x] Preview model and generation (for rip track selection)
- [x] TV show detection logic
- [x] TheTVDB integration
- [x] Extras filtering
- [x] Preview UI in dashboard
- [x] Approval API endpoints for rip workflow
- [x] Agent waits for approval before ripping

### Phase 4: SQLite Database Migration [COMPLETE ✅]
- [x] Database schema design
- [x] SQLite setup with SQLAlchemy ORM
- [x] Migrate Job model to persistent storage
- [x] Migrate Worker/Agent registries
- [x] Migrate Disc tracking
- [x] Migrate TVSeason cache (enables multi-disc across restarts)
- [x] Update all service layers for database queries
- [x] Repository layer with Pydantic ↔ ORM conversion
- [x] Set up Alembic migrations (Phase 4.1)
- [ ] End-to-end testing (REQUIRED BEFORE PRODUCTION)

### Phase 5: File Organization [COMPLETE ✅]
- [x] Complete file organization to network shares (S18)
- [x] Plex library scan integration (S19)
- [x] Auto-cleanup of staging files (A17)
- [x] Auto-eject disc on completion (A18)

### Phase 6: Remote Transcode Mode [NOT STARTED]
- [ ] Remote worker raw file upload (A10)
- [ ] Remote worker file download from server (W4)
- [ ] Remote worker result upload (W6)

### Phase 7: Windows System Tray Launcher [COMPLETE ✅]
- [x] System tray application with status indicator (green/red/yellow/blue)
- [x] Start/Stop/Restart agent controls
- [x] Auto-start agent when launcher runs
- [x] Single-instance protection (prevents multiple launchers/agents)
- [x] Health monitoring with crash detection and notification
- [x] Git-based update checking and auto-pull
- [x] Dashboard quick access button
- [x] Log file viewer
- [x] PyInstaller build configuration for standalone .exe
- [ ] Auto-start launcher on Windows boot (requires manual setup: add to Startup folder or Task Scheduler)

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
- FastAPI server with job queue (in-memory)
- Agent with disc detection and MakeMKV ripping
- Flask dashboard (separate service) with full job/worker management
- Worker system with registration, heartbeat, capabilities
- HandBrake transcoding integration (local mode)
- Transcode approval workflow (user selects worker + preset)
- Upload with retry logic and error visibility

### What's Complete:

**Core Features:**
1. ~~**Movie Detection & Matching**~~ - **COMPLETE** (OMDb integration working)
2. ~~**Video Preview/Verification**~~ - **COMPLETE** (Stage 2 post-rip thumbnails with 2x2 grid)
3. ~~**Worker System**~~ - **COMPLETE** (agents register as workers)
4. ~~**SQLite Database**~~ - **COMPLETE** (Phase 4 - persistent storage with Alembic migrations)
5. ~~**Rip Preview/Approval**~~ - **COMPLETE** (Phase 3)
6. ~~**TV Show Intelligence**~~ - **COMPLETE** (TheTVDB integration, episode matching, multi-disc tracking)
7. ~~**HandBrake Integration**~~ - **COMPLETE** (local transcode working)
8. ~~**Worker Assignment**~~ - **COMPLETE** (priority-based via approval, with failover S13)
9. ~~**Disc Name Cleanup**~~ - **COMPLETE** (auto-detect TV vs movie with TheTVDB)
10. ~~**Plex Integration**~~ - **COMPLETE** (S19: Trigger library scan after organize)
11. ~~**File Organization**~~ - **COMPLETE** (S18: Auto-organize to network shares with Plex trigger)
12. ~~**Staging Cleanup**~~ - **COMPLETE** (A17: Delete temp files after upload)
13. ~~**Auto-eject**~~ - **COMPLETE** (A18: Eject disc on completion)
14. ~~**Discord Notifications**~~ - **COMPLETE** (S20: Webhook notifications)
15. ~~**Windows System Tray Launcher**~~ - **COMPLETE** (Phase 7)
16. ~~**Media Type Override**~~ - **COMPLETE** (P6: Switch movie ↔ TV with TheTVDB re-lookup)
17. ~~**VLC Preview**~~ - **COMPLETE** (VLC1: Full video preview on agent via command relay)

**Still Needed:**
18. **Remote Transcode Mode** - Workers downloading/uploading raw files (A10, W4, W6)
19. **Minor API Endpoints** - Worker priority update and delete endpoints

### Key Architectural Decision:
PRD specifies **Agents** (ripping) and **Workers** (transcoding) as separate concepts:
- An agent CAN also be a worker (if GPU available) - **IMPLEMENTED**
- Workers can exist without being agents (remote Proxmox) - Not yet
- Server can be a fallback worker (CPU only) - Not yet

---

*Last Updated: January 25, 2026 - VLC preview feature (VLC1) for full video preview before transcode approval*
