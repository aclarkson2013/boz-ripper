"""API dependencies."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException

from boz_server.core.config import settings
from boz_server.services.agent_manager import AgentManager
from boz_server.services.job_queue import JobQueue
from boz_server.services.nas_organizer import NASOrganizer
from boz_server.services.preview_generator import PreviewGenerator
from boz_server.services.thetvdb_client import TheTVDBClient
from boz_server.services.thumbnail_storage import ThumbnailStorage
from boz_server.services.worker_manager import WorkerManager

# Global service instances
_agent_manager: AgentManager | None = None
_job_queue: JobQueue | None = None
_nas_organizer: NASOrganizer | None = None
_worker_manager: WorkerManager | None = None
_preview_generator: PreviewGenerator | None = None
_thetvdb_client: TheTVDBClient | None = None
_thumbnail_storage: ThumbnailStorage | None = None


def init_services(
    agent_manager: AgentManager,
    job_queue: JobQueue,
    nas_organizer: NASOrganizer,
    worker_manager: WorkerManager,
    preview_generator: PreviewGenerator,
    thetvdb_client: TheTVDBClient | None = None,
    thumbnail_storage: ThumbnailStorage | None = None,
) -> None:
    """Initialize service instances."""
    global _agent_manager, _job_queue, _nas_organizer, _worker_manager, _preview_generator, _thetvdb_client, _thumbnail_storage
    _agent_manager = agent_manager
    _job_queue = job_queue
    _nas_organizer = nas_organizer
    _worker_manager = worker_manager
    _preview_generator = preview_generator
    _thetvdb_client = thetvdb_client
    _thumbnail_storage = thumbnail_storage


def get_agent_manager() -> AgentManager:
    """Get the agent manager instance."""
    if _agent_manager is None:
        raise RuntimeError("Services not initialized")
    return _agent_manager


def get_job_queue() -> JobQueue:
    """Get the job queue instance."""
    if _job_queue is None:
        raise RuntimeError("Services not initialized")
    return _job_queue


def get_nas_organizer() -> NASOrganizer:
    """Get the NAS organizer instance."""
    if _nas_organizer is None:
        raise RuntimeError("Services not initialized")
    return _nas_organizer


def get_worker_manager() -> WorkerManager:
    """Get the worker manager instance."""
    if _worker_manager is None:
        raise RuntimeError("Services not initialized")
    return _worker_manager


def get_preview_generator() -> PreviewGenerator:
    """Get the preview generator instance."""
    if _preview_generator is None:
        raise RuntimeError("Services not initialized")
    return _preview_generator


def get_thetvdb_client() -> TheTVDBClient | None:
    """Get the TheTVDB client instance (may be None if not configured)."""
    return _thetvdb_client


def get_thumbnail_storage() -> ThumbnailStorage:
    """Get the thumbnail storage instance."""
    if _thumbnail_storage is None:
        raise RuntimeError("Thumbnail storage not initialized")
    return _thumbnail_storage


async def verify_api_key(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Verify API key if configured."""
    if not settings.api_key:
        return  # No API key required

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    # Expect "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    if parts[1] != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# Type aliases for dependency injection
AgentManagerDep = Annotated[AgentManager, Depends(get_agent_manager)]
JobQueueDep = Annotated[JobQueue, Depends(get_job_queue)]
NASOrganizerDep = Annotated[NASOrganizer, Depends(get_nas_organizer)]
WorkerManagerDep = Annotated[WorkerManager, Depends(get_worker_manager)]
PreviewGeneratorDep = Annotated[PreviewGenerator, Depends(get_preview_generator)]
TheTVDBClientDep = Annotated[TheTVDBClient | None, Depends(get_thetvdb_client)]
ThumbnailStorageDep = Annotated[ThumbnailStorage, Depends(get_thumbnail_storage)]
ApiKeyDep = Annotated[None, Depends(verify_api_key)]
