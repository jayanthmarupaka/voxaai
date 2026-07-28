"""Pydantic request/response schemas for the REST API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Business
# ---------------------------------------------------------------------------


class BusinessHoursWindow(BaseModel):
    open: str = Field(pattern=r"^\d{2}:\d{2}$")
    close: str = Field(pattern=r"^\d{2}:\d{2}$")


class ServiceItem(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    duration_minutes: int = Field(default=30, ge=5, le=480)


class BusinessOut(ORMModel):
    id: uuid.UUID
    name: str
    timezone: str
    greeting: str
    business_hours: dict[str, list[BusinessHoursWindow]]
    services: list[ServiceItem]


class PublicBusinessOut(ORMModel):
    """Everything the unauthenticated demo page is allowed to see."""

    id: uuid.UUID
    name: str
    greeting: str
    timezone: str
    services: list[ServiceItem]


class BusinessUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    timezone: str | None = Field(default=None, max_length=64)
    greeting: str | None = Field(default=None, max_length=1000)
    business_hours: dict[str, list[BusinessHoursWindow]] | None = None
    services: list[ServiceItem] | None = None


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


class DocumentOut(ORMModel):
    id: uuid.UUID
    filename: str
    mime_type: str
    byte_size: int
    status: str
    error: str | None
    created_at: datetime


class DocumentUploadResult(BaseModel):
    document: DocumentOut
    chunks_indexed: int


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    reply: str
    intent: str
    outcome: str
    sources: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


class MessageOut(ORMModel):
    id: uuid.UUID
    role: str
    content: str
    intent: str | None
    created_at: datetime


class ConversationOut(ORMModel):
    id: uuid.UUID
    channel: str
    outcome: str
    customer_name: str | None
    customer_email: str | None
    started_at: datetime
    ended_at: datetime | None


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


# ---------------------------------------------------------------------------
# Bookings and follow-ups
# ---------------------------------------------------------------------------


class BookingOut(ORMModel):
    id: uuid.UUID
    customer_name: str
    customer_email: str | None
    customer_phone: str | None
    service: str | None
    starts_at: datetime
    ends_at: datetime
    status: str
    google_event_id: str | None
    created_at: datetime


class FollowUpOut(ORMModel):
    id: uuid.UUID
    conversation_id: uuid.UUID | None
    question: str
    customer_name: str | None
    customer_email: str | None
    customer_phone: str | None
    status: str
    created_at: datetime
    resolved_at: datetime | None


class FollowUpUpdate(BaseModel):
    status: str = Field(pattern=r"^(open|resolved)$")


# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------


class GoogleStatus(BaseModel):
    connected: bool
    calendar_id: str | None = None
    google_account_email: str | None = None
    connected_at: datetime | None = None
    oauth_configured: bool = True


class AvailabilityOut(BaseModel):
    slots: list[datetime]
