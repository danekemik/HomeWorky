from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Attachment,
    AttachmentType,
    Group,
    Homework,
    HomeworkLink,
    MemberRole,
    Subject,
    User,
)
from app.database.repositories import (
    GroupRepository,
    HomeworkRepository,
    SubjectRepository,
    UserRepository,
)


class HomeworkAccessError(Exception):
    """Пользователю запрещено изменение/удаление этого задания."""


class HomeworkExistsError(Exception):
    """На этот предмет и дату уже есть домашнее задание."""


class HomeworkLimitError(Exception):
    """Превышен лимит вложений (не больше 3 фото, 3 файлов и 3 ссылок)."""


class SubjectError(Exception):
    """Ошибка бизнес-логики предметов (передаётся пользователю дословно)."""


_SUBJECT_NAME_MAX = 128

# Маркер «поле не передано» (позволяет явно очистить описание значением None).
_UNSET: Any = object()


def _clean_subject_name(name: str) -> str:
    clean = " ".join(name.split()).strip()
    if not clean:
        raise SubjectError("Название предмета не может быть пустым.")
    if len(clean) > _SUBJECT_NAME_MAX:
        raise SubjectError(
            f"Название слишком длинное (максимум {_SUBJECT_NAME_MAX} символов)."
        )
    return clean


@dataclass(frozen=True)
class AttachmentInfo:
    id: int
    file_type: AttachmentType
    file_name: str | None
    author_id: int | None
    author_name: str | None


@dataclass(frozen=True)
class LinkInfo:
    url: str
    title: str | None
    author_name: str | None = None


@dataclass(frozen=True)
class HomeworkDetail:
    subject: str
    author_name: str
    attachments: list[AttachmentInfo]
    links: list[LinkInfo]


