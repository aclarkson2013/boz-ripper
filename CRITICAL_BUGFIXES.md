# Critical Bug Fixes - Episode Re-insertion & File Path Issues

## Summary

Fixed two critical bugs that occurred when re-inserting the same disc:
1. **Episode numbering bug**: Episodes detected as E13-E18 instead of E01-E06
2. **File path mismatch**: Transcode jobs failing with "Input file not found"

## Bug #1: Episode Re-insertion Numbering

### Problem

When the same disc was ejected and re-inserted, the system detected episodes 13-18 instead of 1-6, all with Low (30%) confidence.

**Example:**
- First insertion: Correctly detected E01-E06
- Eject and re-insert same disc
- Second detection: Incorrectly detected E13-E18

### Root Cause

The `TVSeason` tracker persists in memory and continues the episode counter across disc re-insertions. The system couldn't distinguish between:
- **Re-insertion**: Same disc ejected and re-inserted (should reset to E01)
- **Continuation**: Next disc in a multi-disc season (should continue counting)

Original logic tracked by `disc_id`, but disc IDs change after eject/reinsert because:
1. Disc ejected → disc.status = "ejected"
2. Disc re-inserted → `get_disc_by_agent_drive` filters out ejected discs
3. System creates NEW disc with NEW disc_id
4. TVSeason tracker sees new disc_id and treats it as continuation

### Fix

**Changed detection strategy from disc_id to disc_name:**

1. Added `last_disc_name` field to `TVSeason` model to track the last processed disc
2. Updated `PreviewGenerator` to detect re-insertions by comparing disc names:
   - If `disc_name == last_disc_name` → Re-insertion, reset episode counter to 0
   - If `disc_name != last_disc_name` → Continuation, keep counting

**Files Changed:**
- `server/src/boz_server/models/tv_show.py` - Added `last_disc_name` field
- `server/src/boz_server/services/preview_generator.py` - Updated re-insertion detection logic

**New Logging:**
```
Disc 'OFFICE' was already processed for season theoffice:s1
This appears to be a re-insertion - resetting episode counter to 1
Season tracker: theoffice:s1 (last_episode: 0, disc_count: 1, last_disc: OFFICE)
```

## Bug #2: Transcode File Path Mismatch

### Problem

Transcode jobs failing with error:
```
RuntimeError: Input file not found: /path/to/F1_t00.mkv
```

While rip jobs created files like `G2_t05.mkv` instead of `F1_t00.mkv`.

### Root Cause

**Aggressive temp file cleanup in MakeMKV service:**

```python
# OLD CODE - BUGGY
for old_mkv in output_dir.glob("*.mkv"):
    old_mkv.unlink()  # Deletes ALL .mkv files before ripping!
```

**The Problem Flow:**
1. First insertion: Rip creates `F1_t00.mkv` → Transcode job queued with `input_file=F1_t00.mkv`
2. User ejects and re-inserts disc (e.g., to rip a different title)
3. Second rip starts: **Cleanup code deletes `F1_t00.mkv`** before it can be transcoded!
4. MakeMKV creates new file `G2_t05.mkv` (different disc identifier from MakeMKV)
5. Transcode job tries to find `F1_t00.mkv` → **File not found!**

**Why disc identifiers changed (F1 → G2):**
- MakeMKV uses its own internal disc identifiers (F1, G2, etc.)
- These identifiers are assigned based on disc insertion order and internal state
- Not stable across eject/reinsert cycles
- Files are named like `{disc_id}_t{title_index}.mkv`

### Fix

**Removed aggressive cleanup code:**

```python
# NEW CODE - FIXED
# NOTE: Don't clean up existing MKV files here!
# Previous versions deleted all .mkv files to avoid overwrite prompts,
# but this would delete files that were ripped but not yet transcoded.
# MakeMKV will handle overwrites itself or use unique filenames.
```

**Files Changed:**
- `agent/src/boz_agent/services/makemkv.py` - Removed cleanup loop that deleted .mkv files

**Why This Is Safe:**
- MakeMKV will handle file overwrites automatically
- MakeMKV assigns unique disc identifiers (F1, F2, G1, G2, etc.)
- Existing files from previous rips won't conflict with new rips
- Temp directory can be cleaned up manually if it grows too large

## Testing

### Test Case 1: Episode Re-insertion

**Steps:**
1. Insert "OFFICE" disc (or any TV show disc)
2. Wait for preview generation
3. Verify episodes detected as E01-E06 (or appropriate range)
4. Eject disc
5. Re-insert same disc
6. Wait for preview generation

**Expected Result:**
- Episodes should again be detected as E01-E06 (same as first insertion)
- Confidence scores should be High (90%) if TheTVDB metadata matches
- Logs should show: "This appears to be a re-insertion - resetting episode counter to 1"

### Test Case 2: Multi-Disc Season

**Steps:**
1. Insert "Show S01 Disc 1"
2. Verify episodes E01-E06 (example)
3. Eject disc
4. Insert "Show S01 Disc 2" (different name!)
5. Wait for preview generation

**Expected Result:**
- Disc 2 should continue from E07 (not reset to E01)
- Logs should show: "Continuation from previous disc 'Show S01 Disc 1', starting from episode 7"

### Test Case 3: File Path Persistence

**Steps:**
1. Insert disc and rip a title
2. Verify transcode job is created
3. Eject and re-insert disc
4. Rip another title
5. Check if first transcode job can still find its input file

**Expected Result:**
- First transcode job should still have access to its input file
- Both files should exist in temp directory
- No "Input file not found" errors

## Rebuild Instructions

To apply these fixes:

```bash
# Windows
rebuild.bat

# Linux/Mac
./rebuild.sh
```

Or manually:
```bash
docker compose down
docker compose build --no-cache server agent
docker compose up -d
```

## Verification

After rebuilding, watch the logs during disc re-insertion:

```bash
docker compose logs -f server | grep -A 30 "PREVIEW GENERATION"
```

Look for:
- "This appears to be a re-insertion - resetting episode counter to 1"
- Episode numbers should be E01-E06 (not E13-E18)
- No "Input file not found" errors in agent logs

## Future Improvements

### Episode Tracking
- Consider adding a "Reset Season" button in the UI for manual resets
- Add option to manually override episode numbers in preview page
- Store season state in database instead of in-memory (survives server restarts)

### File Management
- Implement proper temp file lifecycle management
- Move ripped files to permanent storage immediately after ripping
- Add cleanup job for old temp files (only delete files with no pending transcode jobs)
- Consider using subdirectories per disc to avoid naming conflicts

## Related Files

**Episode Re-insertion Fix:**
- `server/src/boz_server/models/tv_show.py`
- `server/src/boz_server/services/preview_generator.py`

**File Path Fix:**
- `agent/src/boz_agent/services/makemkv.py`

**Related Documentation:**
- `EPISODE_MATCHING_FIX.md` - Previous fix for sequential matching
- `PHASE3_IMPLEMENTATION.md` - Overall Phase 3 implementation details
