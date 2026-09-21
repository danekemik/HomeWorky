from datetime import date

from aiogram import Bot, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.calendar import build_calendar_markup
from app.bot.callbacks import (
    HW_ADD_FILES,
    HW_DELETE,
    HW_DELETE_CONFIRM,
    HW_DELETE_FILE,
    HW_DETAIL,
    HW_EDIT,
    HW_EDIT_FIELD,
    MENU_BACK,
    PAGE,
    VIEWS,
)
from app.bot.context import resolve_group, select_current_group
from app.bot.filters.callback import CallbackDataPrefix
from app.bot.formats import (
    bot_today,
    build_homework_card,
    esc,
    format_homework_label,
    safe_int,
)
from app.bot.keyboards.homework import (
    attachment_keyboard,
    back_only_keyboard,
    skip_or_cancel_keyboard,
    subject_picker_keyboard,
)
from app.bot.keyboards.menu import CB_ALL_TASKS, CB_NEAREST_DEADLINES
from app.bot.keyboards.views import (
    PAGE_SIZE,
    homework_delete_confirm_keyboard,
    homework_edit_field_keyboard,
    homework_list_keyboard,
    homeworks_category_keyboard,
)
from app.bot.messages import NO_GROUP_TEXT
from app.bot.render import edit_or_resend
from app.bot.states.homework import HomeworkEditField
from app.database.models import AttachmentType, Homework, User
from app.dates import russian_month_name_short
from app.services.homework_service import (
    AttachmentInfo,
    HomeworkDetail,
    HomeworkLimitError,
    HomeworkService,
)

router = Router(name="views")

_CATEGORY_TITLES = {
    "past": "📜 Прошедшие задания (за неделю)",
    "active": "🔥 Актуальные задания",
    "mine": "👤 Созданные мной",
}

EMPTY_LINE = "  — заданий нет"


def _date_ru(day: date) -> str:
    return f"{day.day} {russian_month_name_short(day.month)}"


def _homework_label(homework: Homework, subject_names: dict[int, str]) -> str:
    subject = subject_names.get(homework.subject_id, "—")
    return format_homework_label(subject, homework.title, homework.deadline)


