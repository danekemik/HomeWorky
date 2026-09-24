from datetime import date

from aiogram.types import Document, Message, PhotoSize, User
from app.bot.calendar import build_calendar_markup
from app.bot.formats import clamp_button_text, esc, safe_int
from app.bot.handlers.homework import _collect_attachment
from app.bot.handlers.settings import _page_args
from app.database.models import AttachmentType
from app.dates import russian_month_name_short


def _message(**fields: object) -> Message:
    base: dict[str, object] = {
        "message_id": 1,
        "date": date(2026, 9, 20),
        "chat": {"id": 1, "type": "private"},
        "from_user": User(id=1, is_bot=False, first_name="Test"),
    }
    base.update(fields)
    return Message.model_validate(base)


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


def _link_message(text: str, *, url: str | None = None) -> Message:
    base: dict[str, object] = {
        "message_id": 1,
        "date": date(2026, 9, 20),
        "chat": {"id": 1, "type": "private"},
        "from_user": User(id=1, is_bot=False, first_name="Test"),
        "text": text,
        "entities": [
            {
                "type": "text_link" if url else "url",
                "offset": 0,
                "length": len(text),
                **({"url": url} if url else {}),
            }
        ],
    }
    return Message.model_validate(base)


def test_extract_link_with_scheme_preserved() -> None:
    from app.bot.handlers.homework import _extract_link

    message = _link_message("https://example.com/file")
    assert _extract_link(message) == "https://example.com/file"


def test_extract_link_bare_url_gets_https_scheme() -> None:
    from app.bot.handlers.homework import _extract_link

    message = _link_message("example.com/file")
    assert _extract_link(message) == "https://example.com/file"


def test_extract_link_text_link_without_scheme_normalized() -> None:
    from app.bot.handlers.homework import _extract_link

    message = _link_message("клик", url="t.me/example")
    assert _extract_link(message) == "https://t.me/example"


def test_calendar_day_callback_format() -> None:
    markup = build_calendar_markup(
        date(2026, 9, 20), today=date(2026, 9, 18)
    )
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


def test_safe_int_parses_and_rejects_bad_values() -> None:
    assert safe_int("42") == 42
    assert safe_int("-7") == -7
    assert safe_int(None) is None
    assert safe_int("abc") is None
    assert safe_int("") is None
    assert safe_int("12abc") is None


def test_russian_month_name_short_forms() -> None:
    assert russian_month_name_short(1) == "янв."
    assert russian_month_name_short(9) == "сент."
    assert russian_month_name_short(12) == "дек."


def test_clamp_button_text_short_unchanged() -> None:
    short = "📚 Математика"
    assert clamp_button_text(short) == short


def test_clamp_button_text_truncates_long_value() -> None:
    clamped = clamp_button_text("📚 " + "я" * 100)
    assert len(clamped) == 60
    assert clamped.endswith("…")
    assert clamped.startswith("📚 ")


def test_clamp_button_text_custom_limit() -> None:
    assert clamp_button_text("abcdef", limit=4) == "abc…"


def test_page_args_parses_group_and_offset() -> None:
    assert _page_args("set:trpg:12:20", "set:trpg:") == (12, 20)
    assert _page_args("set:mpage:7:30", "set:mpage:") == (7, 30)
    assert _page_args("set:mpage:7", "set:mpage:") is None
    assert _page_args("set:mpage:x:1", "set:mpage:") is None


def test_calendar_nav_bounds_not_before_current_month() -> None:
    today = date(2026, 9, 18)
    markup = build_calendar_markup(date(2026, 9, 1), today=today)
    prev_btn, _, next_btn = markup.inline_keyboard[0]
    assert prev_btn.callback_data == "cal:noop"
    assert next_btn.callback_data != "cal:noop"


def test_calendar_nav_bounds_not_after_one_year() -> None:
    today = date(2026, 9, 18)
    markup = build_calendar_markup(date(2027, 9, 1), today=today)
    prev_btn, _, next_btn = markup.inline_keyboard[0]
    assert prev_btn.callback_data != "cal:noop"
    assert next_btn.callback_data == "cal:noop"
