from datetime import date
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery
from app.bot.callbacks import (
    DETAIL_BACK,
    HW_DELETE_FILE,
    HW_DELETE_FILE_CONFIRM,
    HW_FOLDER_BACK,
    HW_OPEN_FILE,
    HW_OPEN_FOLDER,
)
from app.bot.formats import build_homework_card, plural_files
from app.bot.handlers import views as views_handlers
from app.bot.handlers.views import (
    _detail_payload,
    _folder_payload,
    _open_detail,
)
from app.bot.keyboards.views import attachment_delete_confirm_keyboard
from app.database.models import AttachmentType
from app.database.repositories.group_repository import GroupRepository
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


async def test_open_detail_many_photos_keep_card_without_media(session) -> None:
    chat_id = 9001
    user, service, hw = await _seed_homework(session, attachments=3)
    recording = RecordingSession()
    recording.chat_id = chat_id
    bot = Bot(token=BOT_TOKEN, session=recording)

    await _open_detail(_source_message(bot, chat_id), bot, session, user, service, hw)

    names = recording.names()
    assert names == ["EditMessageText"]
    assert "SendMediaGroup" not in names
    assert "SendPhoto" not in names
    assert "SendDocument" not in names


async def test_open_detail_single_file_keeps_card_without_media(session) -> None:
    chat_id = 9002
    user, service, hw = await _seed_homework(session, attachments=1)
    recording = RecordingSession()
    recording.chat_id = chat_id
    bot = Bot(token=BOT_TOKEN, session=recording)

    await _open_detail(_source_message(bot, chat_id), bot, session, user, service, hw)

    names = recording.names()
    assert "SendPhoto" not in names
    assert "SendMediaGroup" not in names
    assert names == ["EditMessageText"]


async def test_open_detail_does_not_stack_previous_media(session) -> None:
    chat_id = 9003
    user, service, hw = await _seed_homework(session, attachments=2)
    recording = RecordingSession()
    recording.chat_id = chat_id
    bot = Bot(token=BOT_TOKEN, session=recording)

    await _open_detail(_source_message(bot, chat_id), bot, session, user, service, hw)
    await _open_detail(_source_message(bot, chat_id), bot, session, user, service, hw)

    assert all(
        type(call).__name__ not in {"SendMediaGroup", "SendPhoto", "SendDocument"}
        for call in recording.calls
    )


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


async def test_folder_rows_are_name_and_delete(session) -> None:
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
    rows = [
        row
        for row in markup.inline_keyboard
        if any(
            btn.callback_data is not None
            and (
                btn.callback_data.startswith(HW_OPEN_FILE)
                or btn.callback_data.startswith(HW_DELETE_FILE)
            )
            for btn in row
        )
    ]
    assert [[btn.text for btn in row] for row in rows] == [
        ["IMG000.jpg", "🗑"],
        ["IMG001.jpg", "🗑"],
        ["задание.pdf", "🗑"],
    ]
    assert "👁" not in {
        btn.text for row in rows for btn in row
    }


