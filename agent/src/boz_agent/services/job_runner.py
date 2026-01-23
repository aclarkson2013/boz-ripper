"""Job execution service - polls for and executes assigned jobs."""

import asyncio
from pathlib import Path
from typing import Optional

import structlog

from boz_agent.core.config import Settings
from boz_agent.services.makemkv import MakeMKVService
from boz_agent.services.server_client import ServerClient
from boz_agent.services.worker import WorkerService, TranscodeJob

logger = structlog.get_logger()


class JobRunner:
    """Polls for assigned jobs and executes them."""

    def __init__(
        self,
        settings: Settings,
        server_client: ServerClient,
        makemkv: MakeMKVService,
    ):
        self.settings = settings
        self.server_client = server_client
        self.makemkv = makemkv

        # Worker for transcoding (if enabled)
        self.worker: Optional[WorkerService] = None
        if settings.worker.enabled:
            from boz_agent.core.config import HandBrakeConfig, WorkerConfig
            self.worker = WorkerService(settings.worker, settings.handbrake)

        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._current_job: Optional[dict] = None

    async def start(self) -> None:
        """Start the job runner."""
        self._running = True

        if self.worker:
            await self.worker.start()
            # Derive gpu_type from config flags
            gpu_type = "cpu"
            if self.settings.worker.nvenc:
                gpu_type = "nvenc"
            elif self.settings.worker.qsv:
                gpu_type = "qsv"
            logger.info("job_runner_started", worker_enabled=True, gpu=gpu_type)
        else:
            logger.info("job_runner_started", worker_enabled=False)

        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop the job runner."""
        self._running = False

        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

        if self.worker:
            await self.worker.stop()

        logger.info("job_runner_stopped")

    async def _poll_loop(self) -> None:
        """Poll for jobs and execute them."""
        while self._running:
            try:
                # Get assigned jobs
                jobs = await self.server_client.get_pending_jobs()

                for job in jobs:
                    if job.get("status") == "assigned":
                        await self._execute_job(job)

                await asyncio.sleep(5)  # Poll every 5 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("job_poll_error", error=str(e))
                await asyncio.sleep(10)

    async def _execute_job(self, job: dict) -> None:
        """Execute a single job."""
        job_id = job["job_id"]
        job_type = job["job_type"]

        logger.info("executing_job", job_id=job_id, job_type=job_type)
        self._current_job = job

        try:
            # Update status to running
            await self.server_client.update_job_status(job_id, "running", progress=0)

            if job_type == "rip":
                await self._execute_rip_job(job)
            elif job_type == "transcode":
                await self._execute_transcode_job(job)
            else:
                logger.warning("unknown_job_type", job_type=job_type)
                await self.server_client.update_job_status(
                    job_id, "failed", error=f"Unknown job type: {job_type}"
                )

        except Exception as e:
            logger.error("job_execution_failed", job_id=job_id, error=str(e))
            await self.server_client.update_job_status(job_id, "failed", error=str(e))

        finally:
            self._current_job = None

    async def _execute_rip_job(self, job: dict) -> None:
        """Execute a rip job using MakeMKV."""
        job_id = job["job_id"]
        disc_id = job.get("disc_id")
        title_index = job.get("title_index", 0)
        output_name = job.get("output_name", f"title_{title_index}")

        logger.info("starting_rip", job_id=job_id, title_index=title_index)

        # Get the disc info to find the drive
        disc = await self.server_client.get_disc(disc_id)
        if not disc:
            raise RuntimeError(f"Disc not found: {disc_id}")

        drive = disc.get("drive", "D:")

        # Create output directory
        output_dir = Path(self.settings.makemkv.temp_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Progress callback
        async def on_progress(progress: float):
            await self.server_client.update_job_status(job_id, "running", progress=progress)

        # Run MakeMKV
        output_file = await self.makemkv.rip_title(
            drive=drive,
            title_index=title_index,
            output_dir=output_dir,
            progress_callback=on_progress,
        )

        logger.info("rip_completed", job_id=job_id, output_file=str(output_file))

        # Update job with output file path
        await self.server_client.update_job_status(
            job_id, "completed", progress=100, output_file=str(output_file)
        )

        # If worker is enabled, automatically queue transcode
        if self.worker and self.settings.worker.enabled:
            logger.info("queuing_transcode", input_file=str(output_file))
            await self.server_client.create_transcode_job(
                input_file=str(output_file),
                output_name=output_name,
                preset=self.settings.handbrake.preset,
            )

    async def _execute_transcode_job(self, job: dict) -> None:
        """Execute a transcode job using HandBrake."""
        if not self.worker:
            raise RuntimeError("Worker not enabled for transcoding")

        job_id = job["job_id"]
        input_file = Path(job.get("input_file", ""))
        output_name = job.get("output_name", input_file.stem)
        preset = job.get("preset") or self.settings.handbrake.preset

        if not input_file.exists():
            raise RuntimeError(f"Input file not found: {input_file}")

        # Create output directory
        output_dir = Path(self.settings.worker.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"{output_name}.mkv"

        logger.info(
            "starting_transcode",
            job_id=job_id,
            input_file=str(input_file),
            output_file=str(output_file),
            preset=preset,
        )

        # Create transcode job for worker
        transcode_job = TranscodeJob(
            job_id=job_id,
            input_file=input_file,
            output_file=output_file,
            preset=preset,
            gpu_type=self.settings.worker.gpu_type,
        )

        # Submit to worker and wait for completion
        await self.worker.submit_job(transcode_job)

        # Poll for completion
        while True:
            status = self.worker.get_job_status(job_id)
            if not status:
                break

            await self.server_client.update_job_status(
                job_id, status.status, progress=status.progress
            )

            if status.status in ("completed", "failed"):
                break

            await asyncio.sleep(2)

        # Get final status
        final_status = self.worker.get_job_status(job_id)
        if final_status and final_status.status == "completed":
            logger.info("transcode_completed", job_id=job_id, output_file=str(output_file))

            # Upload to server
            await self._upload_file(output_file, output_name)

            await self.server_client.update_job_status(
                job_id, "completed", progress=100, output_file=str(output_file)
            )
        else:
            error = final_status.error if final_status else "Unknown error"
            await self.server_client.update_job_status(job_id, "failed", error=error)

    async def _upload_file(self, file_path: Path, name: str) -> None:
        """Upload a completed file to the server."""
        logger.info("uploading_file", file=str(file_path), name=name)

        try:
            await self.server_client.upload_file(file_path, name)
            logger.info("upload_completed", file=str(file_path))
        except Exception as e:
            logger.error("upload_failed", error=str(e))
            raise
