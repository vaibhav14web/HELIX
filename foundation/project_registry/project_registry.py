import os
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

logger = logging.getLogger("helix.project_registry")


@dataclass
class ProjectDescriptor:
    project_id: str
    name: str
    root_path: str
    is_git_repo: bool = False
    current_branch: str | None = None
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    last_modified: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProjectRegistry:
    def __init__(self, search_paths: list[str] | None = None):
        self._projects: dict[str, ProjectDescriptor] = {}
        self._search_paths = search_paths or [
            r"c:\Users\vaibh\OneDrive\Documents",
            r"C:\Users\vaibh\Documents",
        ]
        self._scan_workspaces()

    def _scan_workspaces(self) -> None:
        # Pre-seed current HELIX workspace
        helix_path = r"c:\Users\vaibh\OneDrive\Documents\HELIX-main\HELIX-main"
        if os.path.exists(helix_path):
            self._projects["helix-main"] = ProjectDescriptor(
                project_id="helix-main",
                name="HELIX-main",
                root_path=helix_path,
                is_git_repo=os.path.exists(os.path.join(helix_path, ".git")),
                current_branch="main",
                languages=["Python", "TypeScript"],
                frameworks=["FastAPI", "Next.js"],
            )

        for base_path in self._search_paths:
            if os.path.exists(base_path):
                self._scan_folder(Path(base_path))

    def _scan_folder(self, base_dir: Path) -> None:
        try:
            for item in base_dir.iterdir():
                if item.is_dir():
                    is_git = (item / ".git").exists()
                    has_py = any(item.glob("*.py")) or (item / "pyproject.toml").exists()
                    has_js = (item / "package.json").exists()
                    if is_git or has_py or has_js:
                        pid = item.name.lower()
                        langs = []
                        fworks = []
                        if has_py:
                            langs.append("Python")
                        if has_js:
                            langs.append("TypeScript/JavaScript")
                            fworks.append("Node.js")
                        proj = ProjectDescriptor(
                            project_id=pid,
                            name=item.name,
                            root_path=str(item.resolve()),
                            is_git_repo=is_git,
                            languages=langs,
                            frameworks=fworks,
                        )
                        self._projects[pid] = proj
        except Exception as e:
            logger.debug("Project scan folder skipped for %s: %s", base_dir, e)

    def resolve_project(self, query: str) -> ProjectDescriptor | None:
        clean = query.strip().lower()
        if clean in self._projects:
            return self._projects[clean]

        for pid, proj in self._projects.items():
            if clean in pid or pid in clean or clean in proj.name.lower():
                return proj
        return None

    def list_projects(self) -> list[dict[str, Any]]:
        return [proj.to_dict() for proj in self._projects.values()]
