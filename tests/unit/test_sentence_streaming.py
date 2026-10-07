import pytest
import asyncio
from foundation.event_bus.event_bus import EventBus, HelixEvent
from core_ai.conversation_engine.conversation_engine import ConversationEngine


@pytest.mark.asyncio
async def test_sentence_streaming_tts():
    event_bus = EventBus()
    conv = ConversationEngine(event_bus=event_bus)
    await conv.start()

    tts_events = []

    async def on_tts(event: HelixEvent):
        tts_events.append(event.payload.get("text"))

    event_bus.subscribe("voice.tts", on_tts)

    corr_id = "test-corr-1"
    # Stream tokens forming sentence 1
    tokens_s1 = ["Hello", " ", "there!", " "]
    for t in tokens_s1:
        await event_bus.publish_event(
            source="llm_engine",
            event_type="llm.token",
            payload={"token": t, "session_id": "test"},
            correlation_id=corr_id,
        )

    # Check sentence 1 emitted immediately
    assert len(tts_events) == 1
    assert tts_events[0] == "Hello there!"

    # Stream sentence 2
    tokens_s2 = ["I", " ", "am", " ", "HELIX.", " "]
    for t in tokens_s2:
        await event_bus.publish_event(
            source="llm_engine",
            event_type="llm.token",
            payload={"token": t, "session_id": "test"},
            correlation_id=corr_id,
        )

    assert len(tts_events) == 2
    assert tts_events[1] == "I am HELIX."

    await conv.stop()
