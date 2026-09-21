from datetime import date
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from app.bot.callbacks import DETAIL_BACK, HW_DELETE_FILE
from app.bot.formats import build_homework_card
from app.bot.handlers.views import (
    _attachment_send_plan,
    _detail_payload,
    _open_detail,
)
from app.database.models import Attachment, AttachmentType
from app.database.repositories.homework_repository import HomeworkRepository
from app.database.repositories.subject_repository import SubjectRepository
from app.database.repositories.user_repository import UserRepository
from app.services.group_service import GroupService
from app.services.homework_service import HomeworkService

BOT_TOKEN = "123456789:AAEtesttoken1234567890_ABC"


class RecordingSession(BaseSession):
    """Записывает исходящие методы и id сообщений-результатов."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[Any] = []
        self.results: list[tuple[str, int]] = []
        self.chat_id = 1
        self._message_id = 10

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
        self.calls.append(method)
        name = type(method).__name__
        if name == "SendMediaGroup":
            sent = [self._fake_message(bot) for _ in range(len(method.media))]
            self.results.extend([(name, item.message_id) for item in sent])
            return sent
        if name == "DeleteMessage":
            return True
        sent = self._fake_message(bot)
        self.results.append((name, sent.message_id))
        return sent

    def _fake_message(self, bot: Bot):
        from aiogram.types import Message

        self._message_id += 1
        return Message.model_validate(
            {
                "message_id": self._message_id,
                "date": 0,
                "chat": {"id": self.chat_id, "type": "private"},
                "from_user": {"id": 1, "is_bot": False, "first_name": "Test"},
                "text": "placeholder",
            }
        ).as_(bot)

    def names(self) -> list[str]:
        return [type(call).__name__ for call in self.calls]


def _source_message(bot: Bot, chat_id: int) -> Any:
    from aiogram.types import Message

    return Message.model_validate(
        {
            "message_id": 100,
            "date": 0,
            "chat": {"id": chat_id, "type": "private"},
            "from_user": {"id": 1, "is_bot": False, "first_name": "Test"},
            "text": "📚 Список заданий",
        }
    ).as_(bot)


async def _seed_homework(session, *, attachments: int) -> Any:
    user = await UserRepository(session).get_or_create(
        333, username="admin", first_name="Аня"
    )
    group = await GroupService(session).create_group(creator=user, name="Группа")
    subject = await SubjectRepository(session).create(group.id, "Математика")
    hw = await HomeworkRepository(session).create(
        group_id=group.id,
        subject_id=subject.id,
        author_id=user.id,
        title="Задачи №1-20",
        deadline=date(2026, 9, 25),
    )
    service = HomeworkService(session)
    for index in range(attachments):
        await service.add_attachment(
            hw,
            telegram_file_id=f"PHOTO{index}",
            file_type=AttachmentType.PHOTO,
            author_id=user.id,
        )
    return user, service, hw


def _attach(file_type: AttachmentType) -> Attachment:
    return Attachment(telegram_file_id="f", file_type=file_type)


def test_attachment_send_plan_groups_by_type_and_chunks() -> None:
    photos = [_attach(AttachmentType.PHOTO) for _ in range(3)]
    assert _attachment_send_plan(photos) == [("album", photos)]

    one_photo = photos[:1]
    docs = [_attach(AttachmentType.DOCUMENT) for _ in range(2)]
    assert _attachment_send_plan(one_photo + docs) == [
        ("single", one_photo),
        ("album", docs),
    ]

    eleven = [_attach(AttachmentType.PHOTO) for _ in range(11)]
    ops = _attachment_send_plan(eleven)
    assert ops[0] == ("album", eleven[:10])
    assert ops[1] == ("single", eleven[10:])


async def test_open_detail_many_photos_go_in_one_album(session) -> None:
    chat_id = 9001
    user, service, hw = await _seed_homework(session, attachments=3)
    recording = RecordingSession()
    recording.chat_id = chat_id
    bot = Bot(token=BOT_TOKEN, session=recording)

    await _open_detail(_source_message(bot, chat_id), bot, session, user, service, hw)

    names = recording.names()
    assert names == ["DeleteMessage", "SendMediaGroup", "SendMessage"]
    album = next(
        call for call in recording.calls if type(call).__name__ == "SendMediaGroup"
    )
    assert len(album.media) == 3
    first = album.media[0]
    assert first.caption is not None
    assert "Задачи №1-20" in first.caption
    assert first.parse_mode == ParseMode.HTML
    assert album.media[1].caption is None
    assert album.media[2].caption is None
    buttons = next(
        call for call in recording.calls if type(call).__name__ == "SendMessage"
    )
    assert buttons.reply_markup is not None


async def test_open_detail_single_file_sends_media_and_buttons(session) -> None:
    chat_id = 9002
    user, service, hw = await _seed_homework(session, attachments=1)
    recording = RecordingSession()
    recording.chat_id = chat_id
    bot = Bot(token=BOT_TOKEN, session=recording)

    await _open_detail(_source_message(bot, chat_id), bot, session, user, service, hw)

    names = recording.names()
    assert names == ["DeleteMessage", "SendPhoto", "SendMessage"]
    photo = next(
        call for call in recording.calls if type(call).__name__ == "SendPhoto"
    )
    assert photo.caption is not None
    assert "Задачи №1-20" in photo.caption
    assert photo.reply_markup is None
    message = next(
        call for call in recording.calls if type(call).__name__ == "SendMessage"
    )
    assert "📎 Файлы" in message.text
    assert message.reply_markup is not None


async def test_open_detail_cleans_up_previous_album(session) -> None:
    chat_id = 9003
    user, service, hw = await _seed_homework(session, attachments=2)
    recording = RecordingSession()
    recording.chat_id = chat_id
    bot = Bot(token=BOT_TOKEN, session=recording)

    await _open_detail(_source_message(bot, chat_id), bot, session, user, service, hw)
    first_album_ids = {
        message_id
        for name, message_id in recording.results
        if name == "SendMediaGroup"
    }

    await _open_detail(_source_message(bot, chat_id), bot, session, user, service, hw)

    deleted = [
        call.message_id
        for call in recording.calls
        if type(call).__name__ == "DeleteMessage"
    ]
    assert first_album_ids.issubset(deleted)


async def test_detail_buttons_grouped_and_back_to_list(session) -> None:
    _, service, hw = await _seed_homework(session, attachments=2)
    detail = await service.get_detail(hw)
    deleteable = {item.id for item in detail.attachments}
    text, markup = _detail_payload(
        hw, detail, can_modify=True, can_add_files=True, deleteable_attachment_ids=deleteable
    )
    rows = markup.inline_keyboard
    assert any(btn.text == "✏️ Изменить" for btn in rows[0])
    assert any(btn.text == "🗑 Удалить" for btn in rows[0])
    assert len(rows[0]) == 2
    delete_rows = [
        row
        for row in rows
        if any(
            btn.callback_data is not None
            and btn.callback_data.startswith(HW_DELETE_FILE)
            for btn in row
        )
    ]
    assert len(delete_rows) == 1
    assert len(delete_rows[0]) == 2
    back = rows[-1][0]
    assert back.text == "🔙 К списку"
    assert back.callback_data == f"{DETAIL_BACK}{hw.id}"
    assert "🔗" not in text
    assert "📎 Файлы" in text


def test_card_files_collapsed_to_single_line() -> None:
    text = build_homework_card(
        subject="Математика",
        title="Задачи",
        deadline=date(2026, 9, 25),
        attachment_lines=["a.pdf", "b.pdf", "c.pdf", "d.pdf", "e.pdf"],
        attachment_limit=10,
    )
    assert "📎 Файлы (5/10): a.pdf · b.pdf · c.pdf · и ещё 2" in text
