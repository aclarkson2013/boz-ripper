"""Job management API endpoints."""

from fastapi import APIRouter, HTTPException

from boz_server.api.deps import AgentManagerDep, ApiKeyDep, JobQueueDep
from boz_server.models.job import Job, JobApprovalRequest, JobCreate, JobStatus, JobUpdate

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=Job)
async def create_job(
    request: JobCreate,
    job_queue: JobQueueDep,
    _: ApiKeyDep,
) -> Job:
    """Create a new job."""
    return job_queue.create_job(request)


@router.get("", response_model=list[Job])
async def list_jobs(
    job_queue: JobQueueDep,
    status: JobStatus | None = None,
) -> list[Job]:
    """List all jobs, optionally filtered by status."""
    jobs = job_queue.get_all_jobs()
    if status:
        jobs = [j for j in jobs if j.status == status]
    return jobs


@router.get("/stats")
async def get_queue_stats(
    job_queue: JobQueueDep,
) -> dict:
    """Get job queue statistics."""
    return job_queue.get_queue_stats()


@router.get("/pending")
async def get_pending_jobs(
    job_queue: JobQueueDep,
) -> list[Job]:
    """Get all pending jobs in priority order."""
    return job_queue.get_pending_jobs()


@router.get("/awaiting-approval", response_model=list[Job])
async def get_jobs_awaiting_approval(
    job_queue: JobQueueDep,
) -> list[Job]:
    """Get transcode jobs awaiting user approval."""
    return job_queue.get_jobs_awaiting_approval()


@router.get("/presets")
async def get_available_presets() -> dict:
    """Get available transcoding presets."""
    return {
        "presets": [
            {"id": "H.265 NVENC 1080p", "name": "H.265 NVENC 1080p (Recommended)", "codec": "hevc", "requires": "nvenc"},
            {"id": "H.265 NVENC 4K", "name": "H.265 NVENC 4K", "codec": "hevc", "requires": "nvenc"},
            {"id": "H.264 NVENC 1080p", "name": "H.264 NVENC 1080p", "codec": "h264", "requires": "nvenc"},
            {"id": "H.264 NVENC 720p", "name": "H.264 NVENC 720p", "codec": "h264", "requires": "nvenc"},
            {"id": "H.265 QSV 1080p", "name": "H.265 QuickSync 1080p", "codec": "hevc", "requires": "qsv"},
            {"id": "H.264 QSV 1080p", "name": "H.264 QuickSync 1080p", "codec": "h264", "requires": "qsv"},
            {"id": "H.265 CPU 1080p", "name": "H.265 CPU 1080p (Slow)", "codec": "hevc", "requires": None},
            {"id": "H.264 CPU 1080p", "name": "H.264 CPU 1080p (Slow)", "codec": "h264", "requires": None},
            {"id": "Fast 1080p30", "name": "Fast 1080p30 (HandBrake Default)", "codec": "h264", "requires": None},
        ]
    }


@router.get("/{job_id}", response_model=Job)
async def get_job(
    job_id: str,
    job_queue: JobQueueDep,
) -> Job:
    """Get a specific job."""
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.patch("/{job_id}", response_model=Job)
async def update_job(
    job_id: str,
    update: JobUpdate,
    job_queue: JobQueueDep,
    agent_manager: AgentManagerDep,
    _: ApiKeyDep,
) -> Job:
    """Update a job's status."""
    job = job_queue.update_job(job_id, update)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # If job completed or failed, release the agent
    if update.status in (JobStatus.COMPLETED, JobStatus.FAILED):
        if job.assigned_agent_id:
            agent_manager.complete_job(job.assigned_agent_id)

    return job


@router.post("/{job_id}/assign")
async def assign_job(
    job_id: str,
    agent_id: str,
    job_queue: JobQueueDep,
    agent_manager: AgentManagerDep,
    _: ApiKeyDep,
) -> dict:
    """Manually assign a job to an agent."""
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    agent = agent_manager.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not agent.is_available():
        raise HTTPException(status_code=400, detail="Agent not available")

    if not job_queue.assign_job(job_id, agent_id):
        raise HTTPException(status_code=400, detail="Failed to assign job")

    agent_manager.assign_job(agent_id, job_id)

    return {"status": "ok", "job_id": job_id, "agent_id": agent_id}


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    job_queue: JobQueueDep,
    agent_manager: AgentManagerDep,
    _: ApiKeyDep,
) -> dict:
    """Cancel a job."""
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in (JobStatus.COMPLETED, JobStatus.CANCELLED):
        raise HTTPException(status_code=400, detail="Job already finished")

    update = JobUpdate(status=JobStatus.CANCELLED)
    job_queue.update_job(job_id, update)

    # Release agent if assigned
    if job.assigned_agent_id:
        agent_manager.complete_job(job.assigned_agent_id)

    return {"status": "ok", "job_id": job_id}


@router.post("/{job_id}/approve")
async def approve_job(
    job_id: str,
    request: JobApprovalRequest,
    job_queue: JobQueueDep,
    agent_manager: AgentManagerDep,
    _: ApiKeyDep,
) -> dict:
    """Approve a pending transcode job with worker and preset selection."""
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.requires_approval:
        raise HTTPException(status_code=400, detail="Job does not require approval")

    if job.status != JobStatus.PENDING:
        raise HTTPException(status_code=400, detail="Job is not pending")

    # Validate agent exists
    agent = agent_manager.get(request.worker_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Worker/agent not found")

    # Approve and assign
    approved_job = job_queue.approve_job(job_id, request.worker_id, request.preset)
    if not approved_job:
        raise HTTPException(status_code=400, detail="Failed to approve job")

    # Mark agent as having a job
    agent_manager.assign_job(request.worker_id, job_id)

    return {
        "status": "ok",
        "job_id": job_id,
        "worker_id": request.worker_id,
        "preset": request.preset,
    }
