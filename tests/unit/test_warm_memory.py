import asyncio
import json
import numpy as np
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from foundation.event_bus.event_bus import EventBus, HelixEvent
from memory.warm_memory.models import WarmMemoryEntry
from memory.warm_memory.embedding_engine import EmbeddingEngine
from memory.warm_memory.vector_store import (
    InMemoryVectorStore,
    QdrantVectorStore,
    create_vector_store,
)
from memory.warm_memory.warm_memory import WarmMemory
from core_ai.conversation_engine.conversation_engine import ConversationEngine


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def embedding_engine():
    engine = EmbeddingEngine()
    engine.initialize()
    return engine


class TestEmbeddingEngine:
    def test_dimensions_and_normalization(self, embedding_engine):
        vec = embedding_engine.embed_query("HELIX personal AI operating system")
        assert len(vec) == 384
        norm = np.linalg.norm(np.array(vec, dtype=np.float32))
        assert pytest.approx(norm, rel=1e-3) == 1.0

    def test_semantic_similarity(self, embedding_engine):
        v_code1 = np.array(embedding_engine.embed_query("write python async code"), dtype=np.float32)
        v_code2 = np.array(embedding_engine.embed_query("python programming functions"), dtype=np.float32)
        v_food = np.array(embedding_engine.embed_query("strawberry chocolate gelato dessert"), dtype=np.float32)

        sim_code = float(np.dot(v_code1, v_code2))
        sim_food = float(np.dot(v_code1, v_food))

        assert sim_code > sim_food


class TestVectorStores:
    @pytest.mark.asyncio
    async def test_in_memory_store(self, embedding_engine):
        store = InMemoryVectorStore(dimension=384)
        e1 = WarmMemoryEntry(id="1", text="FastAPI backend on port 8000", category="project")
        e2 = WarmMemoryEntry(id="2", text="Next.js frontend user interface", category="ui")

        v1 = embedding_engine.embed_query(e1.text)
        v2 = embedding_engine.embed_query(e2.text)

        await store.upsert([e1, e2], [v1, v2])
        assert await store.count() == 2

        # Search
        q_vec = embedding_engine.embed_query("FastAPI server endpoints")
        results = await store.search(q_vec, limit=2)
        assert len(results) > 0
        assert results[0].id == "1"

        # Category filter
        filtered = await store.search(q_vec, limit=2, category="ui")
        assert len(filtered) == 1
        assert filtered[0].id == "2"

        # Delete
        deleted = await store.delete("1")
        assert deleted is True
        assert await store.count() == 1

        await store.close()

    @pytest.mark.asyncio
    async def test_qdrant_vector_store_in_memory(self, embedding_engine):
        store = QdrantVectorStore(collection_name="test_helix", dimension=384, path=":memory:")
        e1 = WarmMemoryEntry(id="11111111-1111-1111-1111-111111111111", text="Machine learning model on RTX 3050", category="hardware")
        e2 = WarmMemoryEntry(id="22222222-2222-2222-2222-222222222222", text="Windows 11 desktop audio listener", category="voice")

        v1 = embedding_engine.embed_query(e1.text)
        v2 = embedding_engine.embed_query(e2.text)

        await store.upsert([e1, e2], [v1, v2])
        assert await store.count() == 2

        # Query
        q_vec = embedding_engine.embed_query("NVIDIA GPU architecture")
        results = await store.search(q_vec, limit=1)
        assert len(results) == 1
        assert results[0].id == "11111111-1111-1111-1111-111111111111"

        # Delete
        assert await store.delete("11111111-1111-1111-1111-111111111111") is True
        assert await store.count() == 1

        await store.close()


