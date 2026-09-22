from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import (
    ATTACH_DONE,
    ATTACH_SKIP,
    FLOW_CANCEL,
    HW_EDIT_PENDING,
    HW_SAVE,
    PENDING_EDIT_DONE,
    PENDING_FIELD,
    SKIP,
    SUBJECT_PICK,
)
from app.bot.formats import clamp_button_text
from app.database.models import Subject


def cancel_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(text="🔙 Назад", callback_data=FLOW_CANCEL)


def back_only_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(cancel_button())
    return builder.as_markup()


def subject_picker_keyboard(subjects: list[Subject]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for subject in subjects:
        builder.button(
            text=clamp_button_text(f"📚 {subject.name}"),
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


def attachment_keyboard(has_attachments: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=("✅ Готово" if has_attachments else "➡️ Пропустить"),
        callback_data=(ATTACH_DONE if has_attachments else ATTACH_SKIP),
    )
    return builder.as_markup()


def preview_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Создать", callback_data=HW_SAVE)
    builder.button(text="✏️ Изменить", callback_data=HW_EDIT_PENDING)
    builder.row(cancel_button())
    return builder.as_markup()


def pending_edit_fields_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📚 Предмет", callback_data=f"{PENDING_FIELD}subject")
    builder.button(text="💻 Название", callback_data=f"{PENDING_FIELD}title")
    builder.button(text="📝 Описание", callback_data=f"{PENDING_FIELD}description")
    builder.button(text="📅 Дата сдачи", callback_data=f"{PENDING_FIELD}deadline")
    builder.button(text="📎 Файлы и ссылки", callback_data=f"{PENDING_FIELD}attachment")
    builder.button(text="✅ Готово", callback_data=PENDING_EDIT_DONE)
    builder.button(text="🔙 Назад", callback_data=FLOW_CANCEL)
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()
