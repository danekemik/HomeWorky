from collections import OrderedDict
from datetime import date

from aiogram import Bot, Router
from aiogram.enums import ParseMode
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.calendar import build_calendar_markup
from app.bot.callbacks import (
    DETAIL_BACK,
    HW_ADD_FILES,
    HW_DELETE,
    HW_DELETE_CONFIRM,
    HW_DELETE_FILE,
    HW_DELETE_FILE_CONFIRM,
    HW_DETAIL,
    HW_EDIT,
    HW_EDIT_FIELD,
    HW_FOLDER_BACK,
    HW_OPEN_FILE,
    HW_OPEN_FOLDER,
    MENU_BACK,
    PAGE,
    VIEWS,
)
from app.bot.context import resolve_group, select_current_group
from app.bot.filters.callback import CallbackDataPrefix
from app.bot.formats import (
    bot_today,
    build_folder_card,
    build_homework_card,
    clamp_button_text,
    clamp_file_name,
    esc,
    format_homework_label,
    link_html,
    link_label,
    photo_label,
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
    attachment_delete_confirm_keyboard,
    homework_delete_confirm_keyboard,
    homework_edit_field_keyboard,
    homework_list_keyboard,
    homeworks_category_keyboard,
)
from app.bot.messages import NO_GROUP_TEXT
from app.bot.render import edit_or_resend, replace_message_at_bottom
from app.bot.states.homework import HomeworkCreation, HomeworkEditField
from app.database.models import AttachmentType, Homework, User
from app.dates import russian_month_name_short
from app.services.homework_service import (
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

_OPENED_FILE_MESSAGES: OrderedDict[tuple[int, int], int] = OrderedDict()

_MEMORY_LIMIT = 200


def _bounded_set[K, V](
    store: OrderedDict[K, V], key: K, value: V
) -> None:
    """Вставляет запись и не даёт словарю бесконечно расти на долгих сессиях."""
    store[key] = value
    store.move_to_end(key)
    while len(store) > _MEMORY_LIMIT:
        store.popitem(last=False)


EMPTY_LINE = "  — заданий нет"

_DETAIL_HEADER = "🐹 *Homy достаёт нужную карточку из папки*"

# (chat_id, user_id) -> (категория, страница) последнего просмотренного списка
_list_context: OrderedDict[tuple[int, int], tuple[str, int]] = OrderedDict()


def _remember_list_context(
    chat_id: int, user_id: int, target: tuple[str, int]
) -> None:
    _bounded_set(_list_context, (chat_id, user_id), target)


def _date_ru(day: date) -> str:
    return f"{day.day} {russian_month_name_short(day.month)}"


def _homework_label(homework: Homework, subject_names: dict[int, str]) -> str:
    subject = subject_names.get(homework.subject_id, "—")
    return clamp_button_text(
        format_homework_label(subject, homework.title, homework.deadline)
    )


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
    photos = sum(
        1
        for item in detail.attachments
        if item.file_type == AttachmentType.PHOTO
    )
    files = len(detail.attachments) - photos
    text = build_homework_card(
        header=_DETAIL_HEADER,
        subject=detail.subject,
        title=homework.title,
        deadline=homework.deadline,
        description=homework.description,
        author_name=detail.author_name,
        photo_count=photos,
        file_count=files,
        link_lines=[link.title or link.url for link in detail.links],
    )
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    if can_modify:
        builder.row(
            InlineKeyboardButton(
                text="✏️ Изменить", callback_data=f"{HW_EDIT}{homework.id}"
            ),
            InlineKeyboardButton(
                text="🗑 Удалить", callback_data=f"{HW_DELETE}{homework.id}"
            ),
        )
    if can_add_files or detail.attachments:
        builder.row(
            InlineKeyboardButton(
                text="📁 Посмотреть файлы",
                callback_data=f"{HW_OPEN_FOLDER}{homework.id}",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="🔙 К списку", callback_data=f"{DETAIL_BACK}{homework.id}"
        )
    )
    return text, builder.as_markup()


def _author_suffix(name: str, author: str | None) -> str:
    return f"{name} — {author}" if author else name


def _attachment_menu_rows(
    homework: Homework,
    detail: HomeworkDetail,
    deleteable_attachment_ids: set[int],
) -> list[list[InlineKeyboardButton]]:
    """Ряды меню папки: [название] [🗑] по одному вложению в ряд."""
    rows: list[list[InlineKeyboardButton]] = []
    photo_index = 0
    for item in detail.attachments:
        if item.file_type == AttachmentType.PHOTO:
            label = photo_label(photo_index)
            photo_index += 1
        else:
            label = clamp_file_name(item.file_name or "Файл")
        row = [
            InlineKeyboardButton(
                text=clamp_button_text(label, limit=28),
                callback_data=f"{HW_OPEN_FILE}{homework.id}:{item.id}",
            )
        ]
        if item.id in deleteable_attachment_ids:
            row.append(
                InlineKeyboardButton(
                    text="🗑",
                    callback_data=f"{HW_DELETE_FILE}{homework.id}:{item.id}",
                )
            )
        rows.append(row)
    return rows


def _folder_markup(
    homework: Homework,
    detail: HomeworkDetail,
    can_add_files: bool,
    deleteable_attachment_ids: set[int],
) -> InlineKeyboardMarkup:
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    if can_add_files:
        builder.row(
            InlineKeyboardButton(
                text="📎 Добавить файлы",
                callback_data=f"{HW_ADD_FILES}{homework.id}",
            )
        )
    for row in _attachment_menu_rows(homework, detail, deleteable_attachment_ids):
        builder.row(*row)
    builder.row(
        InlineKeyboardButton(
            text="🔙 К заданию",
            callback_data=f"{HW_FOLDER_BACK}{homework.id}",
        )
    )
    return builder.as_markup()


def _folder_payload(
    homework: Homework,
    detail: HomeworkDetail,
    can_add_files: bool,
    deleteable_attachment_ids: set[int],
) -> tuple[str, InlineKeyboardMarkup]:
    photo_lines: list[str] = []
    file_lines: list[str] = []
    photo_index = 0
    for item in detail.attachments:
        if item.file_type == AttachmentType.PHOTO:
            label = photo_label(photo_index)
            photo_index += 1
            photo_lines.append(_author_suffix(label, item.author_name))
        else:
            label = clamp_file_name(item.file_name or "Файл")
            file_lines.append(_author_suffix(label, item.author_name))
    link_lines = [
        link_html(link.url, link_label(link.url, link.title), link.author_name)
        for link in detail.links
    ]
    text = build_folder_card(
        photo_lines=photo_lines,
        file_lines=file_lines,
        link_lines=link_lines,
    )
    return text, _folder_markup(
        homework,
        detail,
        can_add_files,
        deleteable_attachment_ids,
    )


def _preview_key(chat_id: int, homework_id: int) -> tuple[int, int]:
    return (chat_id, homework_id)


async def _delete_file_preview(bot: Bot, chat_id: int, homework_id: int) -> None:
    """Удаляет сообщение-превью файла (если оно есть), показываемое в папке."""
    key = _preview_key(chat_id, homework_id)
    message_id = _OPENED_FILE_MESSAGES.pop(key, None)
    if message_id is None:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


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
    *,
    delete_source: bool = True,
) -> Message | None:
    """Показывает карточку задания; возвращает сообщение-карточку (или None)."""
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
    chat_id = message.chat.id
    try:
        if delete_source:
            await edit_or_resend(message, text, markup)
            return message
        return await bot.send_message(chat_id, text, reply_markup=markup)
    except Exception:
        try:
            return await bot.send_message(chat_id, text, reply_markup=markup)
        except Exception:
            return None


