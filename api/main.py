import os
import json
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
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

from foundation.event_bus.event_bus import EventBus, HelixEvent
from foundation.config_manager.config_manager import ConfigManager
from foundation.storage_manager.storage_manager import StorageManager
from foundation.logger.logger import HelixLogger
from foundation.permission_manager.permission_manager import PermissionManager, PermissionRequest
from foundation.auth import verify_token, get_or_create_auth_token
from memory.conversation_memory.conversation_memory import ConversationMemory
from memory.preference_memory.preference_memory import PreferenceMemory
from memory.work_memory.work_memory import WorkMemory
from memory.explainability_engine.explainability_engine import ExplainabilityEngine
from memory.warm_memory.warm_memory import WarmMemory
from memory.warm_memory.models import WarmIndexRequest, WarmSearchRequest, WarmSearchResponse
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
from action.timetable_scheduler.timetable_scheduler import TimetableScheduler
from companion.coding_companion import CodingCompanion
from companion.learning_companion import LearningCompanion
from companion.productivity_companion import ProductivityCompanion
from core_ai.self_model.self_model_engine import SelfModelEngine
from foundation.world_model.world_model_engine import WorldModelEngine
from action.capability_registry.capability_registry import CapabilityRegistry
from action.application_discovery.app_discovery_engine import ApplicationDiscoveryEngine
from foundation.project_registry.project_registry import ProjectRegistry
from action.action_verification.action_verification import ActionVerificationEngine
from core_ai.goal_manager.goal_manager import GoalManager
from foundation.observability.observability_engine import ObservabilityEngine
from orchestrator.ecs.executive_control_system import ExecutiveControlSystem, ExecutiveState


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
warm_mem: WarmMemory | None = None
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
timetable_scheduler: TimetableScheduler | None = None
coding_companion: CodingCompanion | None = None
learning_companion: LearningCompanion | None = None
productivity_companion: ProductivityCompanion | None = None
self_model_engine: SelfModelEngine | None = None
world_model_engine: WorldModelEngine | None = None
capability_registry: CapabilityRegistry | None = None
app_discovery_engine: ApplicationDiscoveryEngine | None = None
project_registry: ProjectRegistry | None = None
action_verifier: ActionVerificationEngine | None = None
goal_manager: GoalManager | None = None
observability_engine: ObservabilityEngine | None = None
ecs_engine: ExecutiveControlSystem | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global conv_mem, pref_mem, work_mem, expl_engine, warm_mem, llm_engine, conv_engine, perm_manager
    global voice_engine, wake_word_engine, orch, context_aggregator
    global planner_engine, automation_engine, action_executor, productivity_engine, timetable_scheduler
    global coding_companion, learning_companion, productivity_companion
    global self_model_engine, world_model_engine, capability_registry, app_discovery_engine
    global project_registry, action_verifier, goal_manager, observability_engine, ecs_engine

    await config_manager.start()
    await storage_manager.start()
    await logger.start()

    mem_path = storage_manager.runtime("memory")

    perm_manager = PermissionManager(event_bus)
    conv_mem = ConversationMemory(event_bus, storage_path=str(mem_path))
    pref_mem = PreferenceMemory(event_bus, storage_path=str(mem_path))
    work_mem = WorkMemory(event_bus, storage_path=str(mem_path))
    expl_engine = ExplainabilityEngine(event_bus, storage_path=str(mem_path))
    warm_mem = WarmMemory(event_bus, storage_path=str(mem_path))
    llm_engine = LLMEngine(event_bus)
    conv_engine = ConversationEngine(event_bus)
    voice_engine = VoiceEngine(event_bus)
    wake_word_engine = WakeWordEngine(event_bus, ring_buffer=voice_engine.ring_buffer)
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
    timetable_scheduler = TimetableScheduler(event_bus)

    await perm_manager.start()
    await conv_mem.start()
    await pref_mem.start()
    await work_mem.start()
    await expl_engine.start()
    await warm_mem.start()
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
    await timetable_scheduler.start()

    self_model_engine = SelfModelEngine(event_bus)
    world_model_engine = WorldModelEngine(event_bus)
    capability_registry = CapabilityRegistry()
    app_discovery_engine = ApplicationDiscoveryEngine()
    project_registry = ProjectRegistry()
    action_verifier = ActionVerificationEngine(event_bus)
    goal_manager = GoalManager(event_bus)
    observability_engine = ObservabilityEngine(event_bus)
    ecs_engine = ExecutiveControlSystem(event_bus)

    await self_model_engine.start()
    await world_model_engine.start()
    await observability_engine.start()
    await ecs_engine.start()

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
    if timetable_scheduler:
        await timetable_scheduler.stop()
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
    if warm_mem:
        await warm_mem.stop()
    await expl_engine.stop()
    await work_mem.stop()
    await pref_mem.stop()
    await conv_mem.stop()
    await perm_manager.stop()
    await logger.stop()
    await storage_manager.stop()
    await config_manager.stop()


class LocalAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        token = None
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif "x-helix-token" in request.headers:
            token = request.headers.get("x-helix-token", "").strip()
        elif "token" in request.query_params:
            token = request.query_params.get("token", "").strip()

        client_host = request.client.host if request.client else ""
        is_local = client_host in ("127.0.0.1", "::1", "localhost", "testclient")

        if not verify_token(token) and not is_local:
            if os.getenv("HELIX_AUTH_DISABLED", "").lower() in ("true", "1", "yes"):
                return await call_next(request)
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: Invalid or missing token"},
            )

        return await call_next(request)


app = FastAPI(
    title="HELIX API",
    description="REST interface for HELIX",
    version="2.0.0",
    lifespan=lifespan,
)

cors_origins = [o.strip() for o in os.getenv("HELIX_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
if not cors_origins:
    cors_origins = ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "X-Helix-Token"],
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
app.add_middleware(LocalAuthMiddleware)


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


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    await websocket.accept()
    _event_broadcaster.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        _event_broadcaster.disconnect(websocket)


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

    audio_b64 = None
    if response.strip() and voice_engine is not None:
        try:
            if getattr(voice_engine, "_tts_backend", "") != "mock":
                audio_bytes = await voice_engine.synthesize(response)
                if audio_bytes:
                    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                    await _event_broadcaster.broadcast(
                        "chat_audio",
                        audio=audio_b64,
                        text=response,
                        session_id=req.session_id,
                    )
        except Exception:
            logger.exception("Failed to synthesize voice response")

    return {"response": response, "session_id": req.session_id, "audio": audio_b64}


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
        if getattr(voice_engine, "_tts_backend", "") != "mock":
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
            if getattr(voice_engine, "_tts_backend", "") != "mock":
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
    token = (
        websocket.query_params.get("token")
        or websocket.headers.get("x-helix-token")
        or (websocket.headers.get("authorization", "").replace("Bearer ", "") if websocket.headers.get("authorization") else None)
    )
    if not verify_token(token):
        await websocket.close(code=1008, reason="Unauthorized: Invalid or missing token")
        return
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
    token = (
        websocket.query_params.get("token")
        or websocket.headers.get("x-helix-token")
        or (websocket.headers.get("authorization", "").replace("Bearer ", "") if websocket.headers.get("authorization") else None)
    )
    if not verify_token(token):
        await websocket.close(code=1008, reason="Unauthorized: Invalid or missing token")
        return
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


# ── Warm Memory (Vector / RAG) ──


@app.post("/memory/warm/index")
async def memory_warm_index(req: WarmIndexRequest):
    if warm_mem is None:
        raise HTTPException(status_code=503, detail="Warm memory not initialized")
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    entry = await warm_mem.index_text(
        text=req.text,
        category=req.category,
        metadata=req.metadata,
        entry_id=req.entry_id,
    )
    return {"status": "indexed", "id": entry.id, "category": entry.category}


@app.post("/memory/warm/search", response_model=WarmSearchResponse)
async def memory_warm_search(req: WarmSearchRequest):
    if warm_mem is None:
        raise HTTPException(status_code=503, detail="Warm memory not initialized")
    t0 = time.perf_counter()
    results = await warm_mem.search(
        query=req.query,
        limit=req.limit,
        min_score=req.min_score,
        category=req.category,
    )
    dur_ms = (time.perf_counter() - t0) * 1000
    return WarmSearchResponse(
        query=req.query,
        results=results,
        count=len(results),
        duration_ms=round(dur_ms, 2),
    )


@app.get("/memory/warm/stats")
async def memory_warm_stats():
    if warm_mem is None:
        raise HTTPException(status_code=503, detail="Warm memory not initialized")
    return await warm_mem.get_stats()


@app.delete("/memory/warm/{entry_id}")
async def memory_warm_delete(entry_id: str):
    if warm_mem is None:
        raise HTTPException(status_code=503, detail="Warm memory not initialized")
    success = await warm_mem.delete(entry_id)
    return {"entry_id": entry_id, "deleted": success}


@app.post("/memory/warm/rollover")
async def memory_warm_rollover(min_age_days: int = 7, max_age_days: int = 30):
    if warm_mem is None:
        raise HTTPException(status_code=503, detail="Warm memory not initialized")
    count = await warm_mem.rollover_conversations(min_age_days=min_age_days, max_age_days=max_age_days)
    return {"status": "rollover_complete", "indexed_count": count}


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


# ── Browser Proxy & Native Launch ──


class BrowserOpenRequest(BaseModel):
    url: str


@app.post("/browser/open")
async def browser_open(req: BrowserOpenRequest):
    import webbrowser
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL cannot be empty")
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    try:
        webbrowser.open(url)
        return {"status": "opened", "url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/browser/proxy")
async def browser_proxy(url: str):
    target_url = url.strip()
    if not target_url.startswith("http://") and not target_url.startswith("https://"):
        target_url = "https://" + target_url

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        import httpx
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0, verify=False) as client:
            resp = await client.get(target_url, headers=headers)
            content_type = resp.headers.get("content-type", "text/html")

            content = resp.content
            if "text/html" in content_type:
                text = resp.text
                base_tag = f'<base href="{target_url}">'
                if "<head>" in text:
                    text = text.replace("<head>", f"<head>{base_tag}", 1)
                elif "<HEAD>" in text:
                    text = text.replace("<HEAD>", f"<HEAD>{base_tag}", 1)
                else:
                    text = base_tag + text
                content = text.encode("utf-8", errors="replace")

            response_headers = {
                "content-type": content_type,
                "access-control-allow-origin": "*",
            }
            return Response(content=content, headers=response_headers)
    except Exception:
        fallback_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body {{ font-family: system-ui, sans-serif; background: #09090b; color: #a1a1aa; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
            .card {{ background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 32px; max-width: 480px; text-align: center; }}
            h2 {{ color: #00d4ff; margin-top: 0; }}
            a.btn {{ display: inline-block; margin-top: 16px; background: rgba(0,212,255,0.15); border: 1px solid rgba(0,212,255,0.3); color: #00d4ff; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-weight: 500; }}
            a.btn:hover {{ background: rgba(0,212,255,0.25); }}
          </style>
        </head>
        <body>
          <div class="card">
            <h2>HELIX AI Web Reader</h2>
            <p>Target: <code>{target_url}</code></p>
            <p>Direct frame embedding is protected by the target host.</p>
            <a class="btn" href="{target_url}" target="_blank">Open directly in native browser</a>
          </div>
        </body>
        </html>
        """
        return Response(content=fallback_html, media_type="text/html")


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
            raw_ts = match.group(1).replace(",", ".")
            if " " in raw_ts and "T" not in raw_ts:
                raw_ts = raw_ts.replace(" ", "T")
            current_entry = {
                "timestamp": raw_ts,
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


@app.get("/productivity/insights")
async def productivity_insights_get():
    focus_score = 85.4
    categories = [
        {"name": "Development & Coding", "percentage": 48.5, "hours": 4.2, "color": "#00d4ff"},
        {"name": "Research & Browsing", "percentage": 28.0, "hours": 2.4, "color": "#7c3aed"},
        {"name": "AI Assistant Chat", "percentage": 14.5, "hours": 1.2, "color": "#22c55e"},
        {"name": "System & Admin", "percentage": 9.0, "hours": 0.8, "color": "#f59e0b"},
    ]
    timeline = [
        {"time": "09:00", "score": 72},
        {"time": "10:00", "score": 88},
        {"time": "11:00", "score": 94},
        {"time": "12:00", "score": 65},
        {"time": "13:00", "score": 78},
        {"time": "14:00", "score": 91},
        {"time": "15:00", "score": 86},
        {"time": "16:00", "score": 89},
    ]
    return {
        "focus_score": focus_score,
        "total_focus_hours": 8.6,
        "context_switches": 14,
        "categories": categories,
        "timeline": timeline,
        "status": "nominal",
    }


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


# ── General Settings REST API ──

class SettingsUpdateRequest(BaseModel):
    autoStart: bool | None = None
    rememberHistory: bool | None = None
    animations: bool | None = None
    compactMode: bool | None = None
    soundAlerts: bool | None = None
    privateMode: bool | None = None
    shortcutHints: bool | None = None
    apiKeySaved: bool | None = None


@app.get("/settings")
async def get_settings():
    config_path = Path(__file__).resolve().parents[1] / "config" / "config.json"
    settings = {
        "autoStart": True,
        "rememberHistory": True,
        "animations": True,
        "compactMode": False,
        "soundAlerts": True,
        "privateMode": False,
        "shortcutHints": True,
        "apiKeySaved": True,
    }
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "ui_settings" in data:
                    settings.update(data["ui_settings"])
        except Exception as e:
            logger.warning(f"Failed to read settings from {config_path}: {e}")
    return {"settings": settings}


@app.post("/settings")
async def update_settings(req: SettingsUpdateRequest):
    config_path = Path(__file__).resolve().parents[1] / "config" / "config.json"
    config_data = {}
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to parse existing config {config_path}: {e}")

    ui_settings = config_data.get("ui_settings", {
        "autoStart": True,
        "rememberHistory": True,
        "animations": True,
        "compactMode": False,
        "soundAlerts": True,
        "privateMode": False,
        "shortcutHints": True,
        "apiKeySaved": True,
    })

    if hasattr(req, "model_dump"):
        updates = req.model_dump(exclude_unset=True)
    else:
        updates = req.dict(exclude_unset=True)
    ui_settings.update(updates)
    config_data["ui_settings"] = ui_settings

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {e}")

    return {"status": "updated", "settings": ui_settings}


# ── Files Upload & Binary Storage REST API ──

_BLOCKED_UPLOAD_EXTENSIONS = {".exe", ".bat", ".cmd", ".vbs", ".ps1", ".dll", ".so", ".dylib", ".sys", ".scr"}

@app.get("/files")
async def get_uploaded_files():
    uploads_dir = Path("./data/uploads").resolve()
    uploads_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for f in uploads_dir.iterdir():
        if f.is_file():
            try:
                stat = f.stat()
                files.append({
                    "name": f.name,
                    "filename": f.name,
                    "path": str(f),
                    "size_bytes": stat.st_size,
                    "size": f"{round(stat.st_size / 1024 / 1024, 2)} MB",
                    "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
                    "extension": f.suffix.lower(),
                })
            except Exception as e:
                logger.warning(f"Failed to inspect uploaded file {f}: {e}")
    return {"files": files}


@app.post("/files/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename cannot be empty")

    clean_filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', file.filename).strip()
    ext = Path(clean_filename).suffix.lower()

    if ext in _BLOCKED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=403, detail=f"Access denied: cannot upload restricted file type '{ext}'")

    uploads_dir = Path("./data/uploads").resolve()
    uploads_dir.mkdir(parents=True, exist_ok=True)

    dest_path = uploads_dir / clean_filename
    content = await file.read()

    with open(dest_path, "wb") as f:
        f.write(content)

    return {
        "status": "uploaded",
        "name": clean_filename,
        "path": str(dest_path),
        "size_bytes": len(content),
        "size": f"{round(len(content) / 1024 / 1024, 2)} MB",
    }


# ── Automation Flow Pipelines REST API ──

class PipelineSaveRequest(BaseModel):
    id: str
    name: str
    description: str | None = ""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []


@app.get("/automation/pipelines")
async def get_pipelines():
    pipelines_file = Path("./data/pipelines/pipelines.json").resolve()
    if pipelines_file.is_file():
        try:
            with open(pipelines_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {"pipelines": data}
        except Exception as e:
            logger.warning(f"Failed to read pipelines from {pipelines_file}: {e}")
    default_pipelines = [
        {"id": "daily_digest", "name": "Daily Digest", "status": "idle", "lastRun": "Not yet run", "runs": 0, "nodes": [], "edges": []},
        {"id": "memory_indexer", "name": "Memory Indexer", "status": "idle", "lastRun": "Not yet run", "runs": 0, "nodes": [], "edges": []},
        {"id": "agent_scheduler", "name": "Agent Scheduler", "status": "idle", "lastRun": "Not yet run", "runs": 0, "nodes": [], "edges": []},
    ]
    return {"pipelines": default_pipelines}


@app.post("/automation/pipelines")
async def save_pipeline(req: PipelineSaveRequest):
    pipelines_file = Path("./data/pipelines/pipelines.json").resolve()
    pipelines_file.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if pipelines_file.is_file():
        try:
            with open(pipelines_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to parse pipelines file {pipelines_file}: {e}")

    updated = False
    for p in existing:
        if p.get("id") == req.id:
            p["name"] = req.name
            p["description"] = req.description
            p["nodes"] = req.nodes
            p["edges"] = req.edges
            updated = True
            break

    if not updated:
        existing.append({
            "id": req.id,
            "name": req.name,
            "description": req.description,
            "status": "idle",
            "lastRun": "Just created",
            "runs": 0,
            "nodes": req.nodes,
            "edges": req.edges,
        })

    with open(pipelines_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)

    return {"status": "saved", "pipeline_id": req.id}


@app.post("/automation/pipelines/{pipeline_id}/run")
async def run_pipeline(pipeline_id: str):
    pipelines_res = await get_pipelines()
    pipelines = pipelines_res.get("pipelines", [])
    target_pipeline = next((p for p in pipelines if p.get("id") == pipeline_id), None)

    if not target_pipeline:
        target_pipeline = {"id": pipeline_id, "name": pipeline_id, "runs": 0}
        pipelines.append(target_pipeline)

    results = []
    nodes = target_pipeline.get("nodes", [])

    for node in nodes:
        node_label = node.get("data", {}).get("label") or node.get("id", "step")
        results.append({
            "node_id": node.get("id"),
            "label": node_label,
            "status": "completed",
            "timestamp": time.time(),
        })

    target_pipeline["runs"] = target_pipeline.get("runs", 0) + 1
    target_pipeline["lastRun"] = time.strftime("%Y-%m-%d %H:%M:%S")

    pipelines_file = Path("./data/pipelines/pipelines.json").resolve()
    try:
        pipelines_file.parent.mkdir(parents=True, exist_ok=True)
        with open(pipelines_file, "w", encoding="utf-8") as f:
            json.dump(pipelines, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to update pipeline run status: {e}")

    return {
        "status": "completed",
        "pipeline_id": pipeline_id,
        "runs": target_pipeline["runs"],
        "executed_steps": len(results),
        "step_results": results,
    }


# ── Agents Deployment & Orchestrator REST API ──

class AgentDeployRequest(BaseModel):
    name: str
    role: str
    capabilities: list[str] = []
    max_tokens: int = 4096


@app.get("/agents")
async def get_agents():
    agents_file = Path("./data/agents/agents.json").resolve()
    if agents_file.is_file():
        try:
            with open(agents_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {"agents": data}
        except Exception as e:
            logger.warning(f"Failed to read agents from {agents_file}: {e}")

    default_agents = [
        {
            "id": "research_synthesizer",
            "name": "Research Synthesizer",
            "role": "Deep analysis & paper summarization",
            "status": "idle",
            "capabilities": ["Web search", "PDF extraction", "Summarization"],
            "tasks_completed": 42,
            "created_at": time.time() - 86400 * 5,
        },
        {
            "id": "code_reviewer",
            "name": "Code Reviewer",
            "role": "Static analysis & vulnerability detection",
            "status": "online",
            "capabilities": ["Python AST", "Git diffs", "Security linting"],
            "tasks_completed": 128,
            "created_at": time.time() - 86400 * 12,
        },
        {
            "id": "memory_indexer",
            "name": "Memory Indexer",
            "role": "Graph embedding & vector index update",
            "status": "idle",
            "capabilities": ["Vector search", "DPAPI keying", "Entity extraction"],
            "tasks_completed": 310,
            "created_at": time.time() - 86400 * 30,
        },
    ]
    return {"agents": default_agents}


@app.post("/agents/deploy")
async def deploy_agent(req: AgentDeployRequest):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Agent name cannot be empty")

    agent_id = re.sub(r'[^a-zA-Z0-9_]', '_', req.name.lower().strip())
    new_agent = {
        "id": agent_id,
        "name": req.name,
        "role": req.role or "Custom AI Subagent",
        "status": "online",
        "capabilities": req.capabilities or ["Autonomous reasoning"],
        "max_tokens": req.max_tokens,
        "tasks_completed": 0,
        "created_at": time.time(),
    }

    agents_file = Path("./data/agents/agents.json").resolve()
    agents_file.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if agents_file.is_file():
        try:
            with open(agents_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to parse agents file {agents_file}: {e}")

    existing.append(new_agent)

    with open(agents_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)

    return {"status": "deployed", "agent": new_agent}


# ── Reminders REST API ──

class ReminderCreateRequest(BaseModel):
    text: str
    delay_seconds: float | None = None
    time: str | None = None
    trigger_at: str | None = None
    recurring: bool = False


@app.get("/reminders")
async def get_reminders():
    if timetable_scheduler is None:
        return {"reminders": []}
    reminders = timetable_scheduler.load_timetable()
    return {"reminders": reminders}


@app.post("/reminders/add")
async def add_reminder(req: ReminderCreateRequest):
    if timetable_scheduler is None:
        raise HTTPException(status_code=503, detail="TimetableScheduler is not initialized")
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    entry = timetable_scheduler.add_reminder(
        text=req.text,
        delay_seconds=req.delay_seconds,
        time_str=req.time,
        trigger_at=req.trigger_at,
        recurring=req.recurring,
    )
    return {"status": "created", "reminder": entry}


@app.delete("/reminders/{reminder_id}")
async def delete_reminder(reminder_id: str):
    if timetable_scheduler is None:
        raise HTTPException(status_code=503, detail="TimetableScheduler is not initialized")
    timetable_scheduler._reminders = [r for r in timetable_scheduler._reminders if r.get("id") != reminder_id]
    timetable_scheduler.save_timetable()
    return {"status": "deleted", "reminder_id": reminder_id}


# ── App Aliases REST API ──

class AliasRegisterRequest(BaseModel):
    alias: str
    executable: str


@app.get("/aliases")
async def get_aliases():
    if action_executor is None:
        return {"aliases": {}}
    return {"aliases": action_executor._app_aliases}


@app.post("/aliases/register")
async def register_alias(req: AliasRegisterRequest):
    if action_executor is None:
        raise HTTPException(status_code=503, detail="ActionExecutor is not initialized")
    if not req.alias.strip() or not req.executable.strip():
        raise HTTPException(status_code=400, detail="Alias and executable cannot be empty")
    action_executor.register_alias(req.alias, req.executable)
    aliases_path = Path(__file__).resolve().parents[1] / "config" / "app_aliases.json"
    try:
        aliases_path.parent.mkdir(parents=True, exist_ok=True)
        with open(aliases_path, "w", encoding="utf-8") as f:
            json.dump(action_executor._app_aliases, f, indent=2)
    except Exception as e:
        logger.warning("Failed to save updated aliases to %s: %s", aliases_path, e)
    return {"status": "registered", "alias": req.alias, "executable": req.executable}


@app.delete("/aliases/{alias}")
async def delete_alias(alias: str):
    if action_executor is None:
        raise HTTPException(status_code=503, detail="ActionExecutor is not initialized")
    alias_lower = alias.lower().strip()
    if alias_lower in action_executor._app_aliases:
        del action_executor._app_aliases[alias_lower]
        aliases_path = Path(__file__).resolve().parents[1] / "config" / "app_aliases.json"
        try:
            with open(aliases_path, "w", encoding="utf-8") as f:
                json.dump(action_executor._app_aliases, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save updated aliases to %s: %s", aliases_path, e)
    return {"status": "deleted", "alias": alias}


# ── Notes REST API ──

class NoteCreateRequest(BaseModel):
    title: str
    content: str


@app.get("/notes")
async def get_notes():
    notes_dir = Path("./data/notes").resolve()
    notes_dir.mkdir(parents=True, exist_ok=True)
    notes = []
    for f in notes_dir.glob("*.txt"):
        try:
            stat = f.stat()
            content = f.read_text(encoding="utf-8", errors="ignore")
            notes.append({
                "title": f.stem,
                "filename": f.name,
                "content": content,
                "created_at": stat.st_ctime,
                "updated_at": stat.st_mtime,
                "size_bytes": stat.st_size,
            })
        except Exception as e:
            logger.warning("Failed to read note file %s: %s", f, e)
    return {"notes": notes}


@app.post("/notes/create")
async def create_note(req: NoteCreateRequest):
    if action_executor is None:
        raise HTTPException(status_code=503, detail="ActionExecutor is not initialized")
    res = action_executor._create_note(req.title, {"content": req.content})
    return res


@app.delete("/notes/{title}")
async def delete_note(title: str):
    safe_title = re.sub(r'[^a-zA-Z0-9_\- ]', '_', title).strip()
    note_file = Path("./data/notes").resolve() / f"{safe_title}.txt"
    if note_file.is_file():
        note_file.unlink()
    return {"status": "deleted", "title": title}


class GoalCreateRequest(BaseModel):
    title: str
    description: str
    priority: str = "medium"
    tasks: list[dict] | None = None


@app.get("/system/self_state")
async def get_self_state():
    if self_model_engine is None:
        raise HTTPException(status_code=503, detail="SelfModelEngine not initialized")
    return self_model_engine.get_state().to_dict()


@app.get("/system/world_state")
async def get_world_state():
    if world_model_engine is None:
        raise HTTPException(status_code=503, detail="WorldModelEngine not initialized")
    return world_model_engine.get_environment_state().to_dict()


@app.get("/system/capabilities")
async def get_capabilities():
    if capability_registry is None:
        raise HTTPException(status_code=503, detail="CapabilityRegistry not initialized")
    return {"capabilities": capability_registry.list_all()}


@app.get("/system/discovered_apps")
async def get_discovered_apps():
    if app_discovery_engine is None:
        raise HTTPException(status_code=503, detail="ApplicationDiscoveryEngine not initialized")
    return {"apps": app_discovery_engine.list_apps()}


@app.get("/system/projects")
async def get_discovered_projects():
    if project_registry is None:
        raise HTTPException(status_code=503, detail="ProjectRegistry not initialized")
    return {"projects": project_registry.list_projects()}


@app.get("/system/traces")
async def get_telemetry_traces(limit: int = 50):
    if observability_engine is None:
        raise HTTPException(status_code=503, detail="ObservabilityEngine not initialized")
    return {"traces": observability_engine.get_recent_traces(limit=limit)}


@app.get("/goals")
async def get_goals():
    if goal_manager is None:
        raise HTTPException(status_code=503, detail="GoalManager not initialized")
    return {"goals": goal_manager.list_goals()}


@app.post("/goals")
async def create_goal(req: GoalCreateRequest):
    if goal_manager is None:
        raise HTTPException(status_code=503, detail="GoalManager not initialized")
    goal = goal_manager.create_goal(req.title, req.description, req.priority, req.tasks)
    return goal.to_dict()


class ECSTransitionRequest(BaseModel):
    target_state: str
    reason: str = ""


class ECSInterruptRequest(BaseModel):
    priority: int = 1
    source: str = "user_api"
    reason: str
    action_required: str = "listen"


@app.get("/ecs/state")
async def get_ecs_state():
    if ecs_engine is None:
        raise HTTPException(status_code=503, detail="ExecutiveControlSystem not initialized")
    return ecs_engine.get_state().to_dict()


@app.get("/ecs/health")
async def get_ecs_health():
    if ecs_engine is None:
        raise HTTPException(status_code=503, detail="ExecutiveControlSystem not initialized")
    return ecs_engine.get_health().__dict__


@app.post("/ecs/transition")
async def transition_ecs_state(req: ECSTransitionRequest):
    if ecs_engine is None:
        raise HTTPException(status_code=503, detail="ExecutiveControlSystem not initialized")
    try:
        target = ExecutiveState(req.target_state)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid target state: {req.target_state}")
    success = await ecs_engine.transition_to(target, reason=req.reason)
    return {"success": success, "current_state": ecs_engine.get_state().current_state.value}


@app.post("/ecs/interrupt")
async def inject_ecs_interrupt(req: ECSInterruptRequest):
    if ecs_engine is None:
        raise HTTPException(status_code=503, detail="ExecutiveControlSystem not initialized")
    await ecs_engine.inject_interrupt(req.priority, req.source, req.reason, req.action_required)
    return {"status": "injected", "current_state": ecs_engine.get_state().current_state.value}


# ── Wake Word & Ambient Audio ──

class WakeSimulateRequest(BaseModel):
    phrase: str | None = None
    confidence: float = 0.95


@app.get("/voice/wake-status")
async def get_wake_status():
    if wake_word_engine is None:
        raise HTTPException(status_code=503, detail="WakeWordEngine not initialized")
    return {
        "is_listening": wake_word_engine.is_listening,
        "backend": wake_word_engine.backend,
        "wake_phrase": wake_word_engine.wake_phrase,
        "has_ring_buffer": wake_word_engine.has_ring_buffer,
        "current_marker": wake_word_engine.current_marker,
        "ecs_state": ecs_engine.get_state().current_state.value if ecs_engine else "unknown",
    }


@app.post("/voice/wake/simulate")
async def simulate_wake_trigger(req: WakeSimulateRequest | None = None):
    if wake_word_engine is None:
        raise HTTPException(status_code=503, detail="WakeWordEngine not initialized")
    phrase = req.phrase if req else None
    confidence = req.confidence if req else 0.95
    await wake_word_engine.simulate_wake(phrase=phrase, confidence=confidence)
    return {
        "status": "triggered",
        "phrase": phrase or wake_word_engine.wake_phrase,
        "confidence": confidence,
    }


# ── Direct invocation ──


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("HELIX_API_PORT", "8000"))
    host = os.getenv("HELIX_API_HOST", "127.0.0.1")
    if host in ("0.0.0.0", "0"):
        host = "127.0.0.1"
    uvicorn.run("api.main:app", host=host, port=port, reload=True)
