import os
import secrets
from pathlib import Path
import logging

logger = logging.getLogger("helix.auth")

_AUTH_TOKEN: str | None = None


def get_token_file_path() -> Path:
    base_dir = Path(os.getenv("HELIX_MEMORY_PATH", "./data/memory")).parent
    security_dir = base_dir / "security"
    security_dir.mkdir(parents=True, exist_ok=True)
    return security_dir / "auth_token.secret"


def get_or_create_auth_token() -> str:
    global _AUTH_TOKEN
    if _AUTH_TOKEN:
        return _AUTH_TOKEN

    env_token = os.getenv("HELIX_AUTH_TOKEN")
    if env_token and env_token.strip():
        _AUTH_TOKEN = env_token.strip()
        return _AUTH_TOKEN

    token_path = get_token_file_path()
    if token_path.exists():
        try:
            token = token_path.read_text(encoding="utf-8").strip()
            if token:
                _AUTH_TOKEN = token
                return _AUTH_TOKEN
        except Exception as e:
            logger.warning(f"Failed to read auth token file: {e}")

    new_token = secrets.token_hex(32)
    try:
        token_path.write_text(new_token, encoding="utf-8")
        logger.info(f"Generated new local auth token at {token_path}")
    except Exception as e:
        logger.warning(f"Failed to write auth token file: {e}")

    _AUTH_TOKEN = new_token
    return _AUTH_TOKEN


def verify_token(token: str | None) -> bool:
    if not token:
        return False
    expected = get_or_create_auth_token()
    return secrets.compare_digest(token.strip(), expected.strip())
