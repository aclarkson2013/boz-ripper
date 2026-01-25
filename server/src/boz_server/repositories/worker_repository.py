"""Worker repository for database operations."""

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models.worker import WorkerORM
from ..models.worker import Worker, WorkerCapabilities, WorkerStatus, WorkerType
from .base import BaseRepository


class WorkerRepository(BaseRepository[WorkerORM]):
    """Repository for worker database operations."""

    def __init__(self, session: AsyncSession):
        """Initialize worker repository."""
        super().__init__(WorkerORM, session)

    async def create_from_pydantic(self, worker: Worker) -> WorkerORM:
        """
        Create worker from Pydantic model.

        Args:
            worker: Pydantic Worker model

        Returns:
            ORM worker instance
        """
        worker_orm = WorkerORM(
            worker_id=worker.worker_id,
            worker_type=worker.worker_type.value,
            hostname=worker.hostname,
            agent_id=worker.agent_id,
            capabilities=json.dumps(worker.capabilities.model_dump()),
            priority=worker.priority,
            enabled=worker.enabled,
            status=worker.status.value,
            current_jobs=json.dumps(worker.current_jobs),
            last_heartbeat=worker.last_heartbeat,
            registered_at=worker.registered_at,
            total_jobs_completed=worker.total_jobs_completed,
            avg_transcode_time_seconds=worker.avg_transcode_time_seconds,
            cpu_usage=worker.cpu_usage,
            gpu_usage=worker.gpu_usage,
        )
        return await self.create(worker_orm)

    def to_pydantic(self, worker_orm: WorkerORM) -> Worker:
        """
        Convert ORM model to Pydantic model.

        Args:
            worker_orm: ORM worker instance

        Returns:
            Pydantic Worker model
        """
        capabilities_dict = json.loads(worker_orm.capabilities)
        current_jobs = json.loads(worker_orm.current_jobs)

        return Worker(
            worker_id=worker_orm.worker_id,
            worker_type=WorkerType(worker_orm.worker_type),
            hostname=worker_orm.hostname,
            agent_id=worker_orm.agent_id,
            capabilities=WorkerCapabilities(**capabilities_dict),
            priority=worker_orm.priority,
            enabled=worker_orm.enabled,
            status=WorkerStatus(worker_orm.status),
            current_jobs=current_jobs,
            last_heartbeat=worker_orm.last_heartbeat,
            registered_at=worker_orm.registered_at,
            total_jobs_completed=worker_orm.total_jobs_completed,
            avg_transcode_time_seconds=worker_orm.avg_transcode_time_seconds,
            cpu_usage=worker_orm.cpu_usage,
            gpu_usage=worker_orm.gpu_usage,
        )

    async def get_or_create(
        self,
        worker_id: str,
        worker_type: WorkerType,
        hostname: str,
        capabilities: WorkerCapabilities,
        priority: int = 50,
        agent_id: Optional[str] = None,
    ) -> Worker:
        """
        Get existing worker or create new one.

        Args:
            worker_id: Worker ID
            worker_type: Worker type
            hostname: Hostname
            capabilities: Worker capabilities
            priority: Priority (1-99)
            agent_id: Associated agent ID

        Returns:
            Worker instance
        """
        worker_orm = await self.get(worker_id)

        if worker_orm:
            # Update existing worker
            worker_orm.hostname = hostname
            worker_orm.worker_type = worker_type.value
            worker_orm.status = WorkerStatus.AVAILABLE.value
            worker_orm.last_heartbeat = datetime.utcnow()
            worker_orm.capabilities = json.dumps(capabilities.model_dump())
            worker_orm.priority = priority
            if agent_id:
                worker_orm.agent_id = agent_id
            await self.session.flush()
            await self.session.refresh(worker_orm)
        else:
            # Create new worker
            worker = Worker(
                worker_id=worker_id,
                worker_type=worker_type,
                hostname=hostname,
                capabilities=capabilities,
                priority=priority,
                agent_id=agent_id,
                status=WorkerStatus.AVAILABLE,
            )
            worker_orm = await self.create_from_pydantic(worker)

        return self.to_pydantic(worker_orm)

    async def update_heartbeat(
        self,
        worker_id: str,
        status: WorkerStatus = WorkerStatus.AVAILABLE,
        current_jobs: Optional[list[str]] = None,
        cpu_usage: Optional[float] = None,
        gpu_usage: Optional[float] = None,
    ) -> Optional[Worker]:
        """
        Update worker heartbeat and status.

        Args:
            worker_id: Worker ID
            status: Worker status
            current_jobs: List of current job IDs
            cpu_usage: CPU usage percentage
            gpu_usage: GPU usage percentage

        Returns:
            Updated worker or None if not found
        """
        worker_orm = await self.get(worker_id)
        if not worker_orm:
            return None

        worker_orm.last_heartbeat = datetime.utcnow()
        worker_orm.status = status.value
        if current_jobs is not None:
            worker_orm.current_jobs = json.dumps(current_jobs)
        if cpu_usage is not None:
            worker_orm.cpu_usage = cpu_usage
        if gpu_usage is not None:
            worker_orm.gpu_usage = gpu_usage

        await self.session.flush()
        await self.session.refresh(worker_orm)
        return self.to_pydantic(worker_orm)

    async def get_available(self) -> list[Worker]:
        """
        Get all available workers sorted by priority.

        Returns:
            List of available workers
        """
        result = await self.session.execute(
            select(WorkerORM)
            .where(WorkerORM.enabled == True)
            .where(WorkerORM.status != WorkerStatus.OFFLINE.value)
            .order_by(WorkerORM.priority.asc())
        )
        workers = [self.to_pydantic(worker) for worker in result.scalars().all()]
        return [worker for worker in workers if worker.is_available()]

    async def get_by_type(self, worker_type: WorkerType) -> list[Worker]:
        """
        Get workers of a specific type.

        Args:
            worker_type: Worker type

        Returns:
            List of workers
        """
        result = await self.session.execute(
            select(WorkerORM).where(WorkerORM.worker_type == worker_type.value)
        )
        return [self.to_pydantic(worker) for worker in result.scalars().all()]

    async def assign_job(self, worker_id: str, job_id: str) -> Optional[Worker]:
        """
        Assign a job to a worker.

        Args:
            worker_id: Worker ID
            job_id: Job ID

        Returns:
            Updated worker or None if not found
        """
        worker_orm = await self.get(worker_id)
        if not worker_orm:
            return None

        current_jobs = json.loads(worker_orm.current_jobs)
        current_jobs.append(job_id)
        worker_orm.current_jobs = json.dumps(current_jobs)

        # Update status if at max capacity
        capabilities = json.loads(worker_orm.capabilities)
        if len(current_jobs) >= capabilities.get("max_concurrent", 2):
            worker_orm.status = WorkerStatus.BUSY.value

        await self.session.flush()
        await self.session.refresh(worker_orm)
        return self.to_pydantic(worker_orm)

    async def complete_job(
        self, worker_id: str, job_id: str, duration_seconds: float = 0
    ) -> Optional[Worker]:
        """
        Mark a job as complete on a worker.

        Args:
            worker_id: Worker ID
            job_id: Job ID
            duration_seconds: Job duration in seconds

        Returns:
            Updated worker or None if not found
        """
        worker_orm = await self.get(worker_id)
        if not worker_orm:
            return None

        current_jobs = json.loads(worker_orm.current_jobs)
        if job_id in current_jobs:
            current_jobs.remove(job_id)
            worker_orm.current_jobs = json.dumps(current_jobs)
            worker_orm.total_jobs_completed += 1

            # Update average transcode time
            if duration_seconds > 0:
                total_time = (
                    worker_orm.avg_transcode_time_seconds
                    * (worker_orm.total_jobs_completed - 1)
                )
                worker_orm.avg_transcode_time_seconds = (
                    total_time + duration_seconds
                ) / worker_orm.total_jobs_completed

            # Update status
            capabilities = json.loads(worker_orm.capabilities)
            if (
                worker_orm.status == WorkerStatus.BUSY.value
                and len(current_jobs) < capabilities.get("max_concurrent", 2)
            ):
                worker_orm.status = WorkerStatus.AVAILABLE.value

            await self.session.flush()
            await self.session.refresh(worker_orm)

        return self.to_pydantic(worker_orm)

    async def update_priority(self, worker_id: str, priority: int) -> Optional[Worker]:
        """
        Update worker priority.

        Args:
            worker_id: Worker ID
            priority: New priority (1-99)

        Returns:
            Updated worker or None if not found
        """
        worker_orm = await self.get(worker_id)
        if not worker_orm:
            return None

        worker_orm.priority = max(1, min(99, priority))
        await self.session.flush()
        await self.session.refresh(worker_orm)
        return self.to_pydantic(worker_orm)

    async def set_enabled(self, worker_id: str, enabled: bool) -> Optional[Worker]:
        """
        Enable or disable a worker.

        Args:
            worker_id: Worker ID
            enabled: Whether worker is enabled

        Returns:
            Updated worker or None if not found
        """
        worker_orm = await self.get(worker_id)
        if not worker_orm:
            return None

        worker_orm.enabled = enabled
        await self.session.flush()
        await self.session.refresh(worker_orm)
        return self.to_pydantic(worker_orm)

    async def mark_stale_workers_offline(self, timeout_seconds: int) -> tuple[int, list[tuple[str, list[str]]]]:
        """
        Mark workers as offline if heartbeat is stale.

        Args:
            timeout_seconds: Timeout in seconds

        Returns:
            Tuple of (count of workers marked offline, list of (worker_id, orphaned_job_ids))
        """
        cutoff = datetime.utcnow().timestamp() - timeout_seconds
        result = await self.session.execute(
            select(WorkerORM).where(WorkerORM.status != WorkerStatus.OFFLINE.value)
        )

        count = 0
        orphaned_jobs: list[tuple[str, list[str]]] = []

        for worker_orm in result.scalars().all():
            if worker_orm.last_heartbeat.timestamp() < cutoff:
                old_status = worker_orm.status
                worker_orm.status = WorkerStatus.OFFLINE.value

                # Collect orphaned jobs for failover (S13)
                current_jobs = json.loads(worker_orm.current_jobs)
                if current_jobs:
                    orphaned_jobs.append((worker_orm.worker_id, current_jobs))
                    worker_orm.current_jobs = "[]"

                count += 1

        if count > 0:
            await self.session.flush()

        return count, orphaned_jobs
