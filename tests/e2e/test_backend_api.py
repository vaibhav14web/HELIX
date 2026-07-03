import pytest
import requests

BASE_URL = "http://localhost:8000"


def test_health_endpoint():
    resp = requests.get(f"{BASE_URL}/health", timeout=5)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "conversation_engine" in data["modules"]


def test_chat_endpoint():
    resp = requests.post(
        f"{BASE_URL}/chat",
        json={"message": "Hello", "session_id": "test-e2e"},
        timeout=30,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert data["session_id"] == "test-e2e"


def test_cors_preflight():
    resp = requests.options(
        f"{BASE_URL}/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
        timeout=5,
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
