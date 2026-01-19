"""Agent-related models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    """Agent connection status."""

    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"


class AgentCapabilities(BaseModel):
    """What an agent can do."""

    can_rip: bool = True
    can_transcode: bool = False
    gpu_type: Optional[str] = None  # nvidia, amd, intel, none


class AgentRegistration(BaseModel):
    """Request to register a new agent."""

    agent_id: str
    name: str
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)


class Agent(BaseModel):
    """Registered agent."""

    agent_id: str
    name: str
    status: AgentStatus = AgentStatus.ONLINE
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    current_job_id: Optional[str] = None
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    registered_at: datetime = Field(default_factory=datetime.utcnow)

    def is_available(self) -> bool:
        """Check if agent is available for work."""
        return self.status == AgentStatus.ONLINE and self.current_job_id is None
