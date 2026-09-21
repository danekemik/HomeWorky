import secrets
from datetime import UTC, datetime, timedelta

from aiogram.enums import ChatType
from aiogram.types import Chat
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import Group, GroupMember, MemberRole, User
from app.database.repositories import GroupRepository

_GROUP_CHAT_TYPES = frozenset({ChatType.GROUP, ChatType.SUPERGROUP})

_LETTERS = "ABCDEFGHJKMNPQRSTUVWXYZ"
_DIGITS = "23456789"


class GroupError(Exception):
    """Ошибка бизнес-логики групп (передаётся пользователю дословно)."""


def normalize_code(raw: str) -> str:
    """Приводит введённый код к каноническому виду (10 символов, без разделителей)."""
    return "".join(ch for ch in raw.upper() if ch.isalnum())


def format_code(code: str) -> str:
    return f"{code[:5]}-{code[5:]}"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_expiry() -> datetime:
    return _utcnow() + timedelta(days=settings.INVITE_CODE_TTL_DAYS)


class GroupService:
    """Учебные группы, код-доступ и членства."""

    def __init__(self, session: AsyncSession) -> None:
        self._groups = GroupRepository(session)

    async def _unique_code(self) -> str:
        for _ in range(10):
            code = self._generate_code()
            if await self._groups.get_by_invite_code(code) is None:
                return code
        raise GroupError("Не удалось сгенерировать уникальный код. Попробуй ещё раз.")

    async def create_group(self, *, creator: User, name: str) -> Group:
        clean = " ".join(name.split()).strip()
        if not clean:
            raise GroupError("Название группы не может быть пустым.")
        if len(clean) > 64:
            raise GroupError("Название слишком длинное (максимум 64 символа).")
        if await self._groups.name_exists(clean):
            raise GroupError("Группа с таким названием уже существует.")
        group = await self._groups.create(
            name=clean,
            created_by=creator.id,
            invite_code=await self._unique_code(),
            invite_code_expires_at=_new_expiry(),
        )
        await self._groups.upsert_membership(
            group.id, creator.id, MemberRole.ADMIN
        )
        return group

    @staticmethod
    def _generate_code() -> str:
        generator = secrets.SystemRandom()
        chars = [
            generator.choice(_LETTERS) for _ in range(5)
        ] + [generator.choice(_DIGITS) for _ in range(5)]
        generator.shuffle(chars)
        return "".join(chars)

    async def join_group(
        self, *, group: Group, user: User, code: str
    ) -> str | None:
        if normalize_code(code) != group.invite_code:
            return "Неверный код. Проверь его и попробуй ещё раз."
        if group.invite_code_expires_at < _utcnow():
            return "Код устарел. Попроси старосту обновить его в настройках."
        membership = await self._groups.get_membership(group.id, user.id)
        if membership is not None and membership.role == MemberRole.ADMIN:
            return "Ты уже администратор этой группы."
        await self._groups.upsert_membership(group.id, user.id, MemberRole.MEMBER)
        return None

    async def is_admin(self, group: Group, user: User) -> bool:
        membership = await self._groups.get_membership(group.id, user.id)
        return membership is not None and membership.role == MemberRole.ADMIN

    async def has_access(self, group: Group, user: User) -> bool:
        return (await self._groups.get_membership(group.id, user.id)) is not None

    async def list_groups_for_user(self, user: User) -> list[Group]:
        return await self._groups.list_groups_for_user(user.id)

    async def admin_groups(self, user: User) -> list[Group]:
        return await self._groups.list_admin_groups_for_user(user.id)

    async def list_members(self, group: Group) -> list[GroupMember]:
        return await self._groups.list_members(group.id)

    async def remove_member(self, group: Group, target_user_id: int) -> None:
        if group.created_by == target_user_id:
            raise GroupError("Нельзя удалить создателя группы.")
        await self._groups.remove_membership(group.id, target_user_id)

    async def invite_info(
        self, group: Group
    ) -> tuple[str, datetime]:
        """Возвращает актуальный код; устаревший заменяется на новый."""
        if group.invite_code_expires_at < _utcnow():
            await self.rotate_invite_code(group)
        return group.invite_code, group.invite_code_expires_at

    async def rotate_invite_code(self, group: Group) -> None:
        await self._groups.set_invite_code(
            group, await self._unique_code(), _new_expiry()
        )

    async def find_by_invite_code(self, code: str) -> Group | None:
        return await self._groups.get_by_invite_code(normalize_code(code))

    @staticmethod
    def invite_valid(group: Group) -> bool:
        return group.invite_code_expires_at >= _utcnow()

    async def bind_chat(self, group: Group, chat: Chat) -> str | None:
        if chat.type not in _GROUP_CHAT_TYPES:
            return "Привязывать можно только групповой чат."
        existing = await self._groups.get_by_telegram_chat_id(chat.id)
        if existing is not None and existing.id != group.id:
            return f"Этот чат уже привязан к группе «{existing.name}»."
        await self._groups.bind_chat(group, chat.id)
        return None
