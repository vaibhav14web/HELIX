import asyncio
import os
import pytest

from foundation.event_bus.event_bus import EventBus
from core_ai.wake_word_engine.wake_word_engine import WakeWordEngine


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def engine(event_bus):
    os.environ["HELIX_WAKE_WORD_BACKEND"] = "mock"
    return WakeWordEngine(event_bus)


@pytest.mark.asyncio
async def test_start_publishes_ready(engine):
    received = []

    async def capture(event):
        received.append(event)

    engine._event_bus.subscribe("voice.ready", capture)
    await engine.start()
    assert len(received) == 1
    assert received[0].payload["backend"] == "mock"
    await engine.stop()


@pytest.mark.asyncio
async def test_has_correct_subscriptions(engine):
    await engine.start()
    assert "system.state.change" in engine._subscriptions
    assert "voice.listen.start" in engine._subscriptions
    assert "voice.listen.complete" in engine._subscriptions
    await engine.stop()


@pytest.mark.asyncio
async def test_unsubscribe_on_stop(engine):
    await engine.start()
    await engine.stop()
    assert len(engine._subscriptions) == 0


@pytest.mark.asyncio
async def test_listen_loop_starts_on_sleep(engine, event_bus):
    await engine.start()
    received = []

    async def capture(event):
        received.append(event)

    event_bus.subscribe("voice.wake", capture)
    await engine._handle_state_change(
        type("Event", (), {"payload": {"state": "sleep"}})()
    )
    assert engine._listening is True
    await asyncio.sleep(0.2)
    engine._listening = False
    await engine.stop()


@pytest.mark.asyncio
async def test_listen_loop_stops_on_conversation(engine):
    await engine.start()
    await engine._handle_state_change(
        type("Event", (), {"payload": {"state": "sleep"}})()
    )
    assert engine._listening is True
    await engine._handle_state_change(
        type("Event", (), {"payload": {"state": "conversation"}})()
    )
    assert engine._listening is False
    await engine.stop()
