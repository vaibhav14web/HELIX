import pytest

from foundation.event_bus.event_bus import EventBus
from foundation.permission_manager.permission_manager import PermissionManager


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def manager(event_bus):
    m = PermissionManager(event_bus)
    return m


@pytest.mark.asyncio
async def test_request_creates_pending(event_bus, manager):
    await manager.start()
    req = await manager.request(
        action="open_browser",
        reasoning="User asked to open Chrome",
        source_module="action_engine",
    )
    assert req.status == "pending"
    assert req.id is not None
    assert len(manager.pending_requests) == 1
    await manager.stop()


@pytest.mark.asyncio
async def test_grant_approves_request(event_bus, manager):
    await manager.start()
    req = await manager.request("send_email", "User wants to reply")
    assert req.status == "pending"

    await event_bus.publish_event(
        source="test",
        event_type="permission.grant",
        payload={"id": req.id},
    )

    assert req.status == "approved"
    assert req.decided_at is not None
    assert len(manager.pending_requests) == 0
    await manager.stop()


@pytest.mark.asyncio
async def test_deny_rejects_request(event_bus, manager):
    await manager.start()
    req = await manager.request("delete_file", "Cleanup old file", risks=["Data loss"])
    assert req.status == "pending"

    await event_bus.publish_event(
        source="test",
        event_type="permission.deny",
        payload={"id": req.id},
    )

    assert req.status == "denied"
    assert req.decided_at is not None
    assert len(manager.pending_requests) == 0
    await manager.stop()


@pytest.mark.asyncio
async def test_request_publishes_event(event_bus, manager):
    await manager.start()

    received = []

    async def capture(event):
        received.append(event)

    event_bus.subscribe("permission.requested", capture)

    await manager.request(
        action="read_file",
        reasoning="Need to open document",
        resources=["doc.txt"],
    )

    assert len(received) == 1
    assert received[0].payload["action"] == "read_file"
    assert received[0].payload["resources"] == ["doc.txt"]
    await manager.stop()


@pytest.mark.asyncio
async def test_auto_approve_pattern(event_bus, manager):
    await manager.start()
    await event_bus.publish_event(
        source="test",
        event_type="permission.auto_approve.add",
        payload={"pattern": "read_"},
    )

    req = await manager.request("read_file", "Auto approve test")
    assert req.status == "approved"
    assert len(manager.pending_requests) == 0
    await manager.stop()


@pytest.mark.asyncio
async def test_grant_via_event(event_bus, manager):
    await manager.start()
    req = await manager.request("test_action", "Test via event")

    await event_bus.publish_event(
        source="test",
        event_type="permission.grant",
        payload={"id": req.id},
    )

    assert req.status == "approved"
    assert len(req.benefits) == 0
    await manager.stop()
