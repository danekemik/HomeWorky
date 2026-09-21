from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings


def _setup_sqlite(dbapi_connection: object, _connection_record: object) -> None:
    """SQLite: включаем внешние ключи и Unicode-aware LOWER (как в PostgreSQL)."""
    dbapi_connection.create_function(  # type: ignore[attr-defined]
        "lower", 1, lambda value: value.lower() if isinstance(value, str) else value
    )
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Database:
    """Тонкая обёртка над async-движком и фабрикой сессий SQLAlchemy."""

    def __init__(self, url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(url, pool_pre_ping=True)
        if url.startswith("sqlite"):
            event.listen(
                self._engine.sync_engine,
                "connect",
                _setup_sqlite,
            )
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            autoflush=False,
        )

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory

    async def ping(self) -> None:
        from sqlalchemy import text

        async with self._engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def create_schema(self) -> None:
        """Только для тестов и локальной разработки. В прод — Alembic-миграции."""
        from app.database.models import Base

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self._engine.dispose()

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session:
            yield session


database = Database(settings.DATABASE_URL)
