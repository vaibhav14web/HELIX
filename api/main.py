import os
import base64
import asyncio
import time
import re
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

from foundation.event_bus.event_bus import EventBus, HelixEvent
from foundation.config_manager.config_manager import ConfigManager
from foundation.storage_manager.storage_manager import StorageManager
from foundation.logger.logger import HelixLogger
from foundation.permission_manager.permission_manager import PermissionManager, PermissionRequest
from memory.conversation_memory.conversation_memory import ConversationMemory
from memory.preference_memory.preference_memory import PreferenceMemory
from memory.work_memory.work_memory import WorkMemory
from memory.explainability_engine.explainability_engine import ExplainabilityEngine
from core_ai.llm_engine.llm_engine import LLMEngine
from core_ai.conversation_engine.conversation_engine import ConversationEngine
from core_ai.voice_engine.voice_engine import VoiceEngine
from core_ai.wake_word_engine.wake_word_engine import WakeWordEngine
from orchestrator.orchestrator import Orchestrator

from context.context_aggregator.context_aggregator import ContextAggregator
from context.browser_engine.browser_engine import BrowserEngine
from context.file_intelligence_engine.file_intelligence_engine import FileIntelligenceEngine
from context.project_engine.project_engine import ProjectEngine
from context.system_monitor_engine.system_monitor_engine import SystemMonitorEngine

from action.planner_engine.planner_engine import PlannerEngine
from action.automation_engine.automation_engine import AutomationEngine
from action.action_executor.action_executor import ActionExecutor
from action.productivity_engine.productivity_engine import ProductivityEngine
from companion.coding_companion import CodingCompanion
from companion.learning_companion import LearningCompanion
from companion.productivity_companion import ProductivityCompanion


class SessionStartRequest(BaseModel):
    session_id: str


class ProjectRequest(BaseModel):
    session_id: str
    project: str


class ConversationStoreRequest(BaseModel):
    session_id: str
    role: str
    content: str
    companion_id: str | None = None


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class PreferenceStoreRequest(BaseModel):
    key: str
    value: Any
    category: str | None = None
    source: str | None = None


class TaskRequest(BaseModel):
    session_id: str
    task: str


class ContextUpdateRequest(BaseModel):
    session_id: str
    updates: dict[str, Any]


class ExplainLogRequest(BaseModel):
    action: str
    reasoning: str
    benefits: list[str] | None = None
    risks: list[str] | None = None
    alternatives: list[str] | None = None
    rationale: str | None = None
    source_module: str | None = None
    outcome: str | None = None


class ExplainQueryRequest(BaseModel):
    decision_id: str | None = None
    action: str | None = None
    limit: int | None = 10


