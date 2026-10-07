import base64
import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient

import api.main
from api.main import app
from foundation.auth import get_or_create_auth_token
from foundation.event_bus.event_bus import EventBus
from core_ai.voice_engine.voice_engine import VoiceEngine


def get_auth_headers():
    token = get_or_create_auth_token()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def voice_engine():
    import os
    os.environ["HELIX_VOICE_BACKEND"] = "mock"
    os.environ["HELIX_VOICE_TTS_BACKEND"] = "mock"
    os.environ["HELIX_VOICE_STT_BACKEND"] = "mock"
    bus = EventBus()
    return VoiceEngine(bus)


@pytest.mark.asyncio
async def test_voice_engine_clean_text_preserves_code():
    raw_text = "Here is Python code:\n```python\nprint(hello)\n```"
    cleaned = VoiceEngine.clean_text(raw_text)
    assert "print" in cleaned
    assert "hello" in cleaned
    assert "```" not in cleaned


@pytest.mark.asyncio
async def test_voice_engine_synthesize_mock(voice_engine):
    audio_bytes = await voice_engine.synthesize("Hello world! HELIX is speaking.")
    assert isinstance(audio_bytes, bytes)
    assert len(audio_bytes) > 0
    assert audio_bytes[:4] == b"RIFF"


def test_chat_always_returns_voice_audio():
    mock_conv = MagicMock()
    mock_conv.chat = AsyncMock(return_value="Hello from HELIX assistant!")
    
    mock_voice = MagicMock()
    mock_voice.synthesize = AsyncMock(return_value=b"RIFFmockwavdata")

    orig_conv = api.main.conv_engine
    orig_voice = api.main.voice_engine

    api.main.conv_engine = mock_conv
    api.main.voice_engine = mock_voice

    try:
        client = TestClient(app)
        response = client.post("/chat", json={"message": "What is the weather?"}, headers=get_auth_headers())
        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Hello from HELIX assistant!"
        assert data["audio"] is not None
        assert base64.b64decode(data["audio"]) == b"RIFFmockwavdata"
    finally:
        api.main.conv_engine = orig_conv
        api.main.voice_engine = orig_voice


def test_voice_command_always_returns_voice_audio():
    mock_conv = MagicMock()
    mock_conv.chat = AsyncMock(return_value="I received your voice command!")
    
    mock_voice = MagicMock()
    mock_voice.transcribe = AsyncMock(return_value="Open browser")
    mock_voice.synthesize = AsyncMock(return_value=b"RIFFmockwavdata")

    orig_conv = api.main.conv_engine
    orig_voice = api.main.voice_engine

    api.main.conv_engine = mock_conv
    api.main.voice_engine = mock_voice

    try:
        client = TestClient(app)
        files = {"file": ("test.webm", b"dummy_webm_data", "audio/webm")}
        response = client.post("/voice/command", files=files, data={"session_id": "default"}, headers=get_auth_headers())
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "Open browser"
        assert data["response"] == "I received your voice command!"
        assert data["audio"] is not None
        assert base64.b64decode(data["audio"]) == b"RIFFmockwavdata"
    finally:
        api.main.conv_engine = orig_conv
        api.main.voice_engine = orig_voice
