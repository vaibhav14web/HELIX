import time
import json
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from foundation.event_bus.event_bus import EventBus, HelixEvent
from action.timetable_scheduler.timetable_scheduler import TimetableScheduler
from core_ai.voice_engine.voice_engine import VoiceEngine


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def scheduler(event_bus, tmp_path):
    timetable_file = tmp_path / "timetable.json"
    return TimetableScheduler(event_bus, timetable_path=timetable_file, poll_interval=0.05)


@pytest.mark.asyncio
async def test_load_and_save_timetable(scheduler, tmp_path):
    assert scheduler.load_timetable() == []

    rem = scheduler.add_reminder(text="Test Meeting", delay_seconds=120)
    assert rem["text"] == "Test Meeting"
    assert rem["triggered"] is False

    # Check disk content
    content = json.loads((tmp_path / "timetable.json").read_text(encoding="utf-8"))
    assert len(content["reminders"]) == 1
    assert content["reminders"][0]["text"] == "Test Meeting"


@pytest.mark.asyncio
async def test_reminder_due_event_triggered(scheduler, event_bus):
    received_events = []

    async def capture(event):
        received_events.append(event)

    event_bus.subscribe("reminder.due", capture)

    await scheduler.start()
    try:
        scheduler.add_reminder(text="Short Delay Task", delay_seconds=0.02)
        await asyncio.sleep(0.2)

        assert len(received_events) >= 1
        due_event = received_events[0]
        assert due_event.payload["text"] == "Short Delay Task"
        assert due_event.source == "timetable_scheduler"
    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_60_second_reminder_scheduled(scheduler, event_bus):
    received_events = []

    async def capture(event):
        received_events.append(event)

    event_bus.subscribe("reminder.due", capture)

    await scheduler.start()
    try:
        now = time.time()
        rem = scheduler.add_reminder(text="60s Reminder", delay_seconds=60)
        assert abs(rem["timestamp"] - (now + 60)) < 2.0

        # Simulate time passing by updating timestamp to past
        rem["timestamp"] = time.time() - 1
        scheduler.save_timetable()

        await asyncio.sleep(0.2)

        assert len(received_events) >= 1
        assert received_events[0].payload["text"] == "60s Reminder"
    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_add_reminder_via_event_bus(scheduler, event_bus):
    await scheduler.start()
    try:
        await event_bus.publish_event(
            source="test",
            event_type="reminder.add",
            payload={"text": "Event Added Reminder", "delay_seconds": 300},
        )
        await asyncio.sleep(0.05)

        assert len(scheduler._reminders) == 1
        assert scheduler._reminders[0]["text"] == "Event Added Reminder"
    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_voice_engine_handles_reminder_due(event_bus):
    voice = VoiceEngine(event_bus)
    await voice.start()

    tts_events = []

    async def capture_tts(event):
        tts_events.append(event)

    event_bus.subscribe("voice.tts", capture_tts)

    try:
        await event_bus.publish_event(
            source="timetable_scheduler",
            event_type="reminder.due",
            payload={"reminder_id": "rem_test123", "text": "Team Standup Meeting"},
        )
        await asyncio.sleep(0.05)

        assert len(tts_events) == 1
        assert "Reminder: Team Standup Meeting" in tts_events[0].payload["text"]
    finally:
        await voice.stop()
