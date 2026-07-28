"""Dashboard read/write endpoints: conversations, bookings, follow-up tasks."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import CurrentBusiness, SessionDep
from app.models import Booking, Conversation, FollowUpTask
from app.schemas import (
    BookingOut,
    ConversationDetail,
    ConversationOut,
    FollowUpOut,
    FollowUpUpdate,
)

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    business: CurrentBusiness,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ConversationOut]:
    rows = await session.scalars(
        select(Conversation)
        .where(Conversation.business_id == business.id)
        .order_by(Conversation.started_at.desc())
        .limit(limit)
    )
    return [ConversationOut.model_validate(row) for row in rows]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID, business: CurrentBusiness, session: SessionDep
) -> ConversationDetail:
    conversation = await session.scalar(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(
            Conversation.id == conversation_id,
            Conversation.business_id == business.id,
        )
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found."
        )
    return ConversationDetail.model_validate(conversation)


@router.get("/bookings", response_model=list[BookingOut])
async def list_bookings(
    business: CurrentBusiness,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[BookingOut]:
    rows = await session.scalars(
        select(Booking)
        .where(Booking.business_id == business.id)
        .order_by(Booking.starts_at.desc())
        .limit(limit)
    )
    return [BookingOut.model_validate(row) for row in rows]


@router.get("/follow-ups", response_model=list[FollowUpOut])
async def list_follow_ups(
    business: CurrentBusiness,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status", pattern=r"^(open|resolved)$"),
) -> list[FollowUpOut]:
    query = select(FollowUpTask).where(FollowUpTask.business_id == business.id)
    if status_filter:
        query = query.where(FollowUpTask.status == status_filter)
    rows = await session.scalars(query.order_by(FollowUpTask.created_at.desc()).limit(200))
    return [FollowUpOut.model_validate(row) for row in rows]


@router.patch("/follow-ups/{task_id}", response_model=FollowUpOut)
async def update_follow_up(
    task_id: uuid.UUID,
    payload: FollowUpUpdate,
    business: CurrentBusiness,
    session: SessionDep,
) -> FollowUpOut:
    task = await session.scalar(
        select(FollowUpTask).where(
            FollowUpTask.id == task_id,
            FollowUpTask.business_id == business.id,
        )
    )
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

    task.status = payload.status
    task.resolved_at = datetime.now(UTC) if payload.status == "resolved" else None
    await session.flush()
    return FollowUpOut.model_validate(task)
