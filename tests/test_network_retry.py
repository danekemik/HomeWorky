from typing import Any

import pytest
from aiogram.exceptions import TelegramNetworkError
from app.bot.middlewares.network_retry import RetryOnNetworkError


def _error() -> TelegramNetworkError:
    return TelegramNetworkError(
        method="sendMessage", message="HTTP Client says - Request timeout error"
    )


async def _success(bot: Any, method: Any) -> str:
    return "ok"


async def _fail_forever(bot: Any, method: Any) -> str:
    raise _error()


async def _fail_twice_then_ok(bot: Any, method: Any) -> str:
    attempts = _fail_twice_then_ok.calls = getattr(
        _fail_twice_then_ok, "calls", 0
    ) + 1
    if attempts <= 2:
        raise _error()
    return "ok"


async def test_retries_and_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    async def sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr("app.bot.middlewares.network_retry.asyncio.sleep", sleep)
    middleware = RetryOnNetworkError()
    _fail_twice_then_ok.calls = 0
    result = await middleware(_fail_twice_then_ok, bot=None, method="m")
    assert result == "ok"
    assert _fail_twice_then_ok.calls == 3


async def test_raises_after_exhausting_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    async def sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr("app.bot.middlewares.network_retry.asyncio.sleep", sleep)
    middleware = RetryOnNetworkError()
    with pytest.raises(TelegramNetworkError):
        await middleware(_fail_forever, bot=None, method="m")


async def test_success_no_extra_calls() -> None:
    middleware = RetryOnNetworkError()
    assert await middleware(_success, bot=None, method="m") == "ok"
