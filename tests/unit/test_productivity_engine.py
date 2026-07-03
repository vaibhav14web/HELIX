import pytest

from foundation.event_bus.event_bus import EventBus
from action.productivity_engine.productivity_engine import ProductivityEngine


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def engine(event_bus):
    e = ProductivityEngine(event_bus)
    return e


@pytest.mark.asyncio
async def test_start_subscribes_to_events(engine):
    await engine.start()
    assert "automation.completed" in engine._subscriptions
    assert "productivity.suggestion.accept" in engine._subscriptions
    assert "productivity.suggestion.dismiss" in engine._subscriptions
    assert "system.state.change" in engine._subscriptions
    await engine.stop()


@pytest.mark.asyncio
async def test_unsubscribe_on_stop(engine):
    await engine.start()
    await engine.stop()
    assert len(engine._subscriptions) == 0


@pytest.mark.asyncio
async def test_records_action_and_creates_pattern(engine, event_bus):
    engine._min_frequency = 2
    await engine.start()

    for _ in range(3):
        await event_bus.publish_event(
            source="test",
            event_type="automation.completed",
            payload={"action": "browser_search"},
        )

    patterns = engine.get_patterns()
    assert len(patterns) >= 1
    assert patterns[0].category == "browsing"
    await engine.stop()


@pytest.mark.asyncio
async def test_suggestion_created_on_repeated_action(engine, event_bus):
    engine._min_frequency = 2
    await engine.start()

    received = []

    async def capture(event):
        received.append(event)

    event_bus.subscribe("productivity.suggestion", capture)

    for _ in range(3):
        await event_bus.publish_event(
            source="test",
            event_type="automation.completed",
            payload={"action": "browser_search"},
        )

    assert len(received) >= 1
    suggestion = received[0].payload
    assert "title" in suggestion
    assert "workflow" in suggestion
    await engine.stop()


@pytest.mark.asyncio
async def test_suggestion_accept_creates_workflow(engine, event_bus):
    engine._min_frequency = 2
    await engine.start()

    for _ in range(3):
        await event_bus.publish_event(
            source="test",
            event_type="automation.completed",
            payload={"action": "browser_search"},
        )

    suggestions = engine.get_suggestions()
    assert len(suggestions) >= 1
    suggestion_id = suggestions[0].suggestion_id

    workflow_received = []

    async def capture(event):
        workflow_received.append(event)

    event_bus.subscribe("productivity.workflow.create", capture)
    await event_bus.publish_event(
        source="test",
        event_type="productivity.suggestion.accept",
        payload={"suggestion_id": suggestion_id},
    )

    assert len(workflow_received) == 1
    assert workflow_received[0].payload["suggestion_id"] == suggestion_id
    assert suggestions[0].status == "accepted"
    await engine.stop()


@pytest.mark.asyncio
async def test_suggestion_dismiss_clears_pattern_flag(engine, event_bus):
    engine._min_frequency = 2
    await engine.start()

    for _ in range(3):
        await event_bus.publish_event(
            source="test",
            event_type="automation.completed",
            payload={"action": "browser_search"},
        )

    suggestions = engine.get_suggestions()
    suggestion_id = suggestions[0].suggestion_id
    action_name = suggestions[0].action

    await event_bus.publish_event(
        source="test",
        event_type="productivity.suggestion.dismiss",
        payload={"suggestion_id": suggestion_id},
    )

    assert suggestions[0].status == "dismissed"
    pattern = engine._patterns.get(action_name)
    assert pattern is not None
    assert pattern.suggested is False
    await engine.stop()


@pytest.mark.asyncio
async def test_state_change_sleep_pauses(engine, event_bus):
    await engine.start()
    assert engine._active is True

    await event_bus.publish_event(
        source="test",
        event_type="system.state.change",
        payload={"state": "sleep"},
    )

    assert engine._active is False
    await engine.stop()


@pytest.mark.asyncio
async def test_records_different_action_types(engine, event_bus):
    engine._min_frequency = 2
    await engine.start()

    for _ in range(3):
        await event_bus.publish_event(
            source="test",
            event_type="automation.completed",
            payload={"action": "launch_application"},
        )

    patterns = engine.get_patterns()
    assert len(patterns) >= 1
    assert patterns[0].category == "application"
    await engine.stop()


@pytest.mark.asyncio
async def test_get_suggestions_with_status_filter(engine, event_bus):
    engine._min_frequency = 2
    await engine.start()

    for _ in range(3):
        await event_bus.publish_event(
            source="test",
            event_type="automation.completed",
            payload={"action": "browser_search"},
        )

    pending = engine.get_suggestions(status="pending")
    assert len(pending) >= 1
    assert len(engine.get_suggestions(status="accepted")) == 0
    await engine.stop()
