from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import (
    HW_DELETE,
    HW_DELETE_CONFIRM,
    HW_DETAIL,
    HW_EDIT,
    HW_EDIT_FIELD,
    MENU_BACK,
    PAGE,
    VIEWS,
)

PAGE_SIZE = 8


def homeworks_category_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📜 Прошедшие", callback_data=VIEWS + "past")
    builder.button(text="🔥 Актуальные", callback_data=VIEWS + "active")
    builder.button(text="👤 Созданные мной", callback_data=VIEWS + "mine")
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
    builder.button(text="🔙 В меню", callback_data=MENU_BACK)
    if has_prev:
        builder.button(text="◀️ Назад", callback_data=f"{PAGE}{category}:{page - 1}")
    if has_next:
        builder.button(text="Вперёд ▶️", callback_data=f"{PAGE}{category}:{page + 1}")
    builder.adjust(1)
    return builder.as_markup()


def homework_detail_keyboard(homework_id: int, can_modify: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if can_modify:
        builder.button(text="✏️ Изменить", callback_data=f"{HW_EDIT}{homework_id}")
        builder.button(text="🗑 Удалить", callback_data=f"{HW_DELETE}{homework_id}")
    builder.button(text="🔙 В меню", callback_data=MENU_BACK)
    if can_modify:
        builder.adjust(2, 1)
    return builder.as_markup()


def homework_edit_field_keyboard(homework_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📚 Предмет", callback_data=f"{HW_EDIT_FIELD}subject")
    builder.button(text="💻 Название", callback_data=f"{HW_EDIT_FIELD}title")
    builder.button(text="📝 Описание", callback_data=f"{HW_EDIT_FIELD}description")
    builder.button(text="📅 Дата сдачи", callback_data=f"{HW_EDIT_FIELD}deadline")
    builder.button(text="📎 Файлы и ссылки", callback_data=f"{HW_EDIT_FIELD}attachment")
    builder.button(text="🔙 В меню", callback_data=MENU_BACK)
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def homework_delete_confirm_keyboard(homework_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Да, удалить", callback_data=f"{HW_DELETE_CONFIRM}{homework_id}")
    builder.button(text="❌ Нет", callback_data=f"{HW_DETAIL}{homework_id}")
    builder.adjust(2)
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 В меню", callback_data=MENU_BACK)
    return builder.as_markup()
