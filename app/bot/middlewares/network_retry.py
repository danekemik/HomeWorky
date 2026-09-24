import asyncio
import logging
import random

from aiogram import Bot
from aiogram.client.session.middlewares.base import (
    BaseRequestMiddleware,
    NextRequestMiddlewareType,
)
from aiogram.exceptions import TelegramNetworkError, TelegramServerError
from aiogram.methods import Response, TelegramMethod
from aiogram.methods.base import TelegramType

logger = logging.getLogger(__name__)

_RETRY_ATTEMPTS = 8
_RETRY_BASE_DELAY = 0.5
_RETRY_MAX_DELAY = 20.0
_RETRY_JITTER = 0.2

_RETRYABLE = (TelegramNetworkError, TelegramServerError)


class RetryOnNetworkError(BaseRequestMiddleware):
    """Повторяет исходящие запросы к Telegram при сетевых сбоях и 5xx."""

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
            except _RETRYABLE as exc:
                if attempt >= _RETRY_ATTEMPTS:
                    raise
                delay = min(
                    _RETRY_BASE_DELAY * (2 ** (attempt - 1)),
                    _RETRY_MAX_DELAY,
                )
                jitter = delay * random.uniform(0, _RETRY_JITTER)
                logger.warning(
                    "Сетевой сбой Telegram при %s: %s. "
                    "Повтор (%d/%d) через %.1f с",
                    method.__class__.__name__,
                    exc,
                    attempt,
                    _RETRY_ATTEMPTS,
                    delay + jitter,
                )
                await asyncio.sleep(delay + jitter)
        raise RuntimeError("unreachable")
