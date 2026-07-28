"""Public customer-facing endpoints for the demo page.

Everything here is unauthenticated, so it is rate limited, accepts a business
ID from the URL, and exposes only non-sensitive business fields.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Request

from app.agents.graph import get_or_create_conversation, run_turn
from app.deps import PublicBusiness, SessionDep
from app.limiter import limiter
from app.models import Booking
from app.schemas import ChatRequest, ChatResponse, PublicBusinessOut
from app.services.notifications import send_booking_confirmation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/businesses/{business_id}", response_model=PublicBusinessOut)
@limiter.limit("60/minute")
async def get_public_business(request: Request, business: PublicBusiness) -> PublicBusinessOut:
    return PublicBusinessOut.model_validate(business)


@router.post("/businesses/{business_id}/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat(
    request: Request,
    payload: ChatRequest,
    business: PublicBusiness,
    session: SessionDep,
    background: BackgroundTasks,
) -> ChatResponse:
    conversation = await get_or_create_conversation(
        session, business, payload.conversation_id, channel="text"
    )
    result = await run_turn(session, business, conversation, payload.message)

    if result.booking_id is not None:
        booking = await session.get(Booking, result.booking_id)
        if booking is not None and booking.customer_email:
            # Runs after the response is sent, and after this request's
            # transaction has committed.
            background.add_task(_send_confirmation, result.booking_id)

    return ChatResponse(
        conversation_id=result.conversation_id,
        reply=result.reply,
        intent=result.intent,
        outcome=result.outcome,
        sources=result.sources,
    )


async def _send_confirmation(booking_id) -> None:
    """Re-load in a fresh session; the request session is already closed."""
    from app.db import SessionLocal
    from app.models import Business

    async with SessionLocal() as session:
        booking = await session.get(Booking, booking_id)
        if booking is None:
            return
        business = await session.get(Business, booking.business_id)
        if business is None:
            return
        await send_booking_confirmation(booking, business)
