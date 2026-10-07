import os
import uuid
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from foundation.event_bus.event_bus import EventBus, HelixEvent
from core_ai.tool_calling.models import ToolCall
from core_ai.tool_calling.tool_registry import ToolRegistry
from core_ai.tool_calling.tool_executor import ToolExecutor

logger = logging.getLogger("helix.conversation_engine")

_ACTION_TRIGGERS = {
    "open", "launch", "start", "check", "search", "browse", "find", "look",
    "read", "send", "compose", "notify", "alert", "remind", "scan", "list",
    "show", "apps", "app", "application", "applications", "installed", "files",
    "file", "laptop", "pc", "computer", "docs", "documents", "desktop", "downloads",
    "create", "make", "write", "edit", "generate", "save", "word", "pdf", "docx",
    "note", "notes", "document"
}
_PLAN_TIMEOUT = 5.0
_STEP_TIMEOUT = 15.0
_RETRIEVAL_TIMEOUT = 0.5

_APP_DISPLAY_NAMES = {
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "edge": "Microsoft Edge",
    "microsoft edge": "Microsoft Edge",
    "firefox": "Firefox",
    "notepad": "Notepad",
    "calc": "Calculator",
    "calculator": "Calculator",
    "mspaint": "Paint",
    "paint": "Paint",
    "wt": "Terminal",
    "terminal": "Terminal",
    "explorer": "File Explorer",
    "file explorer": "File Explorer",
}


