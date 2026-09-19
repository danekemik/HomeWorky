from aiogram import Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.callback import CallbackDataPrefix
from app.bot.keyboards.menu import CB_SETTINGS
from app.database.models import User

router = Router(name="settings")

SETTINGS_TEXT = (
    "⚙️ Настройки\n\n"
    "🚧 Раздел появится на следующем этапе разработки.\n"
    "Пока здесь можно будет менять время напоминаний и язык бота."
)


@router.callback_query(CallbackDataPrefix(CB_SETTINGS))
async def on_settings(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not isinstance(query.message, Message):
        await query.answer()
        return
    await query.message.edit_text(SETTINGS_TEXT)
    await query.answer()
