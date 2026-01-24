"""Database-backed worker registration and management service."""

import asyncio
import logging
from datetime import timedelta
from enum import Enum
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..database.session import SessionLocal
from ..models.worker import (
    TranscodeJob,
    Worker,
    WorkerAssignment,
    WorkerCapabilities,
    WorkerStatus,
    WorkerType,
)
from ..repositories.worker_repository import WorkerRepository

logger = logging.getLogger(__name__)


class AssignmentStrategy(str, Enum):
    """Strategy for assigning jobs to workers."""

    PRIORITY = "priority"  # Always use highest priority available
    ROUND_ROBIN = "round_robin"  # Distribute evenly
    LOAD_BALANCE = "load_balance"  # Assign to least loaded
    FASTEST_FIRST = "fastest_first"  # Use worker with best historical times


class WorkerManager:
    """Manages transcoding workers with database persistence."""

    def __init__(self):
        """Initialize worker manager."""
        self._cleanup_task: Optional[asyncio.Task] = None
        self._assignment_strategy = AssignmentStrategy.PRIORITY
        self._round_robin_index = 0

    async def _get_session(self) -> AsyncSession:
        """Get a new database session."""
        return SessionLocal()

    async def start(self) -> None:
        """Start the worker manager background tasks."""
        self._cleanup_task = asyncio.create_task(self._health_check_loop())
        logger.info("Worker manager started")

    async def stop(self) -> None:
        """Stop the worker manager."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("Worker manager stopped")

    async def register(
        self,
        worker_id: str,
        worker_type: WorkerType,
        hostname: str,
        capabilities: Optional[WorkerCapabilities] = None,
        priority: int = 50,
        agent_id: Optional[str] = None,
    ) -> Worker:
        """Register a new worker or update existing."""
        async with await self._get_session() as session:
            repo = WorkerRepository(session)
            worker = await repo.get_or_create(
                worker_id,
                worker_type,
                hostname,
                capabilities or WorkerCapabilities(),
                priority,
                agent_id,
            )
            await session.commit()

            status = (
                "reconnected" if worker.registered_at != worker.last_heartbeat else "registered"
            )
            logger.info(
                f"Worker {status}: {worker_id} ({hostname}) - "
                f"Priority {priority}, {worker.get_encoder_name()}, agent={agent_id}"
            )
            return worker

    async def unregister(self, worker_id: str) -> bool:
        """Unregister a worker."""
        async with await self._get_session() as session:
            repo = WorkerRepository(session)
            success = await repo.delete_by_id(worker_id)
            if success:
                await session.commit()
                logger.info(f"Worker unregistered: {worker_id}")
            return success

    async def heartbeat(
        self,
        worker_id: str,
        status: WorkerStatus = WorkerStatus.AVAILABLE,
        current_jobs: Optional[list[str]] = None,
        cpu_usage: Optional[float] = None,
        gpu_usage: Optional[float] = None,
    ) -> bool:
        """Update worker heartbeat and status."""
        async with await self._get_session() as session:
            repo = WorkerRepository(session)
            worker = await repo.update_heartbeat(
                worker_id, status, current_jobs, cpu_usage, gpu_usage
            )
            if worker:
                await session.commit()
                return True
            return False

    async def get(self, worker_id: str) -> Optional[Worker]:
        """Get a worker by ID."""
        async with await self._get_session() as session:
            repo = WorkerRepository(session)
            worker_orm = await repo.get(worker_id)
            return repo.to_pydantic(worker_orm) if worker_orm else None

    async def get_all(self) -> list[Worker]:
        """Get all registered workers."""
        async with await self._get_session() as session:
            repo = WorkerRepository(session)
            worker_orms = await repo.get_all()
            return [repo.to_pydantic(worker) for worker in worker_orms]

    async def get_available(self) -> list[Worker]:
        """Get all available workers sorted by priority."""
        async with await self._get_session() as session:
            repo = WorkerRepository(session)
            return await repo.get_available()

    async def get_by_type(self, worker_type: WorkerType) -> list[Worker]:
        """Get workers of a specific type."""
        async with await self._get_session() as session:
            repo = WorkerRepository(session)
            return await repo.get_by_type(worker_type)

    async def update_priority(self, worker_id: str, priority: int) -> bool:
        """Update a worker's priority."""
        async with await self._get_session() as session:
            repo = WorkerRepository(session)
            worker = await repo.update_priority(worker_id, priority)
            if worker:
                await session.commit()
                logger.info(f"Worker {worker_id} priority updated to {worker.priority}")
                return True
            return False

    async def enable_worker(self, worker_id: str, enabled: bool = True) -> bool:
        """Enable or disable a worker."""
        async with await self._get_session() as session:
            repo = WorkerRepository(session)
            worker = await repo.set_enabled(worker_id, enabled)
            if worker:
                await session.commit()
                logger.info(f"Worker {worker_id} {'enabled' if enabled else 'disabled'}")
                return True
            return False

    async def assign_job(self, worker_id: str, job_id: str) -> bool:
        """Assign a job to a specific worker."""
        async with await self._get_session() as session:
            repo = WorkerRepository(session)
            worker = await repo.assign_job(worker_id, job_id)
            if worker:
                await session.commit()
                logger.info(f"Job {job_id} assigned to worker {worker_id}")
                return True
            return False

    async def complete_job(
        self, worker_id: str, job_id: str, duration_seconds: float = 0
    ) -> bool:
        """Mark a job as complete on a worker."""
        async with await self._get_session() as session:
            repo = WorkerRepository(session)
            worker = await repo.complete_job(worker_id, job_id, duration_seconds)
            if worker:
                await session.commit()
                logger.info(f"Job {job_id} completed on worker {worker_id}")
                return True
            return False

    async def select_worker_for_job(
        self,
        prefer_gpu: bool = True,
        required_codec: Optional[str] = None,
    ) -> Optional[Worker]:
        """Select the best available worker for a job based on strategy."""
        available = await self.get_available()
        if not available:
            return None

        # Filter by codec requirement if specified
        if required_codec:
            if required_codec == "hevc":
                available = [w for w in available if w.capabilities.hevc]
            elif required_codec == "av1":
                available = [w for w in available if w.capabilities.av1]

        if not available:
            return None

        # Prefer GPU workers if requested
        if prefer_gpu:
            gpu_workers = [w for w in available if w.has_gpu()]
            if gpu_workers:
                available = gpu_workers

        # Apply assignment strategy
        if self._assignment_strategy == AssignmentStrategy.PRIORITY:
            # Already sorted by priority
            return available[0]

        elif self._assignment_strategy == AssignmentStrategy.ROUND_ROBIN:
            self._round_robin_index = (self._round_robin_index + 1) % len(available)
            return available[self._round_robin_index]

        elif self._assignment_strategy == AssignmentStrategy.LOAD_BALANCE:
            # Sort by number of current jobs
            available.sort(key=lambda w: len(w.current_jobs))
            return available[0]

        elif self._assignment_strategy == AssignmentStrategy.FASTEST_FIRST:
            # Sort by average transcode time (0 means no history, put last)
            available.sort(key=lambda w: w.avg_transcode_time_seconds or float("inf"))
            return available[0]

        return available[0]

    async def get_stats(self) -> dict:
        """Get worker statistics."""
        workers = await self.get_all()
        return {
            "total_workers": len(workers),
            "available": len([w for w in workers if w.is_available()]),
            "busy": len([w for w in workers if w.status == WorkerStatus.BUSY]),
            "offline": len([w for w in workers if w.status == WorkerStatus.OFFLINE]),
            "gpu_workers": len([w for w in workers if w.has_gpu()]),
            "total_jobs_completed": sum(w.total_jobs_completed for w in workers),
        }

    async def _health_check_loop(self) -> None:
        """Periodically check for stale workers."""
        while True:
            try:
                await asyncio.sleep(30)
                await self._mark_stale_workers()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker health check error: {e}")

    async def _mark_stale_workers(self) -> None:
        """Mark workers as offline if heartbeat is stale."""
        async with await self._get_session() as session:
            repo = WorkerRepository(session)
            count = await repo.mark_stale_workers_offline(settings.worker_timeout_seconds)
            if count > 0:
                await session.commit()
                logger.warning(f"Marked {count} workers offline due to stale heartbeat")
