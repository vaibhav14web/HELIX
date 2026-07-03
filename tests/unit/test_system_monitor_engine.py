import os
import pytest

from foundation.event_bus.event_bus import EventBus, HelixEvent
from context.system_monitor_engine.system_monitor_engine import SystemMonitorEngine


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def engine(event_bus):
    os.environ["HELIX_SYSTEM_MONITOR_INTERVAL"] = "300"  # long interval for tests
    return SystemMonitorEngine(event_bus)


@pytest.mark.asyncio
async def test_start_registers_subscriptions(engine):
    await engine.start()
    assert "system.monitor.request" in engine._subscriptions
    assert "system.state.change" in engine._subscriptions
    await engine.stop()


@pytest.mark.asyncio
async def test_stop_clears_subscriptions(engine):
    await engine.start()
    await engine.stop()
    assert len(engine._subscriptions) == 0


@pytest.mark.asyncio
async def test_handle_request_publishes_metrics(engine):
    await engine.start()
    received = []

    async def capture(event):
        received.append(event)

    engine._event_bus.subscribe("system.monitor.provided", capture)
    await engine._handle_request(
        HelixEvent(
            source="test",
            event_type="system.monitor.request",
            payload={},
            correlation_id="corr-sys-1",
        )
    )
    assert len(received) == 1
    payload = received[0].payload
    assert "timestamp" in payload
    assert "cpu_percent" in payload or "note" in payload
    assert "gpu" in payload
    assert received[0].correlation_id == "corr-sys-1"
    await engine.stop()


@pytest.mark.asyncio
async def test_metrics_contain_memory(engine):
    metrics = engine._get_metrics()
    # If psutil is installed, memory should be present
    if "memory" in metrics:
        assert "total" in metrics["memory"]
        assert "percent" in metrics["memory"]


@pytest.mark.asyncio
async def test_metrics_contain_disk(engine):
    metrics = engine._get_metrics()
    if "disk" in metrics:
        assert "total" in metrics["disk"]
        assert "free" in metrics["disk"]


@pytest.mark.asyncio
async def test_metrics_contain_idle_state(engine):
    metrics = engine._get_metrics()
    assert "is_idle" in metrics
    assert "idle_seconds" in metrics


@pytest.mark.asyncio
async def test_gpu_metrics_returns_dict(engine):
    gpu = engine._get_gpu_metrics()
    assert isinstance(gpu, dict)
    # Either has real GPU data or {"available": False}
    assert "available" in gpu or "utilization_percent" in gpu


@pytest.mark.asyncio
async def test_state_change_sleep_pauses(engine):
    await engine.start()
    assert engine._active is True
    await engine._handle_state_change(
        HelixEvent(
            source="test",
            event_type="system.state.change",
            payload={"state": "sleep"},
            correlation_id="corr-state-1",
        )
    )
    assert engine._active is False
    await engine.stop()


@pytest.mark.asyncio
async def test_state_change_resume(engine):
    await engine.start()
    engine._active = False
    await engine._handle_state_change(
        HelixEvent(
            source="test",
            event_type="system.state.change",
            payload={"state": "conversation"},
            correlation_id="corr-state-2",
        )
    )
    assert engine._active is True
    await engine.stop()


@pytest.mark.asyncio
async def test_state_change_background_publishes_metrics(engine):
    await engine.start()
    received = []

    async def capture(event):
        received.append(event)

    engine._event_bus.subscribe("system.monitor.provided", capture)
    await engine._handle_state_change(
        HelixEvent(
            source="test",
            event_type="system.state.change",
            payload={"state": "background"},
            correlation_id="corr-state-3",
        )
    )
    assert len(received) == 1
    await engine.stop()
