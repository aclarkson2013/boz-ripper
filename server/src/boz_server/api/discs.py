"""Disc detection API endpoints."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from boz_server.api.deps import AgentManagerDep, ApiKeyDep, JobQueueDep
from boz_server.models.disc import Disc, DiscDetected, DiscEjected, DiscType


class RipRequest(BaseModel):
    """Request body for starting a rip."""
    title_indices: list[int] | None = None

router = APIRouter(prefix="/api/discs", tags=["discs"])


@router.post("/detected", response_model=Disc)
async def disc_detected(
    request: DiscDetected,
    agent_manager: AgentManagerDep,
    job_queue: JobQueueDep,
    _: ApiKeyDep,
) -> Disc:
    """Report a detected disc from an agent."""
    # Verify agent exists
    agent = agent_manager.get(request.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Check if we already have this disc
    existing = job_queue.get_disc_by_agent_drive(request.agent_id, request.drive)
    if existing:
        # Update existing disc
        existing.disc_name = request.disc_name
        existing.titles = request.titles
        existing.status = "detected"
        return existing

    # Parse disc type
    disc_type = DiscType.UNKNOWN
    if "DVD" in request.disc_type.upper():
        disc_type = DiscType.DVD
    elif "BLU" in request.disc_type.upper():
        disc_type = DiscType.BLURAY

    # Create new disc record
    disc = Disc(
        disc_id=str(uuid4()),
        agent_id=request.agent_id,
        drive=request.drive,
        disc_name=request.disc_name,
        disc_type=disc_type,
        titles=request.titles,
    )

    job_queue.add_disc(disc)
    return disc


@router.post("/ejected")
async def disc_ejected(
    request: DiscEjected,
    agent_manager: AgentManagerDep,
    job_queue: JobQueueDep,
    _: ApiKeyDep,
) -> dict:
    """Report a disc ejection from an agent."""
    # Find the disc
    disc = job_queue.get_disc_by_agent_drive(request.agent_id, request.drive)
    if disc:
        job_queue.remove_disc(disc.disc_id)
        return {"status": "ok", "disc_id": disc.disc_id}

    return {"status": "ok", "message": "No disc found for that drive"}


@router.get("", response_model=list[Disc])
async def list_discs(
    job_queue: JobQueueDep,
) -> list[Disc]:
    """List all tracked discs."""
    return job_queue.get_all_discs()


@router.get("/{disc_id}", response_model=Disc)
async def get_disc(
    disc_id: str,
    job_queue: JobQueueDep,
) -> Disc:
    """Get a specific disc."""
    disc = job_queue.get_disc(disc_id)
    if not disc:
        raise HTTPException(status_code=404, detail="Disc not found")
    return disc


@router.post("/{disc_id}/rip")
async def start_rip(
    disc_id: str,
    job_queue: JobQueueDep,
    request: RipRequest | None = None,
    _: ApiKeyDep = None,
) -> dict:
    """Start ripping selected titles from a disc."""
    disc = job_queue.get_disc(disc_id)
    if not disc:
        raise HTTPException(status_code=404, detail="Disc not found")

    # Get title indices from request body
    title_indices = request.title_indices if request else None

    # Determine which titles to rip
    if title_indices:
        titles_to_rip = [t for t in disc.titles if t.index in title_indices]
    else:
        # Default to main feature
        main = disc.main_feature
        titles_to_rip = [main] if main else []

    if not titles_to_rip:
        raise HTTPException(status_code=400, detail="No titles selected for ripping")

    # Create rip jobs
    jobs = []
    for title in titles_to_rip:
        output_name = f"{disc.disc_name}_t{title.index:02d}"
        job = job_queue.create_rip_job(disc, title, output_name)
        jobs.append(job)

    disc.status = "ripping"

    return {
        "status": "ok",
        "jobs_created": len(jobs),
        "job_ids": [j.job_id for j in jobs],
    }
