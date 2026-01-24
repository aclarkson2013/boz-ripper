"""Database-backed agent registration and management service."""

import asyncio
import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..database.session import SessionLocal
from ..models.agent import Agent, AgentCapabilities, AgentStatus
from ..repositories.agent_repository import AgentRepository

logger = logging.getLogger(__name__)


class AgentManager:
    """Manages connected agents with database persistence."""

    def __init__(self):
        """Initialize agent manager."""
        self._cleanup_task: Optional[asyncio.Task] = None

    async def _get_session(self) -> AsyncSession:
        """Get a new database session."""
        return SessionLocal()

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

    async def register(
        self,
        agent_id: str,
        name: str,
        capabilities: Optional[AgentCapabilities] = None,
    ) -> Agent:
        """Register a new agent or update existing."""
        async with await self._get_session() as session:
            repo = AgentRepository(session)
            agent = await repo.get_or_create(
                agent_id, name, capabilities or AgentCapabilities()
            )
            await session.commit()

            status = "reconnected" if agent.registered_at != agent.last_heartbeat else "registered"
            logger.info(f"Agent {status}: {agent_id} ({name})")
            return agent

    async def unregister(self, agent_id: str) -> bool:
        """Unregister an agent."""
        async with await self._get_session() as session:
            repo = AgentRepository(session)
            success = await repo.delete_by_id(agent_id)
            if success:
                await session.commit()
                logger.info(f"Agent unregistered: {agent_id}")
            return success

    async def heartbeat(self, agent_id: str) -> bool:
        """Update agent heartbeat timestamp."""
        async with await self._get_session() as session:
            repo = AgentRepository(session)
            agent = await repo.update_heartbeat(agent_id)
            if agent:
                await session.commit()
                return True
            return False

    async def get(self, agent_id: str) -> Optional[Agent]:
        """Get an agent by ID."""
        async with await self._get_session() as session:
            repo = AgentRepository(session)
            agent_orm = await repo.get(agent_id)
            return repo.to_pydantic(agent_orm) if agent_orm else None

    async def get_all(self) -> list[Agent]:
        """Get all registered agents."""
        async with await self._get_session() as session:
            repo = AgentRepository(session)
            agent_orms = await repo.get_all()
            return [repo.to_pydantic(agent) for agent in agent_orms]

    async def get_available_rippers(self) -> list[Agent]:
        """Get agents that can rip and are available."""
        async with await self._get_session() as session:
            repo = AgentRepository(session)
            return await repo.get_available_rippers()

    async def get_available_transcoders(self) -> list[Agent]:
        """Get agents that can transcode and are available."""
        agents = await self.get_all()
        return [
            a
            for a in agents
            if a.is_available() and a.capabilities.can_transcode
        ]

    async def assign_job(self, agent_id: str, job_id: str) -> bool:
        """Assign a job to an agent."""
        async with await self._get_session() as session:
            repo = AgentRepository(session)
            agent = await repo.assign_job(agent_id, job_id)
            if agent:
                await session.commit()
                return True
            return False

    async def complete_job(self, agent_id: str) -> bool:
        """Mark an agent's job as complete."""
        async with await self._get_session() as session:
            repo = AgentRepository(session)
            agent = await repo.complete_job(agent_id)
            if agent:
                await session.commit()
                return True
            return False

    async def _cleanup_loop(self) -> None:
        """Periodically check for stale agents."""
        while True:
            try:
                await asyncio.sleep(30)
                await self._mark_stale_agents()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Agent cleanup error: {e}")

    async def _mark_stale_agents(self) -> None:
        """Mark agents as offline if heartbeat is stale."""
        async with await self._get_session() as session:
            repo = AgentRepository(session)
            count = await repo.mark_stale_agents_offline(settings.agent_timeout_seconds)
            if count > 0:
                await session.commit()
                logger.warning(f"Marked {count} agents offline due to stale heartbeat")
