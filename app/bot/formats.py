from datetime import date, datetime
from html import escape as _escape

from app.bot.calendar import russian_month_name
from app.config import settings
from app.services.notification_service import format_deadline


def esc(value: str | None) -> str:
    return _escape(value or "", quote=False)


_BUTTON_TEXT_LIMIT = 60


def clamp_button_text(value: str, limit: int = _BUTTON_TEXT_LIMIT) -> str:
    """Ограничивает текст кнопки (лимит Telegram — 64 символа)."""
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


def safe_int(value: str | None) -> int | None:
    """Возвращает int или None вместо исключения на битых callback_data."""
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def bot_today() -> date:
    return datetime.now(settings.tz).date()


def format_date_russian(deadline: date) -> str:
    return f"{deadline.day} {russian_month_name(deadline.month)}"


def format_homework_label(subject: str, title: str, deadline: date) -> str:
    return f"📅 {format_deadline(deadline)} · {subject} — {title}"


def plural_files(count: int) -> str:
    """Склонение: 1 файл, 3 файла, 5 файлов, 21 файл, 24 файла."""
    if 11 <= count % 100 <= 14:
        return "файлов"
    last = count % 10
    if last == 1:
        return "файл"
    if 2 <= last <= 4:
        return "файла"
    return "файлов"


def build_homework_card(
    *,
    subject: str,
    title: str,
    deadline: date,
    description: str | None = None,
    author_name: str | None = None,
    attachment_count: int | None = None,
    link_lines: list[str] | None = None,
    header: str | None = None,
    footer_note: str | None = None,
) -> str:
    lines: list[str] = []
    if header:
        lines += [f"<b>{esc(header)}</b>", ""]
    lines += [f"📖 {esc(subject.upper())}", "", f"🎯 {esc(title)}"]
    if description:
        lines += ["", f"📝 {esc(description)}"]
    lines += ["", f"📅 {format_date_russian(deadline)}"]
    if attachment_count:
        word = plural_files(attachment_count)
        lines += ["", f"📎 {attachment_count} {word}"]
    links = link_lines or []
    if links:
        lines += ["", "🔗 Ссылки:"]
        lines += [f"  • {esc(line)}" for line in links]
    if author_name:
        lines += ["", f"👤 Добавил: {esc(author_name)}"]
    if footer_note:
        lines += ["", esc(footer_note)]
    return "\n".join(lines)
