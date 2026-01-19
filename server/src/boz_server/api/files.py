"""File upload and management API endpoints."""

import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from boz_server.api.deps import ApiKeyDep, NASOrganizerDep
from boz_server.core.config import settings

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    name: str = Form(...),
    media_type: str = Form("movie"),  # movie or tv
    _: ApiKeyDep = None,
) -> dict:
    """Upload a transcoded file from an agent.

    Args:
        file: The file to upload
        name: Name/identifier for the file
        media_type: Type of media (movie or tv)

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

        return {
            "status": "ok",
            "filename": file.filename,
            "name": name,
            "path": str(file_path),
            "size": file_size,
            "media_type": media_type,
        }

    except Exception as e:
        # Clean up partial file on error
        if file_path.exists():
            file_path.unlink()
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
    """Organize an uploaded file to the NAS.

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
        final_path = nas_organizer.organize_movie(source_file, name, year)
    elif media_type == "tv":
        if season is None or episode is None:
            raise HTTPException(
                status_code=400,
                detail="Season and episode required for TV shows"
            )
        final_path = nas_organizer.organize_tv_episode(
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
