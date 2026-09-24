from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.database.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        stmt = select(User).where(User.telegram_id == telegram_id)
        return await self._session.scalar(stmt)

    async def get_many(self, ids: set[int]) -> dict[int, User]:
        if not ids:
            return {}
        stmt = select(User).where(User.id.in_(ids))
        users = (await self._session.scalars(stmt)).all()
        return {user.id: user for user in users}

    async def get_or_create(self, telegram_id: int, **attrs: object) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user is not None:
            return user
        user = User(telegram_id=telegram_id, **attrs)
        try:
            return await self.add(user)
        except IntegrityError:
            await self._session.rollback()
            existing = await self.get_by_telegram_id(telegram_id)
            if existing is not None:
                return existing
            raise

    async def update_profile(self, user: User, **attrs: object) -> User:
        for key, value in attrs.items():
            setattr(user, key, value)
        await self._session.flush()
        return user
