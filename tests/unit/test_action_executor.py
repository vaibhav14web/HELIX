import time
import pytest

from foundation.event_bus.event_bus import EventBus
from action.action_executor.action_executor import ActionExecutor


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture(autouse=True)
def trusted_test_source():
    import action.action_executor.action_executor as _ae
    _ae._TRUSTED_SOURCES.add("test")
    yield
    _ae._TRUSTED_SOURCES.discard("test")


@pytest.fixture
def executor(event_bus):
    e = ActionExecutor(event_bus)
    return e


@pytest.mark.asyncio
async def test_start_subscribes_to_action_execute(executor):
    await executor.start()
    assert "action.execute" in executor._subscriptions
    await executor.stop()


@pytest.mark.asyncio
async def test_unsubscribe_on_stop(executor):
    await executor.start()
    await executor.stop()
    assert len(executor._subscriptions) == 0


@pytest.mark.asyncio
async def test_unknown_action_publishes_failed(executor, event_bus):
    await executor.start()

    failed = []

    async def capture(event):
        failed.append(event)

    event_bus.subscribe("automation.failed", capture)
    await event_bus.publish_event(
        source="test",
        event_type="action.execute",
        payload={
            "action_id": "a1",
            "action": "nonexistent_action",
            "params": {},
        },
    )

    assert len(failed) == 1
    assert "Unknown action type" in failed[0].payload["error"]
    await executor.stop()


@pytest.mark.asyncio
async def test_browser_search_empty_query_fails(executor, event_bus):
    await executor.start()

    failed = []

    async def capture(event):
        failed.append(event)

    event_bus.subscribe("automation.failed", capture)
    await event_bus.publish_event(
        source="test",
        event_type="action.execute",
        payload={
            "action_id": "a2",
            "action": "browser_search",
            "params": {"query": ""},
        },
    )

    assert len(failed) == 1
    assert "empty" in failed[0].payload["error"].lower()
    await executor.stop()


@pytest.mark.asyncio
async def test_launch_application_no_target_fails(executor, event_bus):
    await executor.start()

    failed = []

    async def capture(event):
        failed.append(event)

    event_bus.subscribe("automation.failed", capture)
    await event_bus.publish_event(
        source="test",
        event_type="action.execute",
        payload={
            "action_id": "a3",
            "action": "launch_application",
            "params": {},
        },
    )

    assert len(failed) == 1
    assert "No application specified" in failed[0].payload["error"]
    await executor.stop()


@pytest.mark.asyncio
async def test_read_file_no_path_fails(executor, event_bus):
    await executor.start()

    failed = []

    async def capture(event):
        failed.append(event)

    event_bus.subscribe("automation.failed", capture)
    await event_bus.publish_event(
        source="test",
        event_type="action.execute",
        payload={
            "action_id": "a4",
            "action": "read_file",
            "params": {},
        },
    )

    assert len(failed) == 1
    assert "No file path specified" in failed[0].payload["error"]
    await executor.stop()


@pytest.mark.asyncio
async def test_read_file_not_found_fails(executor, event_bus):
    await executor.start()

    failed = []

    async def capture(event):
        failed.append(event)

    event_bus.subscribe("automation.failed", capture)
    await event_bus.publish_event(
        source="test",
        event_type="action.execute",
        payload={
            "action_id": "a5",
            "action": "read_file",
            "params": {"path": "C:\\nonexistent_file_xyz.txt"},
        },
    )

    assert len(failed) == 1
    assert "not found" in failed[0].payload["error"].lower()
    await executor.stop()


@pytest.mark.asyncio
async def test_send_notification_empty_message_fails(executor, event_bus):
    await executor.start()

    failed = []

    async def capture(event):
        failed.append(event)

    event_bus.subscribe("automation.failed", capture)
    await event_bus.publish_event(
        source="test",
        event_type="action.execute",
        payload={
            "action_id": "a6",
            "action": "send_notification",
            "params": {"message": ""},
        },
    )

    assert len(failed) == 1
    assert "Notification message is empty" in failed[0].payload["error"]
    await executor.stop()


