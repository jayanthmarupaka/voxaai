"""The single most important property of a multi-tenant app: no cross-tenant reads.

Every one of these tests writes data for two businesses and then asserts that a
query scoped to one can never see the other's rows. Requires a live database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    Booking,
    Business,
    Conversation,
    Document,
    DocumentChunk,
    FollowUpTask,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.db]


def _fake_embedding(seed: float) -> list[float]:
    return [seed] * settings.embedding_dimensions


def _document(business_id: uuid.UUID, filename: str) -> Document:
    return Document(
        business_id=business_id,
        filename=filename,
        mime_type="text/plain",
        byte_size=32,
        status="ready",
    )


async def test_documents_are_scoped_to_their_business(
    session: AsyncSession, two_businesses: tuple[Business, Business]
):
    alpha, beta = two_businesses
    session.add_all([_document(alpha.id, "alpha-prices.txt"), _document(beta.id, "beta-prices.txt")])
    await session.flush()

    visible = (
        (await session.execute(select(Document.filename).where(Document.business_id == alpha.id)))
        .scalars()
        .all()
    )

    assert visible == ["alpha-prices.txt"]


async def test_vector_search_never_crosses_tenants(
    session: AsyncSession, two_businesses: tuple[Business, Business]
):
    """Beta's chunk is a *closer* vector match, so only the filter can exclude it."""
    alpha, beta = two_businesses
    alpha_doc = _document(alpha.id, "a.txt")
    beta_doc = _document(beta.id, "b.txt")
    session.add_all([alpha_doc, beta_doc])
    await session.flush()

    query_vector = _fake_embedding(0.5)
    session.add_all(
        [
            DocumentChunk(
                document_id=alpha_doc.id,
                business_id=alpha.id,
                chunk_index=0,
                content="Alpha charges 50 dollars for a cleaning.",
                embedding=_fake_embedding(0.1),
            ),
            DocumentChunk(
                document_id=beta_doc.id,
                business_id=beta.id,
                chunk_index=0,
                content="Beta charges 90 dollars for a cleaning.",
                embedding=query_vector,  # an exact match
            ),
        ]
    )
    await session.flush()

    rows = (
        (
            await session.execute(
                select(DocumentChunk.content)
                .where(DocumentChunk.business_id == alpha.id)
                .order_by(DocumentChunk.embedding.cosine_distance(query_vector))
                .limit(5)
            )
        )
        .scalars()
        .all()
    )

    assert len(rows) == 1
    assert "Alpha" in rows[0]


async def test_bookings_are_scoped(session: AsyncSession, two_businesses: tuple[Business, Business]):
    alpha, beta = two_businesses
    alpha_convo = Conversation(business_id=alpha.id, channel="text")
    beta_convo = Conversation(business_id=beta.id, channel="text")
    session.add_all([alpha_convo, beta_convo])
    await session.flush()

    start = datetime.now(UTC) + timedelta(days=1)
    session.add_all(
        [
            Booking(
                business_id=alpha.id,
                conversation_id=alpha_convo.id,
                customer_name="Alpha Customer",
                starts_at=start,
                ends_at=start + timedelta(minutes=30),
                status="confirmed",
            ),
            Booking(
                business_id=beta.id,
                conversation_id=beta_convo.id,
                customer_name="Beta Customer",
                starts_at=start,
                ends_at=start + timedelta(minutes=30),
                status="confirmed",
            ),
        ]
    )
    await session.flush()

    names = (
        (
            await session.execute(
                select(Booking.customer_name).where(Booking.business_id == alpha.id)
            )
        )
        .scalars()
        .all()
    )
    assert names == ["Alpha Customer"]


async def test_fetching_another_tenants_row_by_id_returns_nothing(
    session: AsyncSession, two_businesses: tuple[Business, Business]
):
    """Guessing a UUID must not be enough — the business_id filter is the gate."""
    alpha, beta = two_businesses
    beta_doc = _document(beta.id, "secret.txt")
    session.add(beta_doc)
    await session.flush()

    stolen = (
        await session.execute(
            select(Document).where(Document.id == beta_doc.id, Document.business_id == alpha.id)
        )
    ).scalar_one_or_none()

    assert stolen is None


async def test_follow_ups_are_scoped(
    session: AsyncSession, two_businesses: tuple[Business, Business]
):
    alpha, beta = two_businesses
    alpha_convo = Conversation(business_id=alpha.id, channel="voice")
    beta_convo = Conversation(business_id=beta.id, channel="voice")
    session.add_all([alpha_convo, beta_convo])
    await session.flush()

    session.add_all(
        [
            FollowUpTask(
                business_id=alpha.id,
                conversation_id=alpha_convo.id,
                question="Do you do implants?",
                status="open",
            ),
            FollowUpTask(
                business_id=beta.id,
                conversation_id=beta_convo.id,
                question="Do you do balayage?",
                status="open",
            ),
        ]
    )
    await session.flush()

    count = await session.scalar(
        select(func.count()).select_from(FollowUpTask).where(FollowUpTask.business_id == beta.id)
    )
    assert count == 1


async def test_deleting_a_document_removes_its_chunks(
    session: AsyncSession, two_businesses: tuple[Business, Business]
):
    """Cascades matter: an orphaned chunk would linger in the vector index."""
    alpha, _ = two_businesses
    document = _document(alpha.id, "temp.txt")
    session.add(document)
    await session.flush()
    session.add(
        DocumentChunk(
            document_id=document.id,
            business_id=alpha.id,
            chunk_index=0,
            content="text",
            embedding=_fake_embedding(0.2),
        )
    )
    await session.flush()
    document_id = document.id

    await session.delete(document)
    await session.flush()

    remaining = await session.scalar(
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
    )
    assert remaining == 0


async def test_clerk_org_id_is_unique(
    session: AsyncSession, two_businesses: tuple[Business, Business]
):
    """Two businesses must never be able to claim the same Clerk organisation."""
    alpha, _ = two_businesses
    session.add(Business(clerk_org_id=alpha.clerk_org_id, name="Impostor", timezone="UTC"))

    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_booking_cannot_end_before_it_starts(
    session: AsyncSession, two_businesses: tuple[Business, Business]
):
    alpha, _ = two_businesses
    start = datetime.now(UTC) + timedelta(days=1)
    session.add(
        Booking(
            business_id=alpha.id,
            customer_name="Backwards",
            starts_at=start,
            ends_at=start - timedelta(minutes=30),
            status="confirmed",
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_unknown_business_id_yields_no_rows(session: AsyncSession, database_available: bool):
    ghost = uuid.uuid4()
    rows = (
        (await session.execute(select(Document).where(Document.business_id == ghost)))
        .scalars()
        .all()
    )
    assert rows == []
