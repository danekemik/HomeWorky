import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, ErrorEvent, Message, TelegramObject

from app.bot.handlers import group_events, homework, menu, settings, start, statistics, views
from app.bot.middlewares.db import DatabaseSessionMiddleware
from app.bot.middlewares.user import UserContextMiddleware
from app.database.session import Database

logger = logging.getLogger(__name__)

HandlerType = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


def create_bot(token: str) -> Bot:
    return Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def create_dispatcher(database: Database) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.update.middleware(DatabaseSessionMiddleware(database))
    dispatcher.update.middleware(UserContextMiddleware())
    dispatcher.include_router(start.router)
    dispatcher.include_router(homework.router)
    dispatcher.include_router(views.router)
    dispatcher.include_router(statistics.router)
    dispatcher.include_router(settings.router)
    dispatcher.include_router(group_events.router)
    dispatcher.include_router(menu.router)
    dispatcher.errors.register(global_error_handler)
    return dispatcher


async def global_error_handler(
    event: ErrorEvent, data: dict[str, Any] | None = None
) -> None:
    logger.error(
        "Unhandled update error",
        exc_info=(
            type(event.exception),
            event.exception,
            event.exception.__traceback__,
        ),
    )
    inner = event.update.event
    try:
        if isinstance(inner, CallbackQuery):
            await inner.answer(
                "Произошла ошибка. Попробуй ещё раз.", show_alert=True
            )
        elif isinstance(inner, Message):
            await inner.answer("Произошла ошибка. Попробуй ещё раз.")
    except Exception:
        logger.exception("Failed to notify the user about an error")
