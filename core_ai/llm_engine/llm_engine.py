import os
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from foundation.event_bus.event_bus import EventBus, HelixEvent
from core_ai.tool_calling.tool_parser import ToolParser

logger = logging.getLogger("helix.llm_engine")


class LLMEngine:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus

        self._backend = os.getenv("HELIX_LLM_BACKEND", "mock")
        self._orchestrator_model_path = os.getenv(
            "HELIX_LLM_ORCHESTRATOR_MODEL_PATH",
            r"C:\Users\vaibh\Documents\HELIX_MODELS\LLM\Qwen3-4B-Q8_0.gguf",
        )
        self._coder_model_path = os.getenv(
            "HELIX_LLM_CODER_MODEL_PATH",
            r"C:\Users\vaibh\Documents\HELIX_MODELS\LLM\qwen2.5-coder-3b-instruct-q8_0.gguf",
        )
        self._orchestrator_model_name = os.getenv(
            "HELIX_LLM_ORCHESTRATOR_MODEL_NAME",
            "qwen3:4b",
        )
        self._coder_model_name = os.getenv(
            "HELIX_LLM_CODER_MODEL_NAME",
            "qwen2.5-coder:3b",
        )
        self._model_path = self._orchestrator_model_path
        self._model_name = self._orchestrator_model_name
        self._ollama_url = os.getenv("HELIX_LLM_OLLAMA_URL", "http://localhost:11434")
        self._context_length = int(os.getenv("HELIX_LLM_CONTEXT_LENGTH", "2048"))
        self._max_tokens = int(os.getenv("HELIX_LLM_MAX_TOKENS", "512"))
        self._temperature = float(os.getenv("HELIX_LLM_TEMPERATURE", "0.7"))
        self._gpu_layers = int(os.getenv("HELIX_LLM_GPU_LAYERS", "-1"))
        self._idle_unload_seconds = int(os.getenv("HELIX_LLM_IDLE_UNLOAD_SECONDS", "1800"))
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

    def _detect_coding_in_prompt(self, prompt: str) -> bool:
        lower = prompt.lower()
        keywords = {
            "code", "program", "script", "function", "class", "method", "bug", "debug",
            "compile", "run", "exception", "error", "write a", "implement", "refactor",
            "test", "mock", "unittest", "pytest", "python", "javascript", "typescript",
            "html", "css", "rust", "cpp", "c++", "c#", "java", "sql", "git", "github",
            "regex", "algorithm", "database", "api", "json", "yaml"
        }
        for word in lower.split():
            clean_word = word.strip(".,;:!?()[]{}")
            if clean_word in keywords:
                return True
        if "```" in prompt or "def " in prompt or "import " in prompt or "const " in prompt or "let " in prompt:
            return True
        return False

    async def _handle_generate(self, event: HelixEvent) -> None:
        self._abort.clear()
        prompt = event.payload.get("prompt", "")
        session_id = event.payload.get("session_id", "default")
        
        is_coding = event.payload.get("is_coding", False)
        if not is_coding:
            source = event.source or ""
            if "coding" in source.lower() or "code" in source.lower():
                is_coding = True
            elif self._detect_coding_in_prompt(prompt):
                is_coding = True

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

        tools = event.payload.get("tools")
        messages = event.payload.get("messages")

        try:
            tool_calls = []
            if tools or messages:
                if not messages:
                    messages = [{"role": "user", "content": prompt}]
                chat_res = await self.chat_with_tools(
                    messages=messages,
                    tools=tools,
                    correlation_id=event.correlation_id,
                    session_id=session_id,
                    is_coding=is_coding,
                )
                response = chat_res.get("content", "")
                tool_calls = chat_res.get("tool_calls", [])
            else:
                response = await self.generate(prompt, correlation_id=event.correlation_id, session_id=session_id, is_coding=is_coding)
                cleaned_text, parsed_calls = ToolParser.parse_text_response(response)
                if parsed_calls:
                    response = cleaned_text
                    tool_calls = [tc.to_dict() for tc in parsed_calls]

            self._last_used = datetime.now(timezone.utc)

            self._schedule_unload_if_idle()

            await self._event_bus.publish_event(
                source="llm_engine",
                event_type="llm.generation.complete",
                payload={
                    "session_id": session_id,
                    "response": response,
                    "tool_calls": tool_calls,
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

    async def generate(self, prompt: str, correlation_id: str | None = None, session_id: str = "default", is_coding: bool = False) -> str:
        model_path = self._coder_model_path if is_coding else self._orchestrator_model_path
        model_name = self._coder_model_name if is_coding else self._orchestrator_model_name

        if self._backend == "mock":
            return self._generate_mock(prompt)
        if self._backend == "ollama":
            return await self._generate_ollama(prompt, model_name=model_name, correlation_id=correlation_id, session_id=session_id)

        await self._ensure_model_loaded(model_path, model_name)
        return await self._generate_real(prompt, correlation_id=correlation_id, session_id=session_id)

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        correlation_id: str | None = None,
        session_id: str = "default",
        is_coding: bool = False,
    ) -> dict[str, Any]:
        """Send chat messages with optional tool definitions and return structured response & tool calls."""
        model_name = self._coder_model_name if is_coding else self._orchestrator_model_name

        if self._backend == "mock":
            return self._chat_with_tools_mock(messages, tools)
        if self._backend == "ollama":
            return await self._chat_with_tools_ollama(
                messages=messages,
                tools=tools,
                model_name=model_name,
                correlation_id=correlation_id,
                session_id=session_id,
            )

        # Fallback for llama.cpp / transformers
        prompt = "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages)
        raw_res = await self.generate(prompt, correlation_id=correlation_id, session_id=session_id, is_coding=is_coding)
        cleaned_text, parsed_calls = ToolParser.parse_text_response(raw_res)
        return {
            "content": cleaned_text,
            "tool_calls": [tc.to_dict() for tc in parsed_calls],
        }

    def _chat_with_tools_mock(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        last_msg = ""
        for m in reversed(messages):
            content = m.get("content", "")
            if "<|user|>" in content:
                import re
                matches = re.findall(r"<\|user\|>\n(.*?)</s>", content, re.DOTALL)
                if matches:
                    last_msg = matches[-1].lower().strip()
                    break
            elif m.get("role") == "user":
                last_msg = content.lower().strip()
                break

        if any(trigger in last_msg for trigger in ("open notepad", "launch notepad", "start notepad")):
            return {
                "content": "Launching Notepad for you.",
                "tool_calls": [{"name": "launch_application", "arguments": {"application": "notepad"}}],
            }
        if any(trigger in last_msg for trigger in ("open chrome", "launch chrome", "open google chrome")):
            return {
                "content": "Opening Google Chrome.",
                "tool_calls": [{"name": "launch_application", "arguments": {"application": "chrome"}}],
            }
        if last_msg.startswith("search for ") or last_msg.startswith("google "):
            query = last_msg.replace("search for ", "").replace("google ", "").strip()
            return {
                "content": f"Searching the web for '{query}'.",
                "tool_calls": [{"name": "browser_search", "arguments": {"query": query}}],
            }
        if "system state" in last_msg or "system status" in last_msg:
            return {
                "content": "Retrieving current system perception state.",
                "tool_calls": [{"name": "get_system_state", "arguments": {}}],
            }
        if any(trigger in last_msg for trigger in ("installed apps", "installed applications", "search installed apps", "laptop apps", "applications on my laptop")):
            return {
                "content": "Searching for installed applications on your laptop.",
                "tool_calls": [{"name": "search_installed_apps", "arguments": {"query": ""}}],
            }
        if any(trigger in last_msg for trigger in ("scan documents", "scan files", "search files", "laptop files", "scan my documents")):
            return {
                "content": "Scanning laptop files for you.",
                "tool_calls": [{"name": "scan_laptop_files", "arguments": {"folder": "documents", "query": ""}}],
            }
        return {
            "content": "Hello! I am HELIX running in mock development mode.",
            "tool_calls": [],
        }

    async def _chat_with_tools_ollama(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model_name: str = "qwen3:4b",
        correlation_id: str | None = None,
        session_id: str = "default",
    ) -> dict[str, Any]:
        await self._ensure_session()
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self._temperature,
                "num_predict": self._max_tokens,
                "num_ctx": self._context_length,
            },
        }
        if tools:
            payload["tools"] = tools

        resp = await self._http_session.post(f"{self._ollama_url}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        message = data.get("message", {})
        content = message.get("content", "")
        raw_tool_calls = message.get("tool_calls")

        parsed_calls = []
        if raw_tool_calls:
            parsed_calls = ToolParser.parse_native_tool_calls(raw_tool_calls)

        # If no native tool calls returned in structure, check if content contains text tool calls
        if not parsed_calls and content:
            cleaned_text, text_calls = ToolParser.parse_text_response(content)
            if text_calls:
                content = cleaned_text
                parsed_calls = text_calls

        return {
            "content": content,
            "tool_calls": [tc.to_dict() for tc in parsed_calls],
        }

    def _generate_mock(self, prompt: str) -> str:
        return (
            "Hello! I'm HELIX running in mock development mode. "
            "I received your message and will process it properly "
            "once a real LLM backend is configured. "
            "Set HELIX_LLM_BACKEND=ollama to use your local Ollama models."
        )

    async def _generate_ollama(self, prompt: str, model_name: str, correlation_id: str | None = None, session_id: str = "default") -> str:
        await self._ensure_session()
        payload = {
            "model": model_name,
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
                if "response" in data:
                    chunk = data["response"]
                    full_text.append(chunk)
                    if correlation_id:
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

    async def _ensure_model_loaded(self, model_path: str, model_name: str) -> None:
        async with self._load_lock:
            if self._loaded and self._model_path != model_path:
                logger.info("Unloading previous model to load new model: %s", self._model_path)
                await self._unload_model_internal()

            if self._loaded:
                self._cancel_unload()
                return

            self._model_path = model_path
            self._model_name = model_name

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

        from foundation.security.model_integrity import verify_model_integrity
        verify_model_integrity(model_path)

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
        await self._unload_model_internal()

    async def _unload_model_internal(self) -> None:
        if not self._loaded:
            return

        await self._event_bus.publish_event(
            source="llm_engine",
            event_type="llm.model.unloading",
            payload={},
        )
        logger.info("Unloading model: %s", self._model_path)

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
