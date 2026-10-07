import io
import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_files_upload_and_list_api(client):
    file_content = b"Sample upload content binary/text"
    files = {"file": ("test_upload_sample.txt", io.BytesIO(file_content), "text/plain")}

    res_upload = client.post("/files/upload", files=files)
    assert res_upload.status_code == 200
    upload_data = res_upload.json()
    assert upload_data["status"] == "uploaded"
    assert upload_data["name"] == "test_upload_sample.txt"

    res_list = client.get("/files")
    assert res_list.status_code == 200
    file_list = res_list.json()["files"]
    assert any(f["name"] == "test_upload_sample.txt" for f in file_list)


def test_files_upload_blocked_extension(client):
    file_content = b"malicious binary script"
    files = {"file": ("payload.exe", io.BytesIO(file_content), "application/octet-stream")}

    res_upload = client.post("/files/upload", files=files)
    assert res_upload.status_code == 403
    assert "cannot upload restricted file type" in res_upload.json()["detail"]
