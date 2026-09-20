from datetime import date

from aiogram.types import Document, Message, PhotoSize, User
from app.bot.calendar import build_calendar_markup
from app.bot.formats import esc
from app.bot.handlers.homework import _collect_attachment, _parse_link
from app.database.models import AttachmentType


def _message(**fields: object) -> Message:
    base: dict[str, object] = {
        "message_id": 1,
        "date": date(2026, 9, 20),
        "chat": {"id": 1, "type": "private"},
        "from_user": User(id=1, is_bot=False, first_name="Test"),
    }
    base.update(fields)
    return Message.model_validate(base)


def test_parse_link_only_http() -> None:
    assert _parse_link("https://example.com") == {"url": "https://example.com", "title": None}
    assert _parse_link("http://foo.ru/a") == {"url": "http://foo.ru/a", "title": None}
    assert _parse_link("просто текст") is None
    assert _parse_link("www.example.com") is None


def test_collect_attachment_key_is_telegram_file_id() -> None:
    message = _message(
        document=Document(
            file_id="BQ_ADOC123",
            file_unique_id="u1",
            file_name="ЛР2.pdf",
        )
    )
    item = _collect_attachment(message) or {}
    assert item["telegram_file_id"] == "BQ_ADOC123"
    assert item["file_type"] == AttachmentType.DOCUMENT.value
    assert "file_id" not in item


def test_collect_attachment_photo_uses_largest() -> None:
    message = _message(
        photo=[
            PhotoSize(file_id="small", file_unique_id="s1", width=100, height=100),
            PhotoSize(file_id="large", file_unique_id="l1", width=500, height=500),
        ]
    )
    item = _collect_attachment(message) or {}
    assert item["telegram_file_id"] == "large"
    assert item["file_type"] == AttachmentType.PHOTO.value


def test_calendar_day_callback_format() -> None:
    markup = build_calendar_markup(date(2026, 9, 20))
    buttons = [
        cell.callback_data
        for row in markup.inline_keyboard
        for cell in row
        if cell.callback_data and cell.callback_data.startswith("cal:day:")
    ]
    assert "cal:day:2026-09-20" in buttons
    assert all(len(data) <= 64 for data in buttons)


def test_esc_handles_html_chars() -> None:
    assert esc("Math <3 & stuff > ok") == "Math &lt;3 &amp; stuff &gt; ok"
    assert esc(None) == ""
    assert esc("plain text") == "plain text"
