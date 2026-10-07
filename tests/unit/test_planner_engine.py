import pytest

from foundation.event_bus.event_bus import EventBus
from action.planner_engine.planner_engine import PlannerEngine


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def planner(event_bus, tmp_path):
    p = PlannerEngine(event_bus)
    p._state_path = str(tmp_path)
    return p


@pytest.mark.asyncio
async def test_start_subscribes_to_events(planner):
    await planner.start()
    assert "plan.request" in planner._subscriptions
    assert "plan.step.completed" in planner._subscriptions
    assert "plan.step.failed" in planner._subscriptions
    assert "plan.cancel" in planner._subscriptions
    await planner.stop()


@pytest.mark.asyncio
async def test_unsubscribe_on_stop(planner):
    await planner.start()
    await planner.stop()
    assert len(planner._subscriptions) == 0


@pytest.mark.asyncio
async def test_handle_request_creates_plan(planner, event_bus):
    await planner.start()

    received = []

    async def capture(event):
        received.append(event)

    event_bus.subscribe("plan.created", capture)
    await event_bus.publish_event(
        source="test",
        event_type="plan.request",
        payload={"task": "open chrome"},
    )

    assert len(received) == 1
    payload = received[0].payload
    assert payload["task"] == "open chrome"
    assert len(payload["steps"]) == 1
    assert payload["steps"][0]["action"] == "launch_application"
    assert payload["steps"][0]["target"] in ("chrome", "Google Chrome")
    await planner.stop()


@pytest.mark.asyncio
async def test_handle_request_empty_task_fails(planner, event_bus):
    await planner.start()

    received = []

    async def capture(event):
        received.append(event)

    event_bus.subscribe("plan.failed", capture)
    await event_bus.publish_event(
        source="test",
        event_type="plan.request",
        payload={"task": ""},
    )

    assert len(received) == 1
    assert received[0].payload["error"] == "Task cannot be empty"
    await planner.stop()


@pytest.mark.asyncio
async def test_search_task_creates_browser_search_plan(planner, event_bus):
    await planner.start()

    received = []

    async def capture(event):
        received.append(event)

    event_bus.subscribe("plan.created", capture)
    await event_bus.publish_event(
        source="test",
        event_type="plan.request",
        payload={"task": "search AI news"},
    )

    assert len(received) == 1
    steps = received[0].payload["steps"]
    assert len(steps) == 1
    assert steps[0]["action"] == "browser_search"
    assert steps[0]["params"]["query"] == "AI news"
    await planner.stop()


@pytest.mark.asyncio
async def test_step_completed_triggers_plan_completion(planner, event_bus):
    await planner.start()

    await event_bus.publish_event(
        source="test",
        event_type="plan.request",
        payload={"task": "open chrome"},
    )

    plans = planner.get_plans()
    assert len(plans) == 1
    plan = plans[0]
    plan_id = plan.plan_id
    step_id = plan.steps[0].step_id

    completed = []

    async def capture(event):
        completed.append(event)

    event_bus.subscribe("plan.completed", capture)
    await event_bus.publish_event(
        source="test",
        event_type="plan.step.completed",
        payload={"plan_id": plan_id, "step_id": step_id},
    )

    assert len(completed) == 1
    assert completed[0].payload["plan_id"] == plan_id
    await planner.stop()


@pytest.mark.asyncio
async def test_step_failed_triggers_plan_failure(planner, event_bus):
    await planner.start()

    await event_bus.publish_event(
        source="test",
        event_type="plan.request",
        payload={"task": "open chrome"},
    )

    plan = planner.get_plans()[0]
    plan_id = plan.plan_id
    step_id = plan.steps[0].step_id

    failed = []

    async def capture(event):
        failed.append(event)

    event_bus.subscribe("plan.failed", capture)
    await event_bus.publish_event(
        source="test",
        event_type="plan.step.failed",
        payload={"plan_id": plan_id, "step_id": step_id, "error": "App not found"},
    )

    assert len(failed) == 1
    assert failed[0].payload["error"] == "App not found"
    await planner.stop()


