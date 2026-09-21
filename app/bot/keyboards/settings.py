from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import MENU_BACK
from app.bot.keyboards.menu import CB_ONBOARD_JOIN, CB_SETTINGS
from app.config import settings
from app.database.models import Group, Subject

SET_MANAGE = "set:manage"
SET_MANAGE_GROUP = "set:mng:"  # set:mng:{group_id}
SET_MEMBERS = "set:members:"  # set:members:{group_id}
SET_MEMBER_PAGE = "set:mpage:"  # set:mpage:{group_id}:{offset}
SET_MEMBER_REMOVE = "set:rm:"  # set:rm:{group_id}:{user_id}
SET_MEMBER_REMOVE_CONFIRM = "set:rmc:"  # set:rmc:{group_id}:{user_id}
SET_CODE_ROTATE = "set:code:"  # set:code:{group_id}
SET_RENAME_GROUP = "set:rnm:"  # set:rnm:{group_id}
SET_SUBJECTS = "set:subj:"  # set:subj:{group_id}
SET_SUBJECT_RENAME = "set:subjr:"  # set:subjr:{subject_id}
SET_SUBJECT_DELETE = "set:subjd:"  # set:subjd:{subject_id}
SET_SUBJECT_DELETE_CONFIRM = "set:subjdc:"  # set:subjdc:{subject_id}
SET_LEAVE = "set:leave"
SET_LEAVE_PICK = "set:lv:"  # set:lv:{group_id}
SET_LEAVE_CONFIRM = "set:lvc:"  # set:lvc:{group_id}
SET_REMINDER = "set:rem:"  # set:rem:{group_id}
SET_REMINDER_SET = "set:rems:"  # set:rems:{group_id}:{HH:MM|d}
SET_NAME = "set:name"
SET_NOOP = "set:noop"

PAGE_SIZE_MEMBERS = 10
_REMINDER_OPTIONS = (18, 19, 20, 21, 22)


def settings_keyboard(has_admin_groups: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_admin_groups:
        builder.button(text="🎛 Управление группой", callback_data=SET_MANAGE)
    builder.button(text="🔑 Присоединиться к группе", callback_data=CB_ONBOARD_JOIN)
    builder.button(text="👤 Сменить имя", callback_data=SET_NAME)
    builder.button(text="🚪 Выйти из группы", callback_data=SET_LEAVE)
    builder.button(text="🔙 В меню", callback_data=MENU_BACK)
    builder.adjust(1)
    return builder.as_markup()


def admin_group_picker_keyboard(groups: list[Group]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for group in groups:
        builder.button(
            text=f"🎛 {group.name}", callback_data=f"{SET_MANAGE_GROUP}{group.id}"
        )
    builder.button(text="🔙 Назад", callback_data=CB_SETTINGS)
    builder.adjust(1)
    return builder.as_markup()


def management_keyboard(group_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 Участники", callback_data=f"{SET_MEMBERS}{group_id}")
    builder.button(text="📚 Предметы", callback_data=f"{SET_SUBJECTS}{group_id}")
    builder.button(
        text="✏️ Изменить название", callback_data=f"{SET_RENAME_GROUP}{group_id}"
    )
    builder.button(text="🔄 Новый код", callback_data=f"{SET_CODE_ROTATE}{group_id}")
    builder.button(
        text="⏰ Время напоминаний", callback_data=f"{SET_REMINDER}{group_id}"
    )
    builder.button(text="🔙 Выбор группы", callback_data=SET_MANAGE)
    builder.adjust(1)
    return builder.as_markup()


def leave_picker_keyboard(groups: list[Group]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for group in groups:
        builder.button(
            text=f"🚪 {group.name}", callback_data=f"{SET_LEAVE_PICK}{group.id}"
        )
    builder.button(text="🔙 Назад", callback_data=CB_SETTINGS)
    builder.adjust(1)
    return builder.as_markup()


def leave_confirm_keyboard(group_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Да, выйти", callback_data=f"{SET_LEAVE_CONFIRM}{group_id}"
    )
    builder.button(text="🔙 Назад", callback_data=SET_LEAVE)
    builder.adjust(2)
    return builder.as_markup()


def subjects_keyboard(
    group_id: int, subjects: list[Subject]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for subject in subjects:
        builder.row(
            InlineKeyboardButton(
                text=f"✏️ {subject.name}",
                callback_data=f"{SET_SUBJECT_RENAME}{subject.id}",
            ),
            InlineKeyboardButton(
                text="🗑", callback_data=f"{SET_SUBJECT_DELETE}{subject.id}"
            ),
        )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Управление", callback_data=f"{SET_MANAGE_GROUP}{group_id}"
        )
    )
    return builder.as_markup()


def subject_delete_confirm_keyboard(
    group_id: int, subject_id: int, count: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    label = "✅ Да, удалить" if count else "✅ Да, удалить предмет"
    builder.button(
        text=label, callback_data=f"{SET_SUBJECT_DELETE_CONFIRM}{subject_id}"
    )
    builder.button(text="🔙 Предметы", callback_data=f"{SET_SUBJECTS}{group_id}")
    builder.adjust(2)
    return builder.as_markup()


def reminder_time_keyboard(group_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    default = settings.reminder_time.strftime("%H:%M")
    builder.button(
        text=f"⏱ По умолчанию ({default})",
        callback_data=f"{SET_REMINDER_SET}{group_id}:d",
    )
    for hour in _REMINDER_OPTIONS:
        builder.button(
            text=f"{hour:02d}:00",
            callback_data=f"{SET_REMINDER_SET}{group_id}:{hour:02d}:00",
        )
    builder.button(text="🔙 Управление", callback_data=f"{SET_MANAGE_GROUP}{group_id}")
    builder.adjust(1)
    return builder.as_markup()


def members_keyboard(
    group_id: int,
    members: list[tuple[int, str]],
    offset: int,
    total_count: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for user_id, label in members:
        builder.button(
            text=f"👤 {label}",
            callback_data=SET_NOOP,
        )
        builder.button(
            text="🗑",
            callback_data=f"{SET_MEMBER_REMOVE}{group_id}:{user_id}",
        )
        builder.adjust(2)
    builder.button(text="🔙 Управление", callback_data=f"{SET_MANAGE_GROUP}{group_id}")
    if offset > 0:
        builder.button(
            text="◀️",
            callback_data=f"{SET_MEMBER_PAGE}{group_id}:{max(0, offset - PAGE_SIZE_MEMBERS)}",
        )
    if offset + PAGE_SIZE_MEMBERS < total_count:
        builder.button(
            text="▶️",
            callback_data=f"{SET_MEMBER_PAGE}{group_id}:{offset + PAGE_SIZE_MEMBERS}",
        )
    builder.adjust(1)
    return builder.as_markup()


def member_remove_confirm_keyboard(group_id: int, user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Да, удалить",
        callback_data=f"{SET_MEMBER_REMOVE_CONFIRM}{group_id}:{user_id}",
    )
    builder.button(text="🔙 Назад", callback_data=f"{SET_MEMBERS}{group_id}")
    builder.adjust(2)
    return builder.as_markup()
