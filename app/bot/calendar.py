from calendar import Calendar
from datetime import date, datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import CALENDAR, FLOW_CANCEL
from app.config import settings
from app.dates import month_nominative, russian_month_name

__all__ = ["build_calendar_markup", "russian_month_name"]


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
    label = f"{month_nominative(cursor.month)} {cursor.year}"
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
    month_start = date(cursor.year, cursor.month, 1)
    min_month = date(today.year, today.month, 1)
    max_month = date(today.year + 1, today.month, 1)
    prev_cb = (
        _prev_period(cursor.year, cursor.month)
        if month_start > min_month
        else f"{CALENDAR}noop"
    )
    next_cb = (
        _next_period(cursor.year, cursor.month)
        if month_start < max_month
        else f"{CALENDAR}noop"
    )
    top = [
        InlineKeyboardButton(text="‹", callback_data=prev_cb),
        InlineKeyboardButton(text=header, callback_data=f"{CALENDAR}noop"),
        InlineKeyboardButton(text="›", callback_data=next_cb),
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
    back = [InlineKeyboardButton(text="🔙 Назад", callback_data=FLOW_CANCEL)]
    return InlineKeyboardMarkup(inline_keyboard=[top, *grid, back])