async def test_folder_name_buttons_open_and_unchanged_for_others(session) -> None:
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
    attachment_ids = [item.id for item in detail.attachments]
    open_buttons = [
        btn
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data is not None
        and btn.callback_data.startswith(HW_OPEN_FILE)
    ]
    assert [btn.text for btn in open_buttons] == [
        "IMG000.jpg",
        "IMG001.jpg",
        "задание.pdf",
    ]
    assert [btn.callback_data for btn in open_buttons] == [
        f"{HW_OPEN_FILE}{hw.id}:{item_id}" for item_id in attachment_ids
    ]
    # открыть можно и неудаляемые вложения (например, чужие файлы)
    _, markup = _folder_payload(
        hw, detail, can_add_files=True, deleteable_attachment_ids=set()
    )
    rows = [
        [btn.text for btn in row]
        for row in markup.inline_keyboard
        if any(
            btn.callback_data is not None
            and btn.callback_data.startswith(HW_OPEN_FILE)
            for btn in row
        )
    ]
    assert rows == [
        ["IMG000.jpg"],
        ["IMG001.jpg"],
        ["задание.pdf"],
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
    # первое фото не подлежит удалению — в его ряду нет кнопки, но нумерация глобальная
    deleteable = {photos[1].id, doc.id}
    _, markup = _folder_payload(
        hw, detail, can_add_files=True, deleteable_attachment_ids=deleteable
    )
    rows = [
        [btn.text for btn in row]
        for row in markup.inline_keyboard
        if any(
            btn.callback_data is not None
            and (
                btn.callback_data.startswith(HW_OPEN_FILE)
                or btn.callback_data.startswith(HW_DELETE_FILE)
            )
            for btn in row
        )
    ]
    assert rows == [
        ["IMG000.jpg"],
        ["тезисы.pdf", "🗑"],
        ["IMG001.jpg", "🗑"],
    ]


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
    names = recording.names()
    assert names == ["EditMessageText"]
    attachment_id = (await service.attachments_for(hw))[0].id
    await service.delete_attachment(hw, attachment_id)

    await _open_detail(
        _source_message(bot, chat_id), bot, session, user, service, hw
    )

    names = recording.names()
    assert "EditMessageText" in names
    assert names.count("SendPhoto") == 0
    assert names.count("SendMediaGroup") == 0
    assert "DeleteMessage" not in names


def _folder_callback(bot: Bot, chat_id: int, data: str) -> CallbackQuery:
    query = CallbackQuery.model_validate(
        {
            "id": "1",
            "from_user": {"id": 333, "is_bot": False, "first_name": "Аня"},
            "chat_instance": "x",
            "data": data,
            "message": _source_message(bot, chat_id),
        }
    )
    return query.as_(bot)


async def _fsm_context(bot: Bot) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(
        bot_id=int(BOT_TOKEN.split(":")[0]), chat_id=-1, user_id=333
    )
    return FSMContext(storage=storage, key=key)


def _resolve_group_stub(group):
    async def stub(bot, session, user, chat, state):
        return group

    return stub


async def test_open_file_sends_media_with_folder_menu(monkeypatch, session) -> None:
    chat_id = 9101
    user, service, hw = await _seed_homework(session, attachments=2)
    group = (await GroupRepository(session).list_groups_for_user(user.id))[0]
    monkeypatch.setattr(
        "app.bot.handlers.views.resolve_group", _resolve_group_stub(group)
    )
    views_handlers._OPENED_FILE_MESSAGES.clear()
    recording = RecordingSession()
    recording.chat_id = chat_id
    bot = Bot(token=BOT_TOKEN, session=recording)
    attachments = await service.attachments_for(hw)
    first, second = attachments
    context = await _fsm_context(bot)

    await views_handlers.on_open_file(
        _folder_callback(bot, chat_id, f"{HW_OPEN_FILE}{hw.id}:{first.id}"),
        bot,
        session,
        user,
        context,
    )
    await views_handlers.on_open_file(
        _folder_callback(bot, chat_id, f"{HW_OPEN_FILE}{hw.id}:{second.id}"),
        bot,
        session,
        user,
        context,
    )

    media = [
        call
        for call in recording.calls
        if type(call).__name__ in {"SendPhoto", "EditMessageMedia"}
    ]
    assert [type(call).__name__ for call in media] == ["SendPhoto", "EditMessageMedia"]
    sent = media[0]
    assert sent.photo == first.telegram_file_id
    assert sent.reply_markup is not None
    assert "🔙 К заданию" in {
        btn.text for row in sent.reply_markup.inline_keyboard for btn in row
    }
    edited = media[1]
    sent_id = next(
        (msg_id for name, msg_id in recording.results if name == "SendPhoto"), None
    )
    assert edited.message_id == sent_id
    assert edited.media.media == second.telegram_file_id
    assert edited.media.type == "photo"
    edited_id = next(
        (
            msg_id
            for name, msg_id in recording.results
            if name == "EditMessageMedia"
        ),
        None,
    )
    assert views_handlers._OPENED_FILE_MESSAGES[(chat_id, hw.id)] == edited_id


async def test_open_file_document_uses_send_document_with_caption(
    monkeypatch, session
) -> None:
    chat_id = 9102
    user, service, hw = await _seed_homework(session, attachments=0)
    await service.add_attachment(
        hw,
        telegram_file_id="DOC1",
        file_type=AttachmentType.DOCUMENT,
        author_id=user.id,
        file_name="задание.pdf",
    )
    group = (await GroupRepository(session).list_groups_for_user(user.id))[0]
    monkeypatch.setattr(
        "app.bot.handlers.views.resolve_group", _resolve_group_stub(group)
    )
    views_handlers._OPENED_FILE_MESSAGES.clear()
    recording = RecordingSession()
    recording.chat_id = chat_id
    bot = Bot(token=BOT_TOKEN, session=recording)
    attachment = (await service.attachments_for(hw))[0]
    context = await _fsm_context(bot)

    await views_handlers.on_open_file(
        _folder_callback(bot, chat_id, f"{HW_OPEN_FILE}{hw.id}:{attachment.id}"),
        bot,
        session,
        user,
        context,
    )

    sent = next(
        call for call in recording.calls if type(call).__name__ == "SendDocument"
    )
    assert sent.document == attachment.telegram_file_id
    assert sent.caption == "📎 задание.pdf"


async def test_folder_back_deletes_file_preview(monkeypatch, session) -> None:
    chat_id = 9103
    user, service, hw = await _seed_homework(session, attachments=1)
    group = (await GroupRepository(session).list_groups_for_user(user.id))[0]
    monkeypatch.setattr(
        "app.bot.handlers.views.resolve_group", _resolve_group_stub(group)
    )
    views_handlers._OPENED_FILE_MESSAGES.clear()
    recording = RecordingSession()
    recording.chat_id = chat_id
    bot = Bot(token=BOT_TOKEN, session=recording)
    attachment = (await service.attachments_for(hw))[0]
    context = await _fsm_context(bot)

    await views_handlers.on_open_file(
        _folder_callback(bot, chat_id, f"{HW_OPEN_FILE}{hw.id}:{attachment.id}"),
        bot,
        session,
        user,
        context,
    )
    preview_message_id = next(
        (msg_id for name, msg_id in recording.results if name == "SendPhoto"), None
    )
    assert preview_message_id is not None
    await views_handlers.on_folder_back(
        _folder_callback(bot, chat_id, f"{HW_FOLDER_BACK}{hw.id}"),
        bot,
        session,
        user,
        context,
    )

    deletes = [
        call for call in recording.calls if type(call).__name__ == "DeleteMessage"
    ]
    assert preview_message_id in [call.message_id for call in deletes]
    assert views_handlers._OPENED_FILE_MESSAGES == {}
