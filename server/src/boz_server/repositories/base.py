"""Base repository with common database operations."""

from typing import Generic, Optional, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.base import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """Base repository with common CRUD operations."""

    def __init__(self, model: Type[T], session: AsyncSession):
        """
        Initialize repository.

        Args:
            model: SQLAlchemy ORM model class
            session: Database session
        """
        self.model = model
        self.session = session

    async def get(self, id: str) -> Optional[T]:
        """
        Get a single record by ID.

        Args:
            id: Primary key value

        Returns:
            Model instance or None
        """
        return await self.session.get(self.model, id)

    async def get_all(self) -> list[T]:
        """
        Get all records.

        Returns:
            List of model instances
        """
        result = await self.session.execute(select(self.model))
        return list(result.scalars().all())

    async def create(self, instance: T) -> T:
        """
        Create a new record.

        Args:
            instance: Model instance to create

        Returns:
            Created instance
        """
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, instance: T) -> T:
        """
        Update an existing record.

        Args:
            instance: Model instance to update

        Returns:
            Updated instance
        """
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: T) -> None:
        """
        Delete a record.

        Args:
            instance: Model instance to delete
        """
        await self.session.delete(instance)
        await self.session.flush()

    async def delete_by_id(self, id: str) -> bool:
        """
        Delete a record by ID.

        Args:
            id: Primary key value

        Returns:
            True if deleted, False if not found
        """
        instance = await self.get(id)
        if instance:
            await self.delete(instance)
            return True
        return False
