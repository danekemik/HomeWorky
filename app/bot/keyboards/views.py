from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import (
    HW_DELETE_CONFIRM,
    HW_DELETE_FILE_CONFIRM,
    HW_DETAIL,
    HW_EDIT_FIELD,
    MENU_BACK,
    PAGE,
    VIEWS,
)
from app.bot.keyboards.menu import CB_ALL_TASKS

PAGE_SIZE = 8


def homeworks_category_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📜 Прошедшие", callback_data=VIEWS + "past")
    builder.button(text="🔥 Актуальные", callback_data=VIEWS + "active")
    builder.button(text="👤 Созданные мной", callback_data=VIEWS + "mine")
    builder.button(text="⚠ Просроченные", callback_data=VIEWS + "overdue")
    builder.row(InlineKeyboardButton(text="🔙 В меню", callback_data=MENU_BACK))
    builder.adjust(1)
    return builder.as_markup()


def homework_list_keyboard(
    items: list[tuple[int, str]],
    category: str,
    page: int,
    has_prev: bool,
    has_next: bool,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for homework_id, label in items:
        builder.button(text=label, callback_data=f"{HW_DETAIL}{homework_id}")
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data=CB_ALL_TASKS))
    if has_prev:
        builder.button(text="◀️ Назад", callback_data=f"{PAGE}{category}:{page - 1}")
    if has_next:
        builder.button(text="Вперёд ▶️", callback_data=f"{PAGE}{category}:{page + 1}")
    builder.adjust(1)
    return builder.as_markup()


def homework_edit_field_keyboard(homework_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📚 Предмет", callback_data=f"{HW_EDIT_FIELD}subject")
    builder.button(text="💻 Название", callback_data=f"{HW_EDIT_FIELD}title")
    builder.button(text="📝 Описание", callback_data=f"{HW_EDIT_FIELD}description")
    builder.button(text="📅 Дата сдачи", callback_data=f"{HW_EDIT_FIELD}deadline")
    builder.button(text="📎 Файлы и ссылки", callback_data=f"{HW_EDIT_FIELD}attachment")
    back_data = f"{HW_DETAIL}{homework_id}" if homework_id is not None else MENU_BACK
    builder.button(text="🔙 Назад", callback_data=back_data)
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def homework_delete_confirm_keyboard(homework_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Да, удалить", callback_data=f"{HW_DELETE_CONFIRM}{homework_id}")
    builder.button(text="❌ Нет", callback_data=f"{HW_DETAIL}{homework_id}")
    builder.adjust(2)
    return builder.as_markup()


def attachment_delete_confirm_keyboard(
    homework_id: int, attachment_id: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🗑 Да, удалить",
        callback_data=f"{HW_DELETE_FILE_CONFIRM}{homework_id}:{attachment_id}",
    )
    builder.button(text="❌ Нет", callback_data=f"{HW_DETAIL}{homework_id}")
    builder.adjust(2)
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 В меню", callback_data=MENU_BACK)
    return builder.as_markup()
