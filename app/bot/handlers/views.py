from datetime import date

from aiogram import Bot, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.calendar import build_calendar_markup
from app.bot.callbacks import (
    FILE_SEND,
    HW_DELETE,
    HW_DELETE_CONFIRM,
    HW_DETAIL,
    HW_EDIT,
    HW_EDIT_FIELD,
    MENU_BACK,
    PAGE,
    VIEWS,
)
from app.bot.context import resolve_group, select_current_group
from app.bot.filters.callback import CallbackDataPrefix
from app.bot.formats import bot_today, build_homework_card, esc, format_homework_label
from app.bot.handlers.homework import NO_GROUP_TEXT
from app.bot.keyboards.homework import attachment_keyboard, subject_picker_keyboard
from app.bot.keyboards.menu import CB_ALL_TASKS, CB_NEAREST_DEADLINES
from app.bot.keyboards.views import (
    PAGE_SIZE,
    homework_delete_confirm_keyboard,
    homework_edit_field_keyboard,
    homework_list_keyboard,
    homeworks_category_keyboard,
)
from app.bot.states.homework import HomeworkEditField
from app.database.models import AttachmentType, Homework, User
from app.services.homework_service import HomeworkDetail, HomeworkService

router = Router(name="views")

_MONTHS_RU = (
    "янв.",
    "февр.",
    "марта",
    "апр.",
    "мая",
    "июня",
    "июля",
    "авг.",
    "сент.",
    "окт.",
    "нояб.",
    "дек.",
)

_CATEGORY_TITLES = {
    "past": "📜 Прошедшие задания (2 недели)",
    "active": "🔥 Актуальные задания",
    "mine": "👤 Созданные мной",
}

EMPTY_LINE = "  — заданий нет"


def _date_ru(day: date) -> str:
    return f"{day.day} {_MONTHS_RU[day.month - 1]}"


def _homework_label(homework: Homework, subject_names: dict[int, str]) -> str:
    subject = subject_names.get(homework.subject_id, "—")
    return format_homework_label(subject, homework.title, homework.deadline)


async def _list_homeworks(
    service: HomeworkService,
    group_id: int,
    category: str,
    author_id: int,
    today: date,
) -> list[Homework]:
    if category == "past":
        return await service.list_past(group_id, today)
    if category == "mine":
        return await service.list_created_by(group_id, author_id)
    return await service.list_active(group_id, today)


