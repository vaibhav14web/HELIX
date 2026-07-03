import tempfile

import pytest

from foundation.event_bus.event_bus import EventBus, HelixEvent
from memory.work_memory.work_memory import WorkMemory


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def storage_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


@pytest.fixture
def memory(event_bus, storage_path):
    mem = WorkMemory(event_bus, storage_path=storage_path)
    return mem


@pytest.mark.asyncio
async def test_session_start_creates_active_session(event_bus, memory):
    await memory.start()
    await event_bus.publish_event(
        source="test",
        event_type="session.start",
        payload={"session_id": "session_1"},
    )
    assert memory._active_session is not None
    assert memory._active_session.session_id == "session_1"
    await memory.stop()


@pytest.mark.asyncio
async def test_set_project(event_bus, memory):
    await memory.start()
    await event_bus.publish_event(
        source="test",
        event_type="session.start",
        payload={"session_id": "session_2"},
    )
    await event_bus.publish_event(
        source="test",
        event_type="memory.work.set_project",
        payload={"project": "helix"},
    )
    assert memory._active_session.active_project == "helix"
    await memory.stop()


@pytest.mark.asyncio
async def test_add_task(event_bus, memory):
    await memory.start()
    await event_bus.publish_event(
        source="test",
        event_type="session.start",
        payload={"session_id": "session_3"},
    )
    await event_bus.publish_event(
        source="test",
        event_type="memory.work.add_task",
        payload={"task": "Implement memory module"},
    )
    assert "Implement memory module" in memory._active_session.open_tasks
    await memory.stop()


@pytest.mark.asyncio
async def test_get_context(event_bus, memory):
    await memory.start()
    await event_bus.publish_event(
        source="test",
        event_type="session.start",
        payload={"session_id": "session_4"},
    )
    await event_bus.publish_event(
        source="test",
        event_type="memory.work.set_project",
        payload={"project": "helix"},
    )
    received = []

    async def handler(event: HelixEvent):
        received.append(event)

    event_bus.subscribe("memory.work.context_retrieved", handler)
    await event_bus.publish_event(
        source="test",
        event_type="memory.work.get_context",
        payload={},
    )
    assert len(received) == 1
    assert received[0].payload["context"]["active_project"] == "helix"
    await memory.stop()


@pytest.mark.asyncio
async def test_update_context(event_bus, memory):
    await memory.start()
    await event_bus.publish_event(
        source="test",
        event_type="session.start",
        payload={"session_id": "session_5"},
    )
    await event_bus.publish_event(
        source="test",
        event_type="memory.work.update_context",
        payload={"updates": {"current_file": "main.py", "line": 42}},
    )
    assert memory._active_session.current_context["current_file"] == "main.py"
    assert memory._active_session.current_context["line"] == 42
    await memory.stop()
