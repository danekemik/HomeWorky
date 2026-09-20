from aiogram import Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command
from aiogram.types import ChatMemberUpdated, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.chat_type import ChatTypeFilter
from app.database.models import User
from app.database.repositories import GroupRepository
from app.services.group_service import GroupService

router = Router(name="group_events")

_GROUP_CHAT_TYPES = frozenset({ChatType.GROUP, ChatType.SUPERGROUP})


@router.my_chat_member()
async def on_bot_status_change(
    event: ChatMemberUpdated,
    session: AsyncSession,
) -> None:
    chat = event.chat
    if chat.type not in _GROUP_CHAT_TYPES:
        return
    status = event.new_chat_member.status
    if status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
        group = await GroupRepository(session).get_by_telegram_chat_id(chat.id)
        if group is not None:
            await GroupRepository(session).unbind_chat(group)
            await session.commit()


@router.message(
    Command("link"), ChatTypeFilter(ChatType.GROUP, ChatType.SUPERGROUP)
)
async def on_link_chat(
    message: Message,
    session: AsyncSession,
    user: User,
) -> None:
    raw = (message.text or "").strip()
    parts = raw.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Формат: /link КОД\nВведи инвайт-код своей группы из настроек бота."
        )
        return
    service = GroupService(session)
    group = await service.find_by_invite_code(parts[1])
    if group is None:
        await message.answer("Группа с таким кодом не найдена.")
        return
    if not service.invite_valid(group):
        await message.answer(
            "Код устарел. Обнови его в настройках бота (личный чат → Управление группой)."
        )
        return
    if not await service.is_admin(group, user):
        await message.answer(
            "Привязать чат может только староста этой группы — администратор в боте."
        )
        return
    error = await service.bind_chat(group, message.chat)
    if error is not None:
        await message.answer(error)
        return
    await session.commit()
    await message.answer(
        f"✅ Чат привязан к группе «{group.name}». Напоминания будут приходить сюда."
    )
