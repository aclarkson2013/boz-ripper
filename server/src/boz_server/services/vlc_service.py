"""VLC preview command management service."""

import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models.vlc_command import VLCCommandORM
from ..database.session import SessionLocal

logger = logging.getLogger(__name__)


class VLCService:
    """Manages VLC preview commands for agents."""

    async def _get_session(self) -> AsyncSession:
        """Get a new database session."""
        return SessionLocal()

    async def queue_preview(
        self,
        agent_id: str,
        file_path: str,
        fullscreen: bool = True,
    ) -> dict:
        """Queue a VLC preview command for an agent.

        Args:
            agent_id: Target agent ID
            file_path: Path to the video file to preview
            fullscreen: Whether to open in fullscreen mode

        Returns:
            Command details dict
        """
        command_id = str(uuid4())

        async with await self._get_session() as session:
            command = VLCCommandORM(
                command_id=command_id,
                agent_id=agent_id,
                file_path=file_path,
                fullscreen=fullscreen,
                status="pending",
            )
            session.add(command)
            await session.commit()

            logger.info(
                f"VLC preview queued: {command_id} for agent {agent_id}, file={file_path}"
            )

            return {
                "command_id": command_id,
                "agent_id": agent_id,
                "file_path": file_path,
                "fullscreen": fullscreen,
                "status": "pending",
            }

    async def get_pending_commands(self, agent_id: str) -> list[dict]:
        """Get pending VLC commands for an agent.

        Args:
            agent_id: Agent ID to get commands for

        Returns:
            List of pending command dicts
        """
        async with await self._get_session() as session:
            result = await session.execute(
                select(VLCCommandORM)
                .where(VLCCommandORM.agent_id == agent_id)
                .where(VLCCommandORM.status == "pending")
                .order_by(VLCCommandORM.created_at)
            )
            commands = result.scalars().all()

            # Mark as sent
            for cmd in commands:
                cmd.status = "sent"
                cmd.sent_at = datetime.utcnow()

            await session.commit()

            return [
                {
                    "command_id": cmd.command_id,
                    "file_path": cmd.file_path,
                    "fullscreen": cmd.fullscreen,
                }
                for cmd in commands
            ]

    async def complete_command(
        self,
        command_id: str,
        success: bool = True,
        error: Optional[str] = None,
    ) -> bool:
        """Mark a VLC command as completed.

        Args:
            command_id: Command ID to update
            success: Whether the command succeeded
            error: Error message if failed

        Returns:
            True if command was found and updated
        """
        async with await self._get_session() as session:
            result = await session.execute(
                select(VLCCommandORM).where(VLCCommandORM.command_id == command_id)
            )
            command = result.scalar_one_or_none()

            if not command:
                logger.warning(f"VLC command not found: {command_id}")
                return False

            command.status = "completed" if success else "failed"
            command.error = error
            command.completed_at = datetime.utcnow()

            await session.commit()

            logger.info(
                f"VLC command {command_id}: {'completed' if success else 'failed'}"
            )
            return True

    async def get_command(self, command_id: str) -> Optional[dict]:
        """Get a VLC command by ID.

        Args:
            command_id: Command ID

        Returns:
            Command dict or None
        """
        async with await self._get_session() as session:
            result = await session.execute(
                select(VLCCommandORM).where(VLCCommandORM.command_id == command_id)
            )
            command = result.scalar_one_or_none()

            if not command:
                return None

            return {
                "command_id": command.command_id,
                "agent_id": command.agent_id,
                "file_path": command.file_path,
                "fullscreen": command.fullscreen,
                "status": command.status,
                "error": command.error,
                "created_at": command.created_at.isoformat() if command.created_at else None,
                "sent_at": command.sent_at.isoformat() if command.sent_at else None,
                "completed_at": command.completed_at.isoformat() if command.completed_at else None,
            }
