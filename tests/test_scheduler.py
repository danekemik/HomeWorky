from datetime import date, datetime, timedelta
from datetime import time as dtime
from typing import Any, cast

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from app.config import settings
from app.database.repositories.group_repository import GroupRepository
from app.database.repositories.homework_repository import HomeworkRepository
from app.database.repositories.subject_repository import SubjectRepository
from app.database.repositories.user_repository import UserRepository
from app.database.session import Database as DatabaseType
from app.scheduler import _next_datetime, _send_tomorrow_digests
from app.services.group_service import GroupService

BOT_TOKEN = "123456789:AAEtesttoken1234567890_ABC"


class RecordingSession(BaseSession):
    """Запоминает chat_id всех SendMessage, которые шлёт бот."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[int] = []

    async def close(self) -> None:
        return None

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,  # noqa: ASYNC109
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ):
        raise NotImplementedError
        yield b""

    async def make_request(self, bot: Bot, method, *args, **kwargs):
        if type(method).__name__ == "SendMessage":
            self.sent.append(int(method.chat_id))
        return True


class _FakeDatabase:
    def __init__(self, factory) -> None:
        self.session_factory = factory


async def _creator(session, telegram_id: int):
    return await UserRepository(session).get_or_create(
        telegram_id, username=f"c{telegram_id}", first_name="Староста"
    )


async def _bound_group(session, telegram_id: int, name: str, reminder) -> None:
    creator = await _creator(session, telegram_id)
    group = await GroupService(session).create_group(creator=creator, name=name)
    group.reminder_time = reminder
    group.telegram_chat_id = -1000000 + group.id
    await session.commit()


async def _seed_homework(session, group, deadline: date) -> None:
    creator = await UserRepository(session).get(group.created_by)
    assert creator is not None
    subject = await SubjectRepository(session).create(group.id, "Математика")
    await HomeworkRepository(session).create(
        group_id=group.id,
        subject_id=subject.id,
        author_id=creator.id,
        title="Задание",
        deadline=deadline,
    )


def test_next_datetime_chosen_today_or_tomorrow() -> None:
    tz = settings.tz
    reminder = dtime(20, 0)
    early = datetime(2026, 9, 21, 19, 59, tzinfo=tz)
    assert _next_datetime(early, reminder) == datetime(2026, 9, 21, 20, 0, tzinfo=tz)
    late = datetime(2026, 9, 21, 20, 0, 1, tzinfo=tz)
    assert _next_datetime(late, reminder) == datetime(2026, 9, 22, 20, 0, tzinfo=tz)


async def test_send_tomorrow_digests_due_groups(
    session, session_factory
) -> None:
    now = datetime(2026, 9, 21, 20, 0, 5, tzinfo=settings.tz)
    target = now.date() + timedelta(days=1)
    default = settings.reminder_time

    await _bound_group(session, 7001, "А", default)
    await _bound_group(session, 7002, "Б", dtime(6, 0))
    await _bound_group(session, 7003, "В", None)

    groups = list(await GroupRepository(session).list_all())
    for group in groups:
        await _seed_homework(session, group, target)
    await session.commit()

    # время напоминания уже наступило для всех (никто не получал дайджест сегодня)
    expected = [g.telegram_chat_id for g in groups]

    recording = RecordingSession()
    bot = Bot(token=BOT_TOKEN, session=recording)
    await _send_tomorrow_digests(
        bot,
        cast(DatabaseType, _FakeDatabase(session_factory)),
        now,
        groups,
        settings,
    )

    assert recording.sent == expected
    assert recording.sent  # хотя бы одна группа получила дайджест


async def test_send_tomorrow_digests_skips_future_reminders(
    session, session_factory
) -> None:
    now = datetime(2026, 9, 21, 19, 0, 0, tzinfo=settings.tz)
    target = now.date() + timedelta(days=1)
    default = settings.reminder_time

    await _bound_group(session, 8001, "А", default)
    await _bound_group(session, 8003, "В", None)

    groups = list(await GroupRepository(session).list_all())
    for group in groups:
        await _seed_homework(session, group, target)
    await session.commit()

    # время напоминания ещё не наступило — рассылки быть не должно
    recording = RecordingSession()
    bot = Bot(token=BOT_TOKEN, session=recording)
    await _send_tomorrow_digests(
        bot,
        cast(DatabaseType, _FakeDatabase(session_factory)),
        now,
        groups,
        settings,
    )

    assert recording.sent == []


async def test_send_tomorrow_digests_late_wake_reaches_group(
    session, session_factory
) -> None:
    """Бот проснулся позже запланированного — группа получает дайджест."""
    now = datetime(2026, 9, 21, 21, 30, 0, tzinfo=settings.tz)
    target = now.date() + timedelta(days=1)

    await _bound_group(session, 9501, "А", dtime(20, 0))

    groups = list(await GroupRepository(session).list_all())
    for group in groups:
        await _seed_homework(session, group, target)
    await session.commit()

    recording = RecordingSession()
    bot = Bot(token=BOT_TOKEN, session=recording)
    await _send_tomorrow_digests(
        bot,
        cast(DatabaseType, _FakeDatabase(session_factory)),
        now,
        groups,
        settings,
    )

    assert recording.sent == [groups[0].telegram_chat_id]


async def test_send_tomorrow_digests_does_not_duplicate(
    session, session_factory
) -> None:
    now = datetime(2026, 9, 21, 20, 0, 5, tzinfo=settings.tz)
    target = now.date() + timedelta(days=1)

    await _bound_group(session, 9001, "А", None)

    groups = list(await GroupRepository(session).list_all())
    for group in groups:
        await _seed_homework(session, group, target)
    await session.commit()

    last_sent: dict[int, date] = {groups[0].id: now.date()}

    recording = RecordingSession()
    bot = Bot(token=BOT_TOKEN, session=recording)
    await _send_tomorrow_digests(
        bot,
        cast(DatabaseType, _FakeDatabase(session_factory)),
        now,
        groups,
        settings,
        last_sent=last_sent,
    )

    assert recording.sent == []


async def test_send_tomorrow_digests_empty_day_still_notifies(
    session, session_factory
) -> None:
    """Завтра дедлайнов нет — группа получает сообщение «дедлайнов нет»."""
    now = datetime(2026, 9, 21, 20, 0, 5, tzinfo=settings.tz)

    await _bound_group(session, 9101, "А", None)

    groups = list(await GroupRepository(session).list_all())
    await session.commit()

    recording = RecordingSession()
    bot = Bot(token=BOT_TOKEN, session=recording)
    await _send_tomorrow_digests(
        bot,
        cast(DatabaseType, _FakeDatabase(session_factory)),
        now,
        groups,
        settings,
    )

    assert recording.sent == [groups[0].telegram_chat_id]
