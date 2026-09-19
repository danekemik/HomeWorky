import asyncio
import logging
from datetime import date, datetime, timedelta, tzinfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.config import Settings
from app.database.repositories.group_repository import GroupRepository
from app.database.session import Database
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


async def run_reminder_loop(bot: Bot, database: Database, cfg: Settings) -> None:
    """Раз в сутки в REMINDER_TIME рассылает по группам дедлайны на завтра."""
    while True:
        now = datetime.now(cfg.tz)
        target_time = datetime.combine(
            now.date(), cfg.reminder_time, tzinfo=cfg.tz
        )
        if now < target_time:
            await _sleep_until(target_time, cfg.tz)

        await _send_tomorrow_digests(bot, database, now.date())

        next_day = now.date() + timedelta(days=1)
        next_target = datetime.combine(
            next_day, cfg.reminder_time, tzinfo=cfg.tz
        )
        await _sleep_until(next_target, cfg.tz)


async def _sleep_until(target: datetime, tz: tzinfo) -> None:
    delta = (target - datetime.now(tz)).total_seconds()
    if delta > 0:
        await asyncio.sleep(delta)


async def _send_tomorrow_digests(bot: Bot, database: Database, today: date) -> None:
    async with database.session_factory() as session:
        groups = await GroupRepository(session).list_all()
        target = today + timedelta(days=1)
        service = NotificationService(session)
        for group in groups:
            items = await service.collect_digest(group.id, target)
            text = service.build_digest_text(target, items)
            if not text:
                continue
            try:
                await bot.send_message(group.telegram_chat_id, text)
                await asyncio.sleep(0.05)
            except TelegramAPIError as exc:
                logger.warning(
                    "Не удалось отправить напоминание группе %s: %s",
                    group.id,
                    exc,
                )
