from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import MENU_BACK
from app.bot.keyboards.menu import CB_ONBOARD_JOIN, CB_SETTINGS
from app.database.models import Group

SET_MANAGE = "set:manage"
SET_MANAGE_GROUP = "set:mng:"  # set:mng:{group_id}
SET_MEMBERS = "set:members:"  # set:members:{group_id}
SET_MEMBER_PAGE = "set:mpage:"  # set:mpage:{group_id}:{offset}
SET_MEMBER_REMOVE = "set:rm:"  # set:rm:{group_id}:{user_id}
SET_MEMBER_REMOVE_CONFIRM = "set:rmc:"  # set:rmc:{group_id}:{user_id}
SET_CODE_ROTATE = "set:code:"  # set:code:{group_id}
SET_NAME = "set:name"

PAGE_SIZE_MEMBERS = 10


def settings_keyboard(has_admin_groups: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_admin_groups:
        builder.button(text="🎛 Управление группой", callback_data=SET_MANAGE)
    builder.button(text="🔑 Присоединиться к группе", callback_data=CB_ONBOARD_JOIN)
    builder.button(text="👤 Сменить имя", callback_data=SET_NAME)
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
    builder.button(text="🔄 Новый код", callback_data=f"{SET_CODE_ROTATE}{group_id}")
    builder.button(text="🔙 Выбор группы", callback_data=SET_MANAGE)
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
            callback_data="set:noop",
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