class ConversationEngine:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus

        self._max_history = int(os.getenv("HELIX_CONVERSATION_MAX_HISTORY", "20"))
        self._max_sessions = int(os.getenv("HELIX_CONVERSATION_MAX_SESSIONS", "50"))
        self._system_prompt = os.getenv(
            "HELIX_CONVERSATION_SYSTEM_PROMPT",
            "You are HELIX, an advanced personal AI operating system with direct native execution capabilities on this laptop. "
            "You CAN inspect and open applications, search the web, execute system tasks, scan and read laptop files, edit documents, and automate actions for the user. "
            "NEVER state that you are an AI language model without system access, laptop access, or hardware capabilities. "
            "When the user asks you to perform an action (find apps, scan files, read documents, search web), invoke the corresponding tool. "
            "When the user asks follow-up questions, asks what happened or what was found, or converses with you, answer naturally and helpfully based on the conversation history. "
            "NEVER ask the user to provide function calls or JSON format. You converse like an intelligent, friendly operating system assistant.",
        )
        self._response_timeout = int(os.getenv("HELIX_CONVERSATION_RESPONSE_TIMEOUT", "120"))

        self._pending_requests: dict[str, asyncio.Future[Any]] = {}
        self._pending_retrievals: dict[str, asyncio.Event] = {}
        self._pending_rag_searches: dict[str, asyncio.Future[list[dict]]] = {}
        self._pending_plans: dict[str, asyncio.Future[dict]] = {}
        self._pending_step_results: dict[str, asyncio.Future[dict]] = {}
        self._conversation_history: dict[str, list[dict[str, str]]] = {}
        self._sentence_buffers: dict[str, str] = {}
        self._subscriptions: list[str] = []
        self._event_handler_map: dict[str, Any] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._last_pending_permission: dict[str, dict[str, Any]] = {}

        self.tool_registry = ToolRegistry(load_defaults=True)
        self.tool_executor = ToolExecutor(self._event_bus, registry=self.tool_registry)

    async def start(self) -> None:
        self._event_handler_map = {
            "llm.token": self._handle_llm_token,
            "llm.generation.complete": self._handle_llm_complete,
            "llm.generation.error": self._handle_llm_error,
            "memory.conversation.retrieved": self._handle_memory_retrieved,
            "memory.warm.searched": self._handle_warm_searched,
            "conversation.user_message": self._handle_user_message,
            "plan.created": self._handle_plan_created,
            "plan.failed": self._handle_plan_failed,
            "automation.completed": self._handle_automation_completed,
            "automation.failed": self._handle_automation_failed,
            "automation.permission_needed": self._handle_permission_needed,
            "permission.requested": self._handle_permission_needed,
            "permission.granted": self._handle_permission_decided,
            "permission.denied": self._handle_permission_decided,
        }
        for event_type, handler in self._event_handler_map.items():
            self._event_bus.subscribe(event_type, handler)
        self._subscriptions = list(self._event_handler_map.keys())

        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        await self.tool_executor.start()

        logger.info("Conversation Engine started")

    async def stop(self) -> None:
        await self.tool_executor.stop()
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            self._cleanup_task = None

        for event_type, handler in self._event_handler_map.items():
            self._event_bus.unsubscribe(event_type, handler)
        self._subscriptions.clear()

        for d in (self._pending_requests, self._pending_plans, self._pending_step_results, self._pending_rag_searches):
            for f in d.values():
                if not f.done():
                    f.cancel()
            d.clear()

        logger.info("Conversation Engine stopped")

    # ── Public API ────────────────────────────────────────────────

    async def chat(self, message: str, session_id: str = "default") -> str:
        return await self._process_message(message, session_id)

    # ── Core Message Processing ───────────────────────────────────

    async def _process_message(self, text: str, session_id: str) -> str:
        if not text.strip():
            return ""

        if session_id not in self._conversation_history:
            self._conversation_history[session_id] = []
            self._prune_sessions()

        # Check if user is approving or denying a pending permission
        lower_clean = text.lower().strip().rstrip(".!?")
        approval_phrases = (
            "grant", "allow", "approve", "yes", "yes please", "yes open it",
            "yes do it", "go ahead", "proceed", "grant permission", "allow permission",
            "confirm", "accepted", "sure", "sure open it", "okay open it", "ok open it", "yes open",
            "open it", "please open it", "do it", "open please", "grant it", "allow it",
            "ok", "okay", "yep", "yeah", "i grant permission", "please proceed", "permission granted"
        )
        denial_phrases = (
            "deny", "reject", "don't open", "do not open", "cancel", "no", "no don't", "deny permission", "refuse"
        )
        last_perm = self._last_pending_permission.get(session_id)
        if last_perm and (lower_clean in denial_phrases or any(lower_clean.startswith(p) for p in ("deny", "reject", "cancel", "no "))):
            perm_id = last_perm.get("permission_id") or last_perm.get("id")
            if perm_id:
                await self._event_bus.publish_event(
                    source="conversation_engine",
                    event_type="permission.deny",
                    payload={"id": perm_id},
                )
            self._last_pending_permission.pop(session_id, None)
            response = "Permission denied. The request has been cancelled."
            self._conversation_history[session_id].append({"role": "user", "content": text})
            self._conversation_history[session_id].append({"role": "assistant", "content": response})
            return response

        if last_perm and (lower_clean in approval_phrases or any(lower_clean.startswith(p) for p in ("yes ", "grant ", "allow ", "open "))):
            perm_id = last_perm.get("permission_id") or last_perm.get("step_id") or last_perm.get("id")
            target = last_perm.get("target") or last_perm.get("params", {}).get("application") or last_perm.get("action", "action")
            display_target = _APP_DISPLAY_NAMES.get(str(target).lower(), str(target).title()) if isinstance(target, str) else target

            if perm_id:
                await self._event_bus.publish_event(
                    source="conversation_engine",
                    event_type="permission.grant",
                    payload={"id": perm_id},
                )
            await self._event_bus.publish_event(
                source="conversation_engine",
                event_type="automation.execute",
                payload={
                    "action": last_perm.get("action", "launch_application"),
                    "target": target,
                    "params": last_perm.get("params", {}),
                    "risk_level": "low",
                },
            )
            self._last_pending_permission.pop(session_id, None)

            response = f"Permission granted for {display_target}. Opening now!"
            self._conversation_history[session_id].append({"role": "user", "content": text})
            self._conversation_history[session_id].append({"role": "assistant", "content": response})
            await self._event_bus.publish_event(
                source="conversation_engine",
                event_type="memory.conversation.store",
                payload={"session_id": session_id, "role": "user", "content": text, "companion_id": "helix"},
            )
            await self._event_bus.publish_event(
                source="conversation_engine",
                event_type="memory.conversation.store",
                payload={"session_id": session_id, "role": "assistant", "content": response, "companion_id": "helix"},
            )
            return response

        is_action = self._is_action_message(text)

        retrieve_task = asyncio.create_task(self._retrieve_history(session_id))
        rag_task = asyncio.create_task(self._retrieve_rag_context(text))
        plan_task = asyncio.create_task(self._plan_and_execute(text, session_id)) if is_action else None

        await retrieve_task
        rag_memories = await rag_task if rag_task else []
        action_results = await plan_task if plan_task else []

        self._conversation_history[session_id].append({"role": "user", "content": text})

        await self._event_bus.publish_event(
            source="conversation_engine",
            event_type="memory.conversation.store",
            payload={
                "session_id": session_id,
                "role": "user",
                "content": text,
                "companion_id": "helix",
            },
        )

        permission_response = self._pending_permission_response(action_results, session_id=session_id)
        if permission_response:
            self._conversation_history[session_id].append({"role": "assistant", "content": permission_response})

            await self._event_bus.publish_event(
                source="conversation_engine",
                event_type="memory.conversation.store",
                payload={
                    "session_id": session_id,
                    "role": "assistant",
                    "content": permission_response,
                    "companion_id": "helix",
                },
            )

            return permission_response

        is_coding = self._is_coding_message(text)
        tools_spec = self.tool_registry.to_openai_tools() if is_action else None

        messages_list = self._build_messages(session_id, action_results, is_action=is_action, rag_memories=rag_memories)
        prompt = self._build_prompt(session_id, action_results, is_action=is_action, rag_memories=rag_memories)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        correlation_id = str(uuid.uuid4())
        self._pending_requests[correlation_id] = future

        await self._event_bus.publish_event(
            source="conversation_engine",
            event_type="llm.generate",
            payload={
                "prompt": prompt,
                "messages": messages_list,
                "session_id": session_id,
                "is_coding": is_coding,
                "tools": tools_spec,
            },
            correlation_id=correlation_id,
        )

        try:
            raw_res = await asyncio.wait_for(future, timeout=self._response_timeout)
            if isinstance(raw_res, dict):
                response = raw_res.get("response", "")
                tool_calls_data = raw_res.get("tool_calls", [])
            else:
                response = str(raw_res)
                tool_calls_data = []

            if tool_calls_data:
                executed_lines = []
                for tc_dict in tool_calls_data:
                    tc = ToolCall(name=tc_dict.get("name", ""), arguments=tc_dict.get("arguments", {}))
                    res = await self.tool_executor.execute(tc, session_id=session_id)
                    if res.success:
                        summary = self._format_tool_execution_summary(res.name, res.result)
                        executed_lines.append(summary)
                    else:
                        executed_lines.append(f"Tool `{res.name}`: {res.error or 'failed'}")
                if executed_lines:
                    response = "\n\n".join(executed_lines)
        except asyncio.TimeoutError:
            response = "I'm sorry, I took too long to respond. Please try again."
            logger.warning("LLM response timeout for session %s", session_id)
            # Publish stop event to cancel LLM generation and free resources
            await self._event_bus.publish_event(
                source="conversation_engine",
                event_type="llm.generate.stop",
                payload={"session_id": session_id},
            )
        except asyncio.CancelledError:
            response = "The request was cancelled."
        except Exception as e:
            logger.exception("Error during LLM generation for session %s", session_id)
            response = f"I encountered an error during response generation: {str(e)}"
        finally:
            self._pending_requests.pop(correlation_id, None)

        response = self._format_user_friendly_response(response, action_results, session_id=session_id)

        self._conversation_history[session_id].append({"role": "assistant", "content": response})

        await self._event_bus.publish_event(
            source="conversation_engine",
            event_type="memory.conversation.store",
            payload={
                "session_id": session_id,
                "role": "assistant",
                "content": response,
                "companion_id": "helix",
            },
        )

        return response

    def _format_tool_execution_summary(self, tool_name: str, result: Any) -> str:
        if not isinstance(result, dict):
            return str(result)

        if tool_name == "search_installed_apps":
            apps = result.get("apps", [])
            query = result.get("query", "")
            if not apps:
                return f"I searched your laptop, but no installed applications matching '{query}' were found." if query else "No installed applications found."
            lines = [f"Found {len(apps)} installed application(s)" + (f" matching '{query}':" if query else ":")]
            for a in apps[:10]:
                name = a.get("name") or a.get("executable") or "Unknown"
                path = a.get("path")
                lines.append(f"- **{name}**" + (f" (`{path}`)" if path else ""))
            if len(apps) > 10:
                lines.append(f"... and {len(apps) - 10} more.")
            return "\n".join(lines)

        if tool_name == "scan_laptop_files":
            files = result.get("files", [])
            query = result.get("query", "")
            target_dir = result.get("target_directory", "")
            if not files:
                return f"No files matching '{query}' found in `{target_dir}`." if query else f"No files found in `{target_dir}`."
            lines = [f"Found {len(files)} file(s) in `{target_dir}`" + (f" matching '{query}':" if query else ":")]
            for f in files[:10]:
                lines.append(f"- **{f.get('filename')}** ({f.get('size_kb', 0)} KB) — `{f.get('path')}`")
            if len(files) > 10:
                lines.append(f"... and {len(files) - 10} more.")
            return "\n".join(lines)

        if tool_name == "read_document":
            filename = result.get("filename", "")
            fmt = result.get("format", "").upper()
            content = result.get("content", "")
            if len(content) > 2000:
                content = content[:2000] + "...\n[Document content truncated]"
            return f"### Document: {filename} ({fmt})\n\n{content}"

        if tool_name == "read_file":
            filename = result.get("filename", "")
            content = result.get("content", "")
            if len(content) > 2000:
                content = content[:2000] + "...\n[Content truncated]"
            return f"### File: {filename}\n\n{content}"

        if tool_name == "edit_docx":
            msg = result.get("message", "Document updated.")
            path = result.get("path", "")
            return f"{msg} (`{path}`)"

        if tool_name == "generate_pdf":
            title = result.get("title", "")
            path = result.get("path", "")
            size = round(result.get("size_bytes", 0) / 1024, 1)
            return f"Successfully generated PDF: **{title}** ({size} KB at `{path}`)."

        if tool_name == "browser_search":
            url = result.get("url", "")
            query = result.get("query", "")
            if url:
                return f"Searched the web for **'{query}'**: [Open Search Results]({url})"
            return f"Searched the web for '{query}'."

        if tool_name == "launch_application":
            app = result.get("app", "")
            status = result.get("status", "launched")
            return f"Application **{app}** is {status}."

        if tool_name == "create_note":
            title = result.get("title", "")
            return f"Created note: **{title}**."

        if tool_name == "get_system_state":
            focused = result.get("focused_window") or {}
            title = focused.get("title", "Unknown")
            app = focused.get("application", "Desktop")
            return f"Current active window: **{title}** ({app})."

        if "message" in result:
            return str(result["message"])

        import json
        return json.dumps(result, indent=2)

    def _format_user_friendly_response(self, text: str, action_results: list[dict] | None = None, session_id: str | None = None) -> str:
        trimmed = text.strip()

        # Intercept common LLM refusal hallucinations when local model misinterprets tool definitions
        refusal_markers = (
            "I'm not actually running or executing the functions",
            "not a set of function calls or their results",
            "simply a description of what each function does",
            "beyond my capabilities as an AI assistant",
            "haven't provided any specific function calls",
            "provide the function name and its corresponding arguments",
        )
        if any(marker.lower() in trimmed.lower() for marker in refusal_markers):
            # Check if there is recent useful context in the conversation history
            if session_id and session_id in self._conversation_history:
                for entry in reversed(self._conversation_history[session_id]):
                    if entry.get("role") == "assistant" and not any(m.lower() in entry.get("content", "").lower() for m in refusal_markers):
                        prev = entry.get("content", "").strip()
                        if prev:
                            return f"Regarding your previous question, here is what was found:\n\n{prev}"
            return (
                "I have direct access to your laptop via HELIX's native tool execution system. "
                "I can search for installed applications, scan and read your files (.docx, .pdf, notes), "
                "browse the web, and launch programs. What would you like me to look up or do?"
            )

        # If output is raw JSON dictionary
        if trimmed.startswith("{") and trimmed.endswith("}"):
            try:
                import json
                data = json.loads(trimmed)
                if isinstance(data, dict):
                    name = data.get("name") or data.get("action") or data.get("tool")
                    args = data.get("arguments") or data.get("params") or {}
                    res = data.get("result", {})
                    url = data.get("url") or (res.get("url") if isinstance(res, dict) else None)
                    if url:
                        return f"I've opened the designated link in your browser: [{url}]({url})"
                    if name:
                        app = args.get("application") or args.get("app") or str(name).replace("_open", "").replace("open_", "")
                        display = _APP_DISPLAY_NAMES.get(app.lower(), app.title())
                        return f"I've launched {display} for you."
            except Exception:
                pass

        # If action_results had an opened URL and response didn't link it
        if action_results:
            for r in action_results:
                res_obj = r.get("result", {})
                if isinstance(res_obj, dict) and res_obj.get("url"):
                    u = res_obj["url"]
                    if u not in text:
                        return f"{text}\n\n[Open link in browser]({u})"

        return text

    # ── Action Detection ──────────────────────────────────────────

    def _is_action_message(self, message: str) -> bool:
        lower = message.lower().strip()
        if not lower:
            return False

        # Negations and feedback statements are never action commands
        negations = (
            "did not", "didn't", "not open", "not working", "haven't", "hasn't",
            "why didn't", "why did you not", "you did not", "you didn't",
            "could not", "couldn't", "won't", "wouldn't", "can't open", "cannot open",
            "fail", "failed", "repeat", "repeating"
        )
        if any(neg in lower for neg in negations):
            return False

        # Conversational questions are not action commands
        if lower.startswith(("who ", "what is", "where is", "where are", "how do", "why is", "why do", "tell me")):
            return False

        if any(lower.startswith(p) for p in ("open ", "launch ", "start ", "run ", "look up ", "search for ", "browse for ", "scan files", "list files", "read file", "check ")):
            return True

        # Check explicit action keywords with an app
        app_words = {"chrome", "notepad", "calculator", "calc", "terminal", "paint", "explorer", "edge", "firefox"}
        for word in lower.split():
            clean = word.strip(".,;:!?()[]{}")
            if clean in app_words and any(act in lower for act in ("open", "launch", "start", "run", "check")):
                return True

        for word in lower.split():
            clean = word.strip(".,;:!?()[]{}")
            if clean in _ACTION_TRIGGERS and len(clean) > 3:
                if any(lower.startswith(p) for p in ("can you ", "could you ", "please ", "i want to ", "help me ")):
                    return True

        return False

    def _is_coding_message(self, message: str) -> bool:
        lower = message.lower()
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
        if "```" in message or "def " in message or "import " in message or "const " in message or "let " in message:
            return True
        return False

    # ── History & RAG Retrieval ───────────────────────────────────

    async def _retrieve_history(self, session_id: str) -> None:
        if self._conversation_history.get(session_id):
            return
        retrieval_event = asyncio.Event()
        self._pending_retrievals[session_id] = retrieval_event
        await self._event_bus.publish_event(
            source="conversation_engine",
            event_type="memory.conversation.retrieve",
            payload={"session_id": session_id, "limit": self._max_history},
        )
        try:
            await asyncio.wait_for(retrieval_event.wait(), timeout=_RETRIEVAL_TIMEOUT)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        finally:
            self._pending_retrievals.pop(session_id, None)

    async def _retrieve_rag_context(self, query: str) -> list[dict]:
        """Perform semantic search against Warm Memory for RAG injection."""
        if not query.strip():
            return []
        corr_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future: asyncio.Future[list[dict]] = loop.create_future()
        self._pending_rag_searches[corr_id] = future

        await self._event_bus.publish_event(
            source="conversation_engine",
            event_type="memory.warm.search",
            payload={"query": query, "limit": 4, "min_score": 0.25},
            correlation_id=corr_id,
        )
        try:
            return await asyncio.wait_for(future, timeout=2.5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            return []
        except Exception as e:
            logger.warning("RAG retrieval exception: %s", e)
            return []
        finally:
            self._pending_rag_searches.pop(corr_id, None)

    def _format_rag_memories(self, rag_memories: list[dict]) -> str:
        lines = ["Retrieved Relevant Knowledge & Memories:"]
        for mem in rag_memories:
            text = mem.get("text", "")
            cat = mem.get("category", "memory")
            score = mem.get("score")
            score_str = f" [score: {score:.2f}]" if score is not None else ""
            lines.append(f"- ({cat}){score_str}: {text}")
        return "\n".join(lines)

    # ── Prompt & Messages Building ────────────────────────────────

    def _build_cognitive_context(self) -> str:
        username = os.getenv("USERNAME", os.getenv("USER", "vaibh"))
        display_name = "Vaibhav" if "vaibh" in username.lower() else username.capitalize()
        memory_path = os.getenv("HELIX_MEMORY_PATH", "./data/memory")
        qdrant_path = os.getenv("HELIX_QDRANT_PATH", r"F:\helix\memory\qdrant")

        lines = [
            "=== COGNITIVE SYSTEM PROFILE & USER ENVIRONMENT ===",
            f"- System Identity: HELIX, Personal AI Operating System (PAIOS) running locally with direct hardware and OS access on this laptop.",
            f"- User Identity: The user is {display_name} (system username: {username}), the owner and software engineer/developer of this laptop.",
            f"- What the user does: Developing software, building and enhancing HELIX, coding, managing workflows, and using this PC.",
            f"- Local Memory Storage: All chat sessions, conversation memory, and cognitive context are saved locally and privately on this machine. Long-term conversations are stored encrypted in `{memory_path}/conversations`, and semantic vector memories are indexed in the local Qdrant vector database at `{qdrant_path}`. Zero user data is sent to external cloud servers.",
            "- Capabilities: You have native execution capabilities, direct laptop tools (app launching, file scanning, web search, system monitoring), local Whisper STT, and Piper TTS.",
            "=== MANDATORY BEHAVIORAL CONSTRAINTS ===",
            "1. NEVER say 'As an AI language model, I don't have access to your personal information or chat history'.",
            f"2. When the user asks 'who am I?', identify them as {display_name}, the developer and owner of this system.",
            "3. When the user asks 'what do I do?', answer that they are a software engineer/developer working on this laptop, developing HELIX and related projects.",
            f"4. When the user asks 'where are you saving my chats?', explain clearly that chats and memories are saved locally and securely on their laptop in `{memory_path}/conversations` and the local Qdrant vector database at `{qdrant_path}`.",
            "5. Answer naturally, confidently, and warmly as an intelligent personal operating system companion.",
        ]
        return "\n".join(lines)

    def _build_messages(
        self,
        session_id: str,
        action_results: list[dict] | None = None,
        is_action: bool = False,
        rag_memories: list[dict] | None = None,
    ) -> list[dict[str, str]]:
        messages = []
        system_content = [
            self._system_prompt,
            self._build_cognitive_context(),
            f"Current time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        ]
        if rag_memories:
            system_content.append(self._format_rag_memories(rag_memories))
        if is_action:
            tool_guide = self.tool_registry.to_system_prompt_instruction()
            if tool_guide:
                system_content.append(tool_guide)
        if action_results:
            system_content.append(self._format_action_results(action_results))

        messages.append({"role": "system", "content": "\n\n".join(system_content)})

        history = self._conversation_history.get(session_id, [])
        for entry in history:
            messages.append({"role": entry["role"], "content": entry["content"]})
        return messages

    def _build_prompt(
        self,
        session_id: str,
        action_results: list[dict] | None = None,
        is_action: bool = False,
        rag_memories: list[dict] | None = None,
    ) -> str:
        history = self._conversation_history.get(session_id, [])
        parts = [
            f"<|system|>\n{self._system_prompt}</s>",
            f"<|system|>\n{self._build_cognitive_context()}</s>",
            f"<|system|>\nCurrent time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</s>",
        ]

        if rag_memories:
            parts.append(f"<|context:retrieved_memories|>\n{self._format_rag_memories(rag_memories)}</s>")

        if is_action:
            tool_guide = self.tool_registry.to_system_prompt_instruction()
            if tool_guide:
                parts.append(f"<|system|>\n{tool_guide}</s>")

        if action_results:
            parts.append(f"<|system|>\n{self._format_action_results(action_results)}</s>")

        for entry in history:
            role = entry["role"]
            content = entry["content"]
            if role == "user":
                parts.append(f"<|user|>\n{content}</s>")
            else:
                parts.append(f"<|assistant|>\n{content}</s>")

        parts.append("<|assistant|>\n")
        return "\n".join(parts)

    # ── Action Planning & Execution ───────────────────────────────

    async def _plan_and_execute(self, message: str, session_id: str) -> list[dict]:
        loop = asyncio.get_running_loop()

        plan_corr_id = str(uuid.uuid4())
        plan_future: asyncio.Future[dict] = loop.create_future()
        self._pending_plans[plan_corr_id] = plan_future

        await self._event_bus.publish_event(
            source="conversation_engine",
            event_type="plan.request",
            payload={
                "task": message,
                "session_id": session_id,
                "context": {"source": "conversation"},
            },
            correlation_id=plan_corr_id,
        )

        try:
            plan_data = await asyncio.wait_for(plan_future, timeout=_PLAN_TIMEOUT)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            return []
        except Exception as e:
            logger.exception("Error planning task for session %s", session_id)
            return []
        finally:
            self._pending_plans.pop(plan_corr_id, None)

        steps = plan_data.get("steps", [])
        plan_id = plan_data.get("plan_id", "")
        if not steps:
            return []

        results = []
        for step in steps:
            step_action = step.get("action", "")
            if step_action == "unknown":
                continue

            step_corr_id = str(uuid.uuid4())
            risk_level = step.get("risk_level", "low")

            if risk_level != "low":
                await self._event_bus.publish_event(
                    source="conversation_engine",
                    event_type="automation.execute_step",
                    payload={"plan_id": plan_id, "step": step, "risk_level": risk_level},
                    correlation_id=str(uuid.uuid4()),
                )
                results.append({
                    "step_id": step.get("step_id", ""),
                    "action": step_action,
                    "target": step.get("target", ""),
                    "params": step.get("params", {}),
                    "status": "needs_permission",
                    "risk_level": risk_level,
                    "message": f"This {'confirmation' if risk_level == 'high' else 'permission'}-risk action requires user approval before execution.",
                })
                continue

            step_future: asyncio.Future[dict] = loop.create_future()
            self._pending_step_results[step_corr_id] = step_future

            await self._event_bus.publish_event(
                source="conversation_engine",
                event_type="automation.execute_step",
                payload={"plan_id": plan_id, "step": step, "risk_level": risk_level},
                correlation_id=step_corr_id,
            )

            try:
                result = await asyncio.wait_for(step_future, timeout=_STEP_TIMEOUT)
                results.append(result)
            except asyncio.TimeoutError:
                results.append({
                    "step_id": step.get("step_id", ""),
                    "action": step_action,
                    "target": step.get("target", ""),
                    "status": "timeout",
                    "error": "Step execution timed out",
                })
            except asyncio.CancelledError:
                break
            finally:
                self._pending_step_results.pop(step_corr_id, None)

        return results

    def _pending_permission_response(self, results: list[dict], session_id: str = "default") -> str | None:
        pending = [r for r in results if r.get("status") == "needs_permission"]
        if not pending:
            return None

        first = pending[0]
        if session_id in self._last_pending_permission:
            first["permission_id"] = self._last_pending_permission[session_id].get("permission_id") or self._last_pending_permission[session_id].get("id")
        self._last_pending_permission[session_id] = first
        action = first.get("action", "this action")
        target = first.get("target") or first.get("params", {}).get("application") or "your device"
        risk = first.get("risk_level", "medium")
        if action == "launch_application":
            display_target = _APP_DISPLAY_NAMES.get(str(target).lower(), str(target).title()) if isinstance(target, str) else target
            return f"I can open {display_target}, but I need your {risk}-risk permission first. Please grant or deny the permission request."
        return f"I can do that, but I need your {risk}-risk permission first. Please grant or deny the permission request."

    def _format_action_results(self, results: list[dict]) -> str:
        lines = [
            "CRITICAL SYSTEM DIRECTIVE: You possess native system access capabilities on this device.",
            "Execution status of action requested by user:",
        ]
        for r in results:
            action = r.get("action", "unknown")
            status = r.get("status", "unknown")
            target = r.get("target", r.get("params", {}).get("application", ""))
            target_str = f" ({target})" if target else ""

            if status == "completed":
                lines.append(f"- {action}{target_str}: EXECUTED SUCCESSFULLY ({r.get('result', {})})")
            elif status == "needs_permission":
                risk = r.get("risk_level", "medium")
                lines.append(f"- {action}{target_str}: PENDING USER PERMISSION — Permission popup modal sent to user")
            elif status == "failed":
                lines.append(f"- {action}{target_str}: FAILED ({r.get('error', 'unknown error')})")
            elif status == "timeout":
                lines.append(f"- {action}{target_str}: TIMEOUT — action did not complete in time")
        lines.append("Confirm the execution status clearly and concisely. Do NOT state that you cannot access the computer.")
        return "\n".join(lines)

    # ── Event Handlers ────────────────────────────────────────────

    async def _handle_plan_created(self, event: HelixEvent) -> None:
        future = self._pending_plans.get(event.correlation_id)
        if future and not future.done():
            future.set_result({
                "plan_id": event.payload.get("plan_id", ""),
                "task": event.payload.get("task", ""),
                "steps": event.payload.get("steps", []),
            })

    async def _handle_plan_failed(self, event: HelixEvent) -> None:
        future = self._pending_plans.get(event.correlation_id)
        if future and not future.done():
            future.set_exception(RuntimeError(event.payload.get("error", "Plan failed")))

    async def _handle_automation_completed(self, event: HelixEvent) -> None:
        future = self._pending_step_results.get(event.correlation_id)
        if future and not future.done():
            future.set_result({
                "step_id": event.payload.get("step_id", ""),
                "action": event.payload.get("action", ""),
                "result": event.payload.get("result", {}),
                "status": "completed",
            })

    async def _handle_automation_failed(self, event: HelixEvent) -> None:
        future = self._pending_step_results.get(event.correlation_id)
        if future and not future.done():
            future.set_result({
                "step_id": event.payload.get("step_id", ""),
                "action": event.payload.get("action", ""),
                "error": event.payload.get("error", "Unknown error"),
                "status": "failed",
            })

    async def _handle_permission_needed(self, event: HelixEvent) -> None:
        perm_id = event.payload.get("permission_id") or event.payload.get("id")
        action = event.payload.get("action", "")
        target = event.payload.get("target") or event.payload.get("params", {}).get("application")
        session_id = event.payload.get("session_id", "default")
        self._last_pending_permission[session_id] = {
            "id": perm_id,
            "permission_id": perm_id,
            "action": action,
            "target": target,
            "params": event.payload.get("params", {}),
            "step_id": event.payload.get("step_id"),
            "plan_id": event.payload.get("plan_id"),
        }

    async def _handle_permission_decided(self, event: HelixEvent) -> None:
        perm_id = event.payload.get("id")
        for sess, perm in list(self._last_pending_permission.items()):
            if perm.get("id") == perm_id or perm.get("permission_id") == perm_id:
                self._last_pending_permission.pop(sess, None)

    async def _handle_llm_token(self, event: HelixEvent) -> None:
        corr_id = event.correlation_id
        token = event.payload.get("token", "")
        session_id = event.payload.get("session_id", "default")
        if not corr_id or not token:
            return

        buf = self._sentence_buffers.get(corr_id, "") + token
        import re
        match = re.search(r'([^.!?\n]+[.!?\n])', buf)
        if match:
            sentence = match.group(1).strip()
            remainder = buf[match.end():]
            self._sentence_buffers[corr_id] = remainder
            if len(sentence) >= 3:
                await self._event_bus.publish_event(
                    source="conversation_engine",
                    event_type="voice.tts",
                    payload={"session_id": session_id, "text": sentence},
                    correlation_id=corr_id,
                )
        else:
            self._sentence_buffers[corr_id] = buf

    async def _handle_llm_complete(self, event: HelixEvent) -> None:
        corr_id = event.correlation_id
        session_id = event.payload.get("session_id", "default")
        if corr_id in self._sentence_buffers:
            remaining = self._sentence_buffers.pop(corr_id, "").strip()
            if len(remaining) >= 2:
                await self._event_bus.publish_event(
                    source="conversation_engine",
                    event_type="voice.tts",
                    payload={"session_id": session_id, "text": remaining},
                    correlation_id=corr_id,
                )
        future = self._pending_requests.get(corr_id)
        if future and not future.done():
            tool_calls = event.payload.get("tool_calls", [])
            response_text = event.payload.get("response", "")
            if tool_calls:
                future.set_result({"response": response_text, "tool_calls": tool_calls})
            else:
                future.set_result(response_text)

    async def _handle_llm_error(self, event: HelixEvent) -> None:
        future = self._pending_requests.get(event.correlation_id)
        if future and not future.done():
            future.set_exception(RuntimeError(event.payload.get("error", "Unknown error")))

    async def _handle_memory_retrieved(self, event: HelixEvent) -> None:
        session_id = event.payload.get("session_id", "")
        entries = event.payload.get("entries", [])
        if session_id and entries:
            history = self._conversation_history.setdefault(session_id, [])
            for entry in entries:
                history.append({
                    "role": entry.get("role", "user"),
                    "content": entry.get("content", ""),
                })
            if len(history) > self._max_history:
                self._conversation_history[session_id] = history[-self._max_history:]

        if session_id in self._pending_retrievals:
            self._pending_retrievals[session_id].set()

    async def _handle_warm_searched(self, event: HelixEvent) -> None:
        future = self._pending_rag_searches.get(event.correlation_id)
        if future and not future.done():
            results = event.payload.get("results", [])
            future.set_result(results)

    async def _handle_user_message(self, event: HelixEvent) -> None:
        text = event.payload.get("text", "")
        session_id = event.payload.get("session_id", "default")
        response = await self._process_message(text, session_id)

    # ── Housekeeping ──────────────────────────────────────────────

    async def _cleanup_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(300)
                for d in (self._pending_requests, self._pending_plans, self._pending_step_results, self._pending_rag_searches):
                    stale = [k for k, f in d.items() if f.done()]
                    for k in stale:
                        d.pop(k, None)
                stale_ret = [sid for sid, ev in self._pending_retrievals.items() if ev.is_set()]
                for sid in stale_ret:
                    self._pending_retrievals.pop(sid, None)
        except asyncio.CancelledError:
            pass

    def _prune_sessions(self) -> None:
        if len(self._conversation_history) > self._max_sessions:
            excess = len(self._conversation_history) - self._max_sessions
            for sid in list(self._conversation_history)[:excess]:
                del self._conversation_history[sid]
