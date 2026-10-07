import asyncio
import os
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from foundation.event_bus.event_bus import EventBus, HelixEvent
from foundation.permission_manager.permission_manager import PermissionManager
from core_ai.tool_calling.tool_registry import ToolRegistry
from core_ai.tool_calling.tool_executor import ToolExecutor
from core_ai.tool_calling.models import ToolCall
from action.action_executor.action_executor import ActionExecutor


@pytest.mark.asyncio
async def test_permission_required_tools_are_tagged():
    registry = ToolRegistry(load_defaults=True)
    permission_tools = [
        "scan_laptop_files",
        "read_file",
        "search_installed_apps",
        "launch_application",
        "search_projects",
        "vscode_open",
    ]
    for name in permission_tools:
        tool_def = registry.get(name)
        assert tool_def is not None, f"Tool {name} should be in registry"
        assert tool_def.requires_permission is True, f"Tool {name} must require permission"
        assert tool_def.risk_level == "medium"


@pytest.mark.asyncio
async def test_tool_execution_waits_for_permission_and_succeeds_on_grant():
    event_bus = EventBus()
    perm_manager = PermissionManager(event_bus)
    await perm_manager.start()
    action_executor = ActionExecutor(event_bus)
    await action_executor.start()

    registry = ToolRegistry(load_defaults=True)
    executor = ToolExecutor(event_bus, registry=registry)
    await executor.start()

    call = ToolCall(
        name="search_installed_apps",
        arguments={"query": "notepad"},
        call_id="call_apps_01",
    )

    async def auto_grant():
        # Wait for permission request to register in PermissionManager
        for _ in range(20):
            if perm_manager.pending_requests:
                req = perm_manager.pending_requests[0]
                await event_bus.publish_event(
                    source="ui",
                    event_type="permission.grant",
                    payload={"id": req.id},
                )
                return
            await asyncio.sleep(0.05)

    grant_task = asyncio.create_task(auto_grant())
    result = await executor.execute(call)
    await grant_task

    assert result.success is True
    assert result.result is not None
    assert result.result.get("status") == "success"
    apps = result.result.get("apps", [])
    assert any("notepad" in a["name"].lower() or "notepad" in a["executable"].lower() for a in apps)

    await executor.stop()
    await action_executor.stop()
    await perm_manager.stop()


@pytest.mark.asyncio
async def test_tool_execution_aborts_on_permission_deny():
    event_bus = EventBus()
    perm_manager = PermissionManager(event_bus)
    await perm_manager.start()

    registry = ToolRegistry(load_defaults=True)
    executor = ToolExecutor(event_bus, registry=registry)
    await executor.start()

    call = ToolCall(
        name="scan_laptop_files",
        arguments={"folder": "documents", "query": "test"},
        call_id="call_scan_01",
    )

    async def auto_deny():
        for _ in range(20):
            if perm_manager.pending_requests:
                req = perm_manager.pending_requests[0]
                await event_bus.publish_event(
                    source="ui",
                    event_type="permission.deny",
                    payload={"id": req.id},
                )
                return
            await asyncio.sleep(0.05)

    deny_task = asyncio.create_task(auto_deny())
    result = await executor.execute(call)
    await deny_task

    assert result.success is False
    assert "Permission denied" in result.error

    await executor.stop()
    await perm_manager.stop()


@pytest.mark.asyncio
async def test_action_executor_scan_laptop_files():
    event_bus = EventBus()
    action_executor = ActionExecutor(event_bus)

    with TemporaryDirectory() as temp_dir:
        doc1 = Path(temp_dir) / "notes.txt"
        doc1.write_text("Meeting notes from project", encoding="utf-8")
        doc2 = Path(temp_dir) / "budget_2026.csv"
        doc2.write_text("Revenue,Expenses", encoding="utf-8")
        secret_exe = Path(temp_dir) / "malware.exe"
        secret_exe.write_text("binary", encoding="utf-8")

        res = action_executor._scan_laptop_files({
            "folder": temp_dir,
            "query": "notes",
            "max_results": 10,
        })

        assert res["status"] == "success"
        files = res["files"]
        assert len(files) == 1
        assert files[0]["filename"] == "notes.txt"

        # Verify .exe was ignored even when querying everything
        res_all = action_executor._scan_laptop_files({
            "folder": temp_dir,
            "query": "",
            "max_results": 10,
        })
        assert res_all["status"] == "success"
        filenames = [f["filename"] for f in res_all["files"]]
        assert "malware.exe" not in filenames
        assert "notes.txt" in filenames
        assert "budget_2026.csv" in filenames


@pytest.mark.asyncio
async def test_action_executor_read_file():
    event_bus = EventBus()
    action_executor = ActionExecutor(event_bus)

    with TemporaryDirectory() as temp_dir:
        test_file = Path(temp_dir) / "helix_doc.md"
        test_file.write_text("# HELIX System Architecture\nFully Sovereign AI OS", encoding="utf-8")

        res = action_executor._read_file(str(test_file), {})
        assert res["status"] == "success"
        assert "HELIX System Architecture" in res["content"]
        assert res["filename"] == "helix_doc.md"
