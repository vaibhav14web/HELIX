import pytest
from unittest.mock import AsyncMock, MagicMock
from foundation.event_bus.event_bus import EventBus, HelixEvent
from foundation.permission_manager.permission_manager import PermissionManager


@pytest.mark.asyncio
async def test_permission_wildcard_matching_and_events():
    event_bus = EventBus()
    perm_manager = PermissionManager(event_bus)
    await perm_manager.start()

    # Subscribe to permission.granted to assert event is published on auto-approve
    granted_events = []
    async def granted_handler(event: HelixEvent):
        granted_events.append(event)
    event_bus.subscribe("permission.granted", granted_handler)

    # 1. Add auto-approve pattern with wildcard
    await event_bus.publish_event(
        source="test",
        event_type="permission.auto_approve.add",
        payload={"pattern": "git *"}
    )
    # Wait a tiny bit for event loop processing
    await asyncio.sleep(0.05)

    assert "git *" in perm_manager.auto_approve_patterns

    # 2. Request action matching the wildcard
    req = await perm_manager.request(
        action="git commit -m 'test'",
        reasoning="Testing wildcard matching",
        source_module="test_module"
    )

    # Asserts
    assert req.status == "approved"
    assert len(granted_events) == 1
    assert granted_events[0].payload["id"] == req.id
    assert granted_events[0].payload["action"] == "git commit -m 'test'"
    assert granted_events[0].payload["auto_approved"] is True

    await perm_manager.stop()


@pytest.mark.asyncio
async def test_automation_permission_needed_handler():
    event_bus = EventBus()
    perm_manager = PermissionManager(event_bus)
    await perm_manager.start()

    # Publish automation.permission_needed
    custom_perm_id = "custom_12345"
    await event_bus.publish_event(
        source="automation_engine",
        event_type="automation.permission_needed",
        payload={
            "action": "run_command",
            "permission_id": custom_perm_id,
            "description": "Allow automation to run command",
        }
    )
    # Wait for loop
    await asyncio.sleep(0.05)

    # Assert it was registered as pending
    pending = perm_manager.pending_requests
    assert len(pending) == 1
    assert pending[0].id == custom_perm_id
    assert pending[0].action == "run_command"
    assert pending[0].reasoning == "Allow automation to run command"
    assert pending[0].status == "pending"

    await perm_manager.stop()


import asyncio
