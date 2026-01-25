"""Job execution service - polls for and executes assigned jobs."""

import asyncio
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional

import structlog

from boz_agent.core.config import Settings
from boz_agent.services.makemkv import MakeMKVService
from boz_agent.services.server_client import ServerClient
from boz_agent.services.thumbnail_extractor import ThumbnailExtractor
from boz_agent.services.worker import WorkerService, TranscodeJob

logger = structlog.get_logger()


class JobRunner:
    """Polls for assigned jobs and executes them."""

    def __init__(
        self,
        settings: Settings,
        server_client: ServerClient,
        makemkv: MakeMKVService,
        on_disc_rips_complete: Optional[Callable[[str, str], Coroutine[Any, Any, None]]] = None,
    ):
        """Initialize the job runner.

        Args:
            settings: Agent settings
            server_client: Client for server communication
            makemkv: MakeMKV service for ripping
            on_disc_rips_complete: A18 callback when all rips for a disc finish.
                                   Called with (disc_id, drive) args.
        """
        self.settings = settings
        self.server_client = server_client
        self.makemkv = makemkv
        self.on_disc_rips_complete = on_disc_rips_complete

        # Thumbnail extractor for Stage 2 post-rip preview
        self.thumbnail_extractor = ThumbnailExtractor(settings.thumbnails)

        # Worker for transcoding (if enabled)
        self.worker: Optional[WorkerService] = None
        if settings.worker.enabled:
            from boz_agent.core.config import HandBrakeConfig, WorkerConfig
            self.worker = WorkerService(settings.worker, settings.handbrake)

        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._current_job: Optional[dict] = None
        self._rip_in_progress = False  # Only allow one rip at a time (single drive)

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
                    if job.get("status") != "assigned":
                        continue

                    job_type = job.get("job_type")

                    # Only allow ONE rip job at a time (single optical drive)
                    if job_type == "rip":
                        if self._rip_in_progress:
                            logger.debug("rip_job_queued", job_id=job["job_id"], reason="another rip in progress")
                            continue
                        # Execute the rip job (only one per poll cycle)
                        await self._execute_job(job)
                        break  # Don't process more jobs this cycle
                    else:
                        # Transcode jobs can run in parallel via WorkerService
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

        # Mark rip as in progress (only one at a time)
        self._rip_in_progress = True

        try:
            logger.info("starting_rip", job_id=job_id, title_index=title_index)

            # Get the disc info to find the drive
            disc = await self.server_client.get_disc(disc_id)
            if not disc:
                raise RuntimeError(f"Disc not found: {disc_id}")

            # Check preview approval status
            preview_status = disc.get("preview_status", "pending")
            if preview_status == "pending":
                logger.info(
                    "rip_waiting_for_preview_approval",
                    job_id=job_id,
                    disc_id=disc_id,
                    preview_status=preview_status,
                )
                # Don't fail the job, just return and let it be retried on next poll
                # Reset status back to assigned so it will be picked up again
                await self.server_client.update_job_status(job_id, "assigned", progress=0)
                return
            elif preview_status == "rejected":
                logger.warning("rip_preview_rejected", job_id=job_id, disc_id=disc_id)
                raise RuntimeError(f"Disc preview was rejected, cannot rip")

            # Preview is approved, proceed with rip
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

            logger.info("rip_completed", job_id=job_id, makemkv_output=str(output_file))

            # Rename the file to match our desired output_name
            # MakeMKV creates its own filename (e.g., G2_t05.mkv), we need to rename it
            desired_filename = f"{output_name}.mkv"
            desired_path = output_dir / desired_filename

            if output_file != desired_path:
                logger.info("renaming_output", from_file=str(output_file), to_file=str(desired_path))
                output_file.rename(desired_path)
                output_file = desired_path
                logger.info("file_renamed", final_path=str(output_file))

            logger.info("rip_finalized", job_id=job_id, output_file=str(output_file))
            # Update job with output file path
            await self.server_client.update_job_status(
                job_id, "completed", progress=100, output_file=str(output_file)
            )

            # Stage 2: Extract thumbnails from ripped MKV for visual verification
            thumbnails = None
            thumbnail_timestamps = None
            if self.settings.thumbnails.enabled and self.thumbnail_extractor.is_available():
                logger.info("extracting_post_rip_thumbnails", file=str(output_file))
                try:
                    thumb_result = await self.thumbnail_extractor.extract_from_mkv(
                        output_file,
                        title_index=title_index,
                    )
                    if thumb_result.thumbnails:
                        thumbnails = thumb_result.thumbnails
                        thumbnail_timestamps = thumb_result.timestamps
                        logger.info(
                            "post_rip_thumbnails_extracted",
                            count=len(thumbnails),
                            timestamps=thumbnail_timestamps,
                        )
                    else:
                        logger.warning(
                            "post_rip_thumbnail_extraction_failed",
                            errors=thumb_result.errors,
                        )
                except Exception as e:
                    logger.warning("post_rip_thumbnail_error", error=str(e))
            else:
                logger.debug("post_rip_thumbnails_skipped", reason="disabled or ffmpeg unavailable")

            # Queue transcode job for user approval (no auto-assignment)
            logger.info("queuing_transcode_for_approval", input_file=str(output_file))

            # Get file size for display in dashboard
            import os
            file_size = os.path.getsize(output_file) if output_file.exists() else None

            transcode_job = await self.server_client.create_transcode_job(
                input_file=str(output_file),
                output_name=output_name,
                preset=None,  # User will select via dashboard
                requires_approval=True,
                source_disc_name=disc.get("disc_name", output_name),
                input_file_size=file_size,
                thumbnails=thumbnails,
                thumbnail_timestamps=thumbnail_timestamps,
            )
            if transcode_job:
                logger.info("transcode_job_queued_for_approval", job_id=transcode_job.get("job_id"))

            # A18: Check if all rip jobs for this disc are complete
            await self._check_and_notify_disc_complete(disc_id, drive)

        finally:
            # Always reset the rip-in-progress flag
            self._rip_in_progress = False
            logger.debug("rip_lock_released", job_id=job_id)

    async def _check_and_notify_disc_complete(
        self, disc_id: str, drive: str
    ) -> None:
        """A18: Check if all rips for a disc are complete and notify callback.

        Args:
            disc_id: Disc identifier
            drive: Drive letter where disc is mounted
        """
        if not self.on_disc_rips_complete:
            return

        try:
            all_complete = await self.server_client.check_disc_rips_complete(disc_id)
            if all_complete:
                logger.info(
                    "all_disc_rips_complete",
                    disc_id=disc_id,
                    drive=drive,
                )
                # Call the callback (e.g., to eject the disc)
                await self.on_disc_rips_complete(disc_id, drive)
        except Exception as e:
            logger.warning(
                "disc_complete_check_failed",
                disc_id=disc_id,
                error=str(e),
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

        # Derive gpu_type from config flags
        gpu_type = "cpu"
        if self.settings.worker.nvenc:
            gpu_type = "nvenc"
        elif self.settings.worker.qsv:
            gpu_type = "qsv"

        # Create transcode job for worker
        transcode_job = TranscodeJob(
            job_id=job_id,
            input_file=input_file,
            output_file=output_file,
            preset=preset,
            gpu_type=gpu_type,
        )

        # Submit to worker and wait for completion
        await self.worker.submit_job(transcode_job)

        # Poll for completion with cancellation check
        cancellation_check_interval = 0
        while True:
            status = self.worker.get_job_status(job_id)
            if not status:
                break

            # W9: Check for cancellation every 10 seconds (every 5th iteration)
            cancellation_check_interval += 1
            if cancellation_check_interval >= 5:
                cancellation_check_interval = 0
                if await self.server_client.is_job_cancelled(job_id):
                    logger.info("job_cancelled_by_server", job_id=job_id)
                    await self.worker.cancel_job(job_id)
                    # Wait briefly for cancellation to complete
                    await asyncio.sleep(1)
                    break

            await self.server_client.update_job_status(
                job_id, status.status, progress=status.progress
            )

            if status.status in ("completed", "failed", "cancelled"):
                break

            await asyncio.sleep(2)

        # Get final status
        final_status = self.worker.get_job_status(job_id)

        if final_status and final_status.status == "cancelled":
            logger.info("transcode_cancelled", job_id=job_id)
            # Status already updated on server, just log and return
            return

        if final_status and final_status.status == "completed":
            logger.info("transcode_completed", job_id=job_id, output_file=str(output_file))

            # Try to upload to server (don't fail job if upload fails)
            upload_success = await self._upload_file(output_file, output_name)

            if upload_success:
                await self.server_client.update_job_status(
                    job_id, "completed", progress=100, output_file=str(output_file)
                )

                # A17: Cleanup staging files after successful upload
                await self._cleanup_staging_files(input_file, output_file)
            else:
                # Mark as completed but with upload error note
                await self.server_client.update_job_status(
                    job_id, "completed", progress=100, output_file=str(output_file),
                    error="Upload failed - file available locally for manual retry"
                )
        else:
            error = final_status.error if final_status else "Unknown error"
            await self.server_client.update_job_status(job_id, "failed", error=error)

    async def _upload_file(self, file_path: Path, name: str, retries: int = 3) -> bool:
        """Upload a completed file to the server with retries.

        Returns:
            True if upload succeeded, False otherwise
        """
        logger.info("uploading_file", file=str(file_path), name=name)

        for attempt in range(1, retries + 1):
            try:
                success = await self.server_client.upload_file(file_path, name)
                if success:
                    logger.info("upload_completed", file=str(file_path))
                    return True
                else:
                    logger.warning("upload_returned_false", file=str(file_path), attempt=attempt)
            except Exception as e:
                logger.error("upload_failed", file=str(file_path), error=str(e), attempt=attempt)
                if attempt < retries:
                    logger.info("upload_retrying", file=str(file_path), next_attempt=attempt + 1)
                    await asyncio.sleep(5 * attempt)  # Exponential backoff

        logger.error("upload_all_retries_failed", file=str(file_path), retries=retries)
        return False

    async def _cleanup_staging_files(
        self, input_file: Path, output_file: Path
    ) -> None:
        """A17: Delete staging files after successful upload.

        Cleans up:
        1. The ripped MKV file (input_file) from temp_dir
        2. The transcoded file (output_file) from output_dir

        Args:
            input_file: Path to the ripped MKV file (temp staging)
            output_file: Path to the transcoded file (output staging)
        """
        # Cleanup ripped MKV from temp directory
        if self.settings.makemkv.cleanup_after_transcode:
            if input_file.exists():
                try:
                    input_file.unlink()
                    logger.info(
                        "staging_file_deleted",
                        file=str(input_file),
                        type="ripped_mkv",
                    )
                except Exception as e:
                    logger.warning(
                        "staging_file_delete_failed",
                        file=str(input_file),
                        error=str(e),
                    )
            else:
                logger.debug(
                    "staging_file_not_found",
                    file=str(input_file),
                    type="ripped_mkv",
                )

        # Cleanup transcoded file from output directory
        if self.settings.worker.cleanup_after_upload:
            if output_file.exists():
                try:
                    output_file.unlink()
                    logger.info(
                        "staging_file_deleted",
                        file=str(output_file),
                        type="transcoded_mkv",
                    )
                except Exception as e:
                    logger.warning(
                        "staging_file_delete_failed",
                        file=str(output_file),
                        error=str(e),
                    )
            else:
                logger.debug(
                    "staging_file_not_found",
                    file=str(output_file),
                    type="transcoded_mkv",
                )
