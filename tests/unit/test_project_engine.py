import os
import json
import pytest

from foundation.event_bus.event_bus import EventBus, HelixEvent
from context.project_engine.project_engine import ProjectEngine


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def engine(event_bus, tmp_path):
    os.environ["HELIX_PROJECT_PATH"] = str(tmp_path / "projects")
    return ProjectEngine(event_bus)


@pytest.fixture
def sample_workspace(tmp_path):
    """Create a sample workspace with project markers."""
    ws = tmp_path / "workspace" / "my-project"
    ws.mkdir(parents=True)
    (ws / ".git").mkdir()
    (ws / "pyproject.toml").write_text("[project]\nname='demo'\n")
    (ws / "src").mkdir()
    (ws / "src" / "main.py").write_text("print('hello')")
    return ws


@pytest.mark.asyncio
async def test_start_registers_subscriptions(engine):
    await engine.start()
    assert "project.create" in engine._subscriptions
    assert "project.open" in engine._subscriptions
    assert "project.close" in engine._subscriptions
    assert "project.list" in engine._subscriptions
    assert "project.detect" in engine._subscriptions
    assert "project.update_session" in engine._subscriptions
    await engine.stop()


@pytest.mark.asyncio
async def test_stop_clears_subscriptions(engine):
    await engine.start()
    await engine.stop()
    assert len(engine._subscriptions) == 0


@pytest.mark.asyncio
async def test_create_and_list(engine, sample_workspace):
    await engine.start()
    created = []
    listed = []

    async def capture_created(event):
        created.append(event)

    async def capture_listed(event):
        listed.append(event)

    engine._event_bus.subscribe("project.created", capture_created)
    engine._event_bus.subscribe("project.listed", capture_listed)

    await engine._handle_create(
        HelixEvent(
            source="test",
            event_type="project.create",
            payload={"name": "my-project", "path": str(sample_workspace)},
            correlation_id="corr-create-1",
        )
    )
    assert len(created) == 1
    assert created[0].payload["name"] == "my-project"

    await engine._handle_list(
        HelixEvent(
            source="test",
            event_type="project.list",
            payload={},
            correlation_id="corr-list-1",
        )
    )
    assert len(listed) == 1
    names = [p["name"] for p in listed[0].payload["projects"]]
    assert "my-project" in names
    await engine.stop()


@pytest.mark.asyncio
async def test_open_publishes_rich_payload(engine, sample_workspace):
    await engine.start()
    opened = []

    async def capture(event):
        opened.append(event)

    engine._event_bus.subscribe("project.opened", capture)

    await engine._handle_open(
        HelixEvent(
            source="test",
            event_type="project.open",
            payload={"name": "demo", "path": str(sample_workspace)},
            correlation_id="corr-open-1",
        )
    )
    assert len(opened) == 1
    payload = opened[0].payload
    assert payload["name"] == "demo"
    assert payload["project_type"] == "python"
    assert "session" in payload
    await engine.stop()


@pytest.mark.asyncio
async def test_project_switch_detection(engine, sample_workspace, tmp_path):
    await engine.start()
    switched = []

    async def capture(event):
        switched.append(event)

    engine._event_bus.subscribe("project.switched", capture)

    # Open first project
    await engine._handle_open(
        HelixEvent(
            source="test",
            event_type="project.open",
            payload={"name": "project-a", "path": str(sample_workspace)},
            correlation_id="corr-switch-1",
        )
    )
    assert len(switched) == 0  # no switch on first open

    # Open second project → should trigger switch
    ws2 = tmp_path / "workspace2"
    ws2.mkdir()
    (ws2 / "package.json").write_text("{}")
    await engine._handle_open(
        HelixEvent(
            source="test",
            event_type="project.open",
            payload={"name": "project-b", "path": str(ws2)},
            correlation_id="corr-switch-2",
        )
    )
    assert len(switched) == 1
    assert switched[0].payload["from"] == "project-a"
    assert switched[0].payload["to"] == "project-b"
    await engine.stop()


@pytest.mark.asyncio
async def test_detect_finds_project_root(engine, sample_workspace):
    await engine.start()
    detected = []

    async def capture(event):
        detected.append(event)

    engine._event_bus.subscribe("project.detected", capture)
    deep_file = str(sample_workspace / "src" / "main.py")
    await engine._handle_detect(
        HelixEvent(
            source="test",
            event_type="project.detect",
            payload={"path": deep_file},
            correlation_id="corr-detect-1",
        )
    )
    assert len(detected) == 1
    assert detected[0].payload["project_root"] == str(sample_workspace.resolve())
    assert detected[0].payload["project_type"] == "python"
    await engine.stop()


@pytest.mark.asyncio
async def test_close_clears_active(engine, sample_workspace):
    await engine.start()
    closed = []

    async def capture(event):
        closed.append(event)

    engine._event_bus.subscribe("project.closed", capture)

    # Open then close
    await engine._handle_open(
        HelixEvent(
            source="test",
            event_type="project.open",
            payload={"name": "demo", "path": str(sample_workspace)},
            correlation_id="corr-close-1",
        )
    )
    assert engine._active_project == "demo"
    await engine._handle_close(
        HelixEvent(
            source="test",
            event_type="project.close",
            payload={},
            correlation_id="corr-close-2",
        )
    )
    assert engine._active_project is None
    assert len(closed) == 1
    await engine.stop()


@pytest.mark.asyncio
async def test_session_update(engine, sample_workspace):
    await engine.start()
    await engine._handle_open(
        HelixEvent(
            source="test",
            event_type="project.open",
            payload={"name": "demo", "path": str(sample_workspace)},
            correlation_id="corr-session-1",
        )
    )
    await engine._handle_update_session(
        HelixEvent(
            source="test",
            event_type="project.update_session",
            payload={
                "active_files": ["main.py", "utils.py"],
                "conversation_id": "conv-abc",
            },
            correlation_id="corr-session-2",
        )
    )
    session = engine._projects["demo"]["session"]
    assert session["active_files"] == ["main.py", "utils.py"]
    assert session["last_conversation_id"] == "conv-abc"
    await engine.stop()


@pytest.mark.asyncio
async def test_persistence(engine, sample_workspace):
    """Verify projects are saved and restored across restarts."""
    await engine.start()
    await engine._handle_create(
        HelixEvent(
            source="test",
            event_type="project.create",
            payload={"name": "persist-test", "path": str(sample_workspace)},
            correlation_id="corr-persist-1",
        )
    )
    await engine.stop()

    # Reload
    engine2 = ProjectEngine(engine._event_bus)
    engine2._storage_path = engine._storage_path
    await engine2.start()
    assert "persist-test" in engine2._projects
    await engine2.stop()
