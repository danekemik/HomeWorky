from aiogram.types import InlineKeyboardMarkup, Message


async def edit_or_resend(
    message: Message,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
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
        await message.answer(text, reply_markup=markup)
        return
    await message.edit_text(text, reply_markup=markup)
