import asyncio
import os
import numpy as np
import pytest
from unittest.mock import MagicMock, AsyncMock

from foundation.event_bus.event_bus import EventBus, HelixEvent
from core_ai.voice_engine.audio_capture import RingBuffer, AudioCapture
from core_ai.voice_engine.voice_engine import VoiceEngine
from core_ai.wake_word_engine.wake_word_engine import WakeWordEngine
from orchestrator.ecs.executive_control_system import ExecutiveControlSystem, ExecutiveState
from core_ai.self_model.self_model_engine import SelfModelEngine


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def ring_buffer():
    return RingBuffer(max_seconds=3, sample_rate=16000)


# ── 1. RingBuffer Unit Tests ─────────────────────────────────────────

def test_ring_buffer_write_and_read(ring_buffer):
    # Write 0.5s of audio (8000 samples)
    data1 = np.ones(8000, dtype=np.float32) * 0.5
    ring_buffer.write(data1)
    assert ring_buffer.current_marker == 8000

    # Read from marker 0 for 0.5s
    read_data = ring_buffer.read_from(0, 0.5)
    assert len(read_data) == 8000
    assert np.allclose(read_data, 0.5)

    # Reading past current marker returns empty array
    future_data = ring_buffer.read_from(8000, 0.5)
    assert len(future_data) == 0


def test_ring_buffer_wrap_around():
    # 1 second buffer (16000 samples)
    rb = RingBuffer(max_seconds=1, sample_rate=16000)
    
    # Write 10000 samples of 1.0
    rb.write(np.ones(10000, dtype=np.float32))
    assert rb.current_marker == 10000

    # Write another 10000 samples of 2.0 (total 20000 > capacity 16000)
    rb.write(np.ones(10000, dtype=np.float32) * 2.0)
    assert rb.current_marker == 20000

    # Read last 0.5s (8000 samples) -> all should be 2.0
    last_half = rb.read_last(0.5)
    assert len(last_half) == 8000
    assert np.allclose(last_half, 2.0)


# ── 2. WakeWordEngine Lifecycle & Configuration ─────────────────────

@pytest.mark.asyncio
async def test_wake_word_engine_ready_with_ring(event_bus, ring_buffer):
    engine = WakeWordEngine(event_bus, ring_buffer=ring_buffer)
    received = []

    async def on_ready(ev):
        received.append(ev)

    event_bus.subscribe("voice.ready", on_ready)
    await engine.start()

    assert len(received) == 1
    assert received[0].payload["has_ring_buffer"] is True
    assert engine.has_ring_buffer is True
    assert engine.ring_buffer is ring_buffer
    assert engine.wake_phrase == "Hola Helix"

    await engine.stop()


# ── 3. Energy VAD Wake Word Detection Pipeline ──────────────────────

@pytest.mark.asyncio
async def test_energy_wake_word_detection(event_bus, ring_buffer):
    os.environ["HELIX_WAKE_WORD_BACKEND"] = "energy_vad"
    os.environ["HELIX_WAKE_WORD_THRESHOLD"] = "0.2"
    os.environ["HELIX_WAKE_WORD_CHUNK_DURATION"] = "0.2"

    engine = WakeWordEngine(event_bus, ring_buffer=ring_buffer)
    wake_events = []

    async def on_wake(ev):
        wake_events.append(ev)

    event_bus.subscribe("voice.wake", on_wake)
    await engine.start()

    # Trigger listen loop via sleep state
    await engine._handle_state_change(HelixEvent(source="test", event_type="system.state.change", payload={"state": "sleep"}))
    assert engine.is_listening is True

    # 1. Write silent audio (RMS ~ 0.0) -> should not trigger wake
    silence = np.zeros(3200, dtype=np.float32)
    ring_buffer.write(silence)
    await asyncio.sleep(0.15)
    assert len(wake_events) == 0

    # 2. Write loud audio pulse (amplitude 0.6 > threshold 0.2)
    loud_pulse = np.ones(3200, dtype=np.float32) * 0.6
    ring_buffer.write(loud_pulse)
    await asyncio.sleep(0.2)

    assert len(wake_events) == 1
    assert wake_events[0].payload["phrase"] == "Hola Helix"
    assert wake_events[0].payload["confidence"] > 0.5
    assert engine.is_listening is False  # paused after detection

    await engine.stop()


