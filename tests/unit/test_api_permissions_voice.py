import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient

# Import the app
from api.main import app
import api.main

def test_add_auto_approve_pattern():
    mock_perm = MagicMock()
    mock_event_bus = MagicMock()
    mock_event_bus.publish_event = AsyncMock()

    orig_perm = api.main.perm_manager
    orig_event_bus = api.main.event_bus

    api.main.perm_manager = mock_perm
    api.main.event_bus = mock_event_bus

    try:
        client = TestClient(app)
        response = client.post("/permission/auto-approve", json={"pattern": "git *"})
        assert response.status_code == 200
        data = response.json()
        assert data["pattern"] == "git *"
        assert data["status"] == "added"
        mock_event_bus.publish_event.assert_called_once_with(
            source="api",
            event_type="permission.auto_approve.add",
            payload={"pattern": "git *"}
        )
    finally:
        api.main.perm_manager = orig_perm
        api.main.event_bus = orig_event_bus

def test_remove_auto_approve_pattern():
    mock_perm = MagicMock()
    mock_event_bus = MagicMock()
    mock_event_bus.publish_event = AsyncMock()

    orig_perm = api.main.perm_manager
    orig_event_bus = api.main.event_bus

    api.main.perm_manager = mock_perm
    api.main.event_bus = mock_event_bus

    try:
        client = TestClient(app)
        response = client.delete("/permission/auto-approve?pattern=git%20*")
        assert response.status_code == 200
        data = response.json()
        assert data["pattern"] == "git *"
        assert data["status"] == "removed"
        mock_event_bus.publish_event.assert_called_once_with(
            source="api",
            event_type="permission.auto_approve.remove",
            payload={"pattern": "git *"}
        )
    finally:
        api.main.perm_manager = orig_perm
        api.main.event_bus = orig_event_bus

def test_voice_interrupt():
    mock_voice = MagicMock()
    mock_event_bus = MagicMock()
    mock_event_bus.publish_event = AsyncMock()

    orig_voice = api.main.voice_engine
    orig_event_bus = api.main.event_bus

    api.main.voice_engine = mock_voice
    api.main.event_bus = mock_event_bus

    try:
        client = TestClient(app)
        response = client.post("/voice/interrupt")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "interrupted"
        mock_event_bus.publish_event.assert_called_once_with(
            source="api",
            event_type="voice.interrupt",
            payload={}
        )
    finally:
        api.main.voice_engine = orig_voice
        api.main.event_bus = orig_event_bus
