import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from foundation.event_bus.event_bus import EventBus, HelixEvent


class PreferenceEntry(BaseModel):
    key: str
    value: Any
    category: str = "general"
    source: str = "user"


class PreferenceMemory:
    def __init__(self, event_bus: EventBus, storage_path: str | None = None):
        self._event_bus = event_bus
        self._storage_path = Path(storage_path or os.getenv(
            "HELIX_MEMORY_PATH",
            str(Path.cwd() / "data" / "memory"),
        ))
        self._preferences_path = self._storage_path / "preferences.json"
        self._cache: dict[str, PreferenceEntry] = {}
        self._dirty = False
        self._subscriptions: list[str] = []

    async def start(self) -> None:
        self._load_from_disk()
        self._event_bus.subscribe("memory.preference.store", self._handle_store)
        self._event_bus.subscribe("memory.preference.get", self._handle_get)
        self._event_bus.subscribe("memory.preference.get_all", self._handle_get_all)
        self._event_bus.subscribe("memory.preference.delete", self._handle_delete)
        self._subscriptions = ["memory.preference.store", "memory.preference.get",
                               "memory.preference.get_all", "memory.preference.delete"]

    async def stop(self) -> None:
        if self._dirty:
            self._save_to_disk()
        self._subscriptions.clear()

    def _load_from_disk(self) -> None:
        if self._preferences_path.exists():
            try:
                with open(self._preferences_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not isinstance(data, list):
                        self._cache = {}
                        return
                    for entry_data in data:
                        if not isinstance(entry_data, dict):
                            continue
                        entry = PreferenceEntry(**entry_data)
                        self._cache[entry.key] = entry
            except (json.JSONDecodeError, ValueError, TypeError):
                self._cache = {}

    def _save_to_disk(self) -> None:
        self._preferences_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._preferences_path, "w", encoding="utf-8") as f:
            json.dump([e.model_dump() for e in self._cache.values()], f, indent=2)
        self._dirty = False

    async def _handle_store(self, event: HelixEvent) -> None:
        entry = PreferenceEntry(
            key=event.payload.get("key", ""),
            value=event.payload.get("value"),
            category=event.payload.get("category", "general"),
            source=event.payload.get("source", "inferred"),
        )
        if not entry.key:
            return
        self._cache[entry.key] = entry
        self._dirty = True
        await self._event_bus.publish_event(
            source="preference_memory",
            event_type="memory.preference.stored",
            payload={"key": entry.key, "category": entry.category},
            correlation_id=event.correlation_id,
        )

    async def _handle_get(self, event: HelixEvent) -> None:
        key = event.payload.get("key", "")
        entry = self._cache.get(key)
        await self._event_bus.publish_event(
            source="preference_memory",
            event_type="memory.preference.retrieved",
            payload={"key": key, "entry": entry.model_dump() if entry else None},
            correlation_id=event.correlation_id,
        )

    async def _handle_get_all(self, event: HelixEvent) -> None:
        category = event.payload.get("category", None)
        if category:
            entries = [e for e in self._cache.values() if e.category == category]
        else:
            entries = list(self._cache.values())
        await self._event_bus.publish_event(
            source="preference_memory",
            event_type="memory.preference.all_retrieved",
            payload={"category": category, "entries": [e.model_dump() for e in entries]},
            correlation_id=event.correlation_id,
        )

    async def _handle_delete(self, event: HelixEvent) -> None:
        key = event.payload.get("key", "")
        self._cache.pop(key, None)
        self._dirty = True
        await self._event_bus.publish_event(
            source="preference_memory",
            event_type="memory.preference.deleted",
            payload={"key": key},
            correlation_id=event.correlation_id,
        )

    def get(self, key: str) -> PreferenceEntry | None:
        return self._cache.get(key)

    def get_all(self, category: str | None = None) -> list[PreferenceEntry]:
        if category:
            return [e for e in self._cache.values() if e.category == category]
        return list(self._cache.values())
