import os
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent


def main():
    load_dotenv(ROOT / ".env")
    sys.path.insert(0, str(ROOT))

    host = os.getenv("HELIX_API_HOST", "127.0.0.1")
    if host in ("0.0.0.0", "0"):
        host = "127.0.0.1"
    port = int(os.getenv("HELIX_API_PORT", "8000"))
    reload_enabled = os.getenv("HELIX_API_RELOAD", "true").lower() in ("true", "1", "yes")

    print(f"Starting HELIX API server on {host}:{port} ...")
    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=reload_enabled,
    )


if __name__ == "__main__":
    main()
