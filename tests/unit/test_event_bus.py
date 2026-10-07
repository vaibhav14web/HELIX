import pytest
from foundation.event_bus.event_bus import EventBus, HelixEvent


@pytest.mark.asyncio
async def test_publish_and_subscribe():
    bus = EventBus()
    received = []

    async def handler(event: HelixEvent):
        received.append(event)

    bus.subscribe("test.event", handler)
    event = HelixEvent(source="test", event_type="test.event", payload={"msg": "hello"})
    await bus.publish(event)

    assert len(received) == 1
    assert received[0].payload["msg"] == "hello"


@pytest.mark.asyncio
async def test_unsubscribe():
    bus = EventBus()
    received = []

    async def handler(event: HelixEvent):
        received.append(event)

    bus.subscribe("test.event", handler)
    bus.unsubscribe("test.event", handler)
    event = HelixEvent(source="test", event_type="test.event")
    await bus.publish(event)

    assert len(received) == 0


@pytest.mark.asyncio
async def test_publish_event_helper():
    bus = EventBus()
    received = []

    async def handler(event: HelixEvent):
        received.append(event)

    bus.subscribe("test.event", handler)
    await bus.publish_event(source="test", event_type="test.event", payload={"key": "val"})

    assert len(received) == 1
    assert received[0].source == "test"
    assert received[0].payload["key"] == "val"
    assert received[0].correlation_id is not None


@pytest.mark.asyncio
async def test_multiple_subscribers():
    bus = EventBus()
    received1 = []
    received2 = []

    async def handler1(event: HelixEvent):
        received1.append(event)

    async def handler2(event: HelixEvent):
        received2.append(event)

    bus.subscribe("test.event", handler1)
    bus.subscribe("test.event", handler2)
    event = HelixEvent(source="test", event_type="test.event")
    await bus.publish(event)

    assert len(received1) == 1
    assert len(received2) == 1


@pytest.mark.asyncio
async def test_no_subscribers_does_not_crash():
    bus = EventBus()
    event = HelixEvent(source="test", event_type="nonexistent.event")
    await bus.publish(event)


@pytest.mark.asyncio
async def test_event_defaults():
    event = HelixEvent(source="test_module", event_type="test.event")
    assert event.event_id is not None
    assert event.timestamp is not None
    assert event.priority == 1
    assert event.payload == {}
    assert event.correlation_id is not None


@pytest.mark.asyncio
async def test_fault_isolation_failing_handler():
    bus = EventBus()
    received_good = []
    received_errors = []

    async def failing_handler(event: HelixEvent):
        raise ValueError("Deliberate handler failure")

    async def good_handler(event: HelixEvent):
        received_good.append(event)

    async def error_listener(event: HelixEvent):
        received_errors.append(event)

    bus.subscribe("test.fault", failing_handler)
    bus.subscribe("test.fault", good_handler)
    bus.subscribe("module.error", error_listener)

    # Publishing must not raise an exception even though failing_handler throws ValueError
    event = HelixEvent(source="test", event_type="test.fault", payload={"data": 123})
    await bus.publish(event)

    # Verify good_handler executed successfully
    assert len(received_good) == 1
    assert received_good[0].payload["data"] == 123

    # Verify module.error event was published
    assert len(received_errors) == 1
    assert received_errors[0].payload["original_event_type"] == "test.fault"
    assert "Deliberate handler failure" in received_errors[0].payload["error"]
    assert received_errors[0].payload["exception_type"] == "ValueError"

