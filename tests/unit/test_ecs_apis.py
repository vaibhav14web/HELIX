import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_ecs_state_api(client):
    res = client.get("/ecs/state")
    assert res.status_code == 200
    data = res.json()
    assert "current_state" in data
    assert "health" in data


def test_ecs_health_api(client):
    res = client.get("/ecs/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["overall_score"] == 100.0


def test_ecs_interrupt_api(client):
    res = client.post("/ecs/interrupt", json={"priority": 1, "source": "test_api", "reason": "Emergency interrupt", "action_required": "listen"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "injected"
