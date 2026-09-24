from datetime import date

from aiogram import Bot, Router
from aiogram.enums import MessageEntityType
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.calendar import build_calendar_markup
from app.bot.callbacks import (
    ATTACH_DONE,
    ATTACH_SKIP,
    CALENDAR,
    FLOW_CANCEL,
    HW_EDIT_PENDING,
    HW_SAVE,
    MENU_BACK,
    PENDING_EDIT_DONE,
    PENDING_FIELD,
    SKIP,
    SUBJECT_PICK,
)
from app.bot.context import resolve_group, select_current_group
from app.bot.filters.callback import CallbackDataPrefix
from app.bot.formats import (
    bot_today,
    esc,
    format_date_russian,
)
from app.bot.keyboards.homework import (
    attachment_keyboard,
    back_only_keyboard,
    pending_edit_fields_keyboard,
    preview_keyboard,
    skip_or_cancel_keyboard,
    subject_picker_keyboard,
)
from app.bot.keyboards.menu import CB_ADD_HOMEWORK, main_menu_keyboard
from app.bot.keyboards.views import homework_edit_field_keyboard
from app.bot.messages import NO_GROUP_TEXT
from app.bot.states.group_flow import GroupFlow, SettingsFlow
from app.bot.states.homework import HomeworkCreation, HomeworkEditField
from app.database.models import AttachmentType, Homework, User
from app.database.repositories.subject_repository import SubjectRepository
from app.services.group_service import GroupService
from app.services.homework_service import (
    HomeworkDetail,
    HomeworkExistsError,
    HomeworkLimitError,
    HomeworkService,
)

router = Router(name="homework")


