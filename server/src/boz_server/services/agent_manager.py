"""Agent registration and management service."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from boz_server.core.config import settings
from boz_server.models.agent import Agent, AgentCapabilities, AgentStatus

logger = logging.getLogger(__name__)


class AgentManager:
    """Manages connected agents."""

    def __init__(self):
        self._agents: dict[str, Agent] = {}
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the agent manager background tasks."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Agent manager started")

    async def stop(self) -> None:
        """Stop the agent manager."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("Agent manager stopped")

    def register(
        self,
        agent_id: str,
        name: str,
        capabilities: Optional[AgentCapabilities] = None,
    ) -> Agent:
        """Register a new agent or update existing."""
        if agent_id in self._agents:
            # Update existing agent
            agent = self._agents[agent_id]
            agent.name = name
            agent.status = AgentStatus.ONLINE
            agent.last_heartbeat = datetime.utcnow()
            if capabilities:
                agent.capabilities = capabilities
            logger.info(f"Agent reconnected: {agent_id} ({name})")
        else:
            # Create new agent
            agent = Agent(
                agent_id=agent_id,
                name=name,
                capabilities=capabilities or AgentCapabilities(),
            )
            self._agents[agent_id] = agent
            logger.info(f"Agent registered: {agent_id} ({name})")

        return agent

    def unregister(self, agent_id: str) -> bool:
        """Unregister an agent."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            logger.info(f"Agent unregistered: {agent_id}")
            return True
        return False

    def heartbeat(self, agent_id: str) -> bool:
        """Update agent heartbeat timestamp."""
        if agent_id in self._agents:
            self._agents[agent_id].last_heartbeat = datetime.utcnow()
            self._agents[agent_id].status = AgentStatus.ONLINE
            return True
        return False

    def get(self, agent_id: str) -> Optional[Agent]:
        """Get an agent by ID."""
        return self._agents.get(agent_id)

    def get_all(self) -> list[Agent]:
        """Get all registered agents."""
        return list(self._agents.values())

    def get_available_rippers(self) -> list[Agent]:
        """Get agents that can rip and are available."""
        return [
            a for a in self._agents.values()
            if a.is_available() and a.capabilities.can_rip
        ]

    def get_available_transcoders(self) -> list[Agent]:
        """Get agents that can transcode and are available."""
        return [
            a for a in self._agents.values()
            if a.is_available() and a.capabilities.can_transcode
        ]

    def assign_job(self, agent_id: str, job_id: str) -> bool:
        """Assign a job to an agent."""
        agent = self._agents.get(agent_id)
        if agent and agent.is_available():
            agent.current_job_id = job_id
            agent.status = AgentStatus.BUSY
            return True
        return False

    def complete_job(self, agent_id: str) -> bool:
        """Mark an agent's job as complete."""
        agent = self._agents.get(agent_id)
        if agent:
            agent.current_job_id = None
            agent.status = AgentStatus.ONLINE
            return True
        return False

    async def _cleanup_loop(self) -> None:
        """Periodically check for stale agents."""
        while True:
            try:
                await asyncio.sleep(30)
                self._mark_stale_agents()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Agent cleanup error: {e}")

    def _mark_stale_agents(self) -> None:
        """Mark agents as offline if heartbeat is stale."""
        timeout = timedelta(seconds=settings.agent_timeout_seconds)
        now = datetime.utcnow()

        for agent in self._agents.values():
            if agent.status != AgentStatus.OFFLINE:
                if now - agent.last_heartbeat > timeout:
                    agent.status = AgentStatus.OFFLINE
                    logger.warning(f"Agent marked offline: {agent.agent_id}")
