"""Job management API endpoints."""

import logging

from fastapi import APIRouter, HTTPException

from boz_server.api.deps import AgentManagerDep, ApiKeyDep, JobQueueDep, ThumbnailStorageDep, WorkerManagerDep
from boz_server.models.job import Job, JobApprovalRequest, JobCreate, JobStatus, JobUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=Job)
async def create_job(
    request: JobCreate,
    job_queue: JobQueueDep,
    thumbnail_storage: ThumbnailStorageDep,
    _: ApiKeyDep,
) -> Job:
    """Create a new job."""
    # Create the job first to get the job_id
    job = await job_queue.create_job(request)

    # If thumbnails were provided (Stage 2 post-rip preview), store them
    if request.thumbnails:
        logger.info(f"Processing {len(request.thumbnails)} thumbnails for job {job.job_id}")
        try:
            # Store thumbnails using job_id as the directory
            thumbnail_urls = thumbnail_storage.save_thumbnails(
                disc_id=job.job_id,  # Reuse disc_id storage structure
                title_index=0,  # Single title per job
                thumbnails=request.thumbnails,
                timestamps=request.thumbnail_timestamps,
            )
            # Update job with thumbnail URLs
            job.thumbnails = thumbnail_urls
            job.thumbnail_timestamps = request.thumbnail_timestamps
            # Persist the update
            job = await job_queue.update_job_thumbnails(job.job_id, thumbnail_urls, request.thumbnail_timestamps)
            logger.info(f"Stored {len(thumbnail_urls)} thumbnails for job {job.job_id}")
        except Exception as e:
            logger.error(f"Failed to store thumbnails for job {job.job_id}: {e}")

    return job


@router.get("", response_model=list[Job])
async def list_jobs(
    job_queue: JobQueueDep,
    status: JobStatus | None = None,
) -> list[Job]:
    """List all jobs, optionally filtered by status."""
    jobs = await job_queue.get_all_jobs()
    if status:
        jobs = [j for j in jobs if j.status == status]
    return jobs


@router.get("/stats")
async def get_queue_stats(
    job_queue: JobQueueDep,
) -> dict:
    """Get job queue statistics."""
    return await job_queue.get_queue_stats()


@router.get("/pending")
async def get_pending_jobs(
    job_queue: JobQueueDep,
) -> list[Job]:
    """Get all pending jobs in priority order."""
    return await job_queue.get_pending_jobs()


@router.get("/awaiting-approval", response_model=list[Job])
async def get_jobs_awaiting_approval(
    job_queue: JobQueueDep,
) -> list[Job]:
    """Get transcode jobs awaiting user approval."""
    return await job_queue.get_jobs_awaiting_approval()


@router.get("/upload-errors", response_model=list[Job])
async def get_jobs_with_upload_errors(
    job_queue: JobQueueDep,
) -> list[Job]:
    """Get completed jobs that have upload errors."""
    jobs = await job_queue.get_all_jobs()
    return [
        j for j in jobs
        if j.status == JobStatus.COMPLETED
        and j.error
        and "upload" in j.error.lower()
    ]


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
    job = await job_queue.get_job(job_id)
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
    job = await job_queue.update_job(job_id, update)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # If job completed or failed, release the agent
    if update.status in (JobStatus.COMPLETED, JobStatus.FAILED):
        if job.assigned_agent_id:
            await agent_manager.complete_job(job.assigned_agent_id)

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
    job = await job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    agent = await agent_manager.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not agent.is_available():
        raise HTTPException(status_code=400, detail="Agent not available")

    if not await job_queue.assign_job(job_id, agent_id):
        raise HTTPException(status_code=400, detail="Failed to assign job")

    await agent_manager.assign_job(agent_id, job_id)

    return {"status": "ok", "job_id": job_id, "agent_id": agent_id}


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    job_queue: JobQueueDep,
    agent_manager: AgentManagerDep,
    _: ApiKeyDep,
) -> dict:
    """Cancel a job."""
    job = await job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in (JobStatus.COMPLETED, JobStatus.CANCELLED):
        raise HTTPException(status_code=400, detail="Job already finished")

    update = JobUpdate(status=JobStatus.CANCELLED)
    await job_queue.update_job(job_id, update)

    # Release agent if assigned
    if job.assigned_agent_id:
        await agent_manager.complete_job(job.assigned_agent_id)

    return {"status": "ok", "job_id": job_id}


@router.post("/{job_id}/approve")
async def approve_job(
    job_id: str,
    request: JobApprovalRequest,
    job_queue: JobQueueDep,
    worker_manager: WorkerManagerDep,
    agent_manager: AgentManagerDep,
    _: ApiKeyDep,
) -> dict:
    """Approve a pending transcode job with worker and preset selection."""
    job = await job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.requires_approval:
        raise HTTPException(status_code=400, detail="Job does not require approval")

    if job.status != JobStatus.PENDING:
        raise HTTPException(status_code=400, detail="Job is not pending")

    # Validate worker exists
    worker = await worker_manager.get(request.worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    # Get the agent_id to assign the job to
    # Workers from agents have an agent_id, standalone workers use worker_id
    agent_id = worker.agent_id or request.worker_id

    # Approve and assign to the agent
    approved_job = await job_queue.approve_job(job_id, agent_id, request.preset)
    if not approved_job:
        raise HTTPException(status_code=400, detail="Failed to approve job")

    # Mark agent as having a job (if the agent exists)
    agent = await agent_manager.get(agent_id)
    if agent:
        await agent_manager.assign_job(agent_id, job_id)

    return {
        "status": "ok",
        "job_id": job_id,
        "worker_id": request.worker_id,
        "agent_id": agent_id,
        "preset": request.preset,
    }
