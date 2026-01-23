"""Job-related models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Status of a job."""

    PENDING = "pending"
    QUEUED = "queued"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    """Type of job."""

    RIP = "rip"
    TRANSCODE = "transcode"
    ORGANIZE = "organize"


class JobCreate(BaseModel):
    """Request to create a new job."""

    job_type: JobType
    disc_id: Optional[str] = None
    title_index: Optional[int] = None
    input_file: Optional[str] = None
    output_name: Optional[str] = None
    preset: Optional[str] = None
    priority: int = 0  # Higher = more urgent

    # Approval workflow fields
    requires_approval: bool = False
    source_disc_name: Optional[str] = None
    input_file_size: Optional[int] = None


class JobApprovalRequest(BaseModel):
    """Request to approve a pending transcode job."""

    worker_id: str
    preset: str


class JobUpdate(BaseModel):
    """Request to update job status."""

    status: JobStatus
    progress: Optional[float] = None  # 0-100
    error: Optional[str] = None
    output_file: Optional[str] = None


class Job(BaseModel):
    """A job in the system."""

    job_id: str
    job_type: JobType
    status: JobStatus = JobStatus.PENDING
    priority: int = 0

    # Source info
    disc_id: Optional[str] = None
    title_index: Optional[int] = None
    input_file: Optional[str] = None

    # Output info
    output_name: Optional[str] = None
    output_file: Optional[str] = None
    preset: Optional[str] = None

    # Assignment
    assigned_agent_id: Optional[str] = None
    assigned_at: Optional[datetime] = None

    # Approval workflow
    requires_approval: bool = False
    source_disc_name: Optional[str] = None
    input_file_size: Optional[int] = None

    # Progress tracking
    progress: float = 0.0
    error: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
