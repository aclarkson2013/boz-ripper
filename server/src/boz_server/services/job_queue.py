"""Job queue management service."""

import asyncio
import logging
from datetime import datetime
from typing import Callable, Optional
from uuid import uuid4

from boz_server.models.disc import Disc, Title
from boz_server.models.job import Job, JobCreate, JobStatus, JobType, JobUpdate

logger = logging.getLogger(__name__)


class JobQueue:
    """Manages the job queue and disc tracking."""

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._discs: dict[str, Disc] = {}
        self._job_callbacks: list[Callable] = []

    def add_disc(self, disc: Disc) -> Disc:
        """Add a detected disc."""
        self._discs[disc.disc_id] = disc
        logger.info(f"Disc added: {disc.disc_id} - {disc.disc_name}")
        return disc

    def remove_disc(self, disc_id: str) -> bool:
        """Remove a disc (ejected)."""
        if disc_id in self._discs:
            disc = self._discs[disc_id]
            disc.status = "ejected"
            logger.info(f"Disc ejected: {disc_id}")
            return True
        return False

    def get_disc(self, disc_id: str) -> Optional[Disc]:
        """Get a disc by ID."""
        return self._discs.get(disc_id)

    def get_disc_by_agent_drive(self, agent_id: str, drive: str) -> Optional[Disc]:
        """Get a disc by agent and drive."""
        for disc in self._discs.values():
            if disc.agent_id == agent_id and disc.drive == drive:
                if disc.status != "ejected":
                    return disc
        return None

    def get_all_discs(self) -> list[Disc]:
        """Get all tracked discs."""
        return list(self._discs.values())

    def create_job(self, request: JobCreate) -> Job:
        """Create a new job."""
        job = Job(
            job_id=str(uuid4()),
            job_type=request.job_type,
            status=JobStatus.PENDING,
            priority=request.priority,
            disc_id=request.disc_id,
            title_index=request.title_index,
            input_file=request.input_file,
            output_name=request.output_name,
            preset=request.preset,
            requires_approval=request.requires_approval,
            source_disc_name=request.source_disc_name,
            input_file_size=request.input_file_size,
        )
        self._jobs[job.job_id] = job
        logger.info(f"Job created: {job.job_id} ({job.job_type}), requires_approval={request.requires_approval}")
        return job

    def create_rip_job(self, disc: Disc, title: Title, output_name: str) -> Job:
        """Create a rip job for a disc title."""
        return self.create_job(JobCreate(
            job_type=JobType.RIP,
            disc_id=disc.disc_id,
            title_index=title.index,
            output_name=output_name,
            priority=0,
        ))

    def create_transcode_job(
        self,
        input_file: str,
        output_name: str,
        preset: Optional[str] = None,
        requires_approval: bool = True,
        source_disc_name: Optional[str] = None,
        input_file_size: Optional[int] = None,
    ) -> Job:
        """Create a transcode job."""
        return self.create_job(JobCreate(
            job_type=JobType.TRANSCODE,
            input_file=input_file,
            output_name=output_name,
            preset=preset,
            priority=0,
            requires_approval=requires_approval,
            source_disc_name=source_disc_name,
            input_file_size=input_file_size,
        ))

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    def get_all_jobs(self) -> list[Job]:
        """Get all jobs."""
        return list(self._jobs.values())

    def get_pending_jobs(self, job_type: Optional[JobType] = None) -> list[Job]:
        """Get pending jobs, optionally filtered by type."""
        jobs = [
            j for j in self._jobs.values()
            if j.status in (JobStatus.PENDING, JobStatus.QUEUED)
        ]
        if job_type:
            jobs = [j for j in jobs if j.job_type == job_type]
        # Sort by priority (descending) then created_at (ascending)
        jobs.sort(key=lambda j: (-j.priority, j.created_at))
        return jobs

    def get_jobs_for_agent(self, agent_id: str) -> list[Job]:
        """Get jobs assigned to an agent."""
        return [
            j for j in self._jobs.values()
            if j.assigned_agent_id == agent_id
            and j.status in (JobStatus.ASSIGNED, JobStatus.RUNNING)
        ]

    def assign_job(self, job_id: str, agent_id: str) -> bool:
        """Assign a job to an agent."""
        job = self._jobs.get(job_id)
        if job and job.status in (JobStatus.PENDING, JobStatus.QUEUED):
            job.status = JobStatus.ASSIGNED
            job.assigned_agent_id = agent_id
            job.assigned_at = datetime.utcnow()
            logger.info(f"Job {job_id} assigned to {agent_id}")
            return True
        return False

    def update_job(self, job_id: str, update: JobUpdate) -> Optional[Job]:
        """Update a job's status."""
        job = self._jobs.get(job_id)
        if not job:
            return None

        job.status = update.status
        if update.progress is not None:
            job.progress = update.progress
        if update.error:
            job.error = update.error
        if update.output_file:
            job.output_file = update.output_file

        # Set timestamps based on status
        if update.status == JobStatus.RUNNING and not job.started_at:
            job.started_at = datetime.utcnow()
        elif update.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            job.completed_at = datetime.utcnow()

        logger.info(f"Job {job_id} updated: {update.status}")
        return job

    def get_next_rip_job(self) -> Optional[Job]:
        """Get the next pending rip job."""
        pending = self.get_pending_jobs(JobType.RIP)
        return pending[0] if pending else None

    def get_next_transcode_job(self) -> Optional[Job]:
        """Get the next pending transcode job."""
        pending = self.get_pending_jobs(JobType.TRANSCODE)
        return pending[0] if pending else None

    def get_queue_stats(self) -> dict:
        """Get queue statistics."""
        jobs = list(self._jobs.values())
        return {
            "total_jobs": len(jobs),
            "pending": len([j for j in jobs if j.status == JobStatus.PENDING]),
            "running": len([j for j in jobs if j.status == JobStatus.RUNNING]),
            "completed": len([j for j in jobs if j.status == JobStatus.COMPLETED]),
            "failed": len([j for j in jobs if j.status == JobStatus.FAILED]),
            "rip_jobs": len([j for j in jobs if j.job_type == JobType.RIP]),
            "transcode_jobs": len([j for j in jobs if j.job_type == JobType.TRANSCODE]),
            "awaiting_approval": len([
                j for j in jobs
                if j.status == JobStatus.PENDING and j.requires_approval
            ]),
        }

    def get_jobs_awaiting_approval(self) -> list[Job]:
        """Get transcode jobs awaiting user approval."""
        return [
            j for j in self._jobs.values()
            if j.status == JobStatus.PENDING
            and j.requires_approval
            and j.job_type == JobType.TRANSCODE
        ]

    def approve_job(
        self,
        job_id: str,
        agent_id: str,
        preset: str,
    ) -> Optional[Job]:
        """Approve a pending job and assign to an agent."""
        job = self._jobs.get(job_id)
        if not job:
            return None
        if job.status != JobStatus.PENDING or not job.requires_approval:
            return None

        job.preset = preset
        job.assigned_agent_id = agent_id
        job.requires_approval = False
        job.status = JobStatus.ASSIGNED
        job.assigned_at = datetime.utcnow()

        logger.info(f"Job {job_id} approved: agent={agent_id}, preset={preset}")
        return job
