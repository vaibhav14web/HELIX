import os
import asyncio
import logging
import re
import threading
import queue
import time
import numpy as np
from pathlib import Path
from typing import Any

from foundation.event_bus.event_bus import EventBus, HelixEvent
from core_ai.voice_engine.audio_capture import RingBuffer, AudioCapture
from core_ai.voice_engine.voice_state import VoiceStateMachine, VoiceState

logger = logging.getLogger("helix.voice_engine")

_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"  # dingbats
    "\U000024C2-\U0001F251"  # enclosed characters
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols extended-A
    "\U00002600-\U000026FF"  # misc symbols
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0000200D"             # zero-width joiner
    "]+",
    re.UNICODE,
)

# Patterns for text cleaning before TTS
_MARKDOWN_PATTERN = re.compile(r"[#*_~`>|\[\](){}]")
_URL_PATTERN = re.compile(r"https?://\S+")
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_MULTI_SPACE_PATTERN = re.compile(r"\s+")
_CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```|`[^`]+`")


class VoiceEngine:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus

        self._sample_rate = int(os.getenv("HELIX_VOICE_SAMPLE_RATE", "16000"))
        self._channels = int(os.getenv("HELIX_VOICE_CHANNELS", "1"))
        self._backend = os.getenv("HELIX_VOICE_BACKEND", "mock")
        self._stt_backend = os.getenv("HELIX_VOICE_STT_BACKEND", self._backend)
        self._tts_backend = os.getenv("HELIX_VOICE_TTS_BACKEND", self._backend)
        self._stt_model = os.getenv("HELIX_VOICE_STT_MODEL", "tiny")
        self._tts_model = os.getenv("HELIX_VOICE_TTS_MODEL", "piper")
        self._wake_word = os.getenv("HELIX_VOICE_WAKE_WORD", "helix")
        self._wake_word_threshold = float(os.getenv("HELIX_VOICE_WAKE_THRESHOLD", "0.5"))
        self._audio_device = os.getenv("HELIX_VOICE_AUDIO_DEVICE", "default")
        self._stt_language = os.getenv("HELIX_VOICE_STT_LANGUAGE", "en")
        self._idle_unload_seconds = int(os.getenv("HELIX_VOICE_IDLE_UNLOAD_SECONDS", "300"))
        self._preload = os.getenv("HELIX_VOICE_PRELOAD", "false").lower() == "true"
        self._keep_loaded = os.getenv("HELIX_VOICE_KEEP_LOADED", "false").lower() in ("true", "1", "yes")
        self._ring_seconds = int(os.getenv("HELIX_VOICE_RING_SECONDS", "3"))

        self._silence_threshold = float(os.getenv("HELIX_VOICE_SILENCE_THRESHOLD", "0.003"))
        self._silence_duration = float(os.getenv("HELIX_VOICE_SILENCE_DURATION", "1.5"))
        self._max_listen_duration = float(os.getenv("HELIX_VOICE_MAX_LISTEN_DURATION", "30.0"))
        self._vad_chunk_duration = float(os.getenv("HELIX_VOICE_VAD_CHUNK_DURATION", "0.3"))
        self._voice_chunks_required = int(os.getenv("HELIX_VOICE_CHUNKS_REQUIRED", "3"))

        self._tts_sample_rate = self._sample_rate

        self._state = VoiceStateMachine()
        self._ring = RingBuffer(max_seconds=self._ring_seconds, sample_rate=self._sample_rate)
        self._capture = AudioCapture(
            ring_buffer=self._ring,
            device=self._audio_device if self._audio_device != "default" else None,
            channels=self._channels,
            chunk_duration=0.1,
        )

        self._loaded = False
        self._listening = False
        self._processing = False
        self._last_used: float | None = None
        self._load_lock = asyncio.Lock()
        self._stt_load_lock = asyncio.Lock()
        self._tts_load_lock = asyncio.Lock()
        self._unload_task: asyncio.Task | None = None
        self._subscriptions: list[str] = []
        self._event_handler_map: dict[str, Any] = {}

        self._stt_model_instance: Any = None
        self._tts_model_instance: Any = None
        self._pending_listen: str | None = None
        self._listen_future: asyncio.Future[str] | None = None
        self._listen_task: asyncio.Task | None = None
        self._tts_task: asyncio.Task | None = None

        self._vad_buffer: list[bytes] = []
        self._vad_voice_chunks = 0
        self._vad_silence_chunks = 0
        self._vad_active = False
        self._interrupting = False
        self._stopped = False

    async def start(self) -> None:
        self._capture.start()

        self._event_handler_map = {
            "voice.wake": self._handle_wake,
            "voice.listen": self._handle_listen,
            "voice.tts": self._handle_tts,
            "voice.interrupt": self._handle_interrupt,
            "voice.shutdown": self._handle_shutdown,
            "system.state.change": self._handle_state_change,
        }
        for event_type, handler in self._event_handler_map.items():
            self._event_bus.subscribe(event_type, handler)
        self._subscriptions = list(self._event_handler_map.keys())

        await self._event_bus.publish_event(
            source="voice_engine",
            event_type="voice.ready",
            payload={
                "backend": self._backend,
                "wake_word": self._wake_word,
                "loaded": False,
            },
        )
        logger.info("Voice Engine started (backend=%s)", self._backend)

        if self._preload:
            logger.info("Preloading voice models...")
            await asyncio.gather(
                self._ensure_stt_loaded(),
                self._ensure_tts_loaded(),
            )

    async def stop(self) -> None:
        self._stopped = True
        self._listening = False
        self._processing = False
        self._interrupting = True

        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            self._listen_task = None
        if self._tts_task and not self._tts_task.done():
            self._tts_task.cancel()
            self._tts_task = None
        if self._listen_future and not self._listen_future.done():
            self._listen_future.cancel()
            self._listen_future = None

        self._capture.stop()
        for event_type, handler in self._event_handler_map.items():
            self._event_bus.unsubscribe(event_type, handler)
        self._subscriptions.clear()

        await self._unload_models()
        if self._unload_task and not self._unload_task.done():
            self._unload_task.cancel()
            self._unload_task = None

        await asyncio.sleep(0.5)

        logger.info("Voice Engine stopped")

    # ── State ──────────────────────────────────────────────────

    @property
    def state(self) -> str:
        return self._state.state_name

    # ── Event Handlers ─────────────────────────────────────────

    async def _handle_wake(self, event: HelixEvent) -> None:
        if self._processing:
            logger.debug("Wake ignored: already processing")
            return
        logger.info("Wake word detected: %s", self._wake_word)
        self._last_used = time.time()
        self._schedule_unload_if_idle()

        await self._event_bus.publish_event(
            source="voice_engine",
            event_type="voice.wake.confirmed",
            payload={"wake_word": self._wake_word},
            correlation_id=event.correlation_id,
        )

        await self._event_bus.publish_event(
            source="voice_engine",
            event_type="voice.listen",
            payload={"session_id": event.payload.get("session_id", "default")},
        )

    async def _handle_listen(self, event: HelixEvent) -> None:
        if self._processing:
            logger.debug("Listen ignored: already processing")
            return

        self._listen_task = asyncio.current_task()
        session_id = event.payload.get("session_id", "default")
        self._processing = True
        self._listening = True
        self._vad_buffer = []
        self._vad_voice_chunks = 0
        self._vad_silence_chunks = 0
        self._vad_active = False
        self._interrupting = False

        await self._event_bus.publish_event(
            source="voice_engine",
            event_type="voice.listen.start",
            payload={"session_id": session_id},
            correlation_id=event.correlation_id,
        )

        try:
            await self._ensure_stt_loaded()
            text = await self._capture_and_transcribe(session_id)

            self._listening = False
            self._processing = False

            if self._interrupting:
                return

            if self._listen_future and not self._listen_future.done():
                self._listen_future.set_result(text)

            await self._event_bus.publish_event(
                source="voice_engine",
                event_type="voice.listen.complete",
                payload={"session_id": session_id, "text": text},
                correlation_id=event.correlation_id,
            )
        except asyncio.CancelledError:
            self._listening = False
            self._processing = False
            logger.debug("Listen cancelled")
        except Exception as e:
            self._listening = False
            self._processing = False
            logger.exception("Voice listen failed")
            if self._listen_future and not self._listen_future.done():
                self._listen_future.set_exception(e)
            await self._event_bus.publish_event(
                source="voice_engine",
                event_type="voice.error",
                payload={"error": str(e), "stage": "listen"},
                correlation_id=event.correlation_id,
            )
        finally:
            self._listen_task = None

    async def _handle_tts(self, event: HelixEvent) -> None:
        self._tts_task = asyncio.current_task()
        session_id = event.payload.get("session_id", "default")
        text = event.payload.get("text", "")

        if not text.strip():
            self._tts_task = None
            logger.warning("TTS requested with empty text")
            return

        await self._event_bus.publish_event(
            source="voice_engine",
            event_type="voice.tts.start",
            payload={"session_id": session_id},
            correlation_id=event.correlation_id,
        )

        try:
            await self._ensure_tts_loaded()
            await self._synthesize_and_play(text)

            if not self._interrupting:
                await self._event_bus.publish_event(
                    source="voice_engine",
                    event_type="voice.tts.complete",
                    payload={"session_id": session_id},
                    correlation_id=event.correlation_id,
                )
        except asyncio.CancelledError:
            logger.debug("TTS cancelled")
        except Exception as e:
            logger.exception("TTS failed")
            await self._event_bus.publish_event(
                source="voice_engine",
                event_type="voice.error",
                payload={"error": str(e), "stage": "tts"},
                correlation_id=event.correlation_id,
            )
        finally:
            self._tts_task = None

    async def _handle_interrupt(self, event: HelixEvent) -> None:
        self._interrupting = True
        self._listening = False
        self._vad_buffer = []
        self._vad_active = False
        logger.debug("Voice interrupt acknowledged")

    async def _handle_shutdown(self, event: HelixEvent) -> None:
        logger.info("Voice shutdown requested via event")
        await self.stop()

    async def _handle_state_change(self, event: HelixEvent) -> None:
        state = event.payload.get("state", "sleep")
        if state in ("sleep", "background"):
            self._interrupting = True
            self._listening = False
            if not self._keep_loaded:
                await self._unload_models()

    # ── VAD + Capture Pipeline ────────────────────────────────

    async def _capture_and_transcribe(self, session_id: str) -> str:
        max_samples = int(self._max_listen_duration * self._sample_rate)
        silence_samples = int(self._silence_duration * self._sample_rate)
        total_samples = 0
        silence_counter = 0
        voice_chunk_count = 0
        voice_active = False
        raw_chunks: list[np.ndarray] = []
        max_iterations = int(self._max_listen_duration / 0.02) + 200
        iterations = 0

        last_marker = self._ring.current_marker

        while total_samples < max_samples and self._listening and not self._interrupting and iterations < max_iterations:
            iterations += 1
            new_marker = self._ring.current_marker
            if new_marker == last_marker:
                await asyncio.sleep(0.02)
                continue

            chunk_data = self._ring.read_from(last_marker, self._vad_chunk_duration)
            last_marker = new_marker
            actual_samples = len(chunk_data)
            if actual_samples == 0:
                continue

            total_samples += actual_samples
            rms = float(np.sqrt(np.mean(chunk_data ** 2)))
            raw_chunks.append(chunk_data)

            if rms >= self._silence_threshold:
                voice_chunk_count += 1
                silence_counter = 0
                if voice_chunk_count >= self._voice_chunks_required:
                    voice_active = True
            elif voice_active:
                silence_counter += actual_samples

            if voice_active and silence_counter >= silence_samples:
                break

        if not raw_chunks or not voice_active:
            return ""

        audio = np.concatenate(raw_chunks)
        return await self._transcribe(audio.tobytes())

    # ── Text cleaning for TTS ───────────────────────────────────

    @staticmethod
    def clean_text(text: str) -> str:
        text = _CODE_BLOCK_PATTERN.sub("", text)
        text = _HTML_TAG_PATTERN.sub("", text)
        text = _URL_PATTERN.sub("link", text)
        text = _EMOJI_PATTERN.sub("", text)
        text = _MARKDOWN_PATTERN.sub("", text)
        text = _MULTI_SPACE_PATTERN.sub(" ", text)
        return text.strip()

    # ── Public API ─────────────────────────────────────────────

    async def speak(self, text: str, session_id: str = "default") -> None:
        text = self.clean_text(text)
        if not text:
            return
        await self._event_bus.publish_event(
            source="voice_engine",
            event_type="voice.tts",
            payload={"text": text, "session_id": session_id},
        )

    async def synthesize(self, text: str) -> bytes:
        text = self.clean_text(text)
        if not text:
            return b""

        if self._tts_backend == "mock":
            return b""

        await self._ensure_tts_loaded()
        self._last_used = time.time()
        self._schedule_unload_if_idle()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._synthesize_blocking, text)

    def _synthesize_blocking(self, text: str) -> bytes:
        if self._tts_backend == "piper" and self._tts_model_instance:
            import io
            import wave

            model = self._tts_model_instance
            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # 16-bit PCM
                wav_file.setframerate(self._tts_sample_rate)

                for audio_chunk in model.synthesize(text):
                    wav_file.writeframes(audio_chunk.audio_int16_bytes)

            return wav_io.getvalue()

        if self._tts_backend == "coqui" and self._tts_model_instance:
            import io
            model = self._tts_model_instance
            audio_stream = io.BytesIO()
            model.tts_to_file(text=text, file_path=audio_stream)
            return audio_stream.getvalue()

        raise ValueError(f"TTS synthesis not supported for backend: {self._tts_backend}")

    async def transcribe(self, audio_data: bytes, session_id: str = "default") -> str:
        await self._ensure_stt_loaded()
        self._last_used = time.time()
        self._schedule_unload_if_idle()
        text = await self._transcribe(audio_data)
        return text

    async def listen(self, session_id: str = "default") -> str:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        correlation_id = str(hash(f"listen:{session_id}:{loop.time()}"))

        self._pending_listen = correlation_id
        self._listen_future = future

        await self._event_bus.publish_event(
            source="voice_engine",
            event_type="voice.listen",
            payload={"session_id": session_id},
            correlation_id=correlation_id,
        )

        try:
            text = await asyncio.wait_for(future, timeout=10)
            return text
        except asyncio.TimeoutError:
            logger.warning("Voice listen timeout for session %s", session_id)
            return ""
        finally:
            self._pending_listen = None
            self._listen_future = None

    # ── Model Loading ──────────────────────────────────────────

    async def _ensure_stt_loaded(self) -> None:
        async with self._stt_load_lock:
            if self._stt_model_instance is not None:
                self._last_used = time.time()
                self._schedule_unload_if_idle()
                return

            await self._event_bus.publish_event(
                source="voice_engine",
                event_type="voice.model.loading",
                payload={"type": "stt", "model": self._stt_model},
            )
            logger.info("Loading STT model: %s", self._stt_model)

            try:
                self._stt_model_instance = await asyncio.get_running_loop().run_in_executor(
                    None, self._load_stt_model
                )
                self._loaded = True
                await self._event_bus.publish_event(
                    source="voice_engine",
                    event_type="voice.model.loaded",
                    payload={"type": "stt", "model": self._stt_model},
                )
                logger.info("STT model loaded")
            except Exception as e:
                logger.exception("Failed to load STT model")
                await self._event_bus.publish_event(
                    source="voice_engine",
                    event_type="voice.model.error",
                    payload={"type": "stt", "error": str(e)},
                )
                raise

    async def _ensure_tts_loaded(self) -> None:
        async with self._tts_load_lock:
            if self._tts_model_instance is not None:
                self._last_used = time.time()
                self._schedule_unload_if_idle()
                return

            await self._event_bus.publish_event(
                source="voice_engine",
                event_type="voice.model.loading",
                payload={"type": "tts", "model": self._tts_model},
            )
            logger.info("Loading TTS model: %s", self._tts_model)

            try:
                self._tts_model_instance = await asyncio.get_running_loop().run_in_executor(
                    None, self._load_tts_model
                )
                self._loaded = True
                await self._event_bus.publish_event(
                    source="voice_engine",
                    event_type="voice.model.loaded",
                    payload={"type": "tts", "model": self._tts_model},
                )
                logger.info("TTS model loaded")
            except Exception as e:
                logger.exception("Failed to load TTS model")
                await self._event_bus.publish_event(
                    source="voice_engine",
                    event_type="voice.model.error",
                    payload={"type": "tts", "error": str(e)},
                )
                raise

    def _load_stt_model(self) -> Any:
        if self._stt_backend == "mock":
            return None
        if self._stt_backend == "whisper":
            try:
                import whisper
                return whisper.load_model(self._stt_model)
            except ImportError:
                raise ImportError("openai-whisper not installed. Install with: pip install openai-whisper")
        if self._stt_backend == "faster_whisper":
            try:
                from faster_whisper import WhisperModel
                return WhisperModel(self._stt_model, compute_type="int8")
            except ImportError:
                raise ImportError("faster-whisper not installed. Install with: pip install faster-whisper")
        raise ValueError(f"Unknown STT backend: {self._stt_backend}")

    def _load_tts_model(self) -> Any:
        if self._tts_backend == "mock":
            return None
        if self._tts_backend == "piper":
            try:
                from piper.voice import PiperVoice
                project_root = Path(__file__).resolve().parents[2]
                env_path = os.getenv("HELIX_VOICE_TTS_MODEL_PATH")
                if env_path:
                    model_path = Path(env_path)
                    if not model_path.is_absolute():
                        model_path = (project_root / model_path).resolve()
                else:
                    model_path = project_root / "models" / "tts" / "en_US-lessac-medium.onnx"
                if not model_path.exists():
                    raise FileNotFoundError(f"Piper model not found: {model_path}")
                voice = PiperVoice.load(str(model_path))
                self._tts_sample_rate = voice.config.sample_rate
                return voice
            except ImportError:
                raise ImportError("piper-tts not installed. Install with: pip install piper-tts")
        if self._tts_backend == "coqui":
            try:
                from TTS.api import TTS
                return TTS(model_name=self._tts_model, progress_bar=False)
            except ImportError:
                raise ImportError("coqui-ai TTS not installed. Install with: pip install TTS")
        raise ValueError(f"Unknown TTS backend: {self._tts_backend}")

    # ── Transcription ──────────────────────────────────────────

    async def _transcribe(self, audio_data: bytes) -> str:
        if self._stt_backend == "mock":
            return "This is a mock transcription."

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._transcribe_blocking, audio_data)

    def _transcribe_blocking(self, audio_data: bytes) -> str:
        import numpy as np

        is_media_file = False
        if len(audio_data) % 4 != 0:
            is_media_file = True
        else:
            common_headers = [
                b"RIFF",            # WAV
                b"\x1a\x45\xdf\xa3",   # WebM
                b"OggS",            # Ogg
                b"ftyp",            # MP4/M4A (at offset 4)
                b"ID3",             # MP3
            ]
            if any(h in audio_data[:12] for h in common_headers):
                is_media_file = True

        if is_media_file:
            import tempfile
            import os as _os
            suffix = ".wav"
            if b"\x1a\x45\xdf\xa3" in audio_data[:12]:
                suffix = ".webm"
            elif b"OggS" in audio_data[:12]:
                suffix = ".ogg"
            elif b"ftyp" in audio_data[:12]:
                suffix = ".mp4"
            elif b"ID3" in audio_data[:12]:
                suffix = ".mp3"

            fd, temp_path = tempfile.mkstemp(suffix=suffix)
            try:
                _os.write(fd, audio_data)
            finally:
                _os.close(fd)

            try:
                if self._stt_backend == "whisper" and self._stt_model_instance:
                    result = self._stt_model_instance.transcribe(temp_path, language=self._stt_language)
                    return result["text"].strip()

                if self._stt_backend == "faster_whisper" and self._stt_model_instance:
                    segments, info = self._stt_model_instance.transcribe(temp_path, language=self._stt_language)
                    return " ".join(segment.text for segment in segments).strip()
            finally:
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
        else:
            if self._stt_backend == "whisper" and self._stt_model_instance:
                audio_array = np.frombuffer(audio_data, dtype=np.float32)
                result = self._stt_model_instance.transcribe(audio_array, language=self._stt_language)
                return result["text"].strip()

            if self._stt_backend == "faster_whisper" and self._stt_model_instance:
                audio_array = np.frombuffer(audio_data, dtype=np.float32)
                segments, info = self._stt_model_instance.transcribe(audio_array, language=self._stt_language)
                return " ".join(segment.text for segment in segments).strip()

        raise ValueError(f"STT not available for backend: {self._stt_backend}")

    # ── Streaming TTS ──────────────────────────────────────────

    async def _synthesize_and_play(self, text: str) -> None:
        text = self.clean_text(text)
        if not text:
            return
        if self._tts_backend == "mock":
            await asyncio.sleep(0.1)
            return

        self._last_used = time.time()
        self._schedule_unload_if_idle()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._synthesize_and_play_blocking, text)

    def _synthesize_and_play_blocking(self, text: str) -> None:
        if self._tts_backend == "piper" and self._tts_model_instance:
            self._synthesize_and_play_piper_streaming(text)
        elif self._tts_backend == "coqui" and self._tts_model_instance:
            self._synthesize_and_play_coqui_blocking(text)
        else:
            raise ValueError(f"TTS not available for backend: {self._tts_backend}")

    def _synthesize_and_play_piper_streaming(self, text: str) -> None:
        import threading as _threading
        import queue as _queue
        import sounddevice as sd
        import numpy as np

        model = self._tts_model_instance
        if model is None:
            return

        chunk_q: _queue.Queue = _queue.Queue(maxsize=4)

        def producer():
            try:
                for audio_chunk in model.synthesize(text):
                    if self._interrupting or self._stopped:
                        break
                    chunk_q.put(audio_chunk.audio_float_array.astype(np.float32))
            finally:
                chunk_q.put(None)

        producer_thread = _threading.Thread(target=producer, daemon=True)
        producer_thread.start()

        try:
            while not self._interrupting and not self._stopped:
                try:
                    chunk = chunk_q.get(timeout=0.1)
                except _queue.Empty:
                    continue
                if chunk is None:
                    break
                sd.play(chunk, self._tts_sample_rate)
                self._poll_sd_playback(sd)
        finally:
            sd.stop()
            producer_thread.join(timeout=1)

    def _poll_sd_playback(self, sd) -> None:
        import time as _time
        deadline = _time.time() + 10.0
        try:
            while sd.get_stream() and sd.get_stream().active:
                if self._interrupting or self._stopped:
                    sd.stop()
                    return
                remaining = deadline - _time.time()
                if remaining <= 0:
                    break
                sd.sleep(min(0.05, remaining))
        except Exception:
            pass

    def _synthesize_and_play_coqui_blocking(self, text: str) -> None:
        import sounddevice as sd
        import numpy as np
        import io

        model = self._tts_model_instance
        if model is None:
            return

        audio_stream = io.BytesIO()
        model.tts_to_file(text=text, file_path=audio_stream)
        audio_array = np.frombuffer(audio_stream.getvalue(), dtype=np.float32)
        if audio_array.size > 0:
            sd.play(audio_array, self._tts_sample_rate)
            self._poll_sd_playback(sd)

    # ── Lifecycle ──────────────────────────────────────────────

    async def _unload_models(self) -> None:
        if self._unload_task and not self._unload_task.done():
            self._unload_task.cancel()
            self._unload_task = None

        if not self._loaded:
            return

        await self._event_bus.publish_event(
            source="voice_engine",
            event_type="voice.model.unloading",
            payload={},
        )
        logger.info("Unloading voice models")

        self._stt_model_instance = None
        self._tts_model_instance = None
        self._loaded = False

        await self._event_bus.publish_event(
            source="voice_engine",
            event_type="voice.model.unloaded",
            payload={},
        )
        logger.info("Voice models unloaded")

    def _schedule_unload_if_idle(self) -> None:
        if self._idle_unload_seconds <= 0:
            return
        if self._unload_task is None or self._unload_task.done():
            self._unload_task = asyncio.create_task(self._delayed_unload())

    async def _delayed_unload(self) -> None:
        if self._keep_loaded:
            return
        try:
            await asyncio.sleep(self._idle_unload_seconds)
            if self._last_used is not None:
                idle_time = time.time() - self._last_used
                if idle_time >= self._idle_unload_seconds:
                    await self._unload_models()
        except asyncio.CancelledError:
            pass