async def _open_folder_view(
    message: Message,
    bot: Bot,
    service: HomeworkService,
    homework: Homework,
    user: User,
) -> None:
    """Показывает «папку» файлов в конце чата."""
    await _delete_file_preview(bot, message.chat.id, homework.id)
    detail = await service.get_detail(homework)
    can_add_files = await service.is_member(user, homework.group_id)
    deleteables = await _deleteable_attachment_ids(
        service, user, homework, detail
    )
    text, markup = _folder_payload(homework, detail, can_add_files, deleteables)
    await replace_message_at_bottom(message, text, markup, parse_mode=ParseMode.HTML)


async def _show_card_text(
    message: Message,
    service: HomeworkService,
    homework: Homework,
    user: User,
) -> None:
    """Возвращает папку к карточке задания в конец чата."""
    detail = await service.get_detail(homework)
    can_modify = await service.can_modify(user, homework.group_id, homework)
    can_add_files = await service.is_member(user, homework.group_id)
    deleteables = await _deleteable_attachment_ids(
        service, user, homework, detail
    )
    text, markup = _detail_payload(
        homework, detail, can_modify, can_add_files, deleteables
    )
    await replace_message_at_bottom(message, text, markup)


async def _open_folder_after_changes(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    user: User,
    service: HomeworkService,
    homework: Homework,
) -> None:
    """После добавления/удаления вложений пересобирает вид и остаётся в папке."""
    card = await _open_detail(message, bot, session, user, service, homework)
    if card is not None:
        await _open_folder_view(card, bot, service, homework, user)


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
                text=clamp_button_text(f"{subject} — {item.title}"),
                callback_data=f"{HW_DETAIL}{item.id}",
            )

    add_block(today_items, today)
    lines.append("")
    add_block(tomorrow_items, tomorrow)
    lines += ["", "🐹 *закрывает календарь*"]
    builder.button(text="🔙 В меню", callback_data=MENU_BACK)
    builder.adjust(1)
    _remember_list_context(
        query.message.chat.id, user.id, ("nearest", 0)
    )
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
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if page >= total_pages:
        page = total_pages - 1
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
    _remember_list_context(query.message.chat.id, user.id, (category, page))
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
    state_name = await state.get_state()
    if state_name is None or not (
        state_name.startswith(HomeworkCreation.__name__)
        or state_name.startswith(HomeworkEditField.__name__)
    ):
        await state.clear()
    await _open_detail(
        query.message, bot, session, user, service, homework
    )
    await query.answer()