event_bus = EventBus()
config_manager = ConfigManager()
storage_manager = StorageManager()
logger = HelixLogger()
perm_manager: PermissionManager | None = None
conv_mem: ConversationMemory | None = None
pref_mem: PreferenceMemory | None = None
work_mem: WorkMemory | None = None
expl_engine: ExplainabilityEngine | None = None
llm_engine: LLMEngine | None = None
conv_engine: ConversationEngine | None = None
voice_engine: VoiceEngine | None = None
wake_word_engine: WakeWordEngine | None = None
orch: Orchestrator | None = None
context_aggregator: ContextAggregator | None = None
planner_engine: PlannerEngine | None = None
automation_engine: AutomationEngine | None = None
action_executor: ActionExecutor | None = None
productivity_engine: ProductivityEngine | None = None
coding_companion: CodingCompanion | None = None
learning_companion: LearningCompanion | None = None
productivity_companion: ProductivityCompanion | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global conv_mem, pref_mem, work_mem, expl_engine, llm_engine, conv_engine, perm_manager
    global voice_engine, wake_word_engine, orch, context_aggregator
    global planner_engine, automation_engine, action_executor, productivity_engine
    global coding_companion, learning_companion, productivity_companion

    await config_manager.start()
    await storage_manager.start()
    await logger.start()

    mem_path = storage_manager.runtime("memory")

    perm_manager = PermissionManager(event_bus)
    conv_mem = ConversationMemory(event_bus, storage_path=str(mem_path))
    pref_mem = PreferenceMemory(event_bus, storage_path=str(mem_path))
    work_mem = WorkMemory(event_bus, storage_path=str(mem_path))
    expl_engine = ExplainabilityEngine(event_bus, storage_path=str(mem_path))
    llm_engine = LLMEngine(event_bus)
    conv_engine = ConversationEngine(event_bus)
    voice_engine = VoiceEngine(event_bus)
    wake_word_engine = WakeWordEngine(event_bus)
    orch = Orchestrator(event_bus)

    # Context modules with real implementation
    context_aggregator = ContextAggregator(event_bus)
    browser_engine = BrowserEngine(event_bus)
    file_intelligence_engine = FileIntelligenceEngine(event_bus)
    project_engine = ProjectEngine(event_bus)
    system_monitor_engine = SystemMonitorEngine(event_bus)

    # Action modules
    planner_engine = PlannerEngine(event_bus)
    automation_engine = AutomationEngine(event_bus)
    action_executor = ActionExecutor(event_bus)
    productivity_engine = ProductivityEngine(event_bus)

    await perm_manager.start()
    await conv_mem.start()
    await pref_mem.start()
    await work_mem.start()
    await expl_engine.start()
    await llm_engine.start()
    await conv_engine.start()
    await voice_engine.start()
    await wake_word_engine.start()
    await orch.start()

    await context_aggregator.start()
    await browser_engine.start()
    await file_intelligence_engine.start()
    await project_engine.start()
    await system_monitor_engine.start()

    await planner_engine.start()
    await automation_engine.start()
    await action_executor.start()
    await productivity_engine.start()

    coding_companion = CodingCompanion(event_bus)
    learning_companion = LearningCompanion(event_bus)
    productivity_companion = ProductivityCompanion(event_bus)

    await coding_companion.start()
    await learning_companion.start()
    await productivity_companion.start()

    # Wire real-time event → WebSocket bridge for chat UI
    async def _broadcast_listen_complete(event: HelixEvent) -> None:
        await _event_broadcaster.broadcast(
            "transcription",
            text=event.payload.get("text", ""),
            session_id=event.payload.get("session_id", "default"),
        )

    async def _broadcast_tts(event: HelixEvent) -> None:
        await _event_broadcaster.broadcast(
            "response",
            text=event.payload.get("text", ""),
            session_id=event.payload.get("session_id", "default"),
        )

    async def _broadcast_llm_chunk(event: HelixEvent) -> None:
        await _event_broadcaster.broadcast(
            "llm_chunk",
            text=event.payload.get("chunk", ""),
            session_id=event.payload.get("session_id", "default"),
        )

    async def _broadcast_permission_needed(event: HelixEvent) -> None:
        await _event_broadcaster.broadcast(
            "permission_needed",
            **event.payload,
            session_id=event.payload.get("session_id", "default"),
        )

    async def _broadcast_automation_completed(event: HelixEvent) -> None:
        await _event_broadcaster.broadcast(
            "automation_completed",
            **event.payload,
            session_id=event.payload.get("session_id", "default"),
        )

    async def _broadcast_automation_failed(event: HelixEvent) -> None:
        await _event_broadcaster.broadcast(
            "automation_failed",
            error=event.payload.get("error", ""),
            session_id=event.payload.get("session_id", "default"),
        )

    async def _broadcast_permission_granted(event: HelixEvent) -> None:
        await _event_broadcaster.broadcast(
            "permission_granted",
            id=event.payload.get("id", ""),
            session_id=event.payload.get("session_id", "default"),
        )

    async def _broadcast_permission_denied(event: HelixEvent) -> None:
        await _event_broadcaster.broadcast(
            "permission_denied",
            id=event.payload.get("id", ""),
            session_id=event.payload.get("session_id", "default"),
        )

    async def _broadcast_tts_start(event: HelixEvent) -> None:
        await _event_broadcaster.broadcast(
            "voice_speaking_start",
            session_id=event.payload.get("session_id", "default"),
        )

    async def _broadcast_tts_complete(event: HelixEvent) -> None:
        await _event_broadcaster.broadcast(
            "voice_speaking_stop",
            session_id=event.payload.get("session_id", "default"),
        )

    event_bus.subscribe("voice.listen.complete", _broadcast_listen_complete)
    event_bus.subscribe("voice.tts", _broadcast_tts)
    event_bus.subscribe("voice.tts.start", _broadcast_tts_start)
    event_bus.subscribe("voice.tts.complete", _broadcast_tts_complete)
    event_bus.subscribe("llm.generation.chunk", _broadcast_llm_chunk)
    event_bus.subscribe("automation.permission_needed", _broadcast_permission_needed)
    event_bus.subscribe("automation.completed", _broadcast_automation_completed)
    event_bus.subscribe("automation.failed", _broadcast_automation_failed)
    event_bus.subscribe("permission.granted", _broadcast_permission_granted)
    event_bus.subscribe("permission.denied", _broadcast_permission_denied)

    logger.info("HELIX fully initialized", module="system")

    yield

    event_bus.unsubscribe("permission.denied", _broadcast_permission_denied)
    event_bus.unsubscribe("permission.granted", _broadcast_permission_granted)
    event_bus.unsubscribe("automation.failed", _broadcast_automation_failed)
    event_bus.unsubscribe("automation.completed", _broadcast_automation_completed)
    event_bus.unsubscribe("automation.permission_needed", _broadcast_permission_needed)
    event_bus.unsubscribe("llm.generation.chunk", _broadcast_llm_chunk)
    event_bus.unsubscribe("voice.tts.complete", _broadcast_tts_complete)
    event_bus.unsubscribe("voice.tts.start", _broadcast_tts_start)
    event_bus.unsubscribe("voice.tts", _broadcast_tts)
    event_bus.unsubscribe("voice.listen.complete", _broadcast_listen_complete)

    await productivity_engine.stop()
    await coding_companion.stop()
    await learning_companion.stop()
    await productivity_companion.stop()
    await action_executor.stop()
    await automation_engine.stop()
    await planner_engine.stop()

    await context_aggregator.stop()
    await system_monitor_engine.stop()
    await project_engine.stop()
    await file_intelligence_engine.stop()
    await browser_engine.stop()

    await orch.stop()
    await wake_word_engine.stop()
    await voice_engine.stop()
    await conv_engine.stop()
    await llm_engine.stop()
    await expl_engine.stop()
    await work_mem.stop()
    await pref_mem.stop()
    await conv_mem.stop()
    await perm_manager.stop()
    await logger.stop()
    await storage_manager.stop()
    await config_manager.stop()