class HomeworkService:
    MAX_PHOTOS = 3
    MAX_FILES = 3
    MAX_LINKS = 3

    def __init__(self, session: AsyncSession) -> None:
        self._repo = HomeworkRepository(session)
        self._groups = GroupRepository(session)
        self._subjects = SubjectRepository(session)
        self._users = UserRepository(session)
        self._session = session

    async def find_by_subject_and_date(
        self, group_id: int, subject_id: int, deadline: date
    ) -> Homework | None:
        return await self._repo.find_by_subject_and_deadline(
            group_id, subject_id, deadline
        )

    async def create_homework(
        self,
        *,
        group_id: int,
        subject_id: int,
        author_id: int,
        title: str,
        deadline: date,
        description: str | None = None,
    ) -> Homework:
        exists = await self.find_by_subject_and_date(group_id, subject_id, deadline)
        if exists is not None:
            raise HomeworkExistsError
        try:
            async with self._session.begin_nested():
                return await self._repo.create(
                    group_id=group_id,
                    subject_id=subject_id,
                    author_id=author_id,
                    title=title,
                    deadline=deadline,
                    description=description,
                )
        except IntegrityError as exc:
            if (
                await self.find_by_subject_and_date(
                    group_id, subject_id, deadline
                )
                is not None
            ):
                raise HomeworkExistsError from exc
            raise

    async def get_for_group(self, homework_id: int, group_id: int) -> Homework | None:
        return await self._repo.get_for_group(homework_id, group_id)

    async def update_homework(
        self,
        homework: Homework,
        *,
        title: str | None = None,
        description: Any = _UNSET,
        deadline: date | None = None,
    ) -> Homework:
        if title is not None:
            homework.title = title
        if description is not _UNSET:
            homework.description = description
        if deadline is not None:
            homework.deadline = deadline
        await self._session.flush()
        return homework

    async def set_subject(self, homework: Homework, subject_id: int) -> Homework:
        subject = await self._subjects.get(subject_id)
        if subject is None or subject.group_id != homework.group_id:
            raise HomeworkAccessError("Предмет не найден в этой группе")
        if homework.subject_id != subject_id:
            exists = await self.find_by_subject_and_date(
                homework.group_id, subject_id, homework.deadline
            )
            if exists is not None and exists.id != homework.id:
                raise HomeworkExistsError
        homework.subject_id = subject_id
        await self._session.flush()
        return homework

    async def delete_homework(self, homework: Homework) -> None:
        await self._repo.delete(homework)

    async def can_modify(
        self, user: User, group_id: int, homework: Homework
    ) -> bool:
        membership = await self._groups.get_membership(group_id, user.id)
        role = membership.role if membership is not None else MemberRole.MEMBER
        return role == MemberRole.ADMIN or homework.author_id == user.id

    async def delete_by(self, user: User, group: Group, homework: Homework) -> None:
        if not await self.can_modify(user, group.id, homework):
            raise HomeworkAccessError("Удалять можно только свои задания")
        await self.delete_homework(homework)

    async def nearest(self, group_id: int, today: date) -> tuple[list[Homework], list[Homework]]:
        tomorrow = today + timedelta(days=1)
        return await self._repo.list_due_on(group_id, today), await self._repo.list_due_on(
            group_id, tomorrow
        )

    async def list_active(
        self,
        group_id: int,
        today: date,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Homework]:
        return await self._repo.list_from_date(
            group_id, today, limit=limit, offset=offset
        )

    async def count_active(self, group_id: int, today: date) -> int:
        return await self._repo.count_from_date(group_id, today)

    async def list_past(
        self,
        group_id: int,
        today: date,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Homework]:
        start = today - timedelta(days=7)
        return await self._repo.list_from_date(
            group_id, start, today - timedelta(days=1), limit=limit, offset=offset
        )

    async def count_past(self, group_id: int, today: date) -> int:
        start = today - timedelta(days=7)
        return await self._repo.count_from_date(
            group_id, start, today - timedelta(days=1)
        )

    async def list_created_by(
        self,
        group_id: int,
        author_id: int,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Homework]:
        return await self._repo.list_created_by(
            group_id, author_id, limit=limit, offset=offset
        )

    async def count_created_by(self, group_id: int, author_id: int) -> int:
        return await self._repo.count_created_by(group_id, author_id)

    async def list_all_for_group(self, group_id: int) -> list[Homework]:
        return await self._repo.list_for_group(group_id)

    async def subject_names(self, group_id: int, homeworks: list[Homework]) -> dict[int, str]:
        return await self._repo.subject_names_grouped(group_id, homeworks)

    async def list_subjects(self, group_id: int) -> list[Subject]:
        return await self._subjects.list_for_group(group_id)

    async def subject_by_name(self, group_id: int, name: str) -> Subject | None:
        return await self._subjects.get_by_group_and_name(group_id, name)

    async def get_subject(self, subject_id: int) -> Subject | None:
        return await self._subjects.get(subject_id)

    async def create_subject(self, group_id: int, name: str) -> Subject:
        clean = " ".join(name.split()).strip()
        try:
            async with self._session.begin_nested():
                return await self._subjects.create(group_id, clean)
        except IntegrityError:
            existing = await self._subjects.get_by_group_and_name(group_id, clean)
            if existing is not None:
                return existing
            raise

    async def rename_subject(self, subject: Subject, name: str) -> Subject:
        clean = _clean_subject_name(name)
        if clean.lower() == subject.name.lower():
            return subject
        if await self._subjects.name_exists(
            subject.group_id, clean, exclude_id=subject.id
        ):
            raise SubjectError("Предмет с таким названием уже есть в группе.")
        try:
            async with self._session.begin_nested():
                return await self._subjects.rename(subject, clean)
        except IntegrityError as exc:
            if await self._subjects.name_exists(
                subject.group_id, clean, exclude_id=subject.id
            ):
                raise SubjectError(
                    "Предмет с таким названием уже есть в группе."
                ) from exc
            raise

    async def count_subject_homeworks(self, subject: Subject) -> int:
        return await self._repo.count_for_subject(subject.id)

    async def delete_subject(self, subject: Subject) -> int:
        """Удаляет предмет вместе с заданиями; возвращает число удалённых ДЗ."""
        deleted = await self._repo.delete_for_subject(subject.id)
        await self._subjects.delete(subject)
        return deleted

    async def add_attachment(
        self,
        homework: Homework,
        *,
        telegram_file_id: str,
        file_type: AttachmentType,
        file_name: str | None = None,
        author_id: int | None = None,
    ) -> Attachment:
        await self._repo.lock(homework.id)
        limit = self._attachment_limit(file_type)
        if await self._repo.count_attachments(
            homework.id, file_type
        ) >= limit:
            raise HomeworkLimitError
        return await self._repo.add_attachment(
            homework.id,
            telegram_file_id=telegram_file_id,
            file_type=file_type,
            file_name=file_name,
            author_id=author_id,
        )

    @staticmethod
    def _attachment_limit(file_type: AttachmentType) -> int:
        if file_type == AttachmentType.PHOTO:
            return HomeworkService.MAX_PHOTOS
        return HomeworkService.MAX_FILES

    async def delete_attachment(
        self, homework: Homework, attachment_id: int
    ) -> None:
        await self._repo.delete_attachment(attachment_id)

    async def can_delete_attachment(
        self,
        user: User,
        group_id: int,
        homework: Homework,
        attachment: Attachment,
    ) -> bool:
        if await self.can_modify(user, group_id, homework):
            return True
        membership = await self._groups.get_membership(group_id, user.id)
        if membership is None:
            return False
        return attachment.author_id == user.id

    async def is_member(self, user: User, group_id: int) -> bool:
        membership = await self._groups.get_membership(group_id, user.id)
        return membership is not None

    async def add_link(
        self,
        homework: Homework,
        *,
        url: str,
        title: str | None = None,
        author_id: int | None = None,
    ) -> HomeworkLink:
        await self._repo.lock(homework.id)
        if await self._repo.count_links(homework.id) >= self.MAX_LINKS:
            raise HomeworkLimitError
        return await self._repo.add_link(
            homework.id, url=url, title=title, author_id=author_id
        )

    async def attachments_for(self, homework: Homework) -> list[Attachment]:
        return await self._repo.attachments_for(homework.id)

    async def links_for(self, homework: Homework) -> list[HomeworkLink]:
        return await self._repo.links_for(homework.id)

    async def link_count(self, homework: Homework) -> int:
        return await self._repo.count_links(homework.id)

    async def attachment_count(
        self, homework: Homework, file_type: AttachmentType | None = None
    ) -> int:
        return await self._repo.count_attachments(homework.id, file_type)

    async def get_detail(self, homework: Homework) -> HomeworkDetail:
        subject = await self._repo.get_subject_name(homework)
        attachments = await self._repo.attachments_for(homework.id)
        links = await self._repo.links_for(homework.id)
        author_ids = {homework.author_id} | {
            item.author_id for item in attachments if item.author_id is not None
        } | {
            item.author_id for item in links if item.author_id is not None
        }
        authors = await self._users.get_many(author_ids)
        attachments_info = [
            AttachmentInfo(
                id=item.id,
                file_type=item.file_type,
                file_name=item.file_name,
                author_id=item.author_id,
                author_name=(
                    self._author_label(authors.get(item.author_id))
                    if item.author_id is not None
                    else None
                ),
            )
            for item in attachments
        ]
        links_info = [
            LinkInfo(
                url=link.url,
                title=link.title,
                author_name=(
                    self._author_label(authors.get(link.author_id))
                    if link.author_id is not None
                    else None
                ),
            )
            for link in links
        ]
        return HomeworkDetail(
            subject=subject,
            author_name=self._author_label(authors.get(homework.author_id)),
            attachments=attachments_info,
            links=links_info,
        )

    async def attach_pending(
        self,
        homework: Homework,
        attachments: list[dict[str, object]],
        links: list[dict[str, object]],
        author_id: int | None = None,
    ) -> None:
        """Сохраняет отложенные вложения атомарно: при лимите ничего не остаётся."""
        async with self._session.begin_nested():
            for item in attachments:
                file_name = item.get("file_name")
                await self.add_attachment(
                    homework,
                    telegram_file_id=str(item["telegram_file_id"]),
                    file_type=AttachmentType(str(item["file_type"])),
                    file_name=str(file_name) if file_name else None,
                    author_id=author_id,
                )
            for item in links:
                title = item.get("title")
                await self.add_link(
                    homework,
                    url=str(item["url"]),
                    title=str(title) if title else None,
                    author_id=author_id,
                )

    async def stats(self, group_id: int, user_id: int, today: date) -> dict[str, int]:
        return await self._repo.stats(
            group_id, user_id, today, today + timedelta(days=1)
        )

    @staticmethod
    def _author_label(author: User | None) -> str:
        if author is None:
            return "?"
        if author.display_name:
            return author.display_name
        if author.first_name:
            return author.first_name
        return author.username or f"id{author.telegram_id}"
