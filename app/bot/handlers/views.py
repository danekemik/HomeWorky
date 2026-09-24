from datetime import date

from aiogram import Bot, Router
from aiogram.enums import ParseMode
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaDocument,
    InputMediaPhoto,
    MediaUnion,
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
    MENU_BACK,
    PAGE,
    VIEWS,
)
from app.bot.context import resolve_group, select_current_group
from app.bot.filters.callback import CallbackDataPrefix
from app.bot.formats import (
    bot_today,
    build_homework_card,
    clamp_button_text,
    esc,
    format_date_russian,
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
    attachment_delete_confirm_keyboard,
    homework_delete_confirm_keyboard,
    homework_edit_field_keyboard,
    homework_list_keyboard,
    homeworks_category_keyboard,
)
from app.bot.messages import NO_GROUP_TEXT
from app.bot.render import edit_or_resend
from app.bot.states.homework import HomeworkCreation, HomeworkEditField
from app.database.models import Attachment, AttachmentType, Homework, User
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

_DETAIL_HEADER = "🐹 Homy достаёт нужную карточку из папки"

_ALBUM_MAX_ITEMS = 10

# (chat_id, homework_id) -> id сообщений карточки (альбом + кнопки)
_sent_detail_messages: dict[tuple[int, int], list[int]] = {}

# (chat_id, user_id) -> (категория, страница) последнего просмотренного списка
_list_context: dict[tuple[int, int], tuple[str, int]] = {}


def _remember_detail(
    chat_id: int, homework_id: int, messages: list[Message]
) -> None:
    _sent_detail_messages[(chat_id, homework_id)] = [
        message.message_id for message in messages
    ]


def _forget_detail_ids(chat_id: int, homework_id: int) -> list[int]:
    if len(_sent_detail_messages) > 200:
        _sent_detail_messages.clear()
    return _sent_detail_messages.pop((chat_id, homework_id), [])


async def _cleanup_detail_messages(
    bot: Bot,
    chat_id: int,
    homework_id: int,
    *,
    exclude: int | None = None,
) -> None:
    for message_id in _forget_detail_ids(chat_id, homework_id):
        if message_id == exclude:
            continue
        try:
            await bot.delete_message(chat_id, message_id)
        except Exception:
            pass


def _remember_list_context(
    chat_id: int, user_id: int, target: tuple[str, int]
) -> None:
    _list_context[(chat_id, user_id)] = target


def _compact_caption(homework: Homework, detail: HomeworkDetail) -> str:
    return (
        f"📚 {esc(detail.subject)} · {esc(homework.title)} · "
        f"до {format_date_russian(homework.deadline)}"
    )


