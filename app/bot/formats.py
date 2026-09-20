from datetime import date, datetime
from html import escape as _escape

from app.bot.calendar import russian_month_name
from app.config import settings
from app.services.notification_service import format_deadline


def esc(value: str | None) -> str:
    return _escape(value or "", quote=False)


def bot_today() -> date:
    return datetime.now(settings.tz).date()


def format_date_russian(deadline: date) -> str:
    return f"{deadline.day} {russian_month_name(deadline.month)}"


def format_homework_label(subject: str, title: str, deadline: date) -> str:
    return f"📅 {format_deadline(deadline)} · {subject} — {title}"


def build_homework_card(
    *,
    subject: str,
    title: str,
    deadline: date,
    description: str | None = None,
    author_name: str | None = None,
    attachment_lines: list[str] | None = None,
    link_lines: list[str] | None = None,
    footer_note: str | None = None,
) -> str:
    lines = [f"📚 {esc(subject)}", "", f"💻 {esc(title)}"]
    if description:
        lines += ["", f"📝 {esc(description)}"]
    lines += ["", f"📅 Дедлайн: {format_date_russian(deadline)}"]
    if author_name:
        lines.append(f"👤 Добавил: {esc(author_name)}")
    attachments = attachment_lines or []
    if attachments:
        lines += ["", "📎 Файлы:"]
        lines += [f"  • {esc(line)}" for line in attachments]
    links = link_lines or []
    if links:
        lines += ["", "🔗 Ссылки:"]
        lines += [f"  • {esc(line)}" for line in links]
    if footer_note:
        lines += ["", esc(footer_note)]
    return "\n".join(lines)
