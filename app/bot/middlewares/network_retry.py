import asyncio
import logging

from aiogram import Bot
from aiogram.client.session.middlewares.base import (
    BaseRequestMiddleware,
    NextRequestMiddlewareType,
)
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import Response, TelegramMethod
from aiogram.methods.base import TelegramType

logger = logging.getLogger(__name__)

_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY = 1.0
_RETRY_MAX_DELAY = 8.0


class RetryOnNetworkError(BaseRequestMiddleware):
    """Повторяет исходящие запросы к Telegram при сетевых сбоях провайдера."""

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Response[TelegramType]:
        attempt = 0
        while True:
            attempt += 1
            try:
                return await make_request(bot, method)
            except TelegramNetworkError as exc:
                if attempt >= _RETRY_ATTEMPTS:
                    raise
                delay = min(
                    _RETRY_BASE_DELAY * (2 ** (attempt - 1)),
                    _RETRY_MAX_DELAY,
                )
                logger.warning(
                    "Сетевой сбой Telegram при %s: %s. "
                    "Повтор (%d/%d) через %.1f с",
                    method.__class__.__name__,
                    exc,
                    attempt,
                    _RETRY_ATTEMPTS,
                    delay,
                )
                await asyncio.sleep(delay)
        raise RuntimeError("unreachable")