@router.callback_query(CallbackDataPrefix(DETAIL_BACK))
async def on_detail_back(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not query.data or not isinstance(query.message, Message):
        await query.answer()
        return
    target = _list_context.pop((query.message.chat.id, user.id), None)
    if target is not None:
        category, page = target
        if category == "nearest":
            await on_nearest_deadlines(query, bot, session, user, state)
            return
        if category in _CATEGORY_TITLES:
            await _render_category_list(
                query=query,
                bot=bot,
                session=session,
                user=user,
                state=state,
                category=category,
                page=page,
            )
            return
    from app.bot.handlers.homework import _back_to_menu

    await _back_to_menu(query.message, bot, session, user, state)


@router.callback_query(CallbackDataPrefix(HW_OPEN_FOLDER))
async def on_open_folder(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not query.data or not isinstance(query.message, Message):
        await query.answer()
        return
    homework_id = safe_int(query.data[len(HW_OPEN_FOLDER):])
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
    await _open_folder_view(query.message, bot, service, homework, user)
    await query.answer()


@router.callback_query(CallbackDataPrefix(HW_FOLDER_BACK))
async def on_folder_back(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not query.data or not isinstance(query.message, Message):
        await query.answer()
        return
    homework_id = safe_int(query.data[len(HW_FOLDER_BACK):])
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
    await _delete_file_preview(bot, query.message.chat.id, homework_id)
    await _show_card_text(query.message, service, homework, user)
    await query.answer()


@router.callback_query(CallbackDataPrefix(HW_OPEN_FILE))
async def on_open_file(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not query.data or not isinstance(query.message, Message):
        await query.answer()
        return
    payload = query.data[len(HW_OPEN_FILE):]
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
    detail = await service.get_detail(homework)
    can_add_files = await service.is_member(user, homework.group_id)
    deleteables = await _deleteable_attachment_ids(
        service, user, homework, detail
    )
    markup = _folder_markup(homework, detail, can_add_files, deleteables)
    key = _preview_key(query.message.chat.id, homework_id)
    await _delete_file_preview(bot, query.message.chat.id, homework_id)
    if (
        not query.message.photo
        and not query.message.document
        and not query.message.video
    ):
        try:
            await query.message.delete()
        except Exception:
            pass
    chat_id = query.message.chat.id
    if attachment.file_type == AttachmentType.PHOTO:
        sent = await bot.send_photo(
            chat_id,
            attachment.telegram_file_id,
            reply_markup=markup,
        )
    else:
        sent = await bot.send_document(
            chat_id,
            attachment.telegram_file_id,
            caption=f"📎 {attachment.file_name or 'Файл'}",
            reply_markup=markup,
        )
    _bounded_set(_OPENED_FILE_MESSAGES, key, sent.message_id)
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
    if (
        await service.attachment_count(homework, AttachmentType.PHOTO)
        >= HomeworkService.MAX_PHOTOS
        and await service.attachment_count(homework, AttachmentType.DOCUMENT)
        >= HomeworkService.MAX_FILES
        and await service.link_count(homework) >= HomeworkService.MAX_LINKS
    ):
        await query.answer(
            "Лимит вложений исчерпан: по 3 фото, 3 файла и 3 ссылки на задание.",
            show_alert=True,
        )
        return
    await state.set_state(HomeworkEditField.attachment)
    select_current_group(user, group.id)
    await _delete_file_preview(bot, query.message.chat.id, homework_id)
    await state.update_data(
        add_only=True,
        homework_id=homework_id,
        current_group_id=group.id,
        attachments=[],
        links=[],
    )
    from app.bot.handlers.homework import ATTACH_PENDING

    await replace_message_at_bottom(
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
    if attachment.file_type == AttachmentType.PHOTO:
        confirm_text = "🗑 Удалить фото?"
    else:
        name = esc(attachment.file_name or "Файл")
        confirm_text = f"🗑 Удалить файл «{name}»?"
    await edit_or_resend(
        query.message,
        confirm_text,
        markup=attachment_delete_confirm_keyboard(homework_id, attachment_id),
    )
    await query.answer()


@router.callback_query(CallbackDataPrefix(HW_DELETE_FILE_CONFIRM))
async def on_delete_file_confirm(
    query: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: FSMContext,
) -> None:
    if not query.data or not isinstance(query.message, Message):
        await query.answer()
        return
    payload = query.data[len(HW_DELETE_FILE_CONFIRM):]
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
    await _open_folder_after_changes(
        query.message, bot, session, user, service, homework
    )
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
    await state.update_data(prompt_message_id=query.message.message_id)
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
    prompt_message_id = data.get("prompt_message_id")
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
    if (
        isinstance(prompt_message_id, int)
        and prompt_message_id != message.message_id
    ):
        try:
            await bot.delete_message(message.chat.id, prompt_message_id)
        except Exception:
            pass
    await _send_edited_detail(message, bot, session, user, service, homework)


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
    bot: Bot,
    session: AsyncSession,
    service: HomeworkService,
    homework: Homework,
    user: User,
) -> None:
    await _open_detail(message, bot, session, user, service, homework)


async def _send_edited_detail(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    user: User,
    service: HomeworkService,
    homework: Homework,
) -> None:
    """Показывает отредактированное дз новым сообщением (источник не удаляя)."""
    await _open_detail(
        message,
        bot,
        session,
        user,
        service,
        homework,
        delete_source=False,
    )


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
    prompt_message_id = data.get("prompt_message_id")
    await state.clear()
    if (
        isinstance(prompt_message_id, int)
        and prompt_message_id != query.message.message_id
    ):
        try:
            await bot.delete_message(query.message.chat.id, prompt_message_id)
        except Exception:
            pass
    await _finish_edit(query.message, bot, session, service, homework, user)
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
            "Лимит вложений: до 3 фото, 3 файлов и 3 ссылок на задание.",
            show_alert=True,
        )
        return
    await session.flush()
    await state.clear()
    await _finish_edit(query.message, bot, session, service, homework, user)
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
