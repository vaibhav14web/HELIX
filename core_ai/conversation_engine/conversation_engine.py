import os
import uuid
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from foundation.event_bus.event_bus import EventBus, HelixEvent

logger = logging.getLogger("helix.conversation_engine")

_ACTION_TRIGGERS = {"open", "launch", "start", "check", "search", "browse", "find", "look", "read", "send", "compose", "notify", "alert", "remind"}
_PLAN_TIMEOUT = 5.0
_STEP_TIMEOUT = 15.0
_RETRIEVAL_TIMEOUT = 0.5


class ConversationEngine:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus

        self._max_history = int(os.getenv("HELIX_CONVERSATION_MAX_HISTORY", "20"))
        self._max_sessions = int(os.getenv("HELIX_CONVERSATION_MAX_SESSIONS", "50"))
        self._system_prompt = os.getenv(
            "HELIX_CONVERSATION_SYSTEM_PROMPT",
            "You are HELIX, a context-aware personal cognitive operating system. "
            "You are helpful, concise, and respect user privacy. "
            "Answer questions and assist with tasks. "
            "When you don't know something, say so.",
        )
        self._response_timeout = int(os.getenv("HELIX_CONVERSATION_RESPONSE_TIMEOUT", "30"))

        self._pending_requests: dict[str, asyncio.Future[str]] = {}
        self._pending_retrievals: dict[str, asyncio.Event] = {}
        self._pending_plans: dict[str, asyncio.Future[dict]] = {}
        self._pending_step_results: dict[str, asyncio.Future[dict]] = {}
        self._conversation_history: dict[str, list[dict[str, str]]] = {}
        self._subscriptions: list[str] = []
        self._event_handler_map: dict[str, Any] = {}
        self._cleanup_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._event_handler_map = {
            "llm.generation.complete": self._handle_llm_complete,
            "llm.generation.error": self._handle_llm_error,
            "memory.conversation.retrieved": self._handle_memory_retrieved,
            "conversation.user_message": self._handle_user_message,
            "plan.created": self._handle_plan_created,
            "plan.failed": self._handle_plan_failed,
            "automation.completed": self._handle_automation_completed,
            "automation.failed": self._handle_automation_failed,
        }
        for event_type, handler in self._event_handler_map.items():
            self._event_bus.subscribe(event_type, handler)
        self._subscriptions = list(self._event_handler_map.keys())

        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info("Conversation Engine started")

    async def stop(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            self._cleanup_task = None

        for event_type, handler in self._event_handler_map.items():
            self._event_bus.unsubscribe(event_type, handler)
        self._subscriptions.clear()

        for d in (self._pending_requests, self._pending_plans, self._pending_step_results):
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

        is_action = self._is_action_message(text)

        retrieve_task = asyncio.create_task(self._retrieve_history(session_id))
        plan_task = asyncio.create_task(self._plan_and_execute(text, session_id)) if is_action else None

        await retrieve_task
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

        permission_response = self._pending_permission_response(action_results)
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

        prompt = self._build_prompt(session_id, action_results)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        correlation_id = str(uuid.uuid4())
        self._pending_requests[correlation_id] = future

        await self._event_bus.publish_event(
            source="conversation_engine",
            event_type="llm.generate",
            payload={"prompt": prompt, "session_id": session_id},
            correlation_id=correlation_id,
        )

        try:
            response = await asyncio.wait_for(future, timeout=self._response_timeout)
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

    # ── Action Detection ──────────────────────────────────────────

    def _is_action_message(self, message: str) -> bool:
        lower = message.lower().strip()
        if not lower:
            return False
        if any(lower.startswith(p) for p in ("look up", "search for", "browse for")):
            return True
        for word in lower.split():
            if word in _ACTION_TRIGGERS:
                return True
        return False

    # ── History Retrieval ─────────────────────────────────────────

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

    # ── Prompt Building ───────────────────────────────────────────

    def _build_prompt(self, session_id: str, action_results: list[dict] | None = None) -> str:
        history = self._conversation_history.get(session_id, [])
        parts = [f"<|system|>\n{self._system_prompt}</s>"]
        parts.append(f"<|system|>\nCurrent time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</s>")

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

    def _pending_permission_response(self, results: list[dict]) -> str | None:
        pending = [r for r in results if r.get("status") == "needs_permission"]
        if not pending:
            return None

        first = pending[0]
        action = first.get("action", "this action")
        target = first.get("target") or first.get("params", {}).get("application") or "your device"
        risk = first.get("risk_level", "medium")
        if action == "launch_application":
            return f"I can open {target}, but I need your {risk}-risk permission first. Please grant or deny the permission request."
        return f"I can do that, but I need your {risk}-risk permission first. Please grant or deny the permission request."

    def _format_action_results(self, results: list[dict]) -> str:
        lines = [
            "You have the ability to perform actions on the user's system.",
            "Recent action results for the current user request:",
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
                lines.append(f"- {action}{target_str}: NOT EXECUTED — {risk.upper()}-risk action requires user permission")
            elif status == "failed":
                lines.append(f"- {action}{target_str}: FAILED ({r.get('error', 'unknown error')})")
            elif status == "timeout":
                lines.append(f"- {action}{target_str}: TIMEOUT — action did not complete in time")
        lines.append("Respond naturally about the action results above.")
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

    async def _handle_llm_complete(self, event: HelixEvent) -> None:
        future = self._pending_requests.get(event.correlation_id)
        if future and not future.done():
            future.set_result(event.payload.get("response", ""))

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

    async def _handle_user_message(self, event: HelixEvent) -> None:
        text = event.payload.get("text", "")
        session_id = event.payload.get("session_id", "default")
        response = await self._process_message(text, session_id)

    # ── Housekeeping ──────────────────────────────────────────────

    async def _cleanup_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(300)
                for d in (self._pending_requests, self._pending_plans, self._pending_step_results):
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
