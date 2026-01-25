"""Database session management."""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .base import Base
from .config import get_database_echo, get_database_url

logger = logging.getLogger(__name__)

# Create async engine
engine = create_async_engine(
    get_database_url(),
    echo=get_database_echo(),
    future=True,
)

# Create session factory
SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting database sessions.

    Yields:
        AsyncSession instance
    """
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database tables.

    Creates all tables defined in ORM models.
    """
    async with engine.begin() as conn:
        # Import all models to register them with Base
        from .models import (  # noqa: F401
            AgentORM,
            DiscORM,
            JobORM,
            TitleORM,
            TVEpisodeORM,
            TVSeasonORM,
            VLCCommandORM,
            WorkerORM,
        )

        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database initialized successfully")
