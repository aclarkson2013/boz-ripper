"""VLC preview API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from boz_server.api.deps import AgentManagerDep, ApiKeyDep, WorkerManagerDep
from boz_server.services.vlc_service import VLCService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vlc", tags=["vlc"])

# Service instance
_vlc_service = VLCService()


class VLCPreviewRequest(BaseModel):
    """Request to queue a VLC preview."""

    agent_id: str
    file_path: str
    fullscreen: bool = True


class VLCCommandComplete(BaseModel):
    """Request to mark a VLC command as complete."""

    success: bool = True
    error: Optional[str] = None


@router.post("/preview")
async def queue_vlc_preview(
    request: VLCPreviewRequest,
    worker_manager: WorkerManagerDep,
    _: ApiKeyDep,
) -> dict:
    """Queue a VLC preview request for an agent.

    The command will be picked up by the agent on its next poll cycle (within 5 seconds).

    Args:
        request: Preview request with agent_id and file_path

    Returns:
        Queued command details
    """
    # Verify the agent/worker has VLC installed
    workers = await worker_manager.get_all()
    agent_worker = None
    for worker in workers:
        if worker.agent_id == request.agent_id:
            agent_worker = worker
            break

    if agent_worker and not agent_worker.capabilities.vlc_installed:
        raise HTTPException(
            status_code=400,
            detail="VLC is not installed on the target agent",
        )

    command = await _vlc_service.queue_preview(
        agent_id=request.agent_id,
        file_path=request.file_path,
        fullscreen=request.fullscreen,
    )

    return {
        "status": "queued",
        **command,
    }


@router.get("/commands/{agent_id}")
async def get_pending_commands(
    agent_id: str,
    _: ApiKeyDep,
) -> dict:
    """Get pending VLC commands for an agent.

    Called by agents during their poll cycle to check for VLC preview requests.

    Args:
        agent_id: Agent ID to get commands for

    Returns:
        List of pending commands (marks them as 'sent')
    """
    commands = await _vlc_service.get_pending_commands(agent_id)
    return {"commands": commands}


@router.post("/commands/{command_id}/complete")
async def complete_command(
    command_id: str,
    request: VLCCommandComplete,
    _: ApiKeyDep,
) -> dict:
    """Report completion of a VLC command.

    Called by agents after attempting to launch VLC.

    Args:
        command_id: Command ID to update
        request: Completion status

    Returns:
        Status confirmation
    """
    success = await _vlc_service.complete_command(
        command_id=command_id,
        success=request.success,
        error=request.error,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Command not found")

    return {"status": "ok", "command_id": command_id}


@router.get("/commands/{command_id}/status")
async def get_command_status(
    command_id: str,
) -> dict:
    """Get status of a VLC command.

    Args:
        command_id: Command ID

    Returns:
        Command details with status
    """
    command = await _vlc_service.get_command(command_id)

    if not command:
        raise HTTPException(status_code=404, detail="Command not found")

    return command
