"""API dependencies."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException

from boz_server.core.config import settings
from boz_server.services.agent_manager import AgentManager
from boz_server.services.job_queue import JobQueue
from boz_server.services.nas_organizer import NASOrganizer

# Global service instances
_agent_manager: AgentManager | None = None
_job_queue: JobQueue | None = None
_nas_organizer: NASOrganizer | None = None


def init_services(
    agent_manager: AgentManager,
    job_queue: JobQueue,
    nas_organizer: NASOrganizer,
) -> None:
    """Initialize service instances."""
    global _agent_manager, _job_queue, _nas_organizer
    _agent_manager = agent_manager
    _job_queue = job_queue
    _nas_organizer = nas_organizer


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
ApiKeyDep = Annotated[None, Depends(verify_api_key)]
