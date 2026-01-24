"""Disc repository for database operations."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database.models.disc import DiscORM, TitleORM
from ..models.disc import Disc, DiscType, MediaType, PreviewStatus, Title
from .base import BaseRepository


class DiscRepository(BaseRepository[DiscORM]):
    """Repository for disc database operations."""

    def __init__(self, session: AsyncSession):
        """Initialize disc repository."""
        super().__init__(DiscORM, session)

    async def create_from_pydantic(self, disc: Disc) -> DiscORM:
        """
        Create disc from Pydantic model.

        Args:
            disc: Pydantic Disc model

        Returns:
            ORM disc instance
        """
        disc_orm = DiscORM(
            disc_id=disc.disc_id,
            agent_id=disc.agent_id,
            drive=disc.drive,
            disc_name=disc.disc_name,
            disc_type=disc.disc_type.value,
            detected_at=disc.detected_at,
            status=disc.status,
            media_type=disc.media_type.value,
            preview_status=disc.preview_status.value,
            tv_show_name=disc.tv_show_name,
            tv_season_number=disc.tv_season_number,
            tv_season_id=disc.tv_season_id,
            thetvdb_series_id=disc.thetvdb_series_id,
            starting_episode_number=disc.starting_episode_number,
        )

        # Create title ORMs
        for title in disc.titles:
            title_orm = TitleORM(
                disc_id=disc.disc_id,
                title_index=title.index,
                name=title.name,
                duration_seconds=title.duration_seconds,
                size_bytes=title.size_bytes,
                chapters=title.chapters,
                selected=title.selected,
                is_extra=title.is_extra,
                proposed_filename=title.proposed_filename,
                proposed_path=title.proposed_path,
                episode_number=title.episode_number,
                episode_title=title.episode_title,
                confidence_score=title.confidence_score,
            )
            disc_orm.titles.append(title_orm)

        return await self.create(disc_orm)

    async def get_with_titles(self, disc_id: str) -> Optional[DiscORM]:
        """
        Get disc with titles eagerly loaded.

        Args:
            disc_id: Disc ID

        Returns:
            Disc ORM with titles or None
        """
        result = await self.session.execute(
            select(DiscORM)
            .where(DiscORM.disc_id == disc_id)
            .options(selectinload(DiscORM.titles))
        )
        return result.scalar_one_or_none()

    def to_pydantic(self, disc_orm: DiscORM) -> Disc:
        """
        Convert ORM model to Pydantic model.

        Args:
            disc_orm: ORM disc instance

        Returns:
            Pydantic Disc model
        """
        titles = [
            Title(
                index=title.title_index,
                name=title.name,
                duration_seconds=title.duration_seconds,
                size_bytes=title.size_bytes,
                chapters=title.chapters,
                selected=title.selected,
                is_extra=title.is_extra,
                proposed_filename=title.proposed_filename,
                proposed_path=title.proposed_path,
                episode_number=title.episode_number,
                episode_title=title.episode_title,
                confidence_score=title.confidence_score,
            )
            for title in disc_orm.titles
        ]

        return Disc(
            disc_id=disc_orm.disc_id,
            agent_id=disc_orm.agent_id,
            drive=disc_orm.drive,
            disc_name=disc_orm.disc_name,
            disc_type=DiscType(disc_orm.disc_type),
            titles=titles,
            detected_at=disc_orm.detected_at,
            status=disc_orm.status,
            media_type=MediaType(disc_orm.media_type),
            preview_status=PreviewStatus(disc_orm.preview_status),
            tv_show_name=disc_orm.tv_show_name,
            tv_season_number=disc_orm.tv_season_number,
            tv_season_id=disc_orm.tv_season_id,
            thetvdb_series_id=disc_orm.thetvdb_series_id,
            starting_episode_number=disc_orm.starting_episode_number,
        )

    async def get_by_agent_drive(
        self, agent_id: str, drive: str
    ) -> Optional[Disc]:
        """
        Get disc by agent and drive.

        Args:
            agent_id: Agent ID
            drive: Drive letter/path

        Returns:
            Disc or None
        """
        result = await self.session.execute(
            select(DiscORM)
            .where(DiscORM.agent_id == agent_id)
            .where(DiscORM.drive == drive)
            .where(DiscORM.status != "ejected")
            .options(selectinload(DiscORM.titles))
        )
        disc_orm = result.scalar_one_or_none()
        return self.to_pydantic(disc_orm) if disc_orm else None

    async def update_status(self, disc_id: str, status: str) -> Optional[Disc]:
        """
        Update disc status.

        Args:
            disc_id: Disc ID
            status: New status

        Returns:
            Updated disc or None if not found
        """
        disc_orm = await self.get_with_titles(disc_id)
        if not disc_orm:
            return None

        disc_orm.status = status
        await self.session.flush()
        await self.session.refresh(disc_orm)
        return self.to_pydantic(disc_orm)

    async def update_preview_status(
        self, disc_id: str, preview_status: PreviewStatus
    ) -> Optional[Disc]:
        """
        Update disc preview status.

        Args:
            disc_id: Disc ID
            preview_status: New preview status

        Returns:
            Updated disc or None if not found
        """
        disc_orm = await self.get_with_titles(disc_id)
        if not disc_orm:
            return None

        disc_orm.preview_status = preview_status.value
        await self.session.flush()
        await self.session.refresh(disc_orm)
        return self.to_pydantic(disc_orm)

    async def update_titles(self, disc_id: str, titles: list[Title]) -> Optional[Disc]:
        """
        Update disc titles.

        Args:
            disc_id: Disc ID
            titles: Updated list of titles

        Returns:
            Updated disc or None if not found
        """
        disc_orm = await self.get_with_titles(disc_id)
        if not disc_orm:
            return None

        # Update existing titles by index
        for title in titles:
            for title_orm in disc_orm.titles:
                if title_orm.title_index == title.index:
                    title_orm.name = title.name
                    title_orm.selected = title.selected
                    title_orm.is_extra = title.is_extra
                    title_orm.proposed_filename = title.proposed_filename
                    title_orm.proposed_path = title.proposed_path
                    title_orm.episode_number = title.episode_number
                    title_orm.episode_title = title.episode_title
                    title_orm.confidence_score = title.confidence_score
                    break

        await self.session.flush()
        await self.session.refresh(disc_orm)
        return self.to_pydantic(disc_orm)

    async def get_all_with_titles(self) -> list[Disc]:
        """
        Get all discs with titles.

        Returns:
            List of all discs
        """
        result = await self.session.execute(
            select(DiscORM).options(selectinload(DiscORM.titles))
        )
        return [self.to_pydantic(disc) for disc in result.scalars().all()]

    async def get_pending_previews(self) -> list[Disc]:
        """
        Get discs with pending preview status.

        Returns:
            List of discs awaiting preview approval
        """
        result = await self.session.execute(
            select(DiscORM)
            .where(DiscORM.preview_status == PreviewStatus.PENDING.value)
            .options(selectinload(DiscORM.titles))
        )
        return [self.to_pydantic(disc) for disc in result.scalars().all()]
