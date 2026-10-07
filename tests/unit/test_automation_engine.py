import pytest

from foundation.event_bus.event_bus import EventBus
from action.automation_engine.automation_engine import AutomationEngine


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def engine(event_bus, tmp_path):
    e = AutomationEngine(event_bus)
    e._state_path = str(tmp_path)
    return e


@pytest.mark.asyncio
async def test_start_subscribes_to_events(engine):
    await engine.start()
    assert "automation.execute" in engine._subscriptions
    assert "automation.execute_step" in engine._subscriptions
    assert "automation.result" in engine._subscriptions
    assert "automation.failed" in engine._subscriptions
    assert "automation.cancel" in engine._subscriptions
    assert "automation.confirm.response" in engine._subscriptions
    assert "permission.granted" in engine._subscriptions
    assert "permission.denied" in engine._subscriptions
    await engine.stop()


@pytest.mark.asyncio
async def test_unsubscribe_on_stop(engine):
    await engine.start()
    await engine.stop()
    assert len(engine._subscriptions) == 0


@pytest.mark.asyncio
async def test_execute_action_publishes_action_execute(engine, event_bus):
    await engine.start()

    received = []

    async def capture(event):
        received.append(event)

    event_bus.subscribe("action.execute", capture)
    await event_bus.publish_event(
        source="test",
        event_type="automation.execute",
        payload={
            "action": "launch_application",
            "target": "notepad",
            "params": {"application": "notepad"},
        },
    )

    assert len(received) == 1
    assert received[0].payload["action"] == "launch_application"
    assert received[0].payload["target"] == "notepad"
    await engine.stop()


@pytest.mark.asyncio
async def test_execute_empty_action_fails(engine, event_bus):
    await engine.start()

    received = []

    async def capture(event):
        received.append(event)

    event_bus.subscribe("automation.failed", capture)
    await event_bus.publish_event(
        source="test",
        event_type="automation.execute",
        payload={"action": ""},
    )

    assert len(received) == 1
    await engine.stop()


@pytest.mark.asyncio
async def test_execute_with_permission_id_waits(engine, event_bus):
    await engine.start()

    await event_bus.publish_event(
        source="test",
        event_type="automation.execute",
        payload={
            "action": "delete_file",
            "permission_id": "perm_123",
        },
    )

    actions = [a for a in engine._actions.values()]
    assert len(actions) == 1
    assert actions[0].status == "waiting_permission"
    assert actions[0].permission_id == "perm_123"

    action_executed = []

    async def capture(event):
        action_executed.append(event)

    event_bus.subscribe("action.execute", capture)
    await event_bus.publish_event(
        source="test",
        event_type="permission.granted",
        payload={"id": "perm_123"},
    )

    assert len(action_executed) == 1
    await engine.stop()


@pytest.mark.asyncio
async def test_permission_denied_marks_action_denied(engine, event_bus):
    await engine.start()

    await event_bus.publish_event(
        source="test",
        event_type="automation.execute",
        payload={
            "action": "delete_file",
            "permission_id": "perm_123",
        },
    )

    await event_bus.publish_event(
        source="test",
        event_type="permission.denied",
        payload={"id": "perm_123"},
    )

    with pytest.raises(KeyError):
        _ = engine._actions_by_permission["perm_123"]
    history = engine.get_history()
    assert len(history) == 1
    assert history[0].status == "denied"
    await engine.stop()


@pytest.mark.asyncio
async def test_result_completes_action(engine, event_bus):
    await engine.start()

    await event_bus.publish_event(
        source="test",
        event_type="automation.execute",
        payload={"action": "read_file", "params": {"path": "test.txt"}},
    )

    action_id = list(engine._actions.keys())[0]

    completed = []

    async def capture(event):
        completed.append(event)

    event_bus.subscribe("automation.completed", capture)
    await event_bus.publish_event(
        source="test",
        event_type="automation.result",
        payload={"action_id": action_id, "result": {"content": "ok"}},
    )

    assert len(completed) == 1
    assert completed[0].payload["result"]["content"] == "ok"
    assert action_id not in engine._actions
    await engine.stop()


