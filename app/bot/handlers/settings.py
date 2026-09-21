from datetime import datetime, time

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.callback import CallbackDataPrefix
from app.bot.formats import esc, safe_int
from app.bot.handlers.menu import build_menu_payload
from app.bot.keyboards.homework import back_only_keyboard
from app.bot.keyboards.menu import CB_SETTINGS
from app.bot.keyboards.settings import (
    PAGE_SIZE_MEMBERS,
    SET_CODE_ROTATE,
    SET_LEAVE,
    SET_LEAVE_CONFIRM,
    SET_LEAVE_PICK,
    SET_MANAGE,
    SET_MANAGE_GROUP,
    SET_MEMBER_PAGE,
    SET_MEMBER_REMOVE,
    SET_MEMBER_REMOVE_CONFIRM,
    SET_MEMBERS,
    SET_NAME,
    SET_NOOP,
    SET_REMINDER,
    SET_REMINDER_SET,
    SET_RENAME_GROUP,
    SET_SUBJECT_DELETE,
    SET_SUBJECT_DELETE_CONFIRM,
    SET_SUBJECT_RENAME,
    SET_SUBJECTS,
    admin_group_picker_keyboard,
    leave_confirm_keyboard,
    leave_picker_keyboard,
    management_keyboard,
    member_remove_confirm_keyboard,
    members_keyboard,
    reminder_time_keyboard,
    settings_keyboard,
    subject_delete_confirm_keyboard,
    subjects_keyboard,
)
from app.bot.states.group_flow import SettingsFlow
from app.config import settings
from app.database.models import Group, Subject, User
from app.database.repositories import GroupRepository, SubjectRepository
from app.services.group_service import GroupError, GroupService, format_code
from app.services.homework_service import HomeworkService, SubjectError
from app.services.user_service import UserNameError, UserService

router = Router(name="settings")

SETTINGS_TEXT = "⚙️ Настройки\n\nВыбери раздел:"


def _user_label(user: User) -> str:
    if user.display_name:
        return user.display_name
    if user.first_name:
        return user.first_name
    if user.username:
        return f"@{user.username}"
    return f"id{user.telegram_id}"


def _management_text(
    group: Group, invite_code: str, expires_at: datetime, member_count: int
) -> str:
    chat_status = (
        "✅ чат привязан"
        if group.telegram_chat_id is not None
        else "⚠️ чат не привязан — используй /link КОД в чате группы"
    )
    reminder_label = (
        group.reminder_time.strftime("%H:%M")
        if group.reminder_time is not None
        else f"{settings.reminder_time.strftime('%H:%M')} (по умолчанию)"
    )
    return (
        f"🎛 <b>Управление группой «{esc(group.name)}»</b>\n\n"
        f"🔑 Инвайт-код: <code>{format_code(invite_code)}</code>\n"
        f"⏳ Действует до: {expires_at.strftime('%d.%m.%Y')}\n"
        f"🔔 Напоминания: {chat_status}\n"
        f"⏰ Время напоминания: <b>{esc(reminder_label)}</b>\n\n"
        f"👥 Участников: <b>{member_count}</b>"
    )


