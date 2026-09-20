from datetime import date

import pytest
from app.database.models import Group, MemberRole, User
from app.database.repositories.group_repository import GroupRepository
from app.database.repositories.homework_repository import HomeworkRepository
from app.database.repositories.subject_repository import SubjectRepository
from app.database.repositories.user_repository import UserRepository
from app.services.group_service import GroupError, GroupService
from sqlalchemy.exc import IntegrityError


async def _seed(session) -> tuple[Group, User]:
    user = await UserRepository(session).get_or_create(
        111, username="student", first_name="Иван"
    )
    group = await GroupService(session).create_group(creator=user, name="Группа 1")
    return group, user


async def test_user_get_or_create(session) -> None:
    user = await UserRepository(session).get_or_create(
        111, username="student", first_name="Иван", last_name=None
    )
    same = await UserRepository(session).get_by_telegram_id(111)
    assert same is not None and same.id == user.id


async def test_user_telegram_id_unique(session) -> None:
    repo = UserRepository(session)
    await repo.get_or_create(222)
    await session.commit()
    second_user = User(telegram_id=222, username="copy")
    session.add(second_user)
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_group_name_duplicate_is_rejected(session) -> None:
    user = await UserRepository(session).get_or_create(111)
    service = GroupService(session)
    await service.create_group(creator=user, name="Математика")
    with pytest.raises(GroupError):
        await service.create_group(creator=user, name="  математика ")


async def test_group_created_with_code_and_admin(session) -> None:
    group, user = await _seed(session)
    assert len(group.invite_code) == 10
    membership = await GroupRepository(session).get_membership(group.id, user.id)
    assert membership is not None and membership.role == MemberRole.ADMIN


async def test_group_membership_upsert_admin_promotion(session) -> None:
    group, _user = await _seed(session)
    other = await UserRepository(session).get_or_create(
        222, username="other", first_name="Пётр"
    )
    repo = GroupRepository(session)
    member = await repo.upsert_membership(group.id, other.id)
    assert member.role == MemberRole.MEMBER
    promoted = await repo.upsert_membership(group.id, other.id, MemberRole.ADMIN)
    assert promoted.role == MemberRole.ADMIN
    not_downgraded = await repo.upsert_membership(group.id, other.id)
    assert not_downgraded.role == MemberRole.ADMIN


async def test_list_groups_for_user(session) -> None:
    group, user = await _seed(session)
    membership = await GroupRepository(session).get_membership(group.id, user.id)
    assert membership is not None
    groups = await GroupRepository(session).list_groups_for_user(user.id)
    assert [g.id for g in groups] == [group.id]


async def test_homework_due_on_filter(session) -> None:
    group, user = await _seed(session)
    subject = await SubjectRepository(session).create(group.id, "Математика")
    repo = HomeworkRepository(session)
    await repo.create(
        group_id=group.id,
        subject_id=subject.id,
        author_id=user.id,
        title="Задачи №1-20",
        deadline=date(2026, 9, 25),
    )
    await repo.create(
        group_id=group.id,
        subject_id=subject.id,
        author_id=user.id,
        title="Задачи №1-20",
        deadline=date(2026, 9, 26),
    )
    due = await repo.list_due_on(group.id, date(2026, 9, 26))
    assert len(due) == 1
    assert due[0].deadline == date(2026, 9, 26)


async def test_homework_group_isolation(session) -> None:
    group, user = await _seed(session)
    other_group = await GroupService(session).create_group(
        creator=user, name="Чужая группа"
    )
    subject = await SubjectRepository(session).create(group.id, "Физика")
    other_subject = await SubjectRepository(session).create(other_group.id, "Физика")

    repo = HomeworkRepository(session)
    hw = await repo.create(
        group_id=group.id,
        subject_id=subject.id,
        author_id=user.id,
        title="ЛР №1",
        deadline=date(2026, 10, 1),
    )
    await repo.create(
        group_id=other_group.id,
        subject_id=other_subject.id,
        author_id=user.id,
        title="Чужое",
        deadline=date(2026, 10, 1),
    )
    assert await repo.get_for_group(hw.id, other_group.id) is None
    assert await repo.get_for_group(hw.id, group.id) is not None


async def test_homework_counts(session) -> None:
    group, user = await _seed(session)
    subject = await SubjectRepository(session).create(group.id, "Английский")
    repo = HomeworkRepository(session)
    await repo.create(
        group_id=group.id,
        subject_id=subject.id,
        author_id=user.id,
        title="Unit 4",
        deadline=date(2026, 10, 5),
    )
    assert await repo.count_for_group(group.id) == 1
    assert await repo.count_created_by(group.id, user.id) == 1


async def test_group_member_row_created(session) -> None:
    group, user = await _seed(session)
    member = await GroupRepository(session).get_membership(group.id, user.id)
    assert member is not None and member.group_id == group.id and member.user_id == user.id
