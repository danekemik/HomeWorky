import asyncio
import logging

from app.bot.main import create_bot, create_dispatcher
from app.config import settings
from app.database.session import Database
from app.scheduler import run_reminder_loop


def configure_logging() -> None:
    logging.basicConfig(
        level=settings.LOG_LEVEL.upper(),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )


async def main() -> None:
    configure_logging()
    database = Database(settings.DATABASE_URL)
    bot = create_bot(settings.BOT_TOKEN)
    dispatcher = create_dispatcher(database)
    reminder_task = asyncio.create_task(
        run_reminder_loop(bot, database, settings)
    )
    try:
        await dispatcher.start_polling(bot)
    finally:
        reminder_task.cancel()
        try:
            await reminder_task
        except asyncio.CancelledError:
            pass
        await database.dispose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
