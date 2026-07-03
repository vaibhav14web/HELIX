import os
import re
import asyncio
import logging
from typing import Any

from foundation.event_bus.event_bus import EventBus, HelixEvent

logger = logging.getLogger("helix.orchestrator")

_STOP_PATTERNS = [
    re.compile(r"^(stop|stop it|stop now|stop listening|stop right there)$", re.IGNORECASE),
    re.compile(r"^(cancel|cancel that|cancel the command)$", re.IGNORECASE),
    re.compile(r"^(shut up|shut up please|be quiet|quiet)$", re.IGNORECASE),
    re.compile(r"^(enough|that.s enough|never mind|nevermind)$", re.IGNORECASE),
    re.compile(r"^(go away|leave me alone|forget it)$", re.IGNORECASE),
]


class Orchestrator:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._state = os.getenv("HELIX_SYSTEM_STATE", "sleep")
        self._conversation_timeout = int(os.getenv("HELIX_CONVERSATION_TIMEOUT", "60"))
        self._last_activity: float = 0
        self._subscriptions: list[str] = []
        self._event_handler_map: dict[str, Any] = {}
        self._watchdog_task: asyncio.Task | None = None
        self._interrupt_cooldown: float = 0

    async def start(self) -> None:
        self._event_handler_map = {
            "voice.wake.confirmed": self._on_wake_confirmed,
            "voice.listen.start": self._on_listen_start,
            "voice.listen.complete": self._on_listen_complete,
            "llm.generation.start": self._on_llm_start,
            "llm.generation.complete": self._on_llm_complete,
            "voice.tts.start": self._on_tts_start,
            "voice.tts.complete": self._on_tts_complete,
            "voice.interrupt": self._on_interrupt,
            "voice.error": self._on_voice_error,
            "llm.generation.error": self._on_llm_error,
            "permission.granted": self._on_permission_granted,
            "permission.denied": self._on_permission_denied,
            "system.state.request": self._on_state_request,
        }
        for event_type, handler in self._event_handler_map.items():
            self._event_bus.subscribe(event_type, handler)
        self._subscriptions = list(self._event_handler_map.keys())

        self._last_activity = asyncio.get_running_loop().time()
        self._watchdog_task = asyncio.create_task(self._watchdog())

        await self._publish_state("startup")
        logger.info("Orchestrator started (state=%s)", self._state)

    async def stop(self) -> None:
        for event_type, handler in self._event_handler_map.items():
            self._event_bus.unsubscribe(event_type, handler)
        self._subscriptions.clear()

        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            self._watchdog_task = None

        logger.info("Orchestrator stopped")

    @property
    def current_state(self) -> str:
        return self._state

    async def _publish_state(self, reason: str) -> None:
        await self._event_bus.publish_event(
            source="orchestrator",
            event_type="system.state.change",
            payload={"state": self._state, "reason": reason},
        )

    async def _transition(self, new_state: str, reason: str) -> None:
        if new_state == self._state:
            return
        old_state = self._state
        self._state = new_state
        self._last_activity = asyncio.get_running_loop().time()
        await self._publish_state(reason)
        logger.info("State transition: %s -> %s (%s)", old_state, new_state, reason)

    async def _on_wake_confirmed(self, event: HelixEvent) -> None:
        if self._state not in ("sleep", "idle"):
            logger.debug("Wake ignored: in state %s", self._state)
            return
        await self._transition("listening", "wake_word_detected")

    async def _on_listen_start(self, event: HelixEvent) -> None:
        self._last_activity = asyncio.get_running_loop().time()

    async def _on_listen_complete(self, event: HelixEvent) -> None:
        self._last_activity = asyncio.get_running_loop().time()
        text = event.payload.get("text", "")
        session_id = event.payload.get("session_id", "default")
        if not text.strip():
            asyncio.create_task(self._delayed_return_to_sleep())
            return

        if self._is_stop_command(text):
            logger.info("Stop command detected locally: %r", text)
            await self._event_bus.publish_event(
                source="orchestrator",
                event_type="voice.interrupt",
                payload={"session_id": session_id},
            )
            await self._event_bus.publish_event(
                source="orchestrator",
                event_type="voice.shutdown",
                payload={"session_id": session_id},
            )
            await self._transition("sleep", "stop_command")
            return

        await self._transition("processing", "transcription_complete")
        await self._event_bus.publish_event(
            source="orchestrator",
            event_type="conversation.user_message",
            payload={"text": text, "session_id": session_id},
        )

    @staticmethod
    def _is_stop_command(text: str) -> bool:
        stripped = text.strip().lower().rstrip(".!?")
        return any(p.match(stripped) for p in _STOP_PATTERNS)

    async def _on_llm_start(self, event: HelixEvent) -> None:
        await self._transition("processing", "llm_generation_started")

    async def _on_llm_complete(self, event: HelixEvent) -> None:
        text = event.payload.get("response", "")
        session_id = event.payload.get("session_id", "default")
        self._last_activity = asyncio.get_running_loop().time()

        if text:
            await self._transition("responding", "llm_response_ready")
            await self._event_bus.publish_event(
                source="orchestrator",
                event_type="voice.tts",
                payload={"text": text, "session_id": session_id},
            )
        else:
            asyncio.create_task(self._delayed_return_to_sleep())

    async def _on_tts_start(self, event: HelixEvent) -> None:
        await self._transition("responding", "tts_started")

    async def _on_tts_complete(self, event: HelixEvent) -> None:
        self._last_activity = asyncio.get_running_loop().time()
        await self._transition("idle", "tts_completed")
        asyncio.create_task(self._delayed_return_to_sleep())

    async def _on_interrupt(self, event: HelixEvent) -> None:
        now = asyncio.get_running_loop().time()
        if now - self._interrupt_cooldown < 0.3:
            return
        self._interrupt_cooldown = now
        logger.info("Interrupt received")
        if self._state != "sleep":
            await self._transition("idle", "user_interrupt")

    async def _on_voice_error(self, event: HelixEvent) -> None:
        logger.warning("Voice error: %s", event.payload.get("error"))
        asyncio.create_task(self._delayed_return_to_sleep())

    async def _on_llm_error(self, event: HelixEvent) -> None:
        logger.warning("LLM error: %s", event.payload.get("error"))
        asyncio.create_task(self._delayed_return_to_sleep())

    async def _on_permission_granted(self, event: HelixEvent) -> None:
        self._last_activity = asyncio.get_running_loop().time()

    async def _on_permission_denied(self, event: HelixEvent) -> None:
        asyncio.create_task(self._delayed_return_to_sleep())

    async def _on_state_request(self, event: HelixEvent) -> None:
        requested = event.payload.get("state", "")
        reason = event.payload.get("reason", "external_request")
        if requested in ("sleep", "conversation", "background", "idle", "listening"):
            await self._transition(requested, reason)

    async def _delayed_return_to_sleep(self) -> None:
        await asyncio.sleep(5)
        if self._state in ("processing", "responding", "idle", "listening"):
            await self._transition("sleep", "idle_timeout")

    async def _watchdog(self) -> None:
        try:
            while True:
                await asyncio.sleep(10)
                now = asyncio.get_running_loop().time()
                idle = now - self._last_activity

                if self._state in ("processing", "responding", "listening") and idle > self._conversation_timeout:
                    await self._transition("sleep", "conversation_timeout")
        except asyncio.CancelledError:
            pass
