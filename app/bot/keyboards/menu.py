from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import MENU_BACK
from app.bot.formats import clamp_button_text
from app.database.models import Group

CB_ADD_HOMEWORK = "menu:add_homework"
CB_NEAREST_DEADLINES = "menu:nearest"
CB_ALL_TASKS = "menu:all_tasks"
CB_STATS = "menu:stats"
CB_SETTINGS = "menu:settings"

CB_PICK_GROUP_PREFIX = "pick:"

CB_ONBOARD_CREATE = "onb:create"
CB_ONBOARD_JOIN = "onb:join"
CB_JOIN_PICK = "join:"


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить ДЗ", callback_data=CB_ADD_HOMEWORK)
    builder.button(text="🔥 Ближайшие дедлайны", callback_data=CB_NEAREST_DEADLINES)
    builder.button(text="🗂 Все задания", callback_data=CB_ALL_TASKS)
    builder.button(text="📊 Статистика", callback_data=CB_STATS)
    builder.button(text="⚙️ Настройки", callback_data=CB_SETTINGS)
    builder.adjust(1)
    return builder.as_markup()


def onboarding_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать группу", callback_data=CB_ONBOARD_CREATE)
    builder.button(text="🔑 Присоединиться к группе", callback_data=CB_ONBOARD_JOIN)
    builder.adjust(1)
    return builder.as_markup()


def onboarding_no_join_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать группу", callback_data=CB_ONBOARD_CREATE)
    builder.button(text="🔙 В меню", callback_data=MENU_BACK)
    builder.adjust(1)
    return builder.as_markup()


def group_picker_keyboard(groups: list[Group]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for group in groups:
        builder.button(
            text=clamp_button_text(f"🎓 {group.name}"),
            callback_data=f"{CB_PICK_GROUP_PREFIX}{group.id}",
        )
    builder.adjust(1)
    return builder.as_markup()


def join_group_picker_keyboard(
    groups: list[Group], back_callback: str = MENU_BACK
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for group in groups:
        builder.button(
            text=clamp_button_text(f"🎓 {group.name}"),
            callback_data=f"{CB_JOIN_PICK}{group.id}",
        )
    builder.button(
        text=("🔙 В меню" if back_callback == MENU_BACK else "🔙 Назад"),
        callback_data=back_callback,
    )
    builder.adjust(1)
    return builder.as_markup()
