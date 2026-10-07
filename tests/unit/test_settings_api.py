import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_settings_api(client):
    res_get = client.get("/settings")
    assert res_get.status_code == 200
    data = res_get.json()
    assert "settings" in data
    assert "autoStart" in data["settings"]

    res_post = client.post("/settings", json={"privateMode": True, "compactMode": True})
    assert res_post.status_code == 200
    post_data = res_post.json()
    assert post_data["status"] == "updated"
    assert post_data["settings"]["privateMode"] is True
    assert post_data["settings"]["compactMode"] is True

    # Re-verify GET
    res_get2 = client.get("/settings")
    assert res_get2.status_code == 200
    assert res_get2.json()["settings"]["privateMode"] is True