async def _list_homeworks(
    service: HomeworkService,
    group_id: int,
    category: str,
    author_id: int,
    today: date,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> list[Homework]:
    if category == "past":
        return await service.list_past(group_id, today, limit=limit, offset=offset)
    if category == "mine":
        return await service.list_created_by(
            group_id, author_id, limit=limit, offset=offset
        )
    return await service.list_active(group_id, today, limit=limit, offset=offset)


async def _count_homeworks(
    service: HomeworkService,
    group_id: int,
    category: str,
    author_id: int,
    today: date,
) -> int:
    if category == "past":
        return await service.count_past(group_id, today)
    if category == "mine":
        return await service.count_created_by(group_id, author_id)
    return await service.count_active(group_id, today)


def _detail_payload(
    homework: Homework,
    detail: HomeworkDetail,
    can_modify: bool,
    can_add_files: bool,
    deleteable_attachment_ids: set[int],
) -> tuple[str, InlineKeyboardMarkup]:
    text = build_homework_card(
        subject=detail.subject,
        title=homework.title,
        deadline=homework.deadline,
        description=homework.description,
        author_name=detail.author_name,
        attachment_lines=[
            _attachment_line(item)
            for item in detail.attachments
        ],
        attachment_limit=HomeworkService.MAX_ATTACHMENTS,
        link_lines=[link.title or link.url for link in detail.links],
    )
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    if can_modify:
        builder.button(text="✏️ Изменить", callback_data=f"{HW_EDIT}{homework.id}")
        builder.button(text="🗑 Удалить", callback_data=f"{HW_DELETE}{homework.id}")
    if can_add_files:
        builder.button(
            text="📎 Добавить файлы",
            callback_data=f"{HW_ADD_FILES}{homework.id}",
        )
    for item in detail.attachments:
        if item.id in deleteable_attachment_ids:
            builder.button(
                text=f"🗑 {esc(item.file_name or 'Файл')}",
                callback_data=f"{HW_DELETE_FILE}{homework.id}:{item.id}",
            )
    builder.button(text="🔙 В меню", callback_data=MENU_BACK)
    builder.adjust(1)
    return text, builder.as_markup()


def _attachment_line(item: AttachmentInfo) -> str:
    name = item.file_name or (
        "🖼 Фото" if item.file_type == AttachmentType.PHOTO else "📄 Файл"
    )
    if item.author_name:
        return f"{name} — {item.author_name}"
    return name


async def _deleteable_attachment_ids(
    service: HomeworkService,
    user: User,
    homework: Homework,
    detail: HomeworkDetail,
) -> set[int]:
    if await service.can_modify(user, homework.group_id, homework):
        return {item.id for item in detail.attachments}
    return {
        item.id
        for item in detail.attachments
        if item.author_id == user.id
    }


async def _open_detail(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    user: User,
    service: HomeworkService,
    homework: Homework,
) -> None:
    detail = await service.get_detail(homework)
    can_modify = await service.can_modify(user, homework.group_id, homework)
    can_add_files = await service.is_member(user, homework.group_id)
    deleteables = await _deleteable_attachment_ids(
        service, user, homework, detail
    )
    text, markup = _detail_payload(
        homework,
        detail,
        can_modify,
        can_add_files,
        deleteables,
    )
    attachments = await service.attachments_for(homework)
    if not attachments:
        await edit_or_resend(message, text, markup)
        return
    chat_id = message.chat.id
    try:
        await message.delete()
    except Exception:
        pass
    first, *rest = attachments
    try:
        if first.file_type == AttachmentType.PHOTO:
            await bot.send_photo(
                chat_id,
                first.telegram_file_id,
                caption=text,
                reply_markup=markup,
            )
        else:
            await bot.send_document(
                chat_id,
                first.telegram_file_id,
                caption=text,
                reply_markup=markup,
            )
    except Exception:
        try:
            await message.answer(text, reply_markup=markup)
        except Exception:
            pass
        return
    for item in rest:
        try:
            if item.file_type == AttachmentType.PHOTO:
                await bot.send_photo(chat_id, item.telegram_file_id, caption="🖼 Фото")
            else:
                await bot.send_document(
                    chat_id,
                    item.telegram_file_id,
                    caption=f"📎 {item.file_name or 'Файл'}",
                )
        except Exception:
            pass


async def render_homework_detail(
    *,
    message: Message,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    homework_id: int,
) -> bool:
    group = await resolve_group(bot, session, user, message.chat, state)
    if group is None:
        return False
    service = HomeworkService(session)
    homework = await service.get_for_group(homework_id, group.id)
    if homework is None:
        return False
    detail = await service.get_detail(homework)
    can_modify = await service.can_modify(user, group.id, homework)
    can_add_files = await service.is_member(user, group.id)
    deleteables = await _deleteable_attachment_ids(
        service, user, homework, detail
    )
    text, markup = _detail_payload(
        homework,
        detail,
        can_modify,
        can_add_files,
        deleteables,
    )
    await message.edit_text(text, reply_markup=markup)
    return True


@router.callback_query(CallbackDataPrefix(CB_NEAREST_DEADLINES))
async def on_nearest_deadlines(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not isinstance(query.message, Message):
        await query.answer()
        return
    group = await resolve_group(bot, session, user, query.message.chat, state)
    if group is None:
        await query.answer(NO_GROUP_TEXT, show_alert=True)
        return
    service = HomeworkService(session)
    today = bot_today()
    tomorrow = _tomorrow(today)
    today_items, tomorrow_items = await service.nearest(group.id, today)
    subject_names = await service.subject_names(
        group.id, today_items + tomorrow_items
    )
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    deadline_label = {today: "сегодня", tomorrow: "завтра"}
    lines = [
        "🐹 *Homy открывает календарь и надевает очки*",
        "Так… что у нас тут горит?",
        "",
        "🔥 ДЕДЛАЙНЫ",
        "",
    ]

    def add_block(items: list[Homework], day: date) -> None:
        lines.append(f"📅 {deadline_label[day].capitalize()} ({_date_ru(day)}):")
        if not items:
            lines.append(EMPTY_LINE)
            return
        for index, item in enumerate(items, start=1):
            if index > 1:
                lines.append("")
            subject = subject_names.get(item.subject_id, "—")
            lines.extend([f"{index}. {esc(subject)}", esc(item.title)])
            builder.button(
                text=f"{subject} — {item.title}",
                callback_data=f"{HW_DETAIL}{item.id}",
            )

    add_block(today_items, today)
    lines.append("")
    add_block(tomorrow_items, tomorrow)
    lines += ["", "🐹 *закрывает календарь*"]
    builder.button(text="🔙 В меню", callback_data=MENU_BACK)
    builder.adjust(1)
    await query.message.edit_text("\n".join(lines), reply_markup=builder.as_markup())
    await query.answer()


def _tomorrow(today: date) -> date:
    from datetime import timedelta

    return today + timedelta(days=1)


@router.callback_query(CallbackDataPrefix(CB_ALL_TASKS))
async def on_all_tasks(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not isinstance(query.message, Message):
        await query.answer()
        return
    group = await resolve_group(bot, session, user, query.message.chat, state)
    if group is None:
        await query.answer(NO_GROUP_TEXT, show_alert=True)
        return
    await query.message.edit_text(
        "🐹 *Homy достает стопку тетрадей*\n"
        "Посмотрим, что тут у нас...\n"
        "\n"
        "Выбери категорию:",
        reply_markup=homeworks_category_keyboard(),
    )
    await query.answer()


async def _render_category_list(
    *,
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    category: str,
    page: int,
) -> None:
    if not isinstance(query.message, Message):
        await query.answer()
        return
    group = await resolve_group(bot, session, user, query.message.chat, state)
    if group is None:
        await query.answer(NO_GROUP_TEXT, show_alert=True)
        return
    service = HomeworkService(session)
    today = bot_today()
    total = await _count_homeworks(service, group.id, category, user.id, today)
    items = await _list_homeworks(
        service,
        group.id,
        category,
        user.id,
        today,
        limit=PAGE_SIZE,
        offset=page * PAGE_SIZE,
    )
    subject_names = await service.subject_names(group.id, items)
    rows = [
        (hw.id, _homework_label(hw, subject_names)) for hw in items
    ]
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    title = _CATEGORY_TITLES.get(category, "🗂 Все задания")
    text = f"{title}\n\nСтраница {page + 1} из {total_pages} · всего {total}"
    if not rows:
        text += "\n\n" + EMPTY_LINE
    markup = homework_list_keyboard(
        rows,
        category,
        page,
        has_prev=page > 0,
        has_next=(page + 1) * PAGE_SIZE < total,
    )
    await query.message.edit_text(text, reply_markup=markup)
    await query.answer()


@router.callback_query(CallbackDataPrefix(VIEWS))
async def on_category_view(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not query.data:
        await query.answer()
        return
    category = query.data.split(":", 1)[1]
    if category not in _CATEGORY_TITLES:
        await query.answer()
        return
    await _render_category_list(
        query=query,
        bot=bot,
        session=session,
        user=user,
        state=state,
        category=category,
        page=0,
    )


@router.callback_query(CallbackDataPrefix(PAGE))
async def on_page(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not query.data:
        await query.answer()
        return
    try:
        _, category, index = query.data.split(":")
        page = int(index)
    except (ValueError, IndexError):
        await query.answer()
        return
    if category not in _CATEGORY_TITLES or page < 0:
        await query.answer()
        return
    await _render_category_list(
        query=query,
        bot=bot,
        session=session,
        user=user,
        state=state,
        category=category,
        page=page,
    )


@router.callback_query(CallbackDataPrefix(HW_DETAIL))
async def on_homework_detail(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not query.data or not isinstance(query.message, Message):
        await query.answer()
        return
    homework_id = safe_int(query.data[len(HW_DETAIL):])
    if homework_id is None:
        await query.answer()
        return
    group = await resolve_group(bot, session, user, query.message.chat, state)
    if group is None:
        await query.answer(NO_GROUP_TEXT, show_alert=True)
        return
    service = HomeworkService(session)
    homework = await service.get_for_group(homework_id, group.id)
    if homework is None:
        await query.answer("Задание не найдено.", show_alert=True)
        return
    await state.clear()
    await _open_detail(
        query.message, bot, session, user, service, homework
    )
    await query.answer()


@router.callback_query(CallbackDataPrefix(HW_ADD_FILES))
async def on_add_files(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not query.data or not isinstance(query.message, Message):
        await query.answer()
        return
    homework_id = safe_int(query.data[len(HW_ADD_FILES):])
    if homework_id is None:
        await query.answer()
        return
    group = await resolve_group(bot, session, user, query.message.chat, state)
    if group is None:
        await query.answer(NO_GROUP_TEXT, show_alert=True)
        return
    service = HomeworkService(session)
    homework = await service.get_for_group(homework_id, group.id)
    if homework is None:
        await query.answer("Задание не найдено.", show_alert=True)
        return
    if not await service.is_member(user, group.id):
        await query.answer("Добавлять файлы могут только участники группы.", show_alert=True)
        return
    if await service.attachment_count(homework) >= HomeworkService.MAX_ATTACHMENTS:
        await query.answer(
            f"Лимит — {HomeworkService.MAX_ATTACHMENTS} файла на задание.",
            show_alert=True,
        )
        return
    await state.set_state(HomeworkEditField.attachment)
    select_current_group(user, group.id)
    await state.update_data(
        add_only=True,
        homework_id=homework_id,
        current_group_id=group.id,
        attachments=[],
        links=[],
    )
    from app.bot.handlers.homework import ATTACH_PENDING

    await edit_or_resend(
        query.message,
        ATTACH_PENDING,
        markup=attachment_keyboard(False),
    )
    await query.answer()


@router.callback_query(CallbackDataPrefix(HW_DELETE_FILE))
async def on_delete_file(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not query.data or not isinstance(query.message, Message):
        await query.answer()
        return
    payload = query.data[len(HW_DELETE_FILE):]
    homework_raw, _, attachment_raw = payload.partition(":")
    if not homework_raw or not attachment_raw:
        await query.answer()
        return
    try:
        homework_id, attachment_id = int(homework_raw), int(attachment_raw)
    except ValueError:
        await query.answer()
        return
    group = await resolve_group(bot, session, user, query.message.chat, state)
    if group is None:
        await query.answer(NO_GROUP_TEXT, show_alert=True)
        return
    service = HomeworkService(session)
    homework = await service.get_for_group(homework_id, group.id)
    if homework is None:
        await query.answer("Задание не найдено.", show_alert=True)
        return
    attachments = await service.attachments_for(homework)
    attachment = next(
        (item for item in attachments if item.id == attachment_id), None
    )
    if attachment is None:
        await query.answer("Файл не найден.", show_alert=True)
        return
    if not await service.can_delete_attachment(
        user, group.id, homework, attachment
    ):
        await query.answer(
            "Удалить этот файл может его автор, автор задания или староста.",
            show_alert=True,
        )
        return
    await service.delete_attachment(homework, attachment_id)
    await _open_detail(query.message, bot, session, user, service, homework)
    await query.answer("Файл удалён.")


@router.callback_query(CallbackDataPrefix(HW_EDIT))
async def on_edit_homework(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not query.data or not isinstance(query.message, Message):
        await query.answer()
        return
    homework_id = safe_int(query.data[len(HW_EDIT):])
    if homework_id is None:
        await query.answer()
        return
    group = await resolve_group(
        bot, session, user, query.message.chat, state
    )
    if group is None:
        await query.answer(NO_GROUP_TEXT, show_alert=True)
        return
    service = HomeworkService(session)
    homework = await service.get_for_group(homework_id, group.id)
    if homework is None:
        await query.answer("Задание не найдено.", show_alert=True)
        return
    if not await service.can_modify(user, group.id, homework):
        await query.answer(
            "Изменить можно только своё задание или как модератор.",
            show_alert=True,
        )
        return
    await state.set_state(HomeworkEditField.field)
    select_current_group(user, group.id)
    await state.update_data(homework_id=homework_id, current_group_id=group.id)
    await edit_or_resend(
        query.message,
        "✏️ Что изменить?",
        markup=homework_edit_field_keyboard(homework_id),
    )
    await query.answer()


@router.callback_query(
    StateFilter(HomeworkEditField.field), CallbackDataPrefix(HW_EDIT_FIELD)
)
async def on_edit_field(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not query.data or not isinstance(query.message, Message):
        await query.answer()
        return
    field = query.data[len(HW_EDIT_FIELD):]
    data = await state.get_data()
    homework_id = data.get("homework_id")
    group = await resolve_group(bot, session, user, query.message.chat, state)
    if group is None or homework_id is None:
        await query.answer(NO_GROUP_TEXT, show_alert=True)
        return
    prompts = {
        "title": ("✏️ Введи новое название задания:", HomeworkEditField.title),
        "description": (
            "📝 Введи новое описание (или «⏭ Пропустить», чтобы очистить):",
            HomeworkEditField.description,
        ),
        "deadline": ("📅 Выбери новую дату сдачи:", HomeworkEditField.deadline),
        "attachment": ("📎 Добавь новые файлы или ссылки:", HomeworkEditField.attachment),
    }
    if field == "subject":
        subjects = await HomeworkService(session).list_subjects(group.id)
        await query.message.edit_text(
            "📚 Новый предмет:", reply_markup=subject_picker_keyboard(subjects)
        )
        await query.answer()
        return
    if field not in prompts:
        await query.answer()
        return
    prompt, next_state = prompts[field]
    await state.set_state(next_state)
    if field == "deadline":
        await query.message.edit_text(
            prompt, reply_markup=build_calendar_markup(bot_today())
        )
    elif field == "attachment":
        await query.message.edit_text(
            prompt, reply_markup=attachment_keyboard(False)
        )
    elif field == "description":
        await query.message.edit_text(
            prompt, reply_markup=skip_or_cancel_keyboard()
        )
    else:
        await query.message.edit_text(prompt, reply_markup=back_only_keyboard())
    await query.answer()


async def _apply_text_field(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    field: str,
    value: str | None,
) -> None:
    data = await state.get_data()
    homework_id = data.get("homework_id")
    group = await resolve_group(bot, session, user, message.chat, state)
    if group is None or homework_id is None:
        await state.clear()
        await message.answer(NO_GROUP_TEXT)
        return
    service = HomeworkService(session)
    homework = await service.get_for_group(int(homework_id), group.id)
    if homework is None or not await service.can_modify(user, group.id, homework):
        await state.clear()
        await message.answer("Доступ запрещён или задание не найдено.")
        return
    if field == "title":
        value = (value or "").strip()
        if not value:
            await message.answer("Название не может быть пустым.")
            return
        if len(value) > 255:
            await message.answer("Название слишком длинное (максимум 255 символов).")
            return
        await service.update_homework(homework, title=value)
    elif field == "description":
        value = (value or "").strip() or None
        if value is not None and len(value) > 4000:
            await message.answer("Описание слишком длинное (максимум 4000 символов).")
            return
        await service.update_homework(homework, description=value)
    await state.clear()
    detail = await service.get_detail(homework)
    deleteables = {item.id for item in detail.attachments}
    text, markup = _detail_payload(
        homework, detail, True, True, deleteables
    )
    await message.answer(text, reply_markup=markup)


@router.message(StateFilter(HomeworkEditField.title))
async def on_edit_title(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("Название не может быть пустым.")
        return
    await _apply_text_field(
        message, bot, session, user, state, "title", title
    )


@router.message(StateFilter(HomeworkEditField.description))
async def on_edit_description(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    await _apply_text_field(
        message,
        bot,
        session,
        user,
        state,
        "description",
        (message.text or "").strip() or None,
    )


async def _finish_edit(
    message: Message,
    service: HomeworkService,
    homework: Homework,
    user: User,
) -> None:
    detail = await service.get_detail(homework)
    can_modify = await service.can_modify(
        user, homework.group_id, homework
    )
    can_add_files = await service.is_member(user, homework.group_id)
    deleteables = await _deleteable_attachment_ids(
        service, user, homework, detail
    )
    text, markup = _detail_payload(
        homework,
        detail,
        can_modify,
        can_add_files,
        deleteables,
    )
    await message.edit_text(text, reply_markup=markup)


async def apply_edit_field(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    """Применение поля из callback-контекста (пропуск описания)."""
    if not isinstance(query.message, Message):
        await state.clear()
        await query.answer()
        return
    data = await state.get_data()
    homework_id = data.get("homework_id")
    group = await resolve_group(bot, session, user, query.message.chat, state)
    if group is None or homework_id is None:
        await state.clear()
        await query.answer(NO_GROUP_TEXT, show_alert=True)
        return
    service = HomeworkService(session)
    homework = await service.get_for_group(int(homework_id), group.id)
    if homework is None or not await service.can_modify(user, group.id, homework):
        await state.clear()
        await query.answer("Доступ запрещён.", show_alert=True)
        return
    state_name = await state.get_state()
    if state_name == HomeworkEditField.description.state:
        homework.description = None
    await session.flush()
    await state.clear()
    await _finish_edit(query.message, service, homework, user)
    await query.answer()


async def finalize_edit_attachments(
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
    homework_id = data.get("homework_id")
    group = await resolve_group(bot, session, user, query.message.chat, state)
    if group is None or homework_id is None:
        await state.clear()
        await query.answer(NO_GROUP_TEXT, show_alert=True)
        return
    service = HomeworkService(session)
    homework = await service.get_for_group(int(homework_id), group.id)
    if homework is None or not await service.is_member(user, group.id):
        await state.clear()
        await query.answer("Доступ запрещён.", show_alert=True)
        return
    can_modify = await service.can_modify(user, group.id, homework)
    if not can_modify and not data.get("add_only"):
        await state.clear()
        await query.answer(
            "Изменять задание может только его автор или староста.",
            show_alert=True,
        )
        return
    if data.get("deadline") and can_modify:
        homework.deadline = date.fromisoformat(str(data["deadline"]))
    try:
        await service.attach_pending(
            homework,
            attachments=list(data.get("attachments", [])),  # type: ignore[arg-type]
            links=list(data.get("links", [])),  # type: ignore[arg-type]
            author_id=user.id,
        )
    except HomeworkLimitError:
        await query.answer(
            f"Лимит — {HomeworkService.MAX_ATTACHMENTS} файла на задание.",
            show_alert=True,
        )
        return
    await session.flush()
    await state.clear()
    await _finish_edit(query.message, service, homework, user)
    await query.answer()


@router.callback_query(CallbackDataPrefix(HW_DELETE))
async def on_delete_homework(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not query.data or not isinstance(query.message, Message):
        await query.answer()
        return
    homework_id = safe_int(query.data[len(HW_DELETE):])
    if homework_id is None:
        await query.answer()
        return
    group = await resolve_group(bot, session, user, query.message.chat, state)
    if group is None:
        await query.answer(NO_GROUP_TEXT, show_alert=True)
        return
    service = HomeworkService(session)
    homework = await service.get_for_group(homework_id, group.id)
    if homework is None:
        await query.answer("Задание не найдено.", show_alert=True)
        return
    text = (
        "🗑 Удалить задание?\n\n"
        f"💻 {esc(homework.title)}\n"
        f"📅 Дедлайн: {_date_ru(homework.deadline)}"
    )
    await edit_or_resend(
        query.message,
        text,
        markup=homework_delete_confirm_keyboard(homework_id),
    )
    await query.answer()


@router.callback_query(CallbackDataPrefix(HW_DELETE_CONFIRM))
async def on_delete_confirm(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not query.data or not isinstance(query.message, Message):
        await query.answer()
        return
    homework_id = safe_int(query.data[len(HW_DELETE_CONFIRM):])
    if homework_id is None:
        await query.answer()
        return
    group = await resolve_group(bot, session, user, query.message.chat, state)
    if group is None:
        await query.answer(NO_GROUP_TEXT, show_alert=True)
        return
    service = HomeworkService(session)
    homework = await service.get_for_group(homework_id, group.id)
    if homework is None:
        await query.answer("Задание не найдено.", show_alert=True)
        return
    if not await service.can_modify(user, group.id, homework):
        await query.answer(
            "Удалить можно только своё задание или как модератор.",
            show_alert=True,
        )
        return
    await service.delete_homework(homework)
    await edit_or_resend(
        query.message, "✅ Задание удалено. Нажми /menu для возврата."
    )
    await query.answer()
