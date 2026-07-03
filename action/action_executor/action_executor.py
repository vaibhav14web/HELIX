import os
import sys
import re
import asyncio
import logging
import shutil
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any

from foundation.event_bus.event_bus import EventBus, HelixEvent

logger = logging.getLogger("helix.action_executor")

_SEARCH_URL = os.getenv("HELIX_SEARCH_URL", "https://www.google.com/search?q={}")

_TRUSTED_SOURCES = {"automation_engine", "planner_engine", "orchestrator"}
if os.getenv("HELIX_DEV_MODE", "").lower() in ("true", "1", "yes"):
    _TRUSTED_SOURCES.add("test")

_KNOWN_APPS: dict[str, str] = {
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "firefox": "firefox.exe",
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "terminal": "wt.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
}

_KNOWN_APP_PATHS: dict[str, list[str]] = {
    "chrome.exe": [
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ],
    "msedge.exe": [
        os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Microsoft", "Edge", "Application", "msedge.exe"),
    ],
    "firefox.exe": [
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Mozilla Firefox", "firefox.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Mozilla Firefox", "firefox.exe"),
    ],
}

_BLOCKED_PATH_PREFIXES = [
    Path(os.environ.get("SystemRoot", "C:\\Windows")).resolve(),
    Path(os.environ.get("ProgramData", "C:\\ProgramData")).resolve(),
    Path(os.environ.get("ALLUSERSPROFILE", "C:\\ProgramData")).resolve(),
]

_BLOCKED_FILE_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".msi", ".ps1", ".psm1", ".psd1",
    ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".scr", ".pif",
    ".gadget", ".cpl", ".scf", ".lnk", ".inf", ".reg", ".htaccess",
}

_MAX_STRING_LENGTH = 4096
_MAX_EMAIL_LENGTH = 254
_EXECUTOR_TIMEOUT = 30.0
_RATE_LIMIT_WINDOW = 2.0
_MAX_PER_WINDOW = 5

_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$")


