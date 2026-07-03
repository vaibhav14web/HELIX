import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class HelixLogger:
    def __init__(self, storage_manager: Any = None):
        self._log_path = Path(
            os.getenv("HELIX_LOG_PATH", r"F:\helix\logs")
        )
        self._level = getattr(logging, os.getenv("HELIX_LOG_LEVEL", "INFO").upper(), logging.INFO)
        self._max_size_mb = int(os.getenv("HELIX_LOG_MAX_SIZE_MB", "10"))
        self._retention_days = int(os.getenv("HELIX_LOG_RETENTION_DAYS", "30"))
        self._storage = storage_manager
        self._file: Path | None = None
        self._python_logger = logging.getLogger("helix")
        self._python_logger.setLevel(self._level)

    async def start(self) -> None:
        try:
            self._log_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            fallback = Path.cwd() / "backend" / "data" / "logs"
            self._python_logger.warning(
                "Log path %s is unavailable (%s); using %s",
                self._log_path,
                exc,
                fallback,
            )
            fallback.mkdir(parents=True, exist_ok=True)
            self._log_path = fallback
        self._rotate_if_needed()

        handler = logging.FileHandler(
            self._log_path / "helix.log", encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        self._python_logger.addHandler(handler)

        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        self._python_logger.addHandler(console)

        self._python_logger.info("Logger initialized: %s", self._log_path)

    async def stop(self) -> None:
        for handler in self._python_logger.handlers[:]:
            handler.close()
            self._python_logger.removeHandler(handler)

    def debug(self, msg: str, **meta: Any) -> None:
        self._python_logger.debug(msg, extra=self._meta(meta))

    def info(self, msg: str, **meta: Any) -> None:
        self._python_logger.info(msg, extra=self._meta(meta))

    def warning(self, msg: str, **meta: Any) -> None:
        self._python_logger.warning(msg, extra=self._meta(meta))

    def error(self, msg: str, **meta: Any) -> None:
        self._python_logger.error(msg, extra=self._meta(meta))

    def exception(self, msg: str, **meta: Any) -> None:
        self._python_logger.exception(msg, extra=self._meta(meta))

    def jsonl(self, event: str, **data: Any) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **data,
        }
        log_file = self._log_path / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        self._rotate_if_needed()

    def _meta(self, extra: dict) -> dict:
        return {"_meta": extra}

    def _rotate_if_needed(self) -> None:
        for f in sorted(self._log_path.glob("*.log")):
            if f.stat().st_size > self._max_size_mb * 1024 * 1024:
                rotated = f.with_suffix(f".suffix.1.log")
                f.rename(rotated)

        cutoff = datetime.now(timezone.utc).timestamp() - self._retention_days * 86400
        for f in self._log_path.glob("*.log*"):
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
