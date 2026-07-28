"""Shared state and runtime context for the orchestrator graph."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Business, Conversation

Intent = Literal["book", "reschedule", "cancel", "question", "escalate", "smalltalk"]

CALENDAR_INTENTS: frozenset[str] = frozenset({"book", "reschedule", "cancel"})


class VoxaState(TypedDict, total=False):
    """State threaded through the graph for a single customer turn."""

    # Inputs
    user_message: str
    history: list[dict[str, str]]

    # Set by intent_router
    intent: Intent
    router_reason: str

    # Set by the branch agents
    booking_draft: dict[str, Any]
    agent_result: dict[str, Any]
    sources: list[str]
    outcome: Literal["in_progress", "booked", "answered", "escalated"]

    # Set by response_compiler
    response_text: str


@dataclass
class AgentContext:
    """Per-invocation dependencies, passed via ``config["configurable"]``.

    Kept out of ``VoxaState`` so the state stays JSON-serialisable and the graph
    itself holds no request-scoped resources.
    """

    session: AsyncSession
    business: Business
    conversation: Conversation
    # Populated by nodes so the caller can act after the graph finishes
    # (e.g. send a confirmation email) without re-querying.
    created_booking_id: uuid.UUID | None = None
    notes: list[str] = field(default_factory=list)


def get_context(config: RunnableConfig) -> AgentContext:
    context = (config or {}).get("configurable", {}).get("ctx")
    if not isinstance(context, AgentContext):
        raise RuntimeError("AgentContext missing from graph config.")
    return context
