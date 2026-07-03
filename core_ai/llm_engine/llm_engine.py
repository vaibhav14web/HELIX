import os
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from foundation.event_bus.event_bus import EventBus, HelixEvent

logger = logging.getLogger("helix.llm_engine")


class LLMEngine:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus

        self._backend = os.getenv("HELIX_LLM_BACKEND", "mock")
        self._model_path = os.getenv(
            "HELIX_LLM_MODEL_PATH",
            str(Path.cwd() / "models" / "qwen3" / "qwen3_1.7b_instruct.gguf"),
        )
        self._model_name = os.getenv("HELIX_LLM_MODEL_NAME", "qwen3:1.7b")
        self._ollama_url = os.getenv("HELIX_LLM_OLLAMA_URL", "http://localhost:11434")
        self._context_length = int(os.getenv("HELIX_LLM_CONTEXT_LENGTH", "2048"))
        self._max_tokens = int(os.getenv("HELIX_LLM_MAX_TOKENS", "512"))
        self._temperature = float(os.getenv("HELIX_LLM_TEMPERATURE", "0.7"))
        self._gpu_layers = int(os.getenv("HELIX_LLM_GPU_LAYERS", "-1"))
        self._idle_unload_seconds = int(os.getenv("HELIX_LLM_IDLE_UNLOAD_SECONDS", "300"))
        self._trust_remote_code = os.getenv("HELIX_LLM_TRUST_REMOTE_CODE", "false").lower() in ("true", "1", "yes")

        self._model: Any = None
        self._loaded = False
        self._last_used: datetime | None = None
        self._load_lock = asyncio.Lock()
        self._unload_task: asyncio.Task | None = None
        self._subscriptions: list[str] = []
        self._event_handler_map: dict[str, Any] = {}
        self._http_session: Any = None
        self._abort = asyncio.Event()

    async def start(self) -> None:
        self._event_handler_map = {
            "llm.generate": self._handle_generate,
            "llm.generate.stop": self._handle_stop,
        }
        for event_type, handler in self._event_handler_map.items():
            self._event_bus.subscribe(event_type, handler)
        self._subscriptions = list(self._event_handler_map.keys())

        await self._event_bus.publish_event(
            source="llm_engine",
            event_type="llm.ready",
            payload={"backend": self._backend, "loaded": False},
        )
        logger.info("LLM Engine started (backend=%s)", self._backend)

    async def stop(self) -> None:
        for event_type, handler in self._event_handler_map.items():
            self._event_bus.unsubscribe(event_type, handler)
        self._subscriptions.clear()
        self._abort.set()
        await self._unload_model()
        if self._http_session:
            await self._http_session.aclose()
            self._http_session = None
        logger.info("LLM Engine stopped")

    async def _ensure_session(self) -> None:
        if self._http_session is None:
            import httpx
            timeout_val = float(os.getenv("HELIX_LLM_TIMEOUT", "120.0"))
            self._http_session = httpx.AsyncClient(timeout=timeout_val)

    async def _handle_generate(self, event: HelixEvent) -> None:
        self._abort.clear()
        prompt = event.payload.get("prompt", "")
        session_id = event.payload.get("session_id", "default")

        if not prompt.strip():
            await self._event_bus.publish_event(
                source="llm_engine",
                event_type="llm.generation.error",
                payload={"error": "Empty prompt", "session_id": session_id},
                correlation_id=event.correlation_id,
            )
            return

        await self._event_bus.publish_event(
            source="llm_engine",
            event_type="llm.generation.start",
            payload={"session_id": session_id},
            correlation_id=event.correlation_id,
        )

        try:
            response = await self.generate(prompt, correlation_id=event.correlation_id, session_id=session_id)
            self._last_used = datetime.now(timezone.utc)

            self._schedule_unload_if_idle()

            await self._event_bus.publish_event(
                source="llm_engine",
                event_type="llm.generation.complete",
                payload={
                    "session_id": session_id,
                    "response": response,
                },
                correlation_id=event.correlation_id,
            )
        except asyncio.CancelledError:
            await self._event_bus.publish_event(
                source="llm_engine",
                event_type="llm.generation.error",
                payload={"error": "Generation cancelled", "session_id": session_id},
                correlation_id=event.correlation_id,
            )
        except Exception as e:
            logger.exception("LLM generation failed")
            await self._event_bus.publish_event(
                source="llm_engine",
                event_type="llm.generation.error",
                payload={"error": str(e), "session_id": session_id},
                correlation_id=event.correlation_id,
            )

    async def _handle_stop(self, event: HelixEvent) -> None:
        self._abort.set()
        logger.info("LLM generation stop requested")

    async def generate(self, prompt: str, correlation_id: str | None = None, session_id: str = "default") -> str:
        if self._backend == "mock":
            return self._generate_mock(prompt)
        if self._backend == "ollama":
            return await self._generate_ollama(prompt, correlation_id=correlation_id, session_id=session_id)

        await self._ensure_model_loaded()
        return await self._generate_real(prompt, correlation_id=correlation_id, session_id=session_id)

    def _generate_mock(self, prompt: str) -> str:
        return (
            "Hello! I'm HELIX running in mock development mode. "
            "I received your message and will process it properly "
            "once a real LLM backend is configured. "
            "Set HELIX_LLM_BACKEND=ollama to use your local Ollama models."
        )

    async def _generate_ollama(self, prompt: str, correlation_id: str | None = None, session_id: str = "default") -> str:
        await self._ensure_session()
        payload = {
            "model": self._model_name,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": self._temperature,
                "num_predict": self._max_tokens,
                "num_ctx": self._context_length,
            },
        }
        async with self._http_session.stream(
            "POST", f"{self._ollama_url}/api/generate", json=payload
        ) as resp:
            resp.raise_for_status()
            full_text = []
            async for line in resp.aiter_lines():
                if self._abort.is_set():
                    break
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "error" in data:
                    raise RuntimeError(data["error"])
                if "response" in data and correlation_id:
                    chunk = data["response"]
                    full_text.append(chunk)
                    await self._event_bus.publish_event(
                        source="llm_engine",
                        event_type="llm.generation.chunk",
                        payload={
                            "session_id": session_id,
                            "chunk": chunk,
                        },
                        correlation_id=correlation_id,
                    )
                if data.get("done", False):
                    break
        return "".join(full_text).strip()

    async def _ensure_model_loaded(self) -> None:
        async with self._load_lock:
            if self._loaded:
                self._cancel_unload()
                return

            await self._event_bus.publish_event(
                source="llm_engine",
                event_type="llm.model.loading",
                payload={"backend": self._backend, "model_path": self._model_path},
            )
            logger.info("Loading model (backend=%s, path=%s)", self._backend, self._model_path)

            if self._backend == "llama.cpp":
                self._model = await self._load_llamacpp()
            elif self._backend == "transformers":
                self._model = await self._load_transformers()
            else:
                raise ValueError(f"Unknown LLM backend: {self._backend}")

            self._loaded = True
            await self._event_bus.publish_event(
                source="llm_engine",
                event_type="llm.model.loaded",
                payload={"backend": self._backend},
            )
            logger.info("Model loaded successfully")

    async def _load_llamacpp(self) -> Any:
        try:
            from llama_cpp import Llama
        except ImportError:
            raise ImportError(
                "llama-cpp-python not installed. "
                "Install with: pip install llama-cpp-python "
                "or set HELIX_LLM_BACKEND=ollama to use Ollama."
            )

        model_path = Path(self._model_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model not found: {model_path}. "
                f"Set HELIX_LLM_MODEL_PATH to a valid GGUF file."
            )

        loop = asyncio.get_running_loop()
        model = await loop.run_in_executor(
            None,
            lambda: Llama(
                model_path=str(model_path),
                n_ctx=self._context_length,
                n_gpu_layers=self._gpu_layers if self._gpu_layers >= 0 else -1,
                verbose=False,
            ),
        )
        return model

    async def _load_transformers(self) -> dict[str, Any]:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError:
            raise ImportError(
                "transformers/torch not installed. "
                "Install with: pip install transformers torch "
                "or set HELIX_LLM_BACKEND=ollama to use Ollama."
            )

        loop = asyncio.get_running_loop()
        tokenizer_fut = loop.run_in_executor(
            None,
            lambda: AutoTokenizer.from_pretrained(self._model_name, trust_remote_code=self._trust_remote_code),
        )
        model_fut = loop.run_in_executor(
            None,
            lambda: AutoModelForCausalLM.from_pretrained(
                self._model_name,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                device_map="auto" if torch.cuda.is_available() else None,
                trust_remote_code=self._trust_remote_code,
            ),
        )
        tokenizer, model = await asyncio.gather(tokenizer_fut, model_fut)
        return {"model": model, "tokenizer": tokenizer}

    async def _generate_real(self, prompt: str, correlation_id: str | None = None, session_id: str = "default") -> str:
        if self._backend == "llama.cpp":
            return await self._generate_llamacpp(prompt, correlation_id=correlation_id, session_id=session_id)
        elif self._backend == "transformers":
            return await self._generate_transformers(prompt, correlation_id=correlation_id, session_id=session_id)
        raise ValueError(f"Unknown backend: {self._backend}")

    async def _generate_llamacpp(self, prompt: str, correlation_id: str | None = None, session_id: str = "default") -> str:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._model(
                prompt,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                echo=False,
            ),
        )
        text = result["choices"][0]["text"].strip()
        if correlation_id and text:
            await self._event_bus.publish_event(
                source="llm_engine",
                event_type="llm.generation.chunk",
                payload={"session_id": session_id, "chunk": text},
                correlation_id=correlation_id,
            )
        return text

    async def _generate_transformers(self, prompt: str, correlation_id: str | None = None, session_id: str = "default") -> str:
        import torch

        loop = asyncio.get_running_loop()
        model = self._model["model"]
        tokenizer = self._model["tokenizer"]

        inputs = await loop.run_in_executor(
            None,
            lambda: tokenizer(prompt, return_tensors="pt"),
        )
        if torch.cuda.is_available():
            inputs = {k: v.to("cuda") for k, v in inputs.items()}

        outputs = await loop.run_in_executor(
            None,
            lambda: model.generate(
                **inputs,
                max_new_tokens=self._max_tokens,
                temperature=self._temperature,
                do_sample=True,
            ),
        )
        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        response = response[len(prompt):].strip()
        if correlation_id and response:
            await self._event_bus.publish_event(
                source="llm_engine",
                event_type="llm.generation.chunk",
                payload={"session_id": session_id, "chunk": response},
                correlation_id=correlation_id,
            )
        return response

    async def _unload_model(self) -> None:
        if self._unload_task and not self._unload_task.done():
            self._unload_task.cancel()
            self._unload_task = None

        if not self._loaded:
            return

        await self._event_bus.publish_event(
            source="llm_engine",
            event_type="llm.model.unloading",
            payload={},
        )
        logger.info("Unloading model")

        self._model = None
        self._loaded = False

        await self._event_bus.publish_event(
            source="llm_engine",
            event_type="llm.model.unloaded",
            payload={},
        )
        logger.info("Model unloaded")

    def _schedule_unload_if_idle(self) -> None:
        if self._idle_unload_seconds <= 0:
            return
        if self._unload_task is None or self._unload_task.done():
            self._unload_task = asyncio.create_task(self._delayed_unload())

    def _cancel_unload(self) -> None:
        if self._unload_task and not self._unload_task.done():
            self._unload_task.cancel()
            self._unload_task = None

    async def _delayed_unload(self) -> None:
        try:
            await asyncio.sleep(self._idle_unload_seconds)
            if self._last_used and (datetime.now(timezone.utc) - self._last_used).total_seconds() < self._idle_unload_seconds:
                return
            await self._unload_model()
        except asyncio.CancelledError:
            pass