app = FastAPI(
    title="HELIX API",
    description="REST interface for HELIX",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("HELIX_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)


from starlette.types import ASGIApp, Scope, Receive, Send


class CatchAllOptionsMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "OPTIONS":
            headers = dict(scope.get("headers", []))
            has_origin = b"origin" in headers
            has_cors_method = b"access-control-request-method" in headers
            if has_origin and has_cors_method:
                await self.app(scope, receive, send)
                return
            response = Response(status_code=200)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


app.add_middleware(CatchAllOptionsMiddleware)


# ── Event-to-WebSocket bridge for real-time chat updates ──


class EventBroadcaster:
    def __init__(self):
        self._connections: set[WebSocket] = set()

    def connect(self, ws: WebSocket) -> None:
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    async def broadcast(self, event_type: str, **payload: Any) -> None:
        dead: set[WebSocket] = set()
        msg = {"type": event_type, **payload}
        for ws in list(self._connections):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.add(ws)
        self._connections -= dead


_event_broadcaster = EventBroadcaster()


@app.get("/health")
async def health():
    modules = [
        "config_manager",
        "storage_manager",
        "logger",
        "permission_manager",
        "event_bus",
        "conversation_memory",
        "preference_memory",
        "work_memory",
        "explainability_engine",
        "llm_engine",
        "conversation_engine",
        "voice_engine",
        "wake_word_engine",
        "orchestrator",
        "planner_engine",
        "automation_engine",
        "action_executor",
        "productivity_engine",
    ]
    state = orch.current_state if orch else "unknown"
    return {"status": "ok", "modules": modules, "state": state}


# ── Session ──


@app.post("/session/start")
async def session_start(req: SessionStartRequest):
    await event_bus.publish_event(
        source="api",
        event_type="session.start",
        payload={"session_id": req.session_id},
    )
    return {"session_id": req.session_id}


@app.post("/session/end")
async def session_end(req: SessionStartRequest):
    await event_bus.publish_event(
        source="api",
        event_type="session.end",
        payload={"session_id": req.session_id},
    )
    return {"session_id": req.session_id}


# ── Chat ──


@app.post("/chat")
async def chat(req: ChatRequest):
    if conv_engine is None:
        raise HTTPException(status_code=503, detail="Conversation engine not initialized")
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    response = await conv_engine.chat(req.message, req.session_id)

    async def _background_tts():
        if response.strip() and voice_engine is not None:
            try:
                audio_bytes = await voice_engine.synthesize(response)
                if audio_bytes:
                    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                    await _event_broadcaster.broadcast(
                        "chat_audio",
                        audio=audio_b64,
                        session_id=req.session_id,
                    )
            except Exception:
                logger.exception("Failed to synthesize voice response")

    asyncio.create_task(_background_tts())
    return {"response": response, "session_id": req.session_id}


# ── Voice ──


class SpeakRequest(BaseModel):
    text: str
    session_id: str = "default"


@app.post("/speak")
async def speak(req: SpeakRequest):
    if voice_engine is None:
        raise HTTPException(status_code=503, detail="Voice engine not initialized")
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    audio_b64 = None
    try:
        audio_bytes = await voice_engine.synthesize(req.text)
        if audio_bytes:
            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    except Exception as e:
        logger.exception("Failed to synthesize voice response")
        
    return {"status": "success", "session_id": req.session_id, "audio": audio_b64}


@app.post("/voice/command")
async def voice_command(file: UploadFile = File(...), session_id: str = Form("default")):
    if voice_engine is None or conv_engine is None:
        raise HTTPException(status_code=503, detail="Required engine not initialized")
    MAX_AUDIO_SIZE = 10 * 1024 * 1024
    audio_data = await file.read()
    if len(audio_data) > MAX_AUDIO_SIZE:
        raise HTTPException(status_code=413, detail="Audio file too large")
    await file.close()
    try:
        text = await voice_engine.transcribe(audio_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not text.strip():
        return {"text": "", "response": "", "audio": None}
    response = await conv_engine.chat(text, session_id)
    audio_b64 = None
    if response.strip():
        try:
            audio_bytes = await voice_engine.synthesize(response)
            if audio_bytes:
                audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        except Exception as e:
            logger.exception("Failed to synthesize voice response")
            
    return {"text": text, "response": response, "session_id": session_id, "audio": audio_b64}


@app.post("/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(...), session_id: str = Form("default")):
    if voice_engine is None:
        raise HTTPException(status_code=503, detail="Voice engine not initialized")
    MAX_AUDIO_SIZE = 10 * 1024 * 1024
    audio_data = await file.read()
    if len(audio_data) > MAX_AUDIO_SIZE:
        raise HTTPException(status_code=413, detail="Audio file too large")
    await file.close()
    try:
        text = await voice_engine.transcribe(audio_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"text": text, "session_id": session_id}


@app.post("/voice/interrupt")
async def voice_interrupt():
    if voice_engine is None:
        raise HTTPException(status_code=503, detail="Voice engine not initialized")
    await event_bus.publish_event(
        source="api",
        event_type="voice.interrupt",
        payload={},
    )
    return {"status": "interrupted"}


class ChatStopRequest(BaseModel):
    session_id: str = "default"


@app.post("/chat/stop")
async def chat_stop(req: ChatStopRequest):
    await event_bus.publish_event(
        source="api",
        event_type="llm.generate.stop",
        payload={"session_id": req.session_id},
    )
    return {"status": "stopped", "session_id": req.session_id}


@app.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket):
    await websocket.accept()
    session_id = websocket.query_params.get("session_id", "default")
    try:
        while True:
            data = await websocket.receive_bytes()
            if voice_engine is None or conv_engine is None:
                await websocket.send_json({"error": "Engine not ready"})
                continue
            text = await voice_engine.transcribe(data)
            if not text.strip():
                await websocket.send_json({"text": ""})
                continue
            await event_bus.publish_event(
                source="api",
                event_type="voice.listen.complete",
                payload={"session_id": session_id, "text": text},
            )
            await websocket.send_json({"text": text, "status": "processing"})
            response = await conv_engine.chat(text, session_id)
            if response.strip():
                await voice_engine.speak(response, session_id)
            await websocket.send_json({"response": response})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Voice WebSocket error")


@app.websocket("/ws/events")
async def events_websocket(websocket: WebSocket):
    await websocket.accept()
    _event_broadcaster.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Events WebSocket error")
    finally:
        _event_broadcaster.disconnect(websocket)


# ── Project ──


@app.post("/project/set")
async def set_project(req: ProjectRequest):
    await event_bus.publish_event(
        source="api",
        event_type="memory.work.set_project",
        payload={"session_id": req.session_id, "project": req.project},
    )
    return {"session_id": req.session_id, "project": req.project}


# ── Conversation Memory ──


@app.post("/conversation/store")
async def conversation_store(req: ConversationStoreRequest):
    await event_bus.publish_event(
        source="api",
        event_type="memory.conversation.store",
        payload={
            "session_id": req.session_id,
            "role": req.role,
            "content": req.content,
            "companion_id": req.companion_id or "default",
        },
    )
    return {"session_id": req.session_id, "role": req.role}


@app.get("/conversation/sessions")
async def conversation_sessions():
    if conv_mem is None:
        raise HTTPException(status_code=503, detail="Memory not initialized")
    sessions = await conv_mem.get_all_sessions()
    return {"sessions": sessions}


@app.get("/conversation/{session_id}")
async def conversation_get(session_id: str, limit: int = 50):
    if conv_mem is None:
        raise HTTPException(status_code=503, detail="Memory not initialized")
    entries = await conv_mem.get_session_history(session_id, limit)
    return {
        "session_id": session_id,
        "entries": [e.model_dump() for e in entries],
    }


@app.get("/conversation/search")
async def conversation_search(query: str, limit: int = 10):
    if conv_mem is None:
        raise HTTPException(status_code=503, detail="Memory not initialized")
    entries = await conv_mem.search_entries(query, limit)
    return {"query": query, "results": [e.model_dump() for e in entries]}


# ── Preferences ──


@app.post("/preference/store")
async def preference_store(req: PreferenceStoreRequest):
    await event_bus.publish_event(
        source="api",
        event_type="memory.preference.store",
        payload={
            "key": req.key,
            "value": req.value,
            "category": req.category or "general",
            "source": req.source or "user",
        },
    )
    return {"key": req.key}


@app.get("/preference/{key}")
async def preference_get(key: str):
    if pref_mem is None:
        raise HTTPException(status_code=503, detail="Memory not initialized")
    entry = pref_mem.get(key)
    return {"key": key, "entry": entry.model_dump() if entry else None}


@app.get("/preferences")
async def preferences_get_all(category: str | None = None):
    if pref_mem is None:
        raise HTTPException(status_code=503, detail="Memory not initialized")
    if category:
        entries = pref_mem.get_all(category)
    else:
        entries = pref_mem.get_all()
    return {"category": category, "entries": [e.model_dump() for e in entries]}


# ── Work ──


@app.post("/work/task/add")
async def work_add_task(req: TaskRequest):
    await event_bus.publish_event(
        source="api",
        event_type="memory.work.add_task",
        payload={"session_id": req.session_id, "task": req.task},
    )
    return {"session_id": req.session_id, "task": req.task}


@app.get("/work/context/{session_id}")
async def work_get_context(session_id: str):
    if work_mem is None:
        raise HTTPException(status_code=503, detail="Memory not initialized")
    session = work_mem.get_session(session_id)
    return {"session_id": session_id, "context": session.model_dump() if session else None}


@app.post("/work/context/update")
async def work_update_context(req: ContextUpdateRequest):
    await event_bus.publish_event(
        source="api",
        event_type="memory.work.update_context",
        payload={"session_id": req.session_id, "updates": req.updates},
    )
    return {"session_id": req.session_id}


# ── Aggregated Context ──


@app.get("/context/aggregated/{session_id}")
async def get_aggregated_context(session_id: str, force: bool = False):
    if context_aggregator is None:
        raise HTTPException(status_code=503, detail="Context aggregator not initialized")
    
    # Check if cache needs refreshing
    now = time.time()
    if force or not context_aggregator.is_cache_fresh(now):
        await event_bus.publish_event(
            source="api",
            event_type="context.request",
            payload={"session_id": session_id, "force": force},
        )
        # Give engines a brief window to respond and ContextAggregator to update cache
        await asyncio.sleep(0.15)
        
    return {
        "session_id": session_id,
        "context": context_aggregator.get_consolidated_context(session_id),
    }


# ── Explainability ──


@app.post("/memory/explain/log")
async def explain_log(req: ExplainLogRequest):
    payload = {
        "action": req.action,
        "reasoning": req.reasoning,
        "benefits": req.benefits or [],
        "risks": req.risks or [],
        "alternatives": req.alternatives or [],
        "rationale": req.rationale or "",
        "source_module": req.source_module or "unknown",
        "outcome": req.outcome or "pending",
    }
    await event_bus.publish_event(
        source="api",
        event_type="memory.explain.log",
        payload=payload,
    )
    return {"action": req.action}


@app.post("/memory/explain/query")
async def explain_query(req: ExplainQueryRequest):
    if expl_engine is None:
        raise HTTPException(status_code=503, detail="Memory not initialized")
    if req.decision_id:
        record = expl_engine.find_by_id(req.decision_id)
        return {"decision_id": req.decision_id, "record": record.model_dump() if record else None}
    if req.action:
        records = expl_engine.find_by_action(req.action, req.limit or 10)
    else:
        records = expl_engine.get_recent(req.limit or 10)
    return {"records": [r.model_dump() for r in records]}


# ── Profile / System ──


@app.get("/system/profile")
async def system_profile():
    import os as os_mod
    import getpass
    try:
        username = getpass.getuser()
    except Exception:
        username = os_mod.environ.get("USERNAME", "user")
    hostname = os_mod.environ.get("COMPUTERNAME", os_mod.uname().nodename) if hasattr(os_mod, 'uname') else os_mod.environ.get("COMPUTERNAME", "localhost")
    return {"username": username, "hostname": hostname}


@app.get("/stats/system")
async def system_stats():
    global conv_mem, pref_mem, expl_engine, perm_manager
    conv_count = 0
    pref_count = 0
    expl_count = 0
    perm_count = 0

    if conv_mem is not None:
        try:
            entries = await conv_mem.get_session_history("default", 1000)
            conv_count = len(entries)
        except Exception:
            pass

    if pref_mem is not None:
        pref_count = len(pref_mem.get_all())

    if expl_engine is not None:
        try:
            records = expl_engine.get_recent(1000)
            expl_count = len(records)
        except Exception:
            pass

    if perm_manager is not None:
        perm_count = len(perm_manager.history)

    return {
        "conversations": conv_count,
        "preferences": pref_count,
        "explanations": expl_count,
        "permissions_historical": perm_count,
        "pending_permissions": len(perm_manager.pending_requests) if perm_manager else 0,
    }


# ── Work / Tasks / Scratchpad ──


class ScratchpadSaveRequest(BaseModel):
    session_id: str
    content: str


@app.post("/work/scratchpad/save")
async def work_scratchpad_save(req: ScratchpadSaveRequest):
    await event_bus.publish_event(
        source="api",
        event_type="memory.work.update_context",
        payload={"session_id": req.session_id, "updates": {"scratchpad": req.content}},
    )
    return {"session_id": req.session_id, "saved": True}


@app.get("/work/scratchpad/{session_id}")
async def work_scratchpad_get(session_id: str):
    if work_mem is None:
        raise HTTPException(status_code=503, detail="Work memory not initialized")
    session = work_mem.get_session(session_id)
    scratchpad = ""
    if session and session.current_context:
        scratchpad = session.current_context.get("scratchpad", "")
    return {"session_id": session_id, "content": scratchpad}


@app.get("/work/tasks/{session_id}")
async def work_tasks_get(session_id: str):
    if work_mem is None:
        raise HTTPException(status_code=503, detail="Work memory not initialized")
    session = work_mem.get_session(session_id)
    tasks = session.open_tasks if session else []
    return {"session_id": session_id, "tasks": tasks}


@app.get("/work/sessions")
async def work_sessions_get():
    if work_mem is None:
        raise HTTPException(status_code=503, detail="Work memory not initialized")
    return {"sessions": [s.model_dump() for s in work_mem._sessions.values()]}


# ── Productivity & Logs ──


LOG_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) \[([A-Z]+)\] ([^:]+): (.*)$")


async def read_parsed_logs(limit: int = 100, level: str | None = None) -> list[dict[str, Any]]:
    if not logger or not logger._log_path:
        return []
    log_file = logger._log_path / "helix.log"
    if not log_file.exists():
        return []
        
    try:
        loop = asyncio.get_running_loop()
        def _read():
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                return f.readlines()
        lines = await loop.run_in_executor(None, _read)
    except Exception:
        return []
        
    parsed_entries = []
    current_entry = None
    
    for line in lines:
        line_str = line.strip("\n")
        match = LOG_PATTERN.match(line_str)
        if match:
            if current_entry:
                parsed_entries.append(current_entry)
            current_entry = {
                "timestamp": match.group(1),
                "level": match.group(2),
                "module": match.group(3),
                "message": match.group(4)
            }
        else:
            if current_entry:
                current_entry["message"] += "\n" + line_str
            else:
                current_entry = {
                    "timestamp": None,
                    "level": "INFO",
                    "module": "system",
                    "message": line_str
                }
    if current_entry:
        parsed_entries.append(current_entry)
        
    if level:
        level_upper = level.upper()
        parsed_entries = [e for e in parsed_entries if e["level"] == level_upper]
        
    parsed_entries.reverse()
    return parsed_entries[:limit]


@app.get("/productivity/patterns")
async def productivity_patterns_get():
    if productivity_engine is None:
        raise HTTPException(status_code=503, detail="Productivity engine not initialized")
    patterns = productivity_engine.get_patterns()
    return {"patterns": [p.to_dict() for p in patterns]}


@app.get("/productivity/suggestions")
async def productivity_suggestions_get(status: str | None = None):
    if productivity_engine is None:
        raise HTTPException(status_code=503, detail="Productivity engine not initialized")
    suggestions = productivity_engine.get_suggestions(status=status)
    return {"suggestions": [s.to_dict() for s in suggestions]}


class SuggestionActionRequest(BaseModel):
    suggestion_id: str


@app.post("/productivity/suggestion/accept")
async def productivity_suggestion_accept(req: SuggestionActionRequest):
    await event_bus.publish_event(
        source="api",
        event_type="productivity.suggestion.accept",
        payload={"suggestion_id": req.suggestion_id},
    )
    return {"status": "accepted", "suggestion_id": req.suggestion_id}


@app.post("/productivity/suggestion/dismiss")
async def productivity_suggestion_dismiss(req: SuggestionActionRequest):
    await event_bus.publish_event(
        source="api",
        event_type="productivity.suggestion.dismiss",
        payload={"suggestion_id": req.suggestion_id},
    )
    return {"status": "dismissed", "suggestion_id": req.suggestion_id}


@app.get("/logs")
async def logs_get(level: str | None = None, limit: int = 100):
    if logger is None or not hasattr(logger, "_log_path"):
        raise HTTPException(status_code=503, detail="Logger not initialized")
    try:
        entries = await read_parsed_logs(limit=limit, level=level)
        return {"logs": entries}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Permissions ──


class PermissionRequestPayload(BaseModel):
    action: str
    reasoning: str
    benefits: list[str] | None = None
    risks: list[str] | None = None
    alternatives: list[str] | None = None
    source_module: str = "unknown"
    resources: list[str] | None = None
    scope: str | None = None
    level: str | None = None


class PermissionDecisionPayload(BaseModel):
    id: str


class AutoApproveAddRequest(BaseModel):
    pattern: str


@app.post("/permission/request")
async def permission_request(req: PermissionRequestPayload):
    if perm_manager is None:
        raise HTTPException(status_code=503, detail="Permission manager not initialized")
    p = await perm_manager.request(
        action=req.action,
        reasoning=req.reasoning,
        benefits=req.benefits,
        risks=req.risks,
        alternatives=req.alternatives,
        source_module=req.source_module,
        resources=req.resources,
    )
    return {
        "id": p.id,
        "action": p.action,
        "status": p.status,
        "reasoning": p.reasoning,
        "benefits": p.benefits,
        "risks": p.risks,
        "alternatives": p.alternatives,
        "resources": p.resources,
        "source_module": p.source_module,
        "created_at": p.created_at,
        "scope": req.scope or p.action,
        "level": req.level or "read",
    }


@app.post("/permission/grant")
async def permission_grant(req: PermissionDecisionPayload):
    if perm_manager is None:
        raise HTTPException(status_code=503, detail="Permission manager not initialized")
    known_request = any(p.id == req.id for p in perm_manager.pending_requests)
    if known_request:
        await event_bus.publish_event(
            source="api",
            event_type="permission.grant",
            payload={"id": req.id},
        )
    else:
        await event_bus.publish_event(
            source="api",
            event_type="permission.granted",
            payload={"id": req.id},
        )
    return {"id": req.id, "status": "granted"}


@app.post("/permission/deny")
async def permission_deny(req: PermissionDecisionPayload):
    if perm_manager is None:
        raise HTTPException(status_code=503, detail="Permission manager not initialized")
    known_request = any(p.id == req.id for p in perm_manager.pending_requests)
    if known_request:
        await event_bus.publish_event(
            source="api",
            event_type="permission.deny",
            payload={"id": req.id},
        )
    else:
        await event_bus.publish_event(
            source="api",
            event_type="permission.denied",
            payload={"id": req.id},
        )
    return {"id": req.id, "status": "denied"}


@app.post("/permission/auto-approve")
async def add_auto_approve_pattern(req: AutoApproveAddRequest):
    if perm_manager is None:
        raise HTTPException(status_code=503, detail="Permission manager not initialized")
    await event_bus.publish_event(
        source="api",
        event_type="permission.auto_approve.add",
        payload={"pattern": req.pattern},
    )
    return {"pattern": req.pattern, "status": "added"}


@app.delete("/permission/auto-approve")
async def remove_auto_approve_pattern(pattern: str):
    if perm_manager is None:
        raise HTTPException(status_code=503, detail="Permission manager not initialized")
    await event_bus.publish_event(
        source="api",
        event_type="permission.auto_approve.remove",
        payload={"pattern": pattern},
    )
    return {"pattern": pattern, "status": "removed"}


@app.get("/permission/history")
async def permission_history():
    if perm_manager is None:
        raise HTTPException(status_code=503, detail="Permission manager not initialized")
    return {
        "history": [
            {
                "id": r.id,
                "action": r.action,
                "reasoning": r.reasoning,
                "benefits": r.benefits,
                "risks": r.risks,
                "alternatives": r.alternatives,
                "source_module": r.source_module,
                "resources": r.resources,
                "status": r.status,
                "created_at": r.created_at,
                "decided_at": r.decided_at,
            }
            for r in perm_manager.history
        ]
    }


@app.get("/permission/patterns")
async def permission_patterns():
    if perm_manager is None:
        raise HTTPException(status_code=503, detail="Permission manager not initialized")
    return {"patterns": perm_manager.auto_approve_patterns}


@app.get("/permission/pending")
async def permission_pending():
    if perm_manager is None:
        raise HTTPException(status_code=503, detail="Permission manager not initialized")
    requests = perm_manager.pending_requests
    return {
        "pending": [
            {
                "id": r.id,
                "action": r.action,
                "reasoning": r.reasoning,
                "benefits": r.benefits,
                "risks": r.risks,
                "alternatives": r.alternatives,
                "source_module": r.source_module,
                "resources": r.resources,
                "created_at": r.created_at,
            }
            for r in requests
        ]
    }


# ── State ──


@app.get("/state")
async def get_state():
    current = orch.current_state if orch else "unknown"
    return {"state": current}


# ── Direct invocation ──


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("HELIX_API_PORT", "8000"))
    host = os.getenv("HELIX_API_HOST", "127.0.0.1")
    uvicorn.run("api.main:app", host=host, port=port, reload=True)
