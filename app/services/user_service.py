from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.database.repositories import UserRepository


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = UserRepository(session)

    async def get_or_create_from_telegram(self, tg_user: TelegramUser) -> User:
        user = await self._repo.get_or_create(
            tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
        )
        if (
            user.username != tg_user.username
            or user.first_name != tg_user.first_name
            or user.last_name != tg_user.last_name
        ):
            await self._repo.update_profile(
                user,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
            )
        return user
