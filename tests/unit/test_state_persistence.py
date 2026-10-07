import os
import json
import pytest
from pathlib import Path

from foundation.event_bus.event_bus import EventBus, HelixEvent
from foundation.storage_manager.crypto import encrypt_string, decrypt_string, _HEADER
from action.planner_engine.planner_engine import PlannerEngine, Plan, PlanStep
from action.automation_engine.automation_engine import AutomationEngine, ActionRecord


@pytest.mark.asyncio
async def test_planner_engine_dpapi_encryption(tmp_path, monkeypatch):
    monkeypatch.setenv("HELIX_STATE_DIR", str(tmp_path))
    event_bus = EventBus()
    planner = PlannerEngine(event_bus)
    await planner.start()

    # Create a plan
    await planner._handle_request(
        HelixEvent(
            source="test",
            event_type="plan.request",
            payload={"task": "search for quantum computing"},
            correlation_id="corr-plan-1",
        )
    )

    enc_file = tmp_path / "planner_state.enc"
    assert enc_file.exists()

    # Verify file is DPAPI encrypted on disk
    raw_bytes = enc_file.read_bytes()
    assert raw_bytes.startswith(_HEADER)
    assert b"quantum computing" not in raw_bytes

    # Create new instance and load state
    planner2 = PlannerEngine(event_bus)
    await planner2.start()
    plans = planner2.get_plans()
    assert len(plans) == 1
    assert plans[0].task == "search for quantum computing"

    await planner.stop()
    await planner2.stop()


@pytest.mark.asyncio
async def test_automation_engine_dpapi_encryption(tmp_path, monkeypatch):
    monkeypatch.setenv("HELIX_STATE_DIR", str(tmp_path))
    event_bus = EventBus()
    automation = AutomationEngine(event_bus)
    await automation.start()

    # Execute action
    await automation._handle_execute(
        HelixEvent(
            source="test",
            event_type="automation.execute",
            payload={"action": "browser_search", "params": {"query": "secret query"}, "risk_level": "low"},
            correlation_id="corr-auto-1",
        )
    )

    enc_file = tmp_path / "automation_state.enc"
    assert enc_file.exists()

    # Verify DPAPI encryption header and non-plaintext content
    raw_bytes = enc_file.read_bytes()
    assert raw_bytes.startswith(_HEADER)
    assert b"secret query" not in raw_bytes

    await automation.stop()


@pytest.mark.asyncio
async def test_planner_crash_recovery_on_startup(tmp_path, monkeypatch):
    monkeypatch.setenv("HELIX_STATE_DIR", str(tmp_path))
    event_bus = EventBus()

    # Simulate an in-flight plan left pending during a system crash
    step = PlanStep(step_id="step1", action="launch_application", target="notepad")
    step.status = "pending"
    plan = Plan(plan_id="plan_interrupted", task="open notepad", steps=[step])
    plan.status = "created"

    data = {"plan_interrupted": plan.to_dict()}
    json_str = json.dumps(data)
    enc_bytes = encrypt_string(json_str)
    (tmp_path / "planner_state.enc").write_bytes(enc_bytes)

    # Track published recovery events
    recovery_events = []

    async def capture(event):
        recovery_events.append(event)

    event_bus.subscribe("plan.failed", capture)

    # Start planner engine - should detect and recover interrupted plan
    planner = PlannerEngine(event_bus)
    await planner.start()

    recovered_plan = planner.get_plan("plan_interrupted")
    assert recovered_plan is not None
    assert recovered_plan.status == "failed"
    assert recovered_plan.steps[0].status == "failed"

    assert len(recovery_events) >= 1
    assert recovery_events[0].payload["plan_id"] == "plan_interrupted"
    assert "Interrupted by system restart" in recovery_events[0].payload["error"]

    await planner.stop()


@pytest.mark.asyncio
async def test_automation_crash_recovery_on_startup(tmp_path, monkeypatch):
    monkeypatch.setenv("HELIX_STATE_DIR", str(tmp_path))
    event_bus = EventBus()

    # Simulate an active action left executing during a crash
    record = ActionRecord(action_id="act_interrupted", action="compose_email", target="email")
    record.status = "executing"

    data = {
        "actions": {"act_interrupted": record.to_dict()},
        "history": [],
    }
    json_str = json.dumps(data)
    enc_bytes = encrypt_string(json_str)
    (tmp_path / "automation_state.enc").write_bytes(enc_bytes)

    recovery_events = []

    async def capture(event):
        recovery_events.append(event)

    event_bus.subscribe("automation.failed", capture)

    automation = AutomationEngine(event_bus)
    await automation.start()

    history = automation.get_history()
    assert len(history) == 1
    assert history[0].action_id == "act_interrupted"
    assert history[0].status == "failed"
    assert "Interrupted by system restart" in history[0].error

    assert len(recovery_events) == 1
    assert recovery_events[0].payload["action_id"] == "act_interrupted"

    await automation.stop()
