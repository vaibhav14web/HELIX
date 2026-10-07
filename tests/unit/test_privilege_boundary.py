import pytest
import xml.etree.ElementTree as ET
from pathlib import Path

from foundation.security.privilege import is_admin, check_privilege_boundary


def test_is_admin_returns_bool():
    result = is_admin()
    assert isinstance(result, bool)


def test_check_privilege_boundary_structure():
    status = check_privilege_boundary()
    assert "is_admin" in status
    assert "execution_level" in status
    assert "restricted" in status
    assert isinstance(status["restricted"], bool)


def test_helix_manifest_privilege_level():
    repo_root = Path(__file__).resolve().parents[2]
    manifest_path = repo_root / "deployment" / "helix.manifest"
    assert manifest_path.exists()

    tree = ET.parse(manifest_path)
    root = tree.getroot()

    manifest_str = manifest_path.read_text(encoding="utf-8")
    assert 'requestedExecutionLevel level="asInvoker"' in manifest_str
    assert 'requireAdministrator' not in manifest_str
