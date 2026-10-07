import os
import subprocess
import sys
from pathlib import Path


def test_scripts_package_imports_when_invoked_from_scripts_directory():
    repo_root = Path(__file__).resolve().parents[2]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = str(repo_root)
    result = subprocess.run(
        [sys.executable, "-c", "import scripts.start_all"],
        cwd=repo_root / "scripts",
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
