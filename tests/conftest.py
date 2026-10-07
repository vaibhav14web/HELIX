import os
import tempfile
from pathlib import Path

# Ensure temporary files and pytest tmp_path use workspace data/pytest_tmp
_safe_tmp = Path(__file__).resolve().parent.parent / "data" / "pytest_tmp"
_safe_tmp.mkdir(parents=True, exist_ok=True)
os.environ["TMP"] = str(_safe_tmp)
os.environ["TEMP"] = str(_safe_tmp)
tempfile.tempdir = str(_safe_tmp)
