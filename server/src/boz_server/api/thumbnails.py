"""Thumbnail serving API endpoints."""

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from boz_server.api.deps import ThumbnailStorageDep

router = APIRouter(prefix="/api/thumbnails", tags=["thumbnails"])
logger = logging.getLogger(__name__)


@router.get("/{disc_id}/{filename}")
async def get_thumbnail(
    disc_id: str,
    filename: str,
    thumbnail_storage: ThumbnailStorageDep,
) -> Response:
    """
    Get a thumbnail image.

    Args:
        disc_id: Disc ID
        filename: Thumbnail filename

    Returns:
        JPEG image response
    """
    # Security: validate filename format
    if not filename.endswith(".jpg") or ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    image_data = thumbnail_storage.get_thumbnail(disc_id, filename)

    if image_data is None:
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    return Response(
        content=image_data,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
        },
    )


@router.get("/{disc_id}")
async def list_disc_thumbnails(
    disc_id: str,
    thumbnail_storage: ThumbnailStorageDep,
) -> dict:
    """
    Get info about thumbnails for a disc.

    Args:
        disc_id: Disc ID

    Returns:
        Thumbnail count and info
    """
    count = thumbnail_storage.get_disc_thumbnail_count(disc_id)
    return {
        "disc_id": disc_id,
        "thumbnail_count": count,
    }


@router.delete("/{disc_id}")
async def delete_disc_thumbnails(
    disc_id: str,
    thumbnail_storage: ThumbnailStorageDep,
) -> dict:
    """
    Delete all thumbnails for a disc.

    Args:
        disc_id: Disc ID

    Returns:
        Deletion status
    """
    success = thumbnail_storage.delete_disc_thumbnails(disc_id)
    return {
        "disc_id": disc_id,
        "deleted": success,
    }
