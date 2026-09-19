from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Group, GroupMember, MemberRole
from app.database.repositories.base import BaseRepository


class GroupRepository(BaseRepository[Group]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Group)

    async def get_by_telegram_chat_id(self, telegram_chat_id: int) -> Group | None:
        stmt = select(Group).where(Group.telegram_chat_id == telegram_chat_id)
        return await self._session.scalar(stmt)

    async def list_all(self) -> list[Group]:
        stmt = select(Group).order_by(Group.id)
        return list((await self._session.scalars(stmt)).all())

    async def get_or_create(self, telegram_chat_id: int, title: str | None) -> Group:
        group = await self.get_by_telegram_chat_id(telegram_chat_id)
        if group is not None:
            return group
        group = Group(telegram_chat_id=telegram_chat_id, title=title)
        return await self.add(group)

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

    async def list_groups_for_user(self, user_id: int) -> list[Group]:
        stmt = (
            select(Group)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(GroupMember.user_id == user_id)
            .order_by(Group.title)
        )
        return list((await self._session.scalars(stmt)).all())

    async def list_members(self, group_id: int) -> list[GroupMember]:
        stmt = select(GroupMember).where(GroupMember.group_id == group_id)
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
