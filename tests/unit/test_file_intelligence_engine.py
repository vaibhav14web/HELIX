import os
import tempfile
import pytest

from foundation.event_bus.event_bus import EventBus, HelixEvent
from context.file_intelligence_engine.file_intelligence_engine import FileIntelligenceEngine


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def engine(event_bus):
    return FileIntelligenceEngine(event_bus)


@pytest.fixture
def sample_project(tmp_path):
    """Create a minimal project structure for testing."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')")
    (tmp_path / "src" / "utils.py").write_text("# utils")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("# tests")
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "README.md").write_text("# readme")
    (tmp_path / ".git").mkdir()  # marker
    (tmp_path / "node_modules").mkdir()  # should be ignored
    (tmp_path / "node_modules" / "dep.js").write_text("// dep")
    return tmp_path


@pytest.mark.asyncio
async def test_start_registers_subscriptions(engine):
    await engine.start()
    assert "context.file.request" in engine._subscriptions
    assert "context.file.list" in engine._subscriptions
    assert "context.file.recent" in engine._subscriptions
    assert "context.file.detect_project" in engine._subscriptions
    await engine.stop()


@pytest.mark.asyncio
async def test_stop_clears_subscriptions(engine):
    await engine.start()
    await engine.stop()
    assert len(engine._subscriptions) == 0


@pytest.mark.asyncio
async def test_file_request_existing_file(engine, sample_project):
    await engine.start()
    received = []

    async def capture(event):
        received.append(event)

    engine._event_bus.subscribe("context.file.provided", capture)
    path = str(sample_project / "README.md")
    await engine._handle_request(
        HelixEvent(
            source="test",
            event_type="context.file.request",
            payload={"path": path},
            correlation_id="corr-file-1",
        )
    )
    assert len(received) == 1
    info = received[0].payload["info"]
    assert info["exists"] is True
    assert info["is_file"] is True
    assert info["extension"] == ".md"
    await engine.stop()


@pytest.mark.asyncio
async def test_file_request_missing_file(engine, tmp_path):
    await engine.start()
    received = []

    async def capture(event):
        received.append(event)

    engine._event_bus.subscribe("context.file.provided", capture)
    await engine._handle_request(
        HelixEvent(
            source="test",
            event_type="context.file.request",
            payload={"path": str(tmp_path / "nonexistent.py")},
            correlation_id="corr-file-2",
        )
    )
    assert len(received) == 1
    assert received[0].payload["info"]["exists"] is False
    await engine.stop()


@pytest.mark.asyncio
async def test_list_directory(engine, sample_project):
    await engine.start()
    received = []

    async def capture(event):
        received.append(event)

    engine._event_bus.subscribe("context.file.listed", capture)
    await engine._handle_list(
        HelixEvent(
            source="test",
            event_type="context.file.list",
            payload={"path": str(sample_project), "max_depth": 2},
            correlation_id="corr-list-1",
        )
    )
    assert len(received) == 1
    listing = received[0].payload["listing"]
    paths = [e["path"] for e in listing]
    # node_modules should be excluded
    assert not any("node_modules" in p for p in paths)
    # .git should be excluded
    assert not any(p == ".git" for p in paths)
    # src directory and its files should be present
    assert any("src" in p for p in paths)
    await engine.stop()


@pytest.mark.asyncio
async def test_detect_project_type(engine, sample_project):
    await engine.start()
    received = []

    async def capture(event):
        received.append(event)

    engine._event_bus.subscribe("context.file.project_detected", capture)
    await engine._handle_detect_project(
        HelixEvent(
            source="test",
            event_type="context.file.detect_project",
            payload={"path": str(sample_project)},
            correlation_id="corr-detect-1",
        )
    )
    assert len(received) == 1
    assert "node" in received[0].payload["project_types"]
    assert "package.json" in received[0].payload["markers_found"]
    await engine.stop()


@pytest.mark.asyncio
async def test_recent_files(engine, sample_project):
    await engine.start()
    received = []

    async def capture(event):
        received.append(event)

    engine._event_bus.subscribe("context.file.recent.provided", capture)
    await engine._handle_recent(
        HelixEvent(
            source="test",
            event_type="context.file.recent",
            payload={"path": str(sample_project), "minutes": 60},
            correlation_id="corr-recent-1",
        )
    )
    assert len(received) == 1
    # All files were just created, so they should be recent
    assert received[0].payload["count"] > 0
    await engine.stop()
