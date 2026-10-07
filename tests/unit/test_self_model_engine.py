import pytest
import asyncio
from foundation.event_bus.event_bus import EventBus, HelixEvent
from core_ai.self_model.self_model_engine import SelfModelEngine, SelfStateVector


@pytest.mark.asyncio
async def test_self_model_engine_lifecycle():
    event_bus = EventBus()
    engine = SelfModelEngine(event_bus=event_bus)
    await engine.start()

    state = engine.get_state()
    assert state.identity == "HELIX PAIOS"
    assert state.health_status == "healthy"

    received_updates = []

    async def on_state_updated(event: HelixEvent):
        received_updates.append(event.payload)

    event_bus.subscribe("self.state.updated", on_state_updated)

    # Test resource update
    engine.update_resources(cpu_percent=95.0, memory_percent=80.0)
    assert engine.get_state().health_status == "degraded"

    # Test event handling
    await event_bus.publish_event(
        source="llm_engine",
        event_type="llm.generation.started",
        payload={"session_id": "test"},
    )
    await asyncio.sleep(0.1)

    assert engine.get_state().engines.llm_status == "generating"
    assert len(received_updates) >= 1

    await engine.stop()
