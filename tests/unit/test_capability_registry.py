from action.capability_registry.capability_registry import CapabilityRegistry, CapabilityDescriptor


def test_capability_registry_defaults():
    registry = CapabilityRegistry()
    caps = registry.list_all()
    assert len(caps) >= 5

    assert registry.is_action_supported("launch_app") is True
    assert registry.is_action_supported("unknown_action") is False


def test_capability_registry_custom_registration():
    registry = CapabilityRegistry()
    custom_cap = CapabilityDescriptor(
        id="browser_automation",
        name="Playwright Browser Engine",
        description="Automates Web interactions.",
        supported_actions=["navigate", "click", "scrape"],
        risk_level="medium",
    )
    registry.register(custom_cap)

    assert registry.get("browser_automation") is not None
    assert registry.is_action_supported("scrape") is True