class TestWarmMemoryEngine:
    @pytest.mark.asyncio
    async def test_warm_memory_crud_and_events(self, event_bus, tmp_path):
        store = InMemoryVectorStore(dimension=384)
        engine = WarmMemory(event_bus=event_bus, vector_store=store, storage_path=tmp_path)
        await engine.start()

        # Direct index and search
        await engine.index_text(
            text="User prefers dark theme and Neovim editor",
            category="preference",
            metadata={"source": "user_settings"},
        )
        await engine.index_text(
            text="Docker compose orchestrates Qdrant and PostgreSQL",
            category="infrastructure",
        )

        results = await engine.search("What editor and UI theme does the user like?", limit=2)
        assert len(results) > 0
        assert "dark theme" in results[0].text

        # EventBus search integration
        searched_future = asyncio.get_running_loop().create_future()

        async def _on_searched(event: HelixEvent):
            searched_future.set_result(event.payload)

        event_bus.subscribe("memory.warm.searched", _on_searched)

        await event_bus.publish_event(
            source="test",
            event_type="memory.warm.search",
            payload={"query": "Docker database services", "limit": 2},
            correlation_id="test-corr-1",
        )

        payload = await asyncio.wait_for(searched_future, timeout=2.0)
        assert payload["count"] > 0
        assert "Docker" in payload["results"][0]["text"]

        stats = await engine.get_stats()
        assert stats["vector_count"] == 2
        assert stats["tier"] == "warm_memory"

        await engine.stop()

    @pytest.mark.asyncio
    async def test_rollover_conversations(self, event_bus, tmp_path):
        conv_dir = tmp_path / "conversations"
        conv_dir.mkdir(parents=True)

        # 15 days ago (in warm 8-30d retention window)
        fifteen_days_ago = datetime.now(timezone.utc) - timedelta(days=15)
        date_str = fifteen_days_ago.strftime("%Y-%m-%d")
        file_path = conv_dir / f"sess1_{date_str}.jsonl"

        entry_data = {
            "timestamp": fifteen_days_ago.isoformat(),
            "session_id": "sess1",
            "role": "user",
            "content": "Remember to deploy the vector database before launch",
        }
        file_path.write_text(json.dumps(entry_data) + "\n", encoding="utf-8")

        store = InMemoryVectorStore(dimension=384)
        warm_mem = WarmMemory(event_bus=event_bus, vector_store=store, storage_path=tmp_path)
        await warm_mem.start()

        indexed_count = await warm_mem.rollover_conversations(conversation_dir=conv_dir)
        assert indexed_count == 1

        # Search the rolled-over memory
        hits = await warm_mem.search("vector database launch", limit=1)
        assert len(hits) == 1
        assert "vector database" in hits[0].text

        await warm_mem.stop()


class TestConversationRAGIntegration:
    @pytest.mark.asyncio
    async def test_rag_injection_in_conversation_engine(self, event_bus, tmp_path):
        store = InMemoryVectorStore(dimension=384)
        warm_mem = WarmMemory(event_bus=event_bus, vector_store=store, storage_path=tmp_path)
        await warm_mem.start()

        # Seed warm memory with critical domain knowledge
        await warm_mem.index_text(
            text="The project code name is HELIX and requires Python 3.12 with FastAPI",
            category="project_knowledge",
        )

        conv_engine = ConversationEngine(event_bus=event_bus)
        await conv_engine.start()

        # Intercept llm.generate to inspect prompt and messages
        captured_payload = {}
        llm_generate_received = asyncio.get_running_loop().create_future()

        async def _on_llm_generate(event: HelixEvent):
            captured_payload.update(event.payload)
            llm_generate_received.set_result(True)
            # Emit mock completion
            await event_bus.publish_event(
                source="llm_engine",
                event_type="llm.generation.complete",
                payload={"response": "Understood."},
                correlation_id=event.correlation_id,
            )

        event_bus.subscribe("llm.generate", _on_llm_generate)

        # Send user query that triggers semantic match
        chat_task = asyncio.create_task(conv_engine.chat("Tell me about the project language and framework"))
        await asyncio.wait_for(llm_generate_received, timeout=3.0)
        await chat_task

        prompt = captured_payload.get("prompt", "")
        messages = captured_payload.get("messages", [])

        # Verify that RAG context was injected
        assert "<|context:retrieved_memories|>" in prompt
        assert "HELIX and requires Python 3.12" in prompt

        # Verify messages system content contains knowledge
        system_content = messages[0]["content"]
        assert "Retrieved Relevant Knowledge & Memories:" in system_content
        assert "HELIX and requires Python 3.12" in system_content

        await conv_engine.stop()
        await warm_mem.stop()


class TestWarmMemoryApi:
    @pytest.mark.asyncio
    async def test_api_endpoints(self, event_bus, tmp_path):
        import api.main as main_mod
        from fastapi.testclient import TestClient

        store = InMemoryVectorStore(dimension=384)
        warm_engine = WarmMemory(event_bus=event_bus, vector_store=store, storage_path=tmp_path)
        await warm_engine.start()
        main_mod.warm_mem = warm_engine

        try:
            client = TestClient(main_mod.app)
            # Stats endpoint
            res_stats = client.get("/memory/warm/stats")
            assert res_stats.status_code == 200
            assert res_stats.json()["tier"] == "warm_memory"

            # Index endpoint
            res_idx = client.post("/memory/warm/index", json={
                "text": "Antigravity IDE integrates with local AI models",
                "category": "tooling",
                "metadata": {"env": "windows"},
            })
            assert res_idx.status_code == 200
            entry_id = res_idx.json()["id"]
            assert entry_id is not None

            # Search endpoint
            res_search = client.post("/memory/warm/search", json={
                "query": "local AI model integration",
                "limit": 2,
            })
            assert res_search.status_code == 200
            search_data = res_search.json()
            assert search_data["count"] >= 1
            assert "Antigravity IDE" in search_data["results"][0]["text"]

            # Delete endpoint
            res_del = client.delete(f"/memory/warm/{entry_id}")
            assert res_del.status_code == 200
            assert res_del.json()["deleted"] is True
        finally:
            await warm_engine.stop()
            main_mod.warm_mem = None

