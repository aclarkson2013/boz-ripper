"""Database-backed job queue management service."""

import asyncio
import logging
from typing import Optional
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from ..database.session import SessionLocal
from ..models.disc import Disc, PreviewStatus, Title
from ..models.job import Job, JobCreate, JobStatus, JobType, JobUpdate
from ..repositories.disc_repository import DiscRepository
from ..repositories.job_repository import JobRepository

logger = logging.getLogger(__name__)


class JobQueue:
    """Manages the job queue and disc tracking with database persistence."""

    def __init__(self):
        """Initialize job queue."""
        pass

    async def _get_session(self) -> AsyncSession:
        """Get a new database session."""
        return SessionLocal()

    async def add_disc(self, disc: Disc) -> Disc:
        """Add a detected disc."""
        async with await self._get_session() as session:
            repo = DiscRepository(session)
            disc_orm = await repo.create_from_pydantic(disc)
            await session.commit()
            # Refresh to eagerly load titles
            disc_orm = await repo.get_with_titles(disc.disc_id)
            logger.info(f"Disc added: {disc.disc_id} - {disc.disc_name}")
            return repo.to_pydantic(disc_orm)

    async def remove_disc(self, disc_id: str) -> bool:
        """Remove a disc (ejected)."""
        async with await self._get_session() as session:
            repo = DiscRepository(session)
            disc = await repo.update_status(disc_id, "ejected")
            if disc:
                await session.commit()
                logger.info(f"Disc ejected: {disc_id}")
                return True
            return False

    async def get_disc(self, disc_id: str) -> Optional[Disc]:
        """Get a disc by ID."""
        async with await self._get_session() as session:
            repo = DiscRepository(session)
            disc_orm = await repo.get_with_titles(disc_id)
            return repo.to_pydantic(disc_orm) if disc_orm else None

    async def get_disc_by_agent_drive(
        self, agent_id: str, drive: str
    ) -> Optional[Disc]:
        """Get a disc by agent and drive."""
        async with await self._get_session() as session:
            repo = DiscRepository(session)
            return await repo.get_by_agent_drive(agent_id, drive)

    async def get_all_discs(self) -> list[Disc]:
        """Get all tracked discs."""
        async with await self._get_session() as session:
            repo = DiscRepository(session)
            return await repo.get_all_with_titles()

    async def update_disc(self, disc: Disc) -> Disc:
        """Update a disc (full update including all fields)."""
        async with await self._get_session() as session:
            repo = DiscRepository(session)
            # Full update from Pydantic model
            updated_disc = await repo.update_from_pydantic(disc)
            await session.commit()

            if updated_disc:
                return updated_disc

            # Fallback: fetch updated disc if update returned None
            disc_orm = await repo.get_with_titles(disc.disc_id)
            return repo.to_pydantic(disc_orm) if disc_orm else disc

    async def get_pending_previews(self) -> list[Disc]:
        """Get discs with pending preview status."""
        async with await self._get_session() as session:
            repo = DiscRepository(session)
            return await repo.get_pending_previews()

    async def create_job(self, request: JobCreate) -> Job:
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

        async with await self._get_session() as session:
            repo = JobRepository(session)
            job_orm = await repo.create_from_pydantic(job)
            await session.commit()
            logger.info(
                f"Job created: {job.job_id} ({job.job_type}), "
                f"requires_approval={request.requires_approval}"
            )
            return repo.to_pydantic(job_orm)

    async def create_rip_job(self, disc: Disc, title: Title, output_name: str) -> Job:
        """Create a rip job for a disc title."""
        return await self.create_job(
            JobCreate(
                job_type=JobType.RIP,
                disc_id=disc.disc_id,
                title_index=title.index,
                output_name=output_name,
                priority=0,
            )
        )

    async def create_transcode_job(
        self,
        input_file: str,
        output_name: str,
        preset: Optional[str] = None,
        requires_approval: bool = True,
        source_disc_name: Optional[str] = None,
        input_file_size: Optional[int] = None,
    ) -> Job:
        """Create a transcode job."""
        return await self.create_job(
            JobCreate(
                job_type=JobType.TRANSCODE,
                input_file=input_file,
                output_name=output_name,
                preset=preset,
                priority=0,
                requires_approval=requires_approval,
                source_disc_name=source_disc_name,
                input_file_size=input_file_size,
            )
        )

    async def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        async with await self._get_session() as session:
            repo = JobRepository(session)
            job_orm = await repo.get(job_id)
            return repo.to_pydantic(job_orm) if job_orm else None

    async def get_all_jobs(self) -> list[Job]:
        """Get all jobs."""
        async with await self._get_session() as session:
            repo = JobRepository(session)
            job_orms = await repo.get_all()
            return [repo.to_pydantic(job) for job in job_orms]

    async def get_pending_jobs(self, job_type: Optional[JobType] = None) -> list[Job]:
        """Get pending jobs, optionally filtered by type."""
        async with await self._get_session() as session:
            repo = JobRepository(session)
            return await repo.get_pending_jobs(job_type)

    async def get_jobs_for_agent(self, agent_id: str) -> list[Job]:
        """Get jobs assigned to an agent."""
        async with await self._get_session() as session:
            repo = JobRepository(session)
            return await repo.get_jobs_for_agent(agent_id)

    async def assign_job(self, job_id: str, agent_id: str) -> bool:
        """Assign a job to an agent."""
        async with await self._get_session() as session:
            repo = JobRepository(session)
            job = await repo.assign_to_agent(job_id, agent_id)
            if job:
                await session.commit()
                logger.info(f"Job {job_id} assigned to {agent_id}")
                return True
            return False

    async def update_job(self, job_id: str, update: JobUpdate) -> Optional[Job]:
        """Update a job's status."""
        async with await self._get_session() as session:
            repo = JobRepository(session)
            job = await repo.update_status(
                job_id, update.status, update.progress, update.error, update.output_file
            )
            if job:
                await session.commit()
                logger.info(f"Job {job_id} updated: {update.status}")
            return job

    async def get_next_rip_job(self) -> Optional[Job]:
        """Get the next pending rip job."""
        pending = await self.get_pending_jobs(JobType.RIP)
        return pending[0] if pending else None

    async def get_next_transcode_job(self) -> Optional[Job]:
        """Get the next pending transcode job."""
        pending = await self.get_pending_jobs(JobType.TRANSCODE)
        return pending[0] if pending else None

    async def get_queue_stats(self) -> dict:
        """Get queue statistics."""
        async with await self._get_session() as session:
            repo = JobRepository(session)
            jobs = [repo.to_pydantic(job) for job in await repo.get_all()]

            return {
                "total_jobs": len(jobs),
                "pending": len([j for j in jobs if j.status == JobStatus.PENDING]),
                "running": len([j for j in jobs if j.status == JobStatus.RUNNING]),
                "completed": len([j for j in jobs if j.status == JobStatus.COMPLETED]),
                "failed": len([j for j in jobs if j.status == JobStatus.FAILED]),
                "rip_jobs": len([j for j in jobs if j.job_type == JobType.RIP]),
                "transcode_jobs": len([j for j in jobs if j.job_type == JobType.TRANSCODE]),
                "awaiting_approval": len(
                    [j for j in jobs if j.status == JobStatus.PENDING and j.requires_approval]
                ),
            }

    async def get_jobs_awaiting_approval(self) -> list[Job]:
        """Get transcode jobs awaiting user approval."""
        async with await self._get_session() as session:
            repo = JobRepository(session)
            return await repo.get_awaiting_approval()

    async def approve_job(
        self,
        job_id: str,
        agent_id: str,
        preset: str,
        output_name: Optional[str] = None,
    ) -> Optional[Job]:
        """Approve a pending job and assign to an agent.

        Args:
            job_id: Job ID
            agent_id: Agent ID to assign to
            preset: Transcoding preset
            output_name: Optional new output name (TA9/TA10 file renaming)
        """
        async with await self._get_session() as session:
            repo = JobRepository(session)
            job = await repo.approve_job(job_id, agent_id, preset, output_name)
            if job:
                await session.commit()
                rename_note = f", renamed to '{output_name}'" if output_name else ""
                logger.info(f"Job {job_id} approved: agent={agent_id}, preset={preset}{rename_note}")
            return job

    async def update_job_thumbnails(
        self,
        job_id: str,
        thumbnail_urls: list[str],
        thumbnail_timestamps: list[int],
    ) -> Optional[Job]:
        """Update a job's thumbnail URLs after storage."""
        async with await self._get_session() as session:
            repo = JobRepository(session)
            job = await repo.update_thumbnails(job_id, thumbnail_urls, thumbnail_timestamps)
            if job:
                await session.commit()
                logger.info(f"Job {job_id} thumbnails updated: {len(thumbnail_urls)} images")
            return job
