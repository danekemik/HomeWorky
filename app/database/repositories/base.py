from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.base import Base

ModelT = TypeVar("ModelT", bound="Base")


class BaseRepository[ModelT: Base]:
    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self._session = session
        self._model = model

    async def add(self, instance: ModelT) -> ModelT:
        self._session.add(instance)
        await self._session.flush()
        return instance

    async def get(self, id_: int) -> ModelT | None:
        return await self._session.get(self._model, id_)

    async def delete(self, instance: ModelT) -> None:
        await self._session.delete(instance)
        await self._session.flush()
