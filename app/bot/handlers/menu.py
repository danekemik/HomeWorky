from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.callback import CallbackDataPrefix
from app.bot.filters.chat_type import ChatTypeFilter
from app.bot.keyboards.menu import (
    CB_PICK_GROUP_PREFIX,
    group_picker_keyboard,
    main_menu_keyboard,
)
from app.database.models import Group, User
from app.database.repositories.group_repository import GroupRepository
from app.services.group_service import GroupService

router = Router(name="menu")

WELCOME_NO_GROUP = (
    "👋 Привет!\n\n"
    "Я помогу вашей группе не забывать домашние задания и дедлайны.\n\n"
    "Добавь меня в свою группу, а затем напиши мне в группе /start — "
    "я запомню тебя как её участника. После этого здесь откроется меню."
)

PICK_GROUP_TEXT = "Выбери свою группу 👇"
MENU_TEXT = "🎓 Учебный помощник\n\nГруппа: <b>{title}</b>"
COMING_SOON = "🚧 Этот раздел появится на следующих этапах разработки."


def _menu_text(group: Group) -> str:
    title = group.title or f"Группа #{group.id}"
    return MENU_TEXT.format(title=title)


async def build_menu_payload(
    *,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> tuple[str, InlineKeyboardMarkup | None]:
    groups = await GroupService(session).list_verified_groups(bot, user)
    if not groups:
        return WELCOME_NO_GROUP, None
    if len(groups) == 1:
        group = groups[0]
        await state.update_data(current_group_id=group.id)
        return _menu_text(group), main_menu_keyboard()
    return PICK_GROUP_TEXT, group_picker_keyboard(groups)


@router.message(Command("menu"), ChatTypeFilter(ChatType.PRIVATE))
async def cmd_menu(
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


@router.callback_query(CallbackDataPrefix(CB_PICK_GROUP_PREFIX))
async def on_pick_group(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    raw = query.data
    message = query.message
    if (
        raw is None
        or not isinstance(message, Message)
        or message.edit_text is None
    ):
        await query.answer()
        return
    group_id = int(raw.split(":", 1)[1])
    group = await GroupRepository(session).get(group_id)
    if group is None:
        await query.answer("Группа не найдена.", show_alert=True)
        return
    allowed = await GroupService(session).verify_access(
        bot, group, user.telegram_id
    )
    if not allowed:
        groups = await GroupService(session).list_verified_groups(bot, user)
        await message.edit_text(
            PICK_GROUP_TEXT, reply_markup=group_picker_keyboard(groups)
        )
        await query.answer("Доступ к этой группе запрещён.", show_alert=True)
        return
    await state.update_data(current_group_id=group.id)
    await message.edit_text(
        _menu_text(group), reply_markup=main_menu_keyboard()
    )
    await query.answer()


@router.callback_query(CallbackDataPrefix("menu:"))
async def on_menu_action(query: CallbackQuery) -> None:
    await query.answer(COMING_SOON)
