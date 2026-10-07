import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_agents_list_and_deploy_api(client):
    res_get = client.get("/agents")
    assert res_get.status_code == 200
    data = res_get.json()
    assert "agents" in data

    res_deploy = client.post(
        "/agents/deploy",
        json={
            "name": "Custom Test Agent",
            "role": "Automated Testing",
            "capabilities": ["API Testing", "Validation"],
        },
    )
    assert res_deploy.status_code == 200
    deploy_data = res_deploy.json()
    assert deploy_data["status"] == "deployed"
    assert deploy_data["agent"]["name"] == "Custom Test Agent"

    # Re-verify GET
    res_get2 = client.get("/agents")
    assert res_get2.status_code == 200
    agent_list = res_get2.json()["agents"]
    assert any(a["name"] == "Custom Test Agent" for a in agent_list)
