import pytest
from foundation.event_bus.event_bus import EventBus
from action.action_verification.action_verification import ActionVerificationEngine


@pytest.mark.asyncio
async def test_action_verification_file_check():
    event_bus = EventBus()
    verifier = ActionVerificationEngine(event_bus=event_bus)

    res = await verifier.verify_action(
        action_id="act-1",
        action="create_note",
        params={"path": r"c:\Users\vaibh\OneDrive\Documents\HELIX-main\HELIX-main\pyproject.toml"},
    )
    assert res.success is True
    assert res.verified_via == "file_check"
