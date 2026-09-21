import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.config import settings

HandlerType = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class ThrottlingMiddleware(BaseMiddleware):
    """Ограничивает частоту обработки апдейтов от одного отправителя."""

    def __init__(self, per_second: float = settings.RATE_LIMIT_MESSAGES_PER_SEC) -> None:
        self._min_interval = 1.0 / per_second
        self._last_processed: dict[str, float] = {}

    async def __call__(
        self,
        handler: HandlerType,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = data.get("event_from_user")
        if from_user is None:
            return await handler(event, data)
        key = str(from_user.id)
        now = time.monotonic()
        last = self._last_processed.get(key, 0.0)
        if now - last < self._min_interval:
            return None
        self._last_processed[key] = now
        return await handler(event, data)
