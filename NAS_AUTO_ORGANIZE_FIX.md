# NAS Auto-Organization Fix

## Problem

Transcode jobs complete successfully and files are uploaded to the server, but they never appear on the QNAP NAS at `/mnt/qnap-plex/`.

**Current workflow:**
1. ✅ Agent transcodes file
2. ✅ Agent uploads file to server → saved to `/data/output`
3. ❌ File never organized to NAS
4. ❌ No Plex library scan triggered

## Root Cause

1. **NAS not mounted**: Docker container didn't have `/mnt/qnap-plex/` mounted
2. **NAS disabled**: `BOZ_NAS_ENABLED=false` in environment
3. **No auto-organization**: Upload endpoint saves file but doesn't organize it
4. **Missing organize call**: Agent doesn't call `/api/files/organize` endpoint

## Solution

### Part 1: Configure NAS Mount (✅ DONE)

1. **Updated `.env` file:**
   ```env
   BOZ_NAS_ENABLED=true
   BOZ_NAS_MOVIE_PATH=Movies
   BOZ_NAS_TV_PATH=TV Shows
   ```

2. **Updated `docker-compose.yml`:**
   ```yaml
   volumes:
     - /mnt/qnap-plex:/nas:rw
   ```

3. **Restarted server** to pick up NAS mount

### Part 2: Auto-Organization (IN PROGRESS)

Update the upload endpoint to automatically organize files:

1. **Parse filename** to extract metadata:
   - TV: `Show Name - S01E01 - Episode Title.mkv` → `{show, season, episode, title}`
   - Movie: `Movie Name (2023).mkv` → `{movie, year}`

2. **Call NAS organizer** automatically after upload

3. **Return final path** to agent for logging

### Part 3: Add Metadata to Upload

The agent currently only sends `name` (output_name) to the upload endpoint. The filename should already contain all needed metadata in Plex format.

**Example filenames:**
- TV: `The Office - S01E01 - Pilot.mkv`
- Movie: `The Shawshank Redemption (1994).mkv`

## Implementation

### Updated Upload Endpoint

```python
import re
from pathlib import Path

def parse_tv_filename(filename: str) -> dict | None:
    """Parse TV show filename: 'Show Name - S01E02 - Episode Title.mkv'"""
    pattern = r"^(.+?) - S(\d+)E(\d+)(?: - (.+?))?\.(\w+)$"
    match = re.match(pattern, filename)
    if match:
        return {
            "media_type": "tv",
            "show_name": match.group(1),
            "season": int(match.group(2)),
            "episode": int(match.group(3)),
            "episode_title": match.group(4),
            "extension": match.group(5),
        }
    return None

def parse_movie_filename(filename: str) -> dict | None:
    """Parse movie filename: 'Movie Name (Year).mkv'"""
    pattern = r"^(.+?)(?: \((\d{4})\))?\.(\w+)$"
    match = re.match(pattern, filename)
    if match:
        return {
            "media_type": "movie",
            "movie_name": match.group(1),
            "year": int(match.group(2)) if match.group(2) else None,
            "extension": match.group(3),
        }
    return None

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    name: str = Form(...),
    nas_organizer: NASOrganizerDep = None,
    _: ApiKeyDep = None,
) -> dict:
    # 1. Save file to output_dir
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / file.filename

    # Stream file to disk
    with open(file_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    # 2. Parse filename to get metadata
    metadata = parse_tv_filename(file.filename) or parse_movie_filename(file.filename)

    # 3. Auto-organize to NAS if enabled and metadata parsed
    final_path = None
    if metadata and settings.nas_enabled and nas_organizer:
        if metadata["media_type"] == "tv":
            final_path = nas_organizer.organize_tv_episode(
                file_path,
                metadata["show_name"],
                metadata["season"],
                metadata["episode"],
                metadata.get("episode_title"),
            )
        elif metadata["media_type"] == "movie":
            final_path = nas_organizer.organize_movie(
                file_path,
                metadata["movie_name"],
                metadata.get("year"),
            )

    # 4. Return result
    return {
        "status": "ok",
        "filename": file.filename,
        "name": name,
        "uploaded_path": str(file_path),
        "final_path": str(final_path) if final_path else None,
        "organized": final_path is not None,
        "metadata": metadata,
    }
```

## Testing

After implementing:

1. **Complete a transcode job**
2. **Check agent logs** for:
   - `file_uploaded`
   - `upload_completed`

3. **Check server logs** for:
   - `Moving {source} to {dest}`
   - Final NAS path

4. **Verify file on NAS**:
   ```bash
   ls -la /mnt/qnap-plex/TV\ Shows/The\ Office/Season\ 01/
   ```

5. **Trigger Plex scan** (future enhancement):
   - Add Plex API integration
   - Call scan after organizing files

## Files to Modify

- `server/src/boz_server/api/files.py` - Update upload endpoint
- `.env` - ✅ Added NAS configuration
- `docker-compose.yml` - ✅ Added NAS volume mount

## Future Enhancements

1. **Plex Library Scan**: Call Plex API after organizing
2. **Batch Organization**: Organize multiple files at once
3. **Retry Logic**: Retry failed NAS operations
4. **Cleanup**: Delete source files after successful organization
5. **Notifications**: Notify user when files are organized
