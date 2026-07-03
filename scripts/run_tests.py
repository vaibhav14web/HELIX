import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def main():
    print("Running HELIX test suite...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v"],
        cwd=str(ROOT),
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
