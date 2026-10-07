import os
import sys
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

logger = logging.getLogger("helix.app_discovery")


@dataclass
class DiscoveredApp:
    name: str
    executable_name: str
    executable_path: str
    source: str = "start_menu"  # start_menu | registry | program_files | path | win32
    aliases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ApplicationDiscoveryEngine:
    def __init__(self):
        self._indexed_apps: dict[str, DiscoveredApp] = {}
        self._scan_and_index()

    def _scan_and_index(self) -> None:
        # Pre-seed common windows software
        seed_apps = [
            DiscoveredApp("Google Chrome", "chrome.exe", r"C:\Program Files\Google\Chrome\Application\chrome.exe", "program_files", ["chrome", "google chrome", "browser"]),
            DiscoveredApp("Microsoft Edge", "msedge.exe", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "program_files", ["edge", "microsoft edge"]),
            DiscoveredApp("Visual Studio Code", "code.exe", r"C:\Users\vaibh\AppData\Local\Programs\Microsoft VS Code\Code.exe", "program_files", ["vscode", "vs code", "code"]),
            DiscoveredApp("Notepad", "notepad.exe", r"C:\Windows\System32\notepad.exe", "win32", ["notepad", "editor", "text editor"]),
            DiscoveredApp("Calculator", "calc.exe", r"C:\Windows\System32\calc.exe", "win32", ["calc", "calculator"]),
            DiscoveredApp("File Explorer", "explorer.exe", r"C:\Windows\explorer.exe", "win32", ["explorer", "file explorer", "my computer"]),
            DiscoveredApp("Command Prompt", "cmd.exe", r"C:\Windows\System32\cmd.exe", "win32", ["cmd", "command prompt", "terminal"]),
            DiscoveredApp("Windows Terminal", "wt.exe", r"C:\Users\vaibh\AppData\Local\Microsoft\WindowsApps\wt.exe", "win32", ["wt", "windows terminal", "terminal"]),
        ]
        for app in seed_apps:
            self._add_to_index(app)

        # Dynamic scan of Program Files
        self._scan_directory(Path(r"C:\Program Files"), depth=2)
        self._scan_directory(Path(r"C:\Program Files (x86)"), depth=2)

    def _scan_directory(self, base_dir: Path, depth: int) -> None:
        if not base_dir.exists():
            return
        try:
            for item in base_dir.iterdir():
                if item.is_dir() and depth > 0:
                    try:
                        for subitem in item.iterdir():
                            if subitem.is_file() and subitem.suffix.lower() == ".exe":
                                app_name = item.name
                                exe_name = subitem.name.lower()
                                app = DiscoveredApp(
                                    name=app_name,
                                    executable_name=exe_name,
                                    executable_path=str(subitem),
                                    source="program_files",
                                    aliases=[app_name.lower(), exe_name.replace(".exe", "")],
                                )
                                self._add_to_index(app)
                    except Exception:
                        continue
        except Exception as e:
            logger.debug("Scan directory failed for %s: %s", base_dir, e)

    def _add_to_index(self, app: DiscoveredApp) -> None:
        self._indexed_apps[app.name.lower()] = app
        for alias in app.aliases:
            self._indexed_apps[alias.lower()] = app

    def resolve_app(self, query: str) -> DiscoveredApp | None:
        clean = query.strip().lower()
        if clean in self._indexed_apps:
            return self._indexed_apps[clean]

        # Fuzzy match
        for key, app in self._indexed_apps.items():
            if clean in key or key in clean:
                return app
        return None

    def list_apps(self) -> list[dict[str, Any]]:
        unique = {app.executable_path: app for app in self._indexed_apps.values()}
        return [app.to_dict() for app in unique.values()]
