import hashlib
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("helix.security.model_integrity")

_DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parents[2] / "config" / "model_manifest.json"


class ModelIntegrityError(RuntimeError):
    """Raised when a model file's hash does not match the pinned SHA-256 hash."""
    pass


def calculate_sha256(file_path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Calculate SHA-256 hash of a file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Model file not found: {path}")

    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest().lower()


def load_model_manifest(manifest_path: str | Path | None = None) -> dict[str, str]:
    """Load pinned model SHA-256 hashes from manifest file."""
    path = Path(manifest_path or os.getenv("HELIX_MODEL_MANIFEST", str(_DEFAULT_MANIFEST_PATH)))
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        manifest = {}
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict) and "sha256" in v:
                    manifest[k.lower()] = v["sha256"].lower()
                    if "path" in v:
                        manifest[str(Path(v["path"])).lower()] = v["sha256"].lower()
                elif isinstance(v, str):
                    manifest[k.lower()] = v.lower()
        return manifest
    except Exception as e:
        logger.warning("Failed to load model manifest at %s: %s", path, e)
    return {}


def verify_model_integrity(
    model_path: str | Path,
    expected_hash: str | None = None,
    manifest_path: str | Path | None = None,
    strict: bool = True
) -> str:
    """Verify SHA-256 hash of a model file against pinned hash or manifest.
    
    Raises ModelIntegrityError loudly on hash mismatch.
    """
    path = Path(model_path)
    if not path.exists():
        raise FileNotFoundError(f"Model file does not exist: {path}")

    calculated_hash = calculate_sha256(path)

    if not expected_hash:
        manifest = load_model_manifest(manifest_path)
        expected_hash = (
            manifest.get(str(path).lower())
            or manifest.get(path.name.lower())
            or manifest.get(path.stem.lower())
        )

    if expected_hash:
        expected_hash = expected_hash.strip().lower()
        if expected_hash and calculated_hash != expected_hash:
            raise ModelIntegrityError(
                f"SECURITY FAILURE: Model integrity check failed for '{path.name}'! "
                f"Calculated SHA-256 ({calculated_hash}) does not match pinned hash ({expected_hash}). "
                f"Refusing to load untrusted or tampered model."
            )
        logger.info("Model integrity verified successfully for %s", path.name)
    else:
        if strict and os.getenv("HELIX_STRICT_MODEL_VERIFICATION", "").lower() in ("true", "1", "yes"):
            raise ModelIntegrityError(
                f"SECURITY FAILURE: No pinned SHA-256 hash found for '{path.name}' under strict model verification mode."
            )
        logger.info("No pinned hash found for %s. Calculated SHA-256: %s", path.name, calculated_hash)

    return calculated_hash
