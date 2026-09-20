from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.types import Chat
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Group, User
from app.database.repositories.group_repository import GroupRepository
from app.services.group_service import GroupService

_GROUP_CHAT_TYPES = frozenset({ChatType.GROUP, ChatType.SUPERGROUP})


def select_current_group(user: User, group_id: int) -> None:
    """Запоминает выбранную группу в БД, чтобы выбор переживал рестарты бота."""
    user.selected_group_id = group_id


async def resolve_group(
    bot: Bot,
    session: AsyncSession,
    user: User,
    chat: Chat | None,
    state: FSMContext,
) -> Group | None:
    """Определяет выбранную в меню группу для работы в личном чате.

    Групповые чаты не служат контекстом: членство подтверждается
    инвайт-кодом, а не присутствием в Telegram-группе."""
    if chat is not None and chat.type in _GROUP_CHAT_TYPES:
        return None

    data = await state.get_data()
    group_id = data.get("current_group_id") or user.selected_group_id
    if group_id is None:
        return None
    stored_group = await GroupRepository(session).get(group_id)
    if stored_group is None:
        return None
    if not await GroupService(session).has_access(stored_group, user):
        return None
    return stored_group