@router.callback_query(CallbackDataPrefix(CB_ADD_HOMEWORK))
async def on_add_homework(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    await render_subject_picker(query, bot, session, user, state)
SUBJECT_PENDING = (
    "🐹 *Homy листает блокнот*\n"
    "\n"
    "Нашёл список предметов.\n"
    "\n"
    "По какому сегодня работаем? 👀"
)
TITLE_PENDING = (
    "📝 НОВОЕ ДЗ\n"
    "\n"
    "🐹 *берёт ручку*\n"
    "\n"
    "Так, что нам сегодня задали?"
)
DESCRIPTION_PENDING = (
    "🐹 *Homy уже что-то записал*\n"
    "\n"
    "Название есть. 👍\n"
    "\n"
    "А преподаватель оставил\n"
    "какие-нибудь дополнительные условия?"
)
DEADLINE_PENDING = "📅 Укажи дату сдачи:"
ATTACH_PENDING = (
    "🐹 *Homy освобождает место на столе*\n"
    "\n"
    "Так, теперь материалы.\n"
    "\n"
    "Есть файл, фото, ссылка?\n"
    "Кидай сюда 📎"
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
    select_current_group(user, group.id)
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
    subject = str(data.get("subject_name") or data.get("subject_id") or "—").upper()
    deadline = date.fromisoformat(str(data["deadline"]))
    lines = [
        "🐹 *Homy раскладывает бумаги на столе*",
        "",
        f"📚 {esc(subject)}",
        f"📝 {esc(str(data['title']))}",
    ]
    description = data.get("description")
    if description:
        lines.append(f"🗒 {esc(str(description))}")
    lines.append(f"📅 {format_date_russian(deadline)}")
    for item in data.get("attachments", []):  # type: ignore[arg-type]
        if str(item.get("file_type")) == AttachmentType.PHOTO.value:
            lines.append("🖼 Фото")
        else:
            lines.append("📎 Файл")
    lines += ["", "Всё сходится.", "Сохраняем?"]
    return "\n".join(lines)


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


@router.callback_query(
    StateFilter(HomeworkCreation.subject, HomeworkEditField.field),
    CallbackDataPrefix(SUBJECT_PICK),
)
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
        text = (
            "🐹 *Homy переворачивает страницу*\n"
            "\n"
            "Кажется, такого предмета\n"
            "у меня ещё нет.\n"
            "\n"
            "🐹 *готовится записывать*\n"
            "\n"
            "Как его назовём?"
        )
        new_state = (
            HomeworkCreation.new_subject
            if _is_base_creation(state_name)
            else HomeworkEditField.new_subject
        )
        await state.set_state(new_state)
        await message.edit_text(text, reply_markup=back_only_keyboard())
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
    select_current_group(user, group.id)
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
        from app.bot.handlers.views import _finish_edit

        await state.clear()
        await _finish_edit(message, bot, session, service, homework, user)
        await query.answer()
        return

    subject = await service.get_subject(subject_id)
    await state.update_data(
        subject_id=subject_id,
        subject_name=subject.name if subject is not None else None,
    )
    if (await state.get_data()).get("from_fields"):
        await _render_preview_message(message, state)
        await query.answer()
        return
    await state.set_state(HomeworkCreation.deadline)
    await message.edit_text(
        DEADLINE_PENDING, reply_markup=build_calendar_markup(bot_today())
    )
    await query.answer()


async def _apply_new_subject(
    *,
    text: str,
    group_id: int,
    session: AsyncSession,
) -> int:
    service = HomeworkService(session)
    name = text.strip()
    if len(name) > 128:
        raise ValueError("Название предмета слишком длинное (максимум 128 символов).")
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
    try:
        subject_id = await _apply_new_subject(
            text=name, group_id=group.id, session=session
        )
    except ValueError as exc:
        await message.answer(str(exc))
        return
    subject = await service.get_subject(subject_id)
    select_current_group(user, group.id)
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
        from app.bot.handlers.views import _send_edited_detail

        await _send_edited_detail(message, bot, session, user, service, homework)
    elif (await state.get_data()).get("from_fields"):
        await _render_preview_message(message, state, answer=True)
    else:
        await state.set_state(HomeworkCreation.deadline)
        await message.answer(
            DEADLINE_PENDING, reply_markup=build_calendar_markup(bot_today())
        )


@router.message(StateFilter(HomeworkCreation.title))
async def on_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("Название не может быть пустым.")
        return
    if len(title) > 255:
        await message.answer("Название слишком длинное (максимум 255 символов).")
        return
    await state.update_data(title=title)
    if (await state.get_data()).get("from_fields"):
        await _render_preview_message(message, state, answer=True)
        return
    await state.set_state(HomeworkCreation.description)
    await message.answer(DESCRIPTION_PENDING, reply_markup=skip_or_cancel_keyboard())


@router.message(StateFilter(HomeworkCreation.description))
async def on_description(message: Message, state: FSMContext) -> None:
    description = (message.text or "").strip() or None
    if description is not None and len(description) > 4000:
        await message.answer("Описание слишком длинное (максимум 4000 символов).")
        return
    await state.update_data(description=description)
    if (await state.get_data()).get("from_fields"):
        await _render_preview_message(message, state, answer=True)
        return
    await state.set_state(HomeworkCreation.attachment)
    await message.answer(ATTACH_PENDING, reply_markup=attachment_keyboard(False))


@router.callback_query(
    StateFilter(HomeworkCreation.deadline, HomeworkEditField.deadline),
    CallbackDataPrefix(CALENDAR),
)
async def on_calendar(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
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
            year, month = map(int, payload[4:].split("-"))
            if not (1 <= month <= 12) or not (1 <= year <= 9999):
                raise ValueError
            cursor = date(year, month, 1)
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
    if chosen < bot_today():
        await query.answer(
            "Дата сдачи не может быть в прошлом.", show_alert=True
        )
        return

    if _is_base_edit(state_name):
        data = await state.get_data()
        homework_id = data.get("homework_id")
        service = HomeworkService(session)
        group = await resolve_group(
            bot, session, user, query.message.chat, state
        )
        if group is None or homework_id is None:
            await state.clear()
            await query.answer(NO_GROUP_TEXT, show_alert=True)
            return
        homework = await service.get_for_group(
            int(homework_id), group.id
        )
        if homework is None:
            await state.clear()
            await query.answer("Задание не найдено.", show_alert=True)
            return
        if not await service.can_modify(user, group.id, homework):
            await state.clear()
            await query.answer(
                "Только автор или модератор может менять.", show_alert=True
            )
            return
        homework.deadline = chosen
        await session.flush()
        await state.clear()
        from app.bot.handlers.views import _finish_edit

        await _finish_edit(query.message, bot, session, service, homework, user)
        await query.answer()
        return

    await state.update_data(deadline=chosen.isoformat())
    if (await state.get_data()).get("from_fields"):
        await _render_preview_message(query.message, state)
        await query.answer()
        return
    if not _is_base_edit(state_name):
        data = await state.get_data()
        subject_id = data.get("subject_id")
        homework_id = data.get("homework_id")
        if subject_id and not homework_id:
            service = HomeworkService(session)
            group = await resolve_group(
                bot, session, user, query.message.chat, state
            )
            if group is not None:
                existing = await service.find_by_subject_and_date(
                    group.id, int(subject_id), chosen
                )
                if existing is not None:
                    await _render_existing_homework(
                        query.message, session, user, group.id, existing
                    )
                    await state.clear()
                    await query.answer()
                    return
    await state.set_state(HomeworkCreation.title)
    await query.message.edit_text(TITLE_PENDING, reply_markup=back_only_keyboard())
    await query.answer()


async def _render_existing_homework(
    message: Message,
    session: AsyncSession,
    user: User,
    group_id: int,
    existing: Homework,
) -> None:
    service = HomeworkService(session)
    detail = await service.get_detail(existing)
    from app.bot.handlers.views import _detail_payload

    can_modify = await service.can_modify(user, group_id, existing)
    can_add_files = await service.is_member(user, group_id)
    deleteables = {
        item.id
        for item in detail.attachments
        if item.author_id == user.id
    }
    text, markup = _detail_payload(
        existing, detail, can_modify, can_add_files, deleteables
    )
    await message.edit_text(
        "⚠️ На этот предмет и дату уже есть задание!\n\n" + text,
        reply_markup=markup,
    )


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


def _extract_link(message: Message) -> str | None:
    """Возвращает первый URL из текста сообщения (по entity или по regex-хвосту)."""
    if not message.entities:
        return None
    for entity in message.entities:
        if entity.type == MessageEntityType.URL:
            start, end = entity.offset, entity.offset + entity.length
            url = (message.text or "")[start:end].strip()
            if url and "://" in url:
                return url
        if entity.type == MessageEntityType.TEXT_LINK and entity.url:
            return entity.url
    return None


@router.message(StateFilter(HomeworkCreation.attachment, HomeworkEditField.attachment))
async def on_attachment_message(
    message: Message, bot: Bot, session: AsyncSession, user: User, state: FSMContext
) -> None:
    data = dict(await state.get_data())
    if message.text:
        url = _extract_link(message)
        if url is None:
            await message.answer(
                "Сюда можно добавить файл 📄, фото 🖼 или ссылку 🔗 "
                "(скопируй URL и отправь как текст)."
            )
            return
        homework_id = data.get("homework_id")
        if homework_id is not None:
            homework = await session.get(Homework, int(homework_id))
            if homework is None:
                await message.answer("Задание не найдено. Нажми «✅ Готово».")
                return
            existing_links = await HomeworkService(session).link_count(homework)
        else:
            existing_links = 0
        pending_links = len(data.get("links", []))
        if existing_links + pending_links >= HomeworkService.MAX_LINKS:
            await message.answer(
                f"Лимит — {HomeworkService.MAX_LINKS} ссылки на задание. "
                "Можно добавить файлы или нажми «✅ Готово»."
            )
            return
        data.setdefault("links", []).append({"url": url, "title": None})
        await state.update_data(**data)
        await message.answer(
            f"➕ Добавлена ссылка: 🔗 {esc(url)}\n"
            "Можно добавить ещё или «✅ Готово».",
            reply_markup=attachment_keyboard(True),
        )
        return
    attachment = _collect_attachment(message)
    if attachment is None:
        await message.answer(
            "Пришли файл 📄, фото 🖼, ссылку 🔗 или нажми «✅ Готово»."
        )
        return
    pending = len(data.get("attachments", []))
    if data.get("homework_id"):
        homework = await session.get(Homework, int(data["homework_id"]))
        if homework is None:
            await message.answer("Задание не найдено. Нажми «✅ Готово».")
            return
        existing = await HomeworkService(session).attachment_count(homework)
    else:
        existing = 0
    if existing + pending >= HomeworkService.MAX_ATTACHMENTS:
        await message.answer(
            f"Лимит — {HomeworkService.MAX_ATTACHMENTS} файла на задание. "
            "Удалив лишнее, сможешь добавить новое."
        )
        return
    data.setdefault("attachments", []).append(attachment)
    await state.update_data(**data)
    files = sum(
        str(item.get("file_type")) != AttachmentType.PHOTO.value
        for item in data["attachments"]
    )
    photos = len(data["attachments"]) - files
    await message.answer(
        f"➕ Добавлено: 📄 файл ×{files}, 🖼 фото ×{photos}. "
        "Можно добавить ещё или «✅ Готово».",
        reply_markup=attachment_keyboard(True),
    )


def _created_confirmation_card(detail: HomeworkDetail, homework: Homework) -> str:
    lines = [
        "🐹 *Homy ставит жирную галочку в блокноте*",
        "",
        "✓ ЗАПИСАНО",
        f"📚 {esc(detail.subject.capitalize())}",
        f"📝 {esc(homework.title)}",
        f"📅 {format_date_russian(homework.deadline)}",
    ]
    for item in detail.attachments:
        if item.file_type == AttachmentType.PHOTO:
            lines.append("🖼 Фото")
        else:
            lines.append("📎 Файл")
    for link in detail.links:
        lines.append(f"🔗 {esc(link.title or link.url)}")
    lines += [
        "",
        "🐹 *довольно закрывает блокнот*",
        "",
        "Теперь я прослежу,\nчтобы ты не забыл 😎",
    ]
    return "\n".join(lines)


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
    try:
        homework = await service.create_homework(
            group_id=group.id,
            subject_id=int(data["subject_id"]),
            author_id=user.id,
            title=title,
            deadline=deadline,
            description=data.get("description") and str(data["description"]),
        )
    except HomeworkExistsError:
        existing = await service.find_by_subject_and_date(
            group.id, int(data["subject_id"]), deadline
        )
        await state.clear()
        if existing is None:
            await query.answer(
                "Задание не создано. Попробуй ещё раз.", show_alert=True
            )
            return
        await _render_existing_homework(
            query.message, session, user, group.id, existing
        )
        await query.answer("Задание не создано — оно уже есть.")
        return
    try:
        await service.attach_pending(
            homework,
            attachments=list(data.get("attachments", [])),  # type: ignore[arg-type]
            links=list(data.get("links", [])),  # type: ignore[arg-type]
            author_id=user.id,
        )
    except HomeworkLimitError:
        await service.delete_homework(homework)
        await state.clear()
        await query.answer(
            f"Лимит — {HomeworkService.MAX_ATTACHMENTS} файла на задание.",
            show_alert=True,
        )
        return
    await state.clear()
    detail = await service.get_detail(homework)
    text = _created_confirmation_card(detail, homework)
    await query.message.edit_text(text, reply_markup=main_menu_keyboard())
    await query.answer("Задание создано ✅", show_alert=False)


async def _render_preview_message(
    message: Message, state: FSMContext, *, answer: bool = False
) -> None:
    data = await state.get_data()
    await state.set_state(HomeworkCreation.attachment)
    await state.update_data(preview=True, fields=False, from_fields=False)
    text = _pending_preview_card(data)
    markup = preview_keyboard()
    if answer:
        await message.answer(text, reply_markup=markup)
    else:
        await message.edit_text(text, reply_markup=markup)


async def _show_pending_fields(message: Message, state: FSMContext) -> None:
    await state.set_state(HomeworkCreation.attachment)
    await state.update_data(preview=False, fields=True, from_fields=True)
    await message.edit_text(
        "✏️ Что изменить?", reply_markup=pending_edit_fields_keyboard()
    )


async def _show_preview(query: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(query.message, Message):
        await query.answer()
        return
    await _render_preview_message(query.message, state)
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
        if (await state.get_data()).get("from_fields"):
            await _render_preview_message(query.message, state)
            await query.answer()
            return
        await state.set_state(HomeworkCreation.attachment)
        await query.message.edit_text(
            ATTACH_PENDING, reply_markup=attachment_keyboard(False)
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


async def _back_to_menu(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    await state.clear()
    from app.bot.handlers.menu import build_menu_payload

    text, markup = await build_menu_payload(
        session=session, user=user, state=state
    )
    from app.bot.render import edit_or_resend

    await edit_or_resend(message, text, markup)


@router.callback_query(CallbackDataPrefix(FLOW_CANCEL))
async def on_flow_cancel(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not isinstance(query.message, Message):
        await query.answer()
        return
    message = query.message
    state_name = await state.get_state()
    if state_name is None:
        await _back_to_menu(message, bot, session, user, state)
        await query.answer()
        return

    if state_name == GroupFlow.join_code.state:
        from app.bot.handlers.menu import render_join_picker

        await render_join_picker(query, session, user)
        return
    if state_name == GroupFlow.join_name.state:
        await _back_to_menu(message, bot, session, user, state)
        await query.answer()
        return
    if state_name == GroupFlow.create_name.state:
        await _back_to_menu(message, bot, session, user, state)
        await query.answer()
        return
    if state_name == SettingsFlow.change_name.state:
        from app.bot.handlers.settings import SETTINGS_TEXT, settings_keyboard

        admin_groups = await GroupService(session).admin_groups(user)
        await message.edit_text(
            SETTINGS_TEXT,
            reply_markup=settings_keyboard(has_admin_groups=bool(admin_groups)),
        )
        await state.clear()
        await query.answer()
        return
    if state_name == SettingsFlow.rename_group.state:
        from app.bot.handlers.settings import render_management

        data = await state.get_data()
        group_id = data.get("rename_group_id")
        await state.clear()
        if group_id is not None:
            await render_management(query, session, user, int(group_id))
            return
        await _back_to_menu(message, bot, session, user, state)
        await query.answer()
        return
    if state_name == SettingsFlow.rename_subject.state:
        from app.bot.handlers.settings import render_subjects

        data = await state.get_data()
        subject_id = data.get("rename_subject_id")
        await state.clear()
        subject = (
            await SubjectRepository(session).get(subject_id)
            if subject_id is not None
            else None
        )
        if subject is not None:
            await render_subjects(query, session, user, subject.group_id)
            return
        await _back_to_menu(message, bot, session, user, state)
        await query.answer()
        return

    if _is_base_creation(state_name):
        data = await state.get_data()
        if state_name == HomeworkCreation.new_subject.state:
            await render_subject_picker(query, bot, session, user, state)
            return
        if data.get("fields"):
            await _render_preview_message(message, state)
            await query.answer()
            return
        if data.get("from_fields"):
            await _show_pending_fields(message, state)
            await query.answer()
            return
        if state_name == HomeworkCreation.subject.state:
            await _back_to_menu(message, bot, session, user, state)
            await query.answer()
            return
        if state_name == HomeworkCreation.title.state:
            deadline = data.get("deadline")
            cursor = (
                date.fromisoformat(str(deadline))
                if deadline
                else bot_today()
            )
            await state.set_state(HomeworkCreation.deadline)
            await message.edit_text(
                DEADLINE_PENDING, reply_markup=build_calendar_markup(cursor)
            )
        elif state_name == HomeworkCreation.description.state:
            await state.set_state(HomeworkCreation.title)
            await message.edit_text(TITLE_PENDING, reply_markup=back_only_keyboard())
        elif state_name == HomeworkCreation.deadline.state:
            await render_subject_picker(query, bot, session, user, state)
        elif state_name == HomeworkCreation.attachment.state:
            if data.get("preview"):
                await state.update_data(preview=False)
                has = bool(data.get("attachments") or data.get("links"))
                await message.edit_text(
                    ATTACH_PENDING, reply_markup=attachment_keyboard(has)
                )
            else:
                await state.set_state(HomeworkCreation.description)
                await message.edit_text(
                    DESCRIPTION_PENDING, reply_markup=skip_or_cancel_keyboard()
                )
        await query.answer()
        return

    if state_name.startswith(HomeworkEditField.__name__):
        data = await state.get_data()
        homework_id = data.get("homework_id")
        if homework_id is None:
            await _back_to_menu(message, bot, session, user, state)
            await query.answer()
            return
        if data.get("add_only"):
            from app.bot.handlers.views import _open_folder_after_changes

            service = HomeworkService(session)
            group = await resolve_group(
                bot, session, user, query.message.chat, state
            )
            homework = (
                await service.get_for_group(int(homework_id), group.id)
                if group is not None
                else None
            )
            if homework is not None:
                await state.clear()
                await _open_folder_after_changes(
                    message, bot, session, user, service, homework
                )
                await query.answer()
                return
        await state.set_state(HomeworkEditField.field)
        await message.edit_text(
            "✏️ Что изменить?",
            reply_markup=homework_edit_field_keyboard(int(homework_id)),
        )
        await query.answer()
        return

    await _back_to_menu(message, bot, session, user, state)
    await query.answer()


@router.callback_query(CallbackDataPrefix(HW_EDIT_PENDING))
async def on_preview_edit_request(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not isinstance(query.message, Message):
        await query.answer()
        return
    await state.update_data(preview=False, fields=True, from_fields=True)
    await query.message.edit_text(
        "✏️ Что изменить?", reply_markup=pending_edit_fields_keyboard()
    )
    await query.answer()


@router.callback_query(CallbackDataPrefix(PENDING_EDIT_DONE))
async def on_pending_edit_done(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not isinstance(query.message, Message):
        await query.answer()
        return
    await _render_preview_message(query.message, state)
    await query.answer()


@router.callback_query(
    CallbackDataPrefix(PENDING_FIELD),
    StateFilter(HomeworkCreation.attachment, HomeworkEditField.field),
)
async def on_pending_field_pick(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not query.data or not isinstance(query.message, Message):
        await query.answer()
        return
    data = dict(await state.get_data())
    field = query.data[len(PENDING_FIELD):]
    if field == "subject":
        await state.update_data(fields=False)
        await render_subject_picker(query, bot, session, user, state)
        return
    if field == "title":
        await state.update_data(fields=False)
        await state.set_state(HomeworkCreation.title)
        await query.message.edit_text(TITLE_PENDING, reply_markup=back_only_keyboard())
    elif field == "description":
        await state.update_data(fields=False)
        await state.set_state(HomeworkCreation.description)
        await query.message.edit_text(
            DESCRIPTION_PENDING, reply_markup=skip_or_cancel_keyboard()
        )
    elif field == "deadline":
        await state.update_data(fields=False)
        await state.set_state(HomeworkCreation.deadline)
        await query.message.edit_text(
            DEADLINE_PENDING, reply_markup=build_calendar_markup(bot_today())
        )
    elif field == "attachment":
        await state.update_data(fields=False)
        has = bool(data.get("attachments") or data.get("links"))
        await state.set_state(HomeworkCreation.attachment)
        await query.message.edit_text(
            ATTACH_PENDING, reply_markup=attachment_keyboard(has)
        )
    await query.answer()


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
    await _back_to_menu(query.message, bot, session, user, state)
    await query.answer()
