import tempfile

import pytest

from foundation.event_bus.event_bus import EventBus, HelixEvent
from memory.explainability_engine.explainability_engine import ExplainabilityEngine


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def storage_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


@pytest.fixture
def engine(event_bus, storage_path):
    eng = ExplainabilityEngine(event_bus, storage_path=storage_path)
    return eng


@pytest.mark.asyncio
async def test_log_explanation(event_bus, engine):
    await engine.start()
    await event_bus.publish_event(
        source="test",
        event_type="memory.explain.log",
        payload={
            "action": "switch_project",
            "reasoning": "User opened a new project directory",
            "benefits": ["Faster context switching"],
            "risks": [],
            "alternatives": ["Ask user for project"],
            "source_module": "context.project_engine",
        },
    )
    records = engine.get_recent(10)
    assert len(records) == 1
    assert records[0].action == "switch_project"
    assert "Faster context switching" in records[0].benefits
    await engine.stop()


@pytest.mark.asyncio
async def test_log_triggers_logged_event(event_bus, engine):
    await engine.start()
    received = []

    async def handler(event: HelixEvent):
        received.append(event)

    event_bus.subscribe("memory.explain.logged", handler)
    await event_bus.publish_event(
        source="test",
        event_type="memory.explain.log",
        payload={
            "action": "test_action",
            "reasoning": "test reasoning",
        },
    )
    assert len(received) == 1
    assert received[0].payload["action"] == "test_action"
    await engine.stop()


@pytest.mark.asyncio
async def test_get_explanation_by_id(event_bus, engine):
    await engine.start()
    await event_bus.publish_event(
        source="test",
        event_type="memory.explain.log",
        payload={
            "action": "unique_action",
            "reasoning": "unique reasoning",
        },
    )
    records = engine.get_recent(10)
    assert len(records) == 1
    decision_id = records[0].decision_id

    found = engine.find_by_id(decision_id)
    assert found is not None
    assert found.action == "unique_action"
    await engine.stop()


@pytest.mark.asyncio
async def test_find_by_action(event_bus, engine):
    await engine.start()
    await event_bus.publish_event(
        source="test",
        event_type="memory.explain.log",
        payload={
            "action": "compile_project",
            "reasoning": "User requested build",
        },
    )
    results = engine.find_by_action("compile")
    assert len(results) >= 1
    assert results[0].action == "compile_project"
    await engine.stop()


@pytest.mark.asyncio
async def test_get_via_event_bus(event_bus, engine):
    await engine.start()
    await event_bus.publish_event(
        source="test",
        event_type="memory.explain.log",
        payload={
            "action": "retrieve_test",
            "reasoning": "testing retrieval",
        },
    )
    records = engine.get_recent(1)
    decision_id = records[0].decision_id

    received = []

    async def handler(event: HelixEvent):
        received.append(event)

    event_bus.subscribe("memory.explain.retrieved", handler)
    await event_bus.publish_event(
        source="test",
        event_type="memory.explain.get",
        payload={"decision_id": decision_id},
    )
    assert len(received) == 1
    assert received[0].payload["record"]["action"] == "retrieve_test"
    await engine.stop()