@pytest.mark.asyncio
async def test_browser_search_publishes_result(executor, event_bus):
    old_open = executor._open_url_browser
    opened = []

    def fake_open(url, action="open_url", **meta):
        opened.append((url, action))
        return {"status": "opened", "url": url}

    executor._open_url_browser = fake_open
    await executor.start()

    results = []

    async def capture(event):
        results.append(event)

    event_bus.subscribe("automation.result", capture)
    await event_bus.publish_event(
        source="test",
        event_type="action.execute",
        payload={
            "action_id": "a7",
            "action": "browser_search",
            "params": {"query": "python testing"},
        },
    )

    assert len(results) == 1
    assert results[0].payload["action"] == "browser_search"
    assert results[0].payload["action_id"] == "a7"
    assert len(opened) >= 1
    assert "python+testing" in opened[0][0] or "python%20testing" in opened[0][0]
    executor._open_url_browser = old_open
    await executor.stop()


@pytest.mark.asyncio
async def test_compose_email_publishes_result(executor, event_bus):
    old_open = executor._open_url_browser
    opened = []

    def fake_open(url, action="open_url", **meta):
        opened.append((url, action))
        return {"status": "opened", "url": url}

    executor._open_url_browser = fake_open
    await executor.start()

    results = []

    async def capture(event):
        results.append(event)

    event_bus.subscribe("automation.result", capture)
    await event_bus.publish_event(
        source="test",
        event_type="action.execute",
        payload={
            "action_id": "a8",
            "action": "compose_email",
            "params": {"to": "test@example.com", "subject": "Hello"},
        },
    )

    assert len(results) == 1
    assert results[0].payload["action"] == "compose_email"
    assert len(opened) >= 1
    assert "mailto:" in opened[0][0]
    executor._open_url_browser = old_open
    await executor.stop()


@pytest.mark.asyncio
async def test_open_url_publishes_result(executor, event_bus):
    old_open = executor._open_url_browser
    opened = []

    def fake_open(url, action="open_url", **meta):
        opened.append((url, action))
        return {"status": "opened", "url": url}

    executor._open_url_browser = fake_open
    await executor.start()

    results = []

    async def capture(event):
        results.append(event)

    event_bus.subscribe("automation.result", capture)
    await event_bus.publish_event(
        source="test",
        event_type="action.execute",
        payload={
            "action_id": "a9",
            "action": "open_url",
            "params": {"url": "https://example.com"},
        },
    )

    assert len(results) == 1
    assert results[0].payload["action"] == "open_url"
    assert len(opened) >= 1
    assert "example.com" in opened[0][0]
    executor._open_url_browser = old_open
    await executor.stop()


@pytest.mark.asyncio
async def test_untrusted_source_rejected(executor, event_bus):
    await executor.start()

    failed = []

    async def capture(event):
        failed.append(event)

    event_bus.subscribe("automation.failed", capture)
    await event_bus.publish_event(
        source="untrusted_module",
        event_type="action.execute",
        payload={"action": "browser_search", "params": {"query": "test"}},
    )

    assert len(failed) == 1
    assert "Untrusted event source" in failed[0].payload["error"]
    await executor.stop()


@pytest.mark.asyncio
async def test_open_url_blocks_javascript_scheme(executor, event_bus):
    await executor.start()

    failed = []

    async def capture(event):
        failed.append(event)

    event_bus.subscribe("automation.failed", capture)
    await event_bus.publish_event(
        source="test",
        event_type="action.execute",
        payload={"action": "open_url", "params": {"url": "javascript:alert(1)"}},
    )

    assert len(failed) == 1
    assert "Blocked URL scheme" in failed[0].payload["error"]
    await executor.stop()


