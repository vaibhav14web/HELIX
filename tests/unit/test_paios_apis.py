import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_system_self_state_api(client):
    res = client.get("/system/self_state")
    assert res.status_code == 200
    data = res.json()
    assert data["identity"] == "HELIX PAIOS"
    assert data["health_status"] == "healthy"


def test_system_world_state_api(client):
    res = client.get("/system/world_state")
    assert res.status_code == 200
    data = res.json()
    assert "active_window" in data


def test_system_capabilities_api(client):
    res = client.get("/system/capabilities")
    assert res.status_code == 200
    caps = res.json()["capabilities"]
    assert len(caps) >= 5


def test_system_discovered_apps_api(client):
    res = client.get("/system/discovered_apps")
    assert res.status_code == 200
    apps = res.json()["apps"]
    assert len(apps) >= 1


def test_system_projects_api(client):
    res = client.get("/system/projects")
    assert res.status_code == 200
    projects = res.json()["projects"]
    assert len(projects) >= 1


def test_goals_api(client):
    res = client.get("/goals")
    assert res.status_code == 200
    goals = res.json()["goals"]
    assert len(goals) >= 1
