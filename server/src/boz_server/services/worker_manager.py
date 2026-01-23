"""Worker registration and management service."""

import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from boz_server.core.config import settings
from boz_server.models.worker import (
    Worker,
    WorkerCapabilities,
    WorkerStatus,
    WorkerType,
    WorkerAssignment,
    TranscodeJob,
)

logger = logging.getLogger(__name__)


class AssignmentStrategy(str, Enum):
    """Strategy for assigning jobs to workers."""

    PRIORITY = "priority"          # Always use highest priority available
    ROUND_ROBIN = "round_robin"    # Distribute evenly
    LOAD_BALANCE = "load_balance"  # Assign to least loaded
    FASTEST_FIRST = "fastest_first"  # Use worker with best historical times


class WorkerManager:
    """Manages transcoding workers."""

    def __init__(self):
        self._workers: dict[str, Worker] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._assignment_strategy = AssignmentStrategy.PRIORITY
        self._round_robin_index = 0

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

    def register(
        self,
        worker_id: str,
        worker_type: WorkerType,
        hostname: str,
        capabilities: Optional[WorkerCapabilities] = None,
        priority: int = 50,
        agent_id: Optional[str] = None,
    ) -> Worker:
        """Register a new worker or update existing."""
        if worker_id in self._workers:
            # Update existing worker
            worker = self._workers[worker_id]
            worker.hostname = hostname
            worker.worker_type = worker_type
            worker.status = WorkerStatus.AVAILABLE
            worker.last_heartbeat = datetime.utcnow()
            if capabilities:
                worker.capabilities = capabilities
            if priority:
                worker.priority = priority
            if agent_id:
                worker.agent_id = agent_id
            logger.info(f"Worker reconnected: {worker_id} ({hostname})")
        else:
            # Create new worker
            worker = Worker(
                worker_id=worker_id,
                worker_type=worker_type,
                hostname=hostname,
                capabilities=capabilities or WorkerCapabilities(),
                priority=priority,
                agent_id=agent_id,
            )
            self._workers[worker_id] = worker
            logger.info(
                f"Worker registered: {worker_id} ({hostname}) - "
                f"Priority {priority}, {worker.get_encoder_name()}, agent={agent_id}"
            )

        return worker

    def unregister(self, worker_id: str) -> bool:
        """Unregister a worker."""
        if worker_id in self._workers:
            del self._workers[worker_id]
            logger.info(f"Worker unregistered: {worker_id}")
            return True
        return False

    def heartbeat(
        self,
        worker_id: str,
        status: WorkerStatus = WorkerStatus.AVAILABLE,
        current_jobs: Optional[list[str]] = None,
        cpu_usage: Optional[float] = None,
        gpu_usage: Optional[float] = None,
    ) -> bool:
        """Update worker heartbeat and status."""
        worker = self._workers.get(worker_id)
        if not worker:
            return False

        worker.last_heartbeat = datetime.utcnow()
        worker.status = status
        if current_jobs is not None:
            worker.current_jobs = current_jobs
        if cpu_usage is not None:
            worker.cpu_usage = cpu_usage
        if gpu_usage is not None:
            worker.gpu_usage = gpu_usage

        return True

    def get(self, worker_id: str) -> Optional[Worker]:
        """Get a worker by ID."""
        return self._workers.get(worker_id)

    def get_all(self) -> list[Worker]:
        """Get all registered workers."""
        return list(self._workers.values())

    def get_available(self) -> list[Worker]:
        """Get all available workers sorted by priority."""
        available = [w for w in self._workers.values() if w.is_available()]
        available.sort(key=lambda w: w.priority)
        return available

    def get_by_type(self, worker_type: WorkerType) -> list[Worker]:
        """Get workers of a specific type."""
        return [w for w in self._workers.values() if w.worker_type == worker_type]

    def update_priority(self, worker_id: str, priority: int) -> bool:
        """Update a worker's priority."""
        worker = self._workers.get(worker_id)
        if worker:
            worker.priority = max(1, min(99, priority))
            logger.info(f"Worker {worker_id} priority updated to {worker.priority}")
            return True
        return False

    def enable_worker(self, worker_id: str, enabled: bool = True) -> bool:
        """Enable or disable a worker."""
        worker = self._workers.get(worker_id)
        if worker:
            worker.enabled = enabled
            logger.info(f"Worker {worker_id} {'enabled' if enabled else 'disabled'}")
            return True
        return False

    def assign_job(self, worker_id: str, job_id: str) -> bool:
        """Assign a job to a specific worker."""
        worker = self._workers.get(worker_id)
        if worker and worker.is_available():
            worker.current_jobs.append(job_id)
            if len(worker.current_jobs) >= worker.capabilities.max_concurrent:
                worker.status = WorkerStatus.BUSY
            logger.info(f"Job {job_id} assigned to worker {worker_id}")
            return True
        return False

    def complete_job(self, worker_id: str, job_id: str, duration_seconds: float = 0) -> bool:
        """Mark a job as complete on a worker."""
        worker = self._workers.get(worker_id)
        if worker and job_id in worker.current_jobs:
            worker.current_jobs.remove(job_id)
            worker.total_jobs_completed += 1

            # Update average transcode time
            if duration_seconds > 0:
                total_time = worker.avg_transcode_time_seconds * (worker.total_jobs_completed - 1)
                worker.avg_transcode_time_seconds = (total_time + duration_seconds) / worker.total_jobs_completed

            # Update status
            if worker.status == WorkerStatus.BUSY and len(worker.current_jobs) < worker.capabilities.max_concurrent:
                worker.status = WorkerStatus.AVAILABLE

            logger.info(f"Job {job_id} completed on worker {worker_id}")
            return True
        return False

    def select_worker_for_job(
        self,
        prefer_gpu: bool = True,
        required_codec: Optional[str] = None,
    ) -> Optional[Worker]:
        """Select the best available worker for a job based on strategy."""
        available = self.get_available()
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
            available.sort(key=lambda w: w.avg_transcode_time_seconds or float('inf'))
            return available[0]

        return available[0]

    def request_worker_assignment(
        self,
        job_id: str,
        agent_id: str,
        disc_type: str = "dvd",
        file_size_mb: int = 0,
    ) -> Optional[WorkerAssignment]:
        """Request a worker assignment for a transcode job.

        Returns assignment details including whether to transcode locally
        or upload raw files for remote transcoding.
        """
        # Check if agent has a local worker
        agent_worker = None
        for worker in self._workers.values():
            if worker.worker_type == WorkerType.AGENT and agent_id in worker.worker_id:
                if worker.is_available():
                    agent_worker = worker
                    break

        # Select best worker
        selected = self.select_worker_for_job(prefer_gpu=True)
        if not selected:
            logger.warning(f"No available workers for job {job_id}")
            return None

        # Determine transcoding mode
        if selected.worker_type == WorkerType.AGENT and agent_worker and selected.worker_id == agent_worker.worker_id:
            # Local transcoding on agent
            mode = "local"
            download_url = None
            upload_url = f"/api/files/upload"
        else:
            # Remote transcoding - need to upload raw files
            mode = "upload_raw"
            download_url = f"/api/files/download/{job_id}"
            upload_url = f"/api/files/upload"

        # Select preset based on disc type
        if disc_type.lower() == "bluray":
            if selected.capabilities.nvenc:
                preset = "H.265 NVENC 1080p"
            elif selected.capabilities.qsv:
                preset = "H.265 QSV 1080p"
            else:
                preset = "H.265 CPU 1080p"
        else:
            if selected.capabilities.nvenc:
                preset = "H.264 NVENC 720p"
            elif selected.capabilities.qsv:
                preset = "H.264 QSV 720p"
            else:
                preset = "H.264 CPU 720p"

        # Assign the job
        self.assign_job(selected.worker_id, job_id)

        logger.info(
            f"Worker assignment: job {job_id} -> {selected.worker_id} "
            f"(mode={mode}, preset={preset})"
        )

        return WorkerAssignment(
            assigned_worker=selected.worker_id,
            worker_type=selected.worker_type,
            mode=mode,
            handbrake_preset=preset,
            download_url=download_url,
            upload_url=upload_url,
        )

    def get_pending_jobs_for_worker(self, worker_id: str, max_jobs: int = 1) -> list[TranscodeJob]:
        """Get pending transcode jobs for a remote worker to process.

        This is used by remote workers polling for work.
        """
        # This would integrate with JobQueue - for now return empty
        # In full implementation, query JobQueue for unassigned transcode jobs
        return []

    def get_stats(self) -> dict:
        """Get worker statistics."""
        workers = list(self._workers.values())
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
                self._mark_stale_workers()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker health check error: {e}")

    def _mark_stale_workers(self) -> None:
        """Mark workers as offline if heartbeat is stale."""
        timeout = timedelta(seconds=settings.worker_timeout_seconds)
        now = datetime.utcnow()

        for worker in self._workers.values():
            if worker.status != WorkerStatus.OFFLINE:
                if now - worker.last_heartbeat > timeout:
                    old_status = worker.status
                    worker.status = WorkerStatus.OFFLINE

                    # Reassign jobs if worker went offline while busy
                    if old_status == WorkerStatus.BUSY and worker.current_jobs:
                        logger.warning(
                            f"Worker {worker.worker_id} went offline with "
                            f"{len(worker.current_jobs)} active jobs"
                        )
                        # Jobs would need to be reassigned via JobQueue
                        worker.current_jobs = []

                    logger.warning(f"Worker marked offline: {worker.worker_id}")
