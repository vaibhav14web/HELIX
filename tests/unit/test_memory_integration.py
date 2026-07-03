"""Integration test: all 4 memory modules working together via Event Bus."""
import tempfile

import pytest

from foundation.event_bus.event_bus import EventBus
from memory.conversation_memory.conversation_memory import ConversationMemory
from memory.preference_memory.preference_memory import PreferenceMemory
from memory.work_memory.work_memory import WorkMemory
from memory.explainability_engine.explainability_engine import ExplainabilityEngine


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def storage_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


@pytest.fixture
def memory_modules(event_bus, storage_path):
    conv = ConversationMemory(event_bus, storage_path=storage_path)
    pref = PreferenceMemory(event_bus, storage_path=storage_path)
    work = WorkMemory(event_bus, storage_path=storage_path)
    expl = ExplainabilityEngine(event_bus, storage_path=storage_path)
    return conv, pref, work, expl


@pytest.mark.asyncio
async def test_full_memory_workflow(event_bus, memory_modules):
    conv, pref, work, expl = memory_modules

    await conv.start()
    await pref.start()
    await work.start()
    await expl.start()

    session_id = "integration_session"

    await event_bus.publish_event(
        source="test",
        event_type="session.start",
        payload={"session_id": session_id},
    )

    await event_bus.publish_event(
        source="test",
        event_type="memory.work.set_project",
        payload={"project": "helix"},
    )

    await event_bus.publish_event(
        source="test",
        event_type="memory.conversation.store",
        payload={
            "session_id": session_id,
            "role": "user",
            "content": "What is the status of the project?",
        },
    )

    await event_bus.publish_event(
        source="test",
        event_type="memory.conversation.store",
        payload={
            "session_id": session_id,
            "role": "assistant",
            "content": "The project is in active development.",
        },
    )

    await event_bus.publish_event(
        source="test",
        event_type="memory.preference.store",
        payload={"key": "theme", "value": "dark", "category": "ui"},
    )

    await event_bus.publish_event(
        source="test",
        event_type="memory.explain.log",
        payload={
            "action": "set_project_helix",
            "reasoning": "User started working on Helix project",
            "benefits": ["Focused assistance"],
            "risks": [],
            "alternatives": [],
            "source_module": "work_memory",
            "outcome": "completed",
        },
    )

    conv_history = await conv.get_session_history(session_id, 10)
    assert len(conv_history) == 2
    assert conv_history[0].content == "What is the status of the project?"
    assert conv_history[1].content == "The project is in active development."

    assert pref.get("theme") is not None
    assert pref.get("theme").value == "dark"

    assert work.get_active_session() is not None
    assert work.get_active_session().active_project == "helix"

    explanations = expl.get_recent(10)
    assert len(explanations) == 1
    assert explanations[0].action == "set_project_helix"

    await conv.stop()
    await pref.stop()
    await work.stop()
    await expl.stop()