@pytest.mark.asyncio
async def test_failed_action(engine, event_bus):
    await engine.start()

    await event_bus.publish_event(
        source="test",
        event_type="automation.execute",
        payload={"action": "read_file"},
    )

    action_id = list(engine._actions.keys())[0]

    completed_events = []

    async def capture(event):
        completed_events.append(event)

    event_bus.subscribe("automation.completed", capture)
    await event_bus.publish_event(
        source="test",
        event_type="automation.failed",
        payload={"action_id": action_id, "error": "Permission denied"},
    )

    history = engine.get_history()
    assert len(history) == 1
    assert history[0].status == "failed"
    assert history[0].error == "Permission denied"
    await engine.stop()


@pytest.mark.asyncio
async def test_cancel_action(engine, event_bus):
    await engine.start()

    await event_bus.publish_event(
        source="test",
        event_type="automation.execute",
        payload={"action": "long_task"},
    )

    action_id = list(engine._actions.keys())[0]

    await event_bus.publish_event(
        source="test",
        event_type="automation.cancel",
        payload={"action_id": action_id},
    )

    assert action_id not in engine._actions
    history = engine.get_history()
    assert len(history) == 1
    assert history[0].status == "cancelled"
    await engine.stop()


@pytest.mark.asyncio
async def test_execute_step(engine, event_bus):
    await engine.start()

    received = []

    async def capture(event):
        received.append(event)

    event_bus.subscribe("action.execute", capture)
    await event_bus.publish_event(
        source="test",
        event_type="automation.execute_step",
        payload={
            "plan_id": "plan_1",
            "step": {
                "step_id": "step_1",
                "action": "browser_search",
                "params": {"query": "weather"},
            },
        },
    )

    assert len(received) == 1
    assert received[0].payload["action"] == "browser_search"
    assert received[0].payload["plan_id"] == "plan_1"
    await engine.stop()


@pytest.mark.asyncio
async def test_get_history(engine, event_bus):
    await engine.start()

    await event_bus.publish_event(
        source="test",
        event_type="automation.execute",
        payload={"action": "test_action"},
    )

    action_id = list(engine._actions.keys())[0]

    await event_bus.publish_event(
        source="test",
        event_type="automation.result",
        payload={"action_id": action_id, "result": {}},
    )

    history = engine.get_history()
    assert len(history) == 1
    assert history[0].action == "test_action"
    assert history[0].status == "completed"
    await engine.stop()


# ── Risk-Based Permission Flow Tests ────────────────────────────────


@pytest.mark.asyncio
async def test_low_risk_auto_dispatches(engine, event_bus):
    await engine.start()

    action_executed = []
    event_bus.subscribe("action.execute", lambda e: action_executed.append(e))
    await event_bus.publish_event(
        source="test",
        event_type="automation.execute",
        payload={"action": "browser_search", "risk_level": "low", "params": {"query": "test"}},
    )

    assert len(action_executed) == 1
    assert action_executed[0].payload["risk_level"] == "low"
    await engine.stop()


@pytest.mark.asyncio
async def test_medium_risk_requests_permission(engine, event_bus):
    await engine.start()

    perm_needed = []
    event_bus.subscribe("automation.permission_needed", lambda e: perm_needed.append(e))

    await event_bus.publish_event(
        source="test",
        event_type="automation.execute",
        payload={
            "action": "compose_email",
            "risk_level": "medium",
            "params": {"to": "test@example.com"},
        },
    )

    assert len(perm_needed) == 1
    assert perm_needed[0].payload["risk_level"] == "medium"

    actions = [a for a in engine._actions.values()]
    assert len(actions) == 1
    assert actions[0].status == "waiting_permission"
    assert actions[0].risk_level == "medium"
    assert actions[0].permission_id is not None

    action_executed = []
    event_bus.subscribe("action.execute", lambda e: action_executed.append(e))

    perm_id = actions[0].permission_id
    await event_bus.publish_event(
        source="test",
        event_type="permission.granted",
        payload={"id": perm_id},
    )

    assert len(action_executed) == 1
    assert action_executed[0].payload["action"] == "compose_email"
    await engine.stop()


