from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Attachment,
    AttachmentType,
    Homework,
    HomeworkLink,
    Subject,
)
from app.database.repositories.base import BaseRepository


class HomeworkRepository(BaseRepository[Homework]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Homework)

    async def create(
        self,
        *,
        group_id: int,
        subject_id: int,
        author_id: int,
        title: str,
        deadline: date,
        description: str | None = None,
    ) -> Homework:
        homework = Homework(
            group_id=group_id,
            subject_id=subject_id,
            author_id=author_id,
            title=title,
            deadline=deadline,
            description=description,
        )
        return await self.add(homework)

    async def get_for_group(self, homework_id: int, group_id: int) -> Homework | None:
        stmt = select(Homework).where(
            Homework.id == homework_id,
            Homework.group_id == group_id,
        )
        return await self._session.scalar(stmt)

    async def list_for_group(self, group_id: int) -> list[Homework]:
        stmt = (
            select(Homework)
            .where(Homework.group_id == group_id)
            .order_by(Homework.deadline, Homework.id)
        )
        return list((await self._session.scalars(stmt)).all())

    async def list_from_date(
        self, group_id: int, start: date, end: date | None = None
    ) -> list[Homework]:
        stmt = (
            select(Homework)
            .where(
                Homework.group_id == group_id,
                Homework.deadline >= start,
            )
            .order_by(Homework.deadline, Homework.id)
        )
        if end is not None:
            stmt = stmt.where(Homework.deadline <= end)
        return list((await self._session.scalars(stmt)).all())

    async def list_due_on(self, group_id: int, target: date) -> list[Homework]:
        stmt = (
            select(Homework)
            .where(
                Homework.group_id == group_id,
                Homework.deadline == target,
            )
            .order_by(Homework.deadline, Homework.id)
        )
        return list((await self._session.scalars(stmt)).all())

    async def list_created_by(
        self, group_id: int, author_id: int
    ) -> list[Homework]:
        stmt = (
            select(Homework)
            .where(
                Homework.group_id == group_id,
                Homework.author_id == author_id,
            )
            .order_by(Homework.deadline, Homework.id)
        )
        return list((await self._session.scalars(stmt)).all())

    async def count_for_group(self, group_id: int) -> int:
        stmt = select(func.count(Homework.id)).where(Homework.group_id == group_id)
        return int((await self._session.scalar(stmt)) or 0)

    async def count_created_by(self, group_id: int, author_id: int) -> int:
        stmt = select(func.count(Homework.id)).where(
            Homework.group_id == group_id,
            Homework.author_id == author_id,
        )
        return int((await self._session.scalar(stmt)) or 0)

    async def subject_names_grouped(
        self, group_id: int, homeworks: list[Homework]
    ) -> dict[int, str]:
        ids = {h.subject_id for h in homeworks}
        if not ids:
            return {}
        stmt = select(Subject.id, Subject.name).where(
            Subject.group_id == group_id,
            Subject.id.in_(ids),
        )
        result = await self._session.execute(stmt)
        return {row.id: row.name for row in result.all()}

    async def get_subject_name(self, homework: Homework) -> str:
        subject = await self._session.get(Subject, homework.subject_id)
        return subject.name if subject is not None else "—"

    async def add_attachment(
        self,
        homework_id: int,
        *,
        telegram_file_id: str,
        file_type: AttachmentType,
        file_name: str | None = None,
    ) -> Attachment:
        attachment = Attachment(
            homework_id=homework_id,
            telegram_file_id=telegram_file_id,
            file_type=file_type,
            file_name=file_name,
        )
        self._session.add(attachment)
        await self._session.flush()
        return attachment

    async def add_link(
        self, homework_id: int, *, url: str, title: str | None = None
    ) -> HomeworkLink:
        link = HomeworkLink(homework_id=homework_id, url=url, title=title)
        self._session.add(link)
        await self._session.flush()
        return link

    async def clear_attachments(self, homework_id: int) -> None:
        await self._session.execute(
            delete(Attachment).where(Attachment.homework_id == homework_id)
        )

    async def clear_links(self, homework_id: int) -> None:
        await self._session.execute(
            delete(HomeworkLink).where(HomeworkLink.homework_id == homework_id)
        )

    async def attachments_for(self, homework_id: int) -> list[Attachment]:
        stmt = (
            select(Attachment)
            .where(Attachment.homework_id == homework_id)
            .order_by(Attachment.id)
        )
        return list((await self._session.scalars(stmt)).all())

    async def links_for(self, homework_id: int) -> list[HomeworkLink]:
        stmt = (
            select(HomeworkLink)
            .where(HomeworkLink.homework_id == homework_id)
            .order_by(HomeworkLink.id)
        )
        return list((await self._session.scalars(stmt)).all())
