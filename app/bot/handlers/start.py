from aiogram import Router
from aiogram.enums import ChatType
from aiogram.filters.command import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.chat_type import ChatTypeFilter
from app.bot.handlers.menu import build_menu_payload
from app.database.models import User

router = Router(name="start")

GROUP_HELP = """👋 Я в группе!

Я буду напоминать о дедлайнах и хранить домашние задания.

Управление происходит в личном чате со мной:
1. Нажми /start в личке и создай свою группу или присоединись по коду.
2. Староста может привязать этот чат для напоминаний: /link КОД."""


@router.message(CommandStart(), ChatTypeFilter(ChatType.PRIVATE))
async def cmd_start_private(
    message: Message,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    await state.clear()
    text, markup = await build_menu_payload(session=session, user=user, state=state)
    await message.answer(text, reply_markup=markup)


@router.message(
    CommandStart(), ChatTypeFilter(ChatType.GROUP, ChatType.SUPERGROUP)
)
async def cmd_start_group(message: Message) -> None:
    await message.answer(GROUP_HELP)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(GROUP_HELP)
