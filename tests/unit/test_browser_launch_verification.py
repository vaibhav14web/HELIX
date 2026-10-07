import pytest
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
async def test_launch_application_with_target_url(executor):
    params = {"application": "chrome", "url": "https://google.com"}

    with patch("shutil.which", return_value="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"), \
         patch("subprocess.Popen") as mock_popen, \
         patch.object(executor, "_verify_process_running", return_value=True) as mock_verify:

        res = executor._launch_application("chrome", params)

        assert res["status"] == "launched"
        assert res["application"] == "chrome"
        assert res["url"] == "https://google.com"
        assert res["verified"] is True

        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args == ["C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "https://google.com"]
        mock_verify.assert_called_once_with("chrome.exe")


@pytest.mark.asyncio
async def test_launch_application_process_verification_check(executor):
    params = {"application": "notepad"}

    with patch("shutil.which", return_value="C:\\Windows\\notepad.exe"), \
         patch("subprocess.Popen"), \
         patch.object(executor, "_verify_process_running", return_value=False):

        res = executor._launch_application("notepad", params)

        assert res["status"] == "launched"
        assert res["application"] == "notepad"
        assert res["verified"] is False


@pytest.mark.asyncio
async def test_browser_search_returns_verification_flag(executor):
    params = {"query": "python tutorials"}

    with patch("webbrowser.open"), \
         patch.object(executor, "_verify_process_running", return_value=True):

        res = executor._browser_search(params)

        assert res["status"] == "opened"
        assert "python" in res["url"]
        assert res["verified"] is True
