import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats

from app.bot.main import create_bot, create_dispatcher
from app.config import settings
from app.database.session import Database
from app.scheduler import run_reminder_loop


def configure_logging() -> None:
    logging.basicConfig(
        level=settings.LOG_LEVEL.upper(),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )


async def _register_commands(bot: Bot) -> None:
    try:
        await bot.set_my_commands(
            [
                BotCommand(command="menu", description="🏠 Открыть меню"),
                BotCommand(command="start", description="🚀 Перезапустить бота"),
                BotCommand(command="help", description="❓ Помощь"),
            ],
            scope=BotCommandScopeAllPrivateChats(),
        )
    except TelegramNetworkError:
        logging.warning(
            "Не удалось зарегистрировать команды меню (сеть недоступна), продолжаю без них"
        )


async def main() -> None:
    configure_logging()
    database = Database(settings.DATABASE_URL)
    bot = create_bot(settings.BOT_TOKEN)
    dispatcher = create_dispatcher(database, redis_url=settings.REDIS_URL)
    reminder_task = asyncio.create_task(
        run_reminder_loop(bot, database, settings)
    )
    commands_task = asyncio.create_task(_register_commands(bot))
    try:
        await dispatcher.start_polling(bot)
    finally:
        commands_task.cancel()
        reminder_task.cancel()
        for task in (commands_task, reminder_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
        await database.dispose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
