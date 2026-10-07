from action.application_discovery.app_discovery_engine import ApplicationDiscoveryEngine


def test_app_discovery_seed_apps():
    engine = ApplicationDiscoveryEngine()
    chrome = engine.resolve_app("chrome")
    assert chrome is not None
    assert chrome.executable_name == "chrome.exe"

    vscode = engine.resolve_app("vs code")
    assert vscode is not None
    assert "Code.exe" in vscode.executable_path


def test_app_discovery_fuzzy_matching():
    engine = ApplicationDiscoveryEngine()
    notepad = engine.resolve_app("open notepad please")
    assert notepad is not None
    assert notepad.executable_name == "notepad.exe"
