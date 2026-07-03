import os
import tempfile
from pathlib import Path

import pytest

from foundation.storage_manager.storage_manager import StorageManager


@pytest.fixture
def storage():
    return StorageManager()


@pytest.mark.asyncio
async def test_runtime_path_creates_dir(storage):
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HELIX_RUNTIME_PATH"] = str(Path(tmp) / "runtime")
        s = StorageManager()
        await s.start()
        path = s.runtime("subdir", "nested")
        assert path.exists()
        assert path.name == "nested"
        await s.stop()


@pytest.mark.asyncio
async def test_cold_path_creates_if_available(storage):
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HELIX_COLD_PATH"] = str(Path(tmp) / "cold")
        os.environ["HELIX_COLD_AVAILABLE"] = "true"
        s = StorageManager()
        await s.start()
        path = s.cold("logs")
        assert path.exists()
        await s.stop()


@pytest.mark.asyncio
async def test_cold_path_not_created_if_unavailable(storage):
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HELIX_COLD_PATH"] = str(Path(tmp) / "cold")
        os.environ["HELIX_COLD_AVAILABLE"] = "false"
        s = StorageManager()
        await s.start()
        path = s.cold("logs")
        assert not path.exists()
        await s.stop()


@pytest.mark.asyncio
async def test_cold_available_property(storage):
    os.environ["HELIX_COLD_AVAILABLE"] = "true"
    s = StorageManager()
    await s.start()
    assert s.cold_available is True
    await s.stop()


@pytest.mark.asyncio
async def test_cold_unavailable_property(storage):
    os.environ["HELIX_COLD_AVAILABLE"] = "false"
    s = StorageManager()
    await s.start()
    assert s.cold_available is False
    await s.stop()
