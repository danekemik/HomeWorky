import pytest
from app.database.repositories.user_repository import UserRepository
from app.services.user_service import (
    UserNameError,
    UserService,
    validate_display_name,
)


def test_validate_display_name_accepts_cyrillic() -> None:
    assert validate_display_name("иван") == "Иван"
    assert validate_display_name("  анна-мария  ") == "Анна-Мария"
    assert validate_display_name("серёжа") == "Серёжа"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "   ",
        "Ivan",
        "Ivanov",
        "123",
        "Иван1",
        "Иvан",
        "и",
        "а" * 65,
        "Иван, Петров",
    ],
)
def test_validate_display_name_rejects_bad(bad: str) -> None:
    with pytest.raises(UserNameError):
        validate_display_name(bad)


async def test_set_display_name_persists(session) -> None:
    user = await UserRepository(session).get_or_create(
        999, username="ivan", first_name="Иван"
    )
    service = UserService(session)
    name = await service.set_display_name(user, "иван иванов")
    assert name == "Иван Иванов"
    await session.commit()
    saved = await UserRepository(session).get_by_telegram_id(999)
    assert saved is not None and saved.display_name == "Иван Иванов"


async def test_rejects_non_cyrillic(session) -> None:
    user = await UserRepository(session).get_or_create(
        998, username="john", first_name="John"
    )
    service = UserService(session)
    with pytest.raises(UserNameError):
        await service.set_display_name(user, "John")
    assert user.display_name is None
