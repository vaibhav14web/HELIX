import pytest
from fastapi.testclient import TestClient
from api.main import app, timetable_scheduler, action_executor


@pytest.fixture
def client():
    return TestClient(app)


def test_reminders_api_endpoints(client):
    res_get = client.get("/reminders")
    assert res_get.status_code in (200, 503)

    res_add = client.post("/reminders/add", json={"text": "Test Frontend Reminder", "delay_seconds": 300})
    if res_add.status_code == 200:
        data = res_add.json()
        assert data["status"] == "created"
        rem_id = data["reminder"]["id"]

        res_del = client.delete(f"/reminders/{rem_id}")
        assert res_del.status_code == 200
        assert res_del.json()["status"] == "deleted"


def test_aliases_api_endpoints(client):
    res_get = client.get("/aliases")
    assert res_get.status_code == 200
    assert "aliases" in res_get.json()

    res_reg = client.post("/aliases/register", json={"alias": "test_alias_app", "executable": "notepad.exe"})
    if res_reg.status_code == 200:
        assert res_reg.json()["status"] == "registered"

        res_del = client.delete("/aliases/test_alias_app")
        assert res_del.status_code == 200
        assert res_del.json()["status"] == "deleted"


def test_notes_api_endpoints(client):
    res_get = client.get("/notes")
    assert res_get.status_code == 200
    assert "notes" in res_get.json()

    res_create = client.post("/notes/create", json={"title": "Test_Note_API", "content": "Note API content body"})
    if res_create.status_code == 200:
        assert res_create.json()["status"] == "created"

        res_del = client.delete("/notes/Test_Note_API")
        assert res_del.status_code == 200
        assert res_del.json()["status"] == "deleted"
