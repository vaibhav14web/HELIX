import asyncio
import os
import pytest

from foundation.event_bus.event_bus import EventBus
from core_ai.llm_engine.llm_engine import LLMEngine
from core_ai.conversation_engine.conversation_engine import ConversationEngine
from action.planner_engine.planner_engine import PlannerEngine
from action.automation_engine.automation_engine import AutomationEngine


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
async def engine(event_bus):
    os.environ["HELIX_LLM_BACKEND"] = "mock"
    llm = LLMEngine(event_bus)
    conv = ConversationEngine(event_bus)
    await llm.start()
    await conv.start()
    yield conv, llm
    await conv.stop()
    await llm.stop()


@pytest.mark.asyncio
async def test_chat_returns_response(event_bus, engine):
    conv, llm = engine
    response = await conv.chat("Hello HELIX", "test_session_1")
    assert isinstance(response, str)
    assert len(response) > 0


@pytest.mark.asyncio
async def test_chat_stores_user_and_assistant(event_bus, engine):
    conv, llm = engine
    session_id = "test_session_2"

    await conv.chat("What is HELIX?", session_id)

    history = conv._conversation_history.get(session_id, [])
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "What is HELIX?"
    assert history[1]["role"] == "assistant"
    assert len(history[1]["content"]) > 0


@pytest.mark.asyncio
async def test_chat_maintains_history(event_bus, engine):
    conv, llm = engine
    session_id = "test_session_3"

    await conv.chat("First message", session_id)
    await conv.chat("Second message", session_id)
    await conv.chat("Third message", session_id)

    history = conv._conversation_history.get(session_id, [])
    assert len(history) == 6
    assert history[0]["content"] == "First message"
    assert history[2]["content"] == "Second message"
    assert history[4]["content"] == "Third message"


@pytest.mark.asyncio
async def test_chat_isolated_sessions(event_bus, engine):
    conv, llm = engine

    await conv.chat("Session A message", "session_a")
    await conv.chat("Session B message", "session_b")

    hist_a = conv._conversation_history.get("session_a", [])
    hist_b = conv._conversation_history.get("session_b", [])

    assert len(hist_a) == 2
    assert hist_a[0]["content"] == "Session A message"
    assert len(hist_b) == 2
    assert hist_b[0]["content"] == "Session B message"


@pytest.mark.asyncio
async def test_build_prompt_contains_system_and_history(event_bus, engine):
    conv, llm = engine
    session_id = "test_prompt"

    await conv.chat("Hello", session_id)

    prompt = conv._build_prompt(session_id)
    assert "HELIX" in prompt
    assert "Hello" in prompt
    assert "<|system|>" in prompt
    assert "<|user|>" in prompt
    assert "<|assistant|>" in prompt


@pytest.mark.asyncio
async def test_has_correct_subscriptions(event_bus, engine):
    conv, llm = engine
    assert "llm.generation.complete" in conv._subscriptions
    assert "llm.generation.error" in conv._subscriptions
    assert "memory.conversation.retrieved" in conv._subscriptions
    assert "conversation.user_message" in conv._subscriptions
    assert "plan.created" in conv._subscriptions
    assert "plan.failed" in conv._subscriptions
    assert "automation.completed" in conv._subscriptions
    assert "automation.failed" in conv._subscriptions


@pytest.mark.asyncio
async def test_start_publishes_ready(event_bus, engine):
    conv, llm = engine
    assert conv._subscriptions is not None
    assert len(conv._subscriptions) == 8


@pytest.mark.asyncio
async def test_handle_user_message_triggers_llm(event_bus, engine):
    conv, llm = engine

    received = []

    async def capture(event):
        received.append(event)

    event_bus.subscribe("llm.generation.complete", capture)
    event_bus.subscribe("llm.generation.start", capture)

    await event_bus.publish_event(
        source="test",
        event_type="conversation.user_message",
        payload={"text": "Hello via user message", "session_id": "msg_session"},
    )

    await asyncio.sleep(0.2)

    assert len(received) >= 1
    assert any(e.payload.get("session_id") == "msg_session" for e in received)

    await conv.stop()
    await llm.stop()


@pytest.mark.asyncio
async def test_chat_handles_llm_error(event_bus):
    conv = ConversationEngine(event_bus)
    await conv.start()

    async def respond_with_error(event):
        await event_bus.publish_event(
            source="test",
            event_type="llm.generation.error",
            payload={"error": "Connection timed out", "session_id": event.payload.get("session_id")},
            correlation_id=event.correlation_id,
        )

    event_bus.subscribe("llm.generate", respond_with_error)

    response = await conv.chat("Trigger error", "error_session")
    assert "error" in response.lower()
    assert "connection timed out" in response.lower()

    await conv.stop()


@pytest.mark.asyncio
async def test_chat_timeout_publishes_stop(event_bus):
    conv = ConversationEngine(event_bus)
    conv._response_timeout = 0.1
    await conv.start()

    stop_received = asyncio.Event()
    async def on_stop(event):
        if event.payload.get("session_id") == "timeout_session":
            stop_received.set()

    event_bus.subscribe("llm.generate.stop", on_stop)

    response = await conv.chat("Trigger timeout", "timeout_session")
    assert "too long to respond" in response.lower()

    try:
        await asyncio.wait_for(stop_received.wait(), timeout=1.0)
    except asyncio.TimeoutError:
        pytest.fail("Did not receive llm.generate.stop event")

    await conv.stop()



@pytest.mark.asyncio
async def test_medium_risk_action_returns_permission_prompt(event_bus):
    conv = ConversationEngine(event_bus)
    planner = PlannerEngine(event_bus)
    automation = AutomationEngine(event_bus)

    llm_requests = []
    permission_requests = []
    event_bus.subscribe("llm.generate", lambda e: llm_requests.append(e))
    event_bus.subscribe("automation.permission_needed", lambda e: permission_requests.append(e))

    await planner.start()
    await automation.start()
    await conv.start()

    response = await conv.chat("Can you open Google Chrome?", "permission_session")

    assert "need your medium-risk permission" in response
    assert "Google Chrome" in response
    assert len(permission_requests) == 1
    assert permission_requests[0].payload["target"] == "Google Chrome"
    assert len(llm_requests) == 0

    await conv.stop()
    await automation.stop()
    await planner.stop()


@pytest.mark.asyncio
async def test_check_known_app_requests_permission(event_bus):
    conv = ConversationEngine(event_bus)
    planner = PlannerEngine(event_bus)
    automation = AutomationEngine(event_bus)

    llm_requests = []
    permission_requests = []
    event_bus.subscribe("llm.generate", lambda e: llm_requests.append(e))
    event_bus.subscribe("automation.permission_needed", lambda e: permission_requests.append(e))

    await planner.start()
    await automation.start()
    await conv.start()

    response = await conv.chat("Can you check Google Chrome please?", "check_chrome_session")

    assert "need your medium-risk permission" in response
    assert "Google Chrome" in response
    assert permission_requests[0].payload["target"] == "Google Chrome"
    assert len(llm_requests) == 0

    await conv.stop()
    await automation.stop()
    await planner.stop()
