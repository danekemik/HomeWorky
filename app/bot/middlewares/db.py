from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.database.session import Database

HandlerType = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class DatabaseSessionMiddleware(BaseMiddleware):
    """Создаёт сессию БД на каждый апдейт и коммитит её после обработки."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def __call__(
        self,
        handler: HandlerType,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if "session" in data:
            return await handler(event, data)
        async with self._database.session_factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
