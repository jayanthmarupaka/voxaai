"""The graph's shape and routing decisions, with the LLM and DB stubbed out.

These tests assert the thing the architecture is actually about: that the
router sends each intent to the right node, and that an unanswerable question
falls through to escalation rather than being answered from general knowledge.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.agents.graph import get_graph
from app.agents.nodes import response_compiler, route_after_rag, route_intent
from app.agents.state import AgentContext
from app.models import Business


@pytest.mark.parametrize(
    ("intent", "expected_node"),
    [
        ("book", "calendar_agent"),
        ("reschedule", "calendar_agent"),
        ("cancel", "calendar_agent"),
        ("question", "rag_agent"),
        ("escalate", "escalation_agent"),
        ("smalltalk", "response_compiler"),
    ],
)
def test_router_sends_each_intent_to_the_right_node(intent, expected_node):
    assert route_intent({"intent": intent}) == expected_node


def test_unknown_intent_falls_back_to_escalation():
    """Anything unrecognised must escalate to a human, never be improvised."""
    assert route_intent({}) == "escalation_agent"
    assert route_intent({"intent": "something_new"}) == "escalation_agent"


def test_unanswerable_question_escalates_instead_of_guessing():
    assert route_after_rag({"agent_result": {"kind": "no_answer"}}) == "escalation_agent"
    assert route_after_rag({"agent_result": {"kind": "answer"}}) == "response_compiler"


def _need_time_state(history: list[dict[str, str]]) -> tuple[dict, dict]:
    """A need_time turn offering two fixed slots, with the given history."""
    start = datetime.now(UTC).replace(microsecond=0) + timedelta(days=3)
    state = {
        "history": history,
        "user_message": "sometime in the morning",
        "agent_result": {
            "kind": "need_time",
            "suggestions": [start.isoformat(), (start + timedelta(minutes=15)).isoformat()],
        },
    }
    config = {
        "configurable": {
            "ctx": AgentContext(
                session=None,
                business=Business(name="Test Practice", timezone="UTC"),
                conversation=None,
            )
        }
    }
    return state, config


async def test_asking_for_a_time_twice_does_not_repeat_the_same_sentence():
    """A caller who never names a time must not hear identical words each turn."""
    state, config = _need_time_state([])
    first = (await response_compiler(state, config))["response_text"]

    state, config = _need_time_state([{"role": "assistant", "content": first}])
    second = (await response_compiler(state, config))["response_text"]

    assert second != first
    assert "didn't catch a time" in second


async def test_a_newly_given_name_is_acknowledged():
    state, config = _need_time_state([])
    state["agent_result"]["customer_name"] = "Priya Nair"
    text = (await response_compiler(state, config))["response_text"]
    assert text.startswith("Thanks, Priya.")


def test_graph_has_the_expected_nodes_and_edges():
    graph = get_graph().get_graph()
    node_ids = set(graph.nodes)

    for expected in {
        "intent_router",
        "calendar_agent",
        "rag_agent",
        "escalation_agent",
        "response_compiler",
    }:
        assert expected in node_ids

    edges = {(edge.source, edge.target) for edge in graph.edges}

    # The router fans out to all three tool agents.
    assert ("intent_router", "calendar_agent") in edges
    assert ("intent_router", "rag_agent") in edges
    assert ("intent_router", "escalation_agent") in edges

    # Everything funnels back through the compiler.
    assert ("calendar_agent", "response_compiler") in edges
    assert ("escalation_agent", "response_compiler") in edges

    # RAG's second decision point.
    assert ("rag_agent", "escalation_agent") in edges
    assert ("rag_agent", "response_compiler") in edges
