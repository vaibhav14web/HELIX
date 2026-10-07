import pytest
import json
from pathlib import Path

from foundation.security.model_integrity import (
    calculate_sha256,
    verify_model_integrity,
    load_model_manifest,
    ModelIntegrityError,
)


def test_calculate_sha256(tmp_path):
    test_file = tmp_path / "dummy_model.bin"
    test_file.write_bytes(b"HELIX model test bytes 12345")

    computed_hash = calculate_sha256(test_file)
    assert isinstance(computed_hash, str)
    assert len(computed_hash) == 64  # SHA-256 hex string length


def test_verify_model_integrity_success(tmp_path):
    test_file = tmp_path / "model.gguf"
    content = b"valid model data"
    test_file.write_bytes(content)

    real_hash = calculate_sha256(test_file)
    result = verify_model_integrity(test_file, expected_hash=real_hash)
    assert result == real_hash


def test_verify_model_integrity_mismatch_throws_loudly(tmp_path):
    test_file = tmp_path / "corrupted_model.gguf"
    test_file.write_bytes(b"tampered content")

    bad_hash = "a" * 64
    with pytest.raises(ModelIntegrityError) as exc_info:
        verify_model_integrity(test_file, expected_hash=bad_hash)

    assert "SECURITY FAILURE" in str(exc_info.value)
    assert "corrupted_model.gguf" in str(exc_info.value)


def test_load_manifest_and_verify(tmp_path):
    model_file = tmp_path / "qwen.gguf"
    model_file.write_bytes(b"model data for manifest test")
    real_hash = calculate_sha256(model_file)

    manifest_file = tmp_path / "manifest.json"
    manifest_data = {
        "qwen.gguf": {
            "path": str(model_file),
            "sha256": real_hash
        }
    }
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    manifest = load_model_manifest(manifest_file)
    assert "qwen.gguf" in manifest
    assert manifest["qwen.gguf"] == real_hash

    # Verify model with manifest
    verified_hash = verify_model_integrity(model_file, manifest_path=manifest_file)
    assert verified_hash == real_hash
