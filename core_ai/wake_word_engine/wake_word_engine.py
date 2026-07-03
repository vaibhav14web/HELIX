import os
import asyncio
import logging
import time
from typing import Any

from foundation.event_bus.event_bus import EventBus, HelixEvent

logger = logging.getLogger("helix.wake_word_engine")


class WakeWordEngine:
    def __init__(self, event_bus: EventBus, ring_buffer=None):
        self._event_bus = event_bus
        self._ring = ring_buffer
        self._backend = os.getenv("HELIX_WAKE_WORD_BACKEND", "mock")
        self._wake_phrase = os.getenv("HELIX_WAKE_WORD_PHRASE", "Hola Helix")
        self._model_path = os.getenv(
            "HELIX_WAKE_WORD_MODEL_PATH",
            str(__import__("pathlib").Path.cwd() / "models" / "openwakeword"),
        )
        self._threshold = float(os.getenv("HELIX_WAKE_WORD_THRESHOLD", "0.5"))
        self._sample_rate = int(os.getenv("HELIX_WAKE_WORD_SAMPLE_RATE", "16000"))
        self._chunk_duration = float(os.getenv("HELIX_WAKE_WORD_CHUNK_DURATION", "0.5"))

        self._loaded = False
        self._listening = False
        self._state_before_listen: str | None = None
        self._load_lock = asyncio.Lock()
        self._listen_task: asyncio.Task | None = None
        self._model: Any = None
        self._subscriptions: list[str] = []
        self._event_handler_map: dict[str, Any] = {}
        self._last_marker: int = 0

    async def start(self) -> None:
        self._event_handler_map = {
            "system.state.change": self._handle_state_change,
            "voice.listen.start": self._handle_listen_start,
            "voice.listen.complete": self._handle_listen_complete,
        }
        for event_type, handler in self._event_handler_map.items():
            self._event_bus.subscribe(event_type, handler)
        self._subscriptions = list(self._event_handler_map.keys())

        await self._event_bus.publish_event(
            source="wake_word_engine",
            event_type="voice.ready",
            payload={
                "backend": self._backend,
                "wake_phrase": self._wake_phrase,
            },
        )
        logger.info("Wake Word Engine started (backend=%s, phrase=%s)", self._backend, self._wake_phrase)

    async def stop(self) -> None:
        for event_type, handler in self._event_handler_map.items():
            self._event_bus.unsubscribe(event_type, handler)
        self._subscriptions.clear()

        self._listening = False
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            self._listen_task = None
        self._model = None
        self._loaded = False
        logger.info("Wake Word Engine stopped")

    async def _handle_state_change(self, event: HelixEvent) -> None:
        state = event.payload.get("state", "sleep")
        self._state_before_listen = state
        if state == "sleep":
            if self._listen_task and not self._listen_task.done():
                return
            self._listening = True
            self._listen_task = asyncio.create_task(self._listen_loop())
        else:
            self._listening = False

    async def _handle_listen_start(self, event: HelixEvent) -> None:
        self._listening = False

    async def _handle_listen_complete(self, event: HelixEvent) -> None:
        if self._state_before_listen == "sleep":
            if self._listen_task and not self._listen_task.done():
                return
            self._listening = True
            self._listen_task = asyncio.create_task(self._listen_loop())

    async def _listen_loop(self) -> None:
        await self._load_model_if_needed()

        while self._listening:
            try:
                if self._ring is not None:
                    marker = self._ring.current_marker
                    if marker == self._last_marker:
                        await asyncio.sleep(0.05)
                        continue
                    audio_data = self._ring.read_from(self._last_marker, self._chunk_duration)
                    self._last_marker = marker
                    if len(audio_data) == 0:
                        await asyncio.sleep(0.05)
                        continue
                else:
                    await asyncio.sleep(0.05)
                    continue

                detected = await self._detect(audio_data)
                if detected:
                    await self._event_bus.publish_event(
                        source="wake_word_engine",
                        event_type="voice.wake",
                        payload={
                            "phrase": self._wake_phrase,
                            "confidence": getattr(detected, "confidence", 0.0),
                            "timestamp": time.time(),
                        },
                    )
                    break
            except Exception as e:
                logger.debug("Wake word listen error: %s", e)
                await asyncio.sleep(0.1)

    async def _load_model_if_needed(self) -> None:
        async with self._load_lock:
            if self._loaded:
                return

            await self._event_bus.publish_event(
                source="wake_word_engine",
                event_type="voice.model.loading",
                payload={"type": "wake_word", "model": self._wake_phrase},
            )

            if self._backend == "openwakeword":
                try:
                    from openwakeword.model import Model
                    loop = asyncio.get_event_loop()
                    self._model = await loop.run_in_executor(
                        None,
                        lambda: Model(
                            wakeword_models=[self._wake_phrase.replace(" ", "_")],
                            inference_framework="onnx",
                        ),
                    )
                except ImportError:
                    raise ImportError(
                        "openwakeword not installed. "
                        "Install with: pip install openwakeword"
                    )
            elif self._backend == "mock":
                self._model = None
            else:
                raise ValueError(f"Unknown wake word backend: {self._backend}")

            self._loaded = True
            await self._event_bus.publish_event(
                source="wake_word_engine",
                event_type="voice.model.loaded",
                payload={"type": "wake_word", "model": self._wake_phrase},
            )
            logger.info("Wake word model loaded")

    async def _detect(self, audio_data: Any) -> Any:
        if self._backend == "mock":
            await asyncio.sleep(0.05)
            return None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._detect_blocking,
            audio_data,
        )

    def _detect_blocking(self, audio_data: Any) -> Any:
        if self._backend == "openwakeword" and self._model:
            import numpy as np
            audio_array = np.asarray(audio_data, dtype=np.float32)
            prediction = self._model.predict(audio_array)
            for name, score in prediction.items():
                if score >= self._threshold:
                    return type("Detection", (), {"confidence": score, "name": name})()
        return None
