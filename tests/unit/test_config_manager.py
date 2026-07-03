import os
import tempfile
from pathlib import Path

import pytest

from foundation.config_manager.config_manager import ConfigManager


@pytest.fixture
def config():
    c = ConfigManager()
    return c


@pytest.mark.asyncio
async def test_start_loads_dotenv(config):
    with tempfile.TemporaryDirectory() as tmp:
        env_file = Path(tmp) / ".env"
        env_file.write_text("HELIX_TEST_VAR=test_value_123\n")
        os.environ["HELIX_CONFIG_PATH"] = tmp
        os.environ["HELIX_TEST_VAR"] = "test_value_123"

        cfg = ConfigManager()
        await cfg.start()
        assert cfg.get("HELIX_TEST_VAR") == "test_value_123"
        del os.environ["HELIX_CONFIG_PATH"]
        del os.environ["HELIX_TEST_VAR"]
        await cfg.stop()


@pytest.mark.asyncio
async def test_get_with_default(config):
    await config.start()
    assert config.get("NONEXISTENT_KEY", "fallback") == "fallback"
    await config.stop()


@pytest.mark.asyncio
async def test_get_int(config):
    await config.start()
    os.environ["HELIX_TEST_INT"] = "42"
    assert config.get_int("HELIX_TEST_INT") == 42
    del os.environ["HELIX_TEST_INT"]
    await config.stop()


@pytest.mark.asyncio
async def test_get_bool(config):
    await config.start()
    os.environ["HELIX_TEST_BOOL"] = "true"
    assert config.get_bool("HELIX_TEST_BOOL") is True
    del os.environ["HELIX_TEST_BOOL"]
    await config.stop()


@pytest.mark.asyncio
async def test_get_path(config):
    await config.start()
    os.environ["HELIX_TEST_PATH"] = "C:\\Projects\\test"
    p = config.get_path("HELIX_TEST_PATH")
    assert isinstance(p, Path)
    assert str(p) == "C:\\Projects\\test"
    del os.environ["HELIX_TEST_PATH"]
    await config.stop()