@pytest.mark.asyncio
async def test_medium_risk_denied_does_not_execute(engine, event_bus):
    await engine.start()

    await event_bus.publish_event(
        source="test",
        event_type="automation.execute",
        payload={"action": "compose_email", "risk_level": "medium", "params": {"to": "test@example.com"}},
    )

    actions = [a for a in engine._actions.values()]
    perm_id = actions[0].permission_id

    action_executed = []
    event_bus.subscribe("action.execute", lambda e: action_executed.append(e))
    await event_bus.publish_event(
        source="test",
        event_type="permission.denied",
        payload={"id": perm_id},
    )

    assert len(action_executed) == 0
    history = engine.get_history()
    assert len(history) == 1
    assert history[0].status == "denied"
    await engine.stop()


@pytest.mark.asyncio
async def test_high_risk_requests_confirmation_first(engine, event_bus):
    await engine.start()

    confirm_requests = []
    event_bus.subscribe("automation.confirm.request", lambda e: confirm_requests.append(e))

    await event_bus.publish_event(
        source="test",
        event_type="automation.execute",
        payload={"action": "read_file", "risk_level": "high", "params": {"path": "C:\\Windows\\System32\\config"}},
    )

    assert len(confirm_requests) == 1
    assert confirm_requests[0].payload["risk_level"] == "high"
    assert "Are you sure" in confirm_requests[0].payload["description"]

    assert len(engine._actions_waiting_confirmation) == 1
    await engine.stop()


@pytest.mark.asyncio
async def test_high_risk_confirm_then_permission(engine, event_bus):
    await engine.start()

    await event_bus.publish_event(
        source="test",
        event_type="automation.execute",
        payload={"action": "read_file", "risk_level": "high", "params": {"path": "/etc/config"}},
    )

    action_id = list(engine._actions.keys())[0]

    perm_needed = []
    event_bus.subscribe("automation.permission_needed", lambda e: perm_needed.append(e))

    await event_bus.publish_event(
        source="test",
        event_type="automation.confirm.response",
        payload={"action_id": action_id, "confirmed": True},
    )

    assert len(perm_needed) == 1
    assert perm_needed[0].payload["risk_level"] == "medium"

    action_executed = []
    event_bus.subscribe("action.execute", lambda e: action_executed.append(e))

    actions = [a for a in engine._actions.values()]
    perm_id = actions[0].permission_id
    await event_bus.publish_event(
        source="test",
        event_type="permission.granted",
        payload={"id": perm_id},
    )

    assert len(action_executed) == 1
    await engine.stop()


@pytest.mark.asyncio
async def test_high_risk_denied_confirmation_cancels(engine, event_bus):
    await engine.start()

    await event_bus.publish_event(
        source="test",
        event_type="automation.execute",
        payload={"action": "read_file", "risk_level": "high", "params": {"path": "/etc/config"}},
    )

    action_id = list(engine._actions.keys())[0]

    action_executed = []
    event_bus.subscribe("action.execute", lambda e: action_executed.append(e))

    await event_bus.publish_event(
        source="test",
        event_type="automation.confirm.response",
        payload={"action_id": action_id, "confirmed": False},
    )

    assert len(action_executed) == 0
    assert action_id not in engine._actions
    assert action_id not in engine._actions_waiting_confirmation

    history = engine.get_history()
    assert len(history) == 1
    assert history[0].status == "denied"
    await engine.stop()


@pytest.mark.asyncio
async def test_risk_level_in_action_record(engine, event_bus):
    await engine.start()

    await event_bus.publish_event(
        source="test",
        event_type="automation.execute",
        payload={"action": "test_action", "risk_level": "medium"},
    )

    actions = [a for a in engine._actions.values()]
    assert len(actions) == 1
    assert actions[0].risk_level == "medium"
    await engine.stop()
