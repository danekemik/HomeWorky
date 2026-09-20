from aiogram import Router
from aiogram.enums import ChatType
from aiogram.filters import StateFilter
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.context import select_current_group
from app.bot.filters.callback import CallbackDataPrefix
from app.bot.filters.chat_type import ChatTypeFilter
from app.bot.formats import esc
from app.bot.keyboards.menu import (
    CB_JOIN_PICK,
    CB_ONBOARD_CREATE,
    CB_ONBOARD_JOIN,
    CB_PICK_GROUP_PREFIX,
    group_picker_keyboard,
    join_group_picker_keyboard,
    main_menu_keyboard,
    onboarding_keyboard,
    onboarding_no_join_keyboard,
)
from app.bot.states.group_flow import GroupFlow
from app.database.models import Group, User
from app.database.repositories.group_repository import GroupRepository
from app.services.group_service import (
    GroupError,
    GroupService,
    format_code,
)

router = Router(name="menu")

WELCOME_NO_GROUP = (
    "👋 Привет!\n\n"
    "Я помогу вашей группе не забывать домашние задания и дедлайны.\n\n"
    "Создай свою группу (ты станешь её старостой) или "
    "присоединись к существующей по коду, который староста выдаст в чате группы."
)

PICK_GROUP_TEXT = "Выбери свою группу 👇"
MENU_TEXT = (
    "<b>🐹 Привет, Я Homy!</b>\n\n"
    "Я слежу за твоими домашками, чтобы ты мог не переживать, если что-то забыл 😎\n\n"
    "👥 Группа: <b>{title}</b>\n\n"
    "Выбирай, чем займёмся 👇"
)

CREATE_NAME_PENDING = "✏️ Введи название группы (например, «ВКБ-22»):"
JOIN_GROUPS_EMPTY = "Пока ни одной группы не создано. Создай первую 👇"
JOIN_PICK_TEXT = "Выбери группу, к которой хочешь присоединиться 👇"
JOIN_CODE_PENDING = "🔑 Введи инвайт-код группы:"


def _menu_text(group: Group) -> str:
    return MENU_TEXT.format(title=esc(group.name))


async def build_menu_payload(
    *,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> tuple[str, InlineKeyboardMarkup | None]:
    groups = await GroupService(session).list_groups_for_user(user)
    if not groups:
        return WELCOME_NO_GROUP, onboarding_keyboard()
    if len(groups) == 1:
        select_current_group(user, groups[0].id)
        await state.update_data(current_group_id=groups[0].id)
        return _menu_text(groups[0]), main_menu_keyboard()
    return PICK_GROUP_TEXT, group_picker_keyboard(groups)


@router.message(Command("menu"), ChatTypeFilter(ChatType.PRIVATE))
async def cmd_menu(
    message: Message,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    await state.clear()
    text, markup = await build_menu_payload(session=session, user=user, state=state)
    await message.answer(text, reply_markup=markup)


@router.callback_query(CallbackDataPrefix(CB_PICK_GROUP_PREFIX))
async def on_pick_group(
    query: CallbackQuery,
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
    service = GroupService(session)
    group = await GroupRepository(session).get(group_id)
    if group is None:
        await query.answer("Группа не найдена.", show_alert=True)
        return
    if not await service.has_access(group, user):
        groups = await service.list_groups_for_user(user)
        await message.edit_text(
            PICK_GROUP_TEXT, reply_markup=group_picker_keyboard(groups)
        )
        await query.answer("Доступ к этой группе запрещён.", show_alert=True)
        return
    select_current_group(user, group.id)
    await state.update_data(current_group_id=group.id)
    await message.edit_text(
        _menu_text(group), reply_markup=main_menu_keyboard()
    )
    await query.answer()


@router.callback_query(CallbackDataPrefix(CB_ONBOARD_CREATE))
async def on_create_group(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    message = query.message
    if not isinstance(message, Message):
        await query.answer()
        return
    await state.set_state(GroupFlow.create_name)
    await message.edit_text(CREATE_NAME_PENDING)
    await query.answer()


@router.message(StateFilter(GroupFlow.create_name))
async def on_create_group_name(
    message: Message,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    service = GroupService(session)
    try:
        group = await service.create_group(creator=user, name=message.text or "")
    except GroupError as exc:
        await message.answer(str(exc))
        return

    await state.clear()
    select_current_group(user, group.id)
    await state.update_data(current_group_id=group.id)
    human_code = format_code(group.invite_code)
    await message.answer(
        f"🎉 Группа <b>«{esc(group.name)}»</b> создана!\n\n"
        f"🔑 Инвайт-код: <code>{human_code}</code>\n"
        "Отправь этот код в чат своей группы, чтобы участники могли присоединиться.\n\n"
        "Чтобы я присылал напоминания: добавь меня в групповой чат и напиши в нём:\n"
        f"<code>/link {human_code}</code>",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(CallbackDataPrefix(CB_ONBOARD_JOIN))
async def on_join_start(
    query: CallbackQuery,
    session: AsyncSession,
) -> None:
    message = query.message
    if not isinstance(message, Message):
        await query.answer()
        return
    groups = await GroupRepository(session).list_all()
    if not groups:
        await message.edit_text(
            JOIN_GROUPS_EMPTY, reply_markup=onboarding_no_join_keyboard()
        )
        await query.answer()
        return
    await message.edit_text(JOIN_PICK_TEXT, reply_markup=join_group_picker_keyboard(groups))
    await query.answer()


@router.callback_query(CallbackDataPrefix(CB_JOIN_PICK))
async def on_join_pick(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    message = query.message
    if not query.data or not isinstance(message, Message):
        await query.answer()
        return
    group_id = int(query.data[len(CB_JOIN_PICK):])
    await state.set_state(GroupFlow.join_code)
    await state.update_data(join_group_id=group_id)
    await message.edit_text(JOIN_CODE_PENDING)
    await query.answer()


@router.message(StateFilter(GroupFlow.join_code))
async def on_join_code(
    message: Message,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    group_id = data.get("join_group_id")
    if group_id is None:
        await state.clear()
        await message.answer("Начни заново: /menu")
        return
    group = await GroupRepository(session).get(group_id)
    if group is None:
        await state.clear()
        await message.answer("Группа не найдена.", reply_markup=onboarding_keyboard())
        return
    error = await GroupService(session).join_group(
        group=group, user=user, code=message.text or ""
    )
    if error is not None:
        await message.answer(error)
        return
    await state.clear()
    select_current_group(user, group.id)
    await state.update_data(current_group_id=group.id)
    text, markup = await build_menu_payload(session=session, user=user, state=state)
    await message.answer(f"✅ Ты в группе «{esc(group.name)}»!")
    await message.answer(text, reply_markup=markup)
