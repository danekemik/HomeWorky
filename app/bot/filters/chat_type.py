from aiogram.enums import ChatType
from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject


class ChatTypeFilter(BaseFilter):
    """Пропускает события только из чатов указанных типов."""

    def __init__(self, *chat_types: ChatType) -> None:
        self.chat_types = frozenset(chat_types)

    async def __call__(self, event: TelegramObject) -> bool:
        chat = getattr(event, "chat", None)
        if chat is None:
            return False
        return chat.type in self.chat_types
