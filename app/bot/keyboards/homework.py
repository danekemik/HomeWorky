from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import (
    ATTACH_DONE,
    ATTACH_SKIP,
    FLOW_CANCEL,
    HW_EDIT_PENDING,
    HW_SAVE,
    SKIP,
    SUBJECT_PICK,
)
from app.database.models import Subject


def cancel_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(text="🔙 Назад", callback_data=FLOW_CANCEL)


def subject_picker_keyboard(subjects: list[Subject]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for subject in subjects:
        builder.button(
            text=f"📚 {subject.name}",
            callback_data=f"{SUBJECT_PICK}{subject.id}",
        )
    builder.button(text="➕ Новый предмет", callback_data=f"{SUBJECT_PICK}new")
    builder.row(cancel_button())
    builder.adjust(1)
    return builder.as_markup()


def skip_or_cancel_keyboard(readable: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if readable:
        builder.button(text="➡️ Пропустить", callback_data=SKIP)
    builder.row(cancel_button())
    return builder.as_markup()


def attachment_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Готово", callback_data=ATTACH_DONE)
    builder.button(text="➡️ Пропустить", callback_data=ATTACH_SKIP)
    builder.row(cancel_button())
    return builder.as_markup()


def preview_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Создать", callback_data=HW_SAVE)
    builder.button(text="✏️ Изменить", callback_data=HW_EDIT_PENDING)
    builder.row(cancel_button())
    return builder.as_markup()
