import tempfile

import pytest

from foundation.event_bus.event_bus import EventBus, HelixEvent
from memory.preference_memory.preference_memory import PreferenceMemory


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def storage_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


@pytest.fixture
def memory(event_bus, storage_path):
    mem = PreferenceMemory(event_bus, storage_path=storage_path)
    return mem


@pytest.mark.asyncio
async def test_store_preference(event_bus, memory):
    await memory.start()
    await event_bus.publish_event(
        source="test",
        event_type="memory.preference.store",
        payload={"key": "theme", "value": "dark", "category": "ui"},
    )
    assert memory.get("theme") is not None
    assert memory.get("theme").value == "dark"
    assert memory.get("theme").category == "ui"
    await memory.stop()


@pytest.mark.asyncio
async def test_get_preference(event_bus, memory):
    await memory.start()
    await event_bus.publish_event(
        source="test",
        event_type="memory.preference.store",
        payload={"key": "language", "value": "python", "category": "coding"},
    )
    received = []

    async def handler(event: HelixEvent):
        received.append(event)

    event_bus.subscribe("memory.preference.retrieved", handler)
    await event_bus.publish_event(
        source="test",
        event_type="memory.preference.get",
        payload={"key": "language"},
    )
    assert len(received) == 1
    assert received[0].payload["entry"]["value"] == "python"
    await memory.stop()


@pytest.mark.asyncio
async def test_get_all_preferences(event_bus, memory):
    await memory.start()
    await event_bus.publish_event(
        source="test",
        event_type="memory.preference.store",
        payload={"key": "theme", "value": "dark", "category": "ui"},
    )
    await event_bus.publish_event(
        source="test",
        event_type="memory.preference.store",
        payload={"key": "font_size", "value": 14, "category": "ui"},
    )
    await event_bus.publish_event(
        source="test",
        event_type="memory.preference.store",
        payload={"key": "language", "value": "python", "category": "coding"},
    )
    received = []

    async def handler(event: HelixEvent):
        received.append(event)

    event_bus.subscribe("memory.preference.all_retrieved", handler)

    await event_bus.publish_event(
        source="test",
        event_type="memory.preference.get_all",
        payload={"category": "ui"},
    )
    assert len(received) == 1
    assert len(received[0].payload["entries"]) == 2
    await memory.stop()


@pytest.mark.asyncio
async def test_delete_preference(event_bus, memory):
    await memory.start()
    await event_bus.publish_event(
        source="test",
        event_type="memory.preference.store",
        payload={"key": "temp_setting", "value": "temp"},
    )
    assert memory.get("temp_setting") is not None
    await event_bus.publish_event(
        source="test",
        event_type="memory.preference.delete",
        payload={"key": "temp_setting"},
    )
    assert memory.get("temp_setting") is None
    await memory.stop()


@pytest.mark.asyncio
async def test_persist_to_disk(event_bus, storage_path):
    mem1 = PreferenceMemory(event_bus, storage_path=storage_path)
    await mem1.start()
    await event_bus.publish_event(
        source="test",
        event_type="memory.preference.store",
        payload={"key": "persisted_key", "value": "persisted_value"},
    )
    await mem1.stop()

    mem2 = PreferenceMemory(event_bus, storage_path=storage_path)
    await mem2.start()
    assert mem2.get("persisted_key") is not None
    assert mem2.get("persisted_key").value == "persisted_value"
    await mem2.stop()
