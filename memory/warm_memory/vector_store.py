import abc
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Sequence
import numpy as np

from memory.warm_memory.models import WarmMemoryEntry

logger = logging.getLogger("helix.memory.vector_store")

COLLECTION_NAME = "helix_warm_memory"


class BaseVectorStore(abc.ABC):
    """Abstract interface for vector database backends."""

    @abc.abstractmethod
    async def upsert(self, entries: Sequence[WarmMemoryEntry], vectors: Sequence[Sequence[float]]) -> None:
        """Insert or update entries with their vector representations."""
        pass

    @abc.abstractmethod
    async def search(
        self,
        query_vector: Sequence[float],
        limit: int = 5,
        min_score: float = 0.0,
        category: str | None = None,
    ) -> list[WarmMemoryEntry]:
        """Perform cosine similarity search."""
        pass

    @abc.abstractmethod
    async def delete(self, entry_id: str) -> bool:
        """Delete an entry by ID."""
        pass

    @abc.abstractmethod
    async def count(self) -> int:
        """Return total number of vectors in the store."""
        pass

    @abc.abstractmethod
    async def clear(self) -> None:
        """Clear all entries."""
        pass

    @abc.abstractmethod
    async def close(self) -> None:
        """Close database connections and release resources."""
        pass


class QdrantVectorStore(BaseVectorStore):
    """Qdrant vector store adapter supporting both remote Docker and embedded local disk mode.
    
    Per ADR-019 and Hardware Storage Rules:
    - Embedded mode persists to Laptop SSD (HELIX_MEMORY_PATH/qdrant).
    - Can connect to Docker Qdrant at http://127.0.0.1:6333 when running.
    """

    def __init__(
        self,
        collection_name: str = COLLECTION_NAME,
        dimension: int = 384,
        url: str | None = None,
        path: Path | str | None = None,
    ):
        self._collection_name = collection_name
        self._dimension = dimension
        self._url = url
        self._path = Path(path) if path and path != ":memory:" else path
        self._client = None
        self._init_client()

    def _init_client(self) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        if self._url:
            try:
                self._client = QdrantClient(url=self._url, timeout=5.0)
                # Test connectivity
                self._client.get_collections()
                logger.info("Connected to remote Qdrant at %s", self._url)
            except Exception as e:
                logger.warning("Failed to connect to remote Qdrant at %s: %s. Falling back to local storage.", self._url, e)
                self._client = None

        if self._client is None:
            if self._path == ":memory:":
                self._client = QdrantClient(":memory:")
                logger.info("Initialized in-memory Qdrant instance")
            else:
                local_dir = Path(self._path or (Path.cwd() / "data" / "memory" / "qdrant"))
                local_dir.mkdir(parents=True, exist_ok=True)
                self._client = QdrantClient(path=str(local_dir))
                logger.info("Initialized local disk Qdrant instance at %s", local_dir)

        # Ensure collection exists
        collections = [c.name for c in self._client.get_collections().collections]
        if self._collection_name not in collections:
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(size=self._dimension, distance=Distance.COSINE),
            )
            logger.info("Created Qdrant collection: %s (dim=%d, metric=COSINE)", self._collection_name, self._dimension)

    async def upsert(self, entries: Sequence[WarmMemoryEntry], vectors: Sequence[Sequence[float]]) -> None:
        if not entries:
            return
        from qdrant_client.models import PointStruct

        points = []
        for entry, vec in zip(entries, vectors):
            # Ensure valid UUID or string
            point_id = entry.id
            payload = {
                "text": entry.text,
                "category": entry.category,
                "metadata": entry.metadata,
                "timestamp": entry.timestamp,
            }
            points.append(PointStruct(id=point_id, vector=list(vec), payload=payload))

        self._client.upsert(collection_name=self._collection_name, points=points)

    async def search(
        self,
        query_vector: Sequence[float],
        limit: int = 5,
        min_score: float = 0.0,
        category: str | None = None,
    ) -> list[WarmMemoryEntry]:
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        query_filter = None
        if category:
            query_filter = Filter(must=[FieldCondition(key="category", match=MatchValue(value=category))])

        results = self._client.query_points(
            collection_name=self._collection_name,
            query=list(query_vector),
            query_filter=query_filter,
            limit=limit,
            score_threshold=min_score if min_score > 0 else None,
        ).points

        matched: list[WarmMemoryEntry] = []
        for r in results:
            payload = r.payload or {}
            entry = WarmMemoryEntry(
                id=str(r.id),
                text=payload.get("text", ""),
                category=payload.get("category", "conversation"),
                metadata=payload.get("metadata", {}),
                timestamp=payload.get("timestamp", ""),
                score=float(r.score) if r.score is not None else None,
            )
            matched.append(entry)
        return matched

    async def delete(self, entry_id: str) -> bool:
        from qdrant_client.models import PointIdsList
        res = self._client.delete(
            collection_name=self._collection_name,
            points_selector=PointIdsList(points=[entry_id]),
        )
        return res.status == "completed"

    async def count(self) -> int:
        return self._client.count(collection_name=self._collection_name).count

    async def clear(self) -> None:
        self._client.delete_collection(collection_name=self._collection_name)
        from qdrant_client.models import Distance, VectorParams
        self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config=VectorParams(size=self._dimension, distance=Distance.COSINE),
        )

    async def close(self) -> None:
        if self._client:
            self._client.close()


