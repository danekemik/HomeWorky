from datetime import date
from typing import Any

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message
from app.bot.handlers import homework as homework_handlers
from app.bot.handlers import menu as menu_handlers
from app.bot.states.group_flow import GroupFlow
from app.bot.states.homework import HomeworkCreation
from app.database.repositories.group_repository import GroupRepository
from app.database.repositories.homework_repository import HomeworkRepository
from app.database.repositories.subject_repository import SubjectRepository
from app.database.repositories.user_repository import UserRepository
from app.services.group_service import GroupService
from app.services.homework_service import HomeworkService

BOT_TOKEN = "123456789:AAEtesttoken1234567890_ABC"
FUTURE_DAY = date(2099, 9, 25)


class StubSession(BaseSession):
    """Перехватывает вызовы Telegram API и возвращает заготовки."""

    def __init__(self) -> None:
        super().__init__()
        self.methods: list[object] = []

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

    async def make_request(self, bot, method, *args, **kwargs):
        self.methods.append(method)
        name = type(method).__name__
        if name in {"EditMessageText", "SendMessage", "SendPhoto", "SendDocument"}:
            return _message(bot, method.chat_id if hasattr(method, "chat_id") else 1)
        return True

    def texts(self) -> list[str]:
        return [
            getattr(method, "text", "")
            for method in self.methods
            if type(method).__name__ == "EditMessageText"
        ]

    def sent_texts(self) -> list[str]:
        return [
            getattr(method, "text", "")
            for method in self.methods
            if type(method).__name__ == "SendMessage"
        ]


def _message(bot: Bot, chat_id: int = 1) -> Message:
    message = Message.model_validate(
        {
            "message_id": 10,
            "date": 0,
            "chat": {"id": chat_id, "type": "private"},
            "from_user": {"id": 1, "is_bot": False, "first_name": "Test"},
            "text": "placeholder",
        }
    )
    return message.as_(bot)


def _callback(bot: Bot, data: str, chat_id: int = 1) -> CallbackQuery:
    query = CallbackQuery.model_validate(
        {
            "id": "1",
            "from_user": {"id": 1, "is_bot": False, "first_name": "Test"},
            "chat_instance": "x",
            "data": data,
            "message": _message(bot, chat_id),
        }
    )
    return query.as_(bot)


def _incoming(bot: Bot, text: str, chat_id: int = 1) -> Message:
    message = Message.model_validate(
        {
            "message_id": 11,
            "date": 0,
            "chat": {"id": chat_id, "type": "private"},
            "from_user": {"id": 1, "is_bot": False, "first_name": "Test"},
            "text": text,
        }
    )
    return message.as_(bot)


@pytest.fixture
def bot() -> Bot:
    return Bot(token=BOT_TOKEN, session=StubSession())


@pytest.fixture
async def flow(session, bot):
    admin = await UserRepository(session).get_or_create(
        333, username="admin", first_name="Аня"
    )
    group = await GroupService(session).create_group(creator=admin, name="Группа")
    user = await UserRepository(session).get_or_create(
        111, username="owner", first_name="Иван"
    )
    await GroupRepository(session).upsert_membership(group.id, user.id)
    subject = await SubjectRepository(session).create(group.id, "Математика")
    storage = MemoryStorage()
    key = StorageKey(bot_id=bot.id, chat_id=1, user_id=user.telegram_id)
    context = FSMContext(storage=storage, key=key)
    return group, user, subject, context


async def test_calendar_future_date_moves_to_title(session, bot, flow, monkeypatch):
    group, user, subject, context = flow
    await context.set_state(HomeworkCreation.deadline)
    await context.update_data(subject_id=subject.id)

    async def _resolve(*args, **kwargs):
        return group

    monkeypatch.setattr(homework_handlers, "resolve_group", _resolve)
    query = _callback(bot, f"cal:day:{FUTURE_DAY.isoformat()}")

    await homework_handlers.on_calendar(
        query=query, bot=bot, session=session, user=user, state=context
    )

    assert await context.get_state() == HomeworkCreation.title.state
    assert (await context.get_data())["deadline"] == FUTURE_DAY.isoformat()
    assert homework_handlers.TITLE_PENDING in bot.session.texts()


async def test_calendar_duplicate_shows_existing_and_clears_state(
    session, bot, flow, monkeypatch
):
    group, user, subject, context = flow
    await HomeworkRepository(session).create(
        group_id=group.id,
        subject_id=subject.id,
        author_id=user.id,
        title="Уже есть",
        deadline=FUTURE_DAY,
    )
    await context.set_state(HomeworkCreation.deadline)
    await context.update_data(subject_id=subject.id)

    async def _resolve(*args, **kwargs):
        return group

    monkeypatch.setattr(homework_handlers, "resolve_group", _resolve)
    query = _callback(bot, f"cal:day:{FUTURE_DAY.isoformat()}")

    await homework_handlers.on_calendar(
        query=query, bot=bot, session=session, user=user, state=context
    )

    assert await context.get_state() is None
    assert any("уже есть задание" in text.lower() for text in bot.session.texts())
    assert await HomeworkService(session).count_active(group.id, FUTURE_DAY) == 1


async def test_calendar_past_date_is_rejected(session, bot, flow):
    _group, user, subject, context = flow
    await context.set_state(HomeworkCreation.deadline)
    await context.update_data(subject_id=subject.id)
    query = _callback(bot, "cal:day:2000-01-01")

    await homework_handlers.on_calendar(
        query=query, bot=bot, session=session, user=user, state=context
    )

    assert await context.get_state() == HomeworkCreation.deadline.state
    assert bot.session.texts() == []


async def test_create_group_duplicate_name_warns(session, bot, flow):
    _group, user, _subject, context = flow
    groups = GroupRepository(session)
    await GroupService(session).create_group(creator=user, name="Математика")
    before = len(await groups.list_all())
    await context.set_state(GroupFlow.create_name)

    await menu_handlers.on_create_group_name(
        message=_incoming(bot, "математика"),
        session=session,
        user=user,
        state=context,
    )

    assert any("уже существует" in text for text in bot.session.sent_texts())
    assert await context.get_state() == GroupFlow.create_name.state
    assert len(await groups.list_all()) == before


async def test_create_group_unique_name_succeeds(session, bot, flow):
    _group, user, _subject, context = flow
    groups = GroupRepository(session)
    before = len(await groups.list_all())
    await context.set_state(GroupFlow.create_name)

    await menu_handlers.on_create_group_name(
        message=_incoming(bot, "Новая группа"),
        session=session,
        user=user,
        state=context,
    )

    assert not any("уже существует" in text for text in bot.session.sent_texts())
    assert await context.get_state() != GroupFlow.create_name.state
    assert len(await groups.list_all()) == before + 1
