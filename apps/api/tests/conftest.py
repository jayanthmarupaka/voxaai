"""Shared pytest fixtures.

Tests run against a real Postgres with pgvector (the same DATABASE_URL used for
development) because the things worth testing here — pgvector similarity search
and tenant-scoped SQL — have no meaningful SQLite equivalent.

Each test gets its own schema-level isolation by creating two throwaway
businesses and asserting across them.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "")

from app.db import SessionLocal, engine  # noqa: E402
from app.models import Business  # noqa: E402


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "db: requires a live Postgres with pgvector")
    config.addinivalue_line("markers", "llm: requires live Azure OpenAI credentials")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


async def _database_reachable() -> bool:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest_asyncio.fixture(scope="session")
async def database_available() -> bool:
    available = await _database_reachable()
    if not available:
        pytest.skip("No database reachable at DATABASE_URL; skipping database tests.")
    return available


@pytest_asyncio.fixture
async def session(database_available: bool) -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as db_session:
        yield db_session
        await db_session.rollback()


@pytest_asyncio.fixture
async def two_businesses(session: AsyncSession) -> AsyncIterator[tuple[Business, Business]]:
    """Two isolated tenants, removed again after the test."""
    suffix = uuid.uuid4().hex[:8]
    alpha = Business(clerk_org_id=f"org_test_alpha_{suffix}", name="Alpha Dental", timezone="UTC")
    beta = Business(clerk_org_id=f"org_test_beta_{suffix}", name="Beta Salon", timezone="UTC")
    session.add_all([alpha, beta])
    await session.flush()

    try:
        yield alpha, beta
    finally:
        await session.rollback()
        async with SessionLocal() as cleanup:
            for business in (alpha, beta):
                existing = await cleanup.get(Business, business.id)
                if existing is not None:
                    await cleanup.delete(existing)
            await cleanup.commit()
