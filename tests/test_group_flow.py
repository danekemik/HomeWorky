from datetime import timedelta

import pytest
from aiogram.enums import ChatType
from aiogram.types import Chat
from app.database.models import MemberRole, User
from app.database.repositories.group_repository import GroupRepository
from app.database.repositories.user_repository import UserRepository
from app.services.group_service import (
    GroupError,
    GroupService,
    _utcnow,
    format_code,
    normalize_code,
)


async def _creator(session) -> User:
    return await UserRepository(session).get_or_create(
        1, username="creator", first_name="Староста"
    )


async def _member(session, telegram_id: int) -> User:
    return await UserRepository(session).get_or_create(
        telegram_id, username=f"user{telegram_id}", first_name=f"Участник{telegram_id}"
    )


async def test_create_group_assigns_admin_and_code(session) -> None:
    creator = await _creator(session)
    group = await GroupService(session).create_group(creator=creator, name="ВКБ-22")
    assert len(group.invite_code) == 10
    assert group.invite_code.isalnum()
    assert group.invite_code_expires_at is not None
    membership = await GroupRepository(session).get_membership(group.id, creator.id)
    assert membership is not None and membership.role == MemberRole.ADMIN


async def test_create_group_duplicate_name(session) -> None:
    creator = await _creator(session)
    service = GroupService(session)
    await service.create_group(creator=creator, name="Математика")
    with pytest.raises(GroupError):
        await service.create_group(creator=creator, name="математика ")


async def test_join_group_wrong_code(session) -> None:
    creator = await _creator(session)
    group = await GroupService(session).create_group(creator=creator, name="Физика")
    member = await _member(session, 2)
    service = GroupService(session)
    error = await service.join_group(group=group, user=member, code="ZZZZZZZZZZ")
    assert error is not None
    assert await GroupRepository(session).get_membership(group.id, member.id) is None


async def test_join_group_success(session) -> None:
    creator = await _creator(session)
    group = await GroupService(session).create_group(creator=creator, name="Химия")
    member = await _member(session, 2)
    service = GroupService(session)
    error = await service.join_group(group=group, user=member, code=group.invite_code)
    assert error is None
    membership = await GroupRepository(session).get_membership(group.id, member.id)
    assert membership is not None and membership.role == MemberRole.MEMBER
    assert await service.has_access(group, member)


async def test_join_group_expired_code(session) -> None:
    creator = await _creator(session)
    group = await GroupService(session).create_group(creator=creator, name="Биология")
    group.invite_code_expires_at = _utcnow() - timedelta(minutes=1)
    await session.commit()
    member = await _member(session, 2)
    error = await GroupService(session).join_group(
        group=group, user=member, code=group.invite_code
    )
    assert error is not None
    assert await GroupRepository(session).get_membership(group.id, member.id) is None


async def test_invite_info_regenerates_expired_code(session) -> None:
    creator = await _creator(session)
    group = await GroupService(session).create_group(creator=creator, name="Химура")
    group.invite_code_expires_at = _utcnow() - timedelta(minutes=1)
    await session.commit()
    service = GroupService(session)
    old_code = group.invite_code
    code, expires_at = await service.invite_info(group)
    assert code != old_code
    assert expires_at >= _utcnow()


async def test_remove_member_creator_forbidden(session) -> None:
    creator = await _creator(session)
    group = await GroupService(session).create_group(creator=creator, name="Истфак")
    service = GroupService(session)
    with pytest.raises(GroupError):
        await service.remove_member(group, creator.id)


async def test_remove_member_revokes_access(session) -> None:
    creator = await _creator(session)
    group = await GroupService(session).create_group(creator=creator, name="Турбо")
    member = await _member(session, 2)
    service = GroupService(session)
    await service.join_group(group=group, user=member, code=group.invite_code)
    await service.remove_member(group, member.id)
    assert await GroupRepository(session).get_membership(group.id, member.id) is None
    assert not await service.has_access(group, member)
    assert not await service.is_admin(group, member)


async def test_is_admin_and_member(session) -> None:
    creator = await _creator(session)
    group = await GroupService(session).create_group(creator=creator, name="Лингвистика")
    member = await _member(session, 2)
    service = GroupService(session)
    await service.join_group(group=group, user=member, code=group.invite_code)
    assert await service.is_admin(group, creator)
    assert not await service.is_admin(group, member)


async def test_bind_chat_creates_and_conflicts(session) -> None:
    creator = await _creator(session)
    service = GroupService(session)
    group = await service.create_group(creator=creator, name="Первая")
    other = await service.create_group(creator=creator, name="Вторая")
    chat = Chat(id=-100123, type=ChatType.SUPERGROUP, title="Первая")
    assert await service.bind_chat(group, chat) is None
    assert group.telegram_chat_id == -100123
    error = await service.bind_chat(other, chat)
    assert error is not None
    assert other.telegram_chat_id is None


async def test_code_normalize_and_format_roundtrip(session) -> None:
    raw = "ab3d7x9f2k"
    assert normalize_code(raw) == "AB3D7X9F2K"
    assert normalize_code(" AB3D7-X9F2K ") == "AB3D7X9F2K"
    formatted = format_code("ab3d7x9f2k")
    assert formatted == "ab3d7-x9f2k"
    assert normalize_code(formatted) == "AB3D7X9F2K"
