import pytest

from foundation.event_bus.event_bus import EventBus, HelixEvent
from context.browser_engine.browser_engine import BrowserEngine


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def engine(event_bus):
    return BrowserEngine(event_bus)


@pytest.mark.asyncio
async def test_start_registers_subscriptions(engine):
    await engine.start()
    assert "context.browser.request" in engine._subscriptions
    assert "context.browser.history" in engine._subscriptions
    assert "context.browser.open_url" in engine._subscriptions
    await engine.stop()


@pytest.mark.asyncio
async def test_stop_clears_subscriptions(engine):
    await engine.start()
    await engine.stop()
    assert len(engine._subscriptions) == 0


@pytest.mark.asyncio
async def test_handle_request_publishes_provided(engine):
    await engine.start()
    received = []

    async def capture(event):
        received.append(event)

    engine._event_bus.subscribe("context.browser.provided", capture)
    await engine._handle_request(
        HelixEvent(
            source="test",
            event_type="context.browser.request",
            payload={},
            correlation_id="corr-browser-1",
        )
    )
    assert len(received) == 1
    assert "tabs" in received[0].payload
    assert isinstance(received[0].payload["tabs"], list)
    assert received[0].correlation_id == "corr-browser-1"
    await engine.stop()


@pytest.mark.asyncio
async def test_handle_history_publishes_history(engine):
    await engine.start()
    received = []

    async def capture(event):
        received.append(event)

    engine._event_bus.subscribe("context.browser.history.provided", capture)
    await engine._handle_history(
        HelixEvent(
            source="test",
            event_type="context.browser.history",
            payload={"limit": 5},
            correlation_id="corr-history-1",
        )
    )
    assert len(received) == 1
    assert "history" in received[0].payload
    assert "count" in received[0].payload
    await engine.stop()


@pytest.mark.asyncio
async def test_open_url_without_url_does_nothing(engine):
    await engine.start()
    received = []

    async def capture(event):
        received.append(event)

    engine._event_bus.subscribe("context.browser.url_opened", capture)
    engine._event_bus.subscribe("context.browser.error", capture)
    await engine._handle_open_url(
        HelixEvent(
            source="test",
            event_type="context.browser.open_url",
            payload={},
            correlation_id="corr-url-1",
        )
    )
    # No url provided → no event published
    assert len(received) == 0
    await engine.stop()


@pytest.mark.asyncio
async def test_identify_browser_from_title(engine):
    assert engine._identify_browser_from_title("Hello - Google Chrome") == "Chrome"
    assert engine._identify_browser_from_title("Page - Microsoft Edge") == "Edge"
    assert engine._identify_browser_from_title("Tab - Firefox") == "Firefox"
    assert engine._identify_browser_from_title("Notepad") == ""


@pytest.mark.asyncio
async def test_clean_tab_title(engine):
    assert engine._clean_tab_title("GitHub - Google Chrome", "Chrome") == "GitHub"
    assert engine._clean_tab_title("Docs - Microsoft Edge", "Edge") == "Docs"
    assert engine._clean_tab_title("Plain Title", "Chrome") == "Plain Title"
