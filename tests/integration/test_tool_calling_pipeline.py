import os
import pytest

from foundation.event_bus.event_bus import EventBus
from core_ai.llm_engine.llm_engine import LLMEngine
from core_ai.conversation_engine.conversation_engine import ConversationEngine
from action.action_executor.action_executor import ActionExecutor
from core_ai.tool_calling.models import ToolCall
from core_ai.tool_calling.tool_registry import ToolRegistry
from core_ai.tool_calling.tool_executor import ToolExecutor
from core_ai.tool_calling.tool_parser import ToolParser


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
async def tool_env(event_bus, tmp_path):
    os.environ["HELIX_LLM_BACKEND"] = "mock"

    import action.action_executor.action_executor as _ae
    _ae._TRUSTED_SOURCES.add("planner_engine")

    llm = LLMEngine(event_bus)
    conv = ConversationEngine(event_bus)
    executor = ActionExecutor(event_bus)

    await executor.start()
    await llm.start()
    await conv.start()

    yield {
        "event_bus": event_bus,
        "llm": llm,
        "conv": conv,
        "executor": executor,
    }

    await conv.stop()
    await llm.stop()
    await executor.stop()


@pytest.mark.asyncio
async def test_tool_calling_direct_chat_with_tools(tool_env):
    llm = tool_env["llm"]
    registry = ToolRegistry(load_defaults=True)
    tools = registry.to_openai_tools()

    messages = [{"role": "user", "content": "search for latest AI developments"}]
    result = await llm.chat_with_tools(messages=messages, tools=tools)

    assert "content" in result
    assert len(result["tool_calls"]) == 1
    call_data = result["tool_calls"][0]
    assert call_data["name"] == "browser_search"
    assert "query" in call_data["arguments"]


@pytest.mark.asyncio
async def test_tool_calling_execution_pipeline(tool_env):
    event_bus = tool_env["event_bus"]
    registry = ToolRegistry(load_defaults=True)
    tool_executor = ToolExecutor(event_bus, registry=registry)
    await tool_executor.start()

    # Execute system state tool
    state_call = ToolCall(name="get_system_state", arguments={})
    res = await tool_executor.execute(state_call)
    assert res.success
    assert res.result["status"] == "operational"

    # Execute note creation tool
    note_call = ToolCall(name="create_note", arguments={"title": "Test Title", "content": "Hello note"})
    res = await tool_executor.execute(note_call)
    assert res.success

    await tool_executor.stop()


@pytest.mark.asyncio
async def test_qwen_xml_tool_parsing_and_execution(tool_env):
    event_bus = tool_env["event_bus"]
    registry = ToolRegistry(load_defaults=True)
    tool_executor = ToolExecutor(event_bus, registry=registry)
    await tool_executor.start()

    llm_output = (
        "I'll make a note of this meeting.\n"
        "<tool_call>\n"
        '{"name": "create_note", "arguments": {"title": "Architecture Sync", "content": "Discussed tool calling schema"}}\n'
        "</tool_call>\n"
        "Let me know if you need to add anything else."
    )

    cleaned_text, parsed_calls = ToolParser.parse_text_response(llm_output)
    assert len(parsed_calls) == 1
    assert parsed_calls[0].name == "create_note"
    assert parsed_calls[0].arguments["title"] == "Architecture Sync"

    res = await tool_executor.execute(parsed_calls[0])
    assert res.success
    assert "Architecture Sync" in str(res.result)

    await tool_executor.stop()
