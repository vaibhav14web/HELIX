import pytest
import asyncio
from foundation.event_bus.event_bus import EventBus, HelixEvent
from orchestrator.ecs.executive_control_system import ExecutiveControlSystem, ExecutiveState


@pytest.mark.asyncio
async def test_ecs_state_transitions():
    event_bus = EventBus()
    ecs = ExecutiveControlSystem(event_bus=event_bus)
    await ecs.start()

    assert ecs.get_state().current_state == ExecutiveState.IDLE

    # Listen transition
    await event_bus.publish_event(source="voice", event_type="voice.listen.start", payload={})
    await asyncio.sleep(0.05)
    assert ecs.get_state().current_state == ExecutiveState.LISTENING

    # Thinking transition
    await event_bus.publish_event(source="voice", event_type="voice.listen.complete", payload={})
    await asyncio.sleep(0.05)
    assert ecs.get_state().current_state == ExecutiveState.THINKING

    # Interrupt test
    await ecs.inject_interrupt(priority=1, source="voice_engine", reason="User interrupt", action_required="listen")
    assert ecs.get_state().current_state == ExecutiveState.LISTENING
    assert len(ecs.get_state().pending_interrupts) == 1

    await ecs.stop()
    assert ecs.get_state().current_state == ExecutiveState.SHUTDOWN
