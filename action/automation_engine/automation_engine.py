import os
import asyncio
import logging
import uuid
import time
from datetime import datetime, timezone
from typing import Any

from foundation.event_bus.event_bus import EventBus, HelixEvent
from foundation.storage_manager.crypto import encrypt_string, decrypt_string

logger = logging.getLogger("helix.automation_engine")

_PERMISSION_TIMEOUT = 300


class ActionRecord:
    def __init__(self, action_id: str, action: str, permission_id: str | None = None, target: str | None = None, params: dict[str, Any] | None = None, risk_level: str = "low", plan_id: str | None = None, step_id: str | None = None):
        self.action_id = action_id
        self.action = action
        self.permission_id = permission_id
        self.target = target
        self.params = params or {}
        self.risk_level = risk_level
        self.plan_id = plan_id
        self.step_id = step_id
        self.status = "pending"
        self.result: dict[str, Any] | None = None
        self.error: str | None = None
        self.created_at = time.time()
        self.created_at_iso = datetime.now(timezone.utc).isoformat()
        self.completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action": self.action,
            "permission_id": self.permission_id,
            "target": self.target,
            "params": self.params,
            "risk_level": self.risk_level,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at_iso,
            "completed_at": self.completed_at,
        }


class AutomationEngine:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._lock = asyncio.Lock()
        self._max_history = int(os.getenv("HELIX_AUTOMATION_MAX_HISTORY", "200"))
        self._permission_timeout = int(os.getenv("HELIX_AUTOMATION_PERMISSION_TIMEOUT", str(_PERMISSION_TIMEOUT)))
        self._state_path = os.getenv("HELIX_STATE_DIR", os.path.join(os.getenv("HELIX_DATA_DIR", "./data"), "state"))
        self._actions: dict[str, ActionRecord] = {}
        self._actions_by_permission: dict[str, str] = {}
        self._actions_waiting_confirmation: dict[str, ActionRecord] = {}
        self._history: list[ActionRecord] = []
        self._subscriptions: list[str] = []
        self._event_handler_map: dict[str, Any] = {}
        self._watchdog_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._event_handler_map = {
            "automation.execute": self._handle_execute,
            "automation.execute_step": self._handle_execute_step,
            "automation.result": self._handle_result,
            "automation.failed": self._handle_failed,
            "automation.cancel": self._handle_cancel,
            "automation.confirm.response": self._handle_confirm_response,
            "permission.granted": self._handle_permission_granted,
            "permission.denied": self._handle_permission_denied,
        }
        for event_type, handler in self._event_handler_map.items():
            self._event_bus.subscribe(event_type, handler)
        self._subscriptions = list(self._event_handler_map.keys())
        await self.load_state()
        self._watchdog_task = asyncio.create_task(self._watchdog())
        logger.info("Automation Engine started")

    async def stop(self) -> None:
        for event_type, handler in self._event_handler_map.items():
            self._event_bus.unsubscribe(event_type, handler)
        self._subscriptions.clear()
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            self._watchdog_task = None
        logger.info("Automation Engine stopped")

    async def _handle_execute(self, event: HelixEvent) -> None:
        action = event.payload.get("action", "")
        if not action.strip():
            await self._event_bus.publish_event(
                source="automation_engine",
                event_type="automation.failed",
                payload={"action_id": "", "action": "", "error": "Action cannot be empty"},
                correlation_id=event.correlation_id,
            )
            return

        action_id = uuid.uuid4().hex[:12]
        target = event.payload.get("target")
        params = event.payload.get("params", {})
        plan_id = event.payload.get("plan_id")
        step_id = event.payload.get("step_id")
        permission_id = event.payload.get("permission_id")
        risk_level = event.payload.get("risk_level", "low")

        async with self._lock:
            record = ActionRecord(action_id=action_id, action=action, permission_id=permission_id, target=target, params=params, risk_level=risk_level, plan_id=plan_id, step_id=step_id)
            self._actions[action_id] = record

            if permission_id:
                self._actions_by_permission[permission_id] = action_id
                record.status = "waiting_permission"
                logger.info("Action awaiting permission: %s (%s, perm=%s)", action_id, action, permission_id)
                return

        if risk_level == "high":
            await self._request_confirmation(action_id, record, action, target, params, plan_id, step_id, event.correlation_id)
            return

        if risk_level == "medium":
            await self._request_permission(action_id, record, action, target, params, plan_id, step_id, event.correlation_id)
            return

        await self._execute_action(action_id, record, action, target, params, plan_id, step_id, event.correlation_id)

    async def _handle_execute_step(self, event: HelixEvent) -> None:
        plan_id = event.payload.get("plan_id", "")
        step = event.payload.get("step", {})
        action = step.get("action", "")
        target = step.get("target")
        params = step.get("params", {})
        step_id = step.get("step_id", "")
        risk_level = event.payload.get("risk_level") or step.get("risk_level", "low")

        if not action.strip():
            await self._event_bus.publish_event(
                source="automation_engine",
                event_type="automation.failed",
                payload={"action_id": "", "action": "", "error": "Step action cannot be empty", "plan_id": plan_id, "step_id": step_id},
                correlation_id=event.correlation_id,
            )
            return

        permission_id = event.payload.get("permission_id")
        action_id = uuid.uuid4().hex[:12]

        async with self._lock:
            record = ActionRecord(action_id=action_id, action=action, permission_id=permission_id, target=target, params=params, risk_level=risk_level, plan_id=plan_id, step_id=step_id)
            self._actions[action_id] = record
            if permission_id:
                self._actions_by_permission[permission_id] = action_id
                record.status = "waiting_permission"
                logger.info("Step awaiting permission: %s (%s, perm=%s)", action_id, action, permission_id)
                return

        if risk_level == "high":
            await self._request_confirmation(action_id, record, action, target, params, plan_id, step_id, event.correlation_id)
            return

        if risk_level == "medium":
            await self._request_permission(action_id, record, action, target, params, plan_id, step_id, event.correlation_id)
            return

        await self._execute_action(action_id, record, action, target, params, plan_id, step_id, event.correlation_id)

    async def _handle_result(self, event: HelixEvent) -> None:
        action_id = event.payload.get("action_id", "")
        result = event.payload.get("result", {})

        async with self._lock:
            record = self._actions.pop(action_id, None)
            if not record:
                return
            self._actions_by_permission.pop(record.permission_id, None)
            record.status = "completed"
            record.result = result
            record.completed_at = datetime.now(timezone.utc).isoformat()
            self._history.append(record)
            self._prune_history()

        await self.save_state()
        await self._event_bus.publish_event(
            source="automation_engine",
            event_type="automation.completed",
            payload={
                "action_id": action_id,
                "action": record.action,
                "result": result,
                "plan_id": event.payload.get("plan_id"),
                "step_id": event.payload.get("step_id"),
            },
            correlation_id=event.correlation_id,
        )
        logger.info("Action completed: %s (%s)", action_id, record.action)

    async def _handle_failed(self, event: HelixEvent) -> None:
        action_id = event.payload.get("action_id", "")
        error = event.payload.get("error", "Unknown error")

        async with self._lock:
            record = self._actions.pop(action_id, None)
            if not record:
                return
            self._actions_by_permission.pop(record.permission_id, None)
            record.status = "failed"
            record.error = error
            record.completed_at = datetime.now(timezone.utc).isoformat()
            self._history.append(record)
            self._prune_history()

        await self.save_state()
        logger.warning("Action failed: %s (%s): %s", action_id, record.action, error)

    async def _handle_cancel(self, event: HelixEvent) -> None:
        action_id = event.payload.get("action_id", "")

        async with self._lock:
            record = self._actions.pop(action_id, None)
            if not record:
                record = self._actions_waiting_confirmation.pop(action_id, None)
                if not record:
                    return
            self._actions_by_permission.pop(record.permission_id, None)
            record.status = "cancelled"
            self._history.append(record)
            self._prune_history()

        await self.save_state()
        logger.info("Action cancelled: %s", action_id)

    async def _handle_permission_granted(self, event: HelixEvent) -> None:
        permission_id = event.payload.get("id", "")

        async with self._lock:
            action_id = self._actions_by_permission.get(permission_id)
            if not action_id:
                return
            record = self._actions.get(action_id)
            if not record or record.status != "waiting_permission":
                return
            record.status = "executing"

        action = record.action
        target = record.target
        params = record.params
        plan_id = event.payload.get("plan_id") or record.plan_id
        step_id = event.payload.get("step_id") or record.step_id
        await self._execute_action(action_id, record, action, target, params, plan_id, step_id, event.correlation_id)

    async def _handle_permission_denied(self, event: HelixEvent) -> None:
        permission_id = event.payload.get("id", "")

        async with self._lock:
            action_id = self._actions_by_permission.pop(permission_id, None)
            if not action_id:
                return
            record = self._actions.pop(action_id, None)
            if not record:
                return
            record.status = "denied"
            record.error = "Permission denied by user"
            record.completed_at = datetime.now(timezone.utc).isoformat()
            self._history.append(record)
            self._prune_history()

        logger.info("Action denied: %s (%s)", action_id, record.action)

    async def _request_permission(
        self,
        action_id: str,
        record: ActionRecord,
        action: str,
        target: str | None,
        params: dict[str, Any],
        plan_id: str | None,
        step_id: str | None,
        correlation_id: str,
    ) -> None:
        permission_id = uuid.uuid4().hex[:12]

        async with self._lock:
            record.permission_id = permission_id
            self._actions_by_permission[permission_id] = action_id
            record.status = "waiting_permission"
            logger.info("Action requesting permission: %s (%s, perm=%s)", action_id, action, permission_id)

        description = f"Allow Helix to {action}"
        if target:
            description += f" on {target}"
        if params.get("url"):
            description += f" ({params['url']})"

        await self._event_bus.publish_event(
            source="automation_engine",
            event_type="automation.permission_needed",
            payload={
                "action_id": action_id,
                "permission_id": permission_id,
                "action": action,
                "target": target,
                "params": params,
                "plan_id": plan_id,
                "step_id": step_id,
                "risk_level": "medium",
                "description": description,
            },
            correlation_id=correlation_id,
        )

        await self._event_bus.publish_event(
            source="automation_engine",
            event_type="action.execute",
            payload={
                "action_id": f"notify-{permission_id}",
                "action": "send_notification",
                "params": {
                    "title": "HELIX permission needed",
                    "message": f"{description}. Open HELIX to grant or deny.",
                },
                "risk_level": "low",
            },
            correlation_id=correlation_id,
        )

    async def _request_confirmation(
        self,
        action_id: str,
        record: ActionRecord,
        action: str,
        target: str | None,
        params: dict[str, Any],
        plan_id: str | None,
        step_id: str | None,
        correlation_id: str,
    ) -> None:
        async with self._lock:
            record.status = "waiting_confirmation"
            self._actions_waiting_confirmation[action_id] = record
            logger.info("Action awaiting confirmation: %s (%s)", action_id, action)

        description = f"Are you sure you want to {action}"
        if target:
            description += f" {target}"
        if params.get("url"):
            description += f" ({params['url']})"
        if params.get("path"):
            description += f" ({params['path']})"
        description += "?"

        await self._event_bus.publish_event(
            source="automation_engine",
            event_type="automation.confirm.request",
            payload={
                "action_id": action_id,
                "action": action,
                "target": target,
                "params": params,
                "plan_id": plan_id,
                "step_id": step_id,
                "risk_level": "high",
                "description": description,
                "confirm_prompt": f"High-risk action: {description} Please confirm verbally or in text.",
            },
            correlation_id=correlation_id,
        )

    async def _handle_confirm_response(self, event: HelixEvent) -> None:
        action_id = event.payload.get("action_id", "")
        confirmed = event.payload.get("confirmed", False)

        async with self._lock:
            record = self._actions_waiting_confirmation.pop(action_id, None)
            if not record:
                logger.warning("Confirmation response for unknown action: %s", action_id)
                return

            if not confirmed:
                self._actions.pop(action_id, None)
                record.status = "denied"
                record.error = "User declined high-risk confirmation"
                record.completed_at = datetime.now(timezone.utc).isoformat()
                self._history.append(record)
                self._prune_history()
                logger.info("High-risk action denied by user: %s (%s)", action_id, record.action)
                return

            logger.info("High-risk action confirmed: %s (%s)", action_id, record.action)

        plan_id = event.payload.get("plan_id")
        step_id = event.payload.get("step_id")
        correlation_id = event.correlation_id
        target = record.target
        params = record.params

        await self._request_permission(action_id, record, record.action, target, params, plan_id, step_id, correlation_id)

    async def _execute_action(
        self,
        action_id: str,
        record: ActionRecord,
        action: str,
        target: str | None,
        params: dict[str, Any],
        plan_id: str | None,
        step_id: str | None,
        correlation_id: str,
    ) -> None:
        record.status = "executing"
        await self.save_state()
        logger.info("Executing action: %s (%s)", action_id, action)

        await self._event_bus.publish_event(
            source="automation_engine",
            event_type="action.execute",
            payload={
                "action_id": action_id,
                "action": action,
                "target": target,
                "params": params,
                "plan_id": plan_id,
                "step_id": step_id,
                "risk_level": record.risk_level,
            },
            priority=2,
            correlation_id=correlation_id,
        )

    async def _watchdog(self) -> None:
        try:
            while True:
                await asyncio.sleep(30)
                now = time.time()
                async with self._lock:
                    expired_perm = [
                        aid for aid, rec in self._actions.items()
                        if rec.status == "waiting_permission" and now - rec.created_at > self._permission_timeout
                    ]
                    for aid in expired_perm:
                        record = self._actions.pop(aid, None)
                        if record:
                            self._actions_by_permission.pop(record.permission_id, None)
                            record.status = "timeout"
                            record.error = "Permission request timed out"
                            record.completed_at = datetime.now(timezone.utc).isoformat()
                            self._history.append(record)
                            logger.warning("Permission timeout: %s (%s)", aid, record.action)

                    expired_conf = [
                        aid for aid, rec in self._actions_waiting_confirmation.items()
                        if now - rec.created_at > self._permission_timeout
                    ]
                    for aid in expired_conf:
                        record = self._actions_waiting_confirmation.pop(aid, None)
                        if record:
                            self._actions.pop(aid, None)
                            record.status = "timeout"
                            record.error = "Confirmation request timed out"
                            record.completed_at = datetime.now(timezone.utc).isoformat()
                            self._history.append(record)
                            logger.warning("Confirmation timeout: %s (%s)", aid, record.action)

                    self._prune_history()
        except asyncio.CancelledError:
            pass

    async def save_state(self) -> None:
        import json
        os.makedirs(self._state_path, exist_ok=True)
        path = os.path.join(self._state_path, "automation_state.enc")
        try:
            async with self._lock:
                data = {
                    "actions": {aid: rec.to_dict() for aid, rec in self._actions.items()},
                    "actions_by_permission": dict(self._actions_by_permission),
                    "actions_waiting_confirmation": {aid: rec.to_dict() for aid, rec in self._actions_waiting_confirmation.items()},
                    "history": [r.to_dict() for r in self._history],
                }
            json_str = json.dumps(data, indent=2, default=str)
            enc_bytes = encrypt_string(json_str)
            with open(path, "wb") as f:
                f.write(enc_bytes)
        except Exception as e:
            logger.warning("Failed to save automation state: %s", e)

    async def load_state(self) -> None:
        import json
        enc_path = os.path.join(self._state_path, "automation_state.enc")
        legacy_path = os.path.join(self._state_path, "automation_state.json")
        path_to_read = enc_path if os.path.exists(enc_path) else (legacy_path if os.path.exists(legacy_path) else None)
        if not path_to_read:
            return

        try:
            with open(path_to_read, "rb") as f:
                raw_bytes = f.read()
            json_str = decrypt_string(raw_bytes)
            data = json.loads(json_str)

            recovered_actions: list[ActionRecord] = []
            async with self._lock:
                for entry in data.get("history", []):
                    record = ActionRecord(
                        action_id=entry.get("action_id", ""),
                        action=entry.get("action", ""),
                        permission_id=entry.get("permission_id"),
                        target=entry.get("target"),
                        params=entry.get("params", {}),
                        risk_level=entry.get("risk_level", "low"),
                    )
                    record.status = entry.get("status", "completed")
                    record.result = entry.get("result")
                    record.error = entry.get("error")
                    record.created_at_iso = entry.get("created_at", "")
                    record.completed_at = entry.get("completed_at")
                    self._history.append(record)

                active_dict = data.get("actions", {})
                for aid, entry in active_dict.items():
                    record = ActionRecord(
                        action_id=entry.get("action_id", aid),
                        action=entry.get("action", ""),
                        permission_id=entry.get("permission_id"),
                        target=entry.get("target"),
                        params=entry.get("params", {}),
                        risk_level=entry.get("risk_level", "low"),
                    )
                    st = entry.get("status", "executing")
                    if st in ("executing", "waiting_permission", "waiting_confirmation", "pending"):
                        record.status = "failed"
                        record.error = "Interrupted by system restart"
                        record.completed_at = datetime.now(timezone.utc).isoformat()
                        self._history.append(record)
                        recovered_actions.append(record)

                self._prune_history()

            logger.info("Loaded %d history records from automation state", len(self._history))
            for r_act in recovered_actions:
                logger.warning("Recovered interrupted action on startup: %s (%s)", r_act.action_id, r_act.action)
                await self._event_bus.publish_event(
                    source="automation_engine",
                    event_type="automation.failed",
                    payload={
                        "action_id": r_act.action_id,
                        "action": r_act.action,
                        "error": "Interrupted by system restart",
                    },
                )
            if recovered_actions:
                await self.save_state()
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning("Failed to load automation state: %s", e)

    def get_action(self, action_id: str) -> ActionRecord | None:
        return self._actions.get(action_id)

    def get_history(self, limit: int = 50) -> list[ActionRecord]:
        if limit <= 0:
            return []
        return self._history[-limit:]

    def _prune_history(self) -> None:
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
