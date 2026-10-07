import os
import json
import pytest
from unittest.mock import patch, MagicMock

from foundation.event_bus.event_bus import EventBus
from action.action_executor.action_executor import ActionExecutor, _KNOWN_APPS


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def executor(event_bus):
    return ActionExecutor(event_bus)


@pytest.mark.asyncio
async def test_default_aliases_loaded(executor):
    assert "vscode" in executor._app_aliases
    assert executor._app_aliases["vscode"] == "code.cmd"
    assert "calculator" in executor._app_aliases
    assert executor._app_aliases["calculator"] == "calc.exe"


@pytest.mark.asyncio
async def test_custom_alias_registration(executor):
    executor.register_alias("custom_editor", "notepad.exe")
    assert "custom_editor" in executor._app_aliases

    params = {"application": "custom_editor"}
    with patch("shutil.which", return_value="C:\\Windows\\notepad.exe"), \
         patch("subprocess.Popen") as mock_popen, \
         patch.object(executor, "_verify_process_running", return_value=True) as mock_verify:

        res = executor._launch_application("custom_editor", params)

        assert res["status"] == "launched"
        assert res["application"] == "custom_editor"
        assert res["executable"] == "notepad.exe"
        assert res["verified"] is True
        mock_verify.assert_called_once_with("notepad.exe")


@pytest.mark.asyncio
async def test_load_aliases_from_custom_file(executor, tmp_path):
    custom_json = tmp_path / "custom_aliases.json"
    custom_json.write_text(json.dumps({"my_browser": "chrome.exe", "vlc_player": "vlc.exe"}), encoding="utf-8")

    executor.load_app_aliases(custom_json)

    assert executor._app_aliases["my_browser"] == "chrome.exe"
    assert executor._app_aliases["vlc_player"] == "vlc.exe"


@pytest.mark.asyncio
async def test_launch_app_by_alias_vscode(executor):
    params = {"application": "vscode"}

    with patch("shutil.which", return_value="C:\\Program Files\\Microsoft VS Code\\bin\\code.cmd"), \
         patch("subprocess.Popen") as mock_popen, \
         patch.object(executor, "_verify_process_running", return_value=True) as mock_verify:

        res = executor._launch_application("vscode", params)

        assert res["status"] == "launched"
        assert res["application"] == "vscode"
        assert res["verified"] is True
        mock_verify.assert_called_once_with("code.exe")


@pytest.mark.asyncio
async def test_launch_unknown_app_raises_error(executor):
    params = {"application": "non_existent_app_12345"}
    with pytest.raises(ValueError, match="Unknown application"):
        executor._launch_application("non_existent_app_12345", params)