@pytest.mark.asyncio
async def test_cancel_plan(planner, event_bus):
    await planner.start()

    await event_bus.publish_event(
        source="test",
        event_type="plan.request",
        payload={"task": "open chrome"},
    )

    plan_id = planner.get_plans()[0].plan_id

    cancelled = []

    async def capture(event):
        cancelled.append(event)

    event_bus.subscribe("plan.cancelled", capture)
    await event_bus.publish_event(
        source="test",
        event_type="plan.cancel",
        payload={"plan_id": plan_id},
    )

    assert len(cancelled) == 1
    assert planner.get_plan(plan_id) is None
    await planner.stop()


@pytest.mark.asyncio
async def test_get_plans_with_status_filter(planner, event_bus):
    await planner.start()

    await event_bus.publish_event(
        source="test",
        event_type="plan.request",
        payload={"task": "open chrome"},
    )

    created_plans = planner.get_plans(status="created")
    assert len(created_plans) == 1
    assert planner.get_plans(status="completed") == []
    await planner.stop()


@pytest.mark.asyncio
async def test_notification_task(planner, event_bus):
    await planner.start()

    received = []

    async def capture(event):
        received.append(event)

    event_bus.subscribe("plan.created", capture)
    await event_bus.publish_event(
        source="test",
        event_type="plan.request",
        payload={"task": "notify meeting in 10 minutes"},
    )

    assert len(received) == 1
    steps = received[0].payload["steps"]
    assert steps[0]["action"] == "send_notification"
    assert steps[0]["params"]["message"] == "meeting in 10 minutes"
    await planner.stop()


# ── Risk Classification Tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_low_risk_browser_search(planner, event_bus):
    await planner.start()
    received = []
    event_bus.subscribe("plan.created", lambda e: received.append(e))
    await event_bus.publish_event(
        source="test", event_type="plan.request",
        payload={"task": "search python tutorials"},
    )
    step = received[0].payload["steps"][0]
    assert step["action"] == "browser_search"
    assert step["risk_level"] == "low"
    await planner.stop()


@pytest.mark.asyncio
async def test_launch_known_app_is_medium_risk(planner, event_bus):
    await planner.start()
    received = []
    event_bus.subscribe("plan.created", lambda e: received.append(e))
    await event_bus.publish_event(
        source="test", event_type="plan.request",
        payload={"task": "open notepad"},
    )
    step = received[0].payload["steps"][0]
    assert step["action"] == "launch_application"
    assert step["risk_level"] == "medium"
    assert step["target"] in ("notepad", "Notepad")
    await planner.stop()


@pytest.mark.asyncio
async def test_low_risk_send_notification(planner, event_bus):
    await planner.start()
    received = []
    event_bus.subscribe("plan.created", lambda e: received.append(e))
    await event_bus.publish_event(
        source="test", event_type="plan.request",
        payload={"task": "notify server ready"},
    )
    step = received[0].payload["steps"][0]
    assert step["action"] == "send_notification"
    assert step["risk_level"] == "low"
    await planner.stop()


@pytest.mark.asyncio
async def test_medium_risk_compose_email(planner, event_bus):
    await planner.start()
    received = []
    event_bus.subscribe("plan.created", lambda e: received.append(e))
    await event_bus.publish_event(
        source="test", event_type="plan.request",
        payload={"task": "send email to test@example.com"},
    )
    step = received[0].payload["steps"][0]
    assert step["action"] == "compose_email"
    assert step["risk_level"] == "medium"
    await planner.stop()


