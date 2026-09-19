from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery


class CallbackDataPrefix(BaseFilter):
    """Пропускает callback-query, чей data начинается с заданного префикса."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix

    async def __call__(self, query: CallbackQuery) -> bool:
        return bool(query.data and query.data.startswith(self.prefix))
