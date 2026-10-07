import pytest
import json
from foundation.event_bus.event_bus import EventBus
from core_ai.tool_calling.models import ToolParameter, ToolDefinition, ToolCall, ToolResult
from core_ai.tool_calling.definitions import get_default_tool_definitions
from core_ai.tool_calling.tool_registry import ToolRegistry
from core_ai.tool_calling.tool_parser import ToolParser
from core_ai.tool_calling.tool_executor import ToolExecutor


def test_tool_models():
    param = ToolParameter(
        name="query",
        type="string",
        description="Search query",
        required=True,
    )
    schema = param.to_schema()
    assert schema["type"] == "string"
    assert schema["description"] == "Search query"

    tool = ToolDefinition(
        name="test_tool",
        description="Test description",
        parameters=[param],
        risk_level="low",
    )
    json_schema = tool.to_json_schema()
    assert json_schema["type"] == "object"
    assert "query" in json_schema["properties"]
    assert "query" in json_schema["required"]

    openai_spec = tool.to_openai_tool()
    assert openai_spec["type"] == "function"
    assert openai_spec["function"]["name"] == "test_tool"
    assert openai_spec["function"]["description"] == "Test description"
    assert openai_spec["function"]["parameters"] == json_schema


def test_tool_registry():
    registry = ToolRegistry(load_defaults=True)
    all_tools = registry.list_all()
    assert len(all_tools) >= 10
    assert registry.has("launch_application")
    assert registry.has("browser_search")
    assert registry.has("read_file")

    web_tools = registry.list_all(category="web")
    assert len(web_tools) >= 2
    assert all(t.category == "web" for t in web_tools)

    openai_tools = registry.to_openai_tools()
    assert isinstance(openai_tools, list)
    assert len(openai_tools) == len(all_tools)
    assert openai_tools[0]["type"] == "function"

    instructions = registry.to_system_prompt_instruction()
    assert "Tool Calling Guidelines" in instructions
    assert "<tool_call>" in instructions
    assert "browser_search" in instructions


def test_tool_parser_native():
    sample_native = [
        {
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "browser_search",
                "arguments": json.dumps({"query": "quantum computing breakthroughs"}),
            },
        }
    ]
    calls = ToolParser.parse_native_tool_calls(sample_native)
    assert len(calls) == 1
    assert calls[0].name == "browser_search"
    assert calls[0].arguments == {"query": "quantum computing breakthroughs"}
    assert calls[0].call_id == "call_123"


def test_tool_parser_qwen_xml():
    raw_text = (
        "I'll search for the latest updates.\n"
        "<tool_call>\n"
        '{"name": "browser_search", "arguments": {"query": "deep learning 2026"}}\n'
        "</tool_call>\n"
        "Let me know if you need anything else."
    )
    cleaned, calls = ToolParser.parse_text_response(raw_text)
    assert len(calls) == 1
    assert calls[0].name == "browser_search"
    assert calls[0].arguments == {"query": "deep learning 2026"}
    assert "<tool_call>" not in cleaned
    assert "I'll search for the latest updates." in cleaned


def test_tool_parser_markdown_code_block():
    raw_text = (
        "Opening Notepad for you:\n"
        "```tool_call\n"
        '{"name": "launch_application", "arguments": {"application": "notepad"}}\n'
        "```"
    )
    cleaned, calls = ToolParser.parse_text_response(raw_text)
    assert len(calls) == 1
    assert calls[0].name == "launch_application"
    assert calls[0].arguments == {"application": "notepad"}
    assert "```tool_call" not in cleaned


def test_tool_parser_plain_text():
    raw_text = "Hello! How can I assist your workflow today?"
    cleaned, calls = ToolParser.parse_text_response(raw_text)
    assert len(calls) == 0
    assert cleaned == raw_text


@pytest.mark.asyncio
async def test_tool_executor_validation():
    event_bus = EventBus()
    executor = ToolExecutor(event_bus)
    await executor.start()

    # 1. Unknown tool
    res = await executor.execute(ToolCall(name="non_existent_tool", arguments={}))
    assert not res.success
    assert "Unknown tool" in (res.error or "")

    # 2. Missing required parameter
    res = await executor.execute(ToolCall(name="browser_search", arguments={}))
    assert not res.success
    assert "Missing required parameter 'query'" in (res.error or "")

    # 3. Blocked system path
    res = await executor.execute(ToolCall(name="read_file", arguments={"path": "C:\\Windows\\System32\\cmd.exe"}))
    assert not res.success
    assert "Access denied" in (res.error or "")

    # 4. Blocked extension
    res = await executor.execute(ToolCall(name="read_file", arguments={"path": "notes.bat"}))
    assert not res.success
    assert "blocked file extension" in (res.error or "")

    # 5. Blocked URL scheme
    res = await executor.execute(ToolCall(name="open_url", arguments={"url": "javascript:alert(1)"}))
    assert not res.success
    assert "Blocked URL scheme" in (res.error or "")

    # 6. get_system_state
    res = await executor.execute(ToolCall(name="get_system_state", arguments={}))
    assert res.success
    assert res.result["os"] == "Windows 11"

    await executor.stop()
