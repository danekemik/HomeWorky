from datetime import date, timedelta

import pytest
from app.database.models import AttachmentType
from app.database.repositories.group_repository import GroupRepository
from app.database.repositories.homework_repository import HomeworkRepository
from app.database.repositories.subject_repository import SubjectRepository
from app.database.repositories.user_repository import UserRepository
from app.services import homework_service
from app.services.group_service import GroupService
from app.services.homework_service import HomeworkService


async def _seed(session) -> tuple:
    admin = await UserRepository(session).get_or_create(
        333, username="admin", first_name="Аня"
    )
    group = await GroupService(session).create_group(creator=admin, name="Группа 1")
    owner = await UserRepository(session).get_or_create(
        111, username="owner", first_name="Иван"
    )
    other = await UserRepository(session).get_or_create(
        222, username="other", first_name="Пётр"
    )
    await GroupRepository(session).upsert_membership(group.id, owner.id)
    await GroupRepository(session).upsert_membership(group.id, other.id)
    subject = await SubjectRepository(session).create(group.id, "Математика")
    return group, owner, other, admin, subject


async def _make_hw(session, group, subject, author, deadline: date):
    return await HomeworkRepository(session).create(
        group_id=group.id,
        subject_id=subject.id,
        author_id=author.id,
        title="Задачи №1-20",
        deadline=deadline,
        description="Стр 10-14",
    )


async def test_can_modify_owner_admin_only(session) -> None:
    group, owner, other, admin, subject = await _seed(session)
    hw = await _make_hw(session, group, subject, owner, date(2026, 9, 25))
    service = HomeworkService(session)
    assert await service.can_modify(owner, group.id, hw) is True
    assert await service.can_modify(other, group.id, hw) is False
    assert await service.can_modify(admin, group.id, hw) is True


async def test_delete_by_raises_for_non_owner(session) -> None:
    group, owner, other, _admin, subject = await _seed(session)
    hw = await _make_hw(session, group, subject, owner, date(2026, 9, 25))
    service = HomeworkService(session)
    with pytest.raises(homework_service.HomeworkAccessError):
        await service.delete_by(other, group, hw)
    await service.delete_by(owner, group, hw)


async def test_nearest_splits_today_tomorrow(session) -> None:
    group, owner, _other, _admin, subject = await _seed(session)
    today = date(2026, 9, 19)
    await _make_hw(session, group, subject, owner, today)
    await _make_hw(session, group, subject, owner, today + timedelta(days=1))
    await _make_hw(session, group, subject, owner, today + timedelta(days=2))
    today_items, tomorrow_items = await HomeworkService(session).nearest(
        group.id, today
    )
    assert len(today_items) == 1
    assert len(tomorrow_items) == 1
    assert today_items[0].deadline == today
    assert tomorrow_items[0].deadline == today + timedelta(days=1)


async def test_lists_by_category(session) -> None:
    group, owner, other, _admin, subject = await _seed(session)
    today = date(2026, 9, 19)
    service = HomeworkService(session)
    await _make_hw(session, group, subject, owner, today + timedelta(days=3))
    await _make_hw(session, group, subject, other, today - timedelta(days=2))
    await _make_hw(session, group, subject, owner, today)
    assert len(await service.list_active(group.id, today)) == 2
    assert len(await service.list_past(group.id, today)) == 1
    assert len(await service.list_created_by(group.id, owner.id)) == 2


async def test_attach_files_and_links_then_detail(session) -> None:
    group, owner, _other, _admin, subject = await _seed(session)
    hw = await _make_hw(session, group, subject, owner, date(2026, 9, 25))
    service = HomeworkService(session)
    await service.attach_pending(
        hw,
        attachments=[
            {
                "telegram_file_id": "AAA111",
                "file_type": AttachmentType.DOCUMENT.value,
                "file_name": "ЛР2.pdf",
            }
        ],
        links=[{"url": "https://example.com", "title": "Материалы"}],
    )
    detail = await service.get_detail(hw)
    assert detail.subject == "Математика"
    assert detail.author_name == "Иван"
    assert detail.attachments[0].file_name == "ЛР2.pdf"
    assert detail.links[0].title == "Материалы"


async def test_edit_fields_and_set_subject(session) -> None:
    group, owner, _other, _admin, subject = await _seed(session)
    hw = await _make_hw(session, group, subject, owner, date(2026, 9, 25))
    subject_2 = await SubjectRepository(session).create(group.id, "Физика")
    service = HomeworkService(session)
    await service.update_homework(hw, title="Новое название")
    assert hw.title == "Новое название"
    assert hw.description == "Стр 10-14"
    await service.set_subject(hw, subject_2.id)
    assert hw.subject_id == subject_2.id


async def test_stats(session) -> None:
    group, owner, other, _admin, subject = await _seed(session)
    today = date(2026, 9, 19)
    service = HomeworkService(session)
    await _make_hw(session, group, subject, owner, today)
    await _make_hw(session, group, subject, owner, today + timedelta(days=1))
    await _make_hw(session, group, subject, other, today + timedelta(days=5))
    stats = await service.stats(group.id, owner.id, today)
    assert stats["total"] == 3
    assert stats["active"] == 3
    assert stats["today"] == 1
    assert stats["tomorrow"] == 1
    assert stats["created_by_me"] == 2


async def test_list_all_groups(session) -> None:
    user = await UserRepository(session).get_or_create(444, username="u")
    service = GroupService(session)
    await service.create_group(creator=user, name="Группа 1")
    await service.create_group(creator=user, name="Группа 2")
    groups = await GroupRepository(session).list_all()
    assert len(groups) == 2