@router.callback_query(CallbackDataPrefix(CB_SETTINGS))
async def on_settings(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    message = query.message
    if not isinstance(message, Message):
        await query.answer()
        return
    admin_groups = await GroupService(session).admin_groups(user)
    await message.edit_text(
        SETTINGS_TEXT,
        reply_markup=settings_keyboard(has_admin_groups=bool(admin_groups)),
    )
    await query.answer()


@router.callback_query(CallbackDataPrefix(SET_NAME))
async def on_change_name(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    if not isinstance(query.message, Message):
        await query.answer()
        return
    await state.set_state(SettingsFlow.change_name)
    await query.message.edit_text(
        "👤 Твоё имя в группе.\n\n"
        "Как к тебе обращаться? Напиши имя на русском "
        "(например, «Иван»). Это имя увидят участники групп, "
        "где ты добавляешь домашние задания.",
        reply_markup=back_only_keyboard(),
    )
    await query.answer()


@router.message(StateFilter(SettingsFlow.change_name))
async def on_change_name_input(
    message: Message,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    service = UserService(session)
    try:
        name = await service.set_display_name(user, message.text or "")
    except UserNameError as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    await message.answer(
        f"✅ Готово! Теперь к тебе обращаются как <b>{esc(name)}</b>."
    )


@router.callback_query(CallbackDataPrefix(SET_MANAGE))
async def on_manage_pick(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    message = query.message
    if not isinstance(message, Message):
        await query.answer()
        return
    admin_groups = await GroupService(session).admin_groups(user)
    if not admin_groups:
        await query.answer("Ты не староста ни одной группы.", show_alert=True)
        return
    await message.edit_text(
        "Выбери группу для управления:",
        reply_markup=admin_group_picker_keyboard(admin_groups),
    )
    await query.answer()


async def render_management(
    query: CallbackQuery, session: AsyncSession, user: User, group_id: int
) -> None:
    message = query.message
    if not isinstance(message, Message):
        await query.answer()
        return
    service = GroupService(session)
    group = await GroupRepository(session).get(group_id)
    if group is None:
        await query.answer("Группа не найдена.", show_alert=True)
        return
    if not await service.is_admin(group, user):
        await query.answer("Это доступно только старосте группы.", show_alert=True)
        return
    code, expires_at = await service.invite_info(group)
    members = await service.list_members(group)
    await message.edit_text(
        _management_text(group, code, expires_at, len(members)),
        reply_markup=management_keyboard(group.id),
    )
    await query.answer()


@router.callback_query(CallbackDataPrefix(SET_MANAGE_GROUP))
async def on_management(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    if not query.data:
        await query.answer()
        return
    try:
        group_id = int(query.data[len(SET_MANAGE_GROUP):])
    except ValueError:
        await query.answer()
        return
    await render_management(query, session, user, group_id)


@router.callback_query(CallbackDataPrefix(SET_CODE_ROTATE))
async def on_code_rotate(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    if not query.data:
        await query.answer()
        return
    try:
        group_id = int(query.data[len(SET_CODE_ROTATE):])
    except ValueError:
        await query.answer()
        return
    service = GroupService(session)
    group = await GroupRepository(session).get(group_id)
    if group is None:
        await query.answer("Группа не найдена.", show_alert=True)
        return
    if not await service.is_admin(group, user):
        await query.answer("Это доступно только старосте группы.", show_alert=True)
        return
    await service.rotate_invite_code(group)
    await render_management(query, session, user, group_id)


@router.callback_query(CallbackDataPrefix(SET_NOOP))
async def on_noop(query: CallbackQuery) -> None:
    await query.answer()


@router.callback_query(CallbackDataPrefix(SET_RENAME_GROUP))
async def on_rename_group_request(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not query.data or not isinstance(query.message, Message):
        await query.answer()
        return
    group_id = safe_int(query.data[len(SET_RENAME_GROUP):])
    if group_id is None:
        await query.answer()
        return
    service = GroupService(session)
    group = await GroupRepository(session).get(group_id)
    if group is None or not await service.is_admin(group, user):
        await query.answer("Это доступно только старосте группы.", show_alert=True)
        return
    await state.set_state(SettingsFlow.rename_group)
    await state.update_data(rename_group_id=group_id)
    await query.message.edit_text(
        f"✏️ Новое название для группы «{esc(group.name)}».\n\n"
        "Напиши название (до 64 символов):",
        reply_markup=back_only_keyboard(),
    )
    await query.answer()


@router.message(StateFilter(SettingsFlow.rename_group))
async def on_rename_group_input(
    message: Message,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    group_id = data.get("rename_group_id")
    service = GroupService(session)
    group = (
        await GroupRepository(session).get(group_id)
        if group_id is not None
        else None
    )
    if group is None or not await service.is_admin(group, user):
        await state.clear()
        await message.answer("Группа не найдена или доступ запрещён.")
        return
    try:
        await service.rename_group(group, message.text or "")
    except GroupError as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    await message.answer(
        f"✅ Группа переименована в «{esc(group.name)}».",
        reply_markup=management_keyboard(group.id),
    )


@router.callback_query(CallbackDataPrefix(SET_MEMBERS))
async def on_members(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    if not query.data:
        await query.answer()
        return
    try:
        group_id = int(query.data[len(SET_MEMBERS):])
    except ValueError:
        await query.answer()
        return
    await render_members(query, session, user, group_id, offset=0)


@router.callback_query(CallbackDataPrefix(SET_MEMBER_PAGE))
async def on_members_page(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    if not query.data or query.data.count(":") < 2:
        await query.answer()
        return
    _, group_raw, offset_raw = query.data.split(":")
    try:
        group_id, offset = int(group_raw), int(offset_raw)
    except ValueError:
        await query.answer()
        return
    await render_members(query, session, user, group_id, offset=offset)


async def render_members(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
    group_id: int,
    offset: int,
) -> None:
    message = query.message
    if not isinstance(message, Message):
        await query.answer()
        return
    service = GroupService(session)
    group = await GroupRepository(session).get(group_id)
    if group is None:
        await query.answer("Группа не найдена.", show_alert=True)
        return
    if not await service.is_admin(group, user):
        await query.answer("Это доступно только старосте группы.", show_alert=True)
        return
    members = await service.list_members(group)
    chunk = members[offset : offset + PAGE_SIZE_MEMBERS]
    total_pages = max(1, (len(members) + PAGE_SIZE_MEMBERS - 1) // PAGE_SIZE_MEMBERS)
    labels = [(m.user_id, _user_label(m.user)) for m in chunk]
    text = (
        f"👥 <b>Участники «{esc(group.name)}»</b>\n\n"
        f"Страница {offset // PAGE_SIZE_MEMBERS + 1} из {total_pages}"
    )
    await message.edit_text(
        text,
        reply_markup=members_keyboard(group.id, labels, offset, len(members)),
    )
    await query.answer()


@router.callback_query(CallbackDataPrefix(SET_MEMBER_REMOVE))
async def on_member_remove(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    message = query.message
    payload = query.data[len(SET_MEMBER_REMOVE):] if query.data else ""
    group_raw, _, target_raw = payload.partition(":")
    if not isinstance(message, Message) or not group_raw or not target_raw:
        await query.answer()
        return
    try:
        group_id, target_user_id = int(group_raw), int(target_raw)
    except ValueError:
        await query.answer()
        return
    service = GroupService(session)
    group = await GroupRepository(session).get(group_id)
    if group is None:
        await query.answer("Группа не найдена.", show_alert=True)
        return
    if not await service.is_admin(group, user):
        await query.answer("Это доступно только старосте группы.", show_alert=True)
        return
    target_label = next(
        (
            _user_label(m.user)
            for m in await service.list_members(group)
            if m.user_id == target_user_id
        ),
        f"id{target_user_id}",
    )
    await message.edit_text(
        f"Удалить участника <b>{esc(target_label)}</b> из группы «{esc(group.name)}»?\n\n"
        "Его домашние задания останутся в группе.",
        reply_markup=member_remove_confirm_keyboard(group_id, target_user_id),
    )
    await query.answer()


@router.callback_query(CallbackDataPrefix(SET_MEMBER_REMOVE_CONFIRM))
async def on_member_remove_confirm(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    message = query.message
    payload = query.data[len(SET_MEMBER_REMOVE_CONFIRM):] if query.data else ""
    group_raw, _, target_raw = payload.partition(":")
    if not isinstance(message, Message) or not group_raw or not target_raw:
        await query.answer()
        return
    try:
        group_id, target_user_id = int(group_raw), int(target_raw)
    except ValueError:
        await query.answer()
        return
    service = GroupService(session)
    group = await GroupRepository(session).get(group_id)
    if group is None:
        await query.answer("Группа не найдена.", show_alert=True)
        return
    if not await service.is_admin(group, user):
        await query.answer("Это доступно только старосте группы.", show_alert=True)
        return
    try:
        await service.remove_member(group, target_user_id)
    except GroupError as exc:
        await query.answer(str(exc), show_alert=True)
        return
    await render_members(query, session, user, group_id, offset=0)


# ---------- Выход из группы ----------


@router.callback_query(CallbackDataPrefix(SET_LEAVE))
async def on_leave(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    message = query.message
    if not isinstance(message, Message):
        await query.answer()
        return
    groups = await GroupService(session).list_groups_for_user(user)
    if not groups:
        await query.answer("Ты пока не входишь ни в одну группу.", show_alert=True)
        return
    await message.edit_text(
        "👋 Решил уйти?\n\n"
        "Выбери группу, из которой хочешь выйти:",
        reply_markup=leave_picker_keyboard(groups),
    )
    await query.answer()


@router.callback_query(CallbackDataPrefix(SET_LEAVE_PICK))
async def on_leave_pick(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    message = query.message
    group_id = safe_int(query.data[len(SET_LEAVE_PICK):]) if query.data else None
    if not isinstance(message, Message) or group_id is None:
        await query.answer()
        return
    group = await GroupRepository(session).get(group_id)
    if group is None:
        await query.answer("Группа не найдена.", show_alert=True)
        return
    if not await GroupService(session).has_access(group, user):
        await query.answer("Ты не участник этой группы.", show_alert=True)
        return
    await message.edit_text(
        f"Точно покинуть группу «{esc(group.name)}»?\n\n"
        "Твои добавленные задания и файлы останутся в группе.",
        reply_markup=leave_confirm_keyboard(group_id),
    )
    await query.answer()


@router.callback_query(CallbackDataPrefix(SET_LEAVE_CONFIRM))
async def on_leave_confirm(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    message = query.message
    group_id = safe_int(query.data[len(SET_LEAVE_CONFIRM):]) if query.data else None
    if not isinstance(message, Message) or group_id is None:
        await query.answer()
        return
    group = await GroupRepository(session).get(group_id)
    if group is None:
        await query.answer("Группа не найдена.", show_alert=True)
        return
    if not await GroupService(session).has_access(group, user):
        await query.answer("Ты уже не участник этой группы.", show_alert=True)
        return
    try:
        await GroupService(session).leave_group(group, user)
    except GroupError as exc:
        await query.answer(str(exc), show_alert=True)
        return
    await state.clear()
    text, markup = await build_menu_payload(session=session, user=user, state=state)
    await message.edit_text(text, reply_markup=markup)
    await query.answer("✅ Ты вышел из группы.")


# ---------- Предметы ----------


def _subjects_text(group: Group, subjects: list[Subject]) -> str:
    lines = [f"📚 <b>Предметы «{esc(group.name)}»</b>"]
    if not subjects:
        lines.append("\nПока нет предметов.")
    for index, subject in enumerate(subjects, 1):
        lines.append(f"{index}. {esc(subject.name)}")
    return "\n".join(lines)


async def render_subjects(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
    group_id: int,
) -> None:
    message = query.message
    if not isinstance(message, Message):
        await query.answer()
        return
    service = GroupService(session)
    group = await GroupRepository(session).get(group_id)
    if group is None:
        await query.answer("Группа не найдена.", show_alert=True)
        return
    if not await service.is_admin(group, user):
        await query.answer("Это доступно только старосте группы.", show_alert=True)
        return
    subjects = await HomeworkService(session).list_subjects(group.id)
    await message.edit_text(
        _subjects_text(group, subjects),
        reply_markup=subjects_keyboard(group.id, subjects),
    )
    await query.answer()


@router.callback_query(CallbackDataPrefix(SET_SUBJECTS))
async def on_subjects(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    group_id = safe_int(query.data[len(SET_SUBJECTS):]) if query.data else None
    if group_id is None:
        await query.answer()
        return
    await render_subjects(query, session, user, group_id)


@router.callback_query(CallbackDataPrefix(SET_SUBJECT_RENAME))
async def on_subject_rename_request(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    message = query.message
    subject_id = (
        safe_int(query.data[len(SET_SUBJECT_RENAME):]) if query.data else None
    )
    if not isinstance(message, Message) or subject_id is None:
        await query.answer()
        return
    subject = await SubjectRepository(session).get(subject_id)
    if subject is None:
        await query.answer("Предмет не найден.", show_alert=True)
        return
    group = await GroupRepository(session).get(subject.group_id)
    if group is None or not await GroupService(session).is_admin(group, user):
        await query.answer("Это доступно только старосте группы.", show_alert=True)
        return
    await state.set_state(SettingsFlow.rename_subject)
    await state.update_data(rename_subject_id=subject.id)
    await message.edit_text(
        f"✏️ Новое название для предмета «{esc(subject.name)}»:\n\n"
        "Напиши название (до 128 символов):",
        reply_markup=back_only_keyboard(),
    )
    await query.answer()


@router.message(StateFilter(SettingsFlow.rename_subject))
async def on_subject_rename_input(
    message: Message,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    subject_id = data.get("rename_subject_id")
    service = GroupService(session)
    subject = (
        await SubjectRepository(session).get(subject_id)
        if subject_id is not None
        else None
    )
    if subject is None:
        await state.clear()
        await message.answer("Предмет не найден.")
        return
    group = await GroupRepository(session).get(subject.group_id)
    if group is None or not await service.is_admin(group, user):
        await state.clear()
        await message.answer("Группа не найдена или доступ запрещён.")
        return
    try:
        await HomeworkService(session).rename_subject(subject, message.text or "")
    except SubjectError as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    subjects = await HomeworkService(session).list_subjects(group.id)
    await message.answer(
        f"✅ Предмет переименован в «{esc(subject.name)}».\n\n"
        + _subjects_text(group, subjects),
        reply_markup=subjects_keyboard(group.id, subjects),
    )


@router.callback_query(CallbackDataPrefix(SET_SUBJECT_DELETE))
async def on_subject_delete(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    message = query.message
    subject_id = (
        safe_int(query.data[len(SET_SUBJECT_DELETE):]) if query.data else None
    )
    if not isinstance(message, Message) or subject_id is None:
        await query.answer()
        return
    subject = await SubjectRepository(session).get(subject_id)
    if subject is None:
        await query.answer("Предмет не найден.", show_alert=True)
        return
    group = await GroupRepository(session).get(subject.group_id)
    if group is None or not await GroupService(session).is_admin(group, user):
        await query.answer("Это доступно только старосте группы.", show_alert=True)
        return
    count = await HomeworkService(session).count_subject_homeworks(subject)
    await message.edit_text(
        f"Удалить предмет <b>{esc(subject.name)}</b> из группы «{esc(group.name)}»?\n\n"
        f"Вместе с ним будет удалено заданий: <b>{count}</b> "
        "(и прикреплённые файлы/ссылки).",
        reply_markup=subject_delete_confirm_keyboard(group.id, subject.id, count),
    )
    await query.answer()


@router.callback_query(CallbackDataPrefix(SET_SUBJECT_DELETE_CONFIRM))
async def on_subject_delete_confirm(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    subject_id = (
        safe_int(query.data[len(SET_SUBJECT_DELETE_CONFIRM):])
        if query.data
        else None
    )
    if subject_id is None:
        await query.answer()
        return
    subject = await SubjectRepository(session).get(subject_id)
    if subject is None:
        await query.answer("Предмет не найден.", show_alert=True)
        return
    group = await GroupRepository(session).get(subject.group_id)
    if group is None or not await GroupService(session).is_admin(group, user):
        await query.answer("Это доступно только старосте группы.", show_alert=True)
        return
    deleted = await HomeworkService(session).delete_subject(subject)
    await query.answer(f"Предмет удалён. Заданий удалено: {deleted}")
    await render_subjects(query, session, user, group.id)


# ---------- Время напоминаний ----------


@router.callback_query(CallbackDataPrefix(SET_REMINDER))
async def on_reminder(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    message = query.message
    group_id = safe_int(query.data[len(SET_REMINDER):]) if query.data else None
    if not isinstance(message, Message) or group_id is None:
        await query.answer()
        return
    service = GroupService(session)
    group = await GroupRepository(session).get(group_id)
    if group is None:
        await query.answer("Группа не найдена.", show_alert=True)
        return
    if not await service.is_admin(group, user):
        await query.answer("Это доступно только старосте группы.", show_alert=True)
        return
    reminder_label = (
        group.reminder_time.strftime("%H:%M")
        if group.reminder_time is not None
        else f"{settings.reminder_time.strftime('%H:%M')} (по умолчанию)"
    )
    await message.edit_text(
        "⏰ Время вечернего напоминания о дедлайнах на завтра.\n\n"
        f"Сейчас установлено: <b>{esc(reminder_label)}</b>\n\n"
        "Выбери новое время:",
        reply_markup=reminder_time_keyboard(group.id),
    )
    await query.answer()


@router.callback_query(CallbackDataPrefix(SET_REMINDER_SET))
async def on_reminder_set(
    query: CallbackQuery,
    session: AsyncSession,
    user: User,
) -> None:
    payload = query.data[len(SET_REMINDER_SET):] if query.data else ""
    group_raw, _, value = payload.partition(":")
    group_id = safe_int(group_raw)
    if group_id is None or not value:
        await query.answer()
        return
    service = GroupService(session)
    group = await GroupRepository(session).get(group_id)
    if group is None:
        await query.answer("Группа не найдена.", show_alert=True)
        return
    if not await service.is_admin(group, user):
        await query.answer("Это доступно только старосте группы.", show_alert=True)
        return
    if value == "d":
        reminder: time | None = None
    else:
        hour_raw, _, minute_raw = value.partition(":")
        try:
            reminder = time(int(hour_raw), int(minute_raw))
        except ValueError:
            await query.answer()
            return
    await service.set_reminder_time(group, reminder)
    await render_management(query, session, user, group_id)
