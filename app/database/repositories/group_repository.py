from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import Group, GroupMember, MemberRole
from app.database.repositories.base import BaseRepository


class GroupRepository(BaseRepository[Group]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Group)

    async def get_by_telegram_chat_id(self, telegram_chat_id: int) -> Group | None:
        stmt = select(Group).where(Group.telegram_chat_id == telegram_chat_id)
        return await self._session.scalar(stmt)

    async def get_by_invite_code(self, code: str) -> Group | None:
        stmt = select(Group).where(Group.invite_code == code)
        return await self._session.scalar(stmt)

    async def name_exists(self, name: str) -> bool:
        names = (await self._session.scalars(select(Group.name))).all()
        needle = name.lower()
        return any(existing.lower() == needle for existing in names)

    async def create(
        self,
        *,
        name: str,
        created_by: int | None,
        invite_code: str,
        invite_code_expires_at: datetime,
    ) -> Group:
        group = Group(
            name=name,
            created_by=created_by,
            invite_code=invite_code,
            invite_code_expires_at=invite_code_expires_at,
        )
        return await self.add(group)

    async def list_all(self) -> list[Group]:
        stmt = select(Group).order_by(Group.name)
        return list((await self._session.scalars(stmt)).all())

    async def list_groups_for_user(self, user_id: int) -> list[Group]:
        stmt = (
            select(Group)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(GroupMember.user_id == user_id)
            .order_by(Group.name)
        )
        return list((await self._session.scalars(stmt)).all())

    async def list_admin_groups_for_user(self, user_id: int) -> list[Group]:
        stmt = (
            select(Group)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(
                GroupMember.user_id == user_id,
                GroupMember.role == MemberRole.ADMIN,
            )
            .order_by(Group.name)
        )
        return list((await self._session.scalars(stmt)).all())

    async def get_for_member(
        self, group_id: int, user_id: int
    ) -> Group | None:
        """Возвращает группу одним запросом, только если пользователь — участник."""
        stmt = (
            select(Group)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
            )
        )
        return await self._session.scalar(stmt)

    async def get_membership(self, group_id: int, user_id: int) -> GroupMember | None:
        stmt = select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.user_id == user_id,
        )
        return await self._session.scalar(stmt)

    async def upsert_membership(
        self, group_id: int, user_id: int, role: MemberRole = MemberRole.MEMBER
    ) -> GroupMember:
        membership = await self.get_membership(group_id, user_id)
        if membership is None:
            membership = GroupMember(
                group_id=group_id,
                user_id=user_id,
                role=role,
            )
            self._session.add(membership)
            await self._session.flush()
            return membership
        if role == MemberRole.ADMIN and membership.role != MemberRole.ADMIN:
            membership.role = MemberRole.ADMIN
            await self._session.flush()
        return membership

    async def remove_membership(self, group_id: int, user_id: int) -> None:
        await self._session.execute(
            delete(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
            )
        )
        await self._session.flush()

    async def list_members(self, group_id: int) -> list[GroupMember]:
        stmt = (
            select(GroupMember)
            .where(GroupMember.group_id == group_id)
            .options(selectinload(GroupMember.user))
            .order_by(GroupMember.joined_at)
        )
        return list((await self._session.scalars(stmt)).all())

    async def set_role(
        self, group_id: int, user_id: int, role: MemberRole
    ) -> None:
        await self._session.execute(
            update(GroupMember)
            .where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
            )
            .values(role=role)
        )
        await self._session.flush()

    async def bind_chat(self, group: Group, telegram_chat_id: int) -> Group:
        group.telegram_chat_id = telegram_chat_id
        await self._session.flush()
        return group

    async def unbind_chat(self, group: Group) -> Group:
        group.telegram_chat_id = None
        await self._session.flush()
        return group

    async def set_invite_code(
        self, group: Group, code: str, expires_at: datetime
    ) -> Group:
        group.invite_code = code
        group.invite_code_expires_at = expires_at
        await self._session.flush()
        return group
