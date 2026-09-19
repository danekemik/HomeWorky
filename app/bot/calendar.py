from calendar import Calendar
from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import CALENDAR

_MONTHS_GENITIVE = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)

_WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


def _nav_callback(year: int, month: int) -> str:
    return f"{CALENDAR}nav:{year:04d}-{month:02d}"


def _prev_period(year: int, month: int) -> str:
    if month == 1:
        return _nav_callback(year - 1, 12)
    return _nav_callback(year, month - 1)


def _next_period(year: int, month: int) -> str:
    if month == 12:
        return _nav_callback(year + 1, 1)
    return _nav_callback(year, month + 1)


def build_calendar_markup(cursor: date, today: date | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    header = f"{cursor.year} · {cursor.month:02d}"
    builder.row(
        InlineKeyboardButton(text="‹", callback_data=_prev_period(cursor.year, cursor.month)),
        InlineKeyboardButton(text=header, callback_data=f"{CALENDAR}noop"),
        InlineKeyboardButton(text="›", callback_data=_next_period(cursor.year, cursor.month)),
    )
    builder.row(
        *(InlineKeyboardButton(text=day, callback_data=f"{CALENDAR}noop") for day in _WEEKDAYS)
    )
    for week in Calendar(firstweekday=0).monthdatescalendar(cursor.year, cursor.month):
        for day in week:
            if day.month != cursor.month:
                builder.add(InlineKeyboardButton(text="·", callback_data=f"{CALENDAR}noop"))
                continue
            label = f"·{day.day}·" if today is not None and day == today else str(day.day)
            builder.add(
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"{CALENDAR}day:{day.isoformat()}",
                )
            )
        builder.adjust(7)
    return builder.as_markup()


def russian_month_name(month: int) -> str:
    return _MONTHS_GENITIVE[month - 1]


def build_deadline_keyboard(cursor: date, today: date | None = None) -> InlineKeyboardMarkup:
    return build_calendar_markup(cursor, today)
