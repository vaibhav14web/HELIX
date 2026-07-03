import os
import tempfile

import pytest

from foundation.event_bus.event_bus import EventBus, HelixEvent
from memory.conversation_memory.conversation_memory import ConversationMemory


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def storage_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


@pytest.fixture
def memory(event_bus, storage_path):
    mem = ConversationMemory(event_bus, storage_path=storage_path)
    return mem


@pytest.mark.asyncio
async def test_store_conversation_entry(event_bus, memory):
    await memory.start()
    await event_bus.publish_event(
        source="test",
        event_type="memory.conversation.store",
        payload={
            "session_id": "session_1",
            "role": "user",
            "content": "Hello Helix!",
        },
    )
    history = await memory.get_session_history("session_1", 10)
    assert len(history) == 1
    assert history[0].content == "Hello Helix!"
    assert history[0].role == "user"
    await memory.stop()


@pytest.mark.asyncio
async def test_session_start_loads_recent(event_bus, memory):
    await memory.start()
    await event_bus.publish_event(
        source="test",
        event_type="session.start",
        payload={"session_id": "session_2"},
    )
    assert "session_2" in memory._active
    await memory.stop()


@pytest.mark.asyncio
async def test_session_end_clears_active(event_bus, memory):
    await memory.start()
    await event_bus.publish_event(
        source="test",
        event_type="session.start",
        payload={"session_id": "session_3"},
    )
    await event_bus.publish_event(
        source="test",
        event_type="session.end",
        payload={"session_id": "session_3"},
    )
    assert "session_3" not in memory._active
    await memory.stop()


@pytest.mark.asyncio
async def test_retrieve_via_event_bus(event_bus, memory):
    await memory.start()
    await event_bus.publish_event(
        source="test",
        event_type="memory.conversation.store",
        payload={
            "session_id": "session_4",
            "role": "user",
            "content": "Store this message",
        },
    )
    received = []

    async def handler(event: HelixEvent):
        received.append(event)

    event_bus.subscribe("memory.conversation.retrieved", handler)
    await event_bus.publish_event(
        source="test",
        event_type="memory.conversation.retrieve",
        payload={"session_id": "session_4", "limit": 10},
    )
    assert len(received) == 1
    entries = received[0].payload["entries"]
    assert len(entries) == 1
    assert entries[0]["content"] == "Store this message"
    await memory.stop()


@pytest.mark.asyncio
async def test_search_entries(event_bus, memory):
    await memory.start()
    await event_bus.publish_event(
        source="test",
        event_type="memory.conversation.store",
        payload={
            "session_id": "session_5",
            "role": "user",
            "content": "Working on the memory module implementation",
        },
    )
    await event_bus.publish_event(
        source="test",
        event_type="memory.conversation.store",
        payload={
            "session_id": "session_5",
            "role": "assistant",
            "content": "Let me help you with that",
        },
    )
    results = await memory.search_entries("memory module")
    assert len(results) >= 1
    assert "memory module" in results[0].content.lower()
    await memory.stop()


@pytest.mark.asyncio
async def test_store_triggers_stored_event(event_bus, memory):
    await memory.start()
    received = []

    async def handler(event: HelixEvent):
        received.append(event)

    event_bus.subscribe("memory.conversation.stored", handler)
    await event_bus.publish_event(
        source="test",
        event_type="memory.conversation.store",
        payload={
            "session_id": "session_6",
            "role": "user",
            "content": "Test stored event",
        },
    )
    assert len(received) == 1
    assert received[0].payload["session_id"] == "session_6"
    await memory.stop()


@pytest.mark.asyncio
async def test_get_all_sessions(event_bus, memory):
    await memory.start()
    await event_bus.publish_event(
        source="test",
        event_type="memory.conversation.store",
        payload={
            "session_id": "session_alpha",
            "role": "user",
            "content": "Message A",
        },
    )
    import asyncio
    await asyncio.sleep(0.1)
    await event_bus.publish_event(
        source="test",
        event_type="memory.conversation.store",
        payload={
            "session_id": "session_beta",
            "role": "user",
            "content": "Message B",
        },
    )
    sessions = await memory.get_all_sessions()
    assert "session_alpha" in sessions
    assert "session_beta" in sessions
    assert sessions[0] == "session_beta"
    await memory.stop()

