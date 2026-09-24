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

HELP_TEXT = (
    "🐹 *Homy открывает свой блокнот с инструкцией*\n"
    "\n"
    "📚 <b>Добавить ДЗ</b>\n"
    "Запиши предмет, задание и дедлайн — я всё сохраню\n"
    "\n"
    "📅 <b>Дедлайны</b>\n"
    "Покажу, что нужно сдать сегодня и завтра\n"
    "\n"
    "🔔 <b>Напоминания</b>\n"
    "Сам напомню, когда дедлайн уже близко\n"
    "\n"
    "📎 <b>Файлы и ссылки</b>\n"
    "Прикрепляй задания, методички и полезные ссылки\n"
    "\n"
    "📊 <b>Статистика</b>\n"
    "Посмотри, сколько заданий сейчас активно\n"
    "\n"
    "👥 <b>Присоединиться к группе</b>\n"
    "Попроси <b>код приглашения у старосты</b> и введи его в боте\n"
    "\n"
    "🐹 *Homy закрывает блокнот*\n"
    "\n"
    "<b>Ты учишься — я слежу, чтобы ничего не потерялось 😎</b>"
)


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


@router.message(
    Command("help"), ChatTypeFilter(ChatType.PRIVATE)
)
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)
