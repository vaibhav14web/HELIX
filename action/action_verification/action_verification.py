import os
import sys
import asyncio
import logging
from dataclasses import dataclass, asdict
from typing import Any

from foundation.event_bus.event_bus import EventBus, HelixEvent

logger = logging.getLogger("helix.action_verification")


@dataclass
class VerificationResult:
    action_id: str
    success: bool
    verified_via: str  # process_check | window_check | file_check | network_check
    details: str
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ActionVerificationEngine:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus

    async def verify_action(self, action_id: str, action: str, params: dict[str, Any]) -> VerificationResult:
        start_time = asyncio.get_running_loop().time()
        result = VerificationResult(
            action_id=action_id,
            success=True,
            verified_via="file_check",
            details="Action verified successfully",
        )

        try:
            if action in ("launch_app", "start_process"):
                target = params.get("target") or params.get("app_name") or ""
                verified = await self._verify_process_running(target)
                result.success = verified
                result.verified_via = "process_check"
                result.details = f"Process {target} running verification: {verified}"

            elif action in ("create_note", "upload_file"):
                path = params.get("path") or params.get("file_path") or ""
                exists = os.path.exists(path) if path else True
                result.success = exists
                result.verified_via = "file_check"
                result.details = f"File existence check for {path}: {exists}"

        except Exception as e:
            logger.exception("Verification error for action %s", action_id)
            result.success = False
            result.details = str(e)

        result.latency_ms = round((asyncio.get_running_loop().time() - start_time) * 1000, 2)

        await self._event_bus.publish_event(
            source="action_verification",
            event_type="action.verified" if result.success else "action.failed_verification",
            payload=result.to_dict(),
        )
        return result

    async def _verify_process_running(self, target: str) -> bool:
        if not target:
            return True
        if sys.platform == "win32":
            proc = await asyncio.create_subprocess_exec(
                "tasklist", "/fi", f"IMAGENAME eq {target}*",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            return target.lower().replace(".exe", "") in stdout.decode(errors="ignore").lower()
        return True
