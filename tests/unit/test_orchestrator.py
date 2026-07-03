import asyncio
import os
import pytest

from foundation.event_bus.event_bus import EventBus
from orchestrator.orchestrator import Orchestrator


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def orchestrator(event_bus):
    os.environ["HELIX_CONVERSATION_TIMEOUT"] = "60"
    return Orchestrator(event_bus)


@pytest.mark.asyncio
async def test_start_publishes_state_change(orchestrator):
    received = []

    async def capture(event):
        received.append(event)

    orchestrator._event_bus.subscribe("system.state.change", capture)
    await orchestrator.start()
    assert len(received) == 1
    assert received[0].payload["state"] == "sleep"
    await orchestrator.stop()


@pytest.mark.asyncio
async def test_has_correct_subscriptions(orchestrator):
    await orchestrator.start()
    assert "voice.wake.confirmed" in orchestrator._subscriptions
    assert "voice.listen.complete" in orchestrator._subscriptions
    assert "llm.generation.complete" in orchestrator._subscriptions
    assert "voice.tts.complete" in orchestrator._subscriptions
    assert "system.state.request" in orchestrator._subscriptions
    await orchestrator.stop()


@pytest.mark.asyncio
async def test_unsubscribe_on_stop(orchestrator):
    await orchestrator.start()
    await orchestrator.stop()
    assert len(orchestrator._subscriptions) == 0


@pytest.mark.asyncio
async def test_transition_from_sleep_to_conversation_on_wake(orchestrator):
    await orchestrator.start()
    assert orchestrator.current_state == "sleep"

    await orchestrator._on_wake_confirmed(
        type("Event", (), {
            "payload": {},
            "correlation_id": "c1",
        })()
    )
    assert orchestrator.current_state == "listening"
    await orchestrator.stop()


@pytest.mark.asyncio
async def test_transition_from_listening_to_sleep_on_timeout(orchestrator):
    await orchestrator.start()
    await orchestrator._transition("listening", "wake_word")

    await orchestrator._delayed_return_to_sleep()
    await asyncio.sleep(6)
    assert orchestrator.current_state == "sleep"
    await orchestrator.stop()


@pytest.mark.asyncio
async def test_state_request_updates_state(orchestrator):
    await orchestrator.start()
    await orchestrator._on_state_request(
        type("Event", (), {
            "payload": {"state": "background", "reason": "test"},
        })()
    )
    assert orchestrator.current_state == "background"
    await orchestrator.stop()