# ── 4. Programmatic Wake Word Trigger ───────────────────────────────

@pytest.mark.asyncio
async def test_simulate_wake_word(event_bus):
    engine = WakeWordEngine(event_bus)
    wake_events = []

    async def on_wake(ev):
        wake_events.append(ev)

    event_bus.subscribe("voice.wake", on_wake)
    await engine.start()

    await engine.simulate_wake(phrase="Hola Helix", confidence=0.98)
    assert len(wake_events) == 1
    assert wake_events[0].payload["phrase"] == "Hola Helix"
    assert wake_events[0].payload["confidence"] == 0.98
    assert wake_events[0].payload["simulated"] is True

    await engine.stop()


# ── 5. ECS Integration with voice.wake Event ────────────────────────

@pytest.mark.asyncio
async def test_ecs_transitions_to_listening_on_wake_word(event_bus):
    ecs = ExecutiveControlSystem(event_bus)
    await ecs.start()

    # ECS starts in IDLE
    assert ecs.get_state().current_state == ExecutiveState.IDLE

    # Publish voice.wake event
    await event_bus.publish_event(
        source="wake_word_engine",
        event_type="voice.wake",
        payload={"phrase": "Hola Helix", "confidence": 0.95},
    )
    await asyncio.sleep(0.05)

    # ECS must have transitioned to LISTENING
    assert ecs.get_state().current_state == ExecutiveState.LISTENING
    assert any("Wake phrase recognized" in t["reason"] for t in ecs.get_state().recent_transitions)

    await ecs.stop()


# ── 6. SelfModelEngine Integration ──────────────────────────────────

@pytest.mark.asyncio
async def test_self_model_tracks_wake_word(event_bus):
    self_model = SelfModelEngine(event_bus)
    await self_model.start()

    assert self_model.get_state().engines.listening_state is False

    await event_bus.publish_event(
        source="wake_word_engine",
        event_type="voice.wake",
        payload={"phrase": "Hola Helix"},
    )
    await asyncio.sleep(0.05)

    assert self_model.get_state().engines.listening_state is True

    await self_model.stop()


# ── 7. VoiceEngine & WakeWordEngine Shared Buffer Pipeline ──────────

@pytest.mark.asyncio
async def test_shared_ring_buffer_voice_pipeline(event_bus):
    voice = VoiceEngine(event_bus)
    wake = WakeWordEngine(event_bus, ring_buffer=voice.ring_buffer)

    await voice.start()
    await wake.start()

    assert wake.ring_buffer is voice.ring_buffer

    # Simulate wake word
    wake_confirmed = []
    async def on_wake_confirmed(ev):
        wake_confirmed.append(ev)

    event_bus.subscribe("voice.wake.confirmed", on_wake_confirmed)

    await wake.simulate_wake()
    await asyncio.sleep(0.1)

    assert len(wake_confirmed) == 1

    await wake.stop()
    await voice.stop()


# ── 8. REST API Wake Word Status & Simulation Endpoints ─────────────

def test_wake_word_api_endpoints():
    from fastapi.testclient import TestClient
    from api.main import app
    from foundation.auth import get_or_create_auth_token

    token = get_or_create_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        # 1. GET /voice/wake-status
        resp = client.get("/voice/wake-status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "backend" in data
        assert "wake_phrase" in data
        assert data["wake_phrase"] == "Hola Helix"

        # 2. POST /voice/wake/simulate
        sim_resp = client.post("/voice/wake/simulate", json={"phrase": "Hola Helix", "confidence": 0.99}, headers=headers)
        assert sim_resp.status_code == 200
        sim_data = sim_resp.json()
        assert sim_data["status"] == "triggered"
        assert sim_data["phrase"] == "Hola Helix"
