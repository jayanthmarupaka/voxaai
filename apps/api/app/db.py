"""Async SQLAlchemy engine and session management."""

from __future__ import annotations

import ssl
from collections.abc import AsyncIterator
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


def _connect_args(database_url: str) -> dict[str, object]:
    """Managed Postgres (Neon/Render) requires TLS; local Postgres does not."""
    host = urlparse(database_url.replace("postgresql+asyncpg://", "postgresql://", 1)).hostname
    if host in {"localhost", "127.0.0.1", "::1", None}:
        return {}
    context = ssl.create_default_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return {"ssl": context}


def create_engine() -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        connect_args=_connect_args(settings.database_url),
        pool_pre_ping=True,  # Neon idles connections out; revalidate before use.
        pool_size=5,
        max_overflow=5,
        pool_recycle=280,
        echo=False,
    )


engine: AsyncEngine = create_engine()

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
