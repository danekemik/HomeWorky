import logging

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import AiogramError
from aiogram.types import (
    Chat,
    ChatMember,
    ChatMemberAdministrator,
    ChatMemberOwner,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Group, MemberRole, User
from app.database.repositories import GroupRepository, UserRepository

logger = logging.getLogger(__name__)

_VERIFIED_STATUSES = frozenset(
    {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.RESTRICTED,
    }
)


class GroupService:
    """Business logic: groups, membership and access checks."""

    def __init__(self, session: AsyncSession) -> None:
        self._groups = GroupRepository(session)
        self._users = UserRepository(session)

    async def register_group(self, chat: Chat) -> Group:
        return await self._groups.get_or_create(chat.id, chat.title)

    async def register_membership(
        self,
        group: Group,
        user: User,
        role: MemberRole = MemberRole.MEMBER,
    ) -> None:
        await self._groups.upsert_membership(group.id, user.id, role)

    async def remove_membership(self, group_id: int, user_id: int) -> None:
        await self._groups.remove_membership(group_id, user_id)

    async def sync_administrators(self, bot: Bot, group: Group) -> None:
        """Registers Telegram chat admins (incl. creator) with the ADMIN role."""
        for member in await self._list_administrators(bot, group):
            if not isinstance(member, (ChatMemberAdministrator, ChatMemberOwner)):
                continue
            tg_user = member.user
            if tg_user.is_bot:
                continue
            db_user = await self._users.get_or_create(
                tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
            )
            await self._groups.upsert_membership(
                group.id, db_user.id, MemberRole.ADMIN
            )

    async def _list_administrators(
        self, bot: Bot, group: Group
    ) -> list[ChatMember]:
        try:
            result = await bot.get_chat_administrators(group.telegram_chat_id)
            return [
                member
                for member in result
                if isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
            ]
        except AiogramError as exc:
            logger.warning(
                "Failed to load admins for group %s: %s", group.id, exc
            )
            return []

    async def is_member(self, bot: Bot, group: Group, telegram_id: int) -> bool:
        try:
            member = await bot.get_chat_member(group.telegram_chat_id, telegram_id)
        except AiogramError:
            return False
        return member.status in _VERIFIED_STATUSES

    async def list_verified_groups(self, bot: Bot, user: User) -> list[Group]:
        """Groups the user really belongs to; stale memberships are revoked."""
        groups = await self._groups.list_groups_for_user(user.id)
        verified: list[Group] = []
        revoked: list[Group] = []
        for group in groups:
            if await self.is_member(bot, group, user.telegram_id):
                verified.append(group)
            else:
                revoked.append(group)
        for group in revoked:
            await self._groups.remove_membership(group.id, user.id)
        return verified

    async def verify_access(
        self, bot: Bot, group: Group, telegram_id: int
    ) -> bool:
        """Server-side check before granting access to a group in private chat."""
        allowed = await self.is_member(bot, group, telegram_id)
        if not allowed:
            user = await self._users.get_by_telegram_id(telegram_id)
            if user is not None:
                await self._groups.remove_membership(group.id, user.id)
        return allowed
