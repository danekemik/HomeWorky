from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.types import Chat
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Group, User
from app.database.repositories.group_repository import GroupRepository
from app.services.group_service import GroupService

_GROUP_CHAT_TYPES = frozenset({ChatType.GROUP, ChatType.SUPERGROUP})


async def resolve_group(
    bot: Bot,
    session: AsyncSession,
    user: User,
    chat: Chat | None,
    state: FSMContext,
) -> Group | None:
    """Определяет группу-контекст: в групповом чате — сам чат,
    в личке — выбранную ранее группу. Всегда с проверкой членства."""
    if chat is not None and chat.type in _GROUP_CHAT_TYPES:
        group = await GroupService(session).register_group(chat)
        if not await GroupService(session).is_member(
            bot, group, user.telegram_id
        ):
            return None
        await GroupService(session).register_membership(group, user)
        return group

    data = await state.get_data()
    group_id = data.get("current_group_id")
    if group_id is None:
        return None
    stored_group = await GroupRepository(session).get(group_id)
    if stored_group is None:
        return None
    if not await GroupService(session).verify_access(
        bot, stored_group, user.telegram_id
    ):
        return None
    return stored_group
