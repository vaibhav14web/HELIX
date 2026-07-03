import os
import pytest

from foundation.event_bus.event_bus import EventBus
from core_ai.llm_engine.llm_engine import LLMEngine


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def engine(event_bus):
    os.environ["HELIX_LLM_BACKEND"] = "mock"
    eng = LLMEngine(event_bus)
    return eng


@pytest.mark.asyncio
async def test_start_publishes_ready(event_bus, engine):
    received = []

    async def capture(event):
        received.append(event)

    event_bus.subscribe("llm.ready", capture)
    await engine.start()
    assert len(received) == 1
    assert received[0].payload["backend"] == "mock"
    assert received[0].payload["loaded"] is False
    await engine.stop()


@pytest.mark.asyncio
async def test_generate_mock_response(event_bus, engine):
    await engine.start()
    response = await engine.generate("Hello HELIX")
    assert isinstance(response, str)
    assert len(response) > 0
    assert "mock development mode" in response
    await engine.stop()


@pytest.mark.asyncio
async def test_handle_generate_via_eventbus(event_bus, engine):
    await engine.start()

    received = []

    async def capture(event):
        received.append(event)

    event_bus.subscribe("llm.generation.complete", capture)

    await event_bus.publish_event(
        source="test",
        event_type="llm.generate",
        payload={"prompt": "What can you do?", "session_id": "test_session"},
    )

    import asyncio
    await asyncio.sleep(0.1)

    assert len(received) >= 1
    assert received[0].payload["session_id"] == "test_session"
    assert len(received[0].payload["response"]) > 0

    await engine.stop()


@pytest.mark.asyncio
async def test_handle_generate_empty_prompt(event_bus, engine):
    await engine.start()

    received = []

    async def capture(event):
        received.append(event)

    event_bus.subscribe("llm.generation.error", capture)

    await event_bus.publish_event(
        source="test",
        event_type="llm.generate",
        payload={"prompt": "", "session_id": "test_session"},
    )

    import asyncio
    await asyncio.sleep(0.1)

    assert len(received) >= 1
    assert "Empty prompt" in received[0].payload["error"]

    await engine.stop()


@pytest.mark.asyncio
async def test_has_correct_subscriptions(event_bus, engine):
    await engine.start()
    assert "llm.generate" in engine._subscriptions
    await engine.stop()


@pytest.mark.asyncio
async def test_unsubscribe_on_stop(event_bus, engine):
    await engine.start()
    await engine.stop()
    assert len(engine._subscriptions) == 0


@pytest.mark.asyncio
async def test_generates_start_and_complete_events(event_bus, engine):
    await engine.start()

    events = []

    async def capture(event):
        events.append(event.event_type)

    event_bus.subscribe("llm.generation.start", capture)
    event_bus.subscribe("llm.generation.complete", capture)

    await event_bus.publish_event(
        source="test",
        event_type="llm.generate",
        payload={"prompt": "Test", "session_id": "s1"},
    )

    import asyncio
    await asyncio.sleep(0.1)

    assert "llm.generation.start" in events
    assert "llm.generation.complete" in events

    await engine.stop()