class ActionExecutor:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._lock = asyncio.Lock()
        self._subscriptions: list[str] = []
        self._event_handler_map: dict[str, Any] = {}
        self._action_times: list[float] = []

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._event_handler_map = {
            "action.execute": self._handle_action,
        }
        for event_type, handler in self._event_handler_map.items():
            self._event_bus.subscribe(event_type, handler)
        self._subscriptions = list(self._event_handler_map.keys())
        logger.info("Action Executor started")

    async def stop(self) -> None:
        for event_type, handler in self._event_handler_map.items():
            self._event_bus.unsubscribe(event_type, handler)
        self._subscriptions.clear()
        logger.info("Action Executor stopped")

    async def _handle_action(self, event: HelixEvent) -> None:
        action = event.payload.get("action", "")
        action_id = event.payload.get("action_id", "")
        target = event.payload.get("target")
        params = event.payload.get("params", {})
        plan_id = event.payload.get("plan_id")
        step_id = event.payload.get("step_id")
        source = event.source

        if source not in _TRUSTED_SOURCES:
            error = f"Untrusted event source: {source}"
            logger.warning(error)
            await self._publish_failed(action_id, action, error, plan_id, step_id, event.correlation_id)
            return

        try:
            await self._check_rate_limit()
        except ValueError as e:
            await self._publish_failed(action_id, action, str(e), plan_id, step_id, event.correlation_id)
            return

        try:
            result = await self._dispatch(action, target, params)
            await self._event_bus.publish_event(
                source="action_executor",
                event_type="automation.result",
                payload={
                    "action_id": action_id,
                    "action": action,
                    "result": result,
                    "plan_id": plan_id,
                    "step_id": step_id,
                },
                correlation_id=event.correlation_id,
            )
        except Exception as e:
            logger.exception("Action failed: %s", action)
            await self._publish_failed(action_id, action, str(e), plan_id, step_id, event.correlation_id)

    async def _publish_failed(self, action_id: str, action: str, error: str, plan_id: str | None, step_id: str | None, correlation_id: str) -> None:
        await self._event_bus.publish_event(
            source="action_executor",
            event_type="automation.failed",
            payload={
                "action_id": action_id,
                "action": action,
                "error": error,
                "plan_id": plan_id,
                "step_id": step_id,
            },
            correlation_id=correlation_id,
        )

    async def _check_rate_limit(self) -> None:
        async with self._lock:
            now = time.time()
            self._action_times = [t for t in self._action_times if now - t < _RATE_LIMIT_WINDOW]
            if len(self._action_times) >= _MAX_PER_WINDOW:
                raise ValueError("Rate limit exceeded: too many actions")
            self._action_times.append(now)

    async def _dispatch(self, action: str, target: str | None, params: dict[str, Any]) -> dict[str, Any]:
        if action == "browser_search":
            return await self._executor(self._browser_search, params)
        if action == "launch_application":
            return await self._executor(self._launch_application, target, params)
        if action == "read_file":
            return await self._executor(self._read_file, target, params)
        if action == "send_notification":
            return await self._executor(self._send_notification, params)
        if action == "compose_email":
            return await self._executor(self._compose_email, params)
        if action == "open_url":
            return await self._executor(self._open_url, target, params)
        raise ValueError(f"Unknown action type: {action}")

    async def _executor(self, fn, *args) -> Any:
        return await asyncio.wait_for(
            self._loop.run_in_executor(None, fn, *args),
            timeout=_EXECUTOR_TIMEOUT,
        )

    # ── Input Validation ────────────────────────────────────────

    def _validate_string(self, value: str, name: str, max_len: int = _MAX_STRING_LENGTH) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string, got {type(value).__name__}")
        if len(value) > max_len:
            raise ValueError(f"{name} exceeds maximum length of {max_len}")
        return value

    # ── Browser Search ──────────────────────────────────────────

    def _browser_search(self, params: dict[str, Any]) -> dict[str, Any]:
        query = self._validate_string(params.get("query", ""), "query")
        if not query:
            raise ValueError("Search query is empty")
        url = _SEARCH_URL.format(urllib.parse.quote_plus(query))
        return self._open_url_browser(url, action="browser_search")

    # ── Launch Application ──────────────────────────────────────

    def _launch_application(self, target: str | None, params: dict[str, Any]) -> dict[str, Any]:
        app = target or params.get("application", "")
        if not app:
            raise ValueError("No application specified to launch")
        app = self._validate_string(app, "application")

        app_lower = app.lower().strip()
        executable = _KNOWN_APPS.get(app_lower)
        if not executable:
            safe_list = ", ".join(sorted(_KNOWN_APPS))
            raise ValueError(f"Unknown application: '{app}'. Allowed: {safe_list}")

        resolved = shutil.which(executable)
        if not resolved:
            fallback_paths = _KNOWN_APP_PATHS.get(executable, [])
            for path in fallback_paths:
                if os.path.isfile(path):
                    resolved = path
                    break

        if not resolved:
            raise FileNotFoundError(f"Application not found: {executable}. Make sure it is installed.")

        try:
            subprocess.Popen(
                [resolved],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {"status": "launched", "application": app}
        except OSError as e:
            raise OSError(f"Failed to launch {app}: {e}")

    # ── Read / Open File ────────────────────────────────────────

    def _read_file(self, target: str | None, params: dict[str, Any]) -> dict[str, Any]:
        file_path = target or params.get("path", "")
        if not file_path:
            raise ValueError("No file path specified")
        file_path = self._validate_string(file_path, "path")

        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = path.suffix.lower()
        if ext in _BLOCKED_FILE_EXTENSIONS:
            raise PermissionError(f"Access denied: cannot open {ext} files")

        for blocked in _BLOCKED_PATH_PREFIXES:
            if blocked in path.parents or blocked == path:
                raise PermissionError(f"Access denied: cannot open files under {blocked}")

        try:
            if sys.platform == "win32":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(
                    ["open", str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(
                    ["xdg-open", str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            return {"status": "opened", "path": str(path)}
        except OSError as e:
            raise OSError(f"Failed to open {file_path}: {e}")

    # ── Send Notification ───────────────────────────────────────

    def _send_notification(self, params: dict[str, Any]) -> dict[str, Any]:
        message = self._validate_string(params.get("message", ""), "message")
        title = self._validate_string(params.get("title", "Helix"), "title")
        if not message:
            raise ValueError("Notification message is empty")

        if sys.platform == "win32":
            self._windows_toast(title, message)
        elif sys.platform == "darwin":
            subprocess.run(
                ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
                capture_output=True, timeout=5,
            )
        else:
            try:
                subprocess.run(
                    ["notify-send", title, message],
                    capture_output=True, timeout=5,
                )
            except FileNotFoundError:
                logger.info("Notification (%s): %s", title, message)

        return {"status": "sent", "title": title}

    def _windows_toast(self, title: str, message: str) -> None:
        script = (
            '$t=[Windows.UI.Notifications.ToastNotificationManager,'
            'Windows.UI.Notifications,ContentType=WindowsRuntime];'
            '$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent('
            '[Windows.UI.Notifications.ToastTemplateType]::ToastText02);'
            '$n=$x.GetElementsByTagName("text");'
            '$n.Item(0).AppendChild($x.CreateTextNode($env:HELIX_TOAST_TITLE))|Out-Null;'
            '$n.Item(1).AppendChild($x.CreateTextNode($env:HELIX_TOAST_MESSAGE))|Out-Null;'
            '$t=[Windows.UI.Notifications.ToastNotification]::new($x);'
            '[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Helix").Show($t);'
        )
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                timeout=10,
                env={
                    **os.environ,
                    "HELIX_TOAST_TITLE": title,
                    "HELIX_TOAST_MESSAGE": message,
                },
            )
        except Exception as e:
            logger.warning("Toast notification failed: %s", e)

    # ── Compose Email ───────────────────────────────────────────

    def _compose_email(self, params: dict[str, Any]) -> dict[str, Any]:
        to = self._validate_string(params.get("to", ""), "to", _MAX_EMAIL_LENGTH)
        subject = self._validate_string(params.get("subject", ""), "subject")
        body = self._validate_string(params.get("body", ""), "body")
        cc = self._validate_string(params.get("cc", ""), "cc", _MAX_EMAIL_LENGTH)
        bcc = self._validate_string(params.get("bcc", ""), "bcc", _MAX_EMAIL_LENGTH)

        if to:
            self._validate_email(to)
        if cc:
            self._validate_email(cc)
        if bcc:
            self._validate_email(bcc)

        query_params = {}
        if subject:
            query_params["subject"] = subject
        if body:
            query_params["body"] = body
        if cc:
            query_params["cc"] = cc
        if bcc:
            query_params["bcc"] = bcc

        if to:
            mailto = f"mailto:{to}"
        else:
            mailto = "mailto:"

        if query_params:
            mailto += "?" + urllib.parse.urlencode(query_params)

        self._open_url_browser(mailto, action="compose_email")
        return {"status": "composed"}

    def _validate_email(self, address: str) -> None:
        if not _EMAIL_PATTERN.match(address.strip()):
            raise ValueError(f"Invalid email address: {address}")

    # ── Open URL ────────────────────────────────────────────────

    def _open_url(self, target: str | None, params: dict[str, Any]) -> dict[str, Any]:
        url = target or params.get("url", "")
        if not url:
            raise ValueError("No URL specified")
        url = self._validate_string(url, "url")
        return self._open_url_browser(url, action="open_url")

    def _validate_url(self, url: str) -> None:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https", "mailto"):
            raise ValueError(f"Blocked URL scheme: '{parsed.scheme}'. Only http, https, and mailto are allowed.")
        if not parsed.netloc and parsed.scheme in ("http", "https"):
            raise ValueError("Invalid URL: no host specified")

    def _open_url_browser(self, url: str, action: str = "open_url") -> dict[str, Any]:
        self._validate_url(url)
        import webbrowser
        webbrowser.open(url)
        logger.info("Opened URL (%s): %s", action, url)
        return {"status": "opened", "url": url}
