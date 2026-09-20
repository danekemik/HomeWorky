from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Chat, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.context import resolve_group
from app.bot.filters.callback import CallbackDataPrefix
from app.bot.filters.chat_type import ChatTypeFilter
from app.bot.formats import bot_today, esc
from app.bot.keyboards.menu import CB_STATS
from app.bot.keyboards.views import back_to_menu_keyboard
from app.database.models import User
from app.services.homework_service import HomeworkService

router = Router(name="statistics")

NO_GROUP_TEXT = "Сначала выбери свою группу в меню (/menu)."


@router.callback_query(CallbackDataPrefix(CB_STATS))
async def on_stats_callback(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not isinstance(query.message, Message):
        await query.answer()
        return
    text, markup = await _render_stats(
        bot=bot, session=session, user=user, state=state, chat=query.message.chat
    )
    await query.message.edit_text(text, reply_markup=markup)
    await query.answer()


@router.message(Command("stats"), ChatTypeFilter(ChatType.PRIVATE))
async def on_stats_command(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    text, markup = await _render_stats(
        bot=bot, session=session, user=user, state=state, chat=message.chat
    )
    await message.answer(text, reply_markup=markup)


async def _render_stats(
    *,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    chat: Chat | None,
) -> tuple[str, InlineKeyboardMarkup | None]:
    group = await resolve_group(bot, session, user, chat, state)
    if group is None:
        return NO_GROUP_TEXT, None
    stats = await HomeworkService(session).stats(group.id, user.id, bot_today())
    title = group.name
    text = (
        "📊 <b>Статистика</b>\n\n"
        f"Группа: <b>{esc(title)}</b>\n\n"
        f"• Заданий всего: <b>{stats['total']}</b>\n"
        f"• Актуальных: <b>{stats['active']}</b>\n"
        f"• Сдаётся сегодня: <b>{stats['today']}</b>\n"
        f"• Сдаётся завтра: <b>{stats['tomorrow']}</b>\n"
        f"• Создано мной: <b>{stats['created_by_me']}</b>"
    )
    return text, back_to_menu_keyboard()
