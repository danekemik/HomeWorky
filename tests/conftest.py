import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

os.environ["BOT_TOKEN"] = "123456789:AAEtesttoken1234567890_ABC"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from app.database.models import Base
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def session(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
