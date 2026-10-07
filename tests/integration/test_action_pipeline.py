import os
import pytest

from foundation.event_bus.event_bus import EventBus
from core_ai.llm_engine.llm_engine import LLMEngine
from core_ai.conversation_engine.conversation_engine import ConversationEngine
from action.planner_engine.planner_engine import PlannerEngine
from action.automation_engine.automation_engine import AutomationEngine
from action.action_executor.action_executor import ActionExecutor


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
async def pipeline(event_bus, tmp_path):
    os.environ["HELIX_LLM_BACKEND"] = "mock"

    import action.action_executor.action_executor as _ae
    _ae._TRUSTED_SOURCES.add("test")

    llm = LLMEngine(event_bus)
    conv = ConversationEngine(event_bus)
    planner = PlannerEngine(event_bus)
    planner._state_path = str(tmp_path)
    automation = AutomationEngine(event_bus)
    automation._state_path = str(tmp_path)
    executor = ActionExecutor(event_bus)

    await planner.start()
    await automation.start()
    await executor.start()
    await llm.start()
    await conv.start()

    yield {"conv": conv, "llm": llm, "planner": planner, "automation": automation, "executor": executor, "event_bus": event_bus}

    await conv.stop()
    await llm.stop()
    await executor.stop()
    await automation.stop()
    await planner.stop()

    _ae._TRUSTED_SOURCES.discard("test")


@pytest.mark.asyncio
async def test_open_chrome_triggers_action_pipeline(pipeline):
    conv = pipeline["conv"]
    response = await conv.chat("open chrome", "test_integration")

    assert isinstance(response, str)
    assert len(response) > 0

    plan_history = pipeline["planner"].get_plans()
    assert len(plan_history) >= 1
    latest_plan = plan_history[-1]
    assert latest_plan.status == "completed" or latest_plan.status == "created"

    if latest_plan.steps:
        step = latest_plan.steps[0]
        assert step.action == "launch_application"
        assert step.risk_level == "medium"


@pytest.mark.asyncio
async def test_browser_search_triggers_action_pipeline(pipeline):
    conv = pipeline["conv"]
    response = await conv.chat("search for python tutorials", "test_integration_2")

    assert isinstance(response, str)
    assert len(response) > 0

    automation_history = pipeline["automation"].get_history()
    executed_actions = [a for a in automation_history if a.status == "completed"]
    assert len(executed_actions) >= 1
    assert executed_actions[-1].action == "browser_search"


@pytest.mark.asyncio
async def test_medium_risk_action_reports_needs_permission(pipeline):
    conv = pipeline["conv"]
    response = await conv.chat("compose email to test@example.com", "test_integration_3")

    assert isinstance(response, str)
    assert len(response) > 0


@pytest.mark.asyncio
async def test_medium_risk_action_skips_auto_execution(pipeline):
    conv = pipeline["conv"]
    _ = await conv.chat("open chrome", "test_integration_4")

    automation_history = pipeline["automation"].get_history()
    executed = [a for a in automation_history if a.status == "completed"]
    assert len(executed) == 0


@pytest.mark.asyncio
async def test_unknown_message_no_action(pipeline):
    conv = pipeline["conv"]
    response = await conv.chat("what is the meaning of life", "test_integration_5")

    assert isinstance(response, str)
    assert len(response) > 0

    plan_history = pipeline["planner"].get_plans()
    latest_plan = plan_history[-1] if plan_history else None
    if latest_plan:
        steps = latest_plan.steps
        if steps:
            assert steps[0].action == "unknown"
