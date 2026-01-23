"""Worker-related models for transcoding."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class WorkerType(str, Enum):
    """Type of worker."""

    AGENT = "agent"      # Worker on same machine as ripping agent
    REMOTE = "remote"    # Dedicated remote worker (e.g., Proxmox)
    SERVER = "server"    # Server-side CPU fallback


class WorkerStatus(str, Enum):
    """Worker connection status."""

    AVAILABLE = "available"
    BUSY = "busy"
    OFFLINE = "offline"


class WorkerCapabilities(BaseModel):
    """Hardware capabilities of a worker."""

    # GPU acceleration
    nvenc: bool = False           # NVIDIA NVENC
    nvenc_generation: int = 0     # NVENC generation (8 = RTX 4080)
    qsv: bool = False             # Intel QuickSync
    vaapi: bool = False           # Linux VA-API

    # Codec support
    hevc: bool = False            # H.265 encoding
    av1: bool = False             # AV1 encoding

    # CPU info
    cpu_threads: int = 4

    # Capacity
    max_concurrent: int = 2


class WorkerRegistration(BaseModel):
    """Request to register a new worker."""

    worker_id: str
    worker_type: WorkerType = WorkerType.AGENT
    hostname: str
    capabilities: WorkerCapabilities = Field(default_factory=WorkerCapabilities)
    priority: int = 50  # 1-99, lower = higher priority


class WorkerHeartbeat(BaseModel):
    """Worker heartbeat update."""

    status: WorkerStatus = WorkerStatus.AVAILABLE
    current_jobs: list[str] = Field(default_factory=list)
    cpu_usage: Optional[float] = None  # 0-100
    gpu_usage: Optional[float] = None  # 0-100


class Worker(BaseModel):
    """Registered transcoding worker."""

    worker_id: str
    worker_type: WorkerType = WorkerType.AGENT
    hostname: str
    capabilities: WorkerCapabilities = Field(default_factory=WorkerCapabilities)

    # Priority and status
    priority: int = 50  # 1-99, lower = higher priority
    enabled: bool = True
    status: WorkerStatus = WorkerStatus.AVAILABLE

    # Current work
    current_jobs: list[str] = Field(default_factory=list)

    # Health tracking
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    registered_at: datetime = Field(default_factory=datetime.utcnow)

    # Stats
    total_jobs_completed: int = 0
    avg_transcode_time_seconds: float = 0.0

    # Resource usage
    cpu_usage: Optional[float] = None
    gpu_usage: Optional[float] = None

    def is_available(self) -> bool:
        """Check if worker is available for new jobs."""
        if not self.enabled or self.status == WorkerStatus.OFFLINE:
            return False
        return len(self.current_jobs) < self.capabilities.max_concurrent

    def has_gpu(self) -> bool:
        """Check if worker has GPU acceleration."""
        return self.capabilities.nvenc or self.capabilities.qsv or self.capabilities.vaapi

    def get_encoder_name(self) -> str:
        """Get the name of the best available encoder."""
        if self.capabilities.nvenc:
            return f"NVENC (gen {self.capabilities.nvenc_generation})"
        if self.capabilities.qsv:
            return "QuickSync"
        if self.capabilities.vaapi:
            return "VA-API"
        return f"CPU ({self.capabilities.cpu_threads} threads)"


class WorkerAssignment(BaseModel):
    """Response when assigning a job to a worker."""

    assigned_worker: str
    worker_type: WorkerType
    mode: str  # "local" or "upload_raw"
    handbrake_preset: str
    upload_url: Optional[str] = None
    download_url: Optional[str] = None


class TranscodeJob(BaseModel):
    """A transcode job for a worker to process."""

    job_id: str
    input_file: str
    output_name: str
    handbrake_preset: str
    download_url: Optional[str] = None  # For remote workers
    upload_url: Optional[str] = None    # For remote workers
