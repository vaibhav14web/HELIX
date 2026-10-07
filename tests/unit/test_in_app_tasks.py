import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from foundation.event_bus.event_bus import EventBus
from action.action_executor.action_executor import ActionExecutor


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def executor(event_bus):
    return ActionExecutor(event_bus)


@pytest.mark.asyncio
async def test_vscode_open_file_success(executor, tmp_path):
    sample_file = tmp_path / "test_script.py"
    sample_file.write_text("print('Hello HELIX')", encoding="utf-8")

    with patch("shutil.which", return_value="C:\\Program Files\\Microsoft VS Code\\bin\\code.cmd"), \
         patch("subprocess.Popen") as mock_popen, \
         patch.object(executor, "_verify_process_running", return_value=True) as mock_verify:

        res = executor._vscode_open(str(sample_file), {})

        assert res["status"] == "opened"
        assert res["app"] == "vscode"
        assert res["path"] == str(sample_file.resolve())
        assert res["verified"] is True

        mock_popen.assert_called_once()
        mock_verify.assert_called_once_with("Code.exe")


@pytest.mark.asyncio
async def test_create_note_success(executor, tmp_path):
    with patch("subprocess.Popen") as mock_popen, \
         patch.object(executor, "_verify_process_running", return_value=True) as mock_verify:

        res = executor._create_note("Project Architecture", {"content": "- Component A\n- Component B"})

        assert res["status"] == "created"
        assert res["app"] == "notes"
        assert res["title"] == "Project Architecture"
        assert res["verified"] is True
        assert os.path.exists(res["path"])

        content = Path(res["path"]).read_text(encoding="utf-8")
        assert "Component A" in content
        mock_verify.assert_called_once_with("notepad.exe")


@pytest.mark.asyncio
async def test_in_app_task_dispatch(executor, tmp_path):
    sample_file = tmp_path / "app.py"
    sample_file.write_text("# App code", encoding="utf-8")

    with patch.object(executor, "_vscode_open") as mock_vscode, \
         patch.object(executor, "_create_note") as mock_note:

        mock_vscode.return_value = {"status": "opened", "app": "vscode", "verified": True}
        mock_note.return_value = {"status": "created", "app": "notes", "verified": True}

        res_v = await executor._in_app_task(str(sample_file), {"app": "vscode"})
        assert res_v["app"] == "vscode"

        res_n = await executor._in_app_task("Shopping List", {"app": "notes", "content": "Milk, Eggs"})
        assert res_n["app"] == "notes"


@pytest.mark.asyncio
async def test_vscode_open_blocked_system_path_rejected(executor):
    sys_path = os.environ.get("SystemRoot", "C:\\Windows") + "\\System32\\cmd.exe"
    if os.path.exists(sys_path):
        with pytest.raises(PermissionError, match="Access denied"):
            executor._vscode_open(sys_path, {})


@pytest.mark.asyncio
async def test_in_app_task_unsupported_app_raises_error(executor):
    with pytest.raises(ValueError, match="Unsupported in-app task application target"):
        await executor._in_app_task("unknown_app", {"app": "invalid_app_name"})
