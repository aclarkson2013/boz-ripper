"""Disc detection API endpoints."""

import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from boz_server.api.deps import AgentManagerDep, ApiKeyDep, JobQueueDep, PreviewGeneratorDep
from boz_server.models.disc import Disc, DiscDetected, DiscEjected, DiscType, PreviewStatus, Title
from boz_server.models.tv_show import TVSeason

logger = logging.getLogger(__name__)


class RipRequest(BaseModel):
    """Request body for starting a rip."""
    title_indices: list[int] | None = None

class SeasonEpisodeUpdate(BaseModel):
    """Request to update season and starting episode."""
    season_number: int
    starting_episode: int = 1


router = APIRouter(prefix="/api/discs", tags=["discs"])


@router.post("/detected", response_model=Disc)
async def disc_detected(
    request: DiscDetected,
    agent_manager: AgentManagerDep,
    job_queue: JobQueueDep,
    preview_generator: PreviewGeneratorDep,
    _: ApiKeyDep,
) -> Disc:
    """Report a detected disc from an agent."""
    logger.info(f"========================================")
    logger.info(f"DISC DETECTED ENDPOINT")
    logger.info(f"Disc Name: {request.disc_name}")
    logger.info(f"Disc Type: {request.disc_type}")
    logger.info(f"Agent: {request.agent_id}")
    logger.info(f"Drive: {request.drive}")
    logger.info(f"Titles: {len(request.titles)}")
    logger.info(f"========================================")

    # Verify agent exists
    agent = await agent_manager.get(request.agent_id)
    if not agent:
        logger.error(f"Agent not found: {request.agent_id}")
        raise HTTPException(status_code=404, detail="Agent not found")

    # Check if we already have this disc
    existing = await job_queue.get_disc_by_agent_drive(request.agent_id, request.drive)
    if existing:
        # Update existing disc
        logger.info(f"Updating existing disc: {existing.disc_id}")
        existing.disc_name = request.disc_name
        existing.titles = request.titles
        existing.status = "detected"
        # Regenerate preview with updated data
        logger.info(f"Triggering preview regeneration for existing disc: {existing.disc_id}")
        existing = await preview_generator.generate_preview(existing)
        # Save updated disc to database
        existing = await job_queue.update_disc(existing)
        logger.info(f"Preview regeneration complete, returning disc")
        return existing

    # Parse disc type
    disc_type = DiscType.UNKNOWN
    if "DVD" in request.disc_type.upper():
        disc_type = DiscType.DVD
    elif "BLU" in request.disc_type.upper():
        disc_type = DiscType.BLURAY

    logger.info(f"Creating new disc record with type: {disc_type}")

    # Create new disc record
    disc = Disc(
        disc_id=str(uuid4()),
        agent_id=request.agent_id,
        drive=request.drive,
        disc_name=request.disc_name,
        disc_type=disc_type,
        titles=request.titles,
    )

    # Generate preview automatically
    logger.info(f"Triggering preview generation for new disc: {disc.disc_id}")
    disc = await preview_generator.generate_preview(disc)
    logger.info(f"Preview generation complete, adding to queue")

    await job_queue.add_disc(disc)
    logger.info(f"Disc added to queue, returning response")
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
    disc = await job_queue.get_disc_by_agent_drive(request.agent_id, request.drive)
    if disc:
        await job_queue.remove_disc(disc.disc_id)
        return {"status": "ok", "disc_id": disc.disc_id}

    return {"status": "ok", "message": "No disc found for that drive"}


@router.get("", response_model=list[Disc])
async def list_discs(
    job_queue: JobQueueDep,
) -> list[Disc]:
    """List all tracked discs."""
    return await job_queue.get_all_discs()


@router.get("/{disc_id}", response_model=Disc)
async def get_disc(
    disc_id: str,
    job_queue: JobQueueDep,
) -> Disc:
    """Get a specific disc."""
    disc = await job_queue.get_disc(disc_id)
    if not disc:
        raise HTTPException(status_code=404, detail="Disc not found")
    return disc


class PreviewApprovalRequest(BaseModel):
    """Request body for approving a preview with potential edits."""

    title_edits: list[Title] | None = None  # Optional edited titles


@router.post("/{disc_id}/preview/approve")
async def approve_preview(
    disc_id: str,
    job_queue: JobQueueDep,
    request: PreviewApprovalRequest | None = None,
    _: ApiKeyDep = None,
) -> Disc:
    """Approve disc preview and optionally apply user edits."""
    disc = await job_queue.get_disc(disc_id)
    if not disc:
        raise HTTPException(status_code=404, detail="Disc not found")

    # Apply user edits if provided
    if request and request.title_edits:
        logger.info(f"Applying user edits to disc {disc_id}")
        # Update titles with edits (match by index)
        edit_map = {t.index: t for t in request.title_edits}
        for title in disc.titles:
            if title.index in edit_map:
                edited = edit_map[title.index]
                # Update editable fields
                title.proposed_filename = edited.proposed_filename
                title.proposed_path = edited.proposed_path
                title.episode_number = edited.episode_number
                title.episode_title = edited.episode_title
                title.is_extra = edited.is_extra
                title.selected = edited.selected

    # Mark as approved
    disc.preview_status = PreviewStatus.APPROVED
    logger.info(f"Approved preview for disc {disc_id}")

    # Save to database
    disc = await job_queue.update_disc(disc)

    return disc


