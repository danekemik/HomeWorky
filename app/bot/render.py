from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, Message


async def edit_or_resend(
    message: Message,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
    parse_mode: ParseMode | str | None = None,
) -> None:
    if (
        message.photo
        or message.document
        or message.video
        or message.voice
        or message.audio
        or message.animation
    ):
        try:
            await message.delete()
        except Exception:
            pass
        if parse_mode is None:
            await message.answer(text, reply_markup=markup)
        else:
            await message.answer(text, reply_markup=markup, parse_mode=parse_mode)
        return
    if parse_mode is None:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.edit_text(text, reply_markup=markup, parse_mode=parse_mode)


async def replace_message_at_bottom(
    message: Message,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
    parse_mode: ParseMode | str | None = None,
) -> Message:
    """Ставит меню в конец чата: удаляет старое и шлёт новое сообщение."""
    try:
        await message.delete()
    except Exception:
        pass
    if parse_mode is None:
        return await message.answer(text, reply_markup=markup)
    return await message.answer(text, reply_markup=markup, parse_mode=parse_mode)