@pytest.mark.asyncio
async def test_medium_risk_launch_unknown_app(planner, event_bus):
    await planner.start()
    received = []
    event_bus.subscribe("plan.created", lambda e: received.append(e))
    await event_bus.publish_event(
        source="test", event_type="plan.request",
        payload={"task": "open some_custom_binary"},
    )
    step = received[0].payload["steps"][0]
    assert step["action"] == "launch_application"
    assert step["risk_level"] == "medium"
    assert step["target"] == "some_custom_binary"
    await planner.stop()


@pytest.mark.asyncio
async def test_unknown_task_risk_level(planner, event_bus):
    await planner.start()
    received = []
    event_bus.subscribe("plan.created", lambda e: received.append(e))
    await event_bus.publish_event(
        source="test", event_type="plan.request",
        payload={"task": "do something random"},
    )
    step = received[0].payload["steps"][0]
    assert step["action"] == "unknown"
    assert step["risk_level"] == "medium"
    await planner.stop()


# ── Guardrail Validation Tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_launch_chrome_is_medium_risk(planner, event_bus):
    await planner.start()
    received = []
    event_bus.subscribe("plan.created", lambda e: received.append(e))
    await event_bus.publish_event(
        source="test", event_type="plan.request",
        payload={"task": "open chrome"},
    )
    step = received[0].payload["steps"][0]
    assert step["action"] == "launch_application"
    assert step["risk_level"] == "medium"
    assert step["target"] in ("chrome", "Google Chrome")
    await planner.stop()


@pytest.mark.asyncio
async def test_launch_edge_is_medium_risk(planner, event_bus):
    await planner.start()
    received = []
    event_bus.subscribe("plan.created", lambda e: received.append(e))
    await event_bus.publish_event(
        source="test", event_type="plan.request",
        payload={"task": "start edge"},
    )
    step = received[0].payload["steps"][0]
    assert step["risk_level"] == "medium"
    await planner.stop()


@pytest.mark.asyncio
async def test_read_file_blocks_system_path(planner, event_bus):
    await planner.start()
    failed = []
    event_bus.subscribe("plan.failed", lambda e: failed.append(e))
    await event_bus.publish_event(
        source="test", event_type="plan.request",
        payload={"task": "open file C:\\Windows\\System32\\config"},
    )
    assert len(failed) == 1
    assert "Access denied" in failed[0].payload["error"]
    await planner.stop()


@pytest.mark.asyncio
async def test_read_file_blocks_program_files_path(planner, event_bus):
    await planner.start()
    failed = []
    event_bus.subscribe("plan.failed", lambda e: failed.append(e))
    await event_bus.publish_event(
        source="test", event_type="plan.request",
        payload={"task": "open file C:\\Program Files\\SomeApp\\config.ini"},
    )
    assert len(failed) == 1
    assert "Access denied" in failed[0].payload["error"]
    await planner.stop()


@pytest.mark.asyncio
async def test_read_file_blocks_program_data_path(planner, event_bus):
    await planner.start()
    failed = []
    event_bus.subscribe("plan.failed", lambda e: failed.append(e))
    await event_bus.publish_event(
        source="test", event_type="plan.request",
        payload={"task": "read C:\\ProgramData\\some_file.txt"},
    )
    assert len(failed) == 1
    assert "Access denied" in failed[0].payload["error"]
    await planner.stop()


# ── PlanStep risk_level via to_dict ──────────────────────────────────


def test_plan_step_risk_level_default():
    from action.planner_engine.planner_engine import PlanStep
    import uuid
    step = PlanStep(step_id=uuid.uuid4().hex[:8], action="browser_search")
    assert step.risk_level == "low"
    d = step.to_dict()
    assert d["risk_level"] == "low"


def test_plan_step_risk_level_custom():
    from action.planner_engine.planner_engine import PlanStep
    import uuid
    step = PlanStep(step_id=uuid.uuid4().hex[:8], action="compose_email", risk_level="medium")
    assert step.risk_level == "medium"
    d = step.to_dict()
    assert d["risk_level"] == "medium"
