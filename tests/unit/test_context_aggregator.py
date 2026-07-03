import pytest
import time

from foundation.event_bus.event_bus import EventBus, HelixEvent
from context.context_aggregator.context_aggregator import ContextAggregator


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def aggregator(event_bus):
    return ContextAggregator(event_bus)


@pytest.mark.asyncio
async def test_start_registers_subscriptions(aggregator):
    await aggregator.start()
    assert "context.request" in aggregator._subscriptions
    assert "context.update" in aggregator._subscriptions
    assert "system.state.change" in aggregator._subscriptions
    assert "context.browser.provided" in aggregator._subscriptions
    assert "system.monitor.provided" in aggregator._subscriptions
    assert "project.opened" in aggregator._subscriptions
    assert "project.switched" in aggregator._subscriptions
    await aggregator.stop()


@pytest.mark.asyncio
async def test_stop_clears_subscriptions(aggregator):
    await aggregator.start()
    await aggregator.stop()
    assert len(aggregator._subscriptions) == 0


@pytest.mark.asyncio
async def test_handle_update_sets_cache(aggregator):
    await aggregator.start()
    await aggregator._handle_update(
        HelixEvent(
            source="test",
            event_type="context.update",
            payload={"key": "custom_key", "value": {"data": 42}},
            correlation_id="corr-update-1",
        )
    )
    assert aggregator._cache["custom_key"] == {"data": 42}
    await aggregator.stop()


@pytest.mark.asyncio
async def test_context_request_publishes_provided(aggregator):
    await aggregator.start()
    received = []

    async def capture(event):
        received.append(event)

    aggregator._event_bus.subscribe("context.provided", capture)
    await aggregator._handle_request(
        HelixEvent(
            source="test",
            event_type="context.request",
            payload={"session_id": "test-session"},
            correlation_id="corr-request-1",
        )
    )
    # The aggregator yields to let sub-engines respond, then publishes
    import asyncio
    await asyncio.sleep(0.2)
    assert len(received) >= 1
    ctx = received[-1].payload["context"]
    assert "browser" in ctx
    assert "system" in ctx
    assert "project" in ctx
    assert received[-1].payload["session_id"] == "test-session"
    await aggregator.stop()


@pytest.mark.asyncio
async def test_browser_response_updates_cache(aggregator):
    await aggregator.start()
    tabs_payload = {"tabs": [{"title": "Google", "browser": "Chrome"}]}
    await aggregator._handle_browser_response(
        HelixEvent(
            source="browser_engine",
            event_type="context.browser.provided",
            payload=tabs_payload,
            correlation_id="corr-br-1",
        )
    )
    assert aggregator._cache["browser"] == tabs_payload
    assert "browser" in aggregator._cache_timestamps
    await aggregator.stop()


@pytest.mark.asyncio
async def test_system_response_updates_cache(aggregator):
    await aggregator.start()
    metrics = {"cpu_percent": 15.0, "is_idle": False}
    await aggregator._handle_system_response(
        HelixEvent(
            source="system_monitor_engine",
            event_type="system.monitor.provided",
            payload=metrics,
            correlation_id="corr-sys-1",
        )
    )
    assert aggregator._cache["system"]["cpu_percent"] == 15.0
    await aggregator.stop()


@pytest.mark.asyncio
async def test_project_opened_updates_cache(aggregator):
    await aggregator.start()
    payload = {"name": "my-proj", "project_type": "python"}
    await aggregator._handle_project_opened(
        HelixEvent(
            source="project_engine",
            event_type="project.opened",
            payload=payload,
            correlation_id="corr-proj-1",
        )
    )
    assert aggregator._cache["project"]["name"] == "my-proj"
    await aggregator.stop()


@pytest.mark.asyncio
async def test_project_switch_invalidates_file_cache(aggregator):
    await aggregator.start()
    # Simulate file cache existing
    aggregator._cache_timestamps["files"] = time.time()
    aggregator._cache_timestamps["recent_files"] = time.time()

    await aggregator._handle_project_switched(
        HelixEvent(
            source="project_engine",
            event_type="project.switched",
            payload={"from": "a", "to": "b"},
            correlation_id="corr-switch-1",
        )
    )
    # File caches should be invalidated
    assert "files" not in aggregator._cache_timestamps
    assert "recent_files" not in aggregator._cache_timestamps
    await aggregator.stop()


@pytest.mark.asyncio
async def test_cache_freshness(aggregator):
    aggregator._cache_ttl = 30
    now = time.time()
    aggregator._last_full_context_time = now
    assert aggregator.is_cache_fresh(now + 1) is True
    assert aggregator.is_cache_fresh(now + 100) is False


@pytest.mark.asyncio
async def test_state_sleep_pauses(aggregator):
    await aggregator.start()
    await aggregator._handle_state_change(
        HelixEvent(
            source="test",
            event_type="system.state.change",
            payload={"state": "sleep"},
            correlation_id="corr-sleep-1",
        )
    )
    assert aggregator._active is False
    await aggregator.stop()


@pytest.mark.asyncio
async def test_get_consolidated_context(aggregator):
    await aggregator.start()
    aggregator._cache["system"] = {"cpu_percent": 10.0}
    aggregator._cache_timestamps["system"] = time.time()
    
    ctx = aggregator.get_consolidated_context("test-session")
    assert ctx["session_id"] == "test-session"
    assert ctx["system"] == {"cpu_percent": 10.0}
    assert "cache_ages" in ctx
    assert "system" in ctx["cache_ages"]
    await aggregator.stop()
