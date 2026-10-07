import os
import sqlite3
import tempfile
import pytest
from pathlib import Path

from foundation.event_bus.event_bus import EventBus
from context.file_intelligence_engine.file_intelligence_engine import FileIntelligenceEngine
from context.browser_engine.browser_engine import BrowserEngine


@pytest.mark.asyncio
async def test_file_intelligence_allowlist_sandboxing(tmp_path):
    event_bus = EventBus()
    engine = FileIntelligenceEngine(event_bus)
    await engine.start()

    # 1. Allowed path (current working directory)
    allowed_info = engine._get_file_info(os.getcwd())
    assert allowed_info.get("exists") is True
    assert allowed_info.get("denied") is not True

    # 2. Denied path outside allowlist
    system_path = "C:\\Windows" if os.name == "nt" else "/etc"
    denied_info = engine._get_file_info(system_path)
    assert denied_info.get("exists") is False
    assert denied_info.get("denied") is True

    denied_list = engine._list_directory(system_path, max_depth=1)
    assert denied_list == []

    denied_recent = engine._get_recent_files(system_path, minutes=30)
    assert denied_recent == []

    denied_project = engine._detect_project_type(system_path)
    assert denied_project.get("denied") is True
    await engine.stop()


@pytest.mark.asyncio
async def test_browser_engine_history_temp_cleanup(tmp_path):
    event_bus = EventBus()
    engine = BrowserEngine(event_bus)
    await engine.start()

    # Create dummy Chromium history SQLite DB
    history_db_path = tmp_path / "History"
    conn = sqlite3.connect(history_db_path)
    conn.execute(
        "CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT, visit_count INTEGER, last_visit_time INTEGER)"
    )
    for i in range(60):  # Insert 60 rows
        conn.execute(
            "INSERT INTO urls (url, title, visit_count, last_visit_time) VALUES (?, ?, ?, ?)",
            (f"https://example.com/{i}", f"Page {i}", i + 1, 1000 + i),
        )
    conn.commit()
    conn.close()

    # Track temporary files in tempdir before and after
    temp_dir = Path(tempfile.gettempdir())
    files_before = set(temp_dir.glob("*.sqlite"))

    # Read history via engine (request 100 entries, should be capped to 50)
    entries = engine._read_history_db(history_db_path, limit=100)

    # 1. Check cap enforcement (max 50)
    assert len(entries) <= 50

    # 2. Verify temp SQLite file was deleted post-read
    files_after = set(temp_dir.glob("*.sqlite"))
    new_temp_files = files_after - files_before
    assert len(new_temp_files) == 0, f"Temporary SQLite files were not deleted: {new_temp_files}"

    await engine.stop()