def _detail_payload(
    homework: Homework, detail: HomeworkDetail, can_modify: bool
) -> tuple[str, InlineKeyboardMarkup]:
    text = build_homework_card(
        subject=detail.subject,
        title=homework.title,
        deadline=homework.deadline,
        description=homework.description,
        author_name=detail.author_name,
        attachment_lines=[
            item.file_name
            or ("🖼 Фото" if item.file_type == AttachmentType.PHOTO else "📄 Файл")
            for item in detail.attachments
        ],
        link_lines=[link.title or link.url for link in detail.links],
    )
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    for attachment in detail.attachments:
        is_photo = attachment.file_type == AttachmentType.PHOTO
        label = attachment.file_name or ("🖼 Фото" if is_photo else "📄 Файл")
        builder.button(text=f"⬇️ {label}", callback_data=f"{FILE_SEND}{homework.id}:{attachment.id}")
    if can_modify:
        builder.button(text="✏️ Изменить", callback_data=f"{HW_EDIT}{homework.id}")
        builder.button(text="🗑 Удалить", callback_data=f"{HW_DELETE}{homework.id}")
    builder.button(text="🔙 В меню", callback_data=MENU_BACK)
    builder.adjust(1)
    return text, builder.as_markup()


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
    text, markup = _detail_payload(homework, detail, can_modify)
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
    today_items, tomorrow_items = await service.nearest(group.id, today)
    subject_names = await service.subject_names(
        group.id, today_items + tomorrow_items
    )
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    parts = ["🔥 <b>Ближайшие дедлайны</b>", ""]
    parts.append(f"📅 Сегодня ({_date_ru(today)}):")
    if today_items:
        for item in today_items:
            label = _homework_label(item, subject_names)
            parts.append(esc(label))
            builder.button(text=label, callback_data=f"{HW_DETAIL}{item.id}")
    else:
        parts.append(EMPTY_LINE)
    parts.append("")
    parts.append(f"📅 Завтра ({_date_ru(_tomorrow(today))}):")
    if tomorrow_items:
        for item in tomorrow_items:
            label = _homework_label(item, subject_names)
            parts.append(esc(label))
            builder.button(text=label, callback_data=f"{HW_DETAIL}{item.id}")
    else:
        parts.append(EMPTY_LINE)
    builder.button(text="🔙 В меню", callback_data=MENU_BACK)
    builder.adjust(1)
    await query.message.edit_text("\n".join(parts), reply_markup=builder.as_markup())
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
        "🗂 Все задания\n\nВыбери категорию:",
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
    items = await _list_homeworks(service, group.id, category, user.id, today)
    subject_names = await service.subject_names(group.id, items)
    start = page * PAGE_SIZE
    chunk = items[start : start + PAGE_SIZE]
    rows = [
        (hw.id, _homework_label(hw, subject_names)) for hw in chunk
    ]
    total_pages = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
    title = _CATEGORY_TITLES.get(category, "🗂 Все задания")
    text = f"{title}\n\nСтраница {page + 1} из {total_pages} · всего {len(items)}"
    if not rows:
        text += "\n\n" + EMPTY_LINE
    markup = homework_list_keyboard(
        rows,
        category,
        page,
        has_prev=page > 0,
        has_next=start + PAGE_SIZE < len(items),
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
    _, category, index = query.data.split(":")
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
        page=int(index),
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
    homework_id = int(query.data[len(HW_DETAIL):])
    ok = await render_homework_detail(
        message=query.message,
        bot=bot,
        session=session,
        user=user,
        state=state,
        homework_id=homework_id,
    )
    if ok:
        await state.clear()
        await query.answer()
    else:
        await query.answer("Задание не найдено.", show_alert=True)


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
    homework_id = int(query.data[len(HW_EDIT):])
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
    await query.message.edit_text(
        "✏️ Что изменить?",
        reply_markup=homework_edit_field_keyboard(homework_id),
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
            prompt, reply_markup=attachment_keyboard()
        )
    else:
        await query.message.edit_text(prompt)
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
        await service.update_homework(homework, title=str(value))
    elif field == "description":
        await service.update_homework(
            homework, description=str(value) if value is not None else None
        )
    await state.clear()
    detail = await service.get_detail(homework)
    text, markup = _detail_payload(homework, detail, True)
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
) -> None:
    detail = await service.get_detail(homework)
    text, markup = _detail_payload(homework, detail, True)
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
    await _finish_edit(query.message, service, homework)
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
    if homework is None or not await service.can_modify(user, group.id, homework):
        await state.clear()
        await query.answer("Доступ запрещён.", show_alert=True)
        return
    if data.get("deadline"):
        homework.deadline = date.fromisoformat(str(data["deadline"]))
    await service.attach_pending(
        homework,
        attachments=list(data.get("attachments", [])),  # type: ignore[arg-type]
        links=list(data.get("links", [])),  # type: ignore[arg-type]
    )
    await session.flush()
    await state.clear()
    await _finish_edit(query.message, service, homework)
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
    homework_id = int(query.data[len(HW_DELETE):])
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
    await query.message.edit_text(
        text, reply_markup=homework_delete_confirm_keyboard(homework_id)
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
    homework_id = int(query.data[len(HW_DELETE_CONFIRM):])
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
    await query.message.edit_text("✅ Задание удалено. Нажми /menu для возврата.")
    await query.answer()


@router.callback_query(CallbackDataPrefix(FILE_SEND))
async def on_send_file(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if (
        not query.data
        or not isinstance(query.message, Message)
        or query.message.chat is None
    ):
        await query.answer()
        return
    payload = query.data[len(FILE_SEND):]
    homework_id_raw, attachment_id_raw = payload.split(":")
    homework_id = int(homework_id_raw)
    attachment_id = int(attachment_id_raw)
    group = await resolve_group(bot, session, user, query.message.chat, state)
    if group is None:
        await query.answer(NO_GROUP_TEXT, show_alert=True)
        return
    service = HomeworkService(session)
    homework = await service.get_for_group(homework_id, group.id)
    if homework is None:
        await query.answer("Задание не найдено.", show_alert=True)
        return
    attachment = next(
        (
            item
            for item in await service.attachments_for(homework)
            if item.id == attachment_id
        ),
        None,
    )
    if attachment is None:
        await query.answer("Файл больше недоступен.", show_alert=True)
        return
    chat_id = query.message.chat.id
    try:
        if attachment.file_type == AttachmentType.PHOTO:
            await bot.send_photo(chat_id, attachment.telegram_file_id)
        else:
            await bot.send_document(
                chat_id, attachment.telegram_file_id, caption=attachment.file_name
            )
    except Exception:
        await query.answer("Не удалось скачать файл.", show_alert=True)
        return
    await query.answer("⬇️ Вот файл.")
