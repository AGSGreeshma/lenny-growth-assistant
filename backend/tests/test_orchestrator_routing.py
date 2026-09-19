"""
Agent-layer routing (app/agent/orchestrator.py): the heuristic fallback
classifier, and the fact that classify_intent() degrades to it whenever the
Claude Agent SDK path fails for any reason. This is what keeps the app fully
functional offline (mandatory Ollama-only demo) even though the "real" agent
layer is cloud-based.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.agent.orchestrator import (
    RoutingDecision,
    _classify_via_heuristics,
    _looks_referential,
    classify_intent,
)


@pytest.mark.parametrize(
    "message,expected_intent",
    [
        ("How do I improve activation for a B2B SaaS product?", "chat"),
        ("Turn this into a Ship 30 for 30 essay", "essay"),
        ("write a ship 30 post about onboarding", "essay"),
        ("Give me this as an HTML page", "html_artifact"),
        ("Can you make a one-pager summarizing this?", "html_artifact"),
        ("What did Brian Chesky say about pricing?", "chat"),
    ],
)
def test_heuristic_classifier_intents(message, expected_intent):
    decision = _classify_via_heuristics(message)
    assert decision.intent == expected_intent
    assert decision.used_agent_sdk is False


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Turn this into a Ship 30 for 30 essay", True),
        ("Give me this as an HTML page", True),
        ("Can you make a one-pager summarizing this?", True),
        ("write a ship 30 post about onboarding", False),
        ("What did Brian Chesky say about pricing?", False),
    ],
)
def test_looks_referential(message, expected):
    assert _looks_referential(message) is expected


def test_heuristic_classifier_resolves_referential_topic_from_history():
    # A bare "turn this into an essay" has no topic of its own -- the topic
    # should come from the last real question in the conversation, not the
    # literal referential phrase (see orchestrator.py's _looks_referential).
    history = [
        {"role": "user", "content": "How do I improve onboarding activation?"},
        {"role": "assistant", "content": "Focus on the aha-moment..."},
    ]
    decision = _classify_via_heuristics("Turn this into a Ship 30 for 30 essay", history)
    assert decision.intent == "essay"
    assert decision.topic == "How do I improve onboarding activation?"


def test_heuristic_classifier_keeps_self_contained_topic_even_with_history():
    # When the message already names its own subject, history should not
    # override it.
    history = [{"role": "user", "content": "How do I improve onboarding activation?"}]
    decision = _classify_via_heuristics("write a ship 30 post about retention", history)
    assert decision.intent == "essay"
    assert decision.topic == "write a ship 30 post about retention"


def test_heuristic_classifier_referential_with_no_history_keeps_literal_message():
    # No prior user turn to resolve against -- fall back to the literal
    # message rather than raising or returning an empty topic.
    decision = _classify_via_heuristics("Turn this into a Ship 30 for 30 essay", history=None)
    assert decision.intent == "essay"
    assert decision.topic == "Turn this into a Ship 30 for 30 essay"


@pytest.mark.asyncio
async def test_classify_intent_falls_back_to_heuristics_when_agent_sdk_fails():
    with patch.object(
        __import__("app.agent.orchestrator", fromlist=["_classify_via_agent_sdk"]),
        "_classify_via_agent_sdk",
        AsyncMock(side_effect=RuntimeError("claude CLI not found")),
    ), patch("app.agent.orchestrator.AGENT_SDK_ENABLED", True):
        decision = await classify_intent("how do I grow retention?", db=None)

    assert isinstance(decision, RoutingDecision)
    assert decision.used_agent_sdk is False
    assert decision.intent == "chat"
    assert decision.router_error is not None


@pytest.mark.asyncio
async def test_classify_intent_skips_agent_sdk_when_disabled():
    agent_sdk_mock = AsyncMock()
    with patch("app.agent.orchestrator.AGENT_SDK_ENABLED", False), patch(
        "app.agent.orchestrator._classify_via_agent_sdk", agent_sdk_mock
    ):
        decision = await classify_intent("turn this into an essay", db=None)

    agent_sdk_mock.assert_not_called()
    assert decision.intent == "essay"
    assert decision.used_agent_sdk is False


@pytest.mark.asyncio
async def test_classify_intent_uses_agent_sdk_result_when_it_succeeds():
    fake_decision = RoutingDecision(intent="html_artifact", topic="pricing page", used_agent_sdk=True)
    with patch("app.agent.orchestrator.AGENT_SDK_ENABLED", True), patch(
        "app.agent.orchestrator._classify_via_agent_sdk", AsyncMock(return_value=fake_decision)
    ):
        decision = await classify_intent("some message", db=None)

    assert decision.used_agent_sdk is True
    assert decision.intent == "html_artifact"
    assert decision.topic == "pricing page"
