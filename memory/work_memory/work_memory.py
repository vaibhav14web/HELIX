import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from foundation.event_bus.event_bus import EventBus, HelixEvent


from foundation.storage_manager.crypto import encrypt_string, decrypt_string


class WorkSession(BaseModel):
    session_id: str
    active_project: str | None = None
    open_tasks: list[str] = Field(default_factory=list)
    current_context: dict[str, Any] = Field(default_factory=dict)
    started_at: str = ""
    last_updated: str = ""


class WorkMemory:
    def __init__(self, event_bus: EventBus, storage_path: str | None = None):
        self._event_bus = event_bus
        self._storage_path = Path(storage_path or os.getenv(
            "HELIX_MEMORY_PATH",
            str(Path.cwd() / "data" / "memory"),
        ))
        self._work_path = self._storage_path / "work_sessions.json"
        self._active_session: WorkSession | None = None
        self._sessions: dict[str, WorkSession] = {}
        self._max_sessions = int(os.getenv("HELIX_WORK_MAX_SESSIONS", "50"))
        self._dirty = False
        self._subscriptions: list[str] = []

    async def start(self) -> None:
        self._load_from_disk()
        self._event_bus.subscribe("memory.work.set_project", self._handle_set_project)
        self._event_bus.subscribe("memory.work.add_task", self._handle_add_task)
        self._event_bus.subscribe("memory.work.get_context", self._handle_get_context)
        self._event_bus.subscribe("memory.work.update_context", self._handle_update_context)
        self._event_bus.subscribe("session.start", self._handle_session_start)
        self._event_bus.subscribe("session.end", self._handle_session_end)
        self._subscriptions = [
            "memory.work.set_project", "memory.work.add_task",
            "memory.work.get_context", "memory.work.update_context",
            "session.start", "session.end",
        ]

    async def stop(self) -> None:
        if self._dirty:
            self._save_to_disk()
        self._subscriptions.clear()

    def _load_from_disk(self) -> None:
        if self._work_path.exists():
            try:
                raw_bytes = self._work_path.read_bytes()
                decompressed = decrypt_string(raw_bytes)
                data = json.loads(decompressed)
                if not isinstance(data, list):
                    self._sessions = {}
                    return
                for s in data:
                    if not isinstance(s, dict):
                        continue
                    session = WorkSession(**s)
                    self._sessions[session.session_id] = session
            except (json.JSONDecodeError, ValueError, TypeError, Exception):
                self._sessions = {}

    def _save_to_disk(self) -> None:
        self._work_path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps([s.model_dump() for s in self._sessions.values()], indent=2)
        encrypted = encrypt_string(content)
        self._work_path.write_bytes(encrypted)
        self._dirty = False

    async def _handle_session_start(self, event: HelixEvent) -> None:
        session_id = event.payload.get("session_id", "")
        if not session_id:
            return
        if session_id in self._sessions:
            self._active_session = self._sessions[session_id]
        else:
            self._active_session = WorkSession(
                session_id=session_id,
                started_at=datetime.now(timezone.utc).isoformat(),
                last_updated=datetime.now(timezone.utc).isoformat(),
            )
            self._sessions[session_id] = self._active_session
            self._dirty = True
            self._prune_sessions()

    async def _handle_session_end(self, event: HelixEvent) -> None:
        self._active_session = None

    async def _handle_set_project(self, event: HelixEvent) -> None:
        if not self._active_session:
            return
        self._active_session.active_project = event.payload.get("project", "")
        self._active_session.last_updated = datetime.now(timezone.utc).isoformat()
        self._dirty = True
        await self._event_bus.publish_event(
            source="work_memory",
            event_type="memory.work.project_set",
            payload={"session_id": self._active_session.session_id, "project": self._active_session.active_project},
            correlation_id=event.correlation_id,
        )

    async def _handle_add_task(self, event: HelixEvent) -> None:
        if not self._active_session:
            return
        task = event.payload.get("task", "")
        if task:
            self._active_session.open_tasks.append(task)
            self._active_session.last_updated = datetime.now(timezone.utc).isoformat()
            self._dirty = True

    async def _handle_get_context(self, event: HelixEvent) -> None:
        if not self._active_session:
            await self._event_bus.publish_event(
                source="work_memory",
                event_type="memory.work.context_retrieved",
                payload={"context": None},
                correlation_id=event.correlation_id,
            )
            return
        await self._event_bus.publish_event(
            source="work_memory",
            event_type="memory.work.context_retrieved",
            payload={"context": self._active_session.model_dump()},
            correlation_id=event.correlation_id,
        )

    async def _handle_update_context(self, event: HelixEvent) -> None:
        if not self._active_session:
            return
        updates = event.payload.get("updates", {})
        self._active_session.current_context.update(updates)
        self._active_session.last_updated = datetime.now(timezone.utc).isoformat()
        self._dirty = True

    def _prune_sessions(self) -> None:
        if len(self._sessions) > self._max_sessions:
            sorted_ids = sorted(
                self._sessions.keys(),
                key=lambda sid: self._sessions[sid].last_updated or "",
            )
            for sid in sorted_ids[:len(sorted_ids) - self._max_sessions]:
                del self._sessions[sid]
            self._dirty = True

    def get_active_session(self) -> WorkSession | None:
        return self._active_session

    def get_session(self, session_id: str) -> WorkSession | None:
        return self._sessions.get(session_id)
