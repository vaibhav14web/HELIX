import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient
from pathlib import Path

# Import the app
from api.main import app
import api.main
from foundation.auth import get_or_create_auth_token

def get_auth_headers():
    token = get_or_create_auth_token()
    return {"Authorization": f"Bearer {token}"}

def test_get_productivity_patterns():
    # Mock productivity engine
    mock_engine = MagicMock()
    mock_pattern = MagicMock()
    mock_pattern.to_dict.return_value = {
        "action": "browser_search",
        "category": "browsing",
        "description": "Frequent browser action: browser_search",
        "frequency": 5,
        "first_observed": "2026-06-27T18:00:00Z",
        "last_observed": "2026-06-27T18:10:00Z",
        "suggested": True,
        "automated": False
    }
    mock_engine.get_patterns.return_value = [mock_pattern]
    
    # Store original
    orig_engine = api.main.productivity_engine
    api.main.productivity_engine = mock_engine
    
    try:
        client = TestClient(app)
        response = client.get("/productivity/patterns", headers=get_auth_headers())
        assert response.status_code == 200
        data = response.json()
        assert "patterns" in data
        assert len(data["patterns"]) == 1
        assert data["patterns"][0]["action"] == "browser_search"
    finally:
        api.main.productivity_engine = orig_engine

def test_get_productivity_suggestions():
    # Mock productivity engine
    mock_engine = MagicMock()
    mock_suggestion = MagicMock()
    mock_suggestion.to_dict.return_value = {
        "suggestion_id": "abc12345",
        "action": "browser_search",
        "title": "Automate browser search?",
        "description": "You have performed browser_search 5 times recently.",
        "workflow": {"action": "browser_search"},
        "status": "pending",
        "created_at": "2026-06-27T18:10:00Z"
    }
    mock_engine.get_suggestions.return_value = [mock_suggestion]
    
    # Store original
    orig_engine = api.main.productivity_engine
    api.main.productivity_engine = mock_engine
    
    try:
        client = TestClient(app)
        response = client.get("/productivity/suggestions?status=pending", headers=get_auth_headers())
        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["suggestion_id"] == "abc12345"
        mock_engine.get_suggestions.assert_called_once_with(status="pending")
    finally:
        api.main.productivity_engine = orig_engine

@pytest.mark.asyncio
async def test_get_logs(tmp_path):
    # Mock logger to use temp path
    mock_logger = MagicMock()
    mock_logger._log_path = tmp_path
    
    # Create fake log file
    log_file = tmp_path / "helix.log"
    log_content = (
        "2026-06-27 22:40:26,797 [INFO] helix.productivity_engine: Productivity Engine started\n"
        "2026-06-27 22:40:27,100 [WARNING] helix.some_module: Warnings found\n"
        "Some traceback line 1\n"
        "Some traceback line 2\n"
    )
    log_file.write_text(log_content, encoding="utf-8")
    
    orig_logger = api.main.logger
    api.main.logger = mock_logger
    
    try:
        client = TestClient(app)
        response = client.get("/logs?limit=10", headers=get_auth_headers())
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        logs = data["logs"]
        assert len(logs) == 2
        assert logs[0]["level"] == "WARNING"
        assert logs[0]["module"] == "helix.some_module"
        assert "Some traceback line" in logs[0]["message"]
        assert logs[1]["level"] == "INFO"
        assert logs[1]["module"] == "helix.productivity_engine"
        
        # Test level filtering
        response_filtered = client.get("/logs?level=INFO", headers=get_auth_headers())
        assert response_filtered.status_code == 200
        filtered_logs = response_filtered.json()["logs"]
        assert len(filtered_logs) == 1
        assert filtered_logs[0]["level"] == "INFO"
    finally:
        api.main.logger = orig_logger
