"""Engine, sessions, and schema lifecycle without business logic."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


DATA_DIR = Path("data")
DATABASE_URL = "sqlite+aiosqlite:///./data/electricity.db"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Base(DeclarativeBase):
    pass


engine = create_async_engine(DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Create initial tables for this course-project stage."""
    from app.models import alert, collection, electricity, user  # noqa: F401 -- registers ORM metadata

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def dispose_db() -> None:
    await engine.dispose()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