@pytest.mark.asyncio
async def test_open_url_blocks_file_scheme(executor, event_bus):
    await executor.start()

    failed = []

    async def capture(event):
        failed.append(event)

    event_bus.subscribe("automation.failed", capture)
    await event_bus.publish_event(
        source="test",
        event_type="action.execute",
        payload={"action": "open_url", "params": {"url": "file:///etc/passwd"}},
    )

    assert len(failed) == 1
    assert "Blocked URL scheme" in failed[0].payload["error"]
    await executor.stop()


@pytest.mark.asyncio
async def test_launch_unknown_app_rejected(executor, event_bus):
    await executor.start()

    failed = []

    async def capture(event):
        failed.append(event)

    event_bus.subscribe("automation.failed", capture)
    await event_bus.publish_event(
        source="test",
        event_type="action.execute",
        payload={"action": "launch_application", "params": {"application": "virus.exe"}},
    )

    assert len(failed) == 1
    assert "Unknown application" in failed[0].payload["error"]
    await executor.stop()


@pytest.mark.asyncio
async def test_launch_blocked_app_rejected(executor, event_bus):
    await executor.start()

    failed = []

    async def capture(event):
        failed.append(event)

    event_bus.subscribe("automation.failed", capture)
    await event_bus.publish_event(
        source="test",
        event_type="action.execute",
        payload={"action": "launch_application", "target": "cmd"},
    )

    assert len(failed) == 1
    assert "Unknown application" in failed[0].payload["error"]
    await executor.stop()


@pytest.mark.asyncio
async def test_read_file_system_path_blocked(executor, event_bus):
    await executor.start()

    failed = []

    async def capture(event):
        failed.append(event)

    event_bus.subscribe("automation.failed", capture)
    await event_bus.publish_event(
        source="test",
        event_type="action.execute",
        payload={"action": "read_file", "params": {"path": "C:\\Windows\\System32\\drivers\\etc\\hosts"}},
    )

    assert len(failed) == 1
    assert "Access denied" in failed[0].payload["error"] or "not found" in failed[0].payload["error"].lower()
    await executor.stop()


@pytest.mark.asyncio
async def test_compose_email_invalid_address_rejected(executor, event_bus):
    await executor.start()

    failed = []

    async def capture(event):
        failed.append(event)

    event_bus.subscribe("automation.failed", capture)
    await event_bus.publish_event(
        source="test",
        event_type="action.execute",
        payload={"action": "compose_email", "params": {"to": "not an email"}},
    )

    assert len(failed) == 1
    assert "Invalid email" in failed[0].payload["error"]
    await executor.stop()


@pytest.mark.asyncio
async def test_rate_limit_exceeded(executor, event_bus):
    executor._action_times = [time.time() for _ in range(5)]
    await executor.start()

    old_open = executor._open_url_browser
    executor._open_url_browser = lambda url, **kw: {"status": "opened", "url": url}

    failed = []

    async def capture(event):
        failed.append(event)

    event_bus.subscribe("automation.failed", capture)
    await event_bus.publish_event(
        source="test",
        event_type="action.execute",
        payload={"action": "open_url", "params": {"url": "https://example.com"}},
    )

    assert len(failed) == 1
    assert "Rate limit exceeded" in failed[0].payload["error"]
    executor._open_url_browser = old_open
    await executor.stop()


@pytest.mark.asyncio
async def test_open_url_from_target(executor, event_bus):
    old_open = executor._open_url_browser
    opened = []

    def fake_open(url, action="open_url", **meta):
        opened.append((url, action))
        return {"status": "opened", "url": url}

    executor._open_url_browser = fake_open
    await executor.start()

    results = []

    async def capture(event):
        results.append(event)

    event_bus.subscribe("automation.result", capture)
    await event_bus.publish_event(
        source="test",
        event_type="action.execute",
        payload={
            "action_id": "a10",
            "action": "open_url",
            "target": "https://helix.dev",
            "params": {},
        },
    )

    assert len(results) == 1
    assert len(opened) >= 1
    assert "helix.dev" in opened[0][0]
    executor._open_url_browser = old_open
    await executor.stop()
