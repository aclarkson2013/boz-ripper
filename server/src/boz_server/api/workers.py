"""Worker management API endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from boz_server.api.deps import ApiKeyDep, WorkerManagerDep, JobQueueDep
from boz_server.models.worker import (
    Worker,
    WorkerRegistration,
    WorkerHeartbeat,
    WorkerAssignment,
    WorkerStatus,
    TranscodeJob,
)

router = APIRouter(prefix="/api/workers", tags=["workers"])


# Request/Response models
class WorkerAssignmentRequest(BaseModel):
    """Request for worker assignment."""
    agent_id: str
    disc_type: str = "dvd"
    file_size_mb: int = 0


class PriorityUpdate(BaseModel):
    """Request to update worker priority."""
    priority: int


class JobPollRequest(BaseModel):
    """Request to poll for jobs."""
    max_jobs: int = 1


class JobPollResponse(BaseModel):
    """Response with available jobs."""
    jobs: list[TranscodeJob]


class JobCompleteRequest(BaseModel):
    """Request to mark job complete."""
    job_id: str
    duration_seconds: float = 0
    success: bool = True
    error: Optional[str] = None


# Endpoints

@router.post("/register", response_model=Worker)
async def register_worker(
    request: WorkerRegistration,
    worker_manager: WorkerManagerDep,
    _: ApiKeyDep,
) -> Worker:
    """Register a new worker or reconnect an existing one."""
    worker = worker_manager.register(
        worker_id=request.worker_id,
        worker_type=request.worker_type,
        hostname=request.hostname,
        capabilities=request.capabilities,
        priority=request.priority,
        agent_id=request.agent_id,
    )
    return worker


@router.post("/{worker_id}/heartbeat")
async def worker_heartbeat(
    worker_id: str,
    request: WorkerHeartbeat,
    worker_manager: WorkerManagerDep,
    _: ApiKeyDep,
) -> dict:
    """Update worker heartbeat and status."""
    success = worker_manager.heartbeat(
        worker_id=worker_id,
        status=request.status,
        current_jobs=request.current_jobs,
        cpu_usage=request.cpu_usage,
        gpu_usage=request.gpu_usage,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Worker not found")

    return {
        "acknowledged": True,
        "server_time": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }


@router.get("", response_model=list[Worker])
async def list_workers(
    worker_manager: WorkerManagerDep,
) -> list[Worker]:
    """List all registered workers."""
    return worker_manager.get_all()


@router.get("/stats")
async def get_worker_stats(
    worker_manager: WorkerManagerDep,
) -> dict:
    """Get worker statistics."""
    return worker_manager.get_stats()


@router.get("/available", response_model=list[Worker])
async def list_available_workers(
    worker_manager: WorkerManagerDep,
) -> list[Worker]:
    """List available workers sorted by priority."""
    return worker_manager.get_available()


@router.get("/{worker_id}", response_model=Worker)
async def get_worker(
    worker_id: str,
    worker_manager: WorkerManagerDep,
) -> Worker:
    """Get a specific worker."""
    worker = worker_manager.get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    return worker


@router.post("/{worker_id}/update-priority")
async def update_worker_priority(
    worker_id: str,
    request: PriorityUpdate,
    worker_manager: WorkerManagerDep,
    _: ApiKeyDep,
) -> dict:
    """Update a worker's priority (1-99, lower = higher priority)."""
    if not 1 <= request.priority <= 99:
        raise HTTPException(status_code=400, detail="Priority must be between 1 and 99")

    if worker_manager.update_priority(worker_id, request.priority):
        return {"status": "ok", "priority": request.priority}
    raise HTTPException(status_code=404, detail="Worker not found")


@router.post("/{worker_id}/enable")
async def enable_worker(
    worker_id: str,
    worker_manager: WorkerManagerDep,
    _: ApiKeyDep,
) -> dict:
    """Enable a worker."""
    if worker_manager.enable_worker(worker_id, True):
        return {"status": "ok", "enabled": True}
    raise HTTPException(status_code=404, detail="Worker not found")


@router.post("/{worker_id}/disable")
async def disable_worker(
    worker_id: str,
    worker_manager: WorkerManagerDep,
    _: ApiKeyDep,
) -> dict:
    """Disable a worker."""
    if worker_manager.enable_worker(worker_id, False):
        return {"status": "ok", "enabled": False}
    raise HTTPException(status_code=404, detail="Worker not found")


@router.delete("/{worker_id}")
async def unregister_worker(
    worker_id: str,
    worker_manager: WorkerManagerDep,
    _: ApiKeyDep,
) -> dict:
    """Unregister a worker."""
    if worker_manager.unregister(worker_id):
        return {"status": "ok", "message": "Worker unregistered"}
    raise HTTPException(status_code=404, detail="Worker not found")


@router.post("/{worker_id}/jobs/poll", response_model=JobPollResponse)
async def poll_for_jobs(
    worker_id: str,
    request: JobPollRequest,
    worker_manager: WorkerManagerDep,
    job_queue: JobQueueDep,
    _: ApiKeyDep,
) -> JobPollResponse:
    """Poll for available transcode jobs (used by remote workers)."""
    worker = worker_manager.get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    # Update heartbeat
    worker_manager.heartbeat(worker_id)

    # Get pending transcode jobs
    jobs = worker_manager.get_pending_jobs_for_worker(worker_id, request.max_jobs)
    return JobPollResponse(jobs=jobs)


@router.post("/{worker_id}/jobs/complete")
async def complete_job(
    worker_id: str,
    request: JobCompleteRequest,
    worker_manager: WorkerManagerDep,
    job_queue: JobQueueDep,
    _: ApiKeyDep,
) -> dict:
    """Mark a job as complete on this worker."""
    worker = worker_manager.get(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    # Update worker stats
    worker_manager.complete_job(
        worker_id,
        request.job_id,
        request.duration_seconds,
    )

    # Update job status in queue
    from boz_server.models.job import JobStatus, JobUpdate

    if request.success:
        job_queue.update_job(
            request.job_id,
            JobUpdate(status=JobStatus.COMPLETED, progress=100.0),
        )
    else:
        job_queue.update_job(
            request.job_id,
            JobUpdate(status=JobStatus.FAILED, error=request.error),
        )

    return {"status": "ok"}


# Job assignment endpoint (called by agents)

@router.post("/assign", response_model=WorkerAssignment)
async def request_worker_assignment(
    request: WorkerAssignmentRequest,
    worker_manager: WorkerManagerDep,
    _: ApiKeyDep,
) -> WorkerAssignment:
    """Request a worker assignment for a transcode job.

    Called by agents to determine where transcoding should happen.
    """
    # Generate a temporary job ID for assignment tracking
    import uuid
    job_id = str(uuid.uuid4())

    assignment = worker_manager.request_worker_assignment(
        job_id=job_id,
        agent_id=request.agent_id,
        disc_type=request.disc_type,
        file_size_mb=request.file_size_mb,
    )

    if not assignment:
        raise HTTPException(
            status_code=503,
            detail="No workers available for transcoding",
        )

    return assignment
