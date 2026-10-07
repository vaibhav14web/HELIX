import os
import re
import asyncio
import logging
import uuid
import urllib.parse
from datetime import datetime, timezone
from typing import Any

from foundation.event_bus.event_bus import EventBus, HelixEvent
from foundation.storage_manager.crypto import encrypt_string, decrypt_string

logger = logging.getLogger("helix.planner_engine")


class PlanStep:
    def __init__(
        self,
        step_id: str,
        action: str,
        target: str | None = None,
        params: dict[str, Any] | None = None,
        depends_on: list[str] | None = None,
        risk_level: str = "low",
        status: str = "pending",
    ):
        self.step_id = step_id
        self.action = action
        self.target = target
        self.params = params or {}
        self.depends_on = depends_on or []
        self.status = status
        self.risk_level = risk_level

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action": self.action,
            "target": self.target,
            "params": self.params,
            "depends_on": self.depends_on,
            "status": self.status,
            "risk_level": self.risk_level,
        }


class Plan:
    def __init__(self, plan_id: str, task: str, steps: list[PlanStep], context: dict[str, Any] | None = None):
        self.plan_id = plan_id
        self.task = task
        self.steps = steps
        self.context = context or {}
        self.status = "created"
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "task": self.task,
            "steps": [s.to_dict() for s in self.steps],
            "context": self.context,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


_KNOWN_APPS = {"chrome", "google chrome", "edge", "microsoft edge", "firefox", "notepad", "calc", "calculator", "mspaint", "paint", "wt", "terminal", "explorer", "file explorer"}

_APP_DISPLAY_NAMES = {
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "edge": "Microsoft Edge",
    "microsoft edge": "Microsoft Edge",
    "firefox": "Firefox",
    "notepad": "Notepad",
    "calc": "Calculator",
    "calculator": "Calculator",
    "mspaint": "Paint",
    "paint": "Paint",
    "wt": "Terminal",
    "terminal": "Terminal",
    "explorer": "File Explorer",
    "file explorer": "File Explorer",
}

_LOW_RISK_ACTIONS = {"browser_search", "read_file", "read_browser_page"}

_MEDIUM_RISK_ACTIONS = {"compose_email", "send_notification", "launch_application", "in_app_task", "vscode_open", "create_note"}

_BLOCKED_PATH_TOKENS = {"systemroot", "programdata", "program files"}

_BLOCKED_PATH_PREFIXES = [
    p.lower().rstrip("\\") + "\\"
    for p in [
        os.environ.get("SystemRoot", "C:\\Windows"),
        os.environ.get("ProgramData", "C:\\ProgramData"),
        os.environ.get("ALLUSERSPROFILE", "C:\\ProgramData"),
        os.environ.get("ProgramFiles", "C:\\Program Files"),
        os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
    ]
]

