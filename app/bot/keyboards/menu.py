from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.models import Group

CB_ADD_HOMEWORK = "menu:add_homework"
CB_NEAREST_DEADLINES = "menu:nearest"
CB_ALL_TASKS = "menu:all_tasks"
CB_STATS = "menu:stats"
CB_SETTINGS = "menu:settings"

CB_PICK_GROUP_PREFIX = "pick:"


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить ДЗ", callback_data=CB_ADD_HOMEWORK)
    builder.button(text="🔥 Ближайшие дедлайны", callback_data=CB_NEAREST_DEADLINES)
    builder.button(text="🗂 Все задания", callback_data=CB_ALL_TASKS)
    builder.button(text="📊 Статистика", callback_data=CB_STATS)
    builder.button(text="⚙️ Настройки", callback_data=CB_SETTINGS)
    builder.adjust(1)
    return builder.as_markup()


def group_picker_keyboard(groups: list[Group]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for group in groups:
        label = group.title or f"Группа #{group.id}"
        builder.button(text=label, callback_data=f"{CB_PICK_GROUP_PREFIX}{group.id}")
    builder.adjust(1)
    return builder.as_markup()
