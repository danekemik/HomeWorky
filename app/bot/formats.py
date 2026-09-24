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


FOLDER_HEADER = "🐹 *Homy открывает папку*"

_FOLDER_EMPTY_NOTE = "Тут пока пусто — никто ещё не добавлял вложения."


def clamp_file_name(name: str, limit: int = 40) -> str:
    """Сокращает имя файла, сохраняя расширение (если оно короткое)."""
    name = (name or "").strip()
    if len(name) <= limit:
        return name
    ext = ""
    dot = name.rfind(".")
    candidate = name[dot:] if dot != -1 else ""
    if 0 < len(candidate) <= 10:
        ext = candidate
        name = name[:dot]
    head = name[: max(0, limit - 1 - len(ext))]
    return head + "…" + ext


def photo_label(index: int) -> str:
    """Отображаемое имя фото: IMG000.jpg, IMG001.jpg, ..."""
    return f"IMG{index:03d}.jpg"


def link_label(url: str, title: str | None, limit: int = 50) -> str:
    text = (title or url).strip()
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        text = text.split("://", 1)[1]
    return clamp_file_name(text, limit=limit)


def link_html(url: str, label: str, author: str | None) -> str:
    """Кликабельная ссылка вида <a href=...>label</a> — автор."""
    href = _escape(url or "", quote=True)
    rendered = f'<a href="{href}">{esc(label)}</a>'
    if author:
        rendered += f" — {esc(author)}"
    return rendered


def build_folder_card(
    *,
    photo_lines: list[str],
    file_lines: list[str],
    link_lines: list[str],
) -> str:
    """Сообщение «папки»: секции ФОТО/ФАЙЛЫ/ССЫЛКИ, только непустые."""
    parts: list[str] = []
    if photo_lines:
        parts += ["📷 ФОТО", *[f"• {line}" for line in photo_lines], ""]
    if file_lines:
        parts += ["📄 ФАЙЛЫ", *[f"• {line}" for line in file_lines], ""]
    if link_lines:
        parts += ["🔗 ССЫЛКИ", *[f"• {line}" for line in link_lines], ""]
    body = "\n".join(parts).rstrip()
    if not parts:
        body = _FOLDER_EMPTY_NOTE
    return f"{FOLDER_HEADER}\n{body}"


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
        lines.append(esc(header))
    lines.append(f"📖 {esc(subject.upper())}")
    lines += ["", f"🎯 {esc(title)}"]
    if description:
        lines.append(f"📝 {esc(description)}")
    lines += ["", f"📅 {format_date_russian(deadline)}"]
    if attachment_count:
        word = plural_files(attachment_count)
        lines.append(f"📎 {attachment_count} {word}")
    links = link_lines or []
    if links:
        lines += ["🔗 Ссылки:"]
        lines += [f"  • {esc(line)}" for line in links]
    if author_name:
        lines.append(f"👤 Добавил: {esc(author_name)}")
    if footer_note:
        lines.append(esc(footer_note))
    return "\n".join(lines)
