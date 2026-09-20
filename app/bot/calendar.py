from calendar import Calendar
from datetime import date, datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import CALENDAR
from app.config import settings

_MONTHS_NOMINATIVE = (
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
)

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


_TITLE_WIDTH = 17
_ZJ = "\u200d"


def _month_header(cursor: date) -> str:
    label = f"{_MONTHS_NOMINATIVE[cursor.month - 1]} {cursor.year}"
    pad = max(0, _TITLE_WIDTH - len(label))
    left, right = pad // 2, pad - pad // 2
    return f"{_ZJ}{' ' * left}{label}{' ' * right}{_ZJ}"


def _available_days(cursor: date, today: date) -> list[date]:
    return [
        day
        for week in Calendar(firstweekday=0).monthdatescalendar(cursor.year, cursor.month)
        for day in week
        if day.month == cursor.month and day >= today
    ]


def build_calendar_markup(
    cursor: date, today: date | None = None
) -> InlineKeyboardMarkup:
    today = today or datetime.now(settings.tz).date()
    header = _month_header(cursor)
    top = [
        InlineKeyboardButton(text="‹", callback_data=_prev_period(cursor.year, cursor.month)),
        InlineKeyboardButton(text=header, callback_data=f"{CALENDAR}noop"),
        InlineKeyboardButton(text="›", callback_data=_next_period(cursor.year, cursor.month)),
    ]
    days = _available_days(cursor, today)
    grid = [
        [
            InlineKeyboardButton(
                text=str(day.day),
                callback_data=f"{CALENDAR}day:{day.isoformat()}",
            )
            for day in days[i : i + 7]
        ]
        for i in range(0, len(days), 7)
    ]
    return InlineKeyboardMarkup(inline_keyboard=[top, *grid])


def russian_month_name(month: int) -> str:
    return _MONTHS_GENITIVE[month - 1]
