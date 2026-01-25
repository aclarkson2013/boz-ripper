"""File upload and management API endpoints."""

import logging
import re
import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from boz_server.api.deps import ApiKeyDep, NASOrganizerDep, PlexClientDep
from boz_server.core.config import settings

router = APIRouter(prefix="/api/files", tags=["files"])
logger = logging.getLogger(__name__)


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
    """Upload a transcoded file from an agent.

    Args:
        file: The file to upload
        name: Name/identifier for the file
        nas_organizer: NAS organizer service (injected)

    Returns:
        Upload result with file path
    """
    # Ensure output directory exists
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save the uploaded file
    file_path = output_dir / file.filename

    try:
        with open(file_path, "wb") as f:
            # Stream the file in chunks to handle large files
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                f.write(chunk)

        file_size = file_path.stat().st_size
        logger.info(f"File uploaded: {file.filename} ({file_size} bytes)")

        # Parse filename to get metadata
        metadata = parse_tv_filename(file.filename) or parse_movie_filename(file.filename)

        # Auto-organize to NAS if enabled and metadata parsed
        final_path = None
        organized = False

        if metadata and settings.nas_enabled and nas_organizer:
            logger.info(f"Auto-organizing file: {file.filename}")
            logger.info(f"Parsed metadata: {metadata}")

            if metadata["media_type"] == "tv":
                final_path = await nas_organizer.organize_tv_episode(
                    file_path,
                    metadata["show_name"],
                    metadata["season"],
                    metadata["episode"],
                    metadata.get("episode_title"),
                )
                organized = final_path is not None
            elif metadata["media_type"] == "movie":
                final_path = await nas_organizer.organize_movie(
                    file_path,
                    metadata["movie_name"],
                    metadata.get("year"),
                )
                organized = final_path is not None

            if organized:
                logger.info(f"File organized to NAS: {final_path}")
            else:
                logger.warning(f"Failed to organize file to NAS - file remains at {file_path}")
        else:
            logger.info(f"Auto-organization skipped (nas_enabled={settings.nas_enabled}, metadata={'found' if metadata else 'not found'})")

        return {
            "status": "ok",
            "filename": file.filename,
            "name": name,
            "path": str(file_path),
            "final_path": str(final_path) if final_path else str(file_path),
            "size": file_size,
            "organized": organized,
            "metadata": metadata,
        }

    except Exception as e:
        # Clean up partial file on error
        if file_path.exists():
            file_path.unlink()
        logger.error(f"Upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/organize/{filename}")
async def organize_file(
    filename: str,
    name: str,
    media_type: str = "movie",
    year: int | None = None,
    season: int | None = None,
    episode: int | None = None,
    nas_organizer: NASOrganizerDep = None,
    _: ApiKeyDep = None,
) -> dict:
    """Manually organize an uploaded file to the NAS.

    Args:
        filename: Name of the uploaded file
        name: Movie or show name
        media_type: Type of media (movie or tv)
        year: Release year (for movies)
        season: Season number (for TV)
        episode: Episode number (for TV)

    Returns:
        Organization result with final path
    """
    output_dir = Path(settings.output_dir)
    source_file = output_dir / filename

    if not source_file.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    if media_type == "movie":
        final_path = await nas_organizer.organize_movie(source_file, name, year)
    elif media_type == "tv":
        if season is None or episode is None:
            raise HTTPException(
                status_code=400,
                detail="Season and episode required for TV shows"
            )
        final_path = await nas_organizer.organize_tv_episode(
            source_file, name, season, episode
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown media type: {media_type}")

    if final_path:
        return {
            "status": "ok",
            "original_path": str(source_file),
            "final_path": str(final_path),
        }
    else:
        return {
            "status": "error",
            "message": "Failed to organize file - check NAS connection",
            "original_path": str(source_file),
        }


@router.get("")
async def list_files() -> dict:
    """List files in the output directory."""
    output_dir = Path(settings.output_dir)

    if not output_dir.exists():
        return {"files": []}

    files = []
    for f in output_dir.iterdir():
        if f.is_file():
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "modified": f.stat().st_mtime,
            })

    return {"files": files}


@router.delete("/{filename}")
async def delete_file(
    filename: str,
    _: ApiKeyDep = None,
) -> dict:
    """Delete a file from the output directory."""
    output_dir = Path(settings.output_dir)
    file_path = output_dir / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    # Security check - ensure we're not escaping the output directory
    if not file_path.resolve().is_relative_to(output_dir.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path.unlink()

    return {"status": "ok", "deleted": filename}


@router.get("/plex/status")
async def plex_status(
    nas_organizer: NASOrganizerDep,
    plex_client: PlexClientDep,
) -> dict:
    """Get Plex integration status.

    S19: Used to verify Plex connection and get library configuration.
    """
    nas_status = nas_organizer.get_status()
    plex_status = nas_status.get("plex", {})

    return {
        "enabled": plex_status.get("enabled", False) if plex_status else False,
        "available": plex_status.get("available", False) if plex_status else False,
        "url": plex_status.get("url") if plex_status else None,
        "movie_library_id": plex_status.get("movie_library_id") if plex_status else None,
        "tv_library_id": plex_status.get("tv_library_id") if plex_status else None,
    }


@router.get("/plex/libraries")
async def plex_libraries(
    plex_client: PlexClientDep,
) -> dict:
    """List Plex libraries.

    S19: Useful for finding library section IDs during setup.
    """
    if not plex_client:
        return {"libraries": [], "message": "Plex not configured"}

    libraries = await plex_client.get_libraries()
    return {"libraries": libraries}


@router.post("/plex/scan/{media_type}")
async def trigger_plex_scan(
    media_type: str,
    plex_client: PlexClientDep,
    path: str | None = None,
    _: ApiKeyDep = None,
) -> dict:
    """Manually trigger a Plex library scan.

    Args:
        media_type: Type of media ("movie" or "tv")
        path: Optional specific path to scan

    S19: Manual scan trigger for testing or recovery.
    """
    if not plex_client:
        raise HTTPException(status_code=503, detail="Plex not configured")

    if media_type == "movie":
        success = await plex_client.scan_movie_library(path)
    elif media_type == "tv":
        success = await plex_client.scan_tv_library(path)
    else:
        raise HTTPException(status_code=400, detail="media_type must be 'movie' or 'tv'")

    if success:
        return {"status": "ok", "message": f"Plex {media_type} library scan triggered"}
    else:
        return {"status": "error", "message": "Scan not triggered - check Plex configuration"}
