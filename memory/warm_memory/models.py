import uuid
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field


class WarmMemoryEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    category: str = "conversation"
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    score: float | None = None


class WarmIndexRequest(BaseModel):
    text: str
    category: str = "conversation"
    metadata: dict[str, Any] = Field(default_factory=dict)
    entry_id: str | None = None


class WarmSearchRequest(BaseModel):
    query: str
    limit: int = 5
    min_score: float = 0.3
    category: str | None = None


class WarmSearchResponse(BaseModel):
    query: str
    results: list[WarmMemoryEntry]
    count: int
    duration_ms: float