class InMemoryVectorStore(BaseVectorStore):
    """Pure NumPy in-memory vector store for testing and fallback."""

    def __init__(self, dimension: int = 384):
        self._dimension = dimension
        self._ids: list[str] = []
        self._entries: dict[str, WarmMemoryEntry] = {}
        self._vectors: list[np.ndarray] = []

    async def upsert(self, entries: Sequence[WarmMemoryEntry], vectors: Sequence[Sequence[float]]) -> None:
        for entry, vec in zip(entries, vectors):
            v = np.array(vec, dtype=np.float32)
            norm = np.linalg.norm(v)
            if norm > 1e-12:
                v = v / norm

            if entry.id in self._entries:
                idx = self._ids.index(entry.id)
                self._vectors[idx] = v
                self._entries[entry.id] = entry
            else:
                self._ids.append(entry.id)
                self._vectors.append(v)
                self._entries[entry.id] = entry

    async def search(
        self,
        query_vector: Sequence[float],
        limit: int = 5,
        min_score: float = 0.0,
        category: str | None = None,
    ) -> list[WarmMemoryEntry]:
        if not self._ids:
            return []

        q = np.array(query_vector, dtype=np.float32)
        norm = np.linalg.norm(q)
        if norm > 1e-12:
            q = q / norm

        matrix = np.stack(self._vectors, axis=0)  # shape (N, D)
        scores = np.dot(matrix, q)  # cosine similarity

        candidates = []
        for i, score in enumerate(scores):
            entry_id = self._ids[i]
            entry = self._entries[entry_id]
            if category and entry.category != category:
                continue
            if score >= min_score:
                entry_copy = entry.model_copy()
                entry_copy.score = float(score)
                candidates.append(entry_copy)

        candidates.sort(key=lambda x: (x.score or 0.0), reverse=True)
        return candidates[:limit]

    async def delete(self, entry_id: str) -> bool:
        if entry_id in self._entries:
            idx = self._ids.index(entry_id)
            self._ids.pop(idx)
            self._vectors.pop(idx)
            del self._entries[entry_id]
            return True
        return False

    async def count(self) -> int:
        return len(self._ids)

    async def clear(self) -> None:
        self._ids.clear()
        self._vectors.clear()
        self._entries.clear()

    async def close(self) -> None:
        await self.clear()


def create_vector_store(
    backend: str = "auto",
    storage_path: Path | str | None = None,
    url: str | None = None,
    dimension: int = 384,
) -> BaseVectorStore:
    """Factory creating appropriate vector database backend."""
    target_backend = (backend or os.getenv("HELIX_VECTOR_BACKEND", "auto")).lower()
    target_url = url or os.getenv("HELIX_QDRANT_URL", None)
    target_path = storage_path or os.getenv("HELIX_QDRANT_PATH", None)

    if target_backend == "memory":
        return InMemoryVectorStore(dimension=dimension)

    if target_backend in ("qdrant", "auto"):
        try:
            return QdrantVectorStore(
                dimension=dimension,
                url=target_url,
                path=target_path,
            )
        except Exception as e:
            logger.warning("Could not initialize Qdrant vector store (%s), falling back to InMemoryVectorStore", e)
            return InMemoryVectorStore(dimension=dimension)

    return InMemoryVectorStore(dimension=dimension)
