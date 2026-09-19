from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings


class Database:
    """Тонкая обёртка над async-движком и фабрикой сессий SQLAlchemy."""

    def __init__(self, url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(url, pool_pre_ping=True)
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
