import pytest
from unittest.mock import patch, MagicMock

from foundation.event_bus.event_bus import EventBus
from action.action_executor.action_executor import ActionExecutor, extract_article_text, HTMLArticleParser


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def executor(event_bus):
    return ActionExecutor(event_bus)


def test_extract_article_text_strips_scripts_and_nav():
    html = """
    <html>
        <head><title>Test Article</title></head>
        <body>
            <header><h1>Site Header</h1></header>
            <nav><a href="#">Home</a><a href="#">About</a></nav>
            <script>var x = 10;</script>
            <style>body { color: red; }</style>
            <article>
                <h1>Main Heading</h1>
                <p>This is the main article content that should be extracted for reading aloud.</p>
                <p>Second paragraph with more interesting details.</p>
            </article>
            <footer>Copyright 2026</footer>
        </body>
    </html>
    """
    text = extract_article_text(html)
    assert "Main Heading" in text
    assert "This is the main article content" in text
    assert "Second paragraph with more interesting details" in text
    assert "var x = 10" not in text
    assert "body { color: red; }" not in text
    assert "Site Header" not in text
    assert "Copyright 2026" not in text


@pytest.mark.asyncio
async def test_read_browser_page_explicit_url(executor, event_bus):
    tts_events = []

    async def capture_tts(event):
        tts_events.append(event)

    event_bus.subscribe("voice.tts", capture_tts)

    sample_html = "<html><body><h1>News Article</h1><p>Breaking news story details here.</p></body></html>"

    mock_resp = MagicMock()
    mock_resp.read.return_value = sample_html.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = await executor._read_browser_page("https://example.com/news", {})

        assert res["status"] == "reading"
        assert res["url"] == "https://example.com/news"
        assert res["verified"] is True
        assert res["text_length"] > 0
        assert res["duration_estimate_sec"] >= 0.1

        assert len(tts_events) == 1
        assert "Breaking news story details" in tts_events[0].payload["text"]


@pytest.mark.asyncio
async def test_read_browser_page_active_tab_fallback(executor, event_bus):
    tts_events = []

    async def capture_tts(event):
        tts_events.append(event)

    event_bus.subscribe("voice.tts", capture_tts)

    with patch("context.browser_engine.browser_engine.BrowserEngine._get_browser_history", return_value=[{"url": "https://python.org"}]), \
         patch("urllib.request.urlopen") as mock_urlopen:

        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html><body><p>Python Programming Documentation</p></body></html>"
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = await executor._read_browser_page("the page I have open", {})

        assert res["status"] == "reading"
        assert res["url"] == "https://python.org"
        assert res["verified"] is True
        assert len(tts_events) == 1


@pytest.mark.asyncio
async def test_read_browser_page_no_url_raises_error(executor):
    with patch("context.browser_engine.browser_engine.BrowserEngine._get_browser_history", return_value=[]), \
         patch("context.browser_engine.browser_engine.BrowserEngine._get_active_tabs", return_value=[]):
        with pytest.raises(ValueError, match="No URL or active browser page specified"):
            await executor._read_browser_page("", {})
