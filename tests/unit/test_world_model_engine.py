import pytest
import asyncio
from foundation.event_bus.event_bus import EventBus, HelixEvent
from foundation.world_model.world_model_engine import WorldModelEngine, SystemEnvironmentState


@pytest.mark.asyncio
async def test_world_model_engine_window_tracking():
    event_bus = EventBus()
    engine = WorldModelEngine(event_bus=event_bus)
    await engine.start()

    window_events = []

    async def on_window_changed(event: HelixEvent):
        window_events.append(event.payload)

    event_bus.subscribe("world.window.changed", on_window_changed)

    engine.update_active_window(
        process_name="code.exe",
        window_title="HELIX-main - Visual Studio Code",
        executable_path=r"C:\Users\vaibh\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    )

    await asyncio.sleep(0.1)

    assert len(window_events) == 1
    assert window_events[0]["process_name"] == "code.exe"
    assert "Visual Studio Code" in window_events[0]["window_title"]

    await engine.stop()
