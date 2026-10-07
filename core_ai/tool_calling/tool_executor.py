from __future__ import annotations

import os
import time
import uuid
import asyncio
import logging
import urllib.parse
from typing import Any

from foundation.event_bus.event_bus import EventBus
from core_ai.tool_calling.models import ToolCall, ToolResult, ToolDefinition
from core_ai.tool_calling.tool_registry import ToolRegistry

logger = logging.getLogger("helix.tool_executor")

_BLOCKED_PATH_TOKENS = {"systemroot", "programdata", "program files"}
_BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".msi", ".ps1", ".psm1", ".psd1",
    ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".scr", ".pif",
    ".gadget", ".cpl", ".scf", ".lnk", ".inf", ".reg"
}
_ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


class ToolExecutor:
    """Validates, security-checks, and executes tool calls within HELIX."""

    def __init__(self, event_bus: EventBus, registry: ToolRegistry | None = None):
        self._event_bus = event_bus
        self._registry = registry or ToolRegistry()
        self._pending_tool_futures: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._pending_permission_futures: dict[str, asyncio.Future[bool]] = {}
        self._subscriptions: list[str] = []

    async def start(self) -> None:
        self._event_bus.subscribe("automation.result", self._handle_automation_result)
        self._event_bus.subscribe("automation.failed", self._handle_automation_failed)
        self._event_bus.subscribe("permission.granted", self._handle_permission_granted)
        self._event_bus.subscribe("permission.denied", self._handle_permission_denied)
        self._subscriptions = [
            "automation.result",
            "automation.failed",
            "permission.granted",
            "permission.denied",
        ]

    async def stop(self) -> None:
        for ev in self._subscriptions:
            if ev == "automation.result":
                self._event_bus.unsubscribe(ev, self._handle_automation_result)
            elif ev == "automation.failed":
                self._event_bus.unsubscribe(ev, self._handle_automation_failed)
            elif ev == "permission.granted":
                self._event_bus.unsubscribe(ev, self._handle_permission_granted)
            elif ev == "permission.denied":
                self._event_bus.unsubscribe(ev, self._handle_permission_denied)
        self._subscriptions.clear()
        for fut in self._pending_tool_futures.values():
            if not fut.done():
                fut.cancel()
        self._pending_tool_futures.clear()
        for fut in self._pending_permission_futures.values():
            if not fut.done():
                fut.cancel()
        self._pending_permission_futures.clear()

    async def execute(self, tool_call: ToolCall, session_id: str = "default") -> ToolResult:
        """Execute a validated ToolCall and return a structured ToolResult."""
        start_time = time.time()

        _ALIASES = {
            "read_docx": "read_document",
            "read_pdf": "read_document",
            "create_docx": "edit_docx",
            "write_docx": "edit_docx",
            "create_pdf": "generate_pdf",
            "make_pdf": "generate_pdf",
            "edit_document": "edit_docx",
            "search_apps": "search_installed_apps",
            "scan_files": "scan_laptop_files",
            "find_files": "scan_laptop_files",
        }
        if tool_call.name in _ALIASES:
            tool_call.name = _ALIASES[tool_call.name]

        # Handle hallucinated tool calls from local models (e.g. calculator_open, open_calculator, chrome_open)
        clean_tool = tool_call.name.lower().strip()
        if clean_tool.endswith("_open") or clean_tool.startswith("open_"):
            app_target = clean_tool.replace("_open", "").replace("open_", "").strip()
            tool_call.name = "launch_application"
            if "application" not in tool_call.arguments:
                tool_call.arguments["application"] = app_target
        elif clean_tool in ("calculator", "calc", "notepad", "chrome", "paint", "mspaint", "terminal", "wt", "explorer"):
            tool_call.name = "launch_application"
            if "application" not in tool_call.arguments:
                tool_call.arguments["application"] = clean_tool

        tool_def = self._registry.get(tool_call.name)

        if not tool_def:
            return ToolResult(
                call_id=tool_call.call_id,
                name=tool_call.name,
                success=False,
                error=f"Unknown tool '{tool_call.name}'.",
                duration_ms=(time.time() - start_time) * 1000,
            )

        # 1. Parameter Validation
        val_error = self._validate_parameters(tool_def, tool_call.arguments)
        if val_error:
            return ToolResult(
                call_id=tool_call.call_id,
                name=tool_call.name,
                success=False,
                error=val_error,
                duration_ms=(time.time() - start_time) * 1000,
            )

        # 2. Safety and Security Sandboxing Checks
        safety_error = self._validate_safety(tool_call.name, tool_call.arguments)
        if safety_error:
            return ToolResult(
                call_id=tool_call.call_id,
                name=tool_call.name,
                success=False,
                error=safety_error,
                duration_ms=(time.time() - start_time) * 1000,
            )

        # 2.5 Permission Gating for Laptop Resources
        if tool_def.requires_permission:
            perm_id = f"perm_{uuid.uuid4().hex[:8]}"
            loop = asyncio.get_running_loop()
            perm_future: asyncio.Future[bool] = loop.create_future()
            self._pending_permission_futures[perm_id] = perm_future

            reasoning, benefits, risks = self._build_permission_context(tool_call)

            await self._event_bus.publish_event(
                source="tool_executor",
                event_type="permission.request",
                payload={
                    "id": perm_id,
                    "request_id": perm_id,
                    "action": tool_call.name,
                    "reasoning": reasoning,
                    "benefits": benefits,
                    "risks": risks,
                    "source_module": "laptop_guard",
                    "resources": [f"{k}={v}" for k, v in tool_call.arguments.items()],
                },
                correlation_id=tool_call.call_id,
            )

            try:
                granted = await asyncio.wait_for(perm_future, timeout=60.0)
                if not granted:
                    return ToolResult(
                        call_id=tool_call.call_id,
                        name=tool_call.name,
                        success=False,
                        error=f"Permission denied by user. Access to laptop action '{tool_call.name}' was rejected.",
                        duration_ms=(time.time() - start_time) * 1000,
                    )
            except asyncio.TimeoutError:
                return ToolResult(
                    call_id=tool_call.call_id,
                    name=tool_call.name,
                    success=False,
                    error=f"Permission request timed out waiting for your approval in the HELIX UI.",
                    duration_ms=(time.time() - start_time) * 1000,
                )
            finally:
                self._pending_permission_futures.pop(perm_id, None)

        # 3. Check for Custom In-Engine Tools
        if tool_call.name == "get_system_state":
            state = self._get_system_state()
            return ToolResult(
                call_id=tool_call.call_id,
                name=tool_call.name,
                success=True,
                result=state,
                duration_ms=(time.time() - start_time) * 1000,
            )

        # 4. Dispatch via EventBus to ActionExecutor
        subscribers = getattr(self._event_bus, "_subscribers", {}).get("action.execute", [])
        if not subscribers:
            return ToolResult(
                call_id=tool_call.call_id,
                name=tool_call.name,
                success=True,
                result={"status": "simulated", "action": tool_call.name, "params": tool_call.arguments},
                duration_ms=(time.time() - start_time) * 1000,
            )

        action_id = f"act_{uuid.uuid4().hex[:8]}"
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending_tool_futures[action_id] = future

        await self._event_bus.publish_event(
            source="planner_engine",  # trusted source for ActionExecutor
            event_type="action.execute",
            payload={
                "action": tool_call.name,
                "action_id": action_id,
                "target": tool_call.arguments.get("target") or tool_call.arguments.get("path") or tool_call.arguments.get("application"),
                "params": tool_call.arguments,
            },
            correlation_id=tool_call.call_id,
        )

        try:
            # 15 second timeout for tool execution
            res = await asyncio.wait_for(future, timeout=15.0)
            success = res.get("status") != "failed" and "error" not in res
            return ToolResult(
                call_id=tool_call.call_id,
                name=tool_call.name,
                success=success,
                result=res.get("result", res),
                error=res.get("error"),
                duration_ms=(time.time() - start_time) * 1000,
            )
        except asyncio.TimeoutError:
            return ToolResult(
                call_id=tool_call.call_id,
                name=tool_call.name,
                success=False,
                error=f"Tool execution for '{tool_call.name}' timed out after 15 seconds.",
                duration_ms=(time.time() - start_time) * 1000,
            )
        except Exception as e:
            return ToolResult(
                call_id=tool_call.call_id,
                name=tool_call.name,
                success=False,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )
        finally:
            self._pending_tool_futures.pop(action_id, None)

    async def _handle_automation_result(self, event: Any) -> None:
        action_id = event.payload.get("action_id")
        if action_id in self._pending_tool_futures:
            fut = self._pending_tool_futures[action_id]
            if not fut.done():
                fut.set_result(event.payload.get("result", event.payload))

    async def _handle_automation_failed(self, event: Any) -> None:
        action_id = event.payload.get("action_id")
        if action_id in self._pending_tool_futures:
            fut = self._pending_tool_futures[action_id]
            if not fut.done():
                fut.set_result({"status": "failed", "error": event.payload.get("error", "Action failed")})

    async def _handle_permission_granted(self, event: Any) -> None:
        req_id = event.payload.get("id")
        if req_id in self._pending_permission_futures:
            fut = self._pending_permission_futures[req_id]
            if not fut.done():
                fut.set_result(True)

    async def _handle_permission_denied(self, event: Any) -> None:
        req_id = event.payload.get("id")
        if req_id in self._pending_permission_futures:
            fut = self._pending_permission_futures[req_id]
            if not fut.done():
                fut.set_result(False)

    def _build_permission_context(self, tool_call: ToolCall) -> tuple[str, list[str], list[str]]:
        name = tool_call.name
        args = tool_call.arguments
        if name == "scan_laptop_files":
            folder = args.get("folder", "documents")
            q = args.get("query", "")
            reasoning = f"HELIX requests permission to scan and locate files in your '{folder}' directory"
            if q:
                reasoning += f" matching keyword '{q}'."
            else:
                reasoning += "."
            benefits = [
                f"Enables HELIX to find relevant files in '{folder}'",
                "Provides accurate answers based on your laptop files",
            ]
            risks = ["Allows HELIX to inspect file names and metadata on your laptop"]
        elif name == "read_file":
            path = args.get("path", "")
            reasoning = f"HELIX requests permission to read content from file '{path}' on your laptop."
            benefits = [
                "Allows HELIX to analyze and summarize the requested file content",
                "Assists you with your documents directly",
            ]
            risks = [f"Reads file content from '{path}' into HELIX context"]
        elif name == "search_installed_apps":
            q = args.get("query", "")
            reasoning = f"HELIX requests permission to search your laptop's installed applications and Start Menu programs for '{q}'."
            benefits = [
                "Locates software installed on your machine",
                "Helps launch or interact with apps",
            ]
            risks = ["Inspects installed program registry and Start Menu shortcuts"]
        elif name == "launch_application":
            app = args.get("application", "")
            reasoning = f"HELIX requests permission to launch application '{app}' on your Windows desktop."
            benefits = [
                f"Opens '{app}' on your screen as requested",
            ]
            risks = [f"Starts process '{app}' on your operating system"]
        elif name == "search_projects":
            q = args.get("query", "")
            reasoning = f"HELIX requests permission to search your local codebase projects and git repositories for '{q}'."
            benefits = [
                "Finds development codebases on your laptop",
                "Enables project context awareness",
            ]
            risks = ["Reads repository directories on your laptop"]
        elif name == "vscode_open":
            path = args.get("path", "")
            reasoning = f"HELIX requests permission to open '{path}' in Visual Studio Code."
            benefits = ["Opens project or file in your VS Code workspace"]
            risks = [f"Launches VS Code targeting '{path}'"]
        elif name == "read_document":
            path = args.get("path", "")
            reasoning = f"HELIX requests permission to read and extract content from document '{path}'."
            benefits = [
                "Extracts readable text and tables from Word (.docx) or PDF (.pdf) documents",
                "Allows the assistant to analyze and summarize your document",
            ]
            risks = [f"Reads document data from '{path}' into HELIX context"]
        elif name == "edit_docx":
            path = args.get("path", "")
            action = args.get("action", "modify")
            reasoning = f"HELIX requests permission to {action} Word document '{path}' on your laptop."
            benefits = [
                f"Modifies or creates Microsoft Word document '{path}' per your instructions",
                "Preserves document styling and layout",
            ]
            risks = [f"Writes or modifies file on your disk: '{path}'"]
        elif name == "generate_pdf":
            path = args.get("path", "")
            title = args.get("title", "Document")
            reasoning = f"HELIX requests permission to generate PDF document '{title}' at '{path}'."
            benefits = [
                f"Compiles your text or report into a clean, formatted PDF document at '{path}'",
            ]
            risks = [f"Creates new PDF file on your laptop: '{path}'"]
        else:
            reasoning = f"HELIX requests your permission to execute laptop action '{name}'."
            benefits = ["Fulfills the requested assistant workflow on your machine"]
            risks = [f"Runs privileged action '{name}'"]
        return reasoning, benefits, risks

    def _validate_parameters(self, tool_def: ToolDefinition, args: dict[str, Any]) -> str | None:
        for param in tool_def.parameters:
            if param.required and (param.name not in args or args[param.name] is None):
                return f"Missing required parameter '{param.name}' for tool '{tool_def.name}'."
            if param.name in args and args[param.name] is not None:
                val = args[param.name]
                if param.type == "string" and not isinstance(val, str):
                    args[param.name] = str(val)
                elif param.type == "integer" and not isinstance(val, int):
                    try:
                        args[param.name] = int(val)
                    except ValueError:
                        return f"Parameter '{param.name}' must be an integer, got '{val}'."
        return None

    def _validate_safety(self, name: str, args: dict[str, Any]) -> str | None:
        path = args.get("path") or args.get("target")
        if path and isinstance(path, str):
            path_lower = path.lower()
            if any(token in path_lower for token in _BLOCKED_PATH_TOKENS):
                return f"Access denied: system path token in '{path}'."
            ext = os.path.splitext(path)[1].lower()
            if ext in _BLOCKED_EXTENSIONS:
                return f"Access denied: blocked file extension '{ext}'."

        url = args.get("url")
        if url and isinstance(url, str):
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme and parsed.scheme.lower() not in _ALLOWED_URL_SCHEMES:
                return f"Blocked URL scheme: '{parsed.scheme}'. Only http, https, and mailto are allowed."

        return None

    def _get_system_state(self) -> dict[str, Any]:
        """Fetch basic system perception state."""
        return {
            "os": "Windows 11",
            "active_companion": "HELIX PAIOS",
            "time_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "status": "operational",
        }
