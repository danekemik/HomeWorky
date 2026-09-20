from datetime import date

from aiogram import Bot, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.calendar import build_calendar_markup
from app.bot.callbacks import (
    ATTACH_DONE,
    ATTACH_SKIP,
    FLOW_CANCEL,
    HW_EDIT_PENDING,
    HW_SAVE,
    MENU_BACK,
    SKIP,
)
from app.bot.context import resolve_group
from app.bot.filters.callback import CallbackDataPrefix
from app.bot.formats import bot_today, build_homework_card
from app.bot.keyboards.homework import (
    attachment_keyboard,
    preview_keyboard,
    skip_or_cancel_keyboard,
    subject_picker_keyboard,
)
from app.bot.keyboards.menu import CB_ADD_HOMEWORK, main_menu_keyboard
from app.bot.states.homework import HomeworkCreation, HomeworkEditField
from app.database.models import AttachmentType, User
from app.services.homework_service import HomeworkService

router = Router(name="homework")

NO_GROUP_TEXT = "Сначала выбери свою группу в меню (/menu)."


@router.callback_query(CallbackDataPrefix(CB_ADD_HOMEWORK))
async def on_add_homework(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    await render_subject_picker(query, bot, session, user, state)
SUBJECT_PENDING = "📚 Выбери предмет:"
TITLE_PENDING = "✏️ Введи название задания:"
DESCRIPTION_PENDING = "📝 Добавь описание (или пропусти):"
DEADLINE_PENDING = "📅 Укажи дату сдачи:"
ATTACH_PENDING = (
    "📎 Прикрепи файл, фото или ссылку (можно несколько). "
    "Когда закончишь — нажми «✅ Готово»."
)


async def render_subject_picker(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    message = query.message
    if not isinstance(message, Message):
        await query.answer()
        return
    group = await resolve_group(bot, session, user, message.chat, state)
    if group is None:
        await query.answer(NO_GROUP_TEXT, show_alert=True)
        return
    await state.update_data(current_group_id=group.id)
    await state.set_state(HomeworkCreation.subject)
    subjects = await HomeworkService(session).list_subjects(group.id)
    await message.edit_text(SUBJECT_PENDING, reply_markup=subject_picker_keyboard(subjects))
    await query.answer()


def _attachment_display(item: dict[str, object]) -> str:
    file_type = str(item.get("file_type"))
    file_name = item.get("file_name")
    if file_type == "photo":
        return "🖼 Фото"
    return f"📄 {file_name or 'Файл'}"


def _pending_preview_card(data: dict) -> str:
    subject = str(data.get("subject_name") or data.get("subject_id") or "—")
    deadline = date.fromisoformat(str(data["deadline"]))
    attachment_lines = [
        _attachment_display(item)
        for item in data.get("attachments", [])  # type: ignore[arg-type]
    ]
    link_lines = [
        str(link.get("title") or link["url"])
        for link in data.get("links", [])  # type: ignore[arg-type]
    ]
    return build_homework_card(
        subject=subject,
        title=str(data["title"]),
        deadline=deadline,
        description=data.get("description") and str(data["description"]),
        attachment_lines=attachment_lines,
        link_lines=link_lines,
        footer_note="Сохранить задание?",
    )


async def render_calendar(query: CallbackQuery, cursor: date) -> None:
    if not isinstance(query.message, Message):
        await query.answer()
        return
    await query.message.edit_text(
        DEADLINE_PENDING, reply_markup=build_calendar_markup(cursor)
    )
    await query.answer()


def _is_base_creation(state: str | None) -> bool:
    return state is not None and state.startswith(HomeworkCreation.__name__)


def _is_base_edit(state: str | None) -> bool:
    return state is not None and state.startswith(HomeworkEditField.__name__)


@router.callback_query(StateFilter(HomeworkCreation.subject, HomeworkEditField.field))
async def on_subject_pick(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not query.data or not isinstance(query.message, Message):
        await query.answer()
        return
    message: Message = query.message
    state_name = await state.get_state()
    value = query.data.split(":", 1)[1]
    if value == "new":
        text = "➕ Введи название нового предмета:"
        new_state = (
            HomeworkCreation.new_subject
            if _is_base_creation(state_name)
            else HomeworkEditField.new_subject
        )
        await state.set_state(new_state)
        await message.edit_text(text)
        await query.answer()
        return

    try:
        subject_id = int(value)
    except ValueError:
        await query.answer()
        return

    group = await resolve_group(bot, session, user, message.chat, state)
    if group is None:
        await query.answer(NO_GROUP_TEXT, show_alert=True)
        return
    await state.update_data(current_group_id=group.id)
    service = HomeworkService(session)

    if _is_base_edit(state_name):
        homework_id = (await state.get_data()).get("homework_id")
        homework = (
            await service.get_for_group(int(homework_id), group.id)
            if homework_id is not None
            else None
        )
        if homework is None:
            await query.answer("Задание не найдено.", show_alert=True)
            await state.clear()
            return
        if not await service.can_modify(user, group.id, homework):
            await query.answer("Только автор или модератор может менять.", show_alert=True)
            return
        await service.set_subject(homework, subject_id)
        from app.bot.handlers.views import render_homework_detail

        await render_homework_detail(
            message=message,
            bot=bot,
            session=session,
            user=user,
            state=state,
            homework_id=homework.id,
        )
        await state.clear()
        await query.answer()
        return

    subject = await service.get_subject(subject_id)
    await state.update_data(
        subject_id=subject_id,
        subject_name=subject.name if subject is not None else None,
    )
    await state.set_state(HomeworkCreation.title)
    await message.edit_text(TITLE_PENDING)
    await query.answer()


async def _apply_new_subject(
    *,
    text: str,
    group_id: int,
    session: AsyncSession,
) -> int:
    service = HomeworkService(session)
    name = text.strip()
    existing = await service.subject_by_name(group_id, name)
    if existing is not None:
        return existing.id
    subject = await service.create_subject(group_id, name)
    return subject.id


@router.message(StateFilter(HomeworkCreation.new_subject, HomeworkEditField.new_subject))
async def on_new_subject(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    name = message.text or ""
    if not name.strip():
        await message.answer("Название предмета не может быть пустым.")
        return
    group = await resolve_group(bot, session, user, message.chat, state)
    if group is None:
        await message.answer(NO_GROUP_TEXT)
        return
    service = HomeworkService(session)
    subject_id = await _apply_new_subject(
        text=name, group_id=group.id, session=session
    )
    subject = await service.get_subject(subject_id)
    await state.update_data(
        current_group_id=group.id,
        subject_id=subject_id,
        subject_name=subject.name if subject is not None else name,
    )

    state_name = await state.get_state()
    if _is_base_edit(state_name):
        homework_id = (await state.get_data()).get("homework_id")
        homework = (
            await service.get_for_group(int(homework_id), group.id)
            if homework_id is not None
            else None
        )
        if homework is None or not await service.can_modify(user, group.id, homework):
            await state.clear()
            await message.answer("Доступ запрещён или задание не найдено.")
            return
        await service.set_subject(homework, subject_id)
        await state.clear()
        detail = await service.get_detail(homework)
        from app.bot.handlers.views import _detail_payload

        text, markup = _detail_payload(homework, detail, True)
        await message.answer(text, reply_markup=markup)
    else:
        await state.set_state(HomeworkCreation.title)
        await message.answer(TITLE_PENDING)


@router.message(StateFilter(HomeworkCreation.title))
async def on_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("Название не может быть пустым.")
        return
    await state.update_data(title=title)
    await state.set_state(HomeworkCreation.description)
    await message.answer(DESCRIPTION_PENDING, reply_markup=skip_or_cancel_keyboard())


@router.message(StateFilter(HomeworkCreation.description))
async def on_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=(message.text or "").strip() or None)
    await state.set_state(HomeworkCreation.deadline)
    await message.answer(DEADLINE_PENDING, reply_markup=build_calendar_markup(bot_today()))


@router.callback_query(StateFilter(HomeworkCreation.deadline, HomeworkEditField.deadline))
async def on_calendar(
    query: CallbackQuery, state: FSMContext
) -> None:
    if not query.data or not isinstance(query.message, Message):
        await query.answer()
        return
    payload = query.data.split(":", 1)[1]
    if payload == "noop":
        await query.answer()
        return
    if payload.startswith("nav:"):
        try:
            year_raw, month_raw = payload[4:].split("-")
            cursor = date(int(year_raw), int(month_raw), 1)
        except ValueError:
            await query.answer()
            return
        await render_calendar(query, cursor)
        return
    if not payload.startswith("day:"):
        await query.answer()
        return

    state_name = await state.get_state()
    try:
        chosen = date.fromisoformat(payload[4:])
    except ValueError:
        await query.answer()
        return

    if _is_base_edit(state_name):
        await state.update_data(deadline=chosen.isoformat())
        await state.set_state(HomeworkEditField.attachment)
        await query.message.edit_text(
            ATTACH_PENDING, reply_markup=attachment_keyboard()
        )
        await query.answer()
        return

    await state.update_data(deadline=chosen.isoformat())
    await state.set_state(HomeworkCreation.attachment)
    await query.message.edit_text(ATTACH_PENDING, reply_markup=attachment_keyboard())
    await query.answer()


def _collect_attachment(message: Message) -> dict[str, object] | None:
    if message.document is not None:
        return {
            "file_type": AttachmentType.DOCUMENT.value,
            "telegram_file_id": message.document.file_id,
            "file_name": message.document.file_name,
        }
    if message.photo:
        largest = max(message.photo, key=lambda size: size.width * size.height)
        return {
            "file_type": AttachmentType.PHOTO.value,
            "telegram_file_id": largest.file_id,
            "file_name": None,
        }
    return None


def _parse_link(text: str) -> dict[str, str | None] | None:
    stripped = text.strip()
    if stripped.startswith(("http://", "https://")):
        return {"url": stripped, "title": None}
    return None


@router.message(StateFilter(HomeworkCreation.attachment, HomeworkEditField.attachment))
async def on_attachment_message(
    message: Message, bot: Bot, session: AsyncSession, user: User, state: FSMContext
) -> None:
    data = dict(await state.get_data())
    if message.text:
        link = _parse_link(message.text)
        if link is not None:
            data.setdefault("links", []).append(link)
    else:
        attachment = _collect_attachment(message)
        if attachment is not None:
            data.setdefault("attachments", []).append(attachment)
        else:
            await message.answer("Пришли файл 📄, фото 🖼, ссылку 🔗 или нажми «✅ Готово».")
            return
    await state.update_data(**data)
    files = len(data.get("attachments", []))
    links = len(data.get("links", []))
    await message.answer(
        f"➕ Добавлено: 📄 ×{files}, 🔗 ×{links}. "
        "Можно добавить ещё или «✅ Готово».",
        reply_markup=attachment_keyboard(),
    )


async def _finalize_creation(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not isinstance(query.message, Message):
        await query.answer()
        return
    data = await state.get_data()
    group = await resolve_group(
        bot, session, user, query.message.chat, state
    )
    if group is None:
        await query.answer(NO_GROUP_TEXT, show_alert=True)
        await state.clear()
        return
    service = HomeworkService(session)
    deadline_raw = data.get("deadline")
    title = str(data.get("title", "")).strip()
    if not deadline_raw or not title or not data.get("subject_id"):
        await query.answer("Данные неполные. Начни заново.", show_alert=True)
        await state.clear()
        return
    deadline = date.fromisoformat(str(deadline_raw))
    homework = await service.create_homework(
        group_id=group.id,
        subject_id=int(data["subject_id"]),
        author_id=user.id,
        title=title,
        deadline=deadline,
        description=data.get("description") and str(data["description"]),
    )
    await service.attach_pending(
        homework,
        attachments=list(data.get("attachments", [])),  # type: ignore[arg-type]
        links=list(data.get("links", [])),  # type: ignore[arg-type]
    )
    await state.clear()
    detail = await service.get_detail(homework)
    text = build_homework_card(
        subject=detail.subject,
        title=homework.title,
        deadline=homework.deadline,
        description=homework.description,
        author_name=detail.author_name,
        attachment_lines=[
            (
                item.file_name
                or (
                    "🖼 Фото"
                    if item.file_type == AttachmentType.PHOTO
                    else "📄 Файл"
                )
            )
            + " (✅)"
            for item in detail.attachments
        ],
        link_lines=[link.title or link.url for link in detail.links],
        footer_note="✅ Задание создано и появится в списках.",
    )
    await query.message.edit_text(text, reply_markup=main_menu_keyboard())
    await query.answer("Задание создано ✅", show_alert=False)


async def _show_preview(query: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(query.message, Message):
        await query.answer()
        return
    data = await state.get_data()
    await query.message.edit_text(
        _pending_preview_card(data), reply_markup=preview_keyboard()
    )
    await query.answer()


@router.callback_query(CallbackDataPrefix(ATTACH_DONE))
async def on_attachments_done(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    state_name = await state.get_state()
    if _is_base_edit(state_name):
        from app.bot.handlers.views import finalize_edit_attachments

        await finalize_edit_attachments(
            query=query, bot=bot, session=session, user=user, state=state
        )
        return
    await _show_preview(query, state)


@router.callback_query(CallbackDataPrefix(ATTACH_SKIP))
async def on_attachments_skip(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    await on_attachments_done(query, bot, session, user, state)


@router.callback_query(CallbackDataPrefix(SKIP))
async def on_skip(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not isinstance(query.message, Message):
        await query.answer()
        return
    state_name = await state.get_state()
    if state_name == HomeworkCreation.description.state:
        await state.update_data(description=None)
        await state.set_state(HomeworkCreation.deadline)
        await query.message.edit_text(
            DEADLINE_PENDING, reply_markup=build_calendar_markup(bot_today())
        )
        await query.answer()
        return
    if state_name == HomeworkEditField.description.state:
        from app.bot.handlers.views import apply_edit_field

        await apply_edit_field(
            query=query, bot=bot, session=session, user=user, state=state
        )
        return
    await query.answer()


@router.callback_query(CallbackDataPrefix(FLOW_CANCEL))
async def on_flow_cancel(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    await state.clear()
    if not isinstance(query.message, Message):
        await query.answer()
        return
    from app.bot.handlers.menu import build_menu_payload

    text, markup = await build_menu_payload(
        session=session, user=user, state=state
    )
    await query.message.edit_text(text, reply_markup=markup)
    await query.answer()


@router.callback_query(CallbackDataPrefix(HW_EDIT_PENDING))
async def on_preview_edit_request(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    await render_subject_picker(query, bot, session, user, state)


@router.callback_query(CallbackDataPrefix(HW_SAVE))
async def on_create_save(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    await _finalize_creation(query, bot, session, user, state)


@router.callback_query(CallbackDataPrefix(MENU_BACK))
async def on_back_to_menu(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    await state.clear()
    if not isinstance(query.message, Message):
        await query.answer()
        return
    from app.bot.handlers.menu import build_menu_payload

    text, markup = await build_menu_payload(
        session=session, user=user, state=state
    )
    await query.message.edit_text(text, reply_markup=markup)
    await query.answer()
