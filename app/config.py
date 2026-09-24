from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/homework_bot"
    REDIS_URL: str | None = None
    TIMEZONE: str = "Europe/Moscow"
    REMINDER_TIME: str = "20:00"
    INVITE_CODE_TTL_DAYS: int = 3
    LOG_LEVEL: str = "INFO"
    RATE_LIMIT_MESSAGES_PER_SEC: float = 10.0
    TELEGRAM_REQUEST_TIMEOUT: float = 35.0
    TELEGRAM_PROXY: str | None = None

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.TIMEZONE)

    @property
    def reminder_time(self) -> time:
        hour, minute = self.REMINDER_TIME.split(":")
        return time(int(hour), int(minute))


settings = Settings()
