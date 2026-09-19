from zoneinfo import ZoneInfo

from app.config import settings


def test_default_settings() -> None:
    assert settings.TIMEZONE == "Europe/Moscow"
    assert settings.REMINDER_TIME == "20:00"
    assert isinstance(settings.tz, ZoneInfo)
    assert str(settings.tz) == "Europe/Moscow"
