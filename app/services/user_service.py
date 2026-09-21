import re

from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.database.repositories import UserRepository

_CYRILLIC_NAME_RE = re.compile(r"^[А-Яа-яЁё -]+$")
_MAX_DISPLAY_NAME = 64
_MIN_DISPLAY_NAME = 2


class UserNameError(ValueError):
    """Ошибка валидации введённого пользователем имени."""


def validate_display_name(raw: str) -> str:
    """Проверяет и приводит имя к виду «Имя» (только русские буквы).

    Возвращает нормализованное имя или бросает UserNameError с объяснением.
    """
    name = " ".join(raw.split()).strip()
    if not name:
        raise UserNameError("Имя не может быть пустым.")
    if len(name) < _MIN_DISPLAY_NAME:
        raise UserNameError("Имя слишком короткое (минимум 2 символа).")
    if len(name) > _MAX_DISPLAY_NAME:
        raise UserNameError("Имя слишком длинное (максимум 64 символа).")
    if not _CYRILLIC_NAME_RE.fullmatch(name):
        raise UserNameError(
            "Имя должно быть на русском и состоять только из букв."
        )
    return name.title()


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

    async def set_display_name(self, user: User, raw_name: str) -> str:
        name = validate_display_name(raw_name)
        user.display_name = name
        await self._repo.update_profile(user, display_name=name)
        return name
