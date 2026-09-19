from collections.abc import Awaitable, Callable
from typing import Any, cast

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Chat, Message, TelegramObject

from app.database.models import Group, User
from app.services.group_service import GroupService
from app.services.user_service import UserService

HandlerType = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]

_GROUP_CHAT_TYPES = frozenset({ChatType.GROUP, ChatType.SUPERGROUP})


class UserContextMiddleware(BaseMiddleware):
    """Регистрирует пользователя и его членство в группе при активности."""

    async def __call__(
        self,
        handler: HandlerType,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session = data.get("session")
        tg_user = data.get("event_from_user")
        user: User | None = None
        if session is not None and tg_user is not None:
            user = await UserService(session).get_or_create_from_telegram(tg_user)
            data["user"] = user
            chat_raw = data.get("event_chat")
            if self._should_register_membership(event, chat_raw):
                chat = cast(Chat, chat_raw)
                group: Group = await GroupService(session).register_group(chat)
                await GroupService(session).register_membership(group, user)
        return await handler(event, data)

    @staticmethod
    def _should_register_membership(event: TelegramObject, chat: Any) -> bool:
        if chat is None or chat.type not in _GROUP_CHAT_TYPES:
            return False
        if isinstance(event, Message):
            if event.new_chat_members or event.left_chat_member:
                return False
            return True
        if isinstance(event, CallbackQuery):
            return True
        return False
