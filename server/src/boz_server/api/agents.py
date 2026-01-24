"""Agent management API endpoints."""

from fastapi import APIRouter, HTTPException

from boz_server.api.deps import AgentManagerDep, ApiKeyDep, JobQueueDep
from boz_server.models.agent import Agent, AgentRegistration

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.post("/register", response_model=Agent)
async def register_agent(
    request: AgentRegistration,
    agent_manager: AgentManagerDep,
    _: ApiKeyDep,
) -> Agent:
    """Register a new agent or reconnect an existing one."""
    agent = await agent_manager.register(
        agent_id=request.agent_id,
        name=request.name,
        capabilities=request.capabilities,
    )
    return agent


@router.post("/{agent_id}/unregister")
async def unregister_agent(
    agent_id: str,
    agent_manager: AgentManagerDep,
    _: ApiKeyDep,
) -> dict:
    """Unregister an agent."""
    if await agent_manager.unregister(agent_id):
        return {"status": "ok", "message": "Agent unregistered"}
    raise HTTPException(status_code=404, detail="Agent not found")


@router.post("/{agent_id}/heartbeat")
async def agent_heartbeat(
    agent_id: str,
    agent_manager: AgentManagerDep,
    _: ApiKeyDep,
) -> dict:
    """Update agent heartbeat."""
    if await agent_manager.heartbeat(agent_id):
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail="Agent not found")


@router.get("", response_model=list[Agent])
async def list_agents(
    agent_manager: AgentManagerDep,
) -> list[Agent]:
    """List all registered agents."""
    return await agent_manager.get_all()


@router.get("/{agent_id}", response_model=Agent)
async def get_agent(
    agent_id: str,
    agent_manager: AgentManagerDep,
) -> Agent:
    """Get a specific agent."""
    agent = await agent_manager.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.get("/{agent_id}/jobs")
async def get_agent_jobs(
    agent_id: str,
    agent_manager: AgentManagerDep,
    job_queue: JobQueueDep,
    _: ApiKeyDep,
) -> dict:
    """Get jobs assigned to an agent."""
    agent = await agent_manager.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    jobs = await job_queue.get_jobs_for_agent(agent_id)
    return {"jobs": [j.model_dump() for j in jobs]}