def _attachment_send_plan(
    attachments: list[Attachment],
) -> list[tuple[str, list[Attachment]]]:
    """План отправки вложений: ('album' | 'single', файлы одного типа)."""
    ops: list[tuple[str, list[Attachment]]] = []
    for attachment_type in (AttachmentType.PHOTO, AttachmentType.DOCUMENT):
        items = [a for a in attachments if a.file_type == attachment_type]
        for start in range(0, len(items), _ALBUM_MAX_ITEMS):
            chunk = items[start : start + _ALBUM_MAX_ITEMS]
            ops.append(("single" if len(chunk) == 1 else "album", chunk))
    return ops


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
    text = build_homework_card(
        header=_DETAIL_HEADER,
        subject=detail.subject,
        title=homework.title,
        deadline=homework.deadline,
        description=homework.description,
        author_name=detail.author_name,
        attachment_count=len(detail.attachments) or None,
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
    if can_add_files:
        builder.row(
            InlineKeyboardButton(
                text="📎 Добавить файлы",
                callback_data=f"{HW_ADD_FILES}{homework.id}",
            )
        )
    delete_buttons: list[InlineKeyboardButton] = []
    photo_number = 0
    for item in detail.attachments:
        if item.file_type == AttachmentType.PHOTO:
            photo_number += 1
        if item.id not in deleteable_attachment_ids:
            continue
        if item.file_type == AttachmentType.PHOTO:
            label = f"🗑 Фото {photo_number}"
        else:
            label = f"🗑 {item.file_name or 'Файл'}"
        delete_buttons.append(
            InlineKeyboardButton(
                text=clamp_button_text(label),
                callback_data=f"{HW_DELETE_FILE}{homework.id}:{item.id}",
            )
        )
    for index in range(0, len(delete_buttons), 2):
        builder.row(*delete_buttons[index : index + 2])
    builder.row(
        InlineKeyboardButton(
            text="🔙 К списку", callback_data=f"{DETAIL_BACK}{homework.id}"
        )
    )
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
    *,
    delete_source: bool = True,
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
    chat_id = message.chat.id
    homework_id = homework.id
    attachments = await service.attachments_for(homework)
    if not attachments:
        await _cleanup_detail_messages(
            bot, chat_id, homework_id, exclude=message.message_id
        )
        await edit_or_resend(message, text, markup)
        return
    if delete_source:
        try:
            await message.delete()
        except Exception:
            pass
    await _cleanup_detail_messages(bot, chat_id, homework_id)
    sent: list[Message] = []
    caption_placed = False
    try:
        for operation, chunk in _attachment_send_plan(attachments):
            if operation == "album":
                media = _album_media(
                    chunk,
                    _compact_caption(homework, detail)
                    if not caption_placed
                    else None,
                )
                if not caption_placed:
                    caption_placed = True
                sent.extend(await bot.send_media_group(chat_id, media))
                continue
            item = chunk[0]
            media_caption = (
                _compact_caption(homework, detail) if not caption_placed else None
            )
            if not caption_placed:
                caption_placed = True
            if item.file_type == AttachmentType.PHOTO:
                sent.append(
                    await bot.send_photo(
                        chat_id,
                        item.telegram_file_id,
                        caption=media_caption,
                        parse_mode=(
                            ParseMode.HTML if media_caption is not None else None
                        ),
                    )
                )
            else:
                sent.append(
                    await bot.send_document(
                        chat_id,
                        item.telegram_file_id,
                        caption=media_caption,
                        parse_mode=(
                            ParseMode.HTML if media_caption is not None else None
                        ),
                    )
                )
        sent.append(await bot.send_message(chat_id, text, reply_markup=markup))
        _remember_detail(chat_id, homework_id, sent)
    except Exception:
        try:
            await bot.send_message(chat_id, text, reply_markup=markup)
        except Exception:
            pass
        for item in attachments:
            try:
                if item.file_type == AttachmentType.PHOTO:
                    await bot.send_photo(chat_id, item.telegram_file_id)
                else:
                    await bot.send_document(
                        chat_id,
                        item.telegram_file_id,
                        caption=f"📎 {item.file_name or 'Файл'}",
                    )
            except Exception:
                pass


def _album_media(
    chunk: list[Attachment],
    caption: str | None,
) -> list[MediaUnion]:
    if chunk[0].file_type == AttachmentType.PHOTO:
        media: list[MediaUnion] = []
        for index, item in enumerate(chunk):
            if index == 0 and caption is not None:
                media.append(
                    InputMediaPhoto(
                        media=item.telegram_file_id,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                    )
                )
            else:
                media.append(InputMediaPhoto(media=item.telegram_file_id))
        return media
    documents: list[MediaUnion] = []
    for index, item in enumerate(chunk):
        if index == 0 and caption is not None:
            documents.append(
                InputMediaDocument(
                    media=item.telegram_file_id,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
            )
        else:
            documents.append(
                InputMediaDocument(media=item.telegram_file_id)
            )
    return documents


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
    homework_id = safe_int(query.data[len(DETAIL_BACK):])
    if homework_id is not None:
        await _cleanup_detail_messages(
            bot,
            query.message.chat.id,
            homework_id,
            exclude=query.message.message_id,
        )
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
    detail = await service.get_detail(homework)
    can_modify = await service.can_modify(
        user, homework.group_id, homework
    )
    can_add_files = await service.is_member(user, homework.group_id)
    deleteables = await _deleteable_attachment_ids(
        service, user, homework, detail
    )
    if len(detail.attachments) >= 2:
        await _open_detail(message, bot, session, user, service, homework)
        return
    text, markup = _detail_payload(
        homework,
        detail,
        can_modify,
        can_add_files,
        deleteables,
    )
    await message.edit_text(text, reply_markup=markup)


async def _send_edited_detail(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    user: User,
    service: HomeworkService,
    homework: Homework,
) -> None:
    """Показывает отредактированное дз новым сообщением (источник не удаляя)."""
    detail = await service.get_detail(homework)
    if detail.attachments:
        await _open_detail(
            message,
            bot,
            session,
            user,
            service,
            homework,
            delete_source=False,
        )
        return
    deleteables = {item.id for item in detail.attachments}
    text, markup = _detail_payload(
        homework, detail, True, True, deleteables
    )
    await message.answer(text, reply_markup=markup)


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
            f"Лимит — {HomeworkService.MAX_ATTACHMENTS} файла на задание.",
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
    await _cleanup_detail_messages(
        bot,
        query.message.chat.id,
        homework_id,
        exclude=query.message.message_id,
    )
    await edit_or_resend(
        query.message, "✅ Задание удалено. Нажми /menu для возврата."
    )
    await query.answer()
