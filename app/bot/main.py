import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, ErrorEvent, Message, TelegramObject

from app.bot.handlers import group_events, homework, menu, settings, start, statistics, views
from app.bot.middlewares.db import DatabaseSessionMiddleware
from app.bot.middlewares.network_retry import RetryOnNetworkError
from app.bot.middlewares.throttling import ThrottlingMiddleware
from app.bot.middlewares.user import UserContextMiddleware
from app.config import settings as bot_settings
from app.database.session import Database

logger = logging.getLogger(__name__)

HandlerType = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]

fallback_router = Router(name="fallback")


@fallback_router.callback_query()
async def on_unknown_callback(query: CallbackQuery) -> None:
    """Глотает callback'и от устаревших/чужих клавиатур — снимает «спиннер»."""
    await query.answer()

# Безобидные ошибки Telegram при повторных тапах / устаревших сообщениях,
# которые не стоит показывать пользователю тревожным алертом.
_BENIGN_BAD_REQUESTS = (
    "message is not modified",
    "message not found",
    "there is no text in the message to edit",
    "message can't be edited",
)


def create_bot(token: str) -> Bot:
    session = AiohttpSession(
        timeout=bot_settings.TELEGRAM_REQUEST_TIMEOUT,
        proxy=bot_settings.TELEGRAM_PROXY,
    )
    bot = Bot(
        token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    bot.session.middleware.register(RetryOnNetworkError())
    return bot


def create_storage(redis_url: str | None) -> Any:
    if redis_url:
        from aiogram.fsm.storage.redis import RedisStorage
        from redis.asyncio import Redis

        client = Redis.from_url(redis_url, decode_responses=True)
        return RedisStorage(redis=client)
    return MemoryStorage()


def create_dispatcher(database: Database, redis_url: str | None = None) -> Dispatcher:
    dispatcher = Dispatcher(storage=create_storage(redis_url))
    dispatcher.update.middleware(ThrottlingMiddleware())
    dispatcher.update.middleware(DatabaseSessionMiddleware(database))
    dispatcher.update.middleware(UserContextMiddleware())
    dispatcher.include_router(start.router)
    dispatcher.include_router(homework.router)
    dispatcher.include_router(views.router)
    dispatcher.include_router(statistics.router)
    dispatcher.include_router(settings.router)
    dispatcher.include_router(group_events.router)
    dispatcher.include_router(menu.router)
    dispatcher.include_router(fallback_router)
    dispatcher.errors.register(global_error_handler)
    return dispatcher


async def global_error_handler(
    event: ErrorEvent, data: dict[str, Any] | None = None
) -> None:
    inner = event.update.event
    if isinstance(event.exception, TelegramBadRequest):
        message = (getattr(event.exception, "message", "") or "").lower()
        if any(token in message for token in _BENIGN_BAD_REQUESTS):
            if isinstance(inner, CallbackQuery):
                try:
                    await inner.answer()
                except Exception:
                    pass
            return
    logger.error(
        "Unhandled update error",
        exc_info=(
            type(event.exception),
            event.exception,
            event.exception.__traceback__,
        ),
    )
    state = (data or {}).get("state")
    if state is not None:
        try:
            await state.clear()
        except Exception:
            logger.exception("Failed to clear FSM state after an error")
    try:
        if isinstance(inner, CallbackQuery):
            await inner.answer(
                "Произошла ошибка. Попробуй ещё раз.", show_alert=True
            )
        elif isinstance(inner, Message):
            await inner.answer("Произошла ошибка. Попробуй ещё раз.")
    except Exception:
        logger.exception("Failed to notify the user about an error")