@router.post("/{disc_id}/preview/reject")
async def reject_preview(
    disc_id: str,
    job_queue: JobQueueDep,
    _: ApiKeyDep = None,
) -> Disc:
    """Reject disc preview and block ripping."""
    disc = await job_queue.get_disc(disc_id)
    if not disc:
        raise HTTPException(status_code=404, detail="Disc not found")

    # Mark as rejected
    disc.preview_status = PreviewStatus.REJECTED
    logger.info(f"Rejected preview for disc {disc_id}")

    # Save to database
    disc = await job_queue.update_disc(disc)

    return disc



@router.post("/{disc_id}/preview/update-season")
async def update_season_and_episode(
    disc_id: str,
    request: SeasonEpisodeUpdate,
    job_queue: JobQueueDep,
    preview_generator: PreviewGeneratorDep,
    _: ApiKeyDep = None,
) -> Disc:
    """Update season and starting episode, then regenerate preview."""
    disc = await job_queue.get_disc(disc_id)
    if not disc:
        raise HTTPException(status_code=404, detail="Disc not found")

    logger.info(f"Updating disc {disc_id} to Season {request.season_number}, Episode {request.starting_episode}")

    # Update season and starting episode
    old_season = disc.tv_season_number
    old_episode = disc.starting_episode_number
    disc.tv_season_number = request.season_number
    disc.starting_episode_number = request.starting_episode

    # Get or create the new season tracker
    if disc.tv_show_name:
        tv_season = await preview_generator.get_or_create_season(
            disc.tv_show_name,
            request.season_number
        )
        disc.tv_season_id = tv_season.season_id

        # Re-fetch TheTVDB episodes for this season if needed
        if preview_generator.thetvdb_client and not tv_season.episodes:
            logger.info(f"Fetching TheTVDB episodes for season {request.season_number}")
            if disc.thetvdb_series_id:
                episodes = await preview_generator.thetvdb_client.get_season_episodes(
                    disc.thetvdb_series_id,
                    request.season_number
                )
                if episodes:
                    tv_season.episodes = episodes
                    await preview_generator.update_season_episodes(
                        tv_season.season_id, episodes, disc.thetvdb_series_id
                    )
                    logger.info(f"Loaded {len(episodes)} episodes from TheTVDB")

        # Re-match episodes with the new starting episode
        logger.info("Re-matching episodes with new season/episode settings")
        main_titles = preview_generator.extras_filter.get_main_titles(disc.titles)
        if main_titles:
            preview_generator.episode_matcher.match_episodes(
                main_titles,
                tv_season,
                starting_episode=request.starting_episode
            )

            # Re-generate filenames with new episode numbers
            for title in disc.titles:
                preview_generator.media_namer.apply_naming(
                    title,
                    disc.media_type,
                    show_name=disc.tv_show_name,
                    season_number=request.season_number,
                )

            logger.info(f"✓ Season/episode update complete: S{old_season:02d}E{old_episode or 1:02d} → S{request.season_number:02d}E{request.starting_episode:02d}")
        else:
            logger.warning("No main titles found for episode re-matching")
    else:
        logger.warning("Disc is not a TV show, cannot update season/episode")
        raise HTTPException(status_code=400, detail="Disc is not a TV show")

    # Save the updated disc to the database
    disc = await job_queue.update_disc(disc)

    return disc
@router.get("/tv-seasons/{season_id}", response_model=TVSeason)
async def get_tv_season(
    season_id: str,
    preview_generator: PreviewGeneratorDep,
) -> TVSeason:
    """Get TV season tracking information."""
    season = await preview_generator.get_season(season_id)
    if not season:
        raise HTTPException(status_code=404, detail="TV season not found")
    return season


@router.post("/{disc_id}/rip")
async def start_rip(
    disc_id: str,
    job_queue: JobQueueDep,
    request: RipRequest | None = None,
    _: ApiKeyDep = None,
) -> dict:
    """Start ripping selected titles from a disc."""
    disc = await job_queue.get_disc(disc_id)
    if not disc:
        raise HTTPException(status_code=404, detail="Disc not found")

    # Check preview approval status
    if disc.preview_status != PreviewStatus.APPROVED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot rip disc with preview status: {disc.preview_status}. Preview must be approved first.",
        )

    # Get title indices from request body
    title_indices = request.title_indices if request else None

    # Determine which titles to rip
    if title_indices:
        titles_to_rip = [t for t in disc.titles if t.index in title_indices]
    else:
        # Use selected titles or default to main feature
        selected = [t for t in disc.titles if t.selected]
        if selected:
            titles_to_rip = selected
        else:
            # Default to main feature if nothing selected
            main = disc.main_feature
            titles_to_rip = [main] if main else []

    if not titles_to_rip:
        raise HTTPException(status_code=400, detail="No titles selected for ripping")

    # Create rip jobs and assign to the agent with the disc
    jobs = []
    for title in titles_to_rip:
        # Use proposed filename if available, otherwise fallback to disc_name + index
        if title.proposed_filename:
            # Remove .mkv extension for output_name
            output_name = title.proposed_filename.replace(".mkv", "")
        else:
            output_name = f"{disc.disc_name}_t{title.index:02d}"

        job = await job_queue.create_rip_job(disc, title, output_name)
        # Auto-assign to the agent that reported this disc
        await job_queue.assign_job(job.job_id, disc.agent_id)
        jobs.append(job)

    disc.status = "ripping"

    return {
        "status": "ok",
        "jobs_created": len(jobs),
        "job_ids": [j.job_id for j in jobs],
    }
