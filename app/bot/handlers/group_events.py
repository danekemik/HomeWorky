from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Filter
from aiogram.types import ChatMemberUpdated, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.group_repository import GroupRepository
from app.database.repositories.user_repository import UserRepository
from app.services.group_service import GroupService
from app.services.user_service import UserService

router = Router(name="group_events")

_GROUP_CHAT_TYPES = frozenset({ChatType.GROUP, ChatType.SUPERGROUP})


class NewChatMembersFilter(Filter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.new_chat_members)


class LeftChatMemberFilter(Filter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.left_chat_member)


@router.my_chat_member()
async def on_bot_status_change(
    event: ChatMemberUpdated,
    bot: Bot,
    session: AsyncSession,
) -> None:
    chat = event.chat
    if chat.type not in _GROUP_CHAT_TYPES:
        return
    status = event.new_chat_member.status
    if status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER}:
        group = await GroupService(session).register_group(chat)
        await GroupService(session).sync_administrators(bot, group)
    elif status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
        registered = await GroupRepository(session).get_by_telegram_chat_id(chat.id)
        if registered is not None:
            await session.delete(registered)
            await session.flush()


@router.message(NewChatMembersFilter())
async def on_new_chat_members(
    message: Message,
    session: AsyncSession,
) -> None:
    chat = message.chat
    if chat.type not in _GROUP_CHAT_TYPES or message.bot is None:
        return
    group = await GroupService(session).register_group(chat)
    for tg_user in message.new_chat_members or []:
        if tg_user.is_bot or tg_user.id == message.bot.id:
            continue
        user = await UserService(session).get_or_create_from_telegram(tg_user)
        await GroupService(session).register_membership(group, user)


@router.message(LeftChatMemberFilter())
async def on_left_chat_member(
    message: Message,
    session: AsyncSession,
) -> None:
    tg_user = message.left_chat_member
    chat = message.chat
    if (
        tg_user is None
        or chat.type not in _GROUP_CHAT_TYPES
        or tg_user.is_bot
        or message.bot is None
        or tg_user.id == message.bot.id
    ):
        return
    group = await GroupRepository(session).get_by_telegram_chat_id(chat.id)
    user = await UserRepository(session).get_by_telegram_id(tg_user.id)
    if group is not None and user is not None:
        await GroupService(session).remove_membership(group.id, user.id)
