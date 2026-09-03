"""Async SQLAlchemy engine, session factory, declarative base, and FastAPI dependency.

Test note: the test suite (see tests/conftest.py) overrides DATABASE_URL to a
sqlite+aiosqlite in-memory database so the full stack runs without docker-compose.
Semantic search (memory/semantic.py) relies on the pgvector `<=>` operator and is
therefore only exercised against real Postgres; it is skipped/mocked under sqlite.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a scoped async DB session."""
    async with async_session_factory() as session:
        yield session
