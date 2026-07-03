import os
import logging
from pathlib import Path

logger = logging.getLogger("helix.storage_manager")


class StorageManager:
    def __init__(self):
        self._runtime_path = Path(
            os.getenv("HELIX_RUNTIME_PATH", r"F:\helix")
        )
        self._cold_path = Path(
            os.getenv("HELIX_COLD_PATH", r"F:\helix\cold")
        )
        self._cold_available = os.getenv("HELIX_COLD_AVAILABLE", "false").lower() in ("true", "1", "yes")

    async def start(self) -> None:
        try:
            self._runtime_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            fallback = Path.cwd() / "backend" / "data"
            logger.warning(
                "Runtime path %s is unavailable (%s); using %s",
                self._runtime_path,
                exc,
                fallback,
            )
            fallback.mkdir(parents=True, exist_ok=True)
            self._runtime_path = fallback
        if self._cold_available:
            try:
                self._cold_path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.warning("Cold storage path %s is unavailable: %s", self._cold_path, exc)
                self._cold_available = False

    async def stop(self) -> None:
        pass

    def runtime(self, *subdirs: str) -> Path:
        path = self._runtime_path.joinpath(*subdirs)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cold(self, *subdirs: str) -> Path:
        path = self._cold_path.joinpath(*subdirs)
        if self._cold_available:
            path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def cold_available(self) -> bool:
        return self._cold_available
