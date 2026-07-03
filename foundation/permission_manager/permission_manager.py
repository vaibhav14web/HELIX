import uuid
import logging
import fnmatch
from datetime import datetime, timezone
from typing import Any

from foundation.event_bus.event_bus import EventBus, HelixEvent

logger = logging.getLogger("helix.permission_manager")


class PermissionRequest:
    def __init__(
        self,
        action: str,
        reasoning: str,
        benefits: list[str] | None = None,
        risks: list[str] | None = None,
        alternatives: list[str] | None = None,
        source_module: str = "unknown",
        resources: list[str] | None = None,
        request_id: str | None = None,
    ):
        self.id = request_id or uuid.uuid4().hex[:12]
        self.action = action
        self.reasoning = reasoning
        self.benefits = benefits or []
        self.risks = risks or []
        self.alternatives = alternatives or []
        self.source_module = source_module
        self.resources = resources or []
        self.status = "pending"
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.decided_at: str | None = None


class PermissionManager:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._pending: dict[str, PermissionRequest] = {}
        self._history: list[PermissionRequest] = []
        self._max_history = 200
        self._auto_approve_patterns: list[str] = []
        self._subscriptions: list[str] = []
        self._event_handler_map: dict[str, Any] = {}

    async def start(self) -> None:
        self._event_handler_map = {
            "permission.request": self._handle_request,
            "permission.grant": self._handle_grant,
            "permission.deny": self._handle_deny,
            "permission.auto_approve.add": self._handle_add_pattern,
            "permission.auto_approve.remove": self._handle_remove_pattern,
            "automation.permission_needed": self._handle_automation_permission_needed,
        }
        for event_type, handler in self._event_handler_map.items():
            self._event_bus.subscribe(event_type, handler)
        self._subscriptions = list(self._event_handler_map.keys())
        logger.info("Permission Manager started")

    async def stop(self) -> None:
        for event_type, handler in self._event_handler_map.items():
            self._event_bus.unsubscribe(event_type, handler)
        self._subscriptions.clear()
        logger.info("Permission Manager stopped")

    async def request(
        self,
        action: str,
        reasoning: str,
        benefits: list[str] | None = None,
        risks: list[str] | None = None,
        alternatives: list[str] | None = None,
        source_module: str = "unknown",
        resources: list[str] | None = None,
        request_id: str | None = None,
    ) -> PermissionRequest:
        req = PermissionRequest(
            action=action,
            reasoning=reasoning,
            benefits=benefits,
            risks=risks,
            alternatives=alternatives,
            source_module=source_module,
            resources=resources,
            request_id=request_id,
        )

        if self._matches_auto_approve(action):
            req.status = "approved"
            req.decided_at = datetime.now(timezone.utc).isoformat()
            self._history.append(req)
            self._prune_history()
            await self._event_bus.publish_event(
                source="permission_manager",
                event_type="permission.approved",
                payload={
                    "id": req.id,
                    "action": req.action,
                    "auto_approved": True,
                },
            )
            await self._event_bus.publish_event(
                source="permission_manager",
                event_type="permission.granted",
                payload={
                    "id": req.id,
                    "action": req.action,
                    "source_module": req.source_module,
                    "auto_approved": True,
                },
            )
            return req

        self._pending[req.id] = req
        await self._event_bus.publish_event(
            source="permission_manager",
            event_type="permission.requested",
            payload={
                "id": req.id,
                "action": req.action,
                "reasoning": req.reasoning,
                "benefits": req.benefits,
                "risks": req.risks,
                "alternatives": req.alternatives,
                "source_module": req.source_module,
                "resources": req.resources,
                "created_at": req.created_at,
            },
        )
        logger.info("Permission requested: %s (%s)", req.id, req.action)
        return req

    async def _handle_request(self, event: HelixEvent) -> None:
        await self.request(
            action=event.payload.get("action", ""),
            reasoning=event.payload.get("reasoning", ""),
            benefits=event.payload.get("benefits"),
            risks=event.payload.get("risks"),
            alternatives=event.payload.get("alternatives"),
            source_module=event.payload.get("source_module", "unknown"),
            resources=event.payload.get("resources"),
        )

    async def _handle_automation_permission_needed(self, event: HelixEvent) -> None:
        action = event.payload.get("action", "")
        permission_id = event.payload.get("permission_id", "")
        description = event.payload.get("description", "")
        await self.request(
            action=action,
            reasoning=description or f"Automation needs permission for: {action}",
            source_module="automation_engine",
            request_id=permission_id,
        )

    async def _handle_grant(self, event: HelixEvent) -> None:
        req_id = event.payload.get("id", "")
        req = self._pending.pop(req_id, None)
        if not req:
            logger.warning("Grant for unknown request: %s", req_id)
            return
        req.status = "approved"
        req.decided_at = datetime.now(timezone.utc).isoformat()
        self._history.append(req)
        self._prune_history()

        store_explainability = event.payload.get("store_explainability", True)
        if store_explainability:
            await self._event_bus.publish_event(
                source="permission_manager",
                event_type="memory.explain.log",
                payload={
                    "action": req.action,
                    "reasoning": req.reasoning,
                    "benefits": req.benefits,
                    "risks": req.risks,
                    "alternatives": req.alternatives,
                    "source_module": req.source_module,
                    "outcome": "approved",
                },
            )

        await self._event_bus.publish_event(
            source="permission_manager",
            event_type="permission.granted",
            payload={
                "id": req.id,
                "action": req.action,
                "source_module": req.source_module,
            },
        )
        logger.info("Permission granted: %s (%s)", req.id, req.action)

    async def _handle_deny(self, event: HelixEvent) -> None:
        req_id = event.payload.get("id", "")
        req = self._pending.pop(req_id, None)
        if not req:
            logger.warning("Deny for unknown request: %s", req_id)
            return
        req.status = "denied"
        req.decided_at = datetime.now(timezone.utc).isoformat()
        self._history.append(req)
        self._prune_history()

        await self._event_bus.publish_event(
            source="permission_manager",
            event_type="permission.denied",
            payload={
                "id": req.id,
                "action": req.action,
                "source_module": req.source_module,
            },
        )
        logger.info("Permission denied: %s (%s)", req.id, req.action)

    async def _handle_add_pattern(self, event: HelixEvent) -> None:
        pattern = event.payload.get("pattern", "")
        if pattern and pattern not in self._auto_approve_patterns:
            self._auto_approve_patterns.append(pattern)
            logger.info("Auto-approve pattern added: %s", pattern)

    async def _handle_remove_pattern(self, event: HelixEvent) -> None:
        pattern = event.payload.get("pattern", "")
        self._auto_approve_patterns = [p for p in self._auto_approve_patterns if p != pattern]
        logger.info("Auto-approve pattern removed: %s", pattern)

    def _matches_auto_approve(self, action: str) -> bool:
        act_lower = action.lower()
        for pattern in self._auto_approve_patterns:
            pat_lower = pattern.lower()
            if "*" in pat_lower:
                if fnmatch.fnmatchcase(act_lower, pat_lower):
                    return True
            elif pat_lower in act_lower:
                return True
        return False

    @property
    def pending_requests(self) -> list[PermissionRequest]:
        return list(self._pending.values())

    def _prune_history(self) -> None:
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    @property
    def history(self) -> list[PermissionRequest]:
        return list(self._history)

    @property
    def auto_approve_patterns(self) -> list[str]:
        return list(self._auto_approve_patterns)
