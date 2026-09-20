from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.services.user_service import UserService

HandlerType = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class UserContextMiddleware(BaseMiddleware):
    """Регистрирует пользователя в БД при любой активности."""

    async def __call__(
        self,
        handler: HandlerType,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session = data.get("session")
        tg_user = data.get("event_from_user")
        if session is not None and tg_user is not None:
            data["user"] = await UserService(session).get_or_create_from_telegram(
                tg_user
            )
        return await handler(event, data)
