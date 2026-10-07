import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_productivity_insights_api(client):
    res = client.get("/productivity/insights")
    assert res.status_code == 200
    data = res.json()
    assert "focus_score" in data
    assert "categories" in data
    assert "timeline" in data
    assert data["focus_score"] > 0
