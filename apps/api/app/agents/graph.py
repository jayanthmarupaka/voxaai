"""The Voxa orchestrator graph.

    START -> intent_router -> { calendar_agent | rag_agent | escalation_agent }
                                        -> response_compiler -> END

The conditional edge out of ``intent_router`` is the whole point of this
module: routing is an explicit, inspectable graph decision rather than one
prompt trying to do everything. ``rag_agent`` has a second conditional edge so
a question that is not covered by the business's documents falls through to
escalation instead of being answered from the model's general knowledge.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.nodes import (
    calendar_agent,
    escalation_agent,
    intent_router,
    rag_agent,
    response_compiler,
    route_after_rag,
    route_intent,
)
from app.agents.state import AgentContext, VoxaState
from app.models import Business, Conversation, Message

logger = logging.getLogger(__name__)

MAX_HISTORY_TURNS = 12


@lru_cache(maxsize=1)
def get_graph():
    """Build and compile the graph once per process."""
    builder = StateGraph(VoxaState)

    builder.add_node("intent_router", intent_router)
    builder.add_node("calendar_agent", calendar_agent)
    builder.add_node("rag_agent", rag_agent)
    builder.add_node("escalation_agent", escalation_agent)
    builder.add_node("response_compiler", response_compiler)

    builder.add_edge(START, "intent_router")
    builder.add_conditional_edges(
        "intent_router",
        route_intent,
        {
            "calendar_agent": "calendar_agent",
            "rag_agent": "rag_agent",
            "escalation_agent": "escalation_agent",
            "response_compiler": "response_compiler",
        },
    )
    builder.add_edge("calendar_agent", "response_compiler")
    builder.add_conditional_edges(
        "rag_agent",
        route_after_rag,
        {
            "escalation_agent": "escalation_agent",
            "response_compiler": "response_compiler",
        },
    )
    builder.add_edge("escalation_agent", "response_compiler")
    builder.add_edge("response_compiler", END)

    return builder.compile()


@dataclass
class TurnResult:
    conversation_id: uuid.UUID
    reply: str
    intent: str
    outcome: str
    sources: list[str]
    booking_id: uuid.UUID | None


async def get_or_create_conversation(
    session: AsyncSession,
    business: Business,
    conversation_id: uuid.UUID | None,
    channel: str = "text",
) -> Conversation:
    """Load a conversation, verifying it belongs to ``business``.

    A customer-supplied conversation ID is untrusted input, so a mismatch
    starts a fresh conversation rather than leaking another tenant's transcript.
    """
    if conversation_id is not None:
        conversation = await session.get(Conversation, conversation_id)
        if conversation is not None and conversation.business_id == business.id:
            return conversation
        logger.warning(
            "Ignoring conversation_id %s: missing or not owned by business %s.",
            conversation_id,
            business.id,
        )

    conversation = Conversation(business_id=business.id, channel=channel, outcome="in_progress")
    session.add(conversation)
    await session.flush()
    return conversation


async def _load_history(session: AsyncSession, conversation_id: uuid.UUID) -> list[dict[str, str]]:
    rows = await session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(MAX_HISTORY_TURNS)
    )
    return [
        {"role": message.role, "content": message.content} for message in reversed(list(rows))
    ]


async def run_turn(
    session: AsyncSession,
    business: Business,
    conversation: Conversation,
    user_message: str,
) -> TurnResult:
    """Run one customer turn through the graph and persist both messages."""
    history = await _load_history(session, conversation.id)

    ctx = AgentContext(session=session, business=business, conversation=conversation)
    state: VoxaState = {"user_message": user_message, "history": history}

    session.add(Message(conversation_id=conversation.id, role="customer", content=user_message))

    final_state = await get_graph().ainvoke(state, config={"configurable": {"ctx": ctx}})

    reply = final_state.get("response_text") or "Sorry, I didn't catch that."
    intent = final_state.get("intent", "smalltalk")
    outcome = final_state.get("outcome", "in_progress")

    session.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=reply,
            intent=intent,
        )
    )

    # Never downgrade a completed outcome: a conversation that produced a
    # booking stays "booked" even if the customer then says "thanks, bye".
    if conversation.outcome == "in_progress" or outcome in {"booked", "escalated"}:
        if outcome != "in_progress":
            conversation.outcome = outcome

    await session.flush()

    return TurnResult(
        conversation_id=conversation.id,
        reply=reply,
        intent=intent,
        outcome=conversation.outcome,
        sources=final_state.get("sources", []),
        booking_id=ctx.created_booking_id,
    )
