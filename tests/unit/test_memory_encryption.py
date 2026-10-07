import pytest
from pathlib import Path
import json

from foundation.event_bus.event_bus import EventBus
from memory.conversation_memory.conversation_memory import ConversationMemory, ConversationEntry
from memory.preference_memory.preference_memory import PreferenceMemory, PreferenceEntry
from memory.work_memory.work_memory import WorkMemory, WorkSession
from memory.explainability_engine.explainability_engine import ExplainabilityEngine, ExplanationRecord
from foundation.storage_manager.crypto import _HEADER


@pytest.mark.asyncio
async def test_preference_memory_encryption_at_rest(tmp_path):
    event_bus = EventBus()
    pref_mem = PreferenceMemory(event_bus, storage_path=str(tmp_path))
    await pref_mem.start()

    entry = PreferenceEntry(key="user_theme", value="dark", category="settings")
    pref_mem._cache["user_theme"] = entry
    pref_mem._save_to_disk()

    file_path = tmp_path / "preferences.json"
    assert file_path.exists()

    raw_bytes = file_path.read_bytes()
    assert raw_bytes.startswith(_HEADER)
    # Ensure plaintext "user_theme" is not visible in raw file bytes
    assert b"user_theme" not in raw_bytes

    # Ensure in-memory load decodes properly
    new_pref_mem = PreferenceMemory(event_bus, storage_path=str(tmp_path))
    new_pref_mem._load_from_disk()
    assert "user_theme" in new_pref_mem._cache
    assert new_pref_mem._cache["user_theme"].value == "dark"


@pytest.mark.asyncio
async def test_work_memory_encryption_at_rest(tmp_path):
    event_bus = EventBus()
    work_mem = WorkMemory(event_bus, storage_path=str(tmp_path))
    await work_mem.start()

    session = WorkSession(session_id="s1", active_project="Secret Project X")
    work_mem._sessions["s1"] = session
    work_mem._save_to_disk()

    file_path = tmp_path / "work_sessions.json"
    assert file_path.exists()

    raw_bytes = file_path.read_bytes()
    assert raw_bytes.startswith(_HEADER)
    assert b"Secret Project X" not in raw_bytes

    new_work_mem = WorkMemory(event_bus, storage_path=str(tmp_path))
    new_work_mem._load_from_disk()
    assert "s1" in new_work_mem._sessions
    assert new_work_mem._sessions["s1"].active_project == "Secret Project X"


@pytest.mark.asyncio
async def test_conversation_memory_encryption_at_rest(tmp_path):
    event_bus = EventBus()
    conv_mem = ConversationMemory(event_bus, storage_path=str(tmp_path))
    await conv_mem.start()

    entry = ConversationEntry(session_id="sess_123", role="user", content="Top secret conversation detail")
    await conv_mem._store_entry(entry)

    conversations_dir = tmp_path / "conversations"
    files = list(conversations_dir.glob("sess_123_*.jsonl"))
    assert len(files) == 1

    file_bytes = files[0].read_bytes()
    assert file_bytes.startswith(_HEADER)
    assert b"Top secret conversation detail" not in file_bytes

    history = await conv_mem.get_session_history("sess_123")
    assert len(history) == 1
    assert history[0].content == "Top secret conversation detail"


@pytest.mark.asyncio
async def test_explainability_engine_encryption_at_rest(tmp_path):
    event_bus = EventBus()
    expl = ExplainabilityEngine(event_bus, storage_path=str(tmp_path))
    await expl.start()

    record = ExplanationRecord(action="launch_app", reasoning="User requested launch of confidential file")
    expl._append_to_log(record)

    file_path = tmp_path / "explanations.jsonl"
    assert file_path.exists()

    raw_bytes = file_path.read_bytes()
    assert raw_bytes.startswith(_HEADER)
    assert b"confidential file" not in raw_bytes

    retrieved = expl.find_by_id(record.decision_id)
    assert retrieved is not None
    assert retrieved.action == "launch_app"
