from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Subject
from app.database.repositories.base import BaseRepository


class SubjectRepository(BaseRepository[Subject]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Subject)

    async def list_for_group(self, group_id: int) -> list[Subject]:
        stmt = (
            select(Subject)
            .where(Subject.group_id == group_id)
            .order_by(Subject.name)
        )
        return list((await self._session.scalars(stmt)).all())

    async def get_by_group_and_name(self, group_id: int, name: str) -> Subject | None:
        stmt = (
            select(Subject)
            .where(
                Subject.group_id == group_id,
                func.lower(Subject.name) == name.strip().lower(),
            )
            .order_by(Subject.id)
            .limit(1)
        )
        return await self._session.scalar(stmt)

    async def create(self, group_id: int, name: str) -> Subject:
        subject = Subject(group_id=group_id, name=name)
        return await self.add(subject)

    async def name_exists(
        self, group_id: int, name: str, *, exclude_id: int | None = None
    ) -> bool:
        stmt = select(Subject.id).where(
            Subject.group_id == group_id,
            func.lower(Subject.name) == name.strip().lower(),
        )
        if exclude_id is not None:
            stmt = stmt.where(Subject.id != exclude_id)
        return (await self._session.scalar(stmt.limit(1))) is not None

    async def rename(self, subject: Subject, name: str) -> Subject:
        subject.name = name
        await self._session.flush()
        return subject
