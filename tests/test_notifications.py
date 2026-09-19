from datetime import date

from app.database.models import Group, User
from app.database.repositories.group_repository import GroupRepository
from app.database.repositories.homework_repository import HomeworkRepository
from app.database.repositories.subject_repository import SubjectRepository
from app.database.repositories.user_repository import UserRepository
from app.services.notification_service import NotificationService


async def _seed(session) -> tuple[Group, User]:
    group = await GroupRepository(session).get_or_create(-1000000003, "Программисты")
    user = await UserRepository(session).get_or_create(
        333, username="student", first_name="Даня"
    )
    subject = await SubjectRepository(session).create(group.id, "Программирование")
    repo = HomeworkRepository(session)
    await repo.create(
        group_id=group.id,
        subject_id=subject.id,
        author_id=user.id,
        title="Лабораторная работа №2",
        deadline=date(2026, 9, 25),
    )
    return group, user


async def test_collect_digest_returns_items(session) -> None:
    group, _ = await _seed(session)
    service = NotificationService(session)
    items = await service.collect_digest(group.id, date(2026, 9, 25))
    assert len(items) == 1
    assert items[0].subject == "Программирование"
    assert items[0].title == "Лабораторная работа №2"


async def test_collect_digest_empty_other_date(session) -> None:
    group, _ = await _seed(session)
    service = NotificationService(session)
    assert await service.collect_digest(group.id, date(2026, 9, 26)) == []


async def test_build_digest_text(session) -> None:
    group, _ = await _seed(session)
    service = NotificationService(session)
    items = await service.collect_digest(group.id, date(2026, 9, 25))
    text = service.build_digest_text(date(2026, 9, 25), items)
    assert "ДЕДЛАЙНЫ НА ЗАВТРА" in text
    assert "25 сентября" in text
    assert "Лабораторная работа №2" in text
    assert "Всего заданий: 1" in text


async def test_build_digest_text_empty(session) -> None:
    service = NotificationService(session)
    assert service.build_digest_text(date(2026, 9, 25), []) == ""
