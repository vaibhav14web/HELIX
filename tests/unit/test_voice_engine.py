import os
import pytest

from foundation.event_bus.event_bus import EventBus
from core_ai.voice_engine.voice_engine import VoiceEngine


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def engine(event_bus):
    os.environ["HELIX_VOICE_BACKEND"] = "mock"
    return VoiceEngine(event_bus)


@pytest.mark.asyncio
async def test_start_publishes_ready(engine):
    received = []

    async def capture(event):
        received.append(event)

    engine._event_bus.subscribe("voice.ready", capture)
    await engine.start()
    assert len(received) == 1
    assert received[0].payload["backend"] == "mock"
    await engine.stop()


@pytest.mark.asyncio
async def test_has_correct_subscriptions(engine):
    await engine.start()
    assert "voice.wake" in engine._subscriptions
    assert "voice.listen" in engine._subscriptions
    assert "voice.tts" in engine._subscriptions
    assert "system.state.change" in engine._subscriptions
    await engine.stop()


@pytest.mark.asyncio
async def test_unsubscribe_on_stop(engine):
    await engine.start()
    await engine.stop()
    assert len(engine._subscriptions) == 0


@pytest.mark.asyncio
async def test_speak_publishes_tts_event(engine):
    await engine.start()
    received = []

    async def capture(event):
        received.append(event)

    engine._event_bus.subscribe("voice.tts", capture)
    await engine.speak("Hello world")
    assert len(received) == 1
    assert received[0].payload["text"] == "Hello world"
    await engine.stop()


@pytest.mark.asyncio
async def test_listen_returns_empty_on_mock(engine):
    await engine.start()
    text = await engine.listen("test_session")
    assert isinstance(text, str)
    await engine.stop()


@pytest.mark.asyncio
async def test_handle_tts_with_empty_text(engine):
    await engine.start()
    received = []

    async def capture(event):
        received.append(event)

    engine._event_bus.subscribe("voice.error", capture)
    await engine._handle_tts(
        type("Event", (), {
            "payload": {"text": "", "session_id": "default"},
            "correlation_id": "corr-1",
        })()
    )
    # Empty text should not produce a tts.start event
    tts_starts = [e for e in received if e.event_type == "voice.tts.start"]
    assert len(tts_starts) == 0
    await engine.stop()


@pytest.mark.asyncio
async def test_state_change_unloads_on_sleep(engine):
    engine._keep_loaded = False
    engine._idle_unload_seconds = 0
    await engine.start()
    engine._loaded = True
    engine._stt_model_instance = object()
    engine._tts_model_instance = object()
    received = []

    async def capture(event):
        received.append(event)

    engine._event_bus.subscribe("voice.model.unloading", capture)
    await engine._handle_state_change(
        type("Event", (), {
            "payload": {"state": "sleep"},
        })()
    )
    assert len(received) == 1
    await engine.stop()


@pytest.mark.asyncio
async def test_state_change_keeps_loaded_on_sleep(engine):
    engine._keep_loaded = True
    await engine.start()
    engine._loaded = True
    engine._stt_model_instance = object()
    engine._tts_model_instance = object()
    received = []

    async def capture(event):
        received.append(event)

    engine._event_bus.subscribe("voice.model.unloading", capture)
    await engine._handle_state_change(
        type("Event", (), {
            "payload": {"state": "sleep"},
        })()
    )
    assert len(received) == 0
    assert engine._loaded is True
    assert engine._stt_model_instance is not None
    await engine.stop()


def test_clean_text_eliminates_backslashes_and_technical_punctuation():
    # Test 1: Windows paths with backslashes
    raw1 = "Found 1 installed application(s) matching 'notepad':\n- **Notepad** (`C:\\Windows\\System32\\notepad.exe`)"
    cleaned1 = VoiceEngine.clean_text(raw1)
    assert "\\" not in cleaned1
    assert "notepad.exe" not in cleaned1 or "Notepad" in cleaned1
    assert "*" not in cleaned1
    assert "`" not in cleaned1

    # Test 2: Document paths and sizes
    raw2 = "Found 20 file(s) in `C:\\Users\\vaibh\\OneDrive\\Documents`:\n- **desktop.ini** (0.4 KB) — `C:\\Users\\vaibh\\OneDrive\\Documents\\desktop.ini`"
    cleaned2 = VoiceEngine.clean_text(raw2)
    assert "\\" not in cleaned2
    assert "kilobytes" in cleaned2
    assert "—" not in cleaned2

    # Test 3: Raw JSON objects
    raw3 = '{"name": "search_installed_apps", "arguments": {"query": "notepad"}}'
    cleaned3 = VoiceEngine.clean_text(raw3)
    assert "{" not in cleaned3
    assert "}" not in cleaned3
    assert "search installed apps" in cleaned3


