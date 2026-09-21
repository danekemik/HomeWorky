import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

os.environ["BOT_TOKEN"] = "123456789:AAEtesttoken1234567890_ABC"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from app.database.models import Base
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


def _setup_sqlite(dbapi_connection, _connection_record) -> None:
    dbapi_connection.create_function(
        "lower", 1, lambda value: value.lower() if isinstance(value, str) else value
    )
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool
    )
    event.listen(engine.sync_engine, "connect", _setup_sqlite)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def session(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
