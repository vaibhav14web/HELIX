import os
import json
import tempfile
from pathlib import Path

import pytest

from foundation.logger.logger import HelixLogger


@pytest.fixture
def log_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


@pytest.mark.asyncio
async def test_jsonl_writes_entry(log_path):
    os.environ["HELIX_LOG_PATH"] = log_path
    logger = HelixLogger()
    await logger.start()
    logger.jsonl("test_event", key="value", number=42)
    await logger.stop()

    files = list(Path(log_path).glob("*.jsonl"))
    assert len(files) == 1
    with open(files[0]) as f:
        entry = json.loads(f.readline())
    assert entry["event"] == "test_event"
    assert entry["key"] == "value"
    assert entry["number"] == 42


@pytest.mark.asyncio
async def test_info_logs_to_file(log_path):
    os.environ["HELIX_LOG_PATH"] = log_path
    logger = HelixLogger()
    await logger.start()
    logger.info("Test info message")
    await logger.stop()

    log_file = Path(log_path) / "helix.log"
    assert log_file.exists()
    content = log_file.read_text()
    assert "Test info message" in content


@pytest.mark.asyncio
async def test_error_logs_to_file(log_path):
    os.environ["HELIX_LOG_PATH"] = log_path
    logger = HelixLogger()
    await logger.start()
    logger.error("Test error message")
    await logger.stop()

    log_file = Path(log_path) / "helix.log"
    assert log_file.exists()
    content = log_file.read_text()
    assert "Test error message" in content
