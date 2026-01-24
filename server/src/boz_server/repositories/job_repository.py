"""Job repository for database operations."""

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models.job import JobORM
from ..models.job import Job, JobStatus, JobType
from .base import BaseRepository


class JobRepository(BaseRepository[JobORM]):
    """Repository for job database operations."""

    def __init__(self, session: AsyncSession):
        """Initialize job repository."""
        super().__init__(JobORM, session)

    async def create_from_pydantic(self, job: Job) -> JobORM:
        """
        Create job from Pydantic model.

        Args:
            job: Pydantic Job model

        Returns:
            ORM job instance
        """
        job_orm = JobORM(
            job_id=job.job_id,
            job_type=job.job_type.value,
            status=job.status.value,
            priority=job.priority,
            disc_id=job.disc_id,
            title_index=job.title_index,
            input_file=job.input_file,
            output_name=job.output_name,
            output_file=job.output_file,
            preset=job.preset,
            assigned_agent_id=job.assigned_agent_id,
            assigned_at=job.assigned_at,
            requires_approval=job.requires_approval,
            source_disc_name=job.source_disc_name,
            input_file_size=job.input_file_size,
            progress=job.progress,
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )
        return await self.create(job_orm)

    def to_pydantic(self, job_orm: JobORM) -> Job:
        """
        Convert ORM model to Pydantic model.

        Args:
            job_orm: ORM job instance

        Returns:
            Pydantic Job model
        """
        return Job(
            job_id=job_orm.job_id,
            job_type=JobType(job_orm.job_type),
            status=JobStatus(job_orm.status),
            priority=job_orm.priority,
            disc_id=job_orm.disc_id,
            title_index=job_orm.title_index,
            input_file=job_orm.input_file,
            output_name=job_orm.output_name,
            output_file=job_orm.output_file,
            preset=job_orm.preset,
            assigned_agent_id=job_orm.assigned_agent_id,
            assigned_at=job_orm.assigned_at,
            requires_approval=job_orm.requires_approval,
            source_disc_name=job_orm.source_disc_name,
            input_file_size=job_orm.input_file_size,
            progress=job_orm.progress,
            error=job_orm.error,
            created_at=job_orm.created_at,
            started_at=job_orm.started_at,
            completed_at=job_orm.completed_at,
        )

    async def get_by_status(self, status: JobStatus) -> list[Job]:
        """
        Get jobs by status.

        Args:
            status: Job status to filter by

        Returns:
            List of jobs with matching status
        """
        result = await self.session.execute(
            select(JobORM).where(JobORM.status == status.value)
        )
        return [self.to_pydantic(job) for job in result.scalars().all()]

    async def get_pending_jobs(
        self, job_type: Optional[JobType] = None
    ) -> list[Job]:
        """
        Get pending or queued jobs, optionally filtered by type.

        Args:
            job_type: Optional job type filter

        Returns:
            List of pending jobs sorted by priority and created_at
        """
        query = select(JobORM).where(
            JobORM.status.in_([JobStatus.PENDING.value, JobStatus.QUEUED.value])
        )

        if job_type:
            query = query.where(JobORM.job_type == job_type.value)

        query = query.order_by(JobORM.priority.desc(), JobORM.created_at.asc())

        result = await self.session.execute(query)
        return [self.to_pydantic(job) for job in result.scalars().all()]

    async def get_jobs_for_agent(self, agent_id: str) -> list[Job]:
        """
        Get jobs assigned to a specific agent.

        Args:
            agent_id: Agent ID

        Returns:
            List of jobs assigned to the agent
        """
        result = await self.session.execute(
            select(JobORM)
            .where(JobORM.assigned_agent_id == agent_id)
            .where(JobORM.status.in_([JobStatus.ASSIGNED.value, JobStatus.RUNNING.value]))
        )
        return [self.to_pydantic(job) for job in result.scalars().all()]

    async def get_awaiting_approval(self) -> list[Job]:
        """
        Get jobs awaiting user approval.

        Returns:
            List of jobs requiring approval
        """
        result = await self.session.execute(
            select(JobORM)
            .where(JobORM.status == JobStatus.PENDING.value)
            .where(JobORM.requires_approval == True)
            .where(JobORM.job_type == JobType.TRANSCODE.value)
        )
        return [self.to_pydantic(job) for job in result.scalars().all()]

    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: Optional[float] = None,
        error: Optional[str] = None,
        output_file: Optional[str] = None,
    ) -> Optional[Job]:
        """
        Update job status and related fields.

        Args:
            job_id: Job ID
            status: New status
            progress: Optional progress percentage
            error: Optional error message
            output_file: Optional output file path

        Returns:
            Updated job or None if not found
        """
        job_orm = await self.get(job_id)
        if not job_orm:
            return None

        job_orm.status = status.value
        if progress is not None:
            job_orm.progress = progress
        if error:
            job_orm.error = error
        if output_file:
            job_orm.output_file = output_file

        # Set timestamps based on status
        now = datetime.utcnow()
        if status == JobStatus.RUNNING and not job_orm.started_at:
            job_orm.started_at = now
        elif status in (JobStatus.COMPLETED, JobStatus.FAILED):
            job_orm.completed_at = now

        await self.session.flush()
        await self.session.refresh(job_orm)
        return self.to_pydantic(job_orm)

    async def assign_to_agent(
        self, job_id: str, agent_id: str, preset: Optional[str] = None
    ) -> Optional[Job]:
        """
        Assign a job to an agent.

        Args:
            job_id: Job ID
            agent_id: Agent ID
            preset: Optional transcoding preset

        Returns:
            Updated job or None if not found
        """
        job_orm = await self.get(job_id)
        if not job_orm:
            return None

        job_orm.status = JobStatus.ASSIGNED.value
        job_orm.assigned_agent_id = agent_id
        job_orm.assigned_at = datetime.utcnow()
        if preset:
            job_orm.preset = preset

        await self.session.flush()
        await self.session.refresh(job_orm)
        return self.to_pydantic(job_orm)

    async def approve_job(
        self, job_id: str, agent_id: str, preset: str
    ) -> Optional[Job]:
        """
        Approve a pending job and assign to agent.

        Args:
            job_id: Job ID
            agent_id: Agent ID to assign to
            preset: Transcoding preset

        Returns:
            Updated job or None if not found/invalid
        """
        job_orm = await self.get(job_id)
        if not job_orm:
            return None
        if job_orm.status != JobStatus.PENDING.value or not job_orm.requires_approval:
            return None

        job_orm.preset = preset
        job_orm.assigned_agent_id = agent_id
        job_orm.requires_approval = False
        job_orm.status = JobStatus.ASSIGNED.value
        job_orm.assigned_at = datetime.utcnow()

        await self.session.flush()
        await self.session.refresh(job_orm)
        return self.to_pydantic(job_orm)
