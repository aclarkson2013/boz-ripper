"""Agent repository for database operations."""

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models.agent import AgentORM
from ..models.agent import Agent, AgentCapabilities, AgentStatus
from .base import BaseRepository


class AgentRepository(BaseRepository[AgentORM]):
    """Repository for agent database operations."""

    def __init__(self, session: AsyncSession):
        """Initialize agent repository."""
        super().__init__(AgentORM, session)

    async def create_from_pydantic(self, agent: Agent) -> AgentORM:
        """
        Create agent from Pydantic model.

        Args:
            agent: Pydantic Agent model

        Returns:
            ORM agent instance
        """
        agent_orm = AgentORM(
            agent_id=agent.agent_id,
            name=agent.name,
            status=agent.status.value,
            capabilities=json.dumps(agent.capabilities.model_dump()),
            current_job_id=agent.current_job_id,
            last_heartbeat=agent.last_heartbeat,
            registered_at=agent.registered_at,
        )
        return await self.create(agent_orm)

    def to_pydantic(self, agent_orm: AgentORM) -> Agent:
        """
        Convert ORM model to Pydantic model.

        Args:
            agent_orm: ORM agent instance

        Returns:
            Pydantic Agent model
        """
        capabilities_dict = json.loads(agent_orm.capabilities)
        return Agent(
            agent_id=agent_orm.agent_id,
            name=agent_orm.name,
            status=AgentStatus(agent_orm.status),
            capabilities=AgentCapabilities(**capabilities_dict),
            current_job_id=agent_orm.current_job_id,
            last_heartbeat=agent_orm.last_heartbeat,
            registered_at=agent_orm.registered_at,
        )

    async def get_or_create(
        self, agent_id: str, name: str, capabilities: AgentCapabilities
    ) -> Agent:
        """
        Get existing agent or create new one.

        Args:
            agent_id: Agent ID
            name: Agent name
            capabilities: Agent capabilities

        Returns:
            Agent instance
        """
        agent_orm = await self.get(agent_id)

        if agent_orm:
            # Update existing agent
            agent_orm.name = name
            agent_orm.status = AgentStatus.ONLINE.value
            agent_orm.last_heartbeat = datetime.utcnow()
            agent_orm.capabilities = json.dumps(capabilities.model_dump())
            await self.session.flush()
            await self.session.refresh(agent_orm)
        else:
            # Create new agent
            agent = Agent(
                agent_id=agent_id,
                name=name,
                capabilities=capabilities,
                status=AgentStatus.ONLINE,
            )
            agent_orm = await self.create_from_pydantic(agent)

        return self.to_pydantic(agent_orm)

    async def update_heartbeat(self, agent_id: str) -> Optional[Agent]:
        """
        Update agent heartbeat timestamp.

        Args:
            agent_id: Agent ID

        Returns:
            Updated agent or None if not found
        """
        agent_orm = await self.get(agent_id)
        if not agent_orm:
            return None

        agent_orm.last_heartbeat = datetime.utcnow()
        agent_orm.status = AgentStatus.ONLINE.value

        await self.session.flush()
        await self.session.refresh(agent_orm)
        return self.to_pydantic(agent_orm)

    async def update_status(
        self, agent_id: str, status: AgentStatus
    ) -> Optional[Agent]:
        """
        Update agent status.

        Args:
            agent_id: Agent ID
            status: New status

        Returns:
            Updated agent or None if not found
        """
        agent_orm = await self.get(agent_id)
        if not agent_orm:
            return None

        agent_orm.status = status.value
        await self.session.flush()
        await self.session.refresh(agent_orm)
        return self.to_pydantic(agent_orm)

    async def assign_job(self, agent_id: str, job_id: str) -> Optional[Agent]:
        """
        Assign a job to an agent.

        Args:
            agent_id: Agent ID
            job_id: Job ID

        Returns:
            Updated agent or None if not found
        """
        agent_orm = await self.get(agent_id)
        if not agent_orm:
            return None

        agent_orm.current_job_id = job_id
        agent_orm.status = AgentStatus.BUSY.value

        await self.session.flush()
        await self.session.refresh(agent_orm)
        return self.to_pydantic(agent_orm)

    async def complete_job(self, agent_id: str) -> Optional[Agent]:
        """
        Mark agent's job as complete.

        Args:
            agent_id: Agent ID

        Returns:
            Updated agent or None if not found
        """
        agent_orm = await self.get(agent_id)
        if not agent_orm:
            return None

        agent_orm.current_job_id = None
        agent_orm.status = AgentStatus.ONLINE.value

        await self.session.flush()
        await self.session.refresh(agent_orm)
        return self.to_pydantic(agent_orm)

    async def get_available_rippers(self) -> list[Agent]:
        """
        Get agents that can rip and are available.

        Returns:
            List of available ripping agents
        """
        result = await self.session.execute(
            select(AgentORM).where(
                AgentORM.status == AgentStatus.ONLINE.value,
                AgentORM.current_job_id.is_(None),
            )
        )
        agents = [self.to_pydantic(agent) for agent in result.scalars().all()]
        return [agent for agent in agents if agent.capabilities.can_rip]

    async def mark_stale_agents_offline(self, timeout_seconds: int) -> int:
        """
        Mark agents as offline if heartbeat is stale.

        Args:
            timeout_seconds: Timeout in seconds

        Returns:
            Number of agents marked offline
        """
        cutoff = datetime.utcnow().timestamp() - timeout_seconds
        result = await self.session.execute(
            select(AgentORM).where(
                AgentORM.status != AgentStatus.OFFLINE.value,
            )
        )

        count = 0
        for agent_orm in result.scalars().all():
            if agent_orm.last_heartbeat.timestamp() < cutoff:
                agent_orm.status = AgentStatus.OFFLINE.value
                count += 1

        if count > 0:
            await self.session.flush()

        return count
