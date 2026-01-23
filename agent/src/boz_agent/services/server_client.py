"""HTTP client for communicating with the Boz Ripper server."""

import asyncio
from typing import Any, Optional
from uuid import uuid4

import httpx
import structlog

from boz_agent.core.config import AgentConfig, ServerConfig, WorkerConfig

logger = structlog.get_logger()


class ServerClient:
    """Client for the Boz Ripper server REST API."""

    def __init__(self, config: ServerConfig):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        self._agent_id: Optional[str] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.config.url,
                timeout=self.config.timeout,
                headers=self._get_headers(),
            )
        return self._client

    def _get_headers(self) -> dict[str, str]:
        """Get request headers including authentication."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "BozAgent/0.1.0",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    async def register(self, agent_config: AgentConfig) -> str:
        """Register this agent with the server.

        Args:
            agent_config: Agent configuration

        Returns:
            Assigned agent ID
        """
        client = await self._get_client()

        agent_id = agent_config.id or str(uuid4())

        payload = {
            "agent_id": agent_id,
            "name": agent_config.name,
            "capabilities": {
                "can_rip": True,
                "can_transcode": False,  # Set based on worker config
            },
        }

        try:
            response = await client.post("/api/agents/register", json=payload)
            response.raise_for_status()

            data = response.json()
            self._agent_id = data.get("agent_id", agent_id)

            logger.info("agent_registered", agent_id=self._agent_id)

            # Start heartbeat
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            return self._agent_id

        except httpx.HTTPStatusError as e:
            logger.error(
                "registration_failed",
                status_code=e.response.status_code,
                detail=e.response.text,
            )
            raise
        except httpx.RequestError as e:
            logger.warning(
                "server_unreachable",
                url=self.config.url,
                error=str(e),
            )
            # Continue in offline mode
            self._agent_id = agent_id
            return agent_id

    async def unregister(self) -> None:
        """Unregister this agent from the server."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if not self._agent_id:
            return

        try:
            client = await self._get_client()
            await client.post(f"/api/agents/{self._agent_id}/unregister")
            logger.info("agent_unregistered", agent_id=self._agent_id)
        except Exception as e:
            logger.warning("unregister_failed", error=str(e))
        finally:
            if self._client:
                await self._client.aclose()
                self._client = None

    async def report_disc(self, drive: str, analysis: Any) -> None:
        """Report a detected disc to the server.

        Args:
            drive: Drive letter where disc was detected
            analysis: DiscAnalysis object from MakeMKV
        """
        if not self._agent_id:
            logger.warning("cannot_report_disc_not_registered")
            return

        payload = {
            "agent_id": self._agent_id,
            "drive": drive,
            "disc_name": analysis.disc_name,
            "disc_type": analysis.disc_type,
            "titles": [
                {
                    "index": t.index,
                    "name": t.name,
                    "duration_seconds": t.duration_seconds,
                    "size_bytes": t.size_bytes,
                    "chapters": t.chapters,
                }
                for t in analysis.titles
            ],
        }

        try:
            client = await self._get_client()
            response = await client.post("/api/discs/detected", json=payload)
            response.raise_for_status()
            logger.info("disc_reported", drive=drive, disc_name=analysis.disc_name)
        except Exception as e:
            logger.error("disc_report_failed", error=str(e))

    async def report_disc_ejected(self, drive: str) -> None:
        """Report that a disc was ejected.

        Args:
            drive: Drive letter where disc was ejected
        """
        if not self._agent_id:
            return

        try:
            client = await self._get_client()
            await client.post(
                "/api/discs/ejected",
                json={"agent_id": self._agent_id, "drive": drive},
            )
            logger.info("disc_ejection_reported", drive=drive)
        except Exception as e:
            logger.warning("disc_ejection_report_failed", error=str(e))

    async def get_pending_jobs(self) -> list[dict]:
        """Get pending jobs for this agent.

        Returns:
            List of job dictionaries
        """
        if not self._agent_id:
            return []

        try:
            client = await self._get_client()
            response = await client.get(f"/api/agents/{self._agent_id}/jobs")
            response.raise_for_status()
            return response.json().get("jobs", [])
        except Exception as e:
            logger.warning("get_jobs_failed", error=str(e))
            return []

    async def update_job_status(
        self,
        job_id: str,
        status: str,
        progress: Optional[float] = None,
        error: Optional[str] = None,
        output_file: Optional[str] = None,
    ) -> None:
        """Update the status of a job.

        Args:
            job_id: Job identifier
            status: New status (running, completed, failed)
            progress: Progress percentage (0-100)
            error: Error message if failed
            output_file: Path to output file (if completed)
        """
        payload = {
            "status": status,
            "progress": progress,
            "error": error,
            "output_file": output_file,
        }

        try:
            client = await self._get_client()
            await client.patch(f"/api/jobs/{job_id}", json=payload)
            logger.debug("job_status_updated", job_id=job_id, status=status)
        except Exception as e:
            logger.warning("job_status_update_failed", error=str(e))

    async def get_disc(self, disc_id: str) -> Optional[dict]:
        """Get disc information by ID.

        Args:
            disc_id: Disc identifier

        Returns:
            Disc info dict or None if not found
        """
        try:
            client = await self._get_client()
            response = await client.get(f"/api/discs/{disc_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning("get_disc_failed", disc_id=disc_id, error=str(e))
            return None

    async def create_transcode_job(
        self,
        input_file: str,
        output_name: str,
        preset: Optional[str] = None,
    ) -> Optional[dict]:
        """Create a transcode job on the server.

        Args:
            input_file: Path to input file
            output_name: Name for output file
            preset: HandBrake preset to use

        Returns:
            Created job dict or None if failed
        """
        payload = {
            "job_type": "transcode",
            "input_file": input_file,
            "output_name": output_name,
            "preset": preset,
        }

        try:
            client = await self._get_client()
            response = await client.post("/api/jobs", json=payload)
            response.raise_for_status()
            job = response.json()
            logger.info("transcode_job_created", job_id=job.get("job_id"))
            return job
        except Exception as e:
            logger.error("create_transcode_job_failed", error=str(e))
            return None

    async def upload_file(self, file_path: Any, name: str) -> bool:
        """Upload a file to the server.

        Args:
            file_path: Path to file to upload
            name: Name/identifier for the file

        Returns:
            True if successful
        """
        from pathlib import Path
        file_path = Path(file_path)

        if not file_path.exists():
            logger.error("upload_file_not_found", path=str(file_path))
            return False

        try:
            # Use a separate client for file uploads with longer timeout
            async with httpx.AsyncClient(
                base_url=self.config.url,
                timeout=3600,  # 1 hour timeout for large files
            ) as client:
                with open(file_path, "rb") as f:
                    files = {"file": (file_path.name, f, "application/octet-stream")}
                    data = {"name": name}

                    headers = {}
                    if self.config.api_key:
                        headers["Authorization"] = f"Bearer {self.config.api_key}"

                    response = await client.post(
                        "/api/files/upload",
                        files=files,
                        data=data,
                        headers=headers,
                    )
                    response.raise_for_status()

            logger.info("file_uploaded", path=str(file_path), name=name)
            return True

        except Exception as e:
            logger.error("file_upload_failed", error=str(e))
            return False

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to the server."""
        while True:
            try:
                await asyncio.sleep(30)  # Heartbeat every 30 seconds
                await self._send_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("heartbeat_failed", error=str(e))

    async def _send_heartbeat(self) -> None:
        """Send a single heartbeat."""
        if not self._agent_id:
            return

        try:
            client = await self._get_client()
            await client.post(f"/api/agents/{self._agent_id}/heartbeat")
            logger.debug("heartbeat_sent")
        except Exception as e:
            logger.warning("heartbeat_failed", error=str(e))

    # Worker registration methods

    async def register_worker(
        self,
        worker_config: WorkerConfig,
        agent_name: str,
    ) -> Optional[str]:
        """Register this agent as a transcoding worker.

        Args:
            worker_config: Worker configuration
            agent_name: Name for the worker

        Returns:
            Worker ID if successful
        """
        import socket
        import os

        # Generate worker ID if not set
        worker_id = worker_config.worker_id
        if not worker_id:
            hostname = socket.gethostname()
            # Include GPU info in worker ID if available
            if worker_config.nvenc:
                worker_id = f"{hostname}-NVENC"
            elif worker_config.qsv:
                worker_id = f"{hostname}-QSV"
            else:
                worker_id = f"{hostname}-CPU"

        # Detect CPU threads
        cpu_threads = os.cpu_count() or 4

        payload = {
            "worker_id": worker_id,
            "worker_type": "agent",
            "hostname": socket.gethostname(),
            "capabilities": {
                "nvenc": worker_config.nvenc,
                "nvenc_generation": 8 if worker_config.nvenc else 0,  # Assume RTX 40 series
                "qsv": worker_config.qsv,
                "vaapi": False,
                "hevc": worker_config.hevc,
                "av1": worker_config.av1,
                "cpu_threads": cpu_threads,
                "max_concurrent": worker_config.max_concurrent_jobs,
            },
            "priority": worker_config.priority,
        }

        try:
            client = await self._get_client()
            response = await client.post("/api/workers/register", json=payload)
            response.raise_for_status()

            data = response.json()
            registered_id = data.get("worker_id", worker_id)

            logger.info(
                "worker_registered",
                worker_id=registered_id,
                priority=worker_config.priority,
                nvenc=worker_config.nvenc,
            )

            # Start worker heartbeat
            self._worker_id = registered_id
            self._worker_heartbeat_task = asyncio.create_task(self._worker_heartbeat_loop())

            return registered_id

        except httpx.HTTPStatusError as e:
            logger.error(
                "worker_registration_failed",
                status_code=e.response.status_code,
                detail=e.response.text,
            )
            return None
        except httpx.RequestError as e:
            logger.warning(
                "worker_registration_server_unreachable",
                url=self.config.url,
                error=str(e),
            )
            return None

    async def worker_heartbeat(
        self,
        status: str = "available",
        current_jobs: Optional[list[str]] = None,
        cpu_usage: Optional[float] = None,
        gpu_usage: Optional[float] = None,
    ) -> bool:
        """Send worker heartbeat.

        Args:
            status: Worker status (available, busy, offline)
            current_jobs: List of current job IDs
            cpu_usage: CPU usage percentage
            gpu_usage: GPU usage percentage

        Returns:
            True if successful
        """
        if not hasattr(self, '_worker_id') or not self._worker_id:
            return False

        payload = {
            "status": status,
            "current_jobs": current_jobs or [],
            "cpu_usage": cpu_usage,
            "gpu_usage": gpu_usage,
        }

        try:
            client = await self._get_client()
            await client.post(
                f"/api/workers/{self._worker_id}/heartbeat",
                json=payload,
            )
            logger.debug("worker_heartbeat_sent")
            return True
        except Exception as e:
            logger.warning("worker_heartbeat_failed", error=str(e))
            return False

    async def request_worker_assignment(
        self,
        disc_type: str = "dvd",
        file_size_mb: int = 0,
    ) -> Optional[dict]:
        """Request a worker assignment for transcoding.

        Args:
            disc_type: Type of disc (dvd, bluray)
            file_size_mb: Size of file to transcode

        Returns:
            Assignment dict with worker details and preset
        """
        if not self._agent_id:
            return None

        payload = {
            "agent_id": self._agent_id,
            "disc_type": disc_type,
            "file_size_mb": file_size_mb,
        }

        try:
            client = await self._get_client()
            response = await client.post("/api/workers/assign", json=payload)
            response.raise_for_status()

            assignment = response.json()
            logger.info(
                "worker_assignment_received",
                worker=assignment.get("assigned_worker"),
                mode=assignment.get("mode"),
                preset=assignment.get("handbrake_preset"),
            )
            return assignment

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 503:
                logger.warning("no_workers_available")
            else:
                logger.error("worker_assignment_failed", error=str(e))
            return None
        except Exception as e:
            logger.error("worker_assignment_error", error=str(e))
            return None

    async def complete_worker_job(
        self,
        job_id: str,
        duration_seconds: float = 0,
        success: bool = True,
        error: Optional[str] = None,
    ) -> bool:
        """Mark a transcode job as complete.

        Args:
            job_id: Job identifier
            duration_seconds: How long transcoding took
            success: Whether job succeeded
            error: Error message if failed

        Returns:
            True if successful
        """
        if not hasattr(self, '_worker_id') or not self._worker_id:
            return False

        payload = {
            "job_id": job_id,
            "duration_seconds": duration_seconds,
            "success": success,
            "error": error,
        }

        try:
            client = await self._get_client()
            response = await client.post(
                f"/api/workers/{self._worker_id}/jobs/complete",
                json=payload,
            )
            response.raise_for_status()
            logger.info("worker_job_completed", job_id=job_id, success=success)
            return True
        except Exception as e:
            logger.error("worker_job_complete_failed", error=str(e))
            return False

    async def _worker_heartbeat_loop(self) -> None:
        """Send periodic worker heartbeats."""
        while True:
            try:
                await asyncio.sleep(30)
                await self.worker_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("worker_heartbeat_loop_error", error=str(e))

    async def stop_worker(self) -> None:
        """Stop the worker and cancel heartbeat task."""
        if hasattr(self, '_worker_heartbeat_task') and self._worker_heartbeat_task:
            self._worker_heartbeat_task.cancel()
            try:
                await self._worker_heartbeat_task
            except asyncio.CancelledError:
                pass
            self._worker_heartbeat_task = None
            logger.info("worker_stopped")
