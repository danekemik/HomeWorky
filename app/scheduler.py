import asyncio
import logging
from datetime import date, datetime, time, timedelta, tzinfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.config import Settings
from app.database.models import Group
from app.database.repositories.group_repository import GroupRepository
from app.database.session import Database
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


async def run_reminder_loop(bot: Bot, database: Database, cfg: Settings) -> None:
    """Раз в сутки в нужное время рассылает по группам дедлайны на завтра.

    Время напоминания берётся у каждой группы (groups.reminder_time),
    если оно задано, иначе — глобальное REMINDER_TIME из настроек.
    """
    last_cleanup: date | None = None
    last_sent: dict[int, date] = {}
    while True:
        try:
            now = datetime.now(cfg.tz)
            if last_cleanup != now.date():
                await _try_cleanup(database, now.date())
                last_cleanup = now.date()

            groups = await _bound_groups(database)
            if groups:
                target = min(
                    _next_datetime(now, group.reminder_time or cfg.reminder_time)
                    for group in groups
                )
            else:
                target = _next_datetime(now, cfg.reminder_time)
            await _sleep_until(target, cfg.tz)

            now = datetime.now(cfg.tz)
            if last_cleanup != now.date():
                await _try_cleanup(database, now.date())
                last_cleanup = now.date()
            groups = await _bound_groups(database)
            await _try_send(bot, database, now, groups, cfg, last_sent)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Ошибка в цикле напоминаний; продолжим через 60 секунд"
            )
            await asyncio.sleep(60)


async def _try_cleanup(database: Database, today: date) -> None:
    try:
        await _cleanup_expired_homeworks(database, today)
    except Exception:
        logger.exception("Не удалось почистить просроченные задания")


async def _try_send(
    bot: Bot,
    database: Database,
    now: datetime,
    groups: list[Group],
    cfg: Settings,
    last_sent: dict[int, date],
) -> None:
    try:
        await _send_tomorrow_digests(bot, database, now, groups, cfg, last_sent)
    except Exception:
        logger.exception("Не удалось выполнить вечернюю рассылку")


def _next_datetime(now: datetime, reminder: time) -> datetime:
    """Ближайшее будущее время запуска относительно now (сегодня или завтра)."""
    scheduled = datetime.combine(now.date(), reminder, tzinfo=now.tzinfo)
    if scheduled <= now:
        scheduled += timedelta(days=1)
    return scheduled


async def _bound_groups(database: Database) -> list[Group]:
    """Группы, к которым привязан Telegram-чат (туда приходят напоминания)."""
    async with database.session_factory() as session:
        return [
            group
            for group in await GroupRepository(session).list_all()
            if group.telegram_chat_id is not None
        ]


async def _sleep_until(target: datetime, tz: tzinfo) -> None:
    delta = (target - datetime.now(tz)).total_seconds()
    if delta > 0:
        await asyncio.sleep(delta)


async def _send_tomorrow_digests(
    bot: Bot,
    database: Database,
    now: datetime,
    groups: list[Group],
    cfg: Settings,
    last_sent: dict[int, date] | None = None,
) -> None:
    """Шлёт дайджест группам, чьё время напоминания уже наступило.

    last_sent защищает от повторной рассылки одной группе в течение суток
    (например, если цикл проснулся позже запланированного времени).
    """
    last_sent = last_sent or {}
    target = now.date() + timedelta(days=1)
    due = (now.hour, now.minute)
    async with database.session_factory() as session:
        service = NotificationService(session)
        for group in groups:
            scheduled = group.reminder_time or cfg.reminder_time
            if due < (scheduled.hour, scheduled.minute):
                continue
            if last_sent.get(group.id) == now.date():
                continue
            try:
                items = await service.collect_digest(group.id, target)
                if group.telegram_chat_id is None:
                    continue
                text = service.build_digest_text(target, items)
                if not text:
                    text = service.build_empty_text(target)
                await bot.send_message(group.telegram_chat_id, text)
                last_sent[group.id] = now.date()
                await asyncio.sleep(0.05)
            except TelegramAPIError as exc:
                logger.warning(
                    "Не удалось отправить напоминание группе %s: %s",
                    group.id,
                    exc,
                )
            except Exception:
                logger.exception(
                    "Ошибка при формировании напоминания для группы %s",
                    group.id,
                )


async def _cleanup_expired_homeworks(database: Database, today: date) -> None:
    """Удаляет задания, после дедлайна которых прошла неделя."""
    from app.database.repositories.homework_repository import HomeworkRepository

    cut_off = today - timedelta(days=7)
    async with database.session_factory() as session:
        deleted = await HomeworkRepository(session).delete_expired(cut_off)
        await session.commit()
        if deleted:
            logger.info("Удалено просроченных заданий: %s", deleted)
