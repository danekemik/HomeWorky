from datetime import date
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from app.bot.callbacks import (
    DETAIL_BACK,
    HW_DELETE_FILE,
    HW_DELETE_FILE_CONFIRM,
    HW_FOLDER_BACK,
    HW_OPEN_FOLDER,
)
from app.bot.formats import build_homework_card, plural_files
from app.bot.handlers.views import (
    _attachment_send_plan,
    _detail_payload,
    _folder_payload,
    _open_detail,
)
from app.bot.keyboards.views import attachment_delete_confirm_keyboard
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


def _source_message(bot: Bot, chat_id: int, message_id: int = 100) -> Any:
    from aiogram.types import Message

    return Message.model_validate(
        {
            "message_id": message_id,
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
    assert "📎 1 файл" in message.text
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
    folder_button = next(
        btn for btn in rows[1] if btn.callback_data == f"{HW_OPEN_FOLDER}{hw.id}"
    )
    assert folder_button.text == "📁 Посмотреть файлы"
    back = rows[-1][0]
    assert back.text == "🔙 К списку"
    assert back.callback_data == f"{DETAIL_BACK}{hw.id}"
    _, folder_markup = _folder_payload(
        hw, detail, can_add_files=True, deleteable_attachment_ids=deleteable
    )
    folder_back = folder_markup.inline_keyboard[-1][0]
    assert folder_back.text == "🔙 К заданию"
    assert folder_back.callback_data == f"{HW_FOLDER_BACK}{hw.id}"
    assert "🔗" not in text
    assert "📎 2 файла" in text


async def test_detail_delete_buttons_photos_numbered_and_files_named(session) -> None:
    user, service, hw = await _seed_homework(session, attachments=2)
    await service.add_attachment(
        hw,
        telegram_file_id="DOC1",
        file_type=AttachmentType.DOCUMENT,
        author_id=user.id,
        file_name="задание.pdf",
    )
    detail = await service.get_detail(hw)
    deleteable = {item.id for item in detail.attachments}
    _, markup = _folder_payload(
        hw, detail, can_add_files=True, deleteable_attachment_ids=deleteable
    )
    buttons = [
        btn
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data is not None
        and btn.callback_data.startswith(HW_DELETE_FILE)
    ]
    assert [btn.text for btn in buttons] == [
        "🗑 IMG000.jpg",
        "🗑 IMG001.jpg",
        "🗑 задание.pdf",
    ]


async def test_delete_buttons_use_global_photo_numbering(session) -> None:
    user, service, hw = await _seed_homework(session, attachments=1)
    await service.add_attachment(
        hw,
        telegram_file_id="DOC1",
        file_type=AttachmentType.DOCUMENT,
        author_id=user.id,
        file_name="тезисы.pdf",
    )
    await service.add_attachment(
        hw,
        telegram_file_id="PHOTO2",
        file_type=AttachmentType.PHOTO,
        author_id=user.id,
    )
    detail = await service.get_detail(hw)
    photos = [
        item for item in detail.attachments if item.file_type == AttachmentType.PHOTO
    ]
    assert len(photos) == 2
    doc = next(
        item for item in detail.attachments if item.file_type == AttachmentType.DOCUMENT
    )
    # первое фото не подлежит удалению — кнопки нет, но нумерация глобальная
    deleteable = {photos[1].id, doc.id}
    _, markup = _folder_payload(
        hw, detail, can_add_files=True, deleteable_attachment_ids=deleteable
    )
    labels = [
        btn.text
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data is not None
        and btn.callback_data.startswith(HW_DELETE_FILE)
    ]
    assert labels == ["🗑 тезисы.pdf", "🗑 IMG001.jpg"]


def test_attachment_delete_confirm_keyboard() -> None:
    markup = attachment_delete_confirm_keyboard(homework_id=7, attachment_id=11)
    rows = markup.inline_keyboard
    assert rows[0][0].text == "🗑 Да, удалить"
    assert rows[0][0].callback_data == f"{HW_DELETE_FILE_CONFIRM}7:11"
    assert rows[0][1].text == "❌ Нет"


def test_members_keyboard_delete_button_next_to_each_member() -> None:
    from app.bot.keyboards.settings import members_keyboard

    markup = members_keyboard(
        group_id=5,
        members=[(11, "Аня"), (22, "Боря")],
        offset=0,
        total_count=2,
    )
    rows = markup.inline_keyboard
    assert len(rows[0]) == 2
    assert rows[0][0].text == "👤 Аня"
    assert rows[0][1].text == "🗑"
    assert rows[0][1].callback_data == "set:rm:5:11"
    assert len(rows[1]) == 2
    assert rows[1][1].callback_data == "set:rm:5:22"


def test_card_format() -> None:
    text = build_homework_card(
        header="🐹 *Homy достаёт нужную карточку из папки*",
        subject="История",
        title="Презентация",
        deadline=date(2026, 9, 24),
        description="Про племя",
        author_name="Даня",
        attachment_count=3,
    )
    assert (
        text
        == "🐹 *Homy достаёт нужную карточку из папки*\n"
        "📖 ИСТОРИЯ\n"
        "\n🎯 Презентация\n"
        "📝 Про племя\n"
        "\n📅 24 сентября\n"
        "📎 3 файла\n"
        "👤 Добавил: Даня"
    )


def test_card_without_optional_fields() -> None:
    text = build_homework_card(
        subject="Математика",
        title="Задачи",
        deadline=date(2026, 9, 25),
    )
    assert (
        text
        == "📖 МАТЕМАТИКА\n"
        "\n🎯 Задачи\n"
        "\n📅 25 сентября"
    )


def test_card_links_section() -> None:
    text = build_homework_card(
        subject="Физика",
        title="Лаб",
        deadline=date(2026, 9, 26),
        link_lines=["Гайд"],
    )
    assert "🔗 Ссылки:\n  • Гайд" in text


def test_plural_files() -> None:
    assert plural_files(1) == "файл"
    assert plural_files(3) == "файла"
    assert plural_files(5) == "файлов"
    assert plural_files(11) == "файлов"
    assert plural_files(21) == "файл"
    assert plural_files(24) == "файла"


async def test_delete_last_file_edits_buttons_message(session) -> None:
    chat_id = 9004
    user, service, hw = await _seed_homework(session, attachments=1)
    recording = RecordingSession()
    recording.chat_id = chat_id
    bot = Bot(token=BOT_TOKEN, session=recording)

    await _open_detail(_source_message(bot, chat_id), bot, session, user, service, hw)
    buttons_id = next(
        message_id
        for name, message_id in recording.results
        if name == "SendMessage"
    )
    photo_id = next(
        message_id for name, message_id in recording.results if name == "SendPhoto"
    )
    attachment_id = (await service.attachments_for(hw))[0].id
    await service.delete_attachment(hw, attachment_id)

    await _open_detail(
        _source_message(bot, chat_id, buttons_id), bot, session, user, service, hw
    )

    names = recording.names()
    assert "EditMessageText" in names
    assert names.count("SendPhoto") == 1
    deleted = [
        call.message_id
        for call in recording.calls
        if type(call).__name__ == "DeleteMessage"
    ]
    assert photo_id in deleted
    assert buttons_id not in deleted
