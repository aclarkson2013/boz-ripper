"""Local transcoding worker service."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import structlog

from boz_agent.core.config import HandBrakeConfig, WorkerConfig

logger = structlog.get_logger()


@dataclass
class TranscodeJob:
    """Represents a transcoding job."""

    job_id: str
    input_file: Path
    output_file: Path
    preset: str
    gpu_type: str = "none"
    progress: float = 0.0
    status: str = "pending"


class WorkerService:
    """Local transcoding worker using HandBrake."""

    def __init__(self, worker_config: WorkerConfig, handbrake_config: HandBrakeConfig):
        self.worker_config = worker_config
        self.handbrake_config = handbrake_config

        self._running = False
        self._current_jobs: dict[str, TranscodeJob] = {}
        self._job_queue: asyncio.Queue[TranscodeJob] = asyncio.Queue()
        self._worker_tasks: list[asyncio.Task] = []

    def is_available(self) -> bool:
        """Check if HandBrake is installed."""
        return Path(self.handbrake_config.executable).exists()

    async def start(self) -> None:
        """Start the worker service."""
        if not self.worker_config.enabled:
            logger.info("worker_disabled")
            return

        if not self.is_available():
            logger.warning(
                "handbrake_not_found",
                path=self.handbrake_config.executable,
            )
            return

        self._running = True

        # Start worker tasks
        max_jobs = self.worker_config.max_concurrent_jobs
        for i in range(max_jobs):
            task = asyncio.create_task(self._worker_loop(i))
            self._worker_tasks.append(task)

        # Determine GPU type
        gpu_type = "none"
        if self.worker_config.nvenc:
            gpu_type = "nvenc"
        elif self.worker_config.qsv:
            gpu_type = "qsv"

        logger.info(
            "worker_started",
            max_jobs=max_jobs,
            gpu_type=gpu_type,
        )

    async def stop(self) -> None:
        """Stop the worker service."""
        self._running = False

        for task in self._worker_tasks:
            task.cancel()

        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()

        logger.info("worker_stopped")

    async def submit_job(self, job: TranscodeJob) -> None:
        """Submit a job for transcoding."""
        self._current_jobs[job.job_id] = job
        await self._job_queue.put(job)
        logger.info("job_submitted", job_id=job.job_id)

    def get_job_status(self, job_id: str) -> Optional[TranscodeJob]:
        """Get the status of a job."""
        return self._current_jobs.get(job_id)

    async def _worker_loop(self, worker_id: int) -> None:
        """Main worker loop."""
        logger.info("worker_task_started", worker_id=worker_id)

        while self._running:
            try:
                # Wait for a job
                job = await asyncio.wait_for(
                    self._job_queue.get(),
                    timeout=5.0,
                )

                await self._process_job(job, worker_id)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("worker_error", worker_id=worker_id, error=str(e))

    async def _process_job(self, job: TranscodeJob, worker_id: int) -> None:
        """Process a single transcoding job."""
        logger.info(
            "processing_job",
            job_id=job.job_id,
            worker_id=worker_id,
            input_file=str(job.input_file),
        )

        job.status = "running"

        try:
            # Build HandBrake command
            cmd = self._build_handbrake_command(job)

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            # Monitor progress
            while True:
                line = await process.stdout.readline()
                if not line:
                    break

                line_str = line.decode("utf-8", errors="replace").strip()
                progress = self._parse_progress(line_str)
                if progress is not None:
                    job.progress = progress

            await process.wait()

            if process.returncode == 0:
                job.status = "completed"
                job.progress = 100.0
                logger.info("job_completed", job_id=job.job_id)
            else:
                job.status = "failed"
                logger.error(
                    "job_failed",
                    job_id=job.job_id,
                    returncode=process.returncode,
                )

        except Exception as e:
            job.status = "failed"
            logger.error("job_error", job_id=job.job_id, error=str(e))

    def _build_handbrake_command(self, job: TranscodeJob) -> list[str]:
        """Build the HandBrake CLI command."""
        cmd = [
            self.handbrake_config.executable,
            "-i",
            str(job.input_file),
            "-o",
            str(job.output_file),
            "--preset",
            job.preset or self.handbrake_config.preset,
        ]

        # Add GPU acceleration if configured
        gpu_type = job.gpu_type or self.worker_config.gpu_type

        if gpu_type == "nvidia":
            cmd.extend(["--encoder", "nvenc_h265"])
        elif gpu_type == "amd":
            cmd.extend(["--encoder", "vce_h265"])
        elif gpu_type == "intel":
            cmd.extend(["--encoder", "qsv_h265"])

        return cmd

    def _parse_progress(self, line: str) -> Optional[float]:
        """Parse HandBrake progress output."""
        # HandBrake outputs: Encoding: task 1 of 1, 45.67 %
        if "Encoding:" in line and "%" in line:
            try:
                # Extract percentage
                parts = line.split("%")[0].split()
                if parts:
                    return float(parts[-1])
            except (ValueError, IndexError):
                pass
        return None
