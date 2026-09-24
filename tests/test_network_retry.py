from typing import Any

import pytest
from aiogram.exceptions import TelegramNetworkError
from app.bot.middlewares.network_retry import RetryOnNetworkError


class EditMessageText:
    """Идемпотентный метод — сетевые ошибки допустимо повторять."""


class SendMessage:
    """Неидемпотентный метод — на сетевой ошибке повторять нельзя."""


def _error() -> TelegramNetworkError:
    return TelegramNetworkError(
        method="sendMessage", message="HTTP Client says - Request timeout error"
    )


async def _success(bot: Any, method: Any) -> str:
    return "ok"


async def _fail_forever(bot: Any, method: Any) -> str:
    raise _error()


async def _fail_twice_then_ok(bot: Any, method: Any) -> str:
    attempts = _fail_twice_then_ok.calls = getattr(_fail_twice_then_ok, "calls", 0) + 1
    if attempts <= 2:
        raise _error()
    return "ok"


async def _counted_fail(bot: Any, method: Any) -> str:
    _counted_fail.calls = getattr(_counted_fail, "calls", 0) + 1
    raise _error()


async def test_retries_and_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    async def sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr("app.bot.middlewares.network_retry.asyncio.sleep", sleep)
    middleware = RetryOnNetworkError()
    _fail_twice_then_ok.calls = 0
    result = await middleware(_fail_twice_then_ok, bot=None, method=EditMessageText())
    assert result == "ok"
    assert _fail_twice_then_ok.calls == 3


async def test_raises_after_exhausting_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    async def sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr("app.bot.middlewares.network_retry.asyncio.sleep", sleep)
    middleware = RetryOnNetworkError()
    with pytest.raises(TelegramNetworkError):
        await middleware(_fail_forever, bot=None, method=EditMessageText())


async def test_non_idempotent_network_error_not_retried() -> None:
    middleware = RetryOnNetworkError()
    _counted_fail.calls = 0
    with pytest.raises(TelegramNetworkError):
        await middleware(_counted_fail, bot=None, method=SendMessage())
    assert _counted_fail.calls == 1


async def test_success_no_extra_calls() -> None:
    middleware = RetryOnNetworkError()
    assert await middleware(_success, bot=None, method=SendMessage()) == "ok"
