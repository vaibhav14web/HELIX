import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_automation_pipelines_api(client):
    res_get = client.get("/automation/pipelines")
    assert res_get.status_code == 200
    data = res_get.json()
    assert "pipelines" in data

    res_save = client.post(
        "/automation/pipelines",
        json={
            "id": "test_pipeline_1",
            "name": "Test Pipeline",
            "description": "Pipeline test description",
            "nodes": [{"id": "1", "data": {"label": "Trigger Node"}}],
            "edges": [],
        },
    )
    assert res_save.status_code == 200
    assert res_save.json()["status"] == "saved"

    res_run = client.post("/automation/pipelines/test_pipeline_1/run")
    assert res_run.status_code == 200
    run_data = res_run.json()
    assert run_data["status"] == "completed"
    assert run_data["runs"] >= 1
