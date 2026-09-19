from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.filters.command import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.chat_type import ChatTypeFilter
from app.bot.handlers.menu import build_menu_payload
from app.database.models import User
from app.services.group_service import GroupService

router = Router(name="start")

GROUP_HELP = """👋 Я в группе!

Я буду хранить домашние задания, дедлайны и напоминать о них.

Удобнее пользоваться мной в личке: нажми /start в личном чате со мной и выбери свою группу."""


@router.message(CommandStart(), ChatTypeFilter(ChatType.PRIVATE))
async def cmd_start_private(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    text, markup = await build_menu_payload(
        bot=bot, session=session, user=user, state=state
    )
    await message.answer(text, reply_markup=markup)


@router.message(
    CommandStart(), ChatTypeFilter(ChatType.GROUP, ChatType.SUPERGROUP)
)
async def cmd_start_group(
    message: Message,
    session: AsyncSession,
    user: User,
) -> None:
    group = await GroupService(session).register_group(message.chat)
    await GroupService(session).register_membership(group, user)
    await message.answer(GROUP_HELP)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(GROUP_HELP)
