from dataclasses import dataclass
from datetime import date, timedelta

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


@dataclass(frozen=True)
class AttachmentInfo:
    id: int
    file_type: AttachmentType
    file_name: str | None


@dataclass(frozen=True)
class LinkInfo:
    url: str
    title: str | None


@dataclass(frozen=True)
class HomeworkDetail:
    subject: str
    author_name: str
    attachments: list[AttachmentInfo]
    links: list[LinkInfo]


class HomeworkService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = HomeworkRepository(session)
        self._groups = GroupRepository(session)
        self._subjects = SubjectRepository(session)
        self._users = UserRepository(session)
        self._session = session

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
        return await self._repo.create(
            group_id=group_id,
            subject_id=subject_id,
            author_id=author_id,
            title=title,
            deadline=deadline,
            description=description,
        )

    async def get_for_group(self, homework_id: int, group_id: int) -> Homework | None:
        return await self._repo.get_for_group(homework_id, group_id)

    async def update_homework(
        self,
        homework: Homework,
        *,
        title: str | None = None,
        description: str | None = None,
        deadline: date | None = None,
    ) -> Homework:
        if title is not None:
            homework.title = title
        if description is not None:
            homework.description = description
        if deadline is not None:
            homework.deadline = deadline
        await self._session.flush()
        return homework

    async def set_subject(self, homework: Homework, subject_id: int) -> Homework:
        subject = await self._subjects.get(subject_id)
        if subject is None or subject.group_id != homework.group_id:
            raise HomeworkAccessError("Предмет не найден в этой группе")
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

    async def list_active(self, group_id: int, today: date) -> list[Homework]:
        return await self._repo.list_from_date(group_id, today)

    async def list_past(self, group_id: int, today: date) -> list[Homework]:
        start = today - timedelta(days=14)
        return await self._repo.list_from_date(group_id, start, today - timedelta(days=1))

    async def list_created_by(self, group_id: int, author_id: int) -> list[Homework]:
        return await self._repo.list_created_by(group_id, author_id)

    async def list_all_for_group(self, group_id: int) -> list[Homework]:
        return await self._repo.list_for_group(group_id)

    async def subject_names(self, group_id: int, homeworks: list[Homework]) -> dict[int, str]:
        return await self._repo.subject_names_grouped(group_id, homeworks)

    async def list_subjects(self, group_id: int) -> list[Subject]:
        return await self._subjects.list_for_group(group_id)

    async def subject_by_name(self, group_id: int, name: str) -> Subject | None:
        lowered = name.strip().lower()
        for subject in await self.list_subjects(group_id):
            if subject.name.strip().lower() == lowered:
                return subject
        return None

    async def get_subject(self, subject_id: int) -> Subject | None:
        return await self._subjects.get(subject_id)

    async def create_subject(self, group_id: int, name: str) -> Subject:
        return await self._subjects.create(group_id, name)

    async def add_attachment(
        self,
        homework: Homework,
        *,
        telegram_file_id: str,
        file_type: AttachmentType,
        file_name: str | None = None,
    ) -> Attachment:
        return await self._repo.add_attachment(
            homework.id,
            telegram_file_id=telegram_file_id,
            file_type=file_type,
            file_name=file_name,
        )

    async def add_link(
        self, homework: Homework, *, url: str, title: str | None = None
    ) -> HomeworkLink:
        return await self._repo.add_link(
            homework.id, url=url, title=title
        )

    async def attachments_for(self, homework: Homework) -> list[Attachment]:
        return await self._repo.attachments_for(homework.id)

    async def links_for(self, homework: Homework) -> list[HomeworkLink]:
        return await self._repo.links_for(homework.id)

    async def get_detail(self, homework: Homework) -> HomeworkDetail:
        subject = await self._repo.get_subject_name(homework)
        author = await self._users.get(homework.author_id)
        author_name = self._author_label(author)
        attachments = [
            AttachmentInfo(
                id=item.id,
                file_type=item.file_type,
                file_name=item.file_name,
            )
            for item in await self._repo.attachments_for(homework.id)
        ]
        links = [
            LinkInfo(url=link.url, title=link.title)
            for link in await self._repo.links_for(homework.id)
        ]
        return HomeworkDetail(
            subject=subject,
            author_name=author_name,
            attachments=attachments,
            links=links,
        )

    async def attach_pending(
        self,
        homework: Homework,
        attachments: list[dict[str, object]],
        links: list[dict[str, object]],
    ) -> None:
        for item in attachments:
            file_name = item.get("file_name")
            await self.add_attachment(
                homework,
                telegram_file_id=str(item["telegram_file_id"]),
                file_type=AttachmentType(str(item["file_type"])),
                file_name=str(file_name) if file_name else None,
            )
        for item in links:
            title = item.get("title")
            await self.add_link(
                homework,
                url=str(item["url"]),
                title=str(title) if title else None,
            )

    async def replace_attachments(
        self,
        homework: Homework,
        attachments: list[dict[str, object]],
        links: list[dict[str, object]],
    ) -> None:
        await self._repo.clear_attachments(homework.id)
        await self._repo.clear_links(homework.id)
        await self.attach_pending(homework, attachments, links)

    async def stats(self, group_id: int, user_id: int, today: date) -> dict[str, int]:
        total = await self._repo.count_for_group(group_id)
        created_by_me = await self._repo.count_created_by(group_id, user_id)
        today_list, tomorrow_list = await self.nearest(group_id, today)
        active = len(await self.list_active(group_id, today))
        return {
            "total": total,
            "created_by_me": created_by_me,
            "today": len(today_list),
            "tomorrow": len(tomorrow_list),
            "active": active,
        }

    @staticmethod
    def _author_label(author: User | None) -> str:
        if author is None:
            return "?"
        if author.first_name:
            return author.first_name
        return author.username or f"id{author.telegram_id}"