_BLOCKED_EXTENSIONS = {".exe", ".bat", ".cmd", ".com", ".msi", ".ps1", ".psm1", ".psd1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".scr", ".pif", ".gadget", ".cpl", ".scf", ".lnk", ".inf", ".reg"}

_ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


class PlannerEngine:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._lock = asyncio.Lock()
        self._max_plans = int(os.getenv("HELIX_PLANNER_MAX_PLANS", "50"))
        self._state_path = os.getenv("HELIX_STATE_DIR", os.path.join(os.getenv("HELIX_DATA_DIR", "./data"), "state"))
        self._plans: dict[str, Plan] = {}
        self._subscriptions: list[str] = []
        self._event_handler_map: dict[str, Any] = {}

    async def start(self) -> None:
        self._event_handler_map = {
            "plan.request": self._handle_request,
            "plan.step.completed": self._handle_step_completed,
            "plan.step.failed": self._handle_step_failed,
            "plan.cancel": self._handle_cancel,
        }
        for event_type, handler in self._event_handler_map.items():
            self._event_bus.subscribe(event_type, handler)
        self._subscriptions = list(self._event_handler_map.keys())
        await self.load_state()
        logger.info("Planner Engine started")

    async def stop(self) -> None:
        for event_type, handler in self._event_handler_map.items():
            self._event_bus.unsubscribe(event_type, handler)
        self._subscriptions.clear()
        self._plans.clear()
        logger.info("Planner Engine stopped")

    async def _handle_request(self, event: HelixEvent) -> None:
        task = event.payload.get("task", "")
        if not task.strip():
            await self._event_bus.publish_event(
                source="planner_engine",
                event_type="plan.failed",
                payload={"error": "Task cannot be empty", "correlation_id": event.correlation_id},
                correlation_id=event.correlation_id,
            )
            return

        context = event.payload.get("context", {})

        try:
            steps = self._build_steps(task, context)
            for step in steps:
                self._validate_task_safety(step.action, step.target, step.params)
        except ValueError as e:
            await self._event_bus.publish_event(
                source="planner_engine",
                event_type="plan.failed",
                payload={"error": str(e), "task": task},
                correlation_id=event.correlation_id,
            )
            return

        plan_id = uuid.uuid4().hex[:12]

        async with self._lock:
            plan = Plan(plan_id=plan_id, task=task, steps=steps, context=context)
            self._plans[plan_id] = plan
            self._prune_plans()

        logger.info("Plan created: %s (%d steps)", plan_id, len(steps))
        await self.save_state()
        await self._event_bus.publish_event(
            source="planner_engine",
            event_type="plan.created",
            payload={
                "plan_id": plan_id,
                "task": task,
                "steps": [s.to_dict() for s in steps],
                "context": context,
            },
            priority=2,
            correlation_id=event.correlation_id,
        )

    async def _handle_step_completed(self, event: HelixEvent) -> None:
        plan_id = event.payload.get("plan_id", "")
        step_id = event.payload.get("step_id", "")

        async with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                logger.warning("Step completed for unknown plan: %s", plan_id)
                return

            for step in plan.steps:
                if step.step_id == step_id:
                    step.status = "completed"
                    break

            all_completed = all(s.status == "completed" for s in plan.steps)
            if all_completed:
                plan.status = "completed"
                plan.completed_at = datetime.now(timezone.utc).isoformat()

        await self.save_state()
        if all_completed:
            logger.info("Plan completed: %s", plan_id)
            await self._event_bus.publish_event(
                source="planner_engine",
                event_type="plan.completed",
                payload={"plan_id": plan_id, "task": plan.task},
                correlation_id=event.correlation_id,
            )

    async def _handle_step_failed(self, event: HelixEvent) -> None:
        plan_id = event.payload.get("plan_id", "")
        step_id = event.payload.get("step_id", "")
        error = event.payload.get("error", "Unknown error")

        async with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                return

            for step in plan.steps:
                if step.step_id == step_id:
                    step.status = "failed"
                    break

            plan.status = "failed"

        await self.save_state()
        logger.warning("Plan step failed: %s / %s (%s)", plan_id, step_id, error)
        await self._event_bus.publish_event(
            source="planner_engine",
            event_type="plan.failed",
            payload={"plan_id": plan_id, "step_id": step_id, "error": error, "task": plan.task},
            correlation_id=event.correlation_id,
        )

    async def _handle_cancel(self, event: HelixEvent) -> None:
        plan_id = event.payload.get("plan_id", "")

        async with self._lock:
            plan = self._plans.pop(plan_id, None)

        if plan:
            plan.status = "cancelled"
            await self.save_state()
            logger.info("Plan cancelled: %s", plan_id)
            await self._event_bus.publish_event(
                source="planner_engine",
                event_type="plan.cancelled",
                payload={"plan_id": plan_id, "task": plan.task},
                correlation_id=event.correlation_id,
            )

    def _classify_risk(self, action: str, target: str | None, params: dict[str, Any]) -> str:
        if action == "browser_search":
            return "low"
        if action == "read_file":
            path = target or params.get("path", "")
            if any(token in path.lower() for token in _BLOCKED_PATH_TOKENS):
                return "high"
            ext = os.path.splitext(path)[1].lower()
            if ext in _BLOCKED_EXTENSIONS:
                return "high"
            return "medium"
        if action == "launch_application":
            app = (target or params.get("application", "")).lower().strip()
            for k in _KNOWN_APPS:
                if k in app or app == k:
                    return "low"
            return "medium"
        if action == "compose_email":
            return "medium"
        if action == "send_notification":
            return "low"
        if action == "open_url":
            url = target or params.get("url", "")
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in _ALLOWED_URL_SCHEMES:
                return "high"
            return "low"
        return "medium"

    def _validate_task_safety(self, action: str, target: str | None, params: dict[str, Any]) -> None:
        path = target or params.get("path", "")
        if path:
            path_lower = path.lower()
            if any(token in path_lower for token in _BLOCKED_PATH_TOKENS):
                raise ValueError(f"Access denied: blocked system path in request: {path}")
            resolved = os.path.abspath(path).lower()
            for prefix in _BLOCKED_PATH_PREFIXES:
                if resolved.startswith(prefix):
                    raise ValueError(f"Access denied: blocked system path in request: {path}")
            ext = os.path.splitext(path)[1].lower()
            if ext in _BLOCKED_EXTENSIONS:
                raise ValueError(f"Access denied: blocked file extension: {ext}")

        url = target or params.get("url", "")
        if url:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme and parsed.scheme not in _ALLOWED_URL_SCHEMES:
                raise ValueError(f"Blocked URL scheme: '{parsed.scheme}'. Only http, https, and mailto are allowed.")

    def _build_steps(self, task: str, context: dict[str, Any] | None) -> list[PlanStep]:
        steps: list[PlanStep] = []
        lower = task.lower().strip()
        words = set(lower.split())

        if lower.startswith("open file"):
            file_path = task[len("open file "):].strip() if len(lower) > 9 else ""
            step = PlanStep(
                step_id=uuid.uuid4().hex[:8],
                action="read_file",
                params={"path": file_path},
            )
            step.risk_level = self._classify_risk(step.action, step.target, step.params)
            steps.append(step)
            return steps

        # If user expresses negation, feedback, or complaints, do not create a launch step
        negation_markers = (
            "did not", "didn't", "not open", "won't open", "haven't", "hasn't",
            "why didn't", "you did not", "could not", "repeat", "repeating",
            "repeats", "problem is", "issue is", "broken", "not work", "not working", "fails"
        )
        if any(neg in lower for neg in negation_markers):
            return []

        app_request_words = {"open", "launch", "start", "run"}
        has_action_prefix = any(lower.startswith(p) for p in ("open ", "launch ", "start ", "run ", "check "))
        known_app_found = self._extract_known_app(task)
        check_known_app = "check" in words and known_app_found is not None

        if has_action_prefix or (known_app_found and (app_request_words & words)) or check_known_app:
            raw_target = task
            for prefix in ("open ", "launch ", "start ", "check ", "run "):
                if lower.startswith(prefix):
                    raw_target = task[len(prefix):].strip().rstrip(" ?.! ")
                    break

            app_target = self._extract_known_app(raw_target) or known_app_found
            if not app_target and has_action_prefix:
                raw_lower = raw_target.lower().strip()
                vague_targets = {"it", "this", "that", "them", "something", "anything", "app", "an app", "the app", "application", "the application", "program", "the program"}
                if raw_lower in vague_targets:
                    # Check if previous context has a known target
                    if context and isinstance(context, dict):
                        app_target = context.get("last_application") or context.get("last_target") or context.get("target")
                    else:
                        app_target = None
                else:
                    app_target = raw_target

            if app_target:
                # If compound command like "open google chrome and search for computer"
                if " and search" in app_target.lower() or " to search" in app_target.lower():
                    app_target = app_target.split(" and ")[0].split(" to ")[0].strip()

                params: dict[str, Any] = {"application": app_target}
                if "search" in lower or "browse" in lower or "look" in lower or "find" in lower:
                    match = re.search(r"(?:search\s+for|search|browse\s+for|browse|look\s+for|find)\s+(.+)", task, re.IGNORECASE)
                    if match:
                        search_query = match.group(1).strip()
                        params["url"] = f"https://www.google.com/search?q={urllib.parse.quote_plus(search_query)}"

                step = PlanStep(
                    step_id=uuid.uuid4().hex[:8],
                    action="launch_application",
                    target=app_target,
                    params=params,
                )
                step.risk_level = self._classify_risk(step.action, step.target, step.params)
                steps.append(step)
                return steps

        if {"search", "browse", "look", "find"} & words or lower.startswith("look up"):
            query = task
            for prefix in ("search ", "browse ", "look up ", "find "):
                if lower.startswith(prefix):
                    query = task[len(prefix):].strip()
                    break
            step = PlanStep(
                step_id=uuid.uuid4().hex[:8],
                action="browser_search",
                target="browser",
                params={"query": query},
            )
            step.risk_level = self._classify_risk(step.action, step.target, step.params)
            steps.append(step)
            return steps

        if "send" in words and ({"email", "mail"} & words):
            step = PlanStep(
                step_id=uuid.uuid4().hex[:8],
                action="compose_email",
                params={"subject": task},
            )
            step.risk_level = self._classify_risk(step.action, step.target, step.params)
            steps.append(step)
            return steps

        if {"notify", "notification", "alert", "remind", "reminder"} & words:
            message = task
            for prefix in ("notify ", "alert ", "remind "):
                if lower.startswith(prefix):
                    message = task[len(prefix):].strip()
                    break
            step = PlanStep(
                step_id=uuid.uuid4().hex[:8],
                action="send_notification",
                params={"message": message},
            )
            step.risk_level = self._classify_risk(step.action, step.target, step.params)
            steps.append(step)
            return steps

        if "read" in words:
            file_path = task
            if lower.startswith("read "):
                file_path = task[5:].strip()
            step = PlanStep(
                step_id=uuid.uuid4().hex[:8],
                action="read_file",
                params={"path": file_path},
            )
            step.risk_level = self._classify_risk(step.action, step.target, step.params)
            steps.append(step)
            return steps

        step = PlanStep(
            step_id=uuid.uuid4().hex[:8],
            action="unknown",
            params={"task": task},
        )
        step.risk_level = self._classify_risk(step.action, step.target, step.params)
        steps.append(step)
        return steps

    def _extract_raw_app(self, task: str) -> str | None:
        lower = task.lower()
        for app in sorted(_KNOWN_APPS, key=len, reverse=True):
            if app in lower:
                return app
        return None

    def _extract_known_app(self, task: str) -> str | None:
        lower = task.lower()
        for app in sorted(_KNOWN_APPS, key=len, reverse=True):
            if app in lower:
                return _APP_DISPLAY_NAMES.get(app, app.title())
        return None

    def get_plan(self, plan_id: str) -> Plan | None:
        return self._plans.get(plan_id)

    def get_plans(self, status: str | None = None) -> list[Plan]:
        plans = list(self._plans.values())
        if status:
            plans = [p for p in plans if p.status == status]
        return plans

    async def save_state(self) -> None:
        import json
        os.makedirs(self._state_path, exist_ok=True)
        path = os.path.join(self._state_path, "planner_state.enc")
        try:
            async with self._lock:
                data = {pid: plan.to_dict() for pid, plan in self._plans.items()}
            json_str = json.dumps(data, indent=2, default=str)
            enc_bytes = encrypt_string(json_str)
            with open(path, "wb") as f:
                f.write(enc_bytes)
        except Exception as e:
            logger.warning("Failed to save planner state: %s", e)

    async def load_state(self) -> None:
        import json
        enc_path = os.path.join(self._state_path, "planner_state.enc")
        legacy_path = os.path.join(self._state_path, "planner_state.json")
        path_to_read = enc_path if os.path.exists(enc_path) else (legacy_path if os.path.exists(legacy_path) else None)
        if not path_to_read:
            return

        try:
            with open(path_to_read, "rb") as f:
                raw_bytes = f.read()
            json_str = decrypt_string(raw_bytes)
            data = json.loads(json_str)

            recovered_plans: list[Plan] = []
            async with self._lock:
                for pid, plan_data in data.items():
                    steps = [PlanStep(**s) for s in plan_data.get("steps", [])]
                    plan = Plan(
                        plan_id=pid,
                        task=plan_data.get("task", ""),
                        steps=steps,
                        context=plan_data.get("context", {}),
                    )
                    plan.status = plan_data.get("status", "created")
                    plan.created_at = plan_data.get("created_at", "")
                    plan.completed_at = plan_data.get("completed_at")

                    # Crash recovery: if plan was left in-flight on process restart
                    if plan.status in ("created", "in_progress", "pending"):
                        has_interrupted = False
                        for step in plan.steps:
                            if step.status in ("pending", "executing"):
                                step.status = "failed"
                                has_interrupted = True
                        if has_interrupted or plan.status != "completed":
                            plan.status = "failed"
                            recovered_plans.append(plan)

                    self._plans[pid] = plan

            logger.info("Loaded %d plans from state", len(data))
            for r_plan in recovered_plans:
                logger.warning("Recovered interrupted plan on startup: %s (%s)", r_plan.plan_id, r_plan.task)
                await self._event_bus.publish_event(
                    source="planner_engine",
                    event_type="plan.failed",
                    payload={
                        "plan_id": r_plan.plan_id,
                        "error": "Interrupted by system restart",
                        "task": r_plan.task,
                    },
                )
            if recovered_plans:
                await self.save_state()
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning("Failed to load planner state: %s", e)

    def _prune_plans(self) -> None:
        if len(self._plans) > self._max_plans:
            sorted_ids = sorted(self._plans.keys(), key=lambda pid: self._plans[pid].created_at)
            for pid in sorted_ids[:len(sorted_ids) - self._max_plans]:
                del self._plans[pid]
