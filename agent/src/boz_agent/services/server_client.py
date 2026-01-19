"""HTTP client for communicating with the Boz Ripper server."""

import asyncio
from typing import Any, Optional
from uuid import uuid4

import httpx
import structlog

from boz_agent.core.config import AgentConfig, ServerConfig

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
